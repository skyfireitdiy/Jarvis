//go:build windows

package service

import (
	"strings"
	"testing"
)

// TestBuildTaskXMLCriticalSettings 验证计划任务 XML 包含所有修复「频繁退出」缺陷
// 所必需的关键设置。
//
// 背景：旧实现用 schtasks /SC ONLOGON /RL HIGHEST 注册，真机实测生成的任务存在
// RestartCount=0、ExecutionTimeLimit=PT72H、电池时停止等缺陷，导致 daemon 经常
// 退出且不自动恢复。本测试锁定修复后的关键字段，防止回归。
func TestBuildTaskXMLCriticalSettings(t *testing.T) {
	xmlBody, err := buildTaskXML(Options{ExecPath: `C:\Users\test\.jarvis\bin\jarvis-daemon.exe`})
	if err != nil {
		t.Fatalf("buildTaskXML 失败: %v", err)
	}

	cases := []struct {
		name string
		want string
		why  string
	}{
		// 进程异常退出后自动重启（旧实现 RestartCount=0，崩溃后永不恢复）。
		{"重启间隔", "<Interval>PT1M</Interval>", "异常退出后应每分钟重试"},
		{"重启次数", "<Count>3</Count>", "异常退出后应重试 3 次"},

		// 无执行时限（旧实现默认 PT72H，运行满 72 小时被强制结束）。
		{"执行时限", "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", "不应有 72 小时强制结束"},

		// 电池策略（旧实现 True，笔记本切电池即被停）。
		{"电池不禁用启动", "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>", "电池供电也应能启动"},
		{"电池不停止", "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>", "切到电池不应停止"},

		// 错过触发后补跑。
		{"错过后补跑", "<StartWhenAvailable>true</StartWhenAvailable>", "休眠错过触发后应补跑"},

		// 避免多实例争抢 PID 文件与端口。
		{"多实例策略", "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", "不应重复启动"},

		// 保留原有行为：登录触发 + 最高权限 + 交互令牌。
		{"登录触发", "<LogonTrigger>", "应保留登录时自启"},
		{"最高权限", "<RunLevel>HighestAvailable</RunLevel>", "应保留最高权限"},
		{"交互令牌", "<LogonType>InteractiveToken</LogonType>", "应保留交互会话运行（桌面能力依赖）"},

		// 命令与参数必须分开填，否则 Task Scheduler 会把整串当命令名。
		{"可执行文件", `<Command>C:\Users\test\.jarvis\bin\jarvis-daemon.exe</Command>`, "Command 只放可执行文件路径"},
		{"启动参数", "<Arguments>run</Arguments>", "参数应放入 Arguments"},
	}

	for _, c := range cases {
		if !strings.Contains(xmlBody, c.want) {
			t.Errorf("[%s] XML 缺少 %q（%s）\n实际 XML:\n%s", c.name, c.want, c.why, xmlBody)
		}
	}

	// 旧缺陷的典型值不得出现。
	for _, bad := range []string{"PT72H", "<DisallowStartIfOnBatteries>true<", "<StopIfGoingOnBatteries>true<"} {
		if strings.Contains(xmlBody, bad) {
			t.Errorf("XML 仍包含旧缺陷配置 %q", bad)
		}
	}
}

// TestBuildTaskXMLArgumentsSplit 验证带参数时 Arguments 正确拼接且不与 Command 混淆。
func TestBuildTaskXMLArgumentsSplit(t *testing.T) {
	xmlBody, err := buildTaskXML(Options{
		ExecPath:   `C:\jarvis-daemon.exe`,
		Listen:     "127.0.0.1:17800",
		Gateway:    "http://10.0.0.1:5005",
		ConfigPath: `C:\Users\me\.jarvis\daemon\config.yaml`,
	})
	if err != nil {
		t.Fatalf("buildTaskXML 失败: %v", err)
	}
	if !strings.Contains(xmlBody, "<Command>C:\\jarvis-daemon.exe</Command>") {
		t.Errorf("Command 应为纯可执行文件路径\n%s", xmlBody)
	}
	wantArgs := `<Arguments>run --listen 127.0.0.1:17800 --gateway http://10.0.0.1:5005 --config C:\Users\me\.jarvis\daemon\config.yaml</Arguments>`
	if !strings.Contains(xmlBody, wantArgs) {
		t.Errorf("Arguments 不符合预期\nwant: %s\n实际 XML:\n%s", wantArgs, xmlBody)
	}
}

// TestEncodeUTF16LE 验证 UTF-16LE 编码（schtasks /XML 的硬性要求）。
//
// 断言 BOM 为 FF FE，且 ASCII 字符按小端双字节展开（'r'=0x72 → 72 00）。
func TestEncodeUTF16LE(t *testing.T) {
	got := encodeUTF16LE("run")
	if len(got) != 2+3*2 {
		t.Fatalf("长度错误: got %d, want %d", len(got), 2+3*2)
	}
	if got[0] != 0xFF || got[1] != 0xFE {
		t.Errorf("BOM 应为 FF FE，实际 %02X %02X", got[0], got[1])
	}
	if got[2] != 'r' || got[3] != 0x00 {
		t.Errorf("'r' 编码错误: %02X %02X", got[2], got[3])
	}
	if got[4] != 'u' || got[5] != 0x00 {
		t.Errorf("'u' 编码错误: %02X %02X", got[4], got[5])
	}
	if got[6] != 'n' || got[7] != 0x00 {
		t.Errorf("'n' 编码错误: %02X %02X", got[6], got[7])
	}
}

// TestEncodeUTF16LENonASCII 验证非 ASCII 字符（中文）正确编码为 UTF-16 码元。
//
// 描述字段含中文，若编码错误会导致 schtasks 解析失败或任务描述乱码。
func TestEncodeUTF16LENonASCII(t *testing.T) {
	got := encodeUTF16LE("中") // U+4E2D
	if len(got) != 4 {
		t.Fatalf("长度错误: got %d, want 4", len(got))
	}
	if got[2] != 0x2D || got[3] != 0x4E {
		t.Errorf("'中' 应编码为 2D 4E（小端），实际 %02X %02X", got[2], got[3])
	}
}

// TestXmlEscape 验证 XML 特殊字符转义，避免路径含 & 等字符时生成非法 XML。
func TestXmlEscape(t *testing.T) {
	cases := []struct{ in, want string }{
		{"plain", "plain"},
		{`C:\a&b\c.exe`, `C:\a&amp;b\c.exe`},
		{"<tag>", "&lt;tag&gt;"},
		{`say "hi"`, "say &quot;hi&quot;"},
	}
	for _, c := range cases {
		if got := xmlEscape(c.in); got != c.want {
			t.Errorf("xmlEscape(%q) = %q, 期望 %q", c.in, got, c.want)
		}
	}
}

// TestQuoteArgs 验证含空白的参数被引号包裹。
func TestQuoteArgs(t *testing.T) {
	got := quoteArgs([]string{"run", "--config", `C:\Program Files\a.yaml`})
	want := `run --config "C:\Program Files\a.yaml"`
	if got != want {
		t.Errorf("quoteArgs = %q, 期望 %q", got, want)
	}
}
