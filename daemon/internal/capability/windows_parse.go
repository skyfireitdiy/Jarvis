package capability

import (
	"strconv"
	"strings"
)

// 本文件存放 Windows 能力的纯解析函数。
//
// 这些函数只依赖标准库、不引用任何平台专有类型，因此**不带构建标签**：
// 这样在 Linux / macOS 上也能编译并直接做单元测试，从而在无 Windows 环境时
// 仍能验证 reg.exe / tasklist 输出的解析正确性。
//
// 与之配套的测试见 windows_parse_test.go。

// 本文件同时提供若干跨平台通用的小工具函数（splitNonEmptyLines 等），
// 供带 //go:build windows 标签的能力文件使用。

// splitNonEmptyLines 按行切分并去除空行与首尾空白。
func splitNonEmptyLines(s string) []string {
	raw := strings.Split(strings.ReplaceAll(s, "\r\n", "\n"), "\n")
	out := make([]string, 0, len(raw))
	for _, line := range raw {
		line = strings.TrimSpace(line)
		if line != "" {
			out = append(out, line)
		}
	}
	return out
}

// firstNonEmptyLine 返回首个非空行（已去除首尾空白）。
func firstNonEmptyLine(s string) string {
	lines := splitNonEmptyLines(s)
	if len(lines) == 0 {
		return ""
	}
	return lines[0]
}

// splitCSVLine 按逗号切分一行 CSV，并去掉每个字段两侧的引号与空白。
//
// 这里不处理字段内嵌逗号（引号包裹）的完整 CSV 语义：Windows 的产品名、
// 版本号、构建号均不含逗号，简化解析足以覆盖实际取值。
func splitCSVLine(line string) []string {
	parts := strings.Split(line, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		out = append(out, strings.Trim(strings.TrimSpace(p), `"`))
	}
	return out
}

// indexOfFold 在候选名中按大小写不敏感查找首个命中的下标，未命中返回 -1。
func indexOfFold(header []string, candidates ...string) int {
	for i, h := range header {
		for _, c := range candidates {
			if strings.EqualFold(strings.TrimSpace(h), c) {
				return i
			}
		}
	}
	return -1
}

// minInt 返回两个整数中的较小值。
func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// parseWindowsOSVersionCSV 解析 PowerShell ConvertTo-Csv 或 wmic /format:csv 的输出。
//
// 两种输出的共同点是首行是表头、后续行是逗号分隔的值；本函数按表头定位字段，
// 因此对列顺序不敏感，也能同时兼容两种来源。
func parseWindowsOSVersionCSV(out string) (name, version, build string) {
	lines := splitNonEmptyLines(out)
	if len(lines) < 2 {
		return "", "", ""
	}

	header := splitCSVLine(lines[0])
	idxName := indexOfFold(header, "ProductName", "Caption", "Name")
	idxVersion := indexOfFold(header, "DisplayVersion", "Version")
	idxBuild := indexOfFold(header, "CurrentBuildNumber", "BuildNumber")

	for _, line := range lines[1:] {
		fields := splitCSVLine(line)
		if len(fields) == 0 {
			continue
		}
		if idxName >= 0 && idxName < len(fields) && name == "" {
			name = fields[idxName]
		}
		if idxVersion >= 0 && idxVersion < len(fields) && version == "" {
			version = fields[idxVersion]
		}
		if idxBuild >= 0 && idxBuild < len(fields) && build == "" {
			build = fields[idxBuild]
		}
		if name != "" && version != "" && build != "" {
			break
		}
	}
	return name, version, build
}

// parseWindowsTasklistCSV 解析 tasklist /FO CSV /NH 的输出。
//
// 每行形如："chrome.exe","1234","Console","1","123,456 K"。
// 字段顺序固定为：映像名称、PID、会话名、会话号、内存使用。
func parseWindowsTasklistCSV(out string) []map[string]any {
	lines := splitNonEmptyLines(out)
	procs := make([]map[string]any, 0, len(lines))
	for _, line := range lines {
		fields := splitCSVLine(line)
		if len(fields) < 2 {
			continue
		}
		pid, err := strconv.Atoi(strings.TrimSpace(fields[1]))
		if err != nil {
			continue
		}
		item := map[string]any{
			"name": fields[0],
			"pid":  pid,
		}
		if len(fields) >= 3 {
			item["session_name"] = fields[2]
		}
		if len(fields) >= 4 {
			if sessionID, err := strconv.Atoi(strings.TrimSpace(fields[3])); err == nil {
				item["session_id"] = sessionID
			}
		}
		if len(fields) >= 5 {
			item["mem_usage"] = fields[4]
		}
		procs = append(procs, item)
	}
	return procs
}

// parseWindowsRegSubKeys 解析 reg query <key> 的输出，提取子键名。
//
// 输出形如（首行为所查询键自身的路径，其后每行是完整子键路径）：
//
//	HKEY_LOCAL_MACHINE\SOFTWARE\...\Uninstall
//	    HKEY_LOCAL_MACHINE\SOFTWARE\...\Uninstall\{GUID}
//	    HKEY_LOCAL_MACHINE\SOFTWARE\...\Uninstall\AppName
//
// 本函数取每行最后一个反斜杠之后的部分作为子键名。
func parseWindowsRegSubKeys(out string) []string {
	lines := splitNonEmptyLines(out)
	if len(lines) == 0 {
		return nil
	}
	// 首行是所查询键自身的路径，跳过。
	subKeys := make([]string, 0, len(lines)-1)
	for _, line := range lines[1:] {
		if idx := strings.LastIndex(line, `\`); idx >= 0 && idx+1 < len(line) {
			subKeys = append(subKeys, line[idx+1:])
		}
	}
	return subKeys
}

// parseWindowsUninstallEntry 解析单个卸载项的 reg query 输出，返回应用信息。
//
// 输出形如：
//
//	HKEY_LOCAL_MACHINE\...\Uninstall\{GUID}
//	    DisplayName    REG_SZ    Google Chrome
//	    DisplayVersion    REG_SZ    120.0.1
//	    Publisher    REG_SZ    Google LLC
//	    SystemComponent    REG_DWORD    0x1
//
// 返回 nil 表示该条目应被跳过：缺少 DisplayName，或 SystemComponent 为 1。
func parseWindowsUninstallEntry(out string) map[string]any {
	values := parseWindowsRegValues(out)
	if len(values) == 0 {
		return nil
	}

	name := strings.TrimSpace(values["DisplayName"])
	if name == "" {
		return nil
	}
	// SystemComponent=1 表示这是系统内部组件，不作为用户可见应用列出。
	if isWindowsRegTrue(values["SystemComponent"]) {
		return nil
	}

	app := map[string]any{
		"name": name,
	}
	if v := strings.TrimSpace(values["DisplayVersion"]); v != "" {
		app["version"] = v
	}
	if v := strings.TrimSpace(values["Publisher"]); v != "" {
		app["publisher"] = v
	}
	if v := strings.TrimSpace(values["InstallLocation"]); v != "" {
		app["install_location"] = v
	}
	if v := strings.TrimSpace(values["InstallDate"]); v != "" {
		app["install_date"] = v
	}
	return app
}

// parseWindowsRegValues 把 reg query <key> 的输出解析为「值名 → 值内容」映射。
//
// 每行格式为：    <名称>    <类型>    <数据>
// 名称与数据之间用若干空格分隔，类型是 REG_SZ / REG_DWORD / REG_EXPAND_SZ 等。
// 首行（键路径自身）不含类型标记，会被自然跳过。
func parseWindowsRegValues(out string) map[string]string {
	values := make(map[string]string)
	for _, line := range splitNonEmptyLines(out) {
		fields := strings.Fields(line)
		if len(fields) < 3 {
			continue
		}
		// 找到类型标记字段的位置，其前为值名、其后为数据。
		typeIdx := -1
		for i, f := range fields {
			if strings.HasPrefix(f, "REG_") {
				typeIdx = i
				break
			}
		}
		if typeIdx <= 0 || typeIdx+1 >= len(fields) {
			continue
		}
		name := strings.Join(fields[:typeIdx], " ")
		data := strings.Join(fields[typeIdx+1:], " ")
		values[name] = data
	}
	return values
}

// isWindowsRegTrue 判断注册表值是否表示「真」。
//
// REG_DWORD 的 1 会以 0x1 形式出现在输出中，REG_SZ 则直接是 "1"。
func isWindowsRegTrue(raw string) bool {
	v := strings.ToLower(strings.TrimSpace(raw))
	return v == "1" || v == "0x1" || v == "true" || v == "yes"
}
