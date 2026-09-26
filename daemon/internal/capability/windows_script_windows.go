//go:build windows

package capability

// 本文件实现 Windows 平台的脚本执行能力（windows.script.exec）。
//
// 设计对照 Linux 侧 linux_script_linux.go，保持参数与返回结构一致：
//   - 入参：script（必填）、interpreter、cwd、env、timeout_ms、stdin；
//   - 返回：exit_code、stdout、stderr、timed_out、duration_ms、truncated。
//
// 与 Linux 的差异：
//   - 解释器白名单是 Windows 侧的 powershell / pwsh / cmd；
//   - 脚本经 -EncodedCommand（base64 UTF-16LE）传给 PowerShell，避免中文在
//     命令行参数上被按 ANSI 代码页损坏（与 windows_clipboard_windows.go 同因同解）；
//   - 输出编码统一为 UTF-8（见 windows_encoding.go 的 windowsPowerShellPreamble）。
//
// 注意：本机开发环境为 Linux，无 Windows 运行环境，因此本文件只能保证
// 「在 GOOS=windows 下编译通过」，成功路径未做端到端验证。

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

// Windows 脚本执行能力的默认与上限约束（与 Linux 侧保持同一量级）。
const (
	// windowsScriptDefaultTimeoutMS 是未指定 timeout_ms 时的默认超时（毫秒）。
	windowsScriptDefaultTimeoutMS = 30000
	// windowsScriptMaxTimeoutMS 是 timeout_ms 允许的最大值（毫秒），防止调用方传入超大值导致挂起。
	windowsScriptMaxTimeoutMS = 600000
	// windowsScriptMaxOutputBytes 是 stdout / stderr 各自保留的最大字节数。
	// 超出部分会被截断并置 truncated 标志，避免输出撑爆内存。
	windowsScriptMaxOutputBytes = 1 << 20 // 1 MiB
)

// windowsScriptInterpreterWhitelist 是允许的脚本解释器白名单。
//
// 与 Linux 侧同理：用白名单而非直接执行调用方传入的字符串，避免通过 interpreter
// 参数注入任意可执行文件（等价于任意命令执行）。白名单内的取值都是固定字面量。
var windowsScriptInterpreterWhitelist = []string{
	"powershell",
	"powershell.exe",
	"pwsh",
	"pwsh.exe",
	"cmd",
	"cmd.exe",
}

// registerWindowsScript 注册 Windows 脚本执行能力。
func registerWindowsScript(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.script.exec",
		Description: "在 Windows 上执行一段脚本内容，返回退出码、标准输出与标准错误。" +
			"脚本内容交给指定的解释器执行；解释器必须在白名单内（powershell、pwsh、cmd）。" +
			"PowerShell 脚本经 -EncodedCommand 传递，中文不会损坏；输出统一为 UTF-8。" +
			"执行受超时保护，超时会终止整个进程树。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"script": map[string]any{
					"type":        "string",
					"description": "要执行的脚本内容（交给解释器，而不是作为 shell 命令行拼接）。",
				},
				"interpreter": map[string]any{
					"type":        "string",
					"description": "解释器，默认 powershell；允许 powershell、powershell.exe、pwsh、pwsh.exe、cmd、cmd.exe。",
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
		Handler: handleWindowsScriptExec,
	})
}

// handleWindowsScriptExec 是 windows.script.exec 的实现。
func handleWindowsScriptExec(params map[string]any) (any, error) {
	script, err := requiredString(params, "script")
	if err != nil {
		return nil, err
	}

	interpreter, err := resolveWindowsScriptInterpreter(params)
	if err != nil {
		return nil, err
	}

	timeoutMS, err := optionalInt(params, "timeout_ms", windowsScriptDefaultTimeoutMS)
	if err != nil {
		return nil, err
	}
	if timeoutMS <= 0 {
		return nil, fmt.Errorf("参数 timeout_ms 必须为正整数，实际 %d", timeoutMS)
	}
	if timeoutMS > windowsScriptMaxTimeoutMS {
		return nil, fmt.Errorf("参数 timeout_ms 超出上限 %d 毫秒，实际 %d", windowsScriptMaxTimeoutMS, timeoutMS)
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

	args, cleanup, err := buildWindowsScriptCommand(interpreter, script)
	if err != nil {
		return nil, err
	}
	defer cleanup()

	cmd := exec.CommandContext(ctx, interpreter, args...)
	if stdin != "" {
		cmd.Stdin = strings.NewReader(stdin)
	}
	if cwd != "" {
		cmd.Dir = cwd
	}
	if len(env) > 0 {
		cmd.Env = append(cmd.Environ(), buildWindowsEnvPairs(env)...)
	}

	// 超时后强制结束进程树：Windows 上没有进程组信号，用 taskkill /T /F 兜底，
	// 避免 PowerShell 拉起的子进程残留。若 taskkill 不可用则退回 Kill 单进程。
	cmd.Cancel = func() error {
		if cmd.Process == nil {
			return nil
		}
		if err := exec.Command("taskkill", "/T", "/F", "/PID",
			fmt.Sprintf("%d", cmd.Process.Pid)).Run(); err != nil {
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

	stdoutStr, stdoutTruncated := truncateOutput(stdout.Bytes(), windowsScriptMaxOutputBytes)
	stderrStr, stderrTruncated := truncateOutput(stderr.Bytes(), windowsScriptMaxOutputBytes)

	// PowerShell 在 stderr 非终端时会把错误流序列化成 CLIXML，这里还原为可读文本
	// （见 windows_clixml.go）。非 PowerShell 解释器（cmd）的 stderr 是纯文本，
	// decodePowerShellStderr 会原样返回，不受影响。
	stderrStr = decodePowerShellStderr(stderrStr)

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

// buildWindowsScriptCommand 根据解释器构造命令行参数，并返回清理函数。
//
// PowerShell 走 -EncodedCommand（base64 UTF-16LE），彻底绕开命令行参数的
// ANSI 代码页问题；脚本前面拼 windowsPowerShellPreamble 把输出编码设为 UTF-8。
// cmd 走临时 .cmd 文件（避免命令行长度与转义问题）。
func buildWindowsScriptCommand(interpreter, script string) ([]string, func(), error) {
	base := strings.ToLower(interpreter)
	base = strings.TrimSuffix(base, ".exe")

	switch base {
	case "powershell", "pwsh":
		fullScript := windowsPowerShellPreamble + "\n" + script
		args := []string{
			"-NoProfile",
			"-NonInteractive",
			"-ExecutionPolicy", "Bypass",
			"-EncodedCommand", encodePowerShellCommand(fullScript),
		}
		return args, func() {}, nil
	case "cmd":
		// cmd 无法从命令行安全接收多行脚本，写入临时 .cmd 文件后执行。
		f, err := os.CreateTemp("", "jarvis-script-*.cmd")
		if err != nil {
			return nil, nil, fmt.Errorf("创建脚本临时文件失败: %w", err)
		}
		path := f.Name()
		if _, err := f.WriteString(script); err != nil {
			f.Close()
			os.Remove(path)
			return nil, nil, fmt.Errorf("写入脚本临时文件失败: %w", err)
		}
		if err := f.Close(); err != nil {
			os.Remove(path)
			return nil, nil, fmt.Errorf("关闭脚本临时文件失败: %w", err)
		}
		cleanup := func() { os.Remove(path) }
		// /C 执行后退出；用 & 调用脚本文件路径（路径由 os.CreateTemp 生成，不含用户输入）。
		return []string{"/C", path}, cleanup, nil
	default:
		return nil, nil, fmt.Errorf("不支持的脚本解释器: %q", interpreter)
	}
}

// resolveWindowsScriptInterpreter 解析并校验 interpreter 参数。
func resolveWindowsScriptInterpreter(params map[string]any) (string, error) {
	raw, err := optionalString(params, "interpreter")
	if err != nil {
		return "", err
	}
	if raw == "" {
		return "powershell", nil
	}
	for _, allowed := range windowsScriptInterpreterWhitelist {
		if strings.EqualFold(raw, allowed) {
			return allowed, nil
		}
	}
	return "", fmt.Errorf("参数 interpreter 不在白名单内: %q，允许值: %s",
		raw, strings.Join(windowsScriptInterpreterWhitelist, "、"))
}

// buildWindowsEnvPairs 把环境变量 map 转为 "K=V" 切片，键为空时跳过。
//
// 与 Linux 侧 buildEnvPairs 逻辑一致；因后者带 //go:build linux 标签，
// 在 Windows 构建中不可用，故此处单独实现。
func buildWindowsEnvPairs(env map[string]string) []string {
	out := make([]string, 0, len(env))
	for k, v := range env {
		if k == "" {
			continue
		}
		out = append(out, k+"="+v)
	}
	return out
}
