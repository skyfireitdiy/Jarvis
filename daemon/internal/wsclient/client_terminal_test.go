//go:build linux

package wsclient

import (
	"encoding/base64"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// WS 层终端消息测试：验证 Client 收到 node_terminal_request 后回
// node_terminal_response，并把 PTY 输出经 node_terminal_output 回传。
//
// 复用 client_capability_test.go 的 startCapabilityTestServer /
// readJSONWithTimeout / readJSONSkippingSystemInfo / waitForConn 辅助函数。

// startTerminalTestClient 启动一个带 TerminalManager 的客户端，返回服务端连接。
func startTerminalTestClient(t *testing.T, gateway string, connCh <-chan *websocket.Conn) *websocket.Conn {
	t.Helper()
	tm := NewTerminalManager()
	client := New(Options{
		Gateway:         gateway,
		Token:           "test-token",
		ClientID:        "test-daemon",
		Version:         "0.0.0-test",
		TerminalManager: tm,
	})
	client.Start()
	t.Cleanup(client.Stop)
	t.Cleanup(tm.CloseAll)

	serverConn := waitForConn(t, connCh)
	readJSONWithTimeout(t, serverConn) // hello
	if err := serverConn.WriteJSON(map[string]any{
		"type":       "hello_ack",
		"session_id": "test-session",
	}); err != nil {
		t.Fatalf("回 hello_ack 失败: %v", err)
	}
	return serverConn
}

// TestClientTerminalCreate 验证 WS 层 terminal_create 返回 node_terminal_response。
func TestClientTerminalCreate(t *testing.T) {
	gateway, connCh := startCapabilityTestServer(t)
	serverConn := startTerminalTestClient(t, gateway, connCh)

	reqID := "req-create-1"
	if err := serverConn.WriteJSON(map[string]any{
		"type":       "node_terminal_request",
		"request_id": reqID,
		"payload": map[string]any{
			"action": "terminal_create",
			"payload": map[string]any{
				"interpreter": "bash",
				"working_dir": "/tmp",
			},
			"session_id": "session_test",
		},
	}); err != nil {
		t.Fatalf("发送 node_terminal_request 失败: %v", err)
	}

	reply := readJSONSkippingSystemInfo(t, serverConn)
	if reply["type"] != "node_terminal_response" {
		t.Fatalf("期望 type=node_terminal_response，实际 %v", reply["type"])
	}
	if reply["request_id"] != reqID {
		t.Fatalf("期望 request_id=%s，实际 %v", reqID, reply["request_id"])
	}
	payload, _ := reply["payload"].(map[string]any)
	if payload["success"] != true {
		t.Fatalf("期望 success=true，实际 %v（error=%v）", payload["success"], payload["error"])
	}
	data, _ := payload["data"].(map[string]any)
	if data["terminal_id"] == "" {
		t.Fatalf("期望 terminal_id 非空，实际 %v", data["terminal_id"])
	}
	if data["interpreter"] != "bash" {
		t.Errorf("期望 interpreter=bash，实际 %v", data["interpreter"])
	}
	if data["working_dir"] != "/tmp" {
		t.Errorf("期望 working_dir=/tmp，实际 %v", data["working_dir"])
	}
}

// TestClientTerminalUnknownAction 验证未知 action 返回 UNKNOWN_ACTION。
func TestClientTerminalUnknownAction(t *testing.T) {
	gateway, connCh := startCapabilityTestServer(t)
	serverConn := startTerminalTestClient(t, gateway, connCh)

	reqID := "req-unknown-1"
	if err := serverConn.WriteJSON(map[string]any{
		"type":       "node_terminal_request",
		"request_id": reqID,
		"payload": map[string]any{
			"action":     "terminal_frobnicate",
			"payload":    map[string]any{},
			"session_id": "session_test",
		},
	}); err != nil {
		t.Fatalf("发送 node_terminal_request 失败: %v", err)
	}

	reply := readJSONSkippingSystemInfo(t, serverConn)
	if reply["type"] != "node_terminal_response" {
		t.Fatalf("期望 type=node_terminal_response，实际 %v", reply["type"])
	}
	payload, _ := reply["payload"].(map[string]any)
	if payload["success"] != false {
		t.Fatalf("期望 success=false，实际 %v", payload["success"])
	}
	errObj, _ := payload["error"].(map[string]any)
	if errObj["code"] != "UNKNOWN_ACTION" {
		t.Fatalf("期望错误码 UNKNOWN_ACTION，实际 %v", payload["error"])
	}
}

// TestClientTerminalOutput 验证 WS 层 PTY 输出经 node_terminal_output 回传。
func TestClientTerminalOutput(t *testing.T) {
	gateway, connCh := startCapabilityTestServer(t)
	serverConn := startTerminalTestClient(t, gateway, connCh)

	// 创建终端
	if err := serverConn.WriteJSON(map[string]any{
		"type":       "node_terminal_request",
		"request_id": "req-create-2",
		"payload": map[string]any{
			"action": "terminal_create",
			"payload": map[string]any{
				"interpreter": "bash",
				"working_dir": "/tmp",
			},
			"session_id": "session_test",
		},
	}); err != nil {
		t.Fatalf("发送 node_terminal_request 失败: %v", err)
	}
	createReply := readJSONSkippingSystemInfo(t, serverConn)
	createPayload, _ := createReply["payload"].(map[string]any)
	data, _ := createPayload["data"].(map[string]any)
	terminalID, _ := data["terminal_id"].(string)
	if terminalID == "" {
		t.Fatalf("创建终端失败: %v", createReply)
	}

	// 发送输入触发输出
	if err := serverConn.WriteJSON(map[string]any{
		"type":       "node_terminal_request",
		"request_id": "req-input-2",
		"payload": map[string]any{
			"action": "terminal_session_input",
			"payload": map[string]any{
				"terminal_id": terminalID,
				"data":        "echo ws_stream_probe\n",
			},
			"session_id": "session_test",
		},
	}); err != nil {
		t.Fatalf("发送输入失败: %v", err)
	}
	// 读回输入响应
	readJSONSkippingSystemInfo(t, serverConn)

	// 等待 node_terminal_output
	deadline := time.Now().Add(3 * time.Second)
	for {
		msg := readJSONWithTimeout(t, serverConn)
		if msg["type"] != "node_terminal_output" {
			continue
		}
		payload, _ := msg["payload"].(map[string]any)
		if payload["session_id"] != "session_test" {
			t.Errorf("期望 session_id=session_test，实际 %v", payload["session_id"])
		}
		inner, _ := payload["message"].(map[string]any)
		innerPayload, _ := inner["payload"].(map[string]any)
		raw, _ := innerPayload["data"].(string)
		decoded, err := base64.StdEncoding.DecodeString(raw)
		if err != nil {
			t.Fatalf("解码 base64 失败: %v", err)
		}
		if strings.Contains(string(decoded), "ws_stream_probe") {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("未在 3 秒内收到包含 ws_stream_probe 的输出，最近消息: %v", msg)
		}
	}
}
