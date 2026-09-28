package wsclient

import (
	"testing"
	"time"
)

// TestManagerAllowGatewayBlocksConnect 验证 AllowGateway 返回 false 时，
// ConnectWithName 直接跳过、不创建任何 Client。
//
// 这是「网关黑白名单」在 daemon 侧的最终拦截点：即便上层（页面推送、
// autoDiscover 等）把不在名单内的网关塞进来，也不会真的建连。
func TestManagerAllowGatewayBlocksConnect(t *testing.T) {
	gateway, _ := startMultiGatewayTestServer(t)

	m := NewManagerWithOptions(ManagerOptions{
		Options: Options{ClientID: "test-daemon", Version: "0.0.0-test"},
		// 一律拒绝。
		AllowGateway: func(string) bool { return false },
	})
	defer m.DisconnectAll()

	m.Connect(gateway, "token-a")

	if got := m.Count(); got != 0 {
		t.Fatalf("被拦截的网关不应创建连接，实际 Count=%d", got)
	}
	if status := m.Status(); len(status) != 0 {
		t.Fatalf("被拦截的网关不应出现在状态里，实际 %+v", status)
	}
	// 再等一小段时间，确认没有异步建连（拦截发生在建连之前，应始终为 0）。
	time.Sleep(50 * time.Millisecond)
	if got := m.Count(); got != 0 {
		t.Fatalf("被拦截的网关在延迟后仍不应创建连接，实际 Count=%d", got)
	}
}

// TestManagerAllowGatewayNilAllows 验证 AllowGateway 为 nil 时不限制（默认行为不变）。
func TestManagerAllowGatewayNilAllows(t *testing.T) {
	gateway, _ := startMultiGatewayTestServer(t)

	// 显式不设置 AllowGateway（nil）。
	m := NewManager(Options{ClientID: "test-daemon", Version: "0.0.0-test"})
	defer m.DisconnectAll()

	m.Connect(gateway, "token-a")
	waitForGatewayConnected(t, m, gateway)

	if got := m.Count(); got != 1 {
		t.Fatalf("nil AllowGateway 应不限制连接，实际 Count=%d", got)
	}
}

// TestManagerAllowGatewaySelective 验证 AllowGateway 按网关逐个判定：
// 允许的建连、拒绝的不建连，互不影响。
func TestManagerAllowGatewaySelective(t *testing.T) {
	allowed, _ := startMultiGatewayTestServer(t)
	blocked, _ := startMultiGatewayTestServer(t)

	m := NewManagerWithOptions(ManagerOptions{
		Options: Options{ClientID: "test-daemon", Version: "0.0.0-test"},
		AllowGateway: func(gateway string) bool {
			return gateway == allowed
		},
	})
	defer m.DisconnectAll()

	m.Connect(allowed, "token-a")
	m.Connect(blocked, "token-b")

	waitForGatewayConnected(t, m, allowed)

	if _, ok := m.Get(blocked); ok {
		t.Fatalf("被拒绝的网关 %s 不应存在 Client", blocked)
	}
	if got := m.Count(); got != 1 {
		t.Fatalf("应只有 1 条连接，实际 %d", got)
	}
}

// TestManagerAllowGatewayKeepsExistingConnection 验证「只阻止新连接，不主动断开旧连接」：
// 先在不限制时建连，之后把该网关改为拒绝，再 Connect 一次也不应断开既有连接。
//
// 注意：ConnectWithName 的拦截发生在加锁之前，返回时不会触碰既有 Client；
// 这里通过再次 Connect（而非 Disconnect）确认旧连接仍存活。
func TestManagerAllowGatewayKeepsExistingConnection(t *testing.T) {
	gateway, _ := startMultiGatewayTestServer(t)

	allow := true
	m := NewManagerWithOptions(ManagerOptions{
		Options:      Options{ClientID: "test-daemon", Version: "0.0.0-test"},
		AllowGateway: func(string) bool { return allow },
	})
	defer m.DisconnectAll()

	// 先允许并建连。
	m.Connect(gateway, "token-a")
	waitForGatewayConnected(t, m, gateway)

	// 之后改为拒绝；再次 Connect 应被拦截，但既有连接不受影响。
	allow = false
	m.Connect(gateway, "token-a")

	c, ok := m.Get(gateway)
	if !ok {
		t.Fatalf("既有连接不应因名单变化被移除")
	}
	if got := c.State(); got != StateConnected {
		t.Fatalf("既有连接应保持 connected，实际 %s", got)
	}
	if got := m.Count(); got != 1 {
		t.Fatalf("应仍只有 1 条连接，实际 %d", got)
	}
}
