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
//
// preamble 参数为脚本前置语句（windowsPowerShellPreamble），用于剥离回显噪音：
// PowerShell 对**非终止错误**（如 Write-Error）会回显整条出错语句的源码，而前置
// 语句被拼在脚本最前面，于是它本身也被一起回显（真机实测暴露）。这属于纯噪音，
// 应剥离。传空串表示不做剥离。
func decodePowerShellStderr(raw, preamble string) string {
	if !strings.Contains(raw, clixmlHeader) {
		return stripPowerShellPreambleEcho(raw, preamble)
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
	// 拼接后再剥离 preamble 回显噪音（CLIXML 的 <S S="Error"> 同样会回显前置语句）。
	return stripPowerShellPreambleEcho(strings.TrimRight(strings.Join(segments, ""), "\r\n"), preamble)
}

// stripPowerShellPreambleEcho 剥离 stderr 中回显的 PowerShell 前置语句。
//
// 背景：PowerShell 对**非终止错误**（如 Write-Error）会回显出错语句的完整源码。
// 由于 windowsPowerShellPreamble 被拼在用户脚本最前面，它会被一起回显，形如：
//
//	[Console]::OutputEncoding = ...::UTF8; $OutputEncoding = ...::UTF8;
//	 [Console]::InputEncoding = ...::UTF8; $ProgressPreference = 'SilentlyContinue'
//	Write-Error 'x' : x
//
// 回显文本里 preamble 的换行被 PowerShell 改写过（const 内没有换行，回显却多出
// 换行与缩进），因此不能做逐字匹配。这里改为**按特征行过滤**：整行同时包含
// "OutputEncoding" 与 "UTF8"、或整行同时包含 "ProgressPreference" 与
// "SilentlyContinue" 的行视为 preamble 回显行，予以丢弃。
//
// 这样只删噪音行，不影响用户脚本自身的错误信息（用户代码里同时出现这几个
// 标识符的概率极低，且即便出现也仅丢失该行）。
func stripPowerShellPreambleEcho(s, preamble string) string {
	if preamble == "" || s == "" {
		return s
	}
	// 快速判断：没有编码设置特征就不必逐行处理。
	if !strings.Contains(s, "OutputEncoding") && !strings.Contains(s, "ProgressPreference") {
		return s
	}

	lines := strings.Split(s, "\n")
	kept := lines[:0]
	for _, line := range lines {
		if isPowerShellPreambleEchoLine(line) {
			continue
		}
		kept = append(kept, line)
	}
	return strings.Join(kept, "\n")
}

// isPowerShellPreambleEchoLine 判断一行是否为 windowsPowerShellPreamble 的回显。
func isPowerShellPreambleEchoLine(line string) bool {
	if strings.Contains(line, "OutputEncoding") && strings.Contains(line, "UTF8") {
		return true
	}
	if strings.Contains(line, "ProgressPreference") && strings.Contains(line, "SilentlyContinue") {
		return true
	}
	return false
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
