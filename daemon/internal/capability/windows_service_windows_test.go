//go:build windows

package capability

// 本文件单测 windows_service_windows.go 中「不依赖真实 Windows 运行环境」的纯函数：
// 服务名校验 validateWindowsServiceName。
//
// 之所以单独放在带 //go:build windows 标签的文件里：validateWindowsServiceName
// 定义在 windows_service_windows.go（同样带 windows 标签），在 Linux 上不可见，
// 因此测试也必须带相同标签，才能与目标函数一起参与 Windows 构建。
//
// 验证方式：CGO_ENABLED=0 GOOS=windows go test -c 编译通过（本机无法运行 .exe）。

import "testing"

// TestValidateWindowsServiceName 覆盖服务名白名单校验的各种取值。
func TestValidateWindowsServiceName(t *testing.T) {
	valid := []string{
		"Spooler",
		"wuauserv",
		"W32Time",
		"EventLog",
		"my-service",
		"my.service",
		"svc@host",
		"my_service",
		"Print Spooler",     // 含空格
		"打印后台处理程序",          // 中文
		"Windows Update 更新", // 中英混合含空格
	}

	for _, name := range valid {
		if err := validateWindowsServiceName(name); err != nil {
			t.Errorf("期望 %q 合法，实际报错: %v", name, err)
		}
	}

	invalid := []struct {
		name string
		desc string
	}{
		{"", "空字符串"},
		{"   ", "纯空白"},
		{"-Name", "以 - 开头（会被当作选项）"},
		{"-", "单个连字符"},
		{"svc;rm", "含分号（命令注入尝试）"},
		{"svc|whoami", "含管道符"},
		{"svc&calc", "含与符"},
		{"svc$(whoami)", "含子表达式"},
		{"svc`n", "含反引号"},
		{"svc'quote", "含单引号"},
		{`svc"quote`, "含双引号"},
		{"svc/path", "含斜杠"},
		{"svc\\path", "含反斜杠"},
	}

	for _, tc := range invalid {
		if err := validateWindowsServiceName(tc.name); err == nil {
			t.Errorf("期望 %q（%s）非法，实际通过校验", tc.name, tc.desc)
		}
	}
}

// TestValidateWindowsServiceNameTrimsSpace 验证首尾空白被忽略后仍能正确判定。
func TestValidateWindowsServiceNameTrimsSpace(t *testing.T) {
	// 首尾空格应被 Trim 后再校验，因此 " Spooler " 合法。
	if err := validateWindowsServiceName(" Spooler "); err != nil {
		t.Errorf("首尾空格的服务名应合法，实际报错: %v", err)
	}
	// 但 " -x " Trim 后以 - 开头，应被拒绝。
	if err := validateWindowsServiceName(" -x "); err == nil {
		t.Error("Trim 后以 - 开头的服务名应被拒绝，实际通过")
	}
}
