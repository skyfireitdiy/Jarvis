package capability

import (
	"testing"
	"time"
)

func TestParseWindowWaitParams(t *testing.T) {
	// 默认 state=visible，默认超时/间隔。
	windowID, title, state, timeout, interval, err := parseWindowWaitParams(map[string]any{
		"title": "Notepad",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if windowID != "" || title != "Notepad" || state != "visible" {
		t.Fatalf("got window_id=%q title=%q state=%q", windowID, title, state)
	}
	if timeout != windowsWaitDefaultTimeout || interval != windowsWaitDefaultInterval {
		t.Fatalf("got timeout=%v interval=%v", timeout, interval)
	}

	// 显式指定全部参数。
	_, _, state, timeout, interval, err = parseWindowWaitParams(map[string]any{
		"window_id":   "0x00010A2C",
		"state":       "active",
		"timeout_ms":  5000,
		"interval_ms": 100,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if state != "active" || timeout != 5*time.Second || interval != 100*time.Millisecond {
		t.Fatalf("got state=%q timeout=%v interval=%v", state, timeout, interval)
	}
}

func TestParseWindowWaitParamsErrors(t *testing.T) {
	cases := []map[string]any{
		{},                             // 缺 window_id 与 title
		{"title": "x", "state": "bad"}, // 非法 state
		{"title": "x", "timeout_ms": 0},
		{"title": "x", "timeout_ms": -1},
		{"title": "x", "interval_ms": 0},
	}
	for _, params := range cases {
		if _, _, _, _, _, err := parseWindowWaitParams(params); err == nil {
			t.Fatalf("expected error for params %v", params)
		}
	}
}

func TestParseProcessWaitParams(t *testing.T) {
	pid, timeout, interval, err := parseProcessWaitParams(map[string]any{
		"pid": 1234,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pid != 1234 || timeout != windowsWaitDefaultTimeout || interval != windowsWaitDefaultInterval {
		t.Fatalf("got pid=%d timeout=%v interval=%v", pid, timeout, interval)
	}

	if _, _, _, err := parseProcessWaitParams(map[string]any{"pid": 0}); err == nil {
		t.Fatal("expected error for pid=0")
	}
	if _, _, _, err := parseProcessWaitParams(map[string]any{}); err == nil {
		t.Fatal("expected error for missing pid")
	}
}

func TestWindowWaitConditionMet(t *testing.T) {
	// visible：只要窗口存在。
	if met, _ := windowWaitConditionMet("visible", true, false); !met {
		t.Fatal("visible + present should be met")
	}
	if met, _ := windowWaitConditionMet("visible", false, false); met {
		t.Fatal("visible + absent should not be met")
	}
	// active：窗口存在且为前台。
	if met, _ := windowWaitConditionMet("active", true, true); !met {
		t.Fatal("active + present + foreground should be met")
	}
	if met, _ := windowWaitConditionMet("active", true, false); met {
		t.Fatal("active + present + not foreground should not be met")
	}
	if met, _ := windowWaitConditionMet("active", false, true); met {
		t.Fatal("active + absent should not be met")
	}
	// gone：窗口消失。
	if met, _ := windowWaitConditionMet("gone", false, false); !met {
		t.Fatal("gone + absent should be met")
	}
	if met, _ := windowWaitConditionMet("gone", true, false); met {
		t.Fatal("gone + present should not be met")
	}
	// 非法 state。
	if _, err := windowWaitConditionMet("bad", true, true); err == nil {
		t.Fatal("expected error for bad state")
	}
}

func TestWaitLoop(t *testing.T) {
	// 第一次就满足。
	calls := 0
	met, err := waitLoop(time.Second, time.Millisecond, func() (bool, error) {
		calls++
		return true, nil
	})
	if err != nil || !met {
		t.Fatalf("got met=%v err=%v", met, err)
	}
	if calls != 1 {
		t.Fatalf("expected 1 call, got %d", calls)
	}

	// 第 3 次才满足。
	calls = 0
	met, err = waitLoop(time.Second, time.Millisecond, func() (bool, error) {
		calls++
		return calls >= 3, nil
	})
	if err != nil || !met {
		t.Fatalf("got met=%v err=%v", met, err)
	}

	// 一直不满足 → 超时返回 false。
	met, err = waitLoop(5*time.Millisecond, time.Millisecond, func() (bool, error) {
		return false, nil
	})
	if err != nil || met {
		t.Fatalf("got met=%v err=%v, want met=false", met, err)
	}

	// check 返回错误 → 直接返回错误。
	_, err = waitLoop(time.Second, time.Millisecond, func() (bool, error) {
		return false, errTestWait
	})
	if err == nil {
		t.Fatal("expected error to propagate")
	}
}

var errTestWait = &testWaitError{}

type testWaitError struct{}

func (e *testWaitError) Error() string { return "test wait error" }
