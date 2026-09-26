package capability

import (
	"errors"
	"testing"
)

// TestRegister 覆盖注册的成功、空名与重复注册三种情况。
func TestRegister(t *testing.T) {
	r := NewRegistry()

	if err := r.Register(Capability{Name: "demo.echo", Description: "回显"}); err != nil {
		t.Fatalf("注册失败: %v", err)
	}
	if err := r.Register(Capability{Name: ""}); err == nil {
		t.Fatal("空名称应当报错")
	}
	if err := r.Register(Capability{Name: "demo.echo"}); err == nil {
		t.Fatal("重复注册应当报错")
	}

	// 平台为空时默认 PlatformAny。
	c, ok := r.Get("demo.echo")
	if !ok {
		t.Fatal("应当能查到 demo.echo")
	}
	if c.Platform != PlatformAny {
		t.Fatalf("平台默认值应为 any，实际 %q", c.Platform)
	}
}

// TestGet 覆盖命中与未命中。
func TestGet(t *testing.T) {
	r := NewRegistry()
	_ = r.Register(Capability{Name: "a.one"})

	if _, ok := r.Get("a.one"); !ok {
		t.Fatal("应当命中 a.one")
	}
	if _, ok := r.Get("a.none"); ok {
		t.Fatal("不应当命中 a.none")
	}
}

// TestListSorted 验证 List 按名称升序返回副本。
func TestListSorted(t *testing.T) {
	r := NewRegistry()
	for _, n := range []string{"c", "a", "b"} {
		if err := r.Register(Capability{Name: n}); err != nil {
			t.Fatalf("注册 %s 失败: %v", n, err)
		}
	}

	// NewRegistry 会装配平台能力，这里只校验本次注册的三项相对顺序。
	list := r.List()
	got := make([]string, 0, 3)
	for _, c := range list {
		if c.Name == "a" || c.Name == "b" || c.Name == "c" {
			got = append(got, c.Name)
		}
	}
	if len(got) != 3 {
		t.Fatalf("期望 3 项，实际 %d", len(got))
	}
	want := []string{"a", "b", "c"}
	for i, name := range got {
		if name != want[i] {
			t.Fatalf("第 %d 项应为 %s，实际 %s", i, want[i], name)
		}
	}

	// 返回的应当是副本，修改不影响注册表。
	list[0].Name = "mutated"
	if _, ok := r.Get("a"); !ok {
		t.Fatal("List 返回的应当是副本")
	}
}

// TestListForPlatform 验证平台过滤：PlatformAny 与平台专属都出现，其他平台被过滤。
func TestListForPlatform(t *testing.T) {
	r := NewRegistry()
	_ = r.Register(Capability{Name: "any.cap", Platform: PlatformAny})
	_ = r.Register(Capability{Name: "linux.cap", Platform: PlatformLinux})
	_ = r.Register(Capability{Name: "windows.cap", Platform: PlatformWindows})

	linux := r.ListForPlatform(PlatformLinux)
	// NewRegistry 会装配平台能力，这里只校验本次注册的三项。
	gotLinux := namesOf(linux)
	if !containsAll(gotLinux, "any.cap", "linux.cap") {
		t.Fatalf("Linux 平台应包含 any.cap 与 linux.cap，实际 %v", gotLinux)
	}
	if contains(gotLinux, "windows.cap") {
		t.Fatalf("Linux 平台不应当出现 windows.cap，实际 %v", gotLinux)
	}

	windows := r.ListForPlatform(PlatformWindows)
	gotWindows := namesOf(windows)
	if !containsAll(gotWindows, "any.cap", "windows.cap") {
		t.Fatalf("Windows 平台应包含 any.cap 与 windows.cap，实际 %v", gotWindows)
	}
	for _, c := range windows {
		if c.Name == "linux.cap" {
			t.Fatal("Windows 平台不应当出现 linux.cap")
		}
	}
}

// namesOf 提取能力名称列表，便于断言。
func namesOf(caps []Capability) []string {
	out := make([]string, 0, len(caps))
	for _, c := range caps {
		out = append(out, c.Name)
	}
	return out
}

// contains 判断名称列表是否包含指定名称。
func contains(names []string, target string) bool {
	for _, n := range names {
		if n == target {
			return true
		}
	}
	return false
}

// containsAll 判断名称列表是否包含全部指定名称。
func containsAll(names []string, targets ...string) bool {
	for _, t := range targets {
		if !contains(names, t) {
			return false
		}
	}
	return true
}

// TestExecute 覆盖成功、未注册、Handler 返回错误、Handler panic 四种情况。
func TestExecute(t *testing.T) {
	r := NewRegistry()
	_ = r.Register(Capability{
		Name: "demo.echo",
		Handler: func(params map[string]any) (any, error) {
			return params["text"], nil
		},
	})
	_ = r.Register(Capability{
		Name: "demo.fail",
		Handler: func(map[string]any) (any, error) {
			return nil, errors.New("boom")
		},
	})
	_ = r.Register(Capability{
		Name: "demo.panic",
		Handler: func(map[string]any) (any, error) {
			panic("kaboom")
		},
	})
	_ = r.Register(Capability{Name: "demo.nil"})

	// 成功
	res := r.Execute("demo.echo", map[string]any{"text": "hi"})
	if !res.Success || res.Data != "hi" {
		t.Fatalf("期望成功且返回 hi，实际 %+v", res)
	}

	// 未注册
	res = r.Execute("demo.missing", nil)
	if res.Success || res.Error != "unknown capability: demo.missing" {
		t.Fatalf("未注册能力应返回明确错误，实际 %+v", res)
	}

	// Handler 返回错误
	res = r.Execute("demo.fail", nil)
	if res.Success || res.Error != "boom" {
		t.Fatalf("期望透传 handler 错误，实际 %+v", res)
	}

	// Handler panic 被 recover
	res = r.Execute("demo.panic", nil)
	if res.Success || res.Error == "" {
		t.Fatalf("panic 应被捕获并转为错误，实际 %+v", res)
	}

	// Handler 为 nil
	res = r.Execute("demo.nil", nil)
	if res.Success || res.Error == "" {
		t.Fatalf("nil handler 应返回明确错误，实际 %+v", res)
	}
}

// TestPlatformHelpers 验证 Current 与 Matches。
func TestPlatformHelpers(t *testing.T) {
	if Current() == "" {
		t.Fatal("Current 不应为空")
	}
	if !Matches(PlatformAny, PlatformLinux) {
		t.Fatal("any 应匹配任意平台")
	}
	if !Matches(PlatformLinux, PlatformLinux) {
		t.Fatal("同平台应匹配")
	}
	if Matches(PlatformWindows, PlatformLinux) {
		t.Fatal("不同平台不应匹配")
	}
}

// TestMultiRegistryIsolation 验证多个注册表实例互不影响（对应多后台服务连接同一网关的场景：
// 每个守护进程各自持有一份注册表，不存在全局共享状态）。
func TestMultiRegistryIsolation(t *testing.T) {
	r1 := NewRegistry()
	r2 := NewRegistry()

	if err := r1.Register(Capability{Name: "only.in.r1"}); err != nil {
		t.Fatalf("r1 注册失败: %v", err)
	}
	if _, ok := r2.Get("only.in.r1"); ok {
		t.Fatal("r2 不应看到 r1 的能力，注册表之间必须隔离")
	}
	// 两个实例各自装配了平台能力，但 r1 新增的能力不应出现在 r2 中。
	for _, c := range r2.List() {
		if c.Name == "only.in.r1" {
			t.Fatal("r2 不应包含 r1 注册的能力")
		}
	}
}
