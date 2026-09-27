package selfupdate

import (
	"fmt"
	"os"
	"path/filepath"
)

// Apply 用 newBinaryPath 处的新可执行文件替换 targetPath 处的当前可执行文件。
//
// 语义（跨平台统一）：
//   - 若 newBinaryPath 与 targetPath 不在同一目录，先拷贝到 targetPath 同目录的
//     临时文件（同文件系统才能保证 rename 原子性）；
//   - 平台差异由 replaceExecutable 实现（见 apply_linux.go / apply_windows.go）；
//   - 成功后 newBinaryPath 可能已被移动/删除（Linux 走 rename）。
//
// 注意：本函数不负责重启服务，只负责「把磁盘上的可执行文件换成新版」。
func Apply(newBinaryPath, targetPath string) error {
	if newBinaryPath == "" || targetPath == "" {
		return fmt.Errorf("替换参数不完整: src=%q dst=%q", newBinaryPath, targetPath)
	}
	if _, err := os.Stat(newBinaryPath); err != nil {
		return fmt.Errorf("新可执行文件不可用: %w", err)
	}

	// 统一放到 targetPath 同目录的临时文件，确保与目标同文件系统（rename 原子）。
	tmpPath := filepath.Join(filepath.Dir(targetPath), "."+filepath.Base(targetPath)+".new")
	if !samePath(newBinaryPath, tmpPath) {
		if err := copyFileExecutable(newBinaryPath, tmpPath); err != nil {
			return err
		}
	}
	if err := os.Chmod(tmpPath, 0o755); err != nil {
		return fmt.Errorf("设置可执行权限失败: %w", err)
	}
	return replaceExecutable(tmpPath, targetPath)
}

// copyFileExecutable 把 src 拷贝到 dst（覆盖），并设置可执行权限。
func copyFileExecutable(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("打开新可执行文件失败: %w", err)
	}
	defer in.Close()
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o755)
	if err != nil {
		return fmt.Errorf("创建临时可执行文件失败: %w", err)
	}
	if _, err := out.ReadFrom(in); err != nil {
		out.Close()
		_ = os.Remove(dst)
		return fmt.Errorf("拷贝新可执行文件失败: %w", err)
	}
	if err := out.Close(); err != nil {
		_ = os.Remove(dst)
		return fmt.Errorf("关闭临时可执行文件失败: %w", err)
	}
	return nil
}

// samePath 判断两个路径是否指向同一文件（Windows 上忽略大小写）。
func samePath(a, b string) bool {
	if a == "" || b == "" {
		return false
	}
	if isWindows() {
		return filepath.Clean(lower(a)) == filepath.Clean(lower(b))
	}
	return filepath.Clean(a) == filepath.Clean(b)
}
