<template>
  <div class="app">
    <header class="app-header">
      <div>
        <h1>Jarvis Web Gateway</h1>
        <p class="subtitle">WebSocket + Gateway 交互面板</p>
      </div>
      <div class="status">
        <span :class="['dot', connectionStatus]"></span>
        {{ connectionLabel }}
      </div>
    </header>

    <section class="panel auth">
      <h2>认证</h2>
      <div class="field">
        <label>Token</label>
        <input v-model="auth.token" placeholder="可选" />
      </div>
      <div class="field">
        <label>Password</label>
        <input v-model="auth.password" type="password" placeholder="可选" />
      </div>
      <div class="field">
        <label>后端地址</label>
        <input v-model="backendHost" placeholder="如 127.0.0.1" />
      </div>
      <div class="field">
        <label>后端端口</label>
        <input v-model="backendPort" placeholder="如 8000" />
      </div>
      <div class="field">
        <label>Session ID</label>
        <input v-model="sessionId" placeholder="留空自动生成" />
      </div>
      <button class="primary" @click="connect" :disabled="connecting">
        {{ connecting ? '连接中...' : '连接 WebSocket' }}
      </button>
      <button class="ghost" @click="disconnect" :disabled="!socket">
        断开连接
      </button>
    </section>

    <section class="panel output">
      <h2>输出</h2>
      <div class="output-list" ref="outputList">
        <article v-for="(item, index) in outputs" :key="index" class="output-item">
          <div class="output-meta">
            <span class="badge">{{ item.output_type }}</span>
            <span v-if="item.timestamp" class="timestamp">{{ item.timestamp }}</span>
            <span v-if="item.section" class="section">{{ item.section }}</span>
          </div>
          <div class="output-body" v-html="item.html"></div>
          <!-- 如果这是执行事件，嵌入对应的终端 -->
          <div v-if="item.output_type === 'execution' && item.execution_id" class="terminal-wrapper">
            <div :ref="el => setTerminalRef(item.execution_id, el)" class="terminal-host"></div>
          </div>
        </article>
      </div>
    </section>

    <section class="panel input">
      <h2>输入</h2>
      <p class="hint">当前模式：{{ inputModeLabel }}</p>
      <div v-if="inputMode === 'multi'" class="input-area">
        <textarea v-model="inputText" rows="5" placeholder="多行输入"></textarea>
        <button class="primary" @click="submitInput">提交</button>
      </div>
      <div v-else class="input-area">
        <input v-model="inputText" placeholder="单行输入" @keyup.enter="submitInput" />
        <button class="primary" @click="submitInput">提交</button>
      </div>
      <div v-if="inputTip" class="input-tip">提示：{{ inputTip }}</div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { marked } from 'marked'
import { Terminal } from 'xterm'
import 'xterm/css/xterm.css'

const auth = ref({ token: '', password: '' })
const sessionId = ref('')
const backendHost = ref('127.0.0.1')
const backendPort = ref('8000')
const socket = ref(null)
const connecting = ref(false)
const outputs = ref([])
const inputText = ref('')
const inputMode = ref('single')
const inputTip = ref('')
const outputList = ref(null)
// 多终端管理：每个 executionId 对应一个终端实例
const terminalHosts = ref(new Map())
const terminals = ref([]) // [{ executionId, terminal, active, hostEl, resizeObserver, lastSize, pendingChunks, ended }]

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
    inputMode.value = payload.metadata?.mode || 'single'
    inputText.value = payload.preset || ''
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
  outputs.value.push({
    ...payload,
    html,
  })
  nextTick(() => {
    if (outputList.value) {
      outputList.value.scrollTop = outputList.value.scrollHeight
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
  
  // 处理执行结束事件
  if (payload?.message_type === 'tool_stream_end' && termInfo.active) {
    console.log(`[terminal] Execution ${executionId} ended, disabling interaction`)
    termInfo.active = false
    termInfo.ended = true
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
  const message = {
    type: 'input_result',
    payload: {
      text: inputText.value,
      metadata: {
        session_id: sessionId.value || undefined,
      },
    },
  }
  console.log('[ws] send input_result', message)
  socket.value.send(JSON.stringify(message))
  inputText.value = ''
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.innerText = text
  return div.innerHTML
}

function computeTerminalSize(terminal, hostEl) {
  const core = terminal?._core
  const dims = core?._renderService?.dimensions
  const cellWidth = dims?.actualCellWidth
  const cellHeight = dims?.actualCellHeight
  if (!cellWidth || !cellHeight) return null
  const rect = hostEl.getBoundingClientRect()
  if (!rect.width || !rect.height) return null
  const cols = Math.max(2, Math.floor(rect.width / cellWidth))
  const rows = Math.max(1, Math.floor(rect.height / cellHeight))
  return { cols, rows }
}

function syncTerminalSize(executionId, termInfo) {
  if (!termInfo?.terminal || !termInfo?.hostEl) return
  const size = computeTerminalSize(termInfo.terminal, termInfo.hostEl)
  if (!size) return
  const same = termInfo.lastSize &&
    termInfo.lastSize.cols === size.cols &&
    termInfo.lastSize.rows === size.rows
  if (same) return
  termInfo.lastSize = size
  try {
    termInfo.terminal.resize(size.cols, size.rows)
  } catch (error) {
    console.warn('[terminal] resize failed', error)
  }
  if (!socket.value) return
  const message = {
    type: 'terminal_resize',
    payload: {
      execution_id: executionId,
      rows: size.rows,
      cols: size.cols,
    },
  }
  socket.value.send(JSON.stringify(message))
}

// 动态绑定终端 DOM 元素
function setTerminalRef(executionId, el) {
  const termInfo = terminals.value.find(t => t.executionId === executionId)
  if (el) {
    console.log(`[terminal] Setting ref for execution ${executionId}`)
    terminalHosts.value.set(executionId, el)
    if (termInfo) {
      termInfo.hostEl = el
    }
    // 立即初始化终端
    if (termInfo && !termInfo.terminal) {
      console.log(`[terminal] Initializing terminal for execution ${executionId}`)
      console.log(`[terminal] Element size: width=${el.clientWidth}px, height=${el.clientHeight}px`)
      
      // 先使用较大的默认尺寸初始化
      const initialCols = 120
      const initialRows = 30
      console.log(`[terminal] Using initial size: cols=${initialCols}, rows=${initialRows}`)
      termInfo.terminal = new Terminal({
        theme: {
          background: '#0b1220',
        },
        fontSize: 12,
        cols: initialCols,
        rows: initialRows,
      })
      termInfo.terminal.open(el)
      console.log(`[terminal] Terminal actual size: cols=${termInfo.terminal.cols}, rows=${termInfo.terminal.rows}`)
      
      // 延迟调整尺寸，等待 DOM 完全渲染
      setTimeout(() => {
        // 使用 xterm.js 的 proposeDimensions API 根据实际元素尺寸计算终端大小
        const dims = termInfo.terminal.proposeDimensions()
        if (dims) {
          console.log(`[terminal] Proposed dimensions: cols=${dims.cols}, rows=${dims.rows}`)
          termInfo.terminal.resize(dims.cols, dims.rows)
          console.log(`[terminal] Resized to: cols=${termInfo.terminal.cols}, rows=${termInfo.terminal.rows}`)
          
          // 同步到后端
          syncTerminalSize(executionId, termInfo)
        } else {
          console.error('[terminal] Failed to propose dimensions')
        }
      }, 100)
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
      if (typeof ResizeObserver !== 'undefined') {
        termInfo.resizeObserver = new ResizeObserver(() => {
          syncTerminalSize(executionId, termInfo)
        })
        termInfo.resizeObserver.observe(el)
      }
      requestAnimationFrame(() => {
        syncTerminalSize(executionId, termInfo)
        try {
          termInfo.terminal.focus()
        } catch (error) {
          // ignore focus errors
        }
      })
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
.terminal-wrapper {
  margin-top: 12px;
}

.terminals-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.terminal-item {
  border: 1px solid #2a3a50;
  border-radius: 4px;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #15202b;
  border-bottom: 1px solid #2a3a50;
}

.terminal-id {
  font-family: monospace;
  font-size: 14px;
  color: #58a6ff;
}

.terminal-status {
  font-size: 12px;
  color: #3fb950;
}

.terminal-host {
  padding: 4px;
  background: #0b1220;
  min-height: 200px;
}
</style>
