package config

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

// writeTempConfig 写入临时配置文件并返回路径。
func writeTempConfig(t *testing.T, content string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "config.yaml")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("写入临时配置失败: %v", err)
	}
	return path
}

func TestDefaultGatewayFilter(t *testing.T) {
	cfg := Default()
	if cfg.GatewayFilterMode != "off" {
		t.Fatalf("默认模式应为 off，实际 %q", cfg.GatewayFilterMode)
	}
	if len(cfg.GatewayFilterPatterns) != 0 {
		t.Fatalf("默认名单应为空，实际 %v", cfg.GatewayFilterPatterns)
	}
}

func TestLoadGatewayFilterMode(t *testing.T) {
	path := writeTempConfig(t, "listen: 127.0.0.1:17800\ngateway_filter_mode: whitelist\n")
	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if cfg.GatewayFilterMode != "whitelist" {
		t.Fatalf("mode = %q, want whitelist", cfg.GatewayFilterMode)
	}
}

func TestLoadGatewayFilterPatterns(t *testing.T) {
	path := writeTempConfig(t,
		"gateway_filter_patterns: \"*.example.com:8000, 192.168.1.5:* ,,  a:1  \"\n")
	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	want := []string{"*.example.com:8000", "192.168.1.5:*", "a:1"}
	if !reflect.DeepEqual(cfg.GatewayFilterPatterns, want) {
		t.Fatalf("patterns = %v, want %v", cfg.GatewayFilterPatterns, want)
	}
}

func TestLoadGatewayFilterPatternsEmpty(t *testing.T) {
	path := writeTempConfig(t, "gateway_filter_patterns: \"\"\n")
	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if len(cfg.GatewayFilterPatterns) != 0 {
		t.Fatalf("空值应得到空名单，实际 %v", cfg.GatewayFilterPatterns)
	}
}

func TestValidateGatewayFilterMode(t *testing.T) {
	// 合法值应通过。
	for _, mode := range []string{"off", "whitelist", "blacklist"} {
		cfg := Default()
		cfg.GatewayFilterMode = mode
		if err := cfg.Validate(); err != nil {
			t.Errorf("mode=%q 应通过校验，实际报错: %v", mode, err)
		}
	}
	// 非法值应报错。
	cfg := Default()
	cfg.GatewayFilterMode = "allow"
	if err := cfg.Validate(); err == nil {
		t.Fatal("非法 mode 应校验失败")
	}
}

func TestValidateEmptyModeFails(t *testing.T) {
	// 空 mode（例如用户手写配置时漏填）应报错，避免静默变成不限制。
	cfg := Default()
	cfg.GatewayFilterMode = ""
	if err := cfg.Validate(); err == nil {
		t.Fatal("空 mode 应校验失败")
	}
}
