package buildinfo

import "time"

// Windows FILETIME 与 Unix 时间换算的常量与纯函数。
//
// 放在无构建标签的文件里，是为了让 Linux 上也能单测这段换算逻辑——
// 它曾经出过真机才暴露的溢出 bug（见 filetimeToTime 的注释）。

const (
	// windowsEpochToUnixSec 是 1601-01-01 到 1970-01-01 的秒数。
	windowsEpochToUnixSec = 11644473600
	// filetimeTicksPerSecond 是 FILETIME 每秒的计数（单位 100ns，故为 1e7）。
	filetimeTicksPerSecond = 10000000
)

// filetimeToTime 把 Windows FILETIME 的 100ns 计数（自 1601-01-01 UTC 起算）
// 换算为 time.Time。
//
// 为什么不用 syscall.Filetime.Nanoseconds()：它把计数乘以 100 转成纳秒后返回
// int64，而当前时刻的纳秒值约 1.34e19，已超出 int64 上限（9.22e18），必然溢出
// 为负数。真机实测曾因此得到 started_at=1657-09-26 这种荒谬结果。
//
// 正确路径是先按 100ns 计数算秒（计数约 1.34e17，远在 int64 范围内），
// 再减 epoch 偏移得到 Unix 秒，余下的计数换算成纳秒。
func filetimeToTime(ticks int64) time.Time {
	sec := ticks/filetimeTicksPerSecond - windowsEpochToUnixSec
	nsec := (ticks % filetimeTicksPerSecond) * 100
	return time.Unix(sec, nsec)
}
