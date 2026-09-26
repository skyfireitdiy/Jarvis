package capability

// 本文件测试分块传输的公共纯逻辑（transfer.go），跨平台可跑。
//
// 只测不依赖文件系统的部分：块大小规范化、区间计算、校验和辅助、base64 往返。

import (
	"strings"
	"testing"
)

func TestTransferNormalizeChunkSize(t *testing.T) {
	cases := []struct {
		name      string
		requested int
		want      int
		wantErr   bool
	}{
		{"零取默认", 0, TransferDefaultChunkSize, false},
		{"负数取默认", -1, TransferDefaultChunkSize, false},
		{"正常值原样返回", 4096, 4096, false},
		{"等于上限", TransferMaxChunkSize, TransferMaxChunkSize, false},
		{"超上限报错", TransferMaxChunkSize + 1, 0, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := NormalizeTransferChunkSize(c.requested)
			if c.wantErr {
				if err == nil {
					t.Fatalf("期望报错，实际 got=%d err=nil", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("未期望报错: %v", err)
			}
			if got != c.want {
				t.Fatalf("期望 %d，实际 %d", c.want, got)
			}
		})
	}
}

func TestTransferResolveRange(t *testing.T) {
	const size = 1000

	cases := []struct {
		name      string
		offset    int64
		length    int64
		fileSize  int64
		wantStart int64
		wantCount int64
		wantEOF   bool
		wantErr   bool
	}{
		{"负 offset 报错", -1, 100, size, 0, 0, false, true},
		{"负 fileSize 报错", 0, 100, -1, 0, 0, false, true},
		{"从头读指定长度未到尾", 0, 100, size, 0, 100, false, false},
		{"读到正好到文件尾", 0, 1000, size, 0, 1000, true, false},
		{"length=0 读到尾", 0, 0, size, 0, 1000, true, false},
		{"length 负 读到尾", 0, -5, size, 0, 1000, true, false},
		{"length 超剩余取剩余", 100, 5000, size, 100, 900, true, false},
		{"offset 超文件尾返回空块", 2000, 100, size, 1000, 0, true, false},
		{"offset 等于文件尾返回空块", 1000, 100, size, 1000, 0, true, false},
		{"中段读取未到尾", 500, 100, size, 500, 100, false, false},
		{"中段读取正好到尾", 900, 100, size, 900, 100, true, false},
		{"length 超单块上限报错", 0, TransferMaxChunkSize + 1, size, 0, 0, false, true},
		{"空文件读空块", 0, 100, 0, 0, 0, true, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			start, count, eof, err := ResolveTransferRange(c.offset, c.length, c.fileSize)
			if c.wantErr {
				if err == nil {
					t.Fatalf("期望报错，实际 start=%d count=%d eof=%v", start, count, eof)
				}
				return
			}
			if err != nil {
				t.Fatalf("未期望报错: %v", err)
			}
			if start != c.wantStart || count != c.wantCount || eof != c.wantEOF {
				t.Fatalf("期望 (start=%d,count=%d,eof=%v)，实际 (start=%d,count=%d,eof=%v)",
					c.wantStart, c.wantCount, c.wantEOF, start, count, eof)
			}
		})
	}
}

func TestTransferBytesSHA256(t *testing.T) {
	// 空内容的 SHA-256 是固定值，用于锚定实现正确性。
	const emptySHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
	if got := TransferBytesSHA256(nil); got != emptySHA {
		t.Fatalf("空内容 SHA-256 期望 %s，实际 %s", emptySHA, got)
	}

	// "abc" 的 SHA-256 是众所周知的值。
	const abcSHA = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
	if got := TransferBytesSHA256([]byte("abc")); got != abcSHA {
		t.Fatalf("\"abc\" SHA-256 期望 %s，实际 %s", abcSHA, got)
	}

	// 输出必须是小写十六进制，长度 64。
	got := TransferBytesSHA256([]byte("hello"))
	if len(got) != 64 {
		t.Fatalf("SHA-256 长度期望 64，实际 %d", len(got))
	}
	if got != strings.ToLower(got) {
		t.Fatalf("SHA-256 期望小写，实际 %s", got)
	}
}

func TestTransferEqualSHA256(t *testing.T) {
	const sum = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

	cases := []struct {
		name string
		a    string
		b    string
		want bool
	}{
		{"完全相同", sum, sum, true},
		{"大小写不同视为相等", sum, strings.ToUpper(sum), true},
		{"首尾空白忽略", "  " + sum + "\n", sum, true},
		{"不同值不相等", sum, strings.Repeat("0", 64), false},
		{"左边空串不相等", "", sum, false},
		{"右边空串不相等", sum, "", false},
		{"两边都空不相等", "", "", false},
		{"仅空白不相等", "   ", "   ", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := TransferEqualSHA256(c.a, c.b); got != c.want {
				t.Fatalf("期望 %v，实际 %v", c.want, got)
			}
		})
	}
}

func TestTransferBase64RoundTrip(t *testing.T) {
	// 含二进制字节（NUL、0xFF）的内容，验证 base64 往返无损。
	original := []byte{0x00, 0x01, 0xFF, 0xFE, 'h', 'i', 0x00}
	encoded := TransferEncodeBase64(original)
	decoded, err := TransferDecodeBase64(encoded)
	if err != nil {
		t.Fatalf("解码失败: %v", err)
	}
	if string(decoded) != string(original) {
		t.Fatalf("往返不一致：原文 %v，解码后 %v", original, decoded)
	}

	// 空内容往返。
	emptyDecoded, err := TransferDecodeBase64(TransferEncodeBase64(nil))
	if err != nil {
		t.Fatalf("空内容解码失败: %v", err)
	}
	if len(emptyDecoded) != 0 {
		t.Fatalf("空内容解码后期望长度 0，实际 %d", len(emptyDecoded))
	}

	// 带首尾空白的 base64 应能正常解码。
	decoded2, err := TransferDecodeBase64("  " + encoded + "\n")
	if err != nil {
		t.Fatalf("带空白解码失败: %v", err)
	}
	if string(decoded2) != string(original) {
		t.Fatalf("带空白解码结果不一致")
	}

	// 非法 base64 必须报错。
	if _, err := TransferDecodeBase64("!!!not-base64!!!"); err == nil {
		t.Fatalf("非法 base64 期望报错，实际 nil")
	}
}

func TestTransferParamHelpers(t *testing.T) {
	// transferParamString：缺失/空/非字符串都要报错。
	if _, err := transferParamString(map[string]any{}, "path"); err == nil {
		t.Fatalf("缺失参数期望报错")
	}
	if _, err := transferParamString(map[string]any{"path": "  "}, "path"); err == nil {
		t.Fatalf("空白参数期望报错")
	}
	if _, err := transferParamString(map[string]any{"path": 123}, "path"); err == nil {
		t.Fatalf("非字符串期望报错")
	}
	got, err := transferParamString(map[string]any{"path": " /tmp/a "}, "path")
	if err != nil || got != "/tmp/a" {
		t.Fatalf("期望 \"/tmp/a\"，实际 %q err=%v", got, err)
	}

	// transferParamInt64：兼容 int/int32/int64/float64，拒绝小数。
	cases := []struct {
		name    string
		value   any
		want    int64
		wantErr bool
	}{
		{"int", 42, 42, false},
		{"int32", int32(42), 42, false},
		{"int64", int64(42), 42, false},
		{"float64 整数值", float64(42), 42, false},
		{"float64 小数报错", 42.5, 0, true},
		{"字符串报错", "42", 0, true},
	}
	for _, c := range cases {
		t.Run("int64/"+c.name, func(t *testing.T) {
			v, err := transferParamInt64(map[string]any{"n": c.value}, "n", 0)
			if c.wantErr {
				if err == nil {
					t.Fatalf("期望报错，实际 %d", v)
				}
				return
			}
			if err != nil {
				t.Fatalf("未期望报错: %v", err)
			}
			if v != c.want {
				t.Fatalf("期望 %d，实际 %d", c.want, v)
			}
		})
	}

	// 缺失时返回默认值。
	def, err := transferParamInt64(map[string]any{}, "n", 7)
	if err != nil || def != 7 {
		t.Fatalf("缺失时期望默认 7，实际 %d err=%v", def, err)
	}

	// transferParamBool：缺失取默认，非布尔报错。
	b, err := transferParamBool(map[string]any{}, "truncate", true)
	if err != nil || !b {
		t.Fatalf("缺失时期望默认 true，实际 %v err=%v", b, err)
	}
	if _, err := transferParamBool(map[string]any{"truncate": "yes"}, "truncate", false); err == nil {
		t.Fatalf("非布尔期望报错")
	}
	got2, err := transferParamBool(map[string]any{"truncate": false}, "truncate", true)
	if err != nil || got2 {
		t.Fatalf("期望 false，实际 %v err=%v", got2, err)
	}
}

func TestTransferConstants(t *testing.T) {
	// 常量之间的量级关系必须自洽，避免后续误改。
	if TransferDefaultChunkSize > TransferMaxChunkSize {
		t.Fatalf("默认块 %d 不应大于最大块 %d", TransferDefaultChunkSize, TransferMaxChunkSize)
	}
	if TransferMaxChunkSize > TransferMaxFileSize {
		t.Fatalf("最大块 %d 不应大于单文件上限 %d", TransferMaxChunkSize, TransferMaxFileSize)
	}
	if TransferMaxFileSize != 512<<20 {
		t.Fatalf("单文件上限期望 512 MiB，实际 %d", TransferMaxFileSize)
	}
	if TransferDefaultChunkSize != 1<<20 {
		t.Fatalf("默认块期望 1 MiB，实际 %d", TransferDefaultChunkSize)
	}
	if TransferMaxChunkSize != 8<<20 {
		t.Fatalf("最大块期望 8 MiB，实际 %d", TransferMaxChunkSize)
	}
}
