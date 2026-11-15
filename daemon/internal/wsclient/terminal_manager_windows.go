//go:build windows

package wsclient

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"io"
	"log"
	"os"
	"os/exec"
	"sync"
	"syscall"
	"time"
)

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

// terminalSession 是一个 daemon 内部终端会话（Windows 管道方案）。
//
// creack/pty 在 Windows 上不支持（StartWithSize 返回 ErrUnsupported），
// 因此这里用等价管道方案：cmd 的 stdin/stdout/stderr 接管道，读循环读取
// 输出写入环形缓冲并回传网关。行为与 Linux PTY 路径一致。
type terminalSession struct {
	terminalID  string
	interpreter string
	workingDir  string
	sessionID   string
	createdAt   int64

	cmd    *exec.Cmd
	stdin  io.WriteCloser
	stdout io.ReadCloser

	mu       sync.Mutex
	closed   bool
	sequence int64
	buffer   []byte // 输出环形缓冲（约 1MB）
}

// TerminalManager 是 daemon 内部终端会话管理器（不注册 capability）。
type TerminalManager struct {
	mu       sync.Mutex
	sessions map[string]*terminalSession
	sender   func(msg map[string]any) error
}

// NewTerminalManager 创建终端会话管理器。
func NewTerminalManager() *TerminalManager {
	return &TerminalManager{
		sessions: make(map[string]*terminalSession),
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
	sessions := make([]*terminalSession, 0, len(tm.sessions))
	for _, s := range tm.sessions {
		sessions = append(sessions, s)
	}
	tm.sessions = make(map[string]*terminalSession)
	tm.mu.Unlock()

	for _, s := range sessions {
		s.close()
	}
}

// HandleRequest 处理一条 node_terminal_request，返回 node_terminal_response 的 payload。
func (tm *TerminalManager) HandleRequest(msg map[string]any) map[string]any {
	action, _ := msg["action"].(string)
	inner, _ := msg["payload"].(map[string]any)
	if inner == nil {
		inner = map[string]any{}
	}
	sessionID, _ := msg["session_id"].(string)

	switch action {
	case "terminal_create":
		return tm.create(inner, sessionID)
	case "terminal_close":
		return tm.close(inner)
	case "terminal_session_input":
		return tm.input(inner)
	case "terminal_session_resize":
		return tm.resize(inner)
	case "terminal_attach":
		return tm.attach(inner)
	default:
		return errResponse(termErrUnknownAction, "unknown terminal action: "+action)
	}
}

// create 创建终端会话（Windows 管道方案）。
func (tm *TerminalManager) create(inner map[string]any, sessionID string) map[string]any {
	interpreter, _ := inner["interpreter"].(string)
	if interpreter == "" {
		interpreter = os.Getenv("SHELL")
	}
	if interpreter == "" {
		interpreter = "cmd.exe"
	}
	workingDir, _ := inner["working_dir"].(string)
	if workingDir == "" {
		wd, err := os.UserHomeDir()
		if err != nil {
			wd = "."
		}
		workingDir = wd
	}

	terminalID := newTerminalID()

	cmd := exec.Command(interpreter)
	cmd.Dir = workingDir
	cmd.Env = append(os.Environ(), "TERM=xterm-256color")
	// 守护进程在 Windows 上以分离进程（无控制台）运行，若不带
	// CREATE_NO_WINDOW 启动控制台程序会闪黑框，故必须设置 SysProcAttr。
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: 0x08000000} // CREATE_NO_WINDOW

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return errResponse(termErrCreateFailed, "failed to create stdin pipe: "+err.Error())
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return errResponse(termErrCreateFailed, "failed to create stdout pipe: "+err.Error())
	}
	cmd.Stderr = cmd.Stdout

	if err := cmd.Start(); err != nil {
		log.Printf("[terminal] create failed interpreter=%s working_dir=%s: %v", interpreter, workingDir, err)
		return errResponse(termErrCreateFailed, "failed to start terminal: "+err.Error())
	}

	s := &terminalSession{
		terminalID:  terminalID,
		interpreter: interpreter,
		workingDir:  workingDir,
		sessionID:   sessionID,
		createdAt:   time.Now().Unix(),
		cmd:         cmd,
		stdin:       stdin,
		stdout:      stdout,
	}

	tm.mu.Lock()
	tm.sessions[terminalID] = s
	sender := tm.sender
	tm.mu.Unlock()

	go tm.readLoop(s, sender)

	log.Printf("[terminal] created terminal_id=%s interpreter=%s working_dir=%s session_id=%s",
		terminalID, interpreter, workingDir, sessionID)

	return map[string]any{
		"success": true,
		"data": map[string]any{
			"terminal_id": terminalID,
			"interpreter": interpreter,
			"working_dir": workingDir,
		},
	}
}

// readLoop 读取进程输出，写入环形缓冲并回传网关。
func (tm *TerminalManager) readLoop(s *terminalSession, sender func(msg map[string]any) error) {
	buf := make([]byte, 4096)
	for {
		n, err := s.stdout.Read(buf)
		if n > 0 {
			chunk := make([]byte, n)
			copy(chunk, buf[:n])
			s.appendOutput(chunk)
			tm.publishOutput(s, chunk)
		}
		if err != nil {
			return
		}
	}
}

// publishOutput 把一段输出以 node_terminal_output 消息回传网关。
func (tm *TerminalManager) publishOutput(s *terminalSession, chunk []byte) {
	seq := s.nextSequence()
	msg := map[string]any{
		"type": "node_terminal_output",
		"payload": map[string]any{
			"session_id": s.sessionID,
			"message": map[string]any{
				"type": "execution",
				"payload": map[string]any{
					"event_type":   "stdout",
					"data":         base64.StdEncoding.EncodeToString(chunk),
					"encoded":      true,
					"sequence":     seq,
					"execution_id": "terminal_" + s.terminalID,
				},
			},
		},
	}
	if tm.sender != nil {
		if err := tm.sender(msg); err != nil {
			log.Printf("[terminal] 回传输出失败 terminal_id=%s: %v", s.terminalID, err)
		}
	}
}

// close 关闭终端会话。
func (tm *TerminalManager) close(inner map[string]any) map[string]any {
	terminalID, _ := inner["terminal_id"].(string)
	tm.mu.Lock()
	s := tm.sessions[terminalID]
	delete(tm.sessions, terminalID)
	tm.mu.Unlock()
	if s != nil {
		s.close()
	}
	return map[string]any{"success": true}
}

// input 向终端写入输入。
func (tm *TerminalManager) input(inner map[string]any) map[string]any {
	terminalID, _ := inner["terminal_id"].(string)
	data, _ := inner["data"].(string)
	tm.mu.Lock()
	s := tm.sessions[terminalID]
	tm.mu.Unlock()
	if s == nil {
		return errResponse(termErrNotFound, "terminal not found")
	}
	if err := s.writeInput(data); err != nil {
		return errResponse(termErrInternalError, "write input failed: "+err.Error())
	}
	return map[string]any{"success": true}
}

// resize 调整终端尺寸（Windows 管道方案不支持，no-op）。
func (tm *TerminalManager) resize(inner map[string]any) map[string]any {
	terminalID, _ := inner["terminal_id"].(string)
	tm.mu.Lock()
	s := tm.sessions[terminalID]
	tm.mu.Unlock()
	if s == nil {
		return errResponse(termErrNotFound, "terminal not found")
	}
	return map[string]any{"success": true}
}

// attach 返回终端输出缓冲（base64 编码数组），供重连回放。
func (tm *TerminalManager) attach(inner map[string]any) map[string]any {
	terminalID, _ := inner["terminal_id"].(string)
	tm.mu.Lock()
	s := tm.sessions[terminalID]
	tm.mu.Unlock()
	if s == nil {
		return errResponse(termErrNotFound, "terminal not found")
	}
	output := s.outputBufferBase64()
	return map[string]any{
		"success": true,
		"data": map[string]any{
			"terminal_id": terminalID,
			"interpreter": s.interpreter,
			"working_dir": s.workingDir,
			"output":      output,
		},
	}
}

// appendOutput 把输出写入环形缓冲（约 1MB 上限）。
func (s *terminalSession) appendOutput(chunk []byte) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.buffer = append(s.buffer, chunk...)
	if len(s.buffer) > terminalOutputBufferLimit {
		excess := len(s.buffer) - terminalOutputBufferLimit
		s.buffer = s.buffer[excess:]
	}
}

// outputBufferBase64 返回缓冲中全部数据（按时间顺序）的 base64 编码数组。
//
// 返回 []any（而非 []string）是为了与 WS 层 JSON 反序列化后的类型一致
// （JSON 数组反序列化为 []any），使直接单元测试与端到端行为统一。
func (s *terminalSession) outputBufferBase64() []any {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]any, 0, 1)
	if len(s.buffer) == 0 {
		return out
	}
	out = append(out, base64.StdEncoding.EncodeToString(s.buffer))
	return out
}

// nextSequence 返回下一个输出序号。
func (s *terminalSession) nextSequence() int64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.sequence++
	return s.sequence
}

// writeInput 向进程 stdin 写入输入。
func (s *terminalSession) writeInput(data string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil
	}
	_, err := io.WriteString(s.stdin, data)
	return err
}

// close 关闭会话：关闭 stdin，终止子进程。
func (s *terminalSession) close() {
	s.mu.Lock()
	if s.closed {
		s.mu.Unlock()
		return
	}
	s.closed = true
	cmd := s.cmd
	stdin := s.stdin
	s.mu.Unlock()

	if stdin != nil {
		_ = stdin.Close()
	}
	if cmd != nil && cmd.Process != nil {
		_ = cmd.Process.Kill()
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

// newTerminalID 生成 8 位十六进制终端 ID（与 Gateway 的 uuid4()[:8] 等价）。
func newTerminalID() string {
	b := make([]byte, 4)
	if _, err := rand.Read(b); err != nil {
		now := time.Now().Unix()
		return hex.EncodeToString([]byte{byte(now), byte(now >> 8), byte(now >> 16), byte(now >> 24)})
	}
	return hex.EncodeToString(b)
}

// toInt 把任意值转为 int；非法时返回默认值。
func toInt(v any, def int) int {
	switch n := v.(type) {
	case int:
		return n
	case int64:
		return int(n)
	case float64:
		return int(n)
	case json.Number:
		if i, err := n.Int64(); err == nil {
			return int(i)
		}
	}
	return def
}
