package capability

// 本文件实现「浏览器扩展自动下载与更新」能力的注册与处理逻辑（跨平台共享）。
//
// 平台差异只体现在 Platform 字段（windows / linux），参数与返回结构完全一致，
// 因此注册与处理逻辑放在这里，由 registry_windows.go / registry_linux.go 按
// 平台调用 registerBrowserExt(reg, platform)。

import (
	"fmt"
	"strings"
)

// registerBrowserExt 注册指定平台的浏览器扩展能力。
func registerBrowserExt(reg *Registry, platform Platform) {
	_ = reg.Register(Capability{
		Name: "browser.ext.status",
		Description: "查询本机浏览器扩展的本地副本状态：本地目录、本地版本、网关最新版本。" +
			"用于判断是否需要执行 browser.ext.sync。本地未安装时 local_version 为空串。",
		Platform: platform,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"gateway": map[string]any{
					"type": "string",
					"description": "可选。指定网关地址；提供时若该网关有可用 Token，" +
						"则一并返回网关侧最新版本（latest_version）。",
				},
			},
		},
		Handler: handleBrowserExtStatus,
	})

	_ = reg.Register(Capability{
		Name: "browser.ext.sync",
		Description: "从网关下载浏览器扩展 zip 包并解压覆盖到本地目录（~/.jarvis/browser_extension）。" +
			"不重启浏览器：落盘后需用户在 chrome://extensions 手动点一次「刷新」使新版本生效。",
		Platform: platform,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"gateway": map[string]any{
					"type": "string",
					"description": "网关地址（如 http://127.0.0.1:8000）。" +
						"省略时使用 daemon 已认证的第一个网关。",
				},
			},
		},
		Handler: handleBrowserExtSync,
	})
}

// handleBrowserExtStatus 是 browser.ext.status 的实现。
func handleBrowserExtStatus(params map[string]any) (any, error) {
	dir, err := BrowserExtDir()
	if err != nil {
		return nil, err
	}
	localVersion := LocalBrowserExtVersion()

	result := map[string]any{
		"ext_dir":       dir,
		"local_version": localVersion,
		"installed":     localVersion != "",
	}

	gateway, err := browserExtOptionalString(params, "gateway")
	if err != nil {
		return nil, err
	}
	if gateway != "" {
		result["gateway"] = gateway
		if token, ok := browserExtToken(gateway); ok && token != "" {
			result["token_available"] = true
			if latest, err := fetchRemoteExtVersion(gateway, token); err == nil {
				result["latest_version"] = latest
				result["needs_update"] = latest != "" && latest != localVersion
			} else {
				result["version_error"] = err.Error()
			}
		} else {
			result["token_available"] = false
		}
	}
	return result, nil
}

// handleBrowserExtSync 是 browser.ext.sync 的实现。
func handleBrowserExtSync(params map[string]any) (any, error) {
	gateway, err := browserExtOptionalString(params, "gateway")
	if err != nil {
		return nil, err
	}
	gateway = strings.TrimSpace(gateway)
	if gateway == "" {
		return nil, fmt.Errorf("必须指定 gateway 参数（浏览器扩展同步需要知道从哪个网关下载）")
	}

	token, ok := browserExtToken(gateway)
	if !ok || token == "" {
		return nil, fmt.Errorf("网关 %s 没有可用凭据，请先在网页中登录并推送登录信息", gateway)
	}

	dir, err := BrowserExtDir()
	if err != nil {
		return nil, err
	}
	before := LocalBrowserExtVersion()

	count, version, err := SyncBrowserExt(gateway, token)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"gateway":           gateway,
		"ext_dir":           dir,
		"file_count":        count,
		"version":           version,
		"previous":          before,
		"updated":           version != before,
		"need_reload":       true,
		"reload_hint":       "请在浏览器打开 chrome://extensions，找到 Jarvis Browser Bridge 点击「刷新」；若未安装请点「加载已解压的扩展程序」选择该目录。",
		"browser_restarted": false,
	}, nil
}

// browserExtOptionalString 读取可选字符串参数；缺失或为 nil 时返回空串。
//
// 不复用平台侧（linux/windows）的 optionalString：那些函数带构建标签，在
// darwin 等平台上不参与编译，而本文件是跨平台共享的。
func browserExtOptionalString(params map[string]any, key string) (string, error) {
	v, ok := params[key]
	if !ok || v == nil {
		return "", nil
	}
	s, ok := v.(string)
	if !ok {
		return "", fmt.Errorf("参数 %s 必须是字符串，实际 %T", key, v)
	}
	return s, nil
}

// fetchRemoteExtVersion 查询网关侧扩展最新版本。
//
// 复用 /api/browser-ext/version 接口；只在 status 能力中被调用，失败不致命。
func fetchRemoteExtVersion(gateway, token string) (string, error) {
	body, err := httpGetJSON(gateway, "/api/browser-ext/version", token)
	if err != nil {
		return "", err
	}
	version, _ := body["latest_version"].(string)
	return strings.TrimSpace(version), nil
}
