//go:build windows

package service

import "syscall"

// Windows 进程创建标志（避免引入 golang.org/x/sys 依赖）。
const (
	// detachedProcess 让子进程不继承当前控制台。
	detachedProcess = 0x00000008
	// createNewProcessGroup 让子进程拥有独立的进程组。
	createNewProcessGroup = 0x00000200
)

// detachedProcAttr 返回让子进程脱离当前控制台的启动属性。
func detachedProcAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{
		CreationFlags: detachedProcess | createNewProcessGroup,
	}
}
