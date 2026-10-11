// Panel 会话面板 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 阶段3），保持行为完全一致。
// 覆盖 Panel 子域：
// - 状态查询：getPanelTerminals/getPanelTerminalHosts/getPanelInputDisabled/getPanelWaitingMultiDisabled/
//   getPanelStreamingMessages/getPanelHistoryState/getPanelLayout/getPanelHasBufferedInput
// - 交互：sendFromPanel/completeFromPanel/openCompletionsFromPanel/onLobbyOpenCompletions/
//   handlePanelInputChange/handlePanelKeydown/handlePanelPaste/clearBufferFromPanel
// - 引用绑定：setupHistoryScrollListener/setPanelOutputList/setPanelTerminalRef
// - 工作区承载：workspaceHostsChat/workspaceHostsTerminal/workspaceHostsSession/workspaceSessionPanelId/
//   workspaceHostedPanel/workspaceSessionPanel/visibleSessionAgentIds/embeddedPanelCount/hasNoPanel/
//   agentListLoaded/panelGridStyle
//
// 依赖注入：
// - 直传（定义在调用点之前）：computed/ref/watch/nextTick/showWorkspacePanel/sessionPanelRefs/panels/activePanelId/
//   historyScrollListenerEl/historyScrollHandler/historyScrollDebounceTimer/panelOutputLists/outputList/
//   inputMode/inputRequests/panelInputTexts/inputTip/panelInputModes/panelInputTips/panelConfirmData/inputBuffers/
//   sortCompletionItems/getPanelAgent/getPanelInputMode/saveToHistory/navigateHistory/username/getGatewayAddress/
//   buildNodeHttpUrl/fetchWithAuth/windowWidth/findWorkspacePaneByView/findWorkspacePaneBySessionPanelId/
//   workspaceMainView/workspacePaneTree
// - getter 注入（定义在调用点之后）：sendMessageToAgent/loadHistoryMessages/agentList/currentAgentId/agentStatuses/
//   maybeStartTour/chatName/completionAgentId/completionSource/completionCursorPos/completionHasAtSymbol/
//   completionSearch/showCompletions/completions/completionSearchInput/selectedIndex/streamingMessages/
//   isLoadingHistory/hasMoreHistory/terminals/terminalHosts/setTerminalRef/appendOutput/uploadImageToNode/
//   closeBufferPanelIfForAgent/sendBufferedInput/sendConfirmResult/handlePanelConfirm/handlePanelCancelConfirm/
//   isCursorAtFirstLine/isCursorAtLastLine
import { computed, ref, watch, nextTick } from 'vue'

export function usePanel({
  showWorkspacePanel,
  sessionPanelRefs,
  panels,
  activePanelId,
  historyScrollListenerEl,
  historyScrollHandler,
  historyScrollDebounceTimer,
  panelOutputLists,
  outputList,
  inputMode,
  inputText,
  inputRequests,
  panelInputTexts,
  inputTip,
  panelInputModes,
  panelInputTips,
  panelConfirmData,
  inputBuffers,
  sortCompletionItems,
  getPanelAgent,
  getPanelInputMode,
  saveToHistory,
  navigateHistory,
  username,
  getGatewayAddress,
  buildNodeHttpUrl,
  fetchWithAuth,
  windowWidth,
  findWorkspacePaneByView,
  findWorkspacePaneBySessionPanelId,
  workspaceMainView,
  workspacePaneTree,
  sendMessageToAgentGetter,
  loadHistoryMessagesGetter,
  agentListGetter,
  currentAgentIdGetter,
  agentStatusesGetter,
  maybeStartTourGetter,
  chatNameGetter,
  completionAgentIdGetter,
  completionSourceGetter,
  completionCursorPosGetter,
  completionHasAtSymbolGetter,
  completionSearchGetter,
  showCompletionsGetter,
  completionsGetter,
  completionSearchInputGetter,
  selectedIndexGetter,
  streamingMessagesGetter,
  isLoadingHistoryGetter,
  hasMoreHistoryGetter,
  terminalsGetter,
  terminalHostsGetter,
  setTerminalRefGetter,
  appendOutputGetter,
  uploadImageToNodeGetter,
  closeBufferPanelIfForAgentGetter,
  sendBufferedInputGetter,
  sendConfirmResultGetter,
  handlePanelConfirmGetter,
  handlePanelCancelConfirmGetter,
  isCursorAtFirstLineGetter,
  isCursorAtLastLineGetter,
}) {
  // 获取 Panel 的终端列表
  function getPanelTerminals(panel) {
    if (!panel || !panel.agentId) return []
    return terminalsGetter().value.filter(t => t.agentId === panel.agentId)
  }

  // 获取 Panel 的终端宿主
  function getPanelTerminalHosts(panel) {
    if (!panel || !panel.agentId) return new Map()
    const hosts = new Map()
    for (const [sessionKey, hostEl] of terminalHostsGetter().value.entries()) {
      const [agentId] = sessionKey.split(':')
      if (agentId === panel.agentId) {
        hosts.set(sessionKey, hostEl)
      }
    }
    return hosts
  }

  // 获取 Panel 的输入禁用状态
  function getPanelInputDisabled(panel) {
    if (!panel || !panel.agentId) return true
    const agent = getPanelAgent(panel)
    if (!agent || agent.status !== 'running') return true
    return false
  }

  // 获取 Panel 的等待多行禁用状态
  function getPanelWaitingMultiDisabled(panel) {
    if (!panel || !panel.agentId) return true
    const statusData = agentStatusesGetter().value.get(panel.agentId)
    const executionStatus = statusData?.execution_status || 'running'
    // 等待多行输入时不禁用（允许输入），其他状态禁用
    return executionStatus !== 'waiting_multi'
  }

  // 获取 Panel 的流式消息
  function getPanelStreamingMessages(panel) {
    if (!panel || !panel.agentId) return new Map()
    const msgs = new Map()
    for (const [agentId, msg] of streamingMessagesGetter().value.entries()) {
      if (agentId === panel.agentId) {
        msgs.set(agentId, msg)
      }
    }
    return msgs
  }

  // 获取 Panel 的历史加载状态
  function getPanelHistoryState(panel) {
    if (!panel || !panel.agentId) return { isLoading: false, hasMore: false }
    return {
      isLoading: isLoadingHistoryGetter().value,
      hasMore: hasMoreHistoryGetter().value
    }
  }

  // 编辑器主区域是否正在承载聊天室 / 终端（此时独立面板让位，避免同一状态被两个实例争抢）
  // 已统一为 pane 树：某个 pane 的 view === 'chat'/'terminal'（host 单例，至多一个）即视为承载。
  const workspaceHostsChat = computed(() =>
    showWorkspacePanel.value && !!findWorkspacePaneByView('chat')
  )
  const workspaceHostsTerminal = computed(() =>
    showWorkspacePanel.value && !!findWorkspacePaneByView('terminal')
  )
  // 编辑器主区域是否正在承载会话面板（此时网格中对应 panel 让位，避免同一 xterm host 被两实例争抢）
  const workspaceHostsSession = computed(() => showWorkspacePanel.value && workspaceMainView.value === 'session')
  // 编辑器主区域会话视图当前显示的 panel（由编辑器侧边栏 Agent 列表点击决定）
  const workspaceSessionPanelId = ref(null)
  // 编辑器当前占用的 panel：只要编辑器面板打开且已选定 panel，就让它从网格让位。
  // 不随主区域视图（file/chat/terminal/session）变化而回到网格，否则点 chat/终端时
  // 该 panel 会「凭空」出现在网格里，把布局挤乱（用户期望的是替换，而非并存）。
  const workspaceHostedPanel = computed(() => {
    if (!showWorkspacePanel.value || !workspaceSessionPanelId.value) return null
    // 已统一为 pane 树：panel 由某个 pane 承载时才让它从网格让位；
    // 若没有任何 pane 承载它（例如承载它的 pane 被切成了 file/chat/terminal），
    // 则回到网格渲染，避免 panel「凭空消失」。
    const hostingPane = findWorkspacePaneBySessionPanelId(workspaceSessionPanelId.value)
    if (!hostingPane) return null
    return panels.value.find(p => p.id === workspaceSessionPanelId.value) || null
  })
  // 编辑器会话视图对应的 panel：优先取记录的面板，回退到当前激活/首个已绑定 Agent 的面板
  const workspaceSessionPanel = computed(() => {
    if (!workspaceHostsSession.value) return null
    const byId = workspaceHostedPanel.value
    if (byId) return byId
    const active = panels.value.find(p => p.id === activePanelId.value && p.agentId)
    if (active) return active
    return panels.value.find(p => p.agentId) || null
  })

  // 「当前可见」的会话 Agent 集合：即此刻真正显示在界面上的 Agent 会话。
  // 注意：不能用「panel 对象是否持有 agentId」来判断——面板被收起（视图切回 file）后
  // panel.agentId 仍在，但会话已不可见。命令面板据此判断「选中它是否只是切回自身」：
  // 会话不可见时选中它是有意义的（重新打开），故不能置灰。
  const visibleSessionAgentIds = computed(() => {
    const ids = new Set()
    // 已统一为 pane 树：遍历 pane 树收集所有承载会话的 pane（未分割时唯一 leaf 也会被遍历到）。
    const walk = (node) => {
      if (!node) return
      if (node.type === 'leaf') {
        if (node.view === 'session' && node.sessionPanelId) {
          const panel = panels.value.find(p => p.id === node.sessionPanelId)
          if (panel && panel.agentId) ids.add(panel.agentId)
        }
        return
      }
      ;(node.children || []).forEach(walk)
    }
    walk(workspacePaneTree.value)
    return ids
  })

  // 网格内实际渲染的顶层子项数量（用于 panel-grid 的列/行布局）。
  // 注意：会话/终端/聊天面板一律只在编辑器面板内部渲染（或作为浮动面板），
  // 它们不是 panel-grid 的直接子项，因此绝不能计入网格布局，否则会出现
  // 「网格被切成两列、但只有一个子项」→ 编辑器只占半宽、右侧空白的现象。
  const embeddedPanelCount = computed(() => {
    // 网格唯一子项是编辑器面板（未打开时为空状态）
    return showWorkspacePanel.value ? 1 : 0
  })

  // 当前是否没有任何可见的内嵌 Panel（用于展示空状态欢迎背景）
  const hasNoPanel = computed(() => embeddedPanelCount.value === 0)
  // 是否已完成首次 Agent 列表拉取（无论成功失败）。
  // 声明位置需早于下方 immediate watch（否则 watch 立即求值会命中 TDZ）。
  const agentListLoaded = ref(false)

  // 首次进入宠物大厅（无任何可见 Panel）时展示大厅场景引导
  // 需等 Agent 列表首次拉取完成（agentListLoaded）后再触发：未登录时列表尚未拉取，
  // 登录弹窗正遮住大厅，此时弹引导既看不到、又会被误标记为已看过。
  watch([hasNoPanel, agentListLoaded], ([noPanel, loaded]) => {
    if (noPanel && loaded) maybeStartTourGetter()('lobby')
  }, { immediate: true })

  // 获取 Panel 的布局样式
  function getPanelLayout() {
    const count = embeddedPanelCount.value
    if (count === 0) return {}
    if (count === 1) return { gridTemplateColumns: '1fr', gridTemplateRows: '1fr' }
    if (count === 2) return { gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr' }
    if (count === 3) return { gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr' }
    if (count === 4) return { gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr' }
    if (count === 5) return { gridTemplateColumns: '1fr 1fr 1fr', gridTemplateRows: '1fr 1fr' }
    return { gridTemplateColumns: '1fr 1fr 1fr', gridTemplateRows: '1fr 1fr' }
  }

  // Panel 网格布局样式（计算属性）
  const panelGridStyle = computed(() => {
    return getPanelLayout()
  })

  // 获取 Panel 的缓冲输入状态
  function getPanelHasBufferedInput(panel) {
    if (!panel || !panel.agentId) return false
    return inputBuffers.value.has(panel.agentId)
  }

  // 从 Panel 发送消息
  function sendFromPanel(panel) {
    if (!panel || !panel.agentId) return
    const agentId = panel.agentId
    const agent = getPanelAgent(panel)
    if (!agent || agent.status !== 'running') return

    // 单行输入模式：允许发送空字符串
    // 多行输入模式：不允许发送空字符串（但缓冲区有内容时除外）
    const panelInput = panelInputTexts.value.get(agentId) || ''
    const panelInputMode = getPanelInputMode(panel)
    const hasBuffered = inputBuffers.value.has(agentId) && (inputBuffers.value.get(agentId) || '').trim()
    let userInput
    if (panelInputMode === 'single') {
      userInput = panelInput
    } else {
      userInput = panelInput.trim()
      if (!userInput && !hasBuffered) return
    }

    // 获取当前运行状态
    const statusData = agentStatusesGetter().value.get(agentId)
    const executionStatus = statusData?.execution_status || 'running'

    // 等待确认状态：Enter 发送确认结果
    if (executionStatus === 'waiting_confirm') {
      const trimmedInput = userInput.trim().toLowerCase()
      // 空输入或 y/yes/确认 视为确认，n/no/取消 视为取消
      const confirmed = trimmedInput === '' || trimmedInput === 'y' || trimmedInput === 'yes' || trimmedInput === '确认' || trimmedInput === '是'
      sendConfirmResultGetter()(confirmed, agentId)
      // 清空输入框
      panelInputTexts.value.set(agentId, '')
      inputText.value = ''
      return
    }

    // 判断是发送到缓冲区还是直接发送
    if (panelInputMode === 'single' || executionStatus === 'waiting_multi') {
      // 后端正在等待输入，直接发送
      // 如果有缓冲区内容，先发送缓冲区内容
      let sendText = userInput
      if (hasBuffered) {
        const bufferedText = inputBuffers.value.get(agentId)
        inputBuffers.value.delete(agentId)
        sendText = bufferedText
        // 如果输入框也有内容，追加到缓冲区内容后面
        if (userInput) {
          sendText = `${bufferedText}\n${userInput}`
        }
        // 缓冲已被消费：若缓存面板正显示该 Agent，关闭面板并重置编辑文本
        closeBufferPanelIfForAgentGetter()(agentId)
      }
      const message = {
        type: 'input_result',
        payload: {
          text: sendText,
          agent_id: agentId,
          display_name: chatNameGetter().value || username.value || '',
          input_mode: panelInputMode,
        },
      }
      sendMessageToAgentGetter()(message, agentId)
      // 从Map中删除该Agent的输入请求
      inputRequests.value.delete(agentId)
    } else if (hasBuffered) {
      // 有缓冲区内容且后端没有等待输入，发送缓冲区内容
      sendBufferedInputGetter()(agentId)
      // 如果输入框也有内容，追加到缓冲区
      if (userInput) {
        const existingText = inputBuffers.value.get(agentId) || ''
        const nextValue = existingText ? `${existingText}\n${userInput}` : userInput
        inputBuffers.value.set(agentId, nextValue)
        appendOutputGetter()({
          output_type: 'system',
          agent_name: 'system',
          text: '✓ 输入已追加到缓冲区，等待后端请求',
          lang: 'text',
        }, agentId)
      }
    } else {
      // 后端没有等待输入，保存到缓冲区
      const existingText = inputBuffers.value.get(agentId) || ''
      const nextValue = existingText ? `${existingText}\n${userInput}` : userInput
      inputBuffers.value.set(agentId, nextValue)
      appendOutputGetter()({
        output_type: 'system',
        agent_name: 'system',
        text: '✓ 输入已追加到缓冲区，等待后端请求',
        lang: 'text',
      }, agentId)
    }

    // 保存到历史记录
    saveToHistory(userInput)
    panelInputTexts.value.set(agentId, '')
    inputText.value = ''
  }

  // 从 Panel 完成输入
  function completeFromPanel(panel) {
    if (!panel || !panel.agentId) return
    const agentId = panel.agentId
    const statusData = agentStatusesGetter().value.get(agentId)
    const executionStatus = statusData?.execution_status || 'running'
    // 记住原始状态，确认/取消后恢复
    const originalStatus = executionStatus

    // 使用 Panel 内嵌确认，而非全局弹出对话框
    panelConfirmData.value.set(agentId, {
      message: '确定要发送完成信号吗？',
      defaultConfirm: true,
      onConfirm: () => {
        if (executionStatus === 'waiting_multi') {
          // 后端正在等待多行输入，直接发送 Ctrl+C 信号
          const message = {
            type: 'input_result',
            payload: {
              text: '__CTRL_C_PRESSED__',
              agent_id: agentId,
              display_name: chatNameGetter().value || username.value || '',
              input_mode: 'single',
            },
          }
          sendMessageToAgentGetter()(message, agentId)
        } else {
          // 后端没有等待输入，将完成信号保存到缓冲区
          inputBuffers.value.set(agentId, '__CTRL_C_PRESSED__')
          appendOutputGetter()({
            output_type: 'system',
            agent_name: 'system',
            text: '✅ 完成信号已保存到缓冲区，下次需要输入时自动触发',
            lang: 'text',
          }, agentId)
        }
        // 恢复输入模式为多行
        inputMode.value = 'multi'
        panelInputModes.value.set(agentId, 'multi')
        inputTip.value = ''
        panelInputTips.value.set(agentId, '')
        // 恢复 Agent 状态为原始状态
        agentStatusesGetter().value.set(agentId, {execution_status: originalStatus})
      },
      onCancel: () => {
        // 取消时恢复输入模式为多行
        inputMode.value = 'multi'
        panelInputModes.value.set(agentId, 'multi')
        inputTip.value = ''
        panelInputTips.value.set(agentId, '')
        // 恢复 Agent 状态为原始状态
        agentStatusesGetter().value.set(agentId, {execution_status: originalStatus})
      },
    })

    // 同步设置 waiting_confirm 状态，使 handlePanelKeydown 中 Enter/y/n 键可响应
    agentStatusesGetter().value.set(agentId, {execution_status: 'waiting_confirm'})
    // 确认请求使用单行输入模式，避免多行输入框抢占焦点
    inputMode.value = 'single'
    panelInputModes.value.set(agentId, 'single')
    inputTip.value = '确定要发送完成信号吗？ (Enter/y 确认, n 取消)'
    panelInputTips.value.set(agentId, '确定要发送完成信号吗？ (Enter/y 确认, n 取消)')

    // 聚焦输入框
    const sessionPanel = sessionPanelRefs.get(panel.id)
    if (sessionPanel?.focusInput) {
      sessionPanel.focusInput()
    }
  }

  // 从 Panel 打开补全
  async function openCompletionsFromPanel(panel) {
    if (!panel || !panel.agentId) return
    const agent = getPanelAgent(panel)
    if (!agent) {
      alert('请先选择一个 Agent')
      return
    }

    completionAgentIdGetter().value = panel.agentId
    completionSourceGetter().value = 'panel'
    // 由 @ 按钮触发时（未经过 handlePanelInputChange / handlePanelKeydown），
    // 输入框中并没有 @ 符号，需记录当前光标位置作为插入点，并标记无需删除 @
    if (completionCursorPosGetter().value === -1) {
      const textarea = document.querySelector(`.input-wrapper textarea[data-agent-id="${panel.agentId}"]`) || document.querySelector('.input-wrapper textarea')
      if (textarea) {
        completionCursorPosGetter().value = textarea.selectionStart
      }
      completionHasAtSymbolGetter().value = false
    }
    completionSearchGetter().value = ''
    selectedIndexGetter().value = -1
    showCompletionsGetter().value = true
    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(agent?.node_id || '').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `completions/${agent.agent_id}`))

      const result = await response.json()

      if (!response.ok) {
        alert(`获取补全列表失败: ${result.error?.message || result.detail || '未知错误'}`)
        return
      }

      if (result.success && result.data) {
        completionsGetter().value = sortCompletionItems(result.data)
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
        completionSearchInputGetter().value?.focus()
      })
    }
  }

  // 从宠物大厅输入框打开补全：agentId 为大厅中对应宠物，cursorPos 为 @ 符号位置
  async function onLobbyOpenCompletions(agentId, cursorPos) {
    if (!agentId) return
    const agent = agentListGetter().value.find(a => a.agent_id === agentId)
    if (!agent) return

    completionAgentIdGetter().value = agentId
    completionSourceGetter().value = 'lobby'
    completionCursorPosGetter().value = typeof cursorPos === 'number' ? cursorPos : -1
    completionHasAtSymbolGetter().value = true
    completionSearchGetter().value = ''
    selectedIndexGetter().value = -1
    showCompletionsGetter().value = true
    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(agent?.node_id || '').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `completions/${agentId}`))

      const result = await response.json()

      if (!response.ok) {
        alert(`获取补全列表失败: ${result.error?.message || result.detail || '未知错误'}`)
        return
      }

      if (result.success && result.data) {
        completionsGetter().value = sortCompletionItems(result.data)
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
        completionSearchInputGetter().value?.focus()
      })
    }
  }

  // 处理 Panel 输入变化
  function handlePanelInputChange(panel, event) {
    if (!panel || !panel.agentId) return
    const target = event.target
    // 更新该 Panel 的输入文本
    panelInputTexts.value.set(panel.agentId, target.value)
    // 同步全局输入文本（保持兼容）
    inputText.value = target.value
    const cursorPosition = target.selectionStart
    const textBeforeCursor = target.value.substring(0, cursorPosition)

    // 检测是否刚刚输入了@符号（包括中文输入法）
    // 注意：此处 @ 已真实写入输入框，故 completionHasAtSymbol 置 false，
    // 避免取消补全时 closeCompletionsWithoutSelect 再补插一个 @（导致出现两个 @）
    if (textBeforeCursor.endsWith('@')) {
      completionCursorPosGetter().value = cursorPosition - 1
      completionHasAtSymbolGetter().value = false
      openCompletionsFromPanel(panel)
    }
  }

  // 处理 Panel 键盘事件
  function handlePanelKeydown(panel, event) {
    if (!panel || !panel.agentId) return
    const agentId = panel.agentId

    // @ 键：打开补全列表
    if (event.key === '@') {
      event.preventDefault()
      completionCursorPosGetter().value = event.target.selectionStart
      completionHasAtSymbolGetter().value = true
      openCompletionsFromPanel(panel)
      return
    }

    // waiting_confirm 状态：y/n 键直接发送确认结果，Enter 键触发默认操作
    const statusData = agentStatusesGetter().value.get(agentId)
    const executionStatus = statusData?.execution_status || 'running'
    if (executionStatus === 'waiting_confirm') {
      if (event.key === 'y' || event.key === 'Y') {
        event.preventDefault()
        // 优先走 panelConfirmData 的 onConfirm 回调（如 completeFromPanel 场景）
        const confirmData = panelConfirmData.value.get(agentId)
        if (confirmData?.onConfirm) {
          handlePanelConfirmGetter()(panel)
        } else {
          sendConfirmResultGetter()(true, agentId)
        }
        return
      }
      if (event.key === 'n' || event.key === 'N') {
        event.preventDefault()
        // 优先走 panelConfirmData 的 onCancel 回调（如 completeFromPanel 场景）
        const confirmData = panelConfirmData.value.get(agentId)
        if (confirmData?.onCancel) {
          handlePanelCancelConfirmGetter()(panel)
        } else {
          sendConfirmResultGetter()(false, agentId)
        }
        return
      }
      if (event.key === 'Enter') {
        event.preventDefault()
        const confirmData = panelConfirmData.value.get(agentId)
        const defaultConfirm = confirmData?.defaultConfirm !== false
        if (defaultConfirm) {
          handlePanelConfirmGetter()(panel)
        } else {
          handlePanelCancelConfirmGetter()(panel)
        }
        return
      }
    }

    // 单行输入模式：Enter 键直接提交
    if (event.key === 'Enter' && !event.ctrlKey && getPanelInputMode(panel) === 'single') {
      event.preventDefault()
      sendFromPanel(panel)
      return
    }

    // Ctrl+Enter / Ctrl+D 提交输入
    if (event.ctrlKey && (event.key === 'Enter' || event.key.toLowerCase() === 'd')) {
      event.preventDefault()
      sendFromPanel(panel)
      return
    }

    // Alt+T 触发终端命令执行
    if (event.altKey && (event.code === 'KeyT' || event.key === 't' || event.key === 'T')) {
      event.preventDefault()
      event.stopPropagation()
      panelInputTexts.value.set(agentId, '__ALT_T_PRESSED__')
      sendFromPanel(panel)
      return
    }

    // Ctrl+C 在等待多行输入且输入框为空时，触发完成功能
    // Ctrl+C 在非输入模式下且输入框为空时，发送人工介入消息
    if (event.ctrlKey && event.key === 'c') {
      const userInput = (panelInputTexts.value.get(agentId) || '').trim()
      const statusData = agentStatusesGetter().value.get(agentId)
      const executionStatus = statusData?.execution_status || 'running'

      // 场景1：在等待多行输入且输入框为空时，触发完成功能
      if (executionStatus === 'waiting_multi' && !userInput) {
        event.preventDefault()
        completeFromPanel(panel)
        return
      }

      // 场景2：在非输入模式下（running）且输入框为空时，发送人工介入消息
      if (executionStatus === 'running' && !userInput) {
        event.preventDefault()
        const message = {
          type: 'manual_interrupt',
          payload: {},
        }
        sendMessageToAgentGetter()(message, agentId)
        return
      }
    }

    // 向上箭头：检查是否在第一行，是才触发历史
    // 带 Ctrl/Alt/Meta 修饰键时交由全局快捷键处理，不做历史导航
    if (event.key === 'ArrowUp') {
      if (event.ctrlKey || event.altKey || event.metaKey) return
      const textarea = event.target
      if (isCursorAtFirstLineGetter()(textarea)) {
        event.preventDefault()
        navigateHistory('up', agentId)
      }
      return
    }

    // 向下箭头：检查是否在最后一行，是才触发历史
    if (event.key === 'ArrowDown') {
      if (event.ctrlKey || event.altKey || event.metaKey) return
      const textarea = event.target
      if (isCursorAtLastLineGetter()(textarea)) {
        event.preventDefault()
        navigateHistory('down', agentId)
      }
      return
    }
  }

  // 处理 Panel 粘贴事件
  function handlePanelPaste(panel, event) {
    if (!panel || !panel.agentId) return
    const items = event.clipboardData?.items
    if (!items) return

    for (const item of items) {
      if (item.type.startsWith('image/')) {
        event.preventDefault()
        const file = item.getAsFile()
        if (file) {
          uploadImageToNodeGetter()(file, panel.agentId)
        }
        break
      }
    }
  }

  // 从 Panel 清空缓冲
  function clearBufferFromPanel(panel) {
    if (!panel || !panel.agentId) return
    const agentId = panel.agentId
    inputBuffers.value.delete(agentId)
    // 清空后若缓存面板正显示该 Agent，关闭面板并重置编辑文本
    closeBufferPanelIfForAgentGetter()(agentId)
    appendOutputGetter()({
      output_type: 'system',
      agent_name: 'system',
      text: '🗑 缓冲区已清空',
      lang: 'text',
    }, agentId)
  }

  // 设置滚动监听，实现滚动到顶部时加载更多历史
  // 支持动态切换滚动容器（Panel 创建/切换时调用）
  function setupHistoryScrollListener(el) {
    const SCROLL_THRESHOLD = 50 // 滚动到顶部50px以内触发
    const DEBOUNCE_DELAY = 500 // 防抖延迟500ms

    // 移除旧元素上的监听
    if (historyScrollListenerEl.value && historyScrollHandler.value) {
      historyScrollListenerEl.value.removeEventListener('scroll', historyScrollHandler.value)
    }

    // 清除旧的防抖定时器
    if (historyScrollDebounceTimer.value) {
      clearTimeout(historyScrollDebounceTimer.value)
      historyScrollDebounceTimer.value = null
    }

    if (!el) {
      historyScrollListenerEl.value = null
      historyScrollHandler.value = null
      return
    }

    historyScrollListenerEl.value = el
    historyScrollHandler.value = () => {
      // 清除之前的定时器
      if (historyScrollDebounceTimer.value) {
        clearTimeout(historyScrollDebounceTimer.value)
      }

      // 设置新的定时器
      historyScrollDebounceTimer.value = setTimeout(() => {
        const scrollTop = el.scrollTop
        if (scrollTop <= SCROLL_THRESHOLD && !isLoadingHistoryGetter().value && hasMoreHistoryGetter().value) {
          loadHistoryMessagesGetter()(true) // prepend = true, 插入到开头
        }
      }, DEBOUNCE_DELAY)
    }

    el.addEventListener('scroll', historyScrollHandler.value)
  }

  // 设置 Panel 的输出列表引用
  function setPanelOutputList(panel, el) {
    if (!panel || !panel.agentId) return
    panelOutputLists.value.set(panel.id, el)
    if (panel.agentId === currentAgentIdGetter().value) {
      outputList.value = el
      // Panel 动态创建后补绑滚动监听，确保滚动到顶部可加载历史
      setupHistoryScrollListener(el)
    }
  }

  // 设置 Panel 的终端引用
  function setPanelTerminalRef(panel, executionId, el, agentId) {
    if (!panel || !panel.agentId) return
    const targetAgentId = agentId || panel.agentId
    if (!executionId) return
    // 委托给 setTerminalRef：统一处理 xterm 的初始化/重建/清理
    setTerminalRefGetter()(executionId, el, targetAgentId)
  }

  return {
    getPanelTerminals,
    getPanelTerminalHosts,
    getPanelInputDisabled,
    getPanelWaitingMultiDisabled,
    getPanelStreamingMessages,
    getPanelHistoryState,
    getPanelLayout,
    getPanelHasBufferedInput,
    sendFromPanel,
    completeFromPanel,
    openCompletionsFromPanel,
    onLobbyOpenCompletions,
    handlePanelInputChange,
    handlePanelKeydown,
    handlePanelPaste,
    clearBufferFromPanel,
    setupHistoryScrollListener,
    setPanelOutputList,
    setPanelTerminalRef,
    workspaceHostsChat,
    workspaceHostsTerminal,
    workspaceHostsSession,
    workspaceSessionPanelId,
    workspaceHostedPanel,
    workspaceSessionPanel,
    visibleSessionAgentIds,
    embeddedPanelCount,
    hasNoPanel,
    agentListLoaded,
    panelGridStyle,
  }
}
