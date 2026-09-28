// 本文件对「跨机文件直传」能力（fs.transfer.push / fs.transfer.pull）做单元测试。
//
// 测试策略：用 httptest 起一个假网关，模拟 /api/node/{id}/file-transfer/{upload|download}
// 两个端点，把分块按 offset 拼装成内存文件（模拟远端落盘），再验证：
//  1. push：本机文件分块上传后，远端拼装内容与源一致，且返回摘要不含内容；
//  2. push 目录：自动 tar 打包，远端收到的 tar 可解出原文件；
//  3. pull：从假网关分块拉取内容落盘，与源一致；
//  4. pull 目录：远端 tar 在本机解包成功；
//  5. 凭据缺失时明确报错；
//  6. 参数校验（缺 gateway / 非法 mode / 非 http 前缀）。
//
// 说明：本文件不带构建标签，Linux 与 Windows 均可编译；仅依赖标准库。

package capability

import (
	"archive/tar"
	"bytes"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// fakeGateway 是一个模拟节点文件直传端点的假网关。
//
// 它把上传的分块按 offset 拼装到 remote 缓冲区（模拟远端落盘），
// 并支持按 offset/length 分块下载该缓冲区。
type fakeGateway struct {
	remote   []byte // 远端「文件」内容（dir 模式下为 tar 字节）
	mode     string
	uploads  int // 收到的上传分块次数
	download int // 收到的下载分块次数
}

func (f *fakeGateway) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// 校验 Token 头，确保能力确实带上了凭据。
		if r.Header.Get("Authorization") != "Bearer test-token" {
			http.Error(w, `{"success":false,"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			http.Error(w, `{"success":false,"error":"bad json"}`, http.StatusBadRequest)
			return
		}

		switch {
		case strings.HasSuffix(r.URL.Path, "/file-transfer/upload"):
			f.handleUpload(w, payload)
		case strings.HasSuffix(r.URL.Path, "/file-transfer/download"):
			f.handleDownload(w, payload)
		default:
			http.Error(w, `{"success":false,"error":"not found"}`, http.StatusNotFound)
		}
	}
}

func (f *fakeGateway) handleUpload(w http.ResponseWriter, payload map[string]any) {
	rawData, _ := payload["data"].(string)
	chunk, err := base64.StdEncoding.DecodeString(rawData)
	if err != nil {
		http.Error(w, `{"success":false,"error":"bad base64"}`, http.StatusBadRequest)
		return
	}
	offset := int(toInt64(payload["offset"]))

	// 首块（truncate=true）清空远端缓冲，模拟网关侧 truncate 语义。
	if trunc, _ := payload["truncate"].(bool); trunc {
		f.remote = nil
	}
	// 按 offset 扩展并写入。
	if need := offset + len(chunk); need > len(f.remote) {
		grown := make([]byte, need)
		copy(grown, f.remote)
		f.remote = grown
	}
	copy(f.remote[offset:], chunk)

	f.uploads++
	writeJSON(w, map[string]any{
		"success": true,
		"data": map[string]any{
			"path":   payload["path"],
			"offset": offset,
			"size":   len(f.remote),
		},
	})
}

func (f *fakeGateway) handleDownload(w http.ResponseWriter, payload map[string]any) {
	offset := int(toInt64(payload["offset"]))
	length := int(toInt64(payload["length"]))
	if offset > len(f.remote) {
		offset = len(f.remote)
	}
	end := offset + length
	if end > len(f.remote) {
		end = len(f.remote)
	}
	chunk := f.remote[offset:end]
	eof := end >= len(f.remote)

	f.download++
	writeJSON(w, map[string]any{
		"success": true,
		"data": map[string]any{
			"path":   payload["path"],
			"offset": offset,
			"size":   len(f.remote),
			"eof":    eof,
			"data":   base64.StdEncoding.EncodeToString(chunk),
		},
	})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// toInt64 把 JSON 数字（float64）转成 int64。
func toInt64(v any) int64 {
	if n, ok := v.(float64); ok {
		return int64(n)
	}
	return 0
}

// setupFakeGateway 启动假网关并把凭据提供器指向 test-token，测试结束自动还原。
func setupFakeGateway(t *testing.T, f *fakeGateway) string {
	t.Helper()
	srv := httptest.NewServer(f.handler())
	t.Cleanup(srv.Close)

	SetBrowserExtCredentialProvider(func(gateway string) (string, bool) {
		return "test-token", true
	})
	t.Cleanup(func() { SetBrowserExtCredentialProvider(nil) })
	return srv.URL
}

// TestTransferPushFileChunked 验证单文件 push：分块上传后远端内容与源一致，
// 且返回摘要只含元信息、不含内容字节。
func TestTransferPushFileChunked(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.bin")
	// 3.5 块内容，覆盖「整除」与「尾块」两种边界。
	content := bytes.Repeat([]byte("abcdefgh"), 1000) // 8000 字节
	if err := os.WriteFile(src, content, 0o644); err != nil {
		t.Fatal(err)
	}

	f := &fakeGateway{}
	gateway := setupFakeGateway(t, f)

	reg := NewRegistry()
	res := reg.Execute("fs.transfer.push", map[string]any{
		"gateway":     gateway,
		"node_id":     "node-1",
		"local_path":  src,
		"remote_path": "/data/src.bin",
		"chunk_size":  float64(3000), // 3 块：3000+3000+2000
	})
	if !res.Success {
		t.Fatalf("push 失败: %s", res.Error)
	}

	if !bytes.Equal(f.remote, content) {
		t.Fatalf("远端内容与源不一致：期望 %d 字节，实际 %d 字节", len(content), len(f.remote))
	}
	if f.uploads != 3 {
		t.Fatalf("期望 3 次上传分块，实际 %d", f.uploads)
	}

	// 摘要校验：含 sha256 与 size，且不含内容。
	summary, ok := res.Data.(*transferRemoteResult)
	if !ok {
		t.Fatalf("返回类型异常: %T", res.Data)
	}
	if summary.SHA256 != TransferBytesSHA256(content) {
		t.Fatalf("sha256 不一致: %s", summary.SHA256)
	}
	if summary.Size != int64(len(content)) {
		t.Fatalf("size 不一致: %d", summary.Size)
	}
	if summary.Direction != "push" || summary.Mode != "file" {
		t.Fatalf("摘要方向/模式异常: %+v", summary)
	}
}

// TestTransferPushEmptyFile 验证空文件也能正常 push（至少发一块）。
func TestTransferPushEmptyFile(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "empty.bin")
	if err := os.WriteFile(src, nil, 0o644); err != nil {
		t.Fatal(err)
	}

	f := &fakeGateway{}
	gateway := setupFakeGateway(t, f)

	reg := NewRegistry()
	res := reg.Execute("fs.transfer.push", map[string]any{
		"gateway":     gateway,
		"node_id":     "node-1",
		"local_path":  src,
		"remote_path": "empty.bin",
	})
	if !res.Success {
		t.Fatalf("push 空文件失败: %s", res.Error)
	}
	if len(f.remote) != 0 {
		t.Fatalf("空文件远端应为 0 字节，实际 %d", len(f.remote))
	}
	if f.uploads != 1 {
		t.Fatalf("空文件期望 1 次上传，实际 %d", f.uploads)
	}
}

// TestTransferPushDirectoryPacksTar 验证目录 push：自动 tar 打包且远端可解出原文件。
func TestTransferPushDirectoryPacksTar(t *testing.T) {
	dir := t.TempDir()
	srcDir := filepath.Join(dir, "mydir")
	if err := os.MkdirAll(filepath.Join(srcDir, "sub"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(srcDir, "a.txt"), []byte("alpha"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(srcDir, "sub", "b.txt"), []byte("beta"), 0o644); err != nil {
		t.Fatal(err)
	}

	f := &fakeGateway{}
	gateway := setupFakeGateway(t, f)

	reg := NewRegistry()
	res := reg.Execute("fs.transfer.push", map[string]any{
		"gateway":     gateway,
		"node_id":     "node-1",
		"local_path":  srcDir,
		"remote_path": "mydir",
		"chunk_size":  float64(512), // 强制多块，验证 tar 分块拼接
	})
	if !res.Success {
		t.Fatalf("push 目录失败: %s", res.Error)
	}

	// 远端收到的应是完整 tar，解包后能读出两个文件。
	got := map[string]string{}
	tr := tar.NewReader(bytes.NewReader(f.remote))
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatalf("解析远端 tar 失败: %v", err)
		}
		if hdr.Typeflag != tar.TypeReg {
			continue
		}
		b, _ := io.ReadAll(tr)
		got[filepath.Base(hdr.Name)] = string(b)
	}
	if got["a.txt"] != "alpha" || got["b.txt"] != "beta" {
		t.Fatalf("远端 tar 内容异常: %+v", got)
	}

	summary := res.Data.(*transferRemoteResult)
	if summary.Mode != "dir" {
		t.Fatalf("期望 mode=dir，实际 %s", summary.Mode)
	}
}

// TestTransferPullFileChunked 验证单文件 pull：分块拉取落盘且内容一致。
func TestTransferPullFileChunked(t *testing.T) {
	content := bytes.Repeat([]byte("0123456789"), 500) // 5000 字节
	f := &fakeGateway{remote: content}
	gateway := setupFakeGateway(t, f)

	dir := t.TempDir()
	dst := filepath.Join(dir, "out.bin")

	reg := NewRegistry()
	res := reg.Execute("fs.transfer.pull", map[string]any{
		"gateway":     gateway,
		"node_id":     "node-1",
		"local_path":  dst,
		"remote_path": "src.bin",
		"chunk_size":  float64(2000), // 3 块
	})
	if !res.Success {
		t.Fatalf("pull 失败: %s", res.Error)
	}

	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, content) {
		t.Fatalf("落盘内容与远端不一致：期望 %d 字节，实际 %d 字节", len(content), len(got))
	}
	if f.download != 3 {
		t.Fatalf("期望 3 次下载分块，实际 %d", f.download)
	}

	summary := res.Data.(*transferRemoteResult)
	if summary.SHA256 != TransferBytesSHA256(content) {
		t.Fatalf("摘要 sha256 不一致: %s", summary.SHA256)
	}
}

// TestTransferPullDirectoryUnpacksTar 验证目录 pull：远端 tar 在本机解包成功。
func TestTransferPullDirectoryUnpacksTar(t *testing.T) {
	// 先造一个 tar 作为「远端目录」。
	var buf bytes.Buffer
	tw := tar.NewWriter(&buf)
	payload := []byte("remote-content")
	hdr := &tar.Header{
		Name:     "remote/hello.txt",
		Mode:     0o644,
		Size:     int64(len(payload)),
		Typeflag: tar.TypeReg,
	}
	if err := tw.WriteHeader(hdr); err != nil {
		t.Fatal(err)
	}
	if _, err := tw.Write(payload); err != nil {
		t.Fatal(err)
	}
	if err := tw.Close(); err != nil {
		t.Fatal(err)
	}

	f := &fakeGateway{remote: buf.Bytes()}
	gateway := setupFakeGateway(t, f)

	dir := t.TempDir()
	dst := filepath.Join(dir, "unpacked")

	reg := NewRegistry()
	res := reg.Execute("fs.transfer.pull", map[string]any{
		"gateway":     gateway,
		"node_id":     "node-1",
		"local_path":  dst,
		"remote_path": "remote",
		"mode":        "dir",
	})
	if !res.Success {
		t.Fatalf("pull 目录失败: %s", res.Error)
	}

	got, err := os.ReadFile(filepath.Join(dst, "remote", "hello.txt"))
	if err != nil {
		t.Fatalf("读取解包文件失败: %v", err)
	}
	if string(got) != "remote-content" {
		t.Fatalf("解包内容异常: %s", got)
	}
}

// TestTransferRequiresCredential 验证无凭据时必须明确报错。
func TestTransferRequiresCredential(t *testing.T) {
	SetBrowserExtCredentialProvider(nil)
	t.Cleanup(func() { SetBrowserExtCredentialProvider(nil) })

	reg := NewRegistry()
	res := reg.Execute("fs.transfer.push", map[string]any{
		"gateway":     "http://127.0.0.1:8000",
		"node_id":     "node-1",
		"local_path":  "/tmp/x",
		"remote_path": "x",
	})
	if res.Success {
		t.Fatalf("无凭据时不应成功")
	}
	if !strings.Contains(res.Error, "凭据") {
		t.Fatalf("错误信息应提示凭据缺失，实际: %s", res.Error)
	}
}

// TestTransferParamValidation 验证参数校验：缺 gateway、非法 mode、非 http 前缀。
func TestTransferParamValidation(t *testing.T) {
	SetBrowserExtCredentialProvider(func(string) (string, bool) { return "t", true })
	t.Cleanup(func() { SetBrowserExtCredentialProvider(nil) })

	reg := NewRegistry()

	cases := []struct {
		name   string
		params map[string]any
		want   string
	}{
		{
			name: "缺少 gateway",
			params: map[string]any{
				"node_id": "n", "local_path": "/tmp/x", "remote_path": "x",
			},
			want: "gateway",
		},
		{
			name: "gateway 非 http 前缀",
			params: map[string]any{
				"gateway": "127.0.0.1:8000", "node_id": "n",
				"local_path": "/tmp/x", "remote_path": "x",
			},
			want: "http://",
		},
		{
			name: "非法 mode",
			params: map[string]any{
				"gateway": "http://127.0.0.1:8000", "node_id": "n",
				"local_path": "/tmp/x", "remote_path": "x", "mode": "weird",
			},
			want: "mode",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			res := reg.Execute("fs.transfer.push", tc.params)
			if res.Success {
				t.Fatalf("期望失败，实际成功: %+v", res.Data)
			}
			if !strings.Contains(res.Error, tc.want) {
				t.Fatalf("错误信息应包含 %q，实际: %s", tc.want, res.Error)
			}
		})
	}
}
