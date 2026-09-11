// 统一动作注册表（单一数据源）
// 宠物菜单、命令面板、快捷键均从这里派生动作清单。
// 纯模块：不依赖 Vue，不直接引用 App.vue，所有副作用通过调用方传入的 ctx 回调触发。
//
// 动作对象结构：
// {
//   id: string,
//   label: string,
//   group: string,
//   icon: string,
//   keywords: string[],
//   shortcut?: string,
//   enabled?: (ctx) => boolean,
//   run: (ctx) => void | Promise<void>
// }

export const ACTIONS = [
  {
    id: "interrupt-current",
    label: "中断当前 Agent",
    group: "执行",
    icon: "⏹",
    keywords: ["中断", "停止", "interrupt", "stop", "cancel"],
    enabled: (ctx) => !!ctx?.currentAgentId,
    run: (ctx) => ctx.petInterruptCurrent && ctx.petInterruptCurrent(),
  },
  {
    id: "goto-waiting",
    label: "奔赴等待输入的 Agent",
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
    group: "执行",
    icon: "🔄",
    keywords: ["同步", "刷新", "状态", "sync", "refresh", "status"],
    run: (ctx) => ctx.syncAllStatus && ctx.syncAllStatus(),
  },
  {
    id: "create-agent",
    label: "新建 Agent",
    group: "Agent",
    icon: "➕",
    keywords: ["新建", "创建", "agent", "create", "add"],
    run: (ctx) => ctx.openCreateAgentModal && ctx.openCreateAgentModal(),
  },
  {
    id: "refresh-agents",
    label: "刷新 Agent 列表",
    group: "Agent",
    icon: "🔃",
    keywords: ["刷新", "列表", "refresh", "agents", "list"],
    run: (ctx) => ctx.refreshAgentList && ctx.refreshAgentList(),
  },
  {
    id: "restart-gateway",
    label: "重启网关",
    group: "网关",
    icon: "♻",
    keywords: ["重启", "网关", "restart", "gateway"],
    run: (ctx) => ctx.restartGateway && ctx.restartGateway(),
  },
  {
    id: "restart-all-nodes",
    label: "重启所有节点",
    group: "网关",
    icon: "🔁",
    keywords: ["重启", "节点", "全部", "restart", "nodes", "all"],
    run: (ctx) => ctx.restartAllNodes && ctx.restartAllNodes(),
  },
  {
    id: "toggle-sidebar",
    label: "切换 Agent 侧边栏",
    group: "界面",
    icon: "📋",
    keywords: ["侧边栏", "侧栏", "sidebar", "toggle"],
    run: (ctx) => ctx.toggleAgentSidebar && ctx.toggleAgentSidebar(),
  },
  {
    id: "toggle-terminal",
    label: "切换终端面板",
    group: "界面",
    icon: "🖥",
    keywords: ["终端", "terminal", "toggle"],
    run: (ctx) => ctx.toggleTerminalPanel && ctx.toggleTerminalPanel(),
  },
  {
    id: "toggle-chat",
    label: "切换聊天面板",
    group: "界面",
    icon: "💬",
    keywords: ["聊天", "群聊", "chat", "toggle"],
    run: (ctx) => ctx.toggleChatPanel && ctx.toggleChatPanel(),
  },
  {
    id: "open-topology",
    label: "查看网络拓扑",
    group: "界面",
    icon: "🗺",
    keywords: ["拓扑", "网络", "节点", "topology", "network", "nodes"],
    run: (ctx) => ctx.openTopology && ctx.openTopology(),
  },
  {
    id: "open-settings",
    label: "打开设置",
    group: "界面",
    icon: "⚙",
    keywords: ["设置", "配置", "settings", "config", "preferences"],
    run: (ctx) => ctx.openSettings && ctx.openSettings(),
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
