// Package auth 提供线程安全的凭据内存存储。
//
// Token 仅存于内存，绝不落盘；进程退出即失效。
package auth

import (
	"errors"
	"sync"
)

// ErrNoCredentials 表示当前没有可用的凭据。
var ErrNoCredentials = errors.New("没有可用的凭据")

// Credentials 是一次认证推送的内容。
type Credentials struct {
	Gateway string
	Token   string
}

// Store 是线程安全的凭据存储。
type Store struct {
	mu sync.RWMutex
	// creds 为 nil 表示未认证。
	creds *Credentials
	// tokenValid 标记 Token 是否仍然有效（收到 4401/4403 后置为 false）。
	tokenValid bool
}

// NewStore 创建空的凭据存储。
func NewStore() *Store {
	return &Store{}
}

// Set 写入凭据，并重置 tokenValid 为 true。
func (s *Store) Set(gateway, token string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.creds = &Credentials{Gateway: gateway, Token: token}
	s.tokenValid = true
}

// Get 返回当前凭据的副本；未认证时返回 ErrNoCredentials。
func (s *Store) Get() (Credentials, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.creds == nil {
		return Credentials{}, ErrNoCredentials
	}
	return *s.creds, nil
}

// Clear 清空凭据。
func (s *Store) Clear() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.creds = nil
	s.tokenValid = false
}

// MarkTokenInvalid 标记当前 Token 已失效（鉴权失败时调用）。
func (s *Store) MarkTokenInvalid() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.creds != nil {
		s.tokenValid = false
	}
}

// Has 返回是否已认证。
func (s *Store) Has() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.creds != nil
}

// TokenValid 返回 Token 是否仍然有效。
func (s *Store) TokenValid() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.creds != nil && s.tokenValid
}
