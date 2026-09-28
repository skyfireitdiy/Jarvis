package capability

// 本文件实现「OCR 文字识别」能力（ocr.recognize），跨平台共享。
//
// 为什么把识别放到网关而不是本机：OCR 后端（tesseract / rapidocr / paddleocr /
// easyocr / vision）体积大、依赖多，装在每个被控终端上不现实；网关侧已有现成
// 的 OcrTool（src/jarvis/jarvis_tools/ocr.py）与 POST /api/ocr 接口。
// 因此 daemon 只负责「把图片字节送过去」，识别由网关完成。
//
// 数据通路：
//
//	本机图片（路径或 URL）--(读取/下载)--> base64 --(HTTP, 带网关 Token)--> 网关 /api/ocr
//
// 重要：本文件**不带构建标签**，会被编译进所有平台（含 darwin），因此只能使用
// 标准库，且不得引用平台专有符号（requiredString / optionalBool 等）。
// 参数读取复用跨平台共享的 browserExtOptionalString / transferParamString /
// transferParamInt64 / transferParamBool。

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"jarvis-daemon/internal/proxy"
)

// ocrMaxImageBytes 是允许发送给网关的图片最大字节数（20 MiB）。
//
// 取值理由：与网关侧 OCR 工具的上限（CONTENT_CONFIG.max_image_size 默认 20 MiB）
// 保持一致。本地先拦一道，避免把注定被拒的超大图 base64 后（膨胀约 4/3）
// 白白推过网络。
const ocrMaxImageBytes int64 = 20 << 20 // 20 MiB

// ocrHTTPTimeout 是单次 OCR 请求的超时时间。
//
// 取值理由：OCR 可能跑 tesseract CLI，也可能把图片交给视觉模型，耗时从数秒到
// 数十秒不等；60s 是「够慢的后端能跑完」与「调用方不至于无限等待」的折中。
// 注意：这是「整次请求」的超时，包含上传 base64 与等待识别结果。
const ocrHTTPTimeout = 60 * time.Second

// ocrDownloadTimeout 是下载 image_url 图片的超时时间。
//
// 比 OCR 请求短：下载图片只是搬运字节，30s 足够；若源站很慢，宁可失败也不要
// 把整个能力调用卡住。
const ocrDownloadTimeout = 30 * time.Second

// ocrDefaultFilename 是未提供 filename 时使用的默认文件名。
//
// 必须带扩展名：网关侧按扩展名决定临时文件后缀，进而影响 OCR 后端的解码路径。
const ocrDefaultFilename = "image.png"

// ocrSupportedExts 是网关侧允许的图片扩展名白名单（与 ocr.py 的 _SUPPORTED_EXTS 对齐）。
//
// 本地先做一次校验，好处是错误信息更贴近调用方（能指出是 filename 写错了），
// 而不是等网关返回一个泛泛的失败。非白名单扩展名会回退为 .png。
var ocrSupportedExts = map[string]bool{
	".png":  true,
	".jpg":  true,
	".jpeg": true,
	".bmp":  true,
	".tif":  true,
	".tiff": true,
	".webp": true,
	".gif":  true,
	".pbm":  true,
	".pgm":  true,
	".ppm":  true,
}

// registerOcr 注册指定平台的 OCR 能力。
//
// 平台差异只体现在 Platform 字段，逻辑完全共享，故由 registry_*.go 传入 platform。
func registerOcr(reg *Registry, platform Platform) {
	_ = reg.Register(Capability{
		Name: "ocr.recognize",
		Description: "识别图片中的文字（OCR）。把本机图片（本地路径或图片 URL）交给网关的 OCR 服务，" +
			"返回识别出的文本。典型用途：对本地 UI 截图取字，再据此决定后续点击/输入位置。" +
			"图片上限 20 MiB；image 与 image_url 二选一必填。",
		Platform: platform,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"gateway": map[string]any{
					"type": "string",
					"description": "网关地址（如 https://jvs-ai.cn）。" +
						"省略时使用 daemon 已认证的第一个网关（多网关时按地址排序取首个）。",
				},
				"image": map[string]any{
					"type":        "string",
					"description": "本机图片路径（如 /tmp/shot.png 或 C:\\\\tmp\\\\shot.png）。与 image_url 二选一。",
				},
				"image_url": map[string]any{
					"type":        "string",
					"description": "图片 URL（http/https）。与 image 二选一；由 daemon 自行下载后再上传网关。",
				},
				"filename": map[string]any{
					"type": "string",
					"description": "文件名，用于推断图片扩展名（默认 image.png）。" +
						"支持 png/jpg/jpeg/bmp/tif/tiff/webp/gif/pbm/pgm/ppm，其它一律按 .png 处理。",
				},
				"backend": map[string]any{
					"type": "string",
					"description": "OCR 后端：auto（默认，按优先级自动选择）/ tesseract / rapidocr / " +
						"paddleocr / easyocr / vision。",
				},
				"lang": map[string]any{
					"type":        "string",
					"description": "识别语言，默认 eng；tesseract 支持组合如 chi_sim+eng。",
				},
				"psm": map[string]any{
					"type":        "integer",
					"description": "tesseract 页面分割模式（3=全自动，6=单块文本，7=单行，11=稀疏文本）。",
				},
				"detail": map[string]any{
					"type":        "boolean",
					"description": "是否返回逐行明细（文本/置信度/坐标，取决于后端能力），默认 false。",
				},
			},
			"required": []string{},
		},
		Handler: handleOcrRecognize,
	})
}

// ocrParams 是从能力参数中解析出的规范化入参。
type ocrParams struct {
	Gateway  string
	Image    string
	ImageURL string
	Filename string
	Backend  string
	Lang     string
	PSM      int64
	HasPSM   bool
	Detail   bool
}

// parseOcrParams 解析并校验 ocr.recognize 的参数。
//
// 校验规则：
//   - image 与 image_url 必须恰好提供一个（都缺或都给都报错，避免语义含糊）；
//   - image_url 必须以 http:// 或 https:// 开头；
//   - psm 仅在显式提供时才透传（未提供时传 null，让网关用后端默认值）。
func parseOcrParams(params map[string]any) (*ocrParams, error) {
	gateway, err := browserExtOptionalString(params, "gateway")
	if err != nil {
		return nil, err
	}
	image, err := browserExtOptionalString(params, "image")
	if err != nil {
		return nil, err
	}
	imageURL, err := browserExtOptionalString(params, "image_url")
	if err != nil {
		return nil, err
	}
	image = strings.TrimSpace(image)
	imageURL = strings.TrimSpace(imageURL)
	if image == "" && imageURL == "" {
		return nil, fmt.Errorf("参数 image（本地路径）与 image_url（图片 URL）必须提供其中一个")
	}
	if image != "" && imageURL != "" {
		return nil, fmt.Errorf("参数 image 与 image_url 只能提供其中一个，不能同时提供")
	}
	if imageURL != "" {
		lower := strings.ToLower(imageURL)
		if !strings.HasPrefix(lower, "http://") && !strings.HasPrefix(lower, "https://") {
			return nil, fmt.Errorf("参数 image_url 必须以 http:// 或 https:// 开头，实际 %s", imageURL)
		}
	}
	filename, err := browserExtOptionalString(params, "filename")
	if err != nil {
		return nil, err
	}
	filename = strings.TrimSpace(filename)
	if filename == "" {
		// 未指定时，尽量从 image 路径推断，让网关拿到更贴切的扩展名。
		if image != "" {
			filename = filepath.Base(image)
		}
		if filename == "" || filename == "." || filename == string(filepath.Separator) {
			filename = ocrDefaultFilename
		}
	}
	backend, err := browserExtOptionalString(params, "backend")
	if err != nil {
		return nil, err
	}
	backend = strings.TrimSpace(backend)
	if backend == "" {
		backend = "auto"
	}
	lang, err := browserExtOptionalString(params, "lang")
	if err != nil {
		return nil, err
	}
	lang = strings.TrimSpace(lang)
	if lang == "" {
		lang = "eng"
	}
	psm, err := transferParamInt64(params, "psm", 0)
	if err != nil {
		return nil, err
	}
	// 只有调用方显式给了 psm 才透传：0 对 tesseract 是合法值（自动），
	// 无法用 0 表示「未设置」，故单独用 HasPSM 标记。
	// 显式传 null 等同于未设置（JSON 里 null 与缺省语义一致）。
	hasPSM := false
	if v, ok := params["psm"]; ok && v != nil {
		hasPSM = true
	}
	detail, err := transferParamBool(params, "detail", false)
	if err != nil {
		return nil, err
	}
	return &ocrParams{
		Gateway:  strings.TrimRight(gateway, "/"),
		Image:    image,
		ImageURL: imageURL,
		Filename: filename,
		Backend:  backend,
		Lang:     lang,
		PSM:      psm,
		HasPSM:   hasPSM,
		Detail:   detail,
	}, nil
}

// ocrNormalizeFilename 把 filename 收敛为白名单内的扩展名。
//
// 网关按扩展名决定临时文件后缀；非白名单（如 .txt、无扩展名）统一回退 .png，
// 与网关侧行为一致，避免两边判定不同导致「本地通过、网关拒绝」。
func ocrNormalizeFilename(name string) string {
	ext := strings.ToLower(filepath.Ext(name))
	if ocrSupportedExts[ext] {
		return name
	}
	base := strings.TrimSuffix(name, filepath.Ext(name))
	if base == "" {
		base = "image"
	}
	return base + ".png"
}

// ocrReadLocalImage 读取本地图片字节并校验大小。
func ocrReadLocalImage(path string) ([]byte, error) {
	info, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("读取本地图片 %s 失败: %w", path, err)
	}
	if info.IsDir() {
		return nil, fmt.Errorf("本地路径 %s 是目录，不是图片文件", path)
	}
	if info.Size() > ocrMaxImageBytes {
		return nil, fmt.Errorf("本地图片 %s 大小 %d 字节超出上限 %d 字节（20 MiB）",
			path, info.Size(), ocrMaxImageBytes)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("读取本地图片 %s 失败: %w", path, err)
	}
	if int64(len(data)) > ocrMaxImageBytes {
		return nil, fmt.Errorf("本地图片 %s 大小 %d 字节超出上限 %d 字节（20 MiB）",
			path, len(data), ocrMaxImageBytes)
	}
	return data, nil
}

// ocrDownloadImage 下载 image_url 指向的图片并校验大小。
//
// 用 LimitReader 多读 1 字节来判断「是否超限」，避免先把超大响应整体读进内存。
func ocrDownloadImage(rawURL string) ([]byte, error) {
	req, err := http.NewRequest(http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, fmt.Errorf("构造图片下载请求失败: %w", err)
	}
	client := &http.Client{Timeout: ocrDownloadTimeout, Transport: proxy.Transport()}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("下载图片 %s 失败: %w", rawURL, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("下载图片 %s 失败（HTTP %d）: %s",
			rawURL, resp.StatusCode, strings.TrimSpace(string(body)))
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, ocrMaxImageBytes+1))
	if err != nil {
		return nil, fmt.Errorf("读取图片 %s 响应失败: %w", rawURL, err)
	}
	if int64(len(data)) > ocrMaxImageBytes {
		return nil, fmt.Errorf("图片 %s 超过大小上限 %d 字节（20 MiB）", rawURL, ocrMaxImageBytes)
	}
	if len(data) == 0 {
		return nil, fmt.Errorf("图片 %s 下载结果为空", rawURL)
	}
	return data, nil
}

// ocrResolveGateway 解析要使用的网关地址。
//
// 显式传 gateway 时直接用；未传时回退到「daemon 已认证的第一个网关」。
// 回退依赖 main.go 注入的凭据提供器（见 browser_ext_cred.go 的
// SetBrowserExtCredentialProvider），这里通过 ocrGatewayLister 注入的列表函数实现，
// 避免 capability 包反向依赖 auth 包。
func ocrResolveGateway(explicit string) (string, error) {
	if explicit != "" {
		return explicit, nil
	}
	gateways := ocrListGateways()
	if len(gateways) == 0 {
		return "", fmt.Errorf("未指定 gateway 参数，且 daemon 当前没有已认证的网关；" +
			"请先在网页中登录并推送登录信息，或显式传入 gateway")
	}
	return gateways[0], nil
}

// ocrPostJSON 向网关 POST 一个 JSON 请求体并返回解析后的响应。
//
// 与 transfer_remote.go 的 transferRemotePost 类似，但错误信息面向 OCR 场景，
// 且响应体上限按 OCR 结果规模（文本 + 逐行明细）放宽到 8 MiB。
func ocrPostJSON(gateway, apiPath, token string, payload map[string]any) (map[string]any, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("序列化 OCR 请求体失败: %w", err)
	}
	url := gateway + apiPath
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("构造 OCR 请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	client := &http.Client{Timeout: ocrHTTPTimeout, Transport: proxy.Transport()}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("请求 %s 失败: %w", url, err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if err != nil {
		return nil, fmt.Errorf("读取 %s 响应失败: %w", url, err)
	}
	var parsed map[string]any
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return nil, fmt.Errorf("解析 %s 响应失败（HTTP %d）: %s",
			url, resp.StatusCode, strings.TrimSpace(string(raw)))
	}
	if resp.StatusCode != http.StatusOK {
		// 网关鉴权失败（401/403）时给出更贴近原因的提示。
		if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
			return nil, fmt.Errorf("网关 %s 拒绝了 OCR 请求（HTTP %d，Token 可能已失效）: %v",
				gateway, resp.StatusCode, parsed["detail"])
		}
		return nil, fmt.Errorf("网关 %s OCR 请求失败（HTTP %d）: %v",
			gateway, resp.StatusCode, parsed["error"])
	}
	return parsed, nil
}

// handleOcrRecognize 是 ocr.recognize 的实现。
//
// 流程：解析参数 → 取网关与 Token → 取图片字节（本地读 / URL 下载）→
// base64 → POST 网关 /api/ocr → 归一化返回。
func handleOcrRecognize(params map[string]any) (any, error) {
	p, err := parseOcrParams(params)
	if err != nil {
		return nil, err
	}
	gateway, err := ocrResolveGateway(p.Gateway)
	if err != nil {
		return nil, err
	}
	token, ok := browserExtToken(gateway)
	if !ok || token == "" {
		return nil, fmt.Errorf("网关 %s 没有可用凭据，无法调用 OCR；请先在网页中登录并推送登录信息",
			gateway)
	}

	var data []byte
	if p.Image != "" {
		data, err = ocrReadLocalImage(p.Image)
	} else {
		data, err = ocrDownloadImage(p.ImageURL)
	}
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > ocrMaxImageBytes {
		return nil, fmt.Errorf("图片大小 %d 字节超出上限 %d 字节（20 MiB）",
			len(data), ocrMaxImageBytes)
	}

	filename := ocrNormalizeFilename(p.Filename)
	payload := map[string]any{
		"image_base64": base64.StdEncoding.EncodeToString(data),
		"filename":     filename,
		"backend":      p.Backend,
		"lang":         p.Lang,
		"detail":       p.Detail,
	}
	if p.HasPSM {
		payload["psm"] = p.PSM
	} else {
		// 显式传 null：让网关的 OcrTool 使用后端默认值。
		payload["psm"] = nil
	}

	parsed, err := ocrPostJSON(gateway, "/api/ocr", token, payload)
	if err != nil {
		return nil, err
	}

	// 网关侧约定：success=false 时 error 字段给出原因（如「没有可用的 OCR 后端」）。
	success, _ := parsed["success"].(bool)
	text, _ := parsed["text"].(string)
	backend, _ := parsed["backend"].(string)
	lines, _ := parsed["lines"].([]any)
	ocrErr, _ := parsed["error"].(string)
	if !success {
		if ocrErr == "" {
			ocrErr = "网关 OCR 返回失败但未提供原因"
		}
		return nil, fmt.Errorf("网关 %s OCR 识别失败: %s", gateway, ocrErr)
	}

	result := map[string]any{
		"success": true,
		"text":    text,
		"backend": backend,
		"gateway": gateway,
		"size":    len(data),
	}
	if lines == nil {
		result["lines"] = []any{}
	} else {
		result["lines"] = lines
	}
	if p.Image != "" {
		result["image"] = p.Image
	} else {
		result["image_url"] = p.ImageURL
	}
	return result, nil
}
