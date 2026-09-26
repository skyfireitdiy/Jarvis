package wsclient

import (
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// startMultiGatewayTestServer 起一个本地 WS 服务端，支持多网关场景。
//
// 每次升级连接后：收 hello → 回 hello_ack（session_id 由查询参数决定）→ 保持连接。
// 返回 HTTP 地址与「已建立连接」的通知通道。
func startMultiGatewayTestServer(t *testing.T) (string, <-chan struct{}) {
	t.Helper()

	upgrader := websocket.Upgrader{
		Subprotocols: []string{"jarvis-daemon"},
		CheckOrigin:  func(*http.Request) bool { return true },
	}
	connCh := make(chan struct{}, 64)

	mux := http.NewServeMux()
	mux.HandleFunc("/api/daemon/ws", func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()

		// 收 hello
		if _, _, err := conn.ReadMessage(); err != nil {
			return
		}
		sid := r.URL.Query().Get("sid")
		if sid == "" {
			sid = "sess"
		}
		if err := conn.WriteJSON(map[string]any{
			"type":       "hello_ack",
			"session_id": sid,
		}); err != nil {
			return
		}
		select {
		case connCh <- struct{}{}:
		default:
		}

		// 保持连接直到对端关闭
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	})

	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv.URL, connCh
}

// waitForGatewayConnected 等待 Manager 中指定网关进入 connected 状态。
func waitForGatewayConnected(t *testing.T, m *Manager, gateway string) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		c, ok := m.Get(gateway)
		if ok && c.State() == StateConnected {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("等待网关 %s 连接超时（当前状态 %v）", gateway, m.Status())
}

// TestManagerMultiGatewayIsolation 验证两个网关各自独立连接、状态互不影响。
func TestManagerMultiGatewayIsolation(t *testing.T) {
	gateway, _ := startMultiGatewayTestServer(t)

	m := NewManager(Options{ClientID: "test-daemon", Version: "0.0.0-test"})
	defer m.DisconnectAll()

	m.Connect(gateway, "token-a")
	// 同一网关再次 Connect（同 host:port → 同 GatewayKey），应顶掉旧连接。
	m.Connect(gateway, "token-b")

	// 上面两次是同一网关，只应剩一条。
	if got := m.Count(); got != 1 {
		t.Fatalf("同网关重复 Connect 后应只有 1 条连接，实际 %d", got)
	}

	waitForGatewayConnected(t, m, gateway)

	status := m.Status()
	if len(status) != 1 {
		t.Fatalf("期望 1 条状态，实际 %d: %+v", len(status), status)
	}
	if !status[0].Connected {
		t.Fatalf("期望已连接，实际 %+v", status[0])
	}
	if status[0].Gateway != gateway {
		t.Fatalf("期望 gateway=%s，实际 %s", gateway, status[0].Gateway)
	}
	if !status[0].TokenValid {
		t.Fatalf("期望 token_valid=true，实际 %+v", status[0])
	}
}

// TestManagerConnectReplacesSameGateway 验证同网关重连只保留一个 Client（旧 Client 被 Stop）。
func TestManagerConnectReplacesSameGateway(t *testing.T) {
	gateway, connCh := startMultiGatewayTestServer(t)

	m := NewManager(Options{ClientID: "test-daemon", Version: "0.0.0-test"})
	defer m.DisconnectAll()

	m.Connect(gateway, "token-1")
	first, ok := m.Get(gateway)
	if !ok {
		t.Fatal("首次 Connect 后应能取到 Client")
	}
	select {
	case <-connCh:
	case <-time.After(5 * time.Second):
		t.Fatal("首次连接未建立")
	}

	m.Connect(gateway, "token-2")
	second, ok := m.Get(gateway)
	if !ok {
		t.Fatal("重连后应能取到 Client")
	}
	if first == second {
		t.Fatal("同网关重连应重建 Client（指针不同）")
	}
	if got := m.Count(); got != 1 {
		t.Fatalf("同网关重连后应只有 1 条连接，实际 %d", got)
	}

	// 旧 Client 必须已被 Stop：状态回到 disconnected 且不再重连。
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if first.State() == StateDisconnected {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if got := first.State(); got != StateDisconnected {
		t.Fatalf("旧 Client 应已被 Stop（disconnected），实际 %s", got)
	}

	waitForGatewayConnected(t, m, gateway)
}

// TestManagerDisconnectOneGateway 验证只断开指定网关，不影响其他网关。
func TestManagerDisconnectOneGateway(t *testing.T) {
	gateway, _ := startMultiGatewayTestServer(t)

	m := NewManager(Options{ClientID: "test-daemon", Version: "0.0.0-test"})
	defer m.DisconnectAll()

	// httptest 只提供一个端口，因此第二个网关用一个不可达端口
	// （连接会失败但条目存在），以此验证「断开一个不影响另一个」。
	g1 := gateway
	g2 := "http://127.0.0.1:1"

	m.Connect(g1, "token-1")
	m.Connect(g2, "token-2")
	if got := m.Count(); got != 2 {
		t.Fatalf("期望 2 个网关条目，实际 %d", got)
	}

	m.Disconnect(g1)
	if got := m.Count(); got != 1 {
		t.Fatalf("断开一个网关后应剩 1 条，实际 %d", got)
	}
	if _, ok := m.Get(g1); ok {
		t.Fatal("被断开的网关不应再存在")
	}
	if _, ok := m.Get(g2); !ok {
		t.Fatal("其他网关不应受影响")
	}

	// 断开不存在的网关应 no-op
	m.Disconnect("http://127.0.0.1:9")
	if got := m.Count(); got != 1 {
		t.Fatalf("断开不存在的网关不应改变数量，实际 %d", got)
	}
}

// TestManagerDisconnectAll 验证 DisconnectAll 清空全部网关。
func TestManagerDisconnectAll(t *testing.T) {
	gateway, _ := startMultiGatewayTestServer(t)

	m := NewManager(Options{ClientID: "test-daemon", Version: "0.0.0-test"})

	m.Connect(gateway, "token-1")
	m.Connect("http://127.0.0.1:1", "token-2")
	if got := m.Count(); got != 2 {
		t.Fatalf("期望 2 个网关条目，实际 %d", got)
	}

	first, _ := m.Get(gateway)
	m.DisconnectAll()

	if got := m.Count(); got != 0 {
		t.Fatalf("DisconnectAll 后应为 0 条，实际 %d", got)
	}
	if got := len(m.Status()); got != 0 {
		t.Fatalf("DisconnectAll 后 Status 应为空，实际 %d", got)
	}
	if _, ok := m.Get(gateway); ok {
		t.Fatal("DisconnectAll 后不应再能取到 Client")
	}
	if got := first.State(); got != StateDisconnected {
		t.Fatalf("DisconnectAll 后旧 Client 应为 disconnected，实际 %s", got)
	}
}

// TestManagerStatusSortedAndStable 验证 Status 按网关字典序排序且字段正确。
func TestManagerStatusSortedAndStable(t *testing.T) {
	m := NewManager(Options{ClientID: "test-daemon", Version: "0.0.0-test"})
	defer m.DisconnectAll()

	// 用不可达端口，避免真实网络依赖；只验证条目与排序。
	m.Connect("http://127.0.0.1:3", "t3")
	m.Connect("http://127.0.0.1:1", "t1")
	m.Connect("http://127.0.0.1:2", "t2")

	status := m.Status()
	if len(status) != 3 {
		t.Fatalf("期望 3 条状态，实际 %d", len(status))
	}
	// Gateway 字段是规范化后的地址（含协议前缀）。
	want := []string{"http://127.0.0.1:1", "http://127.0.0.1:2", "http://127.0.0.1:3"}
	for i, s := range status {
		if s.Gateway != want[i] {
			t.Fatalf("第 %d 条期望 gateway=%s，实际 %s（全部 %+v）", i, want[i], s.Gateway, status)
		}
		if s.State == "" {
			t.Fatalf("State 不应为空: %+v", s)
		}
		if s.Connected {
			t.Fatalf("不可达网关不应为 connected: %+v", s)
		}
	}

	// 再次调用应得到相同顺序（稳定）
	again := m.Status()
	for i := range again {
		if again[i].Gateway != status[i].Gateway {
			t.Fatalf("Status 顺序不稳定: %v vs %v", status, again)
		}
	}
}

// TestManagerEmptyInputNoop 验证空 gateway/token 为 no-op。
func TestManagerEmptyInputNoop(t *testing.T) {
	m := NewManager(Options{ClientID: "test-daemon", Version: "0.0.0-test"})
	defer m.DisconnectAll()

	m.Connect("", "token")
	m.Connect("   ", "token")
	m.Connect("http://127.0.0.1:1", "")
	if got := m.Count(); got != 0 {
		t.Fatalf("空 gateway/token 应为 no-op，实际条目数 %d", got)
	}

	// 空网关的 Disconnect / Get 也不应 panic 或产生条目
	m.Disconnect("")
	if _, ok := m.Get(""); ok {
		t.Fatal("空网关不应能取到 Client")
	}
}

// TestManagerConcurrentAccess 验证并发 Connect/Disconnect/Status 无 data race。
func TestManagerConcurrentAccess(t *testing.T) {
	gateway, _ := startMultiGatewayTestServer(t)

	m := NewManager(Options{ClientID: "test-daemon", Version: "0.0.0-test"})
	defer m.DisconnectAll()

	var wg sync.WaitGroup
	stop := make(chan struct{})
	var readers sync.WaitGroup

	// 并发 Connect/Disconnect 同一网关
	wg.Add(1)
	go func() {
		defer wg.Done()
		for i := 0; i < 30; i++ {
			m.Connect(gateway, "token")
			m.Disconnect(gateway)
		}
	}()

	// 并发 Status / Get / Count
	for i := 0; i < 4; i++ {
		readers.Add(1)
		go func() {
			defer readers.Done()
			for {
				select {
				case <-stop:
					return
				default:
				}
				_ = m.Status()
				_, _ = m.Get(gateway)
				_ = m.Count()
			}
		}()
	}

	// 先等写协程结束，再通知读协程退出，最后等读协程收尾。
	wg.Wait()
	close(stop)
	readers.Wait()

	// 最终应能正常收敛
	m.DisconnectAll()
	if got := m.Count(); got != 0 {
		t.Fatalf("DisconnectAll 后应为 0 条，实际 %d", got)
	}
}

// TestManagerGatewayAwareCallbacks 验证 Manager 会把网关上下文注入到回调中。
//
// 每个网关的 Client 回调都应带上该网关自身的地址，且互不串台。
func TestManagerGatewayAwareCallbacks(t *testing.T) {
	g1, connCh1 := startMultiGatewayTestServer(t)
	g2, connCh2 := startMultiGatewayTestServer(t)
	var mu sync.Mutex
	states := map[string][]string{}
	sessions := map[string]string{}
	authErrs := map[string]int{}

	m := NewManagerWithOptions(ManagerOptions{
		Options: Options{
			ClientID: "test-callbacks",
			Version:  "test",
		},
		OnGatewayStateChange: func(gateway, state string) {
			mu.Lock()
			states[gateway] = append(states[gateway], state)
			mu.Unlock()
		},
		OnGatewaySession: func(gateway, sessionID string) {
			mu.Lock()
			sessions[gateway] = sessionID
			mu.Unlock()
		},
		OnGatewayAuthError: func(gateway string, code int, reason string) {
			mu.Lock()
			authErrs[gateway] = code
			mu.Unlock()
		},
	})
	defer m.DisconnectAll()

	// g1/g2 是 startMultiGatewayTestServer 返回的完整网关地址（含 http://），
	// 两个不同的 httptest 服务端口 → 两个不同的 GatewayKey。
	m.Connect(g1, "token-1")
	m.Connect(g2, "token-2")

	// 等两条连接都建立。
	for i, ch := range []<-chan struct{}{connCh1, connCh2} {
		select {
		case <-ch:
		case <-time.After(3 * time.Second):
			t.Fatalf("等待第 %d 条连接建立超时", i+1)
		}
	}
	// 等 hello_ack 回调落地。
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(sessions)
		mu.Unlock()
		if n == 2 {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}

	mu.Lock()
	defer mu.Unlock()
	if len(sessions) != 2 {
		t.Fatalf("应有两个网关的 session 回调，实际 %v", sessions)
	}
	// 回调里的 gateway 必须是规范化后的完整地址。
	if _, ok := sessions[g1]; !ok {
		t.Fatalf("缺少网关 %s 的 session 回调，实际 %v", g1, sessions)
	}
	if _, ok := sessions[g2]; !ok {
		t.Fatalf("缺少网关 %s 的 session 回调，实际 %v", g2, sessions)
	}
	// 状态回调同样应按网关分开记录。
	if len(states[g1]) == 0 || len(states[g2]) == 0 {
		t.Fatalf("两个网关都应有状态回调，实际 %v", states)
	}
	// 未发生鉴权失败。
	if len(authErrs) != 0 {
		t.Fatalf("不应有鉴权失败回调，实际 %v", authErrs)
	}
}

// TestManagerAuthErrorCallbackCarriesGateway 验证鉴权失败回调会带上正确的网关。
//
// 场景：一个网关返回 401（鉴权失败），另一个正常连接；
// 回调必须只针对失败的那个网关，且不影响另一个网关的连接。
func TestManagerAuthErrorCallbackCarriesGateway(t *testing.T) {
	// 起一个握手即返回 401 的服务端，模拟鉴权失败。
	bad := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
	}))
	defer bad.Close()

	good, connCh := startMultiGatewayTestServer(t)

	var mu sync.Mutex
	failed := map[string]int{}

	m := NewManagerWithOptions(ManagerOptions{
		Options: Options{ClientID: "test-auth-err", Version: "test"},
		OnGatewayAuthError: func(gateway string, code int, reason string) {
			mu.Lock()
			failed[gateway] = code
			mu.Unlock()
		},
	})
	defer m.DisconnectAll()

	m.Connect(bad.URL, "bad-token")
	m.Connect(good, "good-token")

	// 正常网关应能连上。
	select {
	case <-connCh:
	case <-time.After(3 * time.Second):
		t.Fatal("正常网关应建立连接")
	}
	// 失败网关应触发鉴权失败回调。
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(failed)
		mu.Unlock()
		if n > 0 {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}

	mu.Lock()
	defer mu.Unlock()
	if len(failed) != 1 {
		t.Fatalf("应只有一个网关鉴权失败，实际 %v", failed)
	}
	if code, ok := failed[bad.URL]; !ok || code != http.StatusUnauthorized {
		t.Fatalf("鉴权失败回调应带网关 %s 与 401，实际 %v", bad.URL, failed)
	}
	// 另一个网关不受影响，仍在管理器中。
	if _, ok := m.Get(good); !ok {
		t.Fatal("正常网关不应因另一个网关鉴权失败而被移除")
	}
	if got := m.Count(); got != 2 {
		t.Fatalf("应仍有两个网关条目，实际 %d", got)
	}
}
