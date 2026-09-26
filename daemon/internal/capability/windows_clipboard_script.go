package capability

// 本文件实现 windows.clipboard.set 的 PowerShell 脚本构造（含重试）。
//
// 为什么单独放在无构建标签的文件里
// ================================
// 脚本构造是纯字符串逻辑，与 Windows 运行时无关。放在无构建标签的文件中，
// 就能在 Linux 开发机上直接单测（本机无 Windows 环境，_windows.go 里的代码
// 只能保证交叉编译通过，无法运行测试）。
//
// 为什么必须重试
// ==============
// Windows 剪贴板同一时刻只能被一个进程打开，任何后台程序（输入法、剪贴板
// 管理器、浏览器等）都可能短暂持有它，此时 Set-Clipboard 会抛
// "Requested Clipboard operation did not succeed"（ExternalException）。
// 真机实测：单次调用失败，最坏情况下重试到第 9 次才成功（耗时约 11s）。
// 因此必须重试，否则 windows.clipboard.set 在真实机器上几乎不可用。

import "fmt"

// windowsClipboardRetryAttempts 是 Set-Clipboard 的最大尝试次数。
//
// 背景（真机实测）：Windows 剪贴板同一时刻只能被一个进程打开，任何后台程序
// （输入法、剪贴板管理器、浏览器等）都可能短暂持有它，此时 Set-Clipboard 会抛
// "Requested Clipboard operation did not succeed"（ExternalException）。
// 真机实测最坏情况下第 9 次尝试才成功，因此必须重试而不是一次失败就报错。
const windowsClipboardRetryAttempts = 20

// windowsClipboardRetryDelayMs 是两次尝试之间的间隔（毫秒）。
const windowsClipboardRetryDelayMs = 100

// buildWindowsClipboardSetScript 构造带重试的 Set-Clipboard 脚本。
//
// valueLiteral 必须是 encodePowerShellText 产出的单引号字面量（防注入）。
// 重试逻辑放在 PowerShell 侧而非 Go 侧：每次重试若都新起一个 powershell.exe，
// 冷启动开销（数百毫秒）会远超重试间隔，20 次重试将耗时数秒；而在同一进程内
// Start-Sleep 重试，开销可忽略。
func buildWindowsClipboardSetScript(valueLiteral string) string {
	return fmt.Sprintf(
		"$ok = $false; "+
			"for ($i = 0; $i -lt %d; $i++) { "+
			"try { Set-Clipboard -Value %s; $ok = $true; break } "+
			"catch { Start-Sleep -Milliseconds %d } "+
			"}; "+
			"if (-not $ok) { Write-Error '设置剪贴板失败：剪贴板被其他程序持续占用' ; exit 1 }",
		windowsClipboardRetryAttempts, valueLiteral, windowsClipboardRetryDelayMs)
}
