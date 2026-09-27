package service

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

// 安装目录：把守护进程可执行文件拷贝到 ~/.jarvis/bin 下，使服务引用的位置固定，
// 不再依赖用户当初运行 install 时那个可能被移动/删除的路径。

// InstallDirName 是安装目录名（位于用户主目录的 .jarvis 下）。
const InstallDirName = "bin"

// BinaryName 是安装后的可执行文件名（Windows 带 .exe 后缀）。
func BinaryName() string {
	if runtime.GOOS == "windows" {
		return "jarvis-daemon.exe"
	}
	return "jarvis-daemon"
}

// InstallDir 返回安装目录的绝对路径：~/.jarvis/bin。
func InstallDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("获取用户主目录失败: %w", err)
	}
	return filepath.Join(home, ".jarvis", InstallDirName), nil
}

// InstalledBinaryPath 返回安装后可执行文件的绝对路径：~/.jarvis/bin/jarvis-daemon[.exe]。
func InstalledBinaryPath() (string, error) {
	dir, err := InstallDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, BinaryName()), nil
}

// samePath 判断两个路径是否指向同一文件（忽略大小写差异在 Windows 上尤为重要）。
func samePath(a, b string) bool {
	if a == "" || b == "" {
		return false
	}
	if runtime.GOOS == "windows" {
		return filepath.Clean(strings.ToLower(a)) == filepath.Clean(strings.ToLower(b))
	}
	return filepath.Clean(a) == filepath.Clean(b)
}

// copyFileAtomic 把 src 拷贝到 dst：先写同目录临时文件再 rename，避免中途失败留下半截文件。
func copyFileAtomic(src, dst string) error {
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return fmt.Errorf("创建安装目录失败: %w", err)
	}
	in, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("打开源文件失败: %w", err)
	}
	defer in.Close()

	tmp, err := os.CreateTemp(filepath.Dir(dst), ".jarvis-daemon-*")
	if err != nil {
		return fmt.Errorf("创建临时文件失败: %w", err)
	}
	tmpName := tmp.Name()
	// 任一步骤失败都清理临时文件。
	defer func() {
		if tmpName != "" {
			_ = os.Remove(tmpName)
		}
	}()

	if _, err := io.Copy(tmp, in); err != nil {
		tmp.Close()
		return fmt.Errorf("拷贝可执行文件失败: %w", err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("写入可执行文件失败: %w", err)
	}
	// 可执行权限（Windows 上忽略）。
	if err := os.Chmod(tmpName, 0o755); err != nil {
		return fmt.Errorf("设置可执行权限失败: %w", err)
	}
	// Windows 上目标可能正被占用，rename 会失败；先尝试删除旧文件再重命名。
	if err := os.Rename(tmpName, dst); err != nil {
		if rmErr := os.Remove(dst); rmErr != nil && !os.IsNotExist(rmErr) {
			return fmt.Errorf("覆盖旧可执行文件失败: %w", err)
		}
		if err := os.Rename(tmpName, dst); err != nil {
			return fmt.Errorf("安装可执行文件失败: %w", err)
		}
	}
	tmpName = "" // 已成功重命名，无需清理
	return nil
}

// PrepareInstalledBinary 把当前可执行文件拷贝到固定安装目录，并返回指向该固定路径的 Options。
// 若当前可执行文件已经是该固定路径（例如服务已安装、用户再次执行 install），则跳过拷贝直接返回。
func PrepareInstalledBinary(opts Options) (Options, string, error) {
	src, err := ResolveExecPath(opts)
	if err != nil {
		return opts, "", err
	}
	dst, err := InstalledBinaryPath()
	if err != nil {
		return opts, "", err
	}
	if samePath(src, dst) {
		// 自身已是安装路径：无需拷贝，继续后续流程。
		opts.ExecPath = dst
		return opts, dst, nil
	}
	if err := copyFileAtomic(src, dst); err != nil {
		return opts, "", err
	}
	opts.ExecPath = dst
	return opts, dst, nil
}

// RemoveInstalledBinary 删除安装目录下的可执行文件；目录为空时一并删除。
// 文件不存在视为成功（幂等）。
func RemoveInstalledBinary() error {
	dst, err := InstalledBinaryPath()
	if err != nil {
		return err
	}
	if err := os.Remove(dst); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("删除可执行文件失败: %w", err)
	}
	// 目录为空则删除（非空说明用户还放了别的东西，保留）。
	if dir, err := InstallDir(); err == nil {
		_ = os.Remove(dir)
	}
	return nil
}
