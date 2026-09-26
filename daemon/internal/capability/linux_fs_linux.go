//go:build linux

package capability

import (
	"encoding/base64"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

// 文件系统能力的默认与上限约束。
const (
	// linuxFSDefaultReadLimit 是 linux.fs.read 未指定 limit 时的默认读取字节数。
	linuxFSDefaultReadLimit = 1 << 20 // 1 MiB
	// linuxFSMaxReadLimit 是 linux.fs.read 允许的最大读取字节数，防止一次读取撑爆内存。
	linuxFSMaxReadLimit = 8 << 20 // 8 MiB
	// linuxFSDefaultListLimit 是 linux.fs.list 未指定 limit 时的默认条目数上限。
	linuxFSDefaultListLimit = 500
	// linuxFSMaxListLimit 是 linux.fs.list 允许的最大条目数上限。
	linuxFSMaxListLimit = 10000
	// linuxFSDefaultMode 是 linux.fs.write 未指定 mode 时的默认文件权限（八进制字符串）。
	linuxFSDefaultMode = "0644"
)

// registerLinuxFS 注册 Linux 文件系统能力。
func registerLinuxFS(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "linux.fs.read",
		Description: "读取 Linux 上的文件内容。支持按 offset/limit 分段读取，" +
			"内容含 NUL 字节时自动按 base64 返回并置 is_binary=true。",
		Platform: PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "要读取的文件路径（绝对路径或相对守护进程工作目录）。",
				},
				"offset": map[string]any{
					"type":        "integer",
					"description": "起始偏移字节数，默认 0。",
				},
				"limit": map[string]any{
					"type":        "integer",
					"description": "最多读取字节数，默认 1048576（1 MiB），最大 8388608（8 MiB）。",
				},
				"encoding": map[string]any{
					"type":        "string",
					"description": "返回内容的编码，支持 utf-8（默认）与 base64。",
				},
			},
			"required": []string{"path"},
		},
		Handler: handleLinuxFSRead,
	})

	_ = reg.Register(Capability{
		Name:        "linux.fs.write",
		Description: "写入 Linux 上的文件内容。支持覆盖/追加、自动创建父目录与自定义权限。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "要写入的文件路径。",
				},
				"content": map[string]any{
					"type":        "string",
					"description": "要写入的内容；encoding=base64 时按 base64 解码后写入。",
				},
				"encoding": map[string]any{
					"type":        "string",
					"description": "content 的编码，支持 utf-8（默认）与 base64。",
				},
				"append": map[string]any{
					"type":        "boolean",
					"description": "是否追加写入，默认 false（覆盖）。",
				},
				"create_dirs": map[string]any{
					"type":        "boolean",
					"description": "是否自动创建父目录，默认 false。",
				},
				"mode": map[string]any{
					"type":        "string",
					"description": "文件权限的八进制字符串，默认 0644；仅在新建文件时生效。",
				},
			},
			"required": []string{"path", "content"},
		},
		Handler: handleLinuxFSWrite,
	})

	_ = reg.Register(Capability{
		Name:        "linux.fs.list",
		Description: "列出 Linux 上目录的内容，支持递归与深度限制。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "要列出的目录路径。",
				},
				"recursive": map[string]any{
					"type":        "boolean",
					"description": "是否递归列出子目录，默认 false。",
				},
				"max_depth": map[string]any{
					"type":        "integer",
					"description": "递归时的最大深度，默认 1（仅当前层）；recursive=false 时忽略。",
				},
				"show_hidden": map[string]any{
					"type":        "boolean",
					"description": "是否包含以 . 开头的隐藏项，默认 true。",
				},
				"limit": map[string]any{
					"type":        "integer",
					"description": "返回条目数上限，默认 500，最大 10000。",
				},
			},
			"required": []string{"path"},
		},
		Handler: handleLinuxFSList,
	})
}

// handleLinuxFSRead 是 linux.fs.read 的实现。
func handleLinuxFSRead(params map[string]any) (any, error) {
	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}

	offset, err := optionalInt(params, "offset", 0)
	if err != nil {
		return nil, err
	}
	if offset < 0 {
		return nil, fmt.Errorf("参数 offset 不能为负数，实际 %d", offset)
	}

	limit, err := optionalInt(params, "limit", linuxFSDefaultReadLimit)
	if err != nil {
		return nil, err
	}
	if limit <= 0 {
		return nil, fmt.Errorf("参数 limit 必须为正整数，实际 %d", limit)
	}
	if limit > linuxFSMaxReadLimit {
		return nil, fmt.Errorf("参数 limit 超出上限 %d 字节，实际 %d", linuxFSMaxReadLimit, limit)
	}

	encoding, err := resolveFSEncoding(params, "utf-8")
	if err != nil {
		return nil, err
	}

	info, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("读取文件 %s 失败: %w", path, err)
	}
	if info.IsDir() {
		return nil, fmt.Errorf("路径 %s 是目录，不能用 linux.fs.read 读取，请改用 linux.fs.list", path)
	}

	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("打开文件 %s 失败: %w", path, err)
	}
	defer f.Close()

	if offset > 0 {
		if _, err := f.Seek(int64(offset), io.SeekStart); err != nil {
			return nil, fmt.Errorf("定位到偏移 %d 失败: %w", offset, err)
		}
	}

	// 多读 1 字节用于判断是否还有剩余内容（即是否发生截断）。
	buf := make([]byte, limit+1)
	n, err := io.ReadFull(f, buf)
	if err != nil && err != io.EOF && err != io.ErrUnexpectedEOF {
		return nil, fmt.Errorf("读取文件 %s 失败: %w", path, err)
	}

	truncated := false
	if n > limit {
		n = limit
		truncated = true
	}
	data := buf[:n]

	isBinary := isBinaryContent(data)
	content := string(data)
	if isBinary && encoding == "utf-8" {
		// 二进制内容无法用 UTF-8 安全表示，自动降级为 base64。
		content = base64.StdEncoding.EncodeToString(data)
	} else if encoding == "base64" {
		content = base64.StdEncoding.EncodeToString(data)
	}

	return map[string]any{
		"path":       path,
		"size":       info.Size(),
		"offset":     offset,
		"read_bytes": n,
		"content":    content,
		"truncated":  truncated,
		"is_binary":  isBinary,
		"encoding":   chooseReportedEncoding(encoding, isBinary),
	}, nil
}

// handleLinuxFSWrite 是 linux.fs.write 的实现。
func handleLinuxFSWrite(params map[string]any) (any, error) {
	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}

	// content 允许为空字符串（例如创建空文件），因此这里不用 requiredString。
	rawContent, ok := params["content"]
	if !ok || rawContent == nil {
		return nil, fmt.Errorf("缺少必填参数 content")
	}
	contentStr, ok := rawContent.(string)
	if !ok {
		return nil, fmt.Errorf("参数 content 必须是字符串，实际 %T", rawContent)
	}

	encoding, err := resolveFSEncoding(params, "utf-8")
	if err != nil {
		return nil, err
	}

	appendMode, err := optionalBool(params, "append", false)
	if err != nil {
		return nil, err
	}

	createDirs, err := optionalBool(params, "create_dirs", false)
	if err != nil {
		return nil, err
	}

	modeStr, err := optionalString(params, "mode")
	if err != nil {
		return nil, err
	}
	if modeStr == "" {
		modeStr = linuxFSDefaultMode
	}
	mode, err := parseFileMode(modeStr)
	if err != nil {
		return nil, err
	}

	var payload []byte
	if encoding == "base64" {
		decoded, err := base64.StdEncoding.DecodeString(strings.TrimSpace(contentStr))
		if err != nil {
			return nil, fmt.Errorf("参数 content 不是合法的 base64: %w", err)
		}
		payload = decoded
	} else {
		payload = []byte(contentStr)
	}

	_, statErr := os.Stat(path)
	existed := statErr == nil

	if createDirs {
		dir := filepath.Dir(path)
		if dir != "" && dir != "." {
			if err := os.MkdirAll(dir, 0o755); err != nil {
				return nil, fmt.Errorf("创建父目录 %s 失败: %w", dir, err)
			}
		}
	}

	flags := os.O_WRONLY | os.O_CREATE
	if appendMode {
		flags |= os.O_APPEND
	} else {
		flags |= os.O_TRUNC
	}

	f, err := os.OpenFile(path, flags, mode)
	if err != nil {
		return nil, fmt.Errorf("打开文件 %s 失败: %w", path, err)
	}

	written, writeErr := f.Write(payload)
	closeErr := f.Close()
	if writeErr != nil {
		return nil, fmt.Errorf("写入文件 %s 失败: %w", path, writeErr)
	}
	if closeErr != nil {
		return nil, fmt.Errorf("关闭文件 %s 失败: %w", path, closeErr)
	}

	return map[string]any{
		"path":          path,
		"written_bytes": written,
		"created":       !existed,
		"appended":      appendMode,
	}, nil
}

// handleLinuxFSList 是 linux.fs.list 的实现。
func handleLinuxFSList(params map[string]any) (any, error) {
	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}

	recursive, err := optionalBool(params, "recursive", false)
	if err != nil {
		return nil, err
	}

	maxDepth, err := optionalInt(params, "max_depth", 1)
	if err != nil {
		return nil, err
	}
	if maxDepth <= 0 {
		return nil, fmt.Errorf("参数 max_depth 必须为正整数，实际 %d", maxDepth)
	}

	showHidden, err := optionalBool(params, "show_hidden", true)
	if err != nil {
		return nil, err
	}

	limit, err := optionalInt(params, "limit", linuxFSDefaultListLimit)
	if err != nil {
		return nil, err
	}
	if limit <= 0 {
		return nil, fmt.Errorf("参数 limit 必须为正整数，实际 %d", limit)
	}
	if limit > linuxFSMaxListLimit {
		return nil, fmt.Errorf("参数 limit 超出上限 %d，实际 %d", linuxFSMaxListLimit, limit)
	}

	info, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("访问路径 %s 失败: %w", path, err)
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("路径 %s 不是目录", path)
	}

	// 非递归时深度固定为 1，即只列当前层。
	if !recursive {
		maxDepth = 1
	}

	entries := make([]map[string]any, 0, 16)

	truncated, err := collectFSEntries(path, 1, maxDepth, showHidden, limit, &entries)
	if err != nil {
		return nil, err
	}

	sort.Slice(entries, func(i, j int) bool {
		return entries[i]["path"].(string) < entries[j]["path"].(string)
	})

	return map[string]any{
		"path":      path,
		"entries":   entries,
		"count":     len(entries),
		"truncated": truncated,
	}, nil
}

// collectFSEntries 递归收集目录条目，达到 limit 时提前返回并置 truncated。
//
// depth 是当前层深度（从 1 开始），maxDepth 是允许的最大深度。
func collectFSEntries(dir string, depth, maxDepth int, showHidden bool, limit int, out *[]map[string]any) (bool, error) {
	if depth > maxDepth {
		return false, nil
	}

	items, err := os.ReadDir(dir)
	if err != nil {
		// 子目录读不到（权限等）时跳过，不中断整体列举。
		if depth == 1 {
			return false, fmt.Errorf("读取目录 %s 失败: %w", dir, err)
		}
		return false, nil
	}

	for _, item := range items {
		if len(*out) >= limit {
			return true, nil
		}

		name := item.Name()
		if !showHidden && strings.HasPrefix(name, ".") {
			continue
		}

		fullPath := filepath.Join(dir, name)
		entry := map[string]any{
			"name":     name,
			"path":     fullPath,
			"is_dir":   item.IsDir(),
			"mod_time": "",
			"size":     int64(0),
			"mode":     "",
		}

		// 用 Lstat 以便识别符号链接本身而不是其目标。
		li, statErr := os.Lstat(fullPath)
		if statErr == nil {
			entry["size"] = li.Size()
			entry["mode"] = li.Mode().String()
			entry["mod_time"] = li.ModTime().Format(time.RFC3339)
			if li.Mode()&os.ModeSymlink != 0 {
				entry["is_dir"] = false
				if target, err := os.Readlink(fullPath); err == nil {
					entry["symlink_target"] = target
				}
			}
		}

		*out = append(*out, entry)

		if item.IsDir() && depth < maxDepth {
			truncated, err := collectFSEntries(fullPath, depth+1, maxDepth, showHidden, limit, out)
			if err != nil {
				return false, err
			}
			if truncated {
				return true, nil
			}
		}
	}

	return false, nil
}

// resolveFSEncoding 解析并校验 encoding 参数，只允许 utf-8 与 base64。
func resolveFSEncoding(params map[string]any, def string) (string, error) {
	raw, err := optionalString(params, "encoding")
	if err != nil {
		return "", err
	}
	if raw == "" {
		return def, nil
	}
	switch strings.ToLower(raw) {
	case "utf-8", "utf8":
		return "utf-8", nil
	case "base64":
		return "base64", nil
	default:
		return "", fmt.Errorf("参数 encoding 不支持 %q，允许值: utf-8、base64", raw)
	}
}

// chooseReportedEncoding 返回实际用于表示 content 的编码。
func chooseReportedEncoding(requested string, isBinary bool) string {
	if isBinary && requested == "utf-8" {
		return "base64"
	}
	return requested
}

// parseFileMode 解析八进制权限字符串，如 "0644"、"755"。
func parseFileMode(s string) (fs.FileMode, error) {
	trimmed := strings.TrimSpace(s)
	trimmed = strings.TrimPrefix(trimmed, "0o")
	trimmed = strings.TrimPrefix(trimmed, "0O")

	parsed, err := strconv.ParseUint(trimmed, 8, 32)
	if err != nil {
		return 0, fmt.Errorf("参数 mode 不是合法的八进制权限值: %q", s)
	}
	if parsed > 0o7777 {
		return 0, fmt.Errorf("参数 mode 超出范围（最大 07777）: %q", s)
	}
	return fs.FileMode(parsed), nil
}

// isBinaryContent 判断内容是否为二进制。
//
// 判定依据：含 NUL 字节，或不是合法的 UTF-8 编码。
func isBinaryContent(data []byte) bool {
	if len(data) == 0 {
		return false
	}
	if strings.IndexByte(string(data), 0) >= 0 {
		return true
	}
	return !utf8.Valid(data)
}

// optionalBool 读取可选布尔参数；缺失或为 nil 时返回默认值。
func optionalBool(params map[string]any, key string, def bool) (bool, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return def, nil
	}
	b, ok := v.(bool)
	if !ok {
		return false, fmt.Errorf("参数 %s 必须是布尔值，实际 %T", key, v)
	}
	return b, nil
}
