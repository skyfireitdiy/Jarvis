//go:build !windows

package service

import "syscall"

// detachedProcAttr 在非 Windows 平台无额外要求。
func detachedProcAttr() *syscall.SysProcAttr {
	return nil
}
