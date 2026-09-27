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
	"os"
	"time"

	"jarvis-daemon/internal/auth"
	"jarvis-daemon/internal/capability"
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
	mux.HandleFunc("/api/settings", s.handleSettings)
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
	// Name 是前端设置的「终端名称」（默认计算机名），随 hello 上报给网关。
	// 可选：为空时保留该网关已有名称。
	Name string `json:"name"`
	// AutoInstallBrowserExt 是「是否自动安装/更新浏览器扩展」开关，随登录态一并
	// 由前端推送。用 *bool 以区分「未提供」（nil，保持原值，兼容旧前端）与
	// 「显式关闭」（false）。
	AutoInstallBrowserExt *bool `json:"auto_install_browser_ext"`
	// AutoUpdateDaemon 是「是否自动更新守护进程自身」开关，随登录态一并由前端
	// 推送。用 *bool 以区分「未提供」（nil，保持原值，兼容旧前端）与「显式关闭」
	// （false）。默认关闭，仅显式打开后才允许静默下载并替换自身。
	AutoUpdateDaemon *bool `json:"auto_update_daemon"`
}

// logoutRequest 的 gateway 可选：带则只登出该网关，不带则登出全部。
type logoutRequest struct {
	Gateway string `json:"gateway"`
}

// settingsRequest 是 /api/settings 的请求体。
//
// AutoInstallBrowserExt / AutoUpdateDaemon 用 *bool：nil 表示请求未提供该字段
// （返回 400），以区分「未提供」与「显式关闭」。目前仅此两项，后续可扩展。
type settingsRequest struct {
	AutoInstallBrowserExt *bool `json:"auto_install_browser_ext"`
	AutoUpdateDaemon      *bool `json:"auto_update_daemon"`
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
	s.store.SetWithName(req.Gateway, req.Token, req.Name)
	s.manager.ConnectWithName(req.Gateway, req.Token, req.Name)
	// 前端可随登录态一并推送「自动安装浏览器扩展」开关；未提供（nil）时保持原值，
	// 兼容旧前端。开关只存内存态，不落盘（用户要求只存浏览器存储）。
	if req.AutoInstallBrowserExt != nil {
		capability.SetAutoInstallBrowserExt(*req.AutoInstallBrowserExt)
	}
	// 同理，「自动更新守护进程」开关也随登录态推送；未提供（nil）时保持原值。
	if req.AutoUpdateDaemon != nil {
		capability.SetAutoUpdateDaemon(*req.AutoUpdateDaemon)
	}
	log.Printf("[localapi] 收到认证推送: gateway=%s token=%s... name=%q",
		req.Gateway, maskToken(req.Token), req.Name)
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
		// hostname 供前端在用户未设置「终端名称」时作为默认值
		// （浏览器无法直接读取系统主机名，故由守护进程提供）。
		"hostname": localHostname(),
	})
}

// localHostname 返回本机主机名；获取失败时返回空串（前端会保持名称为空）。
func localHostname() string {
	host, err := os.Hostname()
	if err != nil {
		return ""
	}
	return host
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

// handleSettings 读写守护进程的设置项（目前含「自动安装浏览器扩展」与
// 「自动更新守护进程」两个开关）。
//
// GET  → 返回当前值，供前端在打开设置界面时回显；
// POST → 更新开关，请求体可含 {"auto_install_browser_ext": bool}
//
//	与/或 {"auto_update_daemon": bool}，至少需提供其中一项。
//
// 注意：两个开关都只存内存态，不落盘（用户要求只存浏览器存储）；守护进程重启后
// 回到默认值 false（关闭），等待前端再次推送。
func (s *Server) handleSettings(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, http.StatusOK, map[string]any{
			"success":                  true,
			"auto_install_browser_ext": capability.AutoInstallBrowserExt(),
			"auto_update_daemon":       capability.AutoUpdateDaemon(),
		})
	case http.MethodPost:
		var req settingsRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]any{
				"success": false,
				"error":   "invalid json: " + err.Error(),
			})
			return
		}
		// 两个字段都缺失（nil）视为非法请求：语义明确，避免「静默不改」让调用方困惑。
		// 只提供其中一个字段是允许的（便于前端只改一项，且兼容旧前端）。
		if req.AutoInstallBrowserExt == nil && req.AutoUpdateDaemon == nil {
			writeJSON(w, http.StatusBadRequest, map[string]any{
				"success": false,
				"error":   "at least one of auto_install_browser_ext / auto_update_daemon is required",
			})
			return
		}
		if req.AutoInstallBrowserExt != nil {
			capability.SetAutoInstallBrowserExt(*req.AutoInstallBrowserExt)
			log.Printf("[localapi] 更新设置: auto_install_browser_ext=%v", *req.AutoInstallBrowserExt)
		}
		if req.AutoUpdateDaemon != nil {
			capability.SetAutoUpdateDaemon(*req.AutoUpdateDaemon)
			log.Printf("[localapi] 更新设置: auto_update_daemon=%v", *req.AutoUpdateDaemon)
		}
		// 回显更新后的实际值，便于调用方确认（未提供的字段返回其当前值）。
		writeJSON(w, http.StatusOK, map[string]any{
			"success":                  true,
			"auto_install_browser_ext": capability.AutoInstallBrowserExt(),
			"auto_update_daemon":       capability.AutoUpdateDaemon(),
		})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{
			"success": false,
			"error":   "method not allowed",
		})
	}
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
