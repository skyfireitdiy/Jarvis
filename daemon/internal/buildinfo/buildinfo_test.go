package buildinfo

import (
	"encoding/json"
	"os"
	"runtime"
	"testing"
	"time"
)

// TestCollectBasicFields 校验 Collect 填充了与运行环境相关的字段。
//
// 这些字段不依赖文件系统，任何平台都应稳定成立。
func TestCollectBasicFields(t *testing.T) {
	info := Collect("v9.9.9-test")

	if info.Version != "v9.9.9-test" {
		t.Errorf("Version = %q, 期望 %q", info.Version, "v9.9.9-test")
	}
	if info.GoVersion != runtime.Version() {
		t.Errorf("GoVersion = %q, 期望 %q", info.GoVersion, runtime.Version())
	}
	if info.OS != runtime.GOOS {
		t.Errorf("OS = %q, 期望 %q", info.OS, runtime.GOOS)
	}
	if info.Arch != runtime.GOARCH {
		t.Errorf("Arch = %q, 期望 %q", info.Arch, runtime.GOARCH)
	}
}

// TestCollectBuildTimeSource 校验编译时间来源标注合法，且时间戳与字符串自洽。
func TestCollectBuildTimeSource(t *testing.T) {
	info := Collect("test")

	switch info.BuildTimeSource {
	case "exe_mtime", "process_start", "unknown":
		// 合法取值。
	default:
		t.Fatalf("BuildTimeSource = %q, 非预期取值", info.BuildTimeSource)
	}

	if info.BuildTimeSource == "unknown" {
		// 极端环境（如 go run 且 /proc 不可用）：允许为空，但必须自洽。
		if info.BuildTime != "" || info.BuildTimeUnix != 0 {
			t.Errorf("source=unknown 时 BuildTime/BuildTimeUnix 应为空值, 实际 %q/%d",
				info.BuildTime, info.BuildTimeUnix)
		}
		return
	}

	parsed, err := time.Parse(time.RFC3339, info.BuildTime)
	if err != nil {
		t.Fatalf("BuildTime %q 无法按 RFC3339 解析: %v", info.BuildTime, err)
	}
	if parsed.Unix() != info.BuildTimeUnix {
		t.Errorf("BuildTimeUnix(%d) 与 BuildTime(%s -> %d) 不一致",
			info.BuildTimeUnix, info.BuildTime, parsed.Unix())
	}

	// 编译时间不应晚于「现在 + 少量容差」，也不应早于 2000 年（明显异常）。
	now := time.Now()
	if parsed.After(now.Add(time.Minute)) {
		t.Errorf("BuildTime %s 晚于当前时间 %s", parsed, now)
	}
	if parsed.Before(time.Date(2000, 1, 1, 0, 0, 0, 0, time.UTC)) {
		t.Errorf("BuildTime %s 早于 2000-01-01，明显异常", parsed)
	}
}

// TestAsMapKeys 校验 AsMap 输出的键集合完整且与结构体字段一致。
func TestAsMapKeys(t *testing.T) {
	info := Collect("v1.2.3")
	m := info.AsMap()

	wantKeys := []string{
		"version", "build_time", "build_time_unix", "build_time_source",
		"go_version", "os", "arch", "exe_path",
		"exe_mtime", "commit", "commit_time", "vcs_modified",
		"pid", "started_at", "started_at_unix",
	}
	if len(m) != len(wantKeys) {
		t.Errorf("AsMap 键数量 = %d, 期望 %d (keys=%v)", len(m), len(wantKeys), m)
	}
	for _, k := range wantKeys {
		if _, ok := m[k]; !ok {
			t.Errorf("AsMap 缺少键 %q", k)
		}
	}

	// 抽查若干值是否与结构体一致（避免整体替换字段时漏改）。
	if m["version"] != info.Version {
		t.Errorf("AsMap[version] = %v, 期望 %q", m["version"], info.Version)
	}
	if m["build_time"] != info.BuildTime {
		t.Errorf("AsMap[build_time] = %v, 期望 %q", m["build_time"], info.BuildTime)
	}
	if m["build_time_unix"] != info.BuildTimeUnix {
		t.Errorf("AsMap[build_time_unix] = %v, 期望 %d", m["build_time_unix"], info.BuildTimeUnix)
	}
	if m["build_time_source"] != info.BuildTimeSource {
		t.Errorf("AsMap[build_time_source] = %v, 期望 %q", m["build_time_source"], info.BuildTimeSource)
	}
	if m["go_version"] != info.GoVersion {
		t.Errorf("AsMap[go_version] = %v, 期望 %q", m["go_version"], info.GoVersion)
	}
	if m["os"] != info.OS {
		t.Errorf("AsMap[os] = %v, 期望 %q", m["os"], info.OS)
	}
	if m["arch"] != info.Arch {
		t.Errorf("AsMap[arch] = %v, 期望 %q", m["arch"], info.Arch)
	}
	if m["exe_path"] != info.ExePath {
		t.Errorf("AsMap[exe_path] = %v, 期望 %q", m["exe_path"], info.ExePath)
	}
}

// TestAsMapJSONRoundTrip 校验 AsMap 结果可被 JSON 序列化（hello 消息要求）。
func TestAsMapJSONRoundTrip(t *testing.T) {
	m := Collect("v1.0.0").AsMap()
	if _, err := json.Marshal(m); err != nil {
		t.Fatalf("AsMap 结果无法 JSON 序列化: %v", err)
	}
}

// TestCollectPIDAndStartedAt 校验进程号与启动时间被采集。
//
// 这两个字段用于区分「同一个 exe 被重启了多次」，是排查部署问题的关键依据。
func TestCollectPIDAndStartedAt(t *testing.T) {
	info := Collect("v1.0.0")

	if info.PID <= 0 {
		t.Errorf("PID = %d, 期望正数", info.PID)
	}
	if info.PID != os.Getpid() {
		t.Errorf("PID = %d, 期望 %d", info.PID, os.Getpid())
	}

	// Linux 上 processStartTime 走 /proc，应当可用；darwin 上降级为空串。
	if info.StartedAt != "" {
		parsed, err := time.Parse(time.RFC3339, info.StartedAt)
		if err != nil {
			t.Fatalf("StartedAt %q 不是合法 RFC3339: %v", info.StartedAt, err)
		}
		if parsed.After(time.Now().Add(time.Minute)) {
			t.Errorf("StartedAt %s 晚于当前时间，明显异常", parsed)
		}
		if info.StartedAtUnix != parsed.Unix() {
			t.Errorf("StartedAtUnix = %d, 与 StartedAt(%d) 不一致", info.StartedAtUnix, parsed.Unix())
		}
	}
}

// TestExeMTimeMatchesBuildTime 校验 exe_mtime 与 build_time 同源。
//
// 两者都取自 exe 的 mtime，仅字段名不同（exe_mtime 语义更直白）。
// 若 BuildTimeSource 不是 exe_mtime（拿不到 exe 信息），则两者都应为空。
func TestExeMTimeMatchesBuildTime(t *testing.T) {
	info := Collect("v1.0.0")

	if info.BuildTimeSource == "exe_mtime" {
		if info.ExeMTime == "" {
			t.Error("source=exe_mtime 时 ExeMTime 不应为空")
		}
		if info.ExeMTime != info.BuildTime {
			t.Errorf("ExeMTime = %q, 期望与 BuildTime(%q) 相同", info.ExeMTime, info.BuildTime)
		}
	} else if info.ExeMTime != "" {
		t.Errorf("source=%s 时 ExeMTime 期望为空，实际 %q", info.BuildTimeSource, info.ExeMTime)
	}
}

// TestCollectVCSInfoDoesNotPanic 校验 VCS 信息采集在缺少 build info 时优雅降级。
//
// go test 构建的二进制通常带 vcs 信息，但 -buildvcs=false 或 go run 时可能没有。
// 本测试只要求不 panic、字段格式合法，不假设 vcs 信息一定存在。
func TestCollectVCSInfoDoesNotPanic(t *testing.T) {
	info := Collect("v1.0.0")

	if info.Commit != "" && len(info.Commit) > 12 {
		t.Errorf("Commit = %q，期望短版（不超过 12 位）", info.Commit)
	}
	if info.CommitTime != "" {
		if _, err := time.Parse(time.RFC3339, info.CommitTime); err != nil {
			t.Errorf("CommitTime %q 不是合法 RFC3339: %v", info.CommitTime, err)
		}
	}
}
