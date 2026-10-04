package capability

import (
	"fmt"
	"time"
)

// 本文件实现 Windows 等待原语（windows.window.wait / windows.process.wait）的纯逻辑部分：
// 参数解析、状态判断与通用轮询循环。无构建标签，可在 Linux 上单测。
//
// 注意：本文件保持「零平台依赖」——不引用 optionalString/optionalInt（它们定义在
// 带 //go:build windows 的 windows_common_windows.go 与 //go:build linux 的
// linux_script_linux.go 中，darwin 平台两者皆无，引用会导致跨平台编译失败）。
// 故此处内联等价的 waitOptionalString / waitOptionalInt，语义与平台版本保持一致。

// waitOptionalString 读取可选字符串参数；缺失或为 nil 时返回空串。
// 与 windows_common_windows.go 的 optionalString 语义一致（零平台依赖内联版）。
func waitOptionalString(params map[string]any, key string) (string, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return "", nil
	}
	s, ok := v.(string)
	if !ok {
		return "", fmt.Errorf("参数 %s 必须是字符串，实际 %T", key, v)
	}
	return s, nil
}

// waitOptionalInt 读取可选整数参数；缺失或为 nil 时返回默认值。
// 兼容 JSON 解码后的 float64（网关传来的数字可能是 float64）。
// 与 windows_common_windows.go 的 optionalInt 语义一致（零平台依赖内联版）。
func waitOptionalInt(params map[string]any, key string, def int) (int, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return def, nil
	}
	switch n := v.(type) {
	case int:
		return n, nil
	case int64:
		return int(n), nil
	case float64:
		if n != float64(int(n)) {
			return 0, fmt.Errorf("参数 %s 必须是整数，实际 %v", key, n)
		}
		return int(n), nil
	default:
		return 0, fmt.Errorf("参数 %s 必须是整数，实际 %T", key, v)
	}
}

// windowsWaitDefaultTimeout 是等待未指定 timeout_ms 时的默认超时。
const windowsWaitDefaultTimeout = 10 * time.Second

// windowsWaitDefaultInterval 是轮询间隔。
const windowsWaitDefaultInterval = 200 * time.Millisecond

// windowsWaitValidStates 是 windows.window.wait 的 state 合法取值。
var windowsWaitValidStates = map[string]bool{
	"visible": true,
	"active":  true,
	"gone":    true,
}

// parseWindowWaitParams 解析 windows.window.wait 的公共参数。
func parseWindowWaitParams(params map[string]any) (windowID, title, state string, timeout, interval time.Duration, err error) {
	windowID, err = waitOptionalString(params, "window_id")
	if err != nil {
		return
	}
	title, err = waitOptionalString(params, "title")
	if err != nil {
		return
	}
	if windowID == "" && title == "" {
		err = fmt.Errorf("参数 window_id 与 title 至少需要提供一个")
		return
	}
	state, err = waitOptionalString(params, "state")
	if err != nil {
		return
	}
	if state == "" {
		state = "visible"
	}
	if !windowsWaitValidStates[state] {
		err = fmt.Errorf("参数 state 必须是 visible/active/gone 之一，实际 %q", state)
		return
	}
	timeout, interval, err = parseWaitTiming(params)
	return
}

// parseProcessWaitParams 解析 windows.process.wait 的公共参数。
func parseProcessWaitParams(params map[string]any) (pid int, timeout, interval time.Duration, err error) {
	pid, err = waitOptionalInt(params, "pid", 0)
	if err != nil {
		return
	}
	if pid <= 0 {
		err = fmt.Errorf("参数 pid 必须为正整数，实际 %d", pid)
		return
	}
	timeout, interval, err = parseWaitTiming(params)
	return
}

// parseWaitTiming 解析 timeout_ms 与 interval_ms 并转成 time.Duration。
func parseWaitTiming(params map[string]any) (timeout, interval time.Duration, err error) {
	timeoutMs, err := waitOptionalInt(params, "timeout_ms", int(windowsWaitDefaultTimeout/time.Millisecond))
	if err != nil {
		return
	}
	if timeoutMs <= 0 {
		err = fmt.Errorf("参数 timeout_ms 必须为正整数，实际 %d", timeoutMs)
		return
	}
	intervalMs, err := waitOptionalInt(params, "interval_ms", int(windowsWaitDefaultInterval/time.Millisecond))
	if err != nil {
		return
	}
	if intervalMs <= 0 {
		err = fmt.Errorf("参数 interval_ms 必须为正整数，实际 %d", intervalMs)
		return
	}
	timeout = time.Duration(timeoutMs) * time.Millisecond
	interval = time.Duration(intervalMs) * time.Millisecond
	return
}

// windowWaitConditionMet 判断窗口等待状态是否满足。
// present 表示窗口当前是否存在；foreground 表示窗口当前是否为前台窗口。
func windowWaitConditionMet(state string, present, foreground bool) (bool, error) {
	switch state {
	case "visible":
		return present, nil
	case "active":
		return present && foreground, nil
	case "gone":
		return !present, nil
	default:
		return false, fmt.Errorf("参数 state 必须是 visible/active/gone 之一，实际 %q", state)
	}
}

// waitLoop 以 interval 间隔轮询 check，直到其返回 true 或超时。
// 返回 (是否在超时前满足, 错误)。
func waitLoop(timeout, interval time.Duration, check func() (bool, error)) (bool, error) {
	deadline := time.Now().Add(timeout)
	for {
		ok, err := check()
		if err != nil {
			return false, err
		}
		if ok {
			return true, nil
		}
		if time.Now().After(deadline) {
			return false, nil
		}
		time.Sleep(interval)
	}
}
