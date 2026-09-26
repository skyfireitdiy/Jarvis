package wsclient

import (
	"sort"
	"sync"

	"jarvis-daemon/internal/auth"
)

// GatewayStatus 是单个网关的连接状态快照。
type GatewayStatus struct {
	// Gateway 是规范化后的网关地址（与扩展 normalizeGateway 一致）。
	Gateway string `json:"gateway"`
	// SessionID 是当前会话 ID（未连接时为空）。
	SessionID string `json:"session_id"`
	// Connected 表示当前是否处于已连接状态。
	Connected bool `json:"connected"`
	// State 是连接状态（connecting/connected/disconnected）。
	State string `json:"state"`
	// TokenValid 表示该网关的 Token 是否仍然有效（鉴权失败后为 false）。
	TokenValid bool `json:"token_valid"`
	// AuthFailed 表示该网关是否因鉴权失败而停止重连。
	AuthFailed bool `json:"auth_failed"`
}

// ManagerOptions 是多网关连接管理器的配置。
//
// 它把「公共配置」与「需要感知网关的回调」分开：
//   - 公共配置（ClientID/Version/Registry/HeartbeatInterval/ReconnectMin/
//     ReconnectMax 等）对所有网关一致，放在 Options 里；
//   - 回调需要知道是哪个网关触发的（例如鉴权失败只标记该网关的 Token 失效），
//     因此单独提供带 gateway 参数的版本。
//
// 注意：Options 里的 OnStateChange / OnAuthError / OnSession 若被设置，
// 会被 Manager 覆盖为「先注入网关、再调用对应 Gateway 版本回调」的包装，
// 以避免上层拿到无法区分网关的回调。
type ManagerOptions struct {
	// Options 是各网关 Client 的公共配置模板（Gateway/Token 会被覆盖）。
	Options Options
	// OnGatewayStateChange 在某个网关的连接状态变化时回调。
	OnGatewayStateChange func(gateway, state string)
	// OnGatewayAuthError 在某个网关鉴权失败时回调（收到 4401/4403）。
	OnGatewayAuthError func(gateway string, code int, reason string)
	// OnGatewaySession 在某个网关收到 hello_ack 时回调。
	OnGatewaySession func(gateway, sessionID string)
}

// Manager 管理多个网关的 WebSocket 连接。
//
// 语义与浏览器扩展 browser_extension/background/service_worker.js 的
// Map<gateway, ...> 一致：
//   - 每个网关各自持有一个独立的 Client（独立连接、独立 session_id）；
//   - 同一网关只保留最新一条连接（重新 Connect 会先停掉旧连接）；
//   - 断开某个网关不影响其他网关；
//   - 鉴权失败只影响该网关。
//
// 内部以 auth.GatewayKey(gateway) 为键，因此忽略协议差异
// （http://h:443 与 https://h:443 视为同一网关）。
type Manager struct {
	mu sync.Mutex
	// opts 是创建各网关 Client 的配置模板（Gateway/Token 会被覆盖）。
	opts Options
	// onStateChange / onAuthError / onSession 是带 gateway 维度的回调。
	onStateChange func(gateway, state string)
	onAuthError   func(gateway string, code int, reason string)
	onSession     func(gateway, sessionID string)
	// clients 以 auth.GatewayKey 为键。
	clients map[string]*Client
	// gateways 记录每个键对应的原始网关地址，供 Status 展示与 Disconnect 反查。
	gateways map[string]string
	// tokens 记录每个网关最近一次设置的 Token，供 Status 判断 token 有效性。
	tokens map[string]string
}

// NewManager 创建多网关连接管理器。
//
// opts 作为所有网关 Client 的公共配置模板（ClientID/Version/Registry/
// HeartbeatInterval/ReconnectMin/ReconnectMax 等）；其中 Gateway 与 Token
// 会在 Connect 时按具体网关覆盖。Options 里的回调（OnStateChange /
// OnAuthError / OnSession）会被忽略，请改用 ManagerOptions 的
// OnGateway* 版本以获得网关上下文。
func NewManager(opts Options) *Manager {
	return NewManagerWithOptions(ManagerOptions{Options: opts})
}

// NewManagerWithOptions 创建多网关连接管理器，并支持带网关维度的回调。
func NewManagerWithOptions(mopts ManagerOptions) *Manager {
	// Options 里的回调无法区分网关，统一由 Manager 注入网关后转发，
	// 因此这里清空，避免被 Client 直接调用导致上层拿不到网关上下文。
	opts := mopts.Options
	opts.OnStateChange = nil
	opts.OnAuthError = nil
	opts.OnSession = nil
	return &Manager{
		opts:          opts,
		onStateChange: mopts.OnGatewayStateChange,
		onAuthError:   mopts.OnGatewayAuthError,
		onSession:     mopts.OnGatewaySession,
		clients:       make(map[string]*Client),
		gateways:      make(map[string]string),
		tokens:        make(map[string]string),
	}
}

// Connect 以给定凭据连接指定网关。
//
// 若该网关已有连接，则先停掉旧 Client 再重建（同网关只保留最新连接），
// 不影响其他网关。gateway 或 token 为空时直接返回（no-op）。
func (m *Manager) Connect(gateway, token string) {
	key := auth.GatewayKey(gateway)
	if key == "" || token == "" {
		return
	}
	normalized := auth.NormalizeGateway(gateway)

	// 先在锁内完成 map 更新，把旧 Client 取出来；解锁后再 Stop，
	// 避免在持锁状态下执行可能阻塞的 Stop（并避免与 Status 互相阻塞）。
	m.mu.Lock()
	old := m.clients[key]
	opts := m.opts
	opts.Gateway = normalized
	opts.Token = token
	// 为每个网关单独注入回调，使上层能区分是哪个网关触发的。
	// 用 normalized 作为回调里的 gateway，与 Status() 展示的地址一致。
	if m.onStateChange != nil {
		opts.OnStateChange = func(state string) { m.onStateChange(normalized, state) }
	}
	if m.onAuthError != nil {
		opts.OnAuthError = func(code int, reason string) { m.onAuthError(normalized, code, reason) }
	}
	if m.onSession != nil {
		opts.OnSession = func(sessionID string) { m.onSession(normalized, sessionID) }
	}
	client := New(opts)
	m.clients[key] = client
	m.gateways[key] = normalized
	m.tokens[key] = token
	m.mu.Unlock()

	if old != nil {
		old.Stop()
	}
	client.Start()
}

// Disconnect 断开指定网关并移除其连接（不影响其他网关）。
// 该网关不存在时 no-op。
func (m *Manager) Disconnect(gateway string) {
	key := auth.GatewayKey(gateway)
	if key == "" {
		return
	}
	m.mu.Lock()
	client := m.clients[key]
	delete(m.clients, key)
	delete(m.gateways, key)
	delete(m.tokens, key)
	m.mu.Unlock()

	if client != nil {
		client.Stop()
	}
}

// DisconnectAll 断开全部网关并清空内部记录。
func (m *Manager) DisconnectAll() {
	m.mu.Lock()
	clients := make([]*Client, 0, len(m.clients))
	for _, c := range m.clients {
		clients = append(clients, c)
	}
	m.clients = make(map[string]*Client)
	m.gateways = make(map[string]string)
	m.tokens = make(map[string]string)
	m.mu.Unlock()

	for _, c := range clients {
		c.Stop()
	}
}

// Get 返回指定网关的 Client（供测试与上层使用）。
func (m *Manager) Get(gateway string) (*Client, bool) {
	key := auth.GatewayKey(gateway)
	if key == "" {
		return nil, false
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	c, ok := m.clients[key]
	return c, ok
}

// Count 返回当前管理的网关数量。
func (m *Manager) Count() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.clients)
}

// Status 返回全部网关的状态快照，按网关地址字典序排序以保证输出稳定。
func (m *Manager) Status() []GatewayStatus {
	m.mu.Lock()
	keys := make([]string, 0, len(m.clients))
	for k := range m.clients {
		keys = append(keys, k)
	}
	clients := make(map[string]*Client, len(m.clients))
	gateways := make(map[string]string, len(m.gateways))
	for k, c := range m.clients {
		clients[k] = c
	}
	for k, g := range m.gateways {
		gateways[k] = g
	}
	m.mu.Unlock()

	out := make([]GatewayStatus, 0, len(keys))
	for _, k := range keys {
		c := clients[k]
		if c == nil {
			continue
		}
		state := c.State()
		out = append(out, GatewayStatus{
			Gateway:    gateways[k],
			SessionID:  c.SessionID(),
			Connected:  state == StateConnected,
			State:      state,
			TokenValid: !c.AuthFailed(),
			AuthFailed: c.AuthFailed(),
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Gateway < out[j].Gateway })
	return out
}
