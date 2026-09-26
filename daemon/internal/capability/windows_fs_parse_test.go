package capability

// 本文件单测 windows_fs_parse.go 中的纯逻辑（编码解析、二进制判定、上报编码选择）。
//
// 这些测试**不带构建标签**，因此在 Linux 上即可运行——本机开发环境为 Linux，
// 无 Windows 运行环境，这是验证 windows.fs.* 核心逻辑的主要手段。
//
// 注意：真正的文件读写（windows_fs_windows.go）带 //go:build windows 标签，
// 其成功路径无法在本机端到端验证，只能保证在 GOOS=windows 下编译通过。

import (
	"bytes"
	"strings"
	"testing"
)

// TestResolveWindowsFSEncoding 覆盖 encoding 参数解析的各种取值。
func TestResolveWindowsFSEncoding(t *testing.T) {
	cases := []struct {
		name    string
		params  map[string]any
		def     string
		want    string
		wantErr bool
	}{
		{"缺省回退默认值", map[string]any{}, "utf-8", "utf-8", false},
		{"空串回退默认值", map[string]any{"encoding": ""}, "utf-8", "utf-8", false},
		{"utf-8 原样", map[string]any{"encoding": "utf-8"}, "utf-8", "utf-8", false},
		{"UTF-8 大小写不敏感", map[string]any{"encoding": "UTF-8"}, "utf-8", "utf-8", false},
		{"utf8 别名归一化", map[string]any{"encoding": "utf8"}, "utf-8", "utf-8", false},
		{"base64 原样", map[string]any{"encoding": "base64"}, "utf-8", "base64", false},
		{"BASE64 大小写不敏感", map[string]any{"encoding": "BASE64"}, "utf-8", "base64", false},
		{"自定义默认值生效", map[string]any{}, "base64", "base64", false},
		{"不支持的值报错", map[string]any{"encoding": "gbk"}, "utf-8", "", true},
		{"类型错误报错", map[string]any{"encoding": 123}, "utf-8", "", true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := resolveWindowsFSEncoding(tc.params, tc.def)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("期望返回错误，实际 got=%q err=nil", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("期望无错误，实际 err=%v", err)
			}
			if got != tc.want {
				t.Fatalf("期望 %q，实际 %q", tc.want, got)
			}
		})
	}
}

// TestChooseWindowsReportedEncoding 覆盖「二进制内容自动降级 base64」的上报逻辑。
func TestChooseWindowsReportedEncoding(t *testing.T) {
	cases := []struct {
		requested string
		isBinary  bool
		want      string
	}{
		{"utf-8", false, "utf-8"},
		{"utf-8", true, "base64"}, // 二进制 + 请求 utf-8 → 实际以 base64 返回
		{"base64", false, "base64"},
		{"base64", true, "base64"},
	}

	for _, tc := range cases {
		got := chooseWindowsReportedEncoding(tc.requested, tc.isBinary)
		if got != tc.want {
			t.Errorf("chooseWindowsReportedEncoding(%q, %v) = %q，期望 %q",
				tc.requested, tc.isBinary, got, tc.want)
		}
	}
}

// TestIsBinaryWindowsContent 覆盖二进制判定：NUL 字节、非法 UTF-8、纯文本、空内容。
func TestIsBinaryWindowsContent(t *testing.T) {
	cases := []struct {
		name string
		data []byte
		want bool
	}{
		{"空内容非二进制", []byte{}, false},
		{"纯 ASCII 非二进制", []byte("hello world"), false},
		{"含中文的合法 UTF-8 非二进制", []byte("你好，世界"), false},
		{"含 NUL 字节为二进制", []byte("abc\x00def"), true},
		{"开头 NUL 为二进制", []byte{0x00, 0x01, 0x02}, true},
		{"非法 UTF-8 为二进制", []byte{0xff, 0xfe, 0xfd}, true},
		{"孤立续字节为二进制", []byte{0x80, 0x80}, true},
		{"截断的多字节序列为二进制", []byte{0xe4, 0xbd}, true},
		{"PNG 魔数为二进制", []byte{0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a}, true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := isBinaryWindowsContent(tc.data); got != tc.want {
				t.Fatalf("isBinaryWindowsContent(%q) = %v，期望 %v", tc.data, got, tc.want)
			}
		})
	}
}

// TestIsBinaryWindowsContentDoesNotMutate 确认判定过程不修改入参切片。
func TestIsBinaryWindowsContentDoesNotMutate(t *testing.T) {
	original := []byte("hello\x00world")
	snapshot := append([]byte(nil), original...)

	_ = isBinaryWindowsContent(original)

	if !bytes.Equal(original, snapshot) {
		t.Fatalf("入参被修改：原 %q，现 %q", snapshot, original)
	}
}

// TestResolveWindowsFSEncodingErrorMessage 确认错误信息对排查友好（含非法值）。
func TestResolveWindowsFSEncodingErrorMessage(t *testing.T) {
	_, err := resolveWindowsFSEncoding(map[string]any{"encoding": "latin1"}, "utf-8")
	if err == nil {
		t.Fatal("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "latin1") {
		t.Fatalf("错误信息应包含非法值 latin1，实际: %v", err)
	}
	if !strings.Contains(err.Error(), "base64") {
		t.Fatalf("错误信息应提示允许值 base64，实际: %v", err)
	}
}
