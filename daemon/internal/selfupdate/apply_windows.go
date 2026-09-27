//go:build windows

package selfupdate

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
)

// isWindows 报告当前平台是否为 Windows。
func isWindows() bool { return true }

// lower 返回 s 的小写形式（Windows 路径比较需忽略大小写）。
func lower(s string) string { return strings.ToLower(s) }

// replaceExecutable 在 Windows 上替换目标可执行文件。
//
// 难点：Windows 不允许覆盖/重命名正在运行的 exe（文件被独占锁）。
// 因此这里不能像 Linux 那样直接 rename，而是启动一个**分离的 helper 子进程**，
// 由它在当前进程退出后再完成替换（见 cmd/jarvis-daemon 的 self-update-apply 子命令）。
//
// 但 helper 方案需要「父进程先退出」，而本函数是在父进程内同步调用的。
// 为保持 Apply 的语义（调用后磁盘已是新版），这里采用如下策略：
//   - 先把新文件放到目标同目录（已是 tmpPath），尝试直接 rename；
//   - 若因文件占用失败，则退回到「计划替换」模式：把新文件保留为
//     <target>.new，并返回一个明确的错误，提示调用方改走 helper 子命令。
//
// 说明：真正的「运行中替换」由 cmd/jarvis-daemon 的 self-update-apply 子命令
// （在父进程退出后运行）完成，本函数只负责尽力而为的即时替换。
func replaceExecutable(tmpPath, targetPath string) error {
	if err := os.Rename(tmpPath, targetPath); err == nil {
		return nil
	}
	// 目标被占用：保留新文件为 <target>.new，交给 helper 子命令在退出后替换。
	pending := targetPath + ".new"
	if err := os.Rename(tmpPath, pending); err != nil {
		_ = os.Remove(tmpPath)
		return fmt.Errorf("替换可执行文件失败（且无法保留待替换文件）: %w", err)
	}
	return fmt.Errorf("目标可执行文件正被占用，已保留待替换文件 %s，请通过 self-update-apply 子命令完成替换", filepath.Base(pending))
}

// SpawnApplyHelper 启动一个分离的 helper 子进程，在当前进程退出后完成替换与重启。
//
// 参数：
//   - exePath：当前可执行文件路径（helper 用它来定位自己，即启动自身的新副本）；
//     注意：helper 应从「待替换的新文件」启动，以避免旧文件被占用无法执行；
//   - newBinary：新版本可执行文件路径（尚未就位）；
//   - target：最终要替换到的路径；
//   - restart：替换后是否重启服务。
//
// 返回 helper 的进程 PID 供日志记录。
//
// 实现要点：使用 DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP，使 helper 不随父进程
// 退出而被终止；helper 内部会轮询等待 target 不再被占用后再替换。
func SpawnApplyHelper(_ string, newBinary, target string, restart bool) (int, error) {
	// helper 从「新文件」启动：先把新文件复制到 <target>.helper.exe 并执行它，
	// 这样即使 target 被占用也不影响 helper 自身运行。
	helperExe := target + ".helper.exe"
	if err := copyFileExecutable(newBinary, helperExe); err != nil {
		return 0, err
	}
	args := []string{"self-update-apply", "--src", helperExe, "--dst", target}
	if restart {
		args = append(args, "--restart")
	}
	cmd := exec.Command(helperExe, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{
		// CREATE_NO_WINDOW：helper 也是控制台程序，父进程无控制台时若不带该标志
		// 会新建控制台窗口（闪黑框）。
		CreationFlags: syscall.CREATE_NEW_PROCESS_GROUP | 0x00000008 | 0x08000000, // DETACHED_PROCESS | CREATE_NO_WINDOW
	}
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err := cmd.Start(); err != nil {
		return 0, fmt.Errorf("启动更新 helper 失败: %w", err)
	}
	pid := cmd.Process.Pid
	// 不 Wait：让 helper 独立运行，父进程随后退出。
	_ = cmd.Process.Release()
	return pid, nil
}
