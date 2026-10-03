package capability

// 本文件存放 Windows 系统配置能力（windows.config.*）的脚本构造纯函数。
//
// 这些函数只依赖标准库与 encodePowerShellText（定义于无构建标签的
// windows_gui_parse.go），不引用任何平台专有类型，因此**不带构建标签**：
// 这样在 Linux / macOS 上也能编译并直接做单元测试，从而在无 Windows 环境时
// 仍能验证「用户输入是否被正确转义、脚本是否无注入面」。
//
// 与之配套的测试见 windows_config_parse_test.go；带 //go:build windows 标签的
// windows_config_windows.go 负责注册能力、解析参数并调用 runWindowsPowerShellCommand。
//
// 安全约定：凡来自用户输入的字符串（plan_id、server、bypass、name）一律经
// encodePowerShellText 转义为单引号字面量后再拼进脚本，绝不直接拼接。

import (
	"fmt"
	"strings"
)

// 主题注册表路径（固定常量，不含用户输入）。
const windowsConfigThemePath = `HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize`

// 代理注册表路径（固定常量，不含用户输入）。
const windowsConfigProxyPath = `HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings`

// 远程桌面注册表路径（固定常量，不含用户输入）。
const windowsConfigRemoteDesktopPath = `HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server`

// 开机启动文件夹（PowerShell 变量，运行时展开，不含用户输入）。
const windowsConfigStartupDir = `$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup`

// buildWindowsConfigThemeScript 构造 windows.config.theme 的 PowerShell 脚本。
// mode 取值 dark/light/toggle，非法值返回错误。
func buildWindowsConfigThemeScript(mode string) (string, error) {
	switch mode {
	case "dark":
		return "Set-ItemProperty -Path '" + windowsConfigThemePath + "' -Name AppsUseLightTheme -Value 0 -Type Dword -Force; " +
			"Set-ItemProperty -Path '" + windowsConfigThemePath + "' -Name SystemUsesLightTheme -Value 0 -Type Dword -Force; " +
			"Write-Output 'Theme: dark'", nil
	case "light":
		return "Set-ItemProperty -Path '" + windowsConfigThemePath + "' -Name AppsUseLightTheme -Value 1 -Type Dword -Force; " +
			"Set-ItemProperty -Path '" + windowsConfigThemePath + "' -Name SystemUsesLightTheme -Value 1 -Type Dword -Force; " +
			"Write-Output 'Theme: light'", nil
	case "toggle":
		return "$p = Get-ItemProperty -Path '" + windowsConfigThemePath + "' -Name AppsUseLightTheme -ErrorAction SilentlyContinue; " +
			"$v = if ($p.AppsUseLightTheme -eq 0) { 1 } else { 0 }; " +
			"Set-ItemProperty -Path '" + windowsConfigThemePath + "' -Name AppsUseLightTheme -Value $v -Type Dword -Force; " +
			"Set-ItemProperty -Path '" + windowsConfigThemePath + "' -Name SystemUsesLightTheme -Value $v -Type Dword -Force; " +
			"Write-Output ('Theme: ' + $(if ($v -eq 0) { 'dark' } else { 'light' }))", nil
	default:
		return "", fmt.Errorf("参数 mode 不支持 %q，允许值: dark、light、toggle", mode)
	}
}

// buildWindowsConfigPowerPlanScript 构造 windows.config.power-plan 的 PowerShell 脚本。
// action 取值 list/set；set 时 planID 必填并经 encodePowerShellText 转义。
func buildWindowsConfigPowerPlanScript(action, planID string) (string, error) {
	switch action {
	case "list":
		return "powercfg /list", nil
	case "set":
		if planID == "" {
			return "", fmt.Errorf("set 操作需要 plan_id 参数")
		}
		// plan_id 是 GUID，经 encodePowerShellText 转义后作为参数传给 powercfg。
		return "powercfg /setactive " + encodePowerShellText(planID), nil
	default:
		return "", fmt.Errorf("参数 action 不支持 %q，允许值: list、set", action)
	}
}

// buildWindowsConfigProxyScript 构造 windows.config.proxy 的 PowerShell 脚本。
// action 取值 get/enable/disable/set；enable/set 时 server 与 bypass 经转义。
func buildWindowsConfigProxyScript(action, server, bypass string) (string, error) {
	switch action {
	case "get":
		return "$p = Get-ItemProperty -Path '" + windowsConfigProxyPath + "' -Name ProxyEnable -ErrorAction SilentlyContinue; " +
			"$s = (Get-ItemProperty -Path '" + windowsConfigProxyPath + "' -Name ProxyServer -ErrorAction SilentlyContinue).ProxyServer; " +
			"Write-Output ('enabled=' + $p.ProxyEnable + '; server=' + $s)", nil
	case "disable":
		return "Set-ItemProperty -Path '" + windowsConfigProxyPath + "' -Name ProxyEnable -Value 0 -Type Dword -Force; " +
			"Write-Output 'Proxy disabled'", nil
	case "enable", "set":
		// server 为空时 enable 用默认地址；set 必须提供 server。
		if server == "" {
			if action == "set" {
				return "", fmt.Errorf("set 操作需要 server 参数")
			}
			server = "127.0.0.1:7890"
		}
		if bypass == "" {
			bypass = "localhost;127.*;10.*;172.16.*;192.168.*"
		}
		// 所有用户输入经 encodePowerShellText 转义，防止命令注入。
		quotedServer := encodePowerShellText(server)
		quotedBypass := encodePowerShellText(bypass)
		return "Set-ItemProperty -Path '" + windowsConfigProxyPath + "' -Name ProxyEnable -Value 1 -Type Dword -Force; " +
			"Set-ItemProperty -Path '" + windowsConfigProxyPath + "' -Name ProxyServer -Value " + quotedServer + " -Force; " +
			"Set-ItemProperty -Path '" + windowsConfigProxyPath + "' -Name ProxyOverride -Value " + quotedBypass + " -Force -ErrorAction SilentlyContinue; " +
			"Write-Output ('Proxy " + action + ": ' + " + quotedServer + ")", nil
	default:
		return "", fmt.Errorf("参数 action 不支持 %q，允许值: get、enable、disable、set", action)
	}
}

// buildWindowsConfigScreenTimeoutScript 构造 windows.config.screen-timeout 的脚本。
// action 取值 get/set；set 时 minutes 为整数（>=0），直接格式化，无注入面。
func buildWindowsConfigScreenTimeoutScript(action string, minutes int) (string, error) {
	switch action {
	case "get":
		return "powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE", nil
	case "set":
		if minutes < 0 {
			return "", fmt.Errorf("参数 minutes 不能为负数，实际 %d", minutes)
		}
		return fmt.Sprintf("powercfg /change monitor-timeout-ac %d; powercfg /change monitor-timeout-dc %d", minutes, minutes), nil
	default:
		return "", fmt.Errorf("参数 action 不支持 %q，允许值: get、set", action)
	}
}

// buildWindowsConfigRemoteDesktopScript 构造 windows.config.remote-desktop 的脚本。
// action 取值 enable/disable/get。
func buildWindowsConfigRemoteDesktopScript(action string) (string, error) {
	switch action {
	case "get":
		return "$v = (Get-ItemProperty -Path '" + windowsConfigRemoteDesktopPath + "' -Name fDenyTSConnections -ErrorAction SilentlyContinue).fDenyTSConnections; " +
			"Write-Output ('fDenyTSConnections=' + $v)", nil
	case "enable":
		return "Set-ItemProperty -Path '" + windowsConfigRemoteDesktopPath + "' -Name fDenyTSConnections -Value 0 -Force; " +
			"Write-Output 'Remote Desktop enabled (may need admin)'", nil
	case "disable":
		return "Set-ItemProperty -Path '" + windowsConfigRemoteDesktopPath + "' -Name fDenyTSConnections -Value 1 -Force; " +
			"Write-Output 'Remote Desktop disabled (may need admin)'", nil
	default:
		return "", fmt.Errorf("参数 action 不支持 %q，允许值: enable、disable、get", action)
	}
}

// buildWindowsConfigStartupScript 构造 windows.config.startup 的脚本。
// action 取值 list/enable/disable；enable/disable 时 name 必填并经转义。
func buildWindowsConfigStartupScript(action, name string) (string, error) {
	switch action {
	case "list":
		return "Get-ChildItem -Path '" + windowsConfigStartupDir + "' -ErrorAction SilentlyContinue | " +
			"ForEach-Object { Write-Output ($_.Name + ' | ' + $_.Target) }", nil
	case "enable", "disable":
		if name == "" {
			return "", fmt.Errorf("%s 操作需要 name 参数", action)
		}
		// name 是文件名，经 encodePowerShellText 转义后作为路径的一部分。
		quotedName := encodePowerShellText(name)
		if action == "disable" {
			return "$p = Join-Path '" + windowsConfigStartupDir + "' " + quotedName + "; " +
				"if (Test-Path $p) { Rename-Item $p ($p + '.disabled') -Force; Write-Output ('Disabled: ' + " + quotedName + ") } " +
				"else { Write-Error ('Not found: ' + " + quotedName + ") }", nil
		}
		return "$p = Join-Path '" + windowsConfigStartupDir + "' " + quotedName + "; " +
			"$disabled = $p + '.disabled'; " +
			"if (Test-Path $disabled) { Rename-Item $disabled $p -Force; Write-Output ('Enabled: ' + " + quotedName + ") } " +
			"elseif (Test-Path $p) { Write-Output ('Already enabled: ' + " + quotedName + ") } " +
			"else { Write-Error ('Not found: ' + " + quotedName + ") }", nil
	default:
		return "", fmt.Errorf("参数 action 不支持 %q，允许值: list、enable、disable", action)
	}
}

// trimWindowsOutput 去除 PowerShell 输出首尾空白。
func trimWindowsOutput(out string) string {
	return strings.TrimSpace(out)
}
