package capability

// 本文件测试 windows_gui_parse.go 中的纯逻辑函数。
//
// 这些函数刻意不带 //go:build windows 标签，因此可在 Linux/macOS 上编译运行，
// 从而在「本机无 Windows 运行环境」的前提下，仍能验证 Windows GUI 能力中
// 参数解析与编码逻辑的正确性（尤其是防命令注入的 encodePowerShellText）。
//
// 只使用标准库 testing，不引入任何第三方断言库。

import (
	"strings"
	"testing"
)

// TestParseWindowIDString 覆盖窗口 ID 解析的正常与异常路径。
func TestParseWindowIDString(t *testing.T) {
	cases := []struct {
		name    string
		in      string
		want    uint64
		wantErr bool
	}{
		{name: "十六进制小写前缀", in: "0x00010A2C", want: 0x00010A2C},
		{name: "十六进制大写前缀", in: "0X00010A2C", want: 0x00010A2C},
		{name: "十六进制无补零", in: "0x1", want: 1},
		{name: "十进制", in: "65535", want: 65535},
		{name: "两侧空白被裁剪", in: "  0x10  ", want: 0x10},
		{name: "空串报错", in: "", wantErr: true},
		{name: "纯空白报错", in: "   ", wantErr: true},
		{name: "非数字报错", in: "abc", wantErr: true},
		{name: "零值报错", in: "0", wantErr: true},
		{name: "十六进制零报错", in: "0x0", wantErr: true},
		{name: "负数报错", in: "-1", wantErr: true},
		{name: "小数报错", in: "1.5", wantErr: true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := parseWindowIDString(tc.in)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("parseWindowIDString(%q) 期望报错，实际返回 %d", tc.in, got)
				}
				return
			}
			if err != nil {
				t.Fatalf("parseWindowIDString(%q) 意外报错: %v", tc.in, err)
			}
			if got != tc.want {
				t.Fatalf("parseWindowIDString(%q) = %d, want %d", tc.in, got, tc.want)
			}
		})
	}
}

// TestParseWindowsKeyCombo 覆盖组合键解析。
func TestParseWindowsKeyCombo(t *testing.T) {
	t.Run("无修饰键", func(t *testing.T) {
		mods, key, err := parseWindowsKeyCombo("Return")
		if err != nil {
			t.Fatalf("意外报错: %v", err)
		}
		if len(mods) != 0 {
			t.Fatalf("期望无修饰键，实际 %v", mods)
		}
		if key != "Return" {
			t.Fatalf("主键应为 Return，实际 %q", key)
		}
	})

	t.Run("单修饰键", func(t *testing.T) {
		mods, key, err := parseWindowsKeyCombo("ctrl+c")
		if err != nil {
			t.Fatalf("意外报错: %v", err)
		}
		if len(mods) != 1 || mods[0] != "ctrl" {
			t.Fatalf("修饰键应为 [ctrl]，实际 %v", mods)
		}
		if key != "c" {
			t.Fatalf("主键应为 c，实际 %q", key)
		}
	})

	t.Run("多修饰键保持输入顺序", func(t *testing.T) {
		mods, key, err := parseWindowsKeyCombo("ctrl+shift+s")
		if err != nil {
			t.Fatalf("意外报错: %v", err)
		}
		if len(mods) != 2 || mods[0] != "ctrl" || mods[1] != "shift" {
			t.Fatalf("修饰键应为 [ctrl shift]，实际 %v", mods)
		}
		if key != "s" {
			t.Fatalf("主键应为 s，实际 %q", key)
		}
	})

	t.Run("修饰键别名归一化", func(t *testing.T) {
		mods, _, err := parseWindowsKeyCombo("control+alt+super+Tab")
		if err != nil {
			t.Fatalf("意外报错: %v", err)
		}
		want := []string{"ctrl", "alt", "win"}
		if len(mods) != len(want) {
			t.Fatalf("修饰键数量不符: got %v, want %v", mods, want)
		}
		for i := range want {
			if mods[i] != want[i] {
				t.Fatalf("修饰键 %d 不符: got %v, want %v", i, mods, want)
			}
		}
	})

	t.Run("修饰键大小写不敏感", func(t *testing.T) {
		mods, key, err := parseWindowsKeyCombo("CTRL+C")
		if err != nil {
			t.Fatalf("意外报错: %v", err)
		}
		if len(mods) != 1 || mods[0] != "ctrl" {
			t.Fatalf("修饰键应为 [ctrl]，实际 %v", mods)
		}
		// 主键保留原始大小写（由 virtualKeyCode 再做大小写不敏感匹配）。
		if key != "C" {
			t.Fatalf("主键应保留原始大小写 C，实际 %q", key)
		}
	})

	t.Run("重复修饰键去重", func(t *testing.T) {
		mods, _, err := parseWindowsKeyCombo("ctrl+ctrl+c")
		if err != nil {
			t.Fatalf("意外报错: %v", err)
		}
		if len(mods) != 1 {
			t.Fatalf("重复修饰键应去重为 1 个，实际 %v", mods)
		}
	})

	t.Run("别名重复也去重", func(t *testing.T) {
		mods, _, err := parseWindowsKeyCombo("ctrl+control+c")
		if err != nil {
			t.Fatalf("意外报错: %v", err)
		}
		if len(mods) != 1 {
			t.Fatalf("别名重复应去重为 1 个，实际 %v", mods)
		}
	})

	t.Run("段内空白被裁剪", func(t *testing.T) {
		mods, key, err := parseWindowsKeyCombo(" ctrl + c ")
		if err != nil {
			t.Fatalf("意外报错: %v", err)
		}
		if len(mods) != 1 || mods[0] != "ctrl" {
			t.Fatalf("修饰键应为 [ctrl]，实际 %v", mods)
		}
		if key != "c" {
			t.Fatalf("主键应为 c，实际 %q", key)
		}
	})

	errCases := []struct {
		name string
		in   string
	}{
		{name: "空串", in: ""},
		{name: "纯空白", in: "   "},
		{name: "以加号开头", in: "+c"},
		{name: "以加号结尾", in: "ctrl+"},
		{name: "连续加号", in: "ctrl++c"},
		{name: "未知修饰键", in: "foo+c"},
		{name: "仅有修饰键", in: "ctrl+"},
	}
	for _, tc := range errCases {
		t.Run(tc.name, func(t *testing.T) {
			if _, _, err := parseWindowsKeyCombo(tc.in); err == nil {
				t.Fatalf("parseWindowsKeyCombo(%q) 期望报错", tc.in)
			}
		})
	}
}

// TestVirtualKeyCode 覆盖按键名到虚拟键码的映射。
func TestVirtualKeyCode(t *testing.T) {
	cases := []struct {
		name   string
		in     string
		want   uint16
		wantOK bool
	}{
		{name: "小写字母", in: "a", want: 0x41, wantOK: true},
		{name: "大写字母", in: "Z", want: 0x5A, wantOK: true},
		{name: "数字", in: "0", want: 0x30, wantOK: true},
		{name: "数字九", in: "9", want: 0x39, wantOK: true},
		{name: "回车小写", in: "return", want: 0x0D, wantOK: true},
		{name: "回车别名", in: "Enter", want: 0x0D, wantOK: true},
		{name: "Tab", in: "tab", want: 0x09, wantOK: true},
		{name: "Esc 别名", in: "escape", want: 0x1B, wantOK: true},
		{name: "空格", in: "space", want: 0x20, wantOK: true},
		{name: "退格", in: "backspace", want: 0x08, wantOK: true},
		{name: "Delete 别名", in: "del", want: 0x2E, wantOK: true},
		{name: "Insert 别名", in: "ins", want: 0x2D, wantOK: true},
		{name: "PageUp 别名", in: "prior", want: 0x21, wantOK: true},
		{name: "PageDown 别名", in: "next", want: 0x22, wantOK: true},
		{name: "方向键左", in: "left", want: 0x25, wantOK: true},
		{name: "方向键下", in: "DOWN", want: 0x28, wantOK: true},
		{name: "F1", in: "f1", want: 0x70, wantOK: true},
		{name: "F12", in: "F12", want: 0x7B, wantOK: true},
		{name: "两侧空白", in: "  tab  ", want: 0x09, wantOK: true},

		{name: "空串", in: "", wantOK: false},
		{name: "空白串", in: "   ", wantOK: false},
		{name: "未知键名", in: "unknownkey", wantOK: false},
		{name: "F0 越界", in: "f0", wantOK: false},
		{name: "F13 越界", in: "f13", wantOK: false},
		{name: "符号键不支持", in: "+", wantOK: false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := virtualKeyCode(tc.in)
			if ok != tc.wantOK {
				t.Fatalf("virtualKeyCode(%q) ok = %v, want %v", tc.in, ok, tc.wantOK)
			}
			if tc.wantOK && got != tc.want {
				t.Fatalf("virtualKeyCode(%q) = 0x%02X, want 0x%02X", tc.in, got, tc.want)
			}
		})
	}
}

// TestMouseButtonFlags 覆盖鼠标按键标志映射。
func TestMouseButtonFlags(t *testing.T) {
	cases := []struct {
		name   string
		button string
		down   bool
		want   uint32
		wantOK bool
	}{
		{name: "左键按下", button: "left", down: true, want: 0x0002, wantOK: true},
		{name: "左键抬起", button: "left", down: false, want: 0x0004, wantOK: true},
		{name: "右键按下", button: "right", down: true, want: 0x0008, wantOK: true},
		{name: "右键抬起", button: "right", down: false, want: 0x0010, wantOK: true},
		{name: "中键按下", button: "middle", down: true, want: 0x0020, wantOK: true},
		{name: "中键抬起", button: "middle", down: false, want: 0x0040, wantOK: true},
		{name: "大小写不敏感", button: "LEFT", down: true, want: 0x0002, wantOK: true},
		{name: "两侧空白", button: "  right  ", down: false, want: 0x0010, wantOK: true},
		{name: "未知按键", button: "back", down: true, wantOK: false},
		{name: "空串", button: "", down: true, wantOK: false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := mouseButtonFlags(tc.button, tc.down)
			if ok != tc.wantOK {
				t.Fatalf("mouseButtonFlags(%q, %v) ok = %v, want %v",
					tc.button, tc.down, ok, tc.wantOK)
			}
			if tc.wantOK && got != tc.want {
				t.Fatalf("mouseButtonFlags(%q, %v) = 0x%04X, want 0x%04X",
					tc.button, tc.down, got, tc.want)
			}
		})
	}
}

// TestEncodePowerShellText 覆盖 PowerShell 字面量编码。
//
// 这是防命令注入的关键函数，因此除了「编码结果正确」外，还额外验证
// 危险字符确实被包在单引号字面量内部、没有被解释的机会。
func TestEncodePowerShellText(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{name: "普通文本", in: "hello", want: "'hello'"},
		{name: "空串", in: "", want: "''"},
		{name: "单个单引号被双写", in: "it's", want: "'it''s'"},
		{name: "多个单引号", in: "''", want: "''''''"},
		{name: "分号不被转义但被包裹", in: "a;b", want: "'a;b'"},
		{name: "美元符被包裹", in: "$env:PATH", want: "'$env:PATH'"},
		{name: "反引号被包裹", in: "`whoami`", want: "'`whoami`'"},
		{name: "换行保留", in: "a\nb", want: "'a\nb'"},
		{name: "回车保留", in: "a\r\nb", want: "'a\r\nb'"},
		{name: "中文保留", in: "你好，世界", want: "'你好，世界'"},
		{name: "反斜杠保留", in: `C:\Users\me`, want: `'C:\Users\me'`},
		{name: "双引号保留", in: `say "hi"`, want: `'say "hi"'`},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := encodePowerShellText(tc.in); got != tc.want {
				t.Fatalf("encodePowerShellText(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}

	t.Run("编码结果始终被单引号包裹", func(t *testing.T) {
		inputs := []string{
			"plain",
			"'; Remove-Item -Recurse -Force C:\\ #",
			"' ; Invoke-Expression 'calc'",
			"$(Get-Process)",
			"a'b'c",
		}
		for _, in := range inputs {
			got := encodePowerShellText(in)
			if !strings.HasPrefix(got, "'") || !strings.HasSuffix(got, "'") {
				t.Fatalf("编码结果未被单引号包裹: %q", got)
			}
			// 去掉首尾单引号后，内部不应再出现「落单」的单引号
			// （即所有单引号都必须成对，才能保证字面量闭合正确）。
			inner := got[1 : len(got)-1]
			if strings.Count(inner, "'")%2 != 0 {
				t.Fatalf("内部单引号数量为奇数，字面量可能提前闭合: %q", got)
			}
		}
	})

	t.Run("注入尝试不会产生未转义单引号", func(t *testing.T) {
		// 攻击者试图用单引号提前闭合字面量并追加命令。
		malicious := "'; Remove-Item -Recurse -Force C:\\ ; '"
		got := encodePowerShellText(malicious)
		// 原始文本中的每个单引号都应变成两个，因此结果中单引号总数
		// = 原始数量*2 + 首尾各 1。
		wantQuotes := strings.Count(malicious, "'")*2 + 2
		if n := strings.Count(got, "'"); n != wantQuotes {
			t.Fatalf("单引号数量不符: got %d, want %d（编码结果 %q）", n, wantQuotes, got)
		}
	})
}

// TestModifierNamesResolveToVirtualKeyCode 是回归测试。
//
// 背景：parseWindowsKeyCombo 会把修饰键归一化为 ctrl/alt/shift/win，
// 而 handleWindowsInputKeys 随后要用 virtualKeyCode 把这些名字转成虚拟键码。
// 曾出现 "win"（以及 super/meta）能通过 parseWindowsKeyCombo 校验、
// 却无法被 virtualKeyCode 映射的断裂，导致 "ctrl+super+Tab" 这类组合
// 在运行时才报「不支持的修饰键」。本测试锁定该不变量：
// parseWindowsKeyCombo 产出的每个修饰键名都必须能被 virtualKeyCode 映射。
func TestModifierNamesResolveToVirtualKeyCode(t *testing.T) {
	// 覆盖 windowsModifierNames 中的全部别名。
	aliases := []string{
		"ctrl", "control",
		"alt",
		"shift",
		"win", "super", "meta",
	}
	for _, alias := range aliases {
		t.Run(alias, func(t *testing.T) {
			mods, key, err := parseWindowsKeyCombo(alias + "+Tab")
			if err != nil {
				t.Fatalf("parseWindowsKeyCombo(%q) 意外报错: %v", alias+"+Tab", err)
			}
			if key != "Tab" {
				t.Fatalf("主键解析错误: got %q, want %q", key, "Tab")
			}
			if len(mods) != 1 {
				t.Fatalf("修饰键数量错误: got %v", mods)
			}
			vk, ok := virtualKeyCode(mods[0])
			if !ok {
				t.Fatalf("修饰键 %q（来自别名 %q）无法映射为虚拟键码", mods[0], alias)
			}
			if vk == 0 {
				t.Fatalf("修饰键 %q 映射到虚拟键码 0，非法", mods[0])
			}
		})
	}
}

// TestVirtualKeyCodeModifiers 校验修饰键本身的虚拟键码取值正确。
func TestVirtualKeyCodeModifiers(t *testing.T) {
	cases := map[string]uint16{
		"ctrl":    0x11, // VK_CONTROL
		"control": 0x11,
		"alt":     0x12, // VK_MENU
		"shift":   0x10, // VK_SHIFT
		"win":     0x5B, // VK_LWIN
		"super":   0x5B,
		"meta":    0x5B,
	}
	for name, want := range cases {
		t.Run(name, func(t *testing.T) {
			got, ok := virtualKeyCode(name)
			if !ok {
				t.Fatalf("virtualKeyCode(%q) 应可映射", name)
			}
			if got != want {
				t.Fatalf("virtualKeyCode(%q) = 0x%02X, want 0x%02X", name, got, want)
			}
		})
	}
}
