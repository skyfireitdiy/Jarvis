//go:build linux

package capability

// registerLinuxBrowserExt 注册 Linux 平台的浏览器扩展下载/更新能力。
//
// 与 Windows 侧语义完全一致（同名能力、同参数、同返回结构），差异仅在 Platform
// 字段；实际逻辑复用 browser_ext.go / browser_ext_cap.go。
func registerLinuxBrowserExt(reg *Registry) {
	registerBrowserExt(reg, PlatformLinux)
}
