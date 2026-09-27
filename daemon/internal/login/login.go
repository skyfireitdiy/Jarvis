// Package login 实现「用用户名密码登录网关，并把凭据推送给本地守护进程」的纯逻辑。
//
// 背景：守护进程的 Token 默认只由网页推送（浏览器 → 本地 /api/auth），
// 在无 GUI 的主机上没有浏览器可用，无法走这条链路。本包提供命令行登录：
//
//	用户名 + 密码 → POST {gateway}/api/auth/login 换取 JWT
//	             → POST http://{listen}/api/auth 推送给本地守护进程
//
// 设计要点：
//   - 本文件只放可测试的纯逻辑（不读 os.Stdin、不解析命令行），便于用
//     httptest 覆盖各分支；交互式输入由 cmd 层与 password_*.go 负责。
//   - 凭据仍然只存于守护进程内存（见 internal/auth/store.go），本包不落盘。
package login

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// loginTimeout 是登录请求的整体超时。
//
// 登录只涉及一次轻量 JSON 往返；15s 足以覆盖慢速网络，同时避免网关无响应时
// 命令行长时间挂起。
const loginTimeout = 15 * time.Second

// pushTimeout 是向本地守护进程推送凭据的超时。
//
// 本地回环调用应极快；设短超时可以快速暴露「守护进程未运行」等问题。
const pushTimeout = 10 * time.Second

// maxErrBodyBytes 是错误响应体最多读取的字节数，用于拼装可读的错误信息。
const maxErrBodyBytes = 512

// LoginResult 是一次成功登录的结果。
type LoginResult struct {
	// Token 是网关签发的 JWT。
	Token string
	// Username 是登录用户名（网关返回的规范化用户名）。
	Username string
	// DisplayName 是用户显示名，可能为空。
	DisplayName string
	// IsAdmin 表示该用户是否管理员。
	IsAdmin bool
}

// loginRequest 是 POST {gateway}/api/auth/login 的请求体。
type loginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// loginResponse 是登录接口的响应体。
//
// 成功：{"success":true,"data":{"token":..,"user":{..}}}
// 失败：{"success":false,"error":{"code":..,"message":..}}
type loginResponse struct {
	Success bool `json:"success"`
	Data    struct {
		Token string `json:"token"`
		User  struct {
			UserID      string `json:"user_id"`
			Username    string `json:"username"`
			DisplayName string `json:"display_name"`
			IsAdmin     bool   `json:"is_admin"`
		} `json:"user"`
	} `json:"data"`
	Error struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

// NormalizeGateway 规范化网关地址：去除首尾空白与末尾斜杠。
//
// 与 internal/auth.NormalizeGateway 的「去尾斜杠」部分语义一致，但这里不补
// http:// 前缀——登录需要用户给出真实可达的地址，静默补全反而容易掩盖错误。
func NormalizeGateway(gateway string) string {
	return strings.TrimRight(strings.TrimSpace(gateway), "/")
}

// Login 用用户名密码登录网关，成功时返回 JWT 及用户信息。
//
// 错误分支：
//   - 网关地址 / 用户名 / 密码为空：直接返回参数错误；
//   - 网络不可达：返回带地址的请求错误；
//   - HTTP 非 200：错误信息含状态码与响应体片段；
//   - success=false：错误信息含网关返回的 error.message；
//   - success=true 但 token 为空：视为异常响应。
func Login(gateway, username, password string) (LoginResult, error) {
	gateway = NormalizeGateway(gateway)
	if gateway == "" {
		return LoginResult{}, fmt.Errorf("网关地址为空")
	}
	if strings.TrimSpace(username) == "" {
		return LoginResult{}, fmt.Errorf("用户名不能为空")
	}
	if password == "" {
		return LoginResult{}, fmt.Errorf("密码不能为空")
	}

	body, err := json.Marshal(loginRequest{Username: username, Password: password})
	if err != nil {
		return LoginResult{}, fmt.Errorf("序列化登录请求失败: %w", err)
	}

	url := gateway + "/api/auth/login"
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return LoginResult{}, fmt.Errorf("构造登录请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: loginTimeout}
	resp, err := client.Do(req)
	if err != nil {
		return LoginResult{}, fmt.Errorf("登录请求失败（%s）: %w", url, err)
	}
	defer resp.Body.Close()

	// 读取响应体：正常响应很小，上限 1MiB 足够且防止异常响应撑爆内存。
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return LoginResult{}, fmt.Errorf("读取登录响应失败: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return LoginResult{}, fmt.Errorf("登录失败（HTTP %d）: %s",
			resp.StatusCode, strings.TrimSpace(truncate(raw, maxErrBodyBytes)))
	}

	var parsed loginResponse
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return LoginResult{}, fmt.Errorf("解析登录响应失败: %w", err)
	}

	if !parsed.Success {
		msg := strings.TrimSpace(parsed.Error.Message)
		if msg == "" {
			msg = strings.TrimSpace(truncate(raw, maxErrBodyBytes))
		}
		if msg == "" {
			msg = "网关拒绝了登录请求"
		}
		return LoginResult{}, fmt.Errorf("登录被拒绝: %s", msg)
	}

	if strings.TrimSpace(parsed.Data.Token) == "" {
		return LoginResult{}, fmt.Errorf("登录响应缺少 token")
	}

	return LoginResult{
		Token:       parsed.Data.Token,
		Username:    parsed.Data.User.Username,
		DisplayName: parsed.Data.User.DisplayName,
		IsAdmin:     parsed.Data.User.IsAdmin,
	}, nil
}

// authPushRequest 是 POST http://{listen}/api/auth 的请求体。
//
// 字段与 internal/localapi 的 authRequest 对齐（gateway / token / name）。
type authPushRequest struct {
	Gateway string `json:"gateway"`
	Token   string `json:"token"`
	Name    string `json:"name"`
}

// PushAuth 把凭据推送给本地守护进程的 /api/auth，触发其连接网关。
//
// listen 形如 "127.0.0.1:17800"（来自配置或默认值）；name 为空时守护进程会
// 保留该网关已有名称（见 internal/localapi 的 SetWithName 语义）。
//
// 连接被拒时给出可读提示，引导用户先启动守护进程。
func PushAuth(listen, gateway, token, name string) error {
	listen = strings.TrimSpace(listen)
	if listen == "" {
		return fmt.Errorf("本地服务监听地址为空")
	}
	gateway = NormalizeGateway(gateway)
	if gateway == "" {
		return fmt.Errorf("网关地址为空")
	}
	if strings.TrimSpace(token) == "" {
		return fmt.Errorf("token 为空，无法推送凭据")
	}

	body, err := json.Marshal(authPushRequest{Gateway: gateway, Token: token, Name: name})
	if err != nil {
		return fmt.Errorf("序列化凭据失败: %w", err)
	}

	url := "http://" + listen + "/api/auth"
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("构造凭据推送请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: pushTimeout}
	resp, err := client.Do(req)
	if err != nil {
		// 本地服务未启动时通常是 connection refused，这里给出可操作的提示。
		return fmt.Errorf(
			"推送凭据失败：本地后台服务未运行（%s），请先启动 jarvis-daemon（%v）",
			listen, err)
	}
	defer resp.Body.Close()

	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("推送凭据失败（HTTP %d）: %s",
			resp.StatusCode, strings.TrimSpace(truncate(raw, maxErrBodyBytes)))
	}
	return nil
}

// MaskToken 只保留 Token 首尾少量字符，避免日志泄露完整凭据。
//
// 与 internal/localapi 的 maskToken 语义一致（本包不便反向依赖 localapi）。
func MaskToken(token string) string {
	if len(token) <= 8 {
		return "***"
	}
	return token[:4] + "..." + token[len(token)-4:]
}

// truncate 把字节切片裁剪到最多 n 字节，用于限制错误信息长度。
func truncate(b []byte, n int) string {
	if len(b) <= n {
		return string(b)
	}
	return string(b[:n])
}
