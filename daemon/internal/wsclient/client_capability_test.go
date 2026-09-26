package wsclient

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"

	"jarvis-daemon/internal/capability"
)

// testServer 起一个本地 WS 服务端，返回其 HTTP 地址与已升级的连接通道。
//
// 服务端只做最小握手：接受子协议 jarvis-daemon，然后回 hello_ack 并等待测试驱动。
func startCapabilityTestServer(t *testing.T) (string, <-chan *websocket.Conn) {
	t.Helper()

	upgrader := websocket.Upgrader{
		Subprotocols: []string{"jarvis-daemon"},
		CheckOrigin:  func(*http.Request) bool { return true },
	}
	connCh := make(chan *websocket.Conn, 1)

	mux := http.NewServeMux()
	mux.HandleFunc("/api/daemon/ws", func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Errorf("升级 WS 失败: %v", err)
			return
		}
		connCh <- conn
	})

	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv.URL, connCh
}

// readJSONWithTimeout 带超时地读取一帧 JSON。
func readJSONWithTimeout(t *testing.T, conn *websocket.Conn) map[string]any {
	t.Helper()

	type readResult struct {
		data []byte
		err  error
	}
	ch := make(chan readResult, 1)
	go func() {
		_, data, err := conn.ReadMessage()
		ch <- readResult{data: data, err: err}
	}()

	select {
	case r := <-ch:
		if r.err != nil {
			t.Fatalf("读取消息失败: %v", r.err)
		}
		var msg map[string]any
		if err := json.Unmarshal(r.data, &msg); err != nil {
			t.Fatalf("解析消息失败: %v（原文 %s）", err, string(r.data))
		}
		return msg
	case <-time.After(5 * time.Second):
		t.Fatal("等待消息超时")
		return nil
	}
}

// waitForConn 等待服务端拿到连接。
func waitForConn(t *testing.T, connCh <-chan *websocket.Conn) *websocket.Conn {
	t.Helper()
	select {
	case conn := <-connCh:
		return conn
	case <-time.After(5 * time.Second):
		t.Fatal("等待客户端连接超时")
		return nil
	}
}

// newEchoRegistry 构造一个注册了 test.echo 能力的注册表。
func newEchoRegistry(t *testing.T) *capability.Registry {
	t.Helper()

	reg := capability.NewRegistry()
	err := reg.Register(capability.Capability{
		Name:        "test.echo",
		Description: "回显参数",
		Parameters:  map[string]any{"msg": "string"},
		Handler: func(params map[string]any) (any, error) {
			return map[string]any{"echo": params["msg"]}, nil
		},
	})
	if err != nil {
		t.Fatalf("注册测试能力失败: %v", err)
	}
	return reg
}

// TestCapabilityList 验证客户端能响应 capability.list。
func TestCapabilityList(t *testing.T) {
	gateway, connCh := startCapabilityTestServer(t)
	reg := newEchoRegistry(t)

	client := New(Options{
		Gateway:  gateway,
		Token:    "test-token",
		ClientID: "test-daemon",
		Version:  "0.0.0-test",
		Registry: reg,
	})
	client.Start()
	defer client.Stop()

	serverConn := waitForConn(t, connCh)

	// 先收 hello，回 hello_ack
	hello := readJSONWithTimeout(t, serverConn)
	if hello["type"] != "hello" {
		t.Fatalf("期望首帧为 hello，实际 %v", hello["type"])
	}
	if err := serverConn.WriteJSON(map[string]any{
		"type":       "hello_ack",
		"session_id": "test-session",
	}); err != nil {
		t.Fatalf("回 hello_ack 失败: %v", err)
	}

	// 查询能力列表
	if err := serverConn.WriteJSON(map[string]any{"type": "capability.list"}); err != nil {
		t.Fatalf("发送 capability.list 失败: %v", err)
	}
	reply := readJSONWithTimeout(t, serverConn)

	if reply["type"] != "capability.list.result" {
		t.Fatalf("期望 type=capability.list.result，实际 %v", reply["type"])
	}
	caps, ok := reply["capabilities"].([]any)
	if !ok {
		t.Fatalf("期望 capabilities 为数组，实际 %T", reply["capabilities"])
	}
	if len(caps) != 1 {
		t.Fatalf("期望 1 个能力，实际 %d", len(caps))
	}
	first, _ := caps[0].(map[string]any)
	if first["name"] != "test.echo" {
		t.Fatalf("期望能力名 test.echo，实际 %v", first["name"])
	}
}

// TestCapabilityCallSuccess 验证客户端能执行已注册能力。
func TestCapabilityCallSuccess(t *testing.T) {
	gateway, connCh := startCapabilityTestServer(t)
	reg := newEchoRegistry(t)

	client := New(Options{
		Gateway:  gateway,
		Token:    "test-token",
		ClientID: "test-daemon",
		Version:  "0.0.0-test",
		Registry: reg,
	})
	client.Start()
	defer client.Stop()

	serverConn := waitForConn(t, connCh)
	readJSONWithTimeout(t, serverConn) // hello
	if err := serverConn.WriteJSON(map[string]any{
		"type":       "hello_ack",
		"session_id": "test-session",
	}); err != nil {
		t.Fatalf("回 hello_ack 失败: %v", err)
	}

	// 调用能力
	if err := serverConn.WriteJSON(map[string]any{
		"type":   "capability.call",
		"id":     "c1",
		"name":   "test.echo",
		"params": map[string]any{"msg": "hi"},
	}); err != nil {
		t.Fatalf("发送 capability.call 失败: %v", err)
	}
	reply := readJSONWithTimeout(t, serverConn)

	if reply["type"] != "capability.call.result" {
		t.Fatalf("期望 type=capability.call.result，实际 %v", reply["type"])
	}
	if reply["id"] != "c1" {
		t.Fatalf("期望 id=c1，实际 %v", reply["id"])
	}
	if reply["success"] != true {
		t.Fatalf("期望 success=true，实际 %v（error=%v）", reply["success"], reply["error"])
	}
	data, ok := reply["data"].(map[string]any)
	if !ok {
		t.Fatalf("期望 data 为对象，实际 %T", reply["data"])
	}
	if data["echo"] != "hi" {
		t.Fatalf("期望 data.echo=hi，实际 %v", data["echo"])
	}
}

// TestCapabilityCallUnknown 验证调用未注册能力返回明确错误。
func TestCapabilityCallUnknown(t *testing.T) {
	gateway, connCh := startCapabilityTestServer(t)
	reg := newEchoRegistry(t)

	client := New(Options{
		Gateway:  gateway,
		Token:    "test-token",
		ClientID: "test-daemon",
		Version:  "0.0.0-test",
		Registry: reg,
	})
	client.Start()
	defer client.Stop()

	serverConn := waitForConn(t, connCh)
	readJSONWithTimeout(t, serverConn) // hello
	if err := serverConn.WriteJSON(map[string]any{
		"type":       "hello_ack",
		"session_id": "test-session",
	}); err != nil {
		t.Fatalf("回 hello_ack 失败: %v", err)
	}

	if err := serverConn.WriteJSON(map[string]any{
		"type": "capability.call",
		"id":   "c2",
		"name": "no.such",
	}); err != nil {
		t.Fatalf("发送 capability.call 失败: %v", err)
	}
	reply := readJSONWithTimeout(t, serverConn)

	if reply["type"] != "capability.call.result" {
		t.Fatalf("期望 type=capability.call.result，实际 %v", reply["type"])
	}
	if reply["id"] != "c2" {
		t.Fatalf("期望 id=c2，实际 %v", reply["id"])
	}
	if reply["success"] != false {
		t.Fatalf("期望 success=false，实际 %v", reply["success"])
	}
	errMsg, _ := reply["error"].(string)
	if !strings.Contains(errMsg, "unknown capability") {
		t.Fatalf("期望 error 含 unknown capability，实际 %q", errMsg)
	}
}
