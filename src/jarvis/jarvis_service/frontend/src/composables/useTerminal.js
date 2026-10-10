// 终端 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 3），保持行为完全一致。
// 覆盖 5 个子域：
// - execution 终端（xterm 管理 + execution_chunks 重建）
// - 独立终端（terminalSessions 会话管理、创建/关闭/切换/输入）
// - 终端浮动面板（位置/尺寸持久化、拖拽/缩放）
// - 终端共享（ACL 分享弹窗）
// - 终端名称/节点（terminalName、selectedTerminalNodeId）
//
// 依赖注入：
// - socket / sockets：ref（WebSocket 连接）
// - currentAgentId：ref(string)
// - currentAgent：ref(object)（当前 Agent，含 working_dir）
// - allOutputs：ref(Map)（Agent 输出消息列表）
// - isExecuting：ref(boolean)（执行状态）
// - windowWidth：ref(number)（窗口宽度，移动端窄屏判断）
// - activeWindow：ref(string)（当前激活窗口，z-index 判断）
// - auth：ref(object)（认证信息）
// - showTerminalPanel：ref(boolean)（终端面板显示标志）
// - getGatewayAddress：函数（返回 { host, port }）
// - fetchWithAuth：函数（带鉴权的 fetch 封装）
// - getHttpProtocol：函数（返回 http/https）
// - sendMessageToAgentById：函数（向 Agent 发送消息）
// - scrollSessionToBottom：函数（滚动 session 对话容器到底部）
// - getCurrentAgentNodeId：函数（返回当前 Agent 的节点 ID）
// - showWorkspaceHostView：函数（在工作区中显示 chat/terminal）
// - clamp：函数（数值钳制）
// - PANEL_DRAG_ACTIVATION_DISTANCE / BASE_Z_INDEX / ACTIVE_Z_INDEX：常量
// - focusWindow：函数（聚焦窗口）
// - fetchUserList：函数（拉取用户列表）
// - showToast：函数（提示）
// - availableUserOptions：ref(Array)（可选用户列表）
// - historyStorage：模块（历史记录存储）
import { computed, nextTick, ref, watch } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from '@xterm/addon-fit'
import { createTerminalCreationTracker } from '../terminalCreationTracker.js'

// ===== 终端名称 / 节点（低耦合子块，需在 useDaemonSync/useAuthBridge 之前调用） =====
// 终端名称：用于在网关侧区分不同终端（Agent 可按名称定位到这台机器）。
// 存 localStorage 后同时暴露给：①浏览器扩展（__jarvisAuthBridge.getName）
// ②本机 daemon（随 /api/auth 推送）。默认值取本机计算机名，浏览器无法直接读
// 系统主机名，故向本机 daemon 的 /api/status 查询（daemon 由 os.Hostname() 提供）。
//
// 依赖注入：
// - auth：ref(object)（认证信息）
// - getDaemonUrl：函数（返回本机 daemon 的 URL；因 useDaemonSync 在其后定义，
//   这里以 getter 形式传入，调用时才求值，避免 TDZ）
// - syncTokenToDaemon：函数（把 token 同步给本机 daemon；同上以 getter 形式传入）
export function useTerminalName({ auth, getDaemonUrl, syncTokenToDaemon }) {
  const TERMINAL_NAME_STORAGE_KEY = 'jarvis_terminal_name'
  function loadTerminalName() {
    try {
      return String(localStorage.getItem(TERMINAL_NAME_STORAGE_KEY) || '').trim()
    } catch (error) {
      console.warn('[TERMINAL] Failed to load terminal name:', error)
      return ''
    }
  }
  const terminalName = ref(loadTerminalName())
  function saveTerminalNameSetting(nextValue = terminalName.value) {
    terminalName.value = String(nextValue || '').trim()
    try {
      localStorage.setItem(TERMINAL_NAME_STORAGE_KEY, terminalName.value)
    } catch (error) {
      console.warn('[TERMINAL] Failed to save terminal name:', error)
    }
    // 名称变化后立即重新推送一次给本机 daemon（扩展是主动读 bridge，无需推送）
    syncTokenToDaemon()(auth.value.token, window.__jarvisAuthBridge.getGateway())
  }
  // 首次进入且用户未配置名称时，用本机 daemon 上报的计算机名作为默认值。
  // 仅在未配置（localStorage 无值）时写入，避免覆盖用户自定义名称。
  async function initTerminalNameFromDaemon() {
    if (loadTerminalName()) return
    try {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 1500)
      const resp = await fetch(`${getDaemonUrl()()}/api/status`, {
        signal: controller.signal,
        credentials: 'omit',
      })
      clearTimeout(timer)
      const data = await resp.json()
      const hostname = String(data?.hostname || '').trim()
      if (hostname) saveTerminalNameSetting(hostname)
    } catch (e) {
      // daemon 不存在或未启动属预期情况，保持名称为空（网关侧回退到 hostname）
      console.debug('[TERMINAL] init terminal name from daemon skipped:', e?.message || e)
    }
  }
  const selectedTerminalNodeId = ref('master')
  return { terminalName, saveTerminalNameSetting, initTerminalNameFromDaemon, selectedTerminalNodeId }
}

// ===== 主 composable：execution 终端 / 独立终端 / 浮动面板 / 共享 =====
export function useTerminal({
  socket,
  sockets,
  currentAgentId,
  currentAgent,
  allOutputs,
  isExecuting,
  windowWidth,
  activeWindow,
  auth,
  showTerminalPanel,
  selectedTerminalNodeId,
  getGatewayAddress,
  fetchWithAuth,
  getHttpProtocol,
  sendMessageToAgentById,
  scrollSessionToBottom,
  getCurrentAgentNodeId,
  showWorkspaceHostView,
  clamp,
  PANEL_DRAG_ACTIVATION_DISTANCE,
  BASE_Z_INDEX,
  ACTIVE_Z_INDEX,
  focusWindow,
  fetchUserList,
  showToast,
  availableUserOptions,
  historyStorage,
}) {

  const terminalHosts = ref(new Map()) // executionSessionKey -> hostEl
  const terminals = ref([]) // [{ sessionKey, agentId, executionId, terminal, active, hostEl, resizeObserver, lastSize, ended }]

  function getExecutionSessionKey(agentId, executionId) {
    const normalizedAgentId = String(agentId || '').trim() || 'unknown-agent'
    const normalizedExecutionId = String(executionId || 'default').trim() || 'default'
    return `${normalizedAgentId}:${normalizedExecutionId}`
  }

  // 独立终端会话
  const terminalSessions = ref([]) // [{ terminal_id, interpreter, working_dir, terminal, hostEl, fitAddon }]
  const activeTerminalId = ref(null) // 当前激活的终端ID
  const independentTerminalHosts = ref(new Map()) // terminal_id -> hostEl
  const isCreatingTerminalSession = ref(false)
  // 终端创建"本设备发起"追踪器：区分本设备创建（自动切换）与他端共享（不切换）
  const terminalCreationTracker = createTerminalCreationTracker()

  // execution_chunks历史更新的debounce（按executionId分组，500ms批量写入localStorage）
  const _execHistoryDebounceMap = new Map()
  function _debouncedSaveExecHistory(executionId, targetAgentId) {
    const key = `${targetAgentId}:${executionId}`
    if (_execHistoryDebounceMap.has(key)) return // 已有pending的debounce
    _execHistoryDebounceMap.set(key, true)
    setTimeout(() => {
      _execHistoryDebounceMap.delete(key)
      const currentOutputs = allOutputs.value.get(targetAgentId) || []
      const msg = currentOutputs.find(item => item.output_type === 'execution' && item.execution_id === executionId)
      if (msg) {
        try {
          // 使用与 appendOutput/appendExecution 一致的 id，确保更新同一条记录而非新增
          historyStorage.saveMessage({
            id: `execution_${executionId}`,
            agent_id: targetAgentId,
            output_type: msg.output_type,
            text: msg.text || '',
            lang: msg.lang || 'text',
            agent_name: msg.agent_name,
            non_interactive: msg.non_interactive,
            agent_list: msg.agent_list,
            timestamp: msg.timestamp,
            execution_id: msg.execution_id,
            context: msg.context,
            is_finished: msg.is_finished || false,
            // terminal_content 仅在执行已结束时用 execution_chunks 兜底，
            // 避免刷新后落盘数据 is_finished 但无内容可显示。
            // 执行进行中（is_finished=false）必须保持 terminal_content 为空，
            // 否则切换回该 Agent 时模板会因 !item.terminal_content 不成立而不渲染 xterm，
            // 导致运行中的终端被错误替换成 Terminal Output 静态文本块。
            terminal_content: msg.is_finished
              ? (msg.terminal_content || (msg.execution_chunks || []).join(''))
              : '',
            execution_chunks: msg.execution_chunks || [],
            seq: msg.seq,
          })
        } catch {
          // 静默失败
        }
      }
    }, 500)
  }

  function appendExecution(payload, agentId = null) {
    const executionId = payload?.execution_id || 'default'
    const eventType = payload?.event_type
    const targetAgentId = agentId || payload?.agent_id || currentAgentId.value
  
  
    // 检查是否是独立终端的输出（格式：terminal_{terminal_id}）
    if (executionId.startsWith('terminal_')) {
      const terminalId = executionId.replace('terminal_', '')
      const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
    
      // 检查会话是否存在
      if (!session) {
        console.warn(`[independent-terminal] No session found for ${terminalId}`)
        return
      }
    
      // 解码数据
      let data = payload?.data || ''
      if (payload?.encoded && data) {
        try {
          const binaryString = atob(data)
          const bytes = new Uint8Array(binaryString.length)
          for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i)
          }
          const decoder = new TextDecoder('utf-8')
          data = decoder.decode(bytes)
        } catch (error) {
          console.error('[independent-terminal] Failed to decode base64 data:', error)
          return
        }
      }
    
      // 如果终端已初始化，直接写入
      if (session.terminal) {
        try {
          session.terminal.write(data)
          // 保存历史输出
          session.history.push({ type: eventType, data: data })
        } catch (error) {
          console.error('[independent-terminal] Failed to write to terminal:', error)
        }
      } else {
        // 终端尚未初始化，将输出暂存到缓冲区
        if (!session.pending_output) {
          session.pending_output = []
        }
        session.pending_output.push(data)
      }
      return
    }
  
    // 处理 base64 编码的数据
    let data = payload?.data || ''
    if (payload?.encoded && data) {
      try {
        // 解码 base64 数据
        const binaryString = atob(data)
        // 将二进制字符串转换为 Uint8Array，然后解码为 UTF-8
        const bytes = new Uint8Array(binaryString.length)
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i)
        }
        // 使用 TextDecoder 处理 UTF-8
        const decoder = new TextDecoder('utf-8')
        data = decoder.decode(bytes)
      } catch (error) {
        console.error('[terminal] Failed to decode base64 data:', error)
        return
      }
    }
  
    const executionSessionKey = getExecutionSessionKey(targetAgentId, executionId)

    // 检查是否需要创建新终端
    let termInfo = terminals.value.find(t => t.sessionKey === executionSessionKey)
    if (!termInfo) {
      termInfo = {
        sessionKey: executionSessionKey,
        agentId: targetAgentId,
        executionId,
        terminal: null,
        active: true,
        hostEl: null,
        ended: false,
      }
      terminals.value.push(termInfo)
      // 终端初始化移到 setTerminalRef 中，确保 DOM 元素准备好
    }

  
    // 处理执行开始事件
    if (payload?.message_type === 'tool_stream_start' && !isExecuting.value) {
      isExecuting.value = true
    }
  
    // 处理执行结束事件
    if (payload?.message_type === 'tool_stream_end' && termInfo.active) {
      // 如果termInfo.terminal不存在，可能是后台执行的命令（DOM未渲染导致terminal未初始化）
      // 后台执行的场景需要正确标记execution为已完成，避免切回时多余重建xterm
      if (!termInfo.terminal) {
        // 检查消息的execution_chunks是否有数据，判断是后台执行还是重连场景
        const currentOutputs = allOutputs.value.get(targetAgentId) || []
        const execMsg = currentOutputs.find(
          item => item.output_type === 'execution' && item.execution_id === executionId
        )
        if (execMsg?.execution_chunks?.length > 0) {
          // 后台执行场景：有数据但terminal未初始化，需要正确结束execution
        } else {
          // 重连场景：没有数据，忽略tool_stream_end
          return
        }
      }
      termInfo.active = false
      termInfo.ended = true
      isExecuting.value = false // 更新执行状态

      // 保存终端内容到消息列表
      // 优先从terminal buffer获取内容（后台执行场景从execution_chunks拼接）
      let terminalContent = ''
      if (termInfo.terminal) {
        terminalContent = getTerminalBufferContent(termInfo.terminal, true)
      } else {
        // 后台执行场景：从消息的execution_chunks拼接
        const currentOutputs = allOutputs.value.get(targetAgentId) || []
        const execMsg = currentOutputs.find(
          item => item.output_type === 'execution' && item.execution_id === executionId
        )
        if (execMsg?.execution_chunks?.length > 0) {
          terminalContent = execMsg.execution_chunks.join('')
        }
      }
      // 获取终端内容并保存
      try {
        // 找到并更新 execution 消息，添加 is_finished 标记和 terminal_content
        const currentOutputs = allOutputs.value.get(targetAgentId) || []
        const execIndex = currentOutputs.findIndex(
          item => item.output_type === 'execution' && item.execution_id === executionId
        )
        if (execIndex !== -1) {
          // 标记 execution 消息为已结束，并保存终端内容（保留execution_chunks用于重建xterm）
          currentOutputs[execIndex].is_finished = true
          currentOutputs[execIndex].terminal_content = terminalContent
          currentOutputs[execIndex].timestamp = new Date().toISOString()
          // 触发响应式更新
          allOutputs.value.set(targetAgentId, [...currentOutputs])
          // 保存到历史记录（更新原有的 execution 消息，保留execution_chunks）
          try {
            const updatedMessage = {
              id: `execution_${executionId}`,
              agent_id: targetAgentId,
              output_type: 'execution',
              text: '',
              lang: 'text',
              agent_name: currentOutputs[execIndex].agent_name,
              non_interactive: false,
              timestamp: currentOutputs[execIndex].timestamp,
              execution_id: executionId,
              context: currentOutputs[execIndex].context,
              is_finished: true,
              terminal_content: terminalContent || (currentOutputs[execIndex].execution_chunks || []).join(''),
              execution_chunks: currentOutputs[execIndex].execution_chunks || [],
            }
            historyStorage.saveMessage(updatedMessage)
          } catch (error) {
            console.warn('[HISTORY] Failed to save terminal content:', error)
          }

        } else {
          console.warn(`🚨 [terminal] execution message ${executionId} not found`)
        }
      } catch (error) {
        console.error(`[terminal] Failed to save terminal content:`, error)
      }

      // 销毁 xterm 实例，释放资源（内容已保存到消息的 terminal_content 和 execution_chunks）
      disposeExecutionTerminal(termInfo)
      const executionSessionKey = getExecutionSessionKey(targetAgentId, executionId)
      terminalHosts.value.delete(executionSessionKey)

      // xterm 销毁并切换为 Terminal Output 文本块后，滚动外层 session 对话容器一次（自动滚动开启时）
      scrollSessionToBottom(targetAgentId)
    }
  
    // 输出到终端
    if (eventType === 'stdout' || eventType === 'stderr') {
      if (data) {
        // 追加到消息的 execution_chunks 并实时更新历史
        const currentOutputs = allOutputs.value.get(targetAgentId) || []
        const execIndex = currentOutputs.findIndex(
          item => item.output_type === 'execution' && item.execution_id === executionId
        )
        if (execIndex !== -1) {
          if (!currentOutputs[execIndex].execution_chunks) currentOutputs[execIndex].execution_chunks = []
          currentOutputs[execIndex].execution_chunks.push(data)
          // debounce更新历史记录（500ms批量写入，避免高频localStorage读写）
          _debouncedSaveExecHistory(executionId, targetAgentId)
        }
      }
      if (termInfo.terminal) {
        // 显示即将写入的数据（前100字符），用于调试
        const preview = data.substring(0, 100).replace(/\x1b/g, 'ESC').replace(/\r/g, 'CR').replace(/\n/g, 'LF')
        try {
          termInfo.terminal.write(data)
        } catch (error) {
          console.error('[terminal] Write failed:', error)
        }
      } else if (data) {
      }
    } else if (eventType === 'status') {
      const statusLine = `\r\n[status] ${payload.data || ''}`
      // 追加到消息的 execution_chunks 并实时更新历史
      const currentOutputs = allOutputs.value.get(targetAgentId) || []
      const execIndex = currentOutputs.findIndex(
        item => item.output_type === 'execution' && item.execution_id === executionId
      )
      if (execIndex !== -1) {
        if (!currentOutputs[execIndex].execution_chunks) currentOutputs[execIndex].execution_chunks = []
        currentOutputs[execIndex].execution_chunks.push(statusLine)
        // debounce更新历史记录（500ms批量写入，避免高频localStorage读写）
        _debouncedSaveExecHistory(executionId, targetAgentId)
      }
      if (termInfo.terminal) {
        termInfo.terminal.writeln(statusLine)
      } else {
      }
    } else if (!termInfo.terminal && data) {
    }
  }

  // 清空指定 agent 的终端缓存
  function clearTerminalCache(agentId) {
    if (!agentId) return
    const beforeCount = terminals.value.length
    // 清除该 agent 的所有终端缓存（已完成的终端从历史重建，无需保留termInfo）
    terminals.value = terminals.value.filter(t => t.agentId !== agentId)
    const afterCount = terminals.value.length
  }

  function getTerminalBufferContent(terminal, trimTrailingWhitespace = false) {
    const buffer = terminal?.buffer?.active
    if (!buffer) return ''

    const lines = []
    for (let i = 0; i < buffer.length; i++) {
      const line = buffer.getLine(i)
      if (line) {
        lines.push(line.translateToString(true))
      }
    }

    const content = lines.join('\n')
    return trimTrailingWhitespace ? content.replace(/\s+$/, '') : content
  }

  function syncTerminalSize(executionId, termInfo) {
    if (!termInfo) {
      return
    }
    if (!termInfo.terminal) {
      return
    }
    if (!termInfo.fitAddon) {
      return
    }
  
    // 使用 FitAddon 自动适配尺寸
    const oldCols = termInfo.terminal.cols
    const oldRows = termInfo.terminal.rows
    termInfo.fitAddon.fit()
    const newCols = termInfo.terminal.cols
    const newRows = termInfo.terminal.rows
  
  
    // 如果尺寸没变，跳过
    if (oldCols === newCols && oldRows === newRows) {
      return
    }
  
    // 发送 resize 消息到后端
    const message = {
      type: 'terminal_resize',
      payload: {
        execution_id: executionId,
        rows: newRows,
        cols: newCols,
      },
    }
    sendMessageToAgentById(termInfo.agentId, message)
  }

  function disposeExecutionTerminal(termInfo) {
    if (termInfo?.resizeObserver) {
      termInfo.resizeObserver.disconnect()
    }
    if (termInfo?.fitAddon) {
      try {
        termInfo.fitAddon.dispose()
      } catch (error) {
        console.warn('[terminal] Failed to dispose fitAddon', error)
      }
    }
    if (termInfo?.terminal) {
      try {
        termInfo.terminal.dispose()
      } catch (error) {
        console.warn('[terminal] Failed to dispose terminal', error)
      }
    }

    termInfo.resizeObserver = null
    termInfo.fitAddon = null
    termInfo.terminal = null
    termInfo.hostEl = null
    // 注意：不设置termInfo.ended = true，因为执行可能还在进行中
    // ended只在收到后端的tool_stream_end事件时设置（见handleToolStreamEnd函数）
    // 这样切换回Agent时可以从execution_chunks恢复终端内容
  }

  function initExecutionTerminal(executionId, termInfo, el, agentId = null) {
    const targetAgentId = agentId || termInfo?.agentId || currentAgentId.value
    termInfo.hostEl = el
    termInfo.terminal = new Terminal({
      theme: {
        background: '#0b1424',
      },
      fontSize: 12,
      fontFamily: "'Consolas', 'Microsoft YaHei', monospace",
      allowProposedApi: true,
      focusOnClick: false,
    })

    // 拦截快捷键，防止浏览器默认行为覆盖终端快捷键
    termInfo.terminal.attachCustomKeyEventHandler((event) => {
      // Ctrl+Shift+C: 复制选中文本到剪贴板
      if (event.ctrlKey && event.shiftKey && event.code === 'KeyC') {
        const selection = termInfo.terminal.getSelection()
        if (selection) {
          navigator.clipboard.writeText(selection).catch(err => {
            console.warn('[terminal] Failed to copy to clipboard:', err)
          })
        }
        return false
      }
      // Ctrl+Shift+V: 粘贴（由 onData 处理，这里阻止浏览器默认行为）
      if (event.ctrlKey && event.shiftKey && event.code === 'KeyV') {
        return false
      }
      return true
    })
    termInfo.terminal.open(el)

    termInfo.fitAddon = new FitAddon()
    termInfo.terminal.loadAddon(termInfo.fitAddon)
    termInfo.fitAddon.fit()

    // 该 execution 是否为当前 Agent 消息列表中的最后一条（新执行刚创建）
    // 用于判断是否需要滚动外层 session 对话容器，避免切换回 Agent 重建 xterm 时干扰用户查看历史
    const isLatestExecution = () => {
      const currentOutputs = allOutputs.value.get(targetAgentId) || []
      const lastMsg = currentOutputs[currentOutputs.length - 1]
      return !!(
        lastMsg?.output_type === 'execution' &&
        lastMsg.execution_id === executionId &&
        !lastMsg.is_finished
      )
    }

    if (typeof ResizeObserver !== 'undefined') {
      termInfo.resizeObserver = new ResizeObserver(() => {
        syncTerminalSize(executionId, termInfo)
      })
      termInfo.resizeObserver.observe(el)
    }

    termInfo.terminal.onData(data => {
      if (!termInfo.active) return
      const message = {
        type: 'terminal_input',
        payload: {
          execution_id: executionId,
          data,
        },
      }
      const ws = targetAgentId ? sockets.value.get(targetAgentId) : null
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(message))
      } else {
        console.warn(`[terminal] No open WebSocket for agent ${targetAgentId}, execution ${executionId}`)
      }
    })

    requestAnimationFrame(() => {
      syncTerminalSize(executionId, termInfo)
      if (isLatestExecution()) {
        scrollSessionToBottom(targetAgentId)
      }
    })

    // xterm 首次渲染后高度才稳定，此时再滚动一次，确保新建的终端可见
    setTimeout(() => {
      syncTerminalSize(executionId, termInfo)
      if (isLatestExecution()) {
        scrollSessionToBottom(targetAgentId)
      }
    }, 300)

    // 从消息的 execution_chunks 回放（切换回来时）
    // 如果终端已结束（finished），不回放chunks，避免恢复已完成的终端
    if (!termInfo.ended) {
      const currentOutputs = allOutputs.value.get(targetAgentId) || []
      const execMsg = currentOutputs.find(
        item => item.output_type === 'execution' && item.execution_id === executionId
      )
      if (execMsg?.execution_chunks?.length > 0) {
        execMsg.execution_chunks.forEach((chunk, index) => {
          try {
            termInfo.terminal.write(chunk)
          } catch (error) {
            console.warn(`[terminal] Failed to replay chunk ${index}`, error)
          }
        })
      }
    }

    if (termInfo.ended) {
      getTerminalBufferContent(termInfo.terminal, true)
    }
  }

  // 动态绑定终端 DOM 元素
  function setTerminalRef(executionId, el, agentId = null) {
    const targetAgentId = agentId || currentAgentId.value
    const executionSessionKey = getExecutionSessionKey(targetAgentId, executionId)
    let termInfo = terminals.value.find(t => t.sessionKey === executionSessionKey)
    if (el) {
      if (el.parentElement) {
      }
      terminalHosts.value.set(executionSessionKey, el)
      if (!termInfo) {
        // 检查对应的execution是否已经finished
        const agentOutputs = allOutputs.value.get(targetAgentId) || []
        const executionMessage = agentOutputs.find(
          item => item.output_type === 'execution' && item.execution_id === executionId
        )
      
        // 如果有terminal_content，说明执行结果已保存，不需要创建xterm（直接显示文本历史即可）
        if (executionMessage?.terminal_content) {
          return
        }
        // 检查是否已经finished但没有terminal_content（重连场景），不需要重新创建终端
        if (executionMessage?.is_finished) {
          return
        }
      
        // termInfo不存在，创建新的终端记录
        termInfo = {
          sessionKey: executionSessionKey,
          agentId: targetAgentId,
          executionId: executionId,
          terminal: null,
          active: true,
          hostEl: null,
          resizeObserver: null,
          lastSize: null,
          ended: false
        }
        terminals.value.push(termInfo)
      }

      const needsRebuild = !!termInfo.terminal && termInfo.hostEl !== el
      if (needsRebuild) {
        // 检查该agent的最后一条消息是否是正在执行的命令，如果不是则不需要重建xterm
        const agentOutputs = allOutputs.value.get(targetAgentId) || []
        const lastMessage = agentOutputs[agentOutputs.length - 1]
        // 如果有terminal_content，说明执行结果已保存，不需要重建xterm
        if (lastMessage?.terminal_content) {
          disposeExecutionTerminal(termInfo)
          termInfo.ended = true
          return
        }
        const isLastMessageExecution = lastMessage?.output_type === 'execution' && !lastMessage?.is_finished
        if (!isLastMessageExecution) {
          disposeExecutionTerminal(termInfo)
          termInfo.ended = true
          return
        }
        disposeExecutionTerminal(termInfo)
      }

      if (!termInfo.terminal && !termInfo.ended) {
        initExecutionTerminal(executionId, termInfo, el, targetAgentId)
      } else if (termInfo.ended) {
      } else {
        termInfo.hostEl = el
        if (!termInfo.resizeObserver && typeof ResizeObserver !== 'undefined') {
          termInfo.resizeObserver = new ResizeObserver(() => {
            syncTerminalSize(executionId, termInfo)
          })
          termInfo.resizeObserver.observe(el)
        }
        syncTerminalSize(executionId, termInfo)
      }
    } else {
      // 元素卸载回调：仅当当前 host 已脱离文档（或本就为空）时才清理，
      // 避免被编辑器承载的 grid 实例卸载时误清理编辑器内仍存活的同一终端
      if (termInfo && termInfo.hostEl && termInfo.hostEl.isConnected) {
        return
      }
      terminalHosts.value.delete(executionSessionKey)
      if (termInfo?.resizeObserver) {
        termInfo.resizeObserver.disconnect()
        termInfo.resizeObserver = null
      }
      if (termInfo) {
        termInfo.hostEl = null
      }
    }
  }

  // 独立终端相关函数
  function setTerminalHostRef(terminalId, el) {
    const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
    if (el) {
      // 如果 hostEl 相同且 terminal 已存在，说明是组件更新触发的 ref 回调，不需要重新初始化
      if (session && session.hostEl === el && session.terminal) {
        return
      }
      independentTerminalHosts.value.set(terminalId, el)
      if (session) {
        session.hostEl = el
        // 无论 terminal 是否已初始化，都确保 xterm 创建（修复重新登录后
        // hostEl 已渲染但 xterm 未初始化、只见标签不见内容的问题）
        initIndependentTerminal(terminalId, el)
      }
    } else {
      independentTerminalHosts.value.delete(terminalId)
      if (session) {
        session.hostEl = null
      }
    }
  }

  function initIndependentTerminal(terminalId, el) {
    const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
    if (!session) {
      console.warn(`[independent-terminal] Session not found for ${terminalId}`)
      return
    }
  
    // 如果 terminal 实例已存在（面板切换导致组件重建），先 dispose 旧实例再创建新的
    if (session.terminal) {
      try {
        // xterm.js 的 Terminal.open() 不能对同一实例调用两次，必须先 dispose 再创建新实例
        // 注意：不设置 session.terminal = null，避免触发响应式更新导致无限循环
        session.terminal.dispose()
        session.fitAddon = null
        if (session.resizeObserver) {
          session.resizeObserver.disconnect()
          session.resizeObserver = null
        }
      } catch (error) {
        console.warn(`[independent-terminal] Failed to dispose old terminal ${terminalId}:`, error)
      }
      // 继续走下面的新实例创建逻辑（session.terminal 会被下面的 new Terminal() 覆盖）
    }

  
    // 创建终端实例
    // 注意：这里不调用 fitAddon.fit()，因为初始时元素可能不可见（v-show）
    // 会在 ResizeObserver 回调中自动调整尺寸
    session.terminal = new Terminal({
      theme: {
        background: '#0b1424',
      },
      fontSize: 12,
      fontFamily: "'Consolas', 'Microsoft YaHei', monospace",
      cols: 80,
      rows: 24,
      allowProposedApi: true,
    })

    // 拦截快捷键，防止浏览器默认行为覆盖终端快捷键
    session.terminal.attachCustomKeyEventHandler((event) => {
      // Ctrl+Shift+C: 复制选中文本到剪贴板
      if (event.ctrlKey && event.shiftKey && event.code === 'KeyC') {
        const selection = session.terminal.getSelection()
        if (selection) {
          navigator.clipboard.writeText(selection).catch(err => {
            console.warn('[independent-terminal] Failed to copy to clipboard:', err)
          })
        }
        return false
      }
      // Ctrl+Shift+V: 粘贴（由 onData 处理，这里阻止浏览器默认行为）
      if (event.ctrlKey && event.shiftKey && event.code === 'KeyV') {
        return false
      }
      return true
    })
    session.terminal.open(el)
  
    // 创建并加载 FitAddon
    session.fitAddon = new FitAddon()
    session.terminal.loadAddon(session.fitAddon)
  
    // 使用 FitAddon 适配终端尺寸（仅当元素可见时）
    if (el.offsetParent !== null) {
      session.fitAddon.fit()
    } else {
    }
  
    // 设置 ResizeObserver 监听尺寸变化
    if (typeof ResizeObserver !== 'undefined') {
      const resizeObserver = new ResizeObserver(() => {
        if (session.fitAddon && session.terminal) {
          session.fitAddon.fit()
          // 发送 resize 消息到后端
          sendTerminalResize(terminalId, session.terminal.rows, session.terminal.cols)
        }
      })
      resizeObserver.observe(el)
      session.resizeObserver = resizeObserver
    }
  
    // 监听用户输入
    session.terminal.onData(data => {
      // 只读模式：不发送输入（read 用户仅可查看）
      if (session.access === 'read') {
        return
      }
      sendTerminalInput(terminalId, data)
    })
  
    // 初始化后发送 resize
    setTimeout(() => {
      if (session.fitAddon && session.terminal) {
        session.fitAddon.fit()
        sendTerminalResize(terminalId, session.terminal.rows, session.terminal.cols)
      
        // 写入缓冲的输出（history + pending_output）
        const allOutputs = [
          ...(session.history || []).map(item => item.data),
          ...(session.pending_output || []),
        ]
        if (allOutputs.length > 0) {
          try {
            for (const bufferedData of allOutputs) {
              session.terminal.write(bufferedData)
            }
          } catch (error) {
            console.error('[independent-terminal] Failed to write buffered outputs:', error)
          }
          // 清空缓冲区
          session.pending_output = []
        }
      }
    }, 300)
  }

  // 解码 base64 字符串为 UTF-8 文本（与 appendExecution 中的解码逻辑一致）
  function decodeTerminalBase64(b64) {
    try {
      const binaryString = atob(b64)
      const bytes = new Uint8Array(binaryString.length)
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }
      return new TextDecoder('utf-8').decode(bytes)
    } catch (error) {
      console.error('[independent-terminal] Failed to decode base64 data:', error)
      return ''
    }
  }

  // 接管终端会话：让后端记录本用户以便接收实时输出，并回放输出缓冲
  async function attachTerminalSession(terminalId) {
    try {
      const { host, port } = getGatewayAddress()
      const baseUrl = `${getHttpProtocol()}://${host}:${port}`
      const attachResp = await fetchWithAuth(
        `${baseUrl}/api/terminals/${encodeURIComponent(terminalId)}/attach`,
        { method: 'POST' }
      )
      const attachResult = await attachResp.json()
      if (!attachResult.success || !Array.isArray(attachResult.data?.output)) return
      const bufferedOutput = attachResult.data.output.map(decodeTerminalBase64)
      if (bufferedOutput.length === 0) return
      // 若 xterm 已初始化则直接写入，否则存入 pending_output 由初始化回放
      const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
      if (session && session.terminal) {
        for (const data of bufferedOutput) {
          session.terminal.write(data)
        }
      } else if (session) {
        session.pending_output = [...(session.pending_output || []), ...bufferedOutput]
      }
    } catch (e) {
      console.warn('[independent-terminal] Failed to attach session:', terminalId, e)
    }
  }

  // 登录/重连后恢复当前用户的存活终端会话（方案A：断开不杀进程 + 输出缓冲回放）
  async function restoreTerminalSessions() {
    if (!socket.value) {
      console.warn('[independent-terminal] No socket connection, skip restore')
      return
    }
    try {
      const { host, port } = getGatewayAddress()
      const baseUrl = `${getHttpProtocol()}://${host}:${port}`
      const url = `${baseUrl}/api/terminals`
      const response = await fetchWithAuth(url)
      if (!response.ok) return
      const result = await response.json()
      if (!result.success || !Array.isArray(result.data)) return

      for (const s of result.data) {
        const terminalId = s.terminal_id
        if (!terminalId) continue
        // 跳过已恢复的会话，避免重复
        if (terminalSessions.value.find(t => t.terminal_id === terminalId)) continue

        // 接管会话并获取输出缓冲（供回放）
        let bufferedOutput = []
        try {
          const attachResp = await fetchWithAuth(
            `${baseUrl}/api/terminals/${encodeURIComponent(terminalId)}/attach`,
            { method: 'POST' }
          )
          const attachResult = await attachResp.json()
          if (attachResult.success && Array.isArray(attachResult.data?.output)) {
            bufferedOutput = attachResult.data.output.map(decodeTerminalBase64)
          }
        } catch (e) {
          console.warn('[independent-terminal] Failed to attach session:', terminalId, e)
        }

        // 加入会话列表，缓冲输出存入 pending_output，由 initIndependentTerminal 回放
        terminalSessions.value.push({
          terminal_id: terminalId,
          node_id: s.node_id || 'master',
          interpreter: s.interpreter || 'bash',
          working_dir: s.working_dir || '.',
          access: s.access || 'read',
          terminal: null,
          hostEl: null,
          fitAddon: null,
          resizeObserver: null,
          history: [],
          pending_output: bufferedOutput,
        })
        if (!activeTerminalId.value) {
          activeTerminalId.value = terminalId
        }
        // 若 DOM 已渲染且 xterm 尚未初始化，则初始化终端（回放缓冲）。
        // 若 hostEl 已由 setTerminalHostRef 触发初始化，则此处跳过，避免重复创建。
        nextTick(() => {
          const sessionNow = terminalSessions.value.find(t => t.terminal_id === terminalId)
          if (!sessionNow || sessionNow.terminal) return
          const hostEl = independentTerminalHosts.value.get(terminalId)
          if (hostEl) {
            initIndependentTerminal(terminalId, hostEl)
          }
        })
      }
    } catch (e) {
      console.error('[independent-terminal] Failed to restore sessions:', e)
    }
  }

  // 标记本设备发起了终端创建；若创建失败（无 terminal_created 回包），超时后自动复位，
  // 避免残留标志导致后续他端共享的终端被误切换
  function markTerminalCreationPending() {
    terminalCreationTracker.mark()
  }

  function createTerminal() {
    if (!socket.value) {
      console.warn('[independent-terminal] No socket connection')
      return
    }
  
    const nodeId = getCurrentAgentNodeId() || ''
    const payload = {}
    if (nodeId) {
      payload.node_id = nodeId
    }
    const currentWorkingDir = currentAgent.value?.working_dir?.trim()
    if (currentWorkingDir) {
      payload.working_dir = currentWorkingDir
    }
    const message = {
      type: 'terminal_create',
      payload,
    }
    socket.value.send(JSON.stringify(message))
    // 标记本设备发起了终端创建，terminal_created 回包时自动切换
    markTerminalCreationPending()
  
    // 自动在工作区中显示终端
    showWorkspaceHostView('terminal')
  }

  function createTerminalForSelectedNode() {
    if (!socket.value) {
      console.warn('[independent-terminal] No socket connection')
      return
    }

    const nodeId = String(selectedTerminalNodeId.value || '').trim()
    if (!nodeId) {
      console.warn('[independent-terminal] No terminal node selected')
      return
    }

    const message = {
      type: 'terminal_create',
      payload: {
        node_id: nodeId,
      },
    }
    socket.value.send(JSON.stringify(message))
    // 标记本设备发起了终端创建，terminal_created 回包时自动切换
    markTerminalCreationPending()

    // 自动在工作区中显示终端
    showWorkspaceHostView('terminal')
  }

  // 在指定节点上创建独立终端（大厅节点右键菜单）
  function createTerminalForNode(nodeId) {
    if (!socket.value) {
      console.warn('[independent-terminal] No socket connection')
      return
    }
    const normalizedNodeId = String(nodeId || '').trim()
    if (!normalizedNodeId) {
      console.warn('[independent-terminal] No terminal node specified')
      return
    }
    const message = {
      type: 'terminal_create',
      payload: { node_id: normalizedNodeId },
    }
    socket.value.send(JSON.stringify(message))
    // 标记本设备发起了终端创建，terminal_created 回包时自动切换
    markTerminalCreationPending()
    // 自动在工作区中显示终端
    showWorkspaceHostView('terminal')
  }

  function createTerminalForAgent(agent) {
    if (!socket.value) {
      console.warn('[independent-terminal] No socket connection')
      return
    }

  
    // 直接使用传入的 agent 参数创建终端，不依赖异步切换
    const nodeId = String(agent?.node_id || '').trim() || ''
    const payload = {}
    if (nodeId) {
      payload.node_id = nodeId
    }
    const workingDir = agent?.working_dir?.trim()
    if (workingDir) {
      payload.working_dir = workingDir
    }
    const message = {
      type: 'terminal_create',
      payload,
    }
    socket.value.send(JSON.stringify(message))
    // 标记本设备发起了终端创建，terminal_created 回包时自动切换
    markTerminalCreationPending()
  
    // 自动在工作区中显示终端
    showWorkspaceHostView('terminal')
  }

  function closeTerminal(terminalId) {
    // 关闭标签页仅关闭本地 xterm 视图，不退出实际终端进程（类似 tmux detach）。
    // 后端会话保留，可通过「同步」按钮重新恢复（restoreTerminalSessions）。
  
    // 清理终端实例
    const sessionIndex = terminalSessions.value.findIndex(t => t.terminal_id === terminalId)
    if (sessionIndex !== -1) {
      const session = terminalSessions.value[sessionIndex]
      if (session.terminal) {
        try {
          session.terminal.dispose()
        } catch (error) {
          console.warn('[independent-terminal] Failed to dispose terminal', error)
        }
      }
      // 从数组中移除
      terminalSessions.value.splice(sessionIndex, 1)
    }
  
    // 如果关闭的是当前激活的终端，切换到另一个
    if (activeTerminalId.value === terminalId) {
      activeTerminalId.value = terminalSessions.value.length > 0 ? terminalSessions.value[0].terminal_id : null
    }
  
    // 清理 ref
    independentTerminalHosts.value.delete(terminalId)
  }

  const TERMINAL_PANEL_MIN_WIDTH = 400
  const TERMINAL_PANEL_MIN_HEIGHT = 300
  const TERMINAL_PANEL_STORAGE_KEY = 'jarvis_terminal_panel_rect'
  const terminalResizeDirections = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

  function getDefaultTerminalPanelRect() {
    return {
      top: 88,
      left: Math.max(window.innerWidth - 824, 16),
      width: 800,
      height: 500,
    }
  }

  function loadTerminalPanelRect() {
    const defaultTerminalPanelRect = getDefaultTerminalPanelRect()
    const savedValue = localStorage.getItem(TERMINAL_PANEL_STORAGE_KEY)
    if (!savedValue) {
      return defaultTerminalPanelRect
    }

    try {
      const parsedValue = JSON.parse(savedValue)
      if (
        typeof parsedValue.top !== 'number' ||
        typeof parsedValue.left !== 'number' ||
        typeof parsedValue.width !== 'number' ||
        typeof parsedValue.height !== 'number'
      ) {
        return defaultTerminalPanelRect
      }

      return parsedValue
    } catch {
      return defaultTerminalPanelRect
    }
  }

  function saveTerminalPanelRect() {
    localStorage.setItem(TERMINAL_PANEL_STORAGE_KEY, JSON.stringify(terminalPanelRect.value))
  }

  const terminalPanelRect = ref(loadTerminalPanelRect())

  const terminalPanelInteraction = ref({
    active: false,
    mode: null,
    direction: null,
    startX: 0,
    startY: 0,
    startTop: 0,
    startLeft: 0,
    startWidth: 0,
    startHeight: 0,
  })

  const terminalPanelStyle = computed(() => ({
    top: `${terminalPanelRect.value.top}px`,
    left: `${terminalPanelRect.value.left}px`,
    width: `${terminalPanelRect.value.width}px`,
    height: `${terminalPanelRect.value.height}px`,
    zIndex: activeWindow.value === 'terminal' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
  }))

  function getTerminalPanelBounds() {
    const HEADER_HEIGHT = 32 // 标题栏高度
    const MIN_VISIBLE_WIDTH = 100 // 至少保留100px面板宽度可见
    return {
      minTop: 0, // 标题栏不能拖到窗口顶部之外
      minLeft: 0, // 标题栏不能拖到窗口左侧之外
      maxLeft: window.innerWidth - MIN_VISIBLE_WIDTH, // 保留至少100px面板宽度可见
      maxTop: window.innerHeight - HEADER_HEIGHT, // 保留标题栏高度可见
    }
  }

  function ensureTerminalPanelInViewport() {
    const HEADER_HEIGHT = 32 // 标题栏高度
    const MIN_VISIBLE_WIDTH = 100 // 至少保留100px面板宽度可见
    const maxWidth = Math.max(window.innerWidth, TERMINAL_PANEL_MIN_WIDTH)
    const maxHeight = Math.max(window.innerHeight, TERMINAL_PANEL_MIN_HEIGHT)

    terminalPanelRect.value.width = clamp(terminalPanelRect.value.width, TERMINAL_PANEL_MIN_WIDTH, maxWidth)
    terminalPanelRect.value.height = clamp(terminalPanelRect.value.height, TERMINAL_PANEL_MIN_HEIGHT, maxHeight)

    // 标题栏不能移出窗口
    terminalPanelRect.value.left = clamp(
      terminalPanelRect.value.left,
      0, // 标题栏不能拖到窗口左侧之外
      window.innerWidth - MIN_VISIBLE_WIDTH // 保留至少100px面板宽度可见
    )
    terminalPanelRect.value.top = clamp(
      terminalPanelRect.value.top,
      0, // 标题栏不能拖到窗口顶部之外
      window.innerHeight - HEADER_HEIGHT // 保留标题栏高度可见
    )
  }

  function startTerminalPanelMove(event) {
    if (windowWidth.value <= 768) return
    if (event.target.closest('.terminal-panel-actions')) return

    focusWindow('terminal')

    terminalPanelInteraction.value = {
      active: false,
      mode: 'move',
      direction: null,
      startX: event.clientX,
      startY: event.clientY,
      startTop: terminalPanelRect.value.top,
      startLeft: terminalPanelRect.value.left,
      startWidth: terminalPanelRect.value.width,
      startHeight: terminalPanelRect.value.height,
    }

    document.addEventListener('mousemove', onTerminalPanelPointerMove)
    document.addEventListener('mouseup', stopTerminalPanelInteraction)
  }

  function startTerminalPanelResize(event, direction) {
    if (windowWidth.value <= 768) return

    terminalPanelInteraction.value = {
      active: true,
      mode: 'resize',
      direction,
      startX: event.clientX,
      startY: event.clientY,
      startTop: terminalPanelRect.value.top,
      startLeft: terminalPanelRect.value.left,
      startWidth: terminalPanelRect.value.width,
      startHeight: terminalPanelRect.value.height,
    }

    document.addEventListener('mousemove', onTerminalPanelPointerMove)
    document.addEventListener('mouseup', stopTerminalPanelInteraction)
    event.preventDefault()
    event.stopPropagation()
  }

  function onTerminalPanelPointerMove(event) {
    const deltaX = event.clientX - terminalPanelInteraction.value.startX
    const deltaY = event.clientY - terminalPanelInteraction.value.startY

    if (terminalPanelInteraction.value.mode === 'move' && !terminalPanelInteraction.value.active) {
      const dragDistance = Math.hypot(deltaX, deltaY)
      if (dragDistance < PANEL_DRAG_ACTIVATION_DISTANCE) {
        return
      }

      terminalPanelInteraction.value = {
        ...terminalPanelInteraction.value,
        active: true,
      }
      event.preventDefault()
    }

    if (!terminalPanelInteraction.value.active) return

    if (terminalPanelInteraction.value.mode === 'move') {
      const bounds = getTerminalPanelBounds()
      terminalPanelRect.value.left = clamp(terminalPanelInteraction.value.startLeft + deltaX, bounds.minLeft, bounds.maxLeft)
      terminalPanelRect.value.top = clamp(terminalPanelInteraction.value.startTop + deltaY, bounds.minTop, bounds.maxTop)
      return
    }

    const direction = terminalPanelInteraction.value.direction || ''
    const startLeft = terminalPanelInteraction.value.startLeft
    const startTop = terminalPanelInteraction.value.startTop
    const startWidth = terminalPanelInteraction.value.startWidth
    const startHeight = terminalPanelInteraction.value.startHeight

    let nextLeft = startLeft
    let nextTop = startTop
    let nextWidth = startWidth
    let nextHeight = startHeight

    if (direction.includes('e')) {
      nextWidth = clamp(startWidth + deltaX, TERMINAL_PANEL_MIN_WIDTH, Math.max(window.innerWidth - startLeft, TERMINAL_PANEL_MIN_WIDTH))
    }

    if (direction.includes('s')) {
      nextHeight = clamp(startHeight + deltaY, TERMINAL_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - startTop, TERMINAL_PANEL_MIN_HEIGHT))
    }

    if (direction.includes('w')) {
      const desiredLeft = clamp(startLeft + deltaX, 0, startLeft + startWidth - TERMINAL_PANEL_MIN_WIDTH)
      nextLeft = desiredLeft
      nextWidth = startWidth - (desiredLeft - startLeft)
    }

    if (direction.includes('n')) {
      const desiredTop = clamp(startTop + deltaY, 0, startTop + startHeight - TERMINAL_PANEL_MIN_HEIGHT)
      nextTop = desiredTop
      nextHeight = startHeight - (desiredTop - startTop)
    }

    if (nextLeft + nextWidth > window.innerWidth) {
      nextWidth = Math.max(TERMINAL_PANEL_MIN_WIDTH, window.innerWidth - nextLeft)
    }

    if (nextTop + nextHeight > window.innerHeight) {
      nextHeight = Math.max(TERMINAL_PANEL_MIN_HEIGHT, window.innerHeight - nextTop)
    }

    terminalPanelRect.value.left = clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0))
    terminalPanelRect.value.top = clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0))
    terminalPanelRect.value.width = clamp(nextWidth, TERMINAL_PANEL_MIN_WIDTH, Math.max(window.innerWidth - terminalPanelRect.value.left, TERMINAL_PANEL_MIN_WIDTH))
    terminalPanelRect.value.height = clamp(nextHeight, TERMINAL_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - terminalPanelRect.value.top, TERMINAL_PANEL_MIN_HEIGHT))
  }

  function stopTerminalPanelInteraction() {
    terminalPanelInteraction.value = {
      active: false,
      mode: null,
      direction: null,
      startX: 0,
      startY: 0,
      startTop: 0,
      startLeft: 0,
      startWidth: 0,
      startHeight: 0,
    }

    document.removeEventListener('mousemove', onTerminalPanelPointerMove)
    document.removeEventListener('mouseup', stopTerminalPanelInteraction)
    saveTerminalPanelRect()
  }

  function switchTerminal(terminalId) {
    activeTerminalId.value = terminalId
  
    // 聚焦到选中的终端
    nextTick(() => {
      const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
      if (session && session.terminal) {
        try {
          session.terminal.focus()
        } catch (error) {
          console.warn('[independent-terminal] Failed to focus terminal', error)
        }
      }
    })
  }

  function sendTerminalInput(terminalId, data) {
    if (!socket.value) {
      console.warn('[independent-terminal] No socket connection')
      return
    }
  
    const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
    const payload = { terminal_id: terminalId, data }
    if (session?.node_id) {
      payload.node_id = session.node_id
    }
    const message = {
      type: 'terminal_session_input',
      payload,
    }
    socket.value.send(JSON.stringify(message))
  }

  function sendTerminalResize(terminalId, rows, cols) {
    if (!socket.value) {
      console.warn('[independent-terminal] No socket connection')
      return
    }
  
    const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
    const payload = { terminal_id: terminalId, rows, cols }
    if (session?.node_id) {
      payload.node_id = session.node_id
    }
    const message = {
      type: 'terminal_session_resize',
      payload,
    }
    socket.value.send(JSON.stringify(message))
  }

  watch(showTerminalPanel, (newValue, oldValue) => {
    if (!newValue && oldValue) {
      stopTerminalPanelInteraction()
      terminalSessions.value.forEach(session => {
        if (session.resizeObserver) {
          session.resizeObserver.disconnect()
        }
      })
    } else if (newValue && !oldValue) {
      ensureTerminalPanelInViewport()
      saveTerminalPanelRect()
      nextTick(() => {
        const activeSession = terminalSessions.value.find(s => s.terminal_id === activeTerminalId.value)
        if (activeSession && activeSession.resizeObserver && activeSession.hostEl) {
          activeSession.resizeObserver.observe(activeSession.hostEl)
          if (activeSession.fitAddon && activeSession.terminal) {
            activeSession.fitAddon.fit()
            sendTerminalResize(activeSession.terminal_id, activeSession.terminal.rows, activeSession.terminal.cols)
          }
        }
      })
    }
  })

  // 监听终端切换
  watch(activeTerminalId, (newId, oldId) => {
    if (newId !== oldId) {
      // 切换终端标签

      // 禁用旧终端的 ResizeObserver
      const oldSession = terminalSessions.value.find(s => s.terminal_id === oldId)
      if (oldSession && oldSession.resizeObserver) {
        oldSession.resizeObserver.disconnect()
      }

      // 启用新终端的 ResizeObserver
      const newSession = terminalSessions.value.find(s => s.terminal_id === newId)
      if (newSession && newSession.resizeObserver && newSession.hostEl) {
        nextTick(() => {
          newSession.resizeObserver.observe(newSession.hostEl)
          if (newSession.fitAddon && newSession.terminal) {
            newSession.fitAddon.fit()
            sendTerminalResize(newSession.terminal_id, newSession.terminal.rows, newSession.terminal.cols)
          }
        })
      }
    }
  })

  const showTerminalShareModal = ref(false)
  const editingShareTerminalId = ref(null)
  const terminalShareRead = ref([])
  const terminalShareInteract = ref([])

  async function openTerminalShareDialog(terminalId) {
    editingShareTerminalId.value = terminalId
    terminalShareRead.value = []
    terminalShareInteract.value = []
    showTerminalShareModal.value = true
    // 获取用户列表供选择
    await fetchUserList()
  }

  // 保存终端分享 ACL：PUT /api/terminals/{id}/acl（主网关路径，非 node 代理）
  async function saveTerminalShare() {
    const terminalId = editingShareTerminalId.value
    if (!terminalId) return
    try {
      const { host, port } = getGatewayAddress()
      const response = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/terminals/${encodeURIComponent(terminalId)}/acl`, {
        method: 'PUT',
        body: JSON.stringify({
          read: terminalShareRead.value,
          interact: terminalShareInteract.value,
        })
      })
      if (!response.ok) {
        const error = await response.json()
        alert(`分享失败: ${error.error?.message || error.detail || '未知错误'}`)
        return
      }
      showToast('分享设置已保存', 'success')
      showTerminalShareModal.value = false
    } catch (error) {
      console.error('[TERMINAL] Share update failed:', error)
      alert(`分享失败: ${error.message}`)
    }
  }

  const filteredUserOptionsForTerminalShare = computed(() => {
    const ownerId = auth.value.userInfo?.user_id || ''
    return availableUserOptions.value.filter(user => {
      if (user.user_id === ownerId) return false
      if (user.is_admin) return false
      return true
    })
  })

  return {
    terminalHosts,
    terminals,
    getExecutionSessionKey,
    terminalSessions,
    activeTerminalId,
    independentTerminalHosts,
    isCreatingTerminalSession,
    terminalCreationTracker,
    _debouncedSaveExecHistory,
    appendExecution,
    clearTerminalCache,
    getTerminalBufferContent,
    syncTerminalSize,
    disposeExecutionTerminal,
    initExecutionTerminal,
    setTerminalRef,
    setTerminalHostRef,
    initIndependentTerminal,
    decodeTerminalBase64,
    attachTerminalSession,
    restoreTerminalSessions,
    markTerminalCreationPending,
    createTerminal,
    createTerminalForSelectedNode,
    createTerminalForNode,
    createTerminalForAgent,
    closeTerminal,
    TERMINAL_PANEL_MIN_WIDTH,
    TERMINAL_PANEL_MIN_HEIGHT,
    TERMINAL_PANEL_STORAGE_KEY,
    terminalResizeDirections,
    getDefaultTerminalPanelRect,
    loadTerminalPanelRect,
    saveTerminalPanelRect,
    terminalPanelRect,
    terminalPanelInteraction,
    terminalPanelStyle,
    getTerminalPanelBounds,
    ensureTerminalPanelInViewport,
    startTerminalPanelMove,
    startTerminalPanelResize,
    onTerminalPanelPointerMove,
    stopTerminalPanelInteraction,
    switchTerminal,
    sendTerminalInput,
    sendTerminalResize,
    showTerminalShareModal,
    editingShareTerminalId,
    terminalShareRead,
    terminalShareInteract,
    openTerminalShareDialog,
    saveTerminalShare,
    filteredUserOptionsForTerminalShare,
  }
}
