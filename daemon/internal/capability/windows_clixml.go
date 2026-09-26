package capability

// 本文件实现 PowerShell 的 CLIXML 输出解码。
//
// 背景：为什么 stderr 会是 CLIXML
// ==============================
// Windows PowerShell 5.1 在**标准错误不是终端**时（守护进程通过管道捕获 stderr
// 即属此情形），会把错误流与 progress 流序列化成 CLIXML（一种 XML 方言）而不是
// 纯文本。真机实测的 windows.script.exec stderr 形如：
//
//	#< CLIXML
//	<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">
//	  <Obj S="progress" RefId="0">...<AV>Preparing modules for first use.</AV>...</Obj>
//	  <S S="Error">Write-Error 'x' : x_x000D__x000A_</S>
//	</Objs>
//
// 这会让调用方拿到一堆 XML 噪音，而不是可读的错误文本。
//
// 为什么不在 PowerShell 侧关掉
// ============================
// 已尝试并排除的方案：
//
//  1. $ProgressPreference = 'SilentlyContinue'：只抑制 progress **流的内容**，
//     但在 -EncodedCommand 模式下 progress 记录仍会被序列化进 CLIXML
//     （真机实测：仍出现 <Obj S="progress"> 节点）。且它对错误流完全无效。
//
//  2. -OutputFormat Text：单独用 -Command 时有效，但**与 -EncodedCommand 不兼容**
//     （-EncodedCommand 隐含 -OutputFormat XML，后者被忽略），真机实测仍输出 CLIXML。
//     而 -Command 会因 ANSI 代码页损坏中文，不能改用。
//
//  3. -Command -（stdin 传脚本）+ -OutputFormat Text：有效，但 stdin 的读取编码
//     受 [Console]::InputEncoding 影响，而设置该编码的语句本身也要经 stdin 传入，
//     存在先后矛盾；且会丢失 -EncodedCommand 的 UTF-16LE 中文保证。
//
// 因此选择在 Go 侧解码 CLIXML：保留 -EncodedCommand 的中文保证，同时把 stderr
// 还原为可读纯文本。这是唯一不牺牲正确性的方案。
//
// 解码规则
// ========
//   - CLIXML 用 <S S="Error">文本</S> 表示一段错误文本（S 属性为流的名字）；
//   - 文本内的换行被编码为字面量 "_x000D__x000A_"（CR LF 的十六进制转义），
//     需还原为 "\r\n"；其他 _xHHHH_ 形式同理还原为对应 Unicode 码点；
//   - XML 实体（&amp; &lt; &gt; &quot; &apos;）需反转义；
//   - 非 CLIXML 输入原样返回（保持对纯文本 stderr 的兼容）。
//
// 只依赖标准库（encoding/xml 或手写扫描），不引入第三方依赖。

import (
	"strconv"
	"strings"
	"unicode/utf16"
)

// clixmlHeader 是 CLIXML 输出的固定起始标记。
// 用它判断一段 stderr 是否为 CLIXML，避免对普通文本做无谓解析。
const clixmlHeader = "#< CLIXML"

// decodePowerShellStderr 把 PowerShell 的 stderr 输出还原为可读纯文本。
//
// 若输入不含 CLIXML 标记，原样返回（普通文本 stderr 不受影响）。
// 若含 CLIXML，则提取所有 <S S="...">文本</S> 节点并按行拼接，
// 同时还原 _xHHHH_ 转义与 XML 实体。
//
// 之所以不引入 encoding/xml：CLIXML 里的 <S> 节点可能包含未转义的裸文本，
// 且我们只关心文本内容，手写扫描更简单、更容错（XML 解析器遇到畸形输入会整体失败，
// 而这里希望「尽力还原」）。
func decodePowerShellStderr(raw string) string {
	if !strings.Contains(raw, clixmlHeader) {
		return raw
	}

	// 剥掉 "#< CLIXML" 行，只保留 XML 主体。
	body := raw
	if idx := strings.Index(body, clixmlHeader); idx >= 0 {
		body = body[idx+len(clixmlHeader):]
	}

	var segments []string
	rest := body
	for {
		// 定位下一个 <S ...> 开始标签。
		open := strings.Index(rest, "<S ")
		if open < 0 {
			break
		}
		// 找到开始标签的结束 '>'。
		openEnd := strings.Index(rest[open:], ">")
		if openEnd < 0 {
			break
		}
		openEnd += open
		// 定位对应的 </S>。
		closeIdx := strings.Index(rest[openEnd:], "</S>")
		if closeIdx < 0 {
			break
		}
		closeIdx += openEnd

		text := rest[openEnd+1 : closeIdx]
		segments = append(segments, decodeCLIXMLText(text))
		rest = rest[closeIdx+len("</S>"):]
	}

	if len(segments) == 0 {
		// 有 CLIXML 头但没有可提取的 <S> 节点（如仅含 progress 的 <Obj>），
		// 返回空串——此时 stderr 无实质错误信息，不应把 XML 噪音透出。
		return ""
	}

	// 各 <S> 段本身已含换行（还原后），直接拼接。
	return strings.TrimRight(strings.Join(segments, ""), "\r\n")
}

// decodeCLIXMLText 还原 CLIXML 文本节点中的转义。
//
//   - _xHHHH_ → 对应 UTF-16 码元组成的字符（如 _x000D_ → '\r'）；
//   - XML 实体反转义。
func decodeCLIXMLText(s string) string {
	s = decodeCLIXMLHexEscapes(s)
	return unescapeXMLEntities(s)
}

// decodeCLIXMLHexEscapes 还原 _xHHHH_ 形式的转义。
//
// CLIXML 把控制字符与部分特殊字符写成 _xHHHH_（H 为十六进制）。
// 连续多个转义会被逐个还原（如 _x000D__x000A_ → "\r\n"）。
//
// 注意：代理对（surrogate pair）会以两个连续 _xHHHH_ 出现，这里收集连续的
// 转义序列后统一用 utf16.Decode 处理，保证非 BMP 字符（如 emoji）正确还原。
func decodeCLIXMLHexEscapes(s string) string {
	if !strings.Contains(s, "_x") {
		return s
	}

	var out strings.Builder
	out.Grow(len(s))

	// pending 收集连续的 _xHHHH_ 码元，遇到非转义内容时统一解码。
	var pending []uint16
	flush := func() {
		if len(pending) == 0 {
			return
		}
		out.WriteString(string(utf16.Decode(pending)))
		pending = pending[:0]
	}

	i := 0
	for i < len(s) {
		if s[i] == '_' && i+6 < len(s) && s[i+1] == 'x' && s[i+6] == '_' {
			if v, err := strconv.ParseUint(s[i+2:i+6], 16, 32); err == nil {
				pending = append(pending, uint16(v))
				i += 7
				continue
			}
		}
		flush()
		out.WriteByte(s[i])
		i++
	}
	flush()
	return out.String()
}

// unescapeXMLEntities 反转义 XML 的五个预定义实体。
//
// 顺序很重要：必须先替换 &amp; 之外的其他实体，最后再处理 &amp;，
// 否则 "&amp;lt;" 会被错误地还原成 "<"（它本应还原为字面量 "&lt;"）。
func unescapeXMLEntities(s string) string {
	if !strings.Contains(s, "&") {
		return s
	}
	replacer := strings.NewReplacer(
		"&lt;", "<",
		"&gt;", ">",
		"&quot;", `"`,
		"&apos;", "'",
		"&amp;", "&",
	)
	return replacer.Replace(s)
}
