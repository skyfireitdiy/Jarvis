// Package handler 负责处理网关下发的指令。
//
// 本轮只打通链路，所有指令一律返回占位结果。
package handler

import "encoding/json"

// Command 是网关下发的指令。
type Command struct {
	ID        string          `json:"id"`
	Type      string          `json:"type"`
	Action    string          `json:"action"`
	Params    json.RawMessage `json:"params,omitempty"`
	TimeoutMS int             `json:"timeout_ms,omitempty"`
}

// Result 是回给网关的指令结果。
type Result struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	Success bool   `json:"success"`
	Error   string `json:"error,omitempty"`
	Data    any    `json:"data,omitempty"`
}

// Dispatch 处理一条指令并返回结果。
//
// 本轮为占位实现：一律返回 not_implemented。
func Dispatch(cmd Command) Result {
	return Result{
		ID:      cmd.ID,
		Type:    "result",
		Success: false,
		Error:   "not_implemented",
	}
}
