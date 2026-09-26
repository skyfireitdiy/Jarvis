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
func (s *taskService) Install(opts Options) (string, error) {
	args, err := BuildCreateArgs(opts)
	if err != nil {
		return "", err
	}
	if _, err := runCmd("schtasks", args...); err != nil {
		return "", fmt.Errorf("创建计划任务失败: %w", err)
	}
	return fmt.Sprintf("计划任务已创建：%s", TaskName), nil
}

// Uninstall 停止服务并删除计划任务。
func (s *taskService) Uninstall() (string, error) {
	_, _ = s.Stop()
	if _, err := runCmd("schtasks", "/Delete", "/TN", TaskName, "/F"); err != nil {
		return "", fmt.Errorf("删除计划任务失败: %w", err)
	}
	return fmt.Sprintf("计划任务已删除：%s", TaskName), nil
}

// Start 以分离进程启动守护进程并记录 PID。
func (s *taskService) Start() (string, error) {
	pidPath, err := PidFilePath()
	if err != nil {
		return "", err
	}
	if pid := readAlivePID(pidPath); pid > 0 {
		return "", fmt.Errorf("服务已在运行（PID: %d）", pid)
	}

	execPath, err := ResolveExecPath(Options{})
	if err != nil {
		return "", err
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

// runCmd 执行外部命令并返回标准输出。
func runCmd(name string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), cmdTimeout)
	defer cancel()

	out, err := exec.CommandContext(ctx, name, args...).Output()
	if err != nil {
		if ctx.Err() != nil {
			return "", fmt.Errorf("%s 超时", name)
		}
		if exitErr, ok := err.(*exec.ExitError); ok {
			msg := strings.TrimSpace(string(exitErr.Stderr))
			if msg == "" {
				msg = strings.TrimSpace(string(out))
			}
			return string(out), fmt.Errorf("%s 失败: %s", name, msg)
		}
		return "", fmt.Errorf("执行 %s 失败: %w", name, err)
	}
	return string(out), nil
}
