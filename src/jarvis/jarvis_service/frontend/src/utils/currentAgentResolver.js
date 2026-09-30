// 「当前 Agent」解析：命令面板 / 右键菜单的「当前 Agent」组动作，统一用它定位作用对象。
//
// 优先级（自上而下，命中即返回）：
//   1) contextMenuAgentId —— 右键菜单锁定的 Agent（侧边栏 / Panel 右键）。
//      必须在最前，且**不依赖菜单是否可见**：菜单项被点击时菜单会先收起，
//      若把「菜单可见」作为条件，锁定就会失效并回退到当前活动 Agent，
//      导致删除/重命名等操作作用到错误的 Agent。
//   2) 宠物大厅（无嵌入面板）中选中的宠物对应的 Agent；
//   3) 当前激活 Panel 内的 Agent；
//   4) 大厅选中宠物（兜底）；
//   5) currentAgentId（最终兜底）。
//
// 抽为纯函数便于单测：入参是各状态的快照，出参是解析出的 agentId（无则 null）。

/**
 * 解析「当前 Agent」的 ID。
 * @param {object} state
 * @param {string|null} [state.contextMenuAgentId] 右键菜单锁定的 Agent ID
 * @param {string|null} [state.lobbyActiveAgentId] 宠物大厅选中的 Agent ID
 * @param {boolean} [state.hasNoPanel] 是否无任何嵌入面板（纯大厅态）
 * @param {string|null} [state.activePanelAgentId] 当前激活 Panel 内的 Agent ID
 * @param {string|null} [state.currentAgentId] 当前 Agent（最终兜底）
 * @returns {string|null}
 */
export function resolveCurrentAgentId(state = {}) {
  const {
    contextMenuAgentId,
    lobbyActiveAgentId,
    hasNoPanel,
    activePanelAgentId,
    currentAgentId,
  } = state;

  // 1) 右键菜单锁定优先（不依赖菜单可见性）
  if (contextMenuAgentId) return contextMenuAgentId;
  // 2) 纯大厅态：以大厅选中的宠物为准
  if (hasNoPanel && lobbyActiveAgentId) return lobbyActiveAgentId;
  // 3) 当前激活 Panel 内的 Agent
  if (activePanelAgentId) return activePanelAgentId;
  // 4) 大厅选中宠物（兜底）
  if (lobbyActiveAgentId) return lobbyActiveAgentId;
  // 5) 最终兜底
  return currentAgentId || null;
}
