package daemonlog

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestLogPathInHomeJarvisLogs 验证日志路径位于 ~/.jarvis/logs 下。
func TestLogPathInHomeJarvisLogs(t *testing.T) {
	path, err := LogPath()
	if err != nil {
		t.Fatalf("LogPath 失败: %v", err)
	}
	home, err := os.UserHomeDir()
	if err != nil {
		t.Fatalf("获取主目录失败: %v", err)
	}
	want := filepath.Join(home, ".jarvis", "logs", "daemon.log")
	if path != want {
		t.Fatalf("期望 %s，实际 %s", want, path)
	}
}

// TestRotateWriterWriteAndAppend 验证写入内容正确且多次写入为追加。
func TestRotateWriterWriteAndAppend(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.log")
	w, err := newRotateWriter(path)
	if err != nil {
		t.Fatalf("newRotateWriter 失败: %v", err)
	}
	defer w.Close()

	if _, err := w.Write([]byte("first\n")); err != nil {
		t.Fatalf("写入失败: %v", err)
	}
	if _, err := w.Write([]byte("second\n")); err != nil {
		t.Fatalf("追加失败: %v", err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取失败: %v", err)
	}
	if got := string(data); got != "first\nsecond\n" {
		t.Fatalf("内容不符，实际 %q", got)
	}
}

// TestRotateWriterRotatesWhenExceedingMax 验证超过上限时轮转并保留备份。
func TestRotateWriterRotatesWhenExceedingMax(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.log")
	w, err := newRotateWriter(path)
	if err != nil {
		t.Fatalf("newRotateWriter 失败: %v", err)
	}
	defer w.Close()

	// 预置一个接近上限的文件，使下一次写入触发轮转。
	big := strings.Repeat("x", maxBytes)
	if _, err := w.Write([]byte(big)); err != nil {
		t.Fatalf("写入大块失败: %v", err)
	}
	if _, err := w.Write([]byte("after-rotate\n")); err != nil {
		t.Fatalf("轮转后写入失败: %v", err)
	}

	backup := path + backupSuffix
	info, err := os.Stat(backup)
	if err != nil {
		t.Fatalf("期望存在备份文件 %s: %v", backup, err)
	}
	if info.Size() != int64(len(big)) {
		t.Fatalf("备份大小期望 %d，实际 %d", len(big), info.Size())
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取当前日志失败: %v", err)
	}
	if string(data) != "after-rotate\n" {
		t.Fatalf("轮转后当前日志内容不符，实际 %q", string(data))
	}
}

// TestRotateReplacesExistingBackup 验证重复轮转会覆盖旧备份而不报错。
func TestRotateReplacesExistingBackup(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.log")
	w, err := newRotateWriter(path)
	if err != nil {
		t.Fatalf("newRotateWriter 失败: %v", err)
	}
	defer w.Close()

	for i := 0; i < 3; i++ {
		if _, err := w.Write([]byte(strings.Repeat("y", maxBytes))); err != nil {
			t.Fatalf("第 %d 次写入失败: %v", i, err)
		}
	}
	if _, err := os.Stat(path + backupSuffix); err != nil {
		t.Fatalf("期望备份存在: %v", err)
	}
}
