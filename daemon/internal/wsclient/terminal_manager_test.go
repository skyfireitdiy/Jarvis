//go:build linux

package wsclient

import (
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

// 终端会话管理器测试（Linux PTY 路径）。
//
// 覆盖 NLSpec Interfaces 中 daemon 侧终端会话管理器的核心行为：
// create / input / resize / close / attach（输出缓冲回放）。
// 这些测试直接驱动 TerminalManager，不经过 WS 层。

// newTestTerminalManager 构造一个带发送器的终端管理器。
// sender 会把 daemon 回传的 node_terminal_output 消息收集到 out 通道。
func newTestTerminalManager(t *testing.T, out chan map[string]any) *TerminalManager {
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

// TestTerminalManagerCreate 验证 create 会话返回 terminal_id/interpreter/working_dir。
func TestTerminalManagerCreate(t *testing.T) {
	tm := newTestTerminalManager(t, nil)

	resp := tm.HandleRequest(map[string]any{
		"action": "terminal_create",
		"payload": map[string]any{
			"interpreter": "bash",
			"working_dir": "/tmp",
		},
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
	if data["interpreter"] != "bash" {
		t.Errorf("期望 interpreter=bash，实际 %v", data["interpreter"])
	}
	if data["working_dir"] != "/tmp" {
		t.Errorf("期望 working_dir=/tmp，实际 %v", data["working_dir"])
	}
}

// TestTerminalManagerCreateDefaults 验证 create 未传 interpreter/working_dir 时使用默认值。
func TestTerminalManagerCreateDefaults(t *testing.T) {
	tm := newTestTerminalManager(t, nil)

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

// TestTerminalManagerInput 验证向会话写入输入后回 success。
func TestTerminalManagerInput(t *testing.T) {
	tm := newTestTerminalManager(t, nil)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "bash", "working_dir": "/tmp"},
		"session_id": "session_test",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	resp := tm.HandleRequest(map[string]any{
		"action": "terminal_session_input",
		"payload": map[string]any{
			"terminal_id": terminalID,
			"data":        "echo hello\n",
		},
		"session_id": "session_test",
	})
	if resp["success"] != true {
		t.Fatalf("期望 input success=true，实际 %v（error=%v）", resp["success"], resp["error"])
	}
}

// TestTerminalManagerResize 验证 resize 会话后回 success。
func TestTerminalManagerResize(t *testing.T) {
	tm := newTestTerminalManager(t, nil)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "bash", "working_dir": "/tmp"},
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

// TestTerminalManagerAttach 验证 attach 返回 base64 编码的输出缓冲。
func TestTerminalManagerAttach(t *testing.T) {
	tm := newTestTerminalManager(t, nil)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "bash", "working_dir": "/tmp"},
		"session_id": "session_test",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	// 写入一些输入，产生输出缓冲
	tm.HandleRequest(map[string]any{
		"action": "terminal_session_input",
		"payload": map[string]any{
			"terminal_id": terminalID,
			"data":        "echo attach_probe\n",
		},
		"session_id": "session_test",
	})

	// 等待输出进入缓冲
	deadline := time.Now().Add(3 * time.Second)
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
			// 解码并检查是否包含 probe 输出
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

// TestTerminalManagerClose 验证 close 会话后回 success，且后续操作返回 NOT_FOUND。
func TestTerminalManagerClose(t *testing.T) {
	tm := newTestTerminalManager(t, nil)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "bash", "working_dir": "/tmp"},
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

// TestTerminalManagerUnknownAction 验证未知 action 返回 UNKNOWN_ACTION。
func TestTerminalManagerUnknownAction(t *testing.T) {
	tm := newTestTerminalManager(t, nil)

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

// TestTerminalManagerOutputStream 验证 PTY 输出经 sender 以 node_terminal_output 回传。
func TestTerminalManagerOutputStream(t *testing.T) {
	out := make(chan map[string]any, 16)
	tm := newTestTerminalManager(t, out)

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "bash", "working_dir": "/tmp"},
		"session_id": "session_test",
	})
	terminalID := createResp["data"].(map[string]any)["terminal_id"].(string)

	// 触发输出
	tm.HandleRequest(map[string]any{
		"action": "terminal_session_input",
		"payload": map[string]any{
			"terminal_id": terminalID,
			"data":        "echo stream_probe\n",
		},
		"session_id": "session_test",
	})

	// 等待 node_terminal_output 消息
	deadline := time.Now().Add(3 * time.Second)
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
			t.Fatal("未在 3 秒内收到包含 stream_probe 的 node_terminal_output")
		}
	}
}

// TestTerminalManagerCloseAll 验证 CloseAll 关闭全部会话。
func TestTerminalManagerCloseAll(t *testing.T) {
	tm := NewTerminalManager()
	tm.SetSender(func(msg map[string]any) error { return nil })

	createResp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "bash", "working_dir": "/tmp"},
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
func TestTerminalManagerResponseSerializable(t *testing.T) {
	tm := newTestTerminalManager(t, nil)

	resp := tm.HandleRequest(map[string]any{
		"action":     "terminal_create",
		"payload":    map[string]any{"interpreter": "bash", "working_dir": "/tmp"},
		"session_id": "session_test",
	})
	if _, err := json.Marshal(resp); err != nil {
		t.Fatalf("响应不可序列化: %v", err)
	}
}
