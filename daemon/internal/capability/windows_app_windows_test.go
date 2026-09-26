//go:build windows

package capability

// 本文件单测 windows_app_windows.go 中「应用列表脚本构造」的正确性。
//
// 带 //go:build windows 标签：buildWindowsAppListScript 依赖 encodePowerShellText
// 等无标签函数，但被测对象本身只在 Windows 构建下存在，故测试也需同样标签。
// 在 Linux 上可用 `GOOS=windows go vet ./...` 做编译期检查。
//
// 解析层 parseWindowsAppCSV 的测试在无标签的 windows_app_parse_test.go 中，
// 因为它是纯函数、可在 Linux 上直接运行。

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

// TestBuildWindowsAppListScriptContainsRequiredPieces 验证生成的脚本包含所有必需片段。
//
// 重点验证：
//   - 三个根键都被转成 PowerShell 路径并作为字面量列出（防止漏掉 32 位视图或 HKCU）；
//   - 使用 Get-ChildItem + Get-ItemProperty 遍历（不是逐键启动进程）；
//   - 用 Select-Object 哈希表把字段统一为 [string]（保证 CSV 列稳定）；
//   - 以 ConvertTo-Csv -NoTypeInformation 结尾。
func TestBuildWindowsAppListScriptContainsRequiredPieces(t *testing.T) {
	script := buildWindowsAppListScript()

	required := []string{
		// 三个根键的 PowerShell 字面量。
		`'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'`,
		`'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'`,
		`'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'`,
		// 遍历与读取。
		"Get-ChildItem",
		"Get-ItemProperty",
		// 字段统一为字符串。
		"Select-Object",
		"[string]$_.DisplayName",
		"[string]$_.DisplayVersion",
		"[string]$_.Publisher",
		"[string]$_.InstallLocation",
		"[string]$_.InstallDate",
		"[string]$_.SystemComponent",
		// 输出格式。
		"ConvertTo-Csv -NoTypeInformation",
	}
	for _, r := range required {
		if !strings.Contains(script, r) {
			t.Errorf("脚本缺少必需片段 %q：\n%s", r, script)
		}
	}

	// 不应出现 Go 原始字符串定界反引号残留导致的语法错误迹象：
	// 若拼接写错，会出现连续两个反引号。
	if strings.Contains(script, "``") {
		t.Errorf("脚本含连续反引号，说明拼接有误：\n%s", script)
	}
}
