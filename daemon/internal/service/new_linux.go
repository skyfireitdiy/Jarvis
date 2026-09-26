//go:build linux

package service

// newPlatformService 返回 Linux 下的 systemd 用户服务实现。
func newPlatformService() Service {
	return &systemdService{}
}
