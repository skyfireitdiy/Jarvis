//go:build windows

package capability

import (
	"context"
	"fmt"
	"os/exec"
	"sort"
	"strings"
	"time"
)

// windowsAppDefaultLimit 是 windows.app.list 未指定 limit 时返回的最大应用数。
const windowsAppDefaultLimit = 1000

// windowsAppMaxLimit 是 limit 允许的最大值，防止一次性返回过多数据。
const windowsAppMaxLimit = 5000

// windowsAppTimeout 是执行 reg.exe 查询的超时时间。
const windowsAppTimeout = 60 * time.Second

// windowsAppUninstallKeys 是存放「已安装应用」卸载信息的注册表路径。
//
// 覆盖 64 位程序、32 位程序（WOW6432Node）与当前用户安装的程序三类来源；
// HKCU 路径下没有 WOW6432Node 子键，故不重复列举。
var windowsAppUninstallKeys = []string{
	`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`,
	`HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall`,
	`HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`,
}

// registerWindowsApp 注册 Windows 已安装应用查询能力。
func registerWindowsApp(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.app.list",
		Description: "列出 Windows 已安装的应用。数据来自注册表卸载项" +
			"（HKLM/HKCU 的 Uninstall 键，含 WOW6432Node 32 位视图），" +
			"通过 reg.exe 查询，无需额外依赖。" +
			"已过滤掉 DisplayName 为空以及标记为 SystemComponent 的条目。" +
			"注意：本能力仅覆盖注册表登记的桌面应用，不含 Microsoft Store(UWP) 应用。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"filter": map[string]any{
					"type":        "string",
					"description": "按应用名称或发布者子串过滤，大小写不敏感；为空时返回全部应用。",
				},
				"limit": map[string]any{
					"type":        "integer",
					"description": "最多返回的应用数，默认 1000，最大 5000。",
				},
			},
		},
		Handler: handleWindowsAppList,
	})
}

// handleWindowsAppList 是 windows.app.list 的实现。
func handleWindowsAppList(params map[string]any) (any, error) {
	filter, err := optionalString(params, "filter")
	if err != nil {
		return nil, err
	}
	limit, err := optionalInt(params, "limit", windowsAppDefaultLimit)
	if err != nil {
		return nil, err
	}
	if limit <= 0 {
		return nil, fmt.Errorf("参数 limit 必须为正整数，实际 %d", limit)
	}
	if limit > windowsAppMaxLimit {
		return nil, fmt.Errorf("参数 limit 超出上限 %d，实际 %d", windowsAppMaxLimit, limit)
	}

	apps, err := collectWindowsApps()
	if err != nil {
		return nil, err
	}

	needle := strings.ToLower(filter)
	filtered := make([]map[string]any, 0, len(apps))
	for _, app := range apps {
		if needle != "" {
			name := strings.ToLower(fmt.Sprint(app["name"]))
			publisher := strings.ToLower(fmt.Sprint(app["publisher"]))
			if !strings.Contains(name, needle) && !strings.Contains(publisher, needle) {
				continue
			}
		}
		filtered = append(filtered, app)
		if len(filtered) >= limit {
			break
		}
	}

	return map[string]any{
		"apps":      filtered,
		"count":     len(filtered),
		"total":     len(apps),
		"truncated": len(apps) > len(filtered),
	}, nil
}

// collectWindowsApps 汇总所有注册表卸载项，去重后按名称排序返回。
func collectWindowsApps() ([]map[string]any, error) {
	if _, err := requireTool("reg", "reg.exe 是 Windows 自带命令，请确认系统 PATH 未被破坏"); err != nil {
		return nil, err
	}

	seen := make(map[string]struct{})
	apps := make([]map[string]any, 0, 128)

	for _, key := range windowsAppUninstallKeys {
		subKeys, err := listWindowsRegistrySubKeys(key)
		if err != nil {
			// 单个根键不可用（如 HKCU 下无该键）不应导致整体失败，跳过即可。
			continue
		}
		for _, subKey := range subKeys {
			fullKey := key + `\` + subKey
			out, err := runRegQuery(fullKey)
			if err != nil {
				continue
			}
			app := parseWindowsUninstallEntry(out)
			if app == nil {
				continue
			}
			name := fmt.Sprint(app["name"])
			dedupKey := strings.ToLower(name) + "\x00" + strings.ToLower(fmt.Sprint(app["version"]))
			if _, exists := seen[dedupKey]; exists {
				continue
			}
			seen[dedupKey] = struct{}{}
			apps = append(apps, app)
		}
	}

	sort.Slice(apps, func(i, j int) bool {
		return strings.ToLower(fmt.Sprint(apps[i]["name"])) < strings.ToLower(fmt.Sprint(apps[j]["name"]))
	})
	return apps, nil
}

// listWindowsRegistrySubKeys 列出注册表键下的子键名。
func listWindowsRegistrySubKeys(key string) ([]string, error) {
	out, err := runRegQuery(key)
	if err != nil {
		return nil, err
	}
	return parseWindowsRegSubKeys(out), nil
}

// runRegQuery 执行 reg.exe query 并返回标准输出。
func runRegQuery(key string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), windowsAppTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "reg", "query", key)
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("执行 reg query %s 失败: %w", key, err)
	}
	return string(out), nil
}
