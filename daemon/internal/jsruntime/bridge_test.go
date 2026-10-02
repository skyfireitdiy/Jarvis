package jsruntime

import (
	"strings"
	"testing"

	"github.com/dop251/goja"

	"jarvis-daemon/internal/capability"
)

// newTestRegistry 创建一个注册了 fake 能力的注册表，用于桥接测试。
func newTestRegistry() *capability.Registry {
	reg := capability.NewRegistry()
	_ = reg.Register(capability.Capability{
		Name:        "demo.echo",
		Description: "回显参数",
		Platform:    capability.PlatformAny,
		Handler: func(params map[string]any) (any, error) {
			return params, nil
		},
	})
	_ = reg.Register(capability.Capability{
		Name:        "demo.add",
		Description: "两数相加",
		Platform:    capability.PlatformAny,
		Handler: func(params map[string]any) (any, error) {
			a, _ := params["a"].(int64)
			b, _ := params["b"].(int64)
			return a + b, nil
		},
	})
	_ = reg.Register(capability.Capability{
		Name:        "demo.fail",
		Description: "总是失败",
		Platform:    capability.PlatformAny,
		Handler: func(params map[string]any) (any, error) {
			return nil, errDemoFail
		},
	})
	_ = reg.Register(capability.Capability{
		Name:        "demo.nested.deep",
		Description: "嵌套能力",
		Platform:    capability.PlatformAny,
		Handler: func(params map[string]any) (any, error) {
			return "deep-result", nil
		},
	})
	return reg
}

var errDemoFail = &demoFailError{}

type demoFailError struct{}

func (e *demoFailError) Error() string { return "demo failed intentionally" }

// runWithBridge 创建运行时、注入桥接并执行脚本。
func runWithBridge(t *testing.T, reg *capability.Registry, src string) (any, error) {
	t.Helper()
	r := New()
	if err := InstallBridge(r, reg); err != nil {
		t.Fatalf("InstallBridge 失败: %v", err)
	}
	return r.RunScript(src)
}

// TestCapSuccess 验证 jarvis.cap 调用成功能力。
func TestCapSuccess(t *testing.T) {
	reg := newTestRegistry()
	val, err := runWithBridge(t, reg, `jarvis.cap("demo.add", {a: 3, b: 4})`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	obj, ok := val.(map[string]any)
	if !ok {
		t.Fatalf("期望 map，得到 %T", val)
	}
	if obj["success"] != true {
		t.Fatalf("期望 success=true，得到 %v", obj)
	}
	if obj["data"] != int64(7) {
		t.Fatalf("期望 data=7，得到 %v", obj)
	}
}

// TestCapUnknown 验证 jarvis.cap 调用未注册能力返回错误。
func TestCapUnknown(t *testing.T) {
	reg := newTestRegistry()
	val, err := runWithBridge(t, reg, `jarvis.cap("no.such.cap")`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	obj, ok := val.(map[string]any)
	if !ok {
		t.Fatalf("期望 map，得到 %T", val)
	}
	if obj["success"] != false {
		t.Fatalf("期望 success=false，得到 %v", obj)
	}
	if obj["error"] == "" {
		t.Fatal("期望 error 非空")
	}
}

// TestCapParams 验证参数传递（string/number/bool/嵌套对象）。
func TestCapParams(t *testing.T) {
	reg := newTestRegistry()
	val, err := runWithBridge(t, reg,
		`jarvis.cap("demo.echo", {s: "hi", n: 42, b: true, nested: {x: 1, y: "z"}})`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	obj := val.(map[string]any)
	data := obj["data"].(map[string]any)
	if data["s"] != "hi" || data["n"] != int64(42) || data["b"] != true {
		t.Fatalf("参数传递不符: %v", data)
	}
	nested, ok := data["nested"].(map[string]any)
	if !ok || nested["x"] != int64(1) || nested["y"] != "z" {
		t.Fatalf("嵌套参数不符: %v", data["nested"])
	}
}

// TestCapsNested 验证 jarvis.caps 嵌套命名空间调用。
func TestCapsNested(t *testing.T) {
	reg := newTestRegistry()
	val, err := runWithBridge(t, reg, `jarvis.caps.demo.add({a: 10, b: 32})`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != int64(42) {
		t.Fatalf("期望 42，得到 %v", val)
	}
}

// TestCapsDeep 验证 jarvis.caps 多级嵌套能力。
func TestCapsDeep(t *testing.T) {
	reg := newTestRegistry()
	val, err := runWithBridge(t, reg, `jarvis.caps.demo.nested.deep({})`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != "deep-result" {
		t.Fatalf("期望 deep-result，得到 %v", val)
	}
}

// TestCapsFailThrows 验证 jarvis.caps 调用失败抛 JS 异常。
func TestCapsFailThrows(t *testing.T) {
	reg := newTestRegistry()
	_, err := runWithBridge(t, reg, `jarvis.caps.demo.fail({})`)
	if err == nil {
		t.Fatal("期望能力失败抛异常，但没有返回错误")
	}
	if err.Error() == "" {
		t.Fatal("错误信息不应为空")
	}
}

// TestCapsFailCatchable 验证 jarvis.caps 失败可用 try/catch 捕获。
func TestCapsFailCatchable(t *testing.T) {
	reg := newTestRegistry()
	val, err := runWithBridge(t, reg, `
		try {
			jarvis.caps.demo.fail({});
			"no-throw";
		} catch (e) {
			"caught:" + e.message;
		}
	`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != "caught:能力 demo.fail 调用失败: demo failed intentionally" {
		t.Fatalf("期望捕获异常信息，得到 %v", val)
	}
}

// TestListCaps 验证 jarvis.listCaps 列出能力。
func TestListCaps(t *testing.T) {
	reg := newTestRegistry()
	val, err := runWithBridge(t, reg, `jarvis.listCaps().length`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	// 至少包含 demo.* 的 4 个能力。
	if val.(int64) < 4 {
		t.Fatalf("期望至少 4 个能力，得到 %v", val)
	}
}

// TestListCapsContains 验证 listCaps 返回能力名（包含 fake 能力）。
func TestListCapsContains(t *testing.T) {
	reg := newTestRegistry()
	val, err := runWithBridge(t, reg, `
		jarvis.listCaps().map(c => c.name).join(",")
	`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	names, ok := val.(string)
	if !ok {
		t.Fatalf("期望字符串，得到 %T", val)
	}
	for _, want := range []string{"demo.add", "demo.echo", "demo.fail", "demo.nested.deep"} {
		if !strings.Contains(names, want) {
			t.Fatalf("能力清单应包含 %s，实际: %s", want, names)
		}
	}
}

// TestSleep 验证 jarvis.sleep 不报错。
func TestSleep(t *testing.T) {
	reg := newTestRegistry()
	_, err := runWithBridge(t, reg, `jarvis.sleep(1); "done"`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
}

// TestBridgeNilRegistry 验证 registry 为 nil 时桥接可用但能力调用失败。
func TestBridgeNilRegistry(t *testing.T) {
	r := New()
	if err := InstallBridge(r, nil); err != nil {
		t.Fatalf("InstallBridge(nil) 失败: %v", err)
	}
	val, err := r.RunScript(`jarvis.cap("anything").success`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != false {
		t.Fatalf("期望 success=false，得到 %v", val)
	}
}

// TestGojaValueExport 验证 goja 值导出类型（辅助确认参数转换）。
func TestGojaValueExport(t *testing.T) {
	vm := goja.New()
	v, _ := vm.RunString(`({a: 1, b: "x"})`)
	m := v.Export().(map[string]any)
	if m["a"] != int64(1) || m["b"] != "x" {
		t.Fatalf("导出不符: %v", m)
	}
}

// TestInstallScriptArgs 验证 jarvis.args 注入脚本参数。
func TestInstallScriptArgs(t *testing.T) {
	r := New()
	reg := newTestRegistry()
	if err := InstallBridge(r, reg); err != nil {
		t.Fatalf("InstallBridge 失败: %v", err)
	}
	if err := InstallScriptArgs(r, map[string]string{"path": "/tmp", "mode": "fast"}); err != nil {
		t.Fatalf("InstallScriptArgs 失败: %v", err)
	}

	val, err := r.RunScript(`jarvis.args.path + ":" + jarvis.args.mode`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != "/tmp:fast" {
		t.Fatalf("期望 '/tmp:fast'，得到 %v", val)
	}
}

// TestInstallScriptArgsBeforeBridge 验证未调用 InstallBridge 时 InstallScriptArgs 报错。
func TestInstallScriptArgsBeforeBridge(t *testing.T) {
	r := New()
	if err := InstallScriptArgs(r, map[string]string{"a": "1"}); err == nil {
		t.Fatalf("期望报错（jarvis 对象不存在），实际无错误")
	}
}
