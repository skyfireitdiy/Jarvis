package selfupdate

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// TokenState 是更新前临时落盘的凭据快照，用于「更新→重启」后恢复登录态。
//
// 为什么需要：daemon 的 Token 默认只存内存、不落盘（见 internal/auth/store.go），
// 进程重启即失效。自动更新会重启服务，若不临时保存，重启后 daemon 会一直处于
// 未认证状态，直到用户下次打开网页重新推送。
//
// 安全边界：该文件**仅在自更新窗口内存在**，重启后由 daemon 启动时一次性读取并
// **立即删除**，不构成长期凭据持久化；文件权限设为 0600（仅属主可读写）。
type TokenState struct {
	// Gateway 是网关地址（规范化前的原始值）。
	Gateway string `json:"gateway"`
	// Token 是网关 JWT。
	Token string `json:"token"`
	// Name 是终端名称（可为空）。
	Name string `json:"name"`
	// SavedAtUnix 是落盘时间（Unix 秒），用于排查。
	SavedAtUnix int64 `json:"saved_at_unix"`
	// ExpiresAtUnix 是凭据过期时间（Unix 秒）；0 表示不过期。
	//
	// 与设计文档的 expires_at 对应：网关 JWT 若带 exp，可在此填入以便启动时判断是否仍可用。
	ExpiresAtUnix int64 `json:"expires_at"`
}

// TokenStatePath 返回临时凭据文件的路径：~/.jarvis/daemon/update-token.json。
//
// 与配置文件（config.DefaultPath）同目录，便于用户排查。
func TokenStatePath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("获取用户主目录失败: %w", err)
	}
	return filepath.Join(home, ".jarvis", "daemon", "update-token.json"), nil
}

// SaveTokenState 把凭据快照写入临时文件（0600）。
//
// 目录不存在时自动创建。写入失败返回错误，调用方应记日志但不阻断更新流程
// （最坏情况只是重启后需重新推送凭据）。
func SaveTokenState(state TokenState) error {
	path, err := TokenStatePath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("创建凭据目录失败: %w", err)
	}
	blob, err := json.Marshal(state)
	if err != nil {
		return fmt.Errorf("序列化凭据失败: %w", err)
	}
	// 先写临时文件再 rename，避免半截文件；权限 0600。
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, blob, 0o600); err != nil {
		return fmt.Errorf("写入凭据临时文件失败: %w", err)
	}
	_ = os.Chmod(tmp, 0o600)
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return fmt.Errorf("保存凭据文件失败: %w", err)
	}
	return nil
}

// LoadAndClearTokenState 读取并**立即删除**临时凭据文件。
//
// 返回：
//   - state, true：成功读取到有效凭据（文件已删除）；
//   - zero, false：文件不存在或解析失败（不报错，调用方静默跳过）。
//
// 为什么读取后立即删除：该文件是一次性中转，避免长期驻留磁盘造成凭据泄露风险。
func LoadAndClearTokenState() (TokenState, bool) {
	path, err := TokenStatePath()
	if err != nil {
		return TokenState{}, false
	}
	blob, err := os.ReadFile(path)
	if err != nil {
		return TokenState{}, false
	}
	// 无论解析是否成功都删除文件（一次性语义）。
	defer func() { _ = os.Remove(path) }()

	var state TokenState
	if err := json.Unmarshal(blob, &state); err != nil {
		return TokenState{}, false
	}
	if state.Gateway == "" || state.Token == "" {
		return TokenState{}, false
	}
	// 过期判断：ExpiresAtUnix 为 0 表示不校验；否则必须晚于当前时间。
	if state.ExpiresAtUnix > 0 && state.ExpiresAtUnix <= time.Now().Unix() {
		return TokenState{}, false
	}
	return state, true
}
