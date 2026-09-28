// Package gatewayfilter 提供「网关黑白名单」的匹配与判定能力。
//
// 背景：守护进程/浏览器扩展会在用户登录某个网关时自动建立连接。若用户只是
// 偶尔登录过一次某台网关（例如测试环境、他人的服务器），之后它会被自动发现
// 并长期连接，造成「意外连上不该连的网关」。本包提供一份可配置的名单，
// 用于限制哪些网关允许/不允许连接。
//
// 三种模式：
//   - off：不限制，任何网关都允许（默认）。
//   - whitelist：白名单，仅名单内命中的网关允许连接。
//   - blacklist：黑名单，名单内命中的网关不允许连接，其余允许。
//
// 匹配对象为「host:port」（与 auth.GatewayKey 语义一致，忽略协议差异），
// 支持通配符：'*' 匹配任意长度字符（含空串），'?' 匹配恰好一个字符。
//
// 本包刻意不 import auth：一是避免与上层包产生不必要的依赖耦合，二是
// hostPort 归一的逻辑很短，自己实现更直观（语义与 auth.GatewayKey 对齐）。
package gatewayfilter

import (
	"net/url"
	"strings"
	"sync"
)

// 模式常量。
const (
	// ModeOff 表示不限制（默认）。
	ModeOff = "off"
	// ModeWhitelist 表示白名单：仅名单内命中才允许。
	ModeWhitelist = "whitelist"
	// ModeBlacklist 表示黑名单：名单内命中则拒绝。
	ModeBlacklist = "blacklist"
)

// NormalizeMode 规范化模式字符串：去空白、转小写；空串或非法值一律回退到 ModeOff。
//
// 回退到「不限制」而非报错，是为了让配置解析与前端推送容错：非法值不应
// 让守护进程启动失败，也不应意外把用户锁死（安全方向由「默认 off」保证）。
func NormalizeMode(s string) string {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case ModeWhitelist:
		return ModeWhitelist
	case ModeBlacklist:
		return ModeBlacklist
	default:
		return ModeOff
	}
}

// ValidMode 判断模式字符串是否为三种合法值之一（规范化后）。
func ValidMode(s string) bool {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case ModeOff, ModeWhitelist, ModeBlacklist:
		return true
	default:
		return false
	}
}

// Match 判断 hostPort 是否匹配 pattern（通配符：'*' 任意长度含空，'?' 恰好一个字符）。
//
// 大小写不敏感；pattern 与 hostPort 均先 trim。
// 用双指针 + 回溯实现（O(n*m) 最坏），刻意不用 regexp：避免用户输入的
// pattern 被当作正则解析（注入/性能陷阱），且通配符语义更直观。
func Match(pattern, hostPort string) bool {
	p := strings.ToLower(strings.TrimSpace(pattern))
	s := strings.ToLower(strings.TrimSpace(hostPort))
	if p == "" {
		// 空 pattern 不匹配任何非空输入；空输入也不匹配。
		return s == ""
	}

	// 经典通配符匹配：pi 指向 pattern，si 指向 hostPort；
	// star 记录最近一次 '*' 的位置，mark 记录该 '*' 当时对应的 si。
	pi, si := 0, 0
	star := -1
	mark := 0
	for si < len(s) {
		if pi < len(p) && (p[pi] == '?' || p[pi] == s[si]) {
			pi++
			si++
			continue
		}
		if pi < len(p) && p[pi] == '*' {
			// 记录回溯点：先尝试让 '*' 匹配空串。
			star = pi
			mark = si
			pi++
			continue
		}
		if star >= 0 {
			// 回溯：让最近的 '*' 多吞一个字符，重新尝试。
			pi = star + 1
			mark++
			si = mark
			continue
		}
		return false
	}
	// hostPort 已耗尽，pattern 剩余的必须全是 '*' 才算匹配。
	for pi < len(p) && p[pi] == '*' {
		pi++
	}
	return pi == len(p)
}

// hostPort 把网关地址归一化为「host:port」（与 auth.GatewayKey 语义一致）：
// 解析 URL 后取 hostname:port，端口缺省时 https/wss→443、http/ws→80；解析失败回退原串。
//
// 必须显式识别 ws:// 与 wss://：daemon 连接的网关地址天然可能是 WebSocket 形式
// （如 ws://host:9999），若只认 http(s) 会被误加 "http://" 前缀，导致
// url.Parse 把 "ws" 当成主机名、端口丢失，黑白名单随之失配。
func hostPort(gateway string) string {
	g := strings.TrimSpace(gateway)
	if g == "" {
		return ""
	}
	lower := strings.ToLower(g)
	if !strings.HasPrefix(lower, "http://") && !strings.HasPrefix(lower, "https://") &&
		!strings.HasPrefix(lower, "ws://") && !strings.HasPrefix(lower, "wss://") {
		g = "http://" + g
	}
	g = strings.TrimRight(g, "/")
	u, err := url.Parse(g)
	if err != nil || u.Hostname() == "" {
		return g
	}
	port := u.Port()
	if port == "" {
		if strings.EqualFold(u.Scheme, "https") || strings.EqualFold(u.Scheme, "wss") {
			port = "443"
		} else {
			port = "80"
		}
	}
	return u.Hostname() + ":" + port
}

// Filter 持有当前名单配置，线程安全（读多写少，用 RWMutex）。
//
// 零值不可用，请用 New 构造。允许把 (*Filter)(nil) 作为「不限制」的哨兵：
// 所有方法对 nil 接收者安全（Allows 返回 true，其余为 no-op/空值）。
type Filter struct {
	mu       sync.RWMutex
	mode     string
	patterns []string
}

// New 构造一个 Filter；mode 会经 NormalizeMode 规范化，patterns 会做 trim 并去空项。
func New(mode string, patterns []string) *Filter {
	f := &Filter{}
	f.Set(mode, patterns)
	return f
}

// Set 更新模式与名单（加锁）。
func (f *Filter) Set(mode string, patterns []string) {
	if f == nil {
		return
	}
	cleaned := make([]string, 0, len(patterns))
	for _, p := range patterns {
		if v := strings.TrimSpace(p); v != "" {
			cleaned = append(cleaned, v)
		}
	}
	f.mu.Lock()
	f.mode = NormalizeMode(mode)
	f.patterns = cleaned
	f.mu.Unlock()
}

// Snapshot 返回当前模式与名单的副本（加锁），供状态查询/持久化使用。
func (f *Filter) Snapshot() (string, []string) {
	if f == nil {
		return ModeOff, nil
	}
	f.mu.RLock()
	defer f.mu.RUnlock()
	out := make([]string, len(f.patterns))
	copy(out, f.patterns)
	return f.mode, out
}

// Allows 判断给定网关是否允许连接。
//
// 判定规则：
//   - nil 接收者 / ModeOff → true（不限制）。
//   - ModeWhitelist → 名单中任一 pattern 命中 host:port 才 true；名单为空则 false
//     （白名单为空表示「谁都不允许」，是安全方向）。
//   - ModeBlacklist → 名单中任一 pattern 命中则 false；名单为空则 true（不限制）。
func (f *Filter) Allows(gateway string) bool {
	if f == nil {
		return true
	}
	f.mu.RLock()
	mode := f.mode
	patterns := f.patterns
	f.mu.RUnlock()

	if mode == ModeOff {
		return true
	}
	hp := hostPort(gateway)
	if hp == "" {
		// 无法归一化的地址：白名单下拒绝（安全方向），黑名单下放行。
		return mode != ModeWhitelist
	}
	hit := false
	for _, p := range patterns {
		if Match(p, hp) {
			hit = true
			break
		}
	}
	if mode == ModeWhitelist {
		return hit
	}
	// ModeBlacklist
	return !hit
}
