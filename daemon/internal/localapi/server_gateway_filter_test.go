package localapi

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"jarvis-daemon/internal/auth"
	"jarvis-daemon/internal/wsclient"
)

// newGatewayFilterTestServer 起一个注入了网关黑白名单回调的测试服务。
//
// 用内存态模拟上层（main）持有的名单，避免依赖真实配置文件；
// 返回的指针指向当前 mode/patterns，便于断言 setter 是否被调用。
func newGatewayFilterTestServer(t *testing.T) (*httptest.Server, *string, *[]string) {
	t.Helper()
	store := auth.NewStore()
	manager := wsclient.NewManager(wsclient.Options{
		ClientID:          "test-client",
		Version:           "test",
		ReconnectMin:      0,
		ReconnectMax:      0,
		HeartbeatInterval: 0,
	})
	srv := New(store, manager, "1.2.3")
	mode := "off"
	var patterns []string
	srv.SetGatewayFilter(
		func() (string, []string) { return mode, patterns },
		func(m string, p []string) (string, []string, error) {
			mode, patterns = m, p
			return mode, patterns, nil
		},
	)
	ts := httptest.NewServer(srv.Handler())
	t.Cleanup(func() {
		ts.Close()
		manager.DisconnectAll()
	})
	return ts, &mode, &patterns
}

// gatewayFilterGet 发送 GET /api/gateway-filter 并解析响应。
func gatewayFilterGet(t *testing.T, base string) (int, map[string]any) {
	t.Helper()
	resp, err := http.Get(base + "/api/gateway-filter")
	if err != nil {
		t.Fatalf("get gateway-filter: %v", err)
	}
	defer resp.Body.Close()
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode gateway-filter response: %v", err)
	}
	return resp.StatusCode, out
}

// TestGatewayFilterGetDefault 验证未设置时 GET 返回 off + 空数组（而非 null）。
func TestGatewayFilterGetDefault(t *testing.T) {
	ts, _, _ := newGatewayFilterTestServer(t)

	code, out := gatewayFilterGet(t, ts.URL)
	if code != http.StatusOK {
		t.Fatalf("期望 200，实际 %d: %+v", code, out)
	}
	if out["mode"] != "off" {
		t.Fatalf("期望 mode=off，实际 %v", out["mode"])
	}
	patterns, ok := out["patterns"].([]any)
	if !ok {
		t.Fatalf("patterns 应为数组，实际 %T (%v)", out["patterns"], out["patterns"])
	}
	if len(patterns) != 0 {
		t.Fatalf("默认 patterns 应为空，实际 %v", patterns)
	}
}

// TestGatewayFilterPostThenGet 验证 POST 更新后 GET 能读到，且 setter 被真实调用。
func TestGatewayFilterPostThenGet(t *testing.T) {
	ts, mode, patterns := newGatewayFilterTestServer(t)

	body := map[string]any{
		"mode":     "whitelist",
		"patterns": []string{"example.com:443", "*.internal:8443"},
	}
	code, out := postJSON(t, ts.URL+"/api/gateway-filter", body)
	if code != http.StatusOK {
		t.Fatalf("期望 200，实际 %d: %+v", code, out)
	}
	if out["mode"] != "whitelist" {
		t.Fatalf("响应 mode 应为 whitelist，实际 %v", out["mode"])
	}
	if *mode != "whitelist" {
		t.Fatalf("setter 应更新内存态，实际 %q", *mode)
	}
	if len(*patterns) != 2 {
		t.Fatalf("setter 应收到 2 个 pattern，实际 %v", *patterns)
	}

	// 再 GET 一次，确认读回调返回的是更新后的值。
	code, out = gatewayFilterGet(t, ts.URL)
	if code != http.StatusOK {
		t.Fatalf("GET 期望 200，实际 %d: %+v", code, out)
	}
	if out["mode"] != "whitelist" {
		t.Fatalf("GET mode 应为 whitelist，实际 %v", out["mode"])
	}
	got, ok := out["patterns"].([]any)
	if !ok || len(got) != 2 {
		t.Fatalf("GET patterns 应为 2 项，实际 %v", out["patterns"])
	}
}

// TestGatewayFilterPostEmptyPatterns 验证 patterns 为空数组时合法（表示清空名单）。
func TestGatewayFilterPostEmptyPatterns(t *testing.T) {
	ts, _, patterns := newGatewayFilterTestServer(t)

	code, out := postJSON(t, ts.URL+"/api/gateway-filter", map[string]any{
		"mode":     "blacklist",
		"patterns": []string{},
	})
	if code != http.StatusOK {
		t.Fatalf("期望 200，实际 %d: %+v", code, out)
	}
	if len(*patterns) != 0 {
		t.Fatalf("patterns 应被清空，实际 %v", *patterns)
	}
}

// TestGatewayFilterPostInvalidMode 验证非法 mode 返回 400 且不调用 setter。
func TestGatewayFilterPostInvalidMode(t *testing.T) {
	ts, mode, _ := newGatewayFilterTestServer(t)

	// 注意：ValidMode 内部会 TrimSpace + 转小写，故 "WHITELIST " 视为合法，
	// 这里只列真正非法的值。
	for _, bad := range []string{"", "allow", "deny", "whitelistx", "1"} {
		code, out := postJSON(t, ts.URL+"/api/gateway-filter", map[string]any{
			"mode":     bad,
			"patterns": []string{"a:1"},
		})
		if code != http.StatusBadRequest {
			t.Fatalf("mode=%q 期望 400，实际 %d: %+v", bad, code, out)
		}
	}
	if *mode != "off" {
		t.Fatalf("非法 mode 不应改动内存态，实际 %q", *mode)
	}
}

// TestGatewayFilterPostInvalidJSON 验证请求体不是合法 JSON 时返回 400。
func TestGatewayFilterPostInvalidJSON(t *testing.T) {
	ts, _, _ := newGatewayFilterTestServer(t)

	resp, err := http.Post(ts.URL+"/api/gateway-filter", "application/json",
		bytes.NewBufferString("{not json"))
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("期望 400，实际 %d", resp.StatusCode)
	}
}

// TestGatewayFilterMethodNotAllowed 验证不支持的方法返回 405。
func TestGatewayFilterMethodNotAllowed(t *testing.T) {
	ts, _, _ := newGatewayFilterTestServer(t)

	req, err := http.NewRequest(http.MethodDelete, ts.URL+"/api/gateway-filter", nil)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("期望 405，实际 %d", resp.StatusCode)
	}
}

// TestGatewayFilterNotInjected 验证未注入 setter 时 POST 返回 501，
// 避免「看起来成功实则没生效」。
func TestGatewayFilterNotInjected(t *testing.T) {
	store := auth.NewStore()
	manager := wsclient.NewManager(wsclient.Options{ClientID: "c", Version: "v"})
	srv := New(store, manager, "1.2.3")
	ts := httptest.NewServer(srv.Handler())
	t.Cleanup(func() {
		ts.Close()
		manager.DisconnectAll()
	})

	code, out := postJSON(t, ts.URL+"/api/gateway-filter", map[string]any{
		"mode": "off",
	})
	if code != http.StatusNotImplemented {
		t.Fatalf("未注入 setter 时应返回 501，实际 %d: %+v", code, out)
	}
}

// TestIsLoopbackRequest 覆盖来源判定：只认回环，且不信任 X-Forwarded-For。
func TestIsLoopbackRequest(t *testing.T) {
	cases := []struct {
		name       string
		remoteAddr string
		xff        string
		want       bool
	}{
		{"ipv4 回环", "127.0.0.1:12345", "", true},
		{"ipv4 回环网段", "127.8.8.8:1", "", true},
		{"ipv6 回环", "[::1]:12345", "", true},
		{"localhost", "localhost:12345", "", true},
		{"公网 IPv4", "8.8.8.8:12345", "", false},
		{"内网 IPv4", "192.168.1.10:12345", "", false},
		{"无端口回环", "127.0.0.1", "", true},
		{"空", "", "", false},
		{"伪造 XFF 不能放行", "8.8.8.8:12345", "127.0.0.1", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, "/api/gateway-filter", nil)
			req.RemoteAddr = tc.remoteAddr
			if tc.xff != "" {
				req.Header.Set("X-Forwarded-For", tc.xff)
			}
			if got := isLoopbackRequest(req); got != tc.want {
				t.Fatalf("isLoopbackRequest(remote=%q, xff=%q) = %v，期望 %v",
					tc.remoteAddr, tc.xff, got, tc.want)
			}
		})
	}
}

// TestGatewayFilterRejectsNonLoopback 验证非回环来源一律 403（GET 与 POST 都拦）。
//
// 直接调用 handler（绕过 httptest.Server 的真实 TCP），以便伪造 RemoteAddr。
func TestGatewayFilterRejectsNonLoopback(t *testing.T) {
	srv := New(auth.NewStore(), wsclient.NewManager(wsclient.Options{ClientID: "c", Version: "v"}), "1.2.3")
	srv.SetGatewayFilter(
		func() (string, []string) { return "off", nil },
		func(m string, p []string) (string, []string, error) { return m, p, nil },
	)

	for _, method := range []string{http.MethodGet, http.MethodPost} {
		req := httptest.NewRequest(method, "/api/gateway-filter", nil)
		req.RemoteAddr = "203.0.113.7:5555"
		rec := httptest.NewRecorder()
		srv.handleGatewayFilter(rec, req)
		if rec.Code != http.StatusForbidden {
			t.Fatalf("%s 非回环来源期望 403，实际 %d", method, rec.Code)
		}
	}
}

// TestGatewayFilterAllowsLoopback 验证回环来源可正常读写（handler 层直接调用）。
func TestGatewayFilterAllowsLoopback(t *testing.T) {
	srv := New(auth.NewStore(), wsclient.NewManager(wsclient.Options{ClientID: "c", Version: "v"}), "1.2.3")
	srv.SetGatewayFilter(
		func() (string, []string) { return "off", nil },
		func(m string, p []string) (string, []string, error) { return m, p, nil },
	)

	req := httptest.NewRequest(http.MethodGet, "/api/gateway-filter", nil)
	req.RemoteAddr = "127.0.0.1:5555"
	rec := httptest.NewRecorder()
	srv.handleGatewayFilter(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("回环来源期望 200，实际 %d: %s", rec.Code, rec.Body.String())
	}
}
