//go:build linux

package wsclient

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"log"
	"os"
	"os/exec"
	"sync"
	"time"

	"github.com/creack/pty"
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

// terminalSession 是一个 daemon 内部终端会话（Linux PTY 宿主）。
//
// 会话生命周期：断开不杀进程；关闭标签页仅 detach（不退出进程）；
// 输出写入环形缓冲供重连回放。与 Gateway 终端行为一致。
type terminalSession struct {
	terminalID  string
	interpreter string
	workingDir  string
	sessionID   string
	createdAt   int64

	ptmx *os.File // PTY master
	cmd  *exec.Cmd

	mu       sync.Mutex
	closed   bool
	sequence int64
	buffer   []byte // 输出环形缓冲（约 1MB）

	// exitOnce 保证进程退出处理只执行一次（Wait 监视器与 readLoop 可能同时
	// 感知到退出）。
	exitOnce sync.Once
}

// TerminalManager 是 daemon 内部终端会话管理器（不注册 capability）。
//
// 它只处理 node_terminal_request 消息，并把 PTY 输出经 sender 以
// node_terminal_output 消息回传网关。sender 由 wsclient.Client 注入
// （复用 writeJSON 写锁），使输出与其它消息共享同一条连接。
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
//
// 语义与子节点 node_manager.py:2553 对称：terminal_create / terminal_close /
// terminal_session_input / terminal_session_resize / terminal_attach。
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

// create 创建终端会话（Linux PTY）。
func (tm *TerminalManager) create(inner map[string]any, sessionID string) map[string]any {
	interpreter, _ := inner["interpreter"].(string)
	if interpreter == "" {
		interpreter = os.Getenv("SHELL")
	}
	if interpreter == "" {
		interpreter = "bash"
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

	// 默认 80x24 尺寸（与 Gateway 终端初始尺寸一致）。
	ptmx, err := pty.StartWithSize(cmd, &pty.Winsize{Rows: 24, Cols: 80})
	if err != nil {
		log.Printf("[terminal] create failed interpreter=%s working_dir=%s: %v", interpreter, workingDir, err)
		return errResponse(termErrCreateFailed, "failed to start terminal: "+err.Error())
	}

	s := &terminalSession{
		terminalID:  terminalID,
		interpreter: interpreter,
		workingDir:  workingDir,
		sessionID:   sessionID,
		createdAt:   time.Now().Unix(),
		ptmx:        ptmx,
		cmd:         cmd,
	}

	tm.mu.Lock()
	tm.sessions[terminalID] = s
	sender := tm.sender
	tm.mu.Unlock()

	// 启动 PTY 读循环：把输出写入环形缓冲并回传网关。
	go tm.readLoop(s, sender)
	// 进程退出监视器：子进程退出后关闭 PTY master 打断阻塞中的 Read，
	// 由 handleProcessExit 统一处理（exitOnce 保证只一次）。
	go tm.watchProcessExit(s, sender)

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

// readLoop 读取 PTY 输出，写入环形缓冲并回传网关。
func (tm *TerminalManager) readLoop(s *terminalSession, sender func(msg map[string]any) error) {
	buf := make([]byte, 4096)
	for {
		n, err := s.ptmx.Read(buf)
		if n > 0 {
			chunk := make([]byte, n)
			copy(chunk, buf[:n])
			s.appendOutput(chunk)
			tm.publishOutput(s, chunk)
		}
		if err != nil {
			tm.handleProcessExit(s, sender)
			return
		}
	}
}

// watchProcessExit 监视子进程退出。
//
// Linux 侧 Read 在子进程退出后通常能返回 EOF/EIO，但为避免个别情况
// （PTY 被其他进程持有写端等）导致读循环阻塞，这里用 cmd.Wait 兜底：
// 进程退出后关闭 PTY master 打断 Read，并直接触发退出处理（幂等）。
func (tm *TerminalManager) watchProcessExit(s *terminalSession, sender func(msg map[string]any) error) {
	if s.cmd == nil {
		return
	}
	err := s.cmd.Wait()
	code := 0
	if s.cmd.ProcessState != nil {
		code = s.cmd.ProcessState.ExitCode()
	}
	if err != nil {
		log.Printf("[terminal] wait process terminal_id=%s exit_code=%d: %v", s.terminalID, code, err)
	} else {
		log.Printf("[terminal] child process exited terminal_id=%s exit_code=%d", s.terminalID, code)
	}
	if s.ptmx != nil {
		_ = s.ptmx.Close()
	}
	tm.handleProcessExit(s, sender)
}

// handleProcessExit 处理终端进程退出：移除会话并通知网关。
//
// 读循环结束意味着 PTY 已关闭（进程退出或会话被 close）。若为进程自行退出
// （用户输入 exit），必须移除会话并回传 event_type=closed 事件，让网关/前端
// 销毁标签页；主动 close 的会话已从 map 移除且 s.closed=true，此处不再重复通知。
//
// 幂等：watchProcessExit 与 readLoop 可能同时触发，由 s.exitOnce 保证只执行一次。
func (tm *TerminalManager) handleProcessExit(s *terminalSession, sender func(msg map[string]any) error) {
	s.exitOnce.Do(func() {
		tm.doHandleProcessExit(s, sender)
	})
}

func (tm *TerminalManager) doHandleProcessExit(s *terminalSession, sender func(msg map[string]any) error) {
	tm.mu.Lock()
	cur, ok := tm.sessions[s.terminalID]
	removed := ok && cur == s
	if removed {
		delete(tm.sessions, s.terminalID)
	}
	tm.mu.Unlock()

	s.mu.Lock()
	alreadyClosed := s.closed
	s.closed = true
	s.mu.Unlock()

	if alreadyClosed || !removed {
		// 主动 close 触发的退出，网关侧已收到 terminal_closed，无需重复通知。
		return
	}

	log.Printf("[terminal] process exited terminal_id=%s", s.terminalID)

	if sender == nil {
		return
	}
	seq := s.nextSequence()
	msg := map[string]any{
		"type": "node_terminal_output",
		"payload": map[string]any{
			"session_id": s.sessionID,
			"message": map[string]any{
				"type": "execution",
				"payload": map[string]any{
					"event_type":   "closed",
					"data":         "",
					"encoded":      true,
					"sequence":     seq,
					"execution_id": "terminal_" + s.terminalID,
				},
			},
		},
	}
	if err := sender(msg); err != nil {
		log.Printf("[terminal] 回传退出事件失败 terminal_id=%s: %v", s.terminalID, err)
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

// resize 调整终端尺寸。
func (tm *TerminalManager) resize(inner map[string]any) map[string]any {
	terminalID, _ := inner["terminal_id"].(string)
	rows := toInt(inner["rows"], 24)
	cols := toInt(inner["cols"], 80)
	tm.mu.Lock()
	s := tm.sessions[terminalID]
	tm.mu.Unlock()
	if s == nil {
		return errResponse(termErrNotFound, "terminal not found")
	}
	if err := s.resize(rows, cols); err != nil {
		return errResponse(termErrInternalError, "resize failed: "+err.Error())
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
		// 丢弃最旧部分，保留最近约 1MB。
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

// writeInput 向 PTY 写入输入。
func (s *terminalSession) writeInput(data string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil
	}
	_, err := s.ptmx.WriteString(data)
	return err
}

// resize 调整 PTY 尺寸。
func (s *terminalSession) resize(rows, cols int) error {
	if rows <= 0 || cols <= 0 {
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil
	}
	return pty.Setsize(s.ptmx, &pty.Winsize{Rows: uint16(rows), Cols: uint16(cols)})
}

// close 关闭会话：关闭 PTY master，终止子进程。
func (s *terminalSession) close() {
	s.mu.Lock()
	if s.closed {
		s.mu.Unlock()
		return
	}
	s.closed = true
	ptmx := s.ptmx
	s.mu.Unlock()

	if ptmx != nil {
		_ = ptmx.Close()
	}
	// 关闭 PTY master 不会终止子进程，需显式 Kill，否则会话被关闭后
	// 子进程（bash 等）会成为孤儿继续运行。
	if s.cmd != nil && s.cmd.Process != nil {
		_ = s.cmd.Process.Kill()
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
		// 极低概率回退：用时间戳低位。
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
