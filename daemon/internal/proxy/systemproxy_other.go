//go:build !windows

package proxy

import (
	"net/http"
	"net/url"
)

// systemProxyForRequest 在非 Windows 平台没有「系统代理」概念，
// 代理只由环境变量决定（已由 http.ProxyFromEnvironment 处理），故恒返回 nil。
func systemProxyForRequest(*http.Request) (*url.URL, error) {
	return nil, nil
}
