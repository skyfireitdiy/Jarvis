package proxy

import (
	"net/url"
	"runtime"
	"strings"
)

// isWindows 报告当前是否运行在 Windows 上。
func isWindows() bool {
	return runtime.GOOS == "windows"
}

// 本文件放置与平台无关的代理字符串解析逻辑，便于在所有平台单测覆盖。

// pickProxyForScheme 从 ProxyServer 中取出指定 scheme 对应的代理地址。
//
// ProxyServer 有两种形式：
//   - "host:port"：所有协议共用；
//   - "http=host:port;https=host:port;ftp=host:port;socks=host:port"：按协议区分。
//
// 按协议区分时若没有该 scheme 的条目，则返回空（不使用代理）。
func pickProxyForScheme(server, scheme string) string {
	if !strings.Contains(server, "=") {
		return server
	}
	scheme = strings.ToLower(scheme)
	for _, part := range strings.Split(server, ";") {
		k, v, ok := strings.Cut(part, "=")
		if !ok {
			continue
		}
		if strings.ToLower(strings.TrimSpace(k)) == scheme {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

// parseProxyURL 把 "host:port" 或带协议的地址解析为 *url.URL。
// 无协议前缀时默认按 http 处理。
func parseProxyURL(raw string) (*url.URL, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	if !strings.Contains(raw, "://") {
		raw = "http://" + raw
	}
	return url.Parse(raw)
}

// matchProxyOverride 判断主机是否命中 ProxyOverride（NO_PROXY 语义）。
//
// 规则（与 Windows/主流实现一致）：
//   - 列表以 ';' 或 ',' 分隔；
//   - "*" 表示全部直连；
//   - "<local>" 表示不含点的本地主机名直连；
//   - 其余条目按后缀匹配（如 "example.com" 命中 "a.example.com"）。
func matchProxyOverride(host, override string) bool {
	host = strings.ToLower(strings.TrimSpace(host))
	if host == "" {
		return false
	}
	for _, item := range strings.FieldsFunc(override, func(r rune) bool {
		return r == ';' || r == ','
	}) {
		item = strings.ToLower(strings.TrimSpace(item))
		if item == "" {
			continue
		}
		switch item {
		case "*":
			return true
		case "<local>":
			if !strings.Contains(host, ".") {
				return true
			}
		default:
			item = strings.TrimPrefix(item, ".")
			if host == item || strings.HasSuffix(host, "."+item) {
				return true
			}
		}
	}
	return false
}
