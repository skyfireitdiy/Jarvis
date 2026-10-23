//go:build linux

package capability

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// writeTestFile 写入测试文件并返回路径。
func writeTestFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "edit_target.txt")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入测试文件失败: %v", err)
	}
	return path
}

// readTestFile 读取文件内容。
func readTestFile(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取文件失败: %v", err)
	}
	return string(data)
}

// TestFSEditFileUniqueMatch 验证唯一匹配时正常替换。
func TestFSEditFileUniqueMatch(t *testing.T) {
	path := writeTestFile(t, "hello world\nfoo bar\n")
	res, err := fsEditFile(path, "foo bar", "baz qux", false)
	if err != nil {
		t.Fatalf("编辑失败: %v", err)
	}
	m := res
	if m["replaced"] != true {
		t.Errorf("replaced 应为 true，实际 %v", m["replaced"])
	}
	if m["match_count"].(int) != 1 {
		t.Errorf("match_count 应为 1，实际 %v", m["match_count"])
	}
	got := readTestFile(t, path)
	if got != "hello world\nbaz qux\n" {
		t.Errorf("替换结果不符:\n期望 %q\n实际 %q", "hello world\nbaz qux\n", got)
	}
}

// TestFSEditFileMultipleMatchNeedsReplaceAll 验证多匹配且 replace_all=false 时报错。
func TestFSEditFileMultipleMatchNeedsReplaceAll(t *testing.T) {
	path := writeTestFile(t, "abc\nabc\n")
	_, err := fsEditFile(path, "abc", "xyz", false)
	if err == nil {
		t.Fatal("多匹配且 replace_all=false 应报错，实际未报错")
	}
	if !strings.Contains(err.Error(), "2 处") {
		t.Errorf("错误信息应包含匹配次数，实际: %v", err)
	}
	// 文件不应被修改
	if got := readTestFile(t, path); got != "abc\nabc\n" {
		t.Errorf("多匹配失败时文件不应被修改，实际 %q", got)
	}

	// replace_all=true 应全部替换
	if _, err := fsEditFile(path, "abc", "xyz", true); err != nil {
		t.Fatalf("replace_all=true 编辑失败: %v", err)
	}
	if got := readTestFile(t, path); got != "xyz\nxyz\n" {
		t.Errorf("replace_all 结果不符，实际 %q", got)
	}
}

// TestFSEditFileQuoteNormalization 验证弯引号归一化匹配（对齐 tool_registry）。
func TestFSEditFileQuoteNormalization(t *testing.T) {
	// 文件内容是弯引号，search 用直引号（冒号保持一致），应能匹配。
	// 替换结果与 tool_registry 的 preserve_quote_style 完全一致：
	// 全角冒号不在开引号上下文集合中，故两个引号都转为右弯引号 ”。
	path := writeTestFile(t, "他说：“你好”\n")
	if _, err := fsEditFile(path, `他说："你好"`, `她说："再见"`, false); err != nil {
		t.Fatalf("引号归一化匹配失败: %v", err)
	}
	got := readTestFile(t, path)
	if got != "她说：”再见”\n" {
		t.Errorf("引号归一化替换结果不符，实际 %q", got)
	}
}

// TestFSEditFileInvalidSearch 验证空 search 与 search==replace 报错。
func TestFSEditFileInvalidSearch(t *testing.T) {
	path := writeTestFile(t, "content\n")
	if _, err := fsEditFile(path, "", "x", false); err == nil {
		t.Error("空 search 应报错")
	}
	if _, err := fsEditFile(path, "content", "content", false); err == nil {
		t.Error("search==replace 应报错")
	}
}

// TestFSEditFileNotFound 验证未找到匹配时报错且不修改文件。
func TestFSEditFileNotFound(t *testing.T) {
	path := writeTestFile(t, "hello\n")
	if _, err := fsEditFile(path, "not-exist", "x", false); err == nil {
		t.Fatal("未找到匹配应报错")
	}
	if got := readTestFile(t, path); got != "hello\n" {
		t.Errorf("未找到匹配时文件不应被修改，实际 %q", got)
	}
}

// TestFSEditByLineReplaceRange 验证按行号闭区间替换。
func TestFSEditByLineReplaceRange(t *testing.T) {
	path := writeTestFile(t, "line1\nline2\nline3\nline4\n")
	res, err := fsEditByLine(path, 2, 3, "X\nY")
	if err != nil {
		t.Fatalf("按行号替换失败: %v", err)
	}
	m := res
	if m["start_line"].(int) != 2 || m["end_line"].(int) != 3 {
		t.Errorf("返回行号不符: %v", m)
	}
	got := readTestFile(t, path)
	if got != "line1\nX\nY\nline4\n" {
		t.Errorf("按行号替换结果不符:\n期望 %q\n实际 %q", "line1\nX\nY\nline4\n", got)
	}
}

// TestFSEditByLineOutOfRange 验证行号越界报错且不修改文件。
func TestFSEditByLineOutOfRange(t *testing.T) {
	path := writeTestFile(t, "line1\nline2\n")
	if _, err := fsEditByLine(path, 3, 3, "x"); err == nil {
		t.Fatal("start_line 越界应报错")
	}
	if _, err := fsEditByLine(path, 2, 1, "x"); err == nil {
		t.Fatal("end_line < start_line 应报错")
	}
	if _, err := fsEditByLine(path, 0, 1, "x"); err == nil {
		t.Fatal("start_line < 1 应报错")
	}
	if got := readTestFile(t, path); got != "line1\nline2\n" {
		t.Errorf("越界时文件不应被修改，实际 %q", got)
	}
}

// TestFSEditByLineReplaceToEOF 验证替换到文件末尾。
func TestFSEditByLineReplaceToEOF(t *testing.T) {
	path := writeTestFile(t, "a\nb\nc\n")
	if _, err := fsEditByLine(path, 2, 3, "END"); err != nil {
		t.Fatalf("替换到末尾失败: %v", err)
	}
	got := readTestFile(t, path)
	// 与 tool_registry 行为一致：替换到末尾时不额外补末尾换行。
	if got != "a\nEND" {
		t.Errorf("替换到末尾结果不符，实际 %q", got)
	}
}

// TestFSEditFileBackupCleaned 验证编辑成功后 .bak 备份被清理。
func TestFSEditFileBackupCleaned(t *testing.T) {
	path := writeTestFile(t, "hello\n")
	if _, err := fsEditFile(path, "hello", "hi", false); err != nil {
		t.Fatalf("编辑失败: %v", err)
	}
	if _, err := os.Stat(path + ".bak"); !os.IsNotExist(err) {
		t.Error("编辑成功后 .bak 备份应被清理")
	}
}
