// Agent 管理 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 9），保持行为完全一致：
// - 状态文本/状态类：getStatusText / getStatusClass / isWaitingInput / fetchAgentStatus / syncOnlineAgentStatuses
// - 目录选择：dirDialogContext / openDirDialog / fetchDirectories / selectDirectory / confirmDirectory / cancelDirDialog
// - 创建 Agent：openCreateAgentModal / createAgentWithOptions / afterAgentCreated / createAgent / 一句话创建
// - 补全：openCompletions / insertCompletion / 键盘导航
// - 列表/增删改：fetchAgentList / copyAgent / 分组管理 / renameAgent / deleteAgent / regenerateAgent / switchAgent
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - 早期 ref（App.vue 顶层创建）：agentList / currentAgentId / agentStatuses / isStoppedAgent / currentAgent /
//   agentGroups / selectedAgents / isBatchMode / inputText / inputMode / inputRequests / inputTip /
//   panelInputTexts / panelInputModes / panelInputTips / panelConfirmData / pendingInputAgentId /
//   pendingConfirmAgentId / inputBuffers / allOutputs / outputs / outputList / panelOutputLists /
//   panels / sessionPanelRefs / showToast / showConfirm / showSettingsModal / showWorkspacePanel /
//   activeWorkspaceSession / hasNoPanel / isAutoFocusSuppressed / isAnyModalOpen / socket / sockets /
//   auth / username / getHttpProtocol / buildNodeHttpUrl / getGatewayAddress / fetchWithAuth /
//   escapeHtml / historyStorage / loadHistoryMessages / sendMessageToAgent / setupHistoryScrollListener /
//   openAgentInPanel / closePanel / closeAgentInPanel / closeOpenDirDialog / confirmOpenDir /
//   restoreWorkspacePaneContents / saveRecentWorkDir / loadRecentWorkDirs / filteredDirList /
//   sortCompletionItems / recordCompletionSelection / switchGeneration / windowWidth / workspaceAutoOpened /
//   agentListLoaded / setModalAutoFocusSuppressUntil / MODAL_AUTOFOCUS_SUPPRESS_MS / hasMoreHistory /
//   historyOffset / showCompletions / completionCursorPos / completionHasAtSymbol / completionAgentId /
//   completionSource / petLobbyRef / completions / completionSearch / fileCompletions /
//   completionSearchInput / completionsModalRef / selectedIndex / showCreateAgentModal /
//   showQuickCreateAgentModal / quickCreateAgentLoading / quickCreateAgentError / showRenameAgentModal /
//   renamingAgent / renameAgentName / showDirDialog / currentDirPath / dirList / selectedDir /
//   dirSearchText / dirSearchInput / selectedDirIndex / recentWorkDirs / renameInput / showOpenDirDialog /
//   openDirNodeId / openDirPath / openDirInput / openDirDialogRef / openDirSource / pluginPickDirResolver /
//   gitCustomDir / newAgentType / newAgentDir / newAgentName / modelGroups / newAgentModelGroup /
//   newCodeAgentWorktree / newAgentQuickMode / newAgentRestoreSession / newAgentNoInteractionMode /
//   newAgentTaskDescription / newAgentCreateError / newAgentProxyNode / newAgentAccessAclRead /
//   newAgentAccessAclInteract / availableUserOptions / filteredUserOptionsForAcl / availableNodeOptions /
//   userAccessibleNodes / userPermissions / nodeDisplayNames / getNodeDisplayName / newAgentNodeId /
//   filteredNodeOptionsForCreateAgent / getDefaultCreateAgentNodeId / generateAgentName / skipNameWatch /
//   showToolsModal / toolsContent / toolsLoading / showEditAccessModal / editingAccessAgent /
//   editAccessRead / editAccessInteract / rulesLoading / showRulesModal / rulesContent /
//   rulesLoadedContent / selectedTerminalNodeId
//
// - composable 返回（直接传引用，调用点在 useAgents 之前）：
//   chatName（useChat）/ saveToHistory / lobbyHistoryIndex / lobbyHistoryTemp（useInputHistory）/
//   maybeStartTour（useTour）/ fileTreeState / fileTreeExpanded / fileTreeLoading（useFileTree）
//
// - getter 注入（调用点在 useAgents 之后，函数执行时才求值）：
//   orchestrateAgents / orchestrateActiveIndex / orchestrateNodeId（useOrchestrate 返回）/
//   terminals / terminalHosts / disposeExecutionTerminal（useTerminal 返回）/
//   connectToAgent / autoConnectToOnlineAgents（useGatewayConnection 返回）/
//   renderMessageHtml / appendOutput / sendInputDirectly / sendBufferedInput / sendConfirmResult /
//   restoreWaitingConfirmUI / pushOverlayState（App.vue 晚期定义函数）
//
// 注意：域内 ref（dirDialogContext / showToolsModal / toolsContent / toolsLoading / showEditAccessModal /
// editingAccessAgent / editAccessRead / editAccessInteract）由本 composable 创建并返回，
// App.vue 解构后共享（isAnyModalOpen / template 等读取）。
import { ref, computed, watch, nextTick } from 'vue'

export function useAgents({
  // 早期 ref（直接传引用）
  agentList,
  currentAgentId,
  agentStatuses,
  isStoppedAgent,
  currentAgent,
  agentGroups,
  selectedAgents,
  isBatchMode,
  inputText,
  inputMode,
  inputRequests,
  inputTip,
  panelInputTexts,
  panelInputModes,
  panelInputTips,
  panelConfirmData,
  pendingInputAgentId,
  pendingConfirmAgentId,
  inputBuffers,
  allOutputs,
  outputs,
  outputList,
  panelOutputLists,
  panels,
  sessionPanelRefs,
  showToast,
  showConfirm,
  showSettingsModal,
  showWorkspacePanel,
  activeWorkspaceSession,
  hasNoPanel,
  isAutoFocusSuppressed,
  isAnyModalOpen,
  socket,
  sockets,
  auth,
  username,
  getHttpProtocol,
  buildNodeHttpUrl,
  getGatewayAddress,
  fetchWithAuth,
  escapeHtml,
  historyStorage,
  loadHistoryMessages,
  sendMessageToAgent,
  setupHistoryScrollListener,
  openAgentInPanel,
  closePanel,
  closeAgentInPanel,
  closeOpenDirDialog,
  confirmOpenDir,
  restoreWorkspacePaneContents,
  saveRecentWorkDir,
  loadRecentWorkDirs,
  filteredDirList,
  sortCompletionItems,
  recordCompletionSelection,
  switchGeneration,
  windowWidth,
  agentListLoaded,
  setModalAutoFocusSuppressUntil,
  MODAL_AUTOFOCUS_SUPPRESS_MS,
  hasMoreHistory,
  historyOffset,
  showCompletions,
  completionCursorPos,
  completionHasAtSymbol,
  completionAgentId,
  completionSource,
  petLobbyRef,
  completions,
  completionSearch,
  fileCompletions,
  completionSearchInput,
  completionsModalRef,
  selectedIndex,
  showCreateAgentModal,
  showQuickCreateAgentModal,
  quickCreateAgentLoading,
  quickCreateAgentError,
  showRenameAgentModal,
  renamingAgent,
  renameAgentName,
  showDirDialog,
  currentDirPath,
  dirList,
  selectedDir,
  dirSearchText,
  dirSearchInput,
  selectedDirIndex,
  dirDialogRef,
  saveAgentGroups,
  renameInput,
  openDirNodeId,
  openDirPath,
  openDirDialogRef,
  newAgentType,
  newAgentDir,
  newAgentName,
  modelGroups,
  newAgentModelGroup,
  newCodeAgentWorktree,
  newAgentQuickMode,
  newAgentRestoreSession,
  newAgentNoInteractionMode,
  newAgentTaskDescription,
  newAgentCreateError,
  newAgentProxyNode,
  newAgentAccessAclRead,
  newAgentAccessAclInteract,
  availableUserOptions,
  availableNodeOptions,
  userAccessibleNodes,
  userPermissions,
  getNodeDisplayName,
  newAgentNodeId,
  filteredNodeOptionsForCreateAgent,
  getDefaultCreateAgentNodeId,
  generateAgentName,
  skipNameWatch,
  rulesLoading,
  showRulesModal,
  rulesContent,
  rulesLoadedContent,
  selectedTerminalNodeId,
  // composable 返回（直接传引用）
  chatName,
  saveToHistory,
  lobbyHistoryIndex,
  lobbyHistoryTemp,
  maybeStartTour,
  fileTreeState,
  fileTreeExpanded,
  fileTreeLoading,
  // getter 注入（useOrchestrate / useTerminal / useGatewayConnection 返回，晚期求值）
  orchestrateAgents: getOrchestrateAgents,
  orchestrateActiveIndex: getOrchestrateActiveIndex,
  orchestrateNodeId: getOrchestrateNodeId,
  terminals: getTerminals,
  terminalHosts: getTerminalHosts,
  disposeExecutionTerminal: getDisposeExecutionTerminal,
  connectToAgent: getConnectToAgent,
  autoConnectToOnlineAgents: getAutoConnectToOnlineAgents,
  // getter 注入（App.vue 晚期定义函数）
  renderMessageHtml: getRenderMessageHtml,
  appendOutput: getAppendOutput,
  sendInputDirectly: getSendInputDirectly,
  sendBufferedInput: getSendBufferedInput,
  sendConfirmResult: getSendConfirmResult,
  restoreWaitingConfirmUI: getRestoreWaitingConfirmUI,
  pushOverlayState: getPushOverlayState,
}) {
  // —— 域内 ref（由本 composable 创建并返回，App.vue 解构共享）——
  // 目录选择弹窗的当前使用场景：'create-agent'（创建 Agent 选工作目录）/ 'open-dir'（按节点打开目录）/ 'orchestrate'（编排选工作目录）
  // 三者复用同一套目录筛选逻辑（fetchDirectories / filteredDirList / 键盘导航等），仅节点来源与确认后的去向不同
  const dirDialogContext = ref('create-agent')
  // 查看工具
  const showToolsModal = ref(false)
  const toolsContent = ref({ all_tools: [], allowed_tools: null })
  const toolsLoading = ref(false)
  // Agent ACL编辑
  const showEditAccessModal = ref(false)
  const editingAccessAgent = ref(null)
  const editAccessRead = ref([])
  const editAccessInteract = ref([])
  // 首次拉取到 Agent 后自动打开编辑器（唯一容器）的标志位（原 App.vue 2880 let，无 zone 外引用，移入本 composable）
  let workspaceAutoOpened = false
  // ========== Agent 管理方法 ==========


  // 获取状态文本（组合显示）
  function getStatusText(agent) {
    const statusData = agentStatuses.value.get(agent.agent_id)

    // Agent 状态（进程级别）
    const agentStatus = agent.status || 'running'

    // 如果 Agent 已停止，只显示停止状态
    if (agentStatus === 'stopped') {
      return '已完成'
    }

    // 如果没有运行状态数据，显示 Agent 状态
    if (!statusData) {
      return '运行中'
    }

    // 组合显示：Agent 状态 + 运行状态
    const executionStatus = statusData.execution_status || 'running'

    // 如果运行状态是 running，只显示"运行中"
    if (executionStatus === 'running') {
      return '运行中'
    }

    // 如果运行状态不是 running，组合显示
    const labels = {
      'running': '运行中',
      'waiting_multi': '等待多行输入',
      'waiting_single': '等待确认',
      'waiting_confirm': '等待确认'
    }
    const executionStatusText = labels[executionStatus] || '运行中'

    // 组合显示：运行中（等待状态）
    return `运行中（${executionStatusText}）`
  }

  // 获取状态 CSS 类名
  function getStatusClass(agent) {
    const statusData = agentStatuses.value.get(agent.agent_id)

    // 优先使用 agent 状态：如果 agent 已停止，直接显示 stopped
    if (agent.status === 'stopped') {
      return 'stopped'
    }

    // 非 stopped 状态：使用 execution_status
    if (statusData && statusData.execution_status) {
      return statusData.execution_status
    }

    // 默认 running
    return 'running'
  }

  // 判断是否处于等待输入状态
  function isWaitingInput(agent) {
    const statusClass = getStatusClass(agent)
    return statusClass === 'waiting_multi' || statusClass === 'waiting_single' || statusClass === 'waiting_confirm'
  }

  // 查询 Agent 状态（通过网关代理）
  async function fetchAgentStatus(agent) {
    if (!agent || !agent.agent_id) {
      console.warn('[AGENT STATUS] Invalid agent:', agent)
      return 'running' // 默认返回 running
    }

    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/status`))

      if (!response.ok) {
        console.warn(`[AGENT STATUS] Failed to fetch status for agent ${agent.agent_id}:`, response.status)
        return 'running' // 默认返回 running
      }

      const result = await response.json()
      // execution_status 是任务级别状态（running/waiting_multi/waiting_single）
      let executionStatus = result.execution_status || 'running'

      // 【竞态防护】input_request 经 WebSocket 实时到达，比 /status HTTP 轮询更权威。
      // 若本地已有未完成的输入请求，说明后端此刻正在等待该请求对应的输入；而本次 /status
      // 响应可能是在命令处理途中（running）读取的过期状态——典型场景：首次执行
      // <SwitchModelGroup> 时后端先 publish input_request(single) 再 _update_status(waiting_single)，
      // 轮询 HTTP 响应晚于 input_request 到达，读到过期的 running。此时以输入请求的 mode 为准，
      // 避免把已切换的单行输入覆盖回多行、并把 agentStatuses 误写为 running。
      //
      // 注意：不能只依赖 inputRequests——当用户发送命令时后端仍在 running，命令会先进入
      // inputBuffers；随后 input_request 到达时走「缓冲区分支」（handleMessage 中提前 return），
      // 不会写入 inputRequests（且 sendInputResult 还会把它删掉）。因此这里同时以
      // agentStatuses 里已记录的等待态（input_request/confirm 处理时写入）作为依据，
      // 只要本地已是等待输入/确认态，而轮询读到过期的 running，就以本地等待态为准，
      // 保证单行输入框不会被在途轮询覆盖回多行。
      const pendingInputRequest = inputRequests.value.get(agent.agent_id)
      if (pendingInputRequest && executionStatus === 'running') {
        executionStatus = pendingInputRequest.mode === 'single' ? 'waiting_single' : 'waiting_multi'
      }
      const localWaitingStatus = agentStatuses.value.get(agent.agent_id)?.execution_status
      if (executionStatus === 'running' && ['waiting_single', 'waiting_multi', 'waiting_confirm'].includes(localWaitingStatus)) {
        executionStatus = localWaitingStatus
      }

      // 更新状态映射（存储对象格式）
      // 本地确认条仍在时（如 completeFromPanel 已在本地进入确认态），后端 execution_status
      // 可能仍停留在 waiting_multi，此时不能覆盖本地状态，否则 y/n/Enter 键会失效。
      const hasLocalConfirm = panelConfirmData.value.has(agent.agent_id)
      if (!hasLocalConfirm) {
        agentStatuses.value.set(agent.agent_id, {execution_status: executionStatus, non_interactive: !!result.non_interactive})
      }

      // 当前 Agent 连接后根据 execution_status 恢复输入 UI
      if (agent.agent_id === currentAgentId.value) {
        if (executionStatus === 'waiting_single') {
          inputMode.value = 'single'
          panelInputModes.value.set(agent.agent_id, 'single')
          // 聚焦输入框（弹窗或宠物环形菜单打开时不抢焦点）
          const targetPanel = panels.value.find(p => p.agentId === agent.agent_id)
          const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
          if (sp?.focusInput && !isAutoFocusSuppressed()) sp.focusInput()
        } else if (executionStatus === 'waiting_multi') {
          // 本地确认条仍在时（如 completeFromPanel 已在本地进入确认态），
          // 后端 execution_status 可能仍停留在 waiting_multi，
          // 此时不能把输入框重置为多行，否则确认条还在、输入框却已变回多行。
          // 用户确认/取消后 panelConfirmData 会被清除，下一次轮询再正常同步。
          if (hasLocalConfirm) {
            return executionStatus
          }
          inputMode.value = 'multi'
          panelInputModes.value.set(agent.agent_id, 'multi')
          // 聚焦输入框（弹窗或宠物环形菜单打开时不抢焦点）
          const targetPanel = panels.value.find(p => p.agentId === agent.agent_id)
          const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
          if (sp?.focusInput && !isAutoFocusSuppressed()) sp.focusInput()
        } else if (executionStatus === 'waiting_confirm') {
          // 从 status 响应中获取 pending_confirm 并显示对话框
          const pendingConfirm = result.pending_confirm
          if (pendingConfirm && pendingConfirm.payload) {
            const payload = pendingConfirm.payload
            pendingConfirmAgentId.value = agent.agent_id
            // 更新 Panel 内嵌确认数据（按 agentId 隔离）
            panelConfirmData.value.set(agent.agent_id, {
              message: payload.message || '请确认',
              defaultConfirm: payload.default !== undefined ? payload.default : true
            })
            // 确认请求使用单行输入模式
            inputMode.value = 'single'
            panelInputModes.value.set(agent.agent_id, 'single')
            inputTip.value = payload.message || '请确认 (y/n/Enter)'
            panelInputTips.value.set(agent.agent_id, payload.message || '请确认 (y/n/Enter)')
            // 聚焦输入框（弹窗或宠物环形菜单打开时不抢焦点）
            const targetPanel = panels.value.find(p => p.agentId === agent.agent_id)
            const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
            if (sp?.focusInput && !isAutoFocusSuppressed()) sp.focusInput()
            // 无 Panel 时不弹全局对话框，确认请求静默等待，用户打开 Panel 后可见 confirm 控件
          } else {
            console.warn('[AGENT STATUS] waiting_confirm but no pending_confirm payload found')
          }
        } else {
          // 运行中（running）：输入框依然可用（可先行输入，Ctrl+Enter 发送/缓冲），
          // 故与 waiting_multi 一样把焦点交给多行输入框，避免用户必须手动点击才能输入。
          inputMode.value = 'multi'
          panelInputModes.value.set(agent.agent_id, 'multi')
          const targetPanel = panels.value.find(p => p.agentId === agent.agent_id)
          const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
          if (sp?.focusInput && !isAutoFocusSuppressed()) sp.focusInput()
        }
      } else {
      }

      return executionStatus
    } catch (error) {
      console.error(`[AGENT STATUS] Error fetching status for agent ${agent.agent_id}:`, error)
      return 'running' // 错误时返回默认状态
    }
  }

  // 主动同步在线 agent 的执行状态（避免仅靠 WebSocket 推送，错过等待输入状态）
  const syncingAgentStatuses = new Set()
  let lastStatusSyncAt = 0
  const STATUS_SYNC_INTERVAL = 5000 // 状态同步最小间隔（毫秒）

  function syncOnlineAgentStatuses() {
    const now = Date.now()
    if (now - lastStatusSyncAt < STATUS_SYNC_INTERVAL) {
      return
    }
    lastStatusSyncAt = now

    for (const agent of agentList.value) {
      if (agent.status !== 'running') continue
      if (syncingAgentStatuses.has(agent.agent_id)) continue
      syncingAgentStatuses.add(agent.agent_id)
      fetchAgentStatus(agent)
        .catch((error) => {
          console.warn(`[AGENT STATUS] Sync failed for ${agent.agent_id}:`, error?.message)
        })
        .finally(() => {
          syncingAgentStatuses.delete(agent.agent_id)
        })
    }
  }

  // Session 恢复逻辑已拆出到 composables/useSession.js（见下方 useSession 调用处）


  function getCreateAgentDirectoryNodeId() {
    if (dirDialogContext.value === 'open-dir') {
      return (openDirNodeId.value || '').trim()
    }
    if (dirDialogContext.value === 'orchestrate') {
      return (getOrchestrateNodeId().value || '').trim()
    }
    return (newAgentNodeId.value || '').trim()
  }

  function resetDirectorySelectionState() {
    showDirDialog.value = false
    currentDirPath.value = ''
    dirList.value = []
    selectedDir.value = null
    dirSearchText.value = ''
    selectedDirIndex.value = -1
  }

  watch(newAgentNodeId, (newNodeId) => {
    newAgentDir.value = '~'
    resetDirectorySelectionState()
    // 切换节点时重新获取对应节点的模型组列表（复制 Agent 时跳过）
    if (!skipNameWatch.value) {
      fetchModelGroups(newNodeId || 'master')
    }
  }, { flush: 'sync' })

  async function openDirDialog() {
    // 三种场景（创建 Agent / 打开目录 / 编排选目录）均以独立弹窗形式展示目录选择
    const isOpenDir = dirDialogContext.value === 'open-dir'
    showDirDialog.value = true
    if (isOpenDir) {
      // 「打开目录」：从根目录开始浏览，确认后回填到「打开目录」弹层
      selectedDir.value = '~'
    } else if (dirDialogContext.value === 'orchestrate') {
      // 编排场景：以编排弹窗所选节点为浏览来源，初始路径取当前编辑的 Agent 工作目录
      const active = getOrchestrateAgents().value[getOrchestrateActiveIndex().value]
      selectedDir.value = (active && active.workingDir) || '~'
    } else {
      dirDialogContext.value = 'create-agent'
      selectedDir.value = newAgentDir.value || '~'
    }
    dirSearchText.value = '' // 清空搜索
    selectedDirIndex.value = -1
    await fetchDirectories(selectedDir.value)
    // PC端自动聚焦到搜索框，移动端不聚焦
    if (windowWidth.value > 768) {
      nextTick(() => {
        dirSearchInput.value?.focus()
      })
    }
  }

  async function fetchDirectories(path = '') {
    try {
      const { host, port } = getGatewayAddress()
      const params = new URLSearchParams({ path })
      const nodeId = String(getCreateAgentDirectoryNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, nodeId, `directories?${params.toString()}`))

      if (!response.ok) {
        const error = await response.json()
        console.error('[DIR] 获取目录列表失败:', error)
        alert(`获取目录列表失败: ${error.error?.message || '未知错误'}`)
        return
      }

      const result = await response.json()
      if (result.success && result.data) {
        currentDirPath.value = result.data.current_path
        // 只显示目录，过滤掉文件（工作目录选择不需要显示文件）
        dirList.value = (result.data.items || []).filter(item => item.type === 'directory')
      }
    } catch (error) {
      console.error('[DIR] 获取目录列表出错:', error)
      alert(`获取目录列表出错: ${error.message}`)
    }
  }

  function selectDirectory(path) {
    selectedDir.value = path
    // 同时更新索引
    const index = filteredDirList.value.findIndex(dir => dir.path === path)
    if (index !== -1) {
      selectedDirIndex.value = index
    }
  }

  // 处理目录搜索框的键盘事件
  function handleDirSearchKeydown(event) {
    const maxIndex = filteredDirList.value.length - 1

    if (event.key === 'Escape') {
      // ESC 键关闭当前场景的对话框
      if (dirDialogContext.value === 'open-dir') {
        closeOpenDirDialog()
      } else {
        cancelDirDialog()
      }
      event.preventDefault()
      return
    }

    // 带 Ctrl/Alt/Meta 修饰键时交由全局快捷键处理，不做列表导航
    if (event.ctrlKey || event.altKey || event.metaKey) return

    if (event.key === 'ArrowDown') {
      // 向下键：选择下一个目录
      if (selectedDirIndex.value < maxIndex) {
        selectedDirIndex.value++
      } else if (selectedDirIndex.value === -1) {
        selectedDirIndex.value = 0
      }
      // 选中的目录同时设置为 selectedDir
      if (selectedDirIndex.value >= 0 && selectedDirIndex.value <= maxIndex) {
        selectedDir.value = filteredDirList.value[selectedDirIndex.value].path
      }
      // 滚动到选中项
      scrollToDirSelected()
      event.preventDefault()
      return
    }

    if (event.key === 'ArrowUp') {
      // 向上键：选择上一个目录
      if (selectedDirIndex.value > 0) {
        selectedDirIndex.value--
      } else if (selectedDirIndex.value === -1) {
        selectedDirIndex.value = maxIndex
      } else {
        // 从第 0 项继续上移：回到「未选中」状态，必须同步清空 selectedDir，
        // 否则 Enter 会因 selectedDir 残留旧值而误判为「确认当前选择」而非「进入目录」
        selectedDirIndex.value = -1
        selectedDir.value = null
      }
      // 选中的目录同时设置为 selectedDir
      if (selectedDirIndex.value >= 0 && selectedDirIndex.value <= maxIndex) {
        selectedDir.value = filteredDirList.value[selectedDirIndex.value].path
      }
      // 滚动到选中项
      scrollToDirSelected()
      event.preventDefault()
      return
    }

    if (event.key === 'Enter') {
      // 回车键：如果选中了列表项，则进入该目录；否则确认当前选择
      if (selectedDirIndex.value >= 0 && selectedDirIndex.value <= maxIndex) {
        // 有选中列表项，进入该目录
        const selectedPath = filteredDirList.value[selectedDirIndex.value].path
        selectDirectory(selectedPath)
        enterDirectory(selectedPath)
        event.preventDefault()
      } else if (selectedDir.value) {
        // 没有选中列表项，但已经有选中的目录，确认当前选择
        if (dirDialogContext.value === 'open-dir') {
          // 「打开目录」场景：直接以当前选中目录打开
          confirmOpenDir()
        } else {
          confirmDirectory()
        }
        event.preventDefault()
      }
      return
    }
  }

  async function enterDirectory(path, shouldFocus = true) {
    await fetchDirectories(path)
    // 清空搜索
    dirSearchText.value = ''
    selectedDirIndex.value = -1
    // 根据参数决定是否聚焦到搜索框
    if (shouldFocus) {
      nextTick(() => {
        dirSearchInput.value?.focus()
      })
    }
  }

  async function goToParentDir() {
    try {
      // 浏览器环境下的路径处理
      const normalizedPath = currentDirPath.value.replace(/\\/g, '/')
      const parts = normalizedPath.split('/').filter(p => p)

      if (parts.length > 0) {
        parts.pop() // 移除最后一部分
        const parentPath = '/' + parts.join('/')
        await fetchDirectories(parentPath)
      }
    } catch (error) {
      console.error('[DIR] 返回上级目录失败:', error)
    }
  }

  async function confirmDirectory() {
    if (selectedDir.value) {
      if (dirDialogContext.value === 'open-dir') {
        // 「打开目录」场景：把选中的目录回填到「打开目录」弹层，但不关闭该弹层
        openDirPath.value = selectedDir.value
      } else if (dirDialogContext.value === 'orchestrate') {
        // 编排场景：把选中的目录回填到当前 Agent 标签页的工作目录
        const active = getOrchestrateAgents().value[getOrchestrateActiveIndex().value]
        if (active) active.workingDir = selectedDir.value
      } else {
        newAgentDir.value = selectedDir.value
      }
      // 保存工作目录到历史记录（按节点区分）
      saveRecentWorkDir(selectedDir.value, getCreateAgentDirectoryNodeId())
      showDirDialog.value = false
    }
  }

  function cancelDirDialog() {
    showDirDialog.value = false
    selectedDir.value = null
    dirSearchText.value = ''
    selectedDirIndex.value = -1
    // 复位场景，避免后续创建 Agent 的「选择目录」被误判为「打开目录」/「编排」场景
    dirDialogContext.value = 'create-agent'
  }

  // 打开创建 Agent 弹窗（可指定初始节点，如从大厅双击某节点进入）
  async function openCreateAgentModal(initialNodeId = '') {
    // 先刷新模型组列表，确保获取最新的配置
    await Promise.all([
      fetchModelGroups(),
      fetchNodeStatus(),
      fetchUserList(),
      fetchUserAccessibleNodes(),
    ])
    // 加载最近使用的工作目录
    loadRecentWorkDirs()
    const target = typeof initialNodeId === 'string' ? initialNodeId.trim() : ''
    // 校验目标节点在可创建范围内，否则回退到默认节点（master）
    const allowed = filteredNodeOptionsForCreateAgent.value.some(n => n.node_id === target)
    newAgentNodeId.value = allowed ? target : getDefaultCreateAgentNodeId()
    newAgentDir.value = '~'
    newAgentCreateError.value = ''
    resetDirectorySelectionState()
    showCreateAgentModal.value = true
  }

  // 大厅中双击节点：打开创建 Agent 弹窗并预选该节点
  function onLobbyCreateAgentOnNode(nodeId) {
    openCreateAgentModal(nodeId)
  }

  // 获取模型组列表
  async function fetchModelGroups(nodeId = 'master', autoSelect = true) {
    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(nodeId || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'model-groups'))
      if (!response.ok) {
        console.error('[MODEL GROUP] 获取模型组列表失败:', response.status)
        return
      }
      const result = await response.json()
      if (result.success && result.data) {
        modelGroups.value = result.data
        // 如果模型组列表不为空，优先使用配置的默认模型组
        if (autoSelect && modelGroups.value.length > 0) {
          const defaultGroup = result.default_llm_group || ''
          const hasDefaultGroup = defaultGroup && modelGroups.value.some(g => g.name === defaultGroup)
          const hasCurrentGroup = modelGroups.value.some(g => g.name === newAgentModelGroup.value)
          if (hasDefaultGroup) {
            // 使用配置的默认模型组
            newAgentModelGroup.value = defaultGroup
          } else if (!hasCurrentGroup) {
            // 如果没有默认模型组或默认模型组不在列表中，选择第一个
            newAgentModelGroup.value = modelGroups.value[0].name
          }
        }
      }
    } catch (error) {
      console.error('[MODEL GROUP] 获取模型组列表出错:', error)
    }
  }

  async function fetchUserAccessibleNodes() {
    try {
      const { host, port } = getGatewayAddress()
      const userId = auth.value.userInfo?.user_id
      if (!userId) { userAccessibleNodes.value = []; return }
      const response = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/permissions/user/${encodeURIComponent(userId)}/accessible-nodes`)
      if (!response.ok) {
        console.warn('[PERM] 获取可访问节点失败:', response.status)
        userAccessibleNodes.value = []
        return
      }
      const result = await response.json()
      if (result.success && result.data) {
        userAccessibleNodes.value = result.data.accessible_nodes || []
      } else {
        userAccessibleNodes.value = []
      }
    } catch (error) {
      console.error('[PERM] 获取可访问节点出错:', error)
      userAccessibleNodes.value = []
    }
  }

  // 获取当前用户权限（allowed/denied 为权限 pattern 列表）
  async function fetchUserPermissions() {
    try {
      const { host, port } = getGatewayAddress()
      const userId = auth.value.userInfo?.user_id
      if (!userId) { userPermissions.value = { allowed: [], denied: [] }; return }
      const response = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/permissions/user/${encodeURIComponent(userId)}`)
      if (!response.ok) {
        console.warn('[PERM] 获取用户权限失败:', response.status)
        userPermissions.value = { allowed: [], denied: [] }
        return
      }
      const result = await response.json()
      if (result.success && result.data?.permissions) {
        userPermissions.value = {
          allowed: result.data.permissions.allowed || [],
          denied: result.data.permissions.denied || []
        }
      } else {
        userPermissions.value = { allowed: [], denied: [] }
      }
    } catch (error) {
      console.error('[PERM] 获取用户权限出错:', error)
      userPermissions.value = { allowed: [], denied: [] }
    }
  }

  // 权限 pattern 匹配：支持 '*:*'、精确匹配、'前缀:*' 通配
  function matchPermissionPattern(pattern, permission) {
    if (!pattern || !permission) return false
    if (pattern === '*:*' || pattern === permission) return true
    const parts = String(pattern).split(':')
    if (parts.length === 2 && parts[1] === '*') {
      return String(permission).startsWith(parts[0] + ':')
    }
    return false
  }

  // 判断当前用户是否拥有指定权限（管理员直接放行；denied 优先于 allowed）
  function hasPermission(permission) {
    if (!permission) return false
    if (auth.value.userInfo?.is_admin) return true
    const perms = userPermissions.value
    if (!perms) return false
    const denied = Array.isArray(perms.denied) ? perms.denied : []
    if (denied.some(p => matchPermissionPattern(p, permission))) return false
    const allowed = Array.isArray(perms.allowed) ? perms.allowed : []
    return allowed.some(p => matchPermissionPattern(p, permission))
  }

  async function fetchNodeStatus() {
    try {
      const { host, port } = getGatewayAddress()
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, 'master', 'node/status'))
      if (!response.ok) {
        console.warn('[NODE] 获取节点状态失败:', response.status)
        availableNodeOptions.value = []
        return
      }
      const result = await response.json()
      const nodes = Array.isArray(result?.data?.nodes) ? result.data.nodes : []
      const processedNodes = nodes
        .filter(node => node && String(node.node_id || '').trim())
        .map(node => ({
          ...node,
          node_id: String(node.node_id || '').trim(),
        }))
      // 确保 master 节点始终在选项列表中
      if (!processedNodes.some(n => n.node_id === 'master')) {
        processedNodes.unshift({ node_id: 'master', status: 'running' })
      }
      availableNodeOptions.value = processedNodes
    } catch (error) {
      console.error('[NODE] 获取节点状态出错:', error)
      availableNodeOptions.value = []
    }
  }

  // 定时刷新节点状态（节点断线后需及时反映到拓扑图）
  let nodeStatusRefreshInterval = null

  function startNodeStatusRefresh() {
    if (nodeStatusRefreshInterval) {
      clearInterval(nodeStatusRefreshInterval)
    }
    // 每 10 秒刷新一次（节点状态变化不频繁，间隔放宽以减少请求）
    nodeStatusRefreshInterval = setInterval(() => {
      fetchNodeStatus()
    }, 10000)
  }

  function stopNodeStatusRefresh() {
    if (nodeStatusRefreshInterval) {
      clearInterval(nodeStatusRefreshInterval)
      nodeStatusRefreshInterval = null
    }
  }

  async function fetchUserList() {
    try {
      const { host, port } = getGatewayAddress()
      const response = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/users/brief`)
      if (!response.ok) {
        console.warn('[USER] 获取用户列表失败:', response.status)
        availableUserOptions.value = []
        return
      }
      const result = await response.json()
      availableUserOptions.value = result?.data?.users || []
    } catch (err) {
      console.warn('[USER] 获取用户列表异常:', err)
      availableUserOptions.value = []
    }
  }

  function formatNodeOptionLabel(node) {
    const nodeId = String(node?.node_id || '').trim()
    const displayName = getNodeDisplayName(nodeId)
    const status = String(node?.status || node?.runtime_status || '').trim()
    return status ? `${displayName} (${status})` : displayName
  }

  function getDefaultTerminalNodeId(nodes = []) {
    if (nodes.some(node => node.node_id === 'master')) {
      return 'master'
    }
    return nodes[0]?.node_id || ''
  }

  watch(availableNodeOptions, (nodes) => {
    const hasSelectedNode = nodes.some(node => node.node_id === selectedTerminalNodeId.value)
    if (!hasSelectedNode) {
      selectedTerminalNodeId.value = getDefaultTerminalNodeId(nodes)
    }
  }, { immediate: true })

  function getAgentNodeLabel(agent) {
    return String(agent?.node_id || '').trim() || 'master'
  }

  // Agent 所属节点的展示名（优先自定义显示名），仅用于界面展示
  function getAgentNodeDisplayLabel(agent) {
    return getNodeDisplayName(getAgentNodeLabel(agent))
  }

  function getAgentProxyNodeLabel(agent) {
    return String(agent?.proxy_node || '').trim()
  }

  function getCurrentAgentNodeId() {
    return String(currentAgent.value?.node_id || '').trim()
  }

  // 获取编辑器目标节点ID（优先使用编辑器对应agent的节点ID）
  function getWorkspaceTargetNodeId() {
    const workspaceAgentNodeId = activeWorkspaceSession.value?.agent?.node_id
    return String(workspaceAgentNodeId || getCurrentAgentNodeId() || 'master').trim() || 'master'
  }

  // 校验：同一节点同一工作目录不允许同时有两个未启用 worktree 的 code_agent。
  // 返回冲突提示文案，无冲突返回空串。
  function checkCodeAgentDirConflict({ agentType, worktree, workingDir, nodeId }) {
    if (agentType !== 'code_agent' || worktree) return ''
    const targetNodeId = String(nodeId || 'master').trim() || 'master'
    const normalizedDir = String(workingDir || '').trim()
    const conflictingAgent = agentList.value.find(agent => {
      if (isStoppedAgent(agent)) return false  // 已停止的 agent 不冲突
      if (agent.agent_type !== 'code_agent') return false
      if (agent.worktree) return false  // 启用了 worktree 的不冲突
      const agentNodeId = String(agent.node_id || '').trim() || 'master'
      if (agentNodeId !== targetNodeId) return false
      if (agent.working_dir?.trim() !== normalizedDir) return false
      return true
    })
    if (!conflictingAgent) return ''
    const conflictName = conflictingAgent.name || conflictingAgent.agent_id || '未命名'
    return `工作目录冲突：节点 ${targetNodeId} 下已存在未启用 worktree 的代码 Agent「${conflictName}」。\n同一工作目录下只能有一个未启用 worktree 的代码 Agent。\n请启用 worktree 或选择其他工作目录。`
  }

  // 参数化创建 Agent：只负责校验与请求，返回 { ok, agent, error }，不处理任何 UI 副作用。
  // 供「新建 Agent 弹窗」与「一句话创建」共用。
  async function createAgentWithOptions(options = {}) {
    const {
      agentType = 'agent',
      workingDir = '~',
      name = '',
      llmGroup = 'default',
      worktree = false,
      quickMode = false,
      restoreSession = false,
      noInteractionMode = false,
      task = '',
      nodeId = '',
      proxyNode = '',
      accessAclRead = [],
      accessAclInteract = [],
      toolGroup = '',
      configFile = '',
      additionalArgs = '',
    } = options

    const trimmedDir = String(workingDir || '').trim()
    if (!trimmedDir) return { ok: false, error: '工作目录不能为空' }
    const trimmedTask = String(task || '').trim()
    if (noInteractionMode && !trimmedTask) {
      return { ok: false, error: '无交互模式下必须提供任务描述' }
    }
    const conflict = checkCodeAgentDirConflict({
      agentType,
      worktree: agentType === 'code_agent' ? worktree : false,
      workingDir: trimmedDir,
      nodeId,
    })
    if (conflict) return { ok: false, error: conflict }

    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(nodeId || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'), {
        method: 'POST',
        body: JSON.stringify({
          agent_type: agentType,
          working_dir: trimmedDir,
          name: name || undefined,
          llm_group: llmGroup,
          worktree: agentType === 'code_agent' ? worktree : false,
          quick_mode: quickMode,
          restore_session: restoreSession,
          no_interaction_mode: noInteractionMode,
          task: trimmedTask || undefined,
          node_id: targetNodeId,
          proxy_node: proxyNode || undefined,
          access_acl: (accessAclRead.length || accessAclInteract.length) ? {
            read: accessAclRead,
            interact: accessAclInteract,
          } : undefined,
          // 编排场景专用字段：非空才写入 body，避免覆盖后端默认值
          tool_group: String(toolGroup || '').trim() || undefined,
          config_file: String(configFile || '').trim() || undefined,
          additional_args: String(additionalArgs || '').trim() || undefined,
        })
      })
      if (!response.ok) {
        const error = await response.json().catch(() => ({}))
        return { ok: false, error: error.error?.message || error.detail || '未知错误' }
      }
      const result = await response.json()
      if (!result.success || !result.data) {
        return { ok: false, error: '返回数据格式错误' }
      }
      const agent = {
        ...result.data,
        node_id: String(result.data?.node_id || '').trim() || 'master',
      }
      return { ok: true, agent }
    } catch (error) {
      console.error('[AGENT] Create failed:', error)
      return { ok: false, error: error.message }
    }
  }

  // 创建成功后的公共收尾：加入列表、刷新、按当前场景打开 Panel 或留在大厅、展示引导。
  async function afterAgentCreated(agent) {
    // 添加到列表开头（让后创建的 agent 排在前面）
    agentList.value.unshift(agent)
    // 若当前处于宠物大厅（无任何可见 Panel），保持在大厅，不切换到 Panel；
    // 否则（已有 Panel 打开）按原逻辑在新 Panel 中打开该 Agent
    if (!hasNoPanel.value) {
      await openAgentInPanel(agent)
    }
    // 刷新列表
    await fetchAgentList()
    // 开始定时刷新列表
    startAgentListRefresh()
    // 首次创建出 Agent 后展示 Agent 场景引导。
    // openAgentInPanel 会在 nextTick 中调度 Panel 场景引导；此处再注册一个 nextTick
    // （注册更晚，回调更晚执行），使 Agent 引导清除 Panel 引导的定时器并优先展示，
    // 避免「创建 Agent」这一更强场景的引导被 Panel 引导吞掉。
    nextTick(() => maybeStartTour('agent'))
  }

  async function createAgent() {
    if (!newAgentDir.value.trim()) return
    // 无交互模式下必须提供任务描述
    if (newAgentNoInteractionMode.value && !newAgentTaskDescription.value.trim()) {
      alert('无交互模式下必须提供任务描述')
      return
    }
    const result = await createAgentWithOptions({
      agentType: newAgentType.value,
      workingDir: newAgentDir.value,
      name: newAgentName.value,
      llmGroup: newAgentModelGroup.value,
      worktree: newCodeAgentWorktree.value,
      quickMode: newAgentQuickMode.value,
      restoreSession: newAgentRestoreSession.value,
      noInteractionMode: newAgentNoInteractionMode.value,
      // 任务描述与是否无交互模式无关：填写即传（无交互模式仅额外要求任务必填）
      task: newAgentTaskDescription.value,
      nodeId: newAgentNodeId.value,
      proxyNode: newAgentProxyNode.value,
      accessAclRead: newAgentAccessAclRead.value,
      accessAclInteract: newAgentAccessAclInteract.value,
    })
    if (!result.ok) {
      // 工作目录冲突提示走弹窗内错误区，其余走 alert（保持原有表现）
      if (result.error && result.error.includes('工作目录冲突')) {
        newAgentCreateError.value = result.error
      } else {
        alert(`创建失败: ${result.error}`)
      }
      return
    }
    // 关闭创建弹窗
    showCreateAgentModal.value = false
    newAgentDir.value = '~' // 重置为默认值
    newAgentCreateError.value = '' // 重置错误信息
    newCodeAgentWorktree.value = false
    newAgentQuickMode.value = false
    newAgentRestoreSession.value = false
    newAgentNoInteractionMode.value = false
    newAgentTaskDescription.value = ''
    newAgentNodeId.value = getDefaultCreateAgentNodeId()
    newAgentAccessAclRead.value = []
    newAgentAccessAclInteract.value = []
    // 重置为默认名称（根据当前选中的 agent 类型）
    newAgentName.value = generateAgentName(newAgentType.value)
    await afterAgentCreated(result.agent)
  }
  // 打开「一句话创建 Agent」弹窗（除任务外全部使用默认参数）
  function openQuickCreateAgent() {
    quickCreateAgentError.value = ''
    quickCreateAgentLoading.value = false
    showQuickCreateAgentModal.value = true
    getPushOverlayState()()
  }

  // 从「一句话创建」切到完整创建面板：关闭快捷弹窗并打开完整弹窗
  async function openFullCreateAgentFromQuick() {
    showQuickCreateAgentModal.value = false
    await openCreateAgentModal()
  }

  // 提交「一句话创建 Agent」：创建后 Agent 立即执行该任务，但保留交互确认（no_interaction_mode=false）
  async function submitQuickCreateAgent({ task, agentType = 'agent', workingDir = '~' } = {}) {
    const trimmedTask = String(task || '').trim()
    if (!trimmedTask) return
    quickCreateAgentLoading.value = true
    quickCreateAgentError.value = ''
    try {
      const result = await createAgentWithOptions({
        agentType,
        workingDir,
        name: generateAgentName(agentType),
        llmGroup: 'default',
        noInteractionMode: false,
        task: trimmedTask,
        nodeId: 'master',
      })
      if (!result.ok) {
        quickCreateAgentError.value = result.error || '创建失败'
        return
      }
      showQuickCreateAgentModal.value = false
      await afterAgentCreated(result.agent)
    } finally {
      quickCreateAgentLoading.value = false
    }
  }
  // 打开补全列表
  async function openCompletions() {
    if (!currentAgent.value) {
      alert('请先选择一个 Agent')
      return
    }

    completionAgentId.value = currentAgentId.value
    completionSearch.value = ''
    selectedIndex.value = -1
    showCompletions.value = true

    // 获取补全列表
    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `completions/${currentAgent.value.agent_id}`))

      const result = await response.json()

      if (!response.ok) {
        alert(`获取补全列表失败: ${result.error?.message || result.detail || '未知错误'}`)
        return
      }

      if (result.success && result.data) {
        completions.value = sortCompletionItems(result.data)
      } else {
        console.error('[COMPLETIONS] Invalid format:', result)
        alert('获取补全列表失败：返回数据格式错误')
      }
    } catch (error) {
      console.error('[COMPLETIONS] Fetch failed:', error)
      alert(`获取补全列表失败: ${error.message}`)
    }

    // PC端聚焦搜索框，移动端不聚焦
    if (windowWidth.value > 768) {
      nextTick(() => {
        completionSearchInput.value?.focus()
      })
    }
  }

  // 过滤补全列表
  const filteredCompletions = computed(() => {
    if (!completionSearch.value) {
      return sortCompletionItems(completions.value)
    }

    const search = completionSearch.value.toLowerCase()
    // 过滤原始补全项
    const filteredOriginal = completions.value.filter(item => {
      const displayText = String(item.display || '').toLowerCase()
      const descriptionText = String(item.description || '').toLowerCase()
      const valueText = String(item.value || '').toLowerCase()
      return displayText.includes(search) || descriptionText.includes(search) || valueText.includes(search)
    })

    // 合并文件补全结果（如果有搜索内容）
    if (fileCompletions.value.length > 0) {
      return sortCompletionItems([...filteredOriginal, ...fileCompletions.value])
    }

    return sortCompletionItems(filteredOriginal)
  })

  // 关闭补全对话框（取消选择）：键盘输入 @ 触发时保留 @ 符号，按钮触发时无需插入任何字符
  function closeCompletionsWithoutSelect() {
    if (completionHasAtSymbol.value && completionSource.value !== 'lobby') {
      insertAtPosition('@', completionCursorPos.value, completionAgentId.value)
    }
    showCompletions.value = false
    selectedIndex.value = -1
    completionCursorPos.value = -1
    completionHasAtSymbol.value = false
    completionAgentId.value = null
    completionSource.value = 'panel'
  }

  // 处理补全对话框的键盘事件
  function handleCompletionKeydown(event) {
    const maxIndex = filteredCompletions.value.length - 1

    if (event.key === 'Escape') {
      // ESC 键关闭对话框
      closeCompletionsWithoutSelect()
      event.preventDefault()
      return
    }

    // 带 Ctrl/Alt/Meta 修饰键时交由全局快捷键处理，不做列表导航
    if (event.ctrlKey || event.altKey || event.metaKey) return

    if (event.key === 'ArrowDown') {
      // 向下键：选择下一个条目
      if (selectedIndex.value < maxIndex) {
        selectedIndex.value++
      } else if (selectedIndex.value === -1) {
        selectedIndex.value = 0
      }
      scrollToSelected()
      event.preventDefault()
      return
    }

    if (event.key === 'ArrowUp') {
      // 向上键：选择上一个条目
      if (selectedIndex.value > 0) {
        selectedIndex.value--
      } else if (selectedIndex.value === -1) {
        selectedIndex.value = maxIndex
      } else {
        selectedIndex.value = -1
      }
      scrollToSelected()
      event.preventDefault()
      return
    }

    if (event.key === 'Enter') {
      // 回车键：如果选中了条目，则插入
      if (selectedIndex.value >= 0 && selectedIndex.value <= maxIndex) {
        insertCompletion(filteredCompletions.value[selectedIndex.value], completionAgentId.value)
        event.preventDefault()
      }
      return
    }
  }

  // 滚动到选中的条目
  function scrollToSelected() {
    nextTick(() => {
      const modal = completionsModalRef.value
      if (!modal) return
      const selectedItem = modal.itemRefs?.[selectedIndex.value]
      if (selectedItem) {
        selectedItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      }
    })
  }

  // 滚动到选中的目录项
  function scrollToDirSelected() {
    nextTick(() => {
      // 「打开目录」用内嵌的 DirectoryDialog；「创建 Agent」用独立弹窗
      const dialog = dirDialogContext.value === 'open-dir' ? openDirDialogRef.value : dirDialogRef.value
      if (!dialog) return
      const listContainer = dialog.dirListRef
      if (!listContainer) return

      // 找到选中项的DOM元素
      const items = listContainer.querySelectorAll('.dir-item')
      const selectedItem = items[selectedDirIndex.value]
      if (selectedItem) {
        selectedItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      }
    })
  }

  // 查找会话输入框 textarea：同一 Agent 可能同时存在多个实例（网格版与编辑器内嵌版），
  // 其中被 v-show 隐藏的副本仍在 DOM 中且排在前面，直接 querySelector 会命中它，
  // 对其 focus() 无效（display:none 元素无法获得焦点），导致补全后焦点回不到输入框。
  // 因此优先取可见实例，全部不可见时再退回首个匹配。
  function findVisiblePanelTextarea(agentId) {
    const selector = agentId
      ? `.input-wrapper textarea[data-agent-id="${agentId}"]`
      : '.input-wrapper textarea'
    const candidates = Array.from(document.querySelectorAll(selector))
    const visible = candidates.find(el => el.getClientRects().length > 0)
    return visible || candidates[0] || null
  }

  // 在指定位置插入文本
  function insertAtPosition(text, position, agentId = null) {
    const targetAgentId = agentId || currentAgentId.value
    const textarea = findVisiblePanelTextarea(targetAgentId)
    if (!textarea || position === -1) return

    const currentText = targetAgentId
      ? (panelInputTexts.value.get(targetAgentId) || '')
      : inputText.value
    // 在指定位置插入文本
    const newText = currentText.substring(0, position) + text + currentText.substring(position)
    if (targetAgentId) {
      panelInputTexts.value.set(targetAgentId, newText)
    }
    inputText.value = newText

    // 更新 textarea 并设置光标位置
    textarea.value = newText
    const newCursorPos = position + text.length
    textarea.setSelectionRange(newCursorPos, newCursorPos)
    textarea.focus()
  }
  // 插入选中的补全
  function insertCompletion(item, agentId = null) {
    const targetAgentId = agentId || currentAgentId.value

    // 来自宠物大厅：写回 PetLobby 内部输入框
    if (completionSource.value === 'lobby') {
      recordCompletionSelection(item)
      petLobbyRef.value?.insertCompletionText?.(
        targetAgentId,
        item.value,
        completionCursorPos.value,
        completionHasAtSymbol.value,
      )
      showCompletions.value = false
      selectedIndex.value = -1
      completionCursorPos.value = -1
      completionHasAtSymbol.value = false
      completionAgentId.value = null
      completionSource.value = 'panel'
      return
    }

    const textarea = findVisiblePanelTextarea(targetAgentId)

    // 数据源以 panelInputTexts / inputText 为准，textarea 仅用于同步光标；
    // 移动端点击补全项时 textarea 可能已失焦甚至查询不到，不能因此直接放弃插入
    const text = targetAgentId
      ? (panelInputTexts.value.get(targetAgentId) || '')
      : (textarea ? textarea.value : inputText.value)

    recordCompletionSelection(item)

    // 键盘输入 @ 触发的补全：删除 @ 符号；按钮触发的补全：输入框中没有 @，直接在光标处插入
    let deleteStart
    if (completionHasAtSymbol.value && completionCursorPos.value !== -1) {
      deleteStart = completionCursorPos.value
    } else {
      // 无 @ 可删：优先用打开补全时记录的光标位置，否则退回到末尾
      deleteStart = completionCursorPos.value === -1 ? text.length : completionCursorPos.value
    }
    if (deleteStart > text.length) deleteStart = text.length

    // 在 deleteStart 位置插入补全（添加单引号包裹）
    const valueToInsert = `'${item.value}'`
    const newText = text.substring(0, deleteStart) + valueToInsert + text.substring(deleteStart)
    if (targetAgentId) {
      // 替换整个 Map 以触发 Vue 响应式更新（Map.set 不会）
      const nextMap = new Map(panelInputTexts.value)
      nextMap.set(targetAgentId, newText)
      panelInputTexts.value = nextMap
    }
    inputText.value = newText

    // 同步 DOM 与光标位置（textarea 存在时才操作）
    if (textarea) {
      textarea.value = newText
      const newCursorPos = deleteStart + valueToInsert.length
      textarea.setSelectionRange(newCursorPos, newCursorPos)
      textarea.focus()
    }

    // 关闭弹窗
    showCompletions.value = false
    selectedIndex.value = -1
    completionCursorPos.value = -1
    completionHasAtSymbol.value = false
    completionAgentId.value = null
  }

  // 获取 Agent 列表
  async function fetchAgentList() {
    try {
      const { host, port } = getGatewayAddress()
      // 始终使用 'master' 节点来获取所有节点的 agent 列表
      const targetNodeId = 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'))

      if (!response.ok) return

      const result = await response.json()


      // 更新列表（后端返回格式: { success: true, data: agents }）
      if (result.success && result.data) {
        // 反转数组，让后创建的 agent 排在前面
        agentList.value = result.data.slice().reverse().map(agent => ({
          ...agent,
          node_id: String(agent?.node_id || '').trim() || 'master',
        }))

        // 确保所有在线 agent 都已建立连接（内部会跳过已连接的，重复调用安全），
        // 这样未被点击过的 agent 也能实时接收状态更新。
        getAutoConnectToOnlineAgents()()

        // 主动同步在线 agent 的执行状态（如等待输入），
        // 避免因错过 WebSocket 推送导致状态停留在 running。
        syncOnlineAgentStatuses()

        // 首次拉取到 Agent 后自动打开编辑器（唯一容器），让用户直接进入工作区；
        // 无 Agent 时保持关闭，露出宠物大厅作为欢迎页。
        if (!workspaceAutoOpened && agentList.value.length > 0) {
          workspaceAutoOpened = true
          showWorkspacePanel.value = true
        }
      }

      // 更新当前 Agent 状态
      const currentAgent = agentList.value.find(a => a.agent_id === currentAgentId.value)
      if (currentAgent && currentAgent.status !== 'running') {
      }
    } catch (error) {
      console.error('[AGENT] Fetch list failed:', error)
    } finally {
      // 首次拉取结束（无论成功失败）后放行大厅空状态引导，避免有 Agent 时闪现
      agentListLoaded.value = true
      // 首次拉取到 Agent 列表后恢复每个 pane 的内容（阶段 B；幂等，只执行一次）。
      // 仅在 socket 已连接时执行：内容恢复依赖文件系统/Git/终端等鉴权能力。
      if (socket.value) {
        restoreWorkspacePaneContents()
      }
    }
  }

  // 构造复制 Agent 的请求参数
  function buildCopiedAgentPayload(agent, copiedName, targetNodeId = undefined) {
    return {
      agent_type: agent.agent_type,
      working_dir: agent.working_dir,
      name: copiedName,
      llm_group: agent.llm_group || 'default',
      worktree: agent.agent_type === 'code_agent' ? Boolean(agent.worktree) : false,
      quick_mode: Boolean(agent.quick_mode),
      restore_session: Boolean(agent.restore_session),
      no_interaction_mode: Boolean(agent.no_interaction_mode),
      task: agent.task || '',
      node_id: targetNodeId || agent.node_id || undefined,
      proxy_node: agent.proxy_node || undefined,
    }

  }

  // 复制 Agent - 弹出创建面板并预填充参数
  async function copyAgent(agent) {
    // 先设置标志位，跳过 watch 中的名称设置和模型组自动选择
    skipNameWatch.value = true

    // 刷新模型组列表和节点状态（不自动选择模型组）
    await Promise.all([
      fetchModelGroups(agent?.node_id || 'master', false),
      fetchNodeStatus(),
      fetchUserList(),
      fetchUserAccessibleNodes(),
    ])

    // 填充表单变量
    newAgentType.value = agent.agent_type || 'code_agent'
    newAgentModelGroup.value = agent.llm_group || 'default'
    newCodeAgentWorktree.value = agent.agent_type === 'code_agent' ? Boolean(agent.worktree) : false
    newAgentQuickMode.value = Boolean(agent.quick_mode)
    newAgentRestoreSession.value = Boolean(agent.restore_session)
    newAgentNoInteractionMode.value = Boolean(agent.no_interaction_mode)
    newAgentTaskDescription.value = agent.task || ''
    newAgentProxyNode.value = agent.proxy_node || ''
    // 先设置 node_id（会触发 watch 重置目录），再设置正确的目录
    newAgentNodeId.value = String(agent?.node_id || '').trim() || getDefaultCreateAgentNodeId()
    newAgentDir.value = agent.working_dir || '~'
    // 设置正确的名称（Agent类型-创建时间格式）
    newAgentName.value = generateAgentName(agent.agent_type || 'code_agent')

    // 重置目录选择状态
    resetDirectorySelectionState()
    newAgentCreateError.value = ''

    // 打开创建弹窗
    showCreateAgentModal.value = true

    // 等待 DOM 更新后重置标志位
    await nextTick()
    skipNameWatch.value = false
  }


  // 批量复制 Agent
  async function batchCopyAgents() {
    const selectedIds = Array.from(selectedAgents.value)
    if (selectedIds.length === 0) {
      showToast('请先选择要复制的 Agent', 'warning')
      return
    }
    const selectedAgentList = agentList.value.filter(agent => selectedAgents.value.has(agent.agent_id))
    try {
      let successCount = 0
      let failCount = 0
      for (const agent of selectedAgentList) {
        try {
          const { host, port } = getGatewayAddress()
          const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
          const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'), {
            method: 'POST',
            body: JSON.stringify(
              buildCopiedAgentPayload(agent, generateAgentName(agent.agent_type || 'code_agent'), targetNodeId)
            )
          })
          if (response.ok) {
            successCount++
          } else {
            failCount++
          }
        } catch (error) {
          console.error(`[AGENT] Failed to copy agent ${agent.agent_id}:`, error)
          failCount++
        }
      }
      await fetchAgentList()
      selectedAgents.value.clear()
      selectedAgents.value = new Set()
      isBatchMode.value = false
      if (failCount === 0) {
        showToast(`成功复制 ${successCount} 个 Agent`, 'success')
      } else {
        showToast(`复制完成：成功 ${successCount} 个，失败 ${failCount} 个`, 'warning')
      }
    } catch (error) {
      console.error('[AGENT] Batch copy failed:', error)
      showToast('批量复制失败', 'error')
    }
  }

  // Agent 分组操作
  // 来自宠物大厅右键菜单：把单个 Agent 加入指定分组或新建分组
  function onLobbyAddAgentToGroup({ agentId, groupId, newGroupName } = {}) {
    if (!agentId) return
    const agent = agentList.value.find(a => a.agent_id === agentId)
    if (!agent) {
      showToast('Agent 不存在', 'error')
      return
    }
    if (isStoppedAgent(agent)) {
      showToast('已停止的 Agent 不能加入分组', 'warning')
      return
    }

    let group = null
    if (groupId) {
      group = agentGroups.value.find(g => g.id === groupId)
      if (!group) {
        showToast('分组不存在', 'error')
        return
      }
    } else {
      const trimmedName = String(newGroupName || '').trim()
      if (!trimmedName) {
        showToast('请输入分组名称', 'warning')
        return
      }
      group = {
        id: `group-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        name: trimmedName,
        agentIds: [],
      }
      agentGroups.value.push(group)
    }

    if (!group.agentIds) group.agentIds = []
    if (group.agentIds.includes(agentId)) {
      showToast(`该 Agent 已在「${group.name}」中`, 'info')
      return
    }
    group.agentIds.push(agentId)
    saveAgentGroups()
    showToast(`已加入「${group.name}」`, 'success')
  }

  // 来自宠物大厅右键菜单：把单个 Agent 从指定分组移出
  function onLobbyRemoveAgentFromGroup({ agentId, groupId } = {}) {
    if (!agentId || !groupId) return
    const group = agentGroups.value.find(g => g.id === groupId)
    if (!group || !Array.isArray(group.agentIds)) return
    const index = group.agentIds.indexOf(agentId)
    if (index === -1) {
      showToast('该 Agent 不在此分组中', 'info')
      return
    }
    group.agentIds.splice(index, 1)
    saveAgentGroups()
    showToast(`已从「${group.name}」移出`, 'success')
  }

  function addSelectedToGroup(groupId) {
    const group = agentGroups.value.find(g => g.id === groupId)
    if (!group) return
    if (!group.agentIds) group.agentIds = []
    // 只添加活跃的 agent，过滤已停止的
    const selectedIds = Array.from(selectedAgents.value).filter(agentId => {
      const agent = agentList.value.find(a => a.agent_id === agentId)
      return agent && !isStoppedAgent(agent)
    })
    if (selectedIds.length === 0) {
      showToast('没有可加入分组的活跃 Agent', 'warning')
      return
    }
    let added = 0
    selectedIds.forEach(agentId => {
      if (!group.agentIds.includes(agentId)) {
        group.agentIds.push(agentId)
        added++
      }
    })
    saveAgentGroups()
    selectedAgents.value.clear()
    selectedAgents.value = new Set()
    isBatchMode.value = false
    showToast(`已加入 ${added} 个 Agent 到「${group.name}」`, 'success')
  }

  function createGroupWithAgents(name) {
    const trimmedName = String(name || '').trim()
    if (!trimmedName) {
      showToast('请输入分组名称', 'warning')
      return
    }
    const group = {
      id: `group-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: trimmedName,
      agentIds: [],
    }
    const selectedIds = Array.from(selectedAgents.value).filter(agentId => {
      const agent = agentList.value.find(a => a.agent_id === agentId)
      return agent && !isStoppedAgent(agent)
    })
    selectedIds.forEach(agentId => {
      if (!group.agentIds.includes(agentId)) {
        group.agentIds.push(agentId)
      }
    })
    agentGroups.value.push(group)
    saveAgentGroups()
    selectedAgents.value.clear()
    selectedAgents.value = new Set()
    isBatchMode.value = false
    showToast(`已创建分组「${group.name}」并加入 ${group.agentIds.length} 个 Agent`, 'success')
  }

  // 重命名分组
  function renameAgentGroup({ groupId, name } = {}) {
    if (!groupId) return
    const trimmedName = String(name || '').trim()
    if (!trimmedName) {
      showToast('分组名称不能为空', 'warning')
      return
    }
    const group = agentGroups.value.find(g => g.id === groupId)
    if (!group) return
    if (group.name === trimmedName) return
    group.name = trimmedName
    saveAgentGroups()
    showToast(`分组已重命名为「${trimmedName}」`, 'success')
  }

  // 删除分组（仅删除分组本身，不影响其中的 Agent）
  function deleteAgentGroup(groupId) {
    if (!groupId) return
    const group = agentGroups.value.find(g => g.id === groupId)
    if (!group) return
    showConfirm(
      `确定删除分组「${group.name}」吗？`,
      () => {
        const index = agentGroups.value.findIndex(g => g.id === groupId)
        if (index === -1) return
        agentGroups.value.splice(index, 1)
        saveAgentGroups()
        showToast(`已删除分组「${group.name}」`, 'success')
      },
      null,
      false
    )
  }



  // 查看规则
  async function viewRules(agent) {
    if (!agent || !agent.agent_id) {
      console.warn('[RULES] Invalid agent:', agent)
      return
    }

    rulesLoading.value = true
    showRulesModal.value = true
    rulesContent.value = []
    rulesLoadedContent.value = ''

    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/rules`))

      if (!response.ok) {
        console.warn(`[RULES] Failed to fetch rules for agent ${agent.agent_id}:`, response.status)
        rulesContent.value = []
        rulesLoadedContent.value = ''
        return
      }

      const result = await response.json()
      const rules = result.rules || []
      // 已加载的规则置顶
      rulesContent.value = rules.sort((a, b) => {
        if (a.is_loaded === b.is_loaded) return 0
        return a.is_loaded ? -1 : 1
      })
      rulesLoadedContent.value = result.loaded_rules_content || ''
    } catch (error) {
      console.error('[RULES] Error fetching rules:', error)
      rulesContent.value = []
      rulesLoadedContent.value = ''
    } finally {
      rulesLoading.value = false
    }
  }

  async function exitNonInteractiveMode(agent) {
    if (!agent || !agent.agent_id) {
      console.warn('[EXIT NON-INTERACTIVE] Invalid agent:', agent)
      return
    }

    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/exit_non_interactive`), {
        method: 'POST'
      })

      if (!response.ok) {
        console.warn(`[EXIT NON-INTERACTIVE] Failed for agent ${agent.agent_id}:`, response.status)
        return
      }

      const result = await response.json()
      if (result.success) {
        // 更新本地状态
        const current = agentStatuses.value.get(agent.agent_id) || {}
        agentStatuses.value.set(agent.agent_id, {...current, non_interactive: false})
      } else {
        console.warn(`[EXIT NON-INTERACTIVE] Failed for agent ${agent.agent_id}:`, result.error || 'Unknown error')
      }
    } catch (error) {
      console.error(`[EXIT NON-INTERACTIVE] Error for agent ${agent.agent_id}:`, error)
    }
  }

  async function viewTools(agent) {
    if (!agent || !agent.agent_id) {
      console.warn('[TOOLS] Invalid agent:', agent)
      return
    }

    toolsLoading.value = true
    showToolsModal.value = true
    toolsContent.value = { all_tools: [], allowed_tools: null }

    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/tools`))

      if (!response.ok) {
        console.warn(`[TOOLS] Failed to fetch tools for agent ${agent.agent_id}:`, response.status)
        toolsContent.value = { all_tools: [], allowed_tools: null }
        return
      }

      const result = await response.json()
      const allTools = result.all_tools || []
      const allowedTools = result.allowed_tools

      // 如果有allowed_tools，将允许的工具排到顶部
      if (allowedTools && allowedTools.length > 0) {
        const allowedSet = new Set(allowedTools)
        allTools.sort((a, b) => {
          const aAllowed = allowedSet.has(a.name)
          const bAllowed = allowedSet.has(b.name)
          if (aAllowed && !bAllowed) return -1
          if (!aAllowed && bAllowed) return 1
          return 0
        })
      }

      toolsContent.value = {
        all_tools: allTools,
        allowed_tools: allowedTools
      }
    } catch (error) {
      console.error('[TOOLS] Error fetching tools:', error)
      toolsContent.value = { all_tools: [], allowed_tools: null }
    } finally {
      toolsLoading.value = false
    }
  }



  // 重命名 Agent
  function renameAgent(agent) {
    renamingAgent.value = agent
    renameAgentName.value = agent.name || ''
    showRenameAgentModal.value = true

    // 自动聚焦到输入框
    nextTick(() => {
      if (renameInput.value) {
        renameInput.value.focus()
        // 选中所有文本
        renameInput.value.select()
      }
    })
  }

  // 确认重命名
  async function confirmRename() {
    const agent = renamingAgent.value
    if (!agent) return

    const newName = renameAgentName.value.trim()

    try {
      const { host, port } = getGatewayAddress()

      const body = newName === '' 
        ? { name: null } 
        : { name: newName }

      const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agent.agent_id}`), {
        method: 'PATCH',
        body: JSON.stringify({ ...body, node_id: targetNodeId })
      })

      if (!response.ok) {
        const error = await response.json()
        alert(`重命名失败: ${error.error?.message || error.detail || '未知错误'}`)
        showRenameAgentModal.value = false
        return
      }

      await fetchAgentList()
      showToast('重命名成功', 'success')
      showRenameAgentModal.value = false
    } catch (error) {
      console.error('[AGENT] Rename failed:', error)
      alert(`重命名失败: ${error.message}`)
      showRenameAgentModal.value = false
    }
  }


  // 弹窗关闭后开启自动聚焦静默窗口：
  // 避免关闭瞬间挂起的异步状态同步（fetchAgentStatus）把焦点抢回输入框。
  // 注意：必须放在所有被监听的 ref 与 modalAutoFocusSuppressUntil 声明之后，
  // 否则 watch 注册时立即求值 getter 会命中 let/const 的暂时性死区（TDZ）而报错。
  watch([showRenameAgentModal, showEditAccessModal, showCreateAgentModal, showSettingsModal], (values, prevValues) => {
    const anyClosed = values.some((v, i) => !v && prevValues[i])
    if (anyClosed) {
      setModalAutoFocusSuppressUntil(Date.now() + MODAL_AUTOFOCUS_SUPPRESS_MS)
    }
  })

  async function editAgentAccess(agent) {
    editingAccessAgent.value = agent
    const acl = agent.access_acl || {}
    editAccessRead.value = Array.isArray(acl.read) ? [...acl.read] : []
    editAccessInteract.value = Array.isArray(acl.interact) ? [...acl.interact] : []
    showEditAccessModal.value = true
    // 获取用户列表供选择
    await fetchUserList()
  }

  async function saveAgentAccess() {
    const agent = editingAccessAgent.value
    if (!agent) return
    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(agent?.node_id || '').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agent.agent_id}/access`), {
        method: 'PUT',
        body: JSON.stringify({
          access_acl: {
            read: editAccessRead.value,
            interact: editAccessInteract.value,
          }
        })
      })
      if (!response.ok) {
        const error = await response.json()
        alert(`权限更新失败: ${error.error?.message || error.detail || '未知错误'}`)
        return
      }
      await fetchAgentList()
      showToast('权限更新成功', 'success')
      showEditAccessModal.value = false
    } catch (error) {
      console.error('[AGENT] Access update failed:', error)
      alert(`权限更新失败: ${error.message}`)
    }
  }



  // 删除 Agent
  async function deleteAgent(agentId) {
    showConfirm(
      '确认删除该 Agent？删除后将无法恢复，且会清除所有历史记录。',
      async () => {
        try {
          const { host, port } = getGatewayAddress()
          const agent = agentList.value.find(item => item.agent_id === agentId)
          const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'

          // 先删除服务端的 Agent 历史数据
          try {
            const historyKey = `agent_history_${agentId}`
            await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `data/${historyKey}`), {
              method: 'DELETE'
            })
          } catch (historyError) {
            console.warn('[HISTORY] Failed to delete server history for', agentId, ':', historyError.message)
            // 历史删除失败不影响后续 agent 删除流程
          }

          // 删除 Agent
          const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agentId}`), {
            method: 'DELETE'
          })

          const result = await response.json()

          if (!response.ok || !result.success) {
            alert(`删除失败：${result.error?.message || '未知错误'}`)
            return
          }


          // 清除该 Agent 的历史记录
          historyStorage.clearHistoryForAgent(agentId)
          // 清理孤儿消息与超限历史
          historyStorage.pruneHistory()

          // 清除该 Agent 的文件树状态
          fileTreeState.value.delete(agentId)
          fileTreeExpanded.value.delete(agentId)
          fileTreeLoading.value.delete(agentId)

          // 销毁该 Agent 对应的 Panel
          for (const panel of [...panels.value]) {
            if (panel.agentId === agentId) {
              closePanel(panel.id)
            }
          }

          // 如果是当前 Agent，清空当前 Agent ID
          if (currentAgentId.value === agentId) {
            currentAgentId.value = null
            outputs.value = []
            // 清空当前显示的历史偏移
            historyOffset.value = 0
            hasMoreHistory.value = true
          }

          // 刷新列表
          await fetchAgentList()
        } catch (error) {
          console.error('[AGENT] Delete failed:', error)
          alert(`删除失败: ${error.message}`)
        }
      }
    )
  }

  // 无损重生 Agent - 保存会话 → 删除 → 重建 → 恢复会话
  async function regenerateAgent(agent) {
    if (!agent || !agent.agent_id) return
    showConfirm(
      `确认无损重生 Agent「${agent.name || agent.agent_id}」？\n\n将保存当前会话后删除并重建，配置（模型组/工具组/任务等）将保留。`,
      async () => {
        try {
          const { host, port } = getGatewayAddress()
          const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'

          // 第一步：保存会话
          let sessionFile = null
          try {
            const saveResp = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/sessions/save`), {
              method: 'POST'
            })
            const saveResult = await saveResp.json()
            if (saveResp.ok && saveResult.success) {
              sessionFile = saveResult.session_file || saveResult.data?.session_file || null
            } else {
              console.warn('[REGENERATE] Session save failed:', saveResult)
            }
          } catch (saveError) {
            console.warn('[REGENERATE] Session save error:', saveError.message)
          }

          // 第二步：删除旧 Agent
          const delResp = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agent.agent_id}`), {
            method: 'DELETE'
          })
          const delResult = await delResp.json()
          if (!delResp.ok || !delResult.success) {
            alert(`重生失败（删除阶段）：${delResult.error?.message || '未知错误'}`)
            return
          }

          // 记录重生前该 Agent 是否已在某个 Panel 中，用于重生后恢复原状态
          const originalPanelId = panels.value.find(p => p.agentId === agent.agent_id)?.id || null

          // 清除本地状态
          historyStorage.clearHistoryForAgent(agent.agent_id)
          // 清理孤儿消息与超限历史
          historyStorage.pruneHistory()
          fileTreeState.value.delete(agent.agent_id)
          fileTreeExpanded.value.delete(agent.agent_id)
          fileTreeLoading.value.delete(agent.agent_id)
          // 仅解绑 Panel 与 Agent 的关联，保留 Panel 本身，便于重生后原位恢复
          if (originalPanelId) {
            closeAgentInPanel(originalPanelId)
          }
          if (currentAgentId.value === agent.agent_id) {
            currentAgentId.value = null
            outputs.value = []
            historyOffset.value = 0
            hasMoreHistory.value = true
          }

          // 第三步：用原配置重建（含恢复会话）
          const payload = {
            agent_type: agent.agent_type,
            working_dir: agent.working_dir,
            name: agent.name || undefined,
            llm_group: agent.llm_group || 'default',
            tool_group: agent.tool_group || 'default',
            config_file: agent.config_file || undefined,
            worktree: agent.agent_type === 'code_agent' ? Boolean(agent.worktree) : false,
            quick_mode: Boolean(agent.quick_mode),
            restore_session: sessionFile || Boolean(agent.restore_session),
            no_interaction_mode: Boolean(agent.no_interaction_mode),
            task: agent.task || undefined,
            node_id: targetNodeId,
            proxy_node: agent.proxy_node || undefined,
            access_acl: agent.access_acl || undefined,
          }
          const createResp = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'), {
            method: 'POST',
            body: JSON.stringify(payload)
          })
          const createResult = await createResp.json()
          if (!createResp.ok || !createResult.success) {
            alert(`重生失败（重建阶段）：${createResult.error?.message || createResult.detail || '未知错误'}`)
            return
          }

          showToast('Agent 无损重生成功', 'success')
          // 刷新列表
          await fetchAgentList()
          // 仅当重生前该 Agent 已在 Panel 中时，才在原 Panel 位置恢复打开
          if (createResult.data && originalPanelId) {
            const newAgent = {
              ...createResult.data,
              node_id: String(createResult.data?.node_id || '').trim() || 'master',
            }
            await openAgentInPanel(newAgent, originalPanelId)
          }
        } catch (error) {
          console.error('[REGENERATE] Failed:', error)
          alert(`重生失败: ${error.message}`)
        }
      }
    )
  }

  // 批量删除 Agent
  async function batchDeleteAgents() {
    const selectedIds = Array.from(selectedAgents.value)
    if (selectedIds.length === 0) {
      showToast('请先选择要删除的 Agent', 'warning')
      return
    }
    showConfirm(
      `确认删除选中的 ${selectedIds.length} 个 Agent？删除后将无法恢复，且会清除所有历史记录。`,
      async () => {
        try {
          let successCount = 0
          let failCount = 0
          for (const agentId of selectedIds) {
            try {
              const { host, port } = getGatewayAddress()
              const agent = agentList.value.find(item => item.agent_id === agentId)
              const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'

              // 先删除服务端的 Agent 历史数据
              try {
                const historyKey = `agent_history_${agentId}`
                await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `data/${historyKey}`), {
                  method: 'DELETE'
                })
              } catch (historyError) {
                console.warn('[HISTORY] Failed to delete server history for', agentId, ':', historyError.message)
                // 历史删除失败不影响后续 agent 删除流程
              }

              // 删除 Agent
              const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agentId}`), {
                method: 'DELETE'
              })
              const result = await response.json()
              if (response.ok && result.success) {
                successCount++
                // 清除该 Agent 的历史记录
                historyStorage.clearHistoryForAgent(agentId)
                // 清理孤儿消息与超限历史
                historyStorage.pruneHistory()
                // 清除该 Agent 的文件树状态
                fileTreeState.value.delete(agentId)
                fileTreeExpanded.value.delete(agentId)
                fileTreeLoading.value.delete(agentId)
                // 销毁该 Agent 对应的 Panel
                for (const panel of [...panels.value]) {
                  if (panel.agentId === agentId) {
                    closePanel(panel.id)
                  }
                }
                // 如果是当前 Agent，清空当前 Agent ID
                if (currentAgentId.value === agentId) {
                  currentAgentId.value = null
                  outputs.value = []
                  historyOffset.value = 0
                  hasMoreHistory.value = true
                }
              } else {
                failCount++
              }
            } catch (error) {
              console.error(`[AGENT] Failed to delete agent ${agentId}:`, error)
              failCount++
            }
          }

          // 刷新列表
          await fetchAgentList()
          // 清空选中状态并退出批量模式
          selectedAgents.value.clear()
          selectedAgents.value = new Set()
          isBatchMode.value = false
          // 显示结果提示
          if (failCount === 0) {
            showToast(`成功删除 ${successCount} 个 Agent`, 'success')
          } else {
            showToast(`删除完成：成功 ${successCount} 个，失败 ${failCount} 个`, 'warning')
          }
        } catch (error) {
          console.error('[AGENT] Batch delete failed:', error)
          showToast('批量删除失败', 'error')
        }
      }
    )
  }

  // 宠物大厅：点击某只宠物，进入该 Agent 的详细视图（打开面板）
  function onLobbySelectAgent(agentId) {
    const agent = agentList.value.find(a => a.agent_id === agentId)
    if (!agent) return
    openAgentInPanel(agent)
  }

  // 宠物大厅：获取某 Agent 的输入态（供大厅宠物输入框使用）
  // 返回 { mode: 'multi'|'single'|'confirm', tip, preset, isPassword, confirmMessage, confirmDefault }
  function getLobbyInputState(agentId) {
    const statusData = agentStatuses.value.get(agentId)
    const executionStatus = statusData?.execution_status || 'running'
    const confirmData = panelConfirmData.value.get(agentId)
    // 仅以 execution_status 判定确认态：panelConfirmData 只用于补充提示文案，
    // 不作为独立触发条件，避免残留数据让大厅显示默认的「请确认」
    if (executionStatus === 'waiting_confirm') {
      return {
        mode: 'confirm',
        tip: confirmData?.message || '请确认 (y/n)',
        preset: '',
        isPassword: false,
        confirmMessage: confirmData?.message || '请确认',
        confirmDefault: confirmData?.defaultConfirm !== false,
        // 是否有待处理的输入/确认请求：大厅据此决定展开宠物时是否自动聚焦输入框
        hasRequest: true,
      }
    }
    const request = inputRequests.value.get(agentId)
    if (request) {
      return {
        mode: request.mode === 'single' ? 'single' : 'multi',
        tip: request.tip || '',
        preset: request.preset || '',
        isPassword: !!request.is_password,
        confirmMessage: '',
        confirmDefault: true,
        hasRequest: true,
      }
    }
    return { mode: 'multi', tip: '', preset: '', isPassword: false, confirmMessage: '', confirmDefault: true, hasRequest: false }
  }

  // 宠物大厅：发送输入到指定 Agent
  // mode: 'multi'|'single' 时走 input_result；'confirm' 时走 confirm_result
  // 判断逻辑与 panel 的 sendFromPanel 保持一致：依据 execution_status 决定直接发送还是写入缓冲区
  function sendLobbyInput(agentId, text, mode = 'multi') {
    if (!agentId) return
    if (mode === 'confirm') {
      // 空输入视为确认（与 panel 行为一致）
      const trimmed = String(text || '').trim().toLowerCase()
      const confirmed = trimmed === '' || trimmed === 'y' || trimmed === 'yes' || trimmed === '确认' || trimmed === '是'
      getSendConfirmResult()(confirmed, agentId)
      return
    }
    // 记录到输入历史（与 panel 的 sendFromPanel 一致；空文本由 saveToHistory 内部跳过）
    saveToHistory(text)
    // 重置该 Agent 的历史翻阅游标，避免发送后仍停留在旧位置
    lobbyHistoryIndex.set(agentId, -1)
    lobbyHistoryTemp.delete(agentId)
    const statusData = agentStatuses.value.get(agentId)
    const executionStatus = statusData?.execution_status || 'running'
    const hasBuffered = inputBuffers.value.has(agentId) && (inputBuffers.value.get(agentId) || '').trim()
    // 单行输入或后端正在等待多行输入：直接发送
    if (mode === 'single' || executionStatus === 'waiting_multi') {
      let sendText = text
      if (hasBuffered) {
        const bufferedText = inputBuffers.value.get(agentId)
        inputBuffers.value.delete(agentId)
        sendText = text ? `${bufferedText}\n${text}` : bufferedText
      }
      getSendInputDirectly()(sendText, mode, agentId)
      return
    }
    // 有缓冲区内容且后端未等待输入：先发送缓冲区内容，本次输入也直接发送
    if (hasBuffered) {
      getSendBufferedInput()(agentId)
      if (text) {
        getSendInputDirectly()(text, mode, agentId)
      }
      return
    }
    // 后端未在等待输入（如运行中）：直接发送，不再写入缓冲区
    getSendInputDirectly()(text, mode, agentId)
  }

  // 宠物大厅：获取某 Agent 的最新一条可显示输出（markdown 渲染后的 html）
  function getLobbyLatestOutput(agentId) {
    const list = allOutputs.value.get(agentId)
    if (list && list.length > 0) {
      // 优先展示 Agent 的回复（STREAM）
      for (let i = list.length - 1; i >= 0; i--) {
        const item = list[i]
        if (item.output_type !== 'STREAM') continue
        if (!item.text) continue
        return { html: item.html || escapeHtml(item.text), outputType: item.output_type }
      }
      // 没有 STREAM 时，回退到最新一条有文本的消息（连接后即可见）
      for (let i = list.length - 1; i >= 0; i--) {
        const item = list[i]
        if (!item.text) continue
        return { html: item.html || escapeHtml(item.text), outputType: item.output_type }
      }
    }
    // 后台 Agent 的历史只写入 historyStorage，未同步到 allOutputs，这里回退读取
    const history = historyStorage.getHistoryForAgent(agentId)
    if (history && history.length > 0) {
      for (let i = history.length - 1; i >= 0; i--) {
        const item = history[i]
        if (!item.text) continue
        return { html: item.html || getRenderMessageHtml()(item), outputType: item.output_type }
      }
    }
    return null
  }

  // 宠物大厅：发送完成信号（与 Panel 的 completeFromPanel 行为一致）
  function onLobbyComplete(agentId) {
    if (!agentId) return
    const statusData = agentStatuses.value.get(agentId)
    const executionStatus = statusData?.execution_status || 'running'
    if (executionStatus === 'waiting_multi') {
      const message = {
        type: 'input_result',
        payload: {
          text: '__CTRL_C_PRESSED__',
          agent_id: agentId,
          display_name: chatName.value || username.value || '',
          input_mode: 'single',
        },
      }
      sendMessageToAgent(message, agentId)
    } else if (executionStatus === 'running') {
      // 与 Panel 的 Ctrl+C 行为一致：运行中且输入为空时发送人工介入消息
      sendMessageToAgent({ type: 'manual_interrupt', payload: {} }, agentId)
    } else {
      inputBuffers.value.set(agentId, '__CTRL_C_PRESSED__')
      getAppendOutput()({
        output_type: 'system',
        agent_name: 'system',
        text: '✅ 完成信号已保存到缓冲区，下次需要输入时自动触发',
        lang: 'text',
      }, agentId)
    }
  }

  // 切换当前工作的 Agent
  async function switchAgent(agent) {
    // 递增切换代数，使旧的switchAgent操作失效
    const thisGeneration = ++switchGeneration.value

    // 如果 Agent 已停止，不触发任何网络活动（不查询状态、不连接 WebSocket）
    if (agent.status === 'stopped') {
      // 只更新当前 agent ID，让用户可以看到该 agent 的本地历史记录
      currentAgentId.value = agent.agent_id
      // 更新 outputList 指向新 Panel 的 .messages 元素，并补绑滚动监听
      const stoppedTargetPanel = panels.value.find(p => p.agentId === agent.agent_id)
      const stoppedTargetOutputList = stoppedTargetPanel ? panelOutputLists.get(stoppedTargetPanel.id) : null
      if (stoppedTargetOutputList) {
        outputList.value = stoppedTargetOutputList
        setupHistoryScrollListener(stoppedTargetOutputList)
      }
      historyOffset.value = 0
      hasMoreHistory.value = true
      // 从本地存储加载历史消息（不涉及网络请求）
      loadHistoryMessages(false)
      return
    }

    if (agent.agent_id === currentAgentId.value) {
      const ws = sockets.value.get(agent.agent_id)
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        try {
          await getConnectToAgent()(agent)
          // 重连后消息同步完全依赖 sync_request 机制，不再手动加载历史
        } catch (error) {
          console.error(`[AGENT] Failed to reconnect:`, error)
          // 不中断流程，让用户看到错误
        }
      } else {
        // 检查本地记录的状态，如果需要恢复UI则恢复
        const localStatus = agentStatuses.value.get(agent.agent_id)
        if (localStatus?.execution_status) {
          // 恢复各种需要用户交互的状态
          if (localStatus.execution_status === 'waiting_confirm') {
            getRestoreWaitingConfirmUI()(agent.agent_id)
          } else if (localStatus.execution_status === 'waiting_single' || localStatus.execution_status === 'waiting_multi') {
            // 从Map中获取该Agent的输入请求
            const inputRequest = inputRequests.value.get(agent.agent_id)
            if (inputRequest) {
              inputTip.value = inputRequest.tip || ''
              inputMode.value = inputRequest.mode || 'multi'
              inputText.value = inputText.value || inputRequest.preset || ''
              pendingInputAgentId.value = agent.agent_id
              if (!isAnyModalOpen()) {
                nextTick(() => {
                  if (isAnyModalOpen()) return
                  const inputEl = document.querySelector(inputMode.value === 'multi' ? 'textarea' : 'input[type="text"]')
                  inputEl?.focus()
                })
              }
            } else {
              console.warn('[AGENT] No input request found in Map for this agent')
            }
          }
        }
      }
      return
    }

    // 注意：不关闭旧Agent的WebSocket连接，保留以便切回时复用
    // 旧连接断开时，onclose会检查currentAgentId，如果不是当前Agent则不重连
    const previousAgentId = currentAgentId.value

    // 清理当前agent的终端实例（切换离开时，从历史execution_chunks重建）
    if (previousAgentId) {
      let cleanedCount = 0
      getTerminals().value.forEach((termInfo) => {
        if (termInfo.agentId === previousAgentId && termInfo.terminal) {
          getDisposeExecutionTerminal()(termInfo)
          cleanedCount++
        }
      })
    }

    // 清理前一个Agent的terminalHosts引用
    if (previousAgentId) {
      let cleanedHostsCount = 0
      for (const [sessionKey, hostEl] of getTerminalHosts().value.entries()) {
        // sessionKey格式为 agentId:executionId
        const [agentId] = sessionKey.split(':')
        if (agentId === previousAgentId) {
          getTerminalHosts().value.delete(sessionKey)
          cleanedHostsCount++
        }
      }
    }


    // 清空当前Agent的输入状态（从Map中删除）
    const oldAgentId = currentAgentId.value
    if (oldAgentId) {
      inputRequests.value.delete(oldAgentId)
    }
    inputText.value = ''
    inputTip.value = ''
    inputMode.value = 'multi'

    // 更新当前 Agent ID
    currentAgentId.value = agent.agent_id

    // 更新 outputList 指向新 Panel 的 .messages 元素，并补绑滚动监听
    const targetPanel = panels.value.find(p => p.agentId === agent.agent_id)
    const targetOutputList = targetPanel ? panelOutputLists.get(targetPanel.id) : null
    if (targetOutputList) {
      outputList.value = targetOutputList
      setupHistoryScrollListener(targetOutputList)
    }

    // 重置历史偏移量和消息状态
    historyOffset.value = 0
    hasMoreHistory.value = true
    // 立即从本地加载该Agent 的历史消息，避免切换时页面空白
    loadHistoryMessages(false)

    // 先连接 Agent，在收到 ready 事件后再加载历史
    // 这样可以避免历史消息和 WebSocket 推送的缓存消息重复渲染
    try {
      // 切换后立即查询一次状态（即使 WebSocket 未连接）
      await fetchAgentStatus(agent)
      // 如果 Agent 已停止（已完成），不尝试连接 WebSocket
      if (agent.status === 'stopped') {
        return
      }
      // 等待连接稳定（Agent启动需要时间，有限重试）
      let stableConnection = false
      let retryCount = 0
      const maxStabilityRetries = 20 // 最大稳定性验证重试次数

      while (!stableConnection && retryCount < maxStabilityRetries) {
        // 检查是否有新的switchAgent调用
        if (switchGeneration.value !== thisGeneration) {
          return
        }

        // 只在连接不存在或已断开时才创建新连接
        const existingWs = sockets.value.get(agent.agent_id)
        if (!existingWs || existingWs.readyState !== WebSocket.OPEN) {
          // 清理已断开的旧连接
          if (existingWs && existingWs.readyState !== WebSocket.CLOSED) {
            existingWs.close()
          }
          if (existingWs) {
            sockets.value.delete(agent.agent_id)
          }
          try {
            await getConnectToAgent()(agent)
          } catch (e) {
            console.warn(`[AGENT] connectToAgent failed: ${e.message}`)
          }

          // 检查代数是否变化
          if (switchGeneration.value !== thisGeneration) {
            return
          }
        }

        // 验证连接是否稳定
        const ws = sockets.value.get(agent.agent_id)
        if (ws && ws.readyState === WebSocket.OPEN) {
          // 等待2000ms，确保连接稳定
          await new Promise(resolve => setTimeout(resolve, 2000))

          // 检查代数是否变化
          if (switchGeneration.value !== thisGeneration) {
            return
          }

          // 再次检查连接是否仍然有效
          if (ws.readyState === WebSocket.OPEN) {
            stableConnection = true
          } else {
            retryCount++
            console.warn(`[AGENT] Connection not stable after ${retryCount} tries, retrying...`)
            await new Promise(resolve => setTimeout(resolve, 2000))
          }
        } else {
          retryCount++
          console.warn(`[AGENT] Connection not established after ${retryCount} tries, retrying...`)
          await new Promise(resolve => setTimeout(resolve, 2000))
        }
      }

      if (!stableConnection) {
        console.warn(`[AGENT] Failed to establish stable connection after ${maxStabilityRetries} retries`)
      }


      // 最终检查WebSocket是否真正连接成功
      const ws = sockets.value.get(agent.agent_id)
      if (ws && ws.readyState === WebSocket.OPEN) {
        // 连接成功后再次查询状态，确保同步
        await fetchAgentStatus(agent)

        // 会话恢复对话框已禁用（用户反馈莫名弹出列表选择框）
        // 原逻辑：若历史为空则检测可恢复 session 并弹出 SessionDialog
        // 如需恢复，取消下方注释即可
        /*
        const currentOutputs = allOutputs.value.get(agent.agent_id) || []
        if (currentOutputs.length === 0) {
          try {
            const { host, port } = getGatewayAddress()
            const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
            const sessionsResponse = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agent.agent_id}/sessions`))
            const sessionsData = await sessionsResponse.json()
            if (sessionsData.success && sessionsData.data && sessionsData.data.length > 0) {
              availableSessions.value = sessionsData.data
              showSessionDialog.value = true
            } else {
            }
          } catch (error) {
            console.error('[AGENT] Failed to fetch sessions:', error)
          }
        } else {
        }
        */
      } else {
        console.warn('[AGENT] Connection verification failed, WebSocket not in OPEN state')
        // WebSocket 未连接，但已经通过 HTTP 查询了状态
      }
    } catch (error) {
      console.error('[AGENT] Failed to connect to agent:', error)
      // 连接失败，不加载历史消息，但保持当前状态
      // 用户可以看到错误并手动重试
      // 即使连接失败，状态已通过 HTTP 查询
    }
  }

  // 自动连接所有在线的 Agent（不切换当前选中的 Agent）

  // 定时刷新 Agent 列表
  let agentListRefreshInterval = null

  function startAgentListRefresh() {
    if (agentListRefreshInterval) {
      clearInterval(agentListRefreshInterval)
    }

    // 每 3 秒刷新一次
    agentListRefreshInterval = setInterval(() => {
      fetchAgentList()
    }, 3000)

    // 立即执行一次
    fetchAgentList()
  }

  function stopAgentListRefresh() {
    if (agentListRefreshInterval) {
      clearInterval(agentListRefreshInterval)
      agentListRefreshInterval = null
    }
  }

  // ========== Agent 管理方法结束 ==========

  return {
    // 域内 ref（App.vue 解构共享）
    dirDialogContext,
    showToolsModal,
    toolsContent,
    toolsLoading,
    showEditAccessModal,
    editingAccessAgent,
    editAccessRead,
    editAccessInteract,
    // 函数
    getStatusText,
    getStatusClass,
    isWaitingInput,
    fetchAgentStatus,
    syncOnlineAgentStatuses,
    getCreateAgentDirectoryNodeId,
    resetDirectorySelectionState,
    openDirDialog,
    fetchDirectories,
    selectDirectory,
    handleDirSearchKeydown,
    enterDirectory,
    goToParentDir,
    confirmDirectory,
    cancelDirDialog,
    openCreateAgentModal,
    onLobbyCreateAgentOnNode,
    fetchModelGroups,
    fetchUserAccessibleNodes,
    fetchUserPermissions,
    matchPermissionPattern,
    hasPermission,
    fetchNodeStatus,
    startNodeStatusRefresh,
    stopNodeStatusRefresh,
    fetchUserList,
    formatNodeOptionLabel,
    getDefaultTerminalNodeId,
    getAgentNodeLabel,
    getAgentNodeDisplayLabel,
    getAgentProxyNodeLabel,
    getCurrentAgentNodeId,
    getWorkspaceTargetNodeId,
    checkCodeAgentDirConflict,
    createAgentWithOptions,
    afterAgentCreated,
    createAgent,
    openQuickCreateAgent,
    openFullCreateAgentFromQuick,
    submitQuickCreateAgent,
    openCompletions,
    closeCompletionsWithoutSelect,
    handleCompletionKeydown,
    scrollToSelected,
    scrollToDirSelected,
    findVisiblePanelTextarea,
    insertAtPosition,
    insertCompletion,
    fetchAgentList,
    buildCopiedAgentPayload,
    copyAgent,
    batchCopyAgents,
    onLobbyAddAgentToGroup,
    onLobbyRemoveAgentFromGroup,
    addSelectedToGroup,
    createGroupWithAgents,
    renameAgentGroup,
    deleteAgentGroup,
    viewRules,
    exitNonInteractiveMode,
    viewTools,
    renameAgent,
    confirmRename,
    editAgentAccess,
    saveAgentAccess,
    deleteAgent,
    regenerateAgent,
    batchDeleteAgents,
    onLobbySelectAgent,
    getLobbyInputState,
    sendLobbyInput,
    getLobbyLatestOutput,
    onLobbyComplete,
    switchAgent,
    startAgentListRefresh,
    stopAgentListRefresh,
  }
}
