package capability

// 本文件存放 Windows 服务能力（windows.service.*）的纯解析函数。
//
// 这些函数只依赖标准库、不引用任何平台专有类型，因此**不带构建标签**：
// 这样在 Linux / macOS 上也能编译并直接做单元测试，从而在无 Windows 环境时
// 仍能验证 PowerShell CSV 输出的解析正确性。
//
// 与之配套的测试见 windows_service_parse_test.go；带 //go:build windows 标签的
// windows_service_windows.go 负责注册能力与调用 PowerShell。
//
// 为什么用 CSV 而不是 Format-Table：
//   - Format-Table 会按控制台宽度截断列，且表头随系统语言本地化，解析脆弱。
//   - ConvertTo-Csv -NoTypeInformation 输出稳定的逗号分隔格式，首行为表头，
//     后续为数据行，引号按 RFC4180 规则转义（字段内的 " 写成 ""）。

import (
	"encoding/csv"
	"strings"
)

// parseWindowsServiceCSV 解析 `Get-Service | Select Name,DisplayName,Status |
// ConvertTo-Csv -NoTypeInformation` 的输出，返回服务条目列表。
//
// 每行被转换为与 Linux 侧 parseSystemctlListUnits 对齐的字段：
// unit（Name）、description（DisplayName）、active（Status）。
// 另外附带 display_name 便于调用方直接使用。
func parseWindowsServiceCSV(out string) []map[string]any {
	rows := parseCSVRows(out)
	units := make([]map[string]any, 0, len(rows))

	// ConvertTo-Csv -NoTypeInformation 的首行是表头（Name,DisplayName,Status），
	// 必须跳过，否则会多出一条名为 "Name" 的伪服务。
	if len(rows) > 0 && isWindowsServiceListHeader(rows[0]) {
		rows = rows[1:]
	}

	for _, row := range rows {
		// 期望列：Name,DisplayName,Status
		if len(row) < 3 {
			continue
		}
		name := strings.TrimSpace(row[0])
		if name == "" {
			continue
		}
		units = append(units, map[string]any{
			"unit":         name,
			"display_name": strings.TrimSpace(row[1]),
			"description":  strings.TrimSpace(row[1]),
			"active":       strings.TrimSpace(row[2]),
			"load":         "",
			"sub":          "",
		})
	}

	return units
}

// isWindowsServiceListHeader 判断某行是否为服务列表 CSV 的表头。
//
// 判定方式：首列等于 "Name" 且第二列等于 "DisplayName"（大小写不敏感），
// 避免把恰好叫 Name 的服务误判为表头。
func isWindowsServiceListHeader(row []string) bool {
	if len(row) < 2 {
		return false
	}
	return strings.EqualFold(strings.TrimSpace(row[0]), "Name") &&
		strings.EqualFold(strings.TrimSpace(row[1]), "DisplayName")
}

// parseWindowsServiceStatusCSV 解析服务详情 CSV，返回「首条数据行」的
// 列名 → 值映射。
//
// 期望列：Name,DisplayName,State,StartMode,ProcessId,PathName,Status
func parseWindowsServiceStatusCSV(out string) map[string]string {
	rows := parseCSVRows(out)
	if len(rows) < 2 {
		return map[string]string{}
	}

	header := rows[0]
	values := rows[1]

	props := make(map[string]string, len(header))
	for i, key := range header {
		key = strings.TrimSpace(key)
		if key == "" {
			continue
		}
		if i < len(values) {
			props[key] = strings.TrimSpace(values[i])
		} else {
			props[key] = ""
		}
	}
	return props
}

// filterWindowsServiceUnits 按 filter 子串过滤服务条目（大小写不敏感），
// 匹配范围为 unit（服务名）与 display_name（显示名）。
func filterWindowsServiceUnits(units []map[string]any, filter string) []map[string]any {
	needle := strings.ToLower(strings.TrimSpace(filter))
	if needle == "" {
		return units
	}

	out := make([]map[string]any, 0, len(units))
	for _, u := range units {
		name := strings.ToLower(asString(u["unit"]))
		display := strings.ToLower(asString(u["display_name"]))
		if strings.Contains(name, needle) || strings.Contains(display, needle) {
			out = append(out, u)
		}
	}
	return out
}

// parseCSVRows 用 encoding/csv 解析文本为二维字符串表。
//
// 之所以用标准库 csv 而非手写 split：服务显示名可能包含逗号（如
// "Windows Update, 自动更新"），手写切分会错位；csv 会按 RFC4180 正确
// 处理引号包裹与 "" 转义。
//
// 解析失败时返回已解析出的部分（尽量容错），不返回错误——因为这是
// 「解析外部命令输出」的场景，宁可少几条也不要整体失败。
func parseCSVRows(out string) [][]string {
	// 统一换行：PowerShell 在 Windows 上输出 CRLF，且末尾可能带 \r。
	// 必须先归一化，否则 encoding/csv 会把结尾的 \r 当作新记录的一部分，
	// 产生多余的空行（曾导致 CRLF 输入解析出 2 条而非 1 条）。
	normalized := strings.ReplaceAll(out, "\r\n", "\n")
	normalized = strings.ReplaceAll(normalized, "\r", "\n")

	trimmed := strings.TrimSpace(normalized)
	if trimmed == "" {
		return nil
	}

	reader := csv.NewReader(strings.NewReader(trimmed))
	// 允许字段数不一致（PowerShell 偶尔会输出额外列）。
	reader.FieldsPerRecord = -1
	reader.LazyQuotes = true

	records, err := reader.ReadAll()
	if err != nil {
		// 容错：逐行尽力解析。
		return parseCSVRowsFallback(trimmed)
	}

	rows := make([][]string, 0, len(records))
	for _, rec := range records {
		if len(rec) == 0 {
			continue
		}
		// 跳过空记录（所有字段均为空白的行）。
		if isBlankCSVRecord(rec) {
			continue
		}
		rows = append(rows, rec)
	}
	return rows
}

// isBlankCSVRecord 判断一条 CSV 记录是否全为空白字段。
func isBlankCSVRecord(rec []string) bool {
	for _, f := range rec {
		if strings.TrimSpace(f) != "" {
			return false
		}
	}
	return true
}

// parseCSVRowsFallback 在 csv 解析整体失败时逐行尽力解析。
func parseCSVRowsFallback(text string) [][]string {
	rows := make([][]string, 0, 16)
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		reader := csv.NewReader(strings.NewReader(line))
		reader.FieldsPerRecord = -1
		reader.LazyQuotes = true
		rec, err := reader.Read()
		if err != nil || len(rec) == 0 {
			continue
		}
		rows = append(rows, rec)
	}
	return rows
}

// asString 把接口值安全转为字符串（非字符串返回空串）。
func asString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}
