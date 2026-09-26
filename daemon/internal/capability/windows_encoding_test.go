package capability

// 本文件单测 windows_encoding.go 中的纯逻辑。
//
// 这些测试**不带构建标签**，因此在 Linux 上即可运行——本机开发环境为 Linux，
// 无 Windows 运行环境，这是验证 -EncodedCommand 编码正确性的唯一手段。

import (
	"encoding/base64"
	"strings"
	"testing"
	"unicode/utf16"
)

// TestUTF16LEBytesRoundTrip 验证 UTF-16LE 编码的往返一致性。
//
// 这是 -EncodedCommand 方案能成立的前提：若往返有损，PowerShell 收到的脚本
// 就会损坏，中文键名等非 ASCII 内容全部失效。
func TestUTF16LEBytesRoundTrip(t *testing.T) {
	cases := []struct {
		name string
		in   string
	}{
		{"空串", ""},
		{"纯 ASCII", "Get-Clipboard -Raw"},
		{"中文", "东方财富信息股份有限公司"},
		{"中英混合", "$k='HKLM:\\SOFTWARE\\测试'; Get-ItemProperty $k"},
		{"emoji（代理对）", "截图完成 ✅ 🎉"},
		{"全角符号", "（测试）【重要】、。；"},
		{"换行与制表", "line1\nline2\ttabbed\r\n"},
		{"日文韩文", "こんにちは 안녕하세요"},
		{"单引号与美元符", "Set-Clipboard -Value 'it''s $HOME'"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			encoded := utf16LEBytes(tc.in)
			got := decodeUTF16LEBytes(encoded)
			if got != tc.in {
				t.Errorf("往返不一致：\n  输入 %q\n  得到 %q", tc.in, got)
			}
		})
	}
}

// TestUTF16LEBytesIsLittleEndian 验证字节序确实是小端。
//
// 大端会静默产生错误结果（PowerShell 收到的脚本变成乱码字符），必须在单测中
// 显式锁定字节序，而不只是验证「往返一致」——因为往返用的是同一套字节序假设，
// 大端实现也能自洽地往返成功。
func TestUTF16LEBytesIsLittleEndian(t *testing.T) {
	// 'A' 的 UTF-16 码元是 0x0041：小端应为 [0x41, 0x00]。
	got := utf16LEBytes("A")
	want := []byte{0x41, 0x00}
	if len(got) != 2 || got[0] != want[0] || got[1] != want[1] {
		t.Errorf("字节序错误：utf16LEBytes(\"A\") = %v，期望 %v（小端）", got, want)
	}

	// '中' 的 UTF-16 码元是 0x4E2D：小端应为 [0x2D, 0x4E]。
	got = utf16LEBytes("中")
	want = []byte{0x2D, 0x4E}
	if len(got) != 2 || got[0] != want[0] || got[1] != want[1] {
		t.Errorf("字节序错误：utf16LEBytes(\"中\") = %v，期望 %v（小端）", got, want)
	}
}

// TestUTF16LEBytesNoBOM 验证编码结果不含 BOM。
//
// 若加了 BOM（0xFF 0xFE），PowerShell 会把 U+FEFF 当作脚本的第一个字符，
// 导致「无法识别的标记」语法错误。这是 -EncodedCommand 的常见坑，必须锁定。
func TestUTF16LEBytesNoBOM(t *testing.T) {
	got := utf16LEBytes("Get-Date")
	if len(got) >= 2 && got[0] == 0xFF && got[1] == 0xFE {
		t.Errorf("编码结果含 UTF-16LE BOM（0xFF 0xFE），会导致 PowerShell 语法错误：%v", got)
	}
	// 也不应含 UTF-8 BOM 或其它前导标记。
	if len(got) >= 3 && got[0] == 0xEF && got[1] == 0xBB && got[2] == 0xBF {
		t.Errorf("编码结果含 UTF-8 BOM，会导致 PowerShell 语法错误：%v", got)
	}
}

// TestEncodePowerShellCommandIsValidBase64 验证输出是合法 base64 且可解回原文。
//
// PowerShell 的 -EncodedCommand 要求参数是 base64；若编码结果含非 base64 字符
// （如直接返回原始字节），PowerShell 会报「参数格式不正确」。
func TestEncodePowerShellCommandIsValidBase64(t *testing.T) {
	script := "Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion'"

	encoded := encodePowerShellCommand(script)

	// 必须是合法 base64（仅含 A-Za-z0-9+/=）。
	if strings.ContainsAny(encoded, " \t\n\r") {
		t.Errorf("编码结果含空白字符，不是合法 base64 参数：%q", encoded)
	}
	raw, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		t.Fatalf("编码结果不是合法 base64：%v（值 %q）", err, encoded)
	}

	// 解出的字节必须是 UTF-16LE，且能还原原文。
	if got := decodeUTF16LEBytes(raw); got != script {
		t.Errorf("base64 解码后原文不一致：\n  期望 %q\n  得到 %q", script, got)
	}
}

// TestEncodePowerShellCommandWithChinese 验证含中文的脚本编码正确。
//
// 这是本修复的核心场景：脚本里可能含中文路径或中文键名，必须保证 PowerShell
// 收到的是正确的中文而非乱码。
func TestEncodePowerShellCommandWithChinese(t *testing.T) {
	script := "Write-Output '东方财富信息股份有限公司'"

	encoded := encodePowerShellCommand(script)
	raw, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		t.Fatalf("编码结果不是合法 base64：%v", err)
	}

	// 用标准库 utf16 独立解码（不复用 decodeUTF16LEBytes），避免与被测代码
	// 共享同一套错误假设。
	units := make([]uint16, 0, len(raw)/2)
	for i := 0; i+1 < len(raw); i += 2 {
		units = append(units, uint16(raw[i])|uint16(raw[i+1])<<8)
	}
	got := string(utf16.Decode(units))

	if got != script {
		t.Errorf("中文脚本编码后无法还原：\n  期望 %q\n  得到 %q", script, got)
	}
	if !strings.Contains(got, "东方财富") {
		t.Errorf("中文内容丢失，得到 %q", got)
	}
}

// TestEncodePowerShellCommandEmpty 验证空脚本不 panic。
func TestEncodePowerShellCommandEmpty(t *testing.T) {
	if got := encodePowerShellCommand(""); got != "" {
		t.Errorf("空脚本应编码为空串，得到 %q", got)
	}
}

// TestLooksLikeUTF8 验证 UTF-8 判据能区分 UTF-8 与 GBK 字节流。
//
// 该判据用于在子进程仍按 GBK 输出时给出明确错误，而不是静默返回 U+FFFD。
func TestLooksLikeUTF8(t *testing.T) {
	cases := []struct {
		name string
		in   []byte
		want bool
	}{
		{"空", []byte{}, true},
		{"纯 ASCII", []byte("Get-Clipboard"), true},
		{"合法 UTF-8 中文", []byte("东方财富"), true},
		{"合法 UTF-8 emoji", []byte("✅"), true},
		{"GBK 中文（东方）", []byte{0xB6, 0xAB, 0xB7, 0xBD}, false},
		{"孤立续字节", []byte{0x80}, false},
		{"过长编码 C0", []byte{0xC0, 0x80}, false},
		{"过长编码 C1", []byte{0xC1, 0xBF}, false},
		{"非法起始字节 FF", []byte{0xFF}, false},
		{"截断的 3 字节序列", []byte{0xE4, 0xB8}, false},
		{"截断的 4 字节序列", []byte{0xF0, 0x9F, 0x8E}, false},
		{"续字节位置错误", []byte{0xE4, 0x41, 0x80}, false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := looksLikeUTF8(tc.in); got != tc.want {
				t.Errorf("looksLikeUTF8(%v) = %v，期望 %v", tc.in, got, tc.want)
			}
		})
	}
}

// TestWindowsPowerShellPreambleSetsAllThreeEncodings 验证前置语句包含三项编码设置。
//
// 三项各自影响不同环节（stdout / 外部管道 / stdin），缺任一项都可能导致
// 特定场景下编码错配。用测试锁定，避免后续被「简化」掉。
func TestWindowsPowerShellPreambleSetsAllThreeEncodings(t *testing.T) {
	required := []string{
		"[Console]::OutputEncoding",
		"$OutputEncoding",
		"[Console]::InputEncoding",
		"UTF8",
	}
	for _, r := range required {
		if !strings.Contains(windowsPowerShellPreamble, r) {
			t.Errorf("前置语句缺少 %q：\n%s", r, windowsPowerShellPreamble)
		}
	}
}
