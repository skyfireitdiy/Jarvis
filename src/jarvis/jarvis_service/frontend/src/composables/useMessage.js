// 消息处理 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 阶段3），保持行为完全一致。
// 覆盖消息处理域：
// - handleMessage：WebSocket 消息分发（ready/sync_response/input_result/output/input_request/confirm/execution/terminal_created/terminal_closed/error/pipeline_event/status_update/file_upload_response/editor_open_file/eval_js_request/chat_*）
// - appendOutput/renderMessageHtml：消息渲染与追加
// - 输入处理：sendInputDirectly/sendInputResult/sendBufferedInput/sendConfirmResult/insertTextAtCursor/updateInputBuffer/appendToInputBuffer
// - 缓冲区：clearBuffer/loadBufferToInput/saveBufferEdit/closeBufferPanelIfForAgent
// - 其他：copyToClipboard/uploadImageToNode/handleFileUploadResponse/scrollSessionToBottom/sendSelectionToAgent/getEditorSelection/handleEditorOpenFile/handleEvalJsRequest/safeSerialize
//
// 依赖注入：
// - 直传（定义在调用点之前）：outputList/currentAgentId/inputText/inputBuffers/panelConfirmData/inputMode/agentStatuses/
//   panelInputTexts/inputRequests/agentList/allOutputs/pendingConfirmAgentId/pendingInputAgentId/panels/sockets/inputTip/
//   panelInputTips/panelInputModes/streamingMessages/bufferPanelAgentId/bufferEditText/panelOutputLists/chatName/username/
//   showBufferPanel/panelInputPasswords/sessionPanelRefs/confirmDialog/historyOffset/hasMoreHistory/auth/showConnectModal/
//   pipelineStore/notifyOnExit/notifyOnInput + 函数 isCurrentAgent/isAutoScrollEnabled/isAnyModalOpen/showToast/
//   sendSystemNotification/notifyInputRequest/handleAutoRead/sendMessageToAgent/loadHistoryMessages/getActiveWorkspaceView/
//   onPipelineEvent/handleChatMessage/resolveAgentRelativePath/openWorkspaceFile/getGatewayAddress/buildNodeHttpUrl/fetchWithAuth/showConfirm
//   + useTerminal 返回（调用点在 useMessage 之前）：terminalSessions/appendExecution/getExecutionSessionKey/
//   isCreatingTerminalSession/terminalCreationTracker/activeTerminalId/independentTerminalHosts/initIndependentTerminal/
//   attachTerminalSession/closeTerminal
// - getter 注入（定义在调用点之后）：connectErrorMessage（useGatewayConnection 返回）
import { nextTick } from 'vue'
import * as monaco from 'monaco-editor/esm/vs/editor/editor.main.js'
import { marked } from 'marked'
import { renderSideBySideDiff, escapeHtml } from '../diffRenderer.js'
import historyStorage from '../historyStorage.js'
/* global ElMessage */

export function useMessage({
  outputList,
  currentAgentId,
  inputText,
  inputBuffers,
  panelConfirmData,
  inputMode,
  agentStatuses,
  panelInputTexts,
  inputRequests,
  agentList,
  allOutputs,
  pendingConfirmAgentId,
  pendingInputAgentId,
  panels,
  sockets,
  socket,
  inputTip,
  panelInputTips,
  panelInputModes,
  streamingMessages,
  bufferPanelAgentId,
  bufferEditText,
  panelOutputLists,
  chatName,
  username,
  showBufferPanel,
  panelInputPasswords,
  sessionPanelRefs,
  confirmDialog,
  historyOffset,
  hasMoreHistory,
  auth,
  showConnectModal,
  pipelineStore,
  notifyOnExit,
  notifyOnInput,
  isCurrentAgent,
  isAutoScrollEnabled,
  isAnyModalOpen,
  showToast,
  sendSystemNotification,
  notifyInputRequest,
  handleAutoRead,
  sendMessageToAgent,
  loadHistoryMessages,
  getActiveWorkspaceView,
  onPipelineEvent,
  handleChatMessage,
  resolveAgentRelativePath,
  openWorkspaceFile,
  getGatewayAddress,
  buildNodeHttpUrl,
  fetchWithAuth,
  showConfirm,
  terminalSessions,
  appendExecution,
  getExecutionSessionKey,
  isCreatingTerminalSession,
  terminalCreationTracker,
  activeTerminalId,
  independentTerminalHosts,
  initIndependentTerminal,
  attachTerminalSession,
  closeTerminal,
  connectErrorMessageGetter,
  ensureAgentEditorPane,
  editorModels,
}) {
function syncAgentInputMode(targetAgentId, payload) {
  if (!targetAgentId) return
  inputTip.value = payload.tip || ''
  inputMode.value = payload.mode || 'multi'
  if (payload.preset) {
    inputText.value = payload.preset
  }
  // 同步到 Panel 隔离状态
  panelInputTips.value.set(targetAgentId, payload.tip || '')
  panelInputModes.value.set(targetAgentId, payload.mode || 'multi')
  panelInputPasswords.value.set(targetAgentId, payload.is_password || false)
  if (payload.preset) {
    panelInputTexts.value.set(targetAgentId, payload.preset)
  }
  pendingInputAgentId.value = targetAgentId
}

function handleMessage(message, agentId = null) {
  const { type, payload, seq } = message
  // 调试：记录所有收到的消息类型


  // 确定目标 Agent ID：优先使用传入的 agentId，否则使用 currentAgentId
  const targetAgentId = agentId || currentAgentId.value
  
  // seq 已随消息保存到历史记录中，无需单独维护
  
  if (type === 'ready') {
    // Agent 连接已建立并准备就绪
    // 消息同步完全依赖 sync_request 机制，不再手动加载历史或清空消息

    // 恢复当前Agent的输入请求状态（从Map中获取）
    const currentAgentIdLocal = targetAgentId
    const inputRequest = inputRequests.value.get(currentAgentIdLocal)
    if (inputRequest) {
      inputTip.value = inputRequest.tip || ''
      inputMode.value = inputRequest.mode || 'multi'
      inputText.value = inputText.value || inputRequest.preset || ''
      // 同步到 Panel 隔离状态
      panelInputTips.value.set(currentAgentIdLocal, inputRequest.tip || '')
      panelInputModes.value.set(currentAgentIdLocal, inputRequest.mode || 'multi')
      panelInputPasswords.value.set(currentAgentIdLocal, inputRequest.is_password || false)
      if (inputRequest.preset) {
        panelInputTexts.value.set(currentAgentIdLocal, inputRequest.preset)
      }
      pendingInputAgentId.value = currentAgentIdLocal
      // 弹窗打开时不抢焦点（避免恢复输入状态时夺走用户正在操作的焦点）
      if (!isAnyModalOpen()) {
        nextTick(() => {
          if (isAnyModalOpen()) return
          const inputEl = document.querySelector(inputMode.value === 'multi' ? 'textarea' : 'input[type="text"]')
          inputEl?.focus()
        })
      }
    }
  } else if (type === 'sync_response') {
    // 处理同步响应，一次性接收多条历史消息（增量模式）
    const messages = payload?.messages || []
    // 与本地历史按 seq 去重合并后保存
    if (messages.length > 0) {
      // 获取本地已有消息，按 seq 建立索引
      const localMessages = historyStorage.getHistoryForAgent(targetAgentId)
      const seqMap = new Map()
      for (const msg of localMessages) {
        if (typeof msg.seq === 'number') {
          seqMap.set(msg.seq, msg)
        }
      }
      // 合并远程消息（远程消息覆盖同 seq 的本地消息）
      // stream 消息合并：将 STREAM_START/STREAM_CHUNK/STREAM_END 合并为一条消息
      const streamAccumulator = new Map() // agent_id -> { streamingMessage, lastSeq }
      for (const rawMsg of messages) {
        // 将 {type, payload, seq} 格式转换为扁平格式 {output_type, text, ..., seq}
        let msg = rawMsg.payload
          ? { ...rawMsg.payload, seq: rawMsg.seq, type: rawMsg.type }
          : rawMsg
        // 补充 input_result 消息的显示字段，与实时消息处理保持一致
        if (rawMsg.type === 'input_result' && !msg.output_type) {
          // 过滤 Ctrl+C 哨兵值，不回显到聊天窗口
          if (msg.text === '__CTRL_C_PRESSED__') {
            continue
          }
          msg.output_type = 'user_input'
          msg.agent_name = 'user'
        }

        // 处理 stream 消息：合并为一条最终消息
        const outputType = msg.output_type
        if (outputType === 'STREAM_START') {
          const agentId = msg.context?.agent_id || msg.agent_id || targetAgentId
          streamAccumulator.set(agentId, {
            output_type: 'STREAM',
            text: '',
            lang: 'markdown',
            agent_name: msg.context?.agent_name || msg.agent_name || '',
            model_name: msg.context?.model_name || '',
            timestamp: msg.timestamp || null,
            context: msg.context || {},
            seq: msg.seq,
          })
          continue
        } else if (outputType === 'STREAM_CHUNK') {
          const agentId = msg.context?.agent_id || msg.agent_id || targetAgentId
          const acc = streamAccumulator.get(agentId)
          if (acc) {
            acc.text += msg.text || ''
            if (typeof msg.seq === 'number') {
              acc.seq = msg.seq // 使用最后一个 chunk 的 seq
            }
          }
          continue
        } else if (outputType === 'STREAM_END') {
          const agentId = msg.context?.agent_id || msg.agent_id || targetAgentId
          const acc = streamAccumulator.get(agentId)
          if (acc) {
            if (typeof msg.seq === 'number') {
              acc.seq = msg.seq
            }
            if (typeof acc.seq === 'number') {
              seqMap.set(acc.seq, acc)
            } else {
              seqMap.set(`_no_seq_${Date.now()}_${Math.random()}`, acc)
            }
            streamAccumulator.delete(agentId)
          }
          continue
        }

        if (typeof msg.seq === 'number') {
          seqMap.set(msg.seq, msg)
        } else {
          // 无 seq 的消息直接追加
          seqMap.set(`_no_seq_${Date.now()}_${Math.random()}`, msg)
        }
      }
      // 处理未收到 STREAM_END 的残留流式消息（异常情况）
      for (const acc of streamAccumulator.values()) {
        if (typeof acc.seq === 'number') {
          seqMap.set(acc.seq, acc)
        } else {
          seqMap.set(`_no_seq_${Date.now()}_${Math.random()}`, acc)
        }
      }
      // 按 seq 排序后保存
      const mergedMessages = Array.from(seqMap.values()).sort((a, b) => {
        const seqA = typeof a.seq === 'number' ? a.seq : 0
        const seqB = typeof b.seq === 'number' ? b.seq : 0
        return seqA - seqB
      })
      historyStorage.setHistoryForAgent(targetAgentId, mergedMessages)
      // 清空当前消息列表，强制从本地存储重新加载完整历史
      // 这样可以确保同步后的历史正确显示，避免与现有消息合并导致的问题
      if (targetAgentId === currentAgentId.value) {
        allOutputs.value.set(targetAgentId, [])
        historyOffset.value = 0
        hasMoreHistory.value = true
      }
      loadHistoryMessages(false)
    }
  } else if (type === 'input_result') {
    // 重连时后端发送的输入缓存，回显用户输入到聊天窗口
    const inputText = payload?.text
    if (inputText && inputText !== '__CTRL_C_PRESSED__') {
      appendOutput({
        output_type: 'user_input',
        agent_name: 'user',
        text: inputText,
        lang: 'text',
        seq: seq, // 传递 seq
      }, targetAgentId)
    }
  } else if (type === 'output') {
    const outputType = payload?.output_type
    
    // 处理流式输出
    if (outputType === 'STREAM_START') {
      // 创建当前 Agent 的流式消息
      const currentOutputs = allOutputs.value.get(targetAgentId) || []
      const streamingMessage = {
        output_type: 'STREAM',
        text: '',
        lang: 'markdown',
        agent_name: payload?.context?.agent_name || payload?.agent_name || '',
        model_name: payload?.context?.model_name || '',
        timestamp: payload?.timestamp || null,
        context: payload?.context || {},
        isStreaming: true
      }
      streamingMessages.value.set(targetAgentId, streamingMessage)
      currentOutputs.push(streamingMessage)
    } else if (outputType === 'STREAM_CHUNK') {
      // 追加到当前 Agent 的流式消息
      const streamingMessage = streamingMessages.value.get(targetAgentId)
      if (streamingMessage) {
        streamingMessage.text += payload.text || ''
        // 使用 renderMessageHtml 确保流式消息和历史消息使用相同的渲染逻辑
        streamingMessage.html = renderMessageHtml(streamingMessage)
        // 流式消息触发滚动（自动滚动开启时），只滚动该 Agent 自己的容器；
        // 仅当该 Agent 就是当前查看的 Agent 且无独立 Panel 容器时，才回退到 outputList，
        // 避免后台 Agent 的流式输出把用户正在查看的其他 Agent 视图滚到底。
        nextTick(() => {
          if (!isAutoScrollEnabled(targetAgentId)) return
          const targetPanel = panels.value.find(p => p.agentId === targetAgentId)
          const targetOutputList = targetPanel ? panelOutputLists.get(targetPanel.id) : null
          const scrollEl = targetOutputList || (isCurrentAgent(targetAgentId) ? outputList.value : null)
          if (scrollEl) {
            scrollEl.scrollTop = scrollEl.scrollHeight
          }
        })
      } else {
        console.warn('[STREAM] Received chunk but no streaming message found for agent:', targetAgentId)
      }
    } else if (outputType === 'STREAM_END') {
      const streamingMessage = streamingMessages.value.get(targetAgentId)
      if (streamingMessage) {
        // 从当前 Agent 的 outputs 数组中删除流式消息
        const currentOutputs = allOutputs.value.get(targetAgentId) || []
        const index = currentOutputs.indexOf(streamingMessage)
        if (index !== -1) {
          currentOutputs.splice(index, 1)
        }
        // 清除当前 Agent 的流式消息引用
        streamingMessages.value.delete(targetAgentId)
      } else {
        console.warn('[STREAM] Received end but no streaming message found for agent:', targetAgentId)
      }
    } else {
      // 普通输出，传递 seq
      appendOutput({ ...payload, seq: seq }, targetAgentId)
    }
  } else if (type === 'input_request') {

    const requestAgentId = targetAgentId
    pendingInputAgentId.value = requestAgentId

    // 检查当前是否处于 waiting_confirm 状态，如果是则跳过状态更新（不覆盖确认状态）
    const currentStatus = requestAgentId ? agentStatuses.value.get(requestAgentId)?.execution_status : null
    if (currentStatus === 'waiting_confirm') {
      return
    }

    // 根据 mode 设置 agentStatuses
    if (requestAgentId && payload.mode) {
      const statusKey = payload.mode === 'multi' ? 'waiting_multi' : 'waiting_single'
      agentStatuses.value.set(requestAgentId, {execution_status: statusKey})
    }
    
    // 检查缓冲区是否有内容
    if (requestAgentId && inputBuffers.value.has(requestAgentId)) {
      // 完成信号 (__CTRL_C_PRESSED__) 只发送给多行输入
      const bufferedText = inputBuffers.value.get(requestAgentId)
      const isCompletionSignal = bufferedText === '__CTRL_C_PRESSED__'
      const isMultiLineRequest = payload.mode === 'multi'
      
      if (isCompletionSignal && !isMultiLineRequest) {
        // 完成信号不能发送给单行输入（如确认对话框），清空缓冲区
        inputBuffers.value.delete(requestAgentId)
      } else {
        // 普通输入或匹配的多行输入，发送缓冲区内容
        inputBuffers.value.delete(requestAgentId)
        sendInputResult(bufferedText, payload.request_id, requestAgentId, payload.mode)
      }
      // 缓冲区内容已消费，但输入模式仍需同步（否则多行输入框不会即时切为单行）
      if (isCurrentAgent(targetAgentId)) {
        syncAgentInputMode(targetAgentId, payload)
      }
      return
    }
    
    // 保存输入请求到Map中，用于重连后恢复和Agent切换
    const hadPendingRequest = inputRequests.value.has(targetAgentId)
    inputRequests.value.set(targetAgentId, {
      tip: payload.tip || '',
      mode: payload.mode || 'multi',
      preset: payload.preset || '',
      is_password: payload.is_password || false,
      request_id: payload.request_id
    })

    // 提示音：以 input_request 为准确触发信号（每次真正请求输入都会到达）
    // 若该 Agent 已有待处理请求（如重连恢复时重复推送），则跳过避免重复播放
    if (!hadPendingRequest) {
      notifyInputRequest()
      // 自动朗读：以 input_request 为准确触发信号（每次真正请求输入都会到达）
      handleAutoRead(targetAgentId, payload.mode === 'multi' ? 'waiting_multi' : 'waiting_single')
    }
    
    // 如果是当前Agent，更新全局UI状态并显示输入框
    if (isCurrentAgent(targetAgentId)) {
      syncAgentInputMode(targetAgentId, payload)
      // 聚焦输入框（弹窗或宠物环形菜单打开时不抢焦点）
      const targetPanel = panels.value.find(p => p.agentId === targetAgentId)
      const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
      if (sp?.focusInput && !isAnyModalOpen()) sp.focusInput()

    }
    
    // 检查是否在底部（用于判断是否需要在显示输入框后滚动）
    const SCROLL_THRESHOLD = 50 // 50px 的容差
    let shouldScrollAfterInputShow = false
    if (outputList.value) {
      const scrollTop = outputList.value.scrollTop
      const scrollHeight = outputList.value.scrollHeight
      const clientHeight = outputList.value.clientHeight
      // 如果已经接近底部，则记录需要在显示输入框后滚动
      shouldScrollAfterInputShow = (scrollTop + clientHeight >= scrollHeight - SCROLL_THRESHOLD)
    }
    
    nextTick(() => {
      
      // 输入框显示后，如果之前在底部且请求属于当前 Agent，就滚动到底部（且自动滚动开启时）
      if (isCurrentAgent(requestAgentId) && shouldScrollAfterInputShow && outputList.value && isAutoScrollEnabled(requestAgentId)) {
        requestAnimationFrame(() => {
          const scrollHeight = outputList.value.scrollHeight
          const scrollTop = outputList.value.scrollTop
          const clientHeight = outputList.value.clientHeight
          outputList.value.scrollTop = scrollHeight
        })
      }
    })
  } else if (type === 'confirm') {
    // 确认请求同样视为需要输入，无条件播放提示音
    notifyInputRequest()

    pendingConfirmAgentId.value = targetAgentId
    // 更新 Agent 状态为 waiting_confirm
    agentStatuses.value.set(targetAgentId, {execution_status: 'waiting_confirm'})

    // 更新 Panel 内嵌确认数据（按 agentId 隔离）
    panelConfirmData.value.set(targetAgentId, {
      message: payload.message || '请确认',
      defaultConfirm: payload.default !== undefined ? payload.default : true
    })

    // 确认请求使用单行输入模式，避免多行输入框抢占焦点
    inputMode.value = 'single'
    panelInputModes.value.set(targetAgentId, 'single')
    inputTip.value = payload.message || '请确认 (y/n/Enter)'
    panelInputTips.value.set(targetAgentId, payload.message || '请确认 (y/n/Enter)')
    // 聚焦输入框（仅当前 Agent 且无弹窗时，避免其他 Agent 的确认请求抢焦点）
    const targetPanel = panels.value.find(p => p.agentId === targetAgentId)
    const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
    if (sp?.focusInput && isCurrentAgent(targetAgentId) && !isAnyModalOpen()) sp.focusInput()
    // 无 Panel 时不弹全局对话框，确认请求静默等待，用户打开 Panel 后可见 confirm 控件
  } else if (type === 'execution') {
    appendExecution(payload, targetAgentId)
    // 只在首次创建终端时创建输出项
    const executionId = payload?.execution_id || 'default'
    const executionSessionKey = getExecutionSessionKey(targetAgentId, executionId)
    const currentOutputs = allOutputs.value.get(targetAgentId) || []
    const existingItem = currentOutputs.find(
      item => item.output_type === 'execution' && item.execution_id === executionId
    )
    // 独立终端（execution_id 以 'terminal_' 开头）不需要创建聊天消息
    // 因为它们的输出会直接写入终端面板，由 appendExecution 处理
    if (!existingItem && !executionId.startsWith('terminal_')) {
      appendOutput({
        output_type: 'execution',
        text: '',
        lang: 'text',
        payload: payload, // 保存 payload 以便后续使用
        execution_id: executionId,
      }, targetAgentId)
      // 终端初始化由模板 :ref 回调自动触发 setTerminalRef，无需手动调用
    }
  } else if (type === 'terminal_created') {
    // 独立终端创建成功
    isCreatingTerminalSession.value = false
    const terminalId = payload?.terminal_id
    const nodeId = payload?.node_id
    if (!nodeId) {
      console.error('[ws] terminal_created missing node_id:', payload)
      ElMessage.error('创建终端失败：后端未返回 node_id')
      return
    }
    if (terminalId) {
      // 去重：已存在的会话（如实时共享/恢复场景）只更新 access 级别，避免重复 push
      const existing = terminalSessions.value.find(t => t.terminal_id === terminalId)
      if (existing) {
        if (payload?.access) existing.access = payload.access
        return
      }
      terminalSessions.value.push({
        terminal_id: terminalId,
        node_id: nodeId,
        interpreter: payload?.interpreter || 'bash',
        working_dir: payload?.working_dir || '.',
        access: payload?.access || 'owner',
        terminal: null,
        hostEl: null,
        fitAddon: null,
        resizeObserver: null,  // ResizeObserver 实例
        history: [],  // 保存历史输出，用于面板隐藏后再显示时恢复
      })
      // 仅当本设备发起了终端创建时才自动切换，避免他端共享的终端打断本设备工作流
      if (terminalCreationTracker.shouldSwitch()) {
        activeTerminalId.value = terminalId
      }
      // 初始化终端
      nextTick(() => {
        const hostEl = independentTerminalHosts.value.get(terminalId)
        if (hostEl) {
          initIndependentTerminal(terminalId, hostEl)
        }
      })
      // 实时共享：接管会话，让后端记录本用户以便接收实时输出
      attachTerminalSession(terminalId)
    }
  } else if (type === 'terminal_closed') {
    // 独立终端关闭
    const terminalId = payload?.terminal_id
    if (terminalId) {
      // 检查终端是否还存在，避免重复关闭导致无限循环
      const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
      if (session) {
        closeTerminal(terminalId)
      }
    }
  } else if (type === 'error') {
    console.warn('[ws] error payload', payload)
    const errorMessage = payload?.message || '未知错误'
    const errorCode = payload?.code || ''
    
    // 如果是认证失败，重新显示连接对话框
    if (errorCode === 'AUTH_FAILED') {
      // 显示错误信息
      connectErrorMessageGetter().value = errorMessage
      // 清空密码输入框
      auth.value.password = ''
      // 重新显示连接对话框
      showConnectModal.value = true
    } else if (errorCode === 'FORBIDDEN') {
      // 权限拒绝：显示toast提示
      showToast(errorMessage, 'error')
    }
    // 其他错误不再通过 appendOutput 显示系统错误消息，避免污染会话窗口
    // 错误信息仍通过 console.warn 输出，便于调试
  } else if (type === 'pipeline_event') {
    // 流水线编排进度事件：归并进 pipelineStore，驱动 DAG 视图实时刷新
    onPipelineEvent(payload)
  } else if (type === 'status_update') {
    // 更新 Agent 执行状态
    if (payload?.execution_status) {
      const prevStatus = agentStatuses.value.get(targetAgentId)?.execution_status
      agentStatuses.value.set(targetAgentId, {execution_status: payload.execution_status})

      // 多端同步：当状态从等待输入/确认切换到运行时，清除该Agent的输入请求和确认对话框
      // 防止一端已响应后，其他端仍显示可重复提交的UI
      if (payload.execution_status === 'running' && ['waiting_single', 'waiting_multi', 'waiting_confirm'].includes(prevStatus)) {
        if (inputRequests.value.has(targetAgentId)) {
          inputRequests.value.delete(targetAgentId)
        }
        if (confirmDialog.value && pendingConfirmAgentId.value === targetAgentId) {
          confirmDialog.value = null
          pendingConfirmAgentId.value = null
        }
        // 清除 Panel 内嵌确认数据
        if (panelConfirmData.value.has(targetAgentId)) {
          panelConfirmData.value.delete(targetAgentId)
        }
      }

      // 同步更新 agentList 中对应 agent 的状态，确保界面能及时响应
      const agentInList = agentList.value.find(a => a.agent_id === targetAgentId)
      if (agentInList) {
        // 如果 execution_status 表示停止（如 'stopped' 或 'finished'），更新 agent.status
        if (['stopped', 'finished'].includes(payload.execution_status)) {
          agentInList.status = 'stopped'
        } else if (payload.execution_status === 'running') {
          agentInList.status = 'running'
        }
      }

      // 当当前 Agent 开始思考时，自动滚动到底部（且自动滚动开启时）
      if (payload.execution_status === 'running' && isCurrentAgent(targetAgentId) && isAutoScrollEnabled(targetAgentId)) {
        nextTick(() => {
          if (outputList.value) {
            outputList.value.scrollTop = outputList.value.scrollHeight
          }
        })
      }

      // Agent结束时发送系统通知
      if (['stopped', 'finished'].includes(payload.execution_status)) {
        const agentInList = agentList.value.find(a => a.agent_id === targetAgentId)
        const agentName = agentInList?.name || agentInList?.agent_type || 'Agent'
        if (notifyOnExit.value) {
          sendSystemNotification(`${agentName} 已退出`)
        }
      }

      // 从运行状态切换到输入状态时发送系统通知
      if (['waiting_single', 'waiting_confirm', 'waiting_multi'].includes(payload.execution_status)) {
        const agentInList = agentList.value.find(a => a.agent_id === targetAgentId)
        const agentName = agentInList?.name || agentInList?.agent_type || 'Agent'
        if (notifyOnInput.value) {
          sendSystemNotification(`${agentName} 等待输入`)
        }
      }
    }
  } else if (type === 'file_upload_response') {
    handleFileUploadResponse(payload)
  } else if (type === 'editor_open_file') {
    // Agent 请求在编辑器中打开文件并定位到指定行/列（结构化编辑器指令，非 eval_js 逃逸口）
    handleEditorOpenFile(payload)
  } else if (type === 'eval_js_request') {
    // 回传必须用收到请求的连接来源 agentId（主网关消息为 null），不能用 targetAgentId
    handleEvalJsRequest(payload, agentId)
  } else if (type && type.startsWith('chat_')) {
    handleChatMessage(type, payload)
  }
}

// 处理后端下发的 JS 执行请求，执行后将结果回传
// agentId：收到该请求的 Agent 连接对应的 agent_id（主网关消息为 null）
async function handleEvalJsRequest(payload, agentId = null) {
  const callId = payload?.call_id
  const code = payload?.code
  if (!callId) return
  let response
  try {
    const fn = new Function(`return (async () => { ${code} })()`)
    const value = await fn()
    response = { call_id: callId, success: true, result: safeSerialize(value) }
  } catch (e) {
    response = { call_id: callId, success: false, error: String(e?.stack || e) }
  }
  // 结果必须回传到收到请求的那条连接：Agent 请求走 sockets 中的 Agent 连接，
  // 而非主网关连接 socket.value（否则主网关无对应 waiter，结果会被丢弃）
  const replyWs = agentId ? sockets.value.get(agentId) : socket.value
  if (replyWs && replyWs.readyState === WebSocket.OPEN) {
    replyWs.send(JSON.stringify({ type: 'eval_js_result', payload: response }))
  }
}

// Agent → 编辑器指令：打开文件并定位到指定行/列
// payload: { agent_id, path, line?, column?, select_start?, select_end?, reveal? }
async function handleEditorOpenFile(payload) {
  const agentId = payload?.agent_id || currentAgentId.value
  const path = resolveAgentRelativePath(payload?.path, agentId)
  if (!path) return
  // 先定位/创建该 Agent 的编辑器面板：复用其已有的 file 面板，或分割当前面板
  // 在新 file 面板中打开——避免把当前会话/聊天/终端区域覆盖掉。
  ensureAgentEditorPane(agentId)
  await openWorkspaceFile(path, agentId)   // 复用现有入口（建会话/加载内容/激活标签）
  await nextTick()
  const modelData = editorModels.get(path)
  const view = getActiveWorkspaceView()
  if (!view || !modelData) return
  const line = Number(payload?.line || 1)
  const col = Number(payload?.column || 1)
  if (payload?.reveal !== false) view.revealLineInCenter(line)
  if (payload?.select_start != null && payload?.select_end != null) {
    const startCol = Number(payload.select_start) + 1
    const endCol = Math.max(startCol, Number(payload.select_end) + 1)
    view.setSelection(new monaco.Selection(line, startCol, line, endCol))
  }
  view.setPosition({ lineNumber: line, column: col })
  view.focus()
}

// 获取当前活跃编辑器中的选中内容（供命令面板动作 enabled 判断与 sendSelectionToAgent 使用）
// 返回 null 表示无选中/无编辑器；否则返回 { path, text, startLine, endLine }
function getEditorSelection() {
  const view = getActiveWorkspaceView()
  if (!view) return null
  const model = view.getModel()
  if (!model) return null
  const selection = view.getSelection()
  if (!selection || selection.isEmpty()) return null
  const path = model.__jarvisPath || ''
  const text = model.getValueInRange(selection)
  if (!text || !text.trim()) return null
  return { path, text, startLine: selection.startLineNumber, endLine: selection.endLineNumber }
}

// 把编辑器选中内容发给当前 Agent，让 Agent 分析/解释/修改
function sendSelectionToAgent() {
  const sel = getEditorSelection()
  if (!sel) {
    showToast('请先在编辑器中选中代码', 'info')
    return
  }
  const agentId = currentAgentId.value
  if (!agentId) {
    showToast('请先选中当前 Agent', 'error')
    return
  }
  const location = sel.path
    ? `（文件: ${sel.path} 行 ${sel.startLine}-${sel.endLine}）`
    : `（行 ${sel.startLine}-${sel.endLine}）`
  const message = {
    type: 'input_result',
    payload: {
      text: `请分析以下选中代码${location}：\n${sel.text}`,
      agent_id: agentId,
      display_name: chatName.value || username.value || '',
      input_mode: 'single',
    },
  }
  sendMessageToAgent(message, agentId)
}

// 将 JS 执行结果转换为可安全传输的 JSON 结构
function safeSerialize(value) {
  if (value === undefined) return null
  try {
    const json = JSON.stringify(value)
    if (json !== undefined) return JSON.parse(json)
  } catch (e) {
    // 循环引用或不可序列化，走降级逻辑
  }
  let text
  if (typeof Element !== 'undefined' && value instanceof Element) {
    text = `[Element ${value.tagName}] ${value.outerHTML.slice(0, 2000)}`
  } else if (typeof value === 'function') {
    text = `[Function ${value.name || 'anonymous'}]`
  } else {
    text = String(value)
  }
  if (text.length > 10 * 1024 * 1024) text = text.slice(0, 10 * 1024 * 1024) + '...[truncated]'
  return text
}


// 统一的消息HTML渲染函数（用于新消息和历史消息）
function renderMessageHtml(payload) {
  if (payload?.output_type === 'DIFF') {
    // 专门的 DIFF 类型：解析 side by side diff 数据
    try {
      const diffData = JSON.parse(payload.text || '{}')
      if (diffData.diff_type === 'side_by_side') {
        return renderSideBySideDiff(diffData)
      }
    } catch (e) {
      return escapeHtml(payload.text || '')
    }
  }
  if (payload?.lang === 'markdown') {
    return marked.parse(payload.text || '', { breaks: true })
  } else if (payload?.lang === 'diff') {
    // 将 diff 包装在 markdown 代码块中，以便语法高亮
    return marked.parse(`\`\`\`diff\n${payload.text || ''}\n\`\`\``)
  } else {
    return escapeHtml(payload.text || '')
  }
}

function appendOutput(payload, agentId = null) {
  // 过滤内部控制信号，防止在 UI 中显示
  if (payload?.text === '__CTRL_C_PRESSED__') {
    return;
  }
  const html = renderMessageHtml(payload)
  
  // 使用后端传的时间戳，不做本地生成
  const now = payload?.timestamp || ''
  
  // 从 context 中提取 agent 信息，但优先使用 payload 顶层的 agent_name
  const context = payload?.context || {}
  const agentName = payload?.agent_name || context.agent_name || context.agent || ''
  const nonInteractive = payload?.non_interactive !== undefined ? payload?.non_interactive : (context.non_interactive || false)
  const agentList = payload?.agent_list || context.agent_list || ''
  const resolvedAgentId = agentId || payload?.agent_id || context.agent_id || currentAgentId.value
  
  // 生成稳定ID，避免v-for使用index作为key导致DOM重建
  const stableId = payload?.execution_id
    ? `exec_${payload.execution_id}`
    : payload?._stableId || `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

  const outputItem = {
    ...payload,
    html,
    timestamp: now,
    agent_name: agentName,
    non_interactive: nonInteractive,
    agent_list: agentList,
    agent_id: resolvedAgentId,
    _stableId: stableId,
  }

  // 确定目标 Agent ID：优先使用传入参数，其次使用消息自带 agent_id，最后回退到当前 Agent
  const targetAgentId = resolvedAgentId
  // 该 Agent 是否在某个 Panel 中（在 Panel 中则自动滚动）
  const targetPanel = panels.value.find(p => p.agentId === targetAgentId)
  const shouldAutoScroll = !!targetPanel || isCurrentAgent(targetAgentId)

  // 添加到目标 Agent 的消息列表
  const currentOutputs = allOutputs.value.get(targetAgentId) || []

  // execution 消息去重：如果已存在相同 execution_id，则跳过（避免历史加载和 WebSocket 推送重复）
  if (outputItem.output_type === 'execution' && outputItem.execution_id) {
    const duplicate = currentOutputs.find(
      item => item.output_type === 'execution' && item.execution_id === outputItem.execution_id
    )
    if (duplicate) {
      return
    }
  }

  // seq 去重：如果已存在相同 seq 的消息，则跳过（避免历史加载和 WebSocket 推送重复）
  if (typeof outputItem.seq === 'number') {
    const duplicate = currentOutputs.find(item => item.seq === outputItem.seq)
    if (duplicate) {
      return
    }
  }

  currentOutputs.push(outputItem)

  // 消息数量限制：超过100条时截断前50条，只保留后50条，避免DOM过多致页面卡顿
  if (currentOutputs.length > 100) {
    currentOutputs.splice(0, currentOutputs.length - 50)
    allOutputs.value.set(targetAgentId, currentOutputs)
  }

  // 保存消息到本地存储
  try {
    // execution 消息也保存到历史（含 execution_chunks），用于切换 Agent 后重建 xterm
    if (outputItem.output_type === 'execution') {
      const messageToSave = {
        id: outputItem.execution_id ? `execution_${outputItem.execution_id}` : undefined,
        agent_id: targetAgentId,
        output_type: outputItem.output_type,
        text: outputItem.text || '',
        lang: outputItem.lang || 'text',
        agent_name: outputItem.agent_name,
        non_interactive: outputItem.non_interactive,
        agent_list: outputItem.agent_list,
        timestamp: outputItem.timestamp,
        execution_id: outputItem.execution_id,
        context: outputItem.context,
        is_finished: outputItem.is_finished || false,
        terminal_content: outputItem.terminal_content || '',
        execution_chunks: outputItem.execution_chunks || [],
        seq: outputItem.seq, // 保存 seq
      }
      historyStorage.saveMessage(messageToSave)
    } else {
      // 非 execution 消息正常保存
      const messageToSave = {
        id: undefined,
        agent_id: targetAgentId,
        output_type: outputItem.output_type,
        text: outputItem.text,
        lang: outputItem.lang,
        agent_name: outputItem.agent_name,
        non_interactive: outputItem.non_interactive,
        agent_list: outputItem.agent_list,
        timestamp: outputItem.timestamp,
        context: outputItem.context,
        seq: outputItem.seq, // 保存 seq
      }
      historyStorage.saveMessage(messageToSave)
    }
  } catch (error) {
    console.warn('[HISTORY] Failed to save message:', error)
  }
  
  // DOM更新后自动滚动到底部（Mermaid/dot 渲染由 MutationObserver 自动触发，且自动滚动开启时）
  nextTick(() => {
    requestAnimationFrame(() => {
      if (!shouldAutoScroll || !isAutoScrollEnabled(targetAgentId)) return
      // 优先使用 Panel 对应的 outputList，其次使用全局 outputList
      const targetOutputList = targetPanel ? panelOutputLists.get(targetPanel.id) : null
      const scrollEl = targetOutputList || outputList.value
      if (scrollEl) {
        const scrollHeight = scrollEl.scrollHeight
        scrollEl.scrollTop = scrollHeight
      }
    })
  })
}

// 将指定 Agent 的 session 对话容器滚动到底部（自动滚动开启时）
// 用于 execute_script 等 execution 输出写入 xterm 后，外层对话容器跟随滚动
function scrollSessionToBottom(targetAgentId) {
  if (!targetAgentId || !isAutoScrollEnabled(targetAgentId)) return
  const targetPanel = panels.value.find(p => p.agentId === targetAgentId)
  const targetOutputList = targetPanel ? panelOutputLists.get(targetPanel.id) : null
  // 只滚动该 Agent 自己的容器；仅当它就是当前查看的 Agent 且无独立 Panel 容器时，
  // 才回退到 outputList，避免后台 Agent 的终端输出把用户正在查看的其他 Agent 视图滚到底。
  const scrollEl = targetOutputList || (isCurrentAgent(targetAgentId) ? outputList.value : null)
  if (!scrollEl) return
  nextTick(() => {
    requestAnimationFrame(() => {
      scrollEl.scrollTop = scrollEl.scrollHeight
    })
  })
}

// 复制消息内容到剪贴板
async function copyToClipboard(text, index) {
  if (!text) {
    console.warn('[COPY] No text to copy')
    return
  }
  
  try {
    await navigator.clipboard.writeText(text)
    showToast('已复制到剪贴板', 'success')
  } catch (err) {
    console.error('[COPY] Failed to copy text:', err)
    // 可选：降级方案
    try {
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.opacity = '0'
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
    } catch (fallbackErr) {
      console.error('[COPY] Fallback also failed:', fallbackErr)
      alert('复制失败，请手动复制')
    }
  }
}



// 检查光标是否在第一行
function isCursorAtFirstLine(textarea) {
  const cursorPosition = textarea.selectionStart
  const textBeforeCursor = textarea.value.substring(0, cursorPosition)
  return !textBeforeCursor.includes('\n')
}



// 检查光标是否在最后一行
function isCursorAtLastLine(textarea) {
  const cursorPosition = textarea.selectionEnd
  const textAfterCursor = textarea.value.substring(cursorPosition)
  return !textAfterCursor.includes('\n')
}

// 存储等待文件上传响应的 Promise resolve 函数
const pendingFileUploads = new Map()

// 处理文件上传响应
function handleFileUploadResponse(payload) {
  const { message_id, success, file_path, error } = payload
  const resolve = pendingFileUploads.get(message_id)
  if (resolve) {
    pendingFileUploads.delete(message_id)
    if (success) {
      resolve(file_path)
    } else {
      console.error('File upload failed:', error)
      alert(`图片上传失败: ${error}`)
      resolve(null)
    }
  }
}



// 上传图片到节点
async function uploadImageToNode(file, agentId = null) {
  // 限制文件大小 20MB
  if (file.size > 20 * 1024 * 1024) {
    alert('图片大小不能超过 20MB')
    return
  }

  const targetAgentId = agentId || currentAgentId.value
  const targetAgent = agentList.value.find(a => a.agent_id === targetAgentId)
  const targetNodeId = String(targetAgent?.node_id || '').trim() || 'master'

  const reader = new FileReader()
  reader.onload = async (e) => {
    const base64Data = e.target.result
    const { host, port } = getGatewayAddress()
    const url = buildNodeHttpUrl(host, port, targetNodeId, 'upload')

    try {
      const response = await fetchWithAuth(url, {
        method: 'POST',
        body: JSON.stringify({
          agent_id: targetAgentId,
          file_name: file.name,
          file_data: base64Data
        })
      })

      const result = await response.json()
      if (result.success && result.data?.file_path) {
        insertTextAtCursor(`${result.data.file_path} `, targetAgentId)
      } else {
        alert('上传失败: ' + (result.error || '未知错误'))
      }
    } catch (error) {
      console.error('上传图片失败:', error)
      alert('上传图片失败: ' + error.message)
    }
  }
  reader.readAsDataURL(file)
}

// 在光标位置插入文本
// 在光标位置插入文本
function insertTextAtCursor(text, agentId = null) {
  const textarea = document.querySelector('textarea')
  if (!textarea) return

  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const targetAgentId = agentId || currentAgentId.value
  const currentText = targetAgentId
    ? (panelInputTexts.value.get(targetAgentId) || '')
    : inputText.value
  const before = currentText.substring(0, start)
  const after = currentText.substring(end)
  const newText = before + text + after

  if (targetAgentId) {
    panelInputTexts.value.set(targetAgentId, newText)
  }
  inputText.value = newText

  // 更新光标位置
  textarea.selectionStart = textarea.selectionEnd = start + text.length
  textarea.focus()
}





// 缓冲被消费/清空时，若缓存管理面板正显示该 Agent 的缓冲，则关闭面板并重置编辑文本。
// 避免：① 面板残留旧内容（消费后再次打开显示旧内容）；② 消费后再次加内容时面板自动重弹
// （showBufferPanel 仍为 true，hasBufferedInput 由 false 变 true 触发 v-if 重新显示）。
function closeBufferPanelIfForAgent(agentId) {
  if (bufferPanelAgentId.value === agentId) {
    showBufferPanel.value = false
    bufferEditText.value = ''
  }
}

function updateInputBuffer(agentId, nextValue) {
  inputBuffers.value.set(agentId, nextValue)
  if (currentAgentId.value === agentId) {
    bufferEditText.value = nextValue
  }
}

function appendToInputBuffer(agentId, text) {
  const existingText = inputBuffers.value.get(agentId) || ''
  const nextValue = existingText
    ? `${existingText}\n${text}`
    : text

  updateInputBuffer(agentId, nextValue)
}



function submitCompletion() {
  const agentId = currentAgentId.value
  if (!agentId) {
    console.warn('[SUBMIT] No current agent ID, cannot submit completion')
    return
  }
  
  // 获取当前运行状态
  const statusData = agentStatuses.value.get(agentId)
  const executionStatus = statusData?.execution_status || 'running'
  
  // 添加确认对话框，防止误触
  showConfirm(
    '确定要发送完成信号吗？',
    () => {
      // 用户确认，发送 Ctrl+C 信号作为完成信号（与 CLI 模式按 Ctrl+C 行为一致）
      // 注意：完成信号只针对多行输入，单行输入（如确认对话框）不使用完成按钮
      if (executionStatus === 'waiting_multi') {
        // 后端正在等待多行输入，直接发送 Ctrl+C 信号
        sendInputDirectly('__CTRL_C_PRESSED__', 'single')
      } else {
        // 后端没有等待输入或正在等待单行输入，将完成信号保存到缓冲区（与普通输入统一机制）
        updateInputBuffer(agentId, '__CTRL_C_PRESSED__')
        appendOutput({
          output_type: 'system',
          agent_name: 'system',
          text: '✅ 完成信号已保存到缓冲区，下次需要输入时自动触发',
          lang: 'text',
        })
      }
    },
    null, // 取消回调，不需要特殊处理
    true  // defaultConfirm=true，默认选择"是"
  )
}

function sendInputDirectly(text, inputMode = 'multi', agentId = null) {
  const targetAgentId = agentId || currentAgentId.value

  const message = {
    type: 'input_result',
    payload: {
      text: text,
      agent_id: targetAgentId,
      display_name: chatName.value || username.value || '',
      input_mode: inputMode,
    },
  }

  sendMessageToAgent(message, targetAgentId)

  // 从Map中删除该Agent的输入请求
  if (targetAgentId) {
    inputRequests.value.delete(targetAgentId)
  }
}

function sendInputResult(text, requestId, agentId = null, inputMode = 'multi') {
  const targetAgentId = agentId || pendingInputAgentId.value || currentAgentId.value



  const message = {
    type: 'input_result',
    payload: {
      text: text,
      request_id: requestId,
      agent_id: targetAgentId,
      display_name: chatName.value || username.value || '',
      input_mode: inputMode,
    },
  }
  if (targetAgentId) {
    const ws = sockets.value.get(targetAgentId)
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
    } else {
      console.warn(`[SEND] No open WebSocket for agent ${targetAgentId}`)
    }
  }
  
  // 从Map中删除该Agent的输入请求（表示已响应）
  if (targetAgentId) {
    inputRequests.value.delete(targetAgentId)
  }
  pendingInputAgentId.value = null
}

function sendBufferedInput(agentId = null) {
  const targetAgentId = agentId || currentAgentId.value
  if (!targetAgentId || !inputBuffers.value.has(targetAgentId)) {
    return
  }
  const bufferedText = inputBuffers.value.get(targetAgentId)
  // 清空缓冲区
  inputBuffers.value.delete(targetAgentId)
  // 发送缓冲区内容
  sendInputDirectly(bufferedText, 'multi', targetAgentId)
  // 缓冲已被消费：若缓存面板正显示该 Agent，关闭面板并重置编辑文本
  closeBufferPanelIfForAgent(targetAgentId)
}

function clearBuffer() {
  const agentId = bufferPanelAgentId.value
  if (!agentId) {
    return
  }
  inputBuffers.value.delete(agentId)
  // 清空后若缓存面板正显示该 Agent，关闭面板并重置编辑文本
  closeBufferPanelIfForAgent(agentId)
  appendOutput({
    output_type: 'system',
    agent_name: 'system',
    text: '🗑️ 缓冲区已清空',
    lang: 'text',
  })
}

function loadBufferToInput() {
  const agentId = bufferPanelAgentId.value
  if (!agentId || !inputBuffers.value.has(agentId)) {
    return
  }
  const bufferedText = inputBuffers.value.get(agentId)
  inputText.value = bufferedText
  showBufferPanel.value = false
  // 聚焦到输入框
  setTimeout(() => {
    const textarea = document.querySelector('.input-wrapper textarea')
    textarea?.focus()
  }, 100)
}

function saveBufferEdit() {
  const agentId = bufferPanelAgentId.value
  if (!agentId || !bufferEditText.value.trim()) {
    return
  }
  updateInputBuffer(agentId, bufferEditText.value.trim())
  appendOutput({
    output_type: 'system',
    agent_name: 'system',
    text: '✅ 缓存已更新',
    lang: 'text',
  })
}

function sendConfirmResult(confirmed, agentId = null) {
  const targetAgentId = agentId || pendingConfirmAgentId.value || currentAgentId.value
  const message = {
    type: 'confirm_result',
    payload: {
      confirmed,
    },
  }
  if (targetAgentId) {
    const ws = sockets.value.get(targetAgentId)
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
    } else {
      console.warn(`[SEND] No open WebSocket for agent ${targetAgentId}`)
    }
    // 清除 Panel 内嵌确认数据
    panelConfirmData.value.delete(targetAgentId)
    // 乐观降级执行状态：避免后端 status_update 到达前，
    // 大厅/面板仍按 waiting_confirm 渲染出无消息的默认「请确认」
    const confirmStatus = agentStatuses.value.get(targetAgentId)?.execution_status
    if (confirmStatus === 'waiting_confirm') {
      agentStatuses.value.set(targetAgentId, {execution_status: 'running'})
    }
    // 恢复输入模式为多行
    inputMode.value = 'multi'
    panelInputModes.value.set(targetAgentId, 'multi')
    inputTip.value = ''
    panelInputTips.value.set(targetAgentId, '')
    // 清空输入框
    panelInputTexts.value.set(targetAgentId, '')
    inputText.value = ''
  }
  pendingConfirmAgentId.value = null
}

// 处理 Panel 内嵌确认
function handlePanelConfirm(panel) {
  if (!panel || !panel.agentId) return
  const confirmData = panelConfirmData.value.get(panel.agentId)
  if (confirmData?.onConfirm) {
    confirmData.onConfirm()
    panelConfirmData.value.delete(panel.agentId)
    // 清空输入框
    panelInputTexts.value.set(panel.agentId, '')
    inputText.value = ''
    return
  }
  sendConfirmResult(true, panel.agentId)
}

// 处理 Panel 内嵌取消确认
function handlePanelCancelConfirm(panel) {
  if (!panel || !panel.agentId) return
  const confirmData = panelConfirmData.value.get(panel.agentId)
  if (confirmData?.onCancel) {
    confirmData.onCancel()
    panelConfirmData.value.delete(panel.agentId)
    // 清空输入框
    panelInputTexts.value.set(panel.agentId, '')
    inputText.value = ''
    return
  }
  sendConfirmResult(false, panel.agentId)
}

// 恢复 waiting_confirm UI（从 panelConfirmData 恢复）
function restoreWaitingConfirmUI(agentId) {
  if (!agentId) return
  const confirmData = panelConfirmData.value.get(agentId)
  if (confirmData) {
    pendingConfirmAgentId.value = agentId
    // 无 Panel 时不弹全局对话框，确认请求静默等待，用户打开 Panel 后可见 confirm 控件
  } else {
    console.warn('[AGENT] No panel confirm data found for agent', agentId)
  }
}

function sendMessageToAgentById(agentId, message) {
  if (!agentId) {
    console.warn('[SEND] No agent ID provided for message:', message?.type)
    return
  }

  const ws = sockets.value.get(agentId)
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message))
  } else {
    console.warn(`[SEND] No open WebSocket for agent ${agentId}`)
  }
}

  return {
    syncAgentInputMode,
    handleMessage,
    handleEvalJsRequest,
    handleEditorOpenFile,
    getEditorSelection,
    sendSelectionToAgent,
    safeSerialize,
    renderMessageHtml,
    appendOutput,
    scrollSessionToBottom,
    copyToClipboard,
    isCursorAtFirstLine,
    isCursorAtLastLine,
    pendingFileUploads,
    handleFileUploadResponse,
    uploadImageToNode,
    insertTextAtCursor,
    closeBufferPanelIfForAgent,
    updateInputBuffer,
    appendToInputBuffer,
    submitCompletion,
    sendInputDirectly,
    sendInputResult,
    sendBufferedInput,
    clearBuffer,
    loadBufferToInput,
    saveBufferEdit,
    sendConfirmResult,
    handlePanelConfirm,
    handlePanelCancelConfirm,
    restoreWaitingConfirmUI,
    sendMessageToAgentById,
  }
}
