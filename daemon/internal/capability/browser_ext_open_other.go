//go:build !windows

package capability

// openBrowserExtensionsPage 在非 Windows 平台上是空实现。
//
// 为什么需要：自动打开浏览器扩展页只在 Windows 上实现（用 PowerShell 的
// Start-Process）。此空实现让调用方（main.go 的自动同步路径）可以跨平台
// 无条件调用，无需在上层写平台分支。
//
// 返回空列表且不报错：非 Windows 平台不提供该能力，调用方据此跳过即可。
func OpenBrowserExtensionsPage() ([]string, error) {
	return nil, nil
}
