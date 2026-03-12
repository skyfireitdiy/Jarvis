<template>
  <div class="app">
    <!-- 顶部栏 -->
    <header class="app-header">
      <div class="header-title">
        <h1>Jarvis Web Gateway</h1>
      </div>
      <div class="header-actions">
        <button class="manual-interrupt-btn" v-if="!showInput" @click="sendManualInterrupt" :disabled="!socket" title="人工介入 (中断当前操作)">
          👤 人工介入
        </button>
        <button class="icon-btn" @click="showSettingsModal = true" :disabled="!socket">
          ⚙️
        </button>
        <div class="status">
          <span :class="['dot', connectionStatus]"></span>
          {{ connectionLabel }}
        </div>
      </div>
    </header>

    <!-- 消息列表 -->
    <main class="chat-container">
      <div class="messages" ref="outputList">
        <article v-for="(item, index) in outputs" :key="index" class="message" :class="`message-${item.output_type?.toLowerCase()}`">
          <div class="message-content">
            <div class="message-meta-left">
              <span class="badge">{{ item.output_type || '' }}</span>
              <span class="agent-name">{{ item.agent_name || '' }}</span>
              <span class="non-interactive" v-if="item.non_interactive">🔕</span>
              <span class="interactive" v-if="item.non_interactive === false">💬</span>
              <span class="interactive" v-if="item.non_interactive === undefined"></span>
              <span class="timestamp">{{ item.timestamp || '' }}</span>
            </div>
            <div class="message-body markdown-content" v-html="item.html"></div>
          </div>
          <!-- 终端嵌入 -->
          <div v-if="item.output_type === 'execution' && item.execution_id" class="terminal-wrapper">
            <div :ref="el => setTerminalRef(item.execution_id, el)" class="terminal-host"></div>
          </div>
        </article>
        <!-- 确认对话框 -->
        <article v-if="confirmDialog" class="message message-confirm">
          <div class="confirm-box">
            <p class="confirm-message">{{ confirmDialog.message }}</p>
            <div class="confirm-actions">
              <button class="confirm-btn cancel" @click="confirmDialog.cancelCallback">取消</button>
              <button class="confirm-btn confirm" @click="confirmDialog.confirmCallback">确认</button>
            </div>
          </div>
        </article>
      </div>
    </main>

    <!-- 底部输入区 -->
    <footer class="input-area" v-if="showInput || isExecuting">
      <!-- 多行输入模式 -->
      <div class="input-wrapper multi-line" v-if="showInput && inputMode === 'multi'">
        <p class="input-hint" v-if="inputTip">{{ inputTip }}</p>
        <textarea v-model="inputText" placeholder="多行输入 (Ctrl+Enter 发送)" @keydown.ctrl.enter="submitInput"></textarea>
        <div class="input-actions">
          <button class="send-btn" @click="submitInput" :disabled="!inputText.trim()">发送 (Ctrl+Enter)</button>
        </div>
      </div>
      
      <!-- 单行输入模式 -->
      <div class="input-wrapper single-line" v-if="showInput && inputMode === 'single'">
        <p class="input-hint" v-if="inputTip">{{ inputTip }}</p>
        <div class="input-controls">
          <input v-model="inputText" placeholder="输入内容 (Enter 发送)" @keyup.enter="submitInput" />
          <button class="send-btn" @click="submitInput" :disabled="!inputText.trim()">发送</button>
        </div>
      </div>
    </footer>

    <!-- 连接弹窗 -->
    <div class="modal-overlay" v-if="showConnectModal">
      <div class="modal connect-modal">
        <h2>连接到 Jarvis</h2>
        <div class="form-group">
          <label>Token</label>
          <input v-model="auth.token" placeholder="可选" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="auth.password" type="password" placeholder="可选" />
        </div>
        <div class="form-group inline">
          <div class="form-item">
            <label>地址</label>
            <input v-model="backendHost" placeholder="127.0.0.1" />
          </div>
          <div class="form-item">
            <label>端口</label>
            <input v-model="backendPort" placeholder="8000" />
          </div>
        </div>
        <button class="primary-btn" @click="connect" :disabled="connecting">
          {{ connecting ? '连接中...' : '连接' }}
        </button>
      </div>
    </div>

    <!-- 设置弹窗 -->
    <div class="modal-overlay" v-if="showSettingsModal">
      <div class="modal settings-modal">
        <div class="modal-header">
          <h2>连接设置</h2>
          <button class="close-btn" @click="showSettingsModal = false">×</button>
        </div>
        <div class="form-group">
          <label>Token</label>
          <input v-model="auth.token" placeholder="可选" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="auth.password" type="password" placeholder="可选" />
        </div>
        <div class="form-group inline">
          <div class="form-item">
            <label>地址</label>
            <input v-model="backendHost" />
          </div>
          <div class="form-item">
            <label>端口</label>
            <input v-model="backendPort" />
          </div>
        </div>
        <div class="form-group">
          <label>Session ID</label>
          <input v-model="sessionId" placeholder="留空自动生成" />
        </div>
        <div class="modal-actions">
          <button class="ghost-btn" @click="showSettingsModal = false">取消</button>
          <button class="primary-btn" @click="reconnect">重新连接</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { marked } from 'marked'
import { Terminal } from 'xterm'
import { FitAddon } from '@xterm/addon-fit'
import 'xterm/css/xterm.css'

// 认证和连接配置
const auth = ref({ token: '', password: '' })
const sessionId = ref('')
const backendHost = ref('127.0.0.1')
const backendPort = ref('8000')
const socket = ref(null)
const connecting = ref(false)

// 弹窗控制
const showConnectModal = ref(true)  // 初始显示连接弹窗
const showSettingsModal = ref(false) // 设置弹窗

// 消息和终端
const outputs = ref([])
const outputList = ref(null)
const terminalHosts = ref(new Map())
const terminals = ref([]) // [{ executionId, terminal, active, hostEl, resizeObserver, lastSize, pendingChunks, ended }]

// 输入控制
const inputText = ref('')
const inputMode = ref('single')
const inputTip = ref('')
const showInput = ref(false) // 是否显示输入框

// 确认对话框
const confirmDialog = ref(null) // { message, confirmCallback, cancelCallback }

// 执行状态
const isExecuting = ref(false)

const connectionStatus = computed(() => {
  if (connecting.value) return 'connecting'
  return socket.value ? 'online' : 'offline'
})

const connectionLabel = computed(() => {
  if (connecting.value) return '连接中'
  return socket.value ? '已连接' : '未连接'
})

const inputModeLabel = computed(() => (inputMode.value === 'multi' ? '多行' : '单行'))

function connect() {
  if (socket.value) return
  const host = backendHost.value || window.location.hostname || '127.0.0.1'
  const port = backendPort.value || '8000'
  const url = `ws://${host}:${port}/ws${sessionId.value ? `?session_id=${sessionId.value}` : ''}`
  connecting.value = true
  const ws = new WebSocket(url)
  ws.onopen = () => {
    console.log('[ws] open')
    connecting.value = false
    socket.value = ws
    // 连接成功后关闭连接弹窗
    showConnectModal.value = false
    const payload = {}
    if (auth.value.token) payload.token = auth.value.token
    if (auth.value.password) payload.password = auth.value.password
    if (Object.keys(payload).length > 0) {
      ws.send(JSON.stringify({ type: 'auth', payload }))
      console.log('[ws] auth sent', payload)
    }
  }
  ws.onmessage = (event) => {
    let message = null
    try {
      message = JSON.parse(event.data)
    } catch (error) {
      console.warn('[ws] message parse failed', event.data)
      return
    }
    console.log('[ws] message', message)
    handleMessage(message)
  }
  ws.onclose = () => {
    console.log('[ws] close')
    socket.value = null
    connecting.value = false
  }
  ws.onerror = () => {
    console.error('[ws] error')
    connecting.value = false
  }
}

function disconnect() {
  if (socket.value) {
    socket.value.close()
  }
}

function reconnect() {
  // 断开现有连接
  if (socket.value) {
    socket.value.close()
  }
  // 关闭设置弹窗
  showSettingsModal.value = false
  // 重新连接
  connect()
}

function handleMessage(message) {
  if (!message || typeof message !== 'object') return
  const { type, payload } = message
  if (type === 'ready') {
    console.log('[ws] ready payload', payload)
    if (payload?.session_id) {
      sessionId.value = payload.session_id
    }
  } else if (type === 'output') {
    appendOutput(payload)
  } else if (type === 'input_request') {
    console.log('[ws] input_request', payload)
    inputTip.value = payload.tip || ''
    inputMode.value = payload.mode || 'multi'  // 默认多行
    inputText.value = payload.preset || ''
    showInput.value = true // 显示输入框
    nextTick(() => {
      // 聚焦到输入框
      const inputEl = document.querySelector(inputMode.value === 'multi' ? 'textarea' : 'input[type="text"]')
      inputEl?.focus()
    })
  } else if (type === 'confirm') {
    console.log('[ws] confirm', payload)
    confirmDialog.value = {
      message: payload.message || '请确认',
      confirmCallback: () => {
        sendConfirmResult(true)
        confirmDialog.value = null
      },
      cancelCallback: () => {
        sendConfirmResult(false)
        confirmDialog.value = null
      },
    }
  } else if (type === 'execution') {
    console.log('[ws] execution event received:', {
      event_type: payload?.event_type,
      execution_id: payload?.execution_id,
      message_type: payload?.message_type,
      has_data: 'data' in payload,
      data_len: payload?.data?.length || 0,
    })
    appendExecution(payload)
    // 只在首次创建终端时创建输出项
    const executionId = payload?.execution_id || 'default'
    const existingItem = outputs.value.find(
      item => item.output_type === 'execution' && item.execution_id === executionId
    )
    if (!existingItem) {
      console.log(`[ws] Creating new output item for execution ${executionId}`)
      appendOutput({
        output_type: 'execution',
        text: '',
        lang: 'text',
        payload: payload, // 保存 payload 以便后续使用
        execution_id: executionId,
      })
      // 等待 DOM 渲染完成后立即初始化终端
      nextTick(() => {
        console.log(`[ws] DOM rendered, initializing terminal ${executionId}`)
        const hostEl = terminalHosts.value.get(executionId)
        if (hostEl) {
          setTerminalRef(executionId, hostEl)
        } else {
          console.warn(`[ws] terminal-host element not found for execution ${executionId}`)
        }
      })
    } else {
      console.log('[ws] output item already exists for execution_id:', executionId)
    }
  } else if (type === 'error') {
    console.warn('[ws] error payload', payload)
    appendOutput({
      output_type: 'ERROR',
      text: payload?.message || '未知错误',
      lang: 'text',
    })
  }
}

function appendOutput(payload) {
  const html = payload?.lang === 'markdown' ? marked.parse(payload.text || '') : escapeHtml(payload.text || '')
  
  // 生成真实时间戳
  const showTimestamp = payload?.timestamp !== false
  const now = showTimestamp ? new Date().toLocaleTimeString('zh-CN', { hour12: false }) : ''
  
  // 从 context 中提取 agent 信息，但优先使用 payload 顶层的 agent_name
  const context = payload?.context || {}
  const agentName = payload?.agent_name || context.agent_name || context.agent || ''
  const nonInteractive = payload?.non_interactive !== undefined ? payload?.non_interactive : (context.non_interactive || false)
  
  const outputItem = {
    ...payload,
    html,
    timestamp: now,
    agent_name: agentName,
    non_interactive: nonInteractive,
  }
  
  console.log('[DEBUG] appendOutput outputItem:', outputItem)
  console.log('[DEBUG] output_type:', outputItem.output_type)
  console.log('[DEBUG] agent_name:', outputItem.agent_name)
  console.log('[DEBUG] Generated class:', `message-${outputItem.output_type?.toLowerCase()}`)
  
  outputs.value.push(outputItem)
  nextTick(() => {
    if (outputList.value) {
      const threshold = 50
      const distanceToBottom = outputList.value.scrollHeight - outputList.value.scrollTop - outputList.value.clientHeight
      if (distanceToBottom < threshold) {
        outputList.value.scrollTop = outputList.value.scrollHeight
      }
    }
  })
}

function appendExecution(payload) {
  const executionId = payload?.execution_id || 'default'
  const eventType = payload?.event_type
  
  console.log(`[terminal DEBUG] appendExecution: executionId=${executionId}, eventType=${eventType}, hasData=${!!payload?.data}, encoded=${payload?.encoded}`)
  
  // 处理 base64 编码的数据
  let data = payload?.data || ''
  if (payload?.encoded && data) {
    try {
      console.log(`[terminal DEBUG] Decoding base64 data, len=${data.length}`)
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
      console.log(`[terminal DEBUG] Decoded to string, len=${data.length}`)
    } catch (error) {
      console.error('[terminal] Failed to decode base64 data:', error)
      return
    }
  }
  
  // 检查是否需要创建新终端
  let termInfo = terminals.value.find(t => t.executionId === executionId)
  if (!termInfo) {
    console.log(`[terminal] Creating new terminal for execution ${executionId}`)
    termInfo = {
      executionId,
      terminal: null,
      active: true,
      hostEl: null,
      pendingChunks: [],
      ended: false,
    }
    terminals.value.push(termInfo)
    // 终端初始化移到 setTerminalRef 中，确保 DOM 元素准备好
  }
  
  console.log(`[terminal DEBUG] termInfo: terminal=${!!termInfo.terminal}, pendingChunks=${termInfo.pendingChunks?.length || 0}`)
  
  // 处理执行开始事件
  if (payload?.message_type === 'tool_stream_start' && !isExecuting.value) {
    console.log(`[terminal] Execution ${executionId} started`)
    isExecuting.value = true
  }
  
  // 处理执行结束事件
  if (payload?.message_type === 'tool_stream_end' && termInfo.active) {
    console.log(`[terminal] Execution ${executionId} ended, disabling interaction`)
    termInfo.active = false
    termInfo.ended = true
    isExecuting.value = false // 更新执行状态
    if (termInfo.terminal) {
      termInfo.terminal.writeln('\r\n[status] Execution completed - terminal is now read-only')
    }
  }
  
  // 输出到终端
  console.log(`[terminal] Writing to terminal: terminal=${!!termInfo.terminal}, eventType=${eventType}, data_len=${data.length}`)
  if (eventType === 'stdout' || eventType === 'stderr') {
    if (termInfo.terminal) {
      // 显示即将写入的数据（前100字符），用于调试
      const preview = data.substring(0, 100).replace(/\x1b/g, 'ESC').replace(/\r/g, 'CR').replace(/\n/g, 'LF')
      console.log(`[terminal] About to write ${data.length} bytes to terminal, preview: ${preview}`)
      try {
        termInfo.terminal.write(data)
        console.log(`[terminal] Write successful: ${data.length} bytes`)
      } catch (error) {
        console.error('[terminal] Write failed:', error)
      }
    } else if (data) {
      termInfo.pendingChunks?.push(data)
      console.log(`[terminal] Terminal not ready, buffered ${data.length} bytes, total pending=${termInfo.pendingChunks.length}`)
    }
  } else if (eventType === 'status') {
    const statusLine = `\r\n[status] ${payload.data || ''}`
    if (termInfo.terminal) {
      termInfo.terminal.writeln(statusLine)
    } else {
      termInfo.pendingChunks?.push(statusLine)
    }
  } else if (!termInfo.terminal && data) {
    console.log(`[terminal] Terminal not ready, skipping output for eventType=${eventType}`)
  }
}

function submitInput() {
  if (!socket.value) return
  
  // 先将用户输入回显到聊天窗口
  const userInput = inputText.value.trim()
  if (userInput) {
    console.log('[DEBUG] User input payload:', {
      output_type: 'user_input',
      agent_name: 'user',
      text: userInput,
      lang: 'text',
    })
    appendOutput({
      output_type: 'user_input',
      agent_name: 'user',
      text: userInput,
      lang: 'text',
    })
  }
  
  const message = {
    type: 'input_result',
    payload: {
      text: userInput,
      metadata: {
        session_id: sessionId.value || undefined,
      },
    },
  }
  console.log('[ws] send input_result', message)
  socket.value.send(JSON.stringify(message))
  inputText.value = ''
  showInput.value = false // 隐藏输入框
}

function sendConfirmResult(confirmed) {
  if (!socket.value) return
  const message = {
    type: 'confirm_result',
    payload: {
      confirmed,
      metadata: {
        session_id: sessionId.value || undefined,
      },
    },
  }
  console.log('[ws] send confirm_result', message)
  socket.value.send(JSON.stringify(message))
}

function sendInterrupt() {
  if (!socket.value) return
  const message = {
    type: 'interrupt',
    payload: {
      metadata: {
        session_id: sessionId.value || undefined,
      },
    },
  }
  console.log('[ws] send interrupt', message)
  socket.value.send(JSON.stringify(message))
}

function sendManualInterrupt() {
  if (!socket.value) return
  const message = {
    type: 'manual_interrupt',
    payload: {
      metadata: {
        session_id: sessionId.value || undefined,
      },
    },
  }
  console.log('[ws] send manual interrupt', message)
  socket.value.send(JSON.stringify(message))
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.innerText = text
  return div.innerHTML
}

function syncTerminalSize(executionId, termInfo) {
  console.log(`[terminal] syncTerminalSize called for execution ${executionId}`)
  if (!termInfo) {
    console.log(`[terminal] syncTerminalSize: termInfo is null`)
    return
  }
  if (!termInfo.terminal) {
    console.log(`[terminal] syncTerminalSize: terminal is null`)
    return
  }
  if (!termInfo.fitAddon) {
    console.log(`[terminal] syncTerminalSize: fitAddon is null`)
    return
  }
  
  // 使用 FitAddon 自动适配尺寸
  const oldCols = termInfo.terminal.cols
  const oldRows = termInfo.terminal.rows
  termInfo.fitAddon.fit()
  const newCols = termInfo.terminal.cols
  const newRows = termInfo.terminal.rows
  
  console.log(`[terminal] syncTerminalSize: ${oldCols}x${oldRows} -> ${newCols}x${newRows}`)
  
  // 如果尺寸没变，跳过
  if (oldCols === newCols && oldRows === newRows) {
    console.log(`[terminal] syncTerminalSize: size unchanged, skipping`)
    return
  }
  
  // 发送 resize 消息到后端
  if (!socket.value) return
  const message = {
    type: 'terminal_resize',
    payload: {
      execution_id: executionId,
      rows: newRows,
      cols: newCols,
    },
  }
  socket.value.send(JSON.stringify(message))
}

// 动态绑定终端 DOM 元素
function setTerminalRef(executionId, el) {
  const termInfo = terminals.value.find(t => t.executionId === executionId)
  if (el) {
    console.log(`[terminal] Setting ref for execution ${executionId}`)
    console.log(`[terminal] Element properties: clientWidth=${el.clientWidth}, clientHeight=${el.clientHeight}, offsetWidth=${el.offsetWidth}, offsetHeight=${el.offsetHeight}`)
    console.log(`[terminal] Computed style: ${window.getComputedStyle(el).width} x ${window.getComputedStyle(el).height}`)
    console.log(`[terminal] Parent element:`, el.parentElement)
    if (el.parentElement) {
      console.log(`[terminal] Parent size: ${window.getComputedStyle(el.parentElement).width} x ${window.getComputedStyle(el.parentElement).height}`)
    }
    terminalHosts.value.set(executionId, el)
    if (termInfo) {
      termInfo.hostEl = el
    }
    // 立即初始化终端
    if (termInfo && !termInfo.terminal) {
      console.log(`[terminal] Initializing terminal for execution ${executionId}`)
      console.log(`[terminal] Element size: width=${el.clientWidth}px, height=${el.clientHeight}px`)
      
      // 使用默认尺寸初始化
      termInfo.terminal = new Terminal({
        theme: {
          background: '#0b1220',
        },
        fontSize: 12,
      })
      termInfo.terminal.open(el)
      
      // 创建并加载 FitAddon
      termInfo.fitAddon = new FitAddon()
      termInfo.terminal.loadAddon(termInfo.fitAddon)
      
      // 使用 FitAddon 适配终端尺寸
      termInfo.fitAddon.fit()
      console.log(`[terminal] FitAddon fit: cols=${termInfo.terminal.cols}, rows=${termInfo.terminal.rows}`)
      
      // 设置 ResizeObserver 监听尺寸变化
      if (typeof ResizeObserver !== 'undefined') {
        termInfo.resizeObserver = new ResizeObserver(() => {
          syncTerminalSize(executionId, termInfo)
        })
        termInfo.resizeObserver.observe(el)
      }
      
      termInfo.terminal.onData(data => {
        if (!termInfo.active) return
        if (!socket.value) return
        const message = {
          type: 'terminal_input',
          payload: {
            execution_id: executionId,
            data,
          },
        }
        socket.value.send(JSON.stringify(message))
      })
      
      // 在下一帧触发初始尺寸计算
      requestAnimationFrame(() => {
        syncTerminalSize(executionId, termInfo)
        try {
          termInfo.terminal.focus()
        } catch (error) {
          // ignore focus errors
        }
      })
      
      // 额外延迟确保容器完全渲染
      setTimeout(() => {
        syncTerminalSize(executionId, termInfo)
      }, 300)
      if (termInfo.pendingChunks && termInfo.pendingChunks.length > 0) {
        termInfo.pendingChunks.forEach(chunk => {
          try {
            termInfo.terminal.write(chunk)
          } catch (error) {
            console.warn('[terminal] flush chunk failed', error)
          }
        })
        termInfo.pendingChunks = []
      }
      if (termInfo.ended) {
        termInfo.terminal.writeln('\r\n[status] Execution completed - terminal is now read-only')
      }
      termInfo.terminal.writeln(`\r\n[Terminal ${executionId}] Ready.\r\n`)
    } else if (termInfo) {
      syncTerminalSize(executionId, termInfo)
    }
  } else {
    terminalHosts.value.delete(executionId)
    if (termInfo?.resizeObserver) {
      termInfo.resizeObserver.disconnect()
      termInfo.resizeObserver = null
    }
    if (termInfo) {
      termInfo.hostEl = null
    }
  }
}

onMounted(() => {
  // 不再在页面加载时创建终端，改为动态创建
  console.log('[app] Mounted')
})
</script>

<style scoped>
/* 全局布局 */
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #0d1117;
  color: #c9d1d9;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
  overflow-x: hidden;
}

/* 顶部栏 */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  flex-shrink: 0;
}

.header-title h1 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #e6edf3;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.icon-btn {
  background: transparent;
  border: none;
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
  color: #8b949e;
  transition: color 0.2s;
}

.icon-btn:hover:not(:disabled) {
  color: #e6edf3;
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.manual-interrupt-btn {
  background: #f0883e;
  border: none;
  border-radius: 6px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  padding: 6px 12px;
  cursor: pointer;
  transition: background 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.manual-interrupt-btn:hover:not(:disabled) {
  background: #e37a33;
}

.manual-interrupt-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #8b949e;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot.offline {
  background: #f85149;
}

.dot.connecting {
  background: #d29922;
}

.dot.online {
  background: #3fb950;
}

/* 聊天容器 */
.chat-container {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.messages {
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  background: #161b22;
  border-radius: 8px;
  padding: 8px 12px;
  border: 1px solid #30363d;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 用户输入消息 - 右对齐样式（必须放在 .message 之后以覆盖） */
.message.message-user_input {
  background: #1f6feb !important;
  border-color: #1f6feb !important;
  align-self: flex-end;
  max-width: 80%;
}

.message.message-user_input .message-meta-left {
  /* 用户输入消息显示元数据，使用 grid 布局 */
  min-width: 260px;
  display: grid;
  grid-template-columns: repeat(4, auto);
  gap: 8px;
  align-items: center;
  justify-self: start;
}

.message.message-user_input .badge {
  background: rgba(255, 255, 255, 0.3);
  color: #fff;
  font-size: 10px;
  padding: 2px 6px;
}

.message.message-user_input .agent-name {
  color: rgba(255, 255, 255, 0.9);
  font-size: 10px;
}

.message.message-user_input .timestamp {
  color: rgba(255, 255, 255, 0.7);
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
  font-size: 10px;
}

.message.message-user_input .message-body {
  color: #fff !important;
  font-style: italic !important;
}

.message-content {
  display: grid;
  grid-template-columns: min-content 1fr;
  gap: 12px;
  align-items: start;
  text-align: left;
}

.message-content .message-meta-left {
  min-width: 260px;
  display: grid;
  grid-template-columns: repeat(4, auto);
  gap: 8px;
  align-items: center;
  justify-self: start;
}

.message-meta-left .badge,
.message-meta-left .agent-name,
.message-meta-left .non-interactive,
.message-meta-left .interactive,
.message-meta-left .timestamp {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.message-meta-left .badge {
  min-width: 60px;
  justify-self: start;
}

.message-meta-left .agent-name {
  min-width: 80px;
  justify-self: start;
}

.message-meta-left .non-interactive,
.message-meta-left .interactive {
  min-width: 20px;
  justify-self: start;
}

.message-meta-left .timestamp {
  min-width: 80px;
  justify-self: start;
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
  font-size: 10px;
}

.message-content .message-body {
  font-size: 13px;
  line-height: 1.5;
  color: #e6edf3;
  justify-self: start;
}

.message-meta-left .badge {
  font-size: 10px;
  padding: 2px 6px;
  background: #21262d;
  color: #8b949e;
}

.message-meta-left .agent-name {
  font-size: 10px;
  color: #58a6ff;
  font-weight: 500;
}

.message-meta-left .non-interactive,
.message-meta-left .interactive {
  font-size: 12px;
  line-height: 1;
}

.message-meta-left .non-interactive {
  color: #f0883e;
}

.message-meta-left .interactive {
  color: #58a6ff;
}

.message-meta-left .timestamp {
  font-size: 10px;
  color: #8b949e;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 12px;
  background: #21262d;
  color: #8b949e;
}

.timestamp {
  font-size: 11px;
  color: #8b949e;
}

.message-body {
  color: #e6edf3;
  line-height: 1.6;
  word-wrap: break-word;
}

.message-body.markdown-content :deep(pre) {
  background: #0d1117;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.message-body.markdown-content :deep(code) {
  background: #0d1117;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
}

.message-body.markdown-content :deep(p) {
  margin: 8px 0;
}

/* 终端 */
.terminal-wrapper {
  margin-top: 12px;
  border: 1px solid #30363d;
  border-radius: 6px;
  overflow: hidden;
  max-height: 600px;
  display: flex;
  flex-direction: column;
}

.terminal-host {
  background: #0d1117;
  flex: 1;
  min-height: 400px;
  overflow: hidden;
}

/* 确认对话框 */
.message-confirm {
  background: #21262d;
  border-color: #58a6ff;
}

.confirm-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.confirm-message {
  margin: 0;
  color: #e6edf3;
}

.confirm-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.confirm-btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid #30363d;
  background: #21262d;
  color: #e6edf3;
  transition: all 0.2s;
}

.confirm-btn:hover {
  background: #30363d;
}

.confirm-btn.confirm {
  background: #238636;
  border-color: #238636;
}

.confirm-btn.confirm:hover {
  background: #2ea043;
}

/* 输入区 */
.input-area {
  background: #161b22;
  border-top: 1px solid #30363d;
  flex-shrink: 0;
}

.input-wrapper {
  padding: 16px;
}

/* 多行输入模式 */
.input-wrapper.multi-line {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  margin: 0 -16px; /* 抵消父容器 padding */
  width: calc(100% + 32px); /* 补偿 margin */
}

.input-wrapper.multi-line textarea {
  width: 100%;
  min-height: 120px;
  max-height: 300px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 12px;
  color: #e6edf3;
  font-size: 14px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  resize: vertical;
  box-sizing: border-box; /* 确保 padding 不会增加总宽度 */
}

.input-wrapper.multi-line textarea:focus {
  outline: none;
  border-color: #58a6ff;
}

.input-wrapper.multi-line .input-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

/* 单行输入模式 */
.input-wrapper.single-line {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.input-wrapper.single-line .input-controls {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.input-wrapper.single-line input {
  flex: 1;
  min-width: 0; /* 允许 flex item 收缩 */
  padding: 10px 14px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  color: #e6edf3;
  font-size: 14px;
}

.input-wrapper.single-line input:focus {
  outline: none;
  border-color: #58a6ff;
}

.input-wrapper.single-line .send-btn {
  padding: 10px 20px;
}

/* 通用 */
.input-hint {
  margin: 0;
  font-size: 13px;
  color: #8b949e;
}

.send-btn {
  background: #238636;
  border: none;
  border-radius: 6px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  background: #2ea043;
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cancel-btn {
  padding: 8px 16px;
  background: transparent;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #8b949e;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.cancel-btn:hover {
  background: #21262d;
  color: #e6edf3;
}

.interrupt-wrapper {
  padding: 12px 16px;
}

.interrupt-btn {
  width: 100%;
  padding: 8px;
  background: #f85149;
  border: none;
  border-radius: 6px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.interrupt-btn:hover {
  background: #da3633;
}

/* 模态框 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(13, 17, 23, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 16px;
}

.modal {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 24px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.connect-modal h2,
.settings-modal h2 {
  margin: 0 0 20px 0;
  font-size: 20px;
  font-weight: 600;
  color: #e6edf3;
}

.form-group {
  margin-bottom: 16px;
}

.form-group.inline {
  display: flex;
  gap: 12px;
}

.form-group.inline .form-item {
  flex: 1;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #8b949e;
}

.form-group input {
  width: 100%;
  padding: 8px 12px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #e6edf3;
  font-size: 14px;
}

.form-group input:focus {
  outline: none;
  border-color: #58a6ff;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.modal-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #e6edf3;
}

.close-btn {
  background: transparent;
  border: none;
  font-size: 24px;
  color: #8b949e;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: #e6edf3;
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 24px;
}

.primary-btn {
  padding: 8px 16px;
  background: #238636;
  border: none;
  border-radius: 6px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.primary-btn:hover:not(:disabled) {
  background: #2ea043;
}

.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ghost-btn {
  padding: 8px 16px;
  background: transparent;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #e6edf3;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.ghost-btn:hover {
  background: #21262d;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .header-title h1 {
    font-size: 16px;
  }
  
  .messages {
    padding: 12px;
  }
  
  .message {
    padding: 10px 12px;
  }
  
  .modal {
    max-width: 100%;
    padding: 20px;
  }
  
  .input-controls {
    flex-direction: column;
  }
  
  .send-btn {
    width: 100%;
  }
}
</style>
