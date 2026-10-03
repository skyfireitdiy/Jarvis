package capability

// 本文件存放 Windows UI 自动化能力（windows.ui.tree / windows.ui.menu）的
// 纯逻辑：PowerShell 脚本构造与输出解析。
//
// 这些函数只依赖标准库与 encodePowerShellText（定义于无构建标签的
// windows_gui_parse.go），不引用任何平台专有类型，因此**不带构建标签**：
// 这样在 Linux / macOS 上也能编译并直接做单元测试，从而在无 Windows 环境时
// 仍能验证「脚本结构完整、用户输入被正确转义、输出解析正确」。
//
// 与之配套的测试见 windows_ui_parse_test.go；带 //go:build windows 标签的
// windows_ui_windows.go 负责注册能力、解析参数并调用 runWindowsPowerShellCommand。
//
// 安全约定：凡来自用户输入的字符串（title、菜单路径段）一律经
// encodePowerShellText 转义为单引号字面量后再拼进脚本，绝不直接拼接。

import (
	"fmt"
	"strconv"
	"strings"
)

// uiTreeMaxDepthDefault 是控件树默认最大深度。
const uiTreeMaxDepthDefault = 10

// uiTreeMaxControlsDefault 是控件树默认最大控件数。
const uiTreeMaxControlsDefault = 200

// windowsUIAddTypePreamble 是加载 UIAutomation 程序集的前置语句。
// UIAutomationClient/UIAutomationTypes 是 .NET Framework 内置程序集，
// Windows PowerShell 5.1 可直接 Add-Type 加载，零第三方依赖。
const windowsUIAddTypePreamble = "Add-Type -AssemblyName UIAutomationClient; Add-Type -AssemblyName UIAutomationTypes"

// buildWindowsUITreeScript 构造 windows.ui.tree 的 PowerShell 脚本。
//
// windowID 与 title 至少提供一个用于定位目标窗口：
//   - windowID 非空时用 FromHandle([IntPtr]) 直接定位（十进制或 0x 十六进制）；
//   - 否则用 title 子串匹配查找窗口句柄。
//
// maxDepth / maxControls 限制遍历规模，防止大窗口卡死。
// 脚本以「|」分隔的文本行输出控件（depth|type|name|automation_id|x|y|w|h），
// 由 parseWindowsUITreeText 解析。
func buildWindowsUITreeScript(windowID, title string, maxDepth, maxControls int) (string, error) {
	if windowID == "" && title == "" {
		return "", fmt.Errorf("参数 window_id 与 title 至少需要提供一个")
	}
	if maxDepth < 1 {
		maxDepth = uiTreeMaxDepthDefault
	}
	if maxControls < 1 {
		maxControls = uiTreeMaxControlsDefault
	}

	var rootExpr string
	if windowID != "" {
		// window_id 是整数（十进制或 0x 十六进制），直接格式化，无注入面。
		rootExpr = "[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]" + windowID + ")"
	} else {
		// title 经 encodePowerShellText 转义为单引号字面量，再与通配符拼接成 -like 模式。
		quotedTitle := encodePowerShellText(title)
		rootExpr = "$w = Get-Process | Where-Object { $_.MainWindowTitle -like ('*' + " + quotedTitle + " + '*') } | Select-Object -First 1; " +
			"if ($w -eq $null) { Write-Output 'ERROR:no-window'; exit }; " +
			"[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$w.MainWindowHandle)"
	}

	return windowsUIAddTypePreamble + "; " +
		"$root = " + rootExpr + "; " +
		"if ($root -eq $null) { Write-Output 'ERROR:no-window'; exit }; " +
		"$sb = New-Object System.Text.StringBuilder; $script:count = 0; " +
		"function Walk($el, $depth) { " +
		"if ($script:count -ge " + strconv.Itoa(maxControls) + ") { return }; " +
		"$t = $el.Current.ControlType.ProgrammaticName; " +
		"$n = $el.Current.Name; " +
		"$a = $el.Current.AutomationId; " +
		"$r = $el.Current.BoundingRectangle; " +
		"[void]$script:sb.AppendLine(\"$depth|$t|$n|$a|$($r.X)|$($r.Y)|$($r.Width)|$($r.Height)\"); " +
		"$script:count++; " +
		"if ($depth -ge " + strconv.Itoa(maxDepth) + ") { return }; " +
		"$children = $el.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition); " +
		"foreach ($c in $children) { Walk $c ($depth + 1) } }; " +
		"Walk $root 0; $script:sb.ToString()", nil
}

// parseWindowsUITreeText 解析控件树文本输出为控件列表。
//
// 每行格式：depth|type|name|automation_id|x|y|w|h（由 buildWindowsUITreeScript 生成）。
// 返回按遍历顺序排列的控件条目，字段为 depth/type/name/automation_id/rect。
func parseWindowsUITreeText(out string) []map[string]any {
	controls := make([]map[string]any, 0, 64)
	lines := strings.Split(strings.ReplaceAll(out, "\r\n", "\n"), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		// 跳过错误标记行（如 ERROR:no-window）。
		if strings.HasPrefix(line, "ERROR:") {
			continue
		}
		parts := strings.Split(line, "|")
		if len(parts) < 8 {
			continue
		}
		controls = append(controls, map[string]any{
			"depth":         strings.TrimSpace(parts[0]),
			"type":          strings.TrimSpace(parts[1]),
			"name":          strings.TrimSpace(parts[2]),
			"automation_id": strings.TrimSpace(parts[3]),
			"rect": map[string]any{
				"x":      strings.TrimSpace(parts[4]),
				"y":      strings.TrimSpace(parts[5]),
				"width":  strings.TrimSpace(parts[6]),
				"height": strings.TrimSpace(parts[7]),
			},
		})
	}
	return controls
}

// parseWindowsUIMenuPath 解析菜单路径字符串为菜单项名列表。
//
// 语法：以 "->" 分隔，如 "File->Open"、"Edit->Copy"。也兼容单段 "Help"。
// 返回去除首尾空白后的段列表；空路径返回错误。
func parseWindowsUIMenuPath(path string) ([]string, error) {
	trimmed := strings.TrimSpace(path)
	if trimmed == "" {
		return nil, fmt.Errorf("参数 path 不能为空")
	}
	raw := strings.Split(trimmed, "->")
	segments := make([]string, 0, len(raw))
	for _, s := range raw {
		s = strings.TrimSpace(s)
		if s == "" {
			return nil, fmt.Errorf("参数 path 格式非法 %q，'->' 两侧不能为空", path)
		}
		segments = append(segments, s)
	}
	return segments, nil
}

// buildWindowsUIMenuScript 构造 windows.ui.menu 的 PowerShell 脚本。
//
// windowID 与 title 至少提供一个用于定位目标窗口（同 tree）。
// path 为菜单路径，如 "File->Open"。脚本用 UIA 逐级查找菜单项：
//   - 前 N-1 段：找到元素后尝试 ExpandCollapsePattern.Expand() 展开子菜单；
//   - 最后一段：找到元素后尝试 InvokePattern.Invoke()，若可展开则 Expand()。
//
// 脚本输出 "OK: <path>" 表示成功，否则输出 "ERROR: <原因>"。
func buildWindowsUIMenuScript(windowID, title, path string) (string, error) {
	if windowID == "" && title == "" {
		return "", fmt.Errorf("参数 window_id 与 title 至少需要提供一个")
	}
	segments, err := parseWindowsUIMenuPath(path)
	if err != nil {
		return "", err
	}

	var rootExpr string
	if windowID != "" {
		rootExpr = "[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]" + windowID + ")"
	} else {
		quotedTitle := encodePowerShellText(title)
		rootExpr = "$w = Get-Process | Where-Object { $_.MainWindowTitle -like ('*' + " + quotedTitle + " + '*') } | Select-Object -First 1; " +
			"if ($w -eq $null) { Write-Output 'ERROR:no-window'; exit }; " +
			"[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$w.MainWindowHandle)"
	}

	// 构造逐级查找的 PowerShell 语句。
	var steps strings.Builder
	steps.WriteString("$cur = " + rootExpr + "; ")
	steps.WriteString("if ($cur -eq $null) { Write-Output 'ERROR:no-window'; exit }; ")
	for i, seg := range segments {
		quoted := encodePowerShellText(seg)
		steps.WriteString("$cond = New-Object System.Windows.Automation.PropertyCondition(" +
			"[System.Windows.Automation.AutomationElement]::NameProperty, " + quoted + "); ")
		steps.WriteString("$el = $cur.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond); ")
		steps.WriteString("if ($el -eq $null) { $el = $cur.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond) }; ")
		steps.WriteString("if ($el -eq $null) { Write-Output ('ERROR:not-found: " + quoted + "'); exit }; ")
		if i == len(segments)-1 {
			// 最后一段：尝试 Invoke，否则 Expand。
			steps.WriteString("try { $p = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern); " +
				"$p.Invoke(); Write-Output ('OK: " + quoted + "') } catch { " +
				"try { $e = $el.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern); " +
				"$e.Expand(); Write-Output ('OK(expanded): " + quoted + "') } catch { " +
				"Write-Output ('ERROR:no-pattern: " + quoted + "') } }")
		} else {
			// 中间段：展开子菜单。
			steps.WriteString("try { $e = $el.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern); $e.Expand() } catch { }; ")
			steps.WriteString("$cur = $el; ")
		}
	}

	return windowsUIAddTypePreamble + "; " + steps.String(), nil
}
