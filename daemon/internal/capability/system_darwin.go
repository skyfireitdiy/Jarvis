//go:build darwin

package capability

import (
	"os"
	"os/user"
	"runtime"
)

// CollectSystemInfo 采集 macOS 主机的基础系统信息。
//
// 仅使用标准库可稳定获取的字段；无法获取的字段省略而非报错，
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
		"os_name":   "macOS",
		"arch":      runtime.GOARCH,
		"cpu_count": runtime.NumCPU(),
		"user":      username,
		"home":      home,
	}
	return info, nil
}
