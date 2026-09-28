package gatewayfilter

import (
	"reflect"
	"testing"
)

func TestMatch(t *testing.T) {
	cases := []struct {
		name    string
		pattern string
		input   string
		want    bool
	}{
		{"精确匹配", "example.com:8000", "example.com:8000", true},
		{"精确不匹配", "example.com:8000", "example.com:8001", false},
		{"星号前缀", "*.example.com:8000", "a.example.com:8000", true},
		{"星号前缀不匹配根域", "*.example.com:8000", "example.com:8000", false},
		{"星号匹配任意含空", "a*b", "ab", true},
		{"星号匹配中间", "a*b", "axxxb", true},
		{"星号在末尾", "192.168.*", "192.168.1.5:8000", true},
		{"星号在开头", "*:8000", "anything:8000", true},
		{"仅星号匹配一切", "*", "whatever:1234", true},
		{"问号单字符", "a?c", "abc", true},
		{"问号不匹配多字符", "a?c", "abbc", false},
		{"问号不匹配空", "a?c", "ac", false},
		{"大小写不敏感 pattern", "Example.COM:8000", "example.com:8000", true},
		{"大小写不敏感 input", "example.com:8000", "EXAMPLE.COM:8000", true},
		{"前后空白 trim", "  example.com:8000  ", "example.com:8000", true},
		{"空 pattern 空 input", "", "", true},
		{"空 pattern 非空 input", "", "x", false},
		{"端口通配", "192.168.*:*", "192.168.1.5:9999", true},
		{"多段星号", "*.example.*:8000", "a.example.com:8000", true},
		{"不匹配前缀", "example.com:8000", "xexample.com:8000", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := Match(c.pattern, c.input); got != c.want {
				t.Fatalf("Match(%q, %q) = %v, want %v", c.pattern, c.input, got, c.want)
			}
		})
	}
}

func TestNormalizeMode(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"off", ModeOff},
		{"OFF", ModeOff},
		{" off ", ModeOff},
		{"whitelist", ModeWhitelist},
		{"WhiteList", ModeWhitelist},
		{"blacklist", ModeBlacklist},
		{"BLACKLIST", ModeBlacklist},
		{"", ModeOff},
		{"garbage", ModeOff},
	}
	for _, c := range cases {
		if got := NormalizeMode(c.in); got != c.want {
			t.Errorf("NormalizeMode(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestValidMode(t *testing.T) {
	for _, m := range []string{"off", "whitelist", "blacklist", "OFF", " Whitelist "} {
		if !ValidMode(m) {
			t.Errorf("ValidMode(%q) = false, want true", m)
		}
	}
	for _, m := range []string{"", "none", "allow", "deny"} {
		if ValidMode(m) {
			t.Errorf("ValidMode(%q) = true, want false", m)
		}
	}
}

func TestAllowsOffMode(t *testing.T) {
	f := New(ModeOff, []string{"example.com:8000"})
	// off 模式恒允许，即使命中名单。
	if !f.Allows("example.com:8000") {
		t.Fatal("off 模式应允许所有网关")
	}
	if !f.Allows("other.com:9000") {
		t.Fatal("off 模式应允许所有网关")
	}
}

func TestAllowsWhitelist(t *testing.T) {
	f := New(ModeWhitelist, []string{"*.example.com:8000", "192.168.1.5:*"})
	if !f.Allows("a.example.com:8000") {
		t.Fatal("白名单命中应允许")
	}
	if !f.Allows("192.168.1.5:9999") {
		t.Fatal("白名单命中应允许")
	}
	if f.Allows("other.com:8000") {
		t.Fatal("白名单未命中应拒绝")
	}
}

func TestAllowsWhitelistEmpty(t *testing.T) {
	f := New(ModeWhitelist, nil)
	// 空白名单 = 谁都不允许（安全方向）。
	if f.Allows("example.com:8000") {
		t.Fatal("空白名单应拒绝所有网关")
	}
}

func TestAllowsBlacklist(t *testing.T) {
	f := New(ModeBlacklist, []string{"*.example.com:8000"})
	if f.Allows("a.example.com:8000") {
		t.Fatal("黑名单命中应拒绝")
	}
	if !f.Allows("other.com:8000") {
		t.Fatal("黑名单未命中应允许")
	}
}

func TestAllowsBlacklistEmpty(t *testing.T) {
	f := New(ModeBlacklist, nil)
	// 空黑名单 = 不限制。
	if !f.Allows("example.com:8000") {
		t.Fatal("空黑名单应允许所有网关")
	}
}

func TestNilFilterAllows(t *testing.T) {
	var f *Filter
	if !f.Allows("anything:1234") {
		t.Fatal("nil Filter 应允许所有网关")
	}
	mode, patterns := f.Snapshot()
	if mode != ModeOff || patterns != nil {
		t.Fatalf("nil Filter Snapshot = (%q, %v), want (off, nil)", mode, patterns)
	}
	// Set 对 nil 应为 no-op，不 panic。
	f.Set(ModeWhitelist, []string{"x"})
}

func TestHostPortNormalization(t *testing.T) {
	f := New(ModeWhitelist, []string{"example.com:8000"})
	// 带协议 / 不带协议 / 带尾斜杠 都应命中同一 host:port。
	for _, gw := range []string{
		"http://example.com:8000",
		"https://example.com:8000",
		"example.com:8000",
		"http://example.com:8000/",
	} {
		if !f.Allows(gw) {
			t.Errorf("Allows(%q) = false, want true（应归一化为 example.com:8000）", gw)
		}
	}
}

func TestHostPortDefaultPort(t *testing.T) {
	// 无端口时 https/wss→443、http/ws→80。
	fHTTPS := New(ModeWhitelist, []string{"example.com:443"})
	if !fHTTPS.Allows("https://example.com") {
		t.Fatal("https 无端口应归一化为 443")
	}
	fHTTP := New(ModeWhitelist, []string{"example.com:80"})
	if !fHTTP.Allows("http://example.com") {
		t.Fatal("http 无端口应归一化为 80")
	}
	fWSS := New(ModeWhitelist, []string{"example.com:443"})
	if !fWSS.Allows("wss://example.com") {
		t.Fatal("wss 无端口应归一化为 443")
	}
	fWS := New(ModeWhitelist, []string{"example.com:80"})
	if !fWS.Allows("ws://example.com") {
		t.Fatal("ws 无端口应归一化为 80")
	}
}

// TestHostPortWebSocketScheme 回归测试：daemon 连接的网关地址天然可能是
// ws:// 或 wss:// 形式。若 hostPort 不识别这两种协议，会被误加 "http://"
// 前缀，url.Parse 把 "ws" 当成主机名、端口丢失，导致黑白名单静默失配。
func TestHostPortWebSocketScheme(t *testing.T) {
	f := New(ModeBlacklist, []string{"bad.example.com:*"})
	for _, gw := range []string{
		"ws://bad.example.com:9999",
		"wss://bad.example.com:9999",
	} {
		if f.Allows(gw) {
			t.Errorf("Allows(%q) = true, want false（ws/wss 应正确归一化并命中黑名单）", gw)
		}
	}
	// 未命中的 ws 地址仍应放行。
	if !f.Allows("ws://ok.example.com:9999") {
		t.Error("Allows(ws://ok.example.com:9999) = false, want true")
	}
}

func TestSetAndSnapshot(t *testing.T) {
	f := New(ModeOff, nil)
	f.Set(ModeBlacklist, []string{" a:1 ", "", "  b:2  "})
	mode, patterns := f.Snapshot()
	if mode != ModeBlacklist {
		t.Fatalf("mode = %q, want blacklist", mode)
	}
	// 空项应被过滤，其余 trim。
	if !reflect.DeepEqual(patterns, []string{"a:1", "b:2"}) {
		t.Fatalf("patterns = %v, want [a:1 b:2]", patterns)
	}
	// Snapshot 返回副本：修改返回值不应影响内部状态。
	patterns[0] = "mutated"
	_, again := f.Snapshot()
	if again[0] != "a:1" {
		t.Fatal("Snapshot 应返回副本，外部修改不应影响内部")
	}
}

func TestAllowsEmptyGateway(t *testing.T) {
	// 无法归一化的空地址：白名单拒绝、黑名单放行。
	wl := New(ModeWhitelist, []string{"*"})
	if wl.Allows("") {
		t.Fatal("白名单下空地址应拒绝")
	}
	bl := New(ModeBlacklist, []string{"*"})
	if !bl.Allows("") {
		t.Fatal("黑名单下空地址应放行")
	}
}
