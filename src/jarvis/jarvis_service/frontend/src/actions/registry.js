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
    en: "Create Terminal",
    group: "当前 Agent",
    icon: "💻",
    keywords: ["终端", "terminal", "创建", "create"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) =>
      ctx.createTerminalForCurrent && ctx.createTerminalForCurrent(),
  },
  {
    id: "current-open-editor",
    label: "打开编辑器",
    en: "Open Editor",
    group: "当前 Agent",
    icon: "📝",
    keywords: ["编辑器", "editor", "打开", "open"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.openEditorForCurrent && ctx.openEditorForCurrent(),
  },
  {
    id: "current-toggle-auto-scroll",
    label: "切换自动滚动",
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
    label: "人工介入（中断当前执行）",
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
    id: "current-detach-panel",
    label: "分离当前焦点面板",
    en: "Detach Focused Panel",
    group: "界面",
    icon: "⧉",
    keywords: ["分离", "浮动", "detach", "float", "panel", "焦点"],
    run: (ctx) => ctx.detachFocusedPanel && ctx.detachFocusedPanel(),
  },
  {
    id: "current-close-panel",
    label: "关闭当前焦点面板",
    en: "Close Focused Panel",
    group: "界面",
    icon: "✕",
    keywords: ["关闭", "面板", "close", "panel", "焦点"],
    run: (ctx) => ctx.closeFocusedPanel && ctx.closeFocusedPanel(),
  },
  {
    id: "interrupt-current",
    label: "中断当前 Agent",
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
    en: "Sync Agent Status",
    group: "执行",
    icon: "🔄",
    keywords: ["同步", "刷新", "状态", "sync", "refresh", "status"],
    run: (ctx) => ctx.syncAllStatus && ctx.syncAllStatus(),
  },
  {
    id: "create-agent",
    label: "新建 Agent",
    en: "New Agent",
    group: "Agent",
    icon: "➕",
    keywords: ["新建", "创建", "agent", "create", "add"],
    run: (ctx) => ctx.openCreateAgentModal && ctx.openCreateAgentModal(),
  },
  {
    id: "refresh-agents",
    label: "刷新 Agent 列表",
    en: "Refresh Agent List",
    group: "Agent",
    icon: "🔃",
    keywords: ["刷新", "列表", "refresh", "agents", "list"],
    run: (ctx) => ctx.refreshAgentList && ctx.refreshAgentList(),
  },
  {
    id: "restart-gateway",
    label: "重启网关",
    en: "Restart Gateway",
    group: "网关",
    icon: "♻",
    keywords: ["重启", "网关", "restart", "gateway"],
    run: (ctx) => ctx.restartGateway && ctx.restartGateway(),
  },
  {
    id: "restart-all-nodes",
    label: "重启所有节点",
    en: "Restart All Nodes",
    group: "网关",
    icon: "🔁",
    keywords: ["重启", "节点", "全部", "restart", "nodes", "all"],
    run: (ctx) => ctx.restartAllNodes && ctx.restartAllNodes(),
  },
  {
    id: "toggle-sidebar",
    label: "切换 Agent 侧边栏",
    en: "Toggle Agent Sidebar",
    group: "界面",
    icon: "📋",
    keywords: ["侧边栏", "侧栏", "sidebar", "toggle"],
    run: (ctx) => ctx.toggleAgentSidebar && ctx.toggleAgentSidebar(),
  },
  {
    id: "toggle-terminal",
    label: "切换终端面板",
    en: "Toggle Terminal Panel",
    group: "界面",
    icon: "🖥",
    keywords: ["终端", "terminal", "toggle"],
    run: (ctx) => ctx.toggleTerminalPanel && ctx.toggleTerminalPanel(),
  },
  {
    id: "toggle-chat",
    label: "切换聊天面板",
    en: "Toggle Chat Panel",
    group: "界面",
    icon: "💬",
    keywords: ["聊天", "群聊", "chat", "toggle"],
    run: (ctx) => ctx.toggleChatPanel && ctx.toggleChatPanel(),
  },
  {
    id: "open-topology",
    label: "查看网络拓扑",
    en: "View Network Topology",
    group: "界面",
    icon: "🗺",
    keywords: ["拓扑", "网络", "节点", "topology", "network", "nodes"],
    run: (ctx) => ctx.openTopology && ctx.openTopology(),
  },
  {
    id: "open-settings",
    label: "打开设置",
    en: "Open Settings",
    group: "界面",
    icon: "⚙",
    keywords: ["设置", "配置", "settings", "config", "preferences"],
    run: (ctx) => ctx.openSettings && ctx.openSettings(),
  },
  {
    id: "toggle-pet",
    label: "隐藏/显示宠物",
    en: "Toggle Pet",
    group: "界面",
    icon: "🐾",
    keywords: ["宠物", "挂件", "隐藏", "显示", "pet", "hide", "show", "toggle"],
    run: (ctx) => ctx.togglePetVisibility && ctx.togglePetVisibility(),
  },
  {
    id: "open-agent-list",
    label: "Agent 列表",
    en: "Agent List",
    group: "界面",
    icon: "📋",
    keywords: ["agent", "列表", "list", "切换", "switch", "选择"],
    run: (ctx) => ctx.openAgentList && ctx.openAgentList(),
  },
  // ===== 标题栏 =====
  {
    id: "toggle-header",
    label: "显示/隐藏标题栏",
    en: "Toggle Header Bar",
    group: "标题栏",
    icon: "▤",
    keywords: [
      "标题栏",
      "顶栏",
      "顶部",
      "header",
      "titlebar",
      "topbar",
      "toggle",
    ],
    run: (ctx) => ctx.toggleHeader && ctx.toggleHeader(),
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

export default ACTIONS;
