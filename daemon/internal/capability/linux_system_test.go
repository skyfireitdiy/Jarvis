//go:build linux

package capability

import (
	"os"
	"strings"
	"testing"
)

// TestLinuxSystemRegistered 验证系统信息能力已注册且平台正确。
func TestLinuxSystemRegistered(t *testing.T) {
	r := NewRegistry()
	c, ok := r.Get("linux.system.info")
	if !ok {
		t.Fatal("linux.system.info 应当已注册")
	}
	if c.Platform != PlatformLinux {
		t.Fatalf("平台应为 linux，实际 %q", c.Platform)
	}
	if c.Description == "" {
		t.Fatal("Description 不应为空")
	}
	if len(c.Parameters) == 0 {
		t.Fatal("Parameters 不应为空")
	}
}

// TestLinuxSystemInfoFields 真机验证各字段非空且类型正确。
func TestLinuxSystemInfoFields(t *testing.T) {
	r := NewRegistry()
	res := r.Execute("linux.system.info", map[string]any{})
	if !res.Success {
		t.Fatalf("执行失败: %s", res.Error)
	}
	data, ok := res.Data.(map[string]any)
	if !ok {
		t.Fatalf("返回类型应为 map[string]any，实际 %T", res.Data)
	}

	// 字符串字段应当非空。
	for _, key := range []string{"hostname", "kernel", "os_name", "arch", "cpu_model", "user", "home"} {
		v, ok := data[key]
		if !ok {
			t.Errorf("缺少字段 %s", key)
			continue
		}
		s, ok := v.(string)
		if !ok {
			t.Errorf("字段 %s 应为字符串，实际 %T", key, v)
			continue
		}
		if strings.TrimSpace(s) == "" {
			t.Errorf("字段 %s 不应为空", key)
		}
	}

	// 数值字段应当为正。
	if v, ok := data["cpu_count"].(int); !ok || v <= 0 {
		t.Errorf("cpu_count 应为正整数，实际 %v (%T)", data["cpu_count"], data["cpu_count"])
	}
	if v, ok := data["mem_total_kb"].(int64); !ok || v <= 0 {
		t.Errorf("mem_total_kb 应为正整数，实际 %v (%T)", data["mem_total_kb"], data["mem_total_kb"])
	}
	if v, ok := data["mem_available_kb"].(int64); !ok || v < 0 {
		t.Errorf("mem_available_kb 应为非负整数，实际 %v (%T)", data["mem_available_kb"], data["mem_available_kb"])
	}
	if v, ok := data["uptime_sec"].(int64); !ok || v <= 0 {
		t.Errorf("uptime_sec 应为正整数，实际 %v (%T)", data["uptime_sec"], data["uptime_sec"])
	}

	// 可用内存不应超过总内存。
	total := data["mem_total_kb"].(int64)
	avail := data["mem_available_kb"].(int64)
	if avail > total {
		t.Errorf("mem_available_kb (%d) 不应大于 mem_total_kb (%d)", avail, total)
	}

	// hostname 应与 os.Hostname 一致。
	wantHost, err := os.Hostname()
	if err == nil && data["hostname"] != wantHost {
		t.Errorf("hostname 应为 %q，实际 %q", wantHost, data["hostname"])
	}
}

// TestReadLinuxOSRelease 验证 /etc/os-release 解析。
func TestReadLinuxOSRelease(t *testing.T) {
	name, version := readLinuxOSRelease()
	if name == "" {
		t.Fatal("发行版名称不应为空（本机应存在 /etc/os-release）")
	}
	if version == "" {
		t.Log("警告：未能解析到发行版版本号（不同发行版字段可能不同）")
	}
	t.Logf("解析结果: name=%q version=%q", name, version)
}

// TestReadLinuxMemInfo 验证 /proc/meminfo 解析。
func TestReadLinuxMemInfo(t *testing.T) {
	total, avail := readLinuxMemInfo()
	if total <= 0 {
		t.Fatalf("MemTotal 应为正数，实际 %d", total)
	}
	if avail < 0 {
		t.Fatalf("MemAvailable 应为非负数，实际 %d", avail)
	}
	if avail > total {
		t.Fatalf("MemAvailable (%d) 不应大于 MemTotal (%d)", avail, total)
	}
}

// TestLinuxFormatBytes 覆盖字节格式化辅助函数。
func TestLinuxFormatBytes(t *testing.T) {
	cases := []struct {
		in   int64
		want string
	}{
		{0, "0 B"},
		{512, "512 B"},
		{1024, "1.0 KB"},
		{1536, "1.5 KB"},
		{1024 * 1024, "1.0 MB"},
		{1024 * 1024 * 1024, "1.0 GB"},
	}
	for _, tc := range cases {
		if got := linuxFormatBytes(tc.in); got != tc.want {
			t.Errorf("linuxFormatBytes(%d) = %q，期望 %q", tc.in, got, tc.want)
		}
	}
}

// TestLinuxPageSizeKB 验证页大小为正数。
func TestLinuxPageSizeKB(t *testing.T) {
	if got := linuxPageSizeKB(); got <= 0 {
		t.Fatalf("页大小应为正数，实际 %d", got)
	}
}
