package capability

// 本文件提供「OCR 能力」所需的网关列表注入点。
//
// 为什么需要注入：ocr.recognize 在未显式指定 gateway 时要回退到「daemon 已认证的
// 第一个网关」，但 capability 包不能反向依赖 auth.Store（会形成 capability → auth
// 的依赖，且 auth 已在 main 中被装配）。因此在 main.go 装配时把「列出已认证网关」
// 的函数注入进来，能力实现只依赖这个函数。
//
// 未注入时（如单元测试或未认证场景），回退逻辑会返回空列表，能力给出明确错误
// 而不是 panic。
import "sync"

// OcrGatewayLister 返回当前已认证的网关地址列表（顺序稳定，按地址升序）。
type OcrGatewayLister func() []string

var (
	ocrGatewayMu     sync.RWMutex
	ocrGatewayLister OcrGatewayLister
)

// SetOcrGatewayLister 注入「列出已认证网关」的函数（由 main.go 调用）。
//
// 传 nil 可清除注入，便于测试隔离。
func SetOcrGatewayLister(lister OcrGatewayLister) {
	ocrGatewayMu.Lock()
	defer ocrGatewayMu.Unlock()
	ocrGatewayLister = lister
}

// ocrListGateways 返回已认证网关列表；未注入时返回空列表。
func ocrListGateways() []string {
	ocrGatewayMu.RLock()
	lister := ocrGatewayLister
	ocrGatewayMu.RUnlock()
	if lister == nil {
		return nil
	}
	return lister()
}
