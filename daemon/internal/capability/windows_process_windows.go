//go:build windows

package capability

import (
	"context"
	"fmt"
	"os/exec"
	"sort"
	"strconv"
	"strings"
	"time"
)

// windowsProcessDefaultLimit 是 windows.process.list 未指定 limit 时返回的最大进程数。
const windowsProcessDefaultLimit = 200

// windowsProcessMaxLimit 是 limit 允许的最大值，防止一次性返回过多数据。
const windowsProcessMaxLimit = 5000

// windowsProcessTimeout 是执行 tasklist / taskkill 的超时时间。
const windowsProcessTimeout = 20 * time.Second

// registerWindowsProcess 注册 Windows 进程管理能力。
func registerWindowsProcess(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.process.list",
		Description: "列出 Windows 当前运行进程，可按进程名或 PID 过滤。" +
			"数据来自 tasklist 命令；无法获取的进程会被跳过。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"filter": map[string]any{
					"type":        "string",
					"description": "按进程名或 PID 子串过滤，大小写不敏感；为空时返回全部进程。",
				},
				"limit": map[string]any{
					"type":        "integer",
					"description": "最多返回的进程数，默认 200，最大 5000。",
				},
			},
		},
		Handler: handleWindowsProcessList,
	})

	_ = reg.Register(Capability{
		Name: "windows.process.kill",
		Description: "结束指定 PID 的进程。仅允许 pid > 0 的正整数；" +
			"可选 force 参数决定是否强制结束（对应 taskkill /F）。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"pid": map[string]any{
					"type":        "integer",
					"description": "目标进程 PID，必须为正整数。",
				},
				"force": map[string]any{
					"type":        "boolean",
					"description": "是否强制结束进程，默认 true（对应 taskkill /F）。",
				},
			},
			"required": []string{"pid"},
		},
		Handler: handleWindowsProcessKill,
	})
}

// handleWindowsProcessList 是 windows.process.list 的实现。
func handleWindowsProcessList(params map[string]any) (any, error) {
	filter, err := optionalString(params, "filter")
	if err != nil {
		return nil, err
	}
	limit, err := optionalInt(params, "limit", windowsProcessDefaultLimit)
	if err != nil {
		return nil, err
	}
	if limit <= 0 {
		return nil, fmt.Errorf("参数 limit 必须为正整数，实际 %d", limit)
	}
	if limit > windowsProcessMaxLimit {
		return nil, fmt.Errorf("参数 limit 超出上限 %d，实际 %d", windowsProcessMaxLimit, limit)
	}

	out, err := runWindowsProcessCommand("tasklist", "/FO", "CSV", "/NH")
	if err != nil {
		return nil, err
	}

	needle := strings.ToLower(filter)
	all := parseWindowsTasklistCSV(out)

	procs := make([]map[string]any, 0, len(all))
	for _, p := range all {
		if needle != "" {
			name := strings.ToLower(fmt.Sprint(p["name"]))
			pidStr := fmt.Sprint(p["pid"])
			if !strings.Contains(name, needle) && !strings.Contains(pidStr, needle) {
				continue
			}
		}
		procs = append(procs, p)
		if len(procs) >= limit {
			break
		}
	}

	// 按 PID 升序，保证输出稳定便于比对。
	sort.Slice(procs, func(i, j int) bool {
		return fmt.Sprint(procs[i]["pid"]) < fmt.Sprint(procs[j]["pid"])
	})

	return map[string]any{
		"processes": procs,
		"count":     len(procs),
		"truncated": len(all) > len(procs),
	}, nil
}

// handleWindowsProcessKill 是 windows.process.kill 的实现。
func handleWindowsProcessKill(params map[string]any) (any, error) {
	pid, err := optionalInt(params, "pid", 0)
	if err != nil {
		return nil, err
	}
	if pid <= 0 {
		return nil, fmt.Errorf("参数 pid 必须为正整数，实际 %d", pid)
	}
	force, err := optionalBool(params, "force", true)
	if err != nil {
		return nil, err
	}

	args := []string{"/PID", strconv.Itoa(pid)}
	if force {
		args = append(args, "/F")
	}
	out, err := runWindowsProcessCommand("taskkill", args...)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"pid":     pid,
		"force":   force,
		"message": strings.TrimSpace(out),
	}, nil
}

// runWindowsProcessCommand 执行进程相关外部命令并返回标准输出。
//
// 与 runWindowsCommand 的区别：taskkill 在失败时会把原因写在 stderr，
// 因此这里合并 stderr 到错误信息中，便于调用方定位（如「拒绝访问」）。
func runWindowsProcessCommand(name string, args ...string) (string, error) {
	if _, err := requireTool(name, ""); err != nil {
		return "", err
	}
	ctx, cancel := context.WithTimeout(context.Background(), windowsProcessTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, name, args...)
	out, err := cmd.Output()
	if err != nil {
		if exitErr, ok := err.(interface{ Stderr() []byte }); ok {
			msg := strings.TrimSpace(string(exitErr.Stderr()))
			if msg != "" {
				return "", fmt.Errorf("执行 %s 失败: %s", name, msg)
			}
		}
		return "", fmt.Errorf("执行 %s 失败: %w", name, err)
	}
	return string(out), nil
}
