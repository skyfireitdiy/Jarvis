package selfupdate

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// 失败退避阶梯：连续失败时按次数取对应等待时长，超过末档则保持末档。
//
// 为什么需要：自动更新的触发点是每次 WS 握手（hello → hello_ack）。若更新持续
// 失败（下载失败、替换失败等），daemon 版本不变，网关每次握手都会再次下发
// available=true，形成「重连即重试」的风暴。退避把重试频率压到可控范围。
var backoffLadder = []time.Duration{
	1 * time.Minute,
	5 * time.Minute,
	30 * time.Minute,
}

// MaxBackoff 是退避上限（最后一档），供调用方与测试引用。
func MaxBackoff() time.Duration { return backoffLadder[len(backoffLadder)-1] }

// BackoffFor 返回连续失败 attempts 次后的等待时长。
//
// attempts <= 0 视为未失败（返回 0）；超出阶梯长度时取最后一档。
func BackoffFor(attempts int) time.Duration {
	if attempts <= 0 {
		return 0
	}
	if attempts > len(backoffLadder) {
		attempts = len(backoffLadder)
	}
	return backoffLadder[attempts-1]
}

// AttemptState 是自动更新的尝试状态，落盘用于跨进程重启识别「重启循环」。
//
// 为什么必须落盘（不能只存内存）：最危险的失败模式是「替换成功但新版本起不来」——
// 新进程启动后版本仍是旧的，握手时网关再次判定需要更新，于是再替换、再重启，
// 无限循环且 daemon 永远起不来。只有把「正在更新到哪个版本」持久化，新进程才能
// 在启动时发现自己「刚尝试过更新到 X 却仍是旧版本」，从而熔断。
//
// 与 TokenState 的区别：本文件不含任何凭据，仅记录版本与计数，长期驻留无安全风险。
type AttemptState struct {
	// TargetVersion 是最近一次尝试更新到的版本号（原始格式，可能带 v 前缀）。
	TargetVersion string `json:"target_version"`
	// Attempts 是同一目标版本的连续失败次数（成功或目标变化时清零）。
	Attempts int `json:"attempts"`
	// LastAttemptUnix 是最近一次尝试的时间（Unix 秒）。
	LastAttemptUnix int64 `json:"last_attempt_unix"`
	// LastError 是最近一次失败原因（便于排查；成功时为空）。
	LastError string `json:"last_error"`
	// InProgress 表示「已开始替换、尚未确认成功」。为 true 且进程重启后版本未变，
	// 即判定为重启循环。
	InProgress bool `json:"in_progress"`
	// RecentUpdates 记录最近若干次「已开始执行更新」的时间戳（Unix 秒），
	// 用于跨版本的全局熔断（见 RecentUpdateBurst）。
	//
	// 为什么需要（与上面以 TargetVersion 为键的熔断互补）：多网关场景下，
	// 各网关下发的目标版本可能**交替变化**（如 7.2.0 / 7.2.1 轮流），
	// 每次 TargetVersion 都不同 → 熔断被反复重置，单靠 TargetVersion 完全挡不住。
	// 用「最近 N 秒内发生了多少次更新」这个与版本无关的维度，才能识别出
	// 「版本号在抖、但实际在无限重启」的病理状态。
	RecentUpdates []int64 `json:"recent_updates,omitempty"`
}

// AttemptStatePath 返回尝试状态文件路径：~/.jarvis/daemon/update-attempt.json。
//
// 与 TokenStatePath 同目录（~/.jarvis/daemon/），便于用户排查。
func AttemptStatePath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("获取用户主目录失败: %w", err)
	}
	return filepath.Join(home, ".jarvis", "daemon", "update-attempt.json"), nil
}

// SaveAttemptState 把尝试状态写入文件（0600）。
//
// 写入失败返回错误，调用方只记日志、不阻断更新流程（最坏情况是失去跨重启熔断）。
func SaveAttemptState(state AttemptState) error {
	path, err := AttemptStatePath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("创建状态目录失败: %w", err)
	}
	blob, err := json.Marshal(state)
	if err != nil {
		return fmt.Errorf("序列化尝试状态失败: %w", err)
	}
	// 先写临时文件再 rename，避免半截文件。
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, blob, 0o600); err != nil {
		return fmt.Errorf("写入尝试状态临时文件失败: %w", err)
	}
	_ = os.Chmod(tmp, 0o600)
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return fmt.Errorf("保存尝试状态失败: %w", err)
	}
	return nil
}

// LoadAttemptState 读取尝试状态；文件不存在或解析失败时返回零值与 false。
func LoadAttemptState() (AttemptState, bool) {
	path, err := AttemptStatePath()
	if err != nil {
		return AttemptState{}, false
	}
	blob, err := os.ReadFile(path)
	if err != nil {
		return AttemptState{}, false
	}
	var state AttemptState
	if err := json.Unmarshal(blob, &state); err != nil {
		return AttemptState{}, false
	}
	return state, true
}

// ClearAttemptState 删除尝试状态文件（不存在视为成功，幂等）。
func ClearAttemptState() error {
	path, err := AttemptStatePath()
	if err != nil {
		return err
	}
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("删除尝试状态失败: %w", err)
	}
	return nil
}

// NormalizeVersion 归一化版本号：去空白 + 去前导 v/V。
//
// 为什么需要：网关版本来自 jarvis.__version__（如 "6.0.0"，无 v 前缀），
// 而 daemon 版本由构建注入（如 "v5.0.5"，带 v）。不归一化会导致「其实同版本
// 却判定为不同」→ 无限下载重启循环。
func NormalizeVersion(value string) string {
	v := strings.TrimSpace(value)
	for len(v) > 0 && (v[0] == 'v' || v[0] == 'V') {
		v = v[1:]
	}
	return v
}

// SameVersion 判断两个版本号是否相同（归一化后比较，大小写与前导 v 不敏感）。
func SameVersion(a, b string) bool {
	return NormalizeVersion(a) == NormalizeVersion(b)
}

// CompareVersions 比较两个版本号的大小，返回 -1 / 0 / 1。
//
// 语义化比较规则（不引入第三方依赖，手写足够）：
//   - 先归一化（去空白、去前导 v）；
//   - 按 '.' 切分成数字段，逐段数值比较（"7.10.0" > "7.9.0"，字符串比较会判错）；
//   - 段数不同时，缺省段按 0 补齐（"7.2" == "7.2.0"）；
//   - 非数字段（如 "1.0.0-beta"）只比较其数字前缀，"beta" 等后缀忽略——
//     本项目版本号均为纯数字点分格式，后缀不参与判定。
//
// 为什么需要：多网关场景下，版本较旧的网关会下发比当前更低的版本号，
// 若不判断方向就执行更新，daemon 会被反复降级/升级（见 ShouldSkipUpdate 的说明）。
func CompareVersions(a, b string) int {
	as := splitVersion(NormalizeVersion(a))
	bs := splitVersion(NormalizeVersion(b))
	n := len(as)
	if len(bs) > n {
		n = len(bs)
	}
	for i := 0; i < n; i++ {
		var av, bv int
		if i < len(as) {
			av = as[i]
		}
		if i < len(bs) {
			bv = bs[i]
		}
		if av < bv {
			return -1
		}
		if av > bv {
			return 1
		}
	}
	return 0
}

// splitVersion 把版本号切成数字段；无法解析的段按 0 处理。
func splitVersion(v string) []int {
	if v == "" {
		return nil
	}
	parts := strings.Split(v, ".")
	out := make([]int, 0, len(parts))
	for _, p := range parts {
		// 只取前导数字（"0-beta" → 0），遇到非数字即停止。
		end := 0
		for end < len(p) && p[end] >= '0' && p[end] <= '9' {
			end++
		}
		if end == 0 {
			out = append(out, 0)
			continue
		}
		n, err := strconv.Atoi(p[:end])
		if err != nil {
			out = append(out, 0)
			continue
		}
		out = append(out, n)
	}
	return out
}

// IsDowngrade 判断 target 是否低于 current（即本次更新是降级）。
//
// 多网关场景：daemon 连接多个网关时，每个网关在 hello_ack 中把**自身版本**作为
// 最新版本下发。若其中某个网关版本较旧，daemon 会认为「有新版本」并降级到旧版，
// 降级后连到新网关又升回去，形成无限重启循环（真机实测：7.2.0 与 7.2.1 两个网关
// 交替下发，每 5~10 秒重启一次）。
//
// 因此必须显式禁止降级：只允许升级到更高版本。
func IsDowngrade(currentVersion, targetVersion string) bool {
	return CompareVersions(targetVersion, currentVersion) < 0
}

// 全局更新频率熔断参数。
//
// 取值依据：正常的版本升级是「偶发事件」（一天几次已属频繁）；而病理性的
// 版本抖动表现为「几分钟内反复重启」。窗口 10 分钟、阈值 3 次能清晰区分两者：
// 正常升级几乎不可能在 10 分钟内触发 3 次，而抖动循环几秒一次，必然命中。
const (
	// updateBurstWindow 是统计窗口（秒）。
	updateBurstWindow = 600
	// updateBurstLimit 是窗口内允许的更新次数上限（达到即熔断）。
	updateBurstLimit = 3
	// recentUpdatesKeep 是 RecentUpdates 最多保留的条数（防止无限增长）。
	recentUpdatesKeep = 10
)

// RecentUpdateBurst 判断「最近窗口内是否更新过于频繁」，用于跨版本的全局熔断。
//
// 与 ShouldSkipUpdate 中以 TargetVersion 为键的熔断互补：后者只能识别
// 「反复尝试同一个目标版本」；当多个网关交替下发不同版本时，TargetVersion 每次
// 都在变，那道熔断会被反复重置而失效。本函数只看「多久内更新了几次」，
// 与版本号无关，因此能兜住版本抖动型重启循环。
//
// 返回 (burst, count)：burst 为 true 表示应熔断，count 为窗口内实际次数。
func RecentUpdateBurst(state AttemptState, now int64) (bool, int) {
	cutoff := now - updateBurstWindow
	count := 0
	for _, ts := range state.RecentUpdates {
		if ts >= cutoff {
			count++
		}
	}
	return count >= updateBurstLimit, count
}

// AppendRecentUpdate 返回追加了本次更新时间戳后的新切片（只保留窗口内且不超过上限）。
//
// 为什么要裁剪：状态文件会被反复读写，若不裁剪会无限增长；同时把窗口外的旧记录
// 丢掉，熔断才能随「安静期」自然恢复（而不是永久锁死）。
func AppendRecentUpdate(existing []int64, now int64) []int64 {
	cutoff := now - updateBurstWindow
	out := make([]int64, 0, len(existing)+1)
	for _, ts := range existing {
		if ts >= cutoff {
			out = append(out, ts)
		}
	}
	out = append(out, now)
	if len(out) > recentUpdatesKeep {
		out = out[len(out)-recentUpdatesKeep:]
	}
	return out
}

// ShouldSkipUpdate 判断是否应跳过本次自动更新（防重复的集中判定）。
//
// 入参：
//   - state：已落盘的尝试状态；
//   - currentVersion：当前 daemon 版本（如 "v5.0.5"）；
//   - targetVersion：网关本次下发的最新版本（如 "6.0.0"）；
//   - now：当前时间（Unix 秒），便于测试注入。
//
// 返回 (skip, reason)：skip 为 true 时应跳过更新，reason 为中文原因（用于日志）。
//
// 判定顺序：
//  0. 禁止降级：目标版本低于当前版本 → 直接跳过（多网关版本不一致时的关键防线）；
//  1. 熔断：上次「已开始替换」但重启后版本仍是旧的（且目标版本与本次相同）
//     → 判定为重启循环，跳过，避免无限重启；
//  2. 熔断恢复：若本次目标版本与熔断记录的目标版本不同（网关发新版了）
//     → 清除熔断，允许尝试；
//  3. 同版本失败不重试 + 退避：上次失败的目标版本与本次相同，且仍在退避窗口内
//     → 跳过；窗口已过则允许重试（Attempts 继续累加）。
func ShouldSkipUpdate(state AttemptState, currentVersion, targetVersion string, now int64) (bool, string) {
	// 禁止降级：必须先于其他判定。
	//
	// 为什么放在最前面：daemon 连接多个网关时，每个网关都把自身版本当作「最新版本」
	// 下发。若旧网关（如 7.2.0）与当前 daemon（7.2.1）握手，会下发「有新版本 7.2.0」。
	// 此时若执行更新，daemon 被降级；降级后连到新网关（7.2.1）又升级回去，
	// 两个网关交替触发形成无限重启循环——且因为 TargetVersion 每次都在变，
	// 下面的熔断判定（以 TargetVersion 为键）会被反复重置，完全失效。
	// 真机实测：7.2.0 与 7.2.1 交替出现 573/566 次，每 5~10 秒重启一次。
	if IsDowngrade(currentVersion, targetVersion) {
		return true, fmt.Sprintf("目标版本 %s 低于当前版本 %s，禁止降级（多网关版本不一致时属正常现象）",
			targetVersion, currentVersion)
	}

	// 全局频率熔断：与版本号无关，兜住「多网关交替下发不同版本」导致的抖动循环。
	// 必须放在 TargetVersion 相关判定之前——那种场景下 TargetVersion 每次都在变，
	// 后面的判定都会被重置而失效。
	if burst, count := RecentUpdateBurst(state, now); burst {
		return true, fmt.Sprintf("最近 %d 分钟内已执行 %d 次自动更新，判定为更新抖动循环，已熔断（等待 %d 分钟窗口滑过后自动恢复）",
			updateBurstWindow/60, count, updateBurstWindow/60)
	}

	if !SameVersion(state.TargetVersion, targetVersion) {
		// 目标版本变化：无论上次是熔断还是失败，都视为新机会，允许尝试。
		return false, ""
	}
	if state.InProgress {
		// 上次已开始替换却仍是旧版本 → 新版没起来（或替换未生效），熔断。
		return true, fmt.Sprintf("检测到重启循环：上次已尝试更新到 %s 但当前版本仍为 %s，已熔断自动更新（等待网关发布更新版本后自动恢复）",
			targetVersion, currentVersion)
	}
	if state.Attempts > 0 {
		wait := BackoffFor(state.Attempts)
		elapsed := now - state.LastAttemptUnix
		if elapsed < int64(wait/time.Second) {
			return true, fmt.Sprintf("上次更新到 %s 失败（第 %d 次，原因：%s），退避中（剩余约 %d 秒）",
				targetVersion, state.Attempts, state.LastError, int64(wait/time.Second)-elapsed)
		}
	}
	return false, ""
}

// RetryAfter 返回距下次可重试还需等待的时长；无需等待（或不应重试）时返回 0。
//
// 为什么需要：ShouldSkipUpdate 只在「触发点」（WS 握手收到 hello_ack）被调用。
// 但连接稳定时只有 ping/pong 心跳，不产生 hello_ack；且前端重复推送相同凭据时
// ConnectWithName 会因幂等判断跳过重建连接（见 wsclient/manager.go），同样不产生
// hello_ack。结果是退避窗口到期后没有任何事件来唤醒检查，更新就此永久停滞。
// 调用方据此返回值安排定时器，实现「退避到期自动重试」，不再依赖外部握手事件。
//
// 返回 0 的三种情形需调用方区分对待：
//   - 目标版本变化 / 无失败记录：应当立即尝试；
//   - 熔断态（InProgress 且目标版本未变）：不应重试，否则会陷入重启循环。
//
// 因此调用方应先经 ShouldSkipUpdate 判定「是否跳过」，仅在跳过时用本函数取等待
// 时长；若返回 0 则说明是熔断态，不得安排重试。
func RetryAfter(state AttemptState, currentVersion, targetVersion string, now int64) time.Duration {
	// 禁止降级：与 ShouldSkipUpdate 保持一致，降级态不安排重试。
	// 否则会每隔一个退避周期就去「重试」一次注定被拒绝的降级，白白唤醒 goroutine。
	if IsDowngrade(currentVersion, targetVersion) {
		return 0
	}
	if !SameVersion(state.TargetVersion, targetVersion) {
		// 目标版本变化：视为新机会，无需等待。
		return 0
	}
	if state.InProgress {
		// 熔断态：等网关发布新版本才恢复，此处不安排重试。
		return 0
	}
	if state.Attempts > 0 {
		wait := BackoffFor(state.Attempts)
		elapsed := now - state.LastAttemptUnix
		if remaining := wait - time.Duration(elapsed)*time.Second; remaining > 0 {
			return remaining
		}
	}
	return 0
}
