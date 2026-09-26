//go:build windows

package capability

// 本文件实现 Windows 平台的服务管理能力（windows.service.*），对照 Linux 侧
// linux_service_linux.go 的 5 个能力，保持参数与返回结构一致：
//   - list：unit_type/all → units/count
//   - status：unit → unit/load/active/sub/description/main_pid/exec_start
//   - start/stop/restart：unit → unit/action/ok/output
//
// 与 Linux 的差异：
//   - Linux 用 systemctl --user 管理用户级 systemd 单元；Windows 没有对等概念，
//     这里管理的是「系统服务」（Service Control Manager），走 PowerShell 的
//     Get-Service / Start-Service / Stop-Service / Restart-Service。
//   - 之所以不用 sc.exe：sc.exe 输出受控制台代码页影响，中文服务名会乱码；
//     而 runWindowsPowerShellCommand 已统一把子进程输出强制为 UTF-8（见
//     windows_encoding.go），中文服务名可正确返回。
//   - 「unit」在 Windows 上即服务名（ServiceName），如 Spooler、wuauserv。
//
// 注意：本机开发环境为 Linux，无 Windows 运行环境，因此本文件只能保证
// 「在 GOOS=windows 下编译通过」，成功路径未做端到端验证。

import (
	"fmt"
	"strings"
	"time"
)

// windowsServiceTimeout 是单次服务查询/操作的超时时间。
//
// 服务启停可能耗时较久（尤其依赖链长的服务），因此比 Linux 侧的 10s 放宽到 30s。
const windowsServiceTimeout = 30 * time.Second

// registerWindowsService 注册 Windows 服务管理能力。
func registerWindowsService(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.service.list",
		Description: "列出 Windows 系统服务（Service Control Manager）。" +
			"数据来自 PowerShell Get-Service；中文服务显示名可正确返回。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"filter": map[string]any{
					"type":        "string",
					"description": "按服务名或显示名子串过滤，大小写不敏感；为空时返回全部服务。",
				},
				"all": map[string]any{
					"type":        "boolean",
					"description": "是否包含已停止的服务，默认 true（Get-Service 默认即包含全部）。",
				},
			},
		},
		Handler: handleWindowsServiceList,
	})

	_ = reg.Register(Capability{
		Name:        "windows.service.status",
		Description: "查询指定 Windows 服务的详细状态（PowerShell Get-Service）。",
		Platform:    PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"unit": map[string]any{
					"type":        "string",
					"description": "服务名（ServiceName），如 Spooler、wuauserv；也接受显示名。",
				},
			},
			"required": []string{"unit"},
		},
		Handler: handleWindowsServiceStatus,
	})

	_ = reg.Register(Capability{
		Name:        "windows.service.start",
		Description: "启动指定 Windows 服务（PowerShell Start-Service）。",
		Platform:    PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"unit": map[string]any{
					"type":        "string",
					"description": "服务名（ServiceName），如 Spooler。",
				},
			},
			"required": []string{"unit"},
		},
		Handler: handleWindowsServiceAction("start"),
	})

	_ = reg.Register(Capability{
		Name:        "windows.service.stop",
		Description: "停止指定 Windows 服务（PowerShell Stop-Service）。",
		Platform:    PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"unit": map[string]any{
					"type":        "string",
					"description": "服务名（ServiceName），如 Spooler。",
				},
			},
			"required": []string{"unit"},
		},
		Handler: handleWindowsServiceAction("stop"),
	})

	_ = reg.Register(Capability{
		Name:        "windows.service.restart",
		Description: "重启指定 Windows 服务（PowerShell Restart-Service）。",
		Platform:    PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"unit": map[string]any{
					"type":        "string",
					"description": "服务名（ServiceName），如 Spooler。",
				},
			},
			"required": []string{"unit"},
		},
		Handler: handleWindowsServiceAction("restart"),
	})
}

// handleWindowsServiceList 是 windows.service.list 的实现。
func handleWindowsServiceList(params map[string]any) (any, error) {
	filter, err := optionalString(params, "filter")
	if err != nil {
		return nil, err
	}

	// all 参数仅为与 Linux 侧参数对齐：Get-Service 本身即返回全部服务（含已停止），
	// 因此这里读取后不使用，但保留校验以便参数类型错误能被及时发现。
	if _, err := optionalBool(params, "all", true); err != nil {
		return nil, err
	}

	// 用 ConvertTo-Csv 输出，避免 Format-Table 的列宽截断与本地化表头问题。
	script := "Get-Service | Select-Object Name,DisplayName,Status | ConvertTo-Csv -NoTypeInformation"

	out, err := runWindowsPowerShellCommand(script, windowsServiceTimeout)
	if err != nil {
		return nil, err
	}

	units := parseWindowsServiceCSV(out)

	if filter != "" {
		units = filterWindowsServiceUnits(units, filter)
	}

	return map[string]any{
		"units": units,
		"count": len(units),
	}, nil
}

// handleWindowsServiceStatus 是 windows.service.status 的实现。
func handleWindowsServiceStatus(params map[string]any) (any, error) {
	unit, err := resolveWindowsServiceUnit(params)
	if err != nil {
		return nil, err
	}

	// 用 Get-CimInstance Win32_Service 可拿到更多字段（启动类型、进程 ID、路径等），
	// 比 Get-Service 更接近 systemctl show 的信息量。
	script := fmt.Sprintf(
		"$s = Get-CimInstance Win32_Service -Filter %s; "+
			"if ($null -eq $s) { Write-Output 'NOT_FOUND'; exit 0 }; "+
			"$s | Select-Object Name,DisplayName,State,StartMode,ProcessId,PathName,Status | ConvertTo-Csv -NoTypeInformation",
		encodePowerShellText(unit),
	)

	out, err := runWindowsPowerShellCommand(script, windowsServiceTimeout)
	if err != nil {
		return nil, err
	}

	trimmed := strings.TrimSpace(out)
	if trimmed == "" || strings.Contains(trimmed, "NOT_FOUND") {
		return nil, fmt.Errorf("未找到服务 %q", unit)
	}

	props := parseWindowsServiceStatusCSV(out)
	if len(props) == 0 {
		return nil, fmt.Errorf("未找到服务 %q", unit)
	}

	return map[string]any{
		"unit":        unit,
		"load":        props["StartMode"],
		"active":      props["State"],
		"sub":         props["Status"],
		"description": props["DisplayName"],
		"main_pid":    props["ProcessId"],
		"exec_start":  props["PathName"],
	}, nil
}

// handleWindowsServiceAction 生成 start / stop / restart 的实现。
func handleWindowsServiceAction(action string) func(map[string]any) (any, error) {
	return func(params map[string]any) (any, error) {
		unit, err := resolveWindowsServiceUnit(params)
		if err != nil {
			return nil, err
		}

		// 把动作名映射到 PowerShell cmdlet。动作名由本函数内部固定传入，
		// 不接受外部输入，因此不存在注入风险。
		var cmdlet string
		switch action {
		case "start":
			cmdlet = "Start-Service"
		case "stop":
			cmdlet = "Stop-Service"
		case "restart":
			cmdlet = "Restart-Service"
		default:
			return nil, fmt.Errorf("不支持的服务动作: %q", action)
		}

		script := fmt.Sprintf(
			"$ErrorActionPreference = 'Stop'; "+
				"try { %s -Name %s; Write-Output 'OK' } catch { Write-Output ('ERR: ' + $_.Exception.Message) }",
			cmdlet,
			encodePowerShellText(unit),
		)

		out, err := runWindowsPowerShellCommand(script, windowsServiceTimeout)
		if err != nil {
			return nil, err
		}

		trimmed := strings.TrimSpace(out)
		if strings.HasPrefix(trimmed, "ERR:") {
			return nil, fmt.Errorf("执行 %s 服务 %q 失败: %s", action, unit, strings.TrimPrefix(trimmed, "ERR: "))
		}

		return map[string]any{
			"unit":   unit,
			"action": action,
			"ok":     true,
			"output": trimmed,
		}, nil
	}
}

// resolveWindowsServiceUnit 解析并校验 unit（服务名）参数。
func resolveWindowsServiceUnit(params map[string]any) (string, error) {
	unit, err := requiredString(params, "unit")
	if err != nil {
		return "", err
	}
	if err := validateWindowsServiceName(unit); err != nil {
		return "", err
	}
	return unit, nil
}

// validateWindowsServiceName 校验服务名合法性。
//
// Windows 服务名（ServiceName）允许的字符比 Linux unit 更宽（可含空格、中文等），
// 但为了安全，这里仍做白名单校验：字母、数字、下划线、点、@、连字符、空格、
// 以及非 ASCII 可见字符（覆盖中文服务名）。
//
// 同时拒绝以 "-" 开头的名字，避免被 PowerShell 当作参数（如 -Name 之后被注入
// 额外的开关）。真正的注入防护由 encodePowerShellText 的单引号转义承担，
// 这里只是「早失败」的第一道防线。
func validateWindowsServiceName(name string) error {
	trimmed := strings.TrimSpace(name)
	if trimmed == "" {
		return fmt.Errorf("参数 unit 不能为空")
	}
	if strings.HasPrefix(trimmed, "-") {
		return fmt.Errorf("参数 unit 不能以 - 开头（会被解析为命令选项）: %q", name)
	}
	for _, r := range trimmed {
		switch {
		case r >= 'a' && r <= 'z':
		case r >= 'A' && r <= 'Z':
		case r >= '0' && r <= '9':
		case r == '_' || r == '.' || r == '@' || r == '-' || r == ' ':
		case r > 0x7f:
			// 允许非 ASCII 可见字符（如中文服务名）。
		default:
			return fmt.Errorf("参数 unit 含非法字符 %q，允许字母、数字、_ . @ - 空格及非 ASCII 字符", string(r))
		}
	}
	return nil
}
