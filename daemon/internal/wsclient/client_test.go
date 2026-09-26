package wsclient

import (
	"testing"
	"time"
)

func TestBuildSubprotocols(t *testing.T) {
	got := BuildSubprotocols("abc.def-ghi")
	want := []string{"jarvis-ext", "jarvis-token.abc.def-ghi"}
	if len(got) != len(want) {
		t.Fatalf("长度不符: got=%v want=%v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("第 %d 项不符: got=%q want=%q", i, got[i], want[i])
		}
	}
}

func TestBuildSubprotocolsEscapesToken(t *testing.T) {
	// JWT 含 '.' 与 '-'，QueryEscape 后应保持可安全放入子协议。
	got := BuildSubprotocols("a b+c/d")
	if len(got) != 2 {
		t.Fatalf("期望 2 个子协议，实际 %d", len(got))
	}
	if got[1] != "jarvis-token.a+b%2Bc%2Fd" {
		t.Errorf("转义结果不符: %q", got[1])
	}
}

func TestBuildSubprotocolsNoToken(t *testing.T) {
	got := BuildSubprotocols("")
	if len(got) != 1 || got[0] != "jarvis-ext" {
		t.Errorf("无 Token 时应只有 jarvis-ext，实际 %v", got)
	}
}

func TestNormalizeGateway(t *testing.T) {
	cases := map[string]string{
		"https://jvs-ai.cn/":     "https://jvs-ai.cn",
		"http://127.0.0.1:8000/": "http://127.0.0.1:8000",
		"jvs-ai.cn":              "https://jvs-ai.cn",
		"  jvs-ai.cn//  ":        "https://jvs-ai.cn",
		"":                       "",
	}
	for in, want := range cases {
		if got := NormalizeGateway(in); got != want {
			t.Errorf("NormalizeGateway(%q)=%q, want %q", in, got, want)
		}
	}
}

func TestBuildWSURL(t *testing.T) {
	cases := map[string]string{
		"https://jvs-ai.cn":      "wss://jvs-ai.cn/api/browser-ext/ws",
		"http://127.0.0.1:8000":  "ws://127.0.0.1:8000/api/browser-ext/ws",
		"http://127.0.0.1:8000/": "ws://127.0.0.1:8000/api/browser-ext/ws",
	}
	for in, want := range cases {
		got, err := BuildWSURL(in)
		if err != nil {
			t.Fatalf("BuildWSURL(%q) 报错: %v", in, err)
		}
		if got != want {
			t.Errorf("BuildWSURL(%q)=%q, want %q", in, got, want)
		}
	}
	if _, err := BuildWSURL(""); err == nil {
		t.Error("空网关地址应报错")
	}
}

func TestReconnectDelay(t *testing.T) {
	// 与扩展一致：min(base*2^attempt, max)，base=1s max=30s。
	cases := []struct {
		attempt int
		want    time.Duration
	}{
		{0, 1 * time.Second},
		{1, 2 * time.Second},
		{2, 4 * time.Second},
		{3, 8 * time.Second},
		{4, 16 * time.Second},
		{5, 30 * time.Second}, // 32 被截断为 30
		{6, 30 * time.Second},
		{100, 30 * time.Second},
	}
	for _, c := range cases {
		if got := ReconnectDelay(c.attempt, 1, 30); got != c.want {
			t.Errorf("ReconnectDelay(%d)=%v, want %v", c.attempt, got, c.want)
		}
	}
}

func TestReconnectDelayCustomBase(t *testing.T) {
	if got := ReconnectDelay(0, 2, 10); got != 2*time.Second {
		t.Errorf("首次退避应为 base，实际 %v", got)
	}
	if got := ReconnectDelay(10, 2, 10); got != 10*time.Second {
		t.Errorf("应截断到 max，实际 %v", got)
	}
}

func TestReconnectDelayNegativeAttempt(t *testing.T) {
	if got := ReconnectDelay(-1, 1, 30); got != 1*time.Second {
		t.Errorf("负数 attempt 应按 0 处理，实际 %v", got)
	}
}
