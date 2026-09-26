package capability

// 本文件单测 windows_service_parse.go 中的纯逻辑（CSV 解析、过滤）。
//
// 这些测试**不带构建标签**，因此在 Linux 上即可运行——本机开发环境为 Linux，
// 无 Windows 运行环境，这是验证 windows.service.* 解析逻辑的主要手段。
//
// 注意：真正的 PowerShell 调用（windows_service_windows.go）带 //go:build windows
// 标签，其成功路径无法在本机端到端验证，只能保证在 GOOS=windows 下编译通过。

import (
	"strings"
	"testing"
)

// 模拟 PowerShell `Get-Service | Select Name,DisplayName,Status |
// ConvertTo-Csv -NoTypeInformation` 的真实输出。
const sampleServiceCSV = `"Name","DisplayName","Status"
"Spooler","Print Spooler","Running"
"wuauserv","Windows Update","Stopped"
"W32Time","Windows Time","Running"
"EventLog","Windows Event Log","Running"`

// TestParseWindowsServiceCSV 覆盖基本解析。
func TestParseWindowsServiceCSV(t *testing.T) {
	units := parseWindowsServiceCSV(sampleServiceCSV)
	if len(units) != 4 {
		t.Fatalf("期望解析出 4 个服务，实际 %d", len(units))
	}

	if units[0]["unit"] != "Spooler" {
		t.Errorf("第 1 个服务名期望 Spooler，实际 %v", units[0]["unit"])
	}
	if units[0]["display_name"] != "Print Spooler" {
		t.Errorf("第 1 个显示名期望 Print Spooler，实际 %v", units[0]["display_name"])
	}
	if units[0]["active"] != "Running" {
		t.Errorf("第 1 个状态期望 Running，实际 %v", units[0]["active"])
	}
	if units[1]["unit"] != "wuauserv" || units[1]["active"] != "Stopped" {
		t.Errorf("第 2 个服务解析异常: %v", units[1])
	}
}

// TestParseWindowsServiceCSVWithCommaInDisplayName 验证显示名含逗号时不错位。
//
// 这是选择 CSV 而非手写 split 的核心原因。
func TestParseWindowsServiceCSVWithCommaInDisplayName(t *testing.T) {
	csvText := `"Name","DisplayName","Status"
"svc1","Windows Update, 自动更新","Running"`

	units := parseWindowsServiceCSV(csvText)
	if len(units) != 1 {
		t.Fatalf("期望 1 个服务，实际 %d", len(units))
	}
	if units[0]["display_name"] != "Windows Update, 自动更新" {
		t.Fatalf("含逗号的显示名解析错误: %q", units[0]["display_name"])
	}
	if units[0]["active"] != "Running" {
		t.Fatalf("状态列错位，实际 %q", units[0]["active"])
	}
}

// TestParseWindowsServiceCSVWithEscapedQuote 验证字段内双引号（"" 转义）正确还原。
func TestParseWindowsServiceCSVWithEscapedQuote(t *testing.T) {
	csvText := `"Name","DisplayName","Status"
"svc1","My ""Quoted"" Service","Running"`

	units := parseWindowsServiceCSV(csvText)
	if len(units) != 1 {
		t.Fatalf("期望 1 个服务，实际 %d", len(units))
	}
	if units[0]["display_name"] != `My "Quoted" Service` {
		t.Fatalf("转义引号还原错误: %q", units[0]["display_name"])
	}
}

// TestParseWindowsServiceCSVChineseDisplayName 验证中文显示名不被破坏。
func TestParseWindowsServiceCSVChineseDisplayName(t *testing.T) {
	csvText := `"Name","DisplayName","Status"
"TestSvc","测试服务（中文）","Running"`

	units := parseWindowsServiceCSV(csvText)
	if len(units) != 1 {
		t.Fatalf("期望 1 个服务，实际 %d", len(units))
	}
	if units[0]["display_name"] != "测试服务（中文）" {
		t.Fatalf("中文显示名解析错误: %q", units[0]["display_name"])
	}
}

// TestParseWindowsServiceCSVEmpty 验证空输入与仅表头输入不 panic。
func TestParseWindowsServiceCSVEmpty(t *testing.T) {
	if got := parseWindowsServiceCSV(""); len(got) != 0 {
		t.Errorf("空输入期望 0 条，实际 %d", len(got))
	}
	if got := parseWindowsServiceCSV("   \n  \n"); len(got) != 0 {
		t.Errorf("纯空白输入期望 0 条，实际 %d", len(got))
	}
	// 仅表头（无数据行）：不应产生条目。
	headerOnly := `"Name","DisplayName","Status"`
	if got := parseWindowsServiceCSV(headerOnly); len(got) != 0 {
		t.Errorf("仅表头期望 0 条，实际 %d", len(got))
	}
}

// TestParseWindowsServiceStatusCSV 覆盖详情解析（列名 → 值映射）。
func TestParseWindowsServiceStatusCSV(t *testing.T) {
	// 注意：这里用反引号原始字符串，其中的 \\ 就是字面两个反斜杠字符，
	// 与 PowerShell CSV 中未转义的反斜杠路径一致（CSV 不转义反斜杠）。
	csvText := `"Name","DisplayName","State","StartMode","ProcessId","PathName","Status"
"Spooler","Print Spooler","Running","Auto","1234","C:\WINDOWS\System32\spoolsv.exe","OK"`

	props := parseWindowsServiceStatusCSV(csvText)
	if len(props) == 0 {
		t.Fatal("期望解析出属性，实际为空")
	}

	want := map[string]string{
		"Name":        "Spooler",
		"DisplayName": "Print Spooler",
		"State":       "Running",
		"StartMode":   "Auto",
		"ProcessId":   "1234",
		"PathName":    `C:\WINDOWS\System32\spoolsv.exe`,
		"Status":      "OK",
	}
	for k, v := range want {
		if props[k] != v {
			t.Errorf("属性 %s 期望 %q，实际 %q", k, v, props[k])
		}
	}
}

// TestParseWindowsServiceStatusCSVInsufficient 验证数据行不足时返回空 map。
func TestParseWindowsServiceStatusCSVInsufficient(t *testing.T) {
	// 只有表头，没有数据行。
	headerOnly := `"Name","DisplayName","State"`
	if got := parseWindowsServiceStatusCSV(headerOnly); len(got) != 0 {
		t.Errorf("仅表头期望空 map，实际 %v", got)
	}
	if got := parseWindowsServiceStatusCSV(""); len(got) != 0 {
		t.Errorf("空输入期望空 map，实际 %v", got)
	}
}

// TestFilterWindowsServiceUnits 覆盖按服务名/显示名过滤（大小写不敏感）。
func TestFilterWindowsServiceUnits(t *testing.T) {
	units := parseWindowsServiceCSV(sampleServiceCSV)

	cases := []struct {
		name   string
		filter string
		want   int
	}{
		{"空过滤返回全部", "", 4},
		{"按服务名精确子串", "Spooler", 1},
		{"按服务名大小写不敏感", "spooler", 1},
		{"按显示名匹配", "Windows Update", 1},
		{"按显示名部分匹配", "Windows", 3}, // Windows Update / Windows Time / Windows Event Log
		{"无匹配返回空", "不存在的服务xyz", 0},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := filterWindowsServiceUnits(units, tc.filter)
			if len(got) != tc.want {
				t.Fatalf("过滤 %q 期望 %d 条，实际 %d", tc.filter, tc.want, len(got))
			}
		})
	}
}

// TestFilterWindowsServiceUnitsByChineseDisplayName 验证中文显示名可被过滤。
func TestFilterWindowsServiceUnitsByChineseDisplayName(t *testing.T) {
	csvText := `"Name","DisplayName","Status"
"svc1","打印后台处理程序","Running"
"svc2","Windows Update","Stopped"`

	units := parseWindowsServiceCSV(csvText)
	got := filterWindowsServiceUnits(units, "打印")
	if len(got) != 1 {
		t.Fatalf("按中文过滤期望 1 条，实际 %d", len(got))
	}
	if got[0]["unit"] != "svc1" {
		t.Fatalf("过滤结果错误: %v", got[0])
	}
}

// TestParseWindowsServiceCSVSkipsMalformedRows 验证列数不足的行被跳过而不 panic。
func TestParseWindowsServiceCSVSkipsMalformedRows(t *testing.T) {
	csvText := `"Name","DisplayName","Status"
"OnlyName"
"Good","Good Display","Running"`

	units := parseWindowsServiceCSV(csvText)
	// 只有 "Good" 一条完整（"OnlyName" 列数不足被跳过）。
	if len(units) != 1 {
		t.Fatalf("期望 1 条有效服务，实际 %d: %v", len(units), units)
	}
	if units[0]["unit"] != "Good" {
		t.Fatalf("有效服务解析错误: %v", units[0])
	}
}

// TestParseWindowsServiceCSVCRLF 验证 CRLF 行尾（Windows 输出）也能解析。
func TestParseWindowsServiceCSVCRLF(t *testing.T) {
	csvText := "\"Name\",\"DisplayName\",\"Status\"\r\n\"Spooler\",\"Print Spooler\",\"Running\"\r\n"

	units := parseWindowsServiceCSV(csvText)
	if len(units) != 1 {
		t.Fatalf("CRLF 输入期望 1 条，实际 %d", len(units))
	}
	if units[0]["unit"] != "Spooler" {
		t.Fatalf("CRLF 解析错误: %v", units[0])
	}
	if strings.Contains(units[0]["active"].(string), "\r") {
		t.Fatalf("状态值残留 \\r: %q", units[0]["active"])
	}
}
