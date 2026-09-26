// Package localapi 提供本地 HTTP 接口，供网页推送登录信息与查询状态。
//
// 仅监听回环地址，不做额外鉴权（已确认）。
//
// 支持多网关并存：网页可以先后向不同网关推送凭据，各网关各自连接、
// 互不覆盖；查询状态返回全部网关的快照。
package localapi

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"jarvis-daemon/internal/auth"
	"jarvis-daemon/internal/wsclient"
)

// Server 是本地 API 服务。
type Server struct {
	store   *auth.Store
	manager *wsclient.Manager
	version string
}

// New 创建本地 API 服务。
//
// store 保存各网关凭据，manager 管理各网关的 WebSocket 连接；
// 两者都以 auth.GatewayKey 为键，因此键天然对齐。
func New(store *auth.Store, manager *wsclient.Manager, version string) *Server {
	return &Server{
		store:   store,
		manager: manager,
		version: version,
	}
}

// Handler 返回路由。
//
// 外层包一层 CORS 处理：网页可能部署在任意源（如 https://jvs-ai.cn），
// 而本服务固定监听 http://127.0.0.1:17800，跨源访问必然触发预检，
// 没有 CORS 响应头浏览器会直接拦截请求。
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/auth", s.handleAuth)
	mux.HandleFunc("/api/status", s.handleStatus)
	mux.HandleFunc("/api/logout", s.handleLogout)
	return withCORS(mux)
}

// withCORS 为所有响应加上 CORS 头，并直接响应预检请求。
//
// 允许任意源（*）：本服务只监听回环地址、且不做鉴权，能被访问到的前提是
// 请求已经打到用户本机；凭据由请求体携带，不使用 Cookie，故无需
// Access-Control-Allow-Credentials。
// 同时允许 Chrome 私有网络访问（PNA）所需的头，避免公网页面访问
// 本机回环地址时被额外的私有网络预检拦截。
func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("Access-Control-Allow-Origin", "*")
		h.Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		h.Set("Access-Control-Allow-Headers", "Content-Type")
		h.Set("Access-Control-Max-Age", "600")
		h.Set("Access-Control-Allow-Private-Network", "true")

		// 预检请求：CORS 头已写入，直接返回 204，不再进入业务路由。
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

type authRequest struct {
	Gateway string `json:"gateway"`
	Token   string `json:"token"`
}

// logoutRequest 的 gateway 可选：带则只登出该网关，不带则登出全部。
type logoutRequest struct {
	Gateway string `json:"gateway"`
}

// handleAuth 接收网页推送的凭据并触发对应网关连接。
//
// 多网关并存：只影响请求中指定的网关，不会顶掉其他网关的连接。
func (s *Server) handleAuth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{
			"success": false,
			"error":   "method not allowed",
		})
		return
	}
	var req authRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{
			"success": false,
			"error":   "invalid json: " + err.Error(),
		})
		return
	}
	if req.Gateway == "" || req.Token == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{
			"success": false,
			"error":   "gateway and token are required",
		})
		return
	}
	s.store.Set(req.Gateway, req.Token)
	s.manager.Connect(req.Gateway, req.Token)
	log.Printf("[localapi] 收到认证推送: gateway=%s token=%s...", req.Gateway, maskToken(req.Token))
	writeJSON(w, http.StatusOK, map[string]any{
		"success":        true,
		"status":         "connecting",
		"daemon_version": s.version,
	})
}

// handleStatus 返回全部网关的状态快照。
//
// token_valid 以凭据存储为准（鉴权失败后为 false），其余字段取自连接管理器。
func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{
			"success": false,
			"error":   "method not allowed",
		})
		return
	}
	statuses := s.manager.Status()
	gateways := make([]wsclient.GatewayStatus, 0, len(statuses))
	for _, st := range statuses {
		// 管理器与存储的键一致（均为 GatewayKey），但 Status 里的 Gateway
		// 是规范化完整地址，需归一化后再查询存储。
		st.TokenValid = s.store.TokenValid(st.Gateway)
		gateways = append(gateways, st)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success":        true,
		"gateways":       gateways,
		"daemon_version": s.version,
	})
}

// handleLogout 登出：请求体可带 gateway 指定单个网关；不带则清空全部。
func (s *Server) handleLogout(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{
			"success": false,
			"error":   "method not allowed",
		})
		return
	}
	// 请求体可以为空（旧的全清语义），解析失败时按全清处理。
	var req logoutRequest
	_ = json.NewDecoder(r.Body).Decode(&req)

	if req.Gateway != "" {
		s.store.Clear(req.Gateway)
		s.manager.Disconnect(req.Gateway)
		log.Printf("[localapi] 已登出网关 %s", req.Gateway)
	} else {
		s.store.ClearAll()
		s.manager.DisconnectAll()
		log.Printf("[localapi] 已登出全部网关，连接已断开")
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true})
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

// maskToken 只保留 Token 首尾少量字符，避免日志泄露完整凭据。
func maskToken(token string) string {
	if len(token) <= 8 {
		return "***"
	}
	return token[:4] + "..." + token[len(token)-4:]
}

// NewHTTPServer 构造带超时的 http.Server。
func NewHTTPServer(addr string, handler http.Handler) *http.Server {
	return &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
	}
}
