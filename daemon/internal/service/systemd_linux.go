//go:build linux

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

// systemctlTimeout 是单次 systemctl 调用的超时时间。
const systemctlTimeout = 10 * time.Second

// proxyEnvVars 是需要透传给服务的代理相关环境变量。
var proxyEnvVars = []string{
	"http_proxy", "HTTP_PROXY",
	"https_proxy", "HTTPS_PROXY",
	"no_proxy", "NO_PROXY",
	"ftp_proxy", "FTP_PROXY",
	"socks_proxy", "SOCKS_PROXY",
}

// systemdService 是 Linux 下的 systemd 用户服务实现。
type systemdService struct{}

// UnitPath 返回服务文件的绝对路径：~/.config/systemd/user/jarvis-daemon.service。
func UnitPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("获取用户主目录失败: %w", err)
	}
	return filepath.Join(home, ".config", "systemd", "user", ServiceName), nil
}

// BuildUnit 生成 systemd unit 文件内容。
func BuildUnit(opts Options) (string, error) {
	execPath, err := ResolveExecPath(opts)
	if err != nil {
		return "", err
	}

	var b strings.Builder
	b.WriteString("[Unit]\n")
	b.WriteString("Description=Jarvis Daemon\n")
	b.WriteString("After=network.target\n")
	b.WriteString("\n[Service]\n")
	b.WriteString("Type=simple\n")
	b.WriteString("Environment=PATH=" + buildServicePath(execPath) + "\n")
	for _, name := range proxyEnvVars {
		if v := os.Getenv(name); v != "" {
			b.WriteString("Environment=" + name + "=" + v + "\n")
		}
	}
	b.WriteString("ExecStart=" + execPath + " " + strings.Join(BuildRunArgs(opts), " ") + "\n")
	b.WriteString("Restart=always\n")
	b.WriteString("RestartSec=5\n")
	b.WriteString("\n[Install]\n")
	b.WriteString("WantedBy=default.target\n")
	return b.String(), nil
}

// buildServicePath 在当前 PATH 前插入可执行文件所在目录，避免服务找不到自身依赖。
func buildServicePath(execPath string) string {
	current := os.Getenv("PATH")
	dir := filepath.Dir(execPath)
	if dir == "" {
		return current
	}
	for _, p := range strings.Split(current, ":") {
		if p == dir {
			return current
		}
	}
	if current == "" {
		return dir
	}
	return dir + ":" + current
}

// Install 写入 unit 文件、daemon-reload 并 enable（不启动）。
func (s *systemdService) Install(opts Options) (string, error) {
	content, err := BuildUnit(opts)
	if err != nil {
		return "", err
	}
	unitPath, err := UnitPath()
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(filepath.Dir(unitPath), 0o755); err != nil {
		return "", fmt.Errorf("创建 systemd 用户目录失败: %w", err)
	}
	if err := os.WriteFile(unitPath, []byte(content), 0o644); err != nil {
		return "", fmt.Errorf("写入服务文件失败: %w", err)
	}
	if _, err := runSystemctl("daemon-reload"); err != nil {
		return "", fmt.Errorf("daemon-reload 失败: %w", err)
	}
	if _, err := runSystemctl("enable", ServiceName); err != nil {
		return "", fmt.Errorf("启用服务失败: %w", err)
	}
	return fmt.Sprintf("服务已安装并设为开机自启：%s", unitPath), nil
}

// Uninstall 停止服务、取消自启并删除 unit 文件。
func (s *systemdService) Uninstall() (string, error) {
	unitPath, err := UnitPath()
	if err != nil {
		return "", err
	}
	if _, err := os.Stat(unitPath); err != nil {
		if os.IsNotExist(err) {
			return "", fmt.Errorf("服务未安装：%s 不存在", unitPath)
		}
		return "", fmt.Errorf("检查服务文件失败: %w", err)
	}
	// 停止与禁用失败不阻断卸载，最终以文件是否删除为准。
	_, _ = runSystemctl("stop", ServiceName)
	_, _ = runSystemctl("disable", ServiceName)
	if err := os.Remove(unitPath); err != nil {
		return "", fmt.Errorf("删除服务文件失败: %w", err)
	}
	if _, err := runSystemctl("daemon-reload"); err != nil {
		return "", fmt.Errorf("daemon-reload 失败: %w", err)
	}
	return fmt.Sprintf("服务已卸载：%s", unitPath), nil
}

// Start 启动服务。
func (s *systemdService) Start() (string, error) {
	if _, err := runSystemctl("start", ServiceName); err != nil {
		return "", fmt.Errorf("启动服务失败: %w", err)
	}
	return "服务已启动", nil
}

// Stop 停止服务。
func (s *systemdService) Stop() (string, error) {
	if _, err := runSystemctl("stop", ServiceName); err != nil {
		return "", fmt.Errorf("停止服务失败: %w", err)
	}
	return "服务已停止", nil
}

// Restart 重启服务。
func (s *systemdService) Restart() (string, error) {
	if _, err := runSystemctl("restart", ServiceName); err != nil {
		return "", fmt.Errorf("重启服务失败: %w", err)
	}
	return "服务已重启", nil
}

// Status 查询服务运行与自启状态。
func (s *systemdService) Status() (Status, error) {
	var st Status

	out, err := runSystemctl("is-active", ServiceName)
	st.Running = err == nil && strings.TrimSpace(out) == "active"

	if _, err := runSystemctl("is-enabled", ServiceName); err == nil {
		st.Enabled = true
	}

	if st.Running {
		pidOut, err := runSystemctl("show", ServiceName, "--property=MainPID")
		if err == nil {
			if v, ok := strings.CutPrefix(strings.TrimSpace(pidOut), "MainPID="); ok {
				if pid, convErr := strconv.Atoi(strings.TrimSpace(v)); convErr == nil && pid > 0 {
					st.PID = pid
				}
			}
		}
	}
	return st, nil
}

// runSystemctl 执行 systemctl --user 命令并返回标准输出。
func runSystemctl(args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), systemctlTimeout)
	defer cancel()

	full := append([]string{"--user"}, args...)
	cmd := exec.CommandContext(ctx, "systemctl", full...)
	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() != nil {
			return "", fmt.Errorf("systemctl %s 超时", strings.Join(args, " "))
		}
		var exitErr *exec.ExitError
		if ok := asExitError(err, &exitErr); ok {
			msg := strings.TrimSpace(string(exitErr.Stderr))
			if msg == "" {
				msg = strings.TrimSpace(string(out))
			}
			return string(out), fmt.Errorf("systemctl %s 失败: %s", strings.Join(args, " "), msg)
		}
		return "", fmt.Errorf("执行 systemctl 失败: %w", err)
	}
	return string(out), nil
}

// asExitError 是 errors.As 的薄封装，避免在此文件重复导入 errors。
func asExitError(err error, target **exec.ExitError) bool {
	e, ok := err.(*exec.ExitError)
	if ok {
		*target = e
	}
	return ok
}
