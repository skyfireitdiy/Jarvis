package localapi

import (
	"net/http"
	"testing"

	"jarvis-daemon/internal/capability"
)

// resetAutoUpdateDaemon 复位包级开关态，避免测试间互相污染。
func resetAutoUpdateDaemon(t *testing.T) {
	t.Helper()
	capability.SetAutoUpdateDaemon(false)
	if capability.AutoUpdateDaemon() {
		t.Fatalf("复位后开关应为 false")
	}
}

// TestSettingsDaemonUpdateDefaultOff 默认（未推送）时 auto_update_daemon 为 false。
func TestSettingsDaemonUpdateDefaultOff(t *testing.T) {
	resetAutoUpdateDaemon(t)
	srv, _, _ := newTestServer(t)
	code, body := getSettings(t, srv.URL)
	if code != http.StatusOK {
		t.Fatalf("GET /api/settings 状态码 = %d, 期望 200; body=%v", code, body)
	}
	if body["auto_update_daemon"] != false {
		t.Fatalf("默认 auto_update_daemon 应为 false, 实际 %v", body["auto_update_daemon"])
	}
}

// TestSettingsDaemonUpdatePostThenGet 打开后 GET 能读到 true；再关闭读回 false。
func TestSettingsDaemonUpdatePostThenGet(t *testing.T) {
	resetAutoUpdateDaemon(t)
	srv, _, _ := newTestServer(t)

	code, body := postJSON(t, srv.URL+"/api/settings", map[string]any{"auto_update_daemon": true})
	if code != http.StatusOK {
		t.Fatalf("POST 状态码 = %d, 期望 200; body=%v", code, body)
	}
	if body["auto_update_daemon"] != true {
		t.Fatalf("POST 响应应回显 true: %v", body)
	}
	if !capability.AutoUpdateDaemon() {
		t.Fatalf("POST 后 capability 开关应为 true")
	}

	code, body = getSettings(t, srv.URL)
	if code != http.StatusOK || body["auto_update_daemon"] != true {
		t.Fatalf("GET 应返回 true: code=%d body=%v", code, body)
	}

	code, body = postJSON(t, srv.URL+"/api/settings", map[string]any{"auto_update_daemon": false})
	if code != http.StatusOK || body["auto_update_daemon"] != false {
		t.Fatalf("关闭响应不符合约定: code=%d body=%v", code, body)
	}
	if capability.AutoUpdateDaemon() {
		t.Fatalf("关闭后 capability 开关应为 false")
	}
}

// TestSettingsDaemonUpdateOnlyField 只提供 auto_update_daemon 时应被接受（与扩展开关独立）。
func TestSettingsDaemonUpdateOnlyField(t *testing.T) {
	resetAutoUpdateDaemon(t)
	resetAutoInstallBrowserExt(t)
	srv, _, _ := newTestServer(t)

	code, body := postJSON(t, srv.URL+"/api/settings", map[string]any{"auto_update_daemon": true})
	if code != http.StatusOK {
		t.Fatalf("仅提供 auto_update_daemon 应被接受: code=%d body=%v", code, body)
	}
	if !capability.AutoUpdateDaemon() {
		t.Fatalf("开关应为 true")
	}
	// 不应影响扩展开关（仍为默认 false）。
	if capability.AutoInstallBrowserExt() {
		t.Fatalf("不应影响 auto_install_browser_ext")
	}
}

// TestAuthCarriesDaemonUpdateSwitch /api/auth 携带该字段时同步更新开关。
func TestAuthCarriesDaemonUpdateSwitch(t *testing.T) {
	resetAutoUpdateDaemon(t)
	srv, _, _ := newTestServer(t)

	enabled := true
	code, body := postJSON(t, srv.URL+"/api/auth", authRequest{
		Gateway:          "http://gw-a.example.com:8080",
		Token:            "token-aaaaaaaa",
		AutoUpdateDaemon: &enabled,
	})
	if code != http.StatusOK {
		t.Fatalf("auth 状态码 = %d, 期望 200; body=%v", code, body)
	}
	if !capability.AutoUpdateDaemon() {
		t.Fatalf("/api/auth 携带 true 后开关应为 true")
	}

	disabled := false
	postJSON(t, srv.URL+"/api/auth", authRequest{
		Gateway:          "http://gw-a.example.com:8080",
		Token:            "token-aaaaaaaa",
		AutoUpdateDaemon: &disabled,
	})
	if capability.AutoUpdateDaemon() {
		t.Fatalf("/api/auth 携带 false 后开关应为 false")
	}
}

// TestAuthWithoutDaemonUpdateKeepsValue 不带该字段（nil）时保持原值，兼容旧前端。
func TestAuthWithoutDaemonUpdateKeepsValue(t *testing.T) {
	resetAutoUpdateDaemon(t)
	srv, _, _ := newTestServer(t)

	enabled := true
	postJSON(t, srv.URL+"/api/auth", authRequest{
		Gateway:          "http://gw-a.example.com:8080",
		Token:            "token-aaaaaaaa",
		AutoUpdateDaemon: &enabled,
	})
	if !capability.AutoUpdateDaemon() {
		t.Fatalf("前置条件失败：开关应为 true")
	}
	// 旧前端不带该字段，开关不应被改回 false。
	postJSON(t, srv.URL+"/api/auth", authRequest{
		Gateway: "http://gw-b.example.com:9090",
		Token:   "token-bbbbbbbb",
	})
	if !capability.AutoUpdateDaemon() {
		t.Fatalf("不带该字段的 /api/auth 不应改变开关（应仍为 true）")
	}
}

// TestAutoUpdateDaemonConcurrent 并发读写开关不应触发数据竞争（配合 -race）。
func TestAutoUpdateDaemonConcurrent(t *testing.T) {
	resetAutoUpdateDaemon(t)
	done := make(chan struct{})
	go func() {
		for i := 0; i < 1000; i++ {
			capability.SetAutoUpdateDaemon(i%2 == 0)
		}
		close(done)
	}()
	for i := 0; i < 1000; i++ {
		_ = capability.AutoUpdateDaemon()
	}
	<-done
}
