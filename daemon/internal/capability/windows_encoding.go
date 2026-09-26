package capability

// 本文件存放 Windows 侧「子进程输出编码」相关的纯逻辑，刻意不加 //go:build windows
// 标签，以便在 Linux 上编译并单测（本机开发环境为 Linux，无 Windows 运行环境）。
//
// 背景：为什么需要这个文件
// ========================
// Go 的 os/exec 在 Windows 上把子进程的 stdout 当作**原始字节**返回，不做任何
// 编码转换。而 Windows 控制台程序（reg.exe、powershell.exe、wmic.exe）默认按
// **控制台输出代码页**写出文本——中文 Windows 上是 GBK/CP936，不是 UTF-8。
//
// 因此 `string(out)` 这种直接转换会把 GBK 字节按 UTF-8 解释：GBK 的双字节序列
// 大多不是合法 UTF-8，会被替换为 U+FFFD（"�"），表现为
//
//	"东方财富信息股份有限公司" → "�����Ƹ���Ϣ�ɷ����޹�˾"
//
// 这正是真实机器上 windows.app.list 的乱码现象。
//
// 修复策略：不引入 GBK 解码表
// ==========================
// 标准库没有 GBK 解码能力，而引入 golang.org/x/text 被项目约束禁止。因此本方案
// 不去「解码 GBK」，而是**让子进程直接输出 UTF-8**，从源头消除编码错配：
//
//  1. PowerShell 路径：用 -EncodedCommand 传递脚本（见 encodePowerShellCommand），
//     并在脚本最前面把 [Console]::OutputEncoding 设为 UTF-8（见
//     windowsPowerShellPreamble）。这样 PowerShell 写出的就是 UTF-8 字节。
//
//  2. reg.exe 路径：reg.exe 没有 UTF-8 输出模式，无法从源头解决。故
//     windows.app.list 改为走 PowerShell 的 Get-ItemProperty（见
//     windows_app_windows.go），从而复用上面第 1 条的 UTF-8 输出保证。
//
// 这样两条路径的 stdout 都是 UTF-8，Go 侧直接 string(out) 即为正确文本。

import (
	"encoding/base64"
	"strings"
	"unicode/utf16"
)

// windowsPowerShellPreamble 是所有 PowerShell 脚本的前置语句。
//
// 作用：把 PowerShell 的输出编码强制为 UTF-8，使 Go 侧可以直接按 UTF-8 解码
// stdout，无需 GBK 解码表。
//
// 三项设置缺一不可，各自作用不同：
//   - [Console]::OutputEncoding：控制 PowerShell 向**控制台/stdout** 写出的编码。
//     这是最关键的一项，直接决定 Go 读到的字节是什么编码。
//   - $OutputEncoding：控制 PowerShell 向**外部程序管道**传递数据时使用的编码。
//     影响 cmdlet 之间的管道以及调用外部命令时的编码。
//   - [Console]::InputEncoding：控制读取 stdin 的编码。虽然本守护进程不向
//     PowerShell 写 stdin，但统一设置可避免某些 cmdlet 因输入编码不一致而报错。
//
// 注意：必须在**任何输出产生之前**设置，因此该前置语句会被拼在脚本最前面。
const windowsPowerShellPreamble = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " +
	"$OutputEncoding = [System.Text.Encoding]::UTF8; " +
	"[Console]::InputEncoding = [System.Text.Encoding]::UTF8"

// encodePowerShellCommand 把 PowerShell 脚本编码为 -EncodedCommand 所需的参数。
//
// 背景：为什么不能直接用 -Command
// ------------------------------
// `powershell.exe -Command <脚本>` 的脚本文本是**通过命令行参数**传递的。Go 的
// os/exec 在 Windows 上把 Go string（UTF-8 字节）交给 CreateProcess，而 Windows
// PowerShell 5.1 解析 -Command 参数时按 **ANSI 代码页**（中文系统 = GBK/CP936）
// 解码。于是脚本内的非 ASCII 字符（中文、全角符号）会被按 GBK 误读而损坏——
// 这会让脚本里的中文字面量（如注册表路径中的中文键名）失效。
//
// -EncodedCommand 接受 **base64 编码的 UTF-16LE** 脚本，base64 是纯 ASCII，
// 因此彻底绕开了命令行参数的代码页问题。
//
// 实现要点：
//   - 先把 Go string 按 UTF-16LE 编码（Go 的 string 是 UTF-8，需先转 []rune
//     再经 utf16.Encode 得到 []uint16，最后按小端序展开为字节）。
//   - **不要加 BOM**：-EncodedCommand 期望无 BOM 的 base64。加了 BOM 会导致
//     PowerShell 把 U+FEFF 当作脚本首个字符而报语法错误。
//   - base64 用标准编码（含 +/ 与 = 填充），PowerShell 可正确解析。
func encodePowerShellCommand(script string) string {
	return base64.StdEncoding.EncodeToString(utf16LEBytes(script))
}

// utf16LEBytes 把 Go 字符串（UTF-8）转换为 UTF-16 小端序字节流（不含 BOM）。
//
// 单独抽出是为了可单测：utf16LEBytes 的往返正确性是 -EncodedCommand 方案能成立
// 的前提，必须独立验证（见 windows_encoding_test.go）。
func utf16LEBytes(s string) []byte {
	units := utf16.Encode([]rune(s))
	out := make([]byte, 0, len(units)*2)
	for _, u := range units {
		// UTF-16 码元按小端序写入：低字节在前，高字节在后。
		out = append(out, byte(u&0xFF), byte(u>>8))
	}
	return out
}

// decodeUTF16LEBytes 把 UTF-16 小端序字节流还原为 Go 字符串。
//
// 仅供单测使用（验证 utf16LEBytes 的往返一致性），因此放在本文件而非测试文件，
// 以免测试文件需要重复实现一遍解码逻辑而失去「独立验证」的意义。
func decodeUTF16LEBytes(b []byte) string {
	if len(b)%2 != 0 {
		// 奇数长度不是合法 UTF-16LE，截掉末尾多余字节以保证不 panic。
		b = b[:len(b)-1]
	}
	units := make([]uint16, 0, len(b)/2)
	for i := 0; i+1 < len(b); i += 2 {
		units = append(units, uint16(b[i])|uint16(b[i+1])<<8)
	}
	return string(utf16.Decode(units))
}

// looksLikeUTF8 粗略判断一段字节是否为合法 UTF-8。
//
// 用途：作为「输出编码兜底」的判据。正常情况下子进程已被要求输出 UTF-8，不会
// 走到这里；但若某些环境（如被裁剪的 PowerShell、第三方替换的 reg.exe）仍按
// GBK 输出，则字节流不是合法 UTF-8，此时可据此给出更明确的错误提示，而不是
// 静默返回一串 U+FFFD 让调用方困惑。
//
// 判据：逐字节校验 UTF-8 编码规则（RFC 3629），拒绝过长编码与代理区码点。
// 这不是完整的 UTF-8 校验器，但足以区分「UTF-8 文本」与「GBK 文本」——
// GBK 的常见双字节序列（如 0xB6 0xAB）在 UTF-8 下是非法起始字节。
func looksLikeUTF8(b []byte) bool {
	for i := 0; i < len(b); {
		c := b[i]
		switch {
		case c < 0x80:
			// ASCII 单字节。
			i++
		case c >= 0xC2 && c <= 0xDF:
			// 2 字节序列：起始字节 C2-DF，续字节必须为 80-BF。
			// 起点从 C2 开始是为了排除过长编码（C0/C1 会编码出 ASCII 码点）。
			if i+1 >= len(b) || b[i+1]&0xC0 != 0x80 {
				return false
			}
			i += 2
		case c >= 0xE0 && c <= 0xEF:
			// 3 字节序列：起始字节 E0-EF，两个续字节均为 80-BF。
			if i+2 >= len(b) || b[i+1]&0xC0 != 0x80 || b[i+2]&0xC0 != 0x80 {
				return false
			}
			i += 3
		case c >= 0xF0 && c <= 0xF4:
			// 4 字节序列：起始字节 F0-F4，三个续字节均为 80-BF。
			if i+3 >= len(b) || b[i+1]&0xC0 != 0x80 || b[i+2]&0xC0 != 0x80 || b[i+3]&0xC0 != 0x80 {
				return false
			}
			i += 4
		default:
			// 0x80-0xC1 与 0xF5-0xFF 都不是合法的 UTF-8 起始字节。
			return false
		}
	}
	return true
}

// trimPowerShellOutput 清理 PowerShell 输出的首尾空白。
//
// PowerShell 的 Out-String / 管道输出常带尾部换行与行首缩进，解析前统一去除，
// 避免调用方反复 TrimSpace。之所以单独抽出：多处调用点需要一致行为。
func trimPowerShellOutput(s string) string {
	return strings.TrimSpace(s)
}
