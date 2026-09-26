package service

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestServiceNameAndTaskName(t *testing.T) {
	if ServiceName != "jarvis-daemon.service" {
		t.Errorf("ServiceName = %q, 期望 jarvis-daemon.service", ServiceName)
	}
	if TaskName != "Jarvis-Daemon" {
		t.Errorf("TaskName = %q, 期望 Jarvis-Daemon", TaskName)
	}
}

func TestResolveExecPathUsesProvidedPath(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "jarvis-daemon")
	if err := os.WriteFile(target, []byte("x"), 0o755); err != nil {
		t.Fatalf("准备测试文件失败: %v", err)
	}
	got, err := ResolveExecPath(Options{ExecPath: target})
	if err != nil {
		t.Fatalf("ResolveExecPath 返回错误: %v", err)
	}
	if got != target {
		t.Errorf("ResolveExecPath = %q, 期望 %q", got, target)
	}
}

func TestResolveExecPathFallsBackToCurrentProcess(t *testing.T) {
	got, err := ResolveExecPath(Options{})
	if err != nil {
		t.Fatalf("ResolveExecPath 返回错误: %v", err)
	}
	if !filepath.IsAbs(got) {
		t.Errorf("兜底路径应为绝对路径，实际 %q", got)
	}
	if _, err := os.Stat(got); err != nil {
		t.Errorf("兜底路径不可访问: %v", err)
	}
}

func TestBuildRunArgs(t *testing.T) {
	cases := []struct {
		name string
		opts Options
		want []string
	}{
		{
			name: "仅 listen",
			opts: Options{Listen: "127.0.0.1:17800"},
			want: []string{"run", "--listen", "127.0.0.1:17800"},
		},
		{
			name: "全参数",
			opts: Options{Listen: "127.0.0.1:17800", Gateway: "https://jvs-ai.cn", ConfigPath: "/tmp/c.yaml"},
			want: []string{"run", "--listen", "127.0.0.1:17800", "--gateway", "https://jvs-ai.cn", "--config", "/tmp/c.yaml"},
		},
		{
			name: "空参数",
			opts: Options{},
			want: []string{"run"},
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := BuildRunArgs(c.opts)
			if strings.Join(got, " ") != strings.Join(c.want, " ") {
				t.Errorf("BuildRunArgs = %v, 期望 %v", got, c.want)
			}
		})
	}
}

func TestNewReturnsPlatformService(t *testing.T) {
	svc := New()
	if svc == nil {
		t.Fatal("New() 返回 nil")
	}
	_, isUnsupported := svc.(*unsupportedService)
	switch runtime.GOOS {
	case "linux", "windows":
		if isUnsupported {
			t.Errorf("平台 %s 不应返回 unsupportedService", runtime.GOOS)
		}
	default:
		if !isUnsupported {
			t.Errorf("平台 %s 应返回 unsupportedService", runtime.GOOS)
		}
	}
}

func TestUnsupportedServiceErrors(t *testing.T) {
	s := &unsupportedService{goos: "plan9"}
	if _, err := s.Install(Options{}); err == nil {
		t.Error("Install 应返回错误")
	}
	if _, err := s.Status(); err == nil {
		t.Error("Status 应返回错误")
	}
	if _, err := s.Start(); err == nil {
		t.Error("Start 应返回错误")
	}
}
