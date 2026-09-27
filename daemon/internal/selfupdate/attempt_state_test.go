package selfupdate

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

// withTempHome 把 HOME 指向临时目录，返回清理函数。
//
// 尝试状态文件路径由 os.UserHomeDir() 决定，测试必须隔离 HOME，
// 否则会污染开发者本机的 ~/.jarvis/daemon/update-attempt.json。
func withTempHome(t *testing.T) {
	t.Helper()
	old := os.Getenv("HOME")
	dir := t.TempDir()
	if err := os.Setenv("HOME", dir); err != nil {
		t.Fatalf("设置 HOME 失败: %v", err)
	}
	t.Cleanup(func() { _ = os.Setenv("HOME", old) })
}

func TestNormalizeVersion(t *testing.T) {
	cases := []struct {
		in, want string
	}{
		{"v5.0.5", "5.0.5"},
		{"V6.0.0", "6.0.0"},
		{"6.0.0", "6.0.0"},
		{"  v1.2.3  ", "1.2.3"},
		{"", ""},
		{"vv1.0.0", "1.0.0"},
	}
	for _, c := range cases {
		if got := NormalizeVersion(c.in); got != c.want {
			t.Errorf("NormalizeVersion(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestSameVersion(t *testing.T) {
	if !SameVersion("v6.0.0", "6.0.0") {
		t.Error("v6.0.0 与 6.0.0 应视为相同版本")
	}
	if !SameVersion(" 6.0.0 ", "V6.0.0") {
		t.Error("空白与大小写差异应视为相同版本")
	}
	if SameVersion("6.0.0", "6.0.1") {
		t.Error("6.0.0 与 6.0.1 不应视为相同版本")
	}
}

func TestBackoffFor(t *testing.T) {
	cases := []struct {
		attempts int
		want     time.Duration
	}{
		{0, 0},
		{-1, 0},
		{1, time.Minute},
		{2, 5 * time.Minute},
		{3, 30 * time.Minute},
		{4, 30 * time.Minute},
		{100, 30 * time.Minute},
	}
	for _, c := range cases {
		if got := BackoffFor(c.attempts); got != c.want {
			t.Errorf("BackoffFor(%d) = %v, want %v", c.attempts, got, c.want)
		}
	}
	if MaxBackoff() != 30*time.Minute {
		t.Errorf("MaxBackoff() = %v, want 30m", MaxBackoff())
	}
}

func TestAttemptStateSaveLoadClear(t *testing.T) {
	withTempHome(t)

	// 初始不存在。
	if _, ok := LoadAttemptState(); ok {
		t.Fatal("初始不应存在尝试状态")
	}

	want := AttemptState{
		TargetVersion:   "v6.0.0",
		Attempts:        2,
		LastAttemptUnix: 1700000000,
		LastError:       "下载失败",
		InProgress:      true,
	}
	if err := SaveAttemptState(want); err != nil {
		t.Fatalf("保存尝试状态失败: %v", err)
	}

	path, err := AttemptStatePath()
	if err != nil {
		t.Fatalf("获取路径失败: %v", err)
	}
	if filepath.Base(path) != "update-attempt.json" {
		t.Errorf("文件名 = %s, want update-attempt.json", filepath.Base(path))
	}
	// 权限应为 0600。
	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("stat 失败: %v", err)
	}
	if perm := info.Mode().Perm(); perm != 0o600 {
		t.Errorf("权限 = %o, want 600", perm)
	}

	got, ok := LoadAttemptState()
	if !ok {
		t.Fatal("应能读到尝试状态")
	}
	if got != want {
		t.Errorf("读回 = %+v, want %+v", got, want)
	}

	// 清除后应读不到，且重复清除幂等。
	if err := ClearAttemptState(); err != nil {
		t.Fatalf("清除失败: %v", err)
	}
	if _, ok := LoadAttemptState(); ok {
		t.Error("清除后不应读到尝试状态")
	}
	if err := ClearAttemptState(); err != nil {
		t.Errorf("重复清除应幂等，实际 %v", err)
	}
}

func TestLoadAttemptStateCorrupt(t *testing.T) {
	withTempHome(t)
	path, err := AttemptStatePath()
	if err != nil {
		t.Fatalf("获取路径失败: %v", err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		t.Fatalf("创建目录失败: %v", err)
	}
	if err := os.WriteFile(path, []byte("{不是合法 json"), 0o600); err != nil {
		t.Fatalf("写入损坏文件失败: %v", err)
	}
	if _, ok := LoadAttemptState(); ok {
		t.Error("损坏文件不应被解析成功")
	}
}

func TestShouldSkipUpdate(t *testing.T) {
	const now = int64(1700000000)

	t.Run("无状态不跳过", func(t *testing.T) {
		skip, _ := ShouldSkipUpdate(AttemptState{}, "v5.0.5", "6.0.0", now)
		if skip {
			t.Error("无历史状态时不应跳过")
		}
	})

	t.Run("同版本失败在退避窗口内跳过", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        1,
			LastAttemptUnix: now - 10, // 退避 1min，仅过 10s
			LastError:       "下载失败",
		}
		skip, reason := ShouldSkipUpdate(state, "v5.0.5", "6.0.0", now)
		if !skip {
			t.Error("退避窗口内应跳过")
		}
		if reason == "" {
			t.Error("跳过时应给出原因")
		}
	})

	t.Run("同版本失败退避窗口已过则重试", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        1,
			LastAttemptUnix: now - 61, // 超过 1min
			LastError:       "下载失败",
		}
		skip, _ := ShouldSkipUpdate(state, "v5.0.5", "6.0.0", now)
		if skip {
			t.Error("退避窗口已过应允许重试")
		}
	})

	t.Run("多次失败退避时间递增", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        2,
			LastAttemptUnix: now - 61, // 第 2 次退避 5min，仅过 61s
			LastError:       "下载失败",
		}
		skip, _ := ShouldSkipUpdate(state, "v5.0.5", "6.0.0", now)
		if !skip {
			t.Error("第 2 次失败退避 5min，61s 后仍应跳过")
		}
	})

	t.Run("目标版本变化则允许重试", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        3,
			LastAttemptUnix: now - 1,
			LastError:       "下载失败",
		}
		skip, _ := ShouldSkipUpdate(state, "v5.0.5", "6.0.1", now)
		if skip {
			t.Error("目标版本变化应允许尝试")
		}
	})

	t.Run("InProgress 且版本未变则熔断", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        1,
			LastAttemptUnix: now - 99999,
			InProgress:      true,
		}
		skip, reason := ShouldSkipUpdate(state, "v5.0.5", "6.0.0", now)
		if !skip {
			t.Error("重启循环应熔断")
		}
		if reason == "" {
			t.Error("熔断时应给出原因")
		}
	})

	t.Run("熔断后网关发新版则恢复", func(t *testing.T) {
		state := AttemptState{
			TargetVersion: "6.0.0",
			InProgress:    true,
		}
		skip, _ := ShouldSkipUpdate(state, "v5.0.5", "6.0.1", now)
		if skip {
			t.Error("网关发新版后应恢复尝试")
		}
	})

	t.Run("熔断判定不受版本 v 前缀影响", func(t *testing.T) {
		state := AttemptState{TargetVersion: "v6.0.0", InProgress: true}
		skip, _ := ShouldSkipUpdate(state, "v5.0.5", "6.0.0", now)
		if !skip {
			t.Error("v6.0.0 与 6.0.0 应视为同一目标，仍熔断")
		}
	})
}

func TestRetryAfter(t *testing.T) {
	const now = int64(1700000000)

	t.Run("无状态无需等待", func(t *testing.T) {
		if got := RetryAfter(AttemptState{}, "v5.0.5", "6.0.0", now); got != 0 {
			t.Errorf("RetryAfter = %v, want 0", got)
		}
	})

	t.Run("目标版本变化无需等待", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        3,
			LastAttemptUnix: now - 1,
		}
		if got := RetryAfter(state, "v5.0.5", "6.0.1", now); got != 0 {
			t.Errorf("目标变化时 RetryAfter = %v, want 0", got)
		}
	})

	t.Run("熔断态返回 0 表示不应重试", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        1,
			LastAttemptUnix: now - 1,
			InProgress:      true,
		}
		if got := RetryAfter(state, "v5.0.5", "6.0.0", now); got != 0 {
			t.Errorf("熔断态 RetryAfter = %v, want 0", got)
		}
	})

	t.Run("退避窗口内返回剩余时长", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        1,
			LastAttemptUnix: now - 10, // 退避 1min，已过 10s
		}
		want := 50 * time.Second
		if got := RetryAfter(state, "v5.0.5", "6.0.0", now); got != want {
			t.Errorf("RetryAfter = %v, want %v", got, want)
		}
	})

	t.Run("退避窗口已过返回 0", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        1,
			LastAttemptUnix: now - 61,
		}
		if got := RetryAfter(state, "v5.0.5", "6.0.0", now); got != 0 {
			t.Errorf("退避已过 RetryAfter = %v, want 0", got)
		}
	})

	t.Run("第 2 次失败按 5min 档计算", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        2,
			LastAttemptUnix: now - 61,
		}
		want := 5*time.Minute - 61*time.Second
		if got := RetryAfter(state, "v5.0.5", "6.0.0", now); got != want {
			t.Errorf("RetryAfter = %v, want %v", got, want)
		}
	})

	t.Run("超出阶梯按 30min 封顶", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "6.0.0",
			Attempts:        100,
			LastAttemptUnix: now - 10,
		}
		want := 30*time.Minute - 10*time.Second
		if got := RetryAfter(state, "v5.0.5", "6.0.0", now); got != want {
			t.Errorf("RetryAfter = %v, want %v", got, want)
		}
	})

	t.Run("版本 v 前缀不影响判定", func(t *testing.T) {
		state := AttemptState{
			TargetVersion:   "v6.0.0",
			Attempts:        1,
			LastAttemptUnix: now - 10,
		}
		if got := RetryAfter(state, "v5.0.5", "6.0.0", now); got != 50*time.Second {
			t.Errorf("RetryAfter = %v, want 50s", got)
		}
	})
}
