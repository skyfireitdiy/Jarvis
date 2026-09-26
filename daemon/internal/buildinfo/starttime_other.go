//go:build !linux && !windows

package buildinfo

import "time"

// processStartTime 在非 Linux/Windows 平台（如 darwin）暂不支持，
// 返回 ok=false，调用方会降级为 BuildTimeSource="unknown"。
//
// 之所以不实现：darwin 需要 sysctl KERN_PROC_PID 等平台专有调用，
// 而当前守护进程的生产平台是 Windows（用户机器 SF-PC）与 Linux（网关本机），
// darwin 仅需保证可编译。后续如需支持可在此补上。
func processStartTime() (time.Time, bool) {
	return time.Time{}, false
}
