package capability

// 本文件存放 Windows 文件系统能力（windows.fs.*）的纯逻辑函数。
//
// 这些函数只依赖标准库、不引用任何平台专有类型，因此**不带构建标签**：
// 这样在 Linux / macOS 上也能编译并直接做单元测试，从而在无 Windows 环境时
// 仍能验证编码解析、二进制判定等核心逻辑的正确性。
//
// 与之配套的测试见 windows_fs_parse_test.go；带 //go:build windows 标签的
// windows_fs_windows.go 负责注册能力与真正的文件读写。

import (
	"fmt"
	"strings"
	"unicode/utf8"
)

// resolveWindowsFSEncoding 解析并校验 encoding 参数，只允许 utf-8 与 base64。
//
// 空值返回 def（调用方传入的默认编码）。大小写不敏感，且接受 "utf8" 作为别名。
//
// 注意：这里直接读取原始值而不使用 optionalString，是为了让本文件保持
// 「零平台依赖」——optionalString 定义在带 //go:build windows 标签的文件中，
// 在 darwin 等平台不可用，若在此引用会导致跨平台编译失败。
func resolveWindowsFSEncoding(params map[string]any, def string) (string, error) {
	rawAny, ok := params["encoding"]
	if !ok || rawAny == nil {
		return def, nil
	}
	raw, ok := rawAny.(string)
	if !ok {
		return "", fmt.Errorf("参数 encoding 必须是字符串，实际 %T", rawAny)
	}
	if raw == "" {
		return def, nil
	}
	switch strings.ToLower(raw) {
	case "utf-8", "utf8":
		return "utf-8", nil
	case "base64":
		return "base64", nil
	default:
		return "", fmt.Errorf("参数 encoding 不支持 %q，允许值: utf-8、base64", raw)
	}
}

// chooseWindowsReportedEncoding 返回实际用于表示 content 的编码。
//
// 当请求 utf-8 但内容被判定为二进制时，实际以 base64 返回，故上报 base64，
// 避免调用方按 utf-8 解码得到乱码。
func chooseWindowsReportedEncoding(requested string, isBinary bool) string {
	if isBinary && requested == "utf-8" {
		return "base64"
	}
	return requested
}

// isBinaryWindowsContent 判断内容是否为二进制。
//
// 判定依据：含 NUL 字节，或不是合法的 UTF-8 编码。空内容视为非二进制。
func isBinaryWindowsContent(data []byte) bool {
	if len(data) == 0 {
		return false
	}
	if strings.IndexByte(string(data), 0) >= 0 {
		return true
	}
	return !utf8.Valid(data)
}
