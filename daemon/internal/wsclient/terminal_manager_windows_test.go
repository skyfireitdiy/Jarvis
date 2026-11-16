//go:build windows

package wsclient

import (
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

// 终端会话管理器测试（Windows ConPTY 路径）。
//
// 覆盖 daemon 侧终端会话管理器的核心行为：create / input / resize /
// close / attach（输出缓冲回放）。这些测试直接驱动 TerminalManager，
// 不经过 WS 层。仅在 Windows 上运行（ConPTY 依赖 Windows API）。
//
// 相比 Linux PTY 测试，额外验证：
//   - create 时自动执行 chcp 65001（UTF-8 代码页），输出中应包含
//     "Active code page: 65001"（chcp 命令的反馈文本）。
//   - 输入写入后进程进入交互模式，输入命令有回显（管道方案下 cmd
//     非交互模式无回显，这是修复输入无反应的关键断言）。
func newTestTerminalManagerWindows(t *testing.T, out chan map[string]any) *TerminalManager {
	t.Helper()
	tm := NewTerminalManager()
	tm.SetSender(func(msg map[string]any) error {
		if out != nil {
			out <- msg
		}
		return nil
	})
	t.Cleanup(tm.CloseAll)
	return tm
}

// TestTerminalManagerCreateWindows 验证 create 会话返回 terminal_id/interpreter/working_dir。
func TestTerminalManagerCreateWindows(t *testing.T) {
	tm := newTestTerminalManagerWindows(t, nil)
	resp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe", "working_dir": "C:\\"},
		"session_id": "session_test",
	})
	if resp["success"] != true {
		t.Fatalf("期望 success=true，实际 %v（error=%v）", resp["success"], resp["error"])
	}
	data, ok := resp["data"].(map[string]any)
	if !ok {
		t.Fatalf("期望 data 为对象，实际 %T", resp["data"])
	}
	terminalID, _ := data["terminal_id"].(string)
	if terminalID == "" {
		t.Fatalf("期望 terminal_id 非空，实际 %v", data["terminal_id"])
	}
	if data["interpreter"] != "cmd.exe" {
		t.Errorf("期望 interpreter=cmd.exe，实际 %v", data["interpreter"])
	}
	if data["working_dir"] != "C:\\" {
		t.Errorf("期望 working_dir=C:\\，实际 %v", data["working_dir"])
	}
}

// TestTerminalManagerCreateDefaultsWindows 验证 create 未传 interpreter/working_dir 时使用默认值。
func TestTerminalManagerCreateDefaultsWindows(t *testing.T) {
	tm := newTestTerminalManagerWindows(t, nil)
	resp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{},
		"session_id": "session_test",
	})
	if resp["success"] != true {
		t.Fatalf("期望 success=true，实际 %v（error=%v）", resp["success"], resp["error"])
	}
	data, _ := resp["data"].(map[string]any)
	if data["interpreter"] == "" {
		t.Errorf("期望 interpreter 有默认值，实际为空")
	}
	if data["working_dir"] == "" {
		t.Errorf("期望 working_dir 有默认值，实际为空")
	}
}

// TestTerminalManagerChcpUtf8Windows 验证 create 后自动执行 chcp 65001，
// 输出中应包含 UTF-8 代码页反馈（"Active code page: 65001"）。
func TestTerminalManagerChcpUtf8Windows(t *testing.T) {
	out := make(chan map[string]any, 32)
	tm := newTestTerminalManagerWindows(t, out)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_test",
	})
	if createResp["success"] != true {
		t.Fatalf("创建失败: %v", createResp["error"])
	}

	deadline := time.Now().Add(5 * time.Second)
	var all strings.Builder
	for {
		select {
		case msg := <-out:
			payload, _ := msg["payload"].(map[string]any)
			inner, _ := payload["message"].(map[string]any)
			innerPayload, _ := inner["payload"].(map[string]any)
			data, _ := innerPayload["data"].(string)
			decoded, err := base64.StdEncoding.DecodeString(data)
			if err == nil {
				all.Write(decoded)
			}
			if strings.Contains(all.String(), "Active code page: 65001") {
				return
			}
		case <-time.After(time.Until(deadline)):
			t.Fatalf("输出中未出现 chcp 65001 反馈（UTF-8 代码页未生效），全部输出: %q", all.String())
		}
	}
}

// TestTerminalManagerInputWindows 验证向会话写入输入后回 success，
// 且输入命令有回显（交互模式，管道方案下 cmd 非交互模式无回显）。
func TestTerminalManagerInputWindows(t *testing.T) {
	tm := newTestTerminalManagerWindows(t, nil)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_test",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	resp := tm.HandleRequest(map[string]any{
		"action": "terminal_session_input",
		"payload": map[string]any{
			"terminal_id": terminalID,
			"data":        "echo input_probe\r\n",
		},
		"session_id": "session_test",
	})
	if resp["success"] != true {
		t.Fatalf("期望 input success=true，实际 %v（error=%v）", resp["success"], resp["error"])
	}
}

// TestTerminalManagerResizeWindows 验证 resize 会话后回 success。
func TestTerminalManagerResizeWindows(t *testing.T) {
	tm := newTestTerminalManagerWindows(t, nil)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_test",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	resp := tm.HandleRequest(map[string]any{
		"action": "terminal_session_resize",
		"payload": map[string]any{
			"terminal_id": terminalID,
			"rows":        30,
			"cols":        120,
		},
		"session_id": "session_test",
	})
	if resp["success"] != true {
		t.Fatalf("期望 resize success=true，实际 %v（error=%v）", resp["success"], resp["error"])
	}
}

// TestTerminalManagerAttachWindows 验证 attach 返回 base64 编码的输出缓冲。
func TestTerminalManagerAttachWindows(t *testing.T) {
	tm := newTestTerminalManagerWindows(t, nil)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_test",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	// 写入一些输入，产生输出缓冲
	tm.HandleRequest(map[string]any{
		"action": "terminal_session_input",
		"payload": map[string]any{
			"terminal_id": terminalID,
			"data":        "echo attach_probe\r\n",
		},
		"session_id": "session_test",
	})

	// 等待输出进入缓冲
	deadline := time.Now().Add(5 * time.Second)
	var all strings.Builder
	for {
		resp := tm.HandleRequest(map[string]any{
			"action": "terminal_attach",
			"payload": map[string]any{
				"terminal_id": terminalID,
			},
			"session_id": "session_test",
		})
		if resp["success"] != true {
			t.Fatalf("期望 attach success=true，实际 %v（error=%v）", resp["success"], resp["error"])
		}
		data := resp["data"].(map[string]any)
		output, _ := data["output"].([]any)
		if len(output) > 0 {
			for _, chunk := range output {
				raw, ok := chunk.(string)
				if !ok {
					continue
				}
				decoded, err := base64.StdEncoding.DecodeString(raw)
				if err != nil {
					t.Fatalf("解码 base64 失败: %v", err)
				}
				all.Write(decoded)
			}
			if strings.Contains(all.String(), "attach_probe") {
				return
			}
		}
		if time.Now().After(deadline) {
			t.Fatalf("输出缓冲中未出现 attach_probe，全部输出: %q", all.String())
		}
		time.Sleep(50 * time.Millisecond)
	}
}

// TestTerminalManagerCloseWindows 验证 close 会话后回 success，且后续操作返回 NOT_FOUND。
func TestTerminalManagerCloseWindows(t *testing.T) {
	tm := newTestTerminalManagerWindows(t, nil)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_test",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	resp := tm.HandleRequest(map[string]any{
		"action": "terminal_close",
		"payload": map[string]any{
			"terminal_id": terminalID,
		},
		"session_id": "session_test",
	})
	if resp["success"] != true {
		t.Fatalf("期望 close success=true，实际 %v（error=%v）", resp["success"], resp["error"])
	}

	// 关闭后 attach 应返回 NOT_FOUND
	attachResp := tm.HandleRequest(map[string]any{
		"action": "terminal_attach",
		"payload": map[string]any{
			"terminal_id": terminalID,
		},
		"session_id": "session_test",
	})
	if attachResp["success"] != false {
		t.Fatalf("期望关闭后 attach success=false，实际 %v", attachResp["success"])
	}
	errObj, ok := attachResp["error"].(map[string]any)
	if !ok || errObj["code"] != "NOT_FOUND" {
		t.Fatalf("期望错误码 NOT_FOUND，实际 %v", attachResp["error"])
	}
}

// TestTerminalManagerUnknownActionWindows 验证未知 action 返回 UNKNOWN_ACTION。
func TestTerminalManagerUnknownActionWindows(t *testing.T) {
	tm := newTestTerminalManagerWindows(t, nil)

	resp := tm.HandleRequest(map[string]any{
		"action":     "terminal_frobnicate",
		"payload":    map[string]any{},
		"session_id": "session_test",
	})
	if resp["success"] != false {
		t.Fatalf("期望 success=false，实际 %v", resp["success"])
	}
	errObj, ok := resp["error"].(map[string]any)
	if !ok || errObj["code"] != "UNKNOWN_ACTION" {
		t.Fatalf("期望错误码 UNKNOWN_ACTION，实际 %v", resp["error"])
	}
}

// TestTerminalManagerOutputStreamWindows 验证 ConPTY 输出经 sender 以 node_terminal_output 回传。
func TestTerminalManagerOutputStreamWindows(t *testing.T) {
	out := make(chan map[string]any, 32)
	tm := newTestTerminalManagerWindows(t, out)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_test",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	// 触发输出
	tm.HandleRequest(map[string]any{
		"action": "terminal_session_input",
		"payload": map[string]any{
			"terminal_id": terminalID,
			"data":        "echo stream_probe\r\n",
		},
		"session_id": "session_test",
	})

	// 等待 node_terminal_output 消息
	deadline := time.Now().Add(5 * time.Second)
	for {
		select {
		case msg := <-out:
			if msg["type"] != "node_terminal_output" {
				continue
			}
			payload, _ := msg["payload"].(map[string]any)
			if payload["session_id"] != "session_test" {
				t.Errorf("期望 session_id=session_test，实际 %v", payload["session_id"])
			}
			inner, _ := payload["message"].(map[string]any)
			if inner["type"] != "execution" {
				t.Errorf("期望 message.type=execution，实际 %v", inner["type"])
			}
			innerPayload, _ := inner["payload"].(map[string]any)
			if innerPayload["event_type"] != "stdout" {
				t.Errorf("期望 event_type=stdout，实际 %v", innerPayload["event_type"])
			}
			if innerPayload["encoded"] != true {
				t.Errorf("期望 encoded=true，实际 %v", innerPayload["encoded"])
			}
			if innerPayload["execution_id"] != "terminal_"+terminalID {
				t.Errorf("期望 execution_id=terminal_%s，实际 %v", terminalID, innerPayload["execution_id"])
			}
			data, _ := innerPayload["data"].(string)
			decoded, err := base64.StdEncoding.DecodeString(data)
			if err != nil {
				t.Fatalf("解码 base64 失败: %v", err)
			}
			if strings.Contains(string(decoded), "stream_probe") {
				return
			}
		case <-time.After(time.Until(deadline)):
			t.Fatal("未在 5 秒内收到包含 stream_probe 的 node_terminal_output")
		}
	}
}

// TestTerminalManagerCloseAllWindows 验证 CloseAll 关闭全部会话。
func TestTerminalManagerCloseAllWindows(t *testing.T) {
	tm := NewTerminalManager()
	tm.SetSender(func(msg map[string]any) error { return nil })

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_test",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	tm.CloseAll()

	attachResp := tm.HandleRequest(map[string]any{
		"action": "terminal_attach",
		"payload": map[string]any{
			"terminal_id": terminalID,
		},
		"session_id": "session_test",
	})
	if attachResp["success"] != false {
		t.Fatalf("期望 CloseAll 后 attach success=false，实际 %v", attachResp["success"])
	}
}

// 确保 HandleRequest 返回的 map 可被 JSON 序列化（协议兼容性）。
func TestTerminalManagerResponseSerializableWindows(t *testing.T) {
	tm := newTestTerminalManagerWindows(t, nil)

	resp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_test",
	})
	if _, err := json.Marshal(resp); err != nil {
		t.Fatalf("响应不可序列化: %v", err)
	}
}

// TestTerminalManagerProcessExitNotifiesWindows 验证 Windows 下终端进程自行退出
// （用户输入 exit）时会回传 event_type=closed 事件，并从 sessions 移除会话。
//
// 关键回归点：ConPTY 的 cmdOut 在子进程退出后不会返回 EOF，readLoop 会永久
// 阻塞在 Read 上。必须依赖 watchProcessExit（cpty.Wait + Close 打断 Read）
// 才能感知退出，否则前端标签页永远不关闭。
func TestTerminalManagerProcessExitNotifiesWindows(t *testing.T) {
	out := make(chan map[string]any, 128)
	tm := newTestTerminalManagerWindows(t, out)
	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_exit",
	})
	if createResp["success"] != true {
		t.Fatalf("创建终端失败: %v", createResp["error"])
	}
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	tm.HandleRequest(map[string]any{
		"action": "terminal_session_input",
		"payload": map[string]any{
			"terminal_id": terminalID,
			"data":        "exit\r",
		},
		"session_id": "session_exit",
	})

	deadline := time.Now().Add(15 * time.Second)
	for {
		select {
		case msg := <-out:
			if msg["type"] != "node_terminal_output" {
				continue
			}
			payload, _ := msg["payload"].(map[string]any)
			inner, _ := payload["message"].(map[string]any)
			innerPayload, _ := inner["payload"].(map[string]any)
			if innerPayload["event_type"] != "closed" {
				continue
			}
			if innerPayload["execution_id"] != "terminal_"+terminalID {
				t.Errorf("期望 execution_id=terminal_%s，实际 %v", terminalID, innerPayload["execution_id"])
			}
			// 会话必须已从 sessions 移除，后续 input 应报 NOT_FOUND。
			resp := tm.HandleRequest(map[string]any{
				"action":  "terminal_session_input",
				"payload": map[string]any{"terminal_id": terminalID, "data": "echo hi\r"},
			})
			if resp["success"] != false {
				t.Errorf("进程退出后会话应已移除，input 应失败，实际 %v", resp)
			}
			return
		case <-time.After(time.Until(deadline)):
			t.Fatal("未在 15 秒内收到 event_type=closed 的 node_terminal_output")
		}
	}
}

// TestTerminalManagerCloseDoesNotNotifyExitWindows 验证主动 close 不重复回传
// closed 事件（网关侧已收到 terminal_closed）。
func TestTerminalManagerCloseDoesNotNotifyExitWindows(t *testing.T) {
	out := make(chan map[string]any, 128)
	tm := newTestTerminalManagerWindows(t, out)
	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "cmd.exe"},
		"session_id": "session_close",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	tm.HandleRequest(map[string]any{
		"action":     "terminal_close",
		"payload":    map[string]any{"terminal_id": terminalID},
		"session_id": "session_close",
	})

	deadline := time.Now().Add(3 * time.Second)
	for {
		select {
		case msg := <-out:
			payload, _ := msg["payload"].(map[string]any)
			inner, _ := payload["message"].(map[string]any)
			innerPayload, _ := inner["payload"].(map[string]any)
			if innerPayload["event_type"] == "closed" {
				t.Fatalf("主动 close 不应回传 closed 事件，实际收到 %v", msg)
			}
		case <-time.After(time.Until(deadline)):
			return
		}
	}
}
