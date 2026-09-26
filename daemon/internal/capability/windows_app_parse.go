package capability

// 本文件存放 Windows 应用列表能力（windows.app.list）的纯解析函数。
//
// 这些函数只依赖标准库、不引用任何平台专有类型，因此**不带构建标签**：
// 这样在 Linux / macOS 上也能编译并直接做单元测试，从而在无 Windows 环境时
// 仍能验证 PowerShell 输出的解析正确性（本机开发环境为 Linux）。
//
// 与之配套的测试见 windows_app_parse_test.go；带 //go:build windows 标签的
// windows_app_windows.go 负责注册能力与调用 PowerShell。
//
// 为什么从「逐键 reg query」改为「单次 CSV」
// ==========================================
// 早期实现是 N+1 次 PowerShell 启动：先枚举 3 个 Uninstall 根键的子键，
// 再对**每个子键**单独启动一次 powershell.exe 读取其值。真机注册表通常有
// 200~500 个卸载项，即 200~500 次进程冷启动（每次约 0.5~1s），累计远超
// 60s 超时——这正是真机 windows.app.list 超时的根因。
//
// 现在改为**一次** PowerShell 调用把三个根键下的所有卸载项一次性导出为 CSV，
// 由 Go 侧解析。进程启动次数从 N+1 降到 1，耗时从分钟级降到秒级。
//
// 选择 CSV 的理由与服务能力一致：ConvertTo-Csv -NoTypeInformation 输出稳定
// 的逗号分隔格式，字段内的逗号/引号按 RFC4180 转义（应用名与发布者常含逗号，
// 如 "Microsoft Corporation, Inc."），手写切分会错位。

import (
	"strings"
)

// parseWindowsAppCSV 解析 `Get-ItemProperty ... | Select ... |
// ConvertTo-Csv -NoTypeInformation` 的输出，返回应用条目列表。
//
// 期望列（顺序不敏感，按表头名取值）：
//
//	DisplayName, DisplayVersion, Publisher, InstallLocation, InstallDate, SystemComponent
//
// 过滤规则与 parseWindowsUninstallEntry 保持一致：
//   - DisplayName 为空 → 跳过；
//   - SystemComponent 为真 → 跳过（系统内部组件，不作为用户可见应用）。
//
// 返回的 map 字段名与旧实现完全一致（name/version/publisher/install_location/
// install_date），以保证上层 handleWindowsAppList 与既有测试无需改动。
func parseWindowsAppCSV(out string) []map[string]any {
	rows := parseCSVRows(out)
	if len(rows) < 2 {
		return nil
	}

	header := rows[0]
	// 建立「列名 → 下标」映射，避免依赖列顺序（PowerShell 的 Select-Object
	// 虽保持给定顺序，但按名取值更稳健）。
	index := make(map[string]int, len(header))
	for i, name := range header {
		index[strings.ToLower(strings.TrimSpace(name))] = i
	}

	// 若表头不含 DisplayName，说明输出不是预期的应用列表（例如脚本报错文本），
	// 直接返回空，交由上层以 count=0 呈现，而不是把错误文本当成应用名。
	if _, ok := index["displayname"]; !ok {
		return nil
	}

	apps := make([]map[string]any, 0, len(rows)-1)
	for _, row := range rows[1:] {
		cell := func(key string) string {
			i, ok := index[key]
			if !ok || i >= len(row) {
				return ""
			}
			return strings.TrimSpace(row[i])
		}

		name := cell("displayname")
		if name == "" {
			continue
		}
		if isWindowsRegTrue(cell("systemcomponent")) {
			continue
		}

		app := map[string]any{
			"name": name,
		}
		if v := cell("displayversion"); v != "" {
			app["version"] = v
		}
		if v := cell("publisher"); v != "" {
			app["publisher"] = v
		}
		if v := cell("installlocation"); v != "" {
			app["install_location"] = v
		}
		if v := cell("installdate"); v != "" {
			app["install_date"] = v
		}
		apps = append(apps, app)
	}

	return apps
}
