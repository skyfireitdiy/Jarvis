package selfupdate

import (
	"os"
	"testing"
)

// TestTokenStateRoundTrip 校验：保存后能读回，且读取会删除文件（一次性语义）。
func TestTokenStateRoundTrip(t *testing.T) {
	// 用临时 HOME 隔离，避免污染真实用户目录。
	t.Setenv("HOME", t.TempDir())

	path, err := TokenStatePath()
	if err != nil {
		t.Fatalf("TokenStatePath 失败: %v", err)
	}

	state := TokenState{
		Gateway:     "https://example.com",
		Token:       "jwt-token",
		Name:        "my-terminal",
		SavedAtUnix: NowUnix(),
	}
	if err := SaveTokenState(state); err != nil {
		t.Fatalf("SaveTokenState 失败: %v", err)
	}

	// 文件应存在且权限为 0600（仅属主可读写）。
	fi, err := os.Stat(path)
	if err != nil {
		t.Fatalf("凭据文件不存在: %v", err)
	}
	if perm := fi.Mode().Perm(); perm != 0o600 {
		t.Fatalf("凭据文件权限应为 0600，实际 %o", perm)
	}

	got, ok := LoadAndClearTokenState()
	if !ok {
		t.Fatal("应成功读取凭据")
	}
	if got.Gateway != state.Gateway || got.Token != state.Token || got.Name != state.Name {
		t.Fatalf("读回内容不一致: %+v", got)
	}

	// 读取后文件必须被删除。
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("读取后凭据文件应被删除: %v", err)
	}
	// 再次读取应返回 false。
	if _, ok := LoadAndClearTokenState(); ok {
		t.Fatal("文件已删除后不应再读到凭据")
	}
}

// TestLoadAndClearTokenState_Missing 校验：文件不存在时返回 false 且不报错。
func TestLoadAndClearTokenState_Missing(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	if _, ok := LoadAndClearTokenState(); ok {
		t.Fatal("文件不存在时应返回 false")
	}
}

// TestLoadAndClearTokenState_Invalid 校验：内容非法时返回 false 并删除文件。
func TestLoadAndClearTokenState_Invalid(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	path, err := TokenStatePath()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(path[:len(path)-len("/update-token.json")], 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("not-json"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, ok := LoadAndClearTokenState(); ok {
		t.Fatal("内容非法时应返回 false")
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("非法内容读取后也应删除文件: %v", err)
	}
}

// TestLoadAndClearTokenState_Expired 校验：已过期（expires_at 早于当前）时视为无效。
func TestLoadAndClearTokenState_Expired(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	if err := SaveTokenState(TokenState{
		Gateway:       "https://example.com",
		Token:         "jwt",
		ExpiresAtUnix: NowUnix() - 10,
	}); err != nil {
		t.Fatal(err)
	}
	if _, ok := LoadAndClearTokenState(); ok {
		t.Fatal("已过期凭据应视为无效")
	}
}

// TestLoadAndClearTokenState_NotExpired 校验：expires_at 在未来时视为有效。
func TestLoadAndClearTokenState_NotExpired(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	if err := SaveTokenState(TokenState{
		Gateway:       "https://example.com",
		Token:         "jwt",
		ExpiresAtUnix: NowUnix() + 3600,
	}); err != nil {
		t.Fatal(err)
	}
	if _, ok := LoadAndClearTokenState(); !ok {
		t.Fatal("未过期凭据应视为有效")
	}
}

// TestLoadAndClearTokenState_EmptyFields 校验：缺失 gateway/token 时视为无效。
func TestLoadAndClearTokenState_EmptyFields(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	// 直接写入仅含 name 的 JSON（绕过 SaveTokenState 的字段校验）。
	path, err := TokenStatePath()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(path[:len(path)-len("/update-token.json")], 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(`{"name":"x"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, ok := LoadAndClearTokenState(); ok {
		t.Fatal("缺少 gateway/token 时应返回 false")
	}
}
