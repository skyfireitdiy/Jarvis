<template>
  <div class="app">
    <!-- 顶部栏 -->
    <header class="app-header">
      <div class="header-title">
        <button class="icon-btn" @click="showAgentSidebar = !showAgentSidebar" title="切换 Agent 侧边栏">
          📋
        </button>
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

    <!-- Agent 侧边栏 -->
    <aside class="agent-sidebar" v-if="showAgentSidebar">
      <div class="agent-sidebar-header">
        <h3>Agent 列表</h3>
        <button class="icon-btn" @click="showCreateAgentModal = true" title="创建新 Agent">➕</button>
      </div>
      <div class="agent-list">
        <div v-for="agent in agentList" :key="agent.agent_id" 
             class="agent-item" 
             :class="{ active: currentAgentId === agent.agent_id }"
             @click="switchAgent(agent)">
          <div class="agent-info">
            <span class="agent-type">{{ agent.name || (agent.agent_type === 'agent' ? '🤖' : '💻') }}</span>
            <span class="agent-status" :class="agent.status">{{ agent.status }}</span>
            <span class="agent-port">:{{ agent.port }}</span>
          </div>
          <div class="agent-dir">{{ agent.working_dir }}</div>
          <button class="icon-btn stop-btn" @click.stop="stopAgent(agent.agent_id)" title="停止 Agent">✕</button>
        </div>
        <div v-if="agentList.length === 0" class="agent-empty">
          暂无 Agent，点击 + 创建
        </div>
      </div>
    </aside>

    <!-- 消息列表 -->
    <main class="chat-container">
      <div class="messages" ref="outputList">
        <article v-for="(item, index) in outputs" :key="index" class="message" :class="`message-${item.output_type?.toLowerCase()}`">
          <div class="message-content">
            <div class="message-meta-left">
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

    <!-- 创建 Agent 弹窗 -->
    <div class="modal-overlay" v-if="showCreateAgentModal">
      <div class="modal create-agent-modal">
        <h2>创建 Agent</h2>
        <div class="form-group">
          <label>Agent 类型</label>
          <select v-model="newAgentType" class="form-control">
            <option value="agent">通用 Agent (agent)</option>
            <option value="codeagent">代码 Agent (codeagent)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Agent 名称（可选）</label>
          <input v-model="newAgentName" type="text" class="form-control" placeholder="例如：开发环境Agent" />
        </div>
        <div class="form-group">
          <label>工作目录</label>
          <input v-model="newAgentDir" type="text" class="form-control" placeholder="/path/to/workspace" />
        </div>
        <div class="modal-actions">
          <button class="btn secondary" @click="showCreateAgentModal = false">取消</button>
          <button class="btn primary" @click="createAgent" :disabled="!newAgentDir.trim()">创建</button>
        </div>
      </div>
    </div>

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
        
        <!-- 历史消息管理 -->
        <div class="form-group">
          <div class="history-info">
            <div class="history-stat">
              <span class="history-stat-label">历史消息数量:</span>
              <span class="history-stat-value">{{ historyStorage.getTotalCount() }}</span>
            </div>
            <div class="history-stat">
              <span class="history-stat-label">存储空间:</span>
              <span class="history-stat-value">{{ historyStorage.getStorageInfo().totalSizeFormatted }}</span>
            </div>
          </div>
        </div>
        <div class="form-group">
          <button class="danger-btn" @click="confirmClearHistory" :disabled="historyStorage.getTotalCount() === 0">
            清除历史记录
          </button>
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
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import { Terminal } from 'xterm'
import { FitAddon } from '@xterm/addon-fit'
import 'xterm/css/xterm.css'
import historyStorage from './historyStorage.js'

// 配置 marked 使用 highlight.js 进行语法高亮
marked.setOptions({
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch (e) {
        console.error('[highlight.js] Error highlighting code:', e)
      }
    }
    return hljs.highlightAuto(code).value
  }
})

// 根据文件扩展名推断语言
function getLanguageFromFilename(filename) {
  if (!filename) return 'plaintext'
  const ext = filename.split('.').pop().toLowerCase()
  const langMap = {
    'py': 'python',
    'js': 'javascript',
    'ts': 'typescript',
    'vue': 'vue',
    'java': 'java',
    'c': 'c',
    'cpp': 'cpp',
    'h': 'cpp',
    'hpp': 'cpp',
    'go': 'go',
    'rs': 'rust',
    'rb': 'ruby',
    'php': 'php',
    'swift': 'swift',
    'kt': 'kotlin',
    'scala': 'scala',
    'sql': 'sql',
    'sh': 'bash',
    'bash': 'bash',
    'zsh': 'bash',
    'yaml': 'yaml',
    'yml': 'yaml',
    'json': 'json',
    'toml': 'toml',
    'ini': 'ini',
    'cfg': 'ini',
    'conf': 'ini',
    'xml': 'xml',
    'html': 'html',
    'css': 'css',
    'scss': 'scss',
    'less': 'less',
    'md': 'markdown',
    'txt': 'plaintext',
    'log': 'plaintext'
  }
  return langMap[ext] || 'plaintext'
}

// 认证和连接配置
const auth = ref({ token: '', password: '' })
const sessionId = ref('')
const backendHost = ref('127.0.0.1')
const backendPort = ref('8000')
const socket = ref(null) // Gateway 连接
const sockets = ref(new Map()) // 多 Agent 连接存储：agent_id -> WebSocket
const connecting = ref(false)

// 弹窗控制
const showConnectModal = ref(true)  // 首次打开显示欢迎界面
const showSettingsModal = ref(false) // 设置弹窗
const showAgentSidebar = ref(true)    // Agent 侧边栏
const showCreateAgentModal = ref(false) // 创建 Agent 弹窗

// 消息和终端
const allOutputs = ref(new Map()) // 按 agent_id 存储消息：agent_id -> outputs array
const outputs = computed(() => allOutputs.value.get(currentAgentId.value) || []) // 当前 Agent 的消息
const outputList = ref(null)
const terminalHosts = ref(new Map())
const terminals = ref([]) // [{ executionId, terminal, active, hostEl, resizeObserver, lastSize, pendingChunks, ended }]

// 输入控制
const inputText = ref('')
const inputMode = ref('single')
const inputTip = ref('')
const showInput = ref(false) // 是否显示输入框
const lastInputRequest = ref(null) // 保存最后一次的输入请求，用于重连后恢复

// Agent 管理
const agentList = ref([])        // Agent 列表
const currentAgentId = ref(null) // 当前连接的 Agent ID
const newAgentType = ref('agent') // 新 Agent 类型
const newAgentDir = ref('')       // 新 Agent 工作目录
const newAgentName = ref('')       // 新 Agent 名称（可选）

// 确认对话框
const confirmDialog = ref(null) // { message, confirmCallback, cancelCallback }

// 流式消息跟踪
const streamingMessage = ref(null) // 当前流式消息

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

// 历史消息加载状态
const isLoadingHistory = ref(false)
const historyOffset = ref(0)
const hasMoreHistory = ref(true)

/**
 * 加载历史消息
 * @param {boolean} prepend - 是否插入到消息列表开头
 */
function loadHistoryMessages(prepend = false) {
  if (isLoadingHistory.value) {
    console.log('[HISTORY] Already loading, skip')
    return
  }
  
  if (!hasMoreHistory.value) {
    console.log('[HISTORY] No more history to load')
    return
  }
  
  isLoadingHistory.value = true
  console.log('[HISTORY] Loading history (prepend:', prepend, ', offset:', historyOffset.value, ')')
  
  try {
    const historyMessages = historyStorage.loadHistory(historyStorage.MAX_MESSAGES_PER_PAGE, historyOffset.value)
    
    if (historyMessages.length === 0) {
      console.log('[HISTORY] No more history messages')
      hasMoreHistory.value = false
      isLoadingHistory.value = false
      return
    }
    
    // 保存当前的滚动位置（用于 prepend 时）
    let scrollPosition = 0
    if (prepend && outputList.value) {
      scrollPosition = outputList.value.scrollHeight - outputList.value.scrollTop
    }
    
    // 处理每条历史消息
    const processedMessages = historyMessages.map(msg => {
      const html = msg.lang === 'markdown' ? marked.parse(msg.text || '') : escapeHtml(msg.text || '')
      return {
        ...msg,
        html,
        timestamp: msg.timestamp || '',
        agent_name: msg.agent_name || '',
        non_interactive: msg.non_interactive !== undefined ? msg.non_interactive : false
      }
    })
    
    // 获取当前 Agent 的消息列表
    const currentOutputs = allOutputs.value.get(currentAgentId.value) || []
    if (prepend) {
      // 插入到消息列表开头
      allOutputs.value.set(currentAgentId.value, [...processedMessages, ...currentOutputs])
    } else {
      // 添加到消息列表末尾
      allOutputs.value.set(currentAgentId.value, processedMessages)
    }
    
    // 更新偏移量
    historyOffset.value += historyMessages.length
    
    // 检查是否还有更多历史
    const totalCount = historyStorage.getTotalCount()
    hasMoreHistory.value = historyOffset.value < totalCount
    
    console.log('[HISTORY] Loaded', historyMessages.length, 'messages, total loaded:', historyOffset.value, '/', totalCount, 'hasMore:', hasMoreHistory.value)
    
    // 恢复滚动位置
    if (prepend && outputList.value) {
      nextTick(() => {
        requestAnimationFrame(() => {
          const newScrollHeight = outputList.value.scrollHeight
          outputList.value.scrollTop = newScrollHeight - scrollPosition
          console.log('[HISTORY] Scroll position restored')
        })
      })
    } else {
      // 首次加载历史，滚动到底部
      nextTick(() => {
        if (outputList.value) {
          outputList.value.scrollTop = outputList.value.scrollHeight
          console.log('[HISTORY] Scrolled to bottom on initial load')
        }
      })
    }
  } catch (error) {
    console.error('[HISTORY] Failed to load history:', error)
  } finally {
    isLoadingHistory.value = false
  }
}

// 连接到 Gateway
function connect() {
  if (socket.value) return
  const host = backendHost.value || window.location.hostname || '127.0.0.1'
  const port = backendPort.value || '8000'
  const url = `ws://${host}:${port}/ws`
  connecting.value = true
  const ws = new WebSocket(url)
  ws.onopen = () => {
    console.log('[ws] open')
    connecting.value = false
    socket.value = ws
    showConnectModal.value = false
    const currentOutputs = allOutputs.value.get(currentAgentId.value) || []
    if (currentOutputs.length === 0) {
      console.log('[HISTORY] Loading history on first connect')
      loadHistoryMessages(false)
    } else {
      console.log('[HISTORY] Skip loading history, messages already exist')
    }
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

// ========== Agent 管理方法 ==========

// 发送消息到当前 Agent 的 WebSocket 连接
function sendMessageToAgent(message) {
  const agentId = currentAgentId.value
  if (!agentId) {
    console.warn('[SEND] No current agent ID, cannot send message')
    return
  }
  
  const ws = sockets.value.get(agentId)
  if (!ws) {
    console.warn(`[SEND] No WebSocket connection for agent ${agentId}`)
    return
  }
  
  if (ws.readyState !== WebSocket.OPEN) {
    console.warn(`[SEND] WebSocket for agent ${agentId} is not open, state: ${ws.readyState}`)
    return
  }
  
  console.log(`[SEND] Sending message to agent ${agentId}:`, message)
  ws.send(JSON.stringify(message))
}

// 连接到指定的 Agent（建立独立的 WebSocket 连接）
async function connectToAgent(agent) {
  const agentId = agent.agent_id
  
  // 检查是否已有连接
  if (sockets.value.has(agentId)) {
    console.log(`[AGENT] Already connected to ${agent.name || agentId}`)
    return
  }
  
  console.log(`[AGENT] Connecting to ${agent.name || agentId}`)
  
  const host = backendHost.value || window.location.hostname || '127.0.0.1'
  const agentPort = agent.port
  const url = `ws://${host}:${agentPort}/ws`
  
  connecting.value = true
  
  try {
    const ws = new WebSocket(url)
    
    // 绑定消息处理
    ws.onmessage = (event) => {
      let message = null
      try {
        message = JSON.parse(event.data)
      } catch (error) {
        console.warn(`[AGENT ${agentId}] message parse failed`, event.data)
        return
      }
      console.log(`[AGENT ${agentId}] message`, message)
      handleMessage(message, agentId)
    }
    
    ws.onopen = () => {
      console.log(`[AGENT ${agentId}] Connected to ${url}`)
      connecting.value = false
      
      // 保存连接
      sockets.value.set(agentId, ws)
      
      // 初始化消息记录
      if (!allOutputs.value.has(agentId)) {
        allOutputs.value.set(agentId, [])
      }
      
      // 发送认证
      const payload = {}
      if (auth.value.token) payload.token = auth.value.token
      if (auth.value.password) payload.password = auth.value.password
      if (Object.keys(payload).length > 0) {
        ws.send(JSON.stringify({ type: 'auth', payload }))
        console.log(`[AGENT ${agentId}] auth sent`, payload)
      }
      
      // 加载历史消息（如果当前是此 Agent）
      if (currentAgentId.value === agentId) {
        const currentOutputs = allOutputs.value.get(agentId) || []
        if (currentOutputs.length === 0) {
          console.log(`[AGENT ${agentId}] Loading history on first connect`)
          loadHistoryMessages(false)
        } else {
          console.log(`[AGENT ${agentId}] Skip loading history, messages already exist`)
        }
      }
    }
    
    ws.onclose = () => {
      console.log(`[AGENT ${agentId}] Disconnected`)
      sockets.value.delete(agentId)
      if (connecting.value) connecting.value = false
    }
    
    ws.onerror = () => {
      console.error(`[AGENT ${agentId}] Connection error`)
      if (connecting.value) connecting.value = false
    }
    
  } catch (error) {
    console.error(`[AGENT ${agentId}] Failed to connect:`, error)
    connecting.value = false
  }
}

// 创建 Agent
async function createAgent() {
  if (!newAgentDir.value.trim()) return
  
  try {
    const host = backendHost.value || window.location.hostname || '127.0.0.1'
    const port = backendPort.value || '8000'
    const response = await fetch(`http://${host}:${port}/api/agents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_type: newAgentType.value,
        working_dir: newAgentDir.value,
        name: newAgentName.value || undefined
      })
    })
    
    if (!response.ok) {
      const error = await response.json()
      alert(`创建失败: ${error.error?.message || error.detail || '未知错误'}`)
      return
    }
    
    const result = await response.json()
    console.log('[AGENT] Created:', result)
    
    // 后端返回格式: { success: true, data: agent }
    if (result.success && result.data) {
      const agent = result.data
      
      // 添加到列表
      agentList.value.push(agent)
      
      // 关闭创建弹窗
      showCreateAgentModal.value = false
      newAgentDir.value = ''
      newAgentName.value = ''
      
      // 刷新列表
      await fetchAgentList()
      
      // 开始定时刷新列表
      startAgentListRefresh()
    } else {
      alert('创建失败：返回数据格式错误')
    }
  } catch (error) {
    console.error('[AGENT] Create failed:', error)
    alert(`创建失败: ${error.message}`)
  }
}

// 获取 Agent 列表
async function fetchAgentList() {
  try {
    const host = backendHost.value || window.location.hostname || '127.0.0.1'
    const port = backendPort.value || '8000'
    const response = await fetch(`http://${host}:${port}/api/agents`)
    
    if (!response.ok) return
    
    const result = await response.json()
    console.log('[AGENT] List:', result)
    
    // 更新列表（后端返回格式: { success: true, data: agents }）
    if (result.success && result.data) {
      agentList.value = result.data
    }
    
    // 更新当前 Agent 状态
    const currentAgent = agentList.value.find(a => a.agent_id === currentAgentId.value)
    if (currentAgent && currentAgent.status !== 'running') {
      console.log('[AGENT] Current agent stopped:', currentAgent)
    }
  } catch (error) {
    console.error('[AGENT] Fetch list failed:', error)
  }
}

// 停止 Agent
async function stopAgent(agentId) {
  if (!confirm('确认停止该 Agent?')) return
  
  try {
    const host = backendHost.value || window.location.hostname || '127.0.0.1'
    const port = backendPort.value || '8000'
    const response = await fetch(`http://${host}:${port}/api/agents/${agentId}`, {
      method: 'DELETE'
    })
    
    if (!response.ok) {
      const error = await response.json()
      alert(`停止失败: ${error.detail || '未知错误'}`)
      return
    }
    
    console.log('[AGENT] Stopped:', agentId)
    
    // 如果是当前 Agent，清空当前 Agent ID
    if (currentAgentId.value === agentId) {
      currentAgentId.value = null
      outputs.value = []
    }
    
    // 刷新列表
    await fetchAgentList()
  } catch (error) {
    console.error('[AGENT] Stop failed:', error)
    alert(`停止失败: ${error.message}`)
  }
}

// 切换当前工作的 Agent
async function switchAgent(agent) {
  console.log('[AGENT] switchAgent called with:', agent)
  if (agent.agent_id === currentAgentId.value) {
    console.log('[AGENT] Already on this agent, skipping')
    return
  }
  
  console.log('[AGENT] Switching to:', agent)
  
  // 清空输入状态
  showInput.value = false
  lastInputRequest.value = null
  inputText.value = ''
  inputTip.value = ''
  
  // 更新当前 Agent ID
  currentAgentId.value = agent.agent_id
  console.log('[AGENT] Current agent ID updated to:', currentAgentId.value)
  
  // 连接到目标 Agent（如果还未连接）
  await connectToAgent(agent)
  
  // 加载历史消息
  console.log('[AGENT] Loading history messages...')
  loadHistoryMessages(false)
}

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

function handleMessage(message, agentId = null) {
  if (!message || typeof message !== 'object') return
  const { type, payload } = message
  
  // 确定目标 Agent ID：优先使用传入的 agentId，否则使用 currentAgentId
  const targetAgentId = agentId || currentAgentId.value
  if (type === 'ready') {
    console.log('[ws] ready payload', payload)
    if (payload?.session_id) {
      sessionId.value = payload.session_id
    }
    // 恢复之前的输入请求状态
    if (lastInputRequest.value) {
      console.log('[ws] Restoring input request from previous session')
      inputTip.value = lastInputRequest.value.tip || ''
      inputMode.value = lastInputRequest.value.mode || 'multi'
      inputText.value = lastInputRequest.value.preset || ''
      showInput.value = true
      nextTick(() => {
        const inputEl = document.querySelector(inputMode.value === 'multi' ? 'textarea' : 'input[type="text"]')
        inputEl?.focus()
      })
    }
  } else if (type === 'output') {
    const outputType = payload?.output_type
    
    // 处理流式输出
    if (outputType === 'STREAM_START') {
      console.log('[STREAM] Start event:', payload)
      // 创建新的流式消息
      const currentOutputs = allOutputs.value.get(targetAgentId) || []
      streamingMessage.value = {
        output_type: 'STREAM',
        text: '',
        lang: 'markdown',
        agent_name: payload?.context?.agent_name || payload?.agent_name || '',
        model_name: payload?.context?.model_name || '',
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        context: payload?.context || {},
        isStreaming: true
      }
      currentOutputs.push(streamingMessage.value)
      console.log('[STREAM] Created streaming message, total:', currentOutputs.length)
    } else if (outputType === 'STREAM_CHUNK') {
      console.log('[STREAM] Chunk event:', payload)
      // 追加到当前流式消息
      if (streamingMessage.value) {
        streamingMessage.value.text += payload.text || ''
        streamingMessage.value.html = marked.parse(streamingMessage.value.text || '')
        // 自动滚动到底部
        nextTick(() => {
          if (outputList.value) {
            outputList.value.scrollTop = outputList.value.scrollHeight
          }
        })
      } else {
        console.warn('[STREAM] Received chunk but no streaming message found')
      }
    } else if (outputType === 'STREAM_END') {
      console.log('[STREAM] End event:', payload)
      if (streamingMessage.value) {
        // 从 outputs 数组中删除流式消息（因为后面会有完整的 RESULT 消息）
        const currentOutputs = allOutputs.value.get(targetAgentId) || []
        const index = currentOutputs.indexOf(streamingMessage.value)
        if (index !== -1) {
          currentOutputs.splice(index, 1)
          console.log('[STREAM] Removed streaming message from outputs')
        }
        // 清除当前流式消息引用
        streamingMessage.value = null
      } else {
        console.warn('[STREAM] Received end but no streaming message found')
      }
    } else {
      // 普通输出
      appendOutput(payload, targetAgentId)
    }
  } else if (type === 'input_request') {
    console.log('[ws] input_request', payload)
    // 保存输入请求，用于重连后恢复
    lastInputRequest.value = payload
    inputTip.value = payload.tip || ''
    inputMode.value = payload.mode || 'multi'  // 默认多行
    inputText.value = payload.preset || ''
    
    // 在显示输入框前判断是否在底部
    const threshold = 100
    let shouldScrollAfterInputShow = false
    if (outputList.value) {
      const distanceToBottom = outputList.value.scrollHeight - outputList.value.scrollTop - outputList.value.clientHeight
      shouldScrollAfterInputShow = distanceToBottom < threshold
      console.log('[INPUT_REQUEST] Before show - distanceToBottom:', distanceToBottom, 'shouldScroll:', shouldScrollAfterInputShow)
    }
    
    showInput.value = true // 显示输入框
    nextTick(() => {
      // 聚焦到输入框
      const inputEl = document.querySelector(inputMode.value === 'multi' ? 'textarea' : 'input[type="text"]')
      inputEl?.focus()
      
      // 输入框显示后，如果之前在底部，就滚动到底部
      if (shouldScrollAfterInputShow && outputList.value) {
        requestAnimationFrame(() => {
          const scrollHeight = outputList.value.scrollHeight
          const scrollTop = outputList.value.scrollTop
          const clientHeight = outputList.value.clientHeight
          console.log('[INPUT_REQUEST] After show - Before scroll - scrollTop:', scrollTop, 'scrollHeight:', scrollHeight, 'clientHeight:', clientHeight)
          outputList.value.scrollTop = scrollHeight
          console.log('[INPUT_REQUEST] After show - After scroll - scrollTop:', outputList.value.scrollTop)
        })
      }
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
    const currentOutputs = allOutputs.value.get(targetAgentId) || []
    const existingItem = currentOutputs.find(
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
      }, targetAgentId)
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

function renderSideBySideDiff(diffData) {
  if (!diffData || !diffData.rows) {
    return '<div class="diff-error">No diff data</div>'
  }
  
  const { file_path, additions, deletions, rows } = diffData
  
  // 推断语言类型用于语法高亮
  const language = getLanguageFromFilename(file_path)
  
  let html = '<div class="diff-side-by-side">'
  
  // 标题
  html += '<div class="diff-header">'
  html += `<span class="diff-file-path">📝 ${escapeHtml(file_path || 'Unknown')}</span>`
  html += `<span class="diff-stats">[<span class="diff-additions">+${additions}</span> / <span class="diff-deletions">-${deletions}</span>]</span>`
  html += '</div>'
  
  // 表格
  html += '<table class="diff-table">'
  
  rows.forEach(row => {
    const { type, old_line_num, old_line, new_line_num, new_line } = row
    
    // 行背景色类
    let rowClass = 'diff-row diff-row-' + type
    
    // 旧代码列
    if (type === 'equal' || type === 'delete' || type === 'replace') {
      html += `<td class="diff-line-num diff-old-num">${escapeHtml(String(old_line_num || ''))}</td>`
      
      // 统计并保留缩进
      let oldContent = ''
      if (old_line) {
        const leadingSpaces = old_line.match(/^(\s*)/)[0]
        const highlighted = hljs.highlight(old_line, { language }).value
        // 在高亮结果前添加显式的 &nbsp; 来保留缩进
        oldContent = '&nbsp;'.repeat(leadingSpaces.length) + highlighted.replace(/^(\s+)/, '')
      }
      
      // 对于 replace 和 delete，添加删除背景色到 td
      const oldClass = (type === 'replace' || type === 'delete') ? 'diff-deleted' : ''
      html += `<td class="diff-content diff-old-content ${oldClass}"><code>${oldContent}</code></td>`
    } else {
      html += '<td class="diff-line-num diff-old-num"></td>'
      html += '<td class="diff-content diff-old-content"></td>'
    }
    
    // 新代码列
    if (type === 'equal' || type === 'insert' || type === 'replace') {
      html += `<td class="diff-line-num diff-new-num">${escapeHtml(String(new_line_num || ''))}</td>`
      
      // 统计并保留缩进
      let newContent = ''
      if (new_line) {
        const leadingSpaces = new_line.match(/^(\s*)/)[0]
        const highlighted = hljs.highlight(new_line, { language }).value
        // 在高亮结果前添加显式的 &nbsp; 来保留缩进
        newContent = '&nbsp;'.repeat(leadingSpaces.length) + highlighted.replace(/^(\s+)/, '')
      }
      
      // 对于 replace 和 insert，添加新增背景色到 td
      const newClass = (type === 'replace' || type === 'insert') ? 'diff-added' : ''
      html += `<td class="diff-content diff-new-content ${newClass}"><code>${newContent}</code></td>`
    } else {
      html += '<td class="diff-line-num diff-new-num"></td>'
      html += '<td class="diff-content diff-new-content"></td>'
    }
    
    html += '</tr>'
  })
  
  html += '</table>'
  html += '</div>'
  
  return html
}

function appendOutput(payload, agentId = null) {
  let html
  if (payload?.lang === 'markdown') {
    html = marked.parse(payload.text || '')
  } else if (payload?.lang === 'diff') {
    // 将 diff 包装在 markdown 代码块中，以便语法高亮
    html = marked.parse(`\`\`\`diff\n${payload.text || ''}\n\`\`\``)
  } else if (payload?.lang === 'json' && payload?.context?.diff_type === 'side_by_side') {
    // 解析 side by side diff 数据
    try {
      const diffData = JSON.parse(payload.text || '{}')
      html = renderSideBySideDiff(diffData)
    } catch (e) {
      console.error('[DIFF] Failed to parse side by side diff:', e)
      html = escapeHtml(payload.text || '')
    }
  } else {
    html = escapeHtml(payload.text || '')
  }
  
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
  
  // 只要 append 就自动滚动到底部，不需要判断位置
  const shouldAutoScroll = true
  
  // 确定目标 Agent ID：优先使用传入的 agentId，否则使用 currentAgentId
  const targetAgentId = agentId || currentAgentId.value
  
  // 添加到目标 Agent 的消息列表
  const currentOutputs = allOutputs.value.get(targetAgentId) || []
  currentOutputs.push(outputItem)
  console.log('[DEBUG] Pushed output, outputs.length:', currentOutputs.length, 'type:', outputItem.output_type)
  
  // 保存消息到本地存储
  try {
    // 只保存必要的数据，避免存储过大的内容
    const messageToSave = {
      output_type: outputItem.output_type,
      text: outputItem.text,
      lang: outputItem.lang,
      agent_name: outputItem.agent_name,
      non_interactive: outputItem.non_interactive,
      timestamp: outputItem.timestamp,
      execution_id: outputItem.execution_id,
      context: outputItem.context
    }
    historyStorage.saveMessage(messageToSave)
  } catch (error) {
    console.warn('[HISTORY] Failed to save message:', error)
    // 不影响正常显示，静默失败
  }
  
  // DOM更新后，自动滚动到底部
  // 使用双 nextTick + requestAnimationFrame 确保布局完全计算后再滚动
  nextTick(() => {
    nextTick(() => {
      requestAnimationFrame(() => {
        if (outputList.value) {
          const scrollHeight = outputList.value.scrollHeight
          outputList.value.scrollTop = scrollHeight
          console.log('[SCROLL] Auto-scrolled to bottom')
        }
      })
    })
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
  const agentId = currentAgentId.value
  if (!agentId) {
    console.warn('[SUBMIT] No current agent ID, cannot submit input')
    return
  }
  
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
  sendMessageToAgent(message)
  inputText.value = ''
  showInput.value = false // 隐藏输入框
  lastInputRequest.value = null // 清空保存的输入请求
}

function sendConfirmResult(confirmed) {
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
  sendMessageToAgent(message)
}

function sendInterrupt() {
  const message = {
    type: 'interrupt',
    payload: {
      metadata: {
        session_id: sessionId.value || undefined,
      },
    },
  }
  console.log('[ws] send interrupt', message)
  sendMessageToAgent(message)
}

function sendManualInterrupt() {
  const message = {
    type: 'manual_interrupt',
    payload: {
      metadata: {
        session_id: sessionId.value || undefined,
      },
    },
  }
  console.log('[ws] send manual interrupt', message)
  sendMessageToAgent(message)
}

function confirmClearHistory() {
  // 先关闭设置弹窗
  showSettingsModal.value = false
  
  confirmDialog.value = {
    message: '确定要清除所有历史记录吗？此操作不可撤销。',
    confirmCallback: () => {
      if (historyStorage.clearHistory()) {
        console.log('[HISTORY] History cleared successfully')
        // 清除当前 Agent 的消息
        allOutputs.value.set(currentAgentId.value, [])
        // 重置历史加载状态
        historyOffset.value = 0
        hasMoreHistory.value = true
      } else {
        console.error('[HISTORY] Failed to clear history')
      }
      // 无论清除是否成功，都关闭设置弹窗
      showSettingsModal.value = false
      confirmDialog.value = null
    },
    cancelCallback: () => {
      confirmDialog.value = null
    },
  }
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
  const message = {
    type: 'terminal_resize',
    payload: {
      execution_id: executionId,
      rows: newRows,
      cols: newCols,
    },
  }
  sendMessageToAgent(message)
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
        const message = {
          type: 'terminal_input',
          payload: {
            execution_id: executionId,
            data,
          },
        }
        sendMessageToAgent(message)
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
  
  // 启动 Agent 列表刷新
  startAgentListRefresh()
  
  // 添加滚动事件监听，实现滚动到顶部时加载更多历史
  let scrollDebounceTimer = null
  const SCROLL_THRESHOLD = 50 // 滚动到顶部50px以内触发
  const DEBOUNCE_DELAY = 500 // 防抖延迟500ms
  
  if (outputList.value) {
    outputList.value.addEventListener('scroll', () => {
      // 清除之前的定时器
      if (scrollDebounceTimer) {
        clearTimeout(scrollDebounceTimer)
      }
      
      // 设置新的定时器
      scrollDebounceTimer = setTimeout(() => {
        const scrollTop = outputList.value.scrollTop
        if (scrollTop <= SCROLL_THRESHOLD && !isLoadingHistory.value && hasMoreHistory.value) {
          console.log('[HISTORY] Scrolled to top, loading more history')
          loadHistoryMessages(true) // prepend = true, 插入到开头
        }
      }, DEBOUNCE_DELAY)
    })
    
    console.log('[HISTORY] Scroll listener added')
  }
})
</script>

<style scoped>
/* 动画定义 */
@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.1);
  }
}

/* 全局布局 */
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
  color: #e6edf3;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Noto Sans', Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  overflow-x: hidden;
}

/* 顶部栏 */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  background: rgba(22, 27, 34, 0.85);
  backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 1px 0 0 rgba(255, 255, 255, 0.04), 0 4px 12px rgba(0, 0, 0, 0.1);
  flex-shrink: 0;
}

.header-title h1 {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
  color: #e6edf3;
  letter-spacing: -0.02em;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.icon-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  font-size: 18px;
  cursor: pointer;
  padding: 6px 10px;
  color: #8b949e;
  transition: all 0.2s ease-out;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

.icon-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.12);
}

.icon-btn:active:not(:disabled) {
  transform: translateY(0);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.manual-interrupt-btn {
  background: linear-gradient(135deg, #f0883e 0%, #e37a33 100%);
  border: 0.5px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 14px;
  cursor: pointer;
  transition: all 0.2s ease-out;
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 2px 4px rgba(240, 136, 62, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.manual-interrupt-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #f09955 0%, #f0883e 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(240, 136, 62, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.manual-interrupt-btn:active:not(:disabled) {
  transform: translateY(0);
}

.manual-interrupt-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  filter: grayscale(0.3);
}

.status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 500;
  color: #8b949e;
  padding: 4px 10px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 20px;
  border: 0.5px solid rgba(255, 255, 255, 0.05);
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  box-shadow: 0 0 8px currentColor;
}

.dot.offline {
  background: #f85149;
  color: #f85149;
}

.dot.connecting {
  background: #d29922;
  color: #d29922;
  animation: pulse 1.5s ease-in-out infinite;
}

.dot.online {
  background: #3fb950;
  color: #3fb950;
}

/* Agent 侧边栏 */
.agent-sidebar {
  width: 280px;
  background: rgba(22, 27, 34, 0.95);
  border-right: 0.5px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.agent-sidebar-header {
  padding: 16px;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.08);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255, 255, 255, 0.02);
}

.agent-sidebar-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-item {
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.agent-item:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.12);
}

.agent-item.active {
  background: rgba(63, 185, 80, 0.15);
  border-color: rgba(63, 185, 80, 0.4);
}

.agent-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.agent-type {
  font-size: 16px;
}

.agent-status {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.agent-status.running {
  background: rgba(63, 185, 80, 0.2);
  color: #3fb950;
}

.agent-status.stopped {
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
}

.agent-port {
  font-size: 12px;
  color: #8b949e;
  margin-left: auto;
}

.agent-dir {
  font-size: 11px;
  color: #8b949e;
  word-break: break-all;
  line-height: 1.4;
}

.agent-item .stop-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transition: opacity 0.2s ease;
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
  border: 0.5px solid rgba(248, 81, 73, 0.3);
}

.agent-item:hover .stop-btn {
  opacity: 1;
}

.agent-item .stop-btn:hover {
  background: rgba(248, 81, 73, 0.3);
}

.agent-empty {
  text-align: center;
  color: #8b949e;
  padding: 40px 20px;
  font-size: 13px;
}

/* 创建 Agent 弹窗 */
.create-agent-modal {
  max-width: 400px;
  width: 90%;
}

.create-agent-modal h2 {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: #e6edf3;
}

.create-agent-modal .form-control {
  width: 100%;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: #e6edf3;
  font-size: 14px;
}

.create-agent-modal .form-control:focus {
  outline: none;
  border-color: rgba(63, 185, 80, 0.6);
  background: rgba(255, 255, 255, 0.08);
}

.create-agent-modal select.form-control option {
  background: #1a1f2e;
  color: #e6edf3;
}

.create-agent-modal .modal-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.create-agent-modal .btn {
  flex: 1;
  padding: 10px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
}

.create-agent-modal .btn.secondary {
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
}

.create-agent-modal .btn.secondary:hover {
  background: rgba(255, 255, 255, 0.15);
}

.create-agent-modal .btn.primary {
  background: linear-gradient(135deg, #3fb950 0%, #2ea043 100%);
  color: white;
}

.create-agent-modal .btn.primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(63, 185, 80, 0.4);
}

.create-agent-modal .btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none !important;
}

/* 聊天容器 */
.chat-container {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}

.messages {
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message {
  background: rgba(22, 27, 34, 0.75);
  backdrop-filter: blur(12px) saturate(150%);
  border-radius: 12px;
  padding: 14px 16px;
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  gap: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15), inset 0 1px 0 0 rgba(255, 255, 255, 0.04);
  transition: all 0.2s ease-out;
}

.message:hover {
  border-color: rgba(255, 255, 255, 0.12);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2), inset 0 1px 0 0 rgba(255, 255, 255, 0.06);
}

/* 用户输入消息 - 右对齐样式（必须放在 .message 之后以覆盖） */
.message.message-user_input {
  background: linear-gradient(135deg, #1f6feb 0%, #1a60d8 100%) !important;
  border: 0.5px solid rgba(255, 255, 255, 0.2) !important;
  align-self: flex-end;
  max-width: 75%;
  box-shadow: 0 4px 12px rgba(31, 111, 235, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
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
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
  text-align: left;
}

.message-content .message-meta-left {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
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
  width: 100%;
}

.message-meta-left .badge {
  font-size: 10px;
  padding: 3px 8px;
  background: rgba(33, 38, 45, 0.8);
  color: #8b949e;
  border-radius: 6px;
  font-weight: 600;
  letter-spacing: 0.02em;
  border: 0.5px solid rgba(255, 255, 255, 0.05);
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
  background: rgba(13, 17, 23, 0.9);
  backdrop-filter: blur(8px);
  padding: 14px;
  border-radius: 8px;
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  overflow-x: auto;
  margin: 10px 0;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.3);
}

.message-body.markdown-content :deep(code) {
  background: rgba(13, 17, 23, 0.7);
  padding: 3px 7px;
  border-radius: 5px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  border: 0.5px solid rgba(255, 255, 255, 0.06);
}

.message-body.markdown-content :deep(p) {
  margin: 8px 0;
}

/* 终端 */
.terminal-wrapper {
  margin-top: 14px;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  overflow: hidden;
  max-height: 600px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25), inset 0 1px 0 0 rgba(255, 255, 255, 0.06);
  background: rgba(13, 17, 23, 0.6);
}

.terminal-host {
  background: linear-gradient(180deg, #0a0d12 0%, #0d1117 100%);
  flex: 1;
  min-height: 400px;
  overflow: hidden;
}

/* 确认对话框 */
.message-confirm {
  background: rgba(33, 38, 45, 0.85);
  backdrop-filter: blur(12px) saturate(150%);
  border: 0.5px solid rgba(88, 166, 255, 0.3);
  box-shadow: 0 0 20px rgba(88, 166, 255, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05);
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
  padding: 9px 18px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  background: rgba(33, 38, 45, 0.8);
  backdrop-filter: blur(8px);
  color: #e6edf3;
  transition: all 0.2s ease-out;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.confirm-btn:hover {
  background: rgba(48, 54, 61, 0.9);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}

.confirm-btn.confirm {
  background: linear-gradient(135deg, #238636 0%, #2ea043 100%);
  border-color: rgba(255, 255, 255, 0.2);
  box-shadow: 0 2px 4px rgba(35, 134, 54, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.confirm-btn.confirm:hover {
  background: linear-gradient(135deg, #2ea043 0%, #36ad5a 100%);
  border-color: rgba(255, 255, 255, 0.25);
  box-shadow: 0 4px 8px rgba(35, 134, 54, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

/* 输入区 */
.input-area {
  background: rgba(22, 27, 34, 0.9);
  backdrop-filter: blur(20px) saturate(180%);
  border-top: 0.5px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.15);
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
  background: rgba(13, 17, 23, 0.8);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 14px;
  color: #e6edf3;
  font-size: 14px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  resize: vertical;
  box-sizing: border-box;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: all 0.2s ease-out;
}

.input-wrapper.multi-line textarea:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
  box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1), inset 0 2px 4px rgba(0, 0, 0, 0.2);
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
  min-width: 0;
  padding: 11px 15px;
  background: rgba(13, 17, 23, 0.8);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #e6edf3;
  font-size: 14px;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: all 0.2s ease-out;
}

.input-wrapper.single-line input:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
  box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1), inset 0 2px 4px rgba(0, 0, 0, 0.2);
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
  background: linear-gradient(135deg, #238636 0%, #2ea043 100%);
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  padding: 11px 22px;
  cursor: pointer;
  transition: all 0.2s ease-out;
  white-space: nowrap;
  box-shadow: 0 2px 6px rgba(35, 134, 54, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.send-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #2ea043 0%, #36ad5a 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(35, 134, 54, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.send-btn:active:not(:disabled) {
  transform: translateY(0);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  filter: grayscale(0.3);
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
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px) saturate(120%);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal {
  background: rgba(22, 27, 34, 0.95);
  backdrop-filter: blur(24px) saturate(180%);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  padding: 28px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(0, 0, 0, 0.2), inset 0 1px 0 0 rgba(255, 255, 255, 0.08);
}

.connect-modal h2,
.settings-modal h2 {
  margin: 0 0 24px 0;
  font-size: 21px;
  font-weight: 600;
  color: #e6edf3;
  letter-spacing: -0.02em;
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
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #8b949e;
  letter-spacing: 0.01em;
}

.form-group input {
  width: 100%;
  padding: 11px 14px;
  background: rgba(13, 17, 23, 0.8);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: all 0.2s ease-out;
}

.form-group input:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
  box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1), inset 0 2px 4px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.modal-header h2 {
  margin: 0;
  font-size: 21px;
  font-weight: 600;
  color: #e6edf3;
  letter-spacing: -0.02em;
}

.close-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  font-size: 22px;
  color: #8b949e;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease-out;
}

.close-btn:hover {
  background: rgba(255, 107, 107, 0.15);
  color: #ff6b6b;
  transform: rotate(90deg);
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 24px;
}

.primary-btn {
  padding: 10px 20px;
  background: linear-gradient(135deg, #238636 0%, #2ea043 100%);
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 9px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease-out;
  box-shadow: 0 2px 6px rgba(35, 134, 54, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.primary-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #2ea043 0%, #36ad5a 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(35, 134, 54, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.primary-btn:active:not(:disabled) {
  transform: translateY(0);
}

.primary-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  filter: grayscale(0.3);
}

.danger-btn {
  padding: 10px 20px;
  background: linear-gradient(135deg, #f85149 0%, #da3633 100%);
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 9px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease-out;
  box-shadow: 0 2px 6px rgba(248, 81, 73, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  width: 100%;
}

.danger-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #ff6b6b 0%, #f85149 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(248, 81, 73, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.danger-btn:active:not(:disabled) {
  transform: translateY(0);
}

.danger-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  filter: grayscale(0.3);
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: rgba(13, 17, 23, 0.6);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
}

.history-stat {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.history-stat-label {
  font-size: 13px;
  color: #8b949e;
  font-weight: 500;
}

.history-stat-value {
  font-size: 14px;
  color: #e6edf3;
  font-weight: 600;
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
}

.ghost-btn {
  padding: 10px 20px;
  background: rgba(33, 38, 45, 0.5);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease-out;
  backdrop-filter: blur(8px);
}

.ghost-btn:hover {
  background: rgba(48, 54, 61, 0.7);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
}

/* Side by side Diff 样式 */
.diff-side-by-side {
  background: #1a1f2e;
  border-radius: 8px;
  overflow: hidden;
  margin: 8px 0;
  width: 100%;
}

.diff-header {
  background: rgba(56, 139, 253, 0.1);
  padding: 8px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.diff-file-path {
  color: #e6edf3;
  font-size: 14px;
  font-weight: 600;
}

.diff-stats {
  color: #8b949e;
  font-size: 12px;
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
}

.diff-additions {
  color: #3fb950;
  font-weight: 600;
}

.diff-deletions {
  color: #f85149;
  font-weight: 600;
}

.diff-table {
  width: 100%;
  border-collapse: collapse;
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
  font-size: 12px;
}

.diff-row {
  transition: background-color 0.1s ease-out;
}

.diff-row:hover {
  background: rgba(255, 255, 255, 0.03);
}

.diff-row-equal {
  /* 背景色移到 td 级别 */
}

.diff-row-delete {
  /* 背景色移到 td 级别 */
}

.diff-row-insert {
  /* 背景色移到 td 级别 */
}

.diff-line-num {
  color: #8b949e;
  padding: 2px 6px;
  text-align: right;
  width: 50px;
  user-select: none;
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  vertical-align: top;
}

.diff-content {
  padding: 2px 6px;
  white-space: pre;
  word-break: break-all;
  width: 50%;
  vertical-align: top;
}

.diff-content code {
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.2;
  background: transparent;
  padding: 0;
  white-space: pre;
}

.diff-deleted {
  background: rgba(248, 81, 73, 0.7);
  color: #fff;
}

.diff-added {
  background: rgba(63, 185, 80, 0.7);
  color: #fff;
}

.diff-error {
  color: #f85149;
  padding: 8px 12px;
  font-weight: 600;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .app {
    background: linear-gradient(180deg, #1a1f2e 0%, #0d1117 100%);
  }
  
  .app-header {
    padding: 12px 16px;
  }
  .header-title h1 {
    font-size: 16px;
  }
  
  .messages {
    padding: 12px;
  }
  
  .message {
    padding: 10px 12px;
  }
  
  .message-content {
    gap: 6px;
  }
  
  .message-content .message-meta-left {
    gap: 6px 8px;
    font-size: 11px;
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
