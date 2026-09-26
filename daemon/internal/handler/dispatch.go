// Package handler 负责处理网关下发的指令。
//
// 指令的 action 即能力名，由 capability.Registry 执行；
// 未接入注册表时回退到占位实现（返回 not_implemented）。
package handler

import (
	"encoding/json"
	"fmt"

	"jarvis-daemon/internal/capability"
)

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
// 兼容入口：未接入能力注册表时一律返回 not_implemented。
func Dispatch(cmd Command) Result {
	return Result{
		ID:      cmd.ID,
		Type:    "result",
		Success: false,
		Error:   "not_implemented",
	}
}

// DispatchWith 用能力注册表处理一条指令并返回结果。
//
// 指令的 action 即能力名；params 会解析为 map 后传给能力处理函数。
// reg 为 nil 时返回明确错误，便于调用方发现配置缺失。
func DispatchWith(reg *capability.Registry, cmd Command) Result {
	if reg == nil {
		return Result{
			ID:      cmd.ID,
			Type:    "result",
			Success: false,
			Error:   "capability registry is nil",
		}
	}
	params, err := parseParams(cmd.Params)
	if err != nil {
		return Result{
			ID:      cmd.ID,
			Type:    "result",
			Success: false,
			Error:   fmt.Sprintf("params 解析失败: %v", err),
		}
	}
	res := reg.Execute(cmd.Action, params)
	return Result{
		ID:      cmd.ID,
		Type:    "result",
		Success: res.Success,
		Error:   res.Error,
		Data:    res.Data,
	}
}

// parseParams 把指令参数解析为 map；空参数返回 nil。
func parseParams(raw json.RawMessage) (map[string]any, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	var params map[string]any
	if err := json.Unmarshal(raw, &params); err != nil {
		return nil, err
	}
	return params, nil
}
