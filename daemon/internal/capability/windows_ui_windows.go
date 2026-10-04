//go:build windows

package capability

// 本文件实现 Windows UI 自动化能力（windows.ui.*），语义对齐
// jarvis-windows (jw) 的 get-tree / menu 命令：
//   - windows.ui.tree：枚举指定窗口的控件树（用 .NET 内置 UIAutomation）
//   - windows.ui.menu：按路径操作菜单项（如 "File->Open"）
//
// 全部通过 PowerShell 加载 UIAutomationClient 程序集实现，零第三方依赖。
//
// 注意：本机开发环境为 Linux，无 Windows 运行环境，因此本文件只能保证
// 「在 GOOS=windows 下编译通过」，成功路径未做端到端验证。
// 脚本构造与输出解析逻辑已抽取到无构建标签的 windows_ui_parse.go，可在 Linux 上单测。

import (
	"strings"
	"time"
)

// windowsUITimeout 是单次 UI 自动化操作的超时时间。
// UIA 遍历大窗口可能较慢，放宽到 30s。
const windowsUITimeout = 30 * time.Second

// registerWindowsUI 注册 Windows UI 自动化能力。
func registerWindowsUI(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.ui.tree",
		Description: "枚举指定窗口的控件树。" +
			"用 .NET 内置 UIAutomation 遍历窗口内所有控件，返回每个控件的类型、名称、AutomationId 与矩形区域。" +
			"通过 window_id 或 title 定位窗口，max_depth/max_controls 限制遍历规模。无需任何第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"window_id": map[string]any{
					"type":        "string",
					"description": "窗口 ID，如 0x00010A2C 或十进制；与 title 至少提供一个。",
				},
				"title": map[string]any{
					"type":        "string",
					"description": "窗口标题（子串匹配，大小写不敏感），当未提供 window_id 时使用。",
				},
				"max_depth": map[string]any{
					"type":        "integer",
					"description": "最大遍历深度，默认 10。",
				},
				"max_controls": map[string]any{
					"type":        "integer",
					"description": "最大控件数量，默认 200。",
				},
			},
		},
		Handler: handleWindowsUITree,
	})

	_ = reg.Register(Capability{
		Name: "windows.ui.menu",
		Description: "按路径操作窗口菜单项（如 'File->Open'）。" +
			"用 .NET 内置 UIAutomation 逐级查找菜单项并触发 Invoke/ExpandCollapse。" +
			"通过 window_id 或 title 定位窗口。无需任何第三方依赖。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"window_id": map[string]any{
					"type":        "string",
					"description": "窗口 ID，如 0x00010A2C 或十进制；与 title 至少提供一个。",
				},
				"title": map[string]any{
					"type":        "string",
					"description": "窗口标题（子串匹配，大小写不敏感），当未提供 window_id 时使用。",
				},
				"path": map[string]any{
					"type":        "string",
					"description": "菜单路径，以 '->' 分隔，如 'File->Open'。",
				},
			},
			"required": []string{"path"},
		},
		Handler: handleWindowsUIMenu,
	})

	_ = reg.Register(Capability{
		Name: "windows.control.click",
		Description: "按控件名或 AutomationId 直接点击窗口内的控件（控件级操作，不依赖屏幕坐标）。" +
			"用 .NET 内置 UIAutomation 定位控件并触发 InvokePattern.Invoke 或 SelectionItemPattern.Select。" +
			"通过 window_id 或 title 定位窗口，name/automation_id 定位控件。无需任何第三方依赖。" +
			"注意：CEF/Electron 等 Chromium 渲染应用不暴露 UIA 控件，本能力对其无效，需改用截图+OCR+坐标点击。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"window_id": map[string]any{
					"type":        "string",
					"description": "窗口 ID，如 0x00010A2C 或十进制；与 title 至少提供一个。",
				},
				"title": map[string]any{
					"type":        "string",
					"description": "窗口标题（子串匹配，大小写不敏感），当未提供 window_id 时使用。",
				},
				"name": map[string]any{
					"type":        "string",
					"description": "控件名称（Name 属性），与 automation_id 至少提供一个。",
				},
				"automation_id": map[string]any{
					"type":        "string",
					"description": "控件 AutomationId，与 name 至少提供一个。",
				},
			},
		},
		Handler: handleWindowsControlClick,
	})

	_ = reg.Register(Capability{
		Name: "windows.control.set-text",
		Description: "按控件名或 AutomationId 直接设置窗口内控件的文本（控件级操作，不依赖屏幕坐标）。" +
			"用 .NET 内置 UIAutomation 定位控件并用 ValuePattern.SetValue 设置文本。" +
			"通过 window_id 或 title 定位窗口，name/automation_id 定位控件。无需任何第三方依赖。" +
			"注意：CEF/Electron 等 Chromium 渲染应用不暴露 UIA 控件，本能力对其无效，需改用截图+OCR+坐标点击。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"window_id": map[string]any{
					"type":        "string",
					"description": "窗口 ID，如 0x00010A2C 或十进制；与 title 至少提供一个。",
				},
				"title": map[string]any{
					"type":        "string",
					"description": "窗口标题（子串匹配，大小写不敏感），当未提供 window_id 时使用。",
				},
				"name": map[string]any{
					"type":        "string",
					"description": "控件名称（Name 属性），与 automation_id 至少提供一个。",
				},
				"automation_id": map[string]any{
					"type":        "string",
					"description": "控件 AutomationId，与 name 至少提供一个。",
				},
				"text": map[string]any{
					"type":        "string",
					"description": "要设置的文本内容。",
				},
			},
			"required": []string{"text"},
		},
		Handler: handleWindowsControlSetText,
	})
}

// handleWindowsUITree 是 windows.ui.tree 的实现。
func handleWindowsUITree(params map[string]any) (any, error) {
	windowID, err := optionalString(params, "window_id")
	if err != nil {
		return nil, err
	}
	title, err := optionalString(params, "title")
	if err != nil {
		return nil, err
	}
	maxDepth, err := optionalInt(params, "max_depth", uiTreeMaxDepthDefault)
	if err != nil {
		return nil, err
	}
	maxControls, err := optionalInt(params, "max_controls", uiTreeMaxControlsDefault)
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsUITreeScript(windowID, title, maxDepth, maxControls)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsUITimeout)
	if err != nil {
		return nil, err
	}

	controls := parseWindowsUITreeText(out)
	return map[string]any{
		"window_id": windowID,
		"title":     title,
		"count":     len(controls),
		"controls":  controls,
		"tool":      "powershell",
	}, nil
}

// handleWindowsUIMenu 是 windows.ui.menu 的实现。
func handleWindowsUIMenu(params map[string]any) (any, error) {
	windowID, err := optionalString(params, "window_id")
	if err != nil {
		return nil, err
	}
	title, err := optionalString(params, "title")
	if err != nil {
		return nil, err
	}
	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsUIMenuScript(windowID, title, path)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsUITimeout)
	if err != nil {
		return nil, err
	}

	result := map[string]any{
		"window_id": windowID,
		"title":     title,
		"path":      path,
		"output":    trimWindowsOutput(out),
		"tool":      "powershell",
	}
	// 若脚本输出 ERROR: 前缀，说明菜单项未找到或无法触发，返回错误。
	if msg := trimWindowsOutput(out); len(msg) > 6 && msg[:6] == "ERROR:" {
		return nil, &windowsUIMenuError{msg: msg[6:]}
	}
	return result, nil
}

// windowsUIMenuError 表示菜单操作失败（如菜单项未找到、无可用模式）。
type windowsUIMenuError struct {
	msg string
}

func (e *windowsUIMenuError) Error() string {
	return "菜单操作失败: " + e.msg
}

// handleWindowsControlClick 是 windows.control.click 的实现。
func handleWindowsControlClick(params map[string]any) (any, error) {
	windowID, err := optionalString(params, "window_id")
	if err != nil {
		return nil, err
	}
	title, err := optionalString(params, "title")
	if err != nil {
		return nil, err
	}
	name, err := optionalString(params, "name")
	if err != nil {
		return nil, err
	}
	automationID, err := optionalString(params, "automation_id")
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsControlClickScript(windowID, title, name, automationID)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsUITimeout)
	if err != nil {
		return nil, err
	}

	result := map[string]any{
		"window_id":     windowID,
		"title":         title,
		"name":          name,
		"automation_id": automationID,
		"output":        trimWindowsOutput(out),
		"tool":          "powershell",
	}
	msg := trimWindowsOutput(out)
	if len(msg) > 6 && msg[:6] == "ERROR:" {
		return nil, &windowsControlError{msg: msg[6:]}
	}
	// 记录实际触发的模式（invoked/selected）。
	if strings.HasPrefix(msg, "OK:invoked") {
		result["clicked"] = "invoked"
	} else if strings.HasPrefix(msg, "OK:selected") {
		result["clicked"] = "selected"
	}
	return result, nil
}

// handleWindowsControlSetText 是 windows.control.set-text 的实现。
func handleWindowsControlSetText(params map[string]any) (any, error) {
	windowID, err := optionalString(params, "window_id")
	if err != nil {
		return nil, err
	}
	title, err := optionalString(params, "title")
	if err != nil {
		return nil, err
	}
	name, err := optionalString(params, "name")
	if err != nil {
		return nil, err
	}
	automationID, err := optionalString(params, "automation_id")
	if err != nil {
		return nil, err
	}
	text, err := requiredString(params, "text")
	if err != nil {
		return nil, err
	}

	script, err := buildWindowsControlSetTextScript(windowID, title, name, automationID, text)
	if err != nil {
		return nil, err
	}

	out, err := runWindowsPowerShellCommand(script, windowsUITimeout)
	if err != nil {
		return nil, err
	}

	result := map[string]any{
		"window_id":     windowID,
		"title":         title,
		"name":          name,
		"automation_id": automationID,
		"text":          text,
		"output":        trimWindowsOutput(out),
		"tool":          "powershell",
	}
	msg := trimWindowsOutput(out)
	if len(msg) > 6 && msg[:6] == "ERROR:" {
		return nil, &windowsControlError{msg: msg[6:]}
	}
	result["text_set"] = true
	return result, nil
}

// windowsControlError 表示控件操作失败（控件未找到、无可用模式等）。
type windowsControlError struct {
	msg string
}

func (e *windowsControlError) Error() string {
	return "控件操作失败: " + e.msg
}
