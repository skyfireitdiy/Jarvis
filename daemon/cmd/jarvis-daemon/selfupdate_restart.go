package main

import "jarvis-daemon/internal/service"

// restartServiceForHelper 由更新 helper 在替换完成后调用，重启守护进程服务。
//
// 与 selfupdate 包内的 restartService 语义一致，但此处位于 cmd 包，
// 直接复用 service.Service 的 Restart 实现（Windows 计划任务 / Linux systemd）。
func restartServiceForHelper() error {
	_, err := service.New().Restart()
	return err
}
