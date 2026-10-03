//go:build windows

package capability

// 本文件实现 Windows 平台的系统配置能力（windows.config.*），语义对齐
// jarvis-windows (jw) 的 config 命令组：
//   - theme：切换系统/应用深色/浅色主题
//   - power-plan：列出或切换电源计划
//   - proxy：获取/启用/禁用/设置系统代理
//   - screen-timeout：获取/设置屏幕关闭超时
//   - remote-desktop：启用/禁用/查询远程桌面
//   - startup：列出/启用/禁用开机启动项
//
// 全部通过 PowerShell 操作注册表或调用系统命令（powercfg 等），零第三方依赖。
// 与 jw（pywinauto 等第三方库）不同，这里只用系统自带的 PowerShell 与注册表。
//
// 注意：本机开发环境为 Linux，无 Windows 运行环境，因此本文件只能保证
// 「在 GOOS=windows 下编译通过」，成功路径未做端到端验证。
// 参数校验与脚本构造逻辑已抽取到无构建标签的 windows_config_parse.go，
// 可在 Linux 上单测。

import (
	"time"
)

// windowsConfigTimeout 是单次系统配置操作的超时时间。
// powercfg /query 等命令可能稍慢，放宽到 30s。
const windowsConfigTimeout = 30 * time.Second

// registerWindowsConfig 注册 Windows 系统配置能力。
func registerWindowsConfig(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.config.theme",
		Description: "切换系统/应用主题（深色/浅色模式）。" +
			"通过修改 HKCU 的 Themes\\Personalize 注册表键的 AppsUseLightTheme 与 " +
			"SystemUsesLightTheme 实现（0=深色，1=浅色）。无需任何第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"mode": map[string]any{
					"type":        "string",
					"description": "目标模式：dark（深色）、light（浅色）、toggle（取反当前值）。",
				},
			},
			"required": []string{"mode"},
		},
		Handler: handleWindowsConfigTheme,
	})

	_ = reg.Register(Capability{
		Name: "windows.config.power-plan",
		Description: "列出或切换 Windows 电源计划。" +
			"list 用 powercfg /list 列出全部计划；set 用 powercfg /setactive 激活指定计划。" +
			"无需任何第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"action": map[string]any{
					"type":        "string",
					"description": "操作：list（列出计划）或 set（切换计划）。",
				},
				"plan_id": map[string]any{
					"type":        "string",
					"description": "电源计划 GUID（set 时必需），如 381b4222-f694-41f0-9685-ff5bb260df2e。",
				},
			},
			"required": []string{"action"},
		},
		Handler: handleWindowsConfigPowerPlan,
	})

	_ = reg.Register(Capability{
		Name: "windows.config.proxy",
		Description: "获取、启用、禁用或设置 Windows 系统代理。" +
			"通过修改 HKCU 的 Internet Settings 注册表键（ProxyEnable/ProxyServer/ProxyOverride）实现。" +
			"无需任何第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"action": map[string]any{
					"type":        "string",
					"description": "操作：get（查询）、enable（启用）、disable（禁用）、set（设置代理地址）。",
				},
				"server": map[string]any{
					"type":        "string",
					"description": "代理地址，如 127.0.0.1:7890（enable/set 时使用）。",
				},
				"bypass": map[string]any{
					"type":        "string",
					"description": "绕过列表，分号分隔，如 localhost;127.*（enable/set 时可选）。",
				},
			},
			"required": []string{"action"},
		},
		Handler: handleWindowsConfigProxy,
	})

	_ = reg.Register(Capability{
		Name: "windows.config.screen-timeout",
		Description: "获取或设置屏幕关闭超时（当前电源计划）。" +
			"get 用 powercfg /query 查询 VIDEOIDLE；set 用 powercfg /change 设置交流/电池供电的熄屏分钟数。" +
			"无需任何第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"action": map[string]any{
					"type":        "string",
					"description": "操作：get（查询）或 set（设置）。",
				},
				"minutes": map[string]any{
					"type":        "integer",
					"description": "熄屏分钟数，0 表示从不（set 时必需）。",
				},
			},
			"required": []string{"action"},
		},
		Handler: handleWindowsConfigScreenTimeout,
	})

	_ = reg.Register(Capability{
		Name: "windows.config.remote-desktop",
		Description: "启用、禁用或查询远程桌面。" +
			"通过修改 HKLM 的 Terminal Server 注册表键 fDenyTSConnections 实现（0=允许，1=拒绝）。" +
			"修改需要管理员权限。无需任何第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"action": map[string]any{
					"type":        "string",
					"description": "操作：enable（启用）、disable（禁用）、get（查询）。",
				},
			},
			"required": []string{"action"},
		},
		Handler: handleWindowsConfigRemoteDesktop,
	})

	_ = reg.Register(Capability{
		Name: "windows.config.startup",
		Description: "列出、启用或禁用当前用户的开机启动项。" +
			"操作 %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup 文件夹，" +
			"禁用时把文件重命名为 .disabled 后缀，启用时还原。无需任何第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"action": map[string]any{
					"type":        "string",
					"description": "操作：list（列出）、enable（启用）、disable（禁用）。",
				},
				"name": map[string]any{
					"type":        "string",
					"description": "启动项文件名（enable/disable 时必需），如 myapp.lnk。",
				},
			},
			"required": []string{"action"},
		},
		Handler: handleWindowsConfigStartup,
	})
}

// handleWindowsConfigTheme 是 windows.config.theme 的实现。
func handleWindowsConfigTheme(params map[string]any) (any, error) {
	mode, err := requiredString(params, "mode")
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsConfigThemeScript(mode)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsConfigTimeout)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"mode":   mode,
		"output": trimWindowsOutput(out),
		"tool":   "powershell",
	}, nil
}

// handleWindowsConfigPowerPlan 是 windows.config.power-plan 的实现。
func handleWindowsConfigPowerPlan(params map[string]any) (any, error) {
	action, err := requiredString(params, "action")
	if err != nil {
		return nil, err
	}

	planID, err := optionalString(params, "plan_id")
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsConfigPowerPlanScript(action, planID)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsConfigTimeout)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"action": action,
		"output": trimWindowsOutput(out),
		"tool":   "powershell",
	}, nil
}

// handleWindowsConfigProxy 是 windows.config.proxy 的实现。
func handleWindowsConfigProxy(params map[string]any) (any, error) {
	action, err := requiredString(params, "action")
	if err != nil {
		return nil, err
	}

	server, err := optionalString(params, "server")
	if err != nil {
		return nil, err
	}
	bypass, err := optionalString(params, "bypass")
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsConfigProxyScript(action, server, bypass)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsConfigTimeout)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"action": action,
		"output": trimWindowsOutput(out),
		"tool":   "powershell",
	}, nil
}

// handleWindowsConfigScreenTimeout 是 windows.config.screen-timeout 的实现。
func handleWindowsConfigScreenTimeout(params map[string]any) (any, error) {
	action, err := requiredString(params, "action")
	if err != nil {
		return nil, err
	}

	minutes, err := optionalInt(params, "minutes", 0)
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsConfigScreenTimeoutScript(action, minutes)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsConfigTimeout)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"action": action,
		"output": trimWindowsOutput(out),
		"tool":   "powershell",
	}, nil
}

// handleWindowsConfigRemoteDesktop 是 windows.config.remote-desktop 的实现。
func handleWindowsConfigRemoteDesktop(params map[string]any) (any, error) {
	action, err := requiredString(params, "action")
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsConfigRemoteDesktopScript(action)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsConfigTimeout)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"action": action,
		"output": trimWindowsOutput(out),
		"tool":   "powershell",
	}, nil
}

// handleWindowsConfigStartup 是 windows.config.startup 的实现。
func handleWindowsConfigStartup(params map[string]any) (any, error) {
	action, err := requiredString(params, "action")
	if err != nil {
		return nil, err
	}

	name, err := optionalString(params, "name")
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsConfigStartupScript(action, name)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsConfigTimeout)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"action": action,
		"output": trimWindowsOutput(out),
		"tool":   "powershell",
	}, nil
}
