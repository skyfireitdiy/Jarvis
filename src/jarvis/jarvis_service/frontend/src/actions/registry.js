// 统一动作注册表（单一数据源）
// 宠物菜单、命令面板、快捷键均从这里派生动作清单。
// 纯模块：不依赖 Vue，不直接引用 App.vue，所有副作用通过调用方传入的 ctx 回调触发。
//
// 动作对象结构：
// {
//   id: string,
//   label: string,
//   en: string,
//   group: string,
//   icon: string,
//   keywords: string[],
//   shortcut?: string,
//   enabled?: (ctx) => boolean,
//   run: (ctx) => void | Promise<void>
// }

export const ACTIONS = [
  // ===== 当前 Agent 组（原面板头部图标操作）=====
  {
    id: "current-view-diff",
    label: "查看变更",
    shortcut: "Space a d",
    condition: "需选中当前 Agent",
    en: "View Diff",
    group: "当前 Agent",
    icon: "🔀",
    keywords: ["变更", "diff", "改动", "修改", "变化"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.viewCurrentDiff && ctx.viewCurrentDiff(),
  },
  {
    id: "current-view-rules",
    label: "查看规则",
    shortcut: "Space a r",
    condition: "需选中当前 Agent",
    en: "View Rules",
    group: "当前 Agent",
    icon: "📜",
    keywords: ["规则", "rules", "规范"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.viewCurrentRules && ctx.viewCurrentRules(),
  },
  {
    id: "current-view-tools",
    label: "查看工具",
    shortcut: "Space a t",
    condition: "需选中当前 Agent",
    en: "View Tools",
    group: "当前 Agent",
    icon: "🔧",
    keywords: ["工具", "tools"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.viewCurrentTools && ctx.viewCurrentTools(),
  },
  {
    id: "current-create-terminal",
    label: "创建终端",
    shortcut: "Space n t",
    condition: "需选中当前 Agent",
    en: "Create Terminal",
    group: "当前 Agent",
    icon: "💻",
    keywords: ["终端", "terminal", "创建", "create"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) =>
      ctx.createTerminalForCurrent && ctx.createTerminalForCurrent(),
  },
  {
    // 全局动作：打开/隐藏编辑器面板，不依赖当前 Agent（与 App.vue 的 Ctrl+E 分支行为一致）
    id: "open-editor",
    label: "打开工作区",
    // 实际由 App.vue 的 Ctrl+E 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Space v e",
    condition: "已登录",
    en: "Open Workspace",
    group: "界面",
    icon: "📝",
    keywords: ["编辑器", "editor", "打开", "open"],
    run: (ctx) => ctx.toggleWorkspacePanel && ctx.toggleWorkspacePanel(),
  },
  {
    // 全局动作：快速抵达编辑器侧边栏的「内容搜索」（编辑器未打开时不响应）
    id: "open-editor-global-search",
    label: "搜索文件内容",
    // 实际由 App.vue 的 Ctrl+Shift+F 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Space v b / Ctrl+Shift+F",
    condition: "需编辑器面板已打开",
    en: "Search File Contents",
    group: "界面",
    icon: "🔎",
    keywords: [
      "全局搜索",
      "内容搜索",
      "搜索",
      "查找",
      "search",
      "content",
      "global",
      "find",
    ],
    run: (ctx) =>
      ctx.openWorkspaceGlobalSearch && ctx.openWorkspaceGlobalSearch(),
  },
  {
    // 全局动作：快速抵达编辑器侧边栏的「文件名搜索」（编辑器未打开时不响应）
    id: "open-editor-file-search",
    label: "搜索文件名",
    // 实际由 App.vue 的 Ctrl+Shift+P 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Space v n / Ctrl+Shift+P",
    condition: "需编辑器面板已打开",
    en: "Search File Names",
    group: "界面",
    icon: "🗂️",
    keywords: [
      "文件名搜索",
      "按名称查找",
      "搜索",
      "查找",
      "search",
      "filename",
      "file",
      "find",
    ],
    run: (ctx) => ctx.openWorkspaceFileSearch && ctx.openWorkspaceFileSearch(),
  },
  {
    // 全局动作：快速抵达编辑器侧边栏的目录树（编辑器未打开时不响应）
    id: "open-editor-file-tree",
    label: "目录树",
    // 实际由 App.vue 的 Ctrl+Shift+E 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Space v r / Ctrl+Shift+E",
    condition: "需编辑器面板已打开",
    en: "File Tree",
    group: "界面",
    icon: "📁",
    keywords: ["目录树", "文件树", "资源管理器", "file", "tree", "explorer"],
    run: (ctx) => ctx.openWorkspaceFileTree && ctx.openWorkspaceFileTree(),
  },
  {
    // 全局动作：打开命令面板
    id: "open-command-palette",
    label: "打开命令面板",
    // 实际由 App.vue 的 Ctrl+P 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Space v p / Ctrl+P",
    condition: "已登录",
    en: "Open Command Palette",
    group: "界面",
    icon: "⌘",
    keywords: ["命令面板", "命令", "面板", "command", "palette", "search"],
    run: (ctx) => ctx.openCommandPalette && ctx.openCommandPalette(),
  },
  {
    // 全局动作：保存编辑器当前标签
    id: "save-active-editor-tab",
    label: "保存当前文件",
    // 实际由 App.vue 的 Ctrl+S 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Space v w / Ctrl+S",
    condition: "需编辑器面板已打开且有活动标签",
    en: "Save Active File",
    group: "界面",
    icon: "💾",
    keywords: ["保存", "文件", "save", "file", "editor"],
    run: (ctx) => ctx.saveActiveWorkspaceTab && ctx.saveActiveWorkspaceTab(),
  },
  {
    // 全局动作：左右分割编辑器工作区
    id: "split-workspace-pane-row",
    label: "左右分割编辑器",
    // 实际由 App.vue 的 Ctrl+\ 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Space p s / Ctrl+\\",
    condition: "需编辑器面板处于文件视图且非移动端",
    en: "Split Editor Right",
    group: "界面",
    icon: "▥",
    keywords: ["分割", "左右", "编辑器", "split", "editor", "pane"],
    run: (ctx) =>
      ctx.splitWorkspacePane && ctx.splitWorkspacePane(ctx.activePaneId, "row"),
  },
  {
    // 全局动作：上下分割编辑器工作区
    id: "split-workspace-pane-column",
    label: "上下分割编辑器",
    // 实际由 App.vue 的 Ctrl+Shift+\ 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Space p h / Ctrl+-",
    condition: "需编辑器面板处于文件视图且非移动端",
    en: "Split Editor Down",
    group: "界面",
    icon: "▤",
    keywords: ["分割", "上下", "编辑器", "split", "editor", "pane"],
    run: (ctx) =>
      ctx.splitWorkspacePane &&
      ctx.splitWorkspacePane(ctx.activePaneId, "column"),
  },
  {
    // 全局动作：关闭当前焦点所在的面板 / 编辑器激活区域
    id: "close-focused-panel",
    label: "关闭当前焦点面板",
    // 实际由 App.vue 的 Ctrl+W 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Space p x / Ctrl+W",
    condition: "需存在当前焦点面板",
    en: "Close Focused Panel",
    group: "界面",
    icon: "✕",
    keywords: ["关闭", "面板", "close", "panel", "焦点"],
    run: (ctx) => ctx.closeFocusedPanel && ctx.closeFocusedPanel(),
  },
  {
    // 全局动作：发送缓冲输入（等待多行输入时）
    id: "send-buffered-input",
    label: "发送缓冲输入",
    // 实际由 App.vue 的 Ctrl+Alt+Enter 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Ctrl+Alt+Enter",
    condition: "需存在缓冲输入",
    en: "Send Buffered Input",
    group: "执行",
    icon: "⏎",
    keywords: ["发送", "缓冲", "输入", "send", "buffer", "input"],
    run: (ctx) => ctx.sendBufferedInput && ctx.sendBufferedInput(),
  },
  {
    // 全局动作：删除宠物大厅中选中的 Agent
    id: "delete-lobby-agent",
    label: "删除选中的 Agent",
    // 实际由 App.vue 的 Delete 分支执行；此处仅作展示，不参与 ctrl+alt 统一分发
    shortcut: "Delete",
    condition: "大厅中已选中 Agent 且焦点不在输入框内",
    en: "Delete Selected Agent",
    group: "大厅",
    icon: "🗑",
    keywords: ["删除", "大厅", "agent", "delete", "lobby"],
    enabled: (ctx) => !!ctx?.lobbyActiveAgentId,
    run: (ctx) =>
      ctx.deleteLobbyAgent && ctx.deleteLobbyAgent(ctx.lobbyActiveAgentId),
  },
  {
    id: "current-toggle-auto-scroll",
    label: "切换自动滚动",
    shortcut: "Space a s",
    condition: "需选中当前 Agent",
    en: "Toggle Auto Scroll",
    group: "当前 Agent",
    icon: "⤓",
    keywords: ["自动滚动", "滚动", "scroll", "auto", "toggle"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.toggleCurrentAutoScroll && ctx.toggleCurrentAutoScroll(),
  },
  {
    id: "current-toggle-auto-read",
    label: "切换自动朗读",
    shortcut: "Space a v",
    condition: "需选中当前 Agent",
    en: "Toggle Auto Read",
    group: "当前 Agent",
    icon: "🔊",
    keywords: ["自动朗读", "朗读", "语音", "read", "speak", "toggle"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.toggleCurrentAutoRead && ctx.toggleCurrentAutoRead(),
  },
  {
    id: "current-exit-non-interactive",
    label: "退出非交互模式",
    shortcut: "Space a x",
    condition: "需选中当前 Agent",
    en: "Exit Non-Interactive Mode",
    group: "当前 Agent",
    icon: "🔓",
    keywords: ["非交互", "退出", "non-interactive", "exit", "unlock"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) =>
      ctx.exitCurrentNonInteractive && ctx.exitCurrentNonInteractive(),
  },
  {
    id: "current-manual-interrupt",
    label: "人工介入",
    shortcut: "Space a i",
    condition: "需选中当前 Agent",
    en: "Manual Interrupt",
    group: "当前 Agent",
    icon: "🛑",
    keywords: ["人工介入", "中断", "介入", "interrupt", "manual", "stop"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.interruptCurrentAgent && ctx.interruptCurrentAgent(),
  },
  {
    id: "current-rename",
    label: "重命名",
    shortcut: "Space a n",
    // F2 优先重命名当前 Agent；无当前 Agent 时才让位给 node-rename（见 App.vue 的 F2 分支）
    shortcutScope: "global",
    condition: "需选中当前 Agent；与节点重命名共用 F2 时以 Agent 优先",
    en: "Rename",
    group: "当前 Agent",
    icon: "✏",
    keywords: ["重命名", "改名", "rename"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.renameCurrentAgent && ctx.renameCurrentAgent(),
  },
  {
    id: "current-copy",
    label: "复制",
    shortcut: "Space a c",
    condition: "需选中当前 Agent",
    en: "Copy",
    group: "当前 Agent",
    icon: "📋",
    keywords: ["复制", "克隆", "copy", "clone", "duplicate"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.copyCurrentAgent && ctx.copyCurrentAgent(),
  },
  {
    id: "current-edit-access",
    label: "权限管理",
    shortcut: "Space a e",
    condition: "需选中当前 Agent 且为属主",
    en: "Access Control",
    group: "当前 Agent",
    icon: "🔒",
    keywords: ["权限", "访问", "access", "permission", "acl"],
    enabled: (ctx) => ctx?.isCurrentAgentOwner === true,
    run: (ctx) => ctx.editCurrentAgentAccess && ctx.editCurrentAgentAccess(),
  },
  {
    id: "current-regenerate",
    label: "无损重生",
    shortcut: "Space a g",
    condition: "需选中当前 Agent 且为属主",
    en: "Regenerate",
    group: "当前 Agent",
    icon: "🔄",
    keywords: ["重生", "重建", "无损", "regenerate", "rebuild"],
    enabled: (ctx) => ctx?.isCurrentAgentOwner === true,
    run: (ctx) => ctx.regenerateCurrentAgent && ctx.regenerateCurrentAgent(),
  },
  {
    id: "current-delete",
    label: "删除",
    shortcut: "Space a z",
    condition: "需选中当前 Agent",
    en: "Delete",
    group: "当前 Agent",
    icon: "🗑",
    keywords: ["删除", "移除", "delete", "remove"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.deleteCurrentAgent && ctx.deleteCurrentAgent(),
  },
  {
    id: "current-toggle-output",
    label: "隐藏输出",
    shortcut: "Space a o",
    condition: "需选中当前 Agent",
    en: "Toggle Output",
    group: "当前 Agent",
    icon: "🙈",
    keywords: [
      "隐藏输出",
      "显示输出",
      "输出",
      "output",
      "hide",
      "show",
      "toggle",
    ],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) =>
      ctx.toggleCurrentAgentOutput && ctx.toggleCurrentAgentOutput(),
  },
  {
    id: "editor-send-selection-to-agent",
    label: "让 Agent 分析选中代码",
    shortcut: "Space v d",
    condition: "需在编辑器中选中代码",
    en: "Send Selection to Agent",
    group: "当前 Agent",
    icon: "🤖",
    keywords: ["分析", "选中", "selection", "agent", "解释", "代码"],
    enabled: (ctx) => !!ctx?.currentAgentId && !!ctx?.getEditorSelection,
    run: (ctx) => ctx.sendSelectionToAgent && ctx.sendSelectionToAgent(),
  },
  {
    id: "interrupt-current",
    label: "中断当前 Agent",
    shortcut: "Space a k",
    condition: "需选中当前 Agent",
    en: "Interrupt Current Agent",
    group: "执行",
    icon: "⏹",
    keywords: ["中断", "停止", "interrupt", "stop", "cancel"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.petInterruptCurrent && ctx.petInterruptCurrent(),
  },
  {
    id: "goto-waiting",
    label: "奔赴等待输入的 Agent",
    shortcut: "Space a w",
    condition: "需存在等待输入的 Agent",
    en: "Go to Waiting Agent",
    group: "执行",
    icon: "🚨",
    keywords: ["等待", "输入", "切换", "waiting", "input", "goto"],
    enabled: (ctx) => {
      const list = ctx?.waitingAgents ?? ctx?.agentList ?? [];
      return Array.isArray(list) ? list.length > 0 : false;
    },
    run: (ctx) => ctx.petGotoWaitingAgent && ctx.petGotoWaitingAgent(),
  },
  {
    id: "sync-status",
    label: "同步 Agent 状态",
    shortcut: "Space a y",
    condition: "无特殊条件（全局可用）",
    en: "Sync Agent Status",
    group: "执行",
    icon: "🔄",
    keywords: ["同步", "刷新", "状态", "sync", "refresh", "status"],
    run: (ctx) => ctx.syncAllStatus && ctx.syncAllStatus(),
  },
  {
    id: "create-agent",
    label: "新建 Agent",
    shortcut: "Space n a / Ctrl+N",
    condition: "已登录且不在输入框内",
    en: "New Agent",
    group: "Agent",
    icon: "➕",
    keywords: ["新建", "创建", "agent", "create", "add"],
    run: (ctx) => ctx.openCreateAgentModal && ctx.openCreateAgentModal(),
  },
  {
    id: "quick-create-agent",
    label: "一句话创建 Agent",
    shortcut: "Space n q",
    condition: "已登录",
    en: "Quick Create Agent",
    group: "Agent",
    icon: "⚡",
    keywords: [
      "一句话",
      "快速",
      "创建",
      "agent",
      "quick",
      "create",
      "task",
      "任务",
    ],
    run: (ctx) => ctx.openQuickCreateAgent && ctx.openQuickCreateAgent(),
  },
  {
    id: "refresh-agents",
    label: "刷新 Agent 列表",
    shortcut: "Space a f",
    condition: "已登录",
    en: "Refresh Agent List",
    group: "Agent",
    icon: "🔃",
    keywords: ["刷新", "列表", "refresh", "agents", "list"],
    run: (ctx) => ctx.refreshAgentList && ctx.refreshAgentList(),
  },
  {
    id: "restart-gateway",
    label: "重启网关",
    shortcut: "Space m q",
    condition: "需 admin:config 权限",
    en: "Restart Gateway",
    group: "网关",
    icon: "♻",
    keywords: ["重启", "网关", "restart", "gateway"],
    enabled: (ctx) => !!ctx?.hasPermission && ctx.hasPermission("admin:config"),
    run: (ctx) => ctx.restartGateway && ctx.restartGateway(),
  },
  {
    id: "restart-all-nodes",
    label: "重启所有节点",
    shortcut: "Space m r",
    condition: "需 admin:config 权限",
    en: "Restart All Nodes",
    group: "网关",
    icon: "🔁",
    keywords: ["重启", "节点", "全部", "restart", "nodes", "all"],
    enabled: (ctx) => !!ctx?.hasPermission && ctx.hasPermission("admin:config"),
    run: (ctx) => ctx.confirmRestartAllNodes && ctx.confirmRestartAllNodes(),
  },
  {
    id: "manage-groups",
    label: "管理分组",
    shortcut: "Space m g",
    condition: "已登录",
    en: "Manage Groups",
    group: "界面",
    icon: "📁",
    keywords: ["分组", "管理", "重命名", "删除", "group", "manage"],
    run: (ctx) => ctx.manageGroups && ctx.manageGroups(),
  },
  {
    id: "toggle-terminal",
    label: "切换终端面板",
    shortcut: "Space v t / Ctrl+`",
    condition: "不在输入框内",
    en: "Toggle Terminal Panel",
    group: "界面",
    icon: "🖥",
    keywords: ["终端", "terminal", "toggle"],
    run: (ctx) => ctx.toggleTerminalPanel && ctx.toggleTerminalPanel(),
  },
  {
    id: "toggle-chat",
    label: "切换聊天面板",
    shortcut: "Space v c",
    condition: "已登录",
    en: "Toggle Chat Panel",
    group: "界面",
    icon: "💬",
    keywords: ["聊天", "群聊", "chat", "toggle"],
    run: (ctx) => ctx.toggleChatPanel && ctx.toggleChatPanel(),
  },
  {
    id: "open-topology",
    label: "查看网络拓扑",
    shortcut: "Space v u",
    condition: "已登录",
    en: "View Network Topology",
    group: "界面",
    icon: "🗺",
    keywords: ["拓扑", "网络", "节点", "topology", "network", "nodes"],
    run: (ctx) => ctx.openTopology && ctx.openTopology(),
  },
  {
    id: "open-settings",
    label: "打开设置",
    shortcut: "Space v s",
    condition: "已登录",
    en: "Open Settings",
    group: "界面",
    icon: "⚙",
    keywords: ["设置", "配置", "settings", "config", "preferences"],
    run: (ctx) => ctx.openSettings && ctx.openSettings(),
  },
  {
    id: "toggle-pet",
    label: "隐藏/显示宠物",
    shortcut: "Space v o",
    condition: "已登录",
    en: "Toggle Pet",
    group: "界面",
    icon: "🐾",
    keywords: ["宠物", "挂件", "隐藏", "显示", "pet", "hide", "show", "toggle"],
    run: (ctx) => ctx.togglePetVisibility && ctx.togglePetVisibility(),
  },
  {
    id: "open-agent-list",
    label: "Agent 列表",
    shortcut: "Space v l / Ctrl+A",
    condition: "已登录",
    en: "Agent List",
    group: "界面",
    icon: "📋",
    keywords: ["agent", "列表", "list", "切换", "switch", "选择"],
    run: (ctx) => ctx.openAgentList && ctx.openAgentList(),
  },
  {
    // 侧边活动栏「Agent 列表」视图：打开工作区并切换到 agents 侧边栏视图
    id: "open-workspace-agent-list",
    label: "工作区 Agent 列表",
    shortcut: "Space v a",
    condition: "已登录",
    en: "Workspace Agent List",
    group: "界面",
    icon: "📋",
    keywords: [
      "agent",
      "列表",
      "工作区",
      "侧边栏",
      "workspace",
      "list",
      "sidebar",
    ],
    run: (ctx) => ctx.openWorkspaceAgentList && ctx.openWorkspaceAgentList(),
  },
  {
    // 命令面板文件搜索：打开命令面板并预输入 f>，直接进入文件搜索（对应 Ctrl+F）
    id: "open-command-palette-file-search",
    label: "文件搜索",
    shortcut: "Space v f / Ctrl+F",
    condition: "已登录",
    en: "File Search",
    group: "界面",
    icon: "🔎",
    keywords: ["文件", "搜索", "file", "search", "find", "命令面板"],
    run: (ctx) =>
      ctx.openCommandPaletteFileSearch && ctx.openCommandPaletteFileSearch(),
  },
  {
    // 侧边活动栏「Git」视图：打开工作区并切换到 Git 侧边栏视图
    id: "open-workspace-git",
    label: "Git 视图",
    shortcut: "Space v g",
    condition: "已登录",
    en: "Git View",
    group: "界面",
    icon: "🔀",
    keywords: ["git", "提交", "分支", "版本", "commit", "branch", "version"],
    run: (ctx) => ctx.openWorkspaceGit && ctx.openWorkspaceGit(),
  },
  {
    id: "open-onboarding",
    label: "查看 Jarvis 介绍",
    condition: "已登录",
    en: "About Jarvis",
    group: "界面",
    icon: "🎓",
    keywords: [
      "新手",
      "引导",
      "教程",
      "入门",
      "介绍",
      "帮助",
      "onboarding",
      "tour",
      "guide",
      "help",
      "about",
    ],
    run: (ctx) => ctx.startOnboarding && ctx.startOnboarding("welcome"),
  },
  {
    id: "open-docs",
    label: "打开使用文档",
    shortcut: "Space m h",
    condition: "已登录",
    en: "Open Documentation",
    group: "界面",
    icon: "📖",
    keywords: [
      "文档",
      "手册",
      "帮助",
      "使用",
      "教程",
      "docs",
      "documentation",
      "manual",
      "help",
      "guide",
    ],
    run: (ctx) => ctx.openDocs && ctx.openDocs(),
  },
  {
    id: "open-sidebar-onboarding",
    label: "查看侧边栏引导",
    condition: "已登录",
    en: "Sidebar Guide",
    group: "界面",
    icon: "📋",
    keywords: [
      "侧边栏",
      "引导",
      "教程",
      "新手",
      "agent 列表",
      "onboarding",
      "sidebar",
      "tour",
      "guide",
    ],
    run: (ctx) => ctx.startOnboarding && ctx.startOnboarding("sidebar"),
  },
  {
    id: "reset-onboarding",
    label: "重置新手引导",
    condition: "已登录",
    en: "Reset Onboarding",
    group: "界面",
    icon: "♻️",
    keywords: [
      "新手",
      "引导",
      "重置",
      "清除",
      "重新",
      "教程",
      "onboarding",
      "reset",
      "clear",
      "tour",
    ],
    run: (ctx) => ctx.resetOnboarding && ctx.resetOnboarding(),
  },
  {
    id: "install-browser-extension",
    label: "安装浏览器插件",
    condition: "已登录",
    en: "Install Browser Extension",
    group: "界面",
    icon: "🧩",
    keywords: [
      "插件",
      "扩展",
      "浏览器",
      "安装",
      "extension",
      "browser",
      "install",
      "plugin",
    ],
    run: (ctx) => ctx.openInstallExtension && ctx.openInstallExtension(),
  },
  {
    id: "install-daemon",
    label: "安装本地后台服务",
    condition: "已登录",
    en: "Install Local Daemon",
    group: "界面",
    icon: "🖥",
    keywords: [
      "后台",
      "服务",
      "本地",
      "守护",
      "进程",
      "安装",
      "daemon",
      "service",
      "local",
      "install",
    ],
    run: (ctx) => ctx.openDaemonInstall && ctx.openDaemonInstall(),
  },
  // ===== 账号 =====
  {
    id: "logout",
    label: "退出登录",
    condition: "已登录",
    en: "Log Out",
    group: "账号",
    icon: "🚪",
    keywords: [
      "退出",
      "登出",
      "注销",
      "断开",
      "logout",
      "signout",
      "disconnect",
      "account",
    ],
    run: (ctx) => ctx.logout && ctx.logout(),
  },
  // ===== 管理（需 admin 权限）=====
  {
    id: "admin-update-code-to-main",
    label: "更新代码到 main 分支",
    condition: "需 admin:config 权限",
    en: "Update Code to main",
    group: "管理",
    icon: "⬆",
    keywords: ["更新", "代码", "main", "拉取", "update", "code", "pull"],
    enabled: (ctx) => !!ctx?.hasPermission && ctx.hasPermission("admin:config"),
    run: (ctx) => ctx.confirmUpdateCodeToMain && ctx.confirmUpdateCodeToMain(),
  },
  {
    id: "admin-restart-node-service",
    label: "重启节点服务",
    condition: "需 admin:config 权限",
    en: "Restart Node Service",
    group: "管理",
    icon: "♻",
    keywords: ["重启", "节点", "服务", "restart", "node", "service"],
    enabled: (ctx) => !!ctx?.hasPermission && ctx.hasPermission("admin:config"),
    run: (ctx) => ctx.openAdminRestartService && ctx.openAdminRestartService(),
  },
  {
    id: "admin-sync-config",
    label: "同步配置到其他节点",
    condition: "需 admin:config 权限",
    en: "Sync Config to Nodes",
    group: "管理",
    icon: "🔃",
    keywords: ["同步", "配置", "节点", "sync", "config"],
    enabled: (ctx) => !!ctx?.hasPermission && ctx.hasPermission("admin:config"),
    run: (ctx) => ctx.openAdminSyncConfig && ctx.openAdminSyncConfig(),
  },
  {
    id: "admin-node-secret",
    label: "查看节点连接私钥",
    condition: "需 admin:config 权限",
    en: "View Node Secret",
    group: "管理",
    icon: "🔑",
    keywords: ["私钥", "密钥", "节点", "secret", "key", "node"],
    enabled: (ctx) => !!ctx?.hasPermission && ctx.hasPermission("admin:config"),
    run: (ctx) => ctx.openAdminNodeSecret && ctx.openAdminNodeSecret(),
  },
  {
    id: "admin-edit-config",
    label: "编辑配置文件",
    condition: "需 admin:config 权限",
    en: "Edit Config File",
    group: "管理",
    icon: "⚙",
    keywords: ["配置", "文件", "模型", "模型组", "config", "edit", "llm"],
    enabled: (ctx) => !!ctx?.hasPermission && ctx.hasPermission("admin:config"),
    run: (ctx) => ctx.openAdminConfigFile && ctx.openAdminConfigFile(),
  },
  {
    id: "admin-open-panel",
    label: "打开管理面板",
    shortcut: "Space m a",
    condition: "需 admin 权限（config/users/permissions 任一）",
    en: "Open Admin Panel",
    group: "管理",
    icon: "🛠",
    keywords: ["管理", "面板", "admin", "panel", "用户", "权限"],
    enabled: (ctx) =>
      !!ctx?.hasPermission &&
      (ctx.hasPermission("admin:config") ||
        ctx.hasPermission("admin:users") ||
        ctx.hasPermission("admin:permissions")),
    run: (ctx) => ctx.openAdminPanel && ctx.openAdminPanel(),
  },
  {
    // 打开工作区并切换到「插件管理」侧边栏视图（侧边活动栏「插件」按钮）
    id: "open-workspace-plugins",
    label: "插件管理",
    shortcut: "Space m p",
    condition: "需 admin:plugins 权限",
    en: "Plugin Management",
    group: "管理",
    icon: "🧩",
    keywords: ["插件", "plugin", "管理", "plugins", "扩展"],
    enabled: (ctx) =>
      !!ctx?.hasPermission && ctx.hasPermission("admin:plugins"),
    run: (ctx) => ctx.openWorkspacePlugins && ctx.openWorkspacePlugins(),
  },
  // ===== 节点（作用于大厅中选中的节点）=====
  {
    id: "node-create-agent",
    label: "在选中节点创建 Agent",
    condition: "大厅中已选中节点",
    en: "Create Agent on Node",
    group: "节点",
    icon: "➕",
    keywords: ["节点", "创建", "agent", "node", "create"],
    enabled: (ctx) => !!ctx?.currentNodeId,
    run: (ctx) =>
      ctx.createAgentOnNode && ctx.createAgentOnNode(ctx.currentNodeId),
  },
  {
    id: "node-open-terminal",
    label: "打开选中节点终端",
    condition: "大厅中已选中节点",
    en: "Open Node Terminal",
    group: "节点",
    icon: "⌨️",
    keywords: ["节点", "终端", "terminal", "node", "shell"],
    enabled: (ctx) => !!ctx?.currentNodeId,
    run: (ctx) =>
      ctx.openTerminalOnNode && ctx.openTerminalOnNode(ctx.currentNodeId),
  },
  {
    id: "node-update-code",
    label: "更新选中节点代码",
    condition: "大厅中已选中节点",
    en: "Update Node Code",
    group: "节点",
    icon: "🔄",
    keywords: ["节点", "更新", "代码", "node", "update", "code", "pull"],
    enabled: (ctx) => !!ctx?.currentNodeId,
    run: (ctx) => ctx.updateNodeCode && ctx.updateNodeCode(ctx.currentNodeId),
  },
  {
    id: "node-restart-service",
    label: "重启选中节点服务",
    condition: "大厅中已选中节点",
    en: "Restart Node Service",
    group: "节点",
    icon: "♻️",
    keywords: ["节点", "重启", "服务", "node", "restart", "service"],
    enabled: (ctx) => !!ctx?.currentNodeId,
    run: (ctx) =>
      ctx.restartNodeService && ctx.restartNodeService(ctx.currentNodeId),
  },
  {
    // 与「当前 Agent」组 current-rename 共用 F2：两者通过 shortcutScope 区分场景，
    // 有当前 Agent 时优先重命名 Agent，无当前 Agent 时才执行本动作（见 App.vue 的 F2 分支）
    id: "node-rename",
    label: "重命名选中节点",
    shortcut: "F2",
    shortcutScope: "node",
    condition: "大厅中已选中节点；与 Agent 重命名共用 F2 时以 Agent 优先",
    en: "Rename Node",
    group: "节点",
    icon: "✏️",
    keywords: ["节点", "重命名", "改名", "node", "rename"],
    enabled: (ctx) => !!ctx?.currentNodeId,
    run: (ctx) => ctx.renameNode && ctx.renameNode(ctx.currentNodeId),
    // 重命名需在大厅内弹输入框，命令面板需先关闭让出焦点
    closePaletteOnRun: true,
  },
  // ===== 大厅方向选中（Ctrl+Alt+方向键）=====
  // 与 App.vue 中既有的「区域焦点跳转」共用同一物理键：大厅有宠物时优先选中宠物，
  // 无宠物时回退为区域跳转（见 App.vue 的 Ctrl+Alt+方向键分支）。
  // 这四个动作仅用于命令面板/快捷键一览的展示与执行，不参与 handleGlobalKeydown 的
  // registry 统一分发（该分发要求 ctrl+alt 且未被前面的分支消费，方向键分支已提前 return）。
  {
    id: "lobby-select-left",
    label: "选中左侧 Agent",
    shortcut: "Ctrl+Alt+ArrowLeft",
    condition: "宠物大厅中有 Agent",
    en: "Select Agent to the Left",
    group: "大厅",
    icon: "⬅️",
    keywords: ["大厅", "选中", "方向", "左", "lobby", "select", "left"],
    enabled: (ctx) => !!ctx?.hasLobbyAgents,
    run: (ctx) =>
      ctx.selectLobbyAgentInDirection &&
      ctx.selectLobbyAgentInDirection("left"),
  },
  {
    id: "lobby-select-right",
    label: "选中右侧 Agent",
    shortcut: "Ctrl+Alt+ArrowRight",
    condition: "宠物大厅中有 Agent",
    en: "Select Agent to the Right",
    group: "大厅",
    icon: "➡️",
    keywords: ["大厅", "选中", "方向", "右", "lobby", "select", "right"],
    enabled: (ctx) => !!ctx?.hasLobbyAgents,
    run: (ctx) =>
      ctx.selectLobbyAgentInDirection &&
      ctx.selectLobbyAgentInDirection("right"),
  },
  {
    id: "lobby-select-up",
    label: "选中上方 Agent",
    shortcut: "Ctrl+Alt+ArrowUp",
    condition: "宠物大厅中有 Agent",
    en: "Select Agent Above",
    group: "大厅",
    icon: "⬆️",
    keywords: ["大厅", "选中", "方向", "上", "lobby", "select", "up"],
    enabled: (ctx) => !!ctx?.hasLobbyAgents,
    run: (ctx) =>
      ctx.selectLobbyAgentInDirection && ctx.selectLobbyAgentInDirection("up"),
  },
  {
    id: "lobby-select-down",
    label: "选中下方 Agent",
    shortcut: "Ctrl+Alt+ArrowDown",
    condition: "宠物大厅中有 Agent",
    en: "Select Agent Below",
    group: "大厅",
    icon: "⬇️",
    keywords: ["大厅", "选中", "方向", "下", "lobby", "select", "down"],
    enabled: (ctx) => !!ctx?.hasLobbyAgents,
    run: (ctx) =>
      ctx.selectLobbyAgentInDirection &&
      ctx.selectLobbyAgentInDirection("down"),
  },

  // ===== 大厅节点方向选中（Ctrl+Shift+方向键）=====
  // 与 Agent 方向选中（Ctrl+Alt+方向键）区分：Shift 作用于节点，Alt 作用于 Agent。
  // 同样仅用于命令面板/快捷键一览的展示与执行，不参与 handleGlobalKeydown 的统一分发。
  {
    id: "lobby-node-select-left",
    label: "选中左侧节点",
    shortcut: "Ctrl+Alt+Shift+ArrowLeft",
    condition: "宠物大厅中有节点",
    en: "Select Node to the Left",
    group: "大厅",
    icon: "⬅️",
    keywords: [
      "大厅",
      "节点",
      "选中",
      "方向",
      "左",
      "lobby",
      "node",
      "select",
      "left",
    ],
    enabled: (ctx) => !!ctx?.hasLobbyNodes,
    run: (ctx) =>
      ctx.selectLobbyNodeInDirection && ctx.selectLobbyNodeInDirection("left"),
  },
  {
    id: "lobby-node-select-right",
    label: "选中右侧节点",
    shortcut: "Ctrl+Alt+Shift+ArrowRight",
    condition: "宠物大厅中有节点",
    en: "Select Node to the Right",
    group: "大厅",
    icon: "➡️",
    keywords: [
      "大厅",
      "节点",
      "选中",
      "方向",
      "右",
      "lobby",
      "node",
      "select",
      "right",
    ],
    enabled: (ctx) => !!ctx?.hasLobbyNodes,
    run: (ctx) =>
      ctx.selectLobbyNodeInDirection && ctx.selectLobbyNodeInDirection("right"),
  },
  {
    id: "lobby-node-select-up",
    label: "选中上方节点",
    shortcut: "Ctrl+Alt+Shift+ArrowUp",
    condition: "宠物大厅中有节点",
    en: "Select Node Above",
    group: "大厅",
    icon: "⬆️",
    keywords: [
      "大厅",
      "节点",
      "选中",
      "方向",
      "上",
      "lobby",
      "node",
      "select",
      "up",
    ],
    enabled: (ctx) => !!ctx?.hasLobbyNodes,
    run: (ctx) =>
      ctx.selectLobbyNodeInDirection && ctx.selectLobbyNodeInDirection("up"),
  },
  {
    id: "lobby-node-select-down",
    label: "选中下方节点",
    shortcut: "Ctrl+Alt+Shift+ArrowDown",
    condition: "宠物大厅中有节点",
    en: "Select Node Below",
    group: "大厅",
    icon: "⬇️",
    keywords: [
      "大厅",
      "节点",
      "选中",
      "方向",
      "下",
      "lobby",
      "node",
      "select",
      "down",
    ],
    enabled: (ctx) => !!ctx?.hasLobbyNodes,
    run: (ctx) =>
      ctx.selectLobbyNodeInDirection && ctx.selectLobbyNodeInDirection("down"),
  },

  // ===== 大厅全部输出显隐（Ctrl+Alt+A）=====
  // 一键切换：全部隐藏 ↔ 全部显示。仅用于命令面板/快捷键一览的展示与执行，
  // 不参与 handleGlobalKeydown 的统一分发（由 App.vue 的 Ctrl+Alt+A 分支处理）。
  {
    id: "lobby-toggle-all-outputs",
    label: "隐藏/显示全部输出",
    shortcut: "Ctrl+Alt+A",
    condition: "宠物大厅中有 Agent",
    en: "Toggle All Outputs",
    group: "大厅",
    icon: "💬",
    keywords: [
      "大厅",
      "输出",
      "全部",
      "隐藏",
      "显示",
      "气泡",
      "lobby",
      "output",
      "toggle",
      "all",
    ],
    enabled: (ctx) => !!ctx?.hasLobbyAgentsForOutput,
    run: (ctx) => ctx.toggleAllLobbyOutputs && ctx.toggleAllLobbyOutputs(),
  },
];

// 大小写不敏感的子串 / 关键词模糊匹配；query 为空时返回全部
export function filterActions(actions, query) {
  const list = Array.isArray(actions) ? actions : [];
  const q = String(query ?? "")
    .trim()
    .toLowerCase();
  if (!q) return list.slice();
  return list.filter((action) => {
    const haystack = [
      action?.label,
      action?.en,
      action?.id,
      action?.group,
      ...(action?.keywords || []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}

// 按 group 聚合，保持组内原始顺序与组首次出现顺序
export function groupActions(actions) {
  const list = Array.isArray(actions) ? actions : [];
  const order = [];
  const buckets = new Map();
  for (const action of list) {
    const key = action?.group || "其他";
    if (!buckets.has(key)) {
      buckets.set(key, []);
      order.push(key);
    }
    buckets.get(key).push(action);
  }
  return order.map((group) => ({ group, actions: buckets.get(group) }));
}

// ===== 快捷键冲突自检 =====
// 同一个物理键在不同场景下复用是允许的，但必须能明确区分，否则 handleGlobalKeydown
// 用 actionDefs.find(...) 取首个匹配项时会产生歧义（后注册的动作永远不生效）。
// 约定：同键动作必须声明 shortcutScope，且 scope 互不相同；未声明 scope 视为 "global"。
// 例：F2 的 current-rename 为 "global"，node-rename 为 "node"（节点选中时优先）。
export function findShortcutConflicts(actions = ACTIONS) {
  const byShortcut = new Map();
  for (const action of Array.isArray(actions) ? actions : []) {
    if (!action?.shortcut) continue;
    const key = String(action.shortcut).trim().toLowerCase();
    if (!byShortcut.has(key)) byShortcut.set(key, []);
    byShortcut.get(key).push(action);
  }
  const conflicts = [];
  for (const [shortcut, list] of byShortcut) {
    if (list.length < 2) continue;
    const scopes = list.map((a) => a.shortcutScope || "global");
    const duplicated = scopes.filter((s, i) => scopes.indexOf(s) !== i);
    if (duplicated.length > 0) {
      conflicts.push({
        shortcut,
        reason: `shortcutScope 重复：${[...new Set(duplicated)].join(", ")}`,
        actions: list.map((a) => a.id),
      });
    }
  }
  return conflicts;
}

// 开发期自检：注册表出现无法区分的同键动作时在控制台告警（不阻断运行）
if (import.meta.env?.DEV) {
  const conflicts = findShortcutConflicts();
  if (conflicts.length > 0) {
    console.warn(
      "[shortcut] 检测到快捷键冲突（同键动作需声明互不相同的 shortcutScope）：",
      conflicts,
    );
  }
}

// ===== 空格 Leader 按键序列命令树 =====
// 整体重设计：用「空格 + 领域键 + 动作键」的两级按键序列替代大量 Ctrl+Alt(+Shift)+字母 组合键。
// 语义键一律用无修饰键的单字母，绝对不被系统/浏览器拦截（用户环境 Ctrl+Alt+Shift 被系统软件拦截）。
// 结构：{ [领域键]: { label, children: { [动作键]: { label, actionId } } } }
// 叶子节点通过 actionId 引用上方 ACTIONS 中的动作；App.vue 命中叶子后执行 onCommandRun(对应 action)。
export const SPACE_COMMANDS = {
  p: {
    label: "面板 Panel",
    children: {
      x: { label: "关闭当前面板", actionId: "close-focused-panel" },
      s: { label: "左右分割", actionId: "split-workspace-pane-row" },
      h: { label: "上下分割", actionId: "split-workspace-pane-column" },
    },
  },
  a: {
    label: "Agent",
    children: {
      d: { label: "查看变更", actionId: "current-view-diff" },
      r: { label: "查看规则", actionId: "current-view-rules" },
      t: { label: "查看工具", actionId: "current-view-tools" },
      i: { label: "人工介入", actionId: "current-manual-interrupt" },
      k: { label: "中断", actionId: "interrupt-current" },
      o: { label: "隐藏/显示输出", actionId: "current-toggle-output" },
      v: { label: "自动朗读", actionId: "current-toggle-auto-read" },
      s: { label: "自动滚动", actionId: "current-toggle-auto-scroll" },
      c: { label: "复制", actionId: "current-copy" },
      e: { label: "权限管理", actionId: "current-edit-access" },
      g: { label: "无损重生", actionId: "current-regenerate" },
      x: { label: "退出非交互", actionId: "current-exit-non-interactive" },
      n: { label: "重命名", actionId: "current-rename" },
      y: { label: "同步状态", actionId: "sync-status" },
      f: { label: "刷新 Agent 列表", actionId: "refresh-agents" },
      w: { label: "奔赴等待输入", actionId: "goto-waiting" },
      z: { label: "删除当前 Agent", actionId: "current-delete" },
    },
  },
  v: {
    label: "视图 View",
    children: {
      a: { label: "Agent 列表", actionId: "open-workspace-agent-list" },
      g: { label: "Git 视图", actionId: "open-workspace-git" },
      e: { label: "工作区", actionId: "open-editor" },
      t: { label: "终端", actionId: "toggle-terminal" },
      c: { label: "聊天", actionId: "toggle-chat" },
      s: { label: "设置", actionId: "open-settings" },
      u: { label: "网络拓扑", actionId: "open-topology" },
      p: { label: "命令面板", actionId: "open-command-palette" },
      l: { label: "Agent 列表(命令面板)", actionId: "open-agent-list" },
      f: { label: "文件搜索", actionId: "open-command-palette-file-search" },
      r: { label: "目录树", actionId: "open-editor-file-tree" },
      b: { label: "内容搜索", actionId: "open-editor-global-search" },
      n: { label: "文件名搜索", actionId: "open-editor-file-search" },
      w: { label: "保存当前文件", actionId: "save-active-editor-tab" },
      d: {
        label: "让 Agent 分析选中代码",
        actionId: "editor-send-selection-to-agent",
      },
      o: { label: "隐藏/显示宠物", actionId: "toggle-pet" },
    },
  },
  n: {
    label: "新建 New",
    children: {
      a: { label: "新建 Agent", actionId: "create-agent" },
      q: { label: "一句话创建", actionId: "quick-create-agent" },
      t: { label: "创建终端", actionId: "current-create-terminal" },
    },
  },
  m: {
    label: "管理 Manage",
    children: {
      g: { label: "管理分组", actionId: "manage-groups" },
      a: { label: "管理面板", actionId: "admin-open-panel" },
      h: { label: "使用文档", actionId: "open-docs" },
      r: { label: "重启所有节点", actionId: "restart-all-nodes" },
      q: { label: "重启网关", actionId: "restart-gateway" },
      p: { label: "插件管理", actionId: "open-workspace-plugins" },
    },
  },
};

// 由 SPACE_COMMANDS 派生的「空格序列 → actionId」扁平映射（用于 App.vue 快速匹配与命令面板展示）
export const SPACE_COMMAND_ACTIONS = (() => {
  const map = {};
  for (const [gKey, group] of Object.entries(SPACE_COMMANDS)) {
    for (const [aKey, leaf] of Object.entries(group.children || {})) {
      map[`${gKey}${aKey}`] = leaf.actionId;
    }
  }
  return map;
})();

export default ACTIONS;
