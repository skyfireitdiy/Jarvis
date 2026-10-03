package capability

import (
	"strings"
	"testing"
)

// 断言脚本中不出现未转义的注入风险：用户输入不应以裸字符串形式拼进脚本。
// 所有用户输入都必须经 encodePowerShellText 转义为单引号字面量。
func assertNoRawInput(t *testing.T, script, input string) {
	t.Helper()
	if input == "" {
		return
	}
	if strings.Contains(script, input) && !strings.Contains(script, encodePowerShellText(input)) {
		t.Errorf("脚本包含未转义的用户输入 %q: %s", input, script)
	}
}

func TestBuildWindowsConfigThemeScript(t *testing.T) {
	cases := []struct {
		mode string
		want string // 期望脚本包含的子串
	}{
		{"dark", "AppsUseLightTheme -Value 0"},
		{"light", "AppsUseLightTheme -Value 1"},
		{"toggle", "$v = if ($p.AppsUseLightTheme -eq 0)"},
	}
	for _, c := range cases {
		script, err := buildWindowsConfigThemeScript(c.mode)
		if err != nil {
			t.Fatalf("mode=%q 意外错误: %v", c.mode, err)
		}
		if !strings.Contains(script, c.want) {
			t.Errorf("mode=%q 脚本缺少 %q，实际: %s", c.mode, c.want, script)
		}
	}

	if _, err := buildWindowsConfigThemeScript("invalid"); err == nil {
		t.Error("非法 mode 应返回错误")
	}
}

func TestBuildWindowsConfigPowerPlanScript(t *testing.T) {
	// list 无需 plan_id。
	script, err := buildWindowsConfigPowerPlanScript("list", "")
	if err != nil {
		t.Fatalf("list 意外错误: %v", err)
	}
	if !strings.Contains(script, "powercfg /list") {
		t.Errorf("list 脚本缺少 powercfg /list: %s", script)
	}

	// set 需要 plan_id，且经转义。
	planID := "381b4222-f694-41f0-9685-ff5bb260df2e"
	script, err = buildWindowsConfigPowerPlanScript("set", planID)
	if err != nil {
		t.Fatalf("set 意外错误: %v", err)
	}
	if !strings.Contains(script, "powercfg /setactive "+encodePowerShellText(planID)) {
		t.Errorf("set 脚本未正确转义 plan_id: %s", script)
	}
	assertNoRawInput(t, script, planID)

	// set 缺 plan_id 报错。
	if _, err := buildWindowsConfigPowerPlanScript("set", ""); err == nil {
		t.Error("set 缺 plan_id 应返回错误")
	}

	// 非法 action。
	if _, err := buildWindowsConfigPowerPlanScript("bogus", ""); err == nil {
		t.Error("非法 action 应返回错误")
	}
}

func TestBuildWindowsConfigProxyScript(t *testing.T) {
	// get。
	script, err := buildWindowsConfigProxyScript("get", "", "")
	if err != nil {
		t.Fatalf("get 意外错误: %v", err)
	}
	if !strings.Contains(script, "ProxyEnable") {
		t.Errorf("get 脚本缺少 ProxyEnable: %s", script)
	}

	// disable。
	script, err = buildWindowsConfigProxyScript("disable", "", "")
	if err != nil {
		t.Fatalf("disable 意外错误: %v", err)
	}
	if !strings.Contains(script, "ProxyEnable -Value 0") {
		t.Errorf("disable 脚本未设 ProxyEnable=0: %s", script)
	}

	// enable 默认地址。
	script, err = buildWindowsConfigProxyScript("enable", "", "")
	if err != nil {
		t.Fatalf("enable 意外错误: %v", err)
	}
	if !strings.Contains(script, encodePowerShellText("127.0.0.1:7890")) {
		t.Errorf("enable 脚本缺少默认代理地址: %s", script)
	}

	// set 需要 server，且 server/bypass 经转义（含单引号注入尝试）。
	server := "127.0.0.1:7890'; Remove-Item -Recurse C:\\ -Force; '"
	bypass := "localhost;192.168.*"
	script, err = buildWindowsConfigProxyScript("set", server, bypass)
	if err != nil {
		t.Fatalf("set 意外错误: %v", err)
	}
	if !strings.Contains(script, encodePowerShellText(server)) {
		t.Errorf("set 脚本未正确转义 server: %s", script)
	}
	if !strings.Contains(script, encodePowerShellText(bypass)) {
		t.Errorf("set 脚本未正确转义 bypass: %s", script)
	}
	assertNoRawInput(t, script, server)
	assertNoRawInput(t, script, bypass)

	// set 缺 server 报错。
	if _, err := buildWindowsConfigProxyScript("set", "", ""); err == nil {
		t.Error("set 缺 server 应返回错误")
	}

	// 非法 action。
	if _, err := buildWindowsConfigProxyScript("bogus", "", ""); err == nil {
		t.Error("非法 action 应返回错误")
	}
}

func TestBuildWindowsConfigScreenTimeoutScript(t *testing.T) {
	// get。
	script, err := buildWindowsConfigScreenTimeoutScript("get", 0)
	if err != nil {
		t.Fatalf("get 意外错误: %v", err)
	}
	if !strings.Contains(script, "powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE") {
		t.Errorf("get 脚本错误: %s", script)
	}

	// set 正常。
	script, err = buildWindowsConfigScreenTimeoutScript("set", 10)
	if err != nil {
		t.Fatalf("set 意外错误: %v", err)
	}
	if !strings.Contains(script, "monitor-timeout-ac 10") || !strings.Contains(script, "monitor-timeout-dc 10") {
		t.Errorf("set 脚本错误: %s", script)
	}

	// set 负数报错。
	if _, err := buildWindowsConfigScreenTimeoutScript("set", -1); err == nil {
		t.Error("set 负 minutes 应返回错误")
	}

	// 非法 action。
	if _, err := buildWindowsConfigScreenTimeoutScript("bogus", 0); err == nil {
		t.Error("非法 action 应返回错误")
	}
}

func TestBuildWindowsConfigRemoteDesktopScript(t *testing.T) {
	// get。
	script, err := buildWindowsConfigRemoteDesktopScript("get")
	if err != nil {
		t.Fatalf("get 意外错误: %v", err)
	}
	if !strings.Contains(script, "fDenyTSConnections") {
		t.Errorf("get 脚本错误: %s", script)
	}

	// enable 设 0。
	script, err = buildWindowsConfigRemoteDesktopScript("enable")
	if err != nil {
		t.Fatalf("enable 意外错误: %v", err)
	}
	if !strings.Contains(script, "fDenyTSConnections -Value 0") {
		t.Errorf("enable 脚本错误: %s", script)
	}

	// disable 设 1。
	script, err = buildWindowsConfigRemoteDesktopScript("disable")
	if err != nil {
		t.Fatalf("disable 意外错误: %v", err)
	}
	if !strings.Contains(script, "fDenyTSConnections -Value 1") {
		t.Errorf("disable 脚本错误: %s", script)
	}

	// 非法 action。
	if _, err := buildWindowsConfigRemoteDesktopScript("bogus"); err == nil {
		t.Error("非法 action 应返回错误")
	}
}

func TestBuildWindowsConfigStartupScript(t *testing.T) {
	// list。
	script, err := buildWindowsConfigStartupScript("list", "")
	if err != nil {
		t.Fatalf("list 意外错误: %v", err)
	}
	if !strings.Contains(script, "Get-ChildItem") {
		t.Errorf("list 脚本错误: %s", script)
	}

	// disable 需 name 且经转义（含注入尝试）。
	name := "myapp.lnk'; Remove-Item -Recurse C:\\ -Force; '"
	script, err = buildWindowsConfigStartupScript("disable", name)
	if err != nil {
		t.Fatalf("disable 意外错误: %v", err)
	}
	if !strings.Contains(script, encodePowerShellText(name)) {
		t.Errorf("disable 脚本未正确转义 name: %s", script)
	}
	assertNoRawInput(t, script, name)

	// enable 需 name。
	script, err = buildWindowsConfigStartupScript("enable", "myapp.lnk")
	if err != nil {
		t.Fatalf("enable 意外错误: %v", err)
	}
	if !strings.Contains(script, ".disabled") {
		t.Errorf("enable 脚本应处理 .disabled 还原: %s", script)
	}

	// 缺 name 报错。
	if _, err := buildWindowsConfigStartupScript("disable", ""); err == nil {
		t.Error("disable 缺 name 应返回错误")
	}

	// 非法 action。
	if _, err := buildWindowsConfigStartupScript("bogus", ""); err == nil {
		t.Error("非法 action 应返回错误")
	}
}

func TestTrimWindowsOutput(t *testing.T) {
	if got := trimWindowsOutput("  hello  \r\n"); got != "hello" {
		t.Errorf("trimWindowsOutput 结果错误: %q", got)
	}
	if got := trimWindowsOutput(""); got != "" {
		t.Errorf("trimWindowsOutput 空串应返回空: %q", got)
	}
}
