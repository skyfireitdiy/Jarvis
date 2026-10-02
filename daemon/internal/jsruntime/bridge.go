package jsruntime

import (
	"fmt"
	"strings"
	"time"

	"github.com/dop251/goja"

	"jarvis-daemon/internal/capability"
)

// InstallBridge 把 capability 能力暴露成全局 jarvis 对象并注入运行时。
//
// 注入的对象：
//   - jarvis.cap(name, params)：按能力名调用，返回 {success, data, error}
//   - jarvis.caps.<域>.<动作>(params)：嵌套命名空间，失败抛 JS 异常
//   - jarvis.listCaps()：列出当前平台可用能力
//   - jarvis.sleep(ms)：Go 侧阻塞延迟（替代 setTimeout 宏任务）
//
// registry 为 nil 时视为空注册表（脚本可运行但调用任何能力都会失败）。
func InstallBridge(r *Runtime, registry *capability.Registry) error {
	vm := r.vm
	if registry == nil {
		registry = capability.NewRegistry()
	}

	// 构建 jarvis 对象。
	jarvis := vm.NewObject()
	if err := vm.Set("jarvis", jarvis); err != nil {
		return fmt.Errorf("注入 jarvis 对象失败: %w", err)
	}

	// jarvis.cap(name, params)
	if err := jarvis.Set("cap", vm.ToValue(func(call goja.FunctionCall) goja.Value {
		name := call.Argument(0).String()
		params := toParams(call.Argument(1))
		res := registry.Execute(name, params)
		return vm.ToValue(map[string]any{
			"success": res.Success,
			"data":    res.Data,
			"error":   res.Error,
		})
	})); err != nil {
		return fmt.Errorf("注入 jarvis.cap 失败: %w", err)
	}

	// jarvis.listCaps()
	if err := jarvis.Set("listCaps", vm.ToValue(func(call goja.FunctionCall) goja.Value {
		caps := registry.ListForPlatform(capability.Current())
		out := make([]map[string]any, 0, len(caps))
		for _, c := range caps {
			out = append(out, map[string]any{
				"name":        c.Name,
				"description": c.Description,
				"parameters":  c.Parameters,
				"platform":    string(c.Platform),
			})
		}
		return vm.ToValue(out)
	})); err != nil {
		return fmt.Errorf("注入 jarvis.listCaps 失败: %w", err)
	}

	// jarvis.sleep(ms)
	if err := jarvis.Set("sleep", vm.ToValue(func(call goja.FunctionCall) goja.Value {
		ms := toInt64(call.Argument(0))
		if ms > 0 {
			time.Sleep(time.Duration(ms) * time.Millisecond)
		}
		return goja.Undefined()
	})); err != nil {
		return fmt.Errorf("注入 jarvis.sleep 失败: %w", err)
	}

	// jarvis.caps 嵌套命名空间。
	capsObj, err := buildCapsNamespace(vm, registry)
	if err != nil {
		return err
	}
	if err := jarvis.Set("caps", capsObj); err != nil {
		return fmt.Errorf("注入 jarvis.caps 失败: %w", err)
	}

	return nil
}

// buildCapsNamespace 遍历注册表，把能力名按 '.' 拆成嵌套对象，叶节点为可调用函数。
//
// 例如 linux.fs.read → jarvis.caps.linux.fs.read({path})。
// 叶节点调用失败时抛 JS 异常（可 try/catch）；成功返回 data。
func buildCapsNamespace(vm *goja.Runtime, registry *capability.Registry) (*goja.Object, error) {
	root := vm.NewObject()
	caps := registry.ListForPlatform(capability.Current())

	for _, c := range caps {
		parts := strings.Split(c.Name, ".")
		cur := root
		// 逐级创建嵌套对象，叶节点（最后一段）绑定调用函数。
		for i, part := range parts {
			if part == "" {
				continue
			}
			last := i == len(parts)-1
			if last {
				// 叶节点：绑定能力调用函数。
				name := c.Name
				if err := cur.Set(part, vm.ToValue(func(call goja.FunctionCall) goja.Value {
					return invokeCap(vm, registry, name, call)
				})); err != nil {
					return nil, fmt.Errorf("绑定能力 %s 失败: %w", name, err)
				}
			} else {
				// 中间节点：获取或创建子对象。
				child := cur.Get(part)
				if child == nil || goja.IsUndefined(child) || goja.IsNull(child) {
					child = vm.NewObject()
					if err := cur.Set(part, child); err != nil {
						return nil, fmt.Errorf("创建命名空间 %s 失败: %w", part, err)
					}
				}
				cur = child.ToObject(vm)
			}
		}
	}
	return root, nil
}

// invokeCap 执行一次能力调用（用于 jarvis.caps 叶节点）。
//
// 成功返回 data；失败抛 JS 异常（Error 携带能力错误信息）。
func invokeCap(vm *goja.Runtime, registry *capability.Registry, name string, call goja.FunctionCall) goja.Value {
	params := toParams(call.Argument(0))
	res := registry.Execute(name, params)
	if !res.Success {
		panic(vm.NewGoError(fmt.Errorf("能力 %s 调用失败: %s", name, res.Error)))
	}
	return vm.ToValue(res.Data)
}

// InstallScriptArgs 把脚本参数注入 jarvis.args 对象。
//
// 需在 InstallBridge 之后调用（依赖已创建的 jarvis 对象）。args 为 nil 时
// 注入空对象，脚本仍可安全访问 jarvis.args。
func InstallScriptArgs(r *Runtime, args map[string]string) error {
	vm := r.vm
	jarvisVal := vm.Get("jarvis")
	if jarvisVal == nil || goja.IsUndefined(jarvisVal) || goja.IsNull(jarvisVal) {
		return fmt.Errorf("jarvis 对象不存在，请先调用 InstallBridge")
	}
	jarvis := jarvisVal.ToObject(vm)
	argsObj := vm.NewObject()
	for k, v := range args {
		if err := argsObj.Set(k, v); err != nil {
			return fmt.Errorf("注入参数 %s 失败: %w", k, err)
		}
	}
	if err := jarvis.Set("args", argsObj); err != nil {
		return fmt.Errorf("注入 jarvis.args 失败: %w", err)
	}
	return nil
}

// toParams 把 goja 参数转成 map[string]any 能力参数。
//
// 参数为 undefined/null 时返回空 map；为对象时导出其属性；
// 为其它类型（非对象）时返回空 map（能力调用方自行处理缺失参数）。
func toParams(v goja.Value) map[string]any {
	if v == nil || goja.IsUndefined(v) || goja.IsNull(v) {
		return map[string]any{}
	}
	exported := v.Export()
	if m, ok := exported.(map[string]any); ok {
		return m
	}
	// 非对象参数（如字符串/数字）无法作为能力参数对象，返回空 map。
	return map[string]any{}
}

// toInt64 把 goja 值安全地转成 int64；非法值返回 0。
func toInt64(v goja.Value) int64 {
	if v == nil || goja.IsUndefined(v) || goja.IsNull(v) {
		return 0
	}
	return v.ToInteger()
}
