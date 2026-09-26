// Package localapi 提供本地 HTTP 接口，供网页推送登录信息与查询状态。
//
// 仅监听回环地址，不做额外鉴权（已确认）。
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
	client  *wsclient.Client
	version string
	// onAuth 在收到新凭据时回调，用于触发连接。
	onAuth func(gateway, token string)
	// onLogout 在登出时回调。
	onLogout func()
}

// New 创建本地 API 服务。
func New(store *auth.Store, client *wsclient.Client, version string, onAuth func(string, string), onLogout func()) *Server {
	return &Server{
		store:    store,
		client:   client,
		version:  version,
		onAuth:   onAuth,
		onLogout: onLogout,
	}
}

// Handler 返回路由。
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/auth", s.handleAuth)
	mux.HandleFunc("/api/status", s.handleStatus)
	mux.HandleFunc("/api/logout", s.handleLogout)
	return mux
}

type authRequest struct {
	Gateway string `json:"gateway"`
	Token   string `json:"token"`
}

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
	log.Printf("[localapi] 收到认证推送: gateway=%s token=%s...", req.Gateway, maskToken(req.Token))
	if s.onAuth != nil {
		s.onAuth(req.Gateway, req.Token)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success":        true,
		"status":         "connecting",
		"daemon_version": s.version,
	})
}

func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{
			"success": false,
			"error":   "method not allowed",
		})
		return
	}
	gateway := ""
	if creds, err := s.store.Get(); err == nil {
		gateway = creds.Gateway
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"connected":      s.client.State() == wsclient.StateConnected,
		"state":          s.client.State(),
		"session_id":     s.client.SessionID(),
		"gateway":        gateway,
		"token_valid":    s.store.TokenValid(),
		"daemon_version": s.version,
	})
}

func (s *Server) handleLogout(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{
			"success": false,
			"error":   "method not allowed",
		})
		return
	}
	s.store.Clear()
	if s.onLogout != nil {
		s.onLogout()
	}
	log.Printf("[localapi] 已登出，连接已断开")
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
