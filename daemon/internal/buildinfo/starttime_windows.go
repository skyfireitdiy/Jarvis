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

	// Filetime 是 100 纳秒为单位、自 1601-01-01 UTC 起算的计数。
	// 转成 Unix 纳秒：减去 1601→1970 的偏移（11644473600 秒）。
	const windowsToUnixEpoch = 11644473600
	nanos := creation.Nanoseconds()
	sec := nanos/1e9 - windowsToUnixEpoch
	nsec := nanos % 1e9
	return time.Unix(sec, nsec), true
}
