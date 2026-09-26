// Package auth 提供线程安全的凭据内存存储（支持多网关并存）。
//
// Token 仅存于内存，绝不落盘；进程退出即失效。
//
// 多网关模型：同一守护进程可同时持有多个网关的凭据，各自独立、互不覆盖。
// 语义与浏览器扩展 browser_extension/background/service_worker.js 保持一致：
// 凭据按「网关索引键」（GatewayKey，忽略协议差异的 host:port）归档。
package auth

import (
	"errors"
	"net/url"
	"strings"
	"sync"
)

// ErrNoCredentials 表示指定网关没有可用的凭据。
var ErrNoCredentials = errors.New("没有可用的凭据")

// Credentials 是一次认证推送的内容。
type Credentials struct {
	Gateway string
	Token   string
}

// NormalizeGateway 规范化网关地址：去除首尾空白；无 http(s):// 前缀时补 http://；
// 去除尾部斜杠。与扩展的 normalizeGateway 语义一致。
func NormalizeGateway(gateway string) string {
	g := strings.TrimSpace(gateway)
	if g == "" {
		return ""
	}
	lower := strings.ToLower(g)
	if !strings.HasPrefix(lower, "http://") && !strings.HasPrefix(lower, "https://") {
		g = "http://" + g
	}
	return strings.TrimRight(g, "/")
}

// GatewayKey 返回用于索引凭据的网关键：解析 URL 后取 hostname:port
// （端口缺省时 https→443、http→80）。
//
// 刻意忽略协议差异：http://host:443 与 https://host:443 视为同一网关，
// 因为前端页面声明的网关与用户填写的网关可能在协议上不一致。
// 解析失败时回退为 NormalizeGateway 的结果。
func GatewayKey(gateway string) string {
	g := NormalizeGateway(gateway)
	if g == "" {
		return ""
	}
	u, err := url.Parse(g)
	if err != nil || u.Hostname() == "" {
		return g
	}
	port := u.Port()
	if port == "" {
		if strings.EqualFold(u.Scheme, "https") {
			port = "443"
		} else {
			port = "80"
		}
	}
	return u.Hostname() + ":" + port
}

// Store 是线程安全的多网关凭据存储。
type Store struct {
	mu sync.RWMutex
	// creds 以 GatewayKey 为键；不存在该键表示该网关未认证。
	creds map[string]Credentials
	// valid 标记各网关的 Token 是否仍然有效（收到 4401/4403 后置为 false）。
	valid map[string]bool
}

// NewStore 创建空的凭据存储。
func NewStore() *Store {
	return &Store{
		creds: make(map[string]Credentials),
		valid: make(map[string]bool),
	}
}

// Set 写入指定网关的凭据，并重置该网关的 tokenValid 为 true。
// 同网关重复 Set 视为覆盖（token 更新），不影响其他网关条目。
func (s *Store) Set(gateway, token string) {
	key := GatewayKey(gateway)
	if key == "" {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.creds[key] = Credentials{Gateway: gateway, Token: token}
	s.valid[key] = true
}

// Get 返回指定网关凭据的副本；未认证时返回 ErrNoCredentials。
func (s *Store) Get(gateway string) (Credentials, error) {
	key := GatewayKey(gateway)
	if key == "" {
		return Credentials{}, ErrNoCredentials
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	creds, ok := s.creds[key]
	if !ok {
		return Credentials{}, ErrNoCredentials
	}
	return creds, nil
}

// Clear 清除指定网关的凭据（不影响其他网关）。
func (s *Store) Clear(gateway string) {
	key := GatewayKey(gateway)
	if key == "" {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.creds, key)
	delete(s.valid, key)
}

// ClearAll 清空全部网关的凭据。
func (s *Store) ClearAll() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.creds = make(map[string]Credentials)
	s.valid = make(map[string]bool)
}

// List 返回全部凭据的副本切片（不暴露内部 map）。
func (s *Store) List() []Credentials {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]Credentials, 0, len(s.creds))
	for _, c := range s.creds {
		out = append(out, c)
	}
	return out
}

// MarkTokenInvalid 标记指定网关的 Token 已失效（鉴权失败时调用）。
func (s *Store) MarkTokenInvalid(gateway string) {
	key := GatewayKey(gateway)
	if key == "" {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.creds[key]; ok {
		s.valid[key] = false
	}
}

// Has 返回指定网关是否已认证。
func (s *Store) Has(gateway string) bool {
	key := GatewayKey(gateway)
	if key == "" {
		return false
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	_, ok := s.creds[key]
	return ok
}

// TokenValid 返回指定网关的 Token 是否仍然有效。
func (s *Store) TokenValid(gateway string) bool {
	key := GatewayKey(gateway)
	if key == "" {
		return false
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	_, ok := s.creds[key]
	return ok && s.valid[key]
}
