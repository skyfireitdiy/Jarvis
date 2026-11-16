//go:build windows

package wsclient

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/UserExistsError/conpty"
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

// terminalSession 是一个 daemon 内部终端会话（Windows ConPTY 方案）。
//
// creack/pty 在 Windows 上不支持（StartWithSize 返回 ErrUnsupported），
// 因此这里用 Windows ConPTY（Pseudo Console）API：通过
// github.com/UserExistsError/conpty 启动进程并挂到伪控制台，行为与
// Linux PTY 路径一致（交互模式 + VT 序列 + UTF-8 输出）。
//
// 相比旧的匿名管道方案，ConPTY 解决了两个问题：
//  1. 输入无反应：cmd.exe 检测到 stdin 非控制台时进入非交互模式
//     （不回显、不处理按键）；ConPTY 提供真正的伪控制台，进程进入
//     交互模式，Xterm 输入能正常驱动。
//  2. 中文乱码：cmd.exe 默认代码页 GBK（cp936），输出 GBK 字节流，
//     前端按 UTF-8 解码即乱码；ConPTY 输出天然为 UTF-8 + VT 序列，
//     且创建时执行 `chcp 65001` 把代码页切到 UTF-8，保证中文正确。
type terminalSession struct {
	terminalID  string
	interpreter string
	workingDir  string
	sessionID   string
	createdAt   int64

	cpty *conpty.ConPty

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

// create 创建终端会话（Windows ConPTY 方案）。
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

	// ConPTY 的 Start 接收完整命令行字符串（含参数）。interpreter 可能是
	// "cmd.exe" 或 "powershell.exe" 等，直接作为命令行传给 CreateProcess。
	//
	// 注意：conpty 库内部调用 CreateProcess 时 lpApplicationName 恒为 nil，
	// Windows 会把命令行**第一段**当作可执行文件去解析。因此命令行首段必须
	// 是真实存在的可执行文件路径，不能是 chcp 这类 cmd 内置命令——否则
	// CreateProcess 直接返回 ERROR_FILE_NOT_FOUND(2)
	// （历史 bug：曾拼成 "chcp 65001 >nul & cmd.exe"，导致终端永远创建失败）。
	commandLine := resolveInterpreterPath(interpreter)

	// 启动命令：先把代码页切到 UTF-8（65001），保证中文输出正确。
	// ConPTY 输出为 UTF-8 + VT 序列，但 cmd.exe 的默认代码页是 GBK（cp936），
	// 若不切换，`chcp` 之前的输出与部分内置命令仍可能按 GBK 编码。
	// 这里把 chcp 作为**参数**传给解释器（cmd.exe 用 /k，powershell 用 -NoExit），
	// 保证命令行首段仍是解释器本身。
	startupCmd := buildStartupCommand(commandLine, interpreter)

	env := append(os.Environ(), "TERM=xterm-256color")

	cpty, err := conpty.Start(startupCmd,
		conpty.ConPtyDimensions(80, 24),
		conpty.ConPtyWorkDir(workingDir),
		conpty.ConPtyEnv(env),
	)
	if err != nil {
		log.Printf("[terminal] create failed interpreter=%s working_dir=%s: %v", interpreter, workingDir, err)
		return errResponse(termErrCreateFailed, "failed to start terminal: "+err.Error())
	}

	// interpreter 回填为实际启动的可执行文件路径（可能是 LookPath 解析后的
	// 绝对路径），前端标签与后续会话恢复都依赖该字段。
	s := &terminalSession{
		terminalID:  terminalID,
		interpreter: commandLine,
		workingDir:  workingDir,
		sessionID:   sessionID,
		createdAt:   time.Now().Unix(),
		cpty:        cpty,
	}

	tm.mu.Lock()
	tm.sessions[terminalID] = s
	sender := tm.sender
	tm.mu.Unlock()

	go tm.readLoop(s, sender)

	log.Printf("[terminal] created terminal_id=%s interpreter=%s working_dir=%s session_id=%s",
		terminalID, commandLine, workingDir, sessionID)

	return map[string]any{
		"success": true,
		"data": map[string]any{
			"terminal_id": terminalID,
			"interpreter": commandLine,
			"working_dir": workingDir,
		},
	}
}

// readLoop 读取进程输出，写入环形缓冲并回传网关。
//
// 读循环结束意味着 ConPTY 已关闭（用户输入 exit 导致进程退出，或会话被
// close）。此时必须：
//  1. 从 tm.sessions 移除会话，避免继续接受 input/resize/attach；
//  2. 回传一条 event_type=closed 的事件，让网关/前端销毁标签页
//     （否则前端永远不知道进程已死，标签页残留且无法再输入）。
func (tm *TerminalManager) readLoop(s *terminalSession, sender func(msg map[string]any) error) {
	buf := make([]byte, 4096)
	for {
		n, err := s.cpty.Read(buf)
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

// handleProcessExit 处理终端进程退出：移除会话并通知网关。
func (tm *TerminalManager) handleProcessExit(s *terminalSession, sender func(msg map[string]any) error) {
	tm.mu.Lock()
	// 仅当 map 中仍是同一会话时移除（close 可能已先移除）。
	cur, ok := tm.sessions[s.terminalID]
	removed := ok && cur == s
	if removed {
		delete(tm.sessions, s.terminalID)
	}
	tm.mu.Unlock()

	// 标记会话已关闭，后续 writeInput/resize 直接返回。
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

// resize 调整终端尺寸（ConPTY 支持真实 resize）。
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

// writeInput 向进程 stdin 写入输入。
func (s *terminalSession) writeInput(data string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil
	}
	_, err := s.cpty.Write([]byte(data))
	return err
}

// resize 调整 ConPTY 尺寸。
func (s *terminalSession) resize(rows, cols int) error {
	if rows <= 0 || cols <= 0 {
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil
	}
	return s.cpty.Resize(cols, rows)
}

// close 关闭会话：关闭 ConPTY（终止子进程）。
func (s *terminalSession) close() {
	s.mu.Lock()
	if s.closed {
		s.mu.Unlock()
		return
	}
	s.closed = true
	cpty := s.cpty
	s.mu.Unlock()

	if cpty != nil {
		_ = cpty.Close()
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

// resolveInterpreterPath 把解释器名解析为绝对路径。
//
// conpty 库调用 CreateProcess 时 lpApplicationName 为 nil，只靠命令行首段
// 解析可执行文件。虽然系统会按 PATH 查找，但显式解析成绝对路径更稳妥：
// 避免 daemon 进程环境块异常（如 PATH 缺失/被裁剪）时解析失败。
// 解析失败时原样返回，交给 CreateProcess 自行处理（错误信息更贴近真实原因）。
func resolveInterpreterPath(interpreter string) string {
	if interpreter == "" {
		return interpreter
	}
	// 已含路径分隔符（绝对/相对路径）时不再解析。
	if strings.ContainsAny(interpreter, `\/`) {
		return interpreter
	}
	if p, err := exec.LookPath(interpreter); err == nil {
		return p
	}
	return interpreter
}

// buildStartupCommand 构造启动命令行：首段必须是解释器本身，chcp 作为参数。
//
// 不同解释器切换代码页的方式不同：
//   - cmd.exe：/k 保持交互并执行 chcp 65001
//   - powershell/pwsh：-NoExit 保持交互；代码页由 $OutputEncoding/控制台
//     UTF-8 决定，chcp 65001 同样有效，用 -Command 执行后保持会话
//   - 其他（bash 等）：直接原样启动，不做代码页切换
//
// 统一保证命令行**第一段**是解释器路径，避免 CreateProcess 把 chcp 当成
// 可执行文件而返回 ERROR_FILE_NOT_FOUND。
func buildStartupCommand(interpreterPath, interpreterName string) string {
	base := strings.ToLower(filepath.Base(interpreterName))
	if base == "" {
		base = strings.ToLower(filepath.Base(interpreterPath))
	}
	switch {
	case strings.HasPrefix(base, "cmd"):
		return interpreterPath + " /k chcp 65001 >nul"
	case strings.HasPrefix(base, "powershell"), strings.HasPrefix(base, "pwsh"):
		return interpreterPath + " -NoExit -Command chcp 65001 >$null"
	default:
		return interpreterPath
	}
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
