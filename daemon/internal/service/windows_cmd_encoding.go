package service

// 本文件存放 Windows 侧「外部命令输出编码」相关的纯逻辑，刻意不加 //go:build windows
// 标签，以便在 Linux 上编译并单测（本机开发环境为 Linux，无 Windows 运行环境）。
// 与 internal/capability/windows_encoding.go 的做法一致。
//
// 背景：为什么需要转码
// ====================
// schtasks / taskkill / tasklist 是原生控制台程序，按**控制台输出代码页**写出文本——
// 中文 Windows 上是 GBK/CP936，不是 UTF-8。Go 的 os/exec 只返回原始字节，直接
// string(out) 会把 GBK 按 UTF-8 解释，得到 "����: �ܾ����ʡ�" 这类乱码，
// 用户无法看懂失败原因（真机实测 install 失败时即如此）。
//
// 修复策略：不引入 GBK 解码表
// ==========================
// 标准库没有 GBK 解码能力，而引入 golang.org/x/text 被项目约束禁止。因此这里借助
// PowerShell 完成「按系统默认编码解码 → 按 UTF-8 输出」的转码，脚本见
// buildPowerShellScript。调用方（task_windows.go 的 runCmd）用 -EncodedCommand 传递
// 该脚本，避免命令行参数按 ANSI 代码页解析导致脚本内非 ASCII 字符损坏。

import (
	"encoding/base64"
	"strings"
	"unicode/utf16"
)

// buildPowerShellScript 构造用于执行外部命令并转码输出的 PowerShell 脚本。
//
// 单独抽出是为了可单测（本机为 Linux，无法真跑 powershell.exe）：
// 参数转义正确性直接决定 schtasks 能否收到预期的 /TR 值。
//
// 脚本结构（顺序不可调换）：
//
//	$ErrorActionPreference='Continue';
//	$out = & <name> <args...> 2>&1 | Out-String;   # 此时 OutputEncoding 仍是系统默认，正确解码子进程输出
//	$code = $LASTEXITCODE;                          # 捕获外部命令退出码（管道不改变它）
//	[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;
//	[Console]::Out.Write($out)                     # 用 UTF-8 写出，供 Go 侧直接读取
//	exit $code                                      # 把外部命令的退出码透传给 Go
//
// 说明：
//   - 第 1 步必须用**系统默认**的 [Console]::OutputEncoding 读取外部命令输出：
//     中文系统下即 GBK，与 schtasks 写出的字节一致，PowerShell 才能正确解码为内部
//     字符串。若先把它设成 UTF-8 再读，就会用 UTF-8 去解码 GBK 字节而得到乱码。
//   - 第 2 步再改编码为 UTF-8 并写出，Go 侧 string(out) 即为正确文本。
//   - `2>&1` 把 stderr 并入 stdout，保证失败原因（如「拒绝访问」）也能被捕获。
//   - `Out-String` 把外部命令的输出对象序列化为文本，保留完整内容。
//   - 用 [Console]::Out.Write 而非 Write-Output，避免额外追加换行。
//   - $ErrorActionPreference='Continue'：外部命令返回非零退出码时不让 PowerShell 中断，
//     以便我们仍能读到它的输出文本。
//   - **必须显式 exit $code**：因为 $ErrorActionPreference='Continue'，外部命令失败时
//     PowerShell 默认仍以 0 退出，Go 的 cmd.Output() 会误判为成功（真机实测：schtasks
//     创建失败却打印「计划任务已创建」）。用 $LASTEXITCODE 捕获并透传退出码后，
//     Go 侧才能正确识别失败。注意 $LASTEXITCODE 要在执行外部命令后立即捕获，
//     管道（| Out-String）不会改变它。
func buildPowerShellScript(name string, args []string) string {
	var b strings.Builder
	b.WriteString("$ErrorActionPreference='Continue'; ")
	b.WriteString("$out = & ")
	b.WriteString(quotePowerShellArg(name))
	for _, a := range args {
		b.WriteString(" ")
		b.WriteString(quotePowerShellArg(a))
	}
	b.WriteString(" 2>&1 | Out-String; ")
	b.WriteString("$code = $LASTEXITCODE; ")
	b.WriteString("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; ")
	b.WriteString("[Console]::Out.Write($out); ")
	b.WriteString("exit $code")
	return b.String()
}

// quotePowerShellArg 按 PowerShell 规则为单个参数加上必要的引号与转义。
//
// 规则：参数含空白或 PowerShell 特殊字符时用单引号包裹；参数内的单引号按
// PowerShell 约定用两个连续的单引号表示一个字面单引号。
// 单引号字符串内不做变量展开，故 $ 等字符无需额外处理。
func quotePowerShellArg(s string) string {
	if s == "" {
		return "''"
	}
	if !strings.ContainsAny(s, " \t'\"$`&|<>;(){}[],") {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", "''") + "'"
}

// encodePowerShellCommand 把脚本编码为 -EncodedCommand 所需的 base64(UTF-16LE)。
//
// 与 internal/capability/windows_encoding.go 的实现一致：base64 是纯 ASCII，
// 彻底绕开「命令行参数按 ANSI 代码页解析」导致的非 ASCII 字符损坏。
// 不加 BOM（-EncodedCommand 期望无 BOM 的 base64）。
func encodePowerShellCommand(script string) string {
	units := utf16.Encode([]rune(script))
	buf := make([]byte, 0, len(units)*2)
	for _, u := range units {
		// UTF-16 码元按小端序写入：低字节在前，高字节在后。
		buf = append(buf, byte(u&0xFF), byte(u>>8))
	}
	return base64.StdEncoding.EncodeToString(buf)
}
