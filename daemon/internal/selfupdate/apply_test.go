package selfupdate

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// TestApply_ReplacesTarget 校验 Apply 能把新可执行文件替换到目标路径。
//
// Linux 上可直接替换；Windows 上若目标未被占用也能成功（本测试目标文件未被运行）。
func TestApply_ReplacesTarget(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src", "jarvis-daemon")
	dst := filepath.Join(dir, "dst", "jarvis-daemon")
	if err := os.MkdirAll(filepath.Dir(src), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		t.Fatal(err)
	}
	// 目标处先放一个旧文件，确保确实发生替换。
	if err := os.WriteFile(dst, []byte("old"), 0o755); err != nil {
		t.Fatal(err)
	}
	want := []byte("new-binary-content")
	if err := os.WriteFile(src, want, 0o755); err != nil {
		t.Fatal(err)
	}

	if err := Apply(src, dst); err != nil {
		t.Fatalf("Apply 失败: %v", err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatalf("读取目标失败: %v", err)
	}
	if string(got) != string(want) {
		t.Fatalf("目标内容未替换: %q", got)
	}
}

// TestApply_MissingSrc 校验：源文件不存在时报错。
func TestApply_MissingSrc(t *testing.T) {
	dir := t.TempDir()
	if err := Apply(filepath.Join(dir, "nope"), filepath.Join(dir, "dst")); err == nil {
		t.Fatal("源文件不存在应报错")
	}
}

// TestApply_EmptyArgs 校验：参数为空时报错。
func TestApply_EmptyArgs(t *testing.T) {
	if err := Apply("", "x"); err == nil {
		t.Fatal("空参数应报错")
	}
	if err := Apply("x", ""); err == nil {
		t.Fatal("空参数应报错")
	}
}

// TestSamePath 校验同路径判断（Windows 忽略大小写）。
func TestSamePath(t *testing.T) {
	if !samePath("/a/b", "/a/b") {
		t.Fatal("相同路径应判定为同一文件")
	}
	if samePath("/a/b", "/a/c") {
		t.Fatal("不同路径不应判定为同一文件")
	}
	if samePath("", "/a") {
		t.Fatal("空路径不应判定为同一文件")
	}
	if runtime.GOOS == "windows" {
		if !samePath(`C:\A\b`, `c:\a\B`) {
			t.Fatal("Windows 下应忽略大小写")
		}
	}
}

// TestBinaryName 校验当前平台的可执行文件名。
func TestBinaryName(t *testing.T) {
	name := binaryName()
	if runtime.GOOS == "windows" {
		if name != "jarvis-daemon.exe" {
			t.Fatalf("Windows 上应为 jarvis-daemon.exe，实际 %q", name)
		}
		return
	}
	if name != "jarvis-daemon" {
		t.Fatalf("非 Windows 上应为 jarvis-daemon，实际 %q", name)
	}
}
