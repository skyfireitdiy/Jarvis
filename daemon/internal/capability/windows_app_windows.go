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
func collectWindowsApps() ([]map[string]any, error) {
	if _, err := requirePowerShell(); err != nil {
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

// runRegQuery 查询注册表键，返回与 reg.exe query 相同格式的文本。
//
// 为什么不用 reg.exe
// ==================
// reg.exe 的输出按**控制台输出代码页**编码（中文 Windows 上是 GBK/CP936），
// 且 reg.exe **没有** UTF-8 输出模式（无 /u 之类的开关）。Go 侧 `string(out)`
// 按 UTF-8 解释 GBK 字节，会把中文应用名与发布者变成一串 U+FFFD——
// 这正是真实机器上 windows.app.list 返回 "�����Ƹ���Ϣ�ɷ����޹�˾" 的原因。
//
// 由于标准库没有 GBK 解码能力、且项目禁止引入第三方包，唯一可行的方案是
// **改用能输出 UTF-8 的数据源**：PowerShell 配合 [Console]::OutputEncoding=UTF8
// （见 runWindowsPowerShellCommand，它已保证 UTF-8 输出）。
//
// 输出格式兼容
// ============
// 为了让既有的 parseWindowsRegSubKeys / parseWindowsUninstallEntry /
// parseWindowsRegValues 三个纯函数**完全不用改**（它们已有完善单测），
// 这里用 PowerShell 主动构造出与 reg.exe 一致的文本格式：
//
//	<键路径>
//	    <值名>    REG_SZ    <数据>
//
// 以及子键列举时：
//
//	<键路径>
//	    <键路径>\<子键名>
//
// 这样解析层与数据源解耦：换数据源不影响解析逻辑，解析逻辑的单测仍然有效。
//
// 安全性：key 由本文件内的 windowsAppUninstallKeys 常量拼接而成，不含用户
// 输入；但仍经 encodePowerShellText 转义，避免反斜杠/引号引发语法问题。
func runRegQuery(key string) (string, error) {
	// PowerShell 的注册表驱动器名与 reg.exe 的根键名不同：
	// reg.exe 用 HKLM/HKCU，PowerShell 用 HKLM:/HKCU:（或 Registry::HKEY_...）。
	psKey, err := toPowerShellRegistryPath(key)
	if err != nil {
		return "", err
	}

	script := buildRegQueryScript(psKey)
	out, err := runWindowsPowerShellCommand(script, windowsAppTimeout)
	if err != nil {
		return "", fmt.Errorf("查询注册表 %s 失败: %w", key, err)
	}
	return out, nil
}

// buildRegQueryScript 构造与 reg.exe query 输出等价的 PowerShell 脚本。
//
// 脚本行为：
//   - 键不存在时静默退出（对应 reg.exe 的失败，由调用方跳过该键）；
//   - 先输出键路径自身一行；
//   - 再输出每个子键（完整路径，缩进 4 空格）；
//   - 最后输出每个值（名称 + 类型 + 数据，缩进 4 空格，用 4 空格分隔）。
//
// 用 [Console]::Out.Write 而非 Write-Output，是为了精确控制换行与缩进，
// 并避免 PowerShell 对输出的额外包装（如自动加空行）。
//
// 类型映射：PowerShell 的 GetValueKind 返回枚举名（如 String、DWord），
// 这里映射为 reg.exe 的 REG_SZ / REG_DWORD 等写法，使 parseWindowsRegValues
// 的 `strings.HasPrefix(f, "REG_")` 判据继续成立。
func buildRegQueryScript(psKey string) string {
	quotedKey := encodePowerShellText(psKey)
	return `
$k = ` + quotedKey + `
if (-not (Test-Path $k)) { exit 1 }
[Console]::Out.Write($k + "` + "`n" + `")
Get-ChildItem -Path $k -ErrorAction SilentlyContinue | ForEach-Object {
    [Console]::Out.Write("    " + $_.PSPath.Replace("Microsoft.PowerShell.Core\Registry::", "") + "` + "`n" + `")
}
$item = Get-Item -Path $k -ErrorAction SilentlyContinue
if ($item -ne $null) {
    foreach ($name in $item.GetValueNames()) {
        $kind = $item.GetValueKind($name)
        $typeName = switch ($kind.ToString()) {
            "String"       { "REG_SZ" }
            "ExpandString" { "REG_EXPAND_SZ" }
            "DWord"        { "REG_DWORD" }
            "QWord"        { "REG_QWORD" }
            "Binary"       { "REG_BINARY" }
            "MultiString"  { "REG_MULTI_SZ" }
            default        { "REG_SZ" }
        }
        $value = $item.GetValue($name)
        if ($value -is [array]) { $value = $value -join " " }
        [Console]::Out.Write("    " + $name + "    " + $typeName + "    " + $value + "` + "`n" + `")
    }
}
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
