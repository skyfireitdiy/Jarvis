//go:build !linux && !windows

package capability

// registerPlatformCapabilities 注册其他平台（如 darwin）专有能力。
//
// 本轮只实现框架，不注册任何实际能力；后续在此处注册对应平台能力。
func registerPlatformCapabilities(reg *Registry) {
	_ = reg
}
