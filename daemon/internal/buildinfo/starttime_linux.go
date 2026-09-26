//go:build linux

package buildinfo

import (
	"os"
	"strconv"
	"strings"
	"time"
)

// processStartTime 通过 /proc/self/stat 的第 22 个字段（starttime，单位 jiffies）
// 推算进程启动时间。
//
// 该字段是进程启动后经过的时钟滴答数，需要除以系统时钟频率（USER_HZ）换算为秒。
// USER_HZ 在 Linux 上恒为 100（POSIX 约定，且 Go 运行时也按此假设），因此这里
// 直接用 100 换算，避免引入 sysconf 调用。
//
// 获取失败时返回 ok=false。
func processStartTime() (time.Time, bool) {
	data, err := os.ReadFile("/proc/self/stat")
	if err != nil {
		return time.Time{}, false
	}

	content := string(data)
	// 进程名可能含空格并被括号包裹（如 "(my proc)"），因此从最后一个 ')' 之后开始切分。
	idx := strings.LastIndexByte(content, ')')
	if idx < 0 || idx+2 >= len(content) {
		return time.Time{}, false
	}
	fields := strings.Fields(content[idx+2:])
	// 切分后 fields[0] 对应 stat 的第 3 个字段（state）；
	// starttime 是第 22 个字段，故下标为 22-3 = 19。
	const starttimeIndex = 19
	if len(fields) <= starttimeIndex {
		return time.Time{}, false
	}

	jiffies, err := strconv.ParseInt(fields[starttimeIndex], 10, 64)
	if err != nil {
		return time.Time{}, false
	}

	// 系统启动时间 + 进程已运行的秒数 = 进程启动时刻。
	bootTime, ok := systemBootTime()
	if !ok {
		return time.Time{}, false
	}

	const userHZ = 100
	start := bootTime.Add(time.Duration(jiffies/userHZ) * time.Second)
	return start, true
}

// systemBootTime 读取 /proc/stat 的 btime 行（系统启动的 Unix 时间戳）。
func systemBootTime() (time.Time, bool) {
	data, err := os.ReadFile("/proc/stat")
	if err != nil {
		return time.Time{}, false
	}
	for _, line := range strings.Split(string(data), "\n") {
		if !strings.HasPrefix(line, "btime ") {
			continue
		}
		sec, err := strconv.ParseInt(strings.TrimSpace(strings.TrimPrefix(line, "btime ")), 10, 64)
		if err != nil {
			return time.Time{}, false
		}
		return time.Unix(sec, 0), true
	}
	return time.Time{}, false
}
