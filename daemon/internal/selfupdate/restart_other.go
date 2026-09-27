//go:build !linux && !windows

package selfupdate

import "fmt"

// restartService 在其他平台（如 darwin）上不重启服务。
//
// 本项目只承诺 Windows 与 Linux；此实现仅为让代码在 darwin 上也能编译通过。
func restartService() error {
	return fmt.Errorf("当前平台不支持自动重启服务")
}
