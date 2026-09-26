//go:build windows

package capability

// 本文件实现 Windows 平台的剪贴板与截图能力（windows.clipboard.*、windows.screenshot）。
//
// 与窗口/输入能力（windows_gui_windows.go、windows_input_windows.go）直接调 user32.dll
// 不同，剪贴板与截图走 PowerShell：
//   - 剪贴板：user32 的剪贴板 API 需要 OpenClipboard/GlobalLock/GlobalAlloc 一整套
//     内存句柄管理，代码量大且易泄漏；而 PowerShell 自带 Get-Clipboard/Set-Clipboard，
//     在 Windows PowerShell 5.1 与 PowerShell 7+ 上均可用，语义清晰。
//   - 截图：需要 GDI+/System.Drawing 的位图编码能力，纯 syscall 手写 GDI+ 的 COM
//     接口（GdipSaveImageToFile 等）极其繁琐；PowerShell 一行即可完成。
//
// 因此本文件复用 windows_common_windows.go 的 requireTool 探测 powershell.exe，
// 并通过 runWindowsPowerShellCommand 统一带超时执行。
//
// 安全要点：**绝不把用户文本直接拼进 PowerShell 命令字符串**。
// windows.clipboard.set 的文本经 encodePowerShellText 编码为单引号字面量
// （见 windows_gui_parse.go），其中的单引号按 PowerShell 规则双写转义，
// $、反引号、分号、换行等不会被解释，从而杜绝命令注入。
//
// 注意：本机开发环境为 Linux，无 Windows 运行环境，因此本文件只能保证
// 「在 GOOS=windows 下编译通过」，各能力的成功路径未做端到端验证。

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

// windowsClipboardTimeout 是执行 PowerShell 剪贴板命令的超时时间。
//
// 与 Linux 侧 linuxGUITimeout（10s）保持一致：剪贴板读写都是毫秒级操作，
// 10s 足够覆盖进程冷启动；超时说明 PowerShell 卡死，应尽快失败而不是挂住调用方。
//
// 注意：windows.clipboard.set 内部带重试（见 windowsClipboardSetScript），
// 真机实测剪贴板被其他进程占用时可能需要重试近 10 次（约 10s）才成功，
// 因此这里放宽到 30s，避免重试尚未完成就被超时打断。
const windowsClipboardTimeout = 30 * time.Second

// windowsScreenshotTimeout 是执行 PowerShell 截图命令的超时时间。
//
// 比剪贴板宽松：截图要加载 System.Drawing 程序集、抓取全屏位图并编码为
// PNG/JPEG（4K 屏编码可能需要数秒），因此给到 30s。
const windowsScreenshotTimeout = 30 * time.Second

// windowsClipboardTool 是剪贴板能力返回结果中 tool 字段的值。
//
// 用 "powershell.exe" 与 Linux 侧的 "xclip"/"xsel" 形式对齐，让调用方一眼看出
// 底层走的是哪个实现。
const windowsClipboardTool = "powershell.exe"

// registerWindowsClipboard 注册 Windows 剪贴板与截图能力。
func registerWindowsClipboard(reg *Registry) {
	_ = reg.Register(Capability{
		Name: "windows.clipboard.get",
		Description: "读取 Windows 剪贴板中的文本。" +
			"通过 PowerShell 的 Get-Clipboard -Raw 实现，保留换行等原始格式" +
			"（不加 -Raw 会被 PowerShell 按行拆成数组后再拼接，丢失行尾）。" +
			"剪贴板中不是文本（如仅含图片）时返回空字符串。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type":       "object",
			"properties": map[string]any{},
		},
		Handler: handleWindowsClipboardGet,
	})

	_ = reg.Register(Capability{
		Name: "windows.clipboard.set",
		Description: "把文本写入 Windows 剪贴板。" +
			"通过 PowerShell 的 Set-Clipboard 实现；文本经单引号字面量转义后传入，" +
			"不会造成命令注入。允许传入空字符串以清空剪贴板。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"text": map[string]any{
					"type":        "string",
					"description": "要写入剪贴板的文本；允许为空串（表示清空剪贴板）。",
				},
			},
			"required": []string{"text"},
		},
		Handler: handleWindowsClipboardSet,
	})

	_ = reg.Register(Capability{
		Name: "windows.screenshot",
		Description: "截取 Windows 主屏并保存到指定路径。" +
			"通过 PowerShell 加载 System.Drawing，用 Graphics.CopyFromScreen 抓取主屏" +
			"并按 format 指定的格式编码保存。支持 png（默认）、jpg/jpeg。" +
			"注意：仅截取主屏，不支持多显示器拼接与指定窗口。",
		Platform: PlatformWindows,
		Parameters: map[string]any{
			"type": "object",
			"properties": map[string]any{
				"path": map[string]any{
					"type":        "string",
					"description": "截图保存的绝对路径，如 C:\\Users\\me\\shot.png。",
				},
				"format": map[string]any{
					"type":        "string",
					"description": "图片格式，默认 png；支持 png、jpg、jpeg。",
				},
			},
			"required": []string{"path"},
		},
		Handler: handleWindowsScreenshot,
	})
}

// requirePowerShell 探测 powershell.exe 是否可用，返回其绝对路径。
//
// Windows 自带 Windows PowerShell 5.1（powershell.exe），因此正常情况下必然存在；
// 探测只是为了在极端环境（被裁剪的镜像、PATH 异常）下给出可读的错误提示。
func requirePowerShell() (string, error) {
	return requireTool("powershell.exe", "Windows 自带 Windows PowerShell 5.1，请确认系统 PATH 未被破坏")
}

// runWindowsPowerShellCommand 执行一段 PowerShell 脚本并返回标准输出（UTF-8）。
//
// 参数说明：
//   - script：完整的 PowerShell 脚本文本。**调用方必须自行保证其中的用户输入
//     已做转义**（见 encodePowerShellText）；本函数不做任何转义。
//   - timeout：超时时间。
//
// 编码方案（这是本函数的核心，修复了真实机器上的中文乱码）：
//
//  1. 用 -EncodedCommand 而非 -Command 传递脚本。原因：-Command 的脚本文本经
//     命令行参数传递，Windows PowerShell 5.1 按 ANSI 代码页（中文系统 = GBK）
//     解析该参数，而 Go 的 exec 按 UTF-8 字节传递，导致脚本内的中文损坏。
//     -EncodedCommand 接受 base64(UTF-16LE)，是纯 ASCII，彻底绕开该问题。
//     编码实现见 windows_encoding.go 的 encodePowerShellCommand。
//
//  2. 脚本最前面拼接 windowsPowerShellPreamble，把 PowerShell 的输出编码设为
//     UTF-8。这样 Go 侧读到的 stdout 字节就是 UTF-8，直接 string(out) 即可，
//     无需引入 GBK 解码表（标准库无此能力，第三方包被项目约束禁止）。
//
// 其余开关：
//   - -NoProfile：跳过用户配置文件（避免自定义 profile 拖慢启动或改变行为）。
//   - -NonInteractive：禁止交互式提示（否则意外弹出的确认框会一直挂到超时）。
//   - -ExecutionPolicy Bypass：绕过脚本执行策略限制。
//
// 失败时把 stderr 内容带进错误信息，便于排查（如 System.Drawing 加载失败）。
func runWindowsPowerShellCommand(script string, timeout time.Duration) (string, error) {
	ps, err := requirePowerShell()
	if err != nil {
		return "", err
	}

	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	// 前置语句必须在任何输出产生之前执行，因此拼在脚本最前面。
	fullScript := windowsPowerShellPreamble + "\n" + script

	cmd := exec.CommandContext(ctx, ps,
		"-NoProfile",
		"-NonInteractive",
		"-ExecutionPolicy", "Bypass",
		"-EncodedCommand", encodePowerShellCommand(fullScript),
	)

	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return "", fmt.Errorf("执行 PowerShell 超时（%s）", timeout)
		}
		if exitErr, ok := err.(*exec.ExitError); ok {
			stderr := strings.TrimSpace(string(exitErr.Stderr))
			if stderr != "" {
				return "", fmt.Errorf("执行 PowerShell 失败: %s", stderr)
			}
		}
		return "", fmt.Errorf("执行 PowerShell 失败: %w", err)
	}

	// 正常情况下 PowerShell 已按 UTF-8 输出，直接转换即可。
	// 若环境异常导致仍按 GBK 输出，字节流不是合法 UTF-8；此时给出明确错误，
	// 而不是静默返回一串 U+FFFD 让调用方困惑于「为什么全是问号」。
	if !looksLikeUTF8(out) {
		return "", fmt.Errorf("PowerShell 输出不是合法 UTF-8（疑似仍按控制台代码页输出），"+
			"请确认系统未强制覆盖控制台输出编码；原始字节长度 %d", len(out))
	}
	return string(out), nil
}

// handleWindowsClipboardGet 是 windows.clipboard.get 的实现。
func handleWindowsClipboardGet(params map[string]any) (any, error) {
	// -Raw 保证返回完整文本（含换行）而不是按行拆分的数组。
	// 末尾追加 [Console]::Out.Write 而非 Write-Output，是为了避免 PowerShell
	// 在输出末尾自动追加换行——否则读回的文本会比原始内容多一个 "\n"。
	//
	// 剪贴板为空（或非文本）时 Get-Clipboard 返回空，此时管道传给 [Console]::Out.Write
	// 的参数为 $null，PowerShell 会把它转成空串输出，符合「返回空字符串」的预期。
	const script = "[Console]::Out.Write((Get-Clipboard -Raw))"

	out, err := runWindowsPowerShellCommand(script, windowsClipboardTimeout)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"text": out,
		"tool": windowsClipboardTool,
	}, nil
}

// handleWindowsClipboardSet 是 windows.clipboard.set 的实现。
func handleWindowsClipboardSet(params map[string]any) (any, error) {
	// 允许写入空字符串以清空剪贴板，因此不能用 requiredString
	// （它会把空串判为「不能为空」）。与 Linux 侧 handleLinuxClipboardSet 一致。
	raw, ok := params["text"]
	if !ok || raw == nil {
		return nil, fmt.Errorf("缺少必填参数 text")
	}
	text, ok := raw.(string)
	if !ok {
		return nil, fmt.Errorf("参数 text 必须是字符串，实际 %T", raw)
	}

	// 关键安全点：text 经 encodePowerShellText 变成单引号字面量后才拼进脚本。
	// 该函数把文本内的单引号双写，其余字符在单引号字面量中不被解释，杜绝注入。
	// 脚本内自带重试：Windows 剪贴板常被其他进程短暂占用，一次调用极易失败
	// （真机实测最坏第 9 次才成功），详见 buildWindowsClipboardSetScript。
	script := buildWindowsClipboardSetScript(encodePowerShellText(text))

	out, err := runWindowsPowerShellCommand(script, windowsClipboardTimeout)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"written_bytes": len(text),
		"output":        strings.TrimSpace(out),
		"tool":          windowsClipboardTool,
	}, nil
}

// handleWindowsScreenshot 是 windows.screenshot 的实现。
func handleWindowsScreenshot(params map[string]any) (any, error) {
	path, err := requiredString(params, "path")
	if err != nil {
		return nil, err
	}

	format, err := optionalString(params, "format")
	if err != nil {
		return nil, err
	}
	if format == "" {
		format = "png"
	}
	// 归一化：jpeg 与 jpg 等价，统一成 jpg 便于后续映射到 ImageFormat。
	format = strings.ToLower(format)
	if format == "jpeg" {
		format = "jpg"
	}
	switch format {
	case "png", "jpg":
	default:
		return nil, fmt.Errorf("参数 format 不支持 %q，允许值: png、jpg、jpeg", format)
	}

	// 选择 System.Drawing 的 ImageFormat 静态属性。
	// png → [System.Drawing.Imaging.ImageFormat]::Png
	// jpg → [System.Drawing.Imaging.ImageFormat]::Jpeg
	imageFormat := "Png"
	if format == "jpg" {
		imageFormat = "Jpeg"
	}

	// 脚本要点：
	//  1. 先 Add-Type 加载 System.Drawing（Windows PowerShell 5.1 内置该程序集；
	//     PowerShell 7 需要已安装对应的 Windows 兼容包，缺失时 Add-Type 会报错，
	//     错误信息会经 stderr 透传给调用方）。
	//  2. 用 System.Windows.Forms.Screen 的 PrimaryScreen.Bounds 取主屏尺寸，
	//     而不是 Graphics.CopyFromScreen 的默认 0,0 到 0,0（后者截不到内容）。
	//  3. 用 try/finally 确保 Bitmap 与 Graphics 一定被释放，避免 GDI 句柄泄漏。
	//  4. 路径经 encodePowerShellText 转义（Windows 路径含反斜杠，单引号字面量中
	//     反斜杠不是转义字符，因此无需额外处理；但路径可能含单引号，仍需转义）。
	script := strings.Join([]string{
		"Add-Type -AssemblyName System.Drawing",
		"Add-Type -AssemblyName System.Windows.Forms",
		"$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds",
		"$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height",
		"try {",
		"  $g = [System.Drawing.Graphics]::FromImage($bmp)",
		"  try {",
		"    $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)",
		"  } finally { $g.Dispose() }",
		"  $bmp.Save(" + encodePowerShellText(path) +
			", [System.Drawing.Imaging.ImageFormat]::" + imageFormat + ")",
		"} finally { $bmp.Dispose() }",
	}, "\n")

	if _, err := runWindowsPowerShellCommand(script, windowsScreenshotTimeout); err != nil {
		return nil, err
	}

	// 与 Linux 侧一致：命令执行成功后再 stat 一次，确认文件确实落盘。
	// 这样能把「脚本静默失败但退出码为 0」的情况暴露出来。
	info, statErr := os.Stat(path)
	if statErr != nil {
		return nil, fmt.Errorf("截图命令已执行但未找到输出文件 %s: %w", path, statErr)
	}

	return map[string]any{
		"path":       path,
		"size_bytes": info.Size(),
		"format":     format,
		"tool":       windowsClipboardTool,
	}, nil
}
