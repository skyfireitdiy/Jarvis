//go:build !windows

package main

import "time"

// waitForReplaceTarget 在非 Windows 平台上无需等待：Linux 允许直接替换运行中的
// 可执行文件，本 helper 子命令也不会在这些平台被触发。此处保留空实现以便跨平台编译。
func waitForReplaceTarget(_ string, _ time.Duration) error { return nil }
