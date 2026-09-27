//go:build windows

package capability

// 本文件实现「打开本机浏览器扩展页面」的 Windows 实现。
//
// 用途：daemon 自动同步浏览器扩展文件（覆盖 ~/.jarvis/browser_extension）之后，
// 需要让用户到浏览器的扩展页点一次「刷新」（已安装）或「加载已解压的扩展程序」
// （未安装）才能生效。此前只能靠用户手动聚焦窗口 → Ctrl+L → 输入 URL → 回车，
// 本函数把这一步自动化。
//
// 浏览器选择策略（用户已确认）：
//   - 本机正在运行 Edge / Chrome：都打开各自的扩展页（扩展可能装在任一个里）；
//   - 都没运行但已安装：用已安装的浏览器启动并打开扩展页；
//   - 都没安装：返回空列表，由调用方决定是否记日志，不视为错误。
//
// 实现要点（全部走 user32.dll syscall，复用 windows_gui_windows.go 与
// windows_input_windows.go 里已有的窗口枚举/聚焦与按键模拟，零第三方依赖、零 cgo）：
//   - 用 tasklist（复用 runWindowsProcessCommand）判断浏览器是否在运行。注意
//     msedgewebview2.exe 是 WebView2 运行时而非浏览器本体，必须排除，否则会在
//     用户并未打开 Edge 时误判为「运行中」；
//   - 用 EnumWindows（复用 enumerateWindows）枚举顶层窗口，按「窗口所属进程名」
//     与「标题后缀」定位目标窗口；
//   - 用 keybd_event / SendInput（复用 focusWindow、sendKeyCombo、sendUnicodeText）
//     模拟 Ctrl+L → URL → 回车。
//
// 为什么不能把 URL 当命令行参数传给浏览器 exe：edge:// 与 chrome:// 是浏览器内部
// scheme，Edge/Chrome 出于安全考虑拒绝从命令行直接打开这类地址，实测会静默退回
// 「新选项卡」，扩展页根本打不开（普通 https URL 则正常）。
//
// 为什么不能直接对「现有浏览器窗口」做按键模拟：用户可能正在使用 PWA（已安装的
// Web 应用）窗口，PWA 窗口没有地址栏，Ctrl+L 会被网页自身截获，URL 会被输进页面
// 的输入框里（实测）。因此必须先定位到一个「普通浏览器窗口」（标题以浏览器名
// 结尾，如 "… - Microsoft Edge"），没有则用 --new-window 新开一个。
//
// 为什么不用 PowerShell 的 SendKeys：实测 SendKeys 在此上下文（由守护进程
// 非交互式启动的 PowerShell 子进程）里对目标窗口无效，而 keybd_event/SendInput
// 有效。故改为纯 Go 实现，同时省掉一次 PowerShell 进程开销。

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

// browserWindowWaitTicks 是等待浏览器窗口出现的轮询次数，每次间隔 500ms。
// 冷启动浏览器通常 1~3 秒内出现主窗口，20 次（10 秒）足够覆盖慢速场景。
const browserWindowWaitTicks = 20

// browserWindowPollInterval 是轮询窗口出现的间隔。
const browserWindowPollInterval = 500 * time.Millisecond

// browserFocusSettleDelay 是聚焦窗口后、发送按键前的等待时间，
// 让窗口完成前台切换与地址栏就绪。
const browserFocusSettleDelay = 800 * time.Millisecond

// browserKeyDelay 是按键之间的等待时间，避免过快导致浏览器来不及处理。
const browserKeyDelay = 500 * time.Millisecond

// browserNavigateSettleDelay 是回车后等待页面加载的时间（仅用于读取标题排错）。
const browserNavigateSettleDelay = 2 * time.Second

// browserTarget 描述一个可打开的浏览器及其扩展页地址。
type browserTarget struct {
	// name 是用于日志与返回值的人类可读名称，如 "Edge"。
	name string
	// processName 是 tasklist 中的进程名（小写），用于判断是否在运行。
	processName string
	// extensionsURL 是该浏览器的扩展页地址。
	extensionsURL string
	// windowTitleSuffix 是「普通浏览器窗口」标题的结尾标识。
	//
	// 普通窗口标题形如 "扩展 - 个人 - Microsoft Edge"（以 "Edge" 结尾），
	// 而 PWA 窗口标题是应用名（如 "Jarvis Web Gateway - Jarvis AI 助手"），
	// 不会以浏览器名结尾，故可用它把 PWA 窗口排除在外。
	windowTitleSuffix string
	// installPaths 是候选安装路径，按优先级排列；用于「未运行时启动」。
	installPaths []string
}

// browserTargets 是支持自动打开扩展页的浏览器清单。
//
// 顺序即优先级：仅用于「都没运行时」的启动选择（按顺序取第一个已安装的）。
var browserTargets = []browserTarget{
	{
		name:              "Edge",
		processName:       "msedge.exe",
		extensionsURL:     "edge://extensions",
		windowTitleSuffix: "Edge",
		installPaths: []string{
			`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`,
			`C:\Program Files\Microsoft\Edge\Application\msedge.exe`,
		},
	},
	{
		name:              "Chrome",
		processName:       "chrome.exe",
		extensionsURL:     "chrome://extensions",
		windowTitleSuffix: "Chrome",
		installPaths: []string{
			`C:\Program Files\Google\Chrome\Application\chrome.exe`,
			`C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`,
		},
	},
}

// OpenBrowserExtensionsPage 打开本机浏览器的扩展页面，返回已打开的浏览器名称列表。
//
// 选择逻辑见文件头注释。返回值用于日志与测试断言；调用方不应把「返回空列表」
// 当作错误（可能只是本机没装任何受支持的浏览器）。
func OpenBrowserExtensionsPage() ([]string, error) {
	running, err := runningBrowserProcessNames()
	if err != nil {
		// 进程枚举失败不致命：退化为「按安装情况启动」，仍尽量把扩展页打开。
		running = map[string]bool{}
	}

	var opened []string
	var lastErr error

	// 第一轮：为所有「正在运行」的浏览器打开扩展页（都开，用户已确认）。
	// 浏览器已在运行，无需冷启动；若它只有 PWA 窗口，会自行 --new-window。
	for _, t := range browserTargets {
		if !running[t.processName] {
			continue
		}
		if err := openExtensionsPage(t, ""); err != nil {
			lastErr = err
			continue
		}
		opened = append(opened, t.name)
	}
	if len(opened) > 0 {
		return opened, nil
	}

	// 第二轮：都没运行，用第一个「已安装」的浏览器冷启动并打开扩展页。
	for _, t := range browserTargets {
		exe, ok := firstExistingPath(t.installPaths)
		if !ok {
			continue
		}
		if err := openExtensionsPage(t, exe); err != nil {
			lastErr = err
			continue
		}
		opened = append(opened, t.name)
		// 只启动一个：本机没开浏览器时，开太多窗口反而打扰用户。
		break
	}
	if len(opened) > 0 {
		return opened, nil
	}

	if lastErr != nil {
		return nil, lastErr
	}
	// 本机未安装任何受支持的浏览器：不是错误，由调用方决定是否记日志。
	return nil, nil
}

// openExtensionsPage 打开指定浏览器的扩展页。
//
// exePath 非空表示浏览器未运行（或已运行但需要新开普通窗口），用于 --new-window；
// 为空时从已安装路径或运行中的进程里解析。
func openExtensionsPage(t browserTarget, exePath string) error {
	hwnd, err := ensureBrowserContentWindow(t, exePath)
	if err != nil {
		return fmt.Errorf("打开 %s 扩展页失败: %w", t.name, err)
	}

	// 聚焦窗口（复用 windows.window.focus 的同一实现）。
	if !focusWindow(hwnd) {
		return fmt.Errorf("聚焦 %s 窗口失败", t.name)
	}
	time.Sleep(browserFocusSettleDelay)

	// Ctrl+L 聚焦地址栏 → 输入扩展页 URL → 回车。
	if err := sendKeyCombo("ctrl+l"); err != nil {
		return fmt.Errorf("发送 Ctrl+L 失败: %w", err)
	}
	time.Sleep(browserKeyDelay)
	sendUnicodeText(t.extensionsURL)
	time.Sleep(browserKeyDelay)
	if err := sendKeyCombo("Return"); err != nil {
		return fmt.Errorf("发送回车失败: %w", err)
	}

	// 等页面加载完再读标题，仅用于日志/排错。
	time.Sleep(browserNavigateSettleDelay)
	_ = getWindowText(hwnd)
	return nil
}

// ensureBrowserContentWindow 返回一个「普通浏览器窗口」的句柄。
//
// 优先复用已存在的普通窗口（标题以 windowTitleSuffix 结尾，且属于该浏览器进程）；
// 没有（例如用户只开着 PWA 窗口）则用 --new-window 新开一个并等待它出现。
func ensureBrowserContentWindow(t browserTarget, exePath string) (uintptr, error) {
	browserPIDs := browserProcessIDs(t.processName)

	if hwnd, ok := findContentWindow(t, browserPIDs); ok {
		return hwnd, nil
	}

	// 需要新开普通窗口：先解析可执行文件路径。
	exe := exePath
	if exe == "" {
		exe = runningProcessPath(t.processName)
	}
	if exe == "" {
		if p, ok := firstExistingPath(t.installPaths); ok {
			exe = p
		}
	}
	if exe == "" {
		return 0, fmt.Errorf("未找到 %s 可执行文件", t.name)
	}

	before := windowIDsOfPIDs(browserPIDs)
	cmd := exec.Command(exe, "--new-window")
	cmd.SysProcAttr = hideWindow()
	if err := cmd.Start(); err != nil {
		return 0, fmt.Errorf("启动 %s 失败: %w", t.name, err)
	}
	// 不等待进程退出（浏览器会把命令转发给已有实例后立即返回）。
	go func() { _ = cmd.Wait() }()

	for i := 0; i < browserWindowWaitTicks; i++ {
		time.Sleep(browserWindowPollInterval)
		// 进程集合可能变化（新窗口由已有实例创建），重新取一次。
		pids := browserProcessIDs(t.processName)
		if hwnd, ok := findNewContentWindow(t, pids, before); ok {
			return hwnd, nil
		}
	}
	return 0, fmt.Errorf("等待 %s 普通窗口超时", t.name)
}

// findContentWindow 在给定进程集合的窗口中查找第一个「普通浏览器窗口」。
func findContentWindow(t browserTarget, pids map[uint32]bool) (uintptr, bool) {
	for _, w := range enumerateWindows() {
		if !pids[w.PID] {
			continue
		}
		if isContentWindowTitle(t, w.Title) {
			if hwnd, err := parseWindowID(w.WindowID); err == nil {
				return hwnd, true
			}
		}
	}
	return 0, false
}

// findNewContentWindow 查找「不在 before 中」且为普通浏览器窗口的新窗口。
func findNewContentWindow(t browserTarget, pids map[uint32]bool, before map[uintptr]bool) (uintptr, bool) {
	for _, w := range enumerateWindows() {
		if !pids[w.PID] {
			continue
		}
		if !isContentWindowTitle(t, w.Title) {
			continue
		}
		hwnd, err := parseWindowID(w.WindowID)
		if err != nil {
			continue
		}
		if before[hwnd] {
			continue
		}
		return hwnd, true
	}
	return 0, false
}

// isContentWindowTitle 判断窗口标题是否属于「普通浏览器窗口」。
//
// 普通窗口标题以浏览器名结尾（如 "… - Microsoft Edge"）；PWA 窗口标题是应用名，
// 不会命中。用后缀匹配而非完整匹配：Edge 的窗口标题里 "Microsoft Edge" 中间
// 夹着一个零宽空格（U+200B，防伪标记），完整字符串匹配会失败。
func isContentWindowTitle(t browserTarget, title string) bool {
	return strings.HasSuffix(title, t.windowTitleSuffix)
}

// windowIDsOfPIDs 返回给定进程集合当前所有可见窗口的句柄集合。
func windowIDsOfPIDs(pids map[uint32]bool) map[uintptr]bool {
	result := map[uintptr]bool{}
	for _, w := range enumerateWindows() {
		if !pids[w.PID] {
			continue
		}
		if hwnd, err := parseWindowID(w.WindowID); err == nil {
			result[hwnd] = true
		}
	}
	return result
}

// browserProcessIDs 返回指定浏览器进程名（如 "msedge.exe"）对应的 PID 集合。
//
// 数据来自 tasklist（与 runningBrowserProcessNames 同一来源）。
func browserProcessIDs(processName string) map[uint32]bool {
	result := map[uint32]bool{}
	out, err := runWindowsProcessCommand("tasklist", "/FO", "CSV", "/NH")
	if err != nil {
		return result
	}
	want := strings.ToLower(strings.TrimSpace(processName))
	for _, p := range parseWindowsTasklistCSV(out) {
		name := strings.ToLower(strings.TrimSpace(fmt.Sprint(p["name"])))
		if name != want {
			continue
		}
		pid, ok := p["pid"].(int)
		if !ok {
			continue
		}
		result[uint32(pid)] = true
	}
	return result
}

// runningProcessPath 返回正在运行的指定进程的可执行文件路径；取不到时返回空串。
//
// 用 PowerShell 的 Get-Process 取 Path：Go 标准库没有跨进程取路径的接口，
// 而 daemon 以管理员权限运行，能读到其它进程的 Path。
func runningProcessPath(processName string) string {
	// 去掉 .exe 后缀：Get-Process 的 -Name 用不带后缀的名字。
	name := strings.TrimSuffix(processName, ".exe")
	script := "$p=Get-Process -Name " + encodePowerShellText(name) +
		" -ErrorAction SilentlyContinue | Select-Object -First 1; if($p){ Write-Output $p.Path }"
	out, err := runWindowsPowerShellCommand(script, 15*time.Second)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(out)
}

// runningBrowserProcessNames 返回正在运行的浏览器进程名集合（小写）。
//
// 数据来自 tasklist（与 windows.process.list 同一来源）。注意排除
// msedgewebview2.exe：它是 WebView2 运行时，大量桌面程序（含本项目的部分依赖）
// 会加载它，但它不代表用户打开了 Edge。
func runningBrowserProcessNames() (map[string]bool, error) {
	out, err := runWindowsProcessCommand("tasklist", "/FO", "CSV", "/NH")
	if err != nil {
		return nil, err
	}

	result := map[string]bool{}
	for _, p := range parseWindowsTasklistCSV(out) {
		name := strings.ToLower(strings.TrimSpace(fmt.Sprint(p["name"])))
		if name == "" {
			continue
		}
		// 排除 WebView2 运行时，避免误判 Edge 正在运行。
		if name == "msedgewebview2.exe" {
			continue
		}
		result[name] = true
	}
	return result, nil
}

// firstExistingPath 返回候选路径中第一个存在的文件；都不存在时返回 ("", false)。
func firstExistingPath(paths []string) (string, bool) {
	for _, p := range paths {
		if info, err := os.Stat(p); err == nil && !info.IsDir() {
			return p, true
		}
	}
	return "", false
}

// sendKeyCombo 发送一个按键组合（如 "ctrl+l"、"Return"）。
//
// 复用 windows.input.keys 的解析与发送逻辑（parseWindowsKeyCombo + virtualKeyCode
// + keybd_event），保证行为一致。
func sendKeyCombo(keys string) error {
	modifiers, keyName, err := parseWindowsKeyCombo(keys)
	if err != nil {
		return err
	}
	keyVK, ok := virtualKeyCode(keyName)
	if !ok {
		return fmt.Errorf("不支持的按键名 %q", keyName)
	}
	modifierVKs := make([]uint16, 0, len(modifiers))
	for _, m := range modifiers {
		vk, ok := virtualKeyCode(m)
		if !ok {
			return fmt.Errorf("不支持的修饰键 %q", m)
		}
		modifierVKs = append(modifierVKs, vk)
	}

	for _, vk := range modifierVKs {
		procKeybdEvent.Call(uintptr(vk), 0, 0, 0)
	}
	procKeybdEvent.Call(uintptr(keyVK), 0, 0, 0)
	procKeybdEvent.Call(uintptr(keyVK), 0, uintptr(keyeventfKeyUp), 0)
	for i := len(modifierVKs) - 1; i >= 0; i-- {
		procKeybdEvent.Call(uintptr(modifierVKs[i]), 0, uintptr(keyeventfKeyUp), 0)
	}
	return nil
}

// sendUnicodeText 逐字符发送文本（含非 ASCII）。
//
// 复用 windows.input.type 的 SendInput + KEYEVENTF_UNICODE 实现。
func sendUnicodeText(text string) {
	const keyeventfUnicode = 0x0004
	for _, r := range text {
		if r > 0xFFFF {
			hi, lo := utf16SurrogatePair(r)
			sendUnicodeChar(hi, keyeventfUnicode)
			sendUnicodeChar(lo, keyeventfUnicode)
		} else {
			sendUnicodeChar(uint16(r), keyeventfUnicode)
		}
	}
}
