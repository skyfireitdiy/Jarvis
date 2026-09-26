//go:build windows

package capability

import (
	"fmt"
	"sort"
	"strings"
	"sync"
	"syscall"
	"unsafe"
)

// 本文件实现 Windows 平台的窗口控制能力（windows.window.*）。
//
// 设计取舍：与 Linux 侧（linux_gui_linux.go 调用 xdotool/wmctrl 外部命令）不同，
// Windows 侧直接通过 syscall 调用 user32.dll 的 Win32 API。这样做的好处是：
//  1. 零第三方依赖（只用标准库 syscall）；
//  2. 零 cgo，保持 CGO_ENABLED=0 静态链接与交叉编译能力；
//  3. 不依赖用户机器上额外安装任何命令行工具。
//
// 注意：本机开发环境为 Linux，无 Windows 运行环境，因此本文件只能保证
// 「在 GOOS=windows 下编译通过」，各能力的成功路径未做端到端验证。
// 参数校验与纯解析逻辑已抽取到无构建标签的 windows_gui_parse.go，可在 Linux 上单测。

// user32 是 user32.dll 的惰性加载句柄。
//
// 使用 syscall.NewLazyDLL 而非 golang.org/x/sys/windows，是为了不引入任何第三方依赖。
var user32 = syscall.NewLazyDLL("user32.dll")

var (
	procEnumWindows              = user32.NewProc("EnumWindows")
	procIsWindowVisible          = user32.NewProc("IsWindowVisible")
	procIsWindow                 = user32.NewProc("IsWindow")
	procGetWindowTextW           = user32.NewProc("GetWindowTextW")
	procGetWindowTextLengthW     = user32.NewProc("GetWindowTextLengthW")
	procGetWindowThreadProcessID = user32.NewProc("GetWindowThreadProcessId")
	procShowWindow               = user32.NewProc("ShowWindow")
	procSetForegroundWindow      = user32.NewProc("SetForegroundWindow")
	procPostMessageW             = user32.NewProc("PostMessageW")
)

// Win32 常量。
const (
	// swRestore 对应 ShowWindow 的 SW_RESTORE：激活并还原窗口（若已最小化则还原）。
	swRestore = 9

	// wmClose 对应 PostMessage 的 WM_CLOSE：请求窗口关闭（等价于用户点关闭按钮）。
	// 与 Linux 侧 wmctrl -c 语义一致，不强制终止进程。
	wmClose = 0x0010

	// windowsGUITool 是本文件各能力返回结果中 tool 字段的值，便于与 Linux 侧对齐。
	windowsGUITool = "user32.dll"
)

// windowsWindowInfo 描述一个顶层窗口。
//
// 字段顺序即 JSON 序列化顺序；window_id 用字符串表示（如 "0x00010A2C"），
// 与 Linux 侧 window_id 为字符串保持一致。
type windowsWindowInfo struct {
	WindowID string `json:"window_id"`
	Title    string `json:"title"`
	PID      uint32 `json:"pid"`
	Visible  bool   `json:"visible"`
}

// windowsEnumState 是一次 EnumWindows 遍历的收集状态。
//
// 每次调用 enumerateWindows 都新建一个实例，并通过 lparam 传递它在
// windowsEnumStates 注册表中的 key。这样做的原因：
//  1. 回调与调用方共享同一个缓冲区，但该缓冲区是「每次调用私有」的，
//     因此并发调用互不干扰；
//  2. 若改用单个包级共享缓冲区，两个并发调用会互相清空/追加对方的结果，
//     即使加锁也无法修正（锁只能保证互斥，不能隔离两次调用的数据）。
//
// 回调函数本身仍是包级变量：syscall.NewCallback 创建的回调有数量上限
// （约 2000 个），不能在每次调用时新建。
type windowsEnumState struct {
	results []windowsWindowInfo
}

// windowsEnumStates 把 lparam（uintptr）映射到本次遍历的状态对象。
//
// 之所以用注册表而不是直接把 *windowsEnumState 指针塞进 lparam：后者需要在
// 回调里做 uintptr → unsafe.Pointer 转换，会被 go vet 判定为
// "possible misuse of unsafe.Pointer"（uintptr 不携带对象生命周期信息，
// 转换不安全）。用注册表则以整数为 key，完全避免该转换。
//
// 用互斥锁保护：能力可能被网关并发调用。
var (
	windowsEnumStatesMu sync.Mutex
	windowsEnumStates           = make(map[uintptr]*windowsEnumState)
	windowsEnumNextKey  uintptr = 1
)

// enumWindowsCallback 是 EnumWindows 的回调函数。
//
// 定义为包级变量，保证进程生命周期内只创建一次 Go 回调。
// lparam 是本次遍历状态在 windowsEnumStates 中的 key，回调只做数据收集，
// 不做阻塞操作。返回值 1 表示继续枚举，0 表示停止。
var enumWindowsCallback = syscall.NewCallback(func(hwnd uintptr, lparam uintptr) uintptr {
	windowsEnumStatesMu.Lock()
	state := windowsEnumStates[lparam]
	windowsEnumStatesMu.Unlock()
	if state == nil {
		// 找不到状态说明调用方已回收，停止枚举。
		return 0
	}

	// 只收集可见窗口。
	if r, _, _ := procIsWindowVisible.Call(hwnd); r == 0 {
		return 1
	}

	title := getWindowText(hwnd)
	// 过滤掉没有标题的窗口（大量系统隐藏窗口、工具窗口标题为空）。
	if title == "" {
		return 1
	}

	var pid uint32
	procGetWindowThreadProcessID.Call(hwnd, uintptr(unsafe.Pointer(&pid)))

	state.results = append(state.results, windowsWindowInfo{
		WindowID: formatWindowID(hwnd),
		Title:    title,
		PID:      pid,
		Visible:  true,
	})
	return 1
})

// getWindowText 读取窗口标题。
//
// 先取长度再分配缓冲，避免固定长度缓冲导致长标题被截断。
// 注意 GetWindowTextLengthW 对某些窗口可能返回 0，此时直接返回空串。
func getWindowText(hwnd uintptr) string {
	n, _, _ := procGetWindowTextLengthW.Call(hwnd)
	if n == 0 {
		return ""
	}
	// 预留 1 个 UTF-16 单元放结尾的 NUL。
	buf := make([]uint16, int(n)+1)
	procGetWindowTextW.Call(
		hwnd,
		uintptr(unsafe.Pointer(&buf[0])),
		uintptr(len(buf)),
	)
	return syscall.UTF16ToString(buf)
}

// formatWindowID 把 HWND 格式化为 "0x%08X" 形式的字符串。
func formatWindowID(hwnd uintptr) string {
	return fmt.Sprintf("0x%08X", hwnd)
}

// enumerateWindows 枚举所有可见且有标题的顶层窗口。
//
// 返回结果已按标题排序，保证多次调用顺序稳定（EnumWindows 本身不保证顺序）。
// 每次调用使用独立的收集状态，并发调用互不干扰。
func enumerateWindows() []windowsWindowInfo {
	state := &windowsEnumState{results: make([]windowsWindowInfo, 0, 64)}

	// 注册本次遍历状态，取一个唯一的 key 作为 lparam。
	windowsEnumStatesMu.Lock()
	key := windowsEnumNextKey
	windowsEnumNextKey++
	windowsEnumStates[key] = state
	windowsEnumStatesMu.Unlock()

	// EnumWindows 遍历结束返回 0，此时 LastError 无意义，故忽略返回值与 err。
	procEnumWindows.Call(enumWindowsCallback, key)

	// 注销本次遍历状态，避免注册表无限增长。
	windowsEnumStatesMu.Lock()
	delete(windowsEnumStates, key)
	windowsEnumStatesMu.Unlock()

	out := make([]windowsWindowInfo, len(state.results))
	copy(out, state.results)

	sort.Slice(out, func(i, j int) bool {
		if out[i].Title != out[j].Title {
			return out[i].Title < out[j].Title
		}
		return out[i].WindowID < out[j].WindowID
	})
	return out
}

// findWindowByTitle 按标题子串（大小写不敏感）查找第一个匹配的窗口。
func findWindowByTitle(title string) (windowsWindowInfo, bool) {
	needle := strings.ToLower(title)
	for _, w := range enumerateWindows() {
		if strings.Contains(strings.ToLower(w.Title), needle) {
			return w, true
		}
	}
	return windowsWindowInfo{}, false
}

// registerWindowsGUI 注册 Windows 窗口控制能力。
func registerWindowsGUI(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.window.list",
		Description: "列出 Windows 桌面上的顶层窗口。" +
			"通过 user32.dll 的 EnumWindows 枚举，仅返回可见且有标题的窗口" +
			"（已过滤掉标题为空的系统隐藏窗口与工具窗口）。" +
			"无需任何外部命令或第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"filter": map[string]any{
					"type":        "string",
					"description": "按窗口标题子串过滤，大小写不敏感；为空时返回全部窗口。",
				},
			},
		},
		Handler: handleWindowsWindowList,
	})

	_ = reg.Register(Capability{
		Name: "windows.window.focus",
		Description: "激活（聚焦）指定窗口。通过 window_id 或 title 定位窗口，" +
			"先 ShowWindow(SW_RESTORE) 还原（若已最小化），再 SetForegroundWindow 置前。" +
			"注意：Windows 对前台窗口切换有限制，若目标进程不在前台且系统拒绝置前，" +
			"返回结果中的 focused 字段会如实反映实际是否成功。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"window_id": map[string]any{
					"type":        "string",
					"description": "窗口 ID，如 0x00010A2C 或十进制；与 title 至少提供一个。",
				},
				"title": map[string]any{
					"type":        "string",
					"description": "窗口标题（子串匹配，大小写不敏感），当未提供 window_id 时使用。",
				},
			},
		},
		Handler: handleWindowsWindowFocus,
	})

	_ = reg.Register(Capability{
		Name: "windows.window.close",
		Description: "关闭指定窗口。通过 PostMessage 发送 WM_CLOSE 消息，" +
			"等价于用户点击窗口关闭按钮，由目标程序自行决定是否退出" +
			"（不会强制结束进程）。与 Linux 侧 wmctrl -c 语义一致。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"window_id": map[string]any{
					"type":        "string",
					"description": "窗口 ID，如 0x00010A2C 或十进制。",
				},
			},
			"required": []string{"window_id"},
		},
		Handler: handleWindowsWindowClose,
	})
}

// handleWindowsWindowList 是 windows.window.list 的实现。
func handleWindowsWindowList(params map[string]any) (any, error) {
	filter, err := optionalString(params, "filter")
	if err != nil {
		return nil, err
	}

	windows := enumerateWindows()

	if filter != "" {
		needle := strings.ToLower(filter)
		filtered := make([]windowsWindowInfo, 0, len(windows))
		for _, w := range windows {
			if strings.Contains(strings.ToLower(w.Title), needle) {
				filtered = append(filtered, w)
			}
		}
		windows = filtered
	}

	return map[string]any{
		"windows": windows,
		"count":   len(windows),
		"tool":    windowsGUITool,
	}, nil
}

// handleWindowsWindowFocus 是 windows.window.focus 的实现。
func handleWindowsWindowFocus(params map[string]any) (any, error) {
	windowID, err := optionalString(params, "window_id")
	if err != nil {
		return nil, err
	}
	title, err := optionalString(params, "title")
	if err != nil {
		return nil, err
	}
	if windowID == "" && title == "" {
		return nil, fmt.Errorf("参数 window_id 与 title 至少需要提供一个")
	}

	var hwnd uintptr
	var resolvedTitle string

	if windowID != "" {
		hwnd, err = parseWindowID(windowID)
		if err != nil {
			return nil, err
		}
		if r, _, _ := procIsWindow.Call(hwnd); r == 0 {
			return nil, fmt.Errorf("窗口 %s 不存在或已关闭", windowID)
		}
		resolvedTitle = getWindowText(hwnd)
	} else {
		info, ok := findWindowByTitle(title)
		if !ok {
			return nil, fmt.Errorf("未找到标题匹配 %q 的窗口", title)
		}
		hwnd, err = parseWindowID(info.WindowID)
		if err != nil {
			return nil, err
		}
		resolvedTitle = info.Title
	}

	// SW_RESTORE：若窗口已最小化则还原；对正常窗口无副作用。
	procShowWindow.Call(hwnd, swRestore)

	// SetForegroundWindow 受 Windows 前台锁定策略限制，可能失败。
	// 这里不把失败当错误，而是如实返回 focused 状态。
	r, _, _ := procSetForegroundWindow.Call(hwnd)
	focused := r != 0

	return map[string]any{
		"window_id": formatWindowID(hwnd),
		"title":     resolvedTitle,
		"focused":   focused,
		"tool":      windowsGUITool,
	}, nil
}

// handleWindowsWindowClose 是 windows.window.close 的实现。
func handleWindowsWindowClose(params map[string]any) (any, error) {
	windowID, err := requiredString(params, "window_id")
	if err != nil {
		return nil, err
	}

	hwnd, err := parseWindowID(windowID)
	if err != nil {
		return nil, err
	}
	if r, _, _ := procIsWindow.Call(hwnd); r == 0 {
		return nil, fmt.Errorf("窗口 %s 不存在或已关闭", windowID)
	}

	title := getWindowText(hwnd)

	// PostMessage 异步投递 WM_CLOSE，不阻塞等待窗口处理完毕。
	r, _, err := procPostMessageW.Call(hwnd, wmClose, 0, 0)
	if r == 0 {
		if err != nil && err != syscall.Errno(0) {
			return nil, fmt.Errorf("向窗口 %s 发送 WM_CLOSE 失败: %v", windowID, err)
		}
		return nil, fmt.Errorf("向窗口 %s 发送 WM_CLOSE 失败", windowID)
	}

	return map[string]any{
		"window_id": formatWindowID(hwnd),
		"title":     title,
		"closed":    true,
		"tool":      windowsGUITool,
	}, nil
}

// parseWindowID 把字符串形式的窗口 ID 解析为 HWND。
//
// 纯解析逻辑在 windows_gui_parse.go 的 parseWindowIDString 中实现（无构建标签，
// 可在 Linux 上单测），本函数只做一层到 uintptr 的薄封装。
func parseWindowID(s string) (uintptr, error) {
	v, err := parseWindowIDString(s)
	if err != nil {
		return 0, err
	}
	return uintptr(v), nil
}
