package wsclient

import "testing"

// TestHandleMessage_DaemonUpdate 校验：hello_ack 携带 daemon_update 时触发 OnDaemonUpdate，
// 且 session_id 与原始 map 被正确透传。
func TestHandleMessage_DaemonUpdate(t *testing.T) {
	var gotSID string
	var gotInfo map[string]any
	c := &Client{opts: Options{
		OnDaemonUpdate: func(sessionID string, info map[string]any) {
			gotSID = sessionID
			gotInfo = info
		},
	}}

	info := map[string]any{"available": true, "latest_version": "v2.0.0"}
	c.handleMessage(nil, map[string]any{
		"type":          "hello_ack",
		"session_id":    "sid-123",
		"daemon_update": info,
	})

	if gotSID != "sid-123" {
		t.Fatalf("session_id 未透传: %q", gotSID)
	}
	if gotInfo == nil || gotInfo["latest_version"] != "v2.0.0" {
		t.Fatalf("daemon_update 未透传: %v", gotInfo)
	}
}

// TestHandleMessage_DaemonUpdateMissing 校验：hello_ack 未携带 daemon_update 时不回调。
func TestHandleMessage_DaemonUpdateMissing(t *testing.T) {
	called := false
	c := &Client{opts: Options{
		OnDaemonUpdate: func(string, map[string]any) { called = true },
	}}
	c.handleMessage(nil, map[string]any{
		"type":       "hello_ack",
		"session_id": "sid-123",
	})
	if called {
		t.Fatal("未携带 daemon_update 时不应回调")
	}
}

// TestHandleMessage_DaemonUpdateWrongType 校验：daemon_update 类型不对时不回调、不 panic。
func TestHandleMessage_DaemonUpdateWrongType(t *testing.T) {
	called := false
	c := &Client{opts: Options{
		OnDaemonUpdate: func(string, map[string]any) { called = true },
	}}
	c.handleMessage(nil, map[string]any{
		"type":          "hello_ack",
		"session_id":    "sid-123",
		"daemon_update": "not-an-object",
	})
	if called {
		t.Fatal("类型不对时不应回调")
	}
}

// TestHandleMessage_DaemonUpdateNilCallback 校验：未设置回调时收到 daemon_update 不 panic。
func TestHandleMessage_DaemonUpdateNilCallback(t *testing.T) {
	c := &Client{opts: Options{}}
	c.handleMessage(nil, map[string]any{
		"type":          "hello_ack",
		"session_id":    "sid-123",
		"daemon_update": map[string]any{"available": true},
	})
}
