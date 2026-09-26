//go:build windows

package capability

import (
	"fmt"
	"os/exec"
	"strings"
)

// 本文件提供 Windows 侧能力共用的参数解析与外部命令辅助函数。
//
// 之所以不复用 linux_script_linux.go 中的同名函数：那些函数带 //go:build linux
// 标签，在 Windows 构建中不参与编译。两端函数签名保持一致，便于对照维护。

// requiredString 读取必填字符串参数。
func requiredString(params map[string]any, key string) (string, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return "", fmt.Errorf("缺少必填参数 %s", key)
	}
	s, ok := v.(string)
	if !ok {
		return "", fmt.Errorf("参数 %s 必须是字符串，实际 %T", key, v)
	}
	if strings.TrimSpace(s) == "" {
		return "", fmt.Errorf("参数 %s 不能为空", key)
	}
	return s, nil
}

// optionalString 读取可选字符串参数；缺失或为 nil 时返回空串。
func optionalString(params map[string]any, key string) (string, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return "", nil
	}
	s, ok := v.(string)
	if !ok {
		return "", fmt.Errorf("参数 %s 必须是字符串，实际 %T", key, v)
	}
	return s, nil
}

// optionalInt 读取可选整数参数；缺失或为 nil 时返回默认值。
//
// 兼容 JSON 解码后的 float64（网关传来的数字可能是 float64）。
func optionalInt(params map[string]any, key string, def int) (int, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return def, nil
	}
	switch n := v.(type) {
	case int:
		return n, nil
	case int64:
		return int(n), nil
	case float64:
		if n != float64(int(n)) {
			return 0, fmt.Errorf("参数 %s 必须是整数，实际 %v", key, n)
		}
		return int(n), nil
	default:
		return 0, fmt.Errorf("参数 %s 必须是整数，实际 %T", key, v)
	}
}

// requiredInt 读取必填整数参数。
//
// 与 optionalInt 的区别：本函数要求参数必须存在，用于「0 是合法值、不能用默认值
// 表示缺失」的场景（如鼠标坐标 x/y 允许为 0）。缺失或为 nil 时返回错误。
//
// 兼容 JSON 解码后的 float64（网关传来的数字可能是 float64）。
func requiredInt(params map[string]any, key string) (int, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return 0, fmt.Errorf("缺少必填参数 %s", key)
	}
	switch n := v.(type) {
	case int:
		return n, nil
	case int64:
		return int(n), nil
	case float64:
		if n != float64(int(n)) {
			return 0, fmt.Errorf("参数 %s 必须是整数，实际 %v", key, n)
		}
		return int(n), nil
	default:
		return 0, fmt.Errorf("参数 %s 必须是整数，实际 %T", key, v)
	}
}

// optionalBool 读取可选布尔参数；缺失或为 nil 时返回默认值。
func optionalBool(params map[string]any, key string, def bool) (bool, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return def, nil
	}
	b, ok := v.(bool)
	if !ok {
		return false, fmt.Errorf("参数 %s 必须是布尔值，实际 %T", key, v)
	}
	return b, nil
}

// optionalStringMap 读取可选字符串 map 参数。
func optionalStringMap(params map[string]any, key string) (map[string]string, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return nil, nil
	}
	switch m := v.(type) {
	case map[string]string:
		return m, nil
	case map[string]any:
		out := make(map[string]string, len(m))
		for k, raw := range m {
			s, ok := raw.(string)
			if !ok {
				return nil, fmt.Errorf("参数 %s.%s 必须是字符串，实际 %T", key, k, raw)
			}
			out[k] = s
		}
		return out, nil
	default:
		return nil, fmt.Errorf("参数 %s 必须是对象，实际 %T", key, v)
	}
}

// truncateOutput 按上限截断字节切片，返回字符串与是否发生截断。
func truncateOutput(b []byte, max int) (string, bool) {
	if len(b) <= max {
		return string(b), false
	}
	return string(b[:max]), true
}

// requireTool 探测外部命令是否可用（exec.LookPath），缺失时返回带安装提示的错误。
//
// Windows 侧能力尽量走系统自带命令（tasklist / taskkill / reg / wmic 等），
// 但仍统一走本函数探测，避免命令不存在时报出难以理解的 exec 错误。
func requireTool(name, hint string) (string, error) {
	path, err := exec.LookPath(name)
	if err != nil {
		if hint != "" {
			return "", fmt.Errorf("未找到命令 %s：%s", name, hint)
		}
		return "", fmt.Errorf("未找到命令 %s，请确认该命令在 PATH 中", name)
	}
	return path, nil
}
