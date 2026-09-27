package login

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestLoginSuccess 登录成功：校验请求方法/路径/请求体，并解析出 token 与用户信息。
func TestLoginSuccess(t *testing.T) {
	var gotMethod, gotPath, gotCT string
	var gotBody map[string]string

	gateway := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		gotCT = r.Header.Get("Content-Type")
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
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

	result, err := Login(gateway.URL, "admin", "secret")
	if err != nil {
		t.Fatalf("Login 失败: %v", err)
	}

	if gotMethod != http.MethodPost {
		t.Errorf("请求方法 = %q, 期望 POST", gotMethod)
	}
	if gotPath != "/api/auth/login" {
		t.Errorf("请求路径 = %q, 期望 /api/auth/login", gotPath)
	}
	if !strings.Contains(gotCT, "application/json") {
		t.Errorf("Content-Type = %q, 期望含 application/json", gotCT)
	}
	if gotBody["username"] != "admin" || gotBody["password"] != "secret" {
		t.Errorf("请求体 = %v, 期望 username=admin password=secret", gotBody)
	}

	if result.Token != "test-token-abcdefgh" {
		t.Errorf("Token = %q, 期望 test-token-abcdefgh", result.Token)
	}
	if result.Username != "admin" || result.DisplayName != "管理员" || !result.IsAdmin {
		t.Errorf("用户信息解析错误: %+v", result)
	}
}

// TestLoginRejected 网关返回 success=false 时应返回含 error.message 的错误。
func TestLoginRejected(t *testing.T) {
	gateway := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"success": false,
			"error":   map[string]any{"code": "AUTH_FAILED", "message": "Invalid username or password"},
		})
	}))
	defer gateway.Close()

	_, err := Login(gateway.URL, "admin", "wrong")
	if err == nil {
		t.Fatal("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "Invalid username or password") {
		t.Fatalf("错误信息未透传网关 message: %v", err)
	}
}

// TestLoginNonOKStatus 网关返回非 200 时，错误信息应含状态码。
func TestLoginNonOKStatus(t *testing.T) {
	gateway := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("boom"))
	}))
	defer gateway.Close()

	_, err := Login(gateway.URL, "admin", "secret")
	if err == nil {
		t.Fatal("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Fatalf("错误信息未含状态码 500: %v", err)
	}
}

// TestLoginEmptyToken 网关返回 success=true 但 token 为空时应视为异常响应。
func TestLoginEmptyToken(t *testing.T) {
	gateway := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"success": true,
			"data":    map[string]any{"token": ""},
		})
	}))
	defer gateway.Close()

	_, err := Login(gateway.URL, "admin", "secret")
	if err == nil {
		t.Fatal("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "token") {
		t.Fatalf("错误信息未提及 token: %v", err)
	}
}

// TestLoginParamErrors 空网关/空用户名/空密码应直接返回参数错误（不发请求）。
func TestLoginParamErrors(t *testing.T) {
	cases := []struct {
		name     string
		gateway  string
		username string
		password string
		wantMsg  string
	}{
		{"空网关", "", "admin", "secret", "网关地址为空"},
		{"空用户名", "http://127.0.0.1:1", "", "secret", "用户名不能为空"},
		{"空密码", "http://127.0.0.1:1", "admin", "", "密码不能为空"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := Login(c.gateway, c.username, c.password)
			if err == nil {
				t.Fatal("期望返回错误，实际为 nil")
			}
			if !strings.Contains(err.Error(), c.wantMsg) {
				t.Fatalf("错误信息 = %v, 期望含 %q", err, c.wantMsg)
			}
		})
	}
}

// TestLoginUnreachable 网关不可达时应返回含地址的请求错误。
func TestLoginUnreachable(t *testing.T) {
	// 端口 1 上不会有服务监听，连接必然失败。
	_, err := Login("http://127.0.0.1:1", "admin", "secret")
	if err == nil {
		t.Fatal("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "登录请求失败") {
		t.Fatalf("错误信息 = %v, 期望含「登录请求失败」", err)
	}
}

// TestPushAuthSuccess 推送成功：校验打到 /api/auth，请求体含 gateway/token/name。
func TestPushAuthSuccess(t *testing.T) {
	var gotMethod, gotPath string
	var gotBody map[string]string

	daemon := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		_ = json.NewEncoder(w).Encode(map[string]any{"success": true})
	}))
	defer daemon.Close()

	// httptest.Server.URL 形如 http://127.0.0.1:PORT，PushAuth 需要 host:port。
	listen := strings.TrimPrefix(daemon.URL, "http://")
	if err := PushAuth(listen, "http://gateway.example", "tok-123456", "my-pc"); err != nil {
		t.Fatalf("PushAuth 失败: %v", err)
	}

	if gotMethod != http.MethodPost {
		t.Errorf("请求方法 = %q, 期望 POST", gotMethod)
	}
	if gotPath != "/api/auth" {
		t.Errorf("请求路径 = %q, 期望 /api/auth", gotPath)
	}
	if gotBody["gateway"] != "http://gateway.example" ||
		gotBody["token"] != "tok-123456" ||
		gotBody["name"] != "my-pc" {
		t.Errorf("请求体 = %v, 期望 gateway/token/name 正确", gotBody)
	}
}

// TestPushAuthDaemonDown 本地守护进程未运行时应给出可读提示。
func TestPushAuthDaemonDown(t *testing.T) {
	err := PushAuth("127.0.0.1:1", "http://gateway.example", "tok-123456", "")
	if err == nil {
		t.Fatal("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "本地后台服务未运行") {
		t.Fatalf("错误信息 = %v, 期望含「本地后台服务未运行」", err)
	}
}

// TestPushAuthParamErrors 空 listen / 空网关 / 空 token 应直接返回参数错误。
func TestPushAuthParamErrors(t *testing.T) {
	cases := []struct {
		name    string
		listen  string
		gateway string
		token   string
		wantMsg string
	}{
		{"空 listen", "", "http://g", "t", "本地服务监听地址为空"},
		{"空网关", "127.0.0.1:1", "", "t", "网关地址为空"},
		{"空 token", "127.0.0.1:1", "http://g", "", "token 为空"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := PushAuth(c.listen, c.gateway, c.token, "")
			if err == nil {
				t.Fatal("期望返回错误，实际为 nil")
			}
			if !strings.Contains(err.Error(), c.wantMsg) {
				t.Fatalf("错误信息 = %v, 期望含 %q", err, c.wantMsg)
			}
		})
	}
}

// TestNormalizeGateway 规范化：去首尾空白与末尾斜杠，不补协议前缀。
func TestNormalizeGateway(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"  http://a:1/  ", "http://a:1"},
		{"http://a:1", "http://a:1"},
		{"http://a:1///", "http://a:1"},
		{"", ""},
		{"   ", ""},
	}
	for _, c := range cases {
		if got := NormalizeGateway(c.in); got != c.want {
			t.Errorf("NormalizeGateway(%q) = %q, 期望 %q", c.in, got, c.want)
		}
	}
}

// TestMaskToken 脱敏：短 token 全掩码，长 token 保留首尾 4 字符。
func TestMaskToken(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"", "***"},
		{"short", "***"},
		{"12345678", "***"},
		{"123456789", "1234...6789"},
	}
	for _, c := range cases {
		if got := MaskToken(c.in); got != c.want {
			t.Errorf("MaskToken(%q) = %q, 期望 %q", c.in, got, c.want)
		}
	}
}
