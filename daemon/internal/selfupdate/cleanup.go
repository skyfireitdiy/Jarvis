package selfupdate

import (
	"log"
	"os"

	"jarvis-daemon/internal/service"
)

// CleanupAfterUpdate 在新进程启动时清理上一次自动更新遗留的中间产物。
//
// 为什么必须在**新进程启动时**做（而不是更新流程结束时）：
//   - Windows 上更新走 helper 路径，父进程在启动 helper 后立即 os.Exit(0) 退出
//     （见 updater.go 的 exitForHelperReplacement），因此父进程根本执行不到任何
//     「收尾」代码；
//   - helper 自身在替换完成后也要退出，且它正运行在 <target>.helper.exe 上，
//     Windows 不允许删除正在运行的可执行文件，所以 helper 也删不掉自己。
//
// 于是唯一能安全清理的时机，就是「替换完成、服务重启后的新 daemon 进程启动时」——
// 此时 helper 已退出、旧进程已退出，两个残留文件都无人占用。
//
// 清理内容：
//  1. 尝试状态文件（~/.jarvis/daemon/update-attempt.json）：若记录的目标版本与当前
//     运行版本一致且处于 InProgress，说明本次更新已成功到位，清除该状态。否则保留
//     （失败退避/熔断信息仍需跨重启保留）。
//  2. 目标可执行文件同目录的 <target>.new 与 <target>.helper.exe 残留。
//
// 任何一步失败都只记日志，绝不影响 daemon 正常启动。
func CleanupAfterUpdate(currentVersion string) {
	clearSettledAttemptState(currentVersion)
	removeUpdateLeftovers()
}

// clearSettledAttemptState 在「更新已成功到位」时清除尝试状态。
//
// 判定条件：状态里记录的目标版本 == 当前运行版本，且 InProgress 为 true。
// 为什么需要：更新成功后若不清除，InProgress 会一直残留；虽然网关下次下发新版本时
// 目标版本变化会自动解除熔断（见 ShouldSkipUpdate），但若网关重复下发同一版本，
// 残留的 InProgress 会让 daemon 永久熔断、只能靠手工删文件恢复。此处清除可消除该
// 脆弱点。
func clearSettledAttemptState(currentVersion string) {
	state, ok := LoadAttemptState()
	if !ok {
		return
	}
	if !state.InProgress || !SameVersion(state.TargetVersion, currentVersion) {
		// 不是「刚更新成功」的场景：可能是失败退避/熔断记录，必须保留。
		return
	}
	if err := ClearAttemptState(); err != nil {
		log.Printf("[selfupdate] 清除已完成的更新尝试状态失败（不影响运行）: %v", err)
		return
	}
	log.Printf("[selfupdate] 自动更新已确认生效（%s），已清除更新尝试状态", currentVersion)
}

// removeUpdateLeftovers 删除目标可执行文件同目录下的更新残留文件。
//
// 文件不存在视为正常（幂等），删除失败只记日志——例如用户手工把文件设为只读。
func removeUpdateLeftovers() {
	target, err := service.InstalledBinaryPath()
	if err != nil {
		return
	}
	for _, path := range []string{target + ".new", target + ".helper.exe"} {
		if err := os.Remove(path); err != nil {
			if !os.IsNotExist(err) {
				log.Printf("[selfupdate] 清理更新残留文件失败（可手动删除）%s: %v", path, err)
			}
			continue
		}
		log.Printf("[selfupdate] 已清理更新残留文件: %s", path)
	}
}
