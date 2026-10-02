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
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"

	"jarvis-daemon/internal/auth"
	"jarvis-daemon/internal/capability"
	"jarvis-daemon/internal/config"
	"jarvis-daemon/internal/daemonlog"
	"jarvis-daemon/internal/gatewayfilter"
	"jarvis-daemon/internal/jsruntime"
	"jarvis-daemon/internal/localapi"
	"jarvis-daemon/internal/login"
	"jarvis-daemon/internal/proxy"
	"jarvis-daemon/internal/selfupdate"
	"jarvis-daemon/internal/service"
	"jarvis-daemon/internal/webui"
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
	case "login":
		return cmdLogin(args)
	case "gateway-filter":
		return cmdGatewayFilter(args)
	case "run-script":
		return cmdRunScript(args)
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
	if hint := service.StartHint(); hint != "" {
		fmt.Printf("[daemon] %s\n", hint)
	} else {
		fmt.Println("[daemon] 提示：使用 jarvis-daemon start 启动服务")
	}
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

// cmdLogin 用用户名密码登录网关，并把拿到的凭据推送给本地守护进程。
//
// 用途：无 GUI 的主机上没有浏览器可推送凭据，本命令提供命令行替代路径。
// 密码只通过交互式隐藏输入获取，不接受命令行参数，避免落入 shell 历史与进程列表。
func cmdLogin(args []string) error {
	fs := flag.NewFlagSet("login", flag.ContinueOnError)
	gatewayFlag := fs.String("gateway", "", "网关地址（覆盖配置文件）")
	userFlag := fs.String("u", "", "登录用户名（缺省时交互式输入）")
	configFlag := fs.String("config", "", "配置文件路径（默认 ~/.jarvis/daemon/config.yaml）")
	listenFlag := fs.String("listen", "", "本地 API 监听地址（覆盖配置文件）")
	if err := fs.Parse(args); err != nil {
		return err
	}

	// 读取配置：用于补齐未在命令行给出的网关地址与本地监听地址。
	cfgPath := *configFlag
	if cfgPath == "" {
		cfgPath = config.DefaultPath()
	}
	cfg, err := config.Load(cfgPath)
	if err != nil {
		return fmt.Errorf("加载配置失败: %w", err)
	}

	// 网关地址：命令行优先，其次配置文件。
	gateway := login.NormalizeGateway(*gatewayFlag)
	if gateway == "" {
		gateway = login.NormalizeGateway(cfg.Gateway)
	}
	if gateway == "" {
		return fmt.Errorf("未指定网关地址，请用 -gateway 指定，或先在配置文件 %s 中配置 gateway", cfgPath)
	}

	// 本地监听地址：命令行优先，其次配置文件，最后回退默认值。
	listen := strings.TrimSpace(*listenFlag)
	if listen == "" {
		listen = strings.TrimSpace(cfg.Listen)
	}
	if listen == "" {
		listen = config.DefaultListen
	}

	// 用户名：命令行优先，否则交互式输入。
	username := strings.TrimSpace(*userFlag)
	if username == "" {
		fmt.Fprint(os.Stderr, "用户名: ")
		reader := bufio.NewReader(os.Stdin)
		line, err := reader.ReadString('\n')
		if err != nil && strings.TrimSpace(line) == "" {
			return fmt.Errorf("读取用户名失败: %w", err)
		}
		username = strings.TrimSpace(line)
	}
	if username == "" {
		return fmt.Errorf("用户名不能为空")
	}

	// 密码：仅交互式隐藏输入。
	password, err := login.ReadPassword("密码: ")
	if err != nil {
		return fmt.Errorf("读取密码失败: %w", err)
	}
	if password == "" {
		return fmt.Errorf("密码不能为空")
	}

	fmt.Printf("[daemon] 正在登录网关 %s ...\n", gateway)
	result, err := login.Login(gateway, username, password)
	if err != nil {
		return err
	}
	// 只打印脱敏后的 token，避免完整凭据进入日志。
	displayName := result.DisplayName
	if displayName == "" {
		displayName = result.Username
	}
	fmt.Printf("[daemon] 登录成功: %s（token %s）\n", displayName, login.MaskToken(result.Token))

	// 推送给本地守护进程：name 传空，保留该网关已有名称。
	if err := login.PushAuth(listen, gateway, result.Token, ""); err != nil {
		return err
	}
	fmt.Printf("[daemon] 已向本地后台服务（%s）推送凭据，守护进程将连接网关\n", listen)
	return nil
}

// cmdGatewayFilter 读写网关黑白名单。
//
// 用法：
//
//	jarvis-daemon gateway-filter get
//	jarvis-daemon gateway-filter set -mode whitelist -pattern "*.example.com:*" -pattern "192.168.*:*"
//
// 实现方式：向本机守护进程的 /api/gateway-filter 发 HTTP 请求（该接口仅限
// 本机访问），而不是直接改内存——这样与「运行中的 daemon」保持单一数据源，
// 改完立即生效并落盘。目标固定为本机回环（127.0.0.1），显式绕过系统代理。
func cmdGatewayFilter(args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("用法: jarvis-daemon gateway-filter <get|set> [选项]")
	}
	action := args[0]
	rest := args[1:]

	fs := flag.NewFlagSet("gateway-filter", flag.ContinueOnError)
	modeFlag := fs.String("mode", "", "名单模式：off / whitelist / blacklist（set 必填）")
	listenFlag := fs.String("listen", "", "本地 API 监听地址（覆盖配置文件）")
	configFlag := fs.String("config", "", "配置文件路径（默认 ~/.jarvis/daemon/config.yaml）")
	var patterns patternFlags
	fs.Var(&patterns, "pattern", "匹配模式（host:port，支持 * 与 ?）；可重复指定")
	if err := fs.Parse(rest); err != nil {
		return err
	}

	// 本地监听地址：命令行优先，其次配置文件，最后回退默认值。
	cfgPath := *configFlag
	if cfgPath == "" {
		cfgPath = config.DefaultPath()
	}
	cfg, err := config.Load(cfgPath)
	if err != nil {
		return fmt.Errorf("加载配置失败: %w", err)
	}
	listen := strings.TrimSpace(*listenFlag)
	if listen == "" {
		listen = strings.TrimSpace(cfg.Listen)
	}
	if listen == "" {
		listen = config.DefaultListen
	}

	switch action {
	case "get":
		mode, pats, err := fetchGatewayFilter(listen)
		if err != nil {
			return err
		}
		printGatewayFilter(mode, pats)
		return nil
	case "set":
		mode := strings.TrimSpace(*modeFlag)
		if mode == "" {
			return fmt.Errorf("set 需要 -mode（off / whitelist / blacklist）")
		}
		if !gatewayfilter.ValidMode(mode) {
			return fmt.Errorf("mode 必须是 off / whitelist / blacklist 之一，当前为 %q", mode)
		}
		mode, pats, err := pushGatewayFilter(listen, mode, patterns)
		if err != nil {
			return err
		}
		fmt.Printf("[daemon] 已更新网关黑白名单\n")
		printGatewayFilter(mode, pats)
		return nil
	default:
		return fmt.Errorf("未知操作: %s（应为 get 或 set）", action)
	}
}

// patternFlags 收集可重复的 -pattern 参数。
type patternFlags []string

func (p *patternFlags) String() string { return strings.Join(*p, ",") }
func (p *patternFlags) Set(v string) error {
	*p = append(*p, v)
	return nil
}

// printGatewayFilter 以可读形式打印名单。
func printGatewayFilter(mode string, patterns []string) {
	fmt.Printf("mode: %s\n", mode)
	if len(patterns) == 0 {
		fmt.Printf("patterns: （空）\n")
		return
	}
	fmt.Printf("patterns:\n")
	for _, p := range patterns {
		fmt.Printf("  - %s\n", p)
	}
}

// gatewayFilterResponse 是 /api/gateway-filter 的响应体。
type gatewayFilterResponse struct {
	Success  bool     `json:"success"`
	Mode     string   `json:"mode"`
	Patterns []string `json:"patterns"`
	Error    string   `json:"error"`
}

// gatewayFilterHTTPClient 返回一个「绕过系统代理」的 HTTP 客户端。
//
// 目标固定为本机回环，若走系统代理会连不上（代理不转发回环），故显式直连。
func gatewayFilterHTTPClient() *http.Client {
	return &http.Client{Timeout: 5 * time.Second, Transport: proxy.DirectTransport()}
}

// fetchGatewayFilter 向本机守护进程查询当前名单。
func fetchGatewayFilter(listen string) (string, []string, error) {
	url := "http://" + listen + "/api/gateway-filter"
	resp, err := gatewayFilterHTTPClient().Get(url)
	if err != nil {
		return "", nil, fmt.Errorf("查询失败：本地后台服务未运行（%s），请先启动 jarvis-daemon（%v）", listen, err)
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	var out gatewayFilterResponse
	if err := json.Unmarshal(raw, &out); err != nil {
		return "", nil, fmt.Errorf("解析响应失败: %w（原始响应: %s）", err, strings.TrimSpace(string(raw)))
	}
	if !out.Success {
		return "", nil, fmt.Errorf("查询失败: %s", out.Error)
	}
	return out.Mode, out.Patterns, nil
}

// pushGatewayFilter 向本机守护进程提交新的名单。
func pushGatewayFilter(listen, mode string, patterns []string) (string, []string, error) {
	body, err := json.Marshal(map[string]any{"mode": mode, "patterns": patterns})
	if err != nil {
		return "", nil, fmt.Errorf("序列化请求失败: %w", err)
	}
	url := "http://" + listen + "/api/gateway-filter"
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return "", nil, fmt.Errorf("构造请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := gatewayFilterHTTPClient().Do(req)
	if err != nil {
		return "", nil, fmt.Errorf("更新失败：本地后台服务未运行（%s），请先启动 jarvis-daemon（%v）", listen, err)
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	var out gatewayFilterResponse
	if err := json.Unmarshal(raw, &out); err != nil {
		return "", nil, fmt.Errorf("解析响应失败: %w（原始响应: %s）", err, strings.TrimSpace(string(raw)))
	}
	if !out.Success {
		return "", nil, fmt.Errorf("更新失败（HTTP %d）: %s", resp.StatusCode, out.Error)
	}
	return out.Mode, out.Patterns, nil

}

// newRuntimeRegistry 创建当前平台的能力注册表，并注入运行所需的外部依赖。
//
// 复用点（见 docs/js-plugin-design.md §7）：run、run-script、script run 共用，
// 避免重复造轮子。store 为 nil 时（如 run-script 无凭据存储场景）跳过 provider 注入，
// browser.ext / ocr 等能力在未注入时会自行返回明确错误而非 panic。
func newRuntimeRegistry(store *auth.Store) *capability.Registry {
	registry := capability.NewRegistry()

	// 把「按网关取 Token」注入能力层，使 browser.ext.sync 能自行从网关下载扩展包。
	// 能力 Handler 签名无法携带凭据存储，故用注入方式解耦（capability 包不反向依赖 auth）。
	if store != nil {
		capability.SetBrowserExtCredentialProvider(func(gateway string) (string, bool) {
			creds, err := store.Get(gateway)
			if err != nil || creds.Token == "" {
				return "", false
			}
			return creds.Token, true
		})
		// 注入「已认证网关列表」，供 ocr.recognize 在未显式指定 gateway 时回退使用。
		// 排序保证顺序稳定（多网关时取地址最小的那个），避免每次调用结果漂移。
		capability.SetOcrGatewayLister(func() []string {
			creds := store.List()
			out := make([]string, 0, len(creds))
			for _, c := range creds {
				if c.Gateway != "" && c.Token != "" {
					out = append(out, c.Gateway)
				}
			}
			sort.Strings(out)
			return out
		})
	}

	return registry
}

// cmdRunScript 执行一个 JS 脚本（run-script 子命令）。
//
// 用法：jarvis-daemon run-script <file.js> [--arg key=value ...]
//   - <file.js>：脚本文件路径（必填）
//   - --arg key=value：可选，注入脚本全局对象 jarvis.args（如 jarvis.args.path）
//
// 脚本内可调用 jarvis.cap / jarvis.caps 做自动化；print/console.log 输出到 stdout，
// console.error 输出到 stderr；脚本顶层返回值打印到 stdout。
func cmdRunScript(args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("用法: jarvis-daemon run-script <file.js> [--arg key=value ...]")
	}

	fs := flag.NewFlagSet("run-script", flag.ContinueOnError)
	argFlags := argFlags{}
	fs.Var(&argFlags, "arg", "脚本参数 key=value（可重复指定）")
	// 手动解析：第一个非 flag 参数是脚本文件路径，其余是 --arg。
	// 用 fs.Parse 会因未知位置参数报错，故先分离脚本路径再解析选项。
	scriptPath := ""
	rest := make([]string, 0, len(args))
	for _, a := range args {
		if scriptPath == "" && !isFlag(a) {
			scriptPath = a
			continue
		}
		rest = append(rest, a)
	}
	if scriptPath == "" {
		return fmt.Errorf("用法: jarvis-daemon run-script <file.js> [--arg key=value ...]")
	}
	if err := fs.Parse(rest); err != nil {
		return err
	}

	// 读取脚本文件。
	source, err := os.ReadFile(scriptPath)
	if err != nil {
		return fmt.Errorf("读取脚本 %s 失败: %w", scriptPath, err)
	}

	// 装配能力注册表（复用 run 流程的装配逻辑）。
	registry := newRuntimeRegistry(nil)

	// 创建运行时并注入 jarvis 能力对象。
	r := jsruntime.New()
	r.SetOutput(func(s string) { fmt.Print(s) }, func(s string) { fmt.Fprint(os.Stderr, s) })
	if err := jsruntime.InstallBridge(r, registry); err != nil {
		return fmt.Errorf("注入 jarvis 能力对象失败: %w", err)
	}

	// 注入脚本参数 jarvis.args。
	if err := jsruntime.InstallScriptArgs(r, argFlags); err != nil {
		return fmt.Errorf("注入 jarvis.args 失败: %w", err)
	}

	// 执行脚本。
	result, err := r.RunScriptFile(scriptPath, string(source))
	if err != nil {
		// 脚本执行错误输出到 stderr（含堆栈），返回错误使退出码非 0。
		fmt.Fprintf(os.Stderr, "[run-script] 执行失败: %v\n", err)
		return fmt.Errorf("脚本执行失败: %v", err)
	}

	// 脚本顶层返回值非 undefined 时打印到 stdout。
	if result != nil {
		if s, ok := result.(string); ok {
			fmt.Println(s)
		} else {
			fmt.Println(result)
		}
	}
	return nil
}

// argFlags 收集 --arg key=value 参数。
type argFlags map[string]string

func (a argFlags) String() string { return "" }
func (a argFlags) Set(v string) error {
	if a == nil {
		return nil
	}
	key, val, ok := strings.Cut(v, "=")
	if !ok || key == "" {
		return fmt.Errorf("--arg 需要 key=value 格式，实际: %q", v)
	}
	a[key] = val
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
  jarvis-daemon login [选项]     用用户名密码登录网关并向本地服务推送凭据
  jarvis-daemon gateway-filter <get|set> [选项]  读写网关黑白名单（仅限本机）
  jarvis-daemon run-script <file.js> [--arg key=value ...]  执行 JS 脚本（可调用 jarvis 能力）
  jarvis-daemon self-update-apply [选项]  自动更新 helper（内部使用，勿手动调用）

选项（run / install 共用）:
  -listen string    本地 API 监听地址（覆盖配置文件）
  -gateway string   默认网关地址（覆盖配置文件）
  -config string    配置文件路径（默认 ~/.jarvis/daemon/config.yaml）
  -web-listen string  Web 登录服务监听地址（覆盖配置文件，默认 0.0.0.0:17801；传空串关闭）

选项（login 专用）:
  -gateway string   网关地址（覆盖配置文件）
  -u string         登录用户名（缺省时交互式输入；密码始终交互式输入）
  -listen string    本地 API 监听地址（覆盖配置文件）
  -config string    配置文件路径（默认 ~/.jarvis/daemon/config.yaml）
`)
}

// isNonLoopbackListen 判断监听地址是否会对外（非回环）暴露。
// 仅用于决定是否打印安全风险提示：绑定 127.0.0.1 / ::1 时不应误报。
// 规则：
//   - 空串视为关闭服务，返回 false；
//   - 主机部分为空（如 ":17801"）或为 0.0.0.0 / :: 表示监听所有网卡，返回 true；
//   - 主机为回环地址（127.0.0.0/8、::1、localhost）返回 false；
//   - 其余（含具体内网 IP、主机名）一律按对外暴露处理，返回 true。
func isNonLoopbackListen(addr string) bool {
	addr = strings.TrimSpace(addr)
	if addr == "" {
		return false
	}
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		// 解析失败时保守处理：无法确认是回环，就按对外暴露提示。
		return true
	}
	host = strings.TrimSpace(host)
	if host == "" {
		return true
	}
	if strings.EqualFold(host, "localhost") {
		return false
	}
	if ip := net.ParseIP(host); ip != nil {
		return !ip.IsLoopback()
	}
	// 主机名等无法判定，按对外暴露处理。
	return true
}

func runDaemon(args []string) {
	// 隐藏自身控制台窗口：Windows 上由计划任务以交互方式启动控制台程序时，
	// 系统会分配一个可见的控制台窗口，用户桌面上会常驻一个黑框。
	// 非 Windows 平台为空操作。
	service.HideSelfConsole()

	// 日志落盘：Windows 上由计划任务启动时 stderr 无接收方，日志会全部丢失。
	// 这里同时写一份到 ~/.jarvis/logs/daemon.log，便于事后排查；失败仅降级为 stderr。
	if logPath := daemonlog.Setup(); logPath != "" {
		log.Printf("[daemon] 日志文件: %s", logPath)
	}

	fs := flag.NewFlagSet("run", flag.ExitOnError)
	listenFlag := fs.String("listen", "", "本地 API 监听地址（覆盖配置文件）")
	gatewayFlag := fs.String("gateway", "", "默认网关地址（覆盖配置文件）")
	configFlag := fs.String("config", "", "配置文件路径（默认 ~/.jarvis/daemon/config.yaml）")
	webListenFlag := fs.String("web-listen", "", "Web 登录服务监听地址（覆盖配置文件；传空串可关闭）")
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
	// -web-listen 需要区分「未提供」（沿用配置文件）与「显式传空串」（关闭服务）：
	// flag 默认值也是空串，无法用值判断，故用 fs.Visit 检测该选项是否真的出现过。
	webListenSet := false
	fs.Visit(func(f *flag.Flag) {
		if f.Name == "web-listen" {
			webListenSet = true
		}
	})
	if webListenSet {
		cfg.WebListen = *webListenFlag
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

	// 清理上一次自动更新遗留的中间产物（尝试状态、.new/.helper.exe 残留）。
	// 放在这里是因为：Windows 上更新走 helper 路径，父进程启动 helper 后立即退出、
	// helper 又删不掉正在运行的自身，只有「替换完成后的新进程启动时」才能安全清理。
	// 无条件调用（不依赖 restored）：函数内部幂等，且仅在「目标版本 == 当前版本」
	// 时才清除尝试状态，失败退避/熔断信息不受影响。
	selfupdate.CleanupAfterUpdate(version)

	// 注册当前平台的能力，供网关下发指令时执行。
	registry := newRuntimeRegistry(store)
	log.Printf("[daemon] 已注册 %d 个平台能力", len(registry.ListForPlatform(capability.Current())))

	// 网关黑白名单：由 daemon 自身配置（config.yaml），仅限本机通过
	// /api/gateway-filter 或 `jarvis-daemon gateway-filter` 修改。
	// 刻意不走前端页面推送：前端与 daemon 可能不同机，推送语义不通。
	// 名单只阻止「新连接」，已在连的旧连接不主动断开（见 ConnectWithName）。
	gwFilter := gatewayfilter.New(cfg.GatewayFilterMode, cfg.GatewayFilterPatterns)
	if mode, patterns := gwFilter.Snapshot(); mode != gatewayfilter.ModeOff {
		log.Printf("[daemon] 网关黑白名单已启用: mode=%s patterns=%v", mode, patterns)
	}

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
		// 黑白名单拦截：不允许的网关不建立连接。
		AllowGateway: gwFilter.Allows,
		OnGatewayStateChange: func(gateway, state string) {
			log.Printf("[daemon] 连接状态: %s (%s)", state, gateway)
		},
		OnGatewayAuthError: func(gateway string, code int, reason string) {
			// 鉴权失败只影响该网关：标记其 Token 失效，等待网页重新推送。
			log.Printf("[daemon] 网关 %s 鉴权失败（关闭码 %d），标记 Token 失效，等待网页重新推送", gateway, code)
			store.MarkTokenInvalid(gateway)
		},
		OnGatewayHelloAck: func(gateway, sessionID, latestExtVersion string) {
			// 网关随握手下发的扩展最新版本（旧字段，兼容保留）。
			// 版本号全局统一，实际同步以 daemon_update.latest_version 为准
			// （见 OnGatewayDaemonUpdate）；此处仅记录，供开关补查时兜底使用。
			rememberGatewayExtVersion(gateway, latestExtVersion)
		},
		OnGatewayDaemonUpdate: func(gateway, sessionID string, info map[string]any) {
			// 网关随握手告知 daemon 有新版本；受「自动更新」开关约束，异步执行。
			// 放在独立 goroutine 中：下载 + 替换可能耗时，不能阻塞 WS 读循环。
			maybeAutoUpdateDaemon(gateway, sessionID, info)
			// 版本号全局统一（扩展与 daemon 同版本），故 daemon_update.latest_version
			// 同时也是「网关打包的扩展最新版本」：据此驱动扩展自动同步。
			// 记下来供「扩展开关随后被打开」时补查使用（开关常晚于握手推送）。
			if latest, _ := info["latest_version"].(string); latest != "" {
				rememberGatewayExtVersion(gateway, latest)
				maybeAutoSyncBrowserExt(gateway, latest)
			}
		},
	})

	// 暴露给自动更新流程，用于回执更新进度（见 reportDaemonUpdateStatus）。
	currentManager = manager

	// 若上一次是「自动更新 → 重启」恢复了凭据，则主动发起连接（否则等网页推送）。
	if restored {
		manager.ConnectWithName(restoredCreds.Gateway, restoredCreds.Token, restoredCreds.Name)
	}

	api := localapi.New(store, manager, version)
	// 开关由关闭变为打开时，补做一次扩展同步检查：daemon 只在 hello_ack 时检查
	// 一次开关，而前端推送开关通常晚于 hello_ack，若不补查会一直判定为「已关闭」。
	api.SetOnBrowserExtEnabled(func() { onBrowserExtSwitchEnabled(manager) })
	// 网关黑白名单：读取当前内存态；更新时同时改内存态并持久化到 config.yaml。
	// 接口本身在 localapi 内已强制校验来源回环（仅限本机访问）。
	api.SetGatewayFilter(
		func() (string, []string) { return gwFilter.Snapshot() },
		func(mode string, patterns []string) (string, []string, error) {
			gwFilter.Set(mode, patterns)
			actualMode, actualPatterns := gwFilter.Snapshot()
			if err := config.UpdateGatewayFilter(cfgPath, actualMode, actualPatterns); err != nil {
				// 内存态已更新但落盘失败：返回错误让调用方知晓（重启后会丢失）。
				return actualMode, actualPatterns, err
			}
			return actualMode, actualPatterns, nil
		},
	)

	srv := localapi.NewHTTPServer(cfg.Listen, api.Handler())

	// Web 登录服务：供**其他机器**的浏览器访问（无 GUI 主机上没有浏览器）。
	// 与本地 API 相互独立；WebListen 为空表示关闭该服务。
	var webSrv *http.Server
	if strings.TrimSpace(cfg.WebListen) != "" {
		ui := webui.New(store, manager, version)
		webSrv = localapi.NewHTTPServer(cfg.WebListen, ui.Handler())
	}

	// 若配置里已有网关但无 Token，则不主动连接（等网页推送）。
	log.Printf("[daemon] jarvis-daemon %s 启动，本地 API: http://%s", version, cfg.Listen)
	if webSrv != nil {
		// 仅当确实绑定了非回环地址时才提示风险，避免绑 127.0.0.1 时误报。
		if isNonLoopbackListen(cfg.WebListen) {
			log.Printf("[daemon] Web 登录页: http://%s/（绑定非回环地址，仅限可信内网使用）", cfg.WebListen)
		} else {
			log.Printf("[daemon] Web 登录页: http://%s/", cfg.WebListen)
		}
	}
	if cfgPath != "" {
		log.Printf("[daemon] 配置文件: %s", cfgPath)
	}

	errCh := make(chan error, 1)
	go func() {
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
	}()
	if webSrv != nil {
		go func() {
			if err := webSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
				// Web 登录服务启动失败不应拖垮整个守护进程（本地 API 仍可用），
				// 仅记录日志，便于用户在无 GUI 主机上排查端口占用等问题。
				log.Printf("[daemon] Web 登录服务启动失败（%s）: %v", cfg.WebListen, err)
			}
		}()
	}

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
	if webSrv != nil {
		if err := webSrv.Shutdown(shutdownCtx); err != nil {
			log.Printf("[daemon] 关闭 Web 登录服务失败: %v", err)
		}
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

// gatewayExtVersionMu 保护 gatewayExtVersions。
var gatewayExtVersionMu sync.Mutex

// gatewayExtVersions 记录各网关最近一次下发的扩展最新版本（键为 GatewayKey）。
//
// 为什么需要：maybeAutoSyncBrowserExt 的版本号来自握手（daemon_update），而
// 「开关被打开」这一事件发生在握手之后，此时没有新的握手可依赖，只能回查这里
// 缓存的值，否则补查时拿不到版本号、无法判断是否需要同步。
var gatewayExtVersions = map[string]string{}

// rememberGatewayExtVersion 记录某网关最近一次下发的扩展最新版本。
//
// 空串表示网关未提供版本：忽略而不覆盖，避免旧的 hello_ack 空值把随后
// daemon_update 带来的真实版本号冲掉（两者在同一轮握手中先后到达）。
func rememberGatewayExtVersion(gateway, latestVersion string) {
	if latestVersion == "" {
		return
	}
	key := auth.GatewayKey(gateway)
	gatewayExtVersionMu.Lock()
	defer gatewayExtVersionMu.Unlock()
	gatewayExtVersions[key] = latestVersion
}

// gatewayExtVersionOf 取某网关最近一次下发的扩展最新版本；无记录时返回 ("", false)。
func gatewayExtVersionOf(gateway string) (string, bool) {
	key := auth.GatewayKey(gateway)
	gatewayExtVersionMu.Lock()
	defer gatewayExtVersionMu.Unlock()
	v, ok := gatewayExtVersions[key]
	return v, ok
}

// onBrowserExtSwitchEnabled 在「自动安装/更新浏览器扩展」开关由关闭变为打开时调用，
// 对所有已连接、且已知网关扩展版本的网关补做一次同步检查。
//
// 为什么需要：daemon 启动后先连网关、收 hello_ack 时开关仍是默认 false（前端尚未
// 推送），于是打印「已关闭，跳过自动同步」；前端随后才把开关推来，但 daemon 不会
// 重新检查，导致用户明明已打开开关却始终不同步，直到下次重连。此处在开关打开时
// 主动补查一次，消除该时序依赖。
func onBrowserExtSwitchEnabled(manager *wsclient.Manager) {
	for _, st := range manager.Status() {
		if !st.Connected {
			continue
		}
		latest, ok := gatewayExtVersionOf(st.Gateway)
		if !ok {
			// 该网关尚未下发过版本（未收到 hello_ack），等其自身握手时再处理。
			continue
		}
		log.Printf("[daemon] 扩展开关已打开，补做一次同步检查（网关 %s，网关版本 %q）", st.Gateway, latest)
		maybeAutoSyncBrowserExt(st.Gateway, latest)
	}
}

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

		// 同步完成后自动打开本机浏览器的扩展页：用户需在扩展页点一次「刷新」
		// （已安装）或「加载已解压的扩展程序」（未安装）新版本才生效，自动打开
		// 省去手动聚焦窗口 → Ctrl+L → 输入 URL → 回车。
		// 失败只记日志：扩展文件已成功落盘，打开页面失败不影响同步结果。
		opened, openErr := capability.OpenBrowserExtensionsPage()
		if openErr != nil {
			log.Printf("[daemon] 自动打开浏览器扩展页失败（网关 %s）: %v", gateway, openErr)
		} else if len(opened) > 0 {
			log.Printf("[daemon] 已自动打开浏览器扩展页：%s", strings.Join(opened, "、"))
		} else {
			log.Printf("[daemon] 未找到可打开的浏览器（Edge/Chrome 均未安装），请手动打开扩展页")
		}
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

// daemonRetryScheduled 标记「已有一个待定的退避重试定时器」。
//
// 为什么需要：退避到期后必须主动重试（见下方 maybeAutoUpdateDaemon 注释），而触发
// 点（WS 握手）可能短时间多次到达（如前端反复推送凭据导致重连）。若无去重，每次
// 触发都会再起一个定时器，窗口一到多个 goroutine 同时抢 daemonUpdateMu，形成重试
// 风暴。定时器到期时先清除本标记再执行，保证后续仍能重新安排。
var daemonRetryScheduled bool

// daemonRetryMu 保护 daemonRetryScheduled。
var daemonRetryMu sync.Mutex

// scheduleDaemonUpdateRetry 在 after 之后自动重试一次自动更新。
//
// 为什么必须主动重试：maybeAutoUpdateDaemon 的触发点是 WS 握手收到 hello_ack，但
// 连接稳定时只有 ping/pong 心跳、不产生 hello_ack；且前端重复推送相同凭据时
// ConnectWithName 会因幂等判断跳过重建连接（见 wsclient/manager.go），同样不产生
// hello_ack。若不主动安排定时器，退避窗口到期后没有任何事件来唤醒检查，更新会
// 永久停滞在「退避中」。
//
// 去重：同一时刻只允许一个待定定时器；已安排则忽略本次请求。
func scheduleDaemonUpdateRetry(gateway, sessionID string, info map[string]any, after time.Duration) {
	daemonRetryMu.Lock()
	if daemonRetryScheduled {
		daemonRetryMu.Unlock()
		return
	}
	daemonRetryScheduled = true
	daemonRetryMu.Unlock()

	log.Printf("[daemon] 将在 %s 后重试自动更新（网关 %s）", after.Round(time.Second), gateway)
	time.AfterFunc(after, func() {
		// 先清除标记再调用：即使重试后再次失败，也能重新安排下一轮定时器。
		daemonRetryMu.Lock()
		daemonRetryScheduled = false
		daemonRetryMu.Unlock()

		log.Printf("[daemon] 退避到期，自动重试 daemon 更新（网关 %s）", gateway)
		maybeAutoUpdateDaemon(gateway, sessionID, info)
	})
}

// maybeAutoUpdateDaemon 在网关下发 daemon 更新指令时异步执行更新。
//
// 设计要点：
//   - 无条件自动更新：daemon 必须与网关保持同版本，网关在 hello_ack 中把自身
//     版本作为「最新版本」下发，daemon 比对后自动更新，无开关、无环境变量；
//   - 立即返回，把下载/替换放到独立 goroutine（可能耗时数秒），不阻塞 WS 读循环；
//   - 更新前把当前凭据临时落盘，供重启后恢复登录态（见 selfupdate.SaveTokenState）；
//   - 任何失败只记日志，绝不影响连接与既有能力；
//   - 退避到期后主动安排定时重试（见 scheduleDaemonUpdateRetry），不依赖外部握手事件。
func maybeAutoUpdateDaemon(gateway, sessionID string, info map[string]any) {
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

		// 防重复：熔断（重启循环）+ 同版本失败不重试 + 失败退避。
		// 触发点是每次 WS 握手，若不加约束，失败的更新会随重连无限重试。
		state, _ := selfupdate.LoadAttemptState()
		if skip, reason := selfupdate.ShouldSkipUpdate(state, version, parsed.LatestVersion, selfupdate.NowUnix()); skip {
			log.Printf("[daemon] 跳过自动更新（网关 %s）: %s", gateway, reason)
			// 退避中则安排到期主动重试；RetryAfter 返回 0 表示熔断态（等网关发新版），
			// 此时不得安排重试，否则会陷入重启循环。
			if wait := selfupdate.RetryAfter(state, version, parsed.LatestVersion, selfupdate.NowUnix()); wait > 0 {
				scheduleDaemonUpdateRetry(gateway, sessionID, info, wait+time.Second)
			}
			return
		}

		target, err := service.InstalledBinaryPath()
		if err != nil {
			log.Printf("[daemon] 无法确定可执行文件路径，跳过自动更新: %v", err)
			return
		}

		// 更新会重启服务，先把当前凭据临时落盘，供重启后恢复登录态。
		// 落盘失败不阻断更新（最坏情况只是重启后需重新推送凭据）。
		saveCurrentCredentialsForUpdate(gateway)

		// 记录「已开始尝试更新到该版本」并置 InProgress：若替换后新版本起不来，
		// 新进程启动时会读到该标记且版本未变，从而熔断，避免无限重启。
		// 目标版本变化时重置计数（视为新机会）。
		attempts := state.Attempts
		if !selfupdate.SameVersion(state.TargetVersion, parsed.LatestVersion) {
			attempts = 0
		}
		_ = selfupdate.SaveAttemptState(selfupdate.AttemptState{
			TargetVersion:   parsed.LatestVersion,
			Attempts:        attempts,
			LastAttemptUnix: selfupdate.NowUnix(),
			InProgress:      true,
		})

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
			// 失败：累加尝试次数并记录原因，供下次握手时退避判断。
			_ = selfupdate.SaveAttemptState(selfupdate.AttemptState{
				TargetVersion:   parsed.LatestVersion,
				Attempts:        attempts + 1,
				LastAttemptUnix: selfupdate.NowUnix(),
				LastError:       err.Error(),
				InProgress:      false,
			})
			log.Printf("[daemon] 自动更新 daemon 失败（网关 %s，第 %d 次）: %v", gateway, attempts+1, err)
			return
		}
		// 成功：清除尝试状态（Linux 上替换已完成；Windows 上已交给 helper）。
		// 若随后重启失败，新进程读到的是已清除状态，不会误熔断。
		_ = selfupdate.ClearAttemptState()
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
