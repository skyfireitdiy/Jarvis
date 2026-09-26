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
)

// Config 是守护进程的运行配置。
type Config struct {
	// Listen 是本地 API 的监听地址，必须绑定回环地址。
	Listen string
	// Gateway 是默认网关地址；可被 /api/auth 推送的值覆盖。
	Gateway string
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
		HeartbeatInterval: DefaultHeartbeatInterval,
		ReconnectMin:      DefaultReconnectMin,
		ReconnectMax:      DefaultReconnectMax,
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
	default:
		return fmt.Errorf("未知配置项: %s", key)
	}
	return nil
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
	return nil
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
