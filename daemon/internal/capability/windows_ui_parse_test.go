package capability

import (
	"strings"
	"testing"
)

func TestParseWindowsUIMenuPath(t *testing.T) {
	cases := []struct {
		path string
		want []string
	}{
		{"File->Open", []string{"File", "Open"}},
		{"Edit->Copy", []string{"Edit", "Copy"}},
		{"Help", []string{"Help"}},
		{"  File  ->  Open  ", []string{"File", "Open"}},
		{"File->Edit->Preferences->General", []string{"File", "Edit", "Preferences", "General"}},
	}
	for _, c := range cases {
		got, err := parseWindowsUIMenuPath(c.path)
		if err != nil {
			t.Fatalf("path=%q 意外错误: %v", c.path, err)
		}
		if len(got) != len(c.want) {
			t.Errorf("path=%q 段数错误: got %v, want %v", c.path, got, c.want)
			continue
		}
		for i := range got {
			if got[i] != c.want[i] {
				t.Errorf("path=%q 段 %d 错误: got %q, want %q", c.path, i, got[i], c.want[i])
			}
		}
	}

	// 错误情形。
	if _, err := parseWindowsUIMenuPath(""); err == nil {
		t.Error("空 path 应返回错误")
	}
	if _, err := parseWindowsUIMenuPath("File->"); err == nil {
		t.Error("path 以 -> 结尾应返回错误")
	}
	if _, err := parseWindowsUIMenuPath("->File"); err == nil {
		t.Error("path 以 -> 开头应返回错误")
	}
}

func TestBuildWindowsUITreeScript(t *testing.T) {
	// window_id 定位。
	script, err := buildWindowsUITreeScript("0x00010A2C", "", 5, 100)
	if err != nil {
		t.Fatalf("意外错误: %v", err)
	}
	for _, want := range []string{
		"UIAutomationClient",
		"UIAutomationTypes",
		"FromHandle([IntPtr]0x00010A2C)",
		"function Walk",
		"FindAll([System.Windows.Automation.TreeScope]::Children",
	} {
		if !strings.Contains(script, want) {
			t.Errorf("tree 脚本缺少 %q: %s", want, script)
		}
	}
	// 深度/数量限制应写入脚本。
	if !strings.Contains(script, "if ($script:count -ge 100)") {
		t.Errorf("tree 脚本缺少 maxControls 限制: %s", script)
	}
	if !strings.Contains(script, "if ($depth -ge 5)") {
		t.Errorf("tree 脚本缺少 maxDepth 限制: %s", script)
	}

	// title 定位：title 必须经转义，不裸拼。
	title := "记事本'; Remove-Item -Recurse C:\\ -Force; '"
	script, err = buildWindowsUITreeScript("", title, 0, 0)
	if err != nil {
		t.Fatalf("title 定位意外错误: %v", err)
	}
	if !strings.Contains(script, encodePowerShellText(title)) {
		t.Errorf("tree title 未正确转义: %s", script)
	}
	assertNoRawInput(t, script, title)

	// 两者都缺报错。
	if _, err := buildWindowsUITreeScript("", "", 0, 0); err == nil {
		t.Error("window_id 与 title 都缺应返回错误")
	}
}

func TestParseWindowsUITreeText(t *testing.T) {
	out := "0|ControlType.Window|Main Window|main|0|0|800|600\r\n" +
		"1|ControlType.MenuBar|Menu|menuBar|0|0|800|30\r\n" +
		"2|ControlType.MenuItem|File|fileMenu|10|5|50|20\r\n" +
		"ERROR:no-window\r\n" +
		"garbage-line\r\n"
	controls := parseWindowsUITreeText(out)
	if len(controls) != 3 {
		t.Fatalf("解析控件数错误: got %d, want 3", len(controls))
	}
	first := controls[0]
	if first["depth"] != "0" || first["type"] != "ControlType.Window" || first["name"] != "Main Window" {
		t.Errorf("首个控件解析错误: %v", first)
	}
	rect, ok := first["rect"].(map[string]any)
	if !ok {
		t.Fatalf("rect 类型错误: %T", first["rect"])
	}
	if rect["x"] != "0" || rect["width"] != "800" {
		t.Errorf("rect 解析错误: %v", rect)
	}
	// ERROR 与垃圾行被跳过。
	for _, c := range controls {
		if c["name"] == "ERROR:no-window" {
			t.Errorf("ERROR 行不应被解析为控件: %v", c)
		}
	}

	// 空输出返回空列表。
	if got := parseWindowsUITreeText(""); len(got) != 0 {
		t.Errorf("空输出应返回空列表: %v", got)
	}
}

func TestBuildWindowsUIMenuScript(t *testing.T) {
	// window_id + path。
	script, err := buildWindowsUIMenuScript("0x00010A2C", "", "File->Open")
	if err != nil {
		t.Fatalf("意外错误: %v", err)
	}
	for _, want := range []string{
		"UIAutomationClient",
		"File",
		"Open",
		"InvokePattern",
		"ExpandCollapsePattern",
	} {
		if !strings.Contains(script, want) {
			t.Errorf("menu 脚本缺少 %q: %s", want, script)
		}
	}
	// 中间段应 Expand，最后段应 Invoke。
	if !strings.Contains(script, "Expand()") {
		t.Errorf("menu 脚本缺少 Expand: %s", script)
	}
	if !strings.Contains(script, "$p.Invoke()") {
		t.Errorf("menu 脚本缺少 Invoke: %s", script)
	}

	// title + 含注入尝试的 path 段。
	title := "App'; Remove-Item -Recurse C:\\ -Force; '"
	path := "File'; Remove-Item -Recurse C:\\ -Force; '->Open"
	script, err = buildWindowsUIMenuScript("", title, path)
	if err != nil {
		t.Fatalf("意外错误: %v", err)
	}
	// title 与每个 path 段都应转义。
	if !strings.Contains(script, encodePowerShellText(title)) {
		t.Errorf("menu title 未转义: %s", script)
	}
	assertNoRawInput(t, script, title)
	for _, seg := range []string{"File'; Remove-Item -Recurse C:\\ -Force; '", "Open"} {
		assertNoRawInput(t, script, seg)
	}

	// 非法 path 报错。
	if _, err := buildWindowsUIMenuScript("0x1", "", "File->"); err == nil {
		t.Error("非法 path 应返回错误")
	}
	// 两者都缺报错。
	if _, err := buildWindowsUIMenuScript("", "", "File->Open"); err == nil {
		t.Error("window_id 与 title 都缺应返回错误")
	}
}
