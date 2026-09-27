package capability

import "testing"

// TestAutoUpdateDaemon_DefaultOff 校验：默认关闭。
func TestAutoUpdateDaemon_DefaultOff(t *testing.T) {
	SetAutoUpdateDaemon(false)
	if AutoUpdateDaemon() {
		t.Fatal("默认应为关闭")
	}
}

// TestAutoUpdateDaemon_Toggle 校验：设置后能读回。
func TestAutoUpdateDaemon_Toggle(t *testing.T) {
	SetAutoUpdateDaemon(true)
	if !AutoUpdateDaemon() {
		t.Fatal("设置 true 后应返回 true")
	}
	SetAutoUpdateDaemon(false)
	if AutoUpdateDaemon() {
		t.Fatal("设置 false 后应返回 false")
	}
}
