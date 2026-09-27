//go:build windows

package login

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"syscall"
	"unsafe"
)

// 隐藏密码输入所需的 Win32 入口。
//
// 用 syscall.NewLazyDLL 动态加载，避免引入 golang.org/x/sys 依赖
// （与 internal/service/console_windows.go 的做法一致）。
var (
	kernel32Login           = syscall.NewLazyDLL("kernel32.dll")
	procGetStdHandleLogin   = kernel32Login.NewProc("GetStdHandle")
	procGetConsoleModeLogin = kernel32Login.NewProc("GetConsoleMode")
	procSetConsoleModeLogin = kernel32Login.NewProc("SetConsoleMode")
)

const (
	// stdInputHandle 对应 STD_INPUT_HANDLE。
	stdInputHandle = ^uintptr(10) + 1 // -10 的无符号表示
	// enableEchoInput 对应 ENABLE_ECHO_INPUT。
	enableEchoInput = 0x0004
)

// ReadPassword 打印 prompt 后读取一行密码，控制台下不回显。
//
// 实现方式：GetConsoleMode 读取当前模式，清除 ENABLE_ECHO_INPUT 后读取，
// 读取完成（含出错路径）立即恢复原模式。
//
// 非控制台（如管道、重定向）时 GetConsoleMode 会失败，此时退化为普通读取。
func ReadPassword(prompt string) (string, error) {
	fmt.Fprint(os.Stderr, prompt)

	handle, _, _ := procGetStdHandleLogin.Call(stdInputHandle)
	oldMode, ok := getConsoleMode(handle)
	if !ok {
		// 不是控制台，退化为普通读取。
		return readLine(os.Stdin)
	}
	// 清除回显位；失败也继续（最坏情况是密码可见）。
	_, _, _ = procSetConsoleModeLogin.Call(handle, uintptr(oldMode&^enableEchoInput))
	defer func() {
		_, _, _ = procSetConsoleModeLogin.Call(handle, uintptr(oldMode))
	}()

	line, err := readLine(os.Stdin)
	fmt.Fprintln(os.Stderr)
	return line, err
}

// readLine 从 r 读取一行，去除行尾的 \r\n。
func readLine(r *os.File) (string, error) {
	reader := bufio.NewReader(r)
	line, err := reader.ReadString('\n')
	if err != nil && line == "" {
		return "", err
	}
	return strings.TrimRight(line, "\r\n"), nil
}

// getConsoleMode 读取控制台模式；非控制台时返回 ok=false。
func getConsoleMode(handle uintptr) (uint32, bool) {
	var mode uint32
	ret, _, _ := procGetConsoleModeLogin.Call(
		handle,
		uintptr(unsafe.Pointer(&mode)),
	)
	if ret == 0 {
		return 0, false
	}
	return mode, true
}
