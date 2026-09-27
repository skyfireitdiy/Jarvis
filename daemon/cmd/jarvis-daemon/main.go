// Command jarvis-daemon 是 Jarvis 本地守护进程。
//
// 职责：接收网页推送的登录信息，以浏览器扩展相同的协议连接网关，
// 保持在线并接收指令（指令处理为占位实现）。
//
// 用法：
//
//	jarvis-daemon run                 前台运行（默认行为）
//	jarvis-daemon install             安装为系统服务并设为开机自启
//	jarvis-daemon uninstall           停止并卸载系统服务
//	jarvis-daemon start|stop|restart  服务生命周期管理
//	jarvis-daemon status              查看服务状态
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"

	"jarvis-daemon/internal/auth"
	"jarvis-daemon/internal/capability"
	"jarvis-daemon/internal/config"
	"jarvis-daemon/internal/localapi"
	"jarvis-daemon/internal/selfupdate"
	"jarvis-daemon/internal/service"
	"jarvis-daemon/internal/wsclient"
)

// version 是守护进程版本，作为 extension_version 上报给网关。
//
// 声明为 var 而非 const，以便发布时通过构建参数注入真实版本号：
//
//	go build -ldflags "-X main.version=v5.0.5" ./cmd/jarvis-daemon
//
// 未注入时使用下面的默认值。
var version = "0.1.0"

// currentStore 是 runDaemon 创建的凭据存储，供自动更新流程在更新前临时落盘凭据。
// 仅在 runDaemon 内被赋值；子命令路径不会用到。
var currentStore *auth.Store

// currentManager 是 runDaemon 创建的多网关连接管理器，供自动更新流程回执进度
// （daemon.update.status）。仅在 runDaemon 内被赋值；子命令路径不会用到。
var currentManager *wsclient.Manager

func main() {
	if len(os.Args) > 1 && !isFlag(os.Args[1]) {
		if err := runSubcommand(os.Args[1], os.Args[2:]); err != nil {
			log.Fatalf("[daemon] %v", err)
		}
		return
	}
	runDaemon(os.Args[1:])
}

// isFlag 判断参数是否为选项（以 '-' 开头）。
func isFlag(arg string) bool {
	return len(arg) > 0 && arg[0] == '-'
}

// runSubcommand 分发服务管理子命令。
func runSubcommand(name string, args []string) error {
	switch name {
	case "run":
		runDaemon(args)
		return nil
	case "install":
		return cmdInstall(args)
	case "uninstall":
		return cmdSimple("卸载", func(s service.Service) (string, error) { return s.Uninstall() })
	case "start":
		return cmdSimple("启动", func(s service.Service) (string, error) { return s.Start() })
	case "stop":
		return cmdSimple("停止", func(s service.Service) (string, error) { return s.Stop() })
	case "restart":
		return cmdSimple("重启", func(s service.Service) (string, error) { return s.Restart() })
	case "status":
		return cmdStatus()
	case "self-update-apply":
		return cmdSelfUpdateApply(args)
	case "help", "-h", "--help":
		printUsage()
		return nil
	default:
		printUsage()
		return fmt.Errorf("未知子命令: %s", name)
	}
}

// cmdInstall 安装服务：写入服务定义并设为开机自启（不启动）。
func cmdInstall(args []string) error {
	fs := flag.NewFlagSet("install", flag.ContinueOnError)
	listenFlag := fs.String("listen", "", "本地 API 监听地址（覆盖配置文件）")
	gatewayFlag := fs.String("gateway", "", "默认网关地址（覆盖配置文件）")
	configFlag := fs.String("config", "", "配置文件路径（默认 ~/.jarvis/daemon/config.yaml）")
	if err := fs.Parse(args); err != nil {
		return err
	}

	opts := service.Options{
		Listen:     *listenFlag,
		Gateway:    *gatewayFlag,
		ConfigPath: *configFlag,
	}
	if notice := service.InstallNotice(); notice != "" {
		fmt.Printf("[daemon] %s\n", notice)
	}
	msg, err := service.New().Install(opts)
	if err != nil {
		return err
	}
	fmt.Printf("[daemon] %s\n", msg)
	fmt.Println("[daemon] 提示：使用 jarvis-daemon start 启动服务")
	return nil
}

// cmdSimple 执行无参数的服务操作并打印结果。
func cmdSimple(action string, fn func(service.Service) (string, error)) error {
	msg, err := fn(service.New())
	if err != nil {
		return fmt.Errorf("%s服务失败: %w", action, err)
	}
	fmt.Printf("[daemon] %s\n", msg)
	return nil
}

// cmdStatus 查询并打印服务状态。
func cmdStatus() error {
	st, err := service.New().Status()
	if err != nil {
		return fmt.Errorf("查询服务状态失败: %w", err)
	}
	fmt.Printf("[daemon] 运行中: %v\n", st.Running)
	fmt.Printf("[daemon] 开机自启: %v\n", st.Enabled)
	if st.PID > 0 {
		fmt.Printf("[daemon] PID: %d\n", st.PID)
	}
	if st.Detail != "" {
		fmt.Printf("[daemon] 说明: %s\n", st.Detail)
	}
	return nil
}

// printUsage 打印用法说明。
func printUsage() {
	fmt.Print(`jarvis-daemon - Jarvis 本地守护进程

用法:
  jarvis-daemon [run] [选项]     前台运行守护进程（默认行为）
  jarvis-daemon install [选项]   安装为系统服务并设为开机自启
  jarvis-daemon uninstall        停止并卸载系统服务
  jarvis-daemon start            启动服务
  jarvis-daemon stop             停止服务
  jarvis-daemon restart          重启服务
  jarvis-daemon status           查看服务状态
  jarvis-daemon self-update-apply [选项]  自动更新 helper（内部使用，勿手动调用）

选项（run / install 共用）:
  -listen string    本地 API 监听地址（覆盖配置文件）
  -gateway string   默认网关地址（覆盖配置文件）
  -config string    配置文件路径（默认 ~/.jarvis/daemon/config.yaml）
`)
}

// runDaemon 以前台方式运行守护进程。
func runDaemon(args []string) {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	listenFlag := fs.String("listen", "", "本地 API 监听地址（覆盖配置文件）")
	gatewayFlag := fs.String("gateway", "", "默认网关地址（覆盖配置文件）")
	configFlag := fs.String("config", "", "配置文件路径（默认 ~/.jarvis/daemon/config.yaml）")
	_ = fs.Parse(args)

	cfgPath := *configFlag
	if cfgPath == "" {
		cfgPath = config.DefaultPath()
	}
	cfg, err := config.Load(cfgPath)
	if err != nil {
		log.Fatalf("加载配置失败: %v", err)
	}
	if *listenFlag != "" {
		cfg.Listen = *listenFlag
	}
	if *gatewayFlag != "" {
		cfg.Gateway = *gatewayFlag
	}
	if err := cfg.Validate(); err != nil {
		log.Fatalf("配置非法: %v", err)
	}

	store := auth.NewStore()

	// 暴露给自动更新流程，用于更新前临时落盘凭据（见 saveCurrentCredentialsForUpdate）。
	currentStore = store

	// 若上一次是「自动更新 → 重启」，启动时恢复临时保存的凭据并立即删除该文件。
	// 必须在 Manager 构造前完成：恢复后下面会主动发起连接。
	restoredCreds, restored := selfupdate.LoadAndClearTokenState()
	if restored {
		store.SetWithName(restoredCreds.Gateway, restoredCreds.Token, restoredCreds.Name)
		log.Printf("[daemon] 已从自动更新中转文件恢复凭据（网关 %s），该文件已删除", restoredCreds.Gateway)
	}

	// 注册当前平台的能力，供网关下发指令时执行。
	registry := capability.NewRegistry()
	log.Printf("[daemon] 已注册 %d 个平台能力", len(registry.ListForPlatform(capability.Current())))

	// 把「按网关取 Token」注入能力层，使 browser.ext.sync 能自行从网关下载扩展包。
	// 能力 Handler 签名无法携带凭据存储，故用注入方式解耦（capability 包不反向依赖 auth）。
	capability.SetBrowserExtCredentialProvider(func(gateway string) (string, bool) {
		creds, err := store.Get(gateway)
		if err != nil || creds.Token == "" {
			return "", false
		}
		return creds.Token, true
	})

	manager := wsclient.NewManagerWithOptions(wsclient.ManagerOptions{
		Options: wsclient.Options{
			// Gateway/Token 由 Connect 按具体网关覆盖，这里不预设。
			ClientID:          buildClientID(),
			Version:           version,
			Registry:          registry,
			HeartbeatInterval: cfg.HeartbeatInterval,
			ReconnectMin:      cfg.ReconnectMin,
			ReconnectMax:      cfg.ReconnectMax,
		},
		OnGatewayStateChange: func(gateway, state string) {
			log.Printf("[daemon] 连接状态: %s (%s)", state, gateway)
		},
		OnGatewayAuthError: func(gateway string, code int, reason string) {
			// 鉴权失败只影响该网关：标记其 Token 失效，等待网页重新推送。
			log.Printf("[daemon] 网关 %s 鉴权失败（关闭码 %d），标记 Token 失效，等待网页重新推送", gateway, code)
			store.MarkTokenInvalid(gateway)
		},
		OnGatewayHelloAck: func(gateway, sessionID, latestExtVersion string) {
			// 网关随握手告知其打包的扩展最新版本；与本地副本不一致时异步同步。
			// 放在独立 goroutine 中：下载可能耗时数秒，不能阻塞 WS 读循环。
			maybeAutoSyncBrowserExt(gateway, latestExtVersion)
		},
		OnGatewayDaemonUpdate: func(gateway, sessionID string, info map[string]any) {
			// 网关随握手告知 daemon 有新版本；受「自动更新」开关约束，异步执行。
			// 放在独立 goroutine 中：下载 + 替换可能耗时，不能阻塞 WS 读循环。
			maybeAutoUpdateDaemon(gateway, sessionID, info)
		},
	})

	// 暴露给自动更新流程，用于回执更新进度（见 reportDaemonUpdateStatus）。
	currentManager = manager

	// 若上一次是「自动更新 → 重启」恢复了凭据，则主动发起连接（否则等网页推送）。
	if restored {
		manager.ConnectWithName(restoredCreds.Gateway, restoredCreds.Token, restoredCreds.Name)
	}

	api := localapi.New(store, manager, version)

	srv := localapi.NewHTTPServer(cfg.Listen, api.Handler())

	// 若配置里已有网关但无 Token，则不主动连接（等网页推送）。
	log.Printf("[daemon] jarvis-daemon %s 启动，本地 API: http://%s", version, cfg.Listen)
	if cfgPath != "" {
		log.Printf("[daemon] 配置文件: %s", cfgPath)
	}

	errCh := make(chan error, 1)
	go func() {
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
	}()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	select {
	case err := <-errCh:
		log.Fatalf("本地 API 启动失败: %v", err)
	case <-ctx.Done():
		log.Printf("[daemon] 收到退出信号，正在关闭…")
	}

	manager.DisconnectAll()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*1e9)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Printf("[daemon] 关闭本地 API 失败: %v", err)
	}
}

// buildClientID 生成客户端标识：daemon-<hostname>-<pid>。
func buildClientID() string {
	host, err := os.Hostname()
	if err != nil || host == "" {
		host = "unknown"
	}
	return fmt.Sprintf("daemon-%s-%d", host, os.Getpid())
}

// browserExtSyncMu 串行化扩展同步，避免多个网关同时握手时并发写同一目录。
var browserExtSyncMu sync.Mutex

// maybeAutoSyncBrowserExt 在网关下发扩展最新版本且与本地不一致时，异步同步扩展包。
//
// 设计要点：
//   - 受「自动安装/更新浏览器扩展」开关约束：开关关闭（默认）时直接跳过，
//     不下载、不起协程。开关由用户在 Web 设置界面显式打开后随登录态推送给
//     本机守护进程（只存内存态，不落盘），故守护进程重启后回到关闭，等待
//     前端再次推送——未收到推送一律不自动同步，这是安全默认；
//   - 立即返回，把下载/解压放到独立 goroutine（下载可能耗时数秒），不阻塞 WS 读循环；
//   - 版本一致时直接跳过，避免每次重连都重复下载；
//   - 任何失败只记日志，绝不影响连接与既有能力；
//   - 不重启浏览器：仅把新版本落盘，由用户在 chrome://extensions 手动刷新。
//
// 注意：本开关只约束此处的「自动同步」；手动能力 browser.ext.sync 由用户显式
// 调用，不受该开关约束。
func maybeAutoSyncBrowserExt(gateway, latestVersion string) {
	// 开关判断必须放在函数入口、goroutine 之外：关闭时提前返回，避免无谓起协程。
	if !capability.AutoInstallBrowserExt() {
		log.Printf("[daemon] 自动安装/更新浏览器扩展已关闭，跳过自动同步（网关 %s，网关版本 %q）",
			gateway, latestVersion)
		return
	}
	latestVersion = strings.TrimSpace(latestVersion)
	if latestVersion == "" {
		// 网关未提供版本（旧版网关或读取失败），无法判断是否需要更新。
		return
	}
	localVersion := capability.LocalBrowserExtVersion()
	if localVersion == latestVersion {
		return
	}

	go func() {
		// 同一时刻只允许一个同步任务，避免并发替换目录互相干扰。
		browserExtSyncMu.Lock()
		defer browserExtSyncMu.Unlock()

		// 加锁后再判断一次：等待期间可能已被其他网关同步到目标版本。
		if capability.LocalBrowserExtVersion() == latestVersion {
			return
		}
		log.Printf("[daemon] 检测到扩展版本不一致（本地 %q → 网关 %q），开始自动同步（网关 %s）",
			localVersion, latestVersion, gateway)

		count, version, err := capability.SyncBrowserExt(gateway, browserExtTokenFor(gateway))
		if err != nil {
			log.Printf("[daemon] 自动同步浏览器扩展失败（网关 %s）: %v", gateway, err)
			return
		}
		log.Printf("[daemon] 浏览器扩展已同步到 %q（%d 个文件，目录 %s）；"+
			"请在浏览器 chrome://extensions 点击「刷新」使新版本生效",
			version, count, capability.BrowserExtDirOrEmpty())
	}()
}

// browserExtTokenFor 取指定网关的 Token；无凭据时返回空串（同步会因此报错并记日志）。
func browserExtTokenFor(gateway string) string {
	token, ok := capability.BrowserExtToken(gateway)
	if !ok {
		return ""
	}
	return token
}

// daemonUpdateMu 串行化自动更新，避免多个网关同时握手时并发下载/替换互相干扰。
var daemonUpdateMu sync.Mutex

// maybeAutoUpdateDaemon 在网关下发 daemon 更新指令且「自动更新」开关开启时，异步执行更新。
//
// 设计要点（与 maybeAutoSyncBrowserExt 一致的安全默认）：
//   - 受「自动更新 daemon」开关约束：开关关闭（默认）时直接跳过，不下载、不起协程。
//     开关由用户在 Web 设置界面显式打开后随登录态推送给本机守护进程（只存内存态，
//     不落盘），故守护进程重启后回到关闭，等待前端再次推送——未收到推送一律不自动更新；
//   - 立即返回，把下载/替换放到独立 goroutine（可能耗时数秒），不阻塞 WS 读循环；
//   - 更新前把当前凭据临时落盘，供重启后恢复登录态（见 selfupdate.SaveTokenState）；
//   - 任何失败只记日志，绝不影响连接与既有能力。
func maybeAutoUpdateDaemon(gateway, sessionID string, info map[string]any) {
	// 开关判断必须放在函数入口、goroutine 之外：关闭时提前返回，避免无谓起协程。
	if !capability.AutoUpdateDaemon() {
		log.Printf("[daemon] 自动更新已关闭，跳过 daemon 更新（网关 %s）", gateway)
		return
	}
	parsed, err := selfupdate.ParseUpdateInfo(info)
	if err != nil {
		// 无可用更新时静默跳过；其他解析错误只记日志。
		if !errors.Is(err, selfupdate.ErrNotAvailable) {
			log.Printf("[daemon] 解析 daemon 更新指令失败（网关 %s）: %v", gateway, err)
		}
		return
	}

	go func() {
		// 同一时刻只允许一个更新任务，避免并发替换同一可执行文件。
		daemonUpdateMu.Lock()
		defer daemonUpdateMu.Unlock()

		target, err := service.InstalledBinaryPath()
		if err != nil {
			log.Printf("[daemon] 无法确定可执行文件路径，跳过自动更新: %v", err)
			return
		}

		// 更新会重启服务，先把当前凭据临时落盘，供重启后恢复登录态。
		// 落盘失败不阻断更新（最坏情况只是重启后需重新推送凭据）。
		saveCurrentCredentialsForUpdate(gateway)

		log.Printf("[daemon] 检测到 daemon 新版本 %s（当前 %s），开始自动更新（网关 %s，目标 %s）",
			parsed.LatestVersion, parsed.CurrentVersion, gateway, target)

		err = selfupdate.Run(selfupdate.Options{
			Info:       parsed,
			Version:    version,
			TargetPath: target,
			Restart:    true,
			// 把更新进度回执给网关（单向 daemon.update.status，网关只记日志）。
			// 连接可能已中断（重启前），Send 失败只记日志、不影响更新流程。
			Report: func(state selfupdate.UpdateState, errMsg string) {
				reportDaemonUpdateStatus(gateway, parsed.LatestVersion, state, errMsg)
			},
		})
		if err != nil {
			log.Printf("[daemon] 自动更新 daemon 失败（网关 %s）: %v", gateway, err)
			return
		}
		log.Printf("[daemon] daemon 自动更新已完成（版本 %s）", parsed.LatestVersion)
	}()
}

// saveCurrentCredentialsForUpdate 把指定网关的当前凭据临时落盘，供更新重启后恢复。
//
// 无凭据或落盘失败时只记日志，不返回错误（调用方不应因此中断更新流程）。
func saveCurrentCredentialsForUpdate(gateway string) {
	creds, err := currentStore.Get(gateway)
	if err != nil || creds.Token == "" {
		log.Printf("[daemon] 更新前未找到网关 %s 的凭据，重启后需重新推送", gateway)
		return
	}
	state := selfupdate.TokenState{
		Gateway:     creds.Gateway,
		Token:       creds.Token,
		Name:        creds.Name,
		SavedAtUnix: selfupdate.NowUnix(),
	}
	if err := selfupdate.SaveTokenState(state); err != nil {
		log.Printf("[daemon] 更新前保存凭据失败（重启后需重新推送）: %v", err)
		return
	}
	log.Printf("[daemon] 更新前已临时保存网关 %s 的凭据，重启后自动恢复", gateway)
}

// reportDaemonUpdateStatus 把更新进度以单向 daemon.update.status 回执给网关。
//
// 网关只记录日志、不回复（协议见 daemon/docs/daemon-self-update-protocol.md）。
// 连接可能已断开（尤其 restarting 阶段）或该网关已不在管理器中，此时只记日志，
// 绝不因回执失败中断更新流程。
func reportDaemonUpdateStatus(gateway, version string, state selfupdate.UpdateState, errMsg string) {
	client, ok := currentManager.Get(gateway)
	if !ok {
		log.Printf("[daemon] 更新状态 %s 无法回执（网关 %s 未连接）", state, gateway)
		return
	}
	payload := map[string]any{
		"type":    "daemon.update.status",
		"state":   string(state),
		"version": version,
	}
	if errMsg != "" {
		payload["error"] = errMsg
	}
	if err := client.Send(payload); err != nil {
		log.Printf("[daemon] 更新状态 %s 回执失败（网关 %s）: %v", state, gateway, err)
		return
	}
	log.Printf("[daemon] 更新状态已回执：state=%s version=%s（网关 %s）", state, version, gateway)
}
