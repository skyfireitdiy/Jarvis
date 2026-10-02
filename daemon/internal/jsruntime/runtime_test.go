package jsruntime

import (
	"strings"
	"testing"
)

// TestRunScriptBasic 验证基础 JS 表达式执行。
func TestRunScriptBasic(t *testing.T) {
	r := New()
	val, err := r.RunScript("1 + 1")
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != int64(2) {
		t.Fatalf("期望 2，得到 %v (%T)", val, val)
	}
}

// TestRunScriptString 验证字符串结果。
func TestRunScriptString(t *testing.T) {
	r := New()
	val, err := r.RunScript(`"hello " + "world"`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != "hello world" {
		t.Fatalf("期望 hello world，得到 %v", val)
	}
}

// TestRunScriptFunction 验证函数定义与调用。
func TestRunScriptFunction(t *testing.T) {
	r := New()
	val, err := r.RunScript(`(function(a, b) { return a * b; })(6, 7)`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != int64(42) {
		t.Fatalf("期望 42，得到 %v", val)
	}
}

// TestRunScriptObject 验证对象字面量返回。
func TestRunScriptObject(t *testing.T) {
	r := New()
	val, err := r.RunScript(`({name: "demo", count: 3})`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	obj, ok := val.(map[string]any)
	if !ok {
		t.Fatalf("期望 map[string]any，得到 %T", val)
	}
	if obj["name"] != "demo" || obj["count"] != int64(3) {
		t.Fatalf("对象内容不符: %v", obj)
	}
}

// TestRunScriptAsync 验证 async/await 与顶层 Promise 处理（microtask）。
func TestRunScriptAsync(t *testing.T) {
	r := New()
	src := `
		(async function() {
			const x = await Promise.resolve(10);
			return x * 2;
		})();
	`
	val, err := r.RunScript(src)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != int64(20) {
		t.Fatalf("期望 20，得到 %v", val)
	}
}

// TestRunScriptSyntaxError 验证语法错误被转成可读错误。
func TestRunScriptSyntaxError(t *testing.T) {
	r := New()
	_, err := r.RunScript("function ( {")
	if err == nil {
		t.Fatal("期望语法错误，但没有返回错误")
	}
	if !strings.Contains(err.Error(), "SyntaxError") {
		t.Fatalf("错误信息应含 SyntaxError，实际: %v", err)
	}
}

// TestRunScriptRuntimeError 验证运行时错误（未捕获异常）。
func TestRunScriptRuntimeError(t *testing.T) {
	r := New()
	_, err := r.RunScript(`throw new Error("boom")`)
	if err == nil {
		t.Fatal("期望运行时错误，但没有返回错误")
	}
	if !strings.Contains(err.Error(), "boom") {
		t.Fatalf("错误信息应含 boom，实际: %v", err)
	}
}

// TestRunScriptRejectedPromise 验证 Promise reject 被转成错误。
func TestRunScriptRejectedPromise(t *testing.T) {
	r := New()
	_, err := r.RunScript(`Promise.reject(new Error("rejected!"))`)
	if err == nil {
		t.Fatal("期望 Promise reject 错误，但没有返回错误")
	}
	if !strings.Contains(err.Error(), "rejected") {
		t.Fatalf("错误信息应含 rejected，实际: %v", err)
	}
}

// TestRunScriptFile 验证按文件名定位错误的编译。
func TestRunScriptFile(t *testing.T) {
	r := New()
	_, err := r.RunScriptFile("myscript.js", `var x = 1; x();`)
	if err == nil {
		t.Fatal("期望错误，但没有返回错误")
	}
	if !strings.Contains(err.Error(), "myscript.js") {
		t.Fatalf("错误信息应含文件名 myscript.js，实际: %v", err)
	}
}

// TestSet 验证 Set 注入全局变量。
func TestSet(t *testing.T) {
	r := New()
	if err := r.Set("greeting", "hi"); err != nil {
		t.Fatalf("Set 失败: %v", err)
	}
	val, err := r.RunScript(`greeting + " there"`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if val != "hi there" {
		t.Fatalf("期望 hi there，得到 %v", val)
	}
}

// TestPrintOutput 验证 print 输出到 stdout 回调。
func TestPrintOutput(t *testing.T) {
	r := New()
	var stdout, stderr strings.Builder
	r.SetOutput(func(s string) { stdout.WriteString(s) }, func(s string) { stderr.WriteString(s) })

	_, err := r.RunScript(`print("hello", "world")`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if stdout.String() != "hello world\n" {
		t.Fatalf("stdout 期望 'hello world\\n'，实际: %q", stdout.String())
	}
	if stderr.Len() != 0 {
		t.Fatalf("stderr 应为空，实际: %q", stderr.String())
	}
}

// TestConsoleOutput 验证 console.log/error 分别输出到 stdout/stderr。
func TestConsoleOutput(t *testing.T) {
	r := New()
	var stdout, stderr strings.Builder
	r.SetOutput(func(s string) { stdout.WriteString(s) }, func(s string) { stderr.WriteString(s) })

	_, err := r.RunScript(`
console.log("log", 42);
console.info("info");
console.error("boom");
console.warn("careful");
`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	if stdout.String() != "log 42\ninfo\n" {
		t.Fatalf("stdout 期望 'log 42\\ninfo\\n'，实际: %q", stdout.String())
	}
	if stderr.String() != "boom\ncareful\n" {
		t.Fatalf("stderr 期望 'boom\\ncareful\\n'，实际: %q", stderr.String())
	}
}

// TestConsoleObjectStringify 验证对象/数组在输出中的序列化。
func TestConsoleObjectStringify(t *testing.T) {
	r := New()
	var stdout strings.Builder
	r.SetOutput(func(s string) { stdout.WriteString(s) }, nil)

	_, err := r.RunScript(`
console.log({a: 1, b: "x"});
console.log([1, 2, 3]);
console.log(null, undefined);
`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
	want := `{"a":1,"b":"x"}
[1,2,3]
null null
`
	if stdout.String() != want {
		t.Fatalf("输出不符，期望:\n%q\n实际:\n%q", want, stdout.String())
	}
}

// TestPrintNilSink 验证未设置输出回调时 print 不 panic。
func TestPrintNilSink(t *testing.T) {
	r := New()
	_, err := r.RunScript(`print("no sink"); console.log("ok")`)
	if err != nil {
		t.Fatalf("执行失败: %v", err)
	}
}
