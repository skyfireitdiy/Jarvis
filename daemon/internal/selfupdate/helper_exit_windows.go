//go:build windows

package selfupdate

import "os"

// exitForHelperReplacement 在 Windows 上立即终止当前进程，为 helper 让出可执行文件句柄。
//
// 为什么必须直接退出而不是调用 restartService：
//   - helper 的替换前提是「目标 exe 不再被占用」，即本进程必须先退出；
//   - restartService 走的是 service.Restart（Stop + Start），而 Stop 依赖 PID 文件。
//     daemon 由计划任务（schtasks /Run）启动时不会写 PID 文件（只有 service start 才写），
//     于是 Stop 读到失效 PID、误判「服务未运行」而**不杀本进程**，Start 又拉起一个
//     新进程抢占监听端口失败（真机实测：bind 127.0.0.1:17800 被占用）。结果是本进程
//     一直占着 exe，helper 等待 60 秒超时、替换失败，更新永远无法生效。
//   - 重启职责本就在 helper 一侧（--restart 参数，替换成功后调 restartServiceForHelper），
//     父进程无需也不应再做重启。
//
// os.Exit(0) 不执行 defer（如清理临时目录），但此时进程即将被替换，可接受。
func exitForHelperReplacement() {
	os.Exit(0)
}
