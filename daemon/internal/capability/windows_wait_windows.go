//go:build windows

package capability

import (
	"fmt"
	"strings"
	"time"
)

// 本文件实现 Windows 等待原语（windows.window.wait / windows.process.wait）。
// 纯逻辑（参数解析、状态判断、轮询循环）在 windows_wait_parse.go（无构建标签，可 Linux 单测）。
// 平台相关部分（窗口存在/前台判断、进程存在判断）在此文件，通过 syscall 与 tasklist 实现。

// windowsProcessWaitTool 是 windows.process.wait 结果中 tool 字段的值。
const windowsProcessWaitTool = "tasklist"

// registerWindowsWait 注册 Windows 等待原语能力。
func registerWindowsWait(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.window.wait",
		Description: "轮询等待窗口进入指定状态，直到满足或超时。" +
			"通过 window_id 或 title 定位窗口；state 支持 visible（窗口出现）、" +
			"active（窗口成为前台）、gone（窗口消失）。" +
			"适合脚本化自动化中等待窗口出现后再操作。",
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
				"state": map[string]any{
					"type":        "string",
					"description": "等待的目标状态：visible（窗口出现，默认）/ active（窗口成为前台）/ gone（窗口消失）。",
				},
				"timeout_ms": map[string]any{
					"type":        "integer",
					"description": "超时毫秒数，默认 10000；超过仍未满足则返回错误。",
				},
				"interval_ms": map[string]any{
					"type":        "integer",
					"description": "轮询间隔毫秒数，默认 200。",
				},
			},
		},
		Handler: handleWindowsWindowWait,
	})

	_ = reg.Register(Capability{
		Name: "windows.process.wait",
		Description: "轮询等待指定 PID 的进程退出，直到进程消失或超时。" +
			"适合脚本化自动化中启动进程后等待其结束。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"pid": map[string]any{
					"type":        "integer",
					"description": "目标进程 PID，必须为正整数。",
				},
				"timeout_ms": map[string]any{
					"type":        "integer",
					"description": "超时毫秒数，默认 10000；超过仍未退出则返回错误。",
				},
				"interval_ms": map[string]any{
					"type":        "integer",
					"description": "轮询间隔毫秒数，默认 200。",
				},
			},
			"required": []string{"pid"},
		},
		Handler: handleWindowsProcessWait,
	})
}

// handleWindowsWindowWait 是 windows.window.wait 的实现。
func handleWindowsWindowWait(params map[string]any) (any, error) {
	windowID, title, state, timeout, interval, err := parseWindowWaitParams(params)
	if err != nil {
		return nil, err
	}

	// window_id 优先：解析出固定句柄，用 IsWindow 判断存在性。
	var hwnd uintptr
	haveHwnd := false
	if windowID != "" {
		hwnd, err = parseWindowID(windowID)
		if err != nil {
			return nil, err
		}
		haveHwnd = true
	}

	// present 判断：window_id 用 IsWindow，title 用 findWindowByTitle。
	present := func() bool {
		if haveHwnd {
			return windowExists(hwnd)
		}
		_, ok := findWindowByTitle(title)
		return ok
	}
	// foreground 判断：窗口存在且为前台窗口。
	foreground := func() bool {
		if haveHwnd {
			return windowIsForeground(hwnd)
		}
		info, ok := findWindowByTitle(title)
		if !ok {
			return false
		}
		h, err := parseWindowID(info.WindowID)
		if err != nil {
			return false
		}
		return windowIsForeground(h)
	}

	start := time.Now()
	met, err := waitLoop(timeout, interval, func() (bool, error) {
		return windowWaitConditionMet(state, present(), foreground())
	})
	if err != nil {
		return nil, err
	}
	elapsed := time.Since(start)

	if !met {
		return nil, fmt.Errorf("等待窗口状态 %s 超时（%s 内未满足）", state, timeout)
	}

	// 汇总最终窗口信息。
	var resolvedID, resolvedTitle string
	if haveHwnd {
		resolvedID = formatWindowID(hwnd)
		resolvedTitle = getWindowText(hwnd)
	} else if info, ok := findWindowByTitle(title); ok {
		resolvedID = info.WindowID
		resolvedTitle = info.Title
	}

	return map[string]any{
		"window_id": resolvedID,
		"title":     resolvedTitle,
		"state":     state,
		"met":       true,
		"waited_ms": int(elapsed.Milliseconds()),
		"tool":      windowsGUITool,
	}, nil
}

// handleWindowsProcessWait 是 windows.process.wait 的实现。
func handleWindowsProcessWait(params map[string]any) (any, error) {
	pid, timeout, interval, err := parseProcessWaitParams(params)
	if err != nil {
		return nil, err
	}

	start := time.Now()
	met, err := waitLoop(timeout, interval, func() (bool, error) {
		// 等待进程消失：进程不存在即满足。
		return !processExists(pid), nil
	})
	if err != nil {
		return nil, err
	}
	elapsed := time.Since(start)

	if !met {
		return nil, fmt.Errorf("等待进程 %d 退出超时（%s 内仍在运行）", pid, timeout)
	}

	return map[string]any{
		"pid":       pid,
		"exited":    true,
		"waited_ms": int(elapsed.Milliseconds()),
		"tool":      windowsProcessWaitTool,
	}, nil
}

// windowExists 判断 hwnd 是否仍为有效窗口。
func windowExists(hwnd uintptr) bool {
	r, _, _ := procIsWindow.Call(hwnd)
	return r != 0
}

// windowIsForeground 判断 hwnd 是否为当前前台窗口。
func windowIsForeground(hwnd uintptr) bool {
	fg, _, _ := procGetForegroundWindow.Call()
	return fg == hwnd
}

// processExists 判断 pid 是否仍在运行（用 tasklist /FI "PID eq N"）。
func processExists(pid int) bool {
	out, err := runWindowsProcessCommand("tasklist", "/FO", "CSV", "/NH", "/FI", fmt.Sprintf("PID eq %d", pid))
	if err != nil {
		return false
	}
	return strings.TrimSpace(out) != ""
}
