//go:build linux

package capability

import (
	"os"
	"strings"
	"testing"
	"time"
)

// execLinuxScript 是测试辅助：通过注册表执行 linux.script.exec 并断言成功。
func execLinuxScript(t *testing.T, params map[string]any) map[string]any {
	t.Helper()
	r := NewRegistry()
	res := r.Execute("linux.script.exec", params)
	if !res.Success {
		t.Fatalf("执行失败: %s", res.Error)
	}
	data, ok := res.Data.(map[string]any)
	if !ok {
		t.Fatalf("返回类型应为 map[string]any，实际 %T", res.Data)
	}
	return data
}

// TestLinuxScriptRegistered 验证能力已注册且平台正确。
func TestLinuxScriptRegistered(t *testing.T) {
	r := NewRegistry()
	c, ok := r.Get("linux.script.exec")
	if !ok {
		t.Fatal("linux.script.exec 应当已注册")
	}
	if c.Platform != PlatformLinux {
		t.Fatalf("平台应为 linux，实际 %q", c.Platform)
	}
	if c.Description == "" {
		t.Fatal("Description 不应为空")
	}
	if len(c.Parameters) == 0 {
		t.Fatal("Parameters 不应为空")
	}
	// 应当出现在 Linux 平台列表中。
	found := false
	for _, cap := range r.ListForPlatform(PlatformLinux) {
		if cap.Name == "linux.script.exec" {
			found = true
		}
	}
	if !found {
		t.Fatal("linux.script.exec 应出现在 Linux 平台能力列表中")
	}
}

// TestLinuxScriptMissingParam 覆盖参数缺失与类型错误。
func TestLinuxScriptMissingParam(t *testing.T) {
	r := NewRegistry()

	cases := []struct {
		name   string
		params map[string]any
		want   string
	}{
		{"完全不带参数", nil, "缺少必填参数 script"},
		{"script 为 nil", map[string]any{"script": nil}, "缺少必填参数 script"},
		{"script 为空串", map[string]any{"script": ""}, "不能为空"},
		{"script 为空白", map[string]any{"script": "   "}, "不能为空"},
		{"script 类型错误", map[string]any{"script": 123}, "必须是字符串"},
		{"timeout_ms 类型错误", map[string]any{"script": "echo hi", "timeout_ms": "abc"}, "必须是整数"},
		{"timeout_ms 为 0", map[string]any{"script": "echo hi", "timeout_ms": 0}, "必须为正整数"},
		{"timeout_ms 为负", map[string]any{"script": "echo hi", "timeout_ms": -1}, "必须为正整数"},
		{"cwd 类型错误", map[string]any{"script": "echo hi", "cwd": 1}, "cwd 必须是字符串"},
		{"env 类型错误", map[string]any{"script": "echo hi", "env": "not-a-map"}, "env 必须是对象"},
		{"env 值类型错误", map[string]any{"script": "echo hi", "env": map[string]any{"A": 1}}, "env.A 必须是字符串"},
		{"stdin 类型错误", map[string]any{"script": "echo hi", "stdin": 1}, "stdin 必须是字符串"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			res := r.Execute("linux.script.exec", tc.params)
			if res.Success {
				t.Fatalf("应当失败，实际成功: %+v", res.Data)
			}
			if !strings.Contains(res.Error, tc.want) {
				t.Fatalf("错误信息应包含 %q，实际 %q", tc.want, res.Error)
			}
		})
	}
}

// TestLinuxScriptInterpreterWhitelist 覆盖解释器白名单校验。
func TestLinuxScriptInterpreterWhitelist(t *testing.T) {
	r := NewRegistry()

	// 非法解释器必须被拒绝。
	illegal := []string{
		"/bin/rm",
		"rm",
		"/usr/bin/python3",
		"/bin/sh -c",   // 带参数注入
		"sh; rm -rf /", // 命令拼接注入
		"../../bin/sh",
		"",
	}
	for _, interp := range illegal {
		if interp == "" {
			continue // 空串表示使用默认值，属于合法情况
		}
		res := r.Execute("linux.script.exec", map[string]any{
			"script":      "echo hi",
			"interpreter": interp,
		})
		if res.Success {
			t.Fatalf("非法解释器 %q 应当被拒绝", interp)
		}
		if !strings.Contains(res.Error, "不在白名单内") {
			t.Fatalf("非法解释器 %q 的错误信息应提示白名单，实际 %q", interp, res.Error)
		}
	}

	// 白名单内的解释器应当可用（用存在性检查过的 /bin/sh 与 /bin/bash）。
	for _, interp := range []string{"/bin/sh", "/bin/bash"} {
		res := r.Execute("linux.script.exec", map[string]any{
			"script":      "echo ok",
			"interpreter": interp,
		})
		if !res.Success {
			t.Fatalf("白名单解释器 %q 应当可用，实际错误: %s", interp, res.Error)
		}
	}

	// 不传 interpreter 时默认 /bin/sh。
	data := execLinuxScript(t, map[string]any{"script": "echo default-interp"})
	if got := strings.TrimSpace(data["stdout"].(string)); got != "default-interp" {
		t.Fatalf("默认解释器应执行成功，实际 stdout=%q", got)
	}
}

// TestLinuxScriptEcho 覆盖正常执行：stdout / exit_code / duration。
func TestLinuxScriptEcho(t *testing.T) {
	data := execLinuxScript(t, map[string]any{"script": "echo hello-jarvis"})

	if got := strings.TrimSpace(data["stdout"].(string)); got != "hello-jarvis" {
		t.Fatalf("stdout 期望 hello-jarvis，实际 %q", got)
	}
	if got := data["exit_code"].(int); got != 0 {
		t.Fatalf("exit_code 期望 0，实际 %d", got)
	}
	if data["timed_out"].(bool) {
		t.Fatal("不应当超时")
	}
	if got := data["duration_ms"].(int64); got < 0 {
		t.Fatalf("duration_ms 不应为负，实际 %d", got)
	}
	if got := data["stderr"].(string); got != "" {
		t.Fatalf("stderr 期望为空，实际 %q", got)
	}
}

// TestLinuxScriptStderrAndExitCode 覆盖非零退出码与 stderr 透传。
func TestLinuxScriptStderrAndExitCode(t *testing.T) {
	data := execLinuxScript(t, map[string]any{
		"script": "echo oops >&2; exit 3",
	})

	if got := data["exit_code"].(int); got != 3 {
		t.Fatalf("exit_code 期望 3，实际 %d", got)
	}
	if got := strings.TrimSpace(data["stderr"].(string)); got != "oops" {
		t.Fatalf("stderr 期望 oops，实际 %q", got)
	}
	if data["timed_out"].(bool) {
		t.Fatal("不应当超时")
	}
}

// TestLinuxScriptEnvAndCwd 覆盖 env 与 cwd 参数生效。
func TestLinuxScriptEnvAndCwd(t *testing.T) {
	dir := t.TempDir()

	data := execLinuxScript(t, map[string]any{
		"script": "echo $JARVIS_TEST_VAR; pwd",
		"cwd":    dir,
		"env":    map[string]string{"JARVIS_TEST_VAR": "env-works"},
	})

	lines := strings.Split(strings.TrimSpace(data["stdout"].(string)), "\n")
	if len(lines) != 2 {
		t.Fatalf("期望 2 行输出，实际 %q", data["stdout"])
	}
	if lines[0] != "env-works" {
		t.Fatalf("env 未生效，第一行期望 env-works，实际 %q", lines[0])
	}
	// t.TempDir 在 macOS 上可能是 /var 符号链接，Linux 下直接比较即可。
	if lines[1] != dir {
		t.Fatalf("cwd 未生效，期望 %q，实际 %q", dir, lines[1])
	}
}

// TestLinuxScriptStdin 覆盖 stdin 参数。
func TestLinuxScriptStdin(t *testing.T) {
	data := execLinuxScript(t, map[string]any{
		"script": "cat",
		"stdin":  "from-stdin",
	})
	if got := strings.TrimSpace(data["stdout"].(string)); got != "from-stdin" {
		t.Fatalf("stdin 未透传，stdout 期望 from-stdin，实际 %q", got)
	}
}

// TestLinuxScriptTimeout 覆盖超时：sleep 5 + timeout 500ms 应当超时且退出码非 0。
func TestLinuxScriptTimeout(t *testing.T) {
	start := time.Now()
	data := execLinuxScript(t, map[string]any{
		"script":     "sleep 5; echo should-not-print",
		"timeout_ms": 500,
	})
	elapsed := time.Since(start)

	if !data["timed_out"].(bool) {
		t.Fatal("应当标记超时")
	}
	if got := data["exit_code"].(int); got == 0 {
		t.Fatalf("超时的 exit_code 不应为 0，实际 %d", got)
	}
	if strings.Contains(data["stdout"].(string), "should-not-print") {
		t.Fatal("超时后不应输出后续内容")
	}
	// 必须在超时后及时返回，不能真的等满 5 秒。
	if elapsed > 4*time.Second {
		t.Fatalf("超时控制未生效，实际耗时 %v", elapsed)
	}
}

// TestLinuxScriptTimeoutKillsProcessGroup 验证超时会终止整个进程组（含子进程）。
func TestLinuxScriptTimeoutKillsProcessGroup(t *testing.T) {
	dir := t.TempDir()
	marker := dir + "/child-alive"

	// 父脚本后台起一个子进程写标记文件，然后自己长时间睡眠。
	// 若只杀父进程而不杀进程组，子进程会存活并写出标记文件。
	script := "sh -c 'sleep 2; touch " + marker + "' & sleep 30"

	data := execLinuxScript(t, map[string]any{
		"script":     script,
		"timeout_ms": 500,
	})
	if !data["timed_out"].(bool) {
		t.Fatal("应当超时")
	}

	// 等待超过子进程原定写标记的时间，确认它已被一并终止。
	time.Sleep(2500 * time.Millisecond)
	if _, err := os.Stat(marker); err == nil {
		t.Fatal("子进程未被终止：标记文件已生成，说明进程组未被清理")
	}
}

// TestLinuxScriptOutputTruncation 验证超长输出会被截断并置 truncated 标志。
func TestLinuxScriptOutputTruncation(t *testing.T) {
	// 生成约 2MB 输出，超过 1MB 上限。
	data := execLinuxScript(t, map[string]any{
		"script": "head -c 2097152 /dev/zero | tr '\\0' 'a'",
	})

	if !data["truncated"].(bool) {
		t.Fatal("超长输出应当置 truncated=true")
	}
	if got := len(data["stdout"].(string)); got != linuxScriptMaxOutputBytes {
		t.Fatalf("stdout 应被截断到 %d 字节，实际 %d", linuxScriptMaxOutputBytes, got)
	}
}

// TestLinuxScriptTimeoutUpperBound 验证 timeout_ms 上限校验。
func TestLinuxScriptTimeoutUpperBound(t *testing.T) {
	r := NewRegistry()
	res := r.Execute("linux.script.exec", map[string]any{
		"script":     "echo hi",
		"timeout_ms": linuxScriptMaxTimeoutMS + 1,
	})
	if res.Success {
		t.Fatal("超出上限的 timeout_ms 应当被拒绝")
	}
	if !strings.Contains(res.Error, "超出上限") {
		t.Fatalf("错误信息应提示超出上限，实际 %q", res.Error)
	}
}
