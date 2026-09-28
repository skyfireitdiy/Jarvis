// Package proxy 为守护进程的出站请求提供统一的代理决策。
//
// 代理来源按以下优先级合并：
//  1. 环境变量 HTTP_PROXY / HTTPS_PROXY / NO_PROXY（含小写形式），
//     由标准库 http.ProxyFromEnvironment 处理；
//  2. 系统代理（仅 Windows）：注册表
//     HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings
//     中的 ProxyEnable / ProxyServer / ProxyOverride，即「Internet 选项 /
//     系统设置 → 代理」里配置的值。
//
// 之所以不能只用 http.ProxyFromEnvironment：它只读环境变量，而 Windows 上
// 用户在系统设置里配置的代理并不会写入环境变量，导致守护进程直连失败。
//
// 本包不引入任何第三方依赖，也不使用 cgo。
package proxy

import (
	"net/http"
	"net/url"
)

// ProxyFunc 返回一个代理决策函数，语义与 http.ProxyFromEnvironment 兼容：
// 返回 nil 表示对该请求不使用代理。
//
// 该函数可直接赋给 http.Transport.Proxy，也可赋给
// gorilla/websocket 的 Dialer.Proxy（二者签名一致）。
func ProxyFunc() func(*http.Request) (*url.URL, error) {
	return func(req *http.Request) (*url.URL, error) {
		if u, err := http.ProxyFromEnvironment(req); err != nil || u != nil {
			return u, err
		}
		// 环境变量未指定代理时，回退到系统代理（仅 Windows 有实现）。
		return systemProxyForRequest(req)
	}
}

// Transport 返回一个使用 ProxyFunc 的 *http.Transport。
//
// 以 http.DefaultTransport 为模板克隆，保留其连接池、超时等默认设置，
// 仅覆盖 Proxy 字段，避免影响其它默认行为。
func Transport() *http.Transport {
	base, ok := http.DefaultTransport.(*http.Transport)
	if !ok {
		// 理论上不会发生；退化为一个最小可用配置。
		return &http.Transport{Proxy: ProxyFunc()}
	}
	t := base.Clone()
	t.Proxy = ProxyFunc()
	return t
}

// DirectTransport 返回一个**不使用任何代理**的 *http.Transport。
//
// 用于访问本机回环地址（如 127.0.0.1）的场景：这类请求绝不应经过代理，
// 即使用户配置了系统代理或环境变量代理。http.ProxyFromEnvironment 只对
// "localhost" 做特殊处理，对 "127.0.0.1" 会按 NO_PROXY 判断，故不能依赖它。
func DirectTransport() *http.Transport {
	base, ok := http.DefaultTransport.(*http.Transport)
	if !ok {
		return &http.Transport{}
	}
	t := base.Clone()
	t.Proxy = nil
	return t
}
