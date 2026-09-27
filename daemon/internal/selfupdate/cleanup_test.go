package selfupdate

import (
	"os"
	"path/filepath"
	"testing"

	"jarvis-daemon/internal/service"
)

// TestCleanupAfterUpdateClearsSettledState 验证「更新已成功到位」时清除尝试状态。
//
// 场景：状态记录 InProgress=true 且目标版本 == 当前运行版本，说明上次更新已生效，
// 应清除状态（否则残留的 InProgress 在网关重复下发同版本时会永久熔断）。
func TestCleanupAfterUpdateClearsSettledState(t *testing.T) {
	withTempHome(t)

	if err := SaveAttemptState(AttemptState{
		TargetVersion:   "6.0.1",
		Attempts:        0,
		LastAttemptUnix: NowUnix(),
		InProgress:      true,
	}); err != nil {
		t.Fatalf("写入尝试状态失败: %v", err)
	}

	CleanupAfterUpdate("v6.0.1")

	if _, ok := LoadAttemptState(); ok {
		t.Fatal("更新已到位时应清除尝试状态，但状态文件仍存在")
	}
}

// TestCleanupAfterUpdateKeepsFailedState 验证失败退避/熔断状态不被误清。
//
// 场景：目标版本与当前版本不同（更新未生效），或 InProgress=false（失败记录），
// 这些状态必须保留，否则会丢失跨重启的退避与熔断保护。
func TestCleanupAfterUpdateKeepsFailedState(t *testing.T) {
	cases := []struct {
		name    string
		state   AttemptState
		version string
	}{
		{
			name: "目标版本与当前版本不同（更新未生效）",
			state: AttemptState{
				TargetVersion:   "6.0.2",
				Attempts:        1,
				LastAttemptUnix: NowUnix(),
				InProgress:      true,
			},
			version: "v6.0.1",
		},
		{
			name: "InProgress=false（失败退避记录）",
			state: AttemptState{
				TargetVersion:   "6.0.1",
				Attempts:        2,
				LastAttemptUnix: NowUnix(),
				LastError:       "下载失败",
				InProgress:      false,
			},
			version: "v6.0.1",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			withTempHome(t)
			if err := SaveAttemptState(tc.state); err != nil {
				t.Fatalf("写入尝试状态失败: %v", err)
			}

			CleanupAfterUpdate(tc.version)

			got, ok := LoadAttemptState()
			if !ok {
				t.Fatal("该场景下尝试状态必须保留，但文件已被删除")
			}
			if got.Attempts != tc.state.Attempts || got.LastError != tc.state.LastError {
				t.Fatalf("状态被意外修改: got=%+v want=%+v", got, tc.state)
			}
		})
	}
}

// TestCleanupAfterUpdateRemovesLeftovers 验证清理 .new / .helper.exe 残留文件。
func TestCleanupAfterUpdateRemovesLeftovers(t *testing.T) {
	withTempHome(t)

	target, err := service.InstalledBinaryPath()
	if err != nil {
		t.Fatalf("获取安装路径失败: %v", err)
	}
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatalf("创建安装目录失败: %v", err)
	}
	leftovers := []string{target + ".new", target + ".helper.exe"}
	for _, p := range leftovers {
		if err := os.WriteFile(p, []byte("stub"), 0o755); err != nil {
			t.Fatalf("创建残留文件 %s 失败: %v", p, err)
		}
	}

	CleanupAfterUpdate("v6.0.1")

	for _, p := range leftovers {
		if _, err := os.Stat(p); !os.IsNotExist(err) {
			t.Fatalf("残留文件 %s 应被删除，stat err=%v", p, err)
		}
	}
}

// TestCleanupAfterUpdateIdempotent 验证无任何残留时调用不报错（幂等）。
func TestCleanupAfterUpdateIdempotent(t *testing.T) {
	withTempHome(t)
	CleanupAfterUpdate("v6.0.1")
	CleanupAfterUpdate("v6.0.1")
}
