package capability

// 本文件提供「是否自动更新守护进程自身」这一开关的内存态。
//
// 为什么需要它：自动更新会下载并替换用户磁盘上的可执行文件、重启系统服务，
// 属于高副作用操作，绝不能无条件自动执行。用户在 Web 设置界面显式打开开关后，
// 前端会把该值随登录态推送给本机守护进程，守护进程据此决定是否在网关下发
// daemon_update 时静默下载并替换自身。
//
// 为什么放在 capability 包：
//   - 与 browser_ext_settings.go 同包，cmd/jarvis-daemon/main.go 的
//     maybeAutoUpdateDaemon 可直接读取，无需跨包再套一层；
//   - 与 browser_ext_settings.go 的「包级变量 + sync.RWMutex + 导出 getter/setter」
//     模式保持一致，风格统一。
//
// 为什么只有内存态、不落盘：与「自动安装浏览器扩展」开关同理，用户要求开关
// 只存浏览器存储（localStorage），守护进程不持久化。因此这里只保留内存态：
// 守护进程重启后回到默认值 false（默认关闭），等待前端再次推送——这正是安全
// 方向（未收到推送一律不自动更新）。注意：这与「更新前临时落盘 Token」是两件事，
// 后者仅是一次性凭据中转，见 internal/selfupdate 与 cmd/jarvis-daemon/main.go。

import "sync"

var (
	// autoUpdateDaemonMu 保护下方开关，读多写少，用 RWMutex。
	// 并发来源：WS 读循环（hello_ack 回调 → maybeAutoUpdateDaemon 读取）
	// 与 HTTP handler（/api/auth、/api/settings 写入）。
	autoUpdateDaemonMu sync.RWMutex
	// autoUpdateDaemon 是开关当前值，默认 false（关闭）。
	autoUpdateDaemon bool
)

// SetAutoUpdateDaemon 设置「自动更新守护进程」开关。
//
// 由 localapi 在收到 /api/settings 或 /api/auth 的推送时调用。
func SetAutoUpdateDaemon(enabled bool) {
	autoUpdateDaemonMu.Lock()
	defer autoUpdateDaemonMu.Unlock()
	autoUpdateDaemon = enabled
}

// AutoUpdateDaemon 返回开关当前值；默认 false（关闭）。
//
// 由 cmd/jarvis-daemon/main.go 的 maybeAutoUpdateDaemon 在决定是否自动更新前调用。
func AutoUpdateDaemon() bool {
	autoUpdateDaemonMu.RLock()
	defer autoUpdateDaemonMu.RUnlock()
	return autoUpdateDaemon
}
