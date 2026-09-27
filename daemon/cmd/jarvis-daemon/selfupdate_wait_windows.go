//go:build windows

package main

import (
	"fmt"
	"os"
	"time"
)

// waitForReplaceTarget 在 Windows 上轮询等待目标可执行文件不再被占用（父进程已退出）。
//
// 做法：反复尝试以「独占写」方式打开目标文件；成功即说明旧进程已释放句柄。
// 达到 timeout 仍未成功则返回错误（调用方仍会尝试替换，只是可能失败）。
func waitForReplaceTarget(target string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for {
		f, err := os.OpenFile(target, os.O_WRONLY, 0)
		if err == nil {
			_ = f.Close()
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("等待 %s 可写超时: %w", target, err)
		}
		time.Sleep(500 * time.Millisecond)
	}
}
