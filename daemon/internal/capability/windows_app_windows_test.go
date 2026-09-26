//go:build windows

package capability

// 本文件单测 windows_app_windows.go 中「注册表查询脚本构造」的正确性。
//
// 带 //go:build windows 标签：buildRegQueryScript 依赖 encodePowerShellText
// 等无标签函数，但被测对象本身只在 Windows 构建下存在，故测试也需同样标签。
// 在 Linux 上可用 `GOOS=windows go vet ./...` 做编译期检查。

import (
	"strings"
	"testing"
)

// TestToPowerShellRegistryPath 验证根键前缀转换。
func TestToPowerShellRegistryPath(t *testing.T) {
	cases := []struct {
		name    string
		in      string
		want    string
		wantErr bool
	}{
		{
			name: "HKLM 卸载键",
			in:   `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`,
			want: `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`,
		},
		{
			name: "WOW6432Node 32 位视图",
			in:   `HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall`,
			want: `HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall`,
		},
		{
			name: "HKCU 当前用户",
			in:   `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`,
			want: `HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`,
		},
		{
			name:    "未知根键报错",
			in:      `HKEY_BOGUS\SOFTWARE\Foo`,
			wantErr: true,
		},
		{
			name:    "空串报错",
			in:      "",
			wantErr: true,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := toPowerShellRegistryPath(tc.in)
			if tc.wantErr {
				if err == nil {
					t.Errorf("期望报错，得到 %q", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("意外错误: %v", err)
			}
			if got != tc.want {
				t.Errorf("转换错误：\n  输入 %q\n  期望 %q\n  得到 %q", tc.in, tc.want, got)
			}
		})
	}
}

// TestBuildRegQueryScriptContainsRequiredPieces 验证生成的脚本包含所有必需片段。
//
// 重点验证反引号拼接是否真的产生了 PowerShell 换行转义（`n）而不是字面量
// 反引号+n。这是本函数最容易出错的地方：Go 的原始字符串用反引号定界，
// 因此 PowerShell 的 `n 必须靠字符串拼接构造。
func TestBuildRegQueryScriptContainsRequiredPieces(t *testing.T) {
	script := buildRegQueryScript(`HKLM:\SOFTWARE\Test`)

	// 必须含键路径的转义字面量。
	if !strings.Contains(script, `'HKLM:\SOFTWARE\Test'`) {
		t.Errorf("脚本未包含转义后的键路径字面量：\n%s", script)
	}

	// 必须含 PowerShell 换行转义 `n（反引号 + n），而不是字面量 "`n" 两个字符。
	// 检查方式：脚本中应出现反引号字符后跟 n。
	if !strings.Contains(script, "`n") {
		t.Errorf("脚本未包含 PowerShell 换行转义（反引号+n）：\n%s", script)
	}

	// 不应出现 Go 原始字符串定界反引号残留导致的语法错误迹象：
	// 若拼接写错，会出现连续两个反引号。
	if strings.Contains(script, "``") {
		t.Errorf("脚本含连续反引号，说明拼接有误：\n%s", script)
	}

	// 必须含关键 cmdlet 与判据。
	required := []string{
		"Test-Path",
		"Get-ChildItem",
		"Get-Item",
		"GetValueNames",
		"GetValueKind",
		"GetValue",
		"[Console]::Out.Write",
		"REG_SZ",
		"REG_DWORD",
		"REG_EXPAND_SZ",
	}
	for _, r := range required {
		if !strings.Contains(script, r) {
			t.Errorf("脚本缺少必需片段 %q：\n%s", r, script)
		}
	}

	// 键不存在时必须 exit 1（对应 reg.exe 失败语义，调用方据此跳过该键）。
	if !strings.Contains(script, "exit 1") {
		t.Errorf("脚本缺少「键不存在时退出」逻辑：\n%s", script)
	}
}

// TestBuildRegQueryScriptOutputFormatMatchesRegExe 验证输出格式与 reg.exe 兼容。
//
// 解析层 parseWindowsRegValues 依赖「值名 类型 数据」三段式且类型以 REG_ 开头。
// 这里用一段模拟输出验证解析层能吃下本脚本产生的格式，从而确认「换数据源
// 不破坏解析」这一设计目标成立。
func TestBuildRegQueryScriptOutputFormatMatchesRegExe(t *testing.T) {
	// 模拟 buildRegQueryScript 在真实 Windows 上产生的输出（含中文应用名）。
	simulated := "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{GUID}\r\n" +
		"    DisplayName    REG_SZ    东方财富信息股份有限公司\r\n" +
		"    DisplayVersion    REG_SZ    12.0.2\r\n" +
		"    Publisher    REG_SZ    东方财富信息股份有限公司\r\n" +
		"    SystemComponent    REG_DWORD    0x0\r\n"

	app := parseWindowsUninstallEntry(simulated)
	if app == nil {
		t.Fatal("解析结果为 nil，说明输出格式与解析层不兼容")
	}
	if got := app["name"]; got != "东方财富信息股份有限公司" {
		t.Errorf("应用名解析错误：期望 %q，得到 %q", "东方财富信息股份有限公司", got)
	}
	if got := app["publisher"]; got != "东方财富信息股份有限公司" {
		t.Errorf("发布者解析错误：期望 %q，得到 %q", "东方财富信息股份有限公司", got)
	}
	if got := app["version"]; got != "12.0.2" {
		t.Errorf("版本解析错误：期望 %q，得到 %q", "12.0.2", got)
	}
}

// TestBuildRegQueryScriptSubKeyFormatMatchesRegExe 验证子键列举格式与解析层兼容。
func TestBuildRegQueryScriptSubKeyFormatMatchesRegExe(t *testing.T) {
	simulated := "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\r\n" +
		"    HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{GUID-A}\r\n" +
		"    HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\AppName\r\n"

	subKeys := parseWindowsRegSubKeys(simulated)
	if len(subKeys) != 2 {
		t.Fatalf("期望解析出 2 个子键，得到 %d 个：%v", len(subKeys), subKeys)
	}
	if subKeys[0] != "{GUID-A}" {
		t.Errorf("首个子键错误：期望 %q，得到 %q", "{GUID-A}", subKeys[0])
	}
	if subKeys[1] != "AppName" {
		t.Errorf("第二个子键错误：期望 %q，得到 %q", "AppName", subKeys[1])
	}
}
