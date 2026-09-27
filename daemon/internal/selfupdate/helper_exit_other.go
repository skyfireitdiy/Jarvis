//go:build !windows

package selfupdate

// exitForHelperReplacement 在非 Windows 平台上是空实现。
//
// 为什么需要：helper 替换路径只在 Windows 上真正使用（Linux 可直接 rename 替换运行中的
// 可执行文件，见 apply_linux.go；SpawnApplyHelper 在非 Windows 返回 (0, nil)，调用方
// 据此判定「无需 helper」）。此空实现让 updater.go 可以跨平台无条件调用，避免在上层
// 写平台分支。
func exitForHelperReplacement() {}
