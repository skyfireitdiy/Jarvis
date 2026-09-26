//go:build linux

package capability

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"testing"
	"time"
)

// TestLinuxProcessRegistered 验证进程能力已注册且平台正确。
func TestLinuxProcessRegistered(t *testing.T) {
	r := NewRegistry()
	for _, name := range []string{"linux.process.list", "linux.process.kill"} {
		c, ok := r.Get(name)
		if !ok {
			t.Fatalf("%s 应当已注册", name)
		}
		if c.Platform != PlatformLinux {
			t.Fatalf("%s 平台应为 linux，实际 %q", name, c.Platform)
		}
		if c.Description == "" {
			t.Fatalf("%s 的 Description 不应为空", name)
		}
		if len(c.Parameters) == 0 {
			t.Fatalf("%s 的 Parameters 不应为空", name)
		}
	}
}

// TestLinuxProcessListReturnsSelf 验证进程列表至少包含当前测试进程。
func TestLinuxProcessListReturnsSelf(t *testing.T) {
	r := NewRegistry()
	res := r.Execute("linux.process.list", map[string]any{"limit": 5000})
	if !res.Success {
		t.Fatalf("执行失败: %s", res.Error)
	}
	data, ok := res.Data.(map[string]any)
	if !ok {
		t.Fatalf("返回类型应为 map[string]any，实际 %T", res.Data)
	}
	procs, ok := data["processes"].([]map[string]any)
	if !ok {
		t.Fatalf("processes 类型应为 []map[string]any，实际 %T", data["processes"])
	}
	if len(procs) == 0 {
		t.Fatal("进程列表不应为空")
	}

	self := os.Getpid()
	found := false
	for _, p := range procs {
		if p["pid"] == self {
			found = true
			// 自身进程的字段应当有值。
			if p["comm"] == "" {
				t.Error("自身进程的 comm 不应为空")
			}
			if p["cmdline"] == "" {
				t.Error("自身进程的 cmdline 不应为空")
			}
			if p["state"] == "" {
				t.Error("自身进程的 state 不应为空")
			}
			if p["ppid"] == 0 {
				t.Error("自身进程的 ppid 不应为 0")
			}
		}
	}
	if !found {
		t.Fatalf("进程列表中应包含当前进程 pid=%d", self)
	}
}

// TestLinuxProcessListFilter 验证过滤与 limit 行为。
func TestLinuxProcessListFilter(t *testing.T) {
	r := NewRegistry()

	// 用当前测试二进制名做过滤，应当能命中自身。
	self, err := os.Executable()
	if err != nil {
		t.Skipf("无法获取自身可执行文件路径: %v", err)
	}
	base := self[strings.LastIndex(self, "/")+1:]

	res := r.Execute("linux.process.list", map[string]any{"filter": base})
	if !res.Success {
		t.Fatalf("执行失败: %s", res.Error)
	}
	data := res.Data.(map[string]any)
	procs := data["processes"].([]map[string]any)
	if len(procs) == 0 {
		t.Fatalf("按 %q 过滤应当至少命中自身进程", base)
	}
	for _, p := range procs {
		comm := strings.ToLower(p["comm"].(string))
		cmdline := strings.ToLower(p["cmdline"].(string))
		if !strings.Contains(comm, strings.ToLower(base)) && !strings.Contains(cmdline, strings.ToLower(base)) {
			t.Errorf("过滤结果不应包含不匹配的进程: comm=%q cmdline=%q", comm, cmdline)
		}
	}

	// limit=1 时应当只返回 1 条并置 truncated。
	res = r.Execute("linux.process.list", map[string]any{"limit": 1})
	if !res.Success {
		t.Fatalf("执行失败: %s", res.Error)
	}
	data = res.Data.(map[string]any)
	procs = data["processes"].([]map[string]any)
	if len(procs) != 1 {
		t.Fatalf("limit=1 时应返回 1 条，实际 %d", len(procs))
	}
	if data["truncated"] != true {
		t.Error("limit=1 且系统进程多于 1 个时 truncated 应为 true")
	}
}

// TestLinuxProcessListParamErrors 覆盖参数校验错误路径。
func TestLinuxProcessListParamErrors(t *testing.T) {
	r := NewRegistry()
	cases := []struct {
		name   string
		params map[string]any
	}{
		{"limit 为 0", map[string]any{"limit": 0}},
		{"limit 为负", map[string]any{"limit": -1}},
		{"limit 超上限", map[string]any{"limit": 999999}},
		{"limit 类型错误", map[string]any{"limit": "abc"}},
		{"filter 类型错误", map[string]any{"filter": 123}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			res := r.Execute("linux.process.list", tc.params)
			if res.Success {
				t.Fatalf("应当失败，实际成功: %+v", res.Data)
			}
			if res.Error == "" {
				t.Fatal("错误信息不应为空")
			}
		})
	}
}

// TestLinuxProcessKillParamErrors 覆盖 kill 的危险参数拒绝逻辑。
func TestLinuxProcessKillParamErrors(t *testing.T) {
	r := NewRegistry()
	cases := []struct {
		name   string
		params map[string]any
	}{
		{"缺少 pid", map[string]any{}},
		{"pid 为 0", map[string]any{"pid": 0}},
		{"pid 为负", map[string]any{"pid": -1}},
		{"pid 类型错误", map[string]any{"pid": "abc"}},
		{"signal 非法", map[string]any{"pid": 1, "signal": "SIGFOO"}},
		{"signal 类型错误", map[string]any{"pid": 1, "signal": 9}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			res := r.Execute("linux.process.kill", tc.params)
			if res.Success {
				t.Fatalf("应当失败，实际成功: %+v", res.Data)
			}
			if res.Error == "" {
				t.Fatal("错误信息不应为空")
			}
		})
	}
}

// TestLinuxProcessKillRealChild 真机验证：向自己派生的子进程发送 SIGTERM。
func TestLinuxProcessKillRealChild(t *testing.T) {
	cmd := exec.Command("/bin/sleep", "30")
	if err := cmd.Start(); err != nil {
		t.Fatalf("启动子进程失败: %v", err)
	}
	pid := cmd.Process.Pid
	defer func() {
		// 兜底清理，避免测试失败时留下孤儿进程。
		_ = syscall.Kill(pid, syscall.SIGKILL)
		_, _ = cmd.Process.Wait()
	}()

	r := NewRegistry()
	res := r.Execute("linux.process.kill", map[string]any{"pid": pid, "signal": "TERM"})
	if !res.Success {
		t.Fatalf("发送 SIGTERM 失败: %s", res.Error)
	}
	data := res.Data.(map[string]any)
	if data["pid"] != pid {
		t.Errorf("返回 pid 应为 %d，实际 %v", pid, data["pid"])
	}
	if data["signal"] != "TERM" {
		t.Errorf("返回 signal 应为 TERM，实际 %v", data["signal"])
	}
	if data["killed"] != true {
		t.Errorf("killed 应为 true，实际 %v", data["killed"])
	}

	// 等待子进程真正退出。
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	select {
	case <-done:
		// 正常退出（被信号终止）。
	case <-time.After(5 * time.Second):
		t.Fatal("子进程在收到 SIGTERM 后 5 秒内未退出")
	}
}

// TestLinuxProcessKillNonexistent 验证对不存在的进程返回明确错误。
func TestLinuxProcessKillNonexistent(t *testing.T) {
	r := NewRegistry()
	// 找一个几乎不可能存在的 PID：先起一个子进程拿到 PID，杀掉后再用该 PID。
	cmd := exec.Command("/bin/sleep", "1")
	if err := cmd.Start(); err != nil {
		t.Fatalf("启动子进程失败: %v", err)
	}
	pid := cmd.Process.Pid
	_ = cmd.Process.Kill()
	_, _ = cmd.Process.Wait()

	// 等待进程彻底回收。
	time.Sleep(200 * time.Millisecond)

	res := r.Execute("linux.process.kill", map[string]any{"pid": pid, "signal": "TERM"})
	if res.Success {
		t.Skipf("PID %d 已被复用，跳过（不视为失败）", pid)
	}
	if !strings.Contains(res.Error, fmt.Sprintf("%d", pid)) {
		t.Errorf("错误信息应包含 pid，实际: %s", res.Error)
	}
}

// TestParseLinuxProcStat 覆盖 /proc/<pid>/stat 的解析，含 comm 带空格与括号的边界。
func TestParseLinuxProcStat(t *testing.T) {
	cases := []struct {
		name      string
		raw       string
		wantComm  string
		wantPPID  int
		wantState string
		wantErr   bool
	}{
		{
			name:      "普通进程",
			raw:       "1234 (bash) S 1000 1234 1234 0 -1 4194304 100 0 0 0 1 2 0 0 20 0 1 0 5000 1000000 200",
			wantComm:  "bash",
			wantPPID:  1000,
			wantState: "S",
		},
		{
			name:      "comm 含空格与括号",
			raw:       "42 (my (weird) proc) R 1 42 42 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 7000 0 5",
			wantComm:  "my (weird) proc",
			wantPPID:  1,
			wantState: "R",
		},
		{
			name:    "字段不足",
			raw:     "1 (x) S 0",
			wantErr: true,
		},
		{
			name:    "缺少括号",
			raw:     "garbage",
			wantErr: true,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			info, err := parseLinuxProcStat(tc.raw)
			if tc.wantErr {
				if err == nil {
					t.Fatal("应当返回错误")
				}
				return
			}
			if err != nil {
				t.Fatalf("不应返回错误: %v", err)
			}
			if info.comm != tc.wantComm {
				t.Errorf("comm 应为 %q，实际 %q", tc.wantComm, info.comm)
			}
			if info.ppid != tc.wantPPID {
				t.Errorf("ppid 应为 %d，实际 %d", tc.wantPPID, info.ppid)
			}
			if info.state != tc.wantState {
				t.Errorf("state 应为 %q，实际 %q", tc.wantState, info.state)
			}
		})
	}
}
