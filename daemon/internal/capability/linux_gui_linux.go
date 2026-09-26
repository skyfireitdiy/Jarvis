//go:build linux

package capability

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// linuxGUITimeout 是单次外部 GUI 命令调用的超时时间。
const linuxGUITimeout = 10 * time.Second

// linuxGUIMaxOutputBytes 是外部命令输出保留的最大字节数。
const linuxGUIMaxOutputBytes = 1 << 20 // 1 MiB

// linuxGUIToolHints 记录各工具的安装提示，用于生成可操作的错误信息。
var linuxGUIToolHints = map[string]string{
	"xdotool": "sudo apt install xdotool",
	"wmctrl":  "sudo apt install wmctrl",
	"xclip":   "sudo apt install xclip",
	"xsel":    "sudo apt install xsel",
	"import":  "sudo apt install imagemagick",
	"scrot":   "sudo apt install scrot",
	"grim":    "sudo apt install grim",
}

// registerLinuxGUI 注册 Linux 图形界面相关能力。
//
// 设计取舍：本实现**不直接调用 X11**（那需要 cgo，会破坏 CGO_ENABLED=0
// 交叉编译能力），而是调用系统上已有的命令行工具（xdotool / wmctrl /
// xclip / import 等）。因此这些能力的可用性取决于：
//  1. 存在图形环境（DISPLAY 或 WAYLAND_DISPLAY 非空）；
//  2. 安装了对应的外部命令。
//
// 两者任一不满足时，能力会返回含安装/排查提示的明确错误，而不是静默失败。
func registerLinuxGUI(reg *Registry) {
	_ = reg.Register(Capability{
		Name:        "linux.window.list",
		Description: "列出当前图形环境中的窗口（优先 wmctrl，回退 xdotool）。需要 DISPLAY 与 wmctrl 或 xdotool。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"filter": map[string]any{
					"type":        "string",
					"description": "按窗口标题子串过滤，可选。",
				},
			},
		},
		Handler: handleLinuxWindowList,
	})

	_ = reg.Register(Capability{
		Name:        "linux.window.focus",
		Description: "激活（聚焦）指定窗口。需要 DISPLAY 与 wmctrl 或 xdotool。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"window_id": map[string]any{
					"type":        "string",
					"description": "窗口 ID，如 0x03400007；与 title 至少提供一个。",
				},
				"title": map[string]any{
					"type":        "string",
					"description": "窗口标题（子串匹配），当未提供 window_id 时使用。",
				},
			},
		},
		Handler: handleLinuxWindowFocus,
	})

	_ = reg.Register(Capability{
		Name:        "linux.window.close",
		Description: "关闭指定窗口。需要 DISPLAY 与 wmctrl 或 xdotool。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"window_id": map[string]any{
					"type":        "string",
					"description": "窗口 ID，如 0x03400007。",
				},
			},
			"required": []string{"window_id"},
		},
		Handler: handleLinuxWindowClose,
	})

	_ = reg.Register(Capability{
		Name:        "linux.input.click",
		Description: "在指定屏幕坐标点击鼠标。需要 DISPLAY 与 xdotool。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"x": map[string]any{
					"type":        "integer",
					"description": "屏幕横坐标（像素）。",
				},
				"y": map[string]any{
					"type":        "integer",
					"description": "屏幕纵坐标（像素）。",
				},
				"button": map[string]any{
					"type":        "string",
					"description": "鼠标按键，默认 left；支持 left/right/middle。",
				},
				"count": map[string]any{
					"type":        "integer",
					"description": "点击次数，默认 1。",
				},
			},
			"required": []string{"x", "y"},
		},
		Handler: handleLinuxInputClick,
	})

	_ = reg.Register(Capability{
		Name:        "linux.input.type",
		Description: "向当前聚焦窗口键入文本。需要 DISPLAY 与 xdotool。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"text": map[string]any{
					"type":        "string",
					"description": "要键入的文本。",
				},
				"delay_ms": map[string]any{
					"type":        "integer",
					"description": "每个按键之间的延迟毫秒数，可选。",
				},
			},
			"required": []string{"text"},
		},
		Handler: handleLinuxInputType,
	})

	_ = reg.Register(Capability{
		Name:        "linux.input.keys",
		Description: "向当前聚焦窗口发送按键组合（xdotool 键位语法，如 ctrl+c、Return）。需要 DISPLAY 与 xdotool。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"keys": map[string]any{
					"type":        "string",
					"description": "按键序列，如 ctrl+c、alt+Tab、Return。",
				},
			},
			"required": []string{"keys"},
		},
		Handler: handleLinuxInputKeys,
	})

	_ = reg.Register(Capability{
		Name:        "linux.clipboard.get",
		Description: "读取剪贴板文本（优先 xclip，回退 xsel）。需要 DISPLAY。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type":       "object",
			"properties": map[string]any{},
		},
		Handler: handleLinuxClipboardGet,
	})

	_ = reg.Register(Capability{
		Name:        "linux.clipboard.set",
		Description: "写入剪贴板文本（优先 xclip，回退 xsel）。需要 DISPLAY。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"text": map[string]any{
					"type":        "string",
					"description": "要写入剪贴板的文本。",
				},
			},
			"required": []string{"text"},
		},
		Handler: handleLinuxClipboardSet,
	})

	_ = reg.Register(Capability{
		Name:        "linux.screenshot",
		Description: "截取屏幕并保存到指定路径（优先 import，回退 scrot，Wayland 下回退 grim）。需要 DISPLAY 或 WAYLAND_DISPLAY。",
		Platform:    PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "截图保存的绝对路径。",
				},
				"window_id": map[string]any{
					"type":        "string",
					"description": "只截取指定窗口，可选；仅 import 支持。",
				},
				"format": map[string]any{
					"type":        "string",
					"description": "图片格式，默认 png。",
				},
			},
			"required": []string{"path"},
		},
		Handler: handleLinuxScreenshot,
	})
}

// requireDisplay 检查是否存在图形环境。
func requireDisplay() error {
	if os.Getenv("DISPLAY") != "" || os.Getenv("WAYLAND_DISPLAY") != "" {
		return nil
	}
	return fmt.Errorf("未检测到图形环境（DISPLAY/WAYLAND_DISPLAY 均为空），GUI 能力不可用；" +
		"若守护进程以 systemd 用户服务运行，请确认其能访问当前图形会话")
}

// requireTool 依次探测候选命令，返回第一个可执行文件的绝对路径。
//
// 全部缺失时返回含安装提示的错误，便于调用方直接照做。
func requireTool(names ...string) (string, error) {
	for _, name := range names {
		if path, err := exec.LookPath(name); err == nil {
			return path, nil
		}
	}

	hints := make([]string, 0, len(names))
	for _, name := range names {
		if hint, ok := linuxGUIToolHints[name]; ok {
			hints = append(hints, fmt.Sprintf("%s（安装：%s）", name, hint))
		} else {
			hints = append(hints, name)
		}
	}
	return "", fmt.Errorf("未找到可用命令 %s，请先安装其中之一", strings.Join(hints, " 或 "))
}

// runGUICommand 执行外部 GUI 命令并返回标准输出。
//
// 统一带超时；失败时把 stderr 内容带进错误信息，便于排查。
func runGUICommand(stdin string, path string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), linuxGUITimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, path, args...)
	if stdin != "" {
		cmd.Stdin = strings.NewReader(stdin)
	}

	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return "", fmt.Errorf("执行 %s 超时（%s）", path, linuxGUITimeout)
		}
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			stderr := strings.TrimSpace(string(exitErr.Stderr))
			if stderr != "" {
				return "", fmt.Errorf("执行 %s 失败: %s", path, stderr)
			}
		}
		return "", fmt.Errorf("执行 %s 失败: %w", path, err)
	}

	if len(out) > linuxGUIMaxOutputBytes {
		out = out[:linuxGUIMaxOutputBytes]
	}
	return string(out), nil
}

// handleLinuxWindowList 是 linux.window.list 的实现。
func handleLinuxWindowList(params map[string]any) (any, error) {
	if err := requireDisplay(); err != nil {
		return nil, err
	}

	filter, err := optionalString(params, "filter")
	if err != nil {
		return nil, err
	}

	tool, err := requireTool("wmctrl", "xdotool")
	if err != nil {
		return nil, err
	}

	var windows []map[string]any
	if strings.HasSuffix(tool, "wmctrl") {
		out, err := runGUICommand("", tool, "-lp")
		if err != nil {
			return nil, err
		}
		windows = parseWmctrlWindowList(out)
	} else {
		out, err := runGUICommand("", tool, "search", "--name", filter)
		if err != nil {
			// xdotool 在无匹配窗口时返回非零退出码，视为空结果而非错误。
			if strings.Contains(err.Error(), "失败") && filter != "" {
				windows = nil
			} else {
				return nil, err
			}
		} else {
			windows = parseXdotoolWindowList(out, tool)
		}
	}

	if filter != "" {
		filtered := make([]map[string]any, 0, len(windows))
		lower := strings.ToLower(filter)
		for _, w := range windows {
			title, _ := w["title"].(string)
			if strings.Contains(strings.ToLower(title), lower) {
				filtered = append(filtered, w)
			}
		}
		windows = filtered
	}

	return map[string]any{
		"windows": windows,
		"count":   len(windows),
		"tool":    tool,
	}, nil
}

// handleLinuxWindowFocus 是 linux.window.focus 的实现。
func handleLinuxWindowFocus(params map[string]any) (any, error) {
	if err := requireDisplay(); err != nil {
		return nil, err
	}

	windowID, err := optionalString(params, "window_id")
	if err != nil {
		return nil, err
	}
	title, err := optionalString(params, "title")
	if err != nil {
		return nil, err
	}
	if windowID == "" && title == "" {
		return nil, fmt.Errorf("参数 window_id 与 title 至少需要提供一个")
	}

	tool, err := requireTool("wmctrl", "xdotool")
	if err != nil {
		return nil, err
	}

	var out string
	if strings.HasSuffix(tool, "wmctrl") {
		if windowID != "" {
			out, err = runGUICommand("", tool, "-i", "-a", windowID)
		} else {
			out, err = runGUICommand("", tool, "-a", title)
		}
	} else {
		if windowID == "" {
			res, searchErr := runGUICommand("", tool, "search", "--name", title)
			if searchErr != nil {
				return nil, fmt.Errorf("按标题 %q 查找窗口失败: %w", title, searchErr)
			}
			ids := strings.Fields(strings.TrimSpace(res))
			if len(ids) == 0 {
				return nil, fmt.Errorf("未找到标题匹配 %q 的窗口", title)
			}
			windowID = ids[0]
		}
		out, err = runGUICommand("", tool, "windowactivate", windowID)
	}
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"window_id": windowID,
		"title":     title,
		"focused":   true,
		"output":    strings.TrimSpace(out),
		"tool":      tool,
	}, nil
}

// handleLinuxWindowClose 是 linux.window.close 的实现。
func handleLinuxWindowClose(params map[string]any) (any, error) {
	if err := requireDisplay(); err != nil {
		return nil, err
	}

	windowID, err := requiredString(params, "window_id")
	if err != nil {
		return nil, err
	}

	tool, err := requireTool("wmctrl", "xdotool")
	if err != nil {
		return nil, err
	}

	var out string
	if strings.HasSuffix(tool, "wmctrl") {
		out, err = runGUICommand("", tool, "-i", "-c", windowID)
	} else {
		out, err = runGUICommand("", tool, "windowclose", windowID)
	}
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"window_id": windowID,
		"closed":    true,
		"output":    strings.TrimSpace(out),
		"tool":      tool,
	}, nil
}

// handleLinuxInputClick 是 linux.input.click 的实现。
func handleLinuxInputClick(params map[string]any) (any, error) {
	if err := requireDisplay(); err != nil {
		return nil, err
	}

	// x/y 允许为 0（屏幕左上角），因此不能复用 optionalInt 的默认值语义，
	// 需要显式判断是否提供了该参数。
	x, err := requiredInt(params, "x")
	if err != nil {
		return nil, err
	}
	y, err := requiredInt(params, "y")
	if err != nil {
		return nil, err
	}

	button, err := optionalString(params, "button")
	if err != nil {
		return nil, err
	}
	if button == "" {
		button = "left"
	}
	switch button {
	case "left", "right", "middle":
	default:
		return nil, fmt.Errorf("参数 button 不支持 %q，允许值: left、right、middle", button)
	}

	count, err := optionalInt(params, "count", 1)
	if err != nil {
		return nil, err
	}
	if count <= 0 {
		return nil, fmt.Errorf("参数 count 必须为正整数，实际 %d", count)
	}

	tool, err := requireTool("xdotool")
	if err != nil {
		return nil, err
	}

	if _, err := runGUICommand("", tool, "mousemove", strconv.Itoa(x), strconv.Itoa(y)); err != nil {
		return nil, err
	}
	out, err := runGUICommand("", tool, "click", "--repeat", strconv.Itoa(count), button)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"x":      x,
		"y":      y,
		"button": button,
		"count":  count,
		"output": strings.TrimSpace(out),
		"tool":   tool,
	}, nil
}

// handleLinuxInputType 是 linux.input.type 的实现。
func handleLinuxInputType(params map[string]any) (any, error) {
	if err := requireDisplay(); err != nil {
		return nil, err
	}

	text, err := requiredString(params, "text")
	if err != nil {
		return nil, err
	}

	delayMS, err := optionalInt(params, "delay_ms", 0)
	if err != nil {
		return nil, err
	}
	if delayMS < 0 {
		return nil, fmt.Errorf("参数 delay_ms 不能为负数，实际 %d", delayMS)
	}

	tool, err := requireTool("xdotool")
	if err != nil {
		return nil, err
	}

	args := []string{"type"}
	if delayMS > 0 {
		args = append(args, "--delay", strconv.Itoa(delayMS))
	}
	// 用 -- 分隔，防止 text 以 "-" 开头时被 xdotool 当作选项。
	args = append(args, "--", text)

	out, err := runGUICommand("", tool, args...)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"typed":  text,
		"output": strings.TrimSpace(out),
		"tool":   tool,
	}, nil
}

// handleLinuxInputKeys 是 linux.input.keys 的实现。
func handleLinuxInputKeys(params map[string]any) (any, error) {
	if err := requireDisplay(); err != nil {
		return nil, err
	}

	keys, err := requiredString(params, "keys")
	if err != nil {
		return nil, err
	}

	tool, err := requireTool("xdotool")
	if err != nil {
		return nil, err
	}

	out, err := runGUICommand("", tool, "key", "--", keys)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"keys":   keys,
		"output": strings.TrimSpace(out),
		"tool":   tool,
	}, nil
}

// handleLinuxClipboardGet 是 linux.clipboard.get 的实现。
func handleLinuxClipboardGet(params map[string]any) (any, error) {
	if err := requireDisplay(); err != nil {
		return nil, err
	}

	tool, err := requireTool("xclip", "xsel")
	if err != nil {
		return nil, err
	}

	var out string
	if strings.HasSuffix(tool, "xclip") {
		out, err = runGUICommand("", tool, "-selection", "clipboard", "-o")
	} else {
		out, err = runGUICommand("", tool, "-b", "-o")
	}
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"text": out,
		"tool": tool,
	}, nil
}

// handleLinuxClipboardSet 是 linux.clipboard.set 的实现。
func handleLinuxClipboardSet(params map[string]any) (any, error) {
	if err := requireDisplay(); err != nil {
		return nil, err
	}

	// 允许写入空字符串以清空剪贴板，因此不用 requiredString。
	raw, ok := params["text"]
	if !ok || raw == nil {
		return nil, fmt.Errorf("缺少必填参数 text")
	}
	text, ok := raw.(string)
	if !ok {
		return nil, fmt.Errorf("参数 text 必须是字符串，实际 %T", raw)
	}

	tool, err := requireTool("xclip", "xsel")
	if err != nil {
		return nil, err
	}

	var out string
	if strings.HasSuffix(tool, "xclip") {
		out, err = runGUICommand(text, tool, "-selection", "clipboard")
	} else {
		out, err = runGUICommand(text, tool, "-b", "-i")
	}
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"written_bytes": len(text),
		"output":        strings.TrimSpace(out),
		"tool":          tool,
	}, nil
}

// handleLinuxScreenshot 是 linux.screenshot 的实现。
func handleLinuxScreenshot(params map[string]any) (any, error) {
	if err := requireDisplay(); err != nil {
		return nil, err
	}

	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}

	windowID, err := optionalString(params, "window_id")
	if err != nil {
		return nil, err
	}

	format, err := optionalString(params, "format")
	if err != nil {
		return nil, err
	}
	if format == "" {
		format = "png"
	}
	switch format {
	case "png", "jpg", "jpeg":
	default:
		return nil, fmt.Errorf("参数 format 不支持 %q，允许值: png、jpg、jpeg", format)
	}

	tool, err := requireTool("import", "scrot", "grim")
	if err != nil {
		return nil, err
	}

	var out string
	switch {
	case strings.HasSuffix(tool, "import"):
		args := []string{"-window", "root"}
		if windowID != "" {
			args = []string{"-window", windowID}
		}
		args = append(args, path)
		out, err = runGUICommand("", tool, args...)
	case strings.HasSuffix(tool, "scrot"):
		out, err = runGUICommand("", tool, path)
	default: // grim
		out, err = runGUICommand("", tool, path)
	}
	if err != nil {
		return nil, err
	}

	info, statErr := os.Stat(path)
	if statErr != nil {
		return nil, fmt.Errorf("截图命令已执行但未找到输出文件 %s: %w", path, statErr)
	}

	return map[string]any{
		"path":       path,
		"size_bytes": info.Size(),
		"format":     format,
		"output":     strings.TrimSpace(out),
		"tool":       tool,
	}, nil
}

// requiredInt 读取必填整数参数。
//
// 与 optionalInt 的区别：缺失时返回错误而不是默认值，
// 用于 x/y 这类「0 是合法值、不能与缺失混淆」的参数。
func requiredInt(params map[string]any, key string) (int, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return 0, fmt.Errorf("缺少必填参数 %s", key)
	}
	switch n := v.(type) {
	case int:
		return n, nil
	case int64:
		return int(n), nil
	case float64:
		if n != float64(int(n)) {
			return 0, fmt.Errorf("参数 %s 必须是整数，实际 %v", key, n)
		}
		return int(n), nil
	default:
		return 0, fmt.Errorf("参数 %s 必须是整数，实际 %T", key, v)
	}
}

// parseWmctrlWindowList 解析 `wmctrl -lp` 的输出。
//
// 每行形如：
//
//	0x03400007  0 12345  hostname Window Title
//
// 字段依次为：窗口 ID、桌面号、PID、主机名、标题（可含空格）。
func parseWmctrlWindowList(out string) []map[string]any {
	windows := make([]map[string]any, 0, 16)
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 5 {
			continue
		}
		windows = append(windows, map[string]any{
			"window_id": fields[0],
			"desktop":   fields[1],
			"pid":       fields[2],
			"hostname":  fields[3],
			"title":     strings.Join(fields[4:], " "),
		})
	}
	return windows
}

// parseXdotoolWindowList 解析 `xdotool search` 的窗口 ID 列表并补齐标题。
func parseXdotoolWindowList(out string, tool string) []map[string]any {
	windows := make([]map[string]any, 0, 16)
	for _, id := range strings.Fields(strings.TrimSpace(out)) {
		entry := map[string]any{
			"window_id": id,
			"title":     "",
		}
		if title, err := runGUICommand("", tool, "getwindowname", id); err == nil {
			entry["title"] = strings.TrimSpace(title)
		}
		windows = append(windows, entry)
	}
	return windows
}
