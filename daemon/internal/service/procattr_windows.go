//go:build windows

package service

import "syscall"

// Windows 进程创建标志（避免引入 golang.org/x/sys 依赖）。
const (
	// detachedProcess 让子进程不继承当前控制台。
	detachedProcess = 0x00000008
	// createNewProcessGroup 让子进程拥有独立的进程组。
	createNewProcessGroup = 0x00000200
	// createNoWindow 让控制台程序不新建控制台窗口。
	//
	// 守护进程以分离进程运行（无控制台），此时启动 powershell / schtasks 等控制台
	// 程序若不带该标志，Windows 会为子进程新建控制台窗口（表现为闪黑框）。
	createNoWindow = 0x08000000
)

// hideWindowProcAttr 返回让子进程不弹控制台窗口的启动属性。
func hideWindowProcAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{CreationFlags: createNoWindow}
}

// detachedProcAttr 返回让子进程脱离当前控制台的启动属性。
//
// 同时带上 CREATE_NO_WINDOW：守护进程是控制台程序，若仅 DETACHED_PROCESS 而不带
// 该标志，Windows 会为分离出的 daemon 新建一个控制台窗口（用户会看到黑框闪现）。
func detachedProcAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{
		CreationFlags: detachedProcess | createNewProcessGroup | createNoWindow,
	}
}
