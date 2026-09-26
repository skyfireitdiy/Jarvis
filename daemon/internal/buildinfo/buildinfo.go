// Package buildinfo 提供守护进程的构建信息（编译时间、Go 版本、目标平台等）。
//
// 设计取舍：编译时间用**可执行文件自身的修改时间（mtime）**，而不是通过
// -ldflags "-X ..." 注入。原因：
//   - 注入会破坏可复现构建（同样源码两次构建产出不同二进制）；
//   - 用户明确回复「可以」采用 mtime 方案；
//   - mtime 在绝大多数场景下就等于构建/替换 exe 的时间，足够表征「这版是什么时候编的」。
//
// 局限（如实说明）：如果 exe 被复制/解压后 mtime 被重置（如某些归档工具），
// 上报的时间会失真。此时可回退到进程启动时间作为近似。
package buildinfo

import (
	"os"
	"runtime"
	"runtime/debug"
	"time"
)

// Info 是守护进程的构建/运行环境信息。
type Info struct {
	// Version 是守护进程版本号（由 main 包通过 -ldflags 或默认值提供）。
	Version string `json:"version"`
	// BuildTime 是推断出的编译时间（exe 的 mtime），RFC3339 格式；未知时为空串。
	BuildTime string `json:"build_time"`
	// BuildTimeUnix 是 BuildTime 的 Unix 秒时间戳；未知时为 0。
	BuildTimeUnix int64 `json:"build_time_unix"`
	// BuildTimeSource 说明 BuildTime 的来源，便于排查（如 "exe_mtime"、"process_start"、"unknown"）。
	BuildTimeSource string `json:"build_time_source"`
	// GoVersion 是编译本二进制的 Go 版本。
	GoVersion string `json:"go_version"`
	// OS 是目标操作系统（如 windows、linux、darwin）。
	OS string `json:"os"`
	// Arch 是目标架构（如 amd64、arm64）。
	Arch string `json:"arch"`
	// ExePath 是当前可执行文件的绝对路径；获取失败时为空串。
	ExePath string `json:"exe_path"`
	// ExeMTime 是可执行文件的修改时间（RFC3339），即通常所说的「编译时间」；
	// 与 BuildTime 同源，单独保留该字段名是为了让调用方语义更直观。
	ExeMTime string `json:"exe_mtime"`
	// Commit 是构建时的 VCS 版本号（git commit），取短版（前 12 位）；未知时为空串。
	Commit string `json:"commit"`
	// CommitTime 是构建时 VCS 提交时间（RFC3339）；未知时为空串。
	CommitTime string `json:"commit_time"`
	// VCSModified 表示构建时工作区是否有未提交改动；信息不可用时为 false。
	VCSModified bool `json:"vcs_modified"`
	// PID 是当前守护进程的进程号，用于区分重启后的不同实例。
	PID int `json:"pid"`
	// StartedAt 是进程启动时间（RFC3339）；获取失败时为空串。
	StartedAt string `json:"started_at"`
	// StartedAtUnix 是 StartedAt 的 Unix 秒时间戳；未知时为 0。
	StartedAtUnix int64 `json:"started_at_unix"`
}

// Collect 采集当前进程的构建信息。
//
// version 由调用方传入（main 包中的 version 变量）。
// 本函数不会返回错误：任何一项采集失败都降级为空值，保证 hello 消息始终可发送。
func Collect(version string) Info {
	info := Info{
		Version:         version,
		GoVersion:       runtime.Version(),
		OS:              runtime.GOOS,
		Arch:            runtime.GOARCH,
		BuildTimeSource: "unknown",
		PID:             os.Getpid(),
	}

	exePath, err := os.Executable()
	if err == nil {
		info.ExePath = exePath

		if fi, statErr := os.Stat(exePath); statErr == nil {
			info.BuildTime = fi.ModTime().UTC().Format(time.RFC3339)
			info.BuildTimeUnix = fi.ModTime().Unix()
			info.BuildTimeSource = "exe_mtime"
			// exe_mtime 与 build_time 同源，语义更直白，便于调用方直接展示。
			info.ExeMTime = info.BuildTime
		}
	}

	// 回退：拿不到 exe mtime 时，用进程启动时间近似（至少能给出「这版大概何时跑的」）。
	if info.BuildTimeSource == "unknown" {
		if start, ok := processStartTime(); ok {
			info.BuildTime = start.UTC().Format(time.RFC3339)
			info.BuildTimeUnix = start.Unix()
			info.BuildTimeSource = "process_start"
		}
	}

	// 进程启动时间：无论 exe mtime 是否可用都独立采集，
	// 用于区分「同一个 exe 被重启了多次」的场景。
	if start, ok := processStartTime(); ok {
		info.StartedAt = start.UTC().Format(time.RFC3339)
		info.StartedAtUnix = start.Unix()
	}

	// VCS 信息来自 Go 构建时嵌入的 build info。
	// 未用 go build 构建（如 go run）、或构建时加了 -buildvcs=false 时，
	// ReadBuildInfo 可能返回 nil 或缺少 vcs 设置项，此时相关字段保持零值。
	collectVCSInfo(&info)

	return info
}

// collectVCSInfo 从 runtime/debug.ReadBuildInfo 提取 VCS 版本信息。
//
// 这些信息由 Go 工具链在构建时自动嵌入（无需 ldflags），因此不破坏可复现构建。
// 任何一项缺失都静默跳过，保证函数不 panic、不报错。
func collectVCSInfo(info *Info) {
	bi, ok := debug.ReadBuildInfo()
	if !ok || bi == nil {
		return
	}
	for _, setting := range bi.Settings {
		switch setting.Key {
		case "vcs.revision":
			rev := setting.Value
			// 取短版：git 完整哈希 40 位，前 12 位足以区分且便于阅读。
			const shortLen = 12
			if len(rev) > shortLen {
				rev = rev[:shortLen]
			}
			info.Commit = rev
		case "vcs.time":
			// vcs.time 是 RFC3339 格式（如 2026-09-26T07:30:00Z），原样上报。
			info.CommitTime = setting.Value
		case "vcs.modified":
			info.VCSModified = setting.Value == "true"
		}
	}
}

// AsMap 把 Info 转为 map，便于塞进 hello 消息（网关侧按 JSON 对象解析）。
func (i Info) AsMap() map[string]any {
	return map[string]any{
		"version":           i.Version,
		"build_time":        i.BuildTime,
		"build_time_unix":   i.BuildTimeUnix,
		"build_time_source": i.BuildTimeSource,
		"go_version":        i.GoVersion,
		"os":                i.OS,
		"arch":              i.Arch,
		"exe_path":          i.ExePath,
		"exe_mtime":         i.ExeMTime,
		"commit":            i.Commit,
		"commit_time":       i.CommitTime,
		"vcs_modified":      i.VCSModified,
		"pid":               i.PID,
		"started_at":        i.StartedAt,
		"started_at_unix":   i.StartedAtUnix,
	}
}
