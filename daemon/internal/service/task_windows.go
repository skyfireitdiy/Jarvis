//go:build windows

package service

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode/utf16"
)

// cmdTimeout 是单次外部命令调用的超时时间。
const cmdTimeout = 30 * time.Second

// taskService 是 Windows 下的计划任务实现。
//
// 自启由计划任务负责（登录时触发），进程生命周期由 PID 文件跟踪。
type taskService struct{}

// PidFilePath 返回 PID 文件路径：~/.jarvis/pids/jarvis-daemon.pid。
func PidFilePath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("获取用户主目录失败: %w", err)
	}
	return filepath.Join(home, ".jarvis", "pids", "jarvis-daemon.pid"), nil
}

// BuildTaskCommand 生成计划任务要执行的命令行（含可执行文件本身）。
func BuildTaskCommand(opts Options) (string, error) {
	execPath, err := ResolveExecPath(opts)
	if err != nil {
		return "", err
	}
	parts := append([]string{execPath}, BuildRunArgs(opts)...)
	for i, p := range parts {
		if strings.ContainsAny(p, " \t") {
			parts[i] = `"` + p + `"`
		}
	}
	return strings.Join(parts, " "), nil
}

// BuildCreateArgs 生成 schtasks 创建计划任务的参数。
//
// Deprecated: 保留仅为兼容既有调用与测试。计划任务改由 buildTaskXML 生成的完整
// XML 定义注册（见 Install），因为 schtasks 的 /SC ONLOGON 等简单参数无法表达
// 重启策略、执行时限、电池策略等关键设置，曾导致 daemon 频繁退出且不自动恢复。
func BuildCreateArgs(opts Options) ([]string, error) {
	command, err := BuildTaskCommand(opts)
	if err != nil {
		return nil, err
	}
	return []string{
		"/Create",
		"/TN", TaskName,
		"/TR", command,
		"/SC", "ONLOGON",
		"/RL", "HIGHEST",
		"/F",
	}, nil
}

// currentUserID 返回计划任务 Principal 使用的用户标识，形如 "DOMAIN\\user"。
//
// 为什么不用 os.Getenv("USERNAME") 单独取值：计划任务的 UserId 需要能唯一定位
// 账户，纯用户名在域环境下可能重名；优先用 USERDOMAIN\USERNAME 组合，
// 取不到时退回 USERNAME（本地账户/测试环境）。
func currentUserID() string {
	user := strings.TrimSpace(os.Getenv("USERNAME"))
	if user == "" {
		return ""
	}
	domain := strings.TrimSpace(os.Getenv("USERDOMAIN"))
	if domain == "" || strings.EqualFold(domain, os.Getenv("COMPUTERNAME")) {
		// 本地账户：用 "计算机名\用户名" 与 Task Scheduler 的显示一致。
		if name := strings.TrimSpace(os.Getenv("COMPUTERNAME")); name != "" {
			return name + `\` + user
		}
		return user
	}
	return domain + `\` + user
}

// buildTaskXML 生成计划任务的完整 XML 定义（Task Scheduler schema 1.2）。
//
// 为什么必须用 XML 而不是 schtasks 的简单参数：真机实测旧实现创建的任务存在
// 以下缺陷，直接导致「daemon 经常退出且不恢复」：
//
//	RestartCount=0          → 进程崩溃后永不重启，只能等下次登录
//	ExecutionTimeLimit=PT72H→ 运行满 72 小时被 Task Scheduler 强制结束
//	DisallowStartIfOnBatteries=True / StopIfGoingOnBatteries=True
//	                        → 笔记本切到电池供电时任务被停掉
//	StartWhenAvailable=False→ 错过触发时机后不补跑
//	MultipleInstances 未设置 → 可能并发起多个实例争抢同一 PID 文件与端口
//
// 这些设置 schtasks 命令行都没有对应开关，只能通过 /XML 注册。
func buildTaskXML(opts Options) (string, error) {
	execPath, err := ResolveExecPath(opts)
	if err != nil {
		return "", err
	}
	// Command 与 Arguments 必须分开填：XML 里 <Command> 只放可执行文件路径，
	// 参数放 <Arguments>。若像 schtasks /TR 那样拼成一整串，Task Scheduler 会把
	// 整串当作命令名，导致启动失败。
	arguments := BuildRunArgs(opts)

	userID := currentUserID()
	if userID == "" {
		return "", fmt.Errorf("无法确定当前用户（USERNAME 为空），不能创建计划任务")
	}

	var b strings.Builder
	b.WriteString(`<?xml version="1.0" encoding="UTF-16"?>` + "\n")
	b.WriteString(`<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">` + "\n")

	// RegistrationInfo：仅用于在任务计划程序中展示，不影响行为。
	b.WriteString("  <RegistrationInfo>\n")
	b.WriteString("    <Description>Jarvis 守护进程（登录时自动启动，异常退出后自动重启）</Description>\n")
	b.WriteString("  </RegistrationInfo>\n")

	// Triggers：登录时触发。
	b.WriteString("  <Triggers>\n")
	b.WriteString("    <LogonTrigger>\n")
	b.WriteString("      <Enabled>true</Enabled>\n")
	b.WriteString("    </LogonTrigger>\n")
	b.WriteString("  </Triggers>\n")

	// Principals：以当前用户身份、最高权限运行。
	// LogonType=InteractiveToken 对应旧实现的 /IT（仅在有交互登录会话时运行），
	// 这样进程能访问用户桌面会话（截图、剪贴板等能力依赖它）。
	b.WriteString("  <Principals>\n")
	b.WriteString(`    <Principal id="Author">` + "\n")
	b.WriteString("      <UserId>" + xmlEscape(userID) + "</UserId>\n")
	b.WriteString("      <LogonType>InteractiveToken</LogonType>\n")
	b.WriteString("      <RunLevel>HighestAvailable</RunLevel>\n")
	b.WriteString("    </Principal>\n")
	b.WriteString("  </Principals>\n")

	b.WriteString("  <Settings>\n")
	// 已在运行时不启动新实例，避免多实例争抢 PID 文件与监听端口。
	b.WriteString("    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n")
	// 电池供电时仍允许启动 / 不因切换到电池而停止。
	b.WriteString("    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n")
	b.WriteString("    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n")
	b.WriteString("    <AllowHardTerminate>true</AllowHardTerminate>\n")
	// 错过触发时机（如机器休眠）后补跑。
	b.WriteString("    <StartWhenAvailable>true</StartWhenAvailable>\n")
	// daemon 自身负责重连网关，不需要网络可用性门控（否则断网时任务不启动）。
	b.WriteString("    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>\n")
	b.WriteString("    <IdleSettings>\n")
	b.WriteString("      <StopOnIdleEnd>false</StopOnIdleEnd>\n")
	b.WriteString("      <RestartOnIdle>false</RestartOnIdle>\n")
	b.WriteString("    </IdleSettings>\n")
	b.WriteString("    <AllowStartOnDemand>true</AllowStartOnDemand>\n")
	b.WriteString("    <Enabled>true</Enabled>\n")
	b.WriteString("    <Hidden>false</Hidden>\n")
	b.WriteString("    <RunOnlyIfIdle>false</RunOnlyIfIdle>\n")
	b.WriteString("    <WakeToRun>false</WakeToRun>\n")
	// PT0S = 无执行时限。旧实现默认 PT72H，运行满 72 小时被强制结束。
	b.WriteString("    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n")
	b.WriteString("    <Priority>7</Priority>\n")
	// 异常退出后自动重启：每 1 分钟重试，最多 3 次。
	b.WriteString("    <RestartOnFailure>\n")
	b.WriteString("      <Interval>PT1M</Interval>\n")
	b.WriteString("      <Count>3</Count>\n")
	b.WriteString("    </RestartOnFailure>\n")
	b.WriteString("  </Settings>\n")

	b.WriteString(`  <Actions Context="Author">` + "\n")
	b.WriteString("    <Exec>\n")
	b.WriteString("      <Command>" + xmlEscape(execPath) + "</Command>\n")
	if len(arguments) > 0 {
		b.WriteString("      <Arguments>" + xmlEscape(quoteArgs(arguments)) + "</Arguments>\n")
	}
	b.WriteString("    </Exec>\n")
	b.WriteString("  </Actions>\n")

	b.WriteString("</Task>\n")
	return b.String(), nil
}

// quoteArgs 把参数列表拼成命令行字符串，含空白的参数用双引号包裹。
func quoteArgs(args []string) string {
	parts := make([]string, len(args))
	for i, a := range args {
		if strings.ContainsAny(a, " \t") {
			parts[i] = `"` + a + `"`
		} else {
			parts[i] = a
		}
	}
	return strings.Join(parts, " ")
}

// xmlEscape 转义 XML 文本节点的特殊字符。
//
// 为什么手写而不用 encoding/xml：这里生成的是固定模板，手写更直观且能精确控制
// 元素顺序（Task Scheduler 对 schema 顺序敏感）。需要转义的字符集很小。
func xmlEscape(s string) string {
	replacer := strings.NewReplacer(
		"&", "&amp;",
		"<", "&lt;",
		">", "&gt;",
		`"`, "&quot;",
		"'", "&apos;",
	)
	return replacer.Replace(s)
}

// encodeUTF16LE 把字符串编码为带 BOM 的 UTF-16LE 字节序列。
//
// 为什么必须 UTF-16LE：schtasks /Create /XML 对 XML 文件的编码有硬性要求——
// 只接受 UTF-16LE（带 BOM）。若写成 UTF-8，即使 XML 声明是 encoding="UTF-8"，
// schtasks 也会报「XML 格式不正确」或直接乱码解析失败。
//
// 不用 golang.org/x/text：项目约束不引入新依赖，标准库 unicode/utf16 足够。
func encodeUTF16LE(s string) []byte {
	units := utf16.Encode([]rune(s))
	out := make([]byte, 0, 2+len(units)*2)
	out = append(out, 0xFF, 0xFE) // BOM，小端
	for _, u := range units {
		out = append(out, byte(u), byte(u>>8))
	}
	return out
}

// Install 创建登录时触发的计划任务（不启动）。
// 安装前先把可执行文件拷贝到固定安装目录 ~/.jarvis/bin，使计划任务指向的位置稳定。
//
// 注册方式为 schtasks /Create /XML：只有 XML 才能表达重启策略、无执行时限、
// 电池策略等关键设置（详见 buildTaskXML 的说明）。
func (s *taskService) Install(opts Options) (string, error) {
	opts, installedPath, err := PrepareInstalledBinary(opts)
	if err != nil {
		return "", err
	}
	xmlBody, err := buildTaskXML(opts)
	if err != nil {
		return "", err
	}
	// schtasks 要求 XML 文件为 UTF-16LE（带 BOM），因此不能直接写字符串。
	tmpPath, err := writeTaskXMLTemp(xmlBody)
	if err != nil {
		return "", err
	}
	defer os.Remove(tmpPath)

	if _, err := runCmd("schtasks", "/Create", "/TN", TaskName, "/XML", tmpPath, "/F"); err != nil {
		return "", fmt.Errorf("创建计划任务失败: %w（该任务以最高权限运行，需在**管理员**终端中执行 install）", err)
	}
	return fmt.Sprintf("计划任务已创建：%s（可执行文件：%s）", TaskName, installedPath), nil
}

// writeTaskXMLTemp 把任务 XML 以 UTF-16LE 写入临时文件并返回路径。
//
// 为什么落在系统临时目录而不是 ~/.jarvis：该文件只在 install 期间存活，
// 注册完立即删除，无需持久化；用 os.CreateTemp 保证文件名唯一，避免并发安装冲突。
func writeTaskXMLTemp(xmlBody string) (string, error) {
	f, err := os.CreateTemp("", "jarvis-task-*.xml")
	if err != nil {
		return "", fmt.Errorf("创建临时 XML 文件失败: %w", err)
	}
	path := f.Name()
	if _, err := f.Write(encodeUTF16LE(xmlBody)); err != nil {
		f.Close()
		os.Remove(path)
		return "", fmt.Errorf("写入临时 XML 文件失败: %w", err)
	}
	if err := f.Close(); err != nil {
		os.Remove(path)
		return "", fmt.Errorf("关闭临时 XML 文件失败: %w", err)
	}
	return path, nil
}

// Uninstall 停止服务并删除计划任务。
func (s *taskService) Uninstall() (string, error) {
	_, _ = s.Stop()
	if _, err := runCmd("schtasks", "/Delete", "/TN", TaskName, "/F"); err != nil {
		return "", fmt.Errorf("删除计划任务失败: %w", err)
	}
	// 清理安装目录中的可执行文件（失败不阻断卸载，仅提示）。
	cleanupNote := ""
	if err := RemoveInstalledBinary(); err != nil {
		cleanupNote = fmt.Sprintf("（可执行文件清理失败：%v）", err)
	}
	return fmt.Sprintf("计划任务已删除：%s%s", TaskName, cleanupNote), nil
}

// Start 以分离进程启动守护进程并记录 PID。
//
// 启动的是**固定安装路径**（~/.jarvis/bin/jarvis-daemon.exe）的可执行文件，而不是
// 当前进程路径：计划任务指向的也是该固定路径，两者必须一致，否则用户从下载目录执行
// start 会启动另一个副本，与服务管理（stop/status）观察到的进程对不上。
func (s *taskService) Start() (string, error) {
	pidPath, err := PidFilePath()
	if err != nil {
		return "", err
	}
	if pid := readAlivePID(pidPath); pid > 0 {
		return "", fmt.Errorf("服务已在运行（PID: %d）", pid)
	}

	execPath, err := InstalledBinaryPath()
	if err != nil {
		return "", err
	}
	if _, statErr := os.Stat(execPath); statErr != nil {
		return "", fmt.Errorf("未找到已安装的可执行文件 %s，请先执行 install", execPath)
	}
	cmd := exec.Command(execPath, BuildRunArgs(Options{})...)
	cmd.SysProcAttr = detachedProcAttr()
	if err := cmd.Start(); err != nil {
		return "", fmt.Errorf("启动服务失败: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(pidPath), 0o755); err != nil {
		return "", fmt.Errorf("创建 PID 目录失败: %w", err)
	}
	if err := os.WriteFile(pidPath, []byte(strconv.Itoa(cmd.Process.Pid)), 0o644); err != nil {
		return "", fmt.Errorf("写入 PID 文件失败: %w", err)
	}
	return fmt.Sprintf("服务已启动（PID: %d）", cmd.Process.Pid), nil
}

// Stop 终止守护进程并清理 PID 文件。
func (s *taskService) Stop() (string, error) {
	pidPath, err := PidFilePath()
	if err != nil {
		return "", err
	}
	pid := readAlivePID(pidPath)
	if pid <= 0 {
		_ = os.Remove(pidPath)
		return "服务未运行", nil
	}
	if _, err := runCmd("taskkill", "/PID", strconv.Itoa(pid), "/F"); err != nil {
		return "", fmt.Errorf("停止服务失败: %w", err)
	}
	_ = os.Remove(pidPath)
	return "服务已停止", nil
}

// Restart 先停止再启动。
func (s *taskService) Restart() (string, error) {
	if _, err := s.Stop(); err != nil {
		return "", err
	}
	time.Sleep(2 * time.Second)
	return s.Start()
}

// Status 查询运行与自启状态。
func (s *taskService) Status() (Status, error) {
	var st Status

	if pidPath, err := PidFilePath(); err == nil {
		st.PID = readAlivePID(pidPath)
		st.Running = st.PID > 0
	}

	if _, err := runCmd("schtasks", "/Query", "/TN", TaskName); err == nil {
		st.Enabled = true
	}
	return st, nil
}

// readAlivePID 读取 PID 文件并校验进程是否存活；无效时删除文件并返回 0。
func readAlivePID(pidPath string) int {
	data, err := os.ReadFile(pidPath)
	if err != nil {
		return 0
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(data)))
	if err != nil || pid <= 0 {
		_ = os.Remove(pidPath)
		return 0
	}
	out, err := runCmd("tasklist", "/FI", fmt.Sprintf("PID eq %d", pid), "/NH")
	if err != nil || !strings.Contains(out, strconv.Itoa(pid)) {
		_ = os.Remove(pidPath)
		return 0
	}
	return pid
}

// runCmd 执行外部命令并返回标准输出（UTF-8 文本）。
//
// 编码问题：schtasks / taskkill / tasklist 是原生控制台程序，按**控制台输出代码页**
// 写出文本——中文 Windows 上是 GBK/CP936，不是 UTF-8。Go 的 os/exec 只返回原始字节，
// 直接 string(out) 会把 GBK 按 UTF-8 解释，得到 "����: �ܾ����ʡ�" 这类乱码，
// 用户无法看懂失败原因（真机实测 install 失败时即如此）。
//
// 修复策略（与 internal/capability 的 windows_encoding.go 同思路，不引入 GBK 解码表）：
// 用 PowerShell 包裹执行，借助 PowerShell 完成「GBK 解码 → UTF-8 输出」的转码：
//
//  1. 先按**系统默认**的 [Console]::OutputEncoding（中文系统 = GBK）读取外部命令输出。
//     这一步必须在改编码之前，否则 PowerShell 会用 UTF-8 去解码 GBK 字节而得到乱码。
//  2. 再把 [Console]::OutputEncoding 设为 UTF-8，用 [Console]::Out.Write 写出。
//     此时 Go 侧读到的就是 UTF-8 字节，直接 string(out) 即为正确文本。
//
// 之所以不用 `cmd /c chcp 65001`：chcp 只改 cmd 会话的输出代码页，而原生工具在
// stdout 被重定向到管道时是否遵循该代码页并无保证；PowerShell 的显式转码不依赖
// 子进程行为，更可靠（也与项目既有的 runWindowsPowerShellCommand 路径一致）。
//
// 脚本经 -EncodedCommand（base64 UTF-16LE）传递，避免命令行参数按 ANSI 代码页解析
// 导致脚本内非 ASCII 字符损坏（见 windows_encoding.go 的说明）。
func runCmd(name string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), cmdTimeout)
	defer cancel()

	script := buildPowerShellScript(name, args)
	cmd := exec.CommandContext(ctx, "powershell.exe",
		"-NoProfile",
		"-NonInteractive",
		"-ExecutionPolicy", "Bypass",
		"-EncodedCommand", encodePowerShellCommand(script),
	)
	// 守护进程本身无控制台，不加该属性会为 PowerShell 新建控制台窗口（闪黑框）。
	cmd.SysProcAttr = hideWindowProcAttr()
	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() != nil {
			return "", fmt.Errorf("%s 超时", name)
		}
		if exitErr, ok := err.(*exec.ExitError); ok {
			msg := strings.TrimSpace(string(exitErr.Stderr))
			if msg == "" {
				// PowerShell 把外部命令的 stdout/stderr 都写到了自己的 stdout，
				// 且可能混入 CLIXML 噪音（见 stripPowerShellClixml），需先清理再取用。
				msg = stripPowerShellClixml(string(out))
			}
			if msg == "" {
				msg = "命令返回非零退出码，但无输出"
			}
			return string(out), fmt.Errorf("%s 失败: %s", name, msg)
		}
		return "", fmt.Errorf("执行 %s 失败: %w", name, err)
	}
	return string(out), nil
}
