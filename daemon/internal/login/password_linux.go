//go:build linux

package login

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"syscall"
	"unsafe"
)

// ReadPassword 打印 prompt 后读取一行密码，终端下不回显。
//
// 实现方式：用 ioctl(TCGETS/TCSETS) 读写终端 termios，关闭 ECHO 位后读取，
// 读完（含出错路径）立即 defer 恢复，避免终端长时间处于不回显状态。
//
// 非终端（如管道、重定向）时 ioctl 会失败，此时退化为普通读取（不隐藏），
// 以便脚本化使用（如 echo "$PASS" | jarvis-daemon login ...）。
//
// 不引入 golang.org/x/term：项目约束禁止第三方依赖。
func ReadPassword(prompt string) (string, error) {
	fmt.Fprint(os.Stderr, prompt)

	fd := int(os.Stdin.Fd())

	// 尝试关闭回显；失败说明不是终端，退化为普通读取。
	oldState, err := disableEcho(fd)
	if err != nil {
		return readLine(os.Stdin)
	}
	// 无论后续是否出错都恢复终端属性。
	defer restoreEcho(fd, oldState)

	line, err := readLine(os.Stdin)
	// 回显关闭时用户按下的回车不会换行，这里补一个，保持输出整洁。
	fmt.Fprintln(os.Stderr)
	return line, err
}

// readLine 从 r 读取一行，去除行尾的 \n 与 \r。
func readLine(r *os.File) (string, error) {
	reader := bufio.NewReader(r)
	line, err := reader.ReadString('\n')
	if err != nil && line == "" {
		return "", err
	}
	return strings.TrimRight(line, "\r\n"), nil
}

// disableEcho 关闭终端回显，返回原 termios 以便恢复。
func disableEcho(fd int) (*syscall.Termios, error) {
	var old syscall.Termios
	if err := ioctlTermios(fd, syscall.TCGETS, &old); err != nil {
		return nil, err
	}
	newState := old
	// 关闭 ECHO（回显）与 ECHONL（换行回显）。
	newState.Lflag &^= syscall.ECHO | syscall.ECHONL
	if err := ioctlTermios(fd, syscall.TCSETS, &newState); err != nil {
		return nil, err
	}
	return &old, nil
}

// restoreEcho 恢复之前保存的 termios。
func restoreEcho(fd int, state *syscall.Termios) {
	if state == nil {
		return
	}
	_ = ioctlTermios(fd, syscall.TCSETS, state)
}

// ioctlTermios 对 fd 执行 termios 相关的 ioctl。
//
// syscall 包未直接导出 IoctlGetTermios 这类封装（那在 x/term 里），
// 故这里直接用 SYS_IOCTL 系统调用。
func ioctlTermios(fd int, req uintptr, state *syscall.Termios) error {
	_, _, errno := syscall.Syscall(
		syscall.SYS_IOCTL,
		uintptr(fd),
		req,
		uintptr(unsafe.Pointer(state)),
	)
	if errno != 0 {
		return errno
	}
	return nil
}
