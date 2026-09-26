//go:build windows

package capability

// registerPlatformCapabilities 注册 Windows 平台专有能力。
//
// 能力按域拆分到独立文件，此处只做装配：
//   - windows_system_windows.go：系统信息
//   - windows_process_windows.go：进程列表与结束进程
//   - windows_app_windows.go：已安装应用查询
//   - windows_gui_windows.go：窗口控制（列表/聚焦/关闭）
//   - windows_input_windows.go：输入模拟（鼠标点击/键入文本/按键组合）
//   - windows_clipboard_windows.go：剪贴板读写与截图
//   - windows_script_windows.go：脚本执行
//   - windows_fs_windows.go：文件系统读写与目录列举
//   - windows_service_windows.go：系统服务查询与启停
//   - windows_common_windows.go：参数解析与外部命令辅助函数
func registerPlatformCapabilities(reg *Registry) {
	registerWindowsSystem(reg)
	registerWindowsProcess(reg)
	registerWindowsApp(reg)
	registerWindowsGUI(reg)
	registerWindowsInput(reg)
	registerWindowsClipboard(reg)
	registerWindowsScript(reg)
	registerWindowsFS(reg)
	registerWindowsService(reg)
}
