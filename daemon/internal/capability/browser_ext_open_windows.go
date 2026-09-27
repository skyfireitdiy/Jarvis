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
// 实现要点：
//   - 用 tasklist（复用 runWindowsProcessCommand）判断浏览器是否在运行。注意
//     msedgewebview2.exe 是 WebView2 运行时而非浏览器本体，必须排除，否则会在
//     用户并未打开 Edge 时误判为「运行中」；
//   - 用 PowerShell 的 Start-Process 打开 URL，复用 runWindowsPowerShellCommand
//     （-EncodedCommand 传参、UTF-8 输出、CREATE_NO_WINDOW 不闪黑框、带超时）；
//   - 本场景的 URL 是固定字面量，不含任何用户输入，无注入风险。

import (
	"fmt"
	"os"
	"strings"
	"time"
)

// browserOpenTimeout 是执行「打开扩展页」PowerShell 脚本的超时时间。
//
// Start-Process 本身立即返回（不等待目标进程退出），正常在数百毫秒内完成；
// 给 20 秒余量以覆盖浏览器冷启动较慢的极端情况。
const browserOpenTimeout = 20 * time.Second

// browserTarget 描述一个可打开的浏览器及其扩展页地址。
type browserTarget struct {
	// name 是用于日志与返回值的人类可读名称，如 "Edge"。
	name string
	// processName 是 tasklist 中的进程名（小写），用于判断是否在运行。
	processName string
	// extensionsURL 是该浏览器的扩展页地址。
	extensionsURL string
	// installPaths 是候选安装路径，按优先级排列；用于「未运行时启动」。
	installPaths []string
}

// browserTargets 是支持自动打开扩展页的浏览器清单。
//
// 顺序即优先级：仅用于「都没运行时」的启动选择（按顺序取第一个已安装的）。
var browserTargets = []browserTarget{
	{
		name:          "Edge",
		processName:   "msedge.exe",
		extensionsURL: "edge://extensions",
		installPaths: []string{
			`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`,
			`C:\Program Files\Microsoft\Edge\Application\msedge.exe`,
		},
	},
	{
		name:          "Chrome",
		processName:   "chrome.exe",
		extensionsURL: "chrome://extensions",
		installPaths: []string{
			`C:\Program Files\Google\Chrome\Application\chrome.exe`,
			`C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`,
		},
	},
}

// openBrowserExtensionsPage 打开本机浏览器的扩展页面，返回已打开的浏览器名称列表。
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
	for _, t := range browserTargets {
		if !running[t.processName] {
			continue
		}
		if err := startBrowserURL(t, ""); err != nil {
			lastErr = err
			continue
		}
		opened = append(opened, t.name)
	}
	if len(opened) > 0 {
		return opened, nil
	}

	// 第二轮：都没运行，用第一个「已安装」的浏览器启动并打开扩展页。
	for _, t := range browserTargets {
		exe, ok := firstExistingPath(t.installPaths)
		if !ok {
			continue
		}
		if err := startBrowserURL(t, exe); err != nil {
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

// startBrowserURL 打开指定浏览器的扩展页。
//
// exePath 为空时用 URL 直接触发（Windows 会交给默认/已运行的浏览器处理，
// 对已运行的浏览器表现为新开一个标签页）；非空时显式用该 exe 启动，用于
// 「浏览器未运行」的场景（避免依赖文件关联，也避免启动到别的浏览器）。
func startBrowserURL(t browserTarget, exePath string) error {
	var script string
	if exePath == "" {
		// 已运行的浏览器：直接用 Start-Process 打开 URL。
		// URL 为固定字面量，经单引号字面量转义后拼入脚本，无注入风险。
		script = fmt.Sprintf("Start-Process %s", encodePowerShellText(t.extensionsURL))
	} else {
		// 未运行：显式用安装路径启动，并把扩展页作为首个参数。
		script = fmt.Sprintf("Start-Process -FilePath %s -ArgumentList %s",
			encodePowerShellText(exePath), encodePowerShellText(t.extensionsURL))
	}
	if _, err := runWindowsPowerShellCommand(script, browserOpenTimeout); err != nil {
		return fmt.Errorf("打开 %s 扩展页失败: %w", t.name, err)
	}
	return nil
}
