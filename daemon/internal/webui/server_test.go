package webui

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"jarvis-daemon/internal/auth"
	"jarvis-daemon/internal/wsclient"
)

// newTestServer 构造一个绑定到给定网关地址的 webui.Server。
//
// manager 用零值 Manager：本测试只验证「凭据已写入 store」，不验证真实连接
// （连接由 wsclient 自己的测试覆盖）。ConnectWithName 对未知网关是安全的空操作。
func newTestServer(t *testing.T, gateway string) (*Server, *auth.Store) {
	t.Helper()
	store := auth.NewStore()
	manager := wsclient.NewManager(wsclient.Options{})
	return New(store, manager, "test-version"), store
}

// postJSON 向 handler 发送 JSON POST 请求。
func postJSON(t *testing.T, h http.Handler, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

// TestIndexReturnsLoginPage GET / 应返回含表单关键元素的 HTML。
func TestIndexReturnsLoginPage(t *testing.T) {
	srv, _ := newTestServer(t, "")
	h := srv.Handler()

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("GET / 状态码 = %d, 期望 200", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "text/html") {
		t.Fatalf("Content-Type = %q, 期望含 text/html", ct)
	}
	body := rec.Body.String()
	for _, want := range []string{"<form", "用户名", "密码", "网关地址", "/api/login"} {
		if !strings.Contains(body, want) {
			t.Errorf("登录页缺少关键内容 %q", want)
		}
	}
}

// TestLoginSuccess 登录成功应写入凭据并返回 success=true。
func TestLoginSuccess(t *testing.T) {
	// mock 网关：返回成功响应。
	gateway := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/auth/login" {
			http.NotFound(w, r)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"success": true,
			"data": map[string]any{
				"token": "test-token-abcdefgh",
				"user": map[string]any{
					"user_id":      "u1",
					"username":     "admin",
					"display_name": "管理员",
					"is_admin":     true,
				},
			},
		})
	}))
	defer gateway.Close()

	srv, store := newTestServer(t, gateway.URL)
	h := srv.Handler()

	rec := postJSON(t, h, "/api/login",
		`{"gateway":"`+gateway.URL+`","username":"admin","password":"secret"}`)

	if rec.Code != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200; body=%s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	if resp["success"] != true {
		t.Fatalf("success = %v, 期望 true", resp["success"])
	}
	// 凭据应已写入 store。
	creds, err := store.Get(gateway.URL)
	if err != nil {
		t.Fatalf("store.Get 失败: %v", err)
	}
	if creds.Token != "test-token-abcdefgh" {
		t.Fatalf("store 中的 token = %q, 期望 test-token-abcdefgh", creds.Token)
	}
}

// TestLoginWrongPassword 网关拒绝时应返回 400 且透传错误信息。
func TestLoginWrongPassword(t *testing.T) {
	gateway := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"success": false,
			"error":   map[string]any{"code": "AUTH_FAILED", "message": "Invalid username or password"},
		})
	}))
	defer gateway.Close()

	srv, store := newTestServer(t, gateway.URL)
	rec := postJSON(t, srv.Handler(), "/api/login",
		`{"gateway":"`+gateway.URL+`","username":"admin","password":"wrong"}`)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("状态码 = %d, 期望 400; body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "Invalid username or password") {
		t.Fatalf("响应未透传网关错误信息: %s", rec.Body.String())
	}
	// 登录失败不应写入凭据。
	if store.Has(gateway.URL) {
		t.Fatalf("登录失败却写入了凭据")
	}
}

// TestLoginMissingParams 缺少必填参数应返回 400。
func TestLoginMissingParams(t *testing.T) {
	srv, _ := newTestServer(t, "")
	h := srv.Handler()

	cases := []struct {
		name string
		body string
	}{
		{"缺网关", `{"username":"admin","password":"x"}`},
		{"缺用户名", `{"gateway":"http://x","password":"x"}`},
		{"缺密码", `{"gateway":"http://x","username":"admin"}`},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			rec := postJSON(t, h, "/api/login", c.body)
			if rec.Code != http.StatusBadRequest {
				t.Fatalf("状态码 = %d, 期望 400; body=%s", rec.Code, rec.Body.String())
			}
		})
	}
}

// TestLoginInvalidJSON 非法 JSON 应返回 400。
func TestLoginInvalidJSON(t *testing.T) {
	srv, _ := newTestServer(t, "")
	rec := postJSON(t, srv.Handler(), "/api/login", "{not json")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("状态码 = %d, 期望 400", rec.Code)
	}
}

// TestLoginMethodNotAllowed GET /api/login 应返回 405。
func TestLoginMethodNotAllowed(t *testing.T) {
	srv, _ := newTestServer(t, "")
	req := httptest.NewRequest(http.MethodGet, "/api/login", nil)
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("状态码 = %d, 期望 405", rec.Code)
	}
}

// TestIndexUnknownPathNotFound 非根路径应 404。
func TestIndexUnknownPathNotFound(t *testing.T) {
	srv, _ := newTestServer(t, "")
	req := httptest.NewRequest(http.MethodGet, "/whatever", nil)
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("状态码 = %d, 期望 404", rec.Code)
	}
}
