// Package auth 提供线程安全的凭据内存存储（支持多网关并存）。
//
// Token 仅存于内存，绝不落盘；进程退出即失效。
//
// 多网关模型：同一守护进程可同时持有多个网关的凭据，各自独立、互不覆盖。
// 语义与浏览器扩展 browser_extension/background/service_worker.js 保持一致：
// 凭据按「网关索引键」（GatewayKey，忽略协议差异的 host:port）归档。
package auth

import (
	"encoding/json"
	"errors"
	"log"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

// ErrNoCredentials 表示指定网关没有可用的凭据。
var ErrNoCredentials = errors.New("没有可用的凭据")

// Credentials 是一次认证推送的内容。
type Credentials struct {
	Gateway string
	Token   string
	// Name 是用户在前端设置的「终端名称」（默认计算机名）。
	// 用于向网关登录（hello 帧）时上报，使网关能区分不同终端。
	// 为空表示用户未设置，此时网关侧回退到 hostname。
	Name string
}

// NormalizeGateway 规范化网关地址：去除首尾空白；无协议前缀时补 http://；
// 去除尾部斜杠。与扩展的 normalizeGateway 语义一致。
//
// 显式识别 ws:// 与 wss://：网关地址天然可能是 WebSocket 形式（如
// ws://host:9999）。若不识别会被误加 "http://" 前缀，得到
// "http://ws://host:9999"，后续 url.Parse 会把 "ws" 当成主机名、端口丢失，
// 导致凭据索引键错误且连接必然失败（静默故障）。
func NormalizeGateway(gateway string) string {
	g := strings.TrimSpace(gateway)
	if g == "" {
		return ""
	}
	lower := strings.ToLower(g)
	if !strings.HasPrefix(lower, "http://") && !strings.HasPrefix(lower, "https://") &&
		!strings.HasPrefix(lower, "ws://") && !strings.HasPrefix(lower, "wss://") {
		g = "http://" + g
	}
	return strings.TrimRight(g, "/")
}

// GatewayKey 返回用于索引凭据的网关键：解析 URL 后取 hostname:port
// （端口缺省时 https/wss→443、http/ws→80）。
//
// 刻意忽略协议差异：http://host:443 与 https://host:443 视为同一网关，
// 因为前端页面声明的网关与用户填写的网关可能在协议上不一致。
// 同理 ws/wss 与 http/https 也视为同一网关（WebSocket 只是传输层差异）。
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
		if strings.EqualFold(u.Scheme, "https") || strings.EqualFold(u.Scheme, "wss") {
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
	// path 是持久化文件路径；为空表示不落盘（纯内存，进程退出即失效）。
	// 非空时，每次写操作都会把全部凭据同步写入该文件，供重启后恢复。
	path string
}

// NewStore 创建空的凭据存储（纯内存，不落盘）。
func NewStore() *Store {
	return &Store{
		creds: make(map[string]Credentials),
		valid: make(map[string]bool),
	}
}

// NewPersistentStore 创建带持久化的凭据存储：每次写操作都会把全部凭据
// 同步写入 path（0600），供进程重启后恢复登录态。
//
// 落盘失败只记日志、不影响内存语义（最坏情况是重启后需重新推送凭据）。
func NewPersistentStore(path string) *Store {
	s := NewStore()
	s.path = path
	return s
}

// LoadStore 从持久化文件加载凭据并返回带持久化的 Store。
//
// 文件不存在或解析失败时返回空 Store（不报错，调用方静默跳过），
// 保证 daemon 首次启动或凭据文件损坏时也能正常启动。
func LoadStore(path string) *Store {
	s := NewPersistentStore(path)
	if path == "" {
		return s
	}
	blob, err := os.ReadFile(path)
	if err != nil {
		return s
	}
	var creds []Credentials
	if err := json.Unmarshal(blob, &creds); err != nil {
		log.Printf("[auth] 解析凭据文件失败（%s）: %v", path, err)
		return s
	}
	for _, c := range creds {
		if c.Gateway == "" || c.Token == "" {
			continue
		}
		key := GatewayKey(c.Gateway)
		if key == "" {
			continue
		}
		s.creds[key] = c
		s.valid[key] = true
	}
	return s
}

// persist 把当前全部凭据同步写入持久化文件（原子写：临时文件 + rename）。
// path 为空时为空操作。写失败只记日志，不影响内存语义。
// 注意：必须在持有 s.mu 写锁时调用（直接读 s.creds，避免死锁）。
func (s *Store) persist() {
	if s.path == "" {
		return
	}
	creds := make([]Credentials, 0, len(s.creds))
	for _, c := range s.creds {
		creds = append(creds, c)
	}
	blob, err := json.Marshal(creds)
	if err != nil {
		log.Printf("[auth] 序列化凭据失败: %v", err)
		return
	}
	if err := os.MkdirAll(filepath.Dir(s.path), 0o700); err != nil {
		log.Printf("[auth] 创建凭据目录失败: %v", err)
		return
	}
	tmp := s.path + ".tmp"
	if err := os.WriteFile(tmp, blob, 0o600); err != nil {
		log.Printf("[auth] 写入凭据临时文件失败: %v", err)
		return
	}
	_ = os.Chmod(tmp, 0o600)
	if err := os.Rename(tmp, s.path); err != nil {
		_ = os.Remove(tmp)
		log.Printf("[auth] 保存凭据文件失败: %v", err)
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
	s.creds[key] = Credentials{Gateway: gateway, Token: token}
	s.valid[key] = true
	s.persist()
	s.mu.Unlock()
}

// SetWithName 写入指定网关的凭据（含终端名称），并重置该网关的 tokenValid 为 true。
// name 为空时保留该网关已有的名称（避免「只更新 token」的推送把名称清空）。
func (s *Store) SetWithName(gateway, token, name string) {
	key := GatewayKey(gateway)
	if key == "" {
		return
	}
	s.mu.Lock()
	prev := s.creds[key]
	if name == "" {
		name = prev.Name
	}
	s.creds[key] = Credentials{Gateway: gateway, Token: token, Name: name}
	s.valid[key] = true
	s.persist()
	s.mu.Unlock()
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
	delete(s.creds, key)
	delete(s.valid, key)
	s.persist()
	s.mu.Unlock()
}

// ClearAll 清空全部网关的凭据。
func (s *Store) ClearAll() {
	s.mu.Lock()
	s.creds = make(map[string]Credentials)
	s.valid = make(map[string]bool)
	s.persist()
	s.mu.Unlock()
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
