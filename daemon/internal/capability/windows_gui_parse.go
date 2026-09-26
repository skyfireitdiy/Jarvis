package capability

// 本文件存放 Windows GUI 能力中「与平台无关的纯逻辑」，刻意不加 //go:build windows
// 标签，以便在 Linux 上编译并单测（本机开发环境为 Linux，无 Windows 运行环境）。
//
// 这里只放不依赖任何 windows 专有类型（uintptr 之外的 syscall 句柄等）的函数：
//   - parseWindowIDString：窗口 ID 字符串解析
//   - parseWindowsKeyCombo：组合键字符串解析
//   - virtualKeyCode：按键名到虚拟键码的映射
//   - mouseButtonFlags：鼠标按键名到 mouse_event 标志的映射
//   - encodePowerShellText：PowerShell 文本参数的安全编码（防命令注入）

import (
	"fmt"
	"strconv"
	"strings"
)

// parseWindowIDString 把字符串形式的窗口 ID 解析为无符号整数。
//
// 支持 "0x" 前缀的十六进制与纯十进制两种写法（strconv.ParseUint 的 base=0
// 会自动识别 0x/0X 前缀）。调用方负责把结果转换为 HWND（uintptr）。
//
// 之所以把纯解析逻辑放在本文件而非 windows_gui_windows.go：这样可以在 Linux
// 上直接单测，而 windows 侧只需一层薄封装（见 windows_gui_windows.go 的
// parseWindowID）。
func parseWindowIDString(s string) (uint64, error) {
	trimmed := strings.TrimSpace(s)
	if trimmed == "" {
		return 0, fmt.Errorf("参数 window_id 不能为空")
	}
	v, err := strconv.ParseUint(trimmed, 0, 64)
	if err != nil {
		return 0, fmt.Errorf("参数 window_id 格式非法 %q，应为 0x 前缀十六进制或十进制整数", s)
	}
	if v == 0 {
		return 0, fmt.Errorf("参数 window_id 不能为 0")
	}
	return v, nil
}

// windowsModifierNames 是修饰键别名的归一化映射。
//
// 键为小写别名，值为归一化后的修饰键名（ctrl/alt/shift/win）。
// ctrl 与 control 等价；win 与 super/meta 等价（Linux 侧 xdotool 用 super，
// Windows 侧习惯叫 win，两者都接受）。
var windowsModifierNames = map[string]string{
	"ctrl":    "ctrl",
	"control": "ctrl",
	"alt":     "alt",
	"shift":   "shift",
	"win":     "win",
	"super":   "win",
	"meta":    "win",
}

// parseWindowsKeyCombo 解析「修饰键+主键」形式的组合键字符串。
//
// 语法：以 '+' 连接，如 "ctrl+c"、"alt+Tab"、"ctrl+shift+s"、"Return"（无修饰键）。
// 修饰键名大小写不敏感，支持 ctrl/control、alt、shift、win/super/meta。
//
// 返回归一化后的修饰键列表（按输入顺序，可能为空）与主键名（保留原始大小写，
// 由 virtualKeyCode 再做大小写不敏感匹配）。
//
// 错误情形：空串、连续加号（如 "ctrl++c"）、以加号开头或结尾、未知修饰键、
// 缺少主键。注意：'+' 本身作为主键（加号键）暂不支持，会因「缺少主键」报错，
// 这是有意的取舍——Windows 侧发送加号键应走 windows.input.type。
func parseWindowsKeyCombo(keys string) ([]string, string, error) {
	trimmed := strings.TrimSpace(keys)
	if trimmed == "" {
		return nil, "", fmt.Errorf("参数 keys 不能为空")
	}

	parts := strings.Split(trimmed, "+")
	// 以 '+' 开头/结尾或出现空段（连续加号）都视为非法。
	for _, p := range parts {
		if strings.TrimSpace(p) == "" {
			return nil, "", fmt.Errorf("参数 keys 格式非法 %q，加号两侧不能为空", keys)
		}
	}

	// 最后一段是主键，其余都是修饰键。
	key := strings.TrimSpace(parts[len(parts)-1])
	modifiers := make([]string, 0, len(parts)-1)
	seen := make(map[string]struct{}, len(parts)-1)
	for _, raw := range parts[:len(parts)-1] {
		name := strings.ToLower(strings.TrimSpace(raw))
		normalized, ok := windowsModifierNames[name]
		if !ok {
			return nil, "", fmt.Errorf("参数 keys 中的 %q 不是有效的修饰键，"+
				"支持 ctrl/control、alt、shift、win/super/meta", raw)
		}
		// 去重：ctrl+ctrl+c 只按一次 Ctrl。
		if _, dup := seen[normalized]; dup {
			continue
		}
		seen[normalized] = struct{}{}
		modifiers = append(modifiers, normalized)
	}

	if key == "" {
		return nil, "", fmt.Errorf("参数 keys 格式非法 %q，缺少主键", keys)
	}
	return modifiers, key, nil
}

// windowsSpecialKeys 是特殊按键名到虚拟键码的映射。
//
// 键为小写按键名（含常见别名），值为对应的 Win32 虚拟键码（VK_*）。
// 单字母与单数字不在此表中，由 virtualKeyCode 单独处理。
var windowsSpecialKeys = map[string]uint16{
	// 编辑与空白
	"return":    0x0D, // VK_RETURN
	"enter":     0x0D,
	"tab":       0x09, // VK_TAB
	"esc":       0x1B, // VK_ESCAPE
	"escape":    0x1B,
	"space":     0x20, // VK_SPACE
	"backspace": 0x08, // VK_BACK
	"delete":    0x2E, // VK_DELETE
	"del":       0x2E,
	"insert":    0x2D, // VK_INSERT
	"ins":       0x2D,

	// 导航
	"home":     0x24, // VK_HOME
	"end":      0x23, // VK_END
	"pageup":   0x21, // VK_PRIOR
	"prior":    0x21,
	"pagedown": 0x22, // VK_NEXT
	"next":     0x22,
	"left":     0x25, // VK_LEFT
	"up":       0x26, // VK_UP
	"right":    0x27, // VK_RIGHT
	"down":     0x28, // VK_DOWN

	// 修饰键本身也可作为主键名出现（如 "win"、"ctrl"）。
	// 这里补齐别名，保证 parseWindowsKeyCombo 归一化出的修饰键名
	// 能被 virtualKeyCode 正确映射——否则 "ctrl+super+Tab" 这类组合
	// 会在查主键码时失败。
	"ctrl":    0x11, // VK_CONTROL
	"control": 0x11,
	"alt":     0x12, // VK_MENU
	"shift":   0x10, // VK_SHIFT
	"win":     0x5B, // VK_LWIN
	"super":   0x5B,
	"meta":    0x5B,
}

// windowsFunctionKeyBase 是 F1 的虚拟键码，F1-F12 依次递增。
const windowsFunctionKeyBase = 0x70 // VK_F1

// virtualKeyCode 把按键名映射为 Win32 虚拟键码。
//
// 大小写不敏感。支持：
//   - 单字母 a-z（VK 码 0x41-0x5A）
//   - 单数字 0-9（VK 码 0x30-0x39）
//   - 特殊键（见 windowsSpecialKeys）
//   - 功能键 F1-F12（VK 码 0x70-0x7B）
//
// 未知按键名返回 ok=false，由调用方决定如何报错。
func virtualKeyCode(name string) (uint16, bool) {
	n := strings.ToLower(strings.TrimSpace(name))
	if n == "" {
		return 0, false
	}

	// 单字母：a-z → 0x41-0x5A。
	if len(n) == 1 {
		c := n[0]
		switch {
		case c >= 'a' && c <= 'z':
			return uint16(c - 'a' + 0x41), true
		case c >= '0' && c <= '9':
			return uint16(c - '0' + 0x30), true
		}
	}

	// 功能键 F1-F12。
	if len(n) >= 2 && n[0] == 'f' {
		if num, err := strconv.Atoi(n[1:]); err == nil && num >= 1 && num <= 12 {
			return uint16(windowsFunctionKeyBase + num - 1), true
		}
	}

	if vk, ok := windowsSpecialKeys[n]; ok {
		return vk, true
	}
	return 0, false
}

// mouseButtonFlags 返回指定鼠标按键在「按下」或「抬起」时对应的 mouse_event 标志。
//
// button 支持 left/right/middle（大小写不敏感）；down 为 true 表示按下。
// 未知按键名返回 0 与 false。
func mouseButtonFlags(button string, down bool) (uint32, bool) {
	switch strings.ToLower(strings.TrimSpace(button)) {
	case "left":
		if down {
			return 0x0002, true // MOUSEEVENTF_LEFTDOWN
		}
		return 0x0004, true // MOUSEEVENTF_LEFTUP
	case "right":
		if down {
			return 0x0008, true // MOUSEEVENTF_RIGHTDOWN
		}
		return 0x0010, true // MOUSEEVENTF_RIGHTUP
	case "middle":
		if down {
			return 0x0020, true // MOUSEEVENTF_MIDDLEDOWN
		}
		return 0x0040, true // MOUSEEVENTF_MIDDLEUP
	default:
		return 0, false
	}
}

// encodePowerShellText 把任意文本编码为可安全嵌入 PowerShell 命令的形式。
//
// 用途：windows.clipboard.set 需要把用户提供的文本传给 PowerShell 的
// Set-Clipboard。**绝不能把文本直接拼进命令字符串**（引号、$、;、反引号、
// 换行等都可能造成命令注入）。
//
// 做法：返回单引号包裹的 PowerShell 字面量，并把文本中的单引号按 PowerShell
// 规则转义为「两个连续单引号」。PowerShell 的单引号字符串是「字面量」，内部的
// $、反引号、分号等都不做解释，因此这是安全且不改变内容的编码方式。
//
// 注意：调用方仍需把该字面量作为 -Command 参数整体传入，不要再用双引号包裹。
func encodePowerShellText(text string) string {
	return "'" + strings.ReplaceAll(text, "'", "''") + "'"
}
