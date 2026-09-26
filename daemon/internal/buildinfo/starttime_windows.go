//go:build windows

package buildinfo

import (
	"syscall"
	"time"
)

// processStartTime 通过 GetProcessTimes 获取当前进程的创建时间。
//
// 仅用标准库 syscall（kernel32!GetProcessTimes），不引入 golang.org/x/sys。
// 获取失败时返回 ok=false。
func processStartTime() (time.Time, bool) {
	handle, err := syscall.GetCurrentProcess()
	if err != nil {
		return time.Time{}, false
	}

	var creation, exit, kernel, user syscall.Filetime
	err = syscall.GetProcessTimes(handle, &creation, &exit, &kernel, &user)
	if err != nil {
		return time.Time{}, false
	}

	// FILETIME 是 100 纳秒为单位、自 1601-01-01 UTC 起算的无符号 64 位计数。
	// 换算逻辑抽到 filetime.go 的 filetimeToTime（无构建标签，Linux 可单测），
	// 那里详细说明了为何不能用 creation.Nanoseconds()（会 int64 溢出）。
	ticks := int64(creation.HighDateTime)<<32 | int64(creation.LowDateTime)
	return filetimeToTime(ticks), true
}
