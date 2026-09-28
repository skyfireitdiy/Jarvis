package wsclient

import (
	"testing"
	"time"
)

// waitUntilConnected 轮询等待客户端进入已连接状态（ws 字段就绪）。
// 用于避免「hello_ack 已发但客户端尚未把连接写入字段」的竞态。
func waitUntilConnected(t *testing.T, c *Client) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if c.State() == StateConnected {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("等待客户端进入已连接状态超时")
}

// TestSendNotConnected 校验：未建立连接时 Send 返回错误且不 panic。
// 自动更新流程可能在连接已断开（尤其 restarting 阶段）时回执进度，
// 此时必须安全失败而不是崩溃。
func TestSendNotConnected(t *testing.T) {
	c := New(Options{Gateway: "http://127.0.0.1:1", Token: "t"})
	if err := c.Send(map[string]any{"type": "daemon.update.status"}); err == nil {
		t.Fatal("未连接时 Send 应返回错误")
	}
}

// TestSendFrame 校验：已连接时 Send 把整帧 JSON 发给对端。
func TestSendFrame(t *testing.T) {
	gateway, connCh := startCapabilityTestServer(t)

	client := New(Options{
		Gateway:  gateway,
		Token:    "test-token",
		ClientID: "test-daemon",
		Version:  "0.0.0-test",
	})
	client.Start()
	defer client.Stop()

	serverConn := waitForConn(t, connCh)
	// 首帧 hello，回 hello_ack 使客户端进入已连接状态。
	if hello := readJSONWithTimeout(t, serverConn); hello["type"] != "hello" {
		t.Fatalf("期望首帧为 hello，实际 %v", hello["type"])
	}
	if err := serverConn.WriteJSON(map[string]any{
		"type":       "hello_ack",
		"session_id": "test-session",
	}); err != nil {
		t.Fatalf("回 hello_ack 失败: %v", err)
	}

	// 等待客户端真正建立连接（ws 字段就绪）后再发送，避免竞态。
	waitUntilConnected(t, client)

	if err := client.Send(map[string]any{
		"type":    "daemon.update.status",
		"state":   "downloading",
		"version": "v2.0.0",
	}); err != nil {
		t.Fatalf("Send 失败: %v", err)
	}

	msg := readJSONSkippingSystemInfo(t, serverConn)
	if msg["type"] != "daemon.update.status" {
		t.Fatalf("期望 type=daemon.update.status，实际 %v", msg["type"])
	}
	if msg["state"] != "downloading" || msg["version"] != "v2.0.0" {
		t.Fatalf("帧内容不符: %v", msg)
	}
}
