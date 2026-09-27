package service

import (
	"encoding/base64"
	"strings"
	"testing"
	"unicode/utf16"
)

// TestQuotePowerShellArg 验证参数转义：只有含空白/特殊字符时才加单引号，
// 内部单引号按 PowerShell 约定写成两个连续单引号。
func TestQuotePowerShellArg(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"空串", "", "''"},
		{"纯 ASCII 无特殊字符", "/Create", "/Create"},
		{"含空格", "C:\\Program Files\\x.exe", "'C:\\Program Files\\x.exe'"},
		{"含单引号", "a'b", "'a''b'"},
		{"含双引号", `a"b`, `'a"b'`},
		{"含 cmd 元字符 &", "a&b", "'a&b'"},
		{"含 $", "a$b", "'a$b'"},
		{"含括号", "a(b)", "'a(b)'"},
		{"含逗号", "a,b", "'a,b'"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := quotePowerShellArg(c.in); got != c.want {
				t.Errorf("quotePowerShellArg(%q) = %q, 期望 %q", c.in, got, c.want)
			}
		})
	}
}

// TestStripPowerShellClixml 验证 CLIXML 噪音被剔除、真实错误文本保留。
// 用例取自真机 Windows 上 install 失败时的实际输出。
func TestStripPowerShellClixml(t *testing.T) {
	// 真机输出：CLIXML 头 + Objs 段（progress 记录）混杂在错误文本之前。
	realWorld := "#< CLIXML\n<Objs Version=\"1.1.0.1\" xmlns=\"http://schemas.microsoft.com/powershell/2004/04\"><Obj S=\"progress\" RefId=\"0\"><TN RefId=\"0\"><T>System.Management.Automation.PSCustomObject</T><T>System.Object</T></TN><MS><I64 N=\"SourceId\">1</I64><PR N=\"Record\"><AV>正在准备首次使用模块。</AV><AI>0</AI><Nil /><PI>-1</PI><PC>-1</PC><T>Completed</T><SR>-1</SR><SD> </SD></PR></MS></Obj></Objs>\n错误: 拒绝访问。"
	got := stripPowerShellClixml(realWorld)
	want := "错误: 拒绝访问。"
	if got != want {
		t.Errorf("stripPowerShellClixml 未正确清理:\n got = %q\nwant = %q", got, want)
	}

	cases := []struct {
		name string
		in   string
		want string
	}{
		{"无 CLIXML 原样返回", "错误: 拒绝访问。", "错误: 拒绝访问。"},
		{"仅 CLIXML 头", "#< CLIXML\n错误: 拒绝访问。", "错误: 拒绝访问。"},
		{"仅 Objs 段", "<Objs Version=\"1.1\"><Obj/></Objs>错误: 拒绝访问。", "错误: 拒绝访问。"},
		{"CLIXML 在错误之后", "错误: 拒绝访问。\n#< CLIXML\n<Objs><Obj/></Objs>", "错误: 拒绝访问。"},
		{"空串", "", ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := stripPowerShellClixml(c.in); got != c.want {
				t.Errorf("stripPowerShellClixml(%q) = %q, 期望 %q", c.in, got, c.want)
			}
		})
	}
}

// TestBuildPowerShellScriptStructure 验证脚本结构：先执行命令再改编码再写出，
// 顺序不可调换（先改编码会导致 GBK 输出被按 UTF-8 误解码）。
func TestBuildPowerShellScriptStructure(t *testing.T) {
	script := buildPowerShellScript("schtasks", []string{"/Create", "/TN", "Jarvis-Daemon"})

	idxProgress := strings.Index(script, "$ProgressPreference='SilentlyContinue'")
	idxExec := strings.Index(script, "$out = & schtasks")
	idxCode := strings.Index(script, "$code = $LASTEXITCODE")
	idxSetEnc := strings.Index(script, "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8")
	idxWrite := strings.Index(script, "[Console]::Out.Write($out)")
	idxExit := strings.Index(script, "exit $code")

	if idxProgress < 0 {
		t.Fatalf("脚本未包含关闭进度流片段: %q", script)
	}
	if idxExec < 0 {
		t.Fatalf("脚本未包含执行命令片段: %q", script)
	}
	if idxCode < 0 {
		t.Fatalf("脚本未包含捕获退出码片段: %q", script)
	}
	if idxSetEnc < 0 {
		t.Fatalf("脚本未包含设置 UTF-8 输出编码片段: %q", script)
	}
	if idxWrite < 0 {
		t.Fatalf("脚本未包含写出片段: %q", script)
	}
	if idxExit < 0 {
		t.Fatalf("脚本未包含透传退出码片段: %q", script)
	}
	// 关键顺序：关闭进度流 → 执行 → 捕获退出码 → 改编码 → 写出 → 透传退出码。
	// 捕获 $LASTEXITCODE 必须在执行之后（否则拿到的是上一条命令的退出码）；
	// exit 必须在最后（否则后续语句不会执行）。
	if !(idxProgress < idxExec && idxExec < idxCode && idxCode < idxSetEnc && idxSetEnc < idxWrite && idxWrite < idxExit) {
		t.Errorf("脚本片段顺序错误（应为 关闭进度流 < 执行 < 捕获退出码 < 改编码 < 写出 < 透传退出码）：progress=%d exec=%d code=%d setEnc=%d write=%d exit=%d\n%s",
			idxProgress, idxExec, idxCode, idxSetEnc, idxWrite, idxExit, script)
	}
	// stderr 合并，保证失败原因也能被捕获。
	if !strings.Contains(script, "2>&1") {
		t.Errorf("脚本未合并 stderr: %q", script)
	}
	// 非 ASCII 参数应被单引号包裹。
	script2 := buildPowerShellScript("schtasks", []string{"/TR", "C:\\Program Files\\jarvis daemon.exe"})
	if !strings.Contains(script2, "'C:\\Program Files\\jarvis daemon.exe'") {
		t.Errorf("含空格参数未被正确引用: %q", script2)
	}
}

// TestEncodePowerShellCommandRoundTrip 验证 -EncodedCommand 编码可被正确还原：
// 这是「脚本内非 ASCII 字符不损坏」的前提。
func TestEncodePowerShellCommandRoundTrip(t *testing.T) {
	original := "$out = & schtasks /TN '计划任务 中文' 2>&1"
	encoded := encodePowerShellCommand(original)

	// base64 必须是纯 ASCII。
	for i := 0; i < len(encoded); i++ {
		if encoded[i] > 0x7F {
			t.Fatalf("base64 含非 ASCII 字节: %q", encoded)
		}
	}

	raw, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		t.Fatalf("base64 解码失败: %v", err)
	}
	if len(raw)%2 != 0 {
		t.Fatalf("UTF-16LE 字节数应为偶数，实际 %d", len(raw))
	}
	units := make([]uint16, 0, len(raw)/2)
	for i := 0; i+1 < len(raw); i += 2 {
		units = append(units, uint16(raw[i])|uint16(raw[i+1])<<8)
	}
	if got := string(utf16.Decode(units)); got != original {
		t.Errorf("往返后不一致:\n got = %q\nwant = %q", got, original)
	}
}
