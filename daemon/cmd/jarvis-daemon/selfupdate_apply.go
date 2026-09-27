package main

import (
	"flag"
	"fmt"
	"log"
	"time"

	"jarvis-daemon/internal/selfupdate"
)

// cmdSelfUpdateApply 是自动更新的 helper 子命令：在父进程（旧版 daemon）退出后，
// 用 --src 处的新可执行文件替换 --dst 处的目标文件，并按需重启服务。
//
// 为什么需要独立进程：Windows 不允许覆盖/重命名正在运行的 exe。父进程在替换失败时
// 会启动本 helper（见 apply_windows.go 的 SpawnApplyHelper），随后父进程退出；
// 本进程等待目标文件不再被占用后再完成替换。
//
// 参数：
//
//	--src    新版本可执行文件路径（helper 自身即从该副本启动）
//	--dst    最终要替换到的路径（如 ~/.jarvis/bin/jarvis-daemon.exe）
//	--restart 替换成功后是否重启服务
//
// 说明：本子命令只在 Windows 上被真正使用；其他平台保留实现仅为跨平台编译，
// 且 Linux 上替换运行中的文件无需 helper，故不会被触发。
func cmdSelfUpdateApply(args []string) error {
	fs := flag.NewFlagSet("self-update-apply", flag.ContinueOnError)
	srcFlag := fs.String("src", "", "新版本可执行文件路径")
	dstFlag := fs.String("dst", "", "要替换的目标路径")
	restartFlag := fs.Bool("restart", false, "替换成功后重启服务")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *srcFlag == "" || *dstFlag == "" {
		return fmt.Errorf("self-update-apply 需要 --src 与 --dst")
	}

	// 等待父进程退出并释放目标文件；超时后仍尝试替换（可能已可写）。
	if err := waitForReplaceTarget(*dstFlag, 60*time.Second); err != nil {
		log.Printf("[selfupdate-helper] 等待目标文件可替换超时，仍尝试替换: %v", err)
	}

	if err := selfupdate.Apply(*srcFlag, *dstFlag); err != nil {
		return fmt.Errorf("helper 替换可执行文件失败: %w", err)
	}
	log.Printf("[selfupdate-helper] 已替换 %s", *dstFlag)

	if *restartFlag {
		if err := restartServiceForHelper(); err != nil {
			// 重启失败不算致命错误：文件已是新版，用户可手动重启。
			log.Printf("[selfupdate-helper] 重启服务失败（可手动重启）: %v", err)
		}
	}
	return nil
}
