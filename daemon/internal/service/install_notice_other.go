//go:build !windows

package service

// InstallNotice 在非 Windows 平台无需额外提示（Linux 使用 systemd 用户服务，
// 不需要管理员权限），返回空串。
func InstallNotice() string {
	return ""
}

// StartHint 在非 Windows 平台返回空串（Linux 通过 systemctl 管理，无需完整路径）。
func StartHint() string {
	return ""
}
