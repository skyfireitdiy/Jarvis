package selfupdate

import "testing"

// TestCompareVersions 验证版本号语义化比较。
//
// 为什么不能用字符串比较：字符串比较下 "7.10.0" < "7.9.0"（因为 '1' < '9'），
// 会导致「新版被当成旧版」而拒绝升级，或「旧版被当成新版」而误降级。
func TestCompareVersions(t *testing.T) {
	cases := []struct {
		a, b string
		want int
		why  string
	}{
		{"7.2.0", "7.2.1", -1, "补丁号升级"},
		{"7.2.1", "7.2.0", 1, "补丁号降级"},
		{"7.2.1", "7.2.1", 0, "完全相同"},
		{"v7.2.1", "7.2.1", 0, "v 前缀不影响比较"},
		{"7.10.0", "7.9.0", 1, "两位数段必须按数值比较（字符串比较会判错）"},
		{"7.9.0", "7.10.0", -1, "两位数段反向"},
		{"7.2", "7.2.0", 0, "缺省段按 0 补齐"},
		{"7.2.0", "7.2", 0, "缺省段按 0 补齐（反向）"},
		{"8.0.0", "7.99.99", 1, "主版本号优先"},
		{"1.0.0-beta", "1.0.0", 0, "后缀不参与比较"},
	}
	for _, c := range cases {
		if got := CompareVersions(c.a, c.b); got != c.want {
			t.Errorf("CompareVersions(%q, %q) = %d, 期望 %d（%s）", c.a, c.b, got, c.want, c.why)
		}
	}
}

// TestIsDowngrade 验证降级判定。
func TestIsDowngrade(t *testing.T) {
	cases := []struct {
		current, target string
		want            bool
	}{
		{"7.2.1", "7.2.0", true},  // 降级：必须拦截
		{"7.2.1", "7.2.1", false}, // 同版本：不算降级
		{"7.2.1", "7.3.0", false}, // 升级：允许
		{"v7.2.1", "7.2.0", true}, // 带 v 前缀也要正确识别
	}
	for _, c := range cases {
		if got := IsDowngrade(c.current, c.target); got != c.want {
			t.Errorf("IsDowngrade(current=%q, target=%q) = %v, 期望 %v", c.current, c.target, got, c.want)
		}
	}
}

// TestShouldSkipUpdate_Downgrade 验证「禁止降级」在 ShouldSkipUpdate 中生效。
//
// 这是真机故障的直接回归测试：daemon 7.2.1 连到版本为 7.2.0 的旧网关时，
// 网关下发「有新版本 7.2.0」，旧实现会执行降级 → 重启后连到新网关又升级回去
// → 无限重启（实测每 5~10 秒一次）。
func TestShouldSkipUpdate_Downgrade(t *testing.T) {
	now := int64(1_700_000_000)
	// 关键：即使状态是「干净的」（无熔断、无失败记录），也必须拦截降级。
	clean := AttemptState{}
	skip, reason := ShouldSkipUpdate(clean, "7.2.1", "7.2.0", now)
	if !skip {
		t.Fatalf("降级到 7.2.0 应被拦截，实际未拦截（reason=%q）", reason)
	}
	if reason == "" {
		t.Error("拦截降级时应给出原因")
	}
}

// TestShouldSkipUpdate_GatewayVersionFlapping 验证多网关版本抖动的回归场景。
//
// 模拟真机故障：两个网关交替下发 7.2.0 / 7.2.1，daemon 当前 7.2.1。
// 期望：所有降级请求（7.2.0）都被拦截，daemon 稳定在 7.2.1 不再重启。
func TestShouldSkipUpdate_GatewayVersionFlapping(t *testing.T) {
	now := int64(1_700_000_000)
	state := AttemptState{}

	// 模拟 20 次交替握手（两个网关轮流）。
	for i := 0; i < 20; i++ {
		target := "7.2.0"
		if i%2 == 1 {
			target = "7.2.1"
		}
		skip, reason := ShouldSkipUpdate(state, "7.2.1", target, now+int64(i))
		if target == "7.2.0" && !skip {
			t.Fatalf("第 %d 次：降级到 7.2.0 未被拦截（reason=%q）", i, reason)
		}
		// 7.2.1 与当前同版本，网关不应下发更新；若下发也应因同版本被跳过或无害。
	}
}

// TestRecentUpdateBurst 验证跨版本的全局频率熔断。
//
// 场景：即使每次目标版本都不同（绕过 TargetVersion 键的熔断），
// 10 分钟内更新 3 次也必须熔断。
func TestRecentUpdateBurst(t *testing.T) {
	now := int64(1_700_000_000)

	// 无历史：不熔断。
	if burst, count := RecentUpdateBurst(AttemptState{}, now); burst || count != 0 {
		t.Errorf("无历史时应不熔断，实际 burst=%v count=%d", burst, count)
	}

	// 窗口内 2 次：未达阈值，不熔断。
	two := AttemptState{RecentUpdates: []int64{now - 100, now - 50}}
	if burst, count := RecentUpdateBurst(two, now); burst || count != 2 {
		t.Errorf("窗口内 2 次应不熔断，实际 burst=%v count=%d", burst, count)
	}

	// 窗口内 3 次：达到阈值，熔断。
	three := AttemptState{RecentUpdates: []int64{now - 300, now - 200, now - 100}}
	if burst, count := RecentUpdateBurst(three, now); !burst || count != 3 {
		t.Errorf("窗口内 3 次应熔断，实际 burst=%v count=%d", burst, count)
	}

	// 窗口外的旧记录不计入（熔断能自然恢复）。
	stale := AttemptState{RecentUpdates: []int64{now - 5000, now - 4000, now - 3000}}
	if burst, count := RecentUpdateBurst(stale, now); burst || count != 0 {
		t.Errorf("窗口外记录不应计入，实际 burst=%v count=%d", burst, count)
	}
}

// TestAppendRecentUpdate 验证更新时间戳的追加与裁剪。
func TestAppendRecentUpdate(t *testing.T) {
	now := int64(1_700_000_000)

	// 空历史 → 只含本次。
	got := AppendRecentUpdate(nil, now)
	if len(got) != 1 || got[0] != now {
		t.Errorf("空历史追加后应为 [%d]，实际 %v", now, got)
	}

	// 窗口外的旧记录被丢弃。
	got = AppendRecentUpdate([]int64{now - 5000}, now)
	if len(got) != 1 || got[0] != now {
		t.Errorf("窗口外记录应被丢弃，实际 %v", got)
	}

	// 窗口内的保留。
	got = AppendRecentUpdate([]int64{now - 100}, now)
	if len(got) != 2 {
		t.Errorf("窗口内记录应保留，实际 %v", got)
	}

	// 超过上限时只保留最近的 recentUpdatesKeep 条。
	many := make([]int64, 0, recentUpdatesKeep+5)
	for i := 0; i < recentUpdatesKeep+5; i++ {
		many = append(many, now-int64(i))
	}
	got = AppendRecentUpdate(many, now)
	if len(got) > recentUpdatesKeep {
		t.Errorf("应裁剪到 %d 条，实际 %d", recentUpdatesKeep, len(got))
	}
	// 最新的一条必须在末尾。
	if got[len(got)-1] != now {
		t.Errorf("末尾应为本次时间戳 %d，实际 %d", now, got[len(got)-1])
	}
}

// TestShouldSkipUpdate_BurstOverridesVersionChange 验证频率熔断优先于「目标版本变化」。
//
// 这是关键顺序约束：若把 TargetVersion 判定放在前面，目标版本一变就会
// 「视为新机会」直接放行，频率熔断形同虚设。
func TestShouldSkipUpdate_BurstOverridesVersionChange(t *testing.T) {
	now := int64(1_700_000_000)
	// 状态：10 分钟内已更新 3 次（不同目标版本），且本次目标版本与上次不同。
	state := AttemptState{
		TargetVersion: "7.2.0",
		RecentUpdates: []int64{now - 300, now - 200, now - 100},
	}
	skip, reason := ShouldSkipUpdate(state, "7.2.1", "7.3.0", now)
	if !skip {
		t.Fatalf("频率熔断应优先于目标版本变化，实际未跳过（reason=%q）", reason)
	}
}

// TestShouldSkipUpdate_NormalUpgradeAllowed 验证正常升级不被误拦。
//
// 防止修复过度：单次正常升级（无历史、版本更高）必须放行。
func TestShouldSkipUpdate_NormalUpgradeAllowed(t *testing.T) {
	now := int64(1_700_000_000)
	skip, reason := ShouldSkipUpdate(AttemptState{}, "7.2.1", "7.3.0", now)
	if skip {
		t.Fatalf("正常升级不应被拦截（reason=%q）", reason)
	}
}

// TestRetryAfter_DowngradeNoRetry 验证降级态不安排重试。
func TestRetryAfter_DowngradeNoRetry(t *testing.T) {
	now := int64(1_700_000_000)
	// 即使有失败记录（本会安排退避重试），降级态也必须返回 0。
	state := AttemptState{
		TargetVersion:   "7.2.0",
		Attempts:        1,
		LastAttemptUnix: now - 10,
	}
	if got := RetryAfter(state, "7.2.1", "7.2.0", now); got != 0 {
		t.Errorf("降级态不应安排重试，实际返回 %v", got)
	}
}
