//go:build windows

package capability

// 本文件实现 Windows 平台的文件系统能力（windows.fs.read / write / list）。
//
// 设计对照 Linux 侧 linux_fs_linux.go，保持参数与返回结构一致：
//   - read：path/offset/limit/encoding → content/truncated/is_binary/encoding…
//   - write：path/content/encoding/append/create_dirs/mode → written_bytes/created/appended
//   - list：path/recursive/max_depth/show_hidden/limit → entries/count/truncated
//
// 与 Linux 的差异：
//   - mode（Unix 权限八进制）在 Windows 上无意义：接受该参数但忽略，并在返回
//     结果中标注 mode_ignored=true，避免调用方误以为权限被设置。
//   - 隐藏项判定：Windows 用 FILE_ATTRIBUTE_HIDDEN 属性，而非「以 . 开头」。
//     这里两者都算隐藏（点开头是跨平台习惯，属性是 Windows 原生语义）。
//
// 注意：本机开发环境为 Linux，无 Windows 运行环境，因此本文件只能保证
// 「在 GOOS=windows 下编译通过」，成功路径未做端到端验证。

import (
	"encoding/base64"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"
)

// Windows 文件系统能力的默认与上限约束（与 Linux 侧保持同一量级）。
const (
	// windowsFSDefaultReadLimit 是 windows.fs.read 未指定 limit 时的默认读取字节数。
	windowsFSDefaultReadLimit = 1 << 20 // 1 MiB
	// windowsFSMaxReadLimit 是 windows.fs.read 允许的最大读取字节数，防止一次读取撑爆内存。
	windowsFSMaxReadLimit = 8 << 20 // 8 MiB
	// windowsFSDefaultListLimit 是 windows.fs.list 未指定 limit 时的默认条目数上限。
	windowsFSDefaultListLimit = 500
	// windowsFSMaxListLimit 是 windows.fs.list 允许的最大条目数上限。
	windowsFSMaxListLimit = 10000
)

// registerWindowsFS 注册 Windows 文件系统能力。
func registerWindowsFS(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.fs.read",
		Description: "读取 Windows 上的文件内容。支持按 offset/limit 分段读取，" +
			"内容含 NUL 字节或非合法 UTF-8 时自动按 base64 返回并置 is_binary=true。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "要读取的文件路径（绝对路径或相对守护进程工作目录），如 C:\\Users\\me\\a.txt。",
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
		Handler: handleWindowsFSRead,
	})

	_ = reg.Register(Capability{
		Name: "windows.fs.write",
		Description: "写入 Windows 上的文件内容。支持覆盖/追加与自动创建父目录。" +
			"注意：mode 参数在 Windows 上无意义，会被忽略（结果中标注 mode_ignored=true）。",
		Platform: PlatformWindows,
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
					"description": "文件权限八进制字符串（仅为与 Linux 侧参数对齐；Windows 上被忽略）。",
				},
			},
			"required": []string{"path", "content"},
		},
		Handler: handleWindowsFSWrite,
	})

	_ = reg.Register(Capability{
		Name:        "windows.fs.list",
		Description: "列出 Windows 上目录的内容，支持递归与深度限制。隐藏项按点开头或 FILE_ATTRIBUTE_HIDDEN 属性判定。",
		Platform:    PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "要列出的目录路径，如 C:\\Users\\me。",
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
					"description": "是否包含隐藏项（点开头或带隐藏属性），默认 true。",
				},
				"limit": map[string]any{
					"type":        "integer",
					"description": "返回条目数上限，默认 500，最大 10000。",
				},
			},
			"required": []string{"path"},
		},
		Handler: handleWindowsFSList,
	})
}

// handleWindowsFSRead 是 windows.fs.read 的实现。
func handleWindowsFSRead(params map[string]any) (any, error) {
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

	limit, err := optionalInt(params, "limit", windowsFSDefaultReadLimit)
	if err != nil {
		return nil, err
	}
	if limit <= 0 {
		return nil, fmt.Errorf("参数 limit 必须为正整数，实际 %d", limit)
	}
	if limit > windowsFSMaxReadLimit {
		return nil, fmt.Errorf("参数 limit 超出上限 %d 字节，实际 %d", windowsFSMaxReadLimit, limit)
	}

	encoding, err := resolveWindowsFSEncoding(params, "utf-8")
	if err != nil {
		return nil, err
	}

	info, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("读取文件 %s 失败: %w", path, err)
	}
	if info.IsDir() {
		return nil, fmt.Errorf("路径 %s 是目录，不能用 windows.fs.read 读取，请改用 windows.fs.list", path)
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

	isBinary := isBinaryWindowsContent(data)
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
		"encoding":   chooseWindowsReportedEncoding(encoding, isBinary),
	}, nil
}

// handleWindowsFSWrite 是 windows.fs.write 的实现。
func handleWindowsFSWrite(params map[string]any) (any, error) {
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

	encoding, err := resolveWindowsFSEncoding(params, "utf-8")
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

	// mode 仅为与 Linux 侧参数对齐而保留：Windows 无 Unix 权限位，忽略其值。
	modeStr, err := optionalString(params, "mode")
	if err != nil {
		return nil, err
	}
	modeIgnored := modeStr != ""

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

	// Windows 忽略权限位，这里传 0o666 交由系统默认（受 umask/ACL 影响）。
	f, err := os.OpenFile(path, flags, 0o666)
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
		"mode_ignored":  modeIgnored,
	}, nil
}

// handleWindowsFSList 是 windows.fs.list 的实现。
func handleWindowsFSList(params map[string]any) (any, error) {
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

	limit, err := optionalInt(params, "limit", windowsFSDefaultListLimit)
	if err != nil {
		return nil, err
	}
	if limit <= 0 {
		return nil, fmt.Errorf("参数 limit 必须为正整数，实际 %d", limit)
	}
	if limit > windowsFSMaxListLimit {
		return nil, fmt.Errorf("参数 limit 超出上限 %d，实际 %d", windowsFSMaxListLimit, limit)
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

	truncated, err := collectWindowsFSEntries(path, 1, maxDepth, showHidden, limit, &entries)
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

// collectWindowsFSEntries 递归收集目录条目，达到 limit 时提前返回并置 truncated。
//
// depth 是当前层深度（从 1 开始），maxDepth 是允许的最大深度。
func collectWindowsFSEntries(dir string, depth, maxDepth int, showHidden bool, limit int, out *[]map[string]any) (bool, error) {
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

		// 用 Lstat 以便识别符号链接本身而不是其目标。
		fullPath := filepath.Join(dir, name)
		li, statErr := os.Lstat(fullPath)

		hidden := strings.HasPrefix(name, ".")
		if statErr == nil && isWindowsHidden(li) {
			hidden = true
		}
		if !showHidden && hidden {
			continue
		}

		entry := map[string]any{
			"name":     name,
			"path":     fullPath,
			"is_dir":   item.IsDir(),
			"hidden":   hidden,
			"mod_time": "",
			"size":     int64(0),
			"mode":     "",
		}

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
			truncated, err := collectWindowsFSEntries(fullPath, depth+1, maxDepth, showHidden, limit, out)
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

// isWindowsHidden 判断文件是否带 Windows 隐藏属性（FILE_ATTRIBUTE_HIDDEN）。
//
// 仅用标准库 syscall（kernel32!GetFileAttributesW），不引入 golang.org/x/sys。
// fs.FileInfo 的 Sys() 在 Windows 上返回 *syscall.Win32FileAttributeData，
// 其 FileAttributes 字段即包含隐藏属性位。类型断言失败时返回 false，
// 由调用方的「点开头」判定兜底。
func isWindowsHidden(info fs.FileInfo) bool {
	if info == nil {
		return false
	}
	data, ok := info.Sys().(*syscall.Win32FileAttributeData)
	if !ok {
		return false
	}
	return data.FileAttributes&syscall.FILE_ATTRIBUTE_HIDDEN != 0
}
