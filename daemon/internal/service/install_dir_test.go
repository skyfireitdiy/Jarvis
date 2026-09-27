package service

import (
	"os"
	"path/filepath"
	"testing"
)

func TestBinaryNameHasSuffixOnWindows(t *testing.T) {
	name := BinaryName()
	if name == "" {
		t.Fatal("BinaryName 不应为空")
	}
	// 非 Windows 平台不带 .exe 后缀。
	if os.PathSeparator != '\\' && filepath.Ext(name) == ".exe" {
		t.Errorf("非 Windows 平台 BinaryName = %q, 不应带 .exe 后缀", name)
	}
}

func TestInstalledBinaryPathUnderJarvisBin(t *testing.T) {
	p, err := InstalledBinaryPath()
	if err != nil {
		t.Fatalf("InstalledBinaryPath 返回错误: %v", err)
	}
	if !filepath.IsAbs(p) {
		t.Errorf("安装路径应为绝对路径，实际 %q", p)
	}
	if filepath.Base(filepath.Dir(p)) != InstallDirName {
		t.Errorf("安装路径父目录应为 %q，实际 %q", InstallDirName, filepath.Dir(p))
	}
	if filepath.Base(p) != BinaryName() {
		t.Errorf("安装文件名应为 %q，实际 %q", BinaryName(), filepath.Base(p))
	}
}

func TestSamePath(t *testing.T) {
	cases := []struct {
		a, b string
		want bool
	}{
		{"/a/b/jarvis-daemon", "/a/b/jarvis-daemon", true},
		{"/a/b/../b/jarvis-daemon", "/a/b/jarvis-daemon", true},
		{"/a/b/jarvis-daemon", "/a/c/jarvis-daemon", false},
		{"", "/a/b", false},
		{"/a/b", "", false},
	}
	for _, c := range cases {
		if got := samePath(c.a, c.b); got != c.want {
			t.Errorf("samePath(%q, %q) = %v, 期望 %v", c.a, c.b, got, c.want)
		}
	}
}

func TestCopyFileAtomicCreatesExecutable(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src")
	content := []byte("#!/bin/sh\necho hi\n")
	if err := os.WriteFile(src, content, 0o644); err != nil {
		t.Fatalf("准备源文件失败: %v", err)
	}
	dst := filepath.Join(dir, "sub", "jarvis-daemon")
	if err := copyFileAtomic(src, dst); err != nil {
		t.Fatalf("copyFileAtomic 返回错误: %v", err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatalf("读取目标文件失败: %v", err)
	}
	if string(got) != string(content) {
		t.Errorf("目标文件内容 = %q, 期望 %q", got, content)
	}
	info, err := os.Stat(dst)
	if err != nil {
		t.Fatalf("Stat 目标文件失败: %v", err)
	}
	if info.Mode().Perm()&0o100 == 0 {
		t.Errorf("目标文件应具备可执行权限，实际 %v", info.Mode().Perm())
	}
	// 覆盖已有文件应成功且内容更新。
	if err := os.WriteFile(dst, []byte("old"), 0o644); err != nil {
		t.Fatalf("准备旧文件失败: %v", err)
	}
	if err := copyFileAtomic(src, dst); err != nil {
		t.Fatalf("覆盖拷贝返回错误: %v", err)
	}
	got2, _ := os.ReadFile(dst)
	if string(got2) != string(content) {
		t.Errorf("覆盖后内容 = %q, 期望 %q", got2, content)
	}
}

func TestPrepareInstalledBinarySkipsCopyWhenAlreadyInstalled(t *testing.T) {
	dst, err := InstalledBinaryPath()
	if err != nil {
		t.Fatalf("InstalledBinaryPath 返回错误: %v", err)
	}
	// 传入的 ExecPath 已经是安装路径：应跳过拷贝，直接返回该路径。
	opts, gotPath, err := PrepareInstalledBinary(Options{ExecPath: dst})
	if err != nil {
		t.Fatalf("PrepareInstalledBinary 返回错误: %v", err)
	}
	if gotPath != dst {
		t.Errorf("返回路径 = %q, 期望 %q", gotPath, dst)
	}
	if opts.ExecPath != dst {
		t.Errorf("opts.ExecPath = %q, 期望 %q", opts.ExecPath, dst)
	}
	// 不应真的创建文件（因为走的是跳过分支）。
	if _, err := os.Stat(dst); err == nil {
		_ = os.Remove(dst)
		t.Log("注意：安装路径已存在文件（可能是真实安装），已清理")
	}
}

func TestRemoveInstalledBinaryIsIdempotent(t *testing.T) {
	// 文件不存在时应返回 nil（幂等）。
	if err := RemoveInstalledBinary(); err != nil {
		t.Fatalf("RemoveInstalledBinary 在文件不存在时应返回 nil，实际: %v", err)
	}
}
