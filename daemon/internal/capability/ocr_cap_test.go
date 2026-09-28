// 本文件对「OCR 文字识别」能力（ocr.recognize）做单元测试。
//
// 测试策略：用 httptest 起一个假网关，模拟 POST /api/ocr，验证：
//  1. 本地图片路径：读文件 → base64 → 上传，网关收到的 base64 与源字节一致；
//  2. 图片 URL：daemon 自行下载后再上传；
//  3. 参数校验：image/image_url 都缺、都给、image_url 非 http 前缀都要报错；
//  4. 大小上限：超过 20 MiB 的本地文件被拒；
//  5. 凭据缺失时明确报错；
//  6. 网关返回 success=false 时把 error 透出；
//  7. gateway 缺省时回退到注入的已认证网关列表；
//  8. filename 扩展名归一化（非白名单回退 .png）。
//
// 说明：本文件不带构建标签，Linux 与 Windows 均可编译；仅依赖标准库。
package capability

import (
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

// fakeOcrGateway 是一个模拟网关 /api/ocr 端点的假网关。
type fakeOcrGateway struct {
	t *testing.T
	// 期望的 Token（为空表示不校验）。
	wantToken string
	// 网关返回的响应体。
	response map[string]any
	// 记录收到的请求体，供断言。
	gotPayload map[string]any
	// 记录收到请求的次数。
	calls int
}

func (f *fakeOcrGateway) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/ocr" {
			http.Error(w, `{"success":false,"error":"not found"}`, http.StatusNotFound)
			return
		}
		if f.wantToken != "" && r.Header.Get("Authorization") != "Bearer "+f.wantToken {
			http.Error(w, `{"success":false,"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			http.Error(w, `{"success":false,"error":"bad json"}`, http.StatusBadRequest)
			return
		}
		f.gotPayload = payload
		f.calls++
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(f.response)
	}
}

// withOcrProvider 注入一个固定 Token 的凭据提供器，并在测试结束后还原。
func withOcrProvider(t *testing.T, token string) {
	t.Helper()
	SetBrowserExtCredentialProvider(func(gateway string) (string, bool) {
		if token == "" {
			return "", false
		}
		return token, true
	})
	t.Cleanup(func() { SetBrowserExtCredentialProvider(nil) })
}

// withOcrGatewayList 注入固定的已认证网关列表，并在测试结束后还原。
func withOcrGatewayList(t *testing.T, gateways []string) {
	t.Helper()
	SetOcrGatewayLister(func() []string { return gateways })
	t.Cleanup(func() { SetOcrGatewayLister(nil) })
}

// writeTempImage 在临时目录写一张假图片，返回路径。
func writeTempImage(t *testing.T, name string, data []byte) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatalf("写临时图片失败: %v", err)
	}
	return path
}

// TestOcrRecognizeLocalImage 验证本地图片路径的完整链路。
func TestOcrRecognizeLocalImage(t *testing.T) {
	imageBytes := []byte("fake-png-bytes-\x89PNG\r\n\x1a\n")
	path := writeTempImage(t, "shot.png", imageBytes)

	fake := &fakeOcrGateway{
		wantToken: "test-token",
		response: map[string]any{
			"success": true,
			"text":    "JARVIS OCR 12345",
			"backend": "tesseract",
			"lines":   []any{},
			"error":   "",
		},
	}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()

	withOcrProvider(t, "test-token")

	res, err := handleOcrRecognize(map[string]any{
		"gateway": srv.URL,
		"image":   path,
	})
	if err != nil {
		t.Fatalf("handleOcrRecognize 失败: %v", err)
	}
	result, ok := res.(map[string]any)
	if !ok {
		t.Fatalf("返回值类型错误: %T", res)
	}
	if result["text"] != "JARVIS OCR 12345" {
		t.Errorf("text = %v, 期望 JARVIS OCR 12345", result["text"])
	}
	if result["backend"] != "tesseract" {
		t.Errorf("backend = %v, 期望 tesseract", result["backend"])
	}
	if result["size"] != len(imageBytes) {
		t.Errorf("size = %v, 期望 %d", result["size"], len(imageBytes))
	}
	// 校验上传的 base64 与源字节一致。
	gotB64, _ := fake.gotPayload["image_base64"].(string)
	decoded, err := base64.StdEncoding.DecodeString(gotB64)
	if err != nil {
		t.Fatalf("网关收到的 base64 无法解码: %v", err)
	}
	if string(decoded) != string(imageBytes) {
		t.Errorf("上传字节与源不一致")
	}
	// filename 从 image 路径推断。
	if fake.gotPayload["filename"] != "shot.png" {
		t.Errorf("filename = %v, 期望 shot.png", fake.gotPayload["filename"])
	}
	// 未指定 psm 时应传 null。
	if v, exists := fake.gotPayload["psm"]; !exists || v != nil {
		t.Errorf("psm = %v, 期望 null", v)
	}
	if fake.gotPayload["backend"] != "auto" {
		t.Errorf("backend = %v, 期望默认 auto", fake.gotPayload["backend"])
	}
	if fake.gotPayload["lang"] != "eng" {
		t.Errorf("lang = %v, 期望默认 eng", fake.gotPayload["lang"])
	}
}

// TestOcrRecognizeImageURL 验证 image_url 由 daemon 自行下载后上传。
func TestOcrRecognizeImageURL(t *testing.T) {
	imageBytes := []byte("remote-image-bytes")
	imgSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(imageBytes)
	}))
	defer imgSrv.Close()

	fake := &fakeOcrGateway{
		wantToken: "tok",
		response: map[string]any{
			"success": true,
			"text":    "hello",
			"backend": "rapidocr",
			"lines":   []any{},
		},
	}
	ocrSrv := httptest.NewServer(fake.handler())
	defer ocrSrv.Close()

	withOcrProvider(t, "tok")

	res, err := handleOcrRecognize(map[string]any{
		"gateway":   ocrSrv.URL,
		"image_url": imgSrv.URL + "/a.png",
		"filename":  "a.png",
	})
	if err != nil {
		t.Fatalf("handleOcrRecognize 失败: %v", err)
	}
	result := res.(map[string]any)
	if result["text"] != "hello" {
		t.Errorf("text = %v, 期望 hello", result["text"])
	}
	gotB64, _ := fake.gotPayload["image_base64"].(string)
	decoded, err := base64.StdEncoding.DecodeString(gotB64)
	if err != nil {
		t.Fatalf("base64 解码失败: %v", err)
	}
	if string(decoded) != string(imageBytes) {
		t.Errorf("上传字节与下载源不一致")
	}
}

// TestOcrRecognizeGatewayFallback 验证 gateway 缺省时回退到已认证网关列表。
func TestOcrRecognizeGatewayFallback(t *testing.T) {
	path := writeTempImage(t, "x.png", []byte("bytes"))

	fake := &fakeOcrGateway{
		wantToken: "tok",
		response:  map[string]any{"success": true, "text": "ok", "backend": "tesseract", "lines": []any{}},
	}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()

	withOcrProvider(t, "tok")
	withOcrGatewayList(t, []string{srv.URL})

	res, err := handleOcrRecognize(map[string]any{"image": path})
	if err != nil {
		t.Fatalf("handleOcrRecognize 失败: %v", err)
	}
	result := res.(map[string]any)
	if result["gateway"] != srv.URL {
		t.Errorf("gateway = %v, 期望回退到 %s", result["gateway"], srv.URL)
	}
}

// TestOcrRecognizeNoGateway 验证无 gateway 且无已认证网关时报错。
func TestOcrRecognizeNoGateway(t *testing.T) {
	path := writeTempImage(t, "x.png", []byte("bytes"))
	withOcrProvider(t, "tok")
	withOcrGatewayList(t, nil)

	_, err := handleOcrRecognize(map[string]any{"image": path})
	if err == nil {
		t.Fatal("期望报错，实际成功")
	}
	if !strings.Contains(err.Error(), "没有已认证的网关") {
		t.Errorf("错误信息不明确: %v", err)
	}
}

// TestOcrRecognizeParamValidation 验证参数校验分支。
func TestOcrRecognizeParamValidation(t *testing.T) {
	path := writeTempImage(t, "x.png", []byte("bytes"))
	withOcrProvider(t, "tok")

	cases := []struct {
		name    string
		params  map[string]any
		wantSub string
	}{
		{
			name:    "都缺",
			params:  map[string]any{"gateway": "http://gw"},
			wantSub: "必须提供其中一个",
		},
		{
			name:    "都给",
			params:  map[string]any{"gateway": "http://gw", "image": path, "image_url": "http://x/a.png"},
			wantSub: "只能提供其中一个",
		},
		{
			name:    "image_url 非 http",
			params:  map[string]any{"gateway": "http://gw", "image_url": "ftp://x/a.png"},
			wantSub: "必须以 http:// 或 https:// 开头",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := handleOcrRecognize(tc.params)
			if err == nil {
				t.Fatal("期望报错，实际成功")
			}
			if !strings.Contains(err.Error(), tc.wantSub) {
				t.Errorf("错误信息 %q 不含 %q", err.Error(), tc.wantSub)
			}
		})
	}
}

// TestOcrRecognizeNoToken 验证凭据缺失时报错。
func TestOcrRecognizeNoToken(t *testing.T) {
	path := writeTempImage(t, "x.png", []byte("bytes"))
	withOcrProvider(t, "") // 无凭据

	_, err := handleOcrRecognize(map[string]any{"gateway": "http://gw.example.com", "image": path})
	if err == nil {
		t.Fatal("期望报错，实际成功")
	}
	if !strings.Contains(err.Error(), "没有可用凭据") {
		t.Errorf("错误信息不明确: %v", err)
	}
}

// TestOcrRecognizeLocalFileMissing 验证本地文件不存在时报错。
func TestOcrRecognizeLocalFileMissing(t *testing.T) {
	withOcrProvider(t, "tok")
	_, err := handleOcrRecognize(map[string]any{
		"gateway": "http://gw.example.com",
		"image":   filepath.Join(t.TempDir(), "not-exist.png"),
	})
	if err == nil {
		t.Fatal("期望报错，实际成功")
	}
	if !strings.Contains(err.Error(), "读取本地图片") {
		t.Errorf("错误信息不明确: %v", err)
	}
}

// TestOcrRecognizeGatewayFailure 验证网关 success=false 时把 error 透出。
func TestOcrRecognizeGatewayFailure(t *testing.T) {
	path := writeTempImage(t, "x.png", []byte("bytes"))
	fake := &fakeOcrGateway{
		wantToken: "tok",
		response: map[string]any{
			"success": false,
			"error":   "没有可用的 OCR 后端",
		},
	}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()
	withOcrProvider(t, "tok")

	_, err := handleOcrRecognize(map[string]any{"gateway": srv.URL, "image": path})
	if err == nil {
		t.Fatal("期望报错，实际成功")
	}
	if !strings.Contains(err.Error(), "没有可用的 OCR 后端") {
		t.Errorf("未透出网关错误: %v", err)
	}
}

// TestOcrRecognizeOversizeLocalFile 验证本地文件超过 20 MiB 被拒（不发起请求）。
func TestOcrRecognizeOversizeLocalFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "big.png")
	f, err := os.Create(path)
	if err != nil {
		t.Fatalf("创建大文件失败: %v", err)
	}
	// 只写 20 MiB + 1 字节，避免测试过慢。
	if err := f.Truncate(ocrMaxImageBytes + 1); err != nil {
		f.Close()
		t.Fatalf("truncate 失败: %v", err)
	}
	f.Close()

	fake := &fakeOcrGateway{wantToken: "tok", response: map[string]any{"success": true}}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()
	withOcrProvider(t, "tok")

	_, err = handleOcrRecognize(map[string]any{"gateway": srv.URL, "image": path})
	if err == nil {
		t.Fatal("期望报错，实际成功")
	}
	if !strings.Contains(err.Error(), "超出上限") {
		t.Errorf("错误信息不明确: %v", err)
	}
	if fake.calls != 0 {
		t.Errorf("超限时不应发起请求，实际发起 %d 次", fake.calls)
	}
}

// TestOcrRecognizeDetailAndPsm 验证 detail/psm 透传。
func TestOcrRecognizeDetailAndPsm(t *testing.T) {
	path := writeTempImage(t, "x.png", []byte("bytes"))
	fake := &fakeOcrGateway{
		wantToken: "tok",
		response: map[string]any{
			"success": true,
			"text":    "ok",
			"backend": "tesseract",
			"lines":   []any{map[string]any{"text": "ok", "confidence": 0.9}},
		},
	}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()
	withOcrProvider(t, "tok")

	res, err := handleOcrRecognize(map[string]any{
		"gateway": srv.URL,
		"image":   path,
		"psm":     float64(7), // 模拟 JSON 反序列化后的数字类型
		"detail":  true,
		"lang":    "chi_sim+eng",
	})
	if err != nil {
		t.Fatalf("handleOcrRecognize 失败: %v", err)
	}
	if fake.gotPayload["psm"] != float64(7) {
		t.Errorf("psm = %v, 期望 7", fake.gotPayload["psm"])
	}
	if fake.gotPayload["detail"] != true {
		t.Errorf("detail = %v, 期望 true", fake.gotPayload["detail"])
	}
	if fake.gotPayload["lang"] != "chi_sim+eng" {
		t.Errorf("lang = %v, 期望 chi_sim+eng", fake.gotPayload["lang"])
	}
	result := res.(map[string]any)
	lines, ok := result["lines"].([]any)
	if !ok || len(lines) != 1 {
		t.Errorf("lines = %v, 期望 1 条", result["lines"])
	}
}

// TestOcrNormalizeFilename 验证扩展名白名单归一化。
func TestOcrNormalizeFilename(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"a.png", "a.png"},
		{"a.JPG", "a.JPG"},
		{"a.jpeg", "a.jpeg"},
		{"a.webp", "a.webp"},
		{"a.txt", "a.png"},     // 非白名单 → 回退 .png
		{"noext", "noext.png"}, // 无扩展名 → 补 .png
		{"a.b.c.tif", "a.b.c.tif"},
	}
	for _, tc := range cases {
		if got := ocrNormalizeFilename(tc.in); got != tc.want {
			t.Errorf("ocrNormalizeFilename(%q) = %q, 期望 %q", tc.in, got, tc.want)
		}
	}
}

// TestOcrCapabilityRegistered 验证能力已注册且参数 schema 完整。
func TestOcrCapabilityRegistered(t *testing.T) {
	reg := NewRegistry()
	cap, ok := reg.Get("ocr.recognize")
	if !ok {
		t.Fatal("ocr.recognize 未注册")
	}
	if cap.Handler == nil {
		t.Fatal("ocr.recognize Handler 为空")
	}
	props, ok := cap.Parameters["properties"].(map[string]any)
	if !ok {
		t.Fatal("参数 schema 缺少 properties")
	}
	for _, key := range []string{"gateway", "image", "image_url", "filename", "backend", "lang", "psm", "detail"} {
		if _, exists := props[key]; !exists {
			t.Errorf("参数 schema 缺少 %s", key)
		}
	}
}

// TestOcrListGatewaysNotInjected 验证未注入时的安全行为。
func TestOcrListGatewaysNotInjected(t *testing.T) {
	SetOcrGatewayLister(nil)
	if got := ocrListGateways(); got != nil {
		t.Errorf("未注入时应返回 nil，实际 %v", got)
	}
}

// 保证 io 被使用（假网关响应读取路径）。
var _ = io.Discard
