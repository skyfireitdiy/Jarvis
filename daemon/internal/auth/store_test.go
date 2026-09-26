package auth

import (
	"sync"
	"testing"
)

func TestNormalizeGateway(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"", ""},
		{"   ", ""},
		{"https://jvs-ai.cn", "https://jvs-ai.cn"},
		{"https://jvs-ai.cn/", "https://jvs-ai.cn"},
		{"https://jvs-ai.cn///", "https://jvs-ai.cn"},
		{"  https://jvs-ai.cn/  ", "https://jvs-ai.cn"},
		{"127.0.0.1:8000", "http://127.0.0.1:8000"},
		{"127.0.0.1:8000/", "http://127.0.0.1:8000"},
		{"HTTP://Host:8000/", "HTTP://Host:8000"},
		{"jvs-ai.cn", "http://jvs-ai.cn"},
	}
	for _, c := range cases {
		if got := NormalizeGateway(c.in); got != c.want {
			t.Errorf("NormalizeGateway(%q) = %q，期望 %q", c.in, got, c.want)
		}
	}
}

func TestGatewayKeyIgnoresScheme(t *testing.T) {
	// 协议差异必须视为同一网关（刻意设计，与扩展一致）。
	a := GatewayKey("http://h.example:443")
	b := GatewayKey("https://h.example:443")
	if a != b {
		t.Errorf("协议差异应同键：%q != %q", a, b)
	}
	if a != "h.example:443" {
		t.Errorf("GatewayKey 结果不符：%q", a)
	}

	// 端口缺省时的默认端口。
	if got := GatewayKey("https://h.example"); got != "h.example:443" {
		t.Errorf("https 默认端口应为 443，实际 %q", got)
	}
	if got := GatewayKey("http://h.example"); got != "h.example:80" {
		t.Errorf("http 默认端口应为 80，实际 %q", got)
	}
	if got := GatewayKey("h.example:8000"); got != "h.example:8000" {
		t.Errorf("无协议输入应补 http 后取 host:port，实际 %q", got)
	}
	if got := GatewayKey(""); got != "" {
		t.Errorf("空输入应返回空键，实际 %q", got)
	}
}

func TestStoreMultiGatewayIsolation(t *testing.T) {
	s := NewStore()
	s.Set("http://127.0.0.1:8000", "tok-local")
	s.Set("https://jvs-ai.cn", "tok-remote")

	if len(s.List()) != 2 {
		t.Fatalf("应有 2 条凭据，实际 %d", len(s.List()))
	}

	local, err := s.Get("http://127.0.0.1:8000")
	if err != nil {
		t.Fatalf("Get 本地网关报错: %v", err)
	}
	if local.Token != "tok-local" {
		t.Errorf("本地网关 token 不符: %+v", local)
	}

	remote, err := s.Get("https://jvs-ai.cn")
	if err != nil {
		t.Fatalf("Get 远程网关报错: %v", err)
	}
	if remote.Token != "tok-remote" {
		t.Errorf("远程网关 token 不符: %+v", remote)
	}

	// 未认证的第三个网关应返回 ErrNoCredentials。
	if _, err := s.Get("http://other:9000"); err != ErrNoCredentials {
		t.Errorf("未认证网关应返回 ErrNoCredentials，实际 %v", err)
	}
}

func TestStoreSetOverwritesSameGateway(t *testing.T) {
	s := NewStore()
	s.Set("http://127.0.0.1:8000", "old")
	s.Set("https://jvs-ai.cn", "remote")
	// 同网关（含协议差异）重复 Set 应覆盖，且不影响其他网关。
	s.Set("https://127.0.0.1:8000", "new")

	if len(s.List()) != 2 {
		t.Fatalf("覆盖后应仍为 2 条，实际 %d", len(s.List()))
	}
	creds, err := s.Get("http://127.0.0.1:8000")
	if err != nil {
		t.Fatalf("Get 报错: %v", err)
	}
	if creds.Token != "new" {
		t.Errorf("覆盖后 token 应为 new，实际 %q", creds.Token)
	}
	remote, err := s.Get("https://jvs-ai.cn")
	if err != nil || remote.Token != "remote" {
		t.Errorf("覆盖不应影响其他网关: %+v err=%v", remote, err)
	}
}

func TestStoreClearSingleGateway(t *testing.T) {
	s := NewStore()
	s.Set("http://127.0.0.1:8000", "a")
	s.Set("https://jvs-ai.cn", "b")

	s.Clear("http://127.0.0.1:8000")

	if s.Has("http://127.0.0.1:8000") {
		t.Error("Clear 后该网关 Has 应为 false")
	}
	if s.TokenValid("http://127.0.0.1:8000") {
		t.Error("Clear 后该网关 TokenValid 应为 false")
	}
	if _, err := s.Get("http://127.0.0.1:8000"); err != ErrNoCredentials {
		t.Errorf("Clear 后 Get 应返回 ErrNoCredentials，实际 %v", err)
	}
	// 其他网关不受影响。
	if !s.Has("https://jvs-ai.cn") {
		t.Error("Clear 单网关不应影响其他网关")
	}
	if len(s.List()) != 1 {
		t.Errorf("Clear 后应剩 1 条，实际 %d", len(s.List()))
	}
}

func TestStoreClearAll(t *testing.T) {
	s := NewStore()
	s.Set("http://127.0.0.1:8000", "a")
	s.Set("https://jvs-ai.cn", "b")

	s.ClearAll()

	if len(s.List()) != 0 {
		t.Errorf("ClearAll 后应无凭据，实际 %d", len(s.List()))
	}
	if s.Has("http://127.0.0.1:8000") || s.Has("https://jvs-ai.cn") {
		t.Error("ClearAll 后 Has 应均为 false")
	}
	if _, err := s.Get("https://jvs-ai.cn"); err != ErrNoCredentials {
		t.Errorf("ClearAll 后 Get 应返回 ErrNoCredentials，实际 %v", err)
	}
}

func TestStoreMarkTokenInvalid(t *testing.T) {
	s := NewStore()
	s.Set("https://jvs-ai.cn", "t")
	s.Set("http://127.0.0.1:8000", "other")

	s.MarkTokenInvalid("https://jvs-ai.cn")

	if !s.Has("https://jvs-ai.cn") {
		t.Error("标记失效不应清空凭据")
	}
	if s.TokenValid("https://jvs-ai.cn") {
		t.Error("标记后 TokenValid 应为 false")
	}
	// 只影响该网关。
	if !s.TokenValid("http://127.0.0.1:8000") {
		t.Error("标记单个网关不应影响其他网关的 TokenValid")
	}
	// 重新 Set 应恢复有效。
	s.Set("https://jvs-ai.cn", "t2")
	if !s.TokenValid("https://jvs-ai.cn") {
		t.Error("重新 Set 后 TokenValid 应恢复为 true")
	}
}

func TestStoreMarkTokenInvalidWithoutCreds(t *testing.T) {
	s := NewStore()
	s.MarkTokenInvalid("https://jvs-ai.cn") // 不应 panic
	if s.Has("https://jvs-ai.cn") {
		t.Error("无凭据时标记不应产生凭据")
	}
	if s.TokenValid("https://jvs-ai.cn") {
		t.Error("无凭据时 TokenValid 应为 false")
	}
}

func TestStoreEmptyGatewayNoop(t *testing.T) {
	s := NewStore()
	s.Set("", "t")
	s.Set("   ", "t")
	if len(s.List()) != 0 {
		t.Errorf("空网关不应写入凭据，实际 %d", len(s.List()))
	}
	if s.Has("") || s.TokenValid("") {
		t.Error("空网关 Has/TokenValid 应为 false")
	}
	s.Clear("") // 不应 panic
	s.MarkTokenInvalid("")
}

func TestStoreListReturnsCopy(t *testing.T) {
	s := NewStore()
	s.Set("https://jvs-ai.cn", "t")
	list := s.List()
	list[0].Token = "mutated"
	creds, err := s.Get("https://jvs-ai.cn")
	if err != nil {
		t.Fatalf("Get 报错: %v", err)
	}
	if creds.Token != "t" {
		t.Errorf("List 返回的应是副本，内部数据被篡改: %q", creds.Token)
	}
}

func TestStoreConcurrentAccess(t *testing.T) {
	s := NewStore()
	gateways := []string{
		"http://127.0.0.1:8000",
		"https://jvs-ai.cn",
		"http://other:9000",
	}
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			g := gateways[n%len(gateways)]
			s.Set(g, "tok")
			_, _ = s.Get(g)
			s.Has(g)
			s.TokenValid(g)
			s.List()
			s.MarkTokenInvalid(g)
			if n%5 == 0 {
				s.Clear(g)
			}
			if n%7 == 0 {
				s.ClearAll()
			}
		}(i)
	}
	wg.Wait()
}
