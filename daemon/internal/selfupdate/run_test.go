package selfupdate

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

// TestRun_EndToEnd 校验完整流程：下载 → 校验 → 解包 → 替换（不重启）。
//
// 用 httptest 提供 tar.gz 产物，并把 127.0.0.1 临时加入白名单。
func TestRun_EndToEnd(t *testing.T) {
	// 构造 tar.gz 产物，内嵌名为 jarvis-daemon 的可执行文件。
	binaryContent := []byte("fake-daemon-binary-v2")
	var buf bytes.Buffer
	writeTarGzToBuffer(t, &buf, binaryName(), binaryContent)
	payload := buf.Bytes()
	sum := sha256.Sum256(payload)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(payload)
	}))
	defer srv.Close()
	setExtraAllowedHosts("127.0.0.1")
	defer setExtraAllowedHosts()
	setAllowInsecureForTest(true)
	defer setAllowInsecureForTest(false)

	dir := t.TempDir()
	target := filepath.Join(dir, "bin", binaryName())
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, []byte("old-daemon"), 0o755); err != nil {
		t.Fatal(err)
	}

	var states []UpdateState
	err := Run(Options{
		Info: UpdateInfo{
			Available:     true,
			LatestVersion: "v2.0.0",
			URL:           srv.URL + "/" + binaryName() + ".tar.gz",
			SHA256:        hex.EncodeToString(sum[:]),
			Asset:         binaryName() + ".tar.gz",
		},
		Version:    "v1.0.0",
		TargetPath: target,
		WorkDir:    filepath.Join(dir, "work"),
		Restart:    false,
		Report: func(s UpdateState, _ string) {
			states = append(states, s)
		},
	})
	if err != nil {
		t.Fatalf("Run 失败: %v", err)
	}

	got, err := os.ReadFile(target)
	if err != nil {
		t.Fatalf("读取目标失败: %v", err)
	}
	if !bytes.Equal(got, binaryContent) {
		t.Fatalf("目标未更新为新版本: %q", got)
	}
	// 应至少上报 downloading/verifying/applying/done。
	if len(states) == 0 || states[len(states)-1] != StateDone {
		t.Fatalf("状态回执异常: %v", states)
	}
}

// TestRun_NotAvailable 校验：Info.Available=false 时返回 ErrNotAvailable。
func TestRun_NotAvailable(t *testing.T) {
	if err := Run(Options{Info: UpdateInfo{Available: false}, TargetPath: "x"}); err == nil {
		t.Fatal("无可用更新应报错")
	}
}

// TestRun_NoTarget 校验：缺少目标路径时报错。
func TestRun_NoTarget(t *testing.T) {
	if err := Run(Options{Info: UpdateInfo{Available: true}}); err == nil {
		t.Fatal("缺少目标路径应报错")
	}
}

// TestRun_DownloadFails 校验：下载失败时上报 failed 并返回错误。
func TestRun_DownloadFails(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()
	setExtraAllowedHosts("127.0.0.1")
	defer setExtraAllowedHosts()
	setAllowInsecureForTest(true)
	defer setAllowInsecureForTest(false)

	var last UpdateState
	err := Run(Options{
		Info: UpdateInfo{
			Available: true,
			URL:       srv.URL + "/" + binaryName() + ".tar.gz",
		},
		Version:    "v1",
		TargetPath: filepath.Join(t.TempDir(), binaryName()),
		WorkDir:    filepath.Join(t.TempDir(), "work"),
		Report:     func(s UpdateState, _ string) { last = s },
	})
	if err == nil {
		t.Fatal("下载失败应返回错误")
	}
	if last != StateFailed {
		t.Fatalf("应上报 failed，实际 %q", last)
	}
}
