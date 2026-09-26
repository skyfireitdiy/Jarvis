//go:build linux

package capability

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
)

// linuxProcessDefaultLimit 是 linux.process.list 未指定 limit 时返回的最大进程数。
const linuxProcessDefaultLimit = 200

// linuxProcessMaxLimit 是 limit 允许的最大值，防止一次性返回过多数据。
const linuxProcessMaxLimit = 5000

// linuxProcessSignalWhitelist 是允许发送的信号白名单。
//
// 用白名单而不是直接解析调用方传入的字符串，是为了避免把参数透传给
// syscall.Kill 时造成意外（例如 pid 为 0 / 负数会波及整个进程组或全部进程）。
var linuxProcessSignalWhitelist = map[string]syscall.Signal{
	"TERM": syscall.SIGTERM,
	"KILL": syscall.SIGKILL,
	"INT":  syscall.SIGINT,
	"HUP":  syscall.SIGHUP,
	"QUIT": syscall.SIGQUIT,
	"USR1": syscall.SIGUSR1,
	"USR2": syscall.SIGUSR2,
	"STOP": syscall.SIGSTOP,
	"CONT": syscall.SIGCONT,
	"15":   syscall.SIGTERM,
	"9":    syscall.SIGKILL,
	"2":    syscall.SIGINT,
	"1":    syscall.SIGHUP,
}

// registerLinuxProcess 注册 Linux 进程管理能力。
func registerLinuxProcess(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "linux.process.list",
		Description: "列出 Linux 系统当前进程，可按名称或命令行子串过滤。" +
			"数据直接读取 /proc，不依赖 ps 命令；无权限读取的进程会被跳过。",
		Platform: PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"filter": map[string]any{
					"type":        "string",
					"description": "按进程名（comm）或命令行（cmdline）子串过滤，大小写不敏感；为空时返回全部进程。",
				},
				"limit": map[string]any{
					"type":        "integer",
					"description": "最多返回的进程数，默认 200，最大 5000。",
				},
			},
		},
		Handler: handleLinuxProcessList,
	})

	_ = reg.Register(Capability{
		Name: "linux.process.kill",
		Description: "向指定进程发送信号，默认 SIGTERM。" +
			"仅允许 pid > 0 的正整数，信号必须在白名单内（TERM/KILL/INT/HUP/QUIT/USR1/USR2/STOP/CONT 或 15/9/2/1）。",
		Platform: PlatformLinux,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"pid": map[string]any{
					"type":        "integer",
					"description": "目标进程 PID，必须为正整数。",
				},
				"signal": map[string]any{
					"type":        "string",
					"description": "信号名或编号，默认 TERM；允许 TERM、KILL、INT、HUP、QUIT、USR1、USR2、STOP、CONT、15、9、2、1。",
				},
			},
			"required": []string{"pid"},
		},
		Handler: handleLinuxProcessKill,
	})
}

// handleLinuxProcessList 是 linux.process.list 的实现。
func handleLinuxProcessList(params map[string]any) (any, error) {
	filter, err := optionalString(params, "filter")
	if err != nil {
		return nil, err
	}
	limit, err := optionalInt(params, "limit", linuxProcessDefaultLimit)
	if err != nil {
		return nil, err
	}
	if limit <= 0 {
		return nil, fmt.Errorf("参数 limit 必须为正整数，实际 %d", limit)
	}
	if limit > linuxProcessMaxLimit {
		return nil, fmt.Errorf("参数 limit 超出上限 %d，实际 %d", linuxProcessMaxLimit, limit)
	}

	entries, err := os.ReadDir("/proc")
	if err != nil {
		return nil, fmt.Errorf("读取 /proc 失败: %w", err)
	}

	needle := strings.ToLower(filter)
	procs := make([]map[string]any, 0, 64)
	truncated := false

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		pid, err := strconv.Atoi(entry.Name())
		if err != nil {
			// 非数字目录（如 /proc/self、/proc/sys）直接跳过。
			continue
		}

		info, err := readLinuxProcessInfo(pid)
		if err != nil {
			// 进程可能已退出，或当前用户无权限读取，跳过即可。
			continue
		}

		if needle != "" {
			comm := strings.ToLower(info.comm)
			cmdline := strings.ToLower(info.cmdline)
			if !strings.Contains(comm, needle) && !strings.Contains(cmdline, needle) {
				continue
			}
		}

		if len(procs) >= limit {
			truncated = true
			break
		}

		procs = append(procs, map[string]any{
			"pid":        info.pid,
			"ppid":       info.ppid,
			"comm":       info.comm,
			"cmdline":    info.cmdline,
			"state":      info.state,
			"rss_kb":     info.rssKB,
			"start_time": info.startTime,
		})
	}

	// 按 PID 升序，保证输出稳定（ReadDir 本身有序，但过滤后仍显式排序更清晰）。
	sort.Slice(procs, func(i, j int) bool {
		return procs[i]["pid"].(int) < procs[j]["pid"].(int)
	})

	return map[string]any{
		"processes": procs,
		"count":     len(procs),
		"truncated": truncated,
	}, nil
}

// linuxProcessInfo 是从 /proc 解析出的进程信息。
type linuxProcessInfo struct {
	pid       int
	ppid      int
	comm      string
	cmdline   string
	state     string
	rssKB     int64
	startTime int64
}

// readLinuxProcessInfo 读取单个进程的信息。
//
// 数据来源：
//   - /proc/<pid>/stat：pid、ppid、comm、state、rss、starttime
//   - /proc/<pid>/cmdline：完整命令行（NUL 分隔）
func readLinuxProcessInfo(pid int) (*linuxProcessInfo, error) {
	statPath := filepath.Join("/proc", strconv.Itoa(pid), "stat")
	raw, err := os.ReadFile(statPath)
	if err != nil {
		return nil, err
	}

	info, err := parseLinuxProcStat(string(raw))
	if err != nil {
		return nil, err
	}
	info.pid = pid

	// cmdline 在僵尸进程或内核线程上可能为空，此时回退到 comm。
	cmdlinePath := filepath.Join("/proc", strconv.Itoa(pid), "cmdline")
	if cmdRaw, err := os.ReadFile(cmdlinePath); err == nil {
		parts := strings.Split(strings.TrimRight(string(cmdRaw), "\x00"), "\x00")
		nonEmpty := make([]string, 0, len(parts))
		for _, p := range parts {
			if p != "" {
				nonEmpty = append(nonEmpty, p)
			}
		}
		info.cmdline = strings.Join(nonEmpty, " ")
	}
	if info.cmdline == "" {
		info.cmdline = "[" + info.comm + "]"
	}

	return info, nil
}

// parseLinuxProcStat 解析 /proc/<pid>/stat 的内容。
//
// 格式为：pid (comm) state ppid ... 其中 comm 可能包含空格与括号，
// 因此不能简单按空格切分，需要从最后一个 ')' 处断开。
func parseLinuxProcStat(raw string) (*linuxProcessInfo, error) {
	open := strings.Index(raw, "(")
	closeIdx := strings.LastIndex(raw, ")")
	if open < 0 || closeIdx < 0 || closeIdx < open {
		return nil, fmt.Errorf("无法解析 stat 内容: %q", raw)
	}

	comm := raw[open+1 : closeIdx]
	rest := strings.Fields(strings.TrimSpace(raw[closeIdx+1:]))
	// rest 依次为：state ppid pgrp session tty_nr tpgid flags minflt cminflt
	// majflt cmajflt utime stime cutime cstime priority nice num_threads itrealvalue starttime ...
	if len(rest) < 20 {
		return nil, fmt.Errorf("stat 字段不足，实际 %d 个", len(rest))
	}

	ppid, err := strconv.Atoi(rest[1])
	if err != nil {
		return nil, fmt.Errorf("解析 ppid 失败: %w", err)
	}
	// rest[21] 是 rss（单位：页），字段不足时容错为 0。
	var rssPages int64
	if len(rest) > 21 {
		if v, err := strconv.ParseInt(rest[21], 10, 64); err == nil {
			rssPages = v
		}
	}
	var startTime int64
	if len(rest) > 19 {
		if v, err := strconv.ParseInt(rest[19], 10, 64); err == nil {
			startTime = v
		}
	}

	return &linuxProcessInfo{
		ppid:      ppid,
		comm:      comm,
		state:     rest[0],
		rssKB:     rssPages * int64(os.Getpagesize()) / 1024,
		startTime: startTime,
	}, nil
}

// handleLinuxProcessKill 是 linux.process.kill 的实现。
func handleLinuxProcessKill(params map[string]any) (any, error) {
	pid, err := optionalInt(params, "pid", 0)
	if err != nil {
		return nil, err
	}
	if pid == 0 {
		if _, ok := params["pid"]; !ok {
			return nil, fmt.Errorf("缺少必填参数 pid")
		}
	}
	// pid <= 0 必须拒绝：kill(0) 会作用于整个进程组，kill(-1) 会作用于全部进程。
	if pid <= 0 {
		return nil, fmt.Errorf("参数 pid 必须为正整数，实际 %d", pid)
	}

	signalName, err := optionalString(params, "signal")
	if err != nil {
		return nil, err
	}
	if signalName == "" {
		signalName = "TERM"
	}
	sig, ok := linuxProcessSignalWhitelist[strings.ToUpper(signalName)]
	if !ok {
		return nil, fmt.Errorf("参数 signal 不在白名单内: %q，允许值: TERM、KILL、INT、HUP、QUIT、USR1、USR2、STOP、CONT、15、9、2、1", signalName)
	}

	if err := syscall.Kill(pid, sig); err != nil {
		return nil, fmt.Errorf("向进程 %d 发送信号 %s 失败: %w", pid, strings.ToUpper(signalName), err)
	}

	return map[string]any{
		"pid":    pid,
		"signal": strings.ToUpper(signalName),
		"killed": true,
	}, nil
}
