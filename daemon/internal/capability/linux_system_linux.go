//go:build linux

package capability

import (
	"bufio"
	"fmt"
	"os"
	"os/user"
	"runtime"
	"strconv"
	"strings"
	"syscall"
)

// registerLinuxSystem 注册 Linux 系统信息能力。
func registerLinuxSystem(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "linux.system.info",
		Description: "获取 Linux 主机的基础系统信息：主机名、内核版本、发行版、架构、" +
			"CPU 数量与型号、内存总量与可用量、运行时长、当前用户与家目录。",
		Platform: PlatformLinux,
		Parameters: map[string]any{
			"type":       "object",
			"properties": map[string]any{},
		},
		Handler: handleLinuxSystemInfo,
	})
}

// handleLinuxSystemInfo 是 linux.system.info 的实现。
func handleLinuxSystemInfo(_ map[string]any) (any, error) {
	return CollectSystemInfo()
}

// CollectSystemInfo 采集本机系统信息。
//
// 该函数同时服务于 linux.system.info 能力与守护进程注册时的 hello 上报，
// 保证两处字段与取值完全一致。各平台在带构建标签的文件中提供实现。
func CollectSystemInfo() (map[string]any, error) {
	hostname, _ := os.Hostname()

	kernel := ""
	if raw, err := os.ReadFile("/proc/sys/kernel/osrelease"); err == nil {
		kernel = strings.TrimSpace(string(raw))
	}

	osName, osVersion := readLinuxOSRelease()

	cpuCount := runtime.NumCPU()
	cpuModel := readLinuxCPUModel()

	memTotalKB, memAvailableKB := readLinuxMemInfo()

	var uptimeSec float64
	if raw, err := os.ReadFile("/proc/uptime"); err == nil {
		fields := strings.Fields(string(raw))
		if len(fields) > 0 {
			if v, err := strconv.ParseFloat(fields[0], 64); err == nil {
				uptimeSec = v
			}
		}
	}

	username := ""
	home := ""
	if u, err := user.Current(); err == nil {
		username = u.Username
		home = u.HomeDir
	}

	return map[string]any{
		"hostname":         hostname,
		"kernel":           kernel,
		"os_name":          osName,
		"os_version":       osVersion,
		"arch":             runtime.GOARCH,
		"cpu_count":        cpuCount,
		"cpu_model":        cpuModel,
		"mem_total_kb":     memTotalKB,
		"mem_available_kb": memAvailableKB,
		"uptime_sec":       int64(uptimeSec),
		"user":             username,
		"home":             home,
	}, nil
}

// readLinuxOSRelease 解析 /etc/os-release，返回发行版名称与版本。
func readLinuxOSRelease() (name, version string) {
	f, err := os.Open("/etc/os-release")
	if err != nil {
		return "", ""
	}
	defer f.Close()

	values := map[string]string{}
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, val, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		values[strings.TrimSpace(key)] = strings.Trim(strings.TrimSpace(val), `"'`)
	}

	name = values["NAME"]
	if name == "" {
		name = values["ID"]
	}
	version = values["VERSION_ID"]
	if version == "" {
		version = values["VERSION"]
	}
	return name, version
}

// readLinuxCPUModel 从 /proc/cpuinfo 读取第一个处理器型号。
func readLinuxCPUModel() string {
	f, err := os.Open("/proc/cpuinfo")
	if err != nil {
		return ""
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Text()
		key, val, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		if strings.TrimSpace(key) == "model name" {
			return strings.TrimSpace(val)
		}
	}
	return ""
}

// readLinuxMemInfo 从 /proc/meminfo 读取内存总量与可用量（单位 KB）。
func readLinuxMemInfo() (totalKB, availableKB int64) {
	f, err := os.Open("/proc/meminfo")
	if err != nil {
		return 0, 0
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Text()
		key, val, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		fields := strings.Fields(val)
		if len(fields) == 0 {
			continue
		}
		n, err := strconv.ParseInt(fields[0], 10, 64)
		if err != nil {
			continue
		}
		switch strings.TrimSpace(key) {
		case "MemTotal":
			totalKB = n
		case "MemAvailable":
			availableKB = n
		}
	}
	return totalKB, availableKB
}

// linuxPageSizeKB 返回系统页大小（KB），供其他 Linux 能力复用。
func linuxPageSizeKB() int64 {
	return int64(syscall.Getpagesize()) / 1024
}

// linuxFormatBytes 把字节数格式化为便于阅读的字符串。
func linuxFormatBytes(n int64) string {
	const unit = 1024
	if n < unit {
		return fmt.Sprintf("%d B", n)
	}
	div, exp := int64(unit), 0
	for m := n / unit; m >= unit; m /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(n)/float64(div), "KMGTPE"[exp])
}
