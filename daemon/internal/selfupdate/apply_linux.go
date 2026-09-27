//go:build linux

package selfupdate

import (
	"fmt"
	"os"
)

// isWindows 报告当前平台是否为 Windows（Linux 实现恒为 false）。
func isWindows() bool { return false }

// lower 返回 s 的小写形式（Windows 路径比较用；Linux 上原样返回）。
func lower(s string) string { return s }

// replaceExecutable 在 Linux 上直接用 rename 覆盖目标。
//
// 为什么可行：Linux 允许替换正在运行的可执行文件——旧进程继续持有已删除的 inode，
// 新进程启动时读到的是新文件。同目录 rename 是原子操作，不会出现「半个可执行文件」。
func replaceExecutable(tmpPath, targetPath string) error {
	if err := os.Rename(tmpPath, targetPath); err != nil {
		// rename 失败时清理临时文件，避免残留。
		_ = os.Remove(tmpPath)
		return fmt.Errorf("替换可执行文件失败: %w", err)
	}
	// 确保可执行位（rename 保留原权限，这里再保险一次）。
	_ = os.Chmod(targetPath, 0o755)
	return nil
}
