package buildinfo

import (
	"testing"
	"time"
)

// TestFiletimeToTimeKnownValue 用真机上报的 FILETIME 计数验算换算结果。
//
// 背景：真机上曾出现 started_at=1657-09-26T15:34:09Z（started_at_unix=-9854036751）
// 这种荒谬值。根因是用了 syscall.Filetime.Nanoseconds()——它把 100ns 计数乘以 100
// 转成纳秒后返回 int64，而当前时刻纳秒值约 1.34e19 > int64 上限 9.22e18，必然溢出。
// 本用例锁定修复后的正确行为。
func TestFiletimeToTimeKnownValue(t *testing.T) {
	// 反推自真机上报：错误值 -9854036751 加上 epoch 偏移后得到正确的 Unix 秒。
	const wantUnixSec = 1790436849 // 2026-09-26T15:34:09Z
	ticks := (int64(wantUnixSec) + windowsEpochToUnixSec) * filetimeTicksPerSecond

	got := filetimeToTime(ticks)

	if got.Unix() != wantUnixSec {
		t.Fatalf("filetimeToTime(%d).Unix() = %d, 期望 %d", ticks, got.Unix(), wantUnixSec)
	}
	if got.UTC().Format(time.RFC3339) != "2026-09-26T15:34:09Z" {
		t.Fatalf("格式化结果 = %q, 期望 %q", got.UTC().Format(time.RFC3339), "2026-09-26T15:34:09Z")
	}
	if got.Unix() < 0 {
		t.Fatalf("Unix 时间戳为负（%d），说明发生了 int64 溢出", got.Unix())
	}
}

// TestFiletimeToTimeNoOverflow 确认当前时刻附近的换算不会溢出为负值。
//
// 这正是原 bug 的判定条件：修复前 int64 溢出会让结果落回 1601 年前后（负数时间戳）。
func TestFiletimeToTimeNoOverflow(t *testing.T) {
	// 覆盖 2020-01-01 到 2100-01-01，确保整个区间都为正且单调递增。
	start := time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC).Unix()
	end := time.Date(2100, 1, 1, 0, 0, 0, 0, time.UTC).Unix()

	var prev int64 = -1
	for sec := start; sec <= end; sec += 86400 * 365 {
		ticks := (sec + windowsEpochToUnixSec) * filetimeTicksPerSecond
		got := filetimeToTime(ticks).Unix()
		if got != sec {
			t.Fatalf("filetimeToTime 在 %d 处往返不一致：得到 %d", sec, got)
		}
		if got <= prev {
			t.Fatalf("时间戳未单调递增：%d 之后得到 %d", prev, got)
		}
		prev = got
	}
}

// TestFiletimeToTimeSubSecond 确认亚秒部分（100ns 计数余数）换算正确。
func TestFiletimeToTimeSubSecond(t *testing.T) {
	const baseSec = 1790436849
	// 加 0.5 秒 = 5,000,000 个 100ns 计数。
	ticks := (int64(baseSec)+windowsEpochToUnixSec)*filetimeTicksPerSecond + 5000000

	got := filetimeToTime(ticks)

	if got.Unix() != baseSec {
		t.Fatalf("秒部分 = %d, 期望 %d", got.Unix(), baseSec)
	}
	if got.Nanosecond() != 500000000 {
		t.Fatalf("纳秒部分 = %d, 期望 500000000", got.Nanosecond())
	}
}
