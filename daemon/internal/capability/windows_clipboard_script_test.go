package capability

import (
	"strings"
	"testing"
)

// TestBuildWindowsClipboardSetScriptContainsRetry 验证脚本确实带重试循环。
//
// 这是真机实测驱动的修复：Windows 剪贴板被其他进程占用时 Set-Clipboard 会抛
// ExternalException，单次调用失败，最坏重试到第 9 次才成功。
func TestBuildWindowsClipboardSetScriptContainsRetry(t *testing.T) {
	script := buildWindowsClipboardSetScript("'hello'")

	for _, want := range []string{"for ($i = 0;", "try {", "catch {", "Start-Sleep", "Set-Clipboard -Value 'hello'"} {
		if !strings.Contains(script, want) {
			t.Errorf("脚本缺少 %q：\n%s", want, script)
		}
	}
	// 尝试次数与间隔必须来自常量，避免脚本与常量脱节。
	if !strings.Contains(script, "20") {
		t.Errorf("脚本未使用重试次数常量值：\n%s", script)
	}
	if !strings.Contains(script, "100") {
		t.Errorf("脚本未使用重试间隔常量值：\n%s", script)
	}
}

// TestBuildWindowsClipboardSetScriptFailsLoudly 验证重试耗尽后以非零退出码失败，
// 而不是静默成功（否则调用方会误以为已写入剪贴板）。
func TestBuildWindowsClipboardSetScriptFailsLoudly(t *testing.T) {
	script := buildWindowsClipboardSetScript("'x'")

	if !strings.Contains(script, "exit 1") {
		t.Errorf("重试耗尽后应 exit 1 而非静默返回：\n%s", script)
	}
	if !strings.Contains(script, "Write-Error") {
		t.Errorf("重试耗尽后应写错误信息：\n%s", script)
	}
}

// TestBuildWindowsClipboardSetScriptInjectionSafety 验证文本字面量被原样嵌入，
// 脚本构造本身不做任何转义（转义由 encodePowerShellText 负责）。
// 这里确认含引号/分号的字面量不会破坏脚本结构——即函数只做字符串拼接。
func TestBuildWindowsClipboardSetScriptInjectionSafety(t *testing.T) {
	// encodePowerShellText 会把内部单引号双写，这里模拟其输出。
	literal := "'it''s; Remove-Item C:\\ -Recurse'"
	script := buildWindowsClipboardSetScript(literal)

	if !strings.Contains(script, literal) {
		t.Errorf("字面量应原样嵌入（转义由 encodePowerShellText 负责）：\n%s", script)
	}
	// 字面量出现在 Set-Clipboard -Value 之后。
	idx := strings.Index(script, "Set-Clipboard -Value ")
	if idx < 0 || !strings.HasPrefix(script[idx+len("Set-Clipboard -Value "):], literal) {
		t.Errorf("字面量未紧跟 Set-Clipboard -Value：\n%s", script)
	}
}

// TestBuildWindowsClipboardSetScriptEmptyLiteral 验证空字符串字面量（清空剪贴板）
// 也能正常构造脚本。
func TestBuildWindowsClipboardSetScriptEmptyLiteral(t *testing.T) {
	script := buildWindowsClipboardSetScript("''")
	if !strings.Contains(script, "Set-Clipboard -Value ''") {
		t.Errorf("空字面量应正常嵌入：\n%s", script)
	}
}
