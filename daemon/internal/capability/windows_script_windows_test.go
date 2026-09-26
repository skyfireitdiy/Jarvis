//go:build windows

package capability

// 本文件单测 windows_script_windows.go 中「不依赖真实 Windows 运行环境」的纯函数：
// 解释器解析、命令行构造、环境变量拼装。
//
// 带 //go:build windows 标签：被测对象只在 Windows 构建下存在。
// 在 Linux 上可用 `GOOS=windows go vet ./...` 做编译期检查；实际执行需在 Windows 上。

import (
	"encoding/base64"
	"strings"
	"testing"
	"unicode/utf16"
)

// TestResolveWindowsScriptInterpreter 验证解释器白名单解析。
func TestResolveWindowsScriptInterpreter(t *testing.T) {
	cases := []struct {
		name    string
		in      map[string]any
		want    string
		wantErr bool
	}{
		{name: "缺省为 powershell", in: map[string]any{}, want: "powershell"},
		{name: "显式 powershell", in: map[string]any{"interpreter": "powershell"}, want: "powershell"},
		{name: "大小写不敏感", in: map[string]any{"interpreter": "PowerShell.EXE"}, want: "powershell.exe"},
		{name: "pwsh", in: map[string]any{"interpreter": "pwsh"}, want: "pwsh"},
		{name: "cmd", in: map[string]any{"interpreter": "cmd.exe"}, want: "cmd.exe"},
		{name: "不在白名单则报错", in: map[string]any{"interpreter": "/bin/sh"}, wantErr: true},
		{name: "空串视为缺省", in: map[string]any{"interpreter": ""}, want: "powershell"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := resolveWindowsScriptInterpreter(tc.in)
			if tc.wantErr {
				if err == nil {
					t.Errorf("期望报错，得到 %q", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("意外错误: %v", err)
			}
			if got != tc.want {
				t.Errorf("期望 %q，得到 %q", tc.want, got)
			}
		})
	}
}

// TestBuildWindowsScriptCommandPowerShell 验证 PowerShell 走 -EncodedCommand。
func TestBuildWindowsScriptCommandPowerShell(t *testing.T) {
	script := "Write-Output '中文测试'"
	args, cleanup, err := buildWindowsScriptCommand("powershell", script)
	if err != nil {
		t.Fatalf("构造命令失败: %v", err)
	}
	defer cleanup()

	joined := strings.Join(args, " ")
	if !strings.Contains(joined, "-EncodedCommand") {
		t.Fatalf("PowerShell 应使用 -EncodedCommand，实际参数: %v", args)
	}
	if !strings.Contains(joined, "-NoProfile") || !strings.Contains(joined, "-NonInteractive") {
		t.Fatalf("缺少 -NoProfile/-NonInteractive，实际参数: %v", args)
	}

	// 取出 -EncodedCommand 的值，解码后应含原脚本与 preamble。
	idx := -1
	for i, a := range args {
		if a == "-EncodedCommand" {
			idx = i
			break
		}
	}
	if idx < 0 || idx+1 >= len(args) {
		t.Fatalf("未找到 -EncodedCommand 的值，参数: %v", args)
	}
	raw, err := base64.StdEncoding.DecodeString(args[idx+1])
	if err != nil {
		t.Fatalf("base64 解码失败: %v", err)
	}
	// 还原 UTF-16LE。
	u16 := make([]uint16, 0, len(raw)/2)
	for i := 0; i+1 < len(raw); i += 2 {
		u16 = append(u16, uint16(raw[i])|uint16(raw[i+1])<<8)
	}
	decoded := string(utf16.Decode(u16))
	if !strings.Contains(decoded, script) {
		t.Errorf("解码后应含原脚本，实际: %q", decoded)
	}
	if !strings.Contains(decoded, "OutputEncoding") {
		t.Errorf("解码后应含编码 preamble，实际: %q", decoded)
	}
}

// TestBuildWindowsScriptCommandCmd 验证 cmd 走临时 .cmd 文件。
func TestBuildWindowsScriptCommandCmd(t *testing.T) {
	args, cleanup, err := buildWindowsScriptCommand("cmd", "echo hi")
	if err != nil {
		t.Fatalf("构造命令失败: %v", err)
	}
	defer cleanup()

	if len(args) != 2 || args[0] != "/C" {
		t.Fatalf("cmd 参数应为 [/C <临时文件>]，实际: %v", args)
	}
	if !strings.HasSuffix(args[1], ".cmd") {
		t.Fatalf("临时文件应以 .cmd 结尾，实际: %q", args[1])
	}
}

// TestBuildWindowsScriptCommandUnknown 验证未知解释器报错。
func TestBuildWindowsScriptCommandUnknown(t *testing.T) {
	if _, _, err := buildWindowsScriptCommand("bash", "echo hi"); err == nil {
		t.Fatal("未知解释器应报错")
	}
}

// TestBuildWindowsEnvPairs 验证环境变量拼装。
func TestBuildWindowsEnvPairs(t *testing.T) {
	got := buildWindowsEnvPairs(map[string]string{"A": "1", "B": "2"})
	if len(got) != 2 {
		t.Fatalf("期望 2 项，实际 %v", got)
	}
	// map 顺序不定，用集合判断。
	set := map[string]bool{}
	for _, kv := range got {
		set[kv] = true
	}
	if !set["A=1"] || !set["B=2"] {
		t.Fatalf("环境变量拼装错误: %v", got)
	}

	// 空键应跳过。
	got = buildWindowsEnvPairs(map[string]string{"": "x", "C": "3"})
	if len(got) != 1 || got[0] != "C=3" {
		t.Fatalf("空键应被跳过，实际: %v", got)
	}
}
