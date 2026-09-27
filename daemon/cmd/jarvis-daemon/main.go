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
	})

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
