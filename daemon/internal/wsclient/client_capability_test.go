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
	// NewRegistry 会装配平台能力，因此这里断言 test.echo 在列表中，而不是断言列表长度为 1。
	var found bool
	for _, raw := range caps {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if item["name"] == "test.echo" {
			found = true
		}
	}
	if !found {
		t.Fatalf("能力列表中应当包含 test.echo，实际 %v", caps)
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

// TestHelloCarriesCapabilities 验证握手帧 hello 中直接携带能力列表。
//
// 背景：网关的 /api/daemon/sessions 只读取会话缓存中的 capabilities，该缓存
// 依赖 hello 或运行时查询填充。若 hello 不带能力，会话刚建立时能力列表为空。
func TestHelloCarriesCapabilities(t *testing.T) {
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
	hello := readJSONWithTimeout(t, serverConn)
	if hello["type"] != "hello" {
		t.Fatalf("期望首帧为 hello，实际 %v", hello["type"])
	}
	caps, ok := hello["capabilities"].([]any)
	if !ok {
		t.Fatalf("期望 hello 携带 capabilities 数组，实际 %T", hello["capabilities"])
	}
	var found bool
	for _, raw := range caps {
		if item, ok := raw.(map[string]any); ok && item["name"] == "test.echo" {
			found = true
		}
	}
	if !found {
		t.Fatalf("hello.capabilities 应包含 test.echo，实际 %v", caps)
	}
}

// TestHelloCarriesBuildInfo 验证握手帧 hello 中携带构建信息（编译时间等）。
//
// 需求：daemon 上报信息需带编译时间，便于网关判断「当前运行的是哪一版、何时编译的」。
// 编译时间取自 exe 的 mtime（见 internal/buildinfo），此处只校验字段存在且格式自洽。
func TestHelloCarriesBuildInfo(t *testing.T) {
	gateway, connCh := startCapabilityTestServer(t)
	reg := newEchoRegistry(t)

	client := New(Options{
		Gateway:  gateway,
		Token:    "test-token",
		ClientID: "test-daemon",
		Version:  "v9.9.9-test",
		Registry: reg,
	})
	client.Start()
	defer client.Stop()

	serverConn := waitForConn(t, connCh)
	hello := readJSONWithTimeout(t, serverConn)
	if hello["type"] != "hello" {
		t.Fatalf("期望首帧为 hello，实际 %v", hello["type"])
	}

	bi, ok := hello["build_info"].(map[string]any)
	if !ok {
		t.Fatalf("期望 hello 携带 build_info 对象，实际 %T", hello["build_info"])
	}

	// 版本应与 Options.Version 一致。
	if bi["version"] != "v9.9.9-test" {
		t.Errorf("build_info.version = %v, 期望 v9.9.9-test", bi["version"])
	}
	// 平台字段应非空（本机运行，必定可采集）。
	if bi["os"] == "" || bi["os"] == nil {
		t.Errorf("build_info.os 不应为空，实际 %v", bi["os"])
	}
	if bi["arch"] == "" || bi["arch"] == nil {
		t.Errorf("build_info.arch 不应为空，实际 %v", bi["arch"])
	}
	if bi["go_version"] == "" || bi["go_version"] == nil {
		t.Errorf("build_info.go_version 不应为空，实际 %v", bi["go_version"])
	}
	// 来源标注必须为已知取值之一。
	src, _ := bi["build_time_source"].(string)
	switch src {
	case "exe_mtime", "process_start", "unknown":
	default:
		t.Errorf("build_info.build_time_source = %q, 非预期取值", src)
	}
}

// TestSlowCapabilityCallDoesNotBlockList 验证耗时能力不会阻塞后续 capability.list。
//
// 这是本次修复的核心回归测试：修复前 handleCapabilityCall 在读循环内同步执行，
// 一个 sleep 能力会把读循环占住，导致随后到达的 capability.list 迟迟得不到响应
// （网关侧表现为查询超时、能力列表返回空）。修复后执行在独立 goroutine 中，
// 列表查询应立即得到响应。
func TestSlowCapabilityCallDoesNotBlockList(t *testing.T) {
	gateway, connCh := startCapabilityTestServer(t)
	reg := capability.NewRegistry()
	if err := reg.Register(capability.Capability{
		Name:        "test.slow",
		Description: "故意耗时的测试能力",
		Handler: func(params map[string]any) (any, error) {
			time.Sleep(2 * time.Second)
			return map[string]any{"done": true}, nil
		},
	}); err != nil {
		t.Fatalf("注册 test.slow 失败: %v", err)
	}

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

	// 触发一个耗时 2 秒的能力调用，但**不等待**其结果。
	if err := serverConn.WriteJSON(map[string]any{
		"type": "capability.call",
		"id":   "slow1",
		"name": "test.slow",
	}); err != nil {
		t.Fatalf("发送 capability.call 失败: %v", err)
	}

	// 紧接着查询能力列表：必须在 1 秒内拿到结果（远小于 slow 的 2 秒）。
	// 若修复失效，读循环被 slow 占住，这里会超时失败。
	if err := serverConn.WriteJSON(map[string]any{"type": "capability.list"}); err != nil {
		t.Fatalf("发送 capability.list 失败: %v", err)
	}

	type readResult struct {
		msg map[string]any
		err error
	}
	ch := make(chan readResult, 1)
	go func() {
		_, data, err := serverConn.ReadMessage()
		if err != nil {
			ch <- readResult{err: err}
			return
		}
		var m map[string]any
		if err := json.Unmarshal(data, &m); err != nil {
			ch <- readResult{err: err}
			return
		}
		ch <- readResult{msg: m}
	}()

	select {
	case r := <-ch:
		if r.err != nil {
			t.Fatalf("读取消息失败: %v", r.err)
		}
		if r.msg["type"] != "capability.list.result" {
			t.Fatalf("期望先收到 capability.list.result，实际 %v", r.msg["type"])
		}
	case <-time.After(1 * time.Second):
		t.Fatal("capability.list 在 1 秒内未得到响应：耗时能力阻塞了读循环")
	}
}
