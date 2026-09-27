//go:build !linux && !windows

package selfupdate

import (
	"fmt"
	"os"
	"runtime"
)

// isWindows 报告当前平台是否为 Windows（其他平台恒为 false）。
func isWindows() bool { return false }

// lower 返回 s 的小写形式（其他平台原样返回）。
func lower(s string) string { return s }

// replaceExecutable 在其他平台（如 darwin）上尽力尝试 rename。
//
// 本项目只承诺 Windows 与 Linux；此实现仅为让代码在 darwin 上也能编译通过，
// 不保证更新流程在该平台可用。
func replaceExecutable(tmpPath, targetPath string) error {
	if err := os.Rename(tmpPath, targetPath); err != nil {
		_ = os.Remove(tmpPath)
		return fmt.Errorf("替换可执行文件失败（平台 %s 不受支持）: %w", runtime.GOOS, err)
	}
	_ = os.Chmod(targetPath, 0o755)
	return nil
}
