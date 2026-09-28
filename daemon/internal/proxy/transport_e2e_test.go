package proxy

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

// TestE2EProxyTransport 端到端验证：设 HTTP_PROXY 后，Transport 对**非回环**
// 主机的请求真的经代理；DirectTransport 则绕过代理。
//
// 注意：Go 的 httpproxy 对 127.0.0.1/localhost 会自动直连，故这里用
// example.invalid 这类不可解析的主机名作为目标——请求必须经代理才能成功，
// 从而证明代理确实生效。
//
// 该用例在子进程中运行（见 runChildE2E），以避免 http.ProxyFromEnvironment
// 的环境变量缓存被同包其它测试污染。
func TestE2EProxyTransport(t *testing.T) {
	out := runChildE2E(t)
	if out != "ok" {
		t.Fatalf("子进程结果异常: %s", out)
	}
}

// TestE2EProxyTransportChild 是子进程入口，执行真正的端到端断言。
func TestE2EProxyTransportChild(t *testing.T) {
	if os.Getenv(e2eChildEnvKey) != childEnvVal {
		t.Skip("仅在子进程中运行")
	}

	var (
		proxied bool
		gotURL  string
	)
	proxySrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		proxied = true
		gotURL = r.URL.String()
		io.WriteString(w, "via-proxy")
	}))
	defer proxySrv.Close()

	os.Setenv("HTTP_PROXY", proxySrv.URL)
	os.Setenv("http_proxy", proxySrv.URL)
	os.Setenv("NO_PROXY", "")
	os.Setenv("no_proxy", "")

	client := &http.Client{Transport: Transport()}
	resp, err := client.Get("http://example.invalid/hello")
	if err != nil {
		t.Fatalf("请求失败: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if !proxied || string(body) != "via-proxy" {
		t.Fatalf("应经代理，实际 proxied=%v body=%q", proxied, body)
	}
	if gotURL != "http://example.invalid/hello" {
		t.Fatalf("代理收到的目标 URL 不符: %q", gotURL)
	}

	// DirectTransport：同样环境变量下应直连（因 example.invalid 不可解析而失败）。
	direct := &http.Client{Transport: DirectTransport()}
	if _, err := direct.Get("http://example.invalid/hello"); err == nil {
		t.Fatal("DirectTransport 不应经代理（example.invalid 应无法直连）")
	}
	t.Logf("端到端：Transport 经代理(目标=%s)，DirectTransport 直连失败，均符合预期", gotURL)
}
