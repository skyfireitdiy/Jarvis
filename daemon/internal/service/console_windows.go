//go:build windows

package service

import "syscall"

// 隐藏自身控制台窗口所需的 Win32 入口。
//
// 用 syscall.NewLazyDLL 动态加载，避免引入 golang.org/x/sys 依赖。
var (
	kernel32Console         = syscall.NewLazyDLL("kernel32.dll")
	procGetConsoleWindow    = kernel32Console.NewProc("GetConsoleWindow")
	user32Console           = syscall.NewLazyDLL("user32.dll")
	procShowWindowForDaemon = user32Console.NewProc("ShowWindow")
)

// swHide 对应 ShowWindow 的 SW_HIDE：隐藏窗口。
const swHide = 0

// HideSelfConsole 隐藏当前进程的控制台窗口（若存在）。
//
// 背景：jarvis-daemon 是控制台子系统程序（PE Subsystem=CONSOLE）。当它由计划任务
// 以交互方式启动时，Windows 会为它分配一个**可见的控制台窗口**，用户桌面上会常驻
// 一个黑框。本函数在 runDaemon 启动时调用，把该窗口隐藏。
//
// 只隐藏窗口，不调用 FreeConsole：进程仍持有控制台，标准输出/错误依然有效，
// 因此前台运行并重定向日志（jarvis-daemon run > log.txt）不受影响。
//
// 无控制台（如以 DETACHED_PROCESS 启动）时 GetConsoleWindow 返回 0，直接返回。
func HideSelfConsole() {
	hwnd, _, _ := procGetConsoleWindow.Call()
	if hwnd == 0 {
		return
	}
	procShowWindowForDaemon.Call(hwnd, uintptr(swHide))
}
