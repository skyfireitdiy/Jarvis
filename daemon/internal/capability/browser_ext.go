package capability

// 本文件实现「浏览器扩展自动下载与更新」的公共逻辑（跨平台，无构建标签）。
//
// 背景：网关提供 GET /api/browser-ext/download，动态打包仓库根目录的
// browser_extension/ 为 zip（内容为扩展源码，非 crx）。守护进程从网关拉取该
// zip 并解压覆盖到本地固定目录 ~/.jarvis/browser_extension，使本地扩展副本
// 与网关版本保持一致；用户只需在 chrome://extensions 点一次「刷新」即可生效
// （Chrome/Edge 不允许外部程序热重载已加载的 unpacked 扩展，也不允许静默安装）。
//
// 平台差异（凭据来源、目录解析）由带构建标签的文件实现，本文件只放两端共用的
// 纯逻辑：目录解析、HTTP 下载、zip 解压覆盖、版本读取。

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"
)

// BrowserExtDirName 是扩展在本地的固定目录名（位于 ~/.jarvis 下）。
//
// 刻意不按版本分目录：需求是「解压覆盖原来的目录」，且浏览器加载的是该
// 目录路径，路径一旦变化就需要用户重新选择目录，故保持路径恒定。
const BrowserExtDirName = "browser_extension"

// browserExtDownloadTimeout 是下载扩展 zip 的整体超时。
//
// 扩展源码包含若干 JS/HTML，压缩后通常几十 KB；60s 足够覆盖慢速网络，
// 同时避免网关无响应时守护进程长时间挂起。
const browserExtDownloadTimeout = 60 * time.Second

// browserExtMaxZipBytes 是允许下载的 zip 最大字节数（64 MiB）。
//
// 扩展源码远小于该值；设上限是为了防止异常响应（如网关返回错误页面被误当
// 二进制、或恶意构造的超大响应）撑爆内存。
const browserExtMaxZipBytes = 64 << 20

// BrowserExtDir 返回本机扩展目录：~/.jarvis/browser_extension。
//
// Windows 下 os.UserHomeDir 返回 %USERPROFILE%，与既有 config.DefaultPath
// 的 ~/.jarvis 约定一致。
func BrowserExtDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("无法确定用户主目录: %w", err)
	}
	return filepath.Join(home, ".jarvis", BrowserExtDirName), nil
}

// DownloadBrowserExtZip 从网关下载扩展 zip 包。
//
// gateway 形如 http://127.0.0.1:8000 或 https://jvs-ai.cn（末尾斜杠可有可无）；
// token 是网关 JWT，作为 Authorization: Bearer 发送。
func DownloadBrowserExtZip(gateway, token string) ([]byte, error) {
	gateway = strings.TrimRight(strings.TrimSpace(gateway), "/")
	if gateway == "" {
		return nil, fmt.Errorf("网关地址为空，无法下载扩展包")
	}
	if strings.TrimSpace(token) == "" {
		return nil, fmt.Errorf("网关 %s 没有可用 Token，无法下载扩展包", gateway)
	}

	url := gateway + "/api/browser-ext/download"
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("构造下载请求失败: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)

	client := &http.Client{Timeout: browserExtDownloadTimeout}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("下载扩展包失败（%s）: %w", url, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		// 读取少量响应体用于排查（如网关返回的 JSON 错误信息）。
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("下载扩展包失败（HTTP %d）: %s",
			resp.StatusCode, strings.TrimSpace(string(body)))
	}

	limited := io.LimitReader(resp.Body, browserExtMaxZipBytes+1)
	data, err := io.ReadAll(limited)
	if err != nil {
		return nil, fmt.Errorf("读取扩展包响应失败: %w", err)
	}
	if len(data) > browserExtMaxZipBytes {
		return nil, fmt.Errorf("扩展包超过大小上限 %d 字节", browserExtMaxZipBytes)
	}
	if len(data) == 0 {
		return nil, fmt.Errorf("网关返回了空的扩展包")
	}
	return data, nil
}

// httpGetJSON 向网关发起带 Token 的 GET 请求并解析 JSON 响应体。
//
// 供版本查询等轻量接口复用；非 200 时返回含状态码与响应片段的错误。
func httpGetJSON(gateway, apiPath, token string) (map[string]any, error) {
	gateway = strings.TrimRight(strings.TrimSpace(gateway), "/")
	if gateway == "" {
		return nil, fmt.Errorf("网关地址为空")
	}
	if strings.TrimSpace(token) == "" {
		return nil, fmt.Errorf("网关 %s 没有可用 Token", gateway)
	}

	url := gateway + apiPath
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("构造请求失败: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)

	client := &http.Client{Timeout: browserExtDownloadTimeout}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("请求 %s 失败: %w", url, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, fmt.Errorf("读取 %s 响应失败: %w", url, err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("请求 %s 失败（HTTP %d）: %s",
			url, resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var parsed map[string]any
	if err := json.Unmarshal(body, &parsed); err != nil {
		return nil, fmt.Errorf("解析 %s 响应失败: %w", url, err)
	}
	return parsed, nil
}

// ExtractBrowserExtZip 解压扩展 zip 并覆盖到 destDir。
//
// 采用「先解压到同级临时目录，校验通过后整体替换」的策略，保证：
//   - 中途失败不会留下半成品目录（原目录保持可用）；
//   - 旧版本文件被清理，不会残留已删除的文件。
//
// 安全检查：
//   - 拒绝绝对路径与含 ".." 的条目（防路径穿越写出到目标目录之外）；
//   - 拒绝符号链接条目（zip 中符号链接可能指向任意位置）；
//   - 解压后必须存在 manifest.json，否则视为非法扩展包。
//
// 返回解压出的文件数量。
func ExtractBrowserExtZip(data []byte, destDir string) (int, error) {
	if destDir == "" {
		return 0, fmt.Errorf("目标目录为空")
	}
	reader, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return 0, fmt.Errorf("扩展包不是合法的 zip: %w", err)
	}

	parent := filepath.Dir(destDir)
	if err := os.MkdirAll(parent, 0o755); err != nil {
		return 0, fmt.Errorf("创建父目录 %s 失败: %w", parent, err)
	}
	tmpDir, err := os.MkdirTemp(parent, ".browser_extension_tmp_")
	if err != nil {
		return 0, fmt.Errorf("创建临时目录失败: %w", err)
	}
	// 成功替换后 tmpDir 已不存在，RemoveAll 是幂等的；失败时负责清理。
	defer os.RemoveAll(tmpDir)

	count, err := extractZipEntries(reader, tmpDir)
	if err != nil {
		return 0, err
	}

	manifestPath := filepath.Join(tmpDir, "manifest.json")
	if info, statErr := os.Stat(manifestPath); statErr != nil || info.IsDir() {
		return 0, fmt.Errorf("扩展包缺少 manifest.json，不是合法的扩展目录")
	}

	if err := replaceDir(tmpDir, destDir); err != nil {
		return 0, err
	}
	return count, nil
}

// extractZipEntries 把 zip 条目解压到 targetDir，返回解压文件数。
//
// 目录条目会被显式创建；文件条目按需创建父目录后写入。
func extractZipEntries(reader *zip.Reader, targetDir string) (int, error) {
	count := 0
	for _, entry := range reader.File {
		rel, err := safeZipEntryPath(entry.Name)
		if err != nil {
			return 0, err
		}
		if rel == "" {
			continue
		}
		dest := filepath.Join(targetDir, filepath.FromSlash(rel))

		if entry.FileInfo().IsDir() {
			if err := os.MkdirAll(dest, 0o755); err != nil {
				return 0, fmt.Errorf("创建目录 %s 失败: %w", dest, err)
			}
			continue
		}
		// 符号链接条目一律拒绝：解压出的链接可能指向目标目录之外。
		if entry.Mode()&os.ModeSymlink != 0 {
			return 0, fmt.Errorf("扩展包含符号链接条目 %s，已拒绝", entry.Name)
		}

		if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
			return 0, fmt.Errorf("创建目录 %s 失败: %w", filepath.Dir(dest), err)
		}
		if err := writeZipEntry(entry, dest); err != nil {
			return 0, err
		}
		count++
	}
	return count, nil
}

// writeZipEntry 把单个 zip 条目写入 dest 文件。
func writeZipEntry(entry *zip.File, dest string) error {
	src, err := entry.Open()
	if err != nil {
		return fmt.Errorf("打开扩展包条目 %s 失败: %w", entry.Name, err)
	}
	defer src.Close()

	out, err := os.OpenFile(dest, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o644)
	if err != nil {
		return fmt.Errorf("创建文件 %s 失败: %w", dest, err)
	}
	if _, err := io.Copy(out, src); err != nil {
		out.Close()
		return fmt.Errorf("写入文件 %s 失败: %w", dest, err)
	}
	if err := out.Close(); err != nil {
		return fmt.Errorf("关闭文件 %s 失败: %w", dest, err)
	}
	return nil
}

// safeZipEntryPath 校验并规范化 zip 条目名，返回以 "/" 分隔的相对路径。
//
// 目录条目（以 "/" 结尾）返回去掉末尾斜杠的路径；空条目返回空串。
// 绝对路径、盘符路径、含 ".." 的路径一律拒绝。
func safeZipEntryPath(name string) (string, error) {
	cleaned := strings.ReplaceAll(name, "\\", "/")
	// 绝对路径条目一律拒绝：filepath.Join 在部分平台会忽略前缀，行为不可预期。
	if strings.HasPrefix(cleaned, "/") {
		return "", fmt.Errorf("扩展包含绝对路径条目 %s，已拒绝", name)
	}
	cleaned = strings.TrimSuffix(cleaned, "/")
	if cleaned == "" {
		return "", nil
	}
	// 盘符形式（如 C:/xxx）在 Windows 上会被 filepath.Join 视为绝对路径。
	if len(cleaned) >= 2 && cleaned[1] == ':' {
		return "", fmt.Errorf("扩展包含绝对路径条目 %s，已拒绝", name)
	}
	if cleaned == ".." || strings.HasPrefix(cleaned, "../") ||
		strings.Contains(cleaned, "/../") || strings.HasSuffix(cleaned, "/..") {
		return "", fmt.Errorf("扩展包含越界路径条目 %s，已拒绝", name)
	}
	// path.Clean 进一步消除 "./" 等冗余段，得到规范相对路径。
	normalized := path.Clean(cleaned)
	if normalized == "." || normalized == ".." || strings.HasPrefix(normalized, "../") {
		return "", fmt.Errorf("扩展包含越界路径条目 %s，已拒绝", name)
	}
	return normalized, nil
}

// replaceDir 用 srcDir 的内容整体替换 destDir。
//
// 先把 destDir 重命名为备份目录，再把 srcDir 重命名为 destDir，最后删除备份；
// 若第二步失败则回滚备份，避免目标目录丢失。
func replaceDir(srcDir, destDir string) error {
	backupDir := ""
	if _, err := os.Stat(destDir); err == nil {
		backupDir = destDir + ".bak"
		_ = os.RemoveAll(backupDir)
		if err := os.Rename(destDir, backupDir); err != nil {
			return fmt.Errorf("备份原扩展目录 %s 失败: %w", destDir, err)
		}
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("检查扩展目录 %s 失败: %w", destDir, err)
	}

	if err := os.Rename(srcDir, destDir); err != nil {
		// 回滚：把备份还原回去，保证原目录仍可用。
		if backupDir != "" {
			if rbErr := os.Rename(backupDir, destDir); rbErr != nil {
				return fmt.Errorf("替换扩展目录失败: %w（且回滚失败: %v）", err, rbErr)
			}
		}
		return fmt.Errorf("替换扩展目录 %s 失败: %w", destDir, err)
	}

	if backupDir != "" {
		_ = os.RemoveAll(backupDir)
	}
	return nil
}

// ReadBrowserExtVersion 读取指定扩展目录 manifest.json 中的版本号。
//
// 目录不存在或读取失败时返回空串与错误，由调用方决定如何呈现。
func ReadBrowserExtVersion(dir string) (string, error) {
	manifestPath := filepath.Join(dir, "manifest.json")
	raw, err := os.ReadFile(manifestPath)
	if err != nil {
		return "", fmt.Errorf("读取 %s 失败: %w", manifestPath, err)
	}
	var manifest struct {
		Version string `json:"version"`
	}
	if err := json.Unmarshal(raw, &manifest); err != nil {
		return "", fmt.Errorf("解析 %s 失败: %w", manifestPath, err)
	}
	return strings.TrimSpace(manifest.Version), nil
}

// LocalBrowserExtVersion 返回本地扩展目录的版本号；目录不存在时返回空串。
//
// 与 ReadBrowserExtVersion 的区别：本函数把「未安装」视为正常状态而非错误，
// 供 status 能力直接使用。
func LocalBrowserExtVersion() string {
	dir, err := BrowserExtDir()
	if err != nil {
		return ""
	}
	version, err := ReadBrowserExtVersion(dir)
	if err != nil {
		return ""
	}
	return version
}

// BrowserExtDirOrEmpty 返回本地扩展目录；无法确定主目录时返回空串。
//
// 供日志等「失败也不应中断流程」的场景使用。
func BrowserExtDirOrEmpty() string {
	dir, err := BrowserExtDir()
	if err != nil {
		return ""
	}
	return dir
}

// SyncBrowserExt 从网关下载扩展包并解压覆盖到本地目录。
//
// 返回解压出的文件数与落盘后的版本号；版本号读取失败时返回空串（不视为失败，
// 因为文件已成功落盘）。
func SyncBrowserExt(gateway, token string) (int, string, error) {
	data, err := DownloadBrowserExtZip(gateway, token)
	if err != nil {
		return 0, "", err
	}
	dir, err := BrowserExtDir()
	if err != nil {
		return 0, "", err
	}
	count, err := ExtractBrowserExtZip(data, dir)
	if err != nil {
		return 0, "", err
	}
	version, _ := ReadBrowserExtVersion(dir)
	return count, version, nil
}
