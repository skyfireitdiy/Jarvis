//go:build linux

package selfupdate

import "jarvis-daemon/internal/service"

// restartService 在 Linux 上通过 systemd 用户服务重启守护进程。
//
// 若服务未安装（如用户以前台方式运行），Restart 会返回错误；调用方只记日志，
// 不影响「文件已替换为新版」的事实。
func restartService() error {
	_, err := service.New().Restart()
	return err
}
