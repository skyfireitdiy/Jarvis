//go:build linux

package capability

// registerPlatformCapabilities 注册 Linux 平台专有能力。
//
// 能力按域拆分到独立文件，此处只做装配：
//   - linux_script_linux.go：脚本执行
//   - linux_process_linux.go：进程列表与信号
//   - linux_system_linux.go：系统信息
//   - linux_fs_linux.go：文件系统读写与目录列举
//   - linux_transfer_linux.go：分块文件传输（stat/read/write/verify）
//   - linux_service_linux.go：systemd 用户服务管理
//   - linux_gui_linux.go：窗口/输入/剪贴板/截图（依赖外部命令）
//   - linux_browser_ext_linux.go：浏览器扩展下载与更新
func registerPlatformCapabilities(reg *Registry) {
	registerLinuxScript(reg)
	registerLinuxProcess(reg)
	registerLinuxSystem(reg)
	registerLinuxFS(reg)
	registerLinuxTransfer(reg)
	// 跨机文件直传（push/pull）：逻辑跨平台共享，仅 Platform 字段不同
	registerTransferRemote(reg, PlatformLinux)
	registerLinuxService(reg)
	registerLinuxGUI(reg)
	registerLinuxBrowserExt(reg)
}
