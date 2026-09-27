// Package selfupdate 实现 jarvis-daemon 的自动更新：解析网关下发的更新指令、
// 下载新版本、校验 sha256、解包并原子替换自身可执行文件。
//
// 设计要点（见 daemon/docs/daemon-self-update-protocol.md）：
//   - 只从 HTTPS 的 GitHub 域名下载（白名单校验，防 SSRF / 中间人）；
//   - 下载后流式校验 sha256（网关未提供校验值时跳过并记警告）；
//   - 解包只取 jarvis-daemon[.exe]，标准库实现，零第三方依赖；
//   - 替换采用「同目录临时文件 + rename」，失败不破坏现有可执行文件；
//   - 只关注 Windows 与 Linux（不含 macOS）。
//
// 平台差异（替换运行中的可执行文件）由带构建标签的文件实现：
//   - apply_linux.go：直接 rename 覆盖（运行中的文件可被替换）；
//   - apply_windows.go：运行中的 exe 无法覆盖，需 helper 子进程在父进程退出后替换。
package selfupdate

import (
	"archive/tar"
	"archive/zip"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// 下载与网络相关常量。
const (
	// downloadTimeout 是单次下载的整体超时。二进制约几 MiB～十几 MiB，
	// 5 分钟足以覆盖慢速网络，又不会让失败请求无限挂起。
	downloadTimeout = 5 * time.Minute
	// maxDownloadBytes 是下载体积上限（64 MiB）。正常产物远小于此值，
	// 设上限是为了防止被恶意/异常的大文件拖垮磁盘与内存。
	maxDownloadBytes = 64 << 20
)

// allowedDownloadHosts 是允许下载更新的主机白名单（小写）。
//
// 为什么需要：更新会替换本机可执行文件，属于高危操作；若允许任意 URL，
// 攻击者可通过伪造网关响应实现 SSRF 或投毒。限定为 GitHub 官方域名后，
// 即便网关被攻破，也只能把用户导向 GitHub 上的产物（可审计）。
var allowedDownloadHosts = map[string]bool{
	"github.com":                    true,
	"objects.githubusercontent.com": true,
}

// extraAllowedHosts 仅供测试注入额外白名单主机（如 httptest 的 127.0.0.1:port）。
//
// 生产代码不会写入它；测试通过 setExtraAllowedHosts 临时添加并在结束后清空。
var extraAllowedHosts = map[string]bool{}

// setExtraAllowedHosts 临时把 hosts 加入下载白名单（仅测试用）。
func setExtraAllowedHosts(hosts ...string) {
	extraAllowedHosts = map[string]bool{}
	for _, h := range hosts {
		extraAllowedHosts[strings.ToLower(h)] = true
	}
}

// allowInsecureForTest 仅供测试：为 true 时放宽 https 要求（httptest 只提供 http）。
var allowInsecureForTest bool

// setAllowInsecureForTest 设置测试用的「允许 http」开关。
func setAllowInsecureForTest(v bool) { allowInsecureForTest = v }

// UpdateInfo 是网关随 hello_ack 下发的更新指令（对应 daemon_update 对象）。
//
// 字段与设计文档的 JSON schema 一一对应；全部可选，缺失时按零值处理。
type UpdateInfo struct {
	// Available 表示网关判断「需要更新」。为 false 时其余字段无意义。
	Available bool `json:"available"`
	// LatestVersion 是最新版本号（如 v1.2.0）。
	LatestVersion string `json:"latest_version"`
	// CurrentVersion 是网关记录的当前版本号（便于日志对照）。
	CurrentVersion string `json:"current_version"`
	// URL 是新版本产物的下载地址（必须为 HTTPS 的 GitHub 域名）。
	URL string `json:"url"`
	// SHA256 是产物的 sha256（小写 hex）；为空时跳过校验并记警告。
	SHA256 string `json:"sha256"`
	// Size 是产物字节数（可选，用于下载前的粗校验与日志）。
	Size int64 `json:"size"`
	// Asset 是产物文件名（用于日志与解包时定位目标文件）。
	Asset string `json:"asset"`
	// Note 是发布说明摘要（可选，仅用于日志）。
	Note string `json:"note"`
}

// ErrNotAvailable 表示网关未下发更新或无需更新。
var ErrNotAvailable = errors.New("无可用更新")

// ParseUpdateInfo 从 hello_ack 的 daemon_update 原始 map 解析更新指令。
//
// 入参 raw 为 nil 或缺少 available=true 时返回 ErrNotAvailable，
// 使调用方可用 errors.Is 统一判断「无需更新」。
func ParseUpdateInfo(raw map[string]any) (UpdateInfo, error) {
	if raw == nil {
		return UpdateInfo{}, ErrNotAvailable
	}
	// 用 JSON 往返做一次宽松解析：网关侧字段类型可能不完全一致（如 size 为 float64），
	// 借助 encoding/json 的容错（数字→int64）避免逐字段断言的繁琐与出错。
	blob, err := json.Marshal(raw)
	if err != nil {
		return UpdateInfo{}, fmt.Errorf("序列化更新指令失败: %w", err)
	}
	var info UpdateInfo
	if err := json.Unmarshal(blob, &info); err != nil {
		return UpdateInfo{}, fmt.Errorf("解析更新指令失败: %w", err)
	}
	info.URL = strings.TrimSpace(info.URL)
	info.SHA256 = strings.ToLower(strings.TrimSpace(info.SHA256))
	if !info.Available {
		return UpdateInfo{}, ErrNotAvailable
	}
	if info.URL == "" {
		return UpdateInfo{}, fmt.Errorf("更新指令缺少下载地址")
	}
	return info, nil
}

// ValidateDownloadURL 校验下载地址：必须是 HTTPS，且主机在白名单内。
//
// 返回规范化后的 URL 字符串；校验失败返回错误（调用方应记日志并放弃更新）。
func ValidateDownloadURL(rawURL string) (string, error) {
	u, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return "", fmt.Errorf("下载地址非法: %w", err)
	}
	if !strings.EqualFold(u.Scheme, "https") && !allowInsecureForTest {
		return "", fmt.Errorf("下载地址必须为 https，实际 %q", u.Scheme)
	}
	host := strings.ToLower(u.Hostname())
	if !allowedDownloadHosts[host] && !extraAllowedHosts[host] {
		return "", fmt.Errorf("下载地址主机 %q 不在白名单内", host)
	}
	return u.String(), nil
}

// Download 下载 url 到 destPath，并按 wantSHA256（非空时）做流式校验。
//
// 行为：
//   - 带 User-Agent: jarvis-daemon/<version>，便于 GitHub 侧识别来源；
//   - 体积超过 maxDownloadBytes 立即报错；
//   - 边写边算 sha256，避免把整个文件读进内存；
//   - 校验失败时删除已下载文件并返回错误。
//
// wantSHA256 为空时跳过校验（仅记日志由调用方负责），返回 nil。
func Download(client *http.Client, version, rawURL, destPath, wantSHA256 string) error {
	safeURL, err := ValidateDownloadURL(rawURL)
	if err != nil {
		return err
	}
	if client == nil {
		client = &http.Client{Timeout: downloadTimeout}
	}

	req, err := http.NewRequest(http.MethodGet, safeURL, nil)
	if err != nil {
		return fmt.Errorf("构造下载请求失败: %w", err)
	}
	req.Header.Set("User-Agent", "jarvis-daemon/"+version)

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("下载失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("下载失败: HTTP %d", resp.StatusCode)
	}

	// 先写同目录临时文件，成功后再改名到 destPath，避免半截文件被当成有效产物。
	if err := os.MkdirAll(filepath.Dir(destPath), 0o755); err != nil {
		return fmt.Errorf("创建下载目录失败: %w", err)
	}
	tmp, err := os.CreateTemp(filepath.Dir(destPath), ".jarvis-daemon-dl-*")
	if err != nil {
		return fmt.Errorf("创建临时文件失败: %w", err)
	}
	tmpName := tmp.Name()
	cleanup := func() {
		tmp.Close()
		_ = os.Remove(tmpName)
	}

	hasher := sha256.New()
	// 限制读取上限，超出即报错（io.LimitReader 会在达到上限后返回 EOF，
	// 故用 maxDownloadBytes+1 探测是否超限）。
	limited := io.LimitReader(resp.Body, maxDownloadBytes+1)
	written, err := io.Copy(io.MultiWriter(tmp, hasher), limited)
	if err != nil {
		cleanup()
		return fmt.Errorf("写入下载内容失败: %w", err)
	}
	if written > maxDownloadBytes {
		cleanup()
		return fmt.Errorf("下载体积超过上限 %d 字节", int64(maxDownloadBytes))
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpName)
		return fmt.Errorf("关闭临时文件失败: %w", err)
	}

	if wantSHA256 != "" {
		got := hex.EncodeToString(hasher.Sum(nil))
		if !strings.EqualFold(got, wantSHA256) {
			_ = os.Remove(tmpName)
			return fmt.Errorf("sha256 校验失败: 期望 %s, 实际 %s", wantSHA256, got)
		}
	}

	if err := os.Rename(tmpName, destPath); err != nil {
		_ = os.Remove(tmpName)
		return fmt.Errorf("保存下载文件失败: %w", err)
	}
	return nil
}

// verifySHA256 流式读取 r 并校验其 sha256 是否等于 wantHex（大小写不敏感）。
//
// 单独抽出便于测试与复用；下载流程内联计算哈希以避免二次读取文件。
func verifySHA256(r io.Reader, wantHex string) error {
	h := sha256.New()
	if _, err := io.Copy(h, r); err != nil {
		return fmt.Errorf("读取内容失败: %w", err)
	}
	got := hex.EncodeToString(h.Sum(nil))
	if !strings.EqualFold(got, wantHex) {
		return fmt.Errorf("sha256 校验失败: 期望 %s, 实际 %s", wantHex, got)
	}
	return nil
}

// ExtractBinary 从压缩包（按扩展名判断 .tar.gz/.tgz 或 .zip）中解出目标可执行文件，
// 写入 outPath。targetName 为期望的文件名（如 jarvis-daemon 或 jarvis-daemon.exe）。
//
// 只取压缩包中「基名等于 targetName」的条目，忽略目录与其他文件，避免路径穿越。
func ExtractBinary(archivePath, outPath, targetName string) error {
	lower := strings.ToLower(archivePath)
	switch {
	case strings.HasSuffix(lower, ".tar.gz"), strings.HasSuffix(lower, ".tgz"):
		return extractTarGz(archivePath, outPath, targetName)
	case strings.HasSuffix(lower, ".zip"):
		return extractZip(archivePath, outPath, targetName)
	default:
		return fmt.Errorf("不支持的压缩格式: %s", filepath.Base(archivePath))
	}
}

// extractTarGz 从 .tar.gz 中解出 targetName。
func extractTarGz(archivePath, outPath, targetName string) error {
	f, err := os.Open(archivePath)
	if err != nil {
		return fmt.Errorf("打开压缩包失败: %w", err)
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return fmt.Errorf("解压 gzip 失败: %w", err)
	}
	defer gz.Close()

	tr := tar.NewReader(gz)
	for {
		hdr, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return fmt.Errorf("读取 tar 失败: %w", err)
		}
		if hdr.Typeflag != tar.TypeReg {
			continue
		}
		if filepath.Base(hdr.Name) != targetName {
			continue
		}
		return writeExecutable(outPath, tr)
	}
	return fmt.Errorf("压缩包中未找到 %s", targetName)
}

// extractZip 从 .zip 中解出 targetName。
func extractZip(archivePath, outPath, targetName string) error {
	zr, err := zip.OpenReader(archivePath)
	if err != nil {
		return fmt.Errorf("打开 zip 失败: %w", err)
	}
	defer zr.Close()
	for _, zf := range zr.File {
		if zf.FileInfo().IsDir() {
			continue
		}
		if filepath.Base(zf.Name) != targetName {
			continue
		}
		rc, err := zf.Open()
		if err != nil {
			return fmt.Errorf("读取 zip 条目失败: %w", err)
		}
		defer rc.Close()
		return writeExecutable(outPath, rc)
	}
	return fmt.Errorf("压缩包中未找到 %s", targetName)
}

// writeExecutable 把 r 的内容写入 outPath 并设置可执行权限（Windows 上忽略）。
func writeExecutable(outPath string, r io.Reader) error {
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return fmt.Errorf("创建输出目录失败: %w", err)
	}
	f, err := os.OpenFile(outPath, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o755)
	if err != nil {
		return fmt.Errorf("创建输出文件失败: %w", err)
	}
	if _, err := io.Copy(f, r); err != nil {
		f.Close()
		_ = os.Remove(outPath)
		return fmt.Errorf("写入可执行文件失败: %w", err)
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(outPath)
		return fmt.Errorf("关闭可执行文件失败: %w", err)
	}
	// Windows 上 Chmod 基本无效，但 Linux 上必须确保可执行位。
	if err := os.Chmod(outPath, 0o755); err != nil {
		return fmt.Errorf("设置可执行权限失败: %w", err)
	}
	return nil
}
