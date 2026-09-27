//go:build !linux && !windows

package login

import (
	"bufio"
	"fmt"
	"os"
	"strings"
)

// ReadPassword 打印 prompt 后读取一行密码。
//
// 本平台（如 macOS）未实现隐藏输入，密码会正常回显。如需隐藏，请在此处补充
// 对应平台的 termios 实现（macOS 的 termios 结构与 Linux 不同）。
func ReadPassword(prompt string) (string, error) {
	fmt.Fprint(os.Stderr, prompt)
	reader := bufio.NewReader(os.Stdin)
	line, err := reader.ReadString('\n')
	if err != nil && line == "" {
		return "", err
	}
	return strings.TrimRight(line, "\r\n"), nil
}
