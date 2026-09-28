package proxy

import (
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"testing"
)

// 说明：http.ProxyFromEnvironment 内部用 sync.Once 缓存环境变量（首次调用
// 时读取，之后不再变化）。因此「设置不同代理环境变量 → 观察不同结果」的
// 用例无法在同一进程内完成，需借助子进程（每次都是全新进程、全新缓存）。
//
// 约定：当环境变量 PROXY_TEST_CHILD 非空时，本测试二进制作为子进程运行，
// 直接执行被测逻辑并以退出码表达结果。

const (
	childEnvKey    = "PROXY_TEST_CHILD"
	e2eChildEnvKey = "PROXY_TEST_E2E_CHILD"
	childEnvVal    = "1"
)

// runChildE2E 以子进程方式运行 TestE2EProxyTransportChild。
func runChildE2E(t *testing.T) string {
	t.Helper()
	cmd := exec.Command(os.Args[0], "-test.run=^TestE2EProxyTransportChild$", "-test.v")
	cmd.Env = append(os.Environ(), e2eChildEnvKey+"="+childEnvVal)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("子进程失败: %v\n%s", err, out)
	}
	return "ok"
}

// TestProxyFuncFromEnvironment 验证设置了 HTTP_PROXY / HTTPS_PROXY 后，
// ProxyFunc 会为对应协议的请求返回环境变量中的代理。
func TestProxyFuncFromEnvironment(t *testing.T) {
	out := runChild(t, map[string]string{
		"HTTP_PROXY":  "http://proxy.example:8080",
		"HTTPS_PROXY": "http://secure.example:8443",
		"NO_PROXY":    "",
	})
	if out != "ok" {
		t.Fatalf("子进程结果异常: %s", out)
	}
}

// TestProxyFuncNoProxy 验证 NO_PROXY 命中的主机不走代理。
func TestProxyFuncNoProxy(t *testing.T) {
	out := runChild(t, map[string]string{
		"HTTP_PROXY": "http://proxy.example:8080",
		"NO_PROXY":   "skip.example",
	})
	if out != "ok" {
		t.Fatalf("子进程结果异常: %s", out)
	}
}

// TestProxyFuncNoEnv 验证未设置任何代理环境变量时不使用代理。
//
// 注意：Windows 上宿主机可能启用了系统代理，此时会返回系统代理而非 nil，
// 故该断言仅在非 Windows 平台生效。
func TestProxyFuncNoEnv(t *testing.T) {
	if isWindows() {
		t.Skip("Windows 上系统代理会影响结果，跳过")
	}
	out := runChild(t, map[string]string{
		"HTTP_PROXY":  "",
		"HTTPS_PROXY": "",
		"NO_PROXY":    "",
		"http_proxy":  "",
		"https_proxy": "",
		"no_proxy":    "",
	})
	if out != "ok" {
		t.Fatalf("子进程结果异常: %s", out)
	}
}

// TestProxyFuncChild 是子进程入口：按 PROXY_TEST_CHILD 指定的场景执行断言。
func TestProxyFuncChild(t *testing.T) {
	if os.Getenv(childEnvKey) != childEnvVal {
		t.Skip("仅在子进程中运行")
	}
	scenario := os.Getenv("PROXY_TEST_SCENARIO")
	fn := ProxyFunc()

	req, _ := http.NewRequest(http.MethodGet, "http://target.example/path", nil)
	got, err := fn(req)
	if err != nil {
		t.Fatalf("代理决策失败: %v", err)
	}

	switch scenario {
	case "env":
		assertProxyURL(t, got, "http://proxy.example:8080")
		httpsReq, _ := http.NewRequest(http.MethodGet, "https://target.example/path", nil)
		got, err = fn(httpsReq)
		if err != nil {
			t.Fatalf("https 代理决策失败: %v", err)
		}
		assertProxyURL(t, got, "http://secure.example:8443")
	case "noproxy":
		skipReq, _ := http.NewRequest(http.MethodGet, "http://skip.example/path", nil)
		got, err = fn(skipReq)
		if err != nil {
			t.Fatalf("代理决策失败: %v", err)
		}
		if got != nil {
			t.Fatalf("NO_PROXY 命中的主机不应走代理，实际 %v", got)
		}
	case "noenv":
		if got != nil {
			t.Fatalf("未配置代理时不应返回代理，实际 %v", got)
		}
	default:
		t.Fatalf("未知场景: %q", scenario)
	}
}

// TestTransportUsesProxyFunc 验证 Transport 的 Proxy 字段已接线。
func TestTransportUsesProxyFunc(t *testing.T) {
	if Transport().Proxy == nil {
		t.Fatal("Transport().Proxy 不应为 nil")
	}
	if DirectTransport().Proxy != nil {
		t.Fatal("DirectTransport().Proxy 应为 nil（不使用代理）")
	}
}

// TestPickProxyForScheme 覆盖 ProxyServer 的两种形式。
func TestPickProxyForScheme(t *testing.T) {
	cases := []struct {
		name   string
		server string
		scheme string
		want   string
	}{
		{"单一地址任意协议", "host:8080", "http", "host:8080"},
		{"单一地址 https", "host:8080", "https", "host:8080"},
		{"按协议区分命中", "http=a:1;https=b:2", "https", "b:2"},
		{"按协议区分不区分大小写", "HTTP=a:1;HTTPS=b:2", "https", "b:2"},
		{"按协议区分未命中", "http=a:1;https=b:2", "socks", ""},
		{"空字符串", "", "http", ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := pickProxyForScheme(c.server, c.scheme); got != c.want {
				t.Fatalf("pickProxyForScheme(%q,%q)=%q, want %q",
					c.server, c.scheme, got, c.want)
			}
		})
	}
}

// TestParseProxyURL 覆盖无协议前缀与带前缀两种形式。
func TestParseProxyURL(t *testing.T) {
	got, err := parseProxyURL("host:8080")
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	assertProxyURL(t, got, "http://host:8080")

	got, err = parseProxyURL("socks5://host:1080")
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	assertProxyURL(t, got, "socks5://host:1080")

	got, err = parseProxyURL("  ")
	if err != nil || got != nil {
		t.Fatalf("空字符串应返回 (nil,nil)，实际 (%v,%v)", got, err)
	}
}

// TestMatchProxyOverride 覆盖 ProxyOverride 的各种匹配规则。
func TestMatchProxyOverride(t *testing.T) {
	cases := []struct {
		name     string
		host     string
		override string
		want     bool
	}{
		{"通配全部", "any.example", "*", true},
		{"精确命中", "example.com", "example.com", true},
		{"后缀命中", "a.example.com", "example.com", true},
		{"前缀不同不命中", "notexample.com", "example.com", false},
		{"分号分隔", "a.com", "b.com;a.com", true},
		{"逗号分隔", "a.com", "b.com,a.com", true},
		{"前导点", "a.example.com", ".example.com", true},
		{"local 命中无点主机", "myhost", "<local>", true},
		{"local 不命中含点主机", "my.host", "<local>", false},
		{"大小写不敏感", "A.Example.COM", "example.com", true},
		{"空 override", "a.com", "", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := matchProxyOverride(c.host, c.override); got != c.want {
				t.Fatalf("matchProxyOverride(%q,%q)=%v, want %v",
					c.host, c.override, got, c.want)
			}
		})
	}
}

// runChild 以子进程方式运行本测试二进制，仅执行 TestProxyFuncChild，
// 并通过环境变量指定代理配置与场景。子进程成功时输出 "ok"。
//
// 之所以用子进程：http.ProxyFromEnvironment 会缓存环境变量，同一进程内
// 无法观察多次环境变量变化。
func runChild(t *testing.T, env map[string]string) string {
	t.Helper()
	cmd := exec.Command(os.Args[0], "-test.run=^TestProxyFuncChild$", "-test.v")
	cmd.Env = append(os.Environ(), childEnvKey+"="+childEnvVal)
	for k, v := range env {
		cmd.Env = append(cmd.Env, k+"="+v)
	}
	cmd.Env = append(cmd.Env, "PROXY_TEST_SCENARIO="+scenarioOf(env))
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("子进程失败: %v\n%s", err, out)
	}
	return "ok"
}

// scenarioOf 依据传入的环境变量推断子进程场景。
func scenarioOf(env map[string]string) string {
	if env["NO_PROXY"] == "skip.example" {
		return "noproxy"
	}
	if env["HTTP_PROXY"] == "" {
		return "noenv"
	}
	return "env"
}

// assertProxyURL 断言解析出的代理 URL 与期望一致。
func assertProxyURL(t *testing.T, got *url.URL, want string) {
	t.Helper()
	if got == nil {
		t.Fatalf("期望代理 %s，实际 nil", want)
	}
	if got.String() != want {
		t.Fatalf("代理 URL = %s, want %s", got.String(), want)
	}
}
