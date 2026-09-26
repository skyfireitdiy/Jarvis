//go:build linux

package capability

// 本文件实现 Linux 平台的分块文件传输能力（linux.fs.transfer.stat / read / write / verify）。
//
// 与既有 linux.fs.read / write 的区别：
//   - linux.fs.read 面向「看内容」，单次上限 8 MiB，带 encoding 推断与二进制降级；
//   - linux.fs.transfer.* 面向「搬文件」，按 offset/length 分块、块级 sha256、
//     整文件 sha256 校验，支持断点续传，单文件上限 512 MiB。
//
// 公共常量与纯逻辑（块大小、区间计算、校验和、base64）全部复用 transfer.go，
// 保证与 Windows 侧语义一致。参数读取复用同包 Linux 侧已有的
// requiredString / optionalString / optionalInt / optionalBool。

import (
	"fmt"
	"os"
	"time"
)

// registerLinuxTransfer 注册 Linux 分块文件传输能力。
func registerLinuxTransfer(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "linux.fs.transfer.stat",
		Description: "获取 Linux 上文件（或目录）的传输元信息：是否存在、大小、修改时间与整文件 SHA-256。" +
			"用于传输前判断「是否需要传」以及传输后比对。文件不存在时返回 exists=false 而非报错。",
		Platform: PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "要查询的文件路径（绝对路径或相对守护进程工作目录）。",
				},
			},
			"required": []string{"path"},
		},
		Handler: handleLinuxTransferStat,
	})

	_ = reg.Register(Capability{
		Name: "linux.fs.transfer.read",
		Description: "按分块读取 Linux 上的文件，返回 base64 内容与该块的 SHA-256。" +
			"配合 offset/length 循环调用即可拉取大文件；length<=0 表示读到文件尾。单文件上限 512 MiB。",
		Platform: PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "要读取的文件路径。",
				},
				"offset": map[string]any{
					"type":        "integer",
					"description": "起始偏移字节数，默认 0，不能为负。",
				},
				"length": map[string]any{
					"type":        "integer",
					"description": "本次读取字节数，默认 1048576（1 MiB），最大 8388608（8 MiB）；<=0 表示读到文件尾。",
				},
			},
			"required": []string{"path"},
		},
		Handler: handleLinuxTransferRead,
	})

	_ = reg.Register(Capability{
		Name: "linux.fs.transfer.write",
		Description: "按分块写入 Linux 上的文件，支持断点续传（按 offset 定位）与首块清空。" +
			"data 为 base64 编码；首块（offset=0）传 truncate=true 可清空已有内容，后续块传 truncate=false 追加到对应偏移。",
		Platform: PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "要写入的文件路径。",
				},
				"offset": map[string]any{
					"type":        "integer",
					"description": "写入起始偏移字节数，默认 0，不能为负。",
				},
				"data": map[string]any{
					"type":        "string",
					"description": "要写入的内容，base64 编码。",
				},
				"truncate": map[string]any{
					"type":        "boolean",
					"description": "是否先清空文件再写入，默认 false。首块（offset=0）通常传 true。",
				},
			},
			"required": []string{"path", "data"},
		},
		Handler: handleLinuxTransferWrite,
	})

	_ = reg.Register(Capability{
		Name: "linux.fs.transfer.verify",
		Description: "校验 Linux 上文件的整文件 SHA-256 是否与期望值一致（大小写不敏感）。" +
			"传输完成后调用，确认落盘内容无损。",
		Platform: PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "要校验的文件路径。",
				},
				"sha256": map[string]any{
					"type":        "string",
					"description": "期望的 SHA-256（十六进制字符串，大小写不敏感）。",
				},
			},
			"required": []string{"path", "sha256"},
		},
		Handler: handleLinuxTransferVerify,
	})
}

// handleLinuxTransferStat 是 linux.fs.transfer.stat 的实现。
func handleLinuxTransferStat(params map[string]any) (any, error) {
	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}

	info, err := os.Stat(path)
	if err != nil {
		if os.IsNotExist(err) {
			// 文件不存在是「正常可预期」的结果，返回 exists=false 让上层决定是否上传。
			return map[string]any{
				"path":    path,
				"exists":  false,
				"size":    int64(0),
				"mtime":   "",
				"sha256":  "",
				"is_dir":  false,
				"message": "文件不存在",
			}, nil
		}
		return nil, fmt.Errorf("访问路径 %s 失败: %w", path, err)
	}

	if info.IsDir() {
		// 目录不做校验和（无意义且开销大），只回元信息。
		return map[string]any{
			"path":   path,
			"exists": true,
			"size":   info.Size(),
			"mtime":  info.ModTime().Format(time.RFC3339),
			"sha256": "",
			"is_dir": true,
		}, nil
	}

	if info.Size() > TransferMaxFileSize {
		return nil, fmt.Errorf("文件 %s 大小 %d 字节超出传输上限 %d 字节（512 MiB）",
			path, info.Size(), TransferMaxFileSize)
	}

	sum, err := TransferFileSHA256(path)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"path":   path,
		"exists": true,
		"size":   info.Size(),
		"mtime":  info.ModTime().Format(time.RFC3339),
		"sha256": sum,
		"is_dir": false,
	}, nil
}

// handleLinuxTransferRead 是 linux.fs.transfer.read 的实现。
func handleLinuxTransferRead(params map[string]any) (any, error) {
	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}

	offset, err := transferParamInt64(params, "offset", 0)
	if err != nil {
		return nil, err
	}
	if offset < 0 {
		return nil, fmt.Errorf("参数 offset 不能为负数，实际 %d", offset)
	}

	length, err := transferParamInt64(params, "length", int64(TransferDefaultChunkSize))
	if err != nil {
		return nil, err
	}

	info, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("读取文件 %s 失败: %w", path, err)
	}
	if info.IsDir() {
		return nil, fmt.Errorf("路径 %s 是目录，不能用 fs.transfer.read 读取", path)
	}
	if info.Size() > TransferMaxFileSize {
		return nil, fmt.Errorf("文件 %s 大小 %d 字节超出传输上限 %d 字节（512 MiB）",
			path, info.Size(), TransferMaxFileSize)
	}

	// 用公共逻辑统一计算实际区间，避免与 Windows 侧语义漂移。
	// 注意：length 需先做块大小上限校验；ResolveTransferRange 内部也会校验。
	if length > TransferMaxChunkSize {
		return nil, fmt.Errorf("参数 length 超出单块上限 %d 字节，实际 %d",
			TransferMaxChunkSize, length)
	}

	start, count, eof, err := ResolveTransferRange(offset, length, info.Size())
	if err != nil {
		return nil, err
	}

	// count 为 0 表示已到文件尾，直接返回空块（不打开文件）。
	if count == 0 {
		return map[string]any{
			"path":         path,
			"offset":       start,
			"bytes_read":   int64(0),
			"eof":          true,
			"data":         "",
			"chunk_sha256": TransferBytesSHA256(nil),
			"size":         info.Size(),
		}, nil
	}

	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("打开文件 %s 失败: %w", path, err)
	}
	defer f.Close()

	if _, err := f.Seek(start, 0); err != nil {
		return nil, fmt.Errorf("定位到偏移 %d 失败: %w", start, err)
	}

	buf := make([]byte, count)
	n, err := f.Read(buf)
	if err != nil && n == 0 {
		return nil, fmt.Errorf("读取文件 %s 失败: %w", path, err)
	}
	chunk := buf[:n]

	return map[string]any{
		"path":         path,
		"offset":       start,
		"bytes_read":   int64(n),
		"eof":          eof || int64(n) < count,
		"data":         TransferEncodeBase64(chunk),
		"chunk_sha256": TransferBytesSHA256(chunk),
		"size":         info.Size(),
	}, nil
}

// handleLinuxTransferWrite 是 linux.fs.transfer.write 的实现。
func handleLinuxTransferWrite(params map[string]any) (any, error) {
	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}

	offset, err := transferParamInt64(params, "offset", 0)
	if err != nil {
		return nil, err
	}
	if offset < 0 {
		return nil, fmt.Errorf("参数 offset 不能为负数，实际 %d", offset)
	}

	rawData, ok := params["data"]
	if !ok || rawData == nil {
		return nil, fmt.Errorf("缺少必填参数 data")
	}
	dataStr, ok := rawData.(string)
	if !ok {
		return nil, fmt.Errorf("参数 data 必须是字符串，实际 %T", rawData)
	}

	truncate, err := transferParamBool(params, "truncate", false)
	if err != nil {
		return nil, err
	}

	payload, err := TransferDecodeBase64(dataStr)
	if err != nil {
		return nil, err
	}
	if int64(len(payload)) > TransferMaxChunkSize {
		return nil, fmt.Errorf("单块数据 %d 字节超出上限 %d 字节",
			len(payload), TransferMaxChunkSize)
	}

	// 写入后的总大小必须仍在单文件上限内。
	end := offset + int64(len(payload))
	if end > TransferMaxFileSize {
		return nil, fmt.Errorf("写入后文件大小 %d 字节超出传输上限 %d 字节（512 MiB）",
			end, TransferMaxFileSize)
	}

	flags := os.O_WRONLY | os.O_CREATE
	if truncate {
		flags |= os.O_TRUNC
	}

	f, err := os.OpenFile(path, flags, 0o644)
	if err != nil {
		return nil, fmt.Errorf("打开文件 %s 失败: %w", path, err)
	}

	if offset > 0 {
		if _, err := f.Seek(offset, 0); err != nil {
			f.Close()
			return nil, fmt.Errorf("定位到偏移 %d 失败: %w", offset, err)
		}
	}

	written, writeErr := f.Write(payload)
	closeErr := f.Close()
	if writeErr != nil {
		return nil, fmt.Errorf("写入文件 %s 失败: %w", path, writeErr)
	}
	if closeErr != nil {
		return nil, fmt.Errorf("关闭文件 %s 失败: %w", path, closeErr)
	}

	// 回读最终文件大小，便于上层判断是否传完。
	var totalSize int64
	if info, statErr := os.Stat(path); statErr == nil {
		totalSize = info.Size()
	}

	return map[string]any{
		"path":          path,
		"offset":        offset,
		"written_bytes": int64(written),
		"size":          totalSize,
		"truncated":     truncate,
	}, nil
}

// handleLinuxTransferVerify 是 linux.fs.transfer.verify 的实现。
func handleLinuxTransferVerify(params map[string]any) (any, error) {
	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}
	expected, err := requiredString(params, "sha256")
	if err != nil {
		return nil, err
	}

	info, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("校验文件 %s 失败: %w", path, err)
	}
	if info.IsDir() {
		return nil, fmt.Errorf("路径 %s 是目录，不能用 fs.transfer.verify 校验", path)
	}

	actual, err := TransferFileSHA256(path)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"path":          path,
		"match":         TransferEqualSHA256(expected, actual),
		"size":          info.Size(),
		"actual_sha256": actual,
		"expect_sha256": expected,
	}, nil
}
