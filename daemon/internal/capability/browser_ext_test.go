package capability

// 本文件测试浏览器扩展包解压与版本读取逻辑（跨平台，无构建标签）。
//
// 测试内用 archive/zip 现场构造 zip，不依赖网络与真实网关；下载相关的
// 网络路径通过 httptest 覆盖（DownloadBrowserExtZip 的成功/失败分支）。

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// zipEntry 描述一个待写入测试 zip 的条目。
type zipEntry struct {
	name  string
	body  string
	isDir bool
	// mode 非 0 时用于设置条目权限位（如 os.ModeSymlink）。
	mode os.FileMode
}

// buildZip 按 entries 构造一个 zip 字节流。
func buildZip(t *testing.T, entries []zipEntry) []byte {
	t.Helper()
	var buf bytes.Buffer
	w := zip.NewWriter(&buf)
	for _, e := range entries {
		hdr := &zip.FileHeader{Name: e.name}
		if e.isDir {
			hdr.Method = zip.Store
			hdr.SetMode(os.ModeDir | 0o755)
		} else if e.mode != 0 {
			hdr.Method = zip.Store
			hdr.SetMode(e.mode)
		} else {
			hdr.Method = zip.Deflate
			hdr.SetMode(0o644)
		}
		fw, err := w.CreateHeader(hdr)
		if err != nil {
			t.Fatalf("创建 zip 条目 %s 失败: %v", e.name, err)
		}
		if !e.isDir {
			if _, err := fw.Write([]byte(e.body)); err != nil {
				t.Fatalf("写入 zip 条目 %s 失败: %v", e.name, err)
			}
		}
	}
	if err := w.Close(); err != nil {
		t.Fatalf("关闭 zip 写入器失败: %v", err)
	}
	return buf.Bytes()
}

// manifestJSON 返回指定版本的 manifest.json 内容。
func manifestJSON(version string) string {
	raw, _ := json.Marshal(map[string]any{
		"manifest_version": 3,
		"name":             "Jarvis Test Extension",
		"version":          version,
	})
	return string(raw)
}

// TestExtractBrowserExtZipOverwrite 验证正常解压覆盖：旧文件被清理、新文件落盘、返回计数正确。
func TestExtractBrowserExtZipOverwrite(t *testing.T) {
	dest := filepath.Join(t.TempDir(), "browser_extension")

	// 先放一个旧版本目录，含一个应被清理的陈旧文件。
	if err := os.MkdirAll(dest, 0o755); err != nil {
		t.Fatalf("准备旧目录失败: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dest, "stale.js"), []byte("old"), 0o644); err != nil {
		t.Fatalf("写入陈旧文件失败: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dest, "manifest.json"), []byte(manifestJSON("1.0.0")), 0o644); err != nil {
		t.Fatalf("写入旧 manifest 失败: %v", err)
	}

	data := buildZip(t, []zipEntry{
		{name: "manifest.json", body: manifestJSON("2.0.0")},
		{name: "background.js", body: "console.log('bg')"},
		{name: "content/", isDir: true},
		{name: "content/inject.js", body: "console.log('inject')"},
	})

	count, err := ExtractBrowserExtZip(data, dest)
	if err != nil {
		t.Fatalf("解压失败: %v", err)
	}
	if count != 3 {
		t.Fatalf("解压文件数应为 3，实际 %d", count)
	}

	// 陈旧文件必须被清理（整体替换语义）。
	if _, err := os.Stat(filepath.Join(dest, "stale.js")); !os.IsNotExist(err) {
		t.Fatalf("陈旧文件 stale.js 应被清理，err=%v", err)
	}
	// 新文件必须存在。
	for _, rel := range []string{"manifest.json", "background.js", "content/inject.js"} {
		if _, err := os.Stat(filepath.Join(dest, rel)); err != nil {
			t.Fatalf("期望文件 %s 不存在: %v", rel, err)
		}
	}
	// 临时目录不得残留。
	parent := filepath.Dir(dest)
	entries, err := os.ReadDir(parent)
	if err != nil {
		t.Fatalf("读取父目录失败: %v", err)
	}
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), ".browser_extension_tmp_") || strings.HasSuffix(e.Name(), ".bak") {
			t.Fatalf("残留临时/备份目录: %s", e.Name())
		}
	}

	version, err := ReadBrowserExtVersion(dest)
	if err != nil {
		t.Fatalf("读取版本失败: %v", err)
	}
	if version != "2.0.0" {
		t.Fatalf("版本应为 2.0.0，实际 %q", version)
	}
}

// TestExtractBrowserExtZipRejectsTraversal 验证路径穿越条目被拒绝，且原目录不被破坏。
func TestExtractBrowserExtZipRejectsTraversal(t *testing.T) {
	cases := []struct {
		name  string
		entry string
	}{
		{"父目录穿越", "../evil.js"},
		{"嵌套穿越", "content/../../evil.js"},
		{"绝对路径", "/etc/evil.js"},
		{"盘符路径", "C:/Windows/evil.js"},
		{"反斜杠穿越", `..\evil.js`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			dest := filepath.Join(t.TempDir(), "browser_extension")
			if err := os.MkdirAll(dest, 0o755); err != nil {
				t.Fatalf("准备旧目录失败: %v", err)
			}
			oldManifest := manifestJSON("1.0.0")
			if err := os.WriteFile(filepath.Join(dest, "manifest.json"), []byte(oldManifest), 0o644); err != nil {
				t.Fatalf("写入旧 manifest 失败: %v", err)
			}

			data := buildZip(t, []zipEntry{
				{name: "manifest.json", body: manifestJSON("2.0.0")},
				{name: tc.entry, body: "pwned"},
			})

			if _, err := ExtractBrowserExtZip(data, dest); err == nil {
				t.Fatalf("越界条目 %q 应被拒绝，但解压成功", tc.entry)
			}
			// 原目录必须保持可用（旧 manifest 未被替换）。
			raw, err := os.ReadFile(filepath.Join(dest, "manifest.json"))
			if err != nil {
				t.Fatalf("原 manifest 丢失: %v", err)
			}
			if string(raw) != oldManifest {
				t.Fatalf("原 manifest 被破坏: %s", string(raw))
			}
		})
	}
}

// TestExtractBrowserExtZipRejectsSymlink 验证符号链接条目被拒绝。
func TestExtractBrowserExtZipRejectsSymlink(t *testing.T) {
	dest := filepath.Join(t.TempDir(), "browser_extension")
	data := buildZip(t, []zipEntry{
		{name: "manifest.json", body: manifestJSON("2.0.0")},
		{name: "link.js", body: "/etc/passwd", mode: os.ModeSymlink | 0o777},
	})

	if _, err := ExtractBrowserExtZip(data, dest); err == nil {
		t.Fatalf("符号链接条目应被拒绝，但解压成功")
	}
	if _, err := os.Stat(dest); !os.IsNotExist(err) {
		t.Fatalf("解压失败后不应创建目标目录，err=%v", err)
	}
}

// TestExtractBrowserExtZipRequiresManifest 验证缺少 manifest.json 时报错且不破坏原目录。
func TestExtractBrowserExtZipRequiresManifest(t *testing.T) {
	dest := filepath.Join(t.TempDir(), "browser_extension")
	if err := os.MkdirAll(dest, 0o755); err != nil {
		t.Fatalf("准备旧目录失败: %v", err)
	}
	oldManifest := manifestJSON("1.0.0")
	if err := os.WriteFile(filepath.Join(dest, "manifest.json"), []byte(oldManifest), 0o644); err != nil {
		t.Fatalf("写入旧 manifest 失败: %v", err)
	}

	data := buildZip(t, []zipEntry{
		{name: "background.js", body: "console.log('bg')"},
	})

	if _, err := ExtractBrowserExtZip(data, dest); err == nil {
		t.Fatalf("缺少 manifest.json 应报错，但解压成功")
	}
	raw, err := os.ReadFile(filepath.Join(dest, "manifest.json"))
	if err != nil {
		t.Fatalf("原 manifest 丢失: %v", err)
	}
	if string(raw) != oldManifest {
		t.Fatalf("原 manifest 被破坏: %s", string(raw))
	}
}

// TestExtractBrowserExtZipInvalidZip 验证非 zip 数据被拒绝。
func TestExtractBrowserExtZipInvalidZip(t *testing.T) {
	dest := filepath.Join(t.TempDir(), "browser_extension")
	if _, err := ExtractBrowserExtZip([]byte("not a zip"), dest); err == nil {
		t.Fatalf("非 zip 数据应被拒绝")
	}
	if _, err := ExtractBrowserExtZip(nil, ""); err == nil {
		t.Fatalf("空目标目录应被拒绝")
	}
}

// TestReadBrowserExtVersion 验证版本读取的正常与异常路径。
func TestReadBrowserExtVersion(t *testing.T) {
	dir := t.TempDir()

	// 正常路径。
	if err := os.WriteFile(filepath.Join(dir, "manifest.json"), []byte(manifestJSON("5.0.5")), 0o644); err != nil {
		t.Fatalf("写入 manifest 失败: %v", err)
	}
	version, err := ReadBrowserExtVersion(dir)
	if err != nil {
		t.Fatalf("读取版本失败: %v", err)
	}
	if version != "5.0.5" {
		t.Fatalf("版本应为 5.0.5，实际 %q", version)
	}

	// 目录不存在。
	if _, err := ReadBrowserExtVersion(filepath.Join(dir, "missing")); err == nil {
		t.Fatalf("目录不存在时应报错")
	}

	// manifest 非法 JSON。
	badDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(badDir, "manifest.json"), []byte("{invalid"), 0o644); err != nil {
		t.Fatalf("写入非法 manifest 失败: %v", err)
	}
	if _, err := ReadBrowserExtVersion(badDir); err == nil {
		t.Fatalf("非法 JSON 应报错")
	}
}

// TestSafeZipEntryPath 验证条目路径规范化与拒绝规则。
func TestSafeZipEntryPath(t *testing.T) {
	cases := []struct {
		name    string
		input   string
		want    string
		wantErr bool
	}{
		{"普通文件", "background.js", "background.js", false},
		{"嵌套文件", "content/inject.js", "content/inject.js", false},
		{"目录条目", "content/", "content", false},
		{"冗余点段", "./content/./a.js", "content/a.js", false},
		{"空条目", "", "", false},
		{"父目录", "../evil.js", "", true},
		{"嵌套父目录", "a/../../evil.js", "", true},
		{"绝对路径", "/etc/passwd", "", true},
		{"盘符", "C:/x.js", "", true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := safeZipEntryPath(tc.input)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("输入 %q 应报错，实际返回 %q", tc.input, got)
				}
				return
			}
			if err != nil {
				t.Fatalf("输入 %q 不应报错: %v", tc.input, err)
			}
			if got != tc.want {
				t.Fatalf("输入 %q 期望 %q，实际 %q", tc.input, tc.want, got)
			}
		})
	}
}

// TestDownloadBrowserExtZip 用 httptest 覆盖下载的成功与失败分支。
func TestDownloadBrowserExtZip(t *testing.T) {
	zipData := buildZip(t, []zipEntry{
		{name: "manifest.json", body: manifestJSON("9.9.9")},
	})

	mux := http.NewServeMux()
	mux.HandleFunc("/api/browser-ext/download", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer good-token" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"bad token"}`))
			return
		}
		w.Header().Set("Content-Type", "application/zip")
		_, _ = w.Write(zipData)
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	// 成功路径。
	data, err := DownloadBrowserExtZip(srv.URL+"/", "good-token")
	if err != nil {
		t.Fatalf("下载失败: %v", err)
	}
	if !bytes.Equal(data, zipData) {
		t.Fatalf("下载内容与源不一致")
	}

	// 参数校验。
	if _, err := DownloadBrowserExtZip("", "good-token"); err == nil {
		t.Fatalf("空网关应报错")
	}
	if _, err := DownloadBrowserExtZip(srv.URL, "  "); err == nil {
		t.Fatalf("空 Token 应报错")
	}

	// 非 200 响应。
	if _, err := DownloadBrowserExtZip(srv.URL, "bad-token"); err == nil {
		t.Fatalf("鉴权失败应报错")
	}
	if _, err := DownloadBrowserExtZip(srv.URL, "bad-token"); err != nil &&
		!strings.Contains(err.Error(), "401") {
		t.Fatalf("错误信息应包含状态码 401，实际: %v", err)
	}
}

// TestHttpGetJSON 覆盖 httpGetJSON 的正常与异常分支。
func TestHttpGetJSON(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/ok", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"latest_version":"5.0.5"}`))
	})
	mux.HandleFunc("/api/bad", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("boom"))
	})
	mux.HandleFunc("/api/notjson", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("plain text"))
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	parsed, err := httpGetJSON(srv.URL, "/api/ok", "tok")
	if err != nil {
		t.Fatalf("正常请求失败: %v", err)
	}
	if parsed["latest_version"] != "5.0.5" {
		t.Fatalf("解析结果不符: %v", parsed)
	}

	if _, err := httpGetJSON(srv.URL, "/api/bad", "tok"); err == nil {
		t.Fatalf("500 响应应报错")
	}
	if _, err := httpGetJSON(srv.URL, "/api/notjson", "tok"); err == nil {
		t.Fatalf("非 JSON 响应应报错")
	}
	if _, err := httpGetJSON(srv.URL, "/api/ok", ""); err == nil {
		t.Fatalf("空 Token 应报错")
	}
}

// TestBrowserExtDirOrEmpty 验证目录解析：正常时非空且以 browser_extension 结尾。
func TestBrowserExtDirOrEmpty(t *testing.T) {
	dir := BrowserExtDirOrEmpty()
	if dir == "" {
		t.Skip("无法确定用户主目录，跳过")
	}
	if filepath.Base(dir) != BrowserExtDirName {
		t.Fatalf("目录应以 %s 结尾，实际 %s", BrowserExtDirName, dir)
	}
	if !strings.Contains(dir, ".jarvis") {
		t.Fatalf("目录应位于 ~/.jarvis 下，实际 %s", dir)
	}
}
