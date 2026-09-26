//go:build windows

package capability

// registerPlatformCapabilities 注册 Windows 平台专有能力。
//
// 本轮只实现框架，不注册任何实际能力；后续在此处注册 Windows 能力。
func registerPlatformCapabilities(reg *Registry) {
	_ = reg
}
