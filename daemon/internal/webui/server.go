// Package webui 提供一个**面向外部浏览器**的 Web 登录界面。
//
// 背景：无 GUI 的主机（如无桌面的 Linux 服务器）没有浏览器可用，无法通过
// 浏览器扩展把凭据推送给守护进程。本服务让用户从**另一台机器**的浏览器访问
// 该主机，在页面上填写「网关地址 + 用户名 + 密码」，由守护进程代为登录网关、
// 拿到 JWT 后直接建立连接。
//
// 与 internal/localapi 的区别：
//   - localapi 只监听回环地址、供本机浏览器/扩展推送已签发的凭据；
//   - 本服务刻意监听 0.0.0.0，供**其他机器**的浏览器访问，因此会接收密码。
//
// ⚠️ 安全提示（方案 A，仅做登录、不做额外防护）：
//   - 页面与接口走明文 HTTP，密码在局域网内明文传输，仅应在可信内网使用；
//   - 服务对访问者不做鉴权，任何能连到该端口的人都可以尝试登录；
//   - 部署时应配合防火墙限制来源网段。
package webui

import (
	"encoding/json"
	"log"
	"net/http"
	"strings"

	"jarvis-daemon/internal/auth"
	"jarvis-daemon/internal/login"
	"jarvis-daemon/internal/wsclient"
)

// Server 是 Web 登录服务。
//
// 与 localapi.Server 同构：持有同一份凭据存储与连接管理器，因此登录成功后
// 直接复用「写入凭据 + 发起连接」的既有链路，无需另起一套状态。
type Server struct {
	store   *auth.Store
	manager *wsclient.Manager
	version string
}

// New 创建 Web 登录服务。
func New(store *auth.Store, manager *wsclient.Manager, version string) *Server {
	return &Server{store: store, manager: manager, version: version}
}

// loginRequest 是 POST /api/login 的请求体。
type loginRequest struct {
	Gateway  string `json:"gateway"`
	Username string `json:"username"`
	Password string `json:"password"`
	// Name 是终端名称（可选）：留空时守护进程保留该网关已有名称。
	Name string `json:"name"`
}

// Handler 返回路由。
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/", s.handleIndex)
	mux.HandleFunc("/api/login", s.handleLogin)
	return mux
}

// handleIndex 返回内嵌的登录页。
//
// 只响应根路径，其余路径一律 404，避免误把页面当作通配兜底。
func (s *Server) handleIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{
			"success": false,
			"error":   "method not allowed",
		})
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	// 登录页含凭据表单，禁止被缓存。
	w.Header().Set("Cache-Control", "no-store")
	_, _ = w.Write([]byte(indexHTML))
}

// handleLogin 接收浏览器提交的凭据，代为登录网关并建立连接。
//
// 成功：写入凭据存储并触发连接，返回 {"success":true,"message":"..."}。
// 失败：返回 400 与可读的中文错误信息（不含密码）。
func (s *Server) handleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{
			"success": false,
			"error":   "method not allowed",
		})
		return
	}

	var req loginRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 64<<10)).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{
			"success": false,
			"error":   "请求格式错误: " + err.Error(),
		})
		return
	}

	gateway := login.NormalizeGateway(req.Gateway)
	username := strings.TrimSpace(req.Username)
	if gateway == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{
			"success": false,
			"error":   "请填写网关地址",
		})
		return
	}
	if username == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{
			"success": false,
			"error":   "请填写用户名",
		})
		return
	}
	if req.Password == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{
			"success": false,
			"error":   "请填写密码",
		})
		return
	}

	// 复用命令行登录的同一套逻辑，避免两处各写一份 HTTP 调用。
	result, err := login.Login(gateway, username, req.Password)
	if err != nil {
		// 错误信息可能来自网关（如「用户名或密码错误」），直接回显给页面；
		// 绝不记录密码本身。
		log.Printf("[webui] 登录失败: gateway=%s username=%s err=%v", gateway, username, err)
		writeJSON(w, http.StatusBadRequest, map[string]any{
			"success": false,
			"error":   err.Error(),
		})
		return
	}

	// 与 localapi.handleAuth 相同的入口：写凭据 + 发起连接（多网关并存，互不覆盖）。
	s.store.SetWithName(gateway, result.Token, req.Name)
	s.manager.ConnectWithName(gateway, result.Token, req.Name)

	log.Printf("[webui] 登录成功并已连接: gateway=%s username=%s token=%s",
		gateway, username, login.MaskToken(result.Token))

	displayName := result.DisplayName
	if displayName == "" {
		displayName = result.Username
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"message": "登录成功，守护进程已连接网关，本页面可以关闭了",
		"user":    displayName,
	})
}

// writeJSON 输出 JSON 响应。
func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
