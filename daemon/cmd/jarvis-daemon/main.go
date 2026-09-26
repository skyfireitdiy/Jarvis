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
	"syscall"

	"jarvis-daemon/internal/auth"
	"jarvis-daemon/internal/capability"
	"jarvis-daemon/internal/config"
	"jarvis-daemon/internal/localapi"
	"jarvis-daemon/internal/service"
	"jarvis-daemon/internal/wsclient"
)

// version 是守护进程版本，作为 extension_version 上报给网关。
const version = "0.1.0"

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
	log.Printf("[daemon] 已注册 %d 个平台能力", len(registry.ListForPlatform(capability.PlatformLinux)))

	client := wsclient.New(wsclient.Options{
		Gateway:           cfg.Gateway,
		Token:             "",
		ClientID:          buildClientID(),
		Version:           version,
		Registry:          registry,
		HeartbeatInterval: cfg.HeartbeatInterval,
		ReconnectMin:      cfg.ReconnectMin,
		ReconnectMax:      cfg.ReconnectMax,
		OnStateChange: func(state string) {
			log.Printf("[daemon] 连接状态: %s", state)
		},
		OnAuthError: func(code int, reason string) {
			log.Printf("[daemon] 鉴权失败（关闭码 %d），标记 Token 失效，等待网页重新推送", code)
			store.MarkTokenInvalid()
		},
	})

	api := localapi.New(store, client, version,
		func(gateway, token string) {
			// 收到新凭据：以新参数重建连接。
			client.UpdateCredentials(gateway, token)
			client.Start()
		},
		func() {
			client.Stop()
		},
	)

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

	client.Stop()
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
