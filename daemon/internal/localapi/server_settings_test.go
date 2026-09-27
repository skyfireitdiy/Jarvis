package localapi

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"jarvis-daemon/internal/auth"
	"jarvis-daemon/internal/capability"
	"jarvis-daemon/internal/wsclient"
)

// resetAutoInstallBrowserExt 复位包级开关态。
//
// 开关是 capability 包级变量，测试之间会互相污染，故每个用例开始前显式复位到
// 默认值 false（关闭）。
func resetAutoInstallBrowserExt(t *testing.T) {
	t.Helper()
	capability.SetAutoInstallBrowserExt(false)
	if capability.AutoInstallBrowserExt() {
		t.Fatalf("复位后开关应为 false")
	}
}

// getSettings 查询 /api/settings 并返回状态码与解析后的 JSON。
func getSettings(t *testing.T, base string) (int, map[string]any) {
	t.Helper()
	resp, err := http.Get(base + "/api/settings")
	if err != nil {
		t.Fatalf("get settings: %v", err)
	}
	defer resp.Body.Close()
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode settings: %v", err)
	}
	return resp.StatusCode, out
}

// TestSettingsDefaultOff 默认（未推送）时开关为 false。
func TestSettingsDefaultOff(t *testing.T) {
	resetAutoInstallBrowserExt(t)
	srv, _, _ := newTestServer(t)

	code, body := getSettings(t, srv.URL)
	if code != http.StatusOK {
		t.Fatalf("GET /api/settings 状态码 = %d, 期望 200; body=%v", code, body)
	}
	if body["success"] != true {
		t.Fatalf("success 应为 true: %v", body)
	}
	if body["auto_install_browser_ext"] != false {
		t.Fatalf("默认 auto_install_browser_ext 应为 false, 实际 %v", body["auto_install_browser_ext"])
	}
}

// TestSettingsPostThenGet 打开开关后 GET 能读到 true；再关闭后读回 false。
func TestSettingsPostThenGet(t *testing.T) {
	resetAutoInstallBrowserExt(t)
	srv, _, _ := newTestServer(t)

	// 打开
	code, body := postJSON(t, srv.URL+"/api/settings", map[string]any{"auto_install_browser_ext": true})
	if code != http.StatusOK {
		t.Fatalf("POST /api/settings 状态码 = %d, 期望 200; body=%v", code, body)
	}
	if body["success"] != true || body["auto_install_browser_ext"] != true {
		t.Fatalf("POST 响应不符合约定: %v", body)
	}
	if !capability.AutoInstallBrowserExt() {
		t.Fatalf("POST 后 capability 开关应为 true")
	}

	code, body = getSettings(t, srv.URL)
	if code != http.StatusOK || body["auto_install_browser_ext"] != true {
		t.Fatalf("GET 应返回 true: code=%d body=%v", code, body)
	}

	// 关闭
	code, body = postJSON(t, srv.URL+"/api/settings", map[string]any{"auto_install_browser_ext": false})
	if code != http.StatusOK || body["auto_install_browser_ext"] != false {
		t.Fatalf("关闭响应不符合约定: code=%d body=%v", code, body)
	}
	if capability.AutoInstallBrowserExt() {
		t.Fatalf("关闭后 capability 开关应为 false")
	}
}

// TestSettingsPostMissingField 缺字段返回 400，且不改变开关值。
func TestSettingsPostMissingField(t *testing.T) {
	resetAutoInstallBrowserExt(t)
	srv, _, _ := newTestServer(t)

	// 先打开，验证缺字段的请求不会把它改掉。
	postJSON(t, srv.URL+"/api/settings", map[string]any{"auto_install_browser_ext": true})

	code, body := postJSON(t, srv.URL+"/api/settings", map[string]any{})
	if code != http.StatusBadRequest {
		t.Fatalf("缺字段状态码 = %d, 期望 400; body=%v", code, body)
	}
	if body["success"] != false {
		t.Fatalf("失败响应 success 应为 false: %v", body)
	}
	if !capability.AutoInstallBrowserExt() {
		t.Fatalf("缺字段请求不应改变开关（应仍为 true）")
	}
}

// TestSettingsInvalidJSON 非法 JSON 返回 400。
func TestSettingsInvalidJSON(t *testing.T) {
	resetAutoInstallBrowserExt(t)
	srv, _, _ := newTestServer(t)

	resp, err := http.Post(srv.URL+"/api/settings", "application/json", bytes.NewBufferString("{not json"))
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("状态码 = %d, 期望 400", resp.StatusCode)
	}
}

// TestSettingsMethodNotAllowed 非 GET/POST 返回 405。
func TestSettingsMethodNotAllowed(t *testing.T) {
	resetAutoInstallBrowserExt(t)
	srv, _, _ := newTestServer(t)

	req, err := http.NewRequest(http.MethodDelete, srv.URL+"/api/settings", nil)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("delete settings: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("DELETE /api/settings 状态码 = %d, 期望 405", resp.StatusCode)
	}
}

// TestAuthCarriesAutoInstallSwitch /api/auth 携带该字段时同步更新开关。
func TestAuthCarriesAutoInstallSwitch(t *testing.T) {
	resetAutoInstallBrowserExt(t)
	srv, _, _ := newTestServer(t)

	enabled := true
	code, body := postJSON(t, srv.URL+"/api/auth", authRequest{
		Gateway:               "http://gw-a.example.com:8080",
		Token:                 "token-aaaaaaaa",
		AutoInstallBrowserExt: &enabled,
	})
	if code != http.StatusOK {
		t.Fatalf("auth 状态码 = %d, 期望 200; body=%v", code, body)
	}
	if !capability.AutoInstallBrowserExt() {
		t.Fatalf("/api/auth 携带 true 后开关应为 true")
	}

	// 关闭方向同样生效（区分 nil 与显式 false）。
	disabled := false
	postJSON(t, srv.URL+"/api/auth", authRequest{
		Gateway:               "http://gw-a.example.com:8080",
		Token:                 "token-aaaaaaaa",
		AutoInstallBrowserExt: &disabled,
	})
	if capability.AutoInstallBrowserExt() {
		t.Fatalf("/api/auth 携带 false 后开关应为 false")
	}
}

// TestAuthWithoutSwitchKeepsValue 不带该字段（nil）时保持原值，兼容旧前端。
func TestAuthWithoutSwitchKeepsValue(t *testing.T) {
	resetAutoInstallBrowserExt(t)
	srv, _, _ := newTestServer(t)

	// 先置为 true。
	enabled := true
	postJSON(t, srv.URL+"/api/auth", authRequest{
		Gateway:               "http://gw-a.example.com:8080",
		Token:                 "token-aaaaaaaa",
		AutoInstallBrowserExt: &enabled,
	})
	if !capability.AutoInstallBrowserExt() {
		t.Fatalf("前置条件失败：开关应为 true")
	}

	// 旧前端不带该字段，开关不应被改回 false。
	postJSON(t, srv.URL+"/api/auth", authRequest{
		Gateway: "http://gw-b.example.com:9090",
		Token:   "token-bbbbbbbb",
	})
	if !capability.AutoInstallBrowserExt() {
		t.Fatalf("不带该字段的 /api/auth 不应改变开关（应仍为 true）")
	}
}

// TestAutoInstallBrowserExtConcurrent 并发读写开关不应触发数据竞争（配合 -race）。
func TestAutoInstallBrowserExtConcurrent(t *testing.T) {
	resetAutoInstallBrowserExt(t)

	done := make(chan struct{})
	// 写协程
	go func() {
		for i := 0; i < 1000; i++ {
			capability.SetAutoInstallBrowserExt(i%2 == 0)
		}
		close(done)
	}()
	// 读协程
	for i := 0; i < 1000; i++ {
		_ = capability.AutoInstallBrowserExt()
	}
	<-done
}

// TestBrowserExtEnabledCallbackOnTransition 开关由关闭变为打开时触发回调；
// 重复置 true（无跃迁）或置 false 均不触发。
//
// 回归背景：daemon 只在 hello_ack 时检查一次开关，而前端推送开关通常晚于
// hello_ack，导致用户已打开开关却仍被判定为「已关闭」并跳过同步。修复方式是在
// 开关发生 false→true 跃迁时回调上层补做一次同步检查；本用例锁定该触发语义。
func TestBrowserExtEnabledCallbackOnTransition(t *testing.T) {
	resetAutoInstallBrowserExt(t)

	store := auth.NewStore()
	manager := wsclient.NewManager(wsclient.Options{
		ClientID:          "test-client",
		Version:           "test",
		ReconnectMin:      0,
		ReconnectMax:      0,
		HeartbeatInterval: 0,
	})
	api := New(store, manager, "1.2.3")
	var calls int
	api.SetOnBrowserExtEnabled(func() { calls++ })
	srv := httptest.NewServer(api.Handler())
	t.Cleanup(func() {
		srv.Close()
		manager.DisconnectAll()
	})

	enabled := true
	// 第一次打开：发生 false→true 跃迁，回调 1 次。
	postJSON(t, srv.URL+"/api/auth", authRequest{
		Gateway:               "http://gw-a.example.com:8080",
		Token:                 "token-aaaaaaaa",
		AutoInstallBrowserExt: &enabled,
	})
	if calls != 1 {
		t.Fatalf("首次打开开关应触发 1 次回调，实际 %d", calls)
	}

	// 再次置 true：无跃迁，不触发。
	postJSON(t, srv.URL+"/api/settings", settingsRequest{AutoInstallBrowserExt: &enabled})
	if calls != 1 {
		t.Fatalf("重复置 true 不应触发回调，实际 %d", calls)
	}

	// 置 false：不触发。
	disabled := false
	postJSON(t, srv.URL+"/api/settings", settingsRequest{AutoInstallBrowserExt: &disabled})
	if calls != 1 {
		t.Fatalf("置 false 不应触发回调，实际 %d", calls)
	}

	// 再次打开：又一次跃迁，回调递增到 2。
	postJSON(t, srv.URL+"/api/settings", settingsRequest{AutoInstallBrowserExt: &enabled})
	if calls != 2 {
		t.Fatalf("再次打开开关应触发第 2 次回调，实际 %d", calls)
	}
}

// TestBrowserExtEnabledCallbackNilSafe 未注入回调时开关跃迁不应 panic。
func TestBrowserExtEnabledCallbackNilSafe(t *testing.T) {
	resetAutoInstallBrowserExt(t)
	srv, _, _ := newTestServer(t)

	enabled := true
	code, body := postJSON(t, srv.URL+"/api/settings", settingsRequest{AutoInstallBrowserExt: &enabled})
	if code != http.StatusOK {
		t.Fatalf("settings 状态码 = %d, 期望 200; body=%v", code, body)
	}
	if !capability.AutoInstallBrowserExt() {
		t.Fatalf("开关应为 true")
	}
}
