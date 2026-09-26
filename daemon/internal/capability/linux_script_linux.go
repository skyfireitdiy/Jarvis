//go:build linux

package capability

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"time"
)

// 脚本执行能力的默认与上限约束。
const (
	// linuxScriptDefaultTimeoutMS 是未指定 timeout_ms 时的默认超时（毫秒）。
	linuxScriptDefaultTimeoutMS = 30000
	// linuxScriptMaxTimeoutMS 是 timeout_ms 允许的最大值（毫秒），防止调用方传入超大值导致挂起。
	linuxScriptMaxTimeoutMS = 600000
	// linuxScriptMaxOutputBytes 是 stdout / stderr 各自保留的最大字节数。
	// 超出部分会被截断并置 truncated 标志，避免输出撑爆内存。
	linuxScriptMaxOutputBytes = 1 << 20 // 1 MiB
)

// linuxScriptInterpreterWhitelist 是允许的脚本解释器白名单。
//
// 之所以用白名单而不是直接执行调用方传入的字符串，是为了避免调用方通过
// interpreter 参数注入任意可执行文件（等价于任意命令执行）。
// 白名单内的取值都是固定字面量，不会被 shell 解析。
var linuxScriptInterpreterWhitelist = []string{
	"/bin/sh",
	"/bin/bash",
	"/usr/bin/sh",
	"/usr/bin/bash",
	"sh",
	"bash",
	"pwsh",
	"powershell",
}

// registerLinuxScript 注册 Linux 脚本执行能力。
func registerLinuxScript(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "linux.script.exec",
		Description: "在 Linux 上执行一段脚本内容，返回退出码、标准输出与标准错误。" +
			"脚本内容交给指定的解释器执行；解释器必须在白名单内（/bin/sh、/bin/bash、sh、bash、pwsh、powershell）。" +
			"执行受超时保护，超时会终止整个进程组。",
		Platform: PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"script": map[string]any{
					"type":        "string",
					"description": "要执行的脚本内容（交给解释器，而不是作为 shell 命令行拼接）。",
				},
				"interpreter": map[string]any{
					"type":        "string",
					"description": "解释器，默认 /bin/sh；允许 /bin/sh、/bin/bash、/usr/bin/sh、/usr/bin/bash、sh、bash、pwsh、powershell。",
				},
				"cwd": map[string]any{
					"type":        "string",
					"description": "工作目录，可选；为空时继承守护进程当前目录。",
				},
				"env": map[string]any{
					"type":        "object",
					"description": "附加环境变量（键值均为字符串），会叠加在守护进程环境之上。",
				},
				"timeout_ms": map[string]any{
					"type":        "integer",
					"description": "超时毫秒数，默认 30000，最大 600000。",
				},
				"stdin": map[string]any{
					"type":        "string",
					"description": "写入标准输入的内容，可选。",
				},
			},
			"required": []string{"script"},
		},
		Handler: handleLinuxScriptExec,
	})
}

// handleLinuxScriptExec 是 linux.script.exec 的实现。
func handleLinuxScriptExec(params map[string]any) (any, error) {
	script, err := requiredString(params, "script")
	if err != nil {
		return nil, err
	}

	interpreter, err := resolveLinuxScriptInterpreter(params)
	if err != nil {
		return nil, err
	}

	timeoutMS, err := optionalInt(params, "timeout_ms", linuxScriptDefaultTimeoutMS)
	if err != nil {
		return nil, err
	}
	if timeoutMS <= 0 {
		return nil, fmt.Errorf("参数 timeout_ms 必须为正整数，实际 %d", timeoutMS)
	}
	if timeoutMS > linuxScriptMaxTimeoutMS {
		return nil, fmt.Errorf("参数 timeout_ms 超出上限 %d 毫秒，实际 %d", linuxScriptMaxTimeoutMS, timeoutMS)
	}

	cwd, err := optionalString(params, "cwd")
	if err != nil {
		return nil, err
	}

	env, err := optionalStringMap(params, "env")
	if err != nil {
		return nil, err
	}

	stdin, err := optionalString(params, "stdin")
	if err != nil {
		return nil, err
	}

	timeout := time.Duration(timeoutMS) * time.Millisecond
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	// 脚本写入临时文件后作为解释器的位置参数执行，而不是通过 stdin 传入。
	// 这样做有两个好处：
	//  1. stdin 可以留给调用方通过 stdin 参数注入数据；
	//  2. 脚本内容不经过命令行拼接，避免参数注入。
	scriptFile, err := os.CreateTemp("", "jarvis-script-*.sh")
	if err != nil {
		return nil, fmt.Errorf("创建脚本临时文件失败: %w", err)
	}
	scriptPath := scriptFile.Name()
	defer os.Remove(scriptPath)

	if _, err := scriptFile.WriteString(script); err != nil {
		scriptFile.Close()
		return nil, fmt.Errorf("写入脚本临时文件失败: %w", err)
	}
	if err := scriptFile.Close(); err != nil {
		return nil, fmt.Errorf("关闭脚本临时文件失败: %w", err)
	}

	cmd := exec.CommandContext(ctx, interpreter, scriptPath)
	if stdin != "" {
		cmd.Stdin = strings.NewReader(stdin)
	}
	if cwd != "" {
		cmd.Dir = cwd
	}
	if len(env) > 0 {
		cmd.Env = append(cmd.Environ(), buildEnvPairs(env)...)
	}

	// 独立进程组：超时时可以连子进程一起终止，避免留下孤儿进程。
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	// 超时后先发 SIGKILL 兜底，再等待进程退出，防止 Wait 永久阻塞。
	cmd.Cancel = func() error {
		if cmd.Process == nil {
			return nil
		}
		// 负号表示向整个进程组发送信号。
		if err := syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL); err != nil {
			return cmd.Process.Kill()
		}
		return nil
	}
	cmd.WaitDelay = 2 * time.Second

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	start := time.Now()
	runErr := cmd.Run()
	duration := time.Since(start)

	stdoutStr, stdoutTruncated := truncateOutput(stdout.Bytes(), linuxScriptMaxOutputBytes)
	stderrStr, stderrTruncated := truncateOutput(stderr.Bytes(), linuxScriptMaxOutputBytes)

	timedOut := errors.Is(ctx.Err(), context.DeadlineExceeded)

	exitCode := 0
	if runErr != nil {
		var exitErr *exec.ExitError
		if errors.As(runErr, &exitErr) {
			exitCode = exitErr.ExitCode()
		} else if timedOut {
			// 超时被强杀时进程可能来不及汇报退出码，用 -1 表示异常终止。
			exitCode = -1
		} else {
			return nil, fmt.Errorf("执行脚本失败: %w", runErr)
		}
	}

	return map[string]any{
		"exit_code":   exitCode,
		"stdout":      stdoutStr,
		"stderr":      stderrStr,
		"timed_out":   timedOut,
		"duration_ms": duration.Milliseconds(),
		"truncated":   stdoutTruncated || stderrTruncated,
	}, nil
}

// resolveLinuxScriptInterpreter 解析并校验 interpreter 参数。
func resolveLinuxScriptInterpreter(params map[string]any) (string, error) {
	raw, err := optionalString(params, "interpreter")
	if err != nil {
		return "", err
	}
	if raw == "" {
		return "/bin/sh", nil
	}
	for _, allowed := range linuxScriptInterpreterWhitelist {
		if raw == allowed {
			return raw, nil
		}
	}
	return "", fmt.Errorf("参数 interpreter 不在白名单内: %q，允许值: %s",
		raw, strings.Join(linuxScriptInterpreterWhitelist, "、"))
}

// buildEnvPairs 把环境变量 map 转为 "K=V" 切片，键为空时跳过。
func buildEnvPairs(env map[string]string) []string {
	out := make([]string, 0, len(env))
	for k, v := range env {
		if k == "" {
			continue
		}
		out = append(out, k+"="+v)
	}
	return out
}

// truncateOutput 按最大字节数截断输出，返回内容与是否发生截断。
func truncateOutput(b []byte, max int) (string, bool) {
	if len(b) <= max {
		return string(b), false
	}
	return string(b[:max]), true
}

// requiredString 读取必填字符串参数。
func requiredString(params map[string]any, key string) (string, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return "", fmt.Errorf("缺少必填参数 %s", key)
	}
	s, ok := v.(string)
	if !ok {
		return "", fmt.Errorf("参数 %s 必须是字符串，实际 %T", key, v)
	}
	if strings.TrimSpace(s) == "" {
		return "", fmt.Errorf("参数 %s 不能为空", key)
	}
	return s, nil
}

// optionalString 读取可选字符串参数；缺失或为 nil 时返回空串。
func optionalString(params map[string]any, key string) (string, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return "", nil
	}
	s, ok := v.(string)
	if !ok {
		return "", fmt.Errorf("参数 %s 必须是字符串，实际 %T", key, v)
	}
	return s, nil
}

// optionalInt 读取可选整数参数；缺失或为 nil 时返回默认值。
//
// 兼容 JSON 解码后的 float64（网关传来的数字可能是 float64）。
func optionalInt(params map[string]any, key string, def int) (int, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return def, nil
	}
	switch n := v.(type) {
	case int:
		return n, nil
	case int64:
		return int(n), nil
	case float64:
		if n != float64(int(n)) {
			return 0, fmt.Errorf("参数 %s 必须是整数，实际 %v", key, n)
		}
		return int(n), nil
	default:
		return 0, fmt.Errorf("参数 %s 必须是整数，实际 %T", key, v)
	}
}

// optionalStringMap 读取可选字符串 map 参数。
func optionalStringMap(params map[string]any, key string) (map[string]string, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return nil, nil
	}
	switch m := v.(type) {
	case map[string]string:
		return m, nil
	case map[string]any:
		out := make(map[string]string, len(m))
		for k, raw := range m {
			s, ok := raw.(string)
			if !ok {
				return nil, fmt.Errorf("参数 %s.%s 必须是字符串，实际 %T", key, k, raw)
			}
			out[k] = s
		}
		return out, nil
	default:
		return nil, fmt.Errorf("参数 %s 必须是对象，实际 %T", key, v)
	}
}
