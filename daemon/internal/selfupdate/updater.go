package selfupdate

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

// UpdateState 是更新流程的状态（对应协议中的 daemon.update.status.state）。
type UpdateState string

const (
	// StateDownloading 正在下载新版本。
	StateDownloading UpdateState = "downloading"
	// StateVerifying 正在校验（sha256）与解包。
	StateVerifying UpdateState = "verifying"
	// StateApplying 正在替换可执行文件。
	StateApplying UpdateState = "applying"
	// StateRestarting 正在重启服务。
	StateRestarting UpdateState = "restarting"
	// StateFailed 更新失败（error 字段说明原因）。
	StateFailed UpdateState = "failed"
	// StateDone 更新已就绪（Linux 上替换完成；Windows 上已交给 helper）。
	StateDone UpdateState = "done"
)

// StatusReporter 由调用方提供，用于把更新进度回执给网关（可选）。
//
// 参数为状态与错误信息（成功时 error 为空串）。实现方不应阻塞太久。
type StatusReporter func(state UpdateState, errMsg string)

// Options 是执行一次更新的参数。
type Options struct {
	// Info 是网关下发的更新指令（须 Available=true）。
	Info UpdateInfo
	// Version 是当前 daemon 版本，用于 User-Agent 与日志。
	Version string
	// TargetPath 是要替换的可执行文件路径（通常是 ~/.jarvis/bin/jarvis-daemon[.exe]）。
	TargetPath string
	// WorkDir 是下载与解包的临时目录；为空时取系统临时目录下的子目录。
	WorkDir string
	// Restart 表示替换成功后是否重启服务。
	Restart bool
	// Report 是可选的状态回执回调。
	Report StatusReporter
	// HTTPClient 可选，便于测试注入；为空时使用默认客户端。
	HTTPClient *http.Client
}

// Run 执行一次完整的更新流程：下载 → 校验/解包 → 替换 → （可选）重启。
//
// 设计原则：任何一步失败都只返回错误（由调用方记日志），绝不 panic、
// 不阻断 WS 连接与既有能力。状态通过 opts.Report 逐步回执。
//
// 返回 nil 表示更新已成功应用（或已交给 helper 完成）。
func Run(opts Options) error {
	if !opts.Info.Available {
		return ErrNotAvailable
	}
	if opts.TargetPath == "" {
		return fmt.Errorf("未指定替换目标路径")
	}
	report := func(s UpdateState, errMsg string) {
		if opts.Report != nil {
			opts.Report(s, errMsg)
		}
	}

	workDir := opts.WorkDir
	if workDir == "" {
		dir, err := os.MkdirTemp("", "jarvis-daemon-update-*")
		if err != nil {
			report(StateFailed, err.Error())
			return fmt.Errorf("创建临时目录失败: %w", err)
		}
		workDir = dir
	} else if err := os.MkdirAll(workDir, 0o700); err != nil {
		report(StateFailed, err.Error())
		return fmt.Errorf("创建临时目录失败: %w", err)
	}
	defer func() { _ = os.RemoveAll(workDir) }()

	// 1) 下载。
	report(StateDownloading, "")
	asset := opts.Info.Asset
	if asset == "" {
		asset = filepath.Base(opts.Info.URL)
	}
	archivePath := filepath.Join(workDir, asset)
	if opts.Info.SHA256 == "" {
		log.Printf("[selfupdate] 网关未提供 sha256，跳过完整性校验（版本 %s）", opts.Info.LatestVersion)
	}
	if err := Download(opts.HTTPClient, opts.Version, opts.Info.URL, archivePath, opts.Info.SHA256); err != nil {
		report(StateFailed, err.Error())
		return fmt.Errorf("下载失败: %w", err)
	}

	// 2) 解包出新可执行文件。
	report(StateVerifying, "")
	newBinary := filepath.Join(workDir, binaryName())
	if err := ExtractBinary(archivePath, newBinary, binaryName()); err != nil {
		report(StateFailed, err.Error())
		return fmt.Errorf("解包失败: %w", err)
	}

	// 3) 替换。
	report(StateApplying, "")
	if err := Apply(newBinary, opts.TargetPath); err != nil {
		// Windows 上目标被占用时会返回「已保留待替换文件」，此时改走 helper。
		if pid, herr := SpawnApplyHelper("", newBinary, opts.TargetPath, opts.Restart); herr == nil && pid > 0 {
			log.Printf("[selfupdate] 已启动更新 helper（pid=%d），将在进程退出后完成替换", pid)
			// 关键：helper 要等目标文件不再被占用才能替换，而当前进程正占着它。
			// 因此必须主动重启服务（Stop 会终止本进程），否则 helper 会一直等到
			// 60 秒超时、替换失败退出，更新永远无法生效。
			if opts.Restart {
				report(StateRestarting, "")
				if rerr := restartService(); rerr != nil {
					// 重启失败不算更新失败（文件待 helper 替换），只记日志。
					log.Printf("[selfupdate] 重启服务失败（helper 将在进程退出后替换，可手动重启）: %v", rerr)
				}
			}
			report(StateDone, "")
			return nil
		}
		report(StateFailed, err.Error())
		return fmt.Errorf("替换可执行文件失败: %w", err)
	}

	// 4) 重启（Linux 上替换已完成，此处真正重启；Windows 上若走 helper 则上面已返回）。
	if opts.Restart {
		report(StateRestarting, "")
		if err := restartService(); err != nil {
			// 重启失败不算更新失败（文件已是新版），只记日志。
			log.Printf("[selfupdate] 重启服务失败（可手动重启）: %v", err)
		}
	}
	report(StateDone, "")
	log.Printf("[selfupdate] 已更新到 %s（目标 %s）", opts.Info.LatestVersion, opts.TargetPath)
	return nil
}

// binaryName 返回当前平台的可执行文件名。
func binaryName() string {
	if isWindows() {
		return "jarvis-daemon.exe"
	}
	return "jarvis-daemon"
}

// restartService 由平台文件实现（见 restart_linux.go / restart_windows.go /
// restart_other.go），避免本文件引入平台依赖。

// NowUnix 返回当前 Unix 秒（供上层填充 TokenState.SavedAtUnix）。
func NowUnix() int64 { return time.Now().Unix() }
