//go:build linux

package capability

import (
	"os/exec"
	"strings"
	"testing"
)

// 注意：本文件的测试**不会**对任何真实 systemd 单元执行 start/stop/restart，
// 只做参数校验与只读查询（list / show），避免影响当前已部署的服务。

// TestLinuxServiceUnitValidation 验证 unit 名白名单校验。
func TestLinuxServiceUnitValidation(t *testing.T) {
	valid := []string{
		"jarvis-daemon.service",
		"dbus.service",
		"foo@bar.service",
		"a_b-c.d",
		"UPPER.SERVICE",
		"123.service",
	}
	for _, u := range valid {
		params := map[string]any{"unit": u}
		got, err := resolveLinuxServiceUnit(params)
		if err != nil {
			t.Errorf("合法 unit %q 不应报错: %v", u, err)
			continue
		}
		if got != u {
			t.Errorf("resolveLinuxServiceUnit(%q) = %q", u, got)
		}
	}

	// 非法字符与注入尝试必须被拒绝。
	invalid := []string{
		"foo; rm -rf /",
		"foo bar.service",
		"foo/bar",
		"foo$(whoami)",
		"foo`id`",
		"foo|bar",
		"foo&bar",
		"foo\nbar",
		"--now",
		"foo.service --now",
		"foo'bar",
		"foo\"bar",
	}
	for _, u := range invalid {
		if _, err := resolveLinuxServiceUnit(map[string]any{"unit": u}); err == nil {
			t.Errorf("非法 unit %q 应报错", u)
		}
	}
}

// TestLinuxServiceUnitMissing 验证 unit 参数缺失/类型错误。
func TestLinuxServiceUnitMissing(t *testing.T) {
	cases := []map[string]any{
		{},
		{"unit": nil},
		{"unit": 123},
		{"unit": ""},
		{"unit": "   "},
	}
	for i, params := range cases {
		if _, err := resolveLinuxServiceUnit(params); err == nil {
			t.Errorf("用例 %d 应报错: %v", i, params)
		}
	}
}

// TestLinuxServiceActionParameterValidation 验证各 action 的参数校验路径。
//
// 这些调用在参数非法时会在执行 systemctl 之前就返回，因此不会影响真实服务。
func TestLinuxServiceActionParameterValidation(t *testing.T) {
	for _, action := range []string{"start", "stop", "restart"} {
		handler := handleLinuxServiceAction(action)

		if _, err := handler(map[string]any{}); err == nil {
			t.Errorf("action=%s 缺少 unit 应报错", action)
		}
		if _, err := handler(map[string]any{"unit": "bad;unit"}); err == nil {
			t.Errorf("action=%s 非法 unit 应报错", action)
		}
		if _, err := handler(map[string]any{"unit": 42}); err == nil {
			t.Errorf("action=%s unit 类型错误应报错", action)
		}
	}
}

// TestLinuxServiceStatusParameterValidation 验证 status 的参数校验。
func TestLinuxServiceStatusParameterValidation(t *testing.T) {
	if _, err := handleLinuxServiceStatus(map[string]any{}); err == nil {
		t.Error("缺少 unit 应报错")
	}
	if _, err := handleLinuxServiceStatus(map[string]any{"unit": "bad unit"}); err == nil {
		t.Error("非法 unit 应报错")
	}
}

// TestLinuxServiceListParameterValidation 验证 list 的 unit_type 校验。
func TestLinuxServiceListParameterValidation(t *testing.T) {
	if _, err := handleLinuxServiceList(map[string]any{"unit_type": "bad type"}); err == nil {
		t.Error("非法 unit_type 应报错")
	}
	if _, err := handleLinuxServiceList(map[string]any{"unit_type": "service;rm"}); err == nil {
		t.Error("含注入字符的 unit_type 应报错")
	}
	if _, err := handleLinuxServiceList(map[string]any{"unit_type": "--all"}); err == nil {
		t.Error("以 - 开头的 unit_type 应报错（会被解析为 systemctl 选项）")
	}
	if _, err := handleLinuxServiceList(map[string]any{"all": "yes"}); err == nil {
		t.Error("all 类型错误应报错")
	}
}

// TestLinuxServiceListReal 真机验证 list 能返回结果。
//
// 本机 systemctl --user 可用（is-system-running=running），因此真跑。
func TestLinuxServiceListReal(t *testing.T) {
	if _, err := exec.LookPath("systemctl"); err != nil {
		t.Skip("本机无 systemctl，跳过")
	}

	res, err := handleLinuxServiceList(map[string]any{})
	if err != nil {
		t.Fatalf("列举服务失败: %v", err)
	}
	m := res.(map[string]any)
	count := m["count"].(int)
	if count == 0 {
		t.Fatal("期望至少返回一个服务单元，实际 0")
	}

	units := m["units"].([]map[string]any)
	for _, u := range units {
		if u["unit"].(string) == "" {
			t.Error("存在 unit 名为空的条目")
		}
		if u["load"].(string) == "" {
			t.Errorf("条目 %v 缺少 load", u["unit"])
		}
		if u["active"].(string) == "" {
			t.Errorf("条目 %v 缺少 active", u["unit"])
		}
		if u["sub"].(string) == "" {
			t.Errorf("条目 %v 缺少 sub", u["unit"])
		}
	}

	// 本机已知存在 jarvis-master.service，验证解析能正确保留描述中的空格。
	found := false
	for _, u := range units {
		if u["unit"].(string) == "jarvis-master.service" {
			found = true
			if desc, _ := u["description"].(string); desc == "" {
				t.Error("jarvis-master.service 的 description 不应为空")
			}
		}
	}
	if !found {
		t.Log("提示：未在列表中找到 jarvis-master.service（环境差异，不作为失败）")
	}
}

// TestLinuxServiceStatusReal 真机验证 status 查询。
//
// 只对 dbus.service 做只读查询（用户会话必备单元，不会因查询被改动）。
func TestLinuxServiceStatusReal(t *testing.T) {
	if _, err := exec.LookPath("systemctl"); err != nil {
		t.Skip("本机无 systemctl，跳过")
	}

	res, err := handleLinuxServiceStatus(map[string]any{"unit": "dbus.service"})
	if err != nil {
		t.Fatalf("查询状态失败: %v", err)
	}
	m := res.(map[string]any)
	if m["unit"].(string) != "dbus.service" {
		t.Errorf("unit 应为 dbus.service，实际 %v", m["unit"])
	}
	if m["load"].(string) == "" {
		t.Error("load 不应为空")
	}
	if m["active"].(string) == "" {
		t.Error("active 不应为空")
	}
	if m["sub"].(string) == "" {
		t.Error("sub 不应为空")
	}
}

// TestLinuxServiceStatusNonexistent 验证查询不存在的单元时的行为。
func TestLinuxServiceStatusNonexistent(t *testing.T) {
	if _, err := exec.LookPath("systemctl"); err != nil {
		t.Skip("本机无 systemctl，跳过")
	}

	// systemctl show 对不存在的单元通常仍返回 0 并输出 inactive 状态，
	// 因此这里只要求「不 panic 且能拿到结果或明确错误」。
	res, err := handleLinuxServiceStatus(map[string]any{"unit": "definitely-not-exist-xyz.service"})
	if err != nil {
		if !strings.Contains(err.Error(), "systemctl") && !strings.Contains(err.Error(), "失败") {
			t.Errorf("错误信息不够明确: %v", err)
		}
		return
	}
	m := res.(map[string]any)
	if m["unit"].(string) != "definitely-not-exist-xyz.service" {
		t.Errorf("unit 字段应回显请求值，实际 %v", m["unit"])
	}
}

// TestParseSystemctlListUnits 验证 list-units 输出解析纯逻辑。
func TestParseSystemctlListUnits(t *testing.T) {
	sample := `UNIT                     LOAD   ACTIVE SUB     DESCRIPTION
dbus.service             loaded active running D-Bus User Message Bus
gpg-agent.service        loaded active running GnuPG cryptographic agent
foo.service              loaded failed failed  Some Failing Service

Legend: LOAD   → Reflects whether the unit definition was properly loaded.
0 loaded units listed.
`
	units := parseSystemctlListUnits(sample)
	if len(units) != 3 {
		t.Fatalf("应解析出 3 个单元，实际 %d", len(units))
	}

	if units[0]["unit"] != "dbus.service" {
		t.Errorf("首个单元应为 dbus.service，实际 %v", units[0]["unit"])
	}
	if units[0]["load"] != "loaded" {
		t.Errorf("load 应为 loaded，实际 %v", units[0]["load"])
	}
	if units[0]["active"] != "active" {
		t.Errorf("active 应为 active，实际 %v", units[0]["active"])
	}
	if units[0]["sub"] != "running" {
		t.Errorf("sub 应为 running，实际 %v", units[0]["sub"])
	}
	// 描述含空格，应完整保留。
	if units[0]["description"] != "D-Bus User Message Bus" {
		t.Errorf("description 解析错误: %q", units[0]["description"])
	}

	// 表头与 Legend/统计行应被跳过。
	for _, u := range units {
		name := u["unit"].(string)
		if strings.HasPrefix(name, "UNIT") || strings.HasPrefix(name, "Legend") {
			t.Errorf("不应包含表头或说明行: %s", name)
		}
	}
}

// TestParseSystemctlShow 验证 show 输出解析纯逻辑。
func TestParseSystemctlShow(t *testing.T) {
	sample := `Type=notify
LoadState=loaded
ActiveState=active
SubState=running
Description=D-Bus User Message Bus
MainPID=1234
ExecStart={ path=/usr/bin/dbus-daemon ; argv[]=/usr/bin/dbus-daemon --session ; ignore_errors=no }
`
	props := parseSystemctlShow(sample)
	expect := map[string]string{
		"Type":        "notify",
		"LoadState":   "loaded",
		"ActiveState": "active",
		"SubState":    "running",
		"Description": "D-Bus User Message Bus",
		"MainPID":     "1234",
	}
	for k, want := range expect {
		if got := props[k]; got != want {
			t.Errorf("props[%q] = %q，期望 %q", k, got, want)
		}
	}
	// 值中含 = 时应保留完整值（只按第一个 = 切分）。
	if !strings.Contains(props["ExecStart"], "ignore_errors=no") {
		t.Errorf("ExecStart 应保留含 = 的完整值，实际 %q", props["ExecStart"])
	}

	// 空行与无 = 的行应被忽略，不产生 panic。
	props2 := parseSystemctlShow("\n\nno-equals-here\n\n")
	if len(props2) != 0 {
		t.Errorf("应忽略无效行，实际解析出 %v", props2)
	}
}

// TestLinuxServiceCapabilitiesRegistered 验证 5 个能力都已注册。
func TestLinuxServiceCapabilitiesRegistered(t *testing.T) {
	reg := NewRegistry()
	names := []string{
		"linux.service.list",
		"linux.service.status",
		"linux.service.start",
		"linux.service.stop",
		"linux.service.restart",
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

// TestCollectLinuxServiceProxyEnv 验证代理环境变量收集。
func TestCollectLinuxServiceProxyEnv(t *testing.T) {
	t.Setenv("http_proxy", "http://127.0.0.1:7890")
	t.Setenv("HTTPS_PROXY", "http://127.0.0.1:7891")
	t.Setenv("no_proxy", "")

	got := collectLinuxServiceProxyEnv()
	joined := strings.Join(got, " ")
	if !strings.Contains(joined, "http_proxy=http://127.0.0.1:7890") {
		t.Errorf("应包含 http_proxy，实际 %v", got)
	}
	if !strings.Contains(joined, "HTTPS_PROXY=http://127.0.0.1:7891") {
		t.Errorf("应包含 HTTPS_PROXY，实际 %v", got)
	}
	if strings.Contains(joined, "no_proxy=") {
		t.Errorf("空值变量不应被收集，实际 %v", got)
	}
}
