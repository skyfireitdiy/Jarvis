//go:build windows

package capability

// 本文件实现 Windows 平台的输入模拟能力（windows.input.*）。
//
// 与窗口能力（windows_gui_windows.go）一样，直接通过 syscall 调用 user32.dll，
// 零第三方依赖、零 cgo。与 Linux 侧（调用 xdotool）不同，Windows 侧不依赖任何
// 外部命令。
//
// 注意：本机开发环境为 Linux，无 Windows 运行环境，因此本文件只能保证
// 「在 GOOS=windows 下编译通过」，各能力的成功路径未做端到端验证。
// 参数校验与纯解析逻辑（组合键解析、虚拟键码映射、鼠标标志映射）已抽取到
// 无构建标签的 windows_gui_parse.go，可在 Linux 上单测。

import (
	"fmt"
	"time"
	"unsafe"
)

// user32.dll 的输入相关过程。
//
// 注意：user32 这个包级变量已在 windows_gui_windows.go 中定义，此处直接复用，
// 不重复定义。
var (
	procSetCursorPos = user32.NewProc("SetCursorPos")
	procMouseEvent   = user32.NewProc("mouse_event")
	procKeybdEvent   = user32.NewProc("keybd_event")
	procSendInput    = user32.NewProc("SendInput")
)

// 键盘事件标志（keybd_event 的 dwFlags）。
const (
	// keyeventfKeyUp 表示「抬起」事件；不带此标志为「按下」。
	keyeventfKeyUp = 0x0002
)

// windowsInputTool 是输入能力返回结果中 tool 字段的值。
const windowsInputTool = "user32.dll"

// registerWindowsInput 注册 Windows 输入模拟能力。
func registerWindowsInput(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.input.click",
		Description: "在指定屏幕坐标点击鼠标。" +
			"先 SetCursorPos 移动光标，再用 mouse_event 发送按下/抬起。" +
			"坐标以主屏左上角为原点（像素）。无需任何外部命令或第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"x": map[string]any{
					"type":        "integer",
					"description": "屏幕横坐标（像素），允许为 0。",
				},
				"y": map[string]any{
					"type":        "integer",
					"description": "屏幕纵坐标（像素），允许为 0。",
				},
				"button": map[string]any{
					"type":        "string",
					"description": "鼠标按键，默认 left；支持 left/right/middle。",
				},
				"count": map[string]any{
					"type":        "integer",
					"description": "点击次数，默认 1；设为 2 可实现双击。",
				},
			},
			"required": []string{"x", "y"},
		},
		Handler: handleWindowsInputClick,
	})

	_ = reg.Register(Capability{
		Name: "windows.input.type",
		Description: "向当前聚焦窗口键入文本。" +
			"通过 keybd_event 的 Unicode 扫描码（VK=0，配合 KEYEVENTF_UNICODE 语义）" +
			"逐字符发送，可正确输入中文等非 ASCII 字符。" +
			"注意：本能力只发送字符本身，不解析控制序列。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"text": map[string]any{
					"type":        "string",
					"description": "要键入的文本。",
				},
				"delay_ms": map[string]any{
					"type":        "integer",
					"description": "每个字符之间的延迟毫秒数，默认 0（不延迟）；不能为负。",
				},
			},
			"required": []string{"text"},
		},
		Handler: handleWindowsInputType,
	})

	_ = reg.Register(Capability{
		Name: "windows.input.keys",
		Description: "向当前聚焦窗口发送按键组合，如 ctrl+c、alt+Tab、ctrl+shift+s、Return。" +
			"修饰键支持 ctrl/control、alt、shift、win/super/meta；主键支持字母、数字、" +
			"功能键 F1-F12、方向键与常见特殊键。无需任何外部命令或第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"keys": map[string]any{
					"type":        "string",
					"description": "按键序列，如 ctrl+c、alt+Tab、ctrl+shift+s、Return。",
				},
			},
			"required": []string{"keys"},
		},
		Handler: handleWindowsInputKeys,
	})
}

// handleWindowsInputClick 是 windows.input.click 的实现。
func handleWindowsInputClick(params map[string]any) (any, error) {
	// x/y 允许为 0（屏幕左上角），因此必须用 requiredInt 显式判断是否提供，
	// 不能复用 optionalInt 的默认值语义。
	x, err := requiredInt(params, "x")
	if err != nil {
		return nil, err
	}
	y, err := requiredInt(params, "y")
	if err != nil {
		return nil, err
	}

	button, err := optionalString(params, "button")
	if err != nil {
		return nil, err
	}
	if button == "" {
		button = "left"
	}
	downFlag, ok := mouseButtonFlags(button, true)
	if !ok {
		return nil, fmt.Errorf("参数 button 不支持 %q，允许值: left、right、middle", button)
	}
	upFlag, _ := mouseButtonFlags(button, false)

	count, err := optionalInt(params, "count", 1)
	if err != nil {
		return nil, err
	}
	if count <= 0 {
		return nil, fmt.Errorf("参数 count 必须为正整数，实际 %d", count)
	}

	// 移动光标：SetCursorPos 返回 0 表示失败。
	if r, _, err := procSetCursorPos.Call(uintptr(x), uintptr(y)); r == 0 {
		return nil, fmt.Errorf("移动光标到 (%d, %d) 失败: %v", x, y, err)
	}

	for i := 0; i < count; i++ {
		procMouseEvent.Call(uintptr(downFlag), 0, 0, 0, 0)
		procMouseEvent.Call(uintptr(upFlag), 0, 0, 0, 0)
	}

	return map[string]any{
		"x":      x,
		"y":      y,
		"button": button,
		"count":  count,
		"tool":   windowsInputTool,
	}, nil
}

// handleWindowsInputType 是 windows.input.type 的实现。
func handleWindowsInputType(params map[string]any) (any, error) {
	text, err := requiredString(params, "text")
	if err != nil {
		return nil, err
	}

	delayMS, err := optionalInt(params, "delay_ms", 0)
	if err != nil {
		return nil, err
	}
	if delayMS < 0 {
		return nil, fmt.Errorf("参数 delay_ms 不能为负数，实际 %d", delayMS)
	}

	// 逐字符发送 Unicode。
	//
	// 方案说明：这里用 SendInput + KEYBDINPUT（dwFlags 带 KEYEVENTF_UNICODE）。
	// 这是 Windows 上输入任意 Unicode 字符（含中文）的标准做法：
	//   - wVk 置 0，wScan 置 UTF-16 码元，dwFlags 带 KEYEVENTF_UNICODE(0x0004)，
	//     系统会把该码元当作字符注入，不经过键盘布局转换；
	//   - 每个字符发送「按下 + 抬起」两个事件。
	//
	// 为什么不用 keybd_event：keybd_event 只接受虚拟键码，没有 KEYEVENTF_UNICODE
	// 语义，无法直接输入非 ASCII 字符（中文会丢失）。SendInput 是唯一可靠路径。
	//
	// 结构体布局风险：INPUT 在 64 位下为 40 字节（type 4 + 对齐 4 + 联合体 32），
	// KEYBDINPUT 为 24 字节（wVk 2 + wScan 2 + dwFlags 4 + time 4 + dwExtraInfo 8
	// + 对齐 4）。下方结构体定义严格按 Win32 布局书写，并用编译期断言校验尺寸，
	// 布局不符会在编译期暴露而非运行时静默失败。
	const keyeventfUnicode = 0x0004
	for _, r := range text {
		// 用 rune 遍历以正确处理 BMP 之外的字符；对代理对（surrogate pair）
		// 需要拆成两个 UTF-16 码元分别发送。
		if r > 0xFFFF {
			hi, lo := utf16SurrogatePair(r)
			sendUnicodeChar(hi, keyeventfUnicode)
			sendUnicodeChar(lo, keyeventfUnicode)
		} else {
			sendUnicodeChar(uint16(r), keyeventfUnicode)
		}
		if delayMS > 0 {
			time.Sleep(time.Duration(delayMS) * time.Millisecond)
		}
	}

	return map[string]any{
		"typed": text,
		"tool":  windowsInputTool,
	}, nil
}

// windowsKeybdInput 对应 Win32 的 KEYBDINPUT 结构。
//
// 字段顺序与类型严格按 Windows SDK 定义：
//
//	typedef struct tagKEYBDINPUT {
//	    WORD      wVk;
//	    WORD      wScan;
//	    DWORD     dwFlags;
//	    DWORD     time;
//	    ULONG_PTR dwExtraInfo;   // 指针宽度：32 位 4 字节，64 位 8 字节
//	} KEYBDINPUT;
type windowsKeybdInput struct {
	WVk         uint16
	WScan       uint16
	DwFlags     uint32
	Time        uint32
	DwExtraInfo uintptr
}

// inputKeyboard 是 INPUT 结构 type 字段的取值 INPUT_KEYBOARD。
const inputKeyboard = 1

// windowsInputSize 是 Win32 INPUT 结构的大小。
//
// INPUT 是「DWORD type + 联合体」，联合体最大成员是 MOUSEINPUT：
//   - 64 位：MOUSEINPUT 32 字节，加上 type 4 字节与 4 字节对齐 = 40 字节；
//   - 32 位：MOUSEINPUT 24 字节，加上 type 4 字节 = 28 字节。
//
// 这里按 64 位取值 40。SendInput 会按 cbSize 校验，传错大小会直接失败
// （返回 0 并置 LastError），不会静默出错。
//
// 注意：本值仅对 64 位 Windows 正确。当前构建矩阵的 Windows 目标为
// amd64/arm64（均为 64 位），故安全；若将来需要支持 386，需改为按
// unsafe.Sizeof(uintptr(0)) 动态计算（32 位取 28）。下方编译期断言会在
// 32 位构建时直接失败，避免静默出错。
const windowsInputSize = 40

// 编译期断言：windowsInputSize 只在 64 位下正确。
//
// 若在 32 位（GOARCH=386/arm）下构建，数组长度会变成负数，直接编译失败，
// 提示需要调整 windowsInputSize 与联合体偏移，而不是运行时静默出错。
var _ [unsafe.Sizeof(uintptr(0)) - 8]struct{}

// sendInputKeyboard 用 SendInput 发送一个键盘事件。
//
// 之所以手工按字节偏移构造 INPUT，而不是定义 Go struct：Go 无法表达 Win32
// 的「type + union」布局——union 的对齐要求（8 字节）无法用 Go 字段自然得到
// （[32]byte 的对齐只有 1）。手工构造可以精确控制偏移与总大小，避免因结构体
// 布局不符导致的静默失败。
//
// INPUT 的内存布局（64 位）：
//
//	偏移 0  : DWORD type
//	偏移 4  : 4 字节对齐填充
//	偏移 8  : 联合体（KEYBDINPUT 从这里开始）
//
// 因此 KEYBDINPUT 应写入偏移 8 处。
func sendInputKeyboard(kb windowsKeybdInput) {
	var buf [windowsInputSize]byte

	// 写入 type 字段（偏移 0）。
	*(*uint32)(unsafe.Pointer(&buf[0])) = inputKeyboard

	// 写入联合体中的 KEYBDINPUT（偏移 8）。
	*(*windowsKeybdInput)(unsafe.Pointer(&buf[8])) = kb

	procSendInput.Call(
		1,
		uintptr(unsafe.Pointer(&buf[0])),
		uintptr(windowsInputSize),
	)
}

// sendUnicodeChar 用 SendInput 发送一个 UTF-16 码元的按下与抬起事件。
//
// KEYEVENTF_UNICODE 要求 wVk 为 0、wScan 为 UTF-16 码元。
func sendUnicodeChar(code uint16, unicodeFlag uint32) {
	// 按下事件。
	sendInputKeyboard(windowsKeybdInput{WScan: code, DwFlags: unicodeFlag})
	// 抬起事件。
	sendInputKeyboard(windowsKeybdInput{WScan: code, DwFlags: unicodeFlag | keyeventfKeyUp})
}

// utf16SurrogatePair 把 U+10000 以上的码点拆成 UTF-16 代理对。
func utf16SurrogatePair(r rune) (uint16, uint16) {
	v := uint32(r) - 0x10000
	hi := uint16(0xD800 + (v >> 10))
	lo := uint16(0xDC00 + (v & 0x3FF))
	return hi, lo
}

// handleWindowsInputKeys 是 windows.input.keys 的实现。
func handleWindowsInputKeys(params map[string]any) (any, error) {
	keys, err := requiredString(params, "keys")
	if err != nil {
		return nil, err
	}

	modifiers, keyName, err := parseWindowsKeyCombo(keys)
	if err != nil {
		return nil, err
	}

	keyVK, ok := virtualKeyCode(keyName)
	if !ok {
		return nil, fmt.Errorf("不支持的按键名 %q", keyName)
	}

	modifierVKs := make([]uint16, 0, len(modifiers))
	for _, m := range modifiers {
		vk, ok := virtualKeyCode(m)
		if !ok {
			// parseWindowsKeyCombo 已校验过修饰键名，正常不会走到这里。
			return nil, fmt.Errorf("不支持的修饰键 %q", m)
		}
		modifierVKs = append(modifierVKs, vk)
	}

	// 依次按下修饰键。
	for _, vk := range modifierVKs {
		procKeybdEvent.Call(uintptr(vk), 0, 0, 0)
	}
	// 按下并抬起主键。
	procKeybdEvent.Call(uintptr(keyVK), 0, 0, 0)
	procKeybdEvent.Call(uintptr(keyVK), 0, uintptr(keyeventfKeyUp), 0)
	// 逆序抬起修饰键。
	for i := len(modifierVKs) - 1; i >= 0; i-- {
		procKeybdEvent.Call(uintptr(modifierVKs[i]), 0, uintptr(keyeventfKeyUp), 0)
	}

	return map[string]any{
		"keys": keys,
		"tool": windowsInputTool,
	}, nil
}
