// Package daemonlog 把守护进程的日志同时写到标准错误与本地日志文件。
//
// 为什么需要：Windows 上守护进程由计划任务启动，标准输出/错误没有接收方，
// 日志会全部丢失，出问题时无从排查。这里在 ~/.jarvis/logs/daemon.log 落一份，
// 并保留 stderr 输出，使前台运行（jarvis-daemon run）行为不变。
//
// 只依赖标准库；不引入日志框架，保持与既有 log.Printf 调用完全兼容。
package daemonlog

import (
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"sync"
)

const (
	// maxBytes 是单个日志文件的大小上限，超过则轮转。
	maxBytes = 5 << 20 // 5 MiB

	// backupSuffix 是轮转后的备份文件名后缀（daemon.log → daemon.log.1）。
	backupSuffix = ".1"
)

// LogDir 返回日志目录：~/.jarvis/logs。
func LogDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("获取用户主目录失败: %w", err)
	}
	return filepath.Join(home, ".jarvis", "logs"), nil
}

// LogPath 返回日志文件路径：~/.jarvis/logs/daemon.log。
func LogPath() (string, error) {
	dir, err := LogDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "daemon.log"), nil
}

// rotateWriter 是带大小轮转的文件写入器。
//
// 轮转策略：写入前检查当前文件大小，超过 maxBytes 时把 daemon.log 重命名为
// daemon.log.1（覆盖旧备份），再重新创建 daemon.log。只保留一份备份，
// 避免无限增长占用磁盘。
type rotateWriter struct {
	mu   sync.Mutex
	path string
	file *os.File
	size int64
}

// newRotateWriter 打开（必要时创建）日志文件并返回写入器。
func newRotateWriter(path string) (*rotateWriter, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return nil, err
	}
	info, err := f.Stat()
	if err != nil {
		_ = f.Close()
		return nil, err
	}
	return &rotateWriter{path: path, file: f, size: info.Size()}, nil
}

// Write 在必要时先轮转，再写入数据。
func (w *rotateWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.size+int64(len(p)) > maxBytes {
		if err := w.rotate(); err != nil {
			// 轮转失败不阻断写入：继续追加到当前文件，避免丢日志。
			_ = err
		}
	}
	n, err := w.file.Write(p)
	w.size += int64(n)
	return n, err
}

// rotate 关闭当前文件、备份旧文件并重新创建。
func (w *rotateWriter) rotate() error {
	if err := w.file.Close(); err != nil {
		return err
	}
	backup := w.path + backupSuffix
	// Windows 上重命名到已存在的目标会失败，先删除旧备份。
	_ = os.Remove(backup)
	if err := os.Rename(w.path, backup); err != nil {
		return err
	}
	f, err := os.OpenFile(w.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return err
	}
	w.file = f
	w.size = 0
	return nil
}

// Close 关闭底层文件。
func (w *rotateWriter) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.file == nil {
		return nil
	}
	err := w.file.Close()
	w.file = nil
	return err
}

// Setup 把标准库 log 的输出改为「stderr + 日志文件」。
//
// 返回日志文件路径（失败时为空串）。任何创建失败都只降级为纯 stderr 输出，
// 不返回错误也不中断启动：日志不可用不应阻止守护进程工作。
func Setup() string {
	path, err := LogPath()
	if err != nil {
		log.Printf("[daemonlog] 无法确定日志路径，仅输出到 stderr: %v", err)
		return ""
	}
	w, err := newRotateWriter(path)
	if err != nil {
		log.Printf("[daemonlog] 打开日志文件失败（%s），仅输出到 stderr: %v", path, err)
		return ""
	}
	log.SetOutput(io.MultiWriter(os.Stderr, w))
	return path
}
