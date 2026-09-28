// 本文件实现「跨机文件直传」能力的公共核心：把本机文件（或目录）推到远端节点，
// 或从远端节点拉回本机。与既有 fs.transfer.read/write 的关键区别：
//
//   - fs.transfer.read/write 是「积木」：每次只搬一块，字节要经过调用方（Agent）上下文；
//   - fs.transfer.push/pull 是「整机搬运」：daemon 内部循环分块，字节只在 daemon 与
//     网关之间流动，调用方（Agent）只拿到一份摘要（路径、大小、sha256），
//     因此搬运 512 MiB 文件也不会撑爆上下文。
//
// 数据通路：
//
//	本机 daemon --(HTTP, 带网关 Token)--> 网关 /api/node/{node_id}/file-transfer/{upload|download}
//	                                        --(WebSocket)--> 目标节点落盘/打包
//
// 重要：本文件**不带构建标签**，会被编译进所有平台，因此只能使用标准库，
// 且不得引用平台专有符号（requiredString 等）。参数读取统一用 transfer.go 里的
// transferParamString / transferParamInt64。
package capability

import (
	"archive/tar"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"jarvis-daemon/internal/proxy"
)

// transferRemoteTimeout 是单次分块 HTTP 请求的超时时间。
//
// 取值理由：单块最大 8 MiB（base64 后约 10.7 MiB），即使跨公网也应在 60s 内完成；
// 超时过短会误杀慢链路，过长则卡住整个 push/pull 循环。
const transferRemoteTimeout = 60 * time.Second

// transferRemoteMaxFileSize 是单次直传允许的最大字节数（512 MiB），与既有
// TransferMaxFileSize 保持一致，避免两套语义漂移。
const transferRemoteMaxFileSize = TransferMaxFileSize

// transferRemoteResult 是 push/pull 返回给调用方的摘要结构。
//
// 刻意只含元信息，不含任何文件内容字节，保证 Agent 上下文不被污染。
type transferRemoteResult struct {
	Direction  string `json:"direction"`   // "push" 或 "pull"
	Gateway    string `json:"gateway"`     // 网关地址
	NodeID     string `json:"node_id"`     // 目标节点 ID
	Mode       string `json:"mode"`        // "file" 或 "dir"
	LocalPath  string `json:"local_path"`  // 本机路径
	RemotePath string `json:"remote_path"` // 远端（节点侧收敛后）路径
	Size       int64  `json:"size"`        // 传输字节数（目录为 tar 包大小）
	SHA256     string `json:"sha256"`      // 整包 SHA-256（小写十六进制）
	Chunks     int    `json:"chunks"`      // 分块次数
	ChunkSize  int    `json:"chunk_size"`  // 每块字节数
}

// transferRemoteParams 是从能力参数中解析出的规范化入参。
type transferRemoteParams struct {
	Gateway    string
	NodeID     string
	LocalPath  string
	RemotePath string
	Mode       string
	ChunkSize  int
}

// parseTransferRemoteParams 解析并校验 push/pull 的公共参数。
//
// 必填：gateway、node_id、local_path、remote_path。
// 可选：mode（file|dir，缺省时按 local_path 是否为目录自动推断）、chunk_size。
func parseTransferRemoteParams(params map[string]any) (*transferRemoteParams, error) {
	gateway, err := transferParamString(params, "gateway")
	if err != nil {
		return nil, err
	}
	gateway = strings.TrimRight(gateway, "/")
	if !strings.HasPrefix(gateway, "http://") && !strings.HasPrefix(gateway, "https://") {
		return nil, fmt.Errorf("参数 gateway 必须以 http:// 或 https:// 开头，实际 %s", gateway)
	}

	nodeID, err := transferParamString(params, "node_id")
	if err != nil {
		return nil, err
	}

	localPath, err := transferParamString(params, "local_path")
	if err != nil {
		return nil, err
	}

	remotePath, err := transferParamString(params, "remote_path")
	if err != nil {
		return nil, err
	}

	mode := strings.ToLower(strings.TrimSpace(stringOrEmpty(params, "mode")))
	if mode == "" {
		// 未显式指定时按本机路径类型推断；push 场景下本机是权威来源。
		info, statErr := os.Stat(localPath)
		if statErr == nil && info.IsDir() {
			mode = "dir"
		} else {
			mode = "file"
		}
	}
	if mode != "file" && mode != "dir" {
		return nil, fmt.Errorf("参数 mode 只能是 file 或 dir，实际 %s", mode)
	}

	chunkSize, err := transferParamInt64(params, "chunk_size", int64(TransferDefaultChunkSize))
	if err != nil {
		return nil, err
	}
	normalized, err := NormalizeTransferChunkSize(int(chunkSize))
	if err != nil {
		return nil, err
	}

	return &transferRemoteParams{
		Gateway:    gateway,
		NodeID:     nodeID,
		LocalPath:  localPath,
		RemotePath: remotePath,
		Mode:       mode,
		ChunkSize:  normalized,
	}, nil
}

// stringOrEmpty 读取可选字符串参数，缺失或非字符串时返回空串。
func stringOrEmpty(params map[string]any, key string) string {
	v, ok := params[key]
	if !ok || v == nil {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		return ""
	}
	return s
}

// transferRemoteURL 拼接网关上的节点文件直传端点地址。
func transferRemoteURL(gateway, nodeID, action string) string {
	return fmt.Sprintf("%s/api/node/%s/file-transfer/%s", gateway, nodeID, action)
}

// transferRemotePost 向网关发起一次带 Token 的 POST 请求，返回解析后的响应体。
//
// 网关响应统一形如 {"success":bool,"data":{...}} 或 {"success":false,"error":{...}}；
// 本函数在 HTTP 非 200 或 success=false 时返回带上下文的错误。
func transferRemotePost(gateway, token, url string, payload map[string]any) (map[string]any, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("序列化请求体失败: %w", err)
	}

	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("构造请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)

	client := &http.Client{Timeout: transferRemoteTimeout, Transport: proxy.Transport()}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("请求 %s 失败: %w", url, err)
	}
	defer resp.Body.Close()

	// 响应体可能较大（下载分块含 base64 内容），但受单块上限约束，这里给 32 MiB 余量。
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	if err != nil {
		return nil, fmt.Errorf("读取 %s 响应失败: %w", url, err)
	}

	var parsed map[string]any
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return nil, fmt.Errorf("解析 %s 响应失败（HTTP %d）: %s",
			url, resp.StatusCode, strings.TrimSpace(string(raw)))
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("请求 %s 失败（HTTP %d）: %v",
			url, resp.StatusCode, parsed["error"])
	}
	if ok, _ := parsed["success"].(bool); !ok {
		return nil, fmt.Errorf("请求 %s 被拒绝: %v", url, parsed["error"])
	}
	return parsed, nil
}

// transferRemoteData 从网关响应中取出 data 子对象。
func transferRemoteData(resp map[string]any) (map[string]any, error) {
	data, ok := resp["data"].(map[string]any)
	if !ok {
		return nil, fmt.Errorf("响应缺少 data 字段: %v", resp)
	}
	return data, nil
}

// transferRemoteInt64 从 data 中读取整数字段（JSON 数字为 float64）。
func transferRemoteInt64(data map[string]any, key string) (int64, error) {
	v, ok := data[key]
	if !ok || v == nil {
		return 0, fmt.Errorf("响应缺少字段 %s", key)
	}
	switch n := v.(type) {
	case float64:
		return int64(n), nil
	case int64:
		return n, nil
	case int:
		return int64(n), nil
	default:
		return 0, fmt.Errorf("字段 %s 不是数字: %T", key, v)
	}
}

// transferPackDirToTar 把目录打包为 tar 字节流，顶层目录名取目录 basename。
//
// 打包到内存而非临时文件：单次直传上限 512 MiB，且只在 push 前调用一次，
// 换取实现简单与无残留临时文件。
func transferPackDirToTar(dir string) ([]byte, error) {
	absDir, err := filepath.Abs(dir)
	if err != nil {
		return nil, fmt.Errorf("解析目录绝对路径失败: %w", err)
	}
	base := filepath.Base(absDir)

	var buf bytes.Buffer
	tw := tar.NewWriter(&buf)

	walkErr := filepath.Walk(absDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(absDir, path)
		if err != nil {
			return err
		}
		if rel == "." {
			return nil
		}
		// tar 内路径统一用正斜杠，且以目录 basename 为顶层。
		name := base + "/" + filepath.ToSlash(rel)

		hdr, err := tar.FileInfoHeader(info, "")
		if err != nil {
			return err
		}
		hdr.Name = name
		if info.IsDir() {
			hdr.Name += "/"
		}
		if err := tw.WriteHeader(hdr); err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}

		f, err := os.Open(path)
		if err != nil {
			return err
		}
		defer f.Close()
		if _, err := io.Copy(tw, f); err != nil {
			return err
		}
		return nil
	})
	if walkErr != nil {
		return nil, fmt.Errorf("打包目录 %s 失败: %w", dir, walkErr)
	}
	if err := tw.Close(); err != nil {
		return nil, fmt.Errorf("关闭 tar 写入器失败: %w", err)
	}
	return buf.Bytes(), nil
}

// transferUnpackTarToDir 把 tar 字节流解包到目标目录。
//
// 安全：拒绝任何逃出目标目录的成员（防 tar 穿越），与网关侧 _safe_extract_tar 同义。
func transferUnpackTarToDir(data []byte, destDir string) error {
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return fmt.Errorf("创建目录 %s 失败: %w", destDir, err)
	}
	root, err := filepath.Abs(destDir)
	if err != nil {
		return fmt.Errorf("解析目录绝对路径失败: %w", err)
	}

	tr := tar.NewReader(bytes.NewReader(data))
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return fmt.Errorf("读取 tar 失败: %w", err)
		}

		target := filepath.Join(root, filepath.FromSlash(hdr.Name))
		rel, err := filepath.Rel(root, target)
		if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			return fmt.Errorf("tar 成员 %s 逃出目标目录 %s", hdr.Name, destDir)
		}

		switch hdr.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(target, 0o755); err != nil {
				return fmt.Errorf("创建目录 %s 失败: %w", target, err)
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return fmt.Errorf("创建目录 %s 失败: %w", filepath.Dir(target), err)
			}
			out, err := os.OpenFile(target, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, os.FileMode(hdr.Mode)&0o777)
			if err != nil {
				return fmt.Errorf("创建文件 %s 失败: %w", target, err)
			}
			if _, err := io.Copy(out, tr); err != nil {
				out.Close()
				return fmt.Errorf("写入文件 %s 失败: %w", target, err)
			}
			if err := out.Close(); err != nil {
				return fmt.Errorf("关闭文件 %s 失败: %w", target, err)
			}
		default:
			// 符号链接、设备文件等一律跳过：直传只搬运普通文件与目录。
			continue
		}
	}
	return nil
}

// transferPushFile 把一段字节按分块上传到远端。
//
// 返回上传字节数与分块次数。最后一块会带 final=true（dir 模式下触发远端解包）。
func transferPushFile(
	gateway, token, nodeID, remotePath, mode string,
	data []byte, chunkSize int,
) (int, error) {
	total := len(data)
	if int64(total) > transferRemoteMaxFileSize {
		return 0, fmt.Errorf("待传输内容 %d 字节超出上限 %d 字节（512 MiB）",
			total, transferRemoteMaxFileSize)
	}

	url := transferRemoteURL(gateway, nodeID, "upload")
	offset := 0
	chunks := 0
	for offset < total || (total == 0 && chunks == 0) {
		end := offset + chunkSize
		if end > total {
			end = total
		}
		chunk := data[offset:end]
		isLast := end >= total

		payload := map[string]any{
			"path":     remotePath,
			"data":     TransferEncodeBase64(chunk),
			"offset":   offset,
			"mode":     mode,
			"truncate": offset == 0,
			"final":    isLast,
		}
		if _, err := transferRemotePost(gateway, token, url, payload); err != nil {
			return chunks, err
		}

		chunks++
		offset = end
		if total == 0 {
			break
		}
	}
	return chunks, nil
}

// transferPullFile 从远端按分块拉取内容，返回完整字节与分块次数。
func transferPullFile(
	gateway, token, nodeID, remotePath, mode string,
	chunkSize int,
) ([]byte, int, error) {
	url := transferRemoteURL(gateway, nodeID, "download")

	var buf bytes.Buffer
	offset := int64(0)
	chunks := 0
	for {
		payload := map[string]any{
			"path":   remotePath,
			"offset": offset,
			"length": chunkSize,
			"mode":   mode,
		}
		resp, err := transferRemotePost(gateway, token, url, payload)
		if err != nil {
			return nil, chunks, err
		}
		data, err := transferRemoteData(resp)
		if err != nil {
			return nil, chunks, err
		}

		b64, _ := data["data"].(string)
		chunk, err := TransferDecodeBase64(b64)
		if err != nil {
			return nil, chunks, err
		}
		if int64(buf.Len())+int64(len(chunk)) > transferRemoteMaxFileSize {
			return nil, chunks, fmt.Errorf("拉取内容超出上限 %d 字节（512 MiB）",
				transferRemoteMaxFileSize)
		}
		buf.Write(chunk)
		chunks++

		eof, _ := data["eof"].(bool)
		if eof {
			break
		}
		offset += int64(len(chunk))
		if len(chunk) == 0 {
			// 防御：远端未标记 eof 却返回空块，避免死循环。
			break
		}
	}
	return buf.Bytes(), chunks, nil
}

// handleTransferPush 是 fs.transfer.push 的公共实现：本机 → 远端节点。
func handleTransferPush(params map[string]any) (any, error) {
	p, err := parseTransferRemoteParams(params)
	if err != nil {
		return nil, err
	}

	token, ok := browserExtToken(p.Gateway)
	if !ok || token == "" {
		return nil, fmt.Errorf("网关 %s 没有可用凭据，无法发起直传；请先登录并推送登录信息", p.Gateway)
	}

	var payload []byte
	switch p.Mode {
	case "file":
		info, err := os.Stat(p.LocalPath)
		if err != nil {
			return nil, fmt.Errorf("读取本机文件 %s 失败: %w", p.LocalPath, err)
		}
		if info.IsDir() {
			return nil, fmt.Errorf("本机路径 %s 是目录，请把 mode 设为 dir", p.LocalPath)
		}
		if info.Size() > transferRemoteMaxFileSize {
			return nil, fmt.Errorf("文件 %s 大小 %d 字节超出上限 %d 字节（512 MiB）",
				p.LocalPath, info.Size(), transferRemoteMaxFileSize)
		}
		payload, err = os.ReadFile(p.LocalPath)
		if err != nil {
			return nil, fmt.Errorf("读取本机文件 %s 失败: %w", p.LocalPath, err)
		}
	case "dir":
		info, err := os.Stat(p.LocalPath)
		if err != nil {
			return nil, fmt.Errorf("读取本机目录 %s 失败: %w", p.LocalPath, err)
		}
		if !info.IsDir() {
			return nil, fmt.Errorf("本机路径 %s 不是目录，请把 mode 设为 file", p.LocalPath)
		}
		payload, err = transferPackDirToTar(p.LocalPath)
		if err != nil {
			return nil, err
		}
		if int64(len(payload)) > transferRemoteMaxFileSize {
			return nil, fmt.Errorf("目录打包后 %d 字节超出上限 %d 字节（512 MiB）",
				len(payload), transferRemoteMaxFileSize)
		}
	}

	chunks, err := transferPushFile(
		p.Gateway, token, p.NodeID, p.RemotePath, p.Mode, payload, p.ChunkSize,
	)
	if err != nil {
		return nil, err
	}

	return &transferRemoteResult{
		Direction:  "push",
		Gateway:    p.Gateway,
		NodeID:     p.NodeID,
		Mode:       p.Mode,
		LocalPath:  p.LocalPath,
		RemotePath: p.RemotePath,
		Size:       int64(len(payload)),
		SHA256:     TransferBytesSHA256(payload),
		Chunks:     chunks,
		ChunkSize:  p.ChunkSize,
	}, nil
}

// handleTransferPull 是 fs.transfer.pull 的公共实现：远端节点 → 本机。
func handleTransferPull(params map[string]any) (any, error) {
	p, err := parseTransferRemoteParams(params)
	if err != nil {
		return nil, err
	}

	token, ok := browserExtToken(p.Gateway)
	if !ok || token == "" {
		return nil, fmt.Errorf("网关 %s 没有可用凭据，无法发起直传；请先登录并推送登录信息", p.Gateway)
	}

	payload, chunks, err := transferPullFile(
		p.Gateway, token, p.NodeID, p.RemotePath, p.Mode, p.ChunkSize,
	)
	if err != nil {
		return nil, err
	}

	// 落盘：file 模式直接写文件；dir 模式解包到 local_path 目录。
	if p.Mode == "dir" {
		if err := transferUnpackTarToDir(payload, p.LocalPath); err != nil {
			return nil, err
		}
	} else {
		if err := os.MkdirAll(filepath.Dir(p.LocalPath), 0o755); err != nil {
			return nil, fmt.Errorf("创建目录 %s 失败: %w", filepath.Dir(p.LocalPath), err)
		}
		if err := os.WriteFile(p.LocalPath, payload, 0o644); err != nil {
			return nil, fmt.Errorf("写入本机文件 %s 失败: %w", p.LocalPath, err)
		}
	}

	return &transferRemoteResult{
		Direction:  "pull",
		Gateway:    p.Gateway,
		NodeID:     p.NodeID,
		Mode:       p.Mode,
		LocalPath:  p.LocalPath,
		RemotePath: p.RemotePath,
		Size:       int64(len(payload)),
		SHA256:     TransferBytesSHA256(payload),
		Chunks:     chunks,
		ChunkSize:  p.ChunkSize,
	}, nil
}

// registerTransferRemote 注册指定平台的跨机文件直传能力（push/pull）。
//
// 平台差异只体现在 Platform 字段，逻辑完全共享，故由 registry_*.go 传入 platform。
func registerTransferRemote(reg *Registry, platform Platform) {
	_ = reg.Register(Capability{
		Name: "fs.transfer.push",
		Description: "把本机文件（或目录）直传到远端节点：daemon 内部循环分块，" +
			"字节不经过调用方上下文，仅返回摘要（路径、大小、sha256）。" +
			"目录会自动打包为 tar 并在远端解包。单次上限 512 MiB。",
		Platform: platform,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"gateway": map[string]any{
					"type":        "string",
					"description": "网关地址（如 http://127.0.0.1:8000），必须以 http:// 或 https:// 开头。",
				},
				"node_id": map[string]any{
					"type":        "string",
					"description": "目标节点 ID（由网关分配）。",
				},
				"local_path": map[string]any{
					"type":        "string",
					"description": "本机源路径（文件或目录）。",
				},
				"remote_path": map[string]any{
					"type": "string",
					"description": "远端目标路径。会被节点收敛到 ~/.jarvis/transfers 之下：" +
						"绝对路径去根保留结构，相对路径直接拼接。",
				},
				"mode": map[string]any{
					"type":        "string",
					"description": "传输模式：file（单文件）或 dir（目录，自动 tar 打包）。缺省时按 local_path 类型推断。",
				},
				"chunk_size": map[string]any{
					"type":        "integer",
					"description": "分块字节数，默认 1048576（1 MiB），最大 8388608（8 MiB）。",
				},
			},
			"required": []string{"gateway", "node_id", "local_path", "remote_path"},
		},
		Handler: handleTransferPush,
	})

	_ = reg.Register(Capability{
		Name: "fs.transfer.pull",
		Description: "从远端节点把文件（或目录）直传回本机：daemon 内部循环分块拉取，" +
			"字节不经过调用方上下文，仅返回摘要（路径、大小、sha256）。" +
			"目录会在远端打包为 tar 并在本机解包。单次上限 512 MiB。",
		Platform: platform,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"gateway": map[string]any{
					"type":        "string",
					"description": "网关地址（如 http://127.0.0.1:8000），必须以 http:// 或 https:// 开头。",
				},
				"node_id": map[string]any{
					"type":        "string",
					"description": "源节点 ID（由网关分配）。",
				},
				"local_path": map[string]any{
					"type":        "string",
					"description": "本机目标路径（dir 模式下为解包目录）。",
				},
				"remote_path": map[string]any{
					"type": "string",
					"description": "远端源路径。会被节点收敛到 ~/.jarvis/transfers 之下：" +
						"绝对路径去根保留结构，相对路径直接拼接。",
				},
				"mode": map[string]any{
					"type":        "string",
					"description": "传输模式：file（单文件）或 dir（目录，远端自动 tar 打包）。缺省时按 local_path 类型推断。",
				},
				"chunk_size": map[string]any{
					"type":        "integer",
					"description": "分块字节数，默认 1048576（1 MiB），最大 8388608（8 MiB）。",
				},
			},
			"required": []string{"gateway", "node_id", "local_path", "remote_path"},
		},
		Handler: handleTransferPull,
	})
}
