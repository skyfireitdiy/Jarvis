//go:build windows

package service

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// cmdTimeout 是单次外部命令调用的超时时间。
const cmdTimeout = 30 * time.Second

// taskService 是 Windows 下的计划任务实现。
//
// 自启由计划任务负责（登录时触发），进程生命周期由 PID 文件跟踪。
type taskService struct{}

// PidFilePath 返回 PID 文件路径：~/.jarvis/pids/jarvis-daemon.pid。
func PidFilePath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("获取用户主目录失败: %w", err)
	}
	return filepath.Join(home, ".jarvis", "pids", "jarvis-daemon.pid"), nil
}

// BuildTaskCommand 生成计划任务要执行的命令行（含可执行文件本身）。
func BuildTaskCommand(opts Options) (string, error) {
	execPath, err := ResolveExecPath(opts)
	if err != nil {
		return "", err
	}
	parts := append([]string{execPath}, BuildRunArgs(opts)...)
	for i, p := range parts {
		if strings.ContainsAny(p, " \t") {
			parts[i] = `"` + p + `"`
		}
	}
	return strings.Join(parts, " "), nil
}

// BuildCreateArgs 生成 schtasks 创建计划任务的参数。
func BuildCreateArgs(opts Options) ([]string, error) {
	command, err := BuildTaskCommand(opts)
	if err != nil {
		return nil, err
	}
	return []string{
		"/Create",
		"/TN", TaskName,
		"/TR", command,
		"/SC", "ONLOGON",
		"/RL", "HIGHEST",
		"/F",
	}, nil
}

// Install 创建登录时触发的计划任务（不启动）。
// 安装前先把可执行文件拷贝到固定安装目录 ~/.jarvis/bin，使计划任务指向的位置稳定。
func (s *taskService) Install(opts Options) (string, error) {
	opts, installedPath, err := PrepareInstalledBinary(opts)
	if err != nil {
		return "", err
	}
	args, err := BuildCreateArgs(opts)
	if err != nil {
		return "", err
	}
	if _, err := runCmd("schtasks", args...); err != nil {
		return "", fmt.Errorf("创建计划任务失败: %w（该任务以最高权限运行，需在**管理员**终端中执行 install）", err)
	}
	return fmt.Sprintf("计划任务已创建：%s（可执行文件：%s）", TaskName, installedPath), nil
}

// Uninstall 停止服务并删除计划任务。
func (s *taskService) Uninstall() (string, error) {
	_, _ = s.Stop()
	if _, err := runCmd("schtasks", "/Delete", "/TN", TaskName, "/F"); err != nil {
		return "", fmt.Errorf("删除计划任务失败: %w", err)
	}
	// 清理安装目录中的可执行文件（失败不阻断卸载，仅提示）。
	cleanupNote := ""
	if err := RemoveInstalledBinary(); err != nil {
		cleanupNote = fmt.Sprintf("（可执行文件清理失败：%v）", err)
	}
	return fmt.Sprintf("计划任务已删除：%s%s", TaskName, cleanupNote), nil
}

// Start 以分离进程启动守护进程并记录 PID。
//
// 启动的是**固定安装路径**（~/.jarvis/bin/jarvis-daemon.exe）的可执行文件，而不是
// 当前进程路径：计划任务指向的也是该固定路径，两者必须一致，否则用户从下载目录执行
// start 会启动另一个副本，与服务管理（stop/status）观察到的进程对不上。
func (s *taskService) Start() (string, error) {
	pidPath, err := PidFilePath()
	if err != nil {
		return "", err
	}
	if pid := readAlivePID(pidPath); pid > 0 {
		return "", fmt.Errorf("服务已在运行（PID: %d）", pid)
	}

	execPath, err := InstalledBinaryPath()
	if err != nil {
		return "", err
	}
	if _, statErr := os.Stat(execPath); statErr != nil {
		return "", fmt.Errorf("未找到已安装的可执行文件 %s，请先执行 install", execPath)
	}
	cmd := exec.Command(execPath, BuildRunArgs(Options{})...)
	cmd.SysProcAttr = detachedProcAttr()
	if err := cmd.Start(); err != nil {
		return "", fmt.Errorf("启动服务失败: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(pidPath), 0o755); err != nil {
		return "", fmt.Errorf("创建 PID 目录失败: %w", err)
	}
	if err := os.WriteFile(pidPath, []byte(strconv.Itoa(cmd.Process.Pid)), 0o644); err != nil {
		return "", fmt.Errorf("写入 PID 文件失败: %w", err)
	}
	return fmt.Sprintf("服务已启动（PID: %d）", cmd.Process.Pid), nil
}

// Stop 终止守护进程并清理 PID 文件。
func (s *taskService) Stop() (string, error) {
	pidPath, err := PidFilePath()
	if err != nil {
		return "", err
	}
	pid := readAlivePID(pidPath)
	if pid <= 0 {
		_ = os.Remove(pidPath)
		return "服务未运行", nil
	}
	if _, err := runCmd("taskkill", "/PID", strconv.Itoa(pid), "/F"); err != nil {
		return "", fmt.Errorf("停止服务失败: %w", err)
	}
	_ = os.Remove(pidPath)
	return "服务已停止", nil
}

// Restart 先停止再启动。
func (s *taskService) Restart() (string, error) {
	if _, err := s.Stop(); err != nil {
		return "", err
	}
	time.Sleep(2 * time.Second)
	return s.Start()
}

// Status 查询运行与自启状态。
func (s *taskService) Status() (Status, error) {
	var st Status

	if pidPath, err := PidFilePath(); err == nil {
		st.PID = readAlivePID(pidPath)
		st.Running = st.PID > 0
	}

	if _, err := runCmd("schtasks", "/Query", "/TN", TaskName); err == nil {
		st.Enabled = true
	}
	return st, nil
}

// readAlivePID 读取 PID 文件并校验进程是否存活；无效时删除文件并返回 0。
func readAlivePID(pidPath string) int {
	data, err := os.ReadFile(pidPath)
	if err != nil {
		return 0
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(data)))
	if err != nil || pid <= 0 {
		_ = os.Remove(pidPath)
		return 0
	}
	out, err := runCmd("tasklist", "/FI", fmt.Sprintf("PID eq %d", pid), "/NH")
	if err != nil || !strings.Contains(out, strconv.Itoa(pid)) {
		_ = os.Remove(pidPath)
		return 0
	}
	return pid
}

// runCmd 执行外部命令并返回标准输出（UTF-8 文本）。
//
// 编码问题：schtasks / taskkill / tasklist 是原生控制台程序，按**控制台输出代码页**
// 写出文本——中文 Windows 上是 GBK/CP936，不是 UTF-8。Go 的 os/exec 只返回原始字节，
// 直接 string(out) 会把 GBK 按 UTF-8 解释，得到 "����: �ܾ����ʡ�" 这类乱码，
// 用户无法看懂失败原因（真机实测 install 失败时即如此）。
//
// 修复策略（与 internal/capability 的 windows_encoding.go 同思路，不引入 GBK 解码表）：
// 用 PowerShell 包裹执行，借助 PowerShell 完成「GBK 解码 → UTF-8 输出」的转码：
//
//  1. 先按**系统默认**的 [Console]::OutputEncoding（中文系统 = GBK）读取外部命令输出。
//     这一步必须在改编码之前，否则 PowerShell 会用 UTF-8 去解码 GBK 字节而得到乱码。
//  2. 再把 [Console]::OutputEncoding 设为 UTF-8，用 [Console]::Out.Write 写出。
//     此时 Go 侧读到的就是 UTF-8 字节，直接 string(out) 即为正确文本。
//
// 之所以不用 `cmd /c chcp 65001`：chcp 只改 cmd 会话的输出代码页，而原生工具在
// stdout 被重定向到管道时是否遵循该代码页并无保证；PowerShell 的显式转码不依赖
// 子进程行为，更可靠（也与项目既有的 runWindowsPowerShellCommand 路径一致）。
//
// 脚本经 -EncodedCommand（base64 UTF-16LE）传递，避免命令行参数按 ANSI 代码页解析
// 导致脚本内非 ASCII 字符损坏（见 windows_encoding.go 的说明）。
func runCmd(name string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), cmdTimeout)
	defer cancel()

	script := buildPowerShellScript(name, args)
	cmd := exec.CommandContext(ctx, "powershell.exe",
		"-NoProfile",
		"-NonInteractive",
		"-ExecutionPolicy", "Bypass",
		"-EncodedCommand", encodePowerShellCommand(script),
	)
	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() != nil {
			return "", fmt.Errorf("%s 超时", name)
		}
		if exitErr, ok := err.(*exec.ExitError); ok {
			msg := strings.TrimSpace(string(exitErr.Stderr))
			if msg == "" {
				// PowerShell 把外部命令的 stdout/stderr 都写到了自己的 stdout，
				// 且可能混入 CLIXML 噪音（见 stripPowerShellClixml），需先清理再取用。
				msg = stripPowerShellClixml(string(out))
			}
			if msg == "" {
				msg = "命令返回非零退出码，但无输出"
			}
			return string(out), fmt.Errorf("%s 失败: %s", name, msg)
		}
		return "", fmt.Errorf("执行 %s 失败: %w", name, err)
	}
	return string(out), nil
}
