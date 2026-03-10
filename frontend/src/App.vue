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

    <section class="panel terminal">
      <h2>终端输出（xterm.js）</h2>
      <div ref="terminalHost" class="terminal-host"></div>
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
const terminalHost = ref(null)
let terminal

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
    appendExecution(payload)
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
  if (!terminal) return
  const eventType = payload?.event_type
  if (eventType === 'stdout' || eventType === 'stderr') {
    terminal.write(payload.data || '')
  } else if (eventType === 'status') {
    terminal.writeln(`\r\n[status] ${payload.data || ''}`)
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

onMounted(() => {
  terminal = new Terminal({
    theme: {
      background: '#0b1220',
    },
    fontSize: 12,
  })
  if (terminalHost.value) {
    terminal.open(terminalHost.value)
    terminal.writeln('Terminal ready.')
  }
})
</script>
