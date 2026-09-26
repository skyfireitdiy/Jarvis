package auth

import "testing"

func TestStoreSetGet(t *testing.T) {
	s := NewStore()
	if s.Has() {
		t.Fatal("新 store 不应有凭据")
	}
	if _, err := s.Get(); err != ErrNoCredentials {
		t.Fatalf("未认证时应返回 ErrNoCredentials，实际 %v", err)
	}

	s.Set("https://jvs-ai.cn", "tok123")
	creds, err := s.Get()
	if err != nil {
		t.Fatalf("Get 报错: %v", err)
	}
	if creds.Gateway != "https://jvs-ai.cn" || creds.Token != "tok123" {
		t.Errorf("凭据不符: %+v", creds)
	}
	if !s.Has() {
		t.Error("Set 后 Has 应为 true")
	}
	if !s.TokenValid() {
		t.Error("Set 后 TokenValid 应为 true")
	}
}

func TestStoreClear(t *testing.T) {
	s := NewStore()
	s.Set("g", "t")
	s.Clear()
	if s.Has() {
		t.Error("Clear 后 Has 应为 false")
	}
	if s.TokenValid() {
		t.Error("Clear 后 TokenValid 应为 false")
	}
	if _, err := s.Get(); err != ErrNoCredentials {
		t.Errorf("Clear 后 Get 应返回 ErrNoCredentials，实际 %v", err)
	}
}

func TestStoreMarkTokenInvalid(t *testing.T) {
	s := NewStore()
	s.Set("g", "t")
	s.MarkTokenInvalid()
	if !s.Has() {
		t.Error("标记失效不应清空凭据")
	}
	if s.TokenValid() {
		t.Error("标记后 TokenValid 应为 false")
	}
	// 重新 Set 应恢复有效。
	s.Set("g", "t2")
	if !s.TokenValid() {
		t.Error("重新 Set 后 TokenValid 应恢复为 true")
	}
}

func TestStoreMarkTokenInvalidWithoutCreds(t *testing.T) {
	s := NewStore()
	s.MarkTokenInvalid() // 不应 panic
	if s.Has() {
		t.Error("无凭据时标记不应产生凭据")
	}
}
