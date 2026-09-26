// 本文件提供「分块文件传输」能力的公共核心：常量、范围计算、校验和与编码辅助。
//
// 设计目标：让 linux.fs.transfer.* 与 windows.fs.transfer.* 两套平台能力共享同一份
// 语义与边界校验，避免两侧实现漂移。
//
// 重要：本文件**不带构建标签**，会被编译进所有平台，因此：
//   - 只能使用标准库；
//   - 绝不能引用仅存在于平台专有文件中的符号（如 requiredString / optionalBool /
//     resolveFSEncoding 等，它们分别在 linux_*.go 或 windows_*.go 中定义）；
//   - 本文件内定义的顶层函数名必须带 Transfer 前缀，以免与平台文件中的同名函数
//     冲突（例如 optionalBool 在 Linux 与 Windows 两侧都有定义）。
package capability

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"strings"
)

// 分块传输的公共约束常量。
const (
	// TransferMaxFileSize 是单个文件允许传输的最大字节数（512 MiB）。
	//
	// 取值理由：内容经 JSON + base64 承载，base64 会膨胀约 4/3。512 MiB 的文件
	// 按 1 MiB 分块需要 512 次往返，是「够用」与「上层循环不至于失控」之间的折中；
	// 再大则应改用独立二进制通道，而不是本能力。
	TransferMaxFileSize int64 = 512 << 20 // 512 MiB

	// TransferDefaultChunkSize 是未指定块大小时使用的默认块字节数（1 MiB）。
	//
	// 取值理由：1 MiB 经 base64 后约 1.33 MiB，单帧 JSON 体积可控，
	// 既不会因块太小导致往返次数过多，也不会因块太大撑爆单帧。
	TransferDefaultChunkSize = 1 << 20 // 1 MiB

	// TransferMaxChunkSize 是单次分块读写的最大字节数（8 MiB）。
	//
	// 取值理由：与既有 fs.read 的单次读取上限（8 MiB）对齐，
	// 保证「一次分块」不会超过一次普通读取的资源占用。
	TransferMaxChunkSize = 8 << 20 // 8 MiB
)

// NormalizeTransferChunkSize 规范化请求的块大小。
//
// 规则：requested <= 0 时返回默认块大小；超过 TransferMaxChunkSize 时报错。
func NormalizeTransferChunkSize(requested int) (int, error) {
	if requested <= 0 {
		return TransferDefaultChunkSize, nil
	}
	if requested > TransferMaxChunkSize {
		return 0, fmt.Errorf("参数 length 超出单块上限 %d 字节，实际 %d",
			TransferMaxChunkSize, requested)
	}
	return requested, nil
}

// ResolveTransferRange 计算一次分块读取的实际区间。
//
// 参数：
//   - offset：起始偏移，必须 >= 0；
//   - length：期望读取长度，<= 0 表示「读到文件尾」；
//   - fileSize：文件总大小，必须 >= 0。
//
// 返回：
//   - start：实际起始偏移；
//   - count：实际读取字节数；
//   - eof：本次读取是否已到达（或越过）文件尾。
//
// 边界语义：
//   - offset < 0 或 fileSize < 0 → 报错；
//   - offset > fileSize → start=fileSize、count=0、eof=true（越界视为已到尾部，不报错）；
//   - offset == fileSize → count=0、eof=true；
//   - length <= 0 或 offset+length > fileSize → 取剩余字节，eof=true。
func ResolveTransferRange(offset, length, fileSize int64) (start, count int64, eof bool, err error) {
	if offset < 0 {
		return 0, 0, false, fmt.Errorf("参数 offset 不能为负数，实际 %d", offset)
	}
	if fileSize < 0 {
		return 0, 0, false, fmt.Errorf("文件大小不能为负数，实际 %d", fileSize)
	}

	// 偏移越过文件尾：按「已到尾部」处理，返回空块而非报错，便于上层循环自然收敛。
	if offset >= fileSize {
		return fileSize, 0, true, nil
	}

	remaining := fileSize - offset
	if length <= 0 || length > remaining {
		// 未指定长度，或请求长度超出剩余：一律取剩余部分，此时必然到达文件尾。
		if length > TransferMaxChunkSize {
			return 0, 0, false, fmt.Errorf("参数 length 超出单块上限 %d 字节，实际 %d",
				TransferMaxChunkSize, length)
		}
		return offset, remaining, true, nil
	}

	if length > TransferMaxChunkSize {
		return 0, 0, false, fmt.Errorf("参数 length 超出单块上限 %d 字节，实际 %d",
			TransferMaxChunkSize, length)
	}

	// 读取到 offset+length，是否正好到文件尾。
	return offset, length, offset+length == fileSize, nil
}

// TransferFileSHA256 以流式方式计算文件的 SHA-256，返回小写十六进制字符串。
//
// 实现上使用 io.Copy 把文件内容喂给哈希器，不会把整个文件读入内存，
// 因此对大文件也安全。
func TransferFileSHA256(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", fmt.Errorf("打开文件 %s 失败: %w", path, err)
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", fmt.Errorf("读取文件 %s 计算校验和失败: %w", path, err)
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

// TransferBytesSHA256 计算一段字节的 SHA-256，返回小写十六进制字符串。
func TransferBytesSHA256(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

// TransferEqualSHA256 比较两个 SHA-256 字符串是否相等。
//
// 比较前会去除首尾空白并忽略大小写，便于调用方直接传用户输入。
// 空字符串一律视为不相等（避免「都没传」被误判为匹配）。
func TransferEqualSHA256(a, b string) bool {
	left := strings.TrimSpace(a)
	right := strings.TrimSpace(b)
	if left == "" || right == "" {
		return false
	}
	return strings.EqualFold(left, right)
}

// TransferDecodeBase64 解码 base64 字符串（先去除首尾空白）。
func TransferDecodeBase64(s string) ([]byte, error) {
	trimmed := strings.TrimSpace(s)
	data, err := base64.StdEncoding.DecodeString(trimmed)
	if err != nil {
		return nil, fmt.Errorf("data 不是合法的 base64 内容: %w", err)
	}
	return data, nil
}

// TransferEncodeBase64 把字节编码为 base64 字符串。
func TransferEncodeBase64(data []byte) string {
	return base64.StdEncoding.EncodeToString(data)
}

// transferParamString 读取必填字符串参数（本文件自包含，不依赖平台专有辅助）。
func transferParamString(params map[string]any, key string) (string, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return "", fmt.Errorf("缺少必填参数 %s", key)
	}
	s, ok := v.(string)
	if !ok {
		return "", fmt.Errorf("参数 %s 必须是字符串，实际 %T", key, v)
	}
	s = strings.TrimSpace(s)
	if s == "" {
		return "", fmt.Errorf("参数 %s 不能为空", key)
	}
	return s, nil
}

// transferParamInt64 读取可选整数参数，支持 int / int64 / float64 三种来源。
//
// 之所以要兼容 float64：参数经 JSON 反序列化后整数会变成 float64。
func transferParamInt64(params map[string]any, key string, def int64) (int64, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return def, nil
	}
	switch n := v.(type) {
	case int:
		return int64(n), nil
	case int32:
		return int64(n), nil
	case int64:
		return n, nil
	case float64:
		// JSON 数字统一为 float64；这里要求它是整数值，避免静默截断。
		if n != float64(int64(n)) {
			return 0, fmt.Errorf("参数 %s 必须是整数，实际 %v", key, n)
		}
		return int64(n), nil
	default:
		return 0, fmt.Errorf("参数 %s 必须是整数，实际 %T", key, v)
	}
}

// transferParamBool 读取可选布尔参数；缺失或为 nil 时返回默认值。
func transferParamBool(params map[string]any, key string, def bool) (bool, error) {
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
