//go:build !windows

package selfupdate

// SpawnApplyHelper 在非 Windows 平台上是空实现。
//
// 为什么需要：Linux 可直接 rename 替换运行中的可执行文件（见 apply_linux.go），
// 无需 helper 子进程。此空实现让 cmd/jarvis-daemon 可以跨平台无条件调用，
// 避免在上层写平台分支。
//
// 返回值恒为 (0, nil)：调用方据此判断「无需 helper」。
func SpawnApplyHelper(_, _, _ string, _ bool) (int, error) {
	return 0, nil
}
