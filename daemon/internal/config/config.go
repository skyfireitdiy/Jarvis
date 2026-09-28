// Package config 负责守护进程的配置加载：默认值 → 配置文件 → 命令行参数。
package config

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// 默认值。
const (
	DefaultListen            = "127.0.0.1:17800"
	DefaultHeartbeatInterval = 20 // 秒
	DefaultReconnectMin      = 1  // 秒
	DefaultReconnectMax      = 30 // 秒
	// DefaultWebListen 是 Web 登录服务的默认监听地址。
	//
	// 刻意监听 0.0.0.0：该服务就是给**其他机器**的浏览器访问的（无 GUI 主机
	// 上没有浏览器）。仅应在可信内网使用，详见 internal/webui 的安全说明。
	DefaultWebListen = "0.0.0.0:17801"
)

// Config 是守护进程的运行配置。
type Config struct {
	// Listen 是本地 API 的监听地址，必须绑定回环地址。
	Listen string
	// Gateway 是默认网关地址；可被 /api/auth 推送的值覆盖。
	Gateway string
	// WebListen 是 Web 登录服务的监听地址（供其他机器的浏览器访问）。
	//
	// 空字符串表示关闭该服务；默认 0.0.0.0:17801（见 DefaultWebListen）。
	WebListen string
	// GatewayFilterMode 是网关黑白名单模式：off / whitelist / blacklist。
	//
	// 默认 off（不限制）。用于防止「偶尔登录一次的网关」被自动发现后长期连接。
	// 该配置只应通过本机接口（命令行 / 本机浏览器）修改，见 internal/localapi
	// 的 /api/gateway-filter。
	GatewayFilterMode string
	// GatewayFilterPatterns 是黑白名单的匹配模式列表（host:port，支持 * 与 ? 通配符）。
	GatewayFilterPatterns []string
	// HeartbeatInterval 是心跳间隔（秒），可被 hello_ack 覆盖。
	HeartbeatInterval int
	// ReconnectMin / ReconnectMax 是重连退避的上下限（秒）。
	ReconnectMin int
	ReconnectMax int
}

// Default 返回内置默认配置。
func Default() Config {
	return Config{
		Listen:            DefaultListen,
		Gateway:           "",
		WebListen:         DefaultWebListen,
		HeartbeatInterval: DefaultHeartbeatInterval,
		ReconnectMin:      DefaultReconnectMin,
		ReconnectMax:      DefaultReconnectMax,
		// 网关黑白名单默认关闭（不限制）。
		GatewayFilterMode:     "off",
		GatewayFilterPatterns: nil,
	}
}

// DefaultPath 返回默认配置文件路径：~/.jarvis/daemon/config.yaml。
func DefaultPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	return filepath.Join(home, ".jarvis", "daemon", "config.yaml")
}

// Load 读取配置文件并返回配置。文件不存在时返回默认配置且不报错。
func Load(path string) (Config, error) {
	cfg := Default()
	if path == "" {
		return cfg, nil
	}
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return cfg, nil
		}
		return cfg, fmt.Errorf("打开配置文件失败: %w", err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	lineNo := 0
	for scanner.Scan() {
		lineNo++
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, ":")
		if !ok {
			return cfg, fmt.Errorf("配置文件第 %d 行格式错误（缺少 ':'）: %s", lineNo, line)
		}
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		value = strings.Trim(value, `"'`)
		if err := cfg.set(key, value); err != nil {
			return cfg, fmt.Errorf("配置文件第 %d 行: %w", lineNo, err)
		}
	}
	if err := scanner.Err(); err != nil {
		return cfg, fmt.Errorf("读取配置文件失败: %w", err)
	}
	return cfg, nil
}

func (c *Config) set(key, value string) error {
	switch key {
	case "listen":
		c.Listen = value
	case "gateway":
		c.Gateway = value
	case "web_listen":
		// 空值表示关闭 Web 登录服务，故不做非空校验。
		c.WebListen = value
	case "heartbeat_interval":
		n, err := strconv.Atoi(value)
		if err != nil {
			return fmt.Errorf("heartbeat_interval 必须是整数: %q", value)
		}
		c.HeartbeatInterval = n
	case "reconnect_min":
		n, err := strconv.Atoi(value)
		if err != nil {
			return fmt.Errorf("reconnect_min 必须是整数: %q", value)
		}
		c.ReconnectMin = n
	case "reconnect_max":
		n, err := strconv.Atoi(value)
		if err != nil {
			return fmt.Errorf("reconnect_max 必须是整数: %q", value)
		}
		c.ReconnectMax = n
	case "gateway_filter_mode":
		// 直接赋值，合法性由 Validate 统一校验（保持 set 只做解析）。
		c.GatewayFilterMode = value
	case "gateway_filter_patterns":
		// 逗号分隔的匹配模式列表；逐项 trim 并过滤空项。
		// 空值表示清空名单（配合 mode=off 即不限制）。
		c.GatewayFilterPatterns = splitPatterns(value)
	default:
		return fmt.Errorf("未知配置项: %s", key)
	}
	return nil
}

// splitPatterns 把逗号分隔的模式串拆成列表，逐项 trim 并过滤空项。
func splitPatterns(value string) []string {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	parts := strings.Split(value, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if v := strings.TrimSpace(p); v != "" {
			out = append(out, v)
		}
	}
	return out
}

// Validate 校验配置合法性。
func (c Config) Validate() error {
	if c.Listen == "" {
		return fmt.Errorf("listen 不能为空")
	}
	if !isLoopback(c.Listen) {
		return fmt.Errorf("listen 必须绑定回环地址（127.0.0.1 / localhost / [::1]），当前为 %q", c.Listen)
	}
	if c.HeartbeatInterval <= 0 {
		return fmt.Errorf("heartbeat_interval 必须为正数，当前为 %d", c.HeartbeatInterval)
	}
	if c.ReconnectMin <= 0 || c.ReconnectMax < c.ReconnectMin {
		return fmt.Errorf("重连退避区间非法: min=%d max=%d", c.ReconnectMin, c.ReconnectMax)
	}
	// 黑白名单模式必须是三种合法值之一；非法值会导致启动失败，避免静默变成
	// 「不限制」而让用户误以为名单已生效。
	switch c.GatewayFilterMode {
	case "off", "whitelist", "blacklist":
	default:
		return fmt.Errorf("gateway_filter_mode 必须是 off / whitelist / blacklist 之一，当前为 %q", c.GatewayFilterMode)
	}
	return nil
}

// UpdateGatewayFilter 把网关黑白名单写回配置文件。
//
// 设计取舍：**只改这两行键，保留文件其余内容（含注释与其他键）**，
// 而不是全量重写——全量重写会丢失用户手写的注释与键顺序。
//
// 行为：
//   - 文件不存在时创建（含必要的父目录）；
//   - 已存在 gateway_filter_mode / gateway_filter_patterns 行则原地替换；
//   - 不存在则追加到文件末尾；
//   - patterns 为空时写空值（gateway_filter_patterns: ）。
//
// 写入用「同目录临时文件 + 原子 rename」，避免写一半崩溃导致配置文件损坏。
func UpdateGatewayFilter(path, mode string, patterns []string) error {
	if strings.TrimSpace(path) == "" {
		return fmt.Errorf("配置文件路径为空")
	}
	mode = strings.TrimSpace(mode)
	if mode == "" {
		mode = "off"
	}
	patternsLine := "gateway_filter_patterns: " + strings.Join(patterns, ",")

	// 读取现有内容（不存在则视为空文件）。
	var lines []string
	raw, err := os.ReadFile(path)
	if err != nil {
		if !os.IsNotExist(err) {
			return fmt.Errorf("读取配置文件失败: %w", err)
		}
	} else {
		lines = strings.Split(strings.TrimRight(string(raw), "\n"), "\n")
		if len(lines) == 1 && lines[0] == "" {
			lines = nil
		}
	}

	// 原地替换或追加这两个键；用 done* 标记避免重复追加。
	modeDone, patternsDone := false, false
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "gateway_filter_mode:") {
			lines[i] = "gateway_filter_mode: " + mode
			modeDone = true
		} else if strings.HasPrefix(trimmed, "gateway_filter_patterns:") {
			lines[i] = patternsLine
			patternsDone = true
		}
	}
	if !modeDone {
		lines = append(lines, "gateway_filter_mode: "+mode)
	}
	if !patternsDone {
		lines = append(lines, patternsLine)
	}

	content := strings.Join(lines, "\n") + "\n"
	if err := writeFileAtomic(path, []byte(content), 0o600); err != nil {
		return fmt.Errorf("写入配置文件失败: %w", err)
	}
	return nil
}

// writeFileAtomic 以「同目录临时文件 + rename」原子地写入文件。
//
// 同目录可保证 rename 在同一文件系统内（跨设备 rename 会失败）；
// 临时文件用 0600 权限，避免配置内容（可能含网关地址）被其他用户读取。
func writeFileAtomic(path string, data []byte, perm os.FileMode) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, ".config-*.tmp")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer func() {
		// 成功路径下 rename 后该文件已不存在，Remove 失败可忽略；
		// 失败路径下则负责清理临时文件。
		_ = os.Remove(tmpName)
	}()
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Chmod(perm); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmpName, path)
}

// isLoopback 判断监听地址是否绑定回环。
func isLoopback(listen string) bool {
	host := listen
	if h, _, err := splitHostPort(listen); err == nil {
		host = h
	}
	host = strings.Trim(host, "[]")
	switch host {
	case "127.0.0.1", "localhost", "::1":
		return true
	}
	return strings.HasPrefix(host, "127.")
}

func splitHostPort(addr string) (string, string, error) {
	idx := strings.LastIndex(addr, ":")
	if idx < 0 {
		return "", "", fmt.Errorf("no port")
	}
	return addr[:idx], addr[idx+1:], nil
}
