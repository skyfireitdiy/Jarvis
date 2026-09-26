package capability

import (
	"testing"
)

// 本文件测试 windows_parse.go 中的纯解析函数。
//
// 这些函数不带构建标签，故在 Linux/macOS 上也能编译运行，
// 从而在无 Windows 环境时仍能验证 reg.exe / tasklist / PowerShell 输出的解析正确性。

func TestSplitNonEmptyLines(t *testing.T) {
	got := splitNonEmptyLines("a\r\n\r\n  b  \n\nc\n")
	want := []string{"a", "b", "c"}
	if len(got) != len(want) {
		t.Fatalf("行数不符: got %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("第 %d 行不符: got %q, want %q", i, got[i], want[i])
		}
	}
}

func TestFirstNonEmptyLine(t *testing.T) {
	if got := firstNonEmptyLine("\n\n  hello  \nworld"); got != "hello" {
		t.Fatalf("got %q, want %q", got, "hello")
	}
	if got := firstNonEmptyLine("   \n\n"); got != "" {
		t.Fatalf("全空行应返回空串，got %q", got)
	}
}

func TestSplitCSVLine(t *testing.T) {
	got := splitCSVLine(`"chrome.exe","1234","Console","1","123,456 K"`)
	// 简化解析不处理引号内嵌逗号，故 "123,456 K" 会被切成两段。
	if len(got) != 6 {
		t.Fatalf("字段数不符: got %v", got)
	}
	if got[0] != "chrome.exe" || got[1] != "1234" || got[2] != "Console" || got[4] != "123" {
		t.Fatalf("字段解析不符: %v", got)
	}
}

func TestIndexOfFold(t *testing.T) {
	header := []string{"Node", "ProductName", "Version"}
	if got := indexOfFold(header, "productname"); got != 1 {
		t.Fatalf("大小写不敏感查找失败: got %d, want 1", got)
	}
	if got := indexOfFold(header, "DisplayVersion", "Version"); got != 2 {
		t.Fatalf("候选名匹配失败: got %d, want 2", got)
	}
	if got := indexOfFold(header, "Missing"); got != -1 {
		t.Fatalf("未命中应返回 -1, got %d", got)
	}
}

func TestMinInt(t *testing.T) {
	if got := minInt(3, 7); got != 3 {
		t.Fatalf("got %d, want 3", got)
	}
	if got := minInt(9, 2); got != 2 {
		t.Fatalf("got %d, want 2", got)
	}
}

func TestParseWindowsOSVersionCSV(t *testing.T) {
	// PowerShell ConvertTo-Csv 风格：首行表头，列顺序与 wmic 不同。
	out := "\"Node\",\"ProductName\",\"DisplayVersion\",\"CurrentBuildNumber\"\r\n" +
		"\"PC\",\"Windows 11 Pro\",\"23H2\",\"22631\"\r\n"
	name, version, build := parseWindowsOSVersionCSV(out)
	if name != "Windows 11 Pro" || version != "23H2" || build != "22631" {
		t.Fatalf("解析结果不符: name=%q version=%q build=%q", name, version, build)
	}
}

func TestParseWindowsOSVersionCSVEmpty(t *testing.T) {
	name, version, build := parseWindowsOSVersionCSV("")
	if name != "" || version != "" || build != "" {
		t.Fatalf("空输入应返回空串: %q %q %q", name, version, build)
	}
	// 只有表头没有数据行。
	name, version, build = parseWindowsOSVersionCSV("\"ProductName\"\r\n")
	if name != "" || version != "" || build != "" {
		t.Fatalf("仅表头应返回空串: %q %q %q", name, version, build)
	}
}

func TestParseWindowsTasklistCSV(t *testing.T) {
	out := "\"chrome.exe\",\"1234\",\"Console\",\"1\",\"123,456 K\"\r\n" +
		"\"notepad.exe\",\"5678\",\"Console\",\"1\",\"12,345 K\"\r\n"
	procs := parseWindowsTasklistCSV(out)
	if len(procs) != 2 {
		t.Fatalf("进程数不符: got %d, want 2", len(procs))
	}
	if procs[0]["name"] != "chrome.exe" {
		t.Fatalf("name 不符: %v", procs[0]["name"])
	}
	if procs[0]["pid"] != 1234 {
		t.Fatalf("pid 应为 int 1234, got %v (%T)", procs[0]["pid"], procs[0]["pid"])
	}
	if procs[0]["session_name"] != "Console" {
		t.Fatalf("session_name 不符: %v", procs[0]["session_name"])
	}
	if procs[0]["session_id"] != 1 {
		t.Fatalf("session_id 应为 int 1, got %v", procs[0]["session_id"])
	}
}

func TestParseWindowsTasklistCSVSkipsInvalid(t *testing.T) {
	// PID 非数字的行应被跳过，字段不足的行也应被跳过。
	out := "\"bad.exe\",\"notanumber\",\"Console\",\"1\",\"0 K\"\r\n" +
		"\"short.exe\"\r\n" +
		"\"good.exe\",\"42\",\"Console\",\"1\",\"1 K\"\r\n"
	procs := parseWindowsTasklistCSV(out)
	if len(procs) != 1 {
		t.Fatalf("应只保留 1 条有效记录, got %d: %v", len(procs), procs)
	}
	if procs[0]["name"] != "good.exe" || procs[0]["pid"] != 42 {
		t.Fatalf("保留的记录不符: %v", procs[0])
	}
}

func TestParseWindowsRegSubKeys(t *testing.T) {
	out := "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\r\n" +
		"    HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{GUID-1}\r\n" +
		"    HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\AppName\r\n"
	keys := parseWindowsRegSubKeys(out)
	if len(keys) != 2 {
		t.Fatalf("子键数不符: got %d, want 2: %v", len(keys), keys)
	}
	if keys[0] != "{GUID-1}" || keys[1] != "AppName" {
		t.Fatalf("子键名不符: %v", keys)
	}
}

func TestParseWindowsRegValues(t *testing.T) {
	out := "HKEY_LOCAL_MACHINE\\SOFTWARE\\...\\Uninstall\\{GUID}\r\n" +
		"    DisplayName    REG_SZ    Google Chrome\r\n" +
		"    DisplayVersion    REG_SZ    120.0.1\r\n" +
		"    SystemComponent    REG_DWORD    0x1\r\n"
	values := parseWindowsRegValues(out)
	if values["DisplayName"] != "Google Chrome" {
		t.Fatalf("DisplayName 不符: %q", values["DisplayName"])
	}
	if values["DisplayVersion"] != "120.0.1" {
		t.Fatalf("DisplayVersion 不符: %q", values["DisplayVersion"])
	}
	if values["SystemComponent"] != "0x1" {
		t.Fatalf("SystemComponent 不符: %q", values["SystemComponent"])
	}
}

func TestParseWindowsRegValuesMultiWordName(t *testing.T) {
	// 值名本身含空格时应完整保留（名称与类型以多个空格分隔）。
	out := "    Install Location    REG_SZ    C:\\Program Files\\App\r\n"
	values := parseWindowsRegValues(out)
	if values["Install Location"] != "C:\\Program Files\\App" {
		t.Fatalf("多词值名解析不符: %v", values)
	}
}

func TestParseWindowsUninstallEntry(t *testing.T) {
	out := "HKEY_LOCAL_MACHINE\\SOFTWARE\\...\\Uninstall\\{GUID}\r\n" +
		"    DisplayName    REG_SZ    Google Chrome\r\n" +
		"    DisplayVersion    REG_SZ    120.0.1\r\n" +
		"    Publisher    REG_SZ    Google LLC\r\n" +
		"    InstallLocation    REG_SZ    C:\\Program Files\\Google\\Chrome\r\n" +
		"    InstallDate    REG_SZ    20240101\r\n"
	app := parseWindowsUninstallEntry(out)
	if app == nil {
		t.Fatal("应解析出有效应用，got nil")
	}
	if app["name"] != "Google Chrome" {
		t.Fatalf("name 不符: %v", app["name"])
	}
	if app["version"] != "120.0.1" {
		t.Fatalf("version 不符: %v", app["version"])
	}
	if app["publisher"] != "Google LLC" {
		t.Fatalf("publisher 不符: %v", app["publisher"])
	}
	if app["install_location"] != "C:\\Program Files\\Google\\Chrome" {
		t.Fatalf("install_location 不符: %v", app["install_location"])
	}
	if app["install_date"] != "20240101" {
		t.Fatalf("install_date 不符: %v", app["install_date"])
	}
}

func TestParseWindowsUninstallEntrySkips(t *testing.T) {
	// 缺少 DisplayName 应跳过。
	noName := "    DisplayVersion    REG_SZ    1.0\r\n"
	if app := parseWindowsUninstallEntry(noName); app != nil {
		t.Fatalf("缺少 DisplayName 应返回 nil, got %v", app)
	}

	// SystemComponent=1 应跳过。
	sysComp := "    DisplayName    REG_SZ    Some Component\r\n" +
		"    SystemComponent    REG_DWORD    0x1\r\n"
	if app := parseWindowsUninstallEntry(sysComp); app != nil {
		t.Fatalf("SystemComponent=1 应返回 nil, got %v", app)
	}
}

func TestParseWindowsUninstallEntryOmitsEmptyFields(t *testing.T) {
	// 只有 DisplayName 时，其余字段不应出现在结果中。
	out := "    DisplayName    REG_SZ    Minimal App\r\n"
	app := parseWindowsUninstallEntry(out)
	if app == nil {
		t.Fatal("应解析出有效应用")
	}
	if _, ok := app["version"]; ok {
		t.Fatalf("空 version 不应写入结果: %v", app)
	}
	if _, ok := app["publisher"]; ok {
		t.Fatalf("空 publisher 不应写入结果: %v", app)
	}
}

func TestIsWindowsRegTrue(t *testing.T) {
	for _, raw := range []string{"1", "0x1", "true", "TRUE", "yes", " 1 "} {
		if !isWindowsRegTrue(raw) {
			t.Fatalf("%q 应判定为真", raw)
		}
	}
	for _, raw := range []string{"0", "0x0", "false", "no", ""} {
		if isWindowsRegTrue(raw) {
			t.Fatalf("%q 应判定为假", raw)
		}
	}
}
