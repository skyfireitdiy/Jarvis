package capability

// 本文件单测 windows_app_parse.go 中的纯解析函数 parseWindowsAppCSV。
//
// 不带构建标签：解析函数只依赖标准库，可在 Linux 上直接运行测试，
// 从而在无 Windows 环境时仍能验证 CSV 解析的正确性（本机开发环境为 Linux）。

import (
	"testing"
)

// TestParseWindowsAppCSVBasic 验证基本解析：表头识别、字段映射、空值省略。
func TestParseWindowsAppCSVBasic(t *testing.T) {
	out := "\"DisplayName\",\"DisplayVersion\",\"Publisher\",\"InstallLocation\",\"InstallDate\",\"SystemComponent\"\r\n" +
		"\"Google Chrome\",\"120.0.1\",\"Google LLC\",\"C:\\Program Files\\Google\\Chrome\",\"20240101\",\"\"\r\n" +
		"\"7-Zip\",\"23.01\",\"Igor Pavlov\",\"\",\"\",\"\"\r\n"

	apps := parseWindowsAppCSV(out)
	if len(apps) != 2 {
		t.Fatalf("期望解析出 2 个应用，得到 %d 个：%v", len(apps), apps)
	}

	chrome := apps[0]
	if got := chrome["name"]; got != "Google Chrome" {
		t.Errorf("name 错误：期望 %q，得到 %q", "Google Chrome", got)
	}
	if got := chrome["version"]; got != "120.0.1" {
		t.Errorf("version 错误：期望 %q，得到 %q", "120.0.1", got)
	}
	if got := chrome["publisher"]; got != "Google LLC" {
		t.Errorf("publisher 错误：期望 %q，得到 %q", "Google LLC", got)
	}
	if got := chrome["install_location"]; got != `C:\Program Files\Google\Chrome` {
		t.Errorf("install_location 错误：期望 %q，得到 %q", `C:\Program Files\Google\Chrome`, got)
	}
	if got := chrome["install_date"]; got != "20240101" {
		t.Errorf("install_date 错误：期望 %q，得到 %q", "20240101", got)
	}

	// 空字段应被省略（不写入 map），保持与旧实现 parseWindowsUninstallEntry 一致。
	sevenZip := apps[1]
	if _, ok := sevenZip["install_location"]; ok {
		t.Errorf("install_location 为空时不应写入 map：%v", sevenZip)
	}
	if _, ok := sevenZip["install_date"]; ok {
		t.Errorf("install_date 为空时不应写入 map：%v", sevenZip)
	}
}

// TestParseWindowsAppCSVChineseAndComma 验证中文与字段内逗号（RFC4180 引号转义）。
//
// 应用名与发布者常含逗号（如 "Microsoft Corporation, Inc."），必须靠 CSV
// 的引号规则正确还原，这也是选用 encoding/csv 而非手写切分的原因。
func TestParseWindowsAppCSVChineseAndComma(t *testing.T) {
	out := "\"DisplayName\",\"DisplayVersion\",\"Publisher\",\"InstallLocation\",\"InstallDate\",\"SystemComponent\"\r\n" +
		"\"东方财富信息股份有限公司\",\"12.0.2\",\"东方财富, Inc.\",\"D:\\东方财富\",\"\",\"\"\r\n"

	apps := parseWindowsAppCSV(out)
	if len(apps) != 1 {
		t.Fatalf("期望解析出 1 个应用，得到 %d 个：%v", len(apps), apps)
	}
	if got := apps[0]["name"]; got != "东方财富信息股份有限公司" {
		t.Errorf("中文 name 解析错误：期望 %q，得到 %q", "东方财富信息股份有限公司", got)
	}
	if got := apps[0]["publisher"]; got != "东方财富, Inc." {
		t.Errorf("含逗号 publisher 解析错误：期望 %q，得到 %q", "东方财富, Inc.", got)
	}
}

// TestParseWindowsAppCSVSkipsEmptyNameAndSystemComponent 验证过滤规则。
//
//   - DisplayName 为空 → 跳过（无名称的卸载项对用户无意义）；
//   - SystemComponent 为真（1 / 0x1 / true / yes）→ 跳过（系统内部组件）。
func TestParseWindowsAppCSVSkipsEmptyNameAndSystemComponent(t *testing.T) {
	out := "\"DisplayName\",\"DisplayVersion\",\"Publisher\",\"InstallLocation\",\"InstallDate\",\"SystemComponent\"\r\n" +
		"\"\",\"1.0\",\"NoName Corp\",\"\",\"\",\"\"\r\n" +
		"\"Windows Internal\",\"1.0\",\"Microsoft\",\"\",\"\",\"1\"\r\n" +
		"\"Hex Component\",\"1.0\",\"Microsoft\",\"\",\"\",\"0x1\"\r\n" +
		"\"Kept App\",\"1.0\",\"Vendor\",\"\",\"\",\"0\"\r\n"

	apps := parseWindowsAppCSV(out)
	if len(apps) != 1 {
		t.Fatalf("期望仅保留 1 个应用，得到 %d 个：%v", len(apps), apps)
	}
	if got := apps[0]["name"]; got != "Kept App" {
		t.Errorf("保留的应用错误：期望 %q，得到 %q", "Kept App", got)
	}
}

// TestParseWindowsAppCSVHeaderMismatch 验证表头不含 DisplayName 时返回空。
//
// 这防止把脚本错误文本（如异常消息）当成应用名。
func TestParseWindowsAppCSVHeaderMismatch(t *testing.T) {
	out := "\"Error\",\"Message\"\r\n" +
		"\"SomethingFailed\",\"details\"\r\n"

	apps := parseWindowsAppCSV(out)
	if len(apps) != 0 {
		t.Errorf("表头不含 DisplayName 时应返回空，得到 %v", apps)
	}
}

// TestParseWindowsAppCSVEmpty 验证空输入与仅表头输入均返回空。
func TestParseWindowsAppCSVEmpty(t *testing.T) {
	for _, in := range []string{"", "   ", "\r\n"} {
		if apps := parseWindowsAppCSV(in); len(apps) != 0 {
			t.Errorf("输入 %q 应返回空，得到 %v", in, apps)
		}
	}

	headerOnly := "\"DisplayName\",\"DisplayVersion\"\r\n"
	if apps := parseWindowsAppCSV(headerOnly); len(apps) != 0 {
		t.Errorf("仅表头应返回空，得到 %v", apps)
	}
}

// TestParseWindowsAppCSVColumnOrderIndependent 验证按列名取值而非列顺序。
//
// PowerShell 的 Select-Object 虽保持给定顺序，但按名取值更稳健；
// 这里打乱列顺序确认仍能正确解析。
func TestParseWindowsAppCSVColumnOrderIndependent(t *testing.T) {
	out := "\"Publisher\",\"DisplayName\",\"SystemComponent\",\"DisplayVersion\"\r\n" +
		"\"Vendor X\",\"Reordered App\",\"\",\"9.9\"\r\n"

	apps := parseWindowsAppCSV(out)
	if len(apps) != 1 {
		t.Fatalf("期望解析出 1 个应用，得到 %d 个：%v", len(apps), apps)
	}
	if got := apps[0]["name"]; got != "Reordered App" {
		t.Errorf("name 错误：期望 %q，得到 %q", "Reordered App", got)
	}
	if got := apps[0]["publisher"]; got != "Vendor X" {
		t.Errorf("publisher 错误：期望 %q，得到 %q", "Vendor X", got)
	}
	if got := apps[0]["version"]; got != "9.9" {
		t.Errorf("version 错误：期望 %q，得到 %q", "9.9", got)
	}
}

// TestParseWindowsAppCSVTrimsWhitespace 验证字段首尾空白被去除。
func TestParseWindowsAppCSVTrimsWhitespace(t *testing.T) {
	out := "\"DisplayName\",\"DisplayVersion\"\r\n" +
		"\"  Padded App  \",\"  1.0  \"\r\n"

	apps := parseWindowsAppCSV(out)
	if len(apps) != 1 {
		t.Fatalf("期望解析出 1 个应用，得到 %d 个：%v", len(apps), apps)
	}
	if got := apps[0]["name"]; got != "Padded App" {
		t.Errorf("name 未去除空白：得到 %q", got)
	}
	if got := apps[0]["version"]; got != "1.0" {
		t.Errorf("version 未去除空白：得到 %q", got)
	}
}
