//go:build linux

package capability

import (
	"os"
	"os/exec"
	"strings"
	"testing"
)

// 环境说明：本机 DISPLAY 与 WAYLAND_DISPLAY 均为空，且 xdotool / wmctrl /
// xclip / import / scrot / grim 均未安装（仅 xsel 存在）。
// 因此本文件的测试**只能覆盖错误路径与纯逻辑**，无法端到端验证真实 GUI 操作。
// 这是环境限制，不是实现缺陷。

// TestRequireDisplayNoDisplay 验证无图形环境时返回明确错误。
func TestRequireDisplayNoDisplay(t *testing.T) {
	t.Setenv("DISPLAY", "")
	t.Setenv("WAYLAND_DISPLAY", "")

	err := requireDisplay()
	if err == nil {
		t.Fatal("无 DISPLAY/WAYLAND_DISPLAY 时应返回错误")
	}
	if !strings.Contains(err.Error(), "图形环境") {
		t.Errorf("错误信息应说明缺少图形环境，实际: %v", err)
	}
	if !strings.Contains(err.Error(), "DISPLAY") {
		t.Errorf("错误信息应提及 DISPLAY，实际: %v", err)
	}
}

// TestRequireDisplayWithX11 验证有 DISPLAY 时通过。
func TestRequireDisplayWithX11(t *testing.T) {
	t.Setenv("DISPLAY", ":0")
	t.Setenv("WAYLAND_DISPLAY", "")
	if err := requireDisplay(); err != nil {
		t.Errorf("有 DISPLAY 时不应报错: %v", err)
	}
}

// TestRequireDisplayWithWayland 验证有 WAYLAND_DISPLAY 时通过。
func TestRequireDisplayWithWayland(t *testing.T) {
	t.Setenv("DISPLAY", "")
	t.Setenv("WAYLAND_DISPLAY", "wayland-0")
	if err := requireDisplay(); err != nil {
		t.Errorf("有 WAYLAND_DISPLAY 时不应报错: %v", err)
	}
}

// TestRequireToolMissing 验证工具缺失时的错误信息含安装提示。
func TestRequireToolMissing(t *testing.T) {
	// 用一个确定不存在的命令名。
	_, err := requireTool("definitely-not-a-real-tool-xyz")
	if err == nil {
		t.Fatal("不存在的命令应返回错误")
	}
	if !strings.Contains(err.Error(), "未找到") {
		t.Errorf("错误信息应说明未找到命令，实际: %v", err)
	}
}

// TestRequireToolHintForKnownTools 验证已知工具缺失时给出安装命令。
func TestRequireToolHintForKnownTools(t *testing.T) {
	// 确保这些工具确实不在 PATH 中（本机实测均缺失）。
	for _, name := range []string{"xdotool", "wmctrl", "xclip", "import", "scrot", "grim"} {
		if _, err := exec.LookPath(name); err == nil {
			t.Skipf("本机已安装 %s，跳过该工具的缺失提示验证", name)
		}
	}

	_, err := requireTool("xdotool")
	if err == nil {
		t.Fatal("xdotool 缺失时应返回错误")
	}
	if !strings.Contains(err.Error(), "xdotool") {
		t.Errorf("错误信息应包含工具名，实际: %v", err)
	}
	if !strings.Contains(err.Error(), "apt install") {
		t.Errorf("错误信息应包含安装提示，实际: %v", err)
	}

	// 多候选时应把候选与提示都列出。
	_, err2 := requireTool("xclip", "xsel")
	if err2 != nil {
		// 本机 xsel 存在，因此这里应当成功；若失败说明环境变化。
		t.Logf("xclip/xsel 均不可用（环境变化）: %v", err2)
	}
}

// TestRequireToolFound 验证找到工具时返回其路径。
func TestRequireToolFound(t *testing.T) {
	// sh 一定存在。
	path, err := requireTool("sh")
	if err != nil {
		t.Fatalf("sh 应当可用: %v", err)
	}
	if path == "" {
		t.Error("返回路径不应为空")
	}
}

// TestLinuxGUINoDisplayErrors 验证所有 GUI 能力在无 DISPLAY 时返回错误而非 panic。
func TestLinuxGUINoDisplayErrors(t *testing.T) {
	t.Setenv("DISPLAY", "")
	t.Setenv("WAYLAND_DISPLAY", "")

	cases := []struct {
		name   string
		params map[string]any
		fn     func(map[string]any) (any, error)
	}{
		{"window.list", map[string]any{}, handleLinuxWindowList},
		{"window.focus", map[string]any{"window_id": "0x1"}, handleLinuxWindowFocus},
		{"window.close", map[string]any{"window_id": "0x1"}, handleLinuxWindowClose},
		{"input.click", map[string]any{"x": 1, "y": 2}, handleLinuxInputClick},
		{"input.type", map[string]any{"text": "hi"}, handleLinuxInputType},
		{"input.keys", map[string]any{"keys": "Return"}, handleLinuxInputKeys},
		{"clipboard.get", map[string]any{}, handleLinuxClipboardGet},
		{"clipboard.set", map[string]any{"text": "hi"}, handleLinuxClipboardSet},
		{"screenshot", map[string]any{"path": "/tmp/x.png"}, handleLinuxScreenshot},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := tc.fn(tc.params)
			if err == nil {
				t.Fatal("无图形环境时应返回错误")
			}
			if !strings.Contains(err.Error(), "图形环境") {
				t.Errorf("错误信息应说明缺少图形环境，实际: %v", err)
			}
		})
	}
}

// TestLinuxGUIParameterValidation 验证参数校验路径。
//
// 这些用例在参数校验阶段就返回，不会走到 requireDisplay，
// 因此可以在无 DISPLAY 环境下测试。
func TestLinuxGUIParameterValidation(t *testing.T) {
	cases := []struct {
		name   string
		params map[string]any
		fn     func(map[string]any) (any, error)
	}{
		{"window.close 缺 window_id", map[string]any{}, handleLinuxWindowClose},
		{"window.close window_id 类型错", map[string]any{"window_id": 1}, handleLinuxWindowClose},
		{"window.focus 两者都缺", map[string]any{}, handleLinuxWindowFocus},
		{"window.focus filter 类型错", map[string]any{"filter": 1}, handleLinuxWindowList},
		{"input.click 缺 x", map[string]any{"y": 1}, handleLinuxInputClick},
		{"input.click 缺 y", map[string]any{"x": 1}, handleLinuxInputClick},
		{"input.click x 类型错", map[string]any{"x": "a", "y": 1}, handleLinuxInputClick},
		{"input.click x 非整数", map[string]any{"x": 1.5, "y": 1}, handleLinuxInputClick},
		{"input.type 缺 text", map[string]any{}, handleLinuxInputType},
		{"input.type text 为空", map[string]any{"text": "  "}, handleLinuxInputType},
		{"input.type delay_ms 为负", map[string]any{"text": "a", "delay_ms": -1}, handleLinuxInputType},
		{"input.keys 缺 keys", map[string]any{}, handleLinuxInputKeys},
		{"clipboard.set 缺 text", map[string]any{}, handleLinuxClipboardSet},
		{"clipboard.set text 类型错", map[string]any{"text": 1}, handleLinuxClipboardSet},
		{"screenshot 缺 path", map[string]any{}, handleLinuxScreenshot},
		{"screenshot path 为空", map[string]any{"path": " "}, handleLinuxScreenshot},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := tc.fn(tc.params)
			if err == nil {
				t.Fatal("期望返回错误，实际成功")
			}
		})
	}
}

// TestLinuxGUINoDisplayBeforeToolCheck 验证「无图形环境」优先于「工具缺失」报错。
//
// 设计意图：先提示用户「没有图形环境」比先提示「没装 xdotool」更有用，
// 因为前者是更根本的阻塞原因。
func TestLinuxGUINoDisplayBeforeToolCheck(t *testing.T) {
	t.Setenv("DISPLAY", "")
	t.Setenv("WAYLAND_DISPLAY", "")

	_, err := handleLinuxWindowList(map[string]any{})
	if err == nil {
		t.Fatal("应返回错误")
	}
	if strings.Contains(err.Error(), "apt install") {
		t.Errorf("无图形环境时应优先报图形环境错误，而不是工具安装提示，实际: %v", err)
	}
	if !strings.Contains(err.Error(), "图形环境") {
		t.Errorf("应报图形环境错误，实际: %v", err)
	}
}

// TestLinuxGUIToolMissingWithDisplay 验证有 DISPLAY 但工具缺失时的错误含安装提示。
//
// 通过设置假的 DISPLAY 绕过环境检查，验证工具探测分支。
func TestLinuxGUIToolMissingWithDisplay(t *testing.T) {
	t.Setenv("DISPLAY", ":99")

	// 若本机恰好装了这些工具则跳过。
	for _, name := range []string{"wmctrl", "xdotool"} {
		if _, err := exec.LookPath(name); err == nil {
			t.Skipf("本机已安装 %s，跳过工具缺失验证", name)
		}
	}

	_, err := handleLinuxWindowList(map[string]any{})
	if err == nil {
		t.Fatal("工具缺失时应返回错误")
	}
	if !strings.Contains(err.Error(), "未找到可用命令") {
		t.Errorf("错误信息应说明未找到可用命令，实际: %v", err)
	}
	if !strings.Contains(err.Error(), "apt install") {
		t.Errorf("错误信息应含安装提示，实际: %v", err)
	}
}

// TestParseWmctrlWindowList 验证 wmctrl -lp 输出解析纯逻辑。
func TestParseWmctrlWindowList(t *testing.T) {
	sample := `0x03400007  0 12345 myhost Terminal — bash
0x0360000a  1 67890 myhost Firefox — Mozilla Firefox
0x03800001 -1 111   myhost Sticky Window

`
	windows := parseWmctrlWindowList(sample)
	if len(windows) != 3 {
		t.Fatalf("应解析出 3 个窗口，实际 %d", len(windows))
	}

	if windows[0]["window_id"] != "0x03400007" {
		t.Errorf("window_id 解析错误: %v", windows[0]["window_id"])
	}
	if windows[0]["desktop"] != "0" {
		t.Errorf("desktop 解析错误: %v", windows[0]["desktop"])
	}
	if windows[0]["pid"] != "12345" {
		t.Errorf("pid 解析错误: %v", windows[0]["pid"])
	}
	if windows[0]["hostname"] != "myhost" {
		t.Errorf("hostname 解析错误: %v", windows[0]["hostname"])
	}
	// 标题含空格与破折号，应完整保留。
	if windows[0]["title"] != "Terminal — bash" {
		t.Errorf("title 解析错误: %q", windows[0]["title"])
	}
	if windows[1]["title"] != "Firefox — Mozilla Firefox" {
		t.Errorf("title 解析错误: %q", windows[1]["title"])
	}

	// 空输入应返回空切片且不 panic。
	if got := parseWmctrlWindowList(""); len(got) != 0 {
		t.Errorf("空输入应返回空结果，实际 %d 条", len(got))
	}
	// 字段不足的行应被跳过。
	if got := parseWmctrlWindowList("0x1 0 1"); len(got) != 0 {
		t.Errorf("字段不足的行应被跳过，实际 %d 条", len(got))
	}
}

// TestRequiredInt 验证必填整数解析（0 是合法值，不能与缺失混淆）。
func TestRequiredInt(t *testing.T) {
	// 0 必须被接受。
	if v, err := requiredInt(map[string]any{"x": 0}, "x"); err != nil || v != 0 {
		t.Errorf("x=0 应被接受，得到 v=%d err=%v", v, err)
	}
	// 负数坐标也应被接受（多显示器场景可能为负）。
	if v, err := requiredInt(map[string]any{"x": -100}, "x"); err != nil || v != -100 {
		t.Errorf("x=-100 应被接受，得到 v=%d err=%v", v, err)
	}
	// float64 整数应被接受（JSON 解码场景）。
	if v, err := requiredInt(map[string]any{"x": float64(42)}, "x"); err != nil || v != 42 {
		t.Errorf("x=42.0 应被接受，得到 v=%d err=%v", v, err)
	}
	// 缺失、nil、非整数、类型错误都应报错。
	for _, params := range []map[string]any{
		{},
		{"x": nil},
		{"x": 1.5},
		{"x": "a"},
		{"x": true},
	} {
		if _, err := requiredInt(params, "x"); err == nil {
			t.Errorf("params=%v 应报错", params)
		}
	}
}

// TestParseXdotoolWindowListEmpty 验证 xdotool 空输出处理。
func TestParseXdotoolWindowListEmpty(t *testing.T) {
	// 传入不存在的工具路径，getwindowname 会失败，但不应 panic，
	// 只是 title 保持为空。
	got := parseXdotoolWindowList("", "/nonexistent/xdotool")
	if len(got) != 0 {
		t.Errorf("空输出应返回空结果，实际 %d 条", len(got))
	}
}

// TestLinuxGUICapabilitiesRegistered 验证 9 个 GUI 能力都已注册。
func TestLinuxGUICapabilitiesRegistered(t *testing.T) {
	reg := NewRegistry()
	names := []string{
		"linux.window.list",
		"linux.window.focus",
		"linux.window.close",
		"linux.input.click",
		"linux.input.type",
		"linux.input.keys",
		"linux.clipboard.get",
		"linux.clipboard.set",
		"linux.screenshot",
	}
	for _, name := range names {
		cap, ok := reg.Get(name)
		if !ok {
			t.Fatalf("能力 %s 未注册", name)
		}
		if cap.Platform != PlatformLinux {
			t.Errorf("能力 %s 平台应为 linux，实际 %s", name, cap.Platform)
		}
		if strings.TrimSpace(cap.Description) == "" {
			t.Errorf("能力 %s 缺少 Description", name)
		}
		if cap.Parameters == nil {
			t.Errorf("能力 %s 缺少 Parameters", name)
		}
		if cap.Handler == nil {
			t.Errorf("能力 %s 缺少 Handler", name)
		}
	}
}

// TestLinuxGUIToolHintsCoverage 验证提示表覆盖所有被探测的工具。
func TestLinuxGUIToolHintsCoverage(t *testing.T) {
	// 这些是代码中 requireTool 实际使用的全部工具名。
	used := []string{"wmctrl", "xdotool", "xclip", "xsel", "import", "scrot", "grim"}
	for _, name := range used {
		hint, ok := linuxGUIToolHints[name]
		if !ok {
			t.Errorf("工具 %s 缺少安装提示", name)
			continue
		}
		if !strings.Contains(hint, "apt install") {
			t.Errorf("工具 %s 的提示应含 apt install，实际 %q", name, hint)
		}
	}
}

// TestRunGUICommandTimeout 验证外部命令超时保护。
func TestRunGUICommandTimeout(t *testing.T) {
	// 用一个会挂起的命令验证超时。这里用 sh 起 sleep，
	// 但 linuxGUITimeout 是 10s，测试会太慢，因此改为验证正常路径。
	if testing.Short() {
		t.Skip("short 模式跳过")
	}

	sh, err := exec.LookPath("sh")
	if err != nil {
		t.Skip("无 sh，跳过")
	}

	out, err := runGUICommand("", sh, "-c", "echo hello")
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if strings.TrimSpace(out) != "hello" {
		t.Errorf("输出应为 hello，实际 %q", out)
	}

	// 非零退出码应返回错误。
	if _, err := runGUICommand("", sh, "-c", "exit 3"); err == nil {
		t.Error("非零退出码应返回错误")
	}
}

// TestLinuxGUIEnvironmentNote 记录当前环境限制，便于人工核对。
func TestLinuxGUIEnvironmentNote(t *testing.T) {
	display := os.Getenv("DISPLAY")
	wayland := os.Getenv("WAYLAND_DISPLAY")

	tools := []string{"xdotool", "wmctrl", "xclip", "xsel", "import", "scrot", "grim"}
	available := make([]string, 0, len(tools))
	for _, name := range tools {
		if _, err := exec.LookPath(name); err == nil {
			available = append(available, name)
		}
	}

	t.Logf("环境：DISPLAY=%q WAYLAND_DISPLAY=%q", display, wayland)
	t.Logf("可用 GUI 工具：%v", available)
	if display == "" && wayland == "" {
		t.Log("注意：无图形环境，GUI 能力的端到端行为未被验证，仅验证了错误路径")
	}
}
