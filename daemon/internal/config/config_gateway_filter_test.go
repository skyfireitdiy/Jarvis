package config

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

// readFileString 读取文件内容为字符串，失败即 Fatal。
func readFileString(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取文件失败: %v", err)
	}
	return string(b)
}

// TestUpdateGatewayFilterReplacesInPlace 验证已存在这两个键时原地替换，
// 且**保留文件其余内容（含注释与其他键）**。
func TestUpdateGatewayFilterReplacesInPlace(t *testing.T) {
	path := writeTempConfig(t, strings.Join([]string{
		"# 用户手写的注释",
		"listen: 127.0.0.1:17800",
		"gateway_filter_mode: off",
		"gateway_filter_patterns: ",
		"web_listen: 127.0.0.1:17801",
		"",
	}, "\n"))

	if err := UpdateGatewayFilter(path, "whitelist", []string{"a.com:443", "b.com:8443"}); err != nil {
		t.Fatalf("UpdateGatewayFilter 失败: %v", err)
	}

	got := readFileString(t, path)
	// 注释与其他键必须保留。
	if !strings.Contains(got, "# 用户手写的注释") {
		t.Fatalf("注释应被保留，实际内容:\n%s", got)
	}
	if !strings.Contains(got, "listen: 127.0.0.1:17800") {
		t.Fatalf("其他键应被保留，实际内容:\n%s", got)
	}
	if !strings.Contains(got, "web_listen: 127.0.0.1:17801") {
		t.Fatalf("其他键应被保留，实际内容:\n%s", got)
	}
	// 两个键被更新。
	if !strings.Contains(got, "gateway_filter_mode: whitelist") {
		t.Fatalf("mode 应被更新，实际内容:\n%s", got)
	}
	if !strings.Contains(got, "gateway_filter_patterns: a.com:443,b.com:8443") {
		t.Fatalf("patterns 应被更新，实际内容:\n%s", got)
	}
	// 不应重复追加。
	if strings.Count(got, "gateway_filter_mode:") != 1 {
		t.Fatalf("gateway_filter_mode 应只出现一次，实际内容:\n%s", got)
	}
	if strings.Count(got, "gateway_filter_patterns:") != 1 {
		t.Fatalf("gateway_filter_patterns 应只出现一次，实际内容:\n%s", got)
	}

	// 落盘后应能被 Load 正确读回。
	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if cfg.GatewayFilterMode != "whitelist" {
		t.Fatalf("读回 mode 应为 whitelist，实际 %q", cfg.GatewayFilterMode)
	}
	if !reflect.DeepEqual(cfg.GatewayFilterPatterns, []string{"a.com:443", "b.com:8443"}) {
		t.Fatalf("读回 patterns 不符，实际 %v", cfg.GatewayFilterPatterns)
	}
}

// TestUpdateGatewayFilterAppendsWhenMissing 验证键不存在时追加到文件末尾。
func TestUpdateGatewayFilterAppendsWhenMissing(t *testing.T) {
	path := writeTempConfig(t, "listen: 127.0.0.1:17800\n")

	if err := UpdateGatewayFilter(path, "blacklist", []string{"evil.com:443"}); err != nil {
		t.Fatalf("UpdateGatewayFilter 失败: %v", err)
	}

	got := readFileString(t, path)
	if !strings.Contains(got, "listen: 127.0.0.1:17800") {
		t.Fatalf("原有内容应保留，实际内容:\n%s", got)
	}
	if !strings.Contains(got, "gateway_filter_mode: blacklist") {
		t.Fatalf("应追加 mode，实际内容:\n%s", got)
	}
	if !strings.Contains(got, "gateway_filter_patterns: evil.com:443") {
		t.Fatalf("应追加 patterns，实际内容:\n%s", got)
	}
}

// TestUpdateGatewayFilterCreatesFile 验证文件不存在时创建（含父目录）。
func TestUpdateGatewayFilterCreatesFile(t *testing.T) {
	dir := t.TempDir()
	// 刻意用一层不存在的子目录，验证 MkdirAll 生效。
	path := filepath.Join(dir, "nested", "config.yaml")

	if err := UpdateGatewayFilter(path, "whitelist", []string{"x.com:1"}); err != nil {
		t.Fatalf("UpdateGatewayFilter 失败: %v", err)
	}

	got := readFileString(t, path)
	if !strings.Contains(got, "gateway_filter_mode: whitelist") {
		t.Fatalf("新建文件应含 mode，实际内容:\n%s", got)
	}
	if !strings.Contains(got, "gateway_filter_patterns: x.com:1") {
		t.Fatalf("新建文件应含 patterns，实际内容:\n%s", got)
	}
}

// TestUpdateGatewayFilterEmptyPatterns 验证空名单写为空值，且能被读回为空。
func TestUpdateGatewayFilterEmptyPatterns(t *testing.T) {
	path := writeTempConfig(t, "gateway_filter_mode: whitelist\ngateway_filter_patterns: a.com:1\n")

	if err := UpdateGatewayFilter(path, "off", nil); err != nil {
		t.Fatalf("UpdateGatewayFilter 失败: %v", err)
	}

	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if cfg.GatewayFilterMode != "off" {
		t.Fatalf("mode 应为 off，实际 %q", cfg.GatewayFilterMode)
	}
	if len(cfg.GatewayFilterPatterns) != 0 {
		t.Fatalf("patterns 应为空，实际 %v", cfg.GatewayFilterPatterns)
	}
}

// TestUpdateGatewayFilterEmptyModeFallsBackOff 验证空 mode 回退为 off（不写空值）。
func TestUpdateGatewayFilterEmptyModeFallsBackOff(t *testing.T) {
	path := writeTempConfig(t, "listen: 127.0.0.1:17800\n")

	if err := UpdateGatewayFilter(path, "  ", nil); err != nil {
		t.Fatalf("UpdateGatewayFilter 失败: %v", err)
	}

	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if cfg.GatewayFilterMode != "off" {
		t.Fatalf("空 mode 应回退为 off，实际 %q", cfg.GatewayFilterMode)
	}
}

// TestUpdateGatewayFilterEmptyPath 验证空路径报错，避免误写到当前目录。
func TestUpdateGatewayFilterEmptyPath(t *testing.T) {
	if err := UpdateGatewayFilter("", "off", nil); err == nil {
		t.Fatal("空路径应报错")
	}
}
