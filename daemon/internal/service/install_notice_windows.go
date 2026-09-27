//go:build windows

package service

import "fmt"

// InstallNotice 返回 Windows 下安装前的权限与风险提示（供 CLI 打印）。
//
// Windows 的计划任务使用 /RL HIGHEST（以最高权限运行），因此创建任务本身
// 需要在**管理员**会话中执行；任务运行时的进程也拥有管理员权限。
// 这里把这两点如实告知用户，避免用户在普通会话里遇到「拒绝访问」时不明所以。
func InstallNotice() string {
	return `注意：Windows 下安装会把守护进程注册为计划任务，并以「最高权限」运行。
  1. 创建计划任务需要管理员权限，请在**以管理员身份运行**的终端中执行 install；
     否则会因权限不足失败（提示「拒绝访问」）。
  2. 任务在用户登录时自动启动，启动后的守护进程拥有管理员权限。
  3. 风险：守护进程可执行的能力（文件读写、进程管理、脚本执行、桌面自动化等）
     将以管理员权限生效，请仅在自己信任的机器上安装，并妥善保管登录凭据。
  4. 卸载：以管理员身份执行 uninstall 可删除计划任务与安装的可执行文件。`
}

// StartHint 返回安装后启动服务的提示（含可执行文件的完整路径）。
//
// 之所以给出完整路径：安装会把 exe 拷贝到 ~/.jarvis/bin 下，该目录**不在 PATH**，
// 直接敲 `jarvis-daemon start` 会报「无法识别为 cmdlet/命令」。用完整路径才能执行。
// 同时提示后续的 start/stop/status/uninstall 都应使用该固定路径的 exe，
// 以保证与计划任务指向的可执行文件一致。
//
// 命令用 PowerShell 的调用运算符 `&`：路径含空格或带引号时，PowerShell 不会把
// 引号后的字符串当作参数（直接写 `"C:\...\x.exe" start` 会报「意外的标记 start」），
// 必须写成 `& "C:\...\x.exe" start` 才能正确执行。这样用户可直接复制粘贴。
func StartHint() string {
	path, err := InstalledBinaryPath()
	if err != nil {
		path = `%USERPROFILE%\.jarvis\bin\jarvis-daemon.exe`
	}
	return fmt.Sprintf("提示：安装目录不在 PATH 中，请在 PowerShell 中使用如下命令（注意开头的 &）：\n"+
		"  & \"%s\" start\n"+
		"  后续 start/stop/status/uninstall 均请使用该路径的 exe。", path)
}
