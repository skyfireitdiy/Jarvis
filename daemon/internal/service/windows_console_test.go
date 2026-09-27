package service

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestWindowsExecCallSitesSetSysProcAttr 静态扫描本仓库所有 *_windows.go 源文件，
// 确保每个 exec.Command / exec.CommandContext 调用点都设置了 SysProcAttr。
//
// 背景：守护进程在 Windows 上以分离进程（无控制台）运行，若启动 powershell /
// tasklist / schtasks 等控制台程序时不带 CREATE_NO_WINDOW，Windows 会为子进程
// 新建控制台窗口，表现为「每次调用能力都闪一下黑框」。该属性只能在 windows
// 构建下编译，本机（Linux）无法运行，故用源码扫描把这条不变量锁住，防止将来
// 新增 exec 调用点时遗漏。
func TestWindowsExecCallSitesSetSysProcAttr(t *testing.T) {
	root := repoRootForTest(t)
	var checked int
	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			// 跳过 vendor 与 .git，避免扫描第三方代码。
			base := filepath.Base(path)
			if base == "vendor" || base == ".git" {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(path, "_windows.go") || strings.HasSuffix(path, "_windows_test.go") {
			return nil
		}
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		lines := strings.Split(string(data), "\n")
		for i, line := range lines {
			if !strings.Contains(line, "exec.Command") {
				continue
			}
			checked++
			// 允许在同一行或紧随其后的 8 行内出现 SysProcAttr（调用可能跨多行参数）。
			if !sysProcAttrNearby(lines, i, 8) {
				rel, _ := filepath.Rel(root, path)
				t.Errorf("%s:%d 的 exec 调用未设置 SysProcAttr，Windows 上会弹出控制台窗口: %s",
					rel, i+1, strings.TrimSpace(line))
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("扫描源码失败: %v", err)
	}
	if checked == 0 {
		t.Fatal("未扫描到任何 exec 调用点，测试可能失效（路径判断有误）")
	}
}

// sysProcAttrNearby 报告 lines[start] 起 offset 行内是否出现 SysProcAttr 赋值。
func sysProcAttrNearby(lines []string, start, offset int) bool {
	end := start + offset
	if end >= len(lines) {
		end = len(lines) - 1
	}
	for i := start; i <= end; i++ {
		if strings.Contains(lines[i], "SysProcAttr") {
			return true
		}
	}
	return false
}

// repoRootForTest 从测试文件所在目录向上找到包含 daemon/go.mod 的仓库根。
func repoRootForTest(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("获取工作目录失败: %v", err)
	}
	for {
		if _, statErr := os.Stat(filepath.Join(dir, "go.mod")); statErr == nil {
			// 当前目录是 daemon 模块根，其父目录即仓库根。
			return filepath.Dir(dir)
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("未找到包含 go.mod 的目录")
		}
		dir = parent
	}
}
