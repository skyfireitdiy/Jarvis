//go:build !linux && !windows

package wsclient

import "sync"

// 终端会话错误码（与子节点 node_manager.py 约定一致）。
const (
	termErrInvalidCommand    = "INVALID_COMMAND"
	termErrNoTerminalManager = "NO_TERMINAL_MANAGER"
	termErrCreateFailed      = "TERMINAL_CREATE_FAILED"
	termErrNotFound          = "NOT_FOUND"
	termErrInternalError     = "INTERNAL_ERROR"
	termErrUnknownAction     = "UNKNOWN_ACTION"
)

// 输出环形缓冲容量上限（约 1MB，与 Gateway 终端一致）。
const terminalOutputBufferLimit = 1024 * 1024

// TerminalManager 是 daemon 内部终端会话管理器（不注册 capability）。
//
// 当前平台（非 Linux/Windows）不在 NLSpec 支持范围内（macOS 明确排除），
// 因此这里提供占位实现：create 一律返回 TERMINAL_CREATE_FAILED，
// 其余动作返回 NOT_FOUND / UNKNOWN_ACTION，保证编译通过且行为安全。
type TerminalManager struct {
	mu       sync.Mutex
	sessions map[string]struct{}
	sender   func(msg map[string]any) error
}

// NewTerminalManager 创建终端会话管理器。
func NewTerminalManager() *TerminalManager {
	return &TerminalManager{
		sessions: make(map[string]struct{}),
	}
}

// SetSender 注入输出回传函数（由 wsclient.Client 调用，复用其写锁）。
func (tm *TerminalManager) SetSender(sender func(msg map[string]any) error) {
	tm.mu.Lock()
	defer tm.mu.Unlock()
	tm.sender = sender
}

// CloseAll 关闭全部终端会话（daemon 退出时调用）。
func (tm *TerminalManager) CloseAll() {
	tm.mu.Lock()
	tm.sessions = make(map[string]struct{})
	tm.mu.Unlock()
}

// HandleRequest 处理一条 node_terminal_request，返回 node_terminal_response 的 payload。
func (tm *TerminalManager) HandleRequest(msg map[string]any) map[string]any {
	action, _ := msg["action"].(string)
	switch action {
	case "terminal_create":
		return errResponse(termErrCreateFailed, "terminal not supported on this platform")
	case "terminal_close", "terminal_session_input", "terminal_session_resize", "terminal_attach":
		return errResponse(termErrNotFound, "terminal not found")
	default:
		return errResponse(termErrUnknownAction, "unknown terminal action: "+action)
	}
}

// errResponse 构造错误响应 payload。
func errResponse(code, message string) map[string]any {
	return map[string]any{
		"success": false,
		"error": map[string]any{
			"code":    code,
			"message": message,
		},
	}
}
