// Package jsruntime 提供基于 goja 的 JS 运行时封装，供 jarvis-daemon 执行
// 用户编写的 JS 自动化脚本。脚本内通过全局 jarvis 对象调用 capability 能力。
//
// goja 是纯 Go 实现的 ES5.1+ 引擎（零 cgo），与 daemon 现有"纯 syscall + 零 cgo"
// 的设计理念一致。本包只封装运行时本身与能力桥接，不依赖外部状态。
package jsruntime

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/dop251/goja"
)

// Runtime 封装一个 goja 运行时。
//
// 每个 Runtime 实例对应一个独立的 JS 虚拟机；脚本之间互不共享状态。
// 一个 Runtime 可执行多个脚本（共享全局对象），但通常一个 Runtime 只跑一个脚本。
type Runtime struct {
	vm *goja.Runtime

	// stdout/stderr 是脚本输出（print/console.log 等）的回调，nil 时输出被丢弃。
	// 调用方可通过 SetOutput 注入，把脚本输出回传到 CLI 或收集 buffer。
	stdout func(string)
	stderr func(string)
}

// New 创建并返回一个新的 JS 运行时。
//
// 默认注入 print / console.log 等输出函数，输出经 stdout/stderr 回调转发
// （默认丢弃，可用 SetOutput 设置）。同时注入 jarvis 占位对象（由 InstallBridge 填充）。
func New() *Runtime {
	vm := goja.New()
	r := &Runtime{vm: vm}
	r.installConsole()
	return r
}

// SetOutput 设置脚本输出（print/console.log 等）的回调。
//
// stdout 接收标准输出，stderr 接收错误/警告输出。传 nil 表示丢弃对应输出。
func (r *Runtime) SetOutput(stdout, stderr func(string)) {
	r.stdout = stdout
	r.stderr = stderr
}

// installConsole 注入 print / console.log 等全局输出函数。
//
// goja 核心不内置 console/print，这里按浏览器语义实现：多个参数以空格分隔，
// 统一写入 stdout（console.error/warn 写入 stderr）。
func (r *Runtime) installConsole() {
	vm := r.vm

	// 通用输出函数：把参数转字符串并 join。
	makePrinter := func(sink func(string)) func(call goja.FunctionCall) goja.Value {
		return func(call goja.FunctionCall) goja.Value {
			parts := make([]string, 0, len(call.Arguments))
			for _, a := range call.Arguments {
				parts = append(parts, stringify(a))
			}
			if sink != nil {
				sink(strings.Join(parts, " ") + "\n")
			}
			return goja.Undefined()
		}
	}

	// print(...) → stdout
	_ = vm.Set("print", vm.ToValue(makePrinter(func(s string) { r.writeStdout(s) })))

	// console.log/info/debug → stdout；console.warn/error → stderr
	console := vm.NewObject()
	_ = console.Set("log", vm.ToValue(makePrinter(func(s string) { r.writeStdout(s) })))
	_ = console.Set("info", vm.ToValue(makePrinter(func(s string) { r.writeStdout(s) })))
	_ = console.Set("debug", vm.ToValue(makePrinter(func(s string) { r.writeStdout(s) })))
	_ = console.Set("warn", vm.ToValue(makePrinter(func(s string) { r.writeStderr(s) })))
	_ = console.Set("error", vm.ToValue(makePrinter(func(s string) { r.writeStderr(s) })))
	_ = vm.Set("console", console)
}

// writeStdout / writeStderr 把一行输出转发到对应回调（nil 时丢弃）。
func (r *Runtime) writeStdout(s string) {
	if r.stdout != nil {
		r.stdout(s)
	}
}

func (r *Runtime) writeStderr(s string) {
	if r.stderr != nil {
		r.stderr(s)
	}
}

// stringify 把 goja 值转成字符串（用于 print/console 输出）。
//
// 对象/数组用 JSON 序列化（与浏览器 console 行为近似），null/undefined 输出字面量。
func stringify(v goja.Value) string {
	if v == nil {
		return "null"
	}
	exported := v.Export()
	switch t := exported.(type) {
	case nil:
		return "null"
	case string:
		return t
	case bool:
		if t {
			return "true"
		}
		return "false"
	case float64:
		// 整数去掉小数部分，与 JS 数字打印一致。
		if t == float64(int64(t)) {
			return fmt.Sprintf("%d", int64(t))
		}
		return fmt.Sprintf("%v", t)
	default:
		// 对象/数组等：尝试 JSON 序列化，失败则退回 String()。
		if b, err := json.Marshal(exported); err == nil {
			return string(b)
		}
		return v.String()
	}
}

// VM 返回底层 goja 运行时，供能力桥接等扩展使用。
func (r *Runtime) VM() *goja.Runtime {
	return r.vm
}

// Set 把 Go 值绑定到全局对象上的指定名字。
//
// 供注入 jarvis 对象、args 等全局量使用。
func (r *Runtime) Set(name string, value any) error {
	if err := r.vm.Set(name, value); err != nil {
		return fmt.Errorf("设置全局 %s 失败: %w", name, err)
	}
	return nil
}

// RunScript 执行一段 JS 源码并返回其完成值（Go 值）。
//
// 脚本顶层返回的 Promise 会被处理：Fulfilled 返回结果，Rejected 返回错误，
// Pending 返回错误提示（宏任务如 setTimeout 需要事件循环，首版不支持，
// 延迟请用 jarvis.sleep() 能力）。语法错误、运行错误以 *Error 形式返回。
func (r *Runtime) RunScript(source string) (any, error) {
	value, err := r.vm.RunString(source)
	if err != nil {
		return nil, wrapError(err)
	}
	return r.exportValue(value)
}

// RunScriptFile 读取文件内容并执行（等价于 RunScript，但按文件名定位错误）。
func (r *Runtime) RunScriptFile(name, source string) (any, error) {
	program, err := goja.Compile(name, source, false)
	if err != nil {
		return nil, wrapError(err)
	}
	value, err := r.vm.RunProgram(program)
	if err != nil {
		return nil, wrapError(err)
	}
	return r.exportValue(value)
}

// exportValue 把 goja 值转成 Go 值；若为 Promise 则按其终态处理。
func (r *Runtime) exportValue(value goja.Value) (any, error) {
	if p, ok := value.Export().(*goja.Promise); ok {
		switch p.State() {
		case goja.PromiseStateFulfilled:
			return p.Result().Export(), nil
		case goja.PromiseStateRejected:
			return nil, &Error{Message: fmt.Sprintf("Promise rejected: %s", p.Result().String())}
		default: // Pending
			return nil, &Error{Message: "脚本返回了未完成的 Promise（含 setTimeout 等宏任务）。" +
				"请改用 jarvis.sleep() 能力做延迟，或确保脚本在同步完成前 resolve。"}
		}
	}
	return value.Export(), nil
}

// wrapError 把 goja 抛出的错误转成带可读信息的 *Error。
//
// goja.Exception 携带 JS 侧堆栈（文件/行号），这里统一提取出来，便于 CLI 输出定位。
func wrapError(err error) error {
	if ex, ok := err.(*goja.Exception); ok {
		return &Error{
			Message: ex.String(),
			Stack:   formatStack(ex.Stack()),
		}
	}
	return &Error{Message: err.Error()}
}

// formatStack 把 goja 的堆栈帧列表转成可读的多行文本。
func formatStack(frames []goja.StackFrame) string {
	if len(frames) == 0 {
		return ""
	}
	var b strings.Builder
	for _, f := range frames {
		pos := f.Position()
		b.WriteString(fmt.Sprintf("  at %s (%s:%d:%d)\n", f.FuncName(), f.SrcName(), pos.Line, pos.Column))
	}
	return strings.TrimSuffix(b.String(), "\n")
}

// Error 是 JS 脚本执行错误的统一表示。
type Error struct {
	// Message 是可读的错误信息（含 JS 侧异常文本）。
	Message string
	// Stack 是 JS 侧堆栈信息（含文件/行号），可能为空。
	Stack string
}

func (e *Error) Error() string {
	if e.Stack != "" {
		return fmt.Sprintf("%s\n%s", e.Message, e.Stack)
	}
	return e.Message
}
