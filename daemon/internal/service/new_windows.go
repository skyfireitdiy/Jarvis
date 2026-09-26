//go:build windows

package service

// newPlatformService 返回 Windows 下的计划任务实现。
func newPlatformService() Service {
	return &taskService{}
}
