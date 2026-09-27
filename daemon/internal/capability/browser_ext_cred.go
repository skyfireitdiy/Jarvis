package capability

// 本文件提供「浏览器扩展同步」所需的凭据注入点。
//
// 为什么需要注入：能力 Handler 的签名是 func(map[string]any)(any,error)，无法
// 直接拿到 daemon 的凭据存储（auth.Store 位于 internal/auth，且 capability 包
// 不应反向依赖它）。因此在 main.go 装配时把「按网关取 Token」的函数注入进来，
// 能力实现只依赖这个函数。
//
// 未注入时（如单元测试或未认证场景），同步能力会返回明确错误而不是 panic。

import "sync"

// BrowserExtCredentialProvider 按网关返回可用 Token；无凭据时 ok=false。
type BrowserExtCredentialProvider func(gateway string) (token string, ok bool)

var (
	browserExtCredMu       sync.RWMutex
	browserExtCredProvider BrowserExtCredentialProvider
)

// SetBrowserExtCredentialProvider 注入凭据提供器（由 main.go 调用）。
//
// 传 nil 可清除注入，便于测试隔离。
func SetBrowserExtCredentialProvider(provider BrowserExtCredentialProvider) {
	browserExtCredMu.Lock()
	defer browserExtCredMu.Unlock()
	browserExtCredProvider = provider
}

// browserExtToken 按网关取 Token；未注入或无凭据时返回 ok=false。
func browserExtToken(gateway string) (string, bool) {
	browserExtCredMu.RLock()
	provider := browserExtCredProvider
	browserExtCredMu.RUnlock()
	if provider == nil {
		return "", false
	}
	return provider(gateway)
}

// BrowserExtToken 是 browserExtToken 的导出版本，供 main.go 在自动同步时取 Token。
func BrowserExtToken(gateway string) (string, bool) {
	return browserExtToken(gateway)
}
