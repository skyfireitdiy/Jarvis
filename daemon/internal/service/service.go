// Package service 负责把守护进程注册为系统服务：
// Linux 使用 systemd 用户服务，Windows 使用计划任务。
package service

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

// ServiceName 是 Linux 下的 systemd 服务文件名。
const ServiceName = "jarvis-daemon.service"

// TaskName 是 Windows 下的计划任务名。
const TaskName = "Jarvis-Daemon"

// Options 是安装服务所需的参数。
type Options struct {
	// ExecPath 是守护进程可执行文件的绝对路径；为空时取当前进程路径。
	ExecPath string
	// Listen 是本地 API 监听地址。
	Listen string
	// Gateway 是默认网关地址，可为空。
	Gateway string
	// ConfigPath 是配置文件路径，可为空。
	ConfigPath string
}

// Status 是服务状态（跨平台统一格式）。
type Status struct {
	// Running 表示服务当前是否在运行。
	Running bool
	// Enabled 表示是否已配置开机自启。
	Enabled bool
	// PID 是主进程 ID，未知时为 0。
	PID int
	// Detail 是补充说明（如原始错误信息）。
	Detail string
}

// Service 是跨平台的服务管理接口。
type Service interface {
	// Install 写入服务定义并启用自启（不启动）。
	Install(opts Options) (string, error)
	// Uninstall 停止服务并删除服务定义。
	Uninstall() (string, error)
	// Start 启动服务。
	Start() (string, error)
	// Stop 停止服务。
	Stop() (string, error)
	// Restart 重启服务。
	Restart() (string, error)
	// Status 查询服务状态。
	Status() (Status, error)
}

// newPlatformService 由各平台的实现文件提供（见 new_linux.go / new_windows.go）。
// 返回 nil 表示当前平台不支持服务安装。

// New 返回当前平台的服务实现；平台不支持时返回一个总是报错的实现。
func New() Service {
	if svc := newPlatformService(); svc != nil {
		return svc
	}
	return &unsupportedService{goos: runtime.GOOS}
}

// ResolveExecPath 返回可执行文件绝对路径：优先使用 opts.ExecPath，否则取当前进程路径。
func ResolveExecPath(opts Options) (string, error) {
	if p := strings.TrimSpace(opts.ExecPath); p != "" {
		abs, err := filepath.Abs(p)
		if err != nil {
			return "", fmt.Errorf("解析可执行文件路径失败: %w", err)
		}
		return abs, nil
	}
	exe, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("获取当前可执行文件路径失败: %w", err)
	}
	if resolved, err := filepath.EvalSymlinks(exe); err == nil {
		exe = resolved
	}
	return exe, nil
}

// BuildRunArgs 构造服务启动时传给守护进程的参数（不含可执行文件本身）。
func BuildRunArgs(opts Options) []string {
	args := []string{"run"}
	if opts.Listen != "" {
		args = append(args, "--listen", opts.Listen)
	}
	if opts.Gateway != "" {
		args = append(args, "--gateway", opts.Gateway)
	}
	if opts.ConfigPath != "" {
		args = append(args, "--config", opts.ConfigPath)
	}
	return args
}

// unsupportedService 用于既非 Linux 也非 Windows 的平台。
type unsupportedService struct {
	goos string
}

func (s *unsupportedService) err() error {
	return fmt.Errorf("当前平台 %s 不支持服务安装", s.goos)
}

func (s *unsupportedService) Install(Options) (string, error) { return "", s.err() }
func (s *unsupportedService) Uninstall() (string, error)      { return "", s.err() }
func (s *unsupportedService) Start() (string, error)          { return "", s.err() }
func (s *unsupportedService) Stop() (string, error)           { return "", s.err() }
func (s *unsupportedService) Restart() (string, error)        { return "", s.err() }
func (s *unsupportedService) Status() (Status, error)         { return Status{}, s.err() }
