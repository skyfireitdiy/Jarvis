//go:build darwin

package capability

import (
	"os"
	"os/user"
	"runtime"
)

// CollectSystemInfoFast 采集不依赖任何外部命令的「零成本」系统信息。
//
// macOS 的系统信息全部来自标准库，读取本就毫秒级，因此这里直接复用
// CollectSystemInfo 的结果（字段完全一致），仅用于与 Windows 保持同一接口，
// 供 hello 首帧调用。
func CollectSystemInfoFast() map[string]any {
	info, _ := CollectSystemInfo()
	if info == nil {
		info = map[string]any{}
	}
	return info
}

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
