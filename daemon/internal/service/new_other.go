//go:build !linux && !windows

package service

// newPlatformService 在非 Linux / 非 Windows 平台返回 nil，由 New 兜底为 unsupportedService。
func newPlatformService() Service {
	return nil
}
