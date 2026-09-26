//go:build linux

package capability

// registerPlatformCapabilities 注册 Linux 平台专有能力。
//
// 能力按域拆分到独立文件，此处只做装配：
//   - linux_script_linux.go：脚本执行
//   - linux_process_linux.go：进程列表与信号
//   - linux_system_linux.go：系统信息
//   - linux_fs_linux.go：文件系统读写与目录列举
//   - linux_service_linux.go：systemd 用户服务管理
//   - linux_gui_linux.go：窗口/输入/剪贴板/截图（依赖外部命令）
func registerPlatformCapabilities(reg *Registry) {
	registerLinuxScript(reg)
	registerLinuxProcess(reg)
	registerLinuxSystem(reg)
	registerLinuxFS(reg)
	registerLinuxService(reg)
	registerLinuxGUI(reg)
}
