package selfupdate

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
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
//  1. 熔断：上次「已开始替换」但重启后版本仍是旧的（且目标版本与本次相同）
//     → 判定为重启循环，跳过，避免无限重启；
//  2. 熔断恢复：若本次目标版本与熔断记录的目标版本不同（网关发新版了）
//     → 清除熔断，允许尝试；
//  3. 同版本失败不重试 + 退避：上次失败的目标版本与本次相同，且仍在退避窗口内
//     → 跳过；窗口已过则允许重试（Attempts 继续累加）。
func ShouldSkipUpdate(state AttemptState, currentVersion, targetVersion string, now int64) (bool, string) {
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
