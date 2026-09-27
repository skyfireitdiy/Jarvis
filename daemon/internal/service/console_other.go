//go:build !windows

package service

// HideSelfConsole 在非 Windows 平台为空操作。
//
// 仅 Windows 上由计划任务以交互方式启动控制台程序时会分配可见控制台窗口，
// Linux / macOS 无此问题。
func HideSelfConsole() {}
