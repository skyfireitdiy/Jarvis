// Package wsclient 实现与网关的 WebSocket 连接。
//
// 协议与浏览器扩展一致，但走独立的守护进程端点：
//   - 连接 {ws_gateway}/api/daemon/ws
//   - 子协议 ["jarvis-daemon", "jarvis-token.<urlencoded-token>"]
//   - 首帧 hello，应答 hello_ack
//   - 周期性 ping / pong
//   - 关闭码 4401/4403 表示鉴权失败，不再重连
package wsclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"

	"jarvis-daemon/internal/capability"
	"jarvis-daemon/internal/handler"
)

// 网关鉴权失败时使用的关闭码（与网关 app.py 的扩展 WS 端点一致）。
const (
	closeAuthFailed = 4401
	closeForbidden  = 4403
)

// Options 是客户端配置。
type Options struct {
	// Gateway 是网关地址，如 https://jvs-ai.cn 或 http://127.0.0.1:8000。
	Gateway string
	// Token 是网关 JWT。
	Token string
	// ClientID 是本客户端标识。
	ClientID string
	// Version 是守护进程版本，作为 extension_version 上报。
	Version string
	// HeartbeatInterval 是默认心跳间隔（秒）；hello_ack 可覆盖。
	HeartbeatInterval int
	// ReconnectMin / ReconnectMax 是重连退避上下限（秒）。
	ReconnectMin int
	ReconnectMax int
	// OnStateChange 在连接状态变化时回调（connecting/connected/disconnected）。
	OnStateChange func(state string)
	// OnAuthError 在鉴权失败时回调（收到 4401/4403）。
	OnAuthError func(code int, reason string)
	// OnSession 在收到 hello_ack 时回调，参数为 session_id。
	OnSession func(sessionID string)
	// Registry 是能力注册表；为 nil 时回退到旧的占位 Dispatch 行为。
	Registry *capability.Registry
}

// Client 是网关 WebSocket 客户端。
type Client struct {
	opts Options

	mu        sync.RWMutex
	state     string
	sessionID string
	ws        *websocket.Conn

	// 控制重连与心跳
	cancel  context.CancelFunc
	stopped bool
	// authFailed 表示当前 Token 已失效，不再重连。
	authFailed bool
}

// 连接状态。
const (
	StateDisconnected = "disconnected"
	StateConnecting   = "connecting"
	StateConnected    = "connected"
)

// New 创建客户端。
func New(opts Options) *Client {
	if opts.HeartbeatInterval <= 0 {
		opts.HeartbeatInterval = 20
	}
	if opts.ReconnectMin <= 0 {
		opts.ReconnectMin = 1
	}
	if opts.ReconnectMax < opts.ReconnectMin {
		opts.ReconnectMax = 30
	}
	return &Client{opts: opts, state: StateDisconnected}
}

// State 返回当前连接状态。
func (c *Client) State() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.state
}

// SessionID 返回当前会话 ID（未连接时为空）。
func (c *Client) SessionID() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.sessionID
}

// AuthFailed 返回是否因鉴权失败而停止。
func (c *Client) AuthFailed() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.authFailed
}

// UpdateCredentials 更新网关与 Token。
//
// 应在 Start 之前调用；若连接已在运行，调用方需自行 Stop 后重新 Start。
func (c *Client) UpdateCredentials(gateway, token string) {
	c.mu.Lock()
	c.opts.Gateway = gateway
	c.opts.Token = token
	c.authFailed = false
	c.mu.Unlock()
}

// Start 启动连接循环（非阻塞）。重复调用会先停止旧循环。
func (c *Client) Start() {
	c.Stop()
	ctx, cancel := context.WithCancel(context.Background())
	c.mu.Lock()
	c.cancel = cancel
	c.stopped = false
	c.authFailed = false
	c.mu.Unlock()
	go c.run(ctx)
}

// Stop 停止连接循环并断开连接。
func (c *Client) Stop() {
	c.mu.Lock()
	if c.cancel != nil {
		c.cancel()
		c.cancel = nil
	}
	c.stopped = true
	ws := c.ws
	c.ws = nil
	c.sessionID = ""
	c.mu.Unlock()
	if ws != nil {
		_ = ws.Close()
	}
	c.setState(StateDisconnected)
}

func (c *Client) setState(state string) {
	c.mu.Lock()
	if c.state == state {
		c.mu.Unlock()
		return
	}
	c.state = state
	c.mu.Unlock()
	if c.opts.OnStateChange != nil {
		c.opts.OnStateChange(state)
	}
}

// run 是连接主循环：连接 → 收发 → 断开 → 退避重连。
func (c *Client) run(ctx context.Context) {
	attempt := 0
	for {
		if ctx.Err() != nil {
			return
		}
		err := c.connectAndServe(ctx)
		if ctx.Err() != nil {
			return
		}
		if errors.Is(err, errAuthFailed) {
			log.Printf("[wsclient] 鉴权失败，停止重连: %v", err)
			return
		}
		if err != nil {
			log.Printf("[wsclient] 连接结束: %v", err)
		}
		delay := ReconnectDelay(attempt, c.opts.ReconnectMin, c.opts.ReconnectMax)
		attempt++
		log.Printf("[wsclient] %s 后重连（第 %d 次）", delay, attempt)
		select {
		case <-ctx.Done():
			return
		case <-time.After(delay):
		}
	}
}

// errAuthFailed 表示鉴权失败，不应重连。
var errAuthFailed = errors.New("鉴权失败")

// connectAndServe 建立一次连接并处理消息，直到断开。
func (c *Client) connectAndServe(ctx context.Context) error {
	c.setState(StateConnecting)

	wsURL, err := BuildWSURL(c.opts.Gateway)
	if err != nil {
		return err
	}
	protocols := BuildSubprotocols(c.opts.Token)

	dialer := websocket.Dialer{
		Subprotocols:     protocols,
		HandshakeTimeout: 15 * time.Second,
	}
	conn, resp, err := dialer.DialContext(ctx, wsURL, http.Header{})
	if err != nil {
		// 握手阶段被拒：网关会以 4401 关闭，但 gorilla 在握手失败时
		// 只能拿到 HTTP 响应，无法拿到关闭码，这里按 HTTP 状态判断。
		if resp != nil && (resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden) {
			c.markAuthFailed(resp.StatusCode)
			return fmt.Errorf("%w: HTTP %d", errAuthFailed, resp.StatusCode)
		}
		return fmt.Errorf("连接失败: %w", err)
	}
	defer conn.Close()

	c.mu.Lock()
	c.ws = conn
	c.mu.Unlock()
	defer func() {
		c.mu.Lock()
		if c.ws == conn {
			c.ws = nil
			c.sessionID = ""
		}
		c.mu.Unlock()
	}()

	c.setState(StateConnected)
	log.Printf("[wsclient] 已连接 %s（子协议 %v）", wsURL, conn.Subprotocol())

	// 发送 hello
	//
	// 守护进程只上报自身（用户侧服务）的系统信息；浏览器信息由浏览器扩展
	// 自行上报，守护进程不代报，故此处不再发送 browser_info。
	hello := map[string]any{
		"type":              "hello",
		"client_id":         c.opts.ClientID,
		"extension_version": c.opts.Version,
		"tabs":              []any{},
	}
	if sysInfo, err := capability.CollectSystemInfo(); err != nil {
		log.Printf("[wsclient] 采集系统信息失败，hello 将不含 system_info: %v", err)
	} else {
		hello["system_info"] = sysInfo
		log.Printf("[wsclient] hello 将上报 system_info: hostname=%v fields=%d",
			sysInfo["hostname"], len(sysInfo))
	}
	if err := conn.WriteJSON(hello); err != nil {
		return fmt.Errorf("发送 hello 失败: %w", err)
	}

	// 心跳
	hbCtx, hbCancel := context.WithCancel(ctx)
	defer hbCancel()
	go c.heartbeatLoop(hbCtx, conn)

	// 读循环
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			return c.classifyClose(err)
		}
		var msg map[string]any
		if err := json.Unmarshal(data, &msg); err != nil {
			log.Printf("[wsclient] 收到非法 JSON，已忽略: %s", string(data))
			continue
		}
		c.handleMessage(conn, msg)
	}
}

// classifyClose 判断断开原因；鉴权失败时标记并返回 errAuthFailed。
func (c *Client) classifyClose(err error) error {
	var closeErr *websocket.CloseError
	if errors.As(err, &closeErr) {
		if closeErr.Code == closeAuthFailed || closeErr.Code == closeForbidden {
			c.markAuthFailed(closeErr.Code)
			return fmt.Errorf("%w: 关闭码 %d %s", errAuthFailed, closeErr.Code, closeErr.Text)
		}
		return fmt.Errorf("连接关闭: %d %s", closeErr.Code, closeErr.Text)
	}
	return fmt.Errorf("读取失败: %w", err)
}

func (c *Client) markAuthFailed(code int) {
	c.mu.Lock()
	c.authFailed = true
	c.mu.Unlock()
	if c.opts.OnAuthError != nil {
		c.opts.OnAuthError(code, "")
	}
}

// handleMessage 处理一条网关消息。
func (c *Client) handleMessage(conn *websocket.Conn, msg map[string]any) {
	msgType, _ := msg["type"].(string)
	switch msgType {
	case "pong":
		return
	case "hello_ack":
		if sid, ok := msg["session_id"].(string); ok {
			c.mu.Lock()
			c.sessionID = sid
			c.mu.Unlock()
			log.Printf("[wsclient] hello_ack: session_id=%s", sid)
			if c.opts.OnSession != nil {
				c.opts.OnSession(sid)
			}
		}
	case "command":
		c.handleCommand(conn, msg)
	case "capability.list":
		c.handleCapabilityList(conn)
	case "capability.call":
		c.handleCapabilityCall(conn, msg)
	default:
		log.Printf("[wsclient] 收到未处理的消息类型: %s", msgType)
	}
}

// handleCapabilityList 回应网关的能力列表查询。
func (c *Client) handleCapabilityList(conn *websocket.Conn) {
	caps := []capability.Capability{}
	if c.opts.Registry != nil {
		caps = c.opts.Registry.List()
	}
	reply := map[string]any{
		"type":         "capability.list.result",
		"capabilities": caps,
	}
	if err := conn.WriteJSON(reply); err != nil {
		log.Printf("[wsclient] 回能力列表失败: %v", err)
	}
}

// handleCapabilityCall 执行一次能力调用并回结果。
func (c *Client) handleCapabilityCall(conn *websocket.Conn, msg map[string]any) {
	callID, _ := msg["id"].(string)
	name, _ := msg["name"].(string)

	var res capability.Result
	switch {
	case c.opts.Registry == nil:
		res = capability.Result{Success: false, Error: "capability registry is nil"}
	case name == "":
		res = capability.Result{Success: false, Error: "capability name is empty"}
	default:
		params, _ := msg["params"].(map[string]any)
		res = c.opts.Registry.Execute(name, params)
	}

	reply := map[string]any{
		"type":    "capability.call.result",
		"id":      callID,
		"success": res.Success,
		"data":    res.Data,
		"error":   res.Error,
	}
	if err := conn.WriteJSON(reply); err != nil {
		log.Printf("[wsclient] 回能力调用结果失败: %v", err)
	}
}

// handleCommand 处理指令并回结果。
func (c *Client) handleCommand(conn *websocket.Conn, msg map[string]any) {
	raw, err := json.Marshal(msg)
	if err != nil {
		log.Printf("[wsclient] 指令序列化失败: %v", err)
		return
	}
	var cmd handler.Command
	if err := json.Unmarshal(raw, &cmd); err != nil {
		log.Printf("[wsclient] 指令解析失败: %v", err)
		return
	}
	// 已接入能力注册表时走注册表，否则保持旧的占位行为。
	var result handler.Result
	if c.opts.Registry != nil {
		result = handler.DispatchWith(c.opts.Registry, cmd)
	} else {
		result = handler.Dispatch(cmd)
	}
	if err := conn.WriteJSON(result); err != nil {
		log.Printf("[wsclient] 回结果失败: %v", err)
	}
}

// heartbeatLoop 周期性发送 ping。
func (c *Client) heartbeatLoop(ctx context.Context, conn *websocket.Conn) {
	interval := time.Duration(c.opts.HeartbeatInterval) * time.Second
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := conn.WriteJSON(map[string]string{"type": "ping"}); err != nil {
				log.Printf("[wsclient] 心跳发送失败: %v", err)
				return
			}
		}
	}
}

// ReconnectDelay 计算第 attempt 次重连的退避时长（attempt 从 0 开始）。
//
// 公式与扩展一致：min(base * 2^attempt, max)。
func ReconnectDelay(attempt, minSec, maxSec int) time.Duration {
	if attempt < 0 {
		attempt = 0
	}
	delay := minSec
	for i := 0; i < attempt; i++ {
		delay *= 2
		if delay >= maxSec {
			delay = maxSec
			break
		}
	}
	if delay > maxSec {
		delay = maxSec
	}
	return time.Duration(delay) * time.Second
}

// BuildSubprotocols 构造 WS 子协议列表。
func BuildSubprotocols(token string) []string {
	protocols := []string{"jarvis-daemon"}
	if token != "" {
		protocols = append(protocols, "jarvis-token."+url.QueryEscape(token))
	}
	return protocols
}

// BuildWSURL 把网关地址转换为 WS 端点地址。
func BuildWSURL(gateway string) (string, error) {
	g := NormalizeGateway(gateway)
	if g == "" {
		return "", errors.New("网关地址为空")
	}
	ws := ToWSURL(g)
	return ws + "/api/daemon/ws", nil
}

// NormalizeGateway 规范化网关地址：补协议、去尾部斜杠。
func NormalizeGateway(gateway string) string {
	g := strings.TrimSpace(gateway)
	if g == "" {
		return ""
	}
	if !strings.HasPrefix(g, "http://") && !strings.HasPrefix(g, "https://") {
		g = "https://" + g
	}
	return strings.TrimRight(g, "/")
}

// ToWSURL 把 http(s) 转换为 ws(s)。
func ToWSURL(gateway string) string {
	if strings.HasPrefix(gateway, "https://") {
		return "wss://" + strings.TrimPrefix(gateway, "https://")
	}
	if strings.HasPrefix(gateway, "http://") {
		return "ws://" + strings.TrimPrefix(gateway, "http://")
	}
	return gateway
}
