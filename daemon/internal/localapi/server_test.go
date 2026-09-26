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

// newTestServer 构造一个使用真实 HTTP 的测试服务（httptest，不依赖固定端口）。
//
// Manager 的客户端指向不可达地址，连接会失败并进入重连，但状态查询与
// 凭据存储的行为不受影响；测试结束统一 DisconnectAll 避免 goroutine 泄漏。
func newTestServer(t *testing.T) (*httptest.Server, *auth.Store, *wsclient.Manager) {
	t.Helper()
	store := auth.NewStore()
	manager := wsclient.NewManager(wsclient.Options{
		ClientID:          "test-client",
		Version:           "test",
		ReconnectMin:      0,
		ReconnectMax:      0,
		HeartbeatInterval: 0,
	})
	srv := httptest.NewServer(New(store, manager, "1.2.3").Handler())
	t.Cleanup(func() {
		srv.Close()
		manager.DisconnectAll()
	})
	return srv, store, manager
}

// postJSON 发送 POST 请求并返回状态码与解析后的 JSON。
func postJSON(t *testing.T, url string, body any) (int, map[string]any) {
	t.Helper()
	var buf bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buf).Encode(body); err != nil {
			t.Fatalf("encode body: %v", err)
		}
	}
	resp, err := http.Post(url, "application/json", &buf)
	if err != nil {
		t.Fatalf("post %s: %v", url, err)
	}
	defer resp.Body.Close()
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode response from %s: %v", url, err)
	}
	return resp.StatusCode, out
}

// getStatus 查询 /api/status 并返回解析后的 JSON。
func getStatus(t *testing.T, base string) (int, map[string]any) {
	t.Helper()
	resp, err := http.Get(base + "/api/status")
	if err != nil {
		t.Fatalf("get status: %v", err)
	}
	defer resp.Body.Close()
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode status: %v", err)
	}
	return resp.StatusCode, out
}

// statusGateways 取出 status 响应中的 gateways 数组。
func statusGateways(t *testing.T, body map[string]any) []map[string]any {
	t.Helper()
	raw, ok := body["gateways"].([]any)
	if !ok {
		t.Fatalf("gateways 字段缺失或类型错误: %#v", body["gateways"])
	}
	out := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		m, ok := item.(map[string]any)
		if !ok {
			t.Fatalf("gateways 元素类型错误: %#v", item)
		}
		out = append(out, m)
	}
	return out
}

// TestAuthMultiGatewayCoexist 核心用例：两个不同网关先后推送凭据，互不顶掉。
func TestAuthMultiGatewayCoexist(t *testing.T) {
	srv, store, manager := newTestServer(t)

	code, body := postJSON(t, srv.URL+"/api/auth", authRequest{Gateway: "http://gw-a.example.com:8080", Token: "token-aaaaaaaa"})
	if code != http.StatusOK {
		t.Fatalf("第一次 auth 状态码 = %d, 期望 200; body=%v", code, body)
	}
	if body["success"] != true || body["status"] != "connecting" || body["daemon_version"] != "1.2.3" {
		t.Fatalf("第一次 auth 响应不符合约定: %v", body)
	}

	code, body = postJSON(t, srv.URL+"/api/auth", authRequest{Gateway: "https://gw-b.example.com", Token: "token-bbbbbbbb"})
	if code != http.StatusOK {
		t.Fatalf("第二次 auth 状态码 = %d, 期望 200; body=%v", code, body)
	}

	if manager.Count() != 2 {
		t.Fatalf("manager.Count() = %d, 期望 2", manager.Count())
	}
	if !store.Has("http://gw-a.example.com:8080") || !store.Has("https://gw-b.example.com") {
		t.Fatalf("两个网关的凭据都应存在: %v", store.List())
	}

	code, body = getStatus(t, srv.URL)
	if code != http.StatusOK {
		t.Fatalf("status 状态码 = %d, 期望 200", code)
	}
	if body["success"] != true || body["daemon_version"] != "1.2.3" {
		t.Fatalf("status 顶层字段不符合约定: %v", body)
	}
	gws := statusGateways(t, body)
	if len(gws) != 2 {
		t.Fatalf("status 返回 %d 个网关, 期望 2: %v", len(gws), gws)
	}
	// 按 gateway 字典序：http://gw-a... < https://gw-b...
	if gws[0]["gateway"] != "http://gw-a.example.com:8080" {
		t.Fatalf("第一个网关 = %v, 期望 http://gw-a.example.com:8080", gws[0]["gateway"])
	}
	if gws[1]["gateway"] != "https://gw-b.example.com" {
		t.Fatalf("第二个网关 = %v, 期望 https://gw-b.example.com", gws[1]["gateway"])
	}
	// 字段完整性与类型。
	for i, gw := range gws {
		for _, key := range []string{"gateway", "session_id", "connected", "state", "token_valid", "auth_failed"} {
			if _, ok := gw[key]; !ok {
				t.Fatalf("第 %d 个网关缺少字段 %q: %v", i, key, gw)
			}
		}
		if gw["token_valid"] != true {
			t.Fatalf("第 %d 个网关 token_valid = %v, 期望 true", i, gw["token_valid"])
		}
		if gw["auth_failed"] != false {
			t.Fatalf("第 %d 个网关 auth_failed = %v, 期望 false", i, gw["auth_failed"])
		}
	}
}

// TestAuthSameGatewayReplaces 同网关重复推送只保留最新连接，其他网关不受影响。
func TestAuthSameGatewayReplaces(t *testing.T) {
	srv, _, manager := newTestServer(t)

	postJSON(t, srv.URL+"/api/auth", authRequest{Gateway: "http://gw-a.example.com:8080", Token: "token-old-old"})
	postJSON(t, srv.URL+"/api/auth", authRequest{Gateway: "http://gw-a.example.com:8080", Token: "token-new-new"})
	postJSON(t, srv.URL+"/api/auth", authRequest{Gateway: "http://gw-b.example.com:9090", Token: "token-bbbbbbbb"})

	if manager.Count() != 2 {
		t.Fatalf("manager.Count() = %d, 期望 2（同网关只保留一条）", manager.Count())
	}
	_, body := getStatus(t, srv.URL)
	gws := statusGateways(t, body)
	if len(gws) != 2 {
		t.Fatalf("status 返回 %d 个网关, 期望 2: %v", len(gws), gws)
	}
}

// TestLogoutSingleGateway 带 gateway 的登出只清该网关，另一网关仍在。
func TestLogoutSingleGateway(t *testing.T) {
	srv, store, manager := newTestServer(t)

	postJSON(t, srv.URL+"/api/auth", authRequest{Gateway: "http://gw-a.example.com:8080", Token: "token-aaaaaaaa"})
	postJSON(t, srv.URL+"/api/auth", authRequest{Gateway: "http://gw-b.example.com:9090", Token: "token-bbbbbbbb"})

	code, body := postJSON(t, srv.URL+"/api/logout", logoutRequest{Gateway: "http://gw-a.example.com:8080"})
	if code != http.StatusOK || body["success"] != true {
		t.Fatalf("logout 响应不符合约定: code=%d body=%v", code, body)
	}

	if store.Has("http://gw-a.example.com:8080") {
		t.Fatalf("gw-a 的凭据应已被清除")
	}
	if !store.Has("http://gw-b.example.com:9090") {
		t.Fatalf("gw-b 的凭据不应被清除")
	}
	if manager.Count() != 1 {
		t.Fatalf("manager.Count() = %d, 期望 1", manager.Count())
	}

	_, body = getStatus(t, srv.URL)
	gws := statusGateways(t, body)
	if len(gws) != 1 {
		t.Fatalf("status 返回 %d 个网关, 期望 1: %v", len(gws), gws)
	}
	if gws[0]["gateway"] != "http://gw-b.example.com:9090" {
		t.Fatalf("剩余网关 = %v, 期望 http://gw-b.example.com:9090", gws[0]["gateway"])
	}
}

// TestLogoutAll 不带 gateway 的登出清空全部（向后兼容旧语义）。
func TestLogoutAll(t *testing.T) {
	srv, store, manager := newTestServer(t)

	postJSON(t, srv.URL+"/api/auth", authRequest{Gateway: "http://gw-a.example.com:8080", Token: "token-aaaaaaaa"})
	postJSON(t, srv.URL+"/api/auth", authRequest{Gateway: "http://gw-b.example.com:9090", Token: "token-bbbbbbbb"})

	// 空请求体也应被接受。
	code, body := postJSON(t, srv.URL+"/api/logout", nil)
	if code != http.StatusOK || body["success"] != true {
		t.Fatalf("logout 响应不符合约定: code=%d body=%v", code, body)
	}

	if len(store.List()) != 0 {
		t.Fatalf("凭据应全部清空: %v", store.List())
	}
	if manager.Count() != 0 {
		t.Fatalf("manager.Count() = %d, 期望 0", manager.Count())
	}

	_, body = getStatus(t, srv.URL)
	gws := statusGateways(t, body)
	if len(gws) != 0 {
		t.Fatalf("status 应返回 0 个网关: %v", gws)
	}
}

// TestAuthValidation gateway 或 token 为空返回 400。
func TestAuthValidation(t *testing.T) {
	srv, _, manager := newTestServer(t)

	cases := []authRequest{
		{Gateway: "", Token: "token-aaaaaaaa"},
		{Gateway: "http://gw-a.example.com:8080", Token: ""},
		{Gateway: "", Token: ""},
	}
	for _, c := range cases {
		code, body := postJSON(t, srv.URL+"/api/auth", c)
		if code != http.StatusBadRequest {
			t.Fatalf("gateway=%q token=%q 状态码 = %d, 期望 400; body=%v", c.Gateway, c.Token, code, body)
		}
		if body["success"] != false {
			t.Fatalf("失败响应 success 应为 false: %v", body)
		}
	}
	if manager.Count() != 0 {
		t.Fatalf("非法请求不应建立连接, Count() = %d", manager.Count())
	}
}

// TestAuthInvalidJSON 非法 JSON 返回 400。
func TestAuthInvalidJSON(t *testing.T) {
	srv, _, _ := newTestServer(t)

	resp, err := http.Post(srv.URL+"/api/auth", "application/json", bytes.NewBufferString("{not json"))
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("状态码 = %d, 期望 400", resp.StatusCode)
	}
}

// TestMethodNotAllowed 错误方法返回 405。
func TestMethodNotAllowed(t *testing.T) {
	srv, _, _ := newTestServer(t)

	// GET /api/auth
	resp, err := http.Get(srv.URL + "/api/auth")
	if err != nil {
		t.Fatalf("get auth: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("GET /api/auth 状态码 = %d, 期望 405", resp.StatusCode)
	}

	// POST /api/status
	code, _ := postJSON(t, srv.URL+"/api/status", nil)
	if code != http.StatusMethodNotAllowed {
		t.Fatalf("POST /api/status 状态码 = %d, 期望 405", code)
	}

	// GET /api/logout
	resp, err = http.Get(srv.URL + "/api/logout")
	if err != nil {
		t.Fatalf("get logout: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("GET /api/logout 状态码 = %d, 期望 405", resp.StatusCode)
	}
}

// TestStatusContentType 响应 Content-Type 与结构约定。
func TestStatusContentType(t *testing.T) {
	srv, _, _ := newTestServer(t)

	resp, err := http.Get(srv.URL + "/api/status")
	if err != nil {
		t.Fatalf("get status: %v", err)
	}
	defer resp.Body.Close()
	if ct := resp.Header.Get("Content-Type"); ct != "application/json; charset=utf-8" {
		t.Fatalf("Content-Type = %q", ct)
	}
	var body map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if _, ok := body["gateways"].([]any); !ok {
		t.Fatalf("gateways 应为数组: %#v", body["gateways"])
	}
	if body["daemon_version"] != "1.2.3" {
		t.Fatalf("daemon_version = %v", body["daemon_version"])
	}
}
