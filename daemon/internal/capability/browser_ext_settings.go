package capability

// 本文件提供「是否自动安装/更新浏览器扩展」这一开关的内存态。
//
// 为什么需要它：安装/覆盖浏览器扩展属于有副作用的操作（会改写用户磁盘上的
// 扩展目录），不应无条件自动执行。用户在 Web 设置界面显式打开开关后，前端
// 会把该值随登录态推送给本机守护进程，守护进程据此决定是否在网关扩展版本
// 变化时自动下载并覆盖本地扩展。
//
// 为什么放在 capability 包：
//   - 与 browser_ext.go 同包，cmd/jarvis-daemon/main.go 的 maybeAutoSyncBrowserExt
//     可直接读取，无需跨包再套一层；
//   - 与 browser_ext_cred.go 的「包级变量 + sync.RWMutex + 导出 getter/setter」
//     模式保持一致，风格统一。
//
// 为什么只有内存态、不落盘：用户明确要求该开关「只存浏览器存储」（localStorage），
// 守护进程不持久化。因此这里只保留内存态：守护进程重启后回到默认值 false
// （默认关闭），等待前端再次推送——这正是安全方向（未收到推送一律不自动装）。
import "sync"

var (
	// autoInstallBrowserExtMu 保护下方开关，读多写少，用 RWMutex。
	// 并发来源：WS 读循环（hello_ack 回调 → maybeAutoSyncBrowserExt 读取）
	// 与 HTTP handler（/api/auth、/api/settings 写入）。
	autoInstallBrowserExtMu sync.RWMutex
	// autoInstallBrowserExt 是开关当前值，默认 false（关闭）。
	autoInstallBrowserExt bool
)

// SetAutoInstallBrowserExt 设置「自动安装/更新浏览器扩展」开关。
//
// 由 localapi 在收到 /api/settings 或 /api/auth 的推送时调用。
//
// 返回「本次调用是否发生了 false → true 的跃迁」（即开关从关闭变为打开）。
// 调用方据此决定是否立刻补做一次扩展同步检查：daemon 仅在收到 hello_ack 时
// 检查一次开关，而前端推送开关通常晚于 hello_ack（daemon 启动后先连网关、
// 前端随后才推设置），若不补查，用户明明已打开开关却会看到「已关闭，跳过
// 自动同步」，且该状态会一直持续到下次重连。
func SetAutoInstallBrowserExt(enabled bool) bool {
	autoInstallBrowserExtMu.Lock()
	defer autoInstallBrowserExtMu.Unlock()
	transitioned := enabled && !autoInstallBrowserExt
	autoInstallBrowserExt = enabled
	return transitioned
}

// AutoInstallBrowserExt 返回开关当前值；默认 false（关闭）。
//
// 由 cmd/jarvis-daemon/main.go 的 maybeAutoSyncBrowserExt 在决定是否自动
// 同步扩展前调用。
func AutoInstallBrowserExt() bool {
	autoInstallBrowserExtMu.RLock()
	defer autoInstallBrowserExtMu.RUnlock()
	return autoInstallBrowserExt
}
