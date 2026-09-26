//go:build windows

package capability

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"os/user"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// windowsSystemInfoTimeout 是采集系统信息时调用外部命令的超时时间。
const windowsSystemInfoTimeout = 10 * time.Second

// registerWindowsSystem 注册 Windows 系统信息能力。
func registerWindowsSystem(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.system.info",
		Description: "获取 Windows 主机的基础系统信息：主机名、系统版本与构建号、架构、" +
			"CPU 数量、内存总量与可用量、系统启动时间与运行时长、当前用户与家目录。" +
			"系统版本与内存信息通过 PowerShell / wmic 获取，命令不可用时相应字段省略而非报错。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type":       "object",
			"properties": map[string]any{},
		},
		Handler: handleWindowsSystemInfo,
	})
}

// handleWindowsSystemInfo 是 windows.system.info 的实现。
func handleWindowsSystemInfo(_ map[string]any) (any, error) {
	return CollectSystemInfo()
}

// CollectSystemInfo 采集本机系统信息。
//
// 该函数同时服务于 windows.system.info 能力与守护进程注册时的 hello 上报，
// 保证两处字段与取值完全一致。各平台在带构建标签的文件中提供实现。
//
// 仅使用标准库与系统自带命令可稳定获取的字段；无法获取的字段省略而非报错，
// 以保证守护进程注册流程不因采集失败而中断。
func CollectSystemInfo() (map[string]any, error) {
	hostname, _ := os.Hostname()

	username := ""
	home := ""
	if u, err := user.Current(); err == nil {
		username = u.Username
		home = u.HomeDir
	}

	info := map[string]any{
		"hostname":  hostname,
		"os_name":   "Windows",
		"arch":      runtime.GOARCH,
		"cpu_count": runtime.NumCPU(),
		"user":      username,
		"home":      home,
	}

	// 系统版本与构建号：优先 PowerShell，回退 wmic。
	if name, version, build := readWindowsOSVersion(); name != "" || version != "" {
		info["os_name"] = name
		info["os_version"] = version
		if build != "" {
			info["os_build"] = build
		}
	}

	// 内存总量与可用量（KB）。
	if totalKB, availableKB := readWindowsMemoryKB(); totalKB > 0 {
		info["mem_total_kb"] = totalKB
		info["mem_available_kb"] = availableKB
	}

	// 系统启动时间与运行时长。
	if bootTime, ok := readWindowsBootTime(); ok {
		info["boot_time"] = bootTime.Format(time.RFC3339)
		info["uptime_sec"] = int64(time.Since(bootTime).Seconds())
	}

	return info, nil
}

// readWindowsOSVersion 读取 Windows 产品名、版本号与构建号。
//
// 数据来源是注册表 CurrentVersion 键（PowerShell Get-ItemProperty），
// 失败时回退到 wmic os。两者都不可用时返回空串，由调用方省略字段。
func readWindowsOSVersion() (name, version, build string) {
	// 走 runWindowsPowerShellCommand：它用 -EncodedCommand 传脚本并强制 UTF-8 输出，
	// 因此 ProductName 即使被本地化为中文（如「Windows 10 专业版」）也不会乱码。
	// 早期版本这里用 runWindowsCommand 直接拼 -Command，中文系统上会输出 GBK 字节
	// 而被 Go 按 UTF-8 误解，故改为统一走 PowerShell 执行器。
	if out, err := runWindowsPowerShellCommand(
		"(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion') | "+
			"Select-Object ProductName,DisplayVersion,CurrentBuildNumber | ConvertTo-Csv -NoTypeInformation",
		windowsSystemInfoTimeout,
	); err == nil {
		name, version, build = parseWindowsOSVersionCSV(out)
		if name != "" || version != "" {
			return name, version, build
		}
	}

	// 回退：wmic 无 UTF-8 输出模式，但该分支只取 Caption/Version/BuildNumber，
	// 若 Caption 为中文仍可能乱码，故仅作为 PowerShell 不可用时的兜底。
	if out, err := runWindowsCommand("wmic", "os", "get", "Caption,Version,BuildNumber", "/format:csv"); err == nil {
		name, version, build = parseWindowsOSVersionCSV(out)
	}
	return name, version, build
}

// readWindowsMemoryKB 读取物理内存总量与可用量（单位 KB）。
//
// 通过 PowerShell 的 Get-CimInstance Win32_OperatingSystem 获取；失败时返回 0。
func readWindowsMemoryKB() (totalKB, availableKB int64) {
	// 统一走 runWindowsPowerShellCommand（-EncodedCommand + UTF-8 输出），
	// 避免任何编码相关的意外；本函数只读数值，但保持与其他 PowerShell 调用一致。
	out, err := runWindowsPowerShellCommand(
		"$os = Get-CimInstance Win32_OperatingSystem; "+
			"'{0},{1}' -f $os.TotalVisibleMemorySize, $os.FreePhysicalMemory",
		windowsSystemInfoTimeout,
	)
	if err != nil {
		return 0, 0
	}
	line := firstNonEmptyLine(out)
	if line == "" {
		return 0, 0
	}
	fields := strings.Split(line, ",")
	if len(fields) < 2 {
		return 0, 0
	}
	totalKB, _ = strconv.ParseInt(strings.TrimSpace(fields[0]), 10, 64)
	availableKB, _ = strconv.ParseInt(strings.TrimSpace(fields[1]), 10, 64)
	return totalKB, availableKB
}

// readWindowsBootTime 读取系统启动时间。
//
// 通过 PowerShell 的 Win32_OperatingSystem.LastBootUpTime 获取；失败时 ok 为 false。
func readWindowsBootTime() (time.Time, bool) {
	// 统一走 runWindowsPowerShellCommand（-EncodedCommand + UTF-8 输出）。
	out, err := runWindowsPowerShellCommand(
		"(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('o')",
		windowsSystemInfoTimeout,
	)
	if err != nil {
		return time.Time{}, false
	}
	line := firstNonEmptyLine(out)
	if line == "" {
		return time.Time{}, false
	}
	// PowerShell 的 'o' 格式形如 2026-09-26T13:00:00.0000000+08:00，
	// Go 的 RFC3339 解析不接受 7 位小数，故先尝试 RFC3339Nano 再截断小数位重试。
	if t, err := time.Parse(time.RFC3339Nano, line); err == nil {
		return t, true
	}
	if t, err := time.Parse("2006-01-02T15:04:05", line[:minInt(len(line), 19)]); err == nil {
		return t, true
	}
	return time.Time{}, false
}

// runWindowsCommand 执行外部命令并返回标准输出（UTF-8）。
//
// 统一带超时，避免命令挂起导致能力调用阻塞；命令不存在时返回明确错误。
//
// 编码说明：本函数被 readWindowsOSVersion / readWindowsMemoryKB /
// readWindowsBootTime 调用，这三个函数只读取**纯 ASCII 数值与英文产品名**
// （如 "Microsoft Windows 10 Pro"、"26200"、"33382940"），不涉及中文。
// 因此这里不强制 UTF-8 输出（wmic 也不支持），直接按 UTF-8 解释即可——
// 即使系统代码页是 GBK，ASCII 字节在两种编码下完全一致，不会乱码。
//
// 若将来这些函数需要读取中文内容，必须改为走 PowerShell 并复用
// runWindowsPowerShellCommand（它已保证 UTF-8 输出），或在此处加
// looksLikeUTF8 校验与明确报错，避免静默产生 U+FFFD。
func runWindowsCommand(name string, args ...string) (string, error) {
	if _, err := requireTool(name, ""); err != nil {
		return "", err
	}
	ctx, cancel := context.WithTimeout(context.Background(), windowsSystemInfoTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, name, args...)
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("执行 %s 失败: %w", name, err)
	}
	return string(out), nil
}
