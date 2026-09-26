package capability

// 本文件单测 windows_clixml.go 中的 CLIXML 解码函数。
//
// 不带构建标签：解码器只依赖标准库，可在 Linux 上直接运行测试。
// 测试样本取自真机（Windows 10 Pro 25H2 / PowerShell 5.1）实测输出，
// 保证解码规则与真实 CLIXML 格式一致。

import (
	"strings"
	"testing"
)

// 真机实测样本：Write-Error 产生的 CLIXML stderr。
const realCLIXMLErrorSample = "#< CLIXML\r\n" +
	"<Objs Version=\"1.1.0.1\" xmlns=\"http://schemas.microsoft.com/powershell/2004/04\">" +
	"<S S=\"Error\">Write-Error 'plain error test' : plain error test_x000D__x000A_</S>" +
	"<S S=\"Error\">    + CategoryInfo          : NotSpecified: (:) [Write-Error], WriteErrorException_x000D__x000A_</S>" +
	"<S S=\"Error\">    + FullyQualifiedErrorId : Microsoft.PowerShell.Commands.WriteErrorException_x000D__x000A_</S>" +
	"<S S=\"Error\"> _x000D__x000A_</S>" +
	"</Objs>"

// TestDecodePowerShellStderrRealSample 用真机样本验证解码。
func TestDecodePowerShellStderrRealSample(t *testing.T) {
	got := decodePowerShellStderr(realCLIXMLErrorSample)

	if strings.Contains(got, "CLIXML") || strings.Contains(got, "<Objs") || strings.Contains(got, "_x000D_") {
		t.Fatalf("解码后仍含 CLIXML 残留：\n%q", got)
	}
	if !strings.Contains(got, "plain error test") {
		t.Errorf("未还原错误文本：\n%q", got)
	}
	if !strings.Contains(got, "WriteErrorException") {
		t.Errorf("未还原 FullyQualifiedErrorId：\n%q", got)
	}
	// _x000D__x000A_ 应还原为换行（\r\n）。
	if !strings.Contains(got, "\r\n") {
		t.Errorf("未还原 _x000D__x000A_ 为换行：\n%q", got)
	}
}

// TestDecodePowerShellStderrNonCLIXML 验证普通文本 stderr 原样返回。
func TestDecodePowerShellStderrNonCLIXML(t *testing.T) {
	plain := "error: file not found\nsecond line\n"
	if got := decodePowerShellStderr(plain); got != plain {
		t.Errorf("非 CLIXML 输入应原样返回：\n期望 %q\n得到 %q", plain, got)
	}
}

// TestDecodePowerShellStderrProgressOnly 验证仅含 progress 节点的 CLIXML 返回空串。
//
// 真机实测：模块首次加载会产出 <Obj S="progress">...<AV>Preparing modules for
// first use.</AV>...</Obj>，这类噪音无实质错误信息，应被丢弃而不是透出。
func TestDecodePowerShellStderrProgressOnly(t *testing.T) {
	progressOnly := "#< CLIXML\r\n" +
		"<Objs Version=\"1.1.0.1\" xmlns=\"http://schemas.microsoft.com/powershell/2004/04\">" +
		"<Obj S=\"progress\" RefId=\"0\"><TN RefId=\"0\"><T>System.Management.Automation.PSCustomObject</T><T>System.Object</T></TN>" +
		"<MS><I64 N=\"SourceId\">1</I64><PR N=\"Record\"><AV>Preparing modules for first use.</AV><AI>0</AI><Nil /><PI>-1</PI><PC>-1</PC><T>Completed</T><SR>-1</SR><SD> </SD></PR></MS></Obj>" +
		"</Objs>"

	if got := decodePowerShellStderr(progressOnly); got != "" {
		t.Errorf("仅含 progress 的 CLIXML 应返回空串，得到 %q", got)
	}
}

// TestDecodePowerShellStderrMixedProgressAndError 验证 progress + error 混合时只保留 error。
func TestDecodePowerShellStderrMixedProgressAndError(t *testing.T) {
	mixed := "#< CLIXML\r\n" +
		"<Objs Version=\"1.1.0.1\" xmlns=\"http://schemas.microsoft.com/powershell/2004/04\">" +
		"<Obj S=\"progress\" RefId=\"0\"><MS><PR N=\"Record\"><AV>Preparing modules for first use.</AV></PR></MS></Obj>" +
		"<S S=\"Error\">real error message_x000D__x000A_</S>" +
		"</Objs>"

	got := decodePowerShellStderr(mixed)
	if strings.Contains(got, "Preparing modules") {
		t.Errorf("progress 噪音不应出现在结果中：\n%q", got)
	}
	if !strings.Contains(got, "real error message") {
		t.Errorf("未还原错误文本：\n%q", got)
	}
}

// TestDecodePowerShellStderrHTMLEntities 验证 XML 实体反转义。
func TestDecodePowerShellStderrHTMLEntities(t *testing.T) {
	sample := "#< CLIXML\r\n" +
		"<Objs Version=\"1.1.0.1\" xmlns=\"http://schemas.microsoft.com/powershell/2004/04\">" +
		"<S S=\"Error\">a &lt; b &amp;&amp; c &gt; d &quot;quoted&quot; &apos;single&apos;</S>" +
		"</Objs>"

	got := decodePowerShellStderr(sample)
	want := `a < b && c > d "quoted" 'single'`
	if got != want {
		t.Errorf("XML 实体反转义错误：\n期望 %q\n得到 %q", want, got)
	}
}

// TestDecodePowerShellStderrAmpersandBeforeEntity 验证 &amp;lt; 正确还原为字面量 "&lt;"。
//
// 这检验替换顺序：若先替换 &amp; 再替换 &lt;，会把 "&amp;lt;" 错误还原成 "<"。
func TestDecodePowerShellStderrAmpersandBeforeEntity(t *testing.T) {
	sample := "#< CLIXML\r\n" +
		"<Objs Version=\"1.1.0.1\" xmlns=\"http://schemas.microsoft.com/powershell/2004/04\">" +
		"<S S=\"Error\">&amp;lt;</S>" +
		"</Objs>"

	got := decodePowerShellStderr(sample)
	if got != "&lt;" {
		t.Errorf("&amp;lt; 应还原为字面量 %q，得到 %q", "&lt;", got)
	}
}

// TestDecodeCLIXMLHexEscapesNonBMP 验证代理对（非 BMP 字符）正确还原。
func TestDecodeCLIXMLHexEscapesNonBMP(t *testing.T) {
	// U+1F600 (😀) 的 UTF-16 代理对为 D83D DE00。
	got := decodeCLIXMLHexEscapes("emoji:_xD83D__xDE00_")
	if got != "emoji:😀" {
		t.Errorf("代理对还原错误：期望 %q，得到 %q", "emoji:😀", got)
	}
}

// TestDecodeCLIXMLHexEscapesPlain 验证不含转义的文本原样返回。
func TestDecodeCLIXMLHexEscapesPlain(t *testing.T) {
	plain := "no escapes here"
	if got := decodeCLIXMLHexEscapes(plain); got != plain {
		t.Errorf("无转义文本应原样返回：期望 %q，得到 %q", plain, got)
	}
}

// TestDecodePowerShellStderrEmpty 验证空输入。
func TestDecodePowerShellStderrEmpty(t *testing.T) {
	if got := decodePowerShellStderr(""); got != "" {
		t.Errorf("空输入应返回空串，得到 %q", got)
	}
}
