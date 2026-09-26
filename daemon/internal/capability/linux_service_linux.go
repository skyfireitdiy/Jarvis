//go:build linux

package capability

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"time"
)

// linuxServiceTimeout 是单次 systemctl 调用的超时时间。
const linuxServiceTimeout = 10 * time.Second

// linuxServiceUnitPattern 是 systemd unit 名的合法字符集。
//
// 限制为字母、数字、下划线、点、@、连字符，用于防止调用方把
// 额外参数（如 `--now`、`; rm -rf /`）注入到 systemctl 命令行。
var linuxServiceUnitPattern = regexp.MustCompile(`^[A-Za-z0-9_.@-]+$`)

// linuxServiceProxyEnvVars 是需要透传给 systemctl 的代理相关环境变量。
//
// 与 internal/service/systemd_linux.go 中的 proxyEnvVars 保持一致：
// 在需要经代理访问外网的场景下，systemctl 自身不需要代理，但保持透传
// 可以避免用户环境差异带来的意外行为。
var linuxServiceProxyEnvVars = []string{
	"http_proxy", "HTTP_PROXY",
	"https_proxy", "HTTPS_PROXY",
	"no_proxy", "NO_PROXY",
	"ftp_proxy", "FTP_PROXY",
	"socks_proxy", "SOCKS_PROXY",
}

// registerLinuxService 注册 Linux systemd 用户服务能力。
//
// 守护进程本身以 systemd 用户服务方式运行（WantedBy=default.target），
// 因此这里统一使用 `systemctl --user`，不涉及系统级服务。
func registerLinuxService(reg *Registry) {
	_ = reg.Register(Capability{
		Name:        "linux.service.list",
		Description: "列出当前用户的 systemd 服务单元（systemctl --user list-units）。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"unit_type": map[string]any{
					"type":        "string",
					"description": "单元类型，默认 service；常见值：service、socket、timer、target。",
				},
				"all": map[string]any{
					"type":        "boolean",
					"description": "是否包含未激活的单元（--all），默认 false。",
				},
			},
		},
		Handler: handleLinuxServiceList,
	})

	_ = reg.Register(Capability{
		Name:        "linux.service.status",
		Description: "查询指定 systemd 用户服务单元的详细状态（systemctl --user show）。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"unit": map[string]any{
					"type":        "string",
					"description": "单元名，如 jarvis-daemon.service；允许字符：字母、数字、_ . @ -。",
				},
			},
			"required": []string{"unit"},
		},
		Handler: handleLinuxServiceStatus,
	})

	_ = reg.Register(Capability{
		Name:        "linux.service.start",
		Description: "启动指定 systemd 用户服务单元（systemctl --user start）。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"unit": map[string]any{
					"type":        "string",
					"description": "单元名，如 jarvis-daemon.service。",
				},
			},
			"required": []string{"unit"},
		},
		Handler: handleLinuxServiceAction("start"),
	})

	_ = reg.Register(Capability{
		Name:        "linux.service.stop",
		Description: "停止指定 systemd 用户服务单元（systemctl --user stop）。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"unit": map[string]any{
					"type":        "string",
					"description": "单元名，如 jarvis-daemon.service。",
				},
			},
			"required": []string{"unit"},
		},
		Handler: handleLinuxServiceAction("stop"),
	})

	_ = reg.Register(Capability{
		Name:        "linux.service.restart",
		Description: "重启指定 systemd 用户服务单元（systemctl --user restart）。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"unit": map[string]any{
					"type":        "string",
					"description": "单元名，如 jarvis-daemon.service。",
				},
			},
			"required": []string{"unit"},
		},
		Handler: handleLinuxServiceAction("restart"),
	})
}

// handleLinuxServiceList 是 linux.service.list 的实现。
func handleLinuxServiceList(params map[string]any) (any, error) {
	unitType, err := optionalString(params, "unit_type")
	if err != nil {
		return nil, err
	}
	if unitType == "" {
		unitType = "service"
	}
	if !linuxServiceUnitPattern.MatchString(unitType) || strings.HasPrefix(unitType, "-") {
		return nil, fmt.Errorf("参数 unit_type 含非法字符: %q，允许字符：字母、数字、_ . @ -（且不能以 - 开头）", unitType)
	}

	all, err := optionalBool(params, "all", false)
	if err != nil {
		return nil, err
	}

	args := []string{"--user", "list-units", "--type=" + unitType, "--no-pager", "--no-legend", "--plain"}
	if all {
		args = append(args, "--all")
	}

	out, err := runSystemctl(args...)
	if err != nil {
		return nil, err
	}

	units := parseSystemctlListUnits(out)
	return map[string]any{
		"units": units,
		"count": len(units),
	}, nil
}

// handleLinuxServiceStatus 是 linux.service.status 的实现。
func handleLinuxServiceStatus(params map[string]any) (any, error) {
	unit, err := resolveLinuxServiceUnit(params)
	if err != nil {
		return nil, err
	}

	out, err := runSystemctl("--user", "show", unit, "--no-pager")
	if err != nil {
		return nil, err
	}

	props := parseSystemctlShow(out)
	result := map[string]any{
		"unit":        unit,
		"load":        props["LoadState"],
		"active":      props["ActiveState"],
		"sub":         props["SubState"],
		"description": props["Description"],
		"main_pid":    props["MainPID"],
		"exec_start":  props["ExecStart"],
	}
	return result, nil
}

// handleLinuxServiceAction 生成 start / stop / restart 的实现。
func handleLinuxServiceAction(action string) func(map[string]any) (any, error) {
	return func(params map[string]any) (any, error) {
		unit, err := resolveLinuxServiceUnit(params)
		if err != nil {
			return nil, err
		}

		out, err := runSystemctl("--user", action, unit)
		if err != nil {
			return nil, err
		}

		return map[string]any{
			"unit":   unit,
			"action": action,
			"ok":     true,
			"output": strings.TrimSpace(out),
		}, nil
	}
}

// resolveLinuxServiceUnit 解析并校验 unit 参数。
func resolveLinuxServiceUnit(params map[string]any) (string, error) {
	unit, err := requiredString(params, "unit")
	if err != nil {
		return "", err
	}
	if err := validateLinuxServiceUnitName(unit); err != nil {
		return "", err
	}
	return unit, nil
}

// validateLinuxServiceUnitName 校验单元名合法性。
//
// 除了字符集白名单外，还必须拒绝以 "-" 开头的名字：
// 这类名字会被 systemctl 当作命令行选项（如 --now、--all），
// 从而绕过「单元名」语义变成参数注入。
func validateLinuxServiceUnitName(name string) error {
	if strings.HasPrefix(name, "-") {
		return fmt.Errorf("参数 unit 不能以 - 开头（会被解析为 systemctl 选项）: %q", name)
	}
	if !linuxServiceUnitPattern.MatchString(name) {
		return fmt.Errorf("参数 unit 含非法字符: %q，允许字符：字母、数字、_ . @ -", name)
	}
	return nil
}

// runSystemctl 执行 systemctl 命令并返回标准输出。
//
// 统一带上超时与代理环境变量透传；systemctl 不存在时给出明确错误。
func runSystemctl(args ...string) (string, error) {
	bin, err := exec.LookPath("systemctl")
	if err != nil {
		return "", fmt.Errorf("未找到 systemctl，当前系统可能未使用 systemd: %w", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), linuxServiceTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, bin, args...)
	cmd.Env = append(os.Environ(), collectLinuxServiceProxyEnv()...)

	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return "", fmt.Errorf("执行 systemctl %s 超时（%s）", strings.Join(args, " "), linuxServiceTimeout)
		}
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			stderr := strings.TrimSpace(string(exitErr.Stderr))
			if stderr != "" {
				return "", fmt.Errorf("执行 systemctl %s 失败: %s", strings.Join(args, " "), stderr)
			}
		}
		return "", fmt.Errorf("执行 systemctl %s 失败: %w", strings.Join(args, " "), err)
	}

	return string(out), nil
}

// collectLinuxServiceProxyEnv 收集当前环境中已设置的代理变量。
func collectLinuxServiceProxyEnv() []string {
	out := make([]string, 0, len(linuxServiceProxyEnvVars))
	for _, name := range linuxServiceProxyEnvVars {
		if v := os.Getenv(name); v != "" {
			out = append(out, name+"="+v)
		}
	}
	return out
}

// parseSystemctlListUnits 解析 `systemctl list-units` 的输出行。
//
// 每行形如：
//
//	jarvis-daemon.service loaded active running Jarvis Daemon
//
// 其中 description 可能包含空格，因此按前 4 个字段切分后剩余部分整体作为描述。
func parseSystemctlListUnits(out string) []map[string]any {
	units := make([]map[string]any, 0, 16)
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		// 跳过表头与统计行。
		if strings.HasPrefix(line, "UNIT") || strings.HasPrefix(line, "LOAD") ||
			strings.HasPrefix(line, "Legend:") || strings.HasPrefix(line, "0 loaded") {
			continue
		}

		fields := strings.Fields(line)
		if len(fields) < 4 {
			continue
		}

		entry := map[string]any{
			"unit":   fields[0],
			"load":   fields[1],
			"active": fields[2],
			"sub":    fields[3],
		}
		if len(fields) > 4 {
			entry["description"] = strings.Join(fields[4:], " ")
		} else {
			entry["description"] = ""
		}
		units = append(units, entry)
	}
	return units
}

// parseSystemctlShow 解析 `systemctl show` 的 key=value 输出。
func parseSystemctlShow(out string) map[string]string {
	props := make(map[string]string, 32)
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		idx := strings.IndexByte(line, '=')
		if idx <= 0 {
			continue
		}
		props[line[:idx]] = line[idx+1:]
	}
	return props
}
