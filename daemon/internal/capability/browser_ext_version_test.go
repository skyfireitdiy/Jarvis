package capability

// 本文件测试扩展版本号比较与「已安装」判定（跨平台，无构建标签）。
//
// 背景：daemon 自动同步浏览器扩展时「只升不降」——同一台机器可能同时连接多个
// 不同版本的网关，若按各自网关下发的版本同步，低版本网关会把本地扩展降级，
// 两个网关交替触发就会反复横跳。版本比较是这条策略的唯一判据，故单独覆盖。

import (
	"os"
	"path/filepath"
	"testing"
)

// TestCompareBrowserExtVersion 覆盖常见版本号形态与不可比较的退化行为。
func TestCompareBrowserExtVersion(t *testing.T) {
	cases := []struct {
		name string
		a    string
		b    string
		want int
	}{
		{"相等", "7.3.2", "7.3.2", 0},
		{"补零相等", "7.3", "7.3.0", 0},
		{"四段补零相等", "7.3.2", "7.3.2.0", 0},
		{"主版本更高", "8.0.0", "7.9.9", 1},
		{"主版本更低", "6.9.9", "7.0.0", -1},
		{"次版本更高", "7.4.0", "7.3.9", 1},
		{"补丁更高", "7.3.10", "7.3.9", 1},
		{"补丁数字比较非字典序", "7.3.10", "7.3.9", 1},
		{"第四段更高", "7.3.2.1", "7.3.2", 1},
		{"第四段更低", "7.3.2", "7.3.2.1", -1},
		{"忽略第五段及以后", "7.3.2.1.9", "7.3.2.1.0", 0},
		{"带后缀视为同版本", "7.3.2-beta", "7.3.2", 0},
		{"带后缀比较数字部分", "7.4.0-rc1", "7.3.2", 1},
		{"两侧空白被忽略", " 7.3.2 ", "7.3.2", 0},
		{"不可解析视为不更高", "abc", "7.3.2", -1},
		{"不可解析（右侧）视为不更高", "7.3.2", "x.y.z", -1},
		{"空串不可解析", "", "7.3.2", -1},
		{"空段不可解析", "7..2", "7.0.2", -1},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := CompareBrowserExtVersion(c.a, c.b); got != c.want {
				t.Fatalf("CompareBrowserExtVersion(%q, %q) = %d，期望 %d", c.a, c.b, got, c.want)
			}
		})
	}
}

// TestCompareBrowserExtVersionAntiDowngrade 从「只升不降」策略角度验证判据：
// 只有当网关版本严格高于本地版本时才应触发同步。
//
// 注意「本地未安装」（localVersion 为空）由调用方单独处理（见
// maybeAutoSyncBrowserExt：空串 + 已安装 = manifest 损坏 → 跳过；空串 + 未安装
// → 允许安装），不经过版本比较，故此处不覆盖该分支。
func TestCompareBrowserExtVersionAntiDowngrade(t *testing.T) {
	shouldSync := func(gatewayVersion, localVersion string) bool {
		return CompareBrowserExtVersion(gatewayVersion, localVersion) > 0
	}
	cases := []struct {
		gateway string
		local   string
		want    bool
	}{
		{"7.4.0", "7.3.2", true},
		{"7.3.2", "7.3.2", false},
		{"7.3.2", "7.4.0", false}, // 本地更高：不降级
		{"7.3.2", "8.0.0", false}, // 本地远高：不降级
		{"garbage", "7.3.2", false},
	}
	for _, c := range cases {
		if got := shouldSync(c.gateway, c.local); got != c.want {
			t.Fatalf("网关 %q / 本地 %q：shouldSync = %v，期望 %v", c.gateway, c.local, got, c.want)
		}
	}
}

// TestBrowserExtInstalled 验证「已安装」判定只看扩展目录内的 manifest.json。
func TestBrowserExtInstalled(t *testing.T) {
	dir := BrowserExtDirOrEmpty()
	if dir == "" {
		t.Skip("无法确定用户主目录，跳过")
	}
	// 该测试依赖真实用户目录，为避免污染用户环境，只在目录原本不存在时验证
	// 「未安装」分支，其余分支用临时目录 + ReadBrowserExtVersion 组合验证。
	if _, err := os.Stat(filepath.Join(dir, "manifest.json")); err == nil {
		if !BrowserExtInstalled() {
			t.Fatalf("manifest.json 存在时 BrowserExtInstalled 应为 true")
		}
	} else if BrowserExtInstalled() {
		t.Fatalf("manifest.json 不存在时 BrowserExtInstalled 应为 false")
	}

	// manifest 存在但内容非法：仍应判定为「已安装」（这正是与 LocalBrowserExtVersion
	// 返回值空串的区别所在——自动同步据此跳过而不覆盖用户目录）。
	badDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(badDir, "manifest.json"), []byte("{invalid"), 0o644); err != nil {
		t.Fatalf("写入非法 manifest 失败: %v", err)
	}
	if _, err := ReadBrowserExtVersion(badDir); err == nil {
		t.Fatalf("非法 manifest 应读取失败")
	}
	// 目录不存在 → 未安装。
	if info, err := os.Stat(filepath.Join(badDir, "missing", "manifest.json")); err == nil && !info.IsDir() {
		t.Fatalf("不存在的 manifest 不应被判定为存在")
	}
}
