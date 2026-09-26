//go:build windows

package capability

import (
	"fmt"
	"sort"
	"strings"
	"time"
)

// windowsAppDefaultLimit 是 windows.app.list 未指定 limit 时返回的最大应用数。
const windowsAppDefaultLimit = 1000

// windowsAppMaxLimit 是 limit 允许的最大值，防止一次性返回过多数据。
const windowsAppMaxLimit = 5000

// windowsAppTimeout 是执行注册表查询的超时时间。
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
			"通过 PowerShell 读取（保证中文应用名与发布者以 UTF-8 返回，不因系统代码页而乱码）。" +
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
//
// 性能关键：**只启动一次 PowerShell**。
//
// 早期实现是 N+1 次进程启动（先枚举 3 个根键的子键，再对每个子键单独
// reg query），而真机注册表通常有 200~500 个卸载项，即 200~500 次
// powershell.exe 冷启动，累计远超 60s 超时——真机 windows.app.list 超时
// 的根因即在此。现在改为一次调用把三个根键下的所有卸载项导出为 CSV，
// 由 parseWindowsAppCSV 解析（见 windows_app_parse.go）。
func collectWindowsApps() ([]map[string]any, error) {
	if _, err := requirePowerShell(); err != nil {
		return nil, err
	}

	script := buildWindowsAppListScript()
	out, err := runWindowsPowerShellCommand(script, windowsAppTimeout)
	if err != nil {
		return nil, err
	}

	apps := parseWindowsAppCSV(out)

	// 去重：同名同版本视为同一应用（不同根键/32-64 位视图可能重复登记）。
	seen := make(map[string]struct{}, len(apps))
	deduped := make([]map[string]any, 0, len(apps))
	for _, app := range apps {
		name := fmt.Sprint(app["name"])
		dedupKey := strings.ToLower(name) + "\x00" + strings.ToLower(fmt.Sprint(app["version"]))
		if _, exists := seen[dedupKey]; exists {
			continue
		}
		seen[dedupKey] = struct{}{}
		deduped = append(deduped, app)
	}

	sort.Slice(deduped, func(i, j int) bool {
		return strings.ToLower(fmt.Sprint(deduped[i]["name"])) < strings.ToLower(fmt.Sprint(deduped[j]["name"]))
	})
	return deduped, nil
}

// buildWindowsAppListScript 构造一次性导出全部卸载项的 PowerShell 脚本。
//
// 脚本行为：
//   - 遍历 windowsAppUninstallKeys 中的三个根键（HKLM 64 位、HKLM WOW6432Node
//     32 位、HKCU），用 Get-ItemProperty 读取每个子键的卸载信息；
//   - 只挑选需要的字段并统一为字符串（Get-ItemProperty 对缺失字段返回 $null，
//     这里用 [string] 强转并 TrimSpace，保证 CSV 中不会出现空列错位）；
//   - 用 ConvertTo-Csv -NoTypeInformation 输出，由 Go 侧 parseWindowsAppCSV 解析。
//
// 键路径由本文件内的 windowsAppUninstallKeys 常量拼接而成，不含用户输入；
// 但仍经 encodePowerShellText 转义，避免反斜杠/引号引发语法问题。
//
// 注意：Get-ItemProperty 对不存在的键会报错，故用 -ErrorAction SilentlyContinue
// 静默跳过（如 HKCU 下可能没有 Uninstall 键）。
func buildWindowsAppListScript() string {
	parts := make([]string, 0, len(windowsAppUninstallKeys))
	for _, key := range windowsAppUninstallKeys {
		psKey, err := toPowerShellRegistryPath(key)
		if err != nil {
			// 常量键不可转换属于编程错误，跳过而非整体失败（保留其余根键）。
			continue
		}
		parts = append(parts, encodePowerShellText(psKey))
	}

	// 用反引号原生字符串书写脚本，避免 Go 层的引号转义与 PowerShell 的
	// 引号语法相互干扰。Select-Object 用哈希表 @{Name=...;Expression={...}}
	// 把每个字段统一为 [string]，使 CSV 列稳定（缺失字段变成空串而非 $null）。
	selectClause := "Select-Object " +
		"@{Name='DisplayName';Expression={[string]$_.DisplayName}}, " +
		"@{Name='DisplayVersion';Expression={[string]$_.DisplayVersion}}, " +
		"@{Name='Publisher';Expression={[string]$_.Publisher}}, " +
		"@{Name='InstallLocation';Expression={[string]$_.InstallLocation}}, " +
		"@{Name='InstallDate';Expression={[string]$_.InstallDate}}, " +
		"@{Name='SystemComponent';Expression={[string]$_.SystemComponent}}"

	return `
$paths = @(` + strings.Join(parts, ", ") + `)
$paths | ForEach-Object {
    Get-ChildItem -Path $_ -ErrorAction SilentlyContinue | ForEach-Object {
        Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue
    }
} | ` + selectClause + ` | ConvertTo-Csv -NoTypeInformation
`
}

// toPowerShellRegistryPath 把 reg.exe 风格的根键名转换为 PowerShell 注册表路径。
//
// reg.exe 用 HKLM / HKCU / HKCR / HKU / HKCC 简写，PowerShell 的注册表提供程序
// 接受 HKLM: / HKCU: 等形式。仅做前缀替换，其余路径原样保留。
func toPowerShellRegistryPath(key string) (string, error) {
	prefixes := []struct {
		reg string
		ps  string
	}{
		{`HKLM\`, `HKLM:\`},
		{`HKCU\`, `HKCU:\`},
		{`HKCR\`, `HKCR:\`},
		{`HKU\`, `HKU:\`},
		{`HKCC\`, `HKCC:\`},
	}
	for _, p := range prefixes {
		if strings.HasPrefix(key, p.reg) {
			return p.ps + strings.TrimPrefix(key, p.reg), nil
		}
	}
	return "", fmt.Errorf("无法识别的注册表根键: %s", key)
}
