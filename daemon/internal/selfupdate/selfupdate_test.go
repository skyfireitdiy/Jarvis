package selfupdate

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestParseUpdateInfo_NotAvailable 校验：raw 为 nil / available=false 时返回 ErrNotAvailable。
func TestParseUpdateInfo_NotAvailable(t *testing.T) {
	if _, err := ParseUpdateInfo(nil); !errors.Is(err, ErrNotAvailable) {
		t.Fatalf("nil 应返回 ErrNotAvailable，实际 %v", err)
	}
	if _, err := ParseUpdateInfo(map[string]any{"available": false}); !errors.Is(err, ErrNotAvailable) {
		t.Fatalf("available=false 应返回 ErrNotAvailable，实际 %v", err)
	}
}

// TestParseUpdateInfo_OK 校验：正常字段可解析，且 URL/sha256 被规范化。
func TestParseUpdateInfo_OK(t *testing.T) {
	raw := map[string]any{
		"available":       true,
		"latest_version":  "v1.2.0",
		"current_version": "v1.1.0",
		"url":             "  https://github.com/o/r/releases/download/v1.2.0/a.tar.gz  ",
		"sha256":          "  ABCDEF  ",
		"size":            float64(1234),
		"asset":           "a.tar.gz",
	}
	info, err := ParseUpdateInfo(raw)
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if info.LatestVersion != "v1.2.0" || info.CurrentVersion != "v1.1.0" {
		t.Fatalf("版本字段错误: %+v", info)
	}
	if info.URL != "https://github.com/o/r/releases/download/v1.2.0/a.tar.gz" {
		t.Fatalf("URL 未去空白: %q", info.URL)
	}
	if info.SHA256 != "abcdef" {
		t.Fatalf("sha256 未转小写去空白: %q", info.SHA256)
	}
	if info.Size != 1234 {
		t.Fatalf("size 解析错误: %d", info.Size)
	}
}

// TestParseUpdateInfo_MissingURL 校验：available=true 但缺 url 时报错。
func TestParseUpdateInfo_MissingURL(t *testing.T) {
	if _, err := ParseUpdateInfo(map[string]any{"available": true}); err == nil {
		t.Fatal("缺少 url 应报错")
	}
}

// TestValidateDownloadURL 校验下载地址白名单与 https 约束。
func TestValidateDownloadURL(t *testing.T) {
	ok := []string{
		"https://github.com/o/r/releases/download/v1/a.tar.gz",
		"https://objects.githubusercontent.com/xxx/a.tar.gz",
	}
	for _, u := range ok {
		if _, err := ValidateDownloadURL(u); err != nil {
			t.Errorf("应通过: %s, err=%v", u, err)
		}
	}
	bad := []string{
		"http://github.com/o/r/a.tar.gz",       // 非 https
		"https://evil.com/a.tar.gz",            // 非白名单
		"https://github.com.evil.com/a.tar.gz", // 伪装域名
		"ftp://github.com/a.tar.gz",            // 非 http(s)
		"",
	}
	for _, u := range bad {
		if _, err := ValidateDownloadURL(u); err == nil {
			t.Errorf("应拒绝: %s", u)
		}
	}
}

// TestDownload_SHA256OK 校验：正常下载并校验 sha256 成功（含 User-Agent）。
func TestDownload_SHA256OK(t *testing.T) {
	payload := []byte("hello-jarvis-daemon")
	sum := sha256.Sum256(payload)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.Header.Get("User-Agent"), "jarvis-daemon/") {
			t.Errorf("User-Agent 缺失或错误: %q", r.Header.Get("User-Agent"))
		}
		_, _ = w.Write(payload)
	}))
	defer srv.Close()

	// httptest 监听 127.0.0.1，需临时加入白名单才能通过校验。
	setExtraAllowedHosts("127.0.0.1")
	defer setExtraAllowedHosts()
	setAllowInsecureForTest(true)
	defer setAllowInsecureForTest(false)

	dest := filepath.Join(t.TempDir(), "out.bin")
	if err := Download(nil, "test", srv.URL, dest, hex.EncodeToString(sum[:])); err != nil {
		t.Fatalf("下载应成功: %v", err)
	}
	got, err := os.ReadFile(dest)
	if err != nil || !bytes.Equal(got, payload) {
		t.Fatalf("下载内容不一致: %q err=%v", got, err)
	}
}

// TestDownload_SHA256Mismatch 校验：sha256 不匹配时报错且不留下目标文件。
func TestDownload_SHA256Mismatch(t *testing.T) {
	payload := []byte("hello-jarvis-daemon")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(payload)
	}))
	defer srv.Close()
	setExtraAllowedHosts("127.0.0.1")
	defer setExtraAllowedHosts()
	setAllowInsecureForTest(true)
	defer setAllowInsecureForTest(false)

	dest := filepath.Join(t.TempDir(), "out.bin")
	if err := Download(nil, "test", srv.URL, dest, "deadbeef"); err == nil {
		t.Fatal("sha256 不匹配应报错")
	}
	if _, err := os.Stat(dest); !os.IsNotExist(err) {
		t.Fatalf("校验失败后不应留下目标文件: %v", err)
	}
}

// TestDownload_SkipSHA256 校验：wantSHA256 为空时跳过校验并成功落盘。
func TestDownload_SkipSHA256(t *testing.T) {
	payload := []byte("no-checksum")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(payload)
	}))
	defer srv.Close()
	setExtraAllowedHosts("127.0.0.1")
	defer setExtraAllowedHosts()
	setAllowInsecureForTest(true)
	defer setAllowInsecureForTest(false)

	dest := filepath.Join(t.TempDir(), "out.bin")
	if err := Download(nil, "test", srv.URL, dest, ""); err != nil {
		t.Fatalf("跳过校验时下载应成功: %v", err)
	}
}

// TestVerifySHA256 校验底层 sha256 校验函数。
func TestVerifySHA256(t *testing.T) {
	payload := []byte("hello-jarvis-daemon")
	sum := sha256.Sum256(payload)
	if err := verifySHA256(bytes.NewReader(payload), hex.EncodeToString(sum[:])); err != nil {
		t.Fatalf("sha256 校验应通过: %v", err)
	}
	if err := verifySHA256(bytes.NewReader(payload), "deadbeef"); err == nil {
		t.Fatal("sha256 不匹配应报错")
	}
}

// TestExtractBinary_TarGz 校验从 tar.gz 中解出目标文件。
func TestExtractBinary_TarGz(t *testing.T) {
	dir := t.TempDir()
	archive := filepath.Join(dir, "a.tar.gz")
	want := []byte("binary-content-targz")
	writeTarGz(t, archive, "jarvis-daemon", want)

	out := filepath.Join(dir, "out", "jarvis-daemon")
	if err := ExtractBinary(archive, out, "jarvis-daemon"); err != nil {
		t.Fatalf("解包失败: %v", err)
	}
	got, err := os.ReadFile(out)
	if err != nil {
		t.Fatalf("读取解包结果失败: %v", err)
	}
	if !bytes.Equal(got, want) {
		t.Fatalf("内容不一致: %q", got)
	}
}

// TestExtractBinary_Zip 校验从 zip 中解出目标文件（含目录前缀）。
func TestExtractBinary_Zip(t *testing.T) {
	dir := t.TempDir()
	archive := filepath.Join(dir, "a.zip")
	want := []byte("binary-content-zip")
	writeZip(t, archive, "sub/dir/jarvis-daemon.exe", want)

	out := filepath.Join(dir, "out", "jarvis-daemon.exe")
	if err := ExtractBinary(archive, out, "jarvis-daemon.exe"); err != nil {
		t.Fatalf("解包失败: %v", err)
	}
	got, err := os.ReadFile(out)
	if err != nil {
		t.Fatalf("读取解包结果失败: %v", err)
	}
	if !bytes.Equal(got, want) {
		t.Fatalf("内容不一致: %q", got)
	}
}

// TestExtractBinary_NotFound 校验压缩包中无目标文件时报错。
func TestExtractBinary_NotFound(t *testing.T) {
	dir := t.TempDir()
	archive := filepath.Join(dir, "a.tar.gz")
	writeTarGz(t, archive, "other-file", []byte("x"))
	out := filepath.Join(dir, "out", "jarvis-daemon")
	if err := ExtractBinary(archive, out, "jarvis-daemon"); err == nil {
		t.Fatal("缺少目标文件应报错")
	}
}

// TestExtractBinary_Unsupported 校验不支持的扩展名报错。
func TestExtractBinary_Unsupported(t *testing.T) {
	if err := ExtractBinary("a.rar", "out", "jarvis-daemon"); err == nil {
		t.Fatal("不支持的格式应报错")
	}
}

// writeTarGz 生成一个仅含单文件的 tar.gz。
func writeTarGz(t *testing.T, path, name string, content []byte) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if err := writeTarGzTo(t, f, name, content); err != nil {
		t.Fatal(err)
	}
}

// writeTarGzToBuffer 把单文件 tar.gz 写入内存缓冲（供 httptest 直接返回）。
func writeTarGzToBuffer(t *testing.T, buf *bytes.Buffer, name string, content []byte) {
	t.Helper()
	if err := writeTarGzTo(t, buf, name, content); err != nil {
		t.Fatal(err)
	}
}

// writeTarGzTo 把单文件 tar.gz 写入任意 io.Writer。
func writeTarGzTo(t *testing.T, w io.Writer, name string, content []byte) error {
	t.Helper()
	gz := gzip.NewWriter(w)
	tw := tar.NewWriter(gz)
	if err := tw.WriteHeader(&tar.Header{
		Name:     name,
		Mode:     0o755,
		Size:     int64(len(content)),
		Typeflag: tar.TypeReg,
	}); err != nil {
		return err
	}
	if _, err := tw.Write(content); err != nil {
		return err
	}
	if err := tw.Close(); err != nil {
		return err
	}
	return gz.Close()
}

// writeZip 生成一个仅含单文件的 zip。
func writeZip(t *testing.T, path, name string, content []byte) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	zw := zip.NewWriter(f)
	w, err := zw.Create(name)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Write(content); err != nil {
		t.Fatal(err)
	}
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
}
