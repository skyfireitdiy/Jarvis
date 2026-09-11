<template>
  <div class="session-panel" :class="{ 'active': active, 'session-panel-embedded': embedded, 'session-panel-dragging': interaction?.active }" :style="panelStyle" @click="handlePanelClick">
    <!-- 空白占位 -->
    <div v-if="!agent" class="session-panel-empty">
      <div class="empty-icon">▦</div>
      <div class="empty-text">点击左侧 Agent 在此打开</div>
      <button class="empty-close-btn" @click.stop="$emit('close-panel')" title="关闭面板">✕</button>
    </div>

    <!-- 有 Agent 的会话 -->
    <template v-else>
      <!-- 会话头部 -->
      <div class="session-panel-header" @mousedown="!embedded && $emit('startMove', $event)">
        <span class="session-agent-name">{{ agent.name || agent.agent_id }}</span>
        <span class="session-agent-status" :class="getStatusClass(agent)">{{ getStatusLabel(agent) }}</span>
        <!-- 操作图标已迁移至 Ctrl+K 命令面板「当前 Agent」组 -->
        <div class="session-header-actions">
          <button class="session-close-panel-btn" @click.stop="$emit('detach')" :title="embedded ? '分离为浮动窗口' : '嵌入回主界面'">⧉</button>
          <button class="session-close-panel-btn" @click.stop="$emit('close-panel')" title="关闭面板">✕</button>
        </div>
      </div>

      <!-- 消息列表 -->
      <div class="messages" :ref="el => setOutputListRef(el)">
        <article v-for="(item, index) in messages" :key="item._stableId || index" class="message" :class="`message-${item.output_type?.toLowerCase()}`">
          <div class="message-content">
            <button class="icon-btn copy-message-btn" @click="copyToClipboard(item.text, index)" title="复制到剪贴板" v-if="item.text">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
            </button>
            <div class="message-body markdown-content" v-html="item.html"></div>
            <!-- 流式输出打字机光标（宠物缩略图） -->
            <span v-if="item.isStreaming && item.output_type === 'STREAM'" class="stream-caret" aria-hidden="true">
              <span class="stream-caret-pet">
                <span class="stream-caret-ear l"></span>
                <span class="stream-caret-ear r"></span>
                <span class="stream-caret-eye l"></span>
                <span class="stream-caret-eye r"></span>
              </span>
            </span>
            <div class="message-meta" v-if="item.agent_name || item.timestamp || item.non_interactive || item.agent_list">
              <span class="message-agent" v-if="item.agent_name">{{ item.agent_name }}</span>
              <span class="message-separator" v-if="item.agent_name && item.agent_list"> · </span>
              <span class="message-agent-list" v-if="item.agent_list" title="当前进程内的 Agent 链">{{ item.agent_list }}</span>
              <span class="message-separator" v-if="(item.agent_name || item.agent_list) && item.timestamp"> · </span>
              <span class="message-time" v-if="item.timestamp">{{ formatMessageTime(item.timestamp) }}</span>
              <span class="message-separator" v-if="(item.agent_name || item.agent_list || item.timestamp) && (item.non_interactive !== undefined)"> · </span>
              <span class="message-silent" v-if="item.non_interactive === true" title="静默模式">🔇</span>
              <span class="message-silent" v-if="item.non_interactive === false" title="交互模式">🔊</span>
              <button
                v-if="ttsSupported && item.text"
                class="message-speak-btn"
                :class="{ 'speaking': isSpeaking(item) }"
                @click.stop="toggleSpeak(item)"
                :title="isSpeaking(item) ? '停止朗读' : '朗读此消息'"
              >{{ isSpeaking(item) ? '⏹' : '🔈' }}</button>
            </div>
          </div>
          <!-- 终端嵌入 -->
          <div v-if="item.output_type === 'execution' && item.execution_id && !item.is_finished && !item.terminal_content" class="terminal-wrapper">
            <div :ref="el => setTerminalRef(item.execution_id, el, item.agent_id)" class="terminal-host"></div>
          </div>
          <!-- 终端内容（历史记录） -->
          <div v-if="item.output_type === 'execution' && item.is_finished && item.terminal_content" class="terminal-history" :style="getTerminalStyle(item.terminal_content)">
            <div class="terminal-history-header">Terminal Output ({{ item.execution_id }})</div>
            <pre class="terminal-history-content">{{ item.terminal_content || '' }}</pre>
          </div>
        </article>
      </div>

      <!-- 调整大小手柄 -->
      <div
        v-for="direction in resizeDirections"
        :key="direction"
        :class="['session-resize-handle', `session-resize-${direction}`]"
        @mousedown="$emit('startResize', $event, direction)"
      ></div>

      <!-- 内嵌确认区域 -->
      <div v-if="confirmData" class="panel-confirm-bar">
        <div class="panel-confirm-message">{{ confirmData.message }}</div>
        <div class="panel-confirm-actions">
          <button class="panel-confirm-btn panel-confirm-no" :class="{ 'default': confirmData.defaultConfirm === false }" :style="{ order: confirmData.defaultConfirm === false ? 2 : 1 }" @click="$emit('cancel-confirm')">取消</button>
          <button class="panel-confirm-btn panel-confirm-yes" :class="{ 'default': confirmData.defaultConfirm !== false }" :style="{ order: confirmData.defaultConfirm !== false ? 2 : 1 }" @click="$emit('confirm')">确认</button>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-area" :class="{ 'collapsed': inputCollapsed }">
        <div class="input-toggle-bar" @click="inputCollapsed = !inputCollapsed" :title="inputCollapsed ? '展开输入框' : '折叠输入框'">
          <!-- Agent 运行中进度指示器（不随输入框折叠） -->
          <div class="agent-thinking-indicator" v-if="agent?.status === 'running' && (agentStatus?.execution_status ?? 'running') === 'running'">
            <div class="thinking-spinner"></div>
            <span class="thinking-text">Agent 正在执行...</span>
          </div>
          <button class="input-toggle-btn">
            {{ inputCollapsed ? '▲' : '▼' }}
          </button>
        </div>
        <div class="input-wrapper" v-show="!inputCollapsed">
          <!-- 多行输入框 -->
          <textarea
            v-if="inputMode === 'multi'"
            ref="multiInputRef"
            :value="inputText"
            :data-agent-id="agent?.agent_id || ''"
            :placeholder="isInputDisabled ? 'Agent 未运行' : (inputTip || '输入内容 (Ctrl+Enter / Ctrl+D 发送，右Ctrl 语音输入)')"
            :disabled="isInputDisabled"
            @input="$emit('input-change', $event)"
            @keydown="handleInputKeydown($event)"
            @keyup="handleInputKeyup($event)"
            @paste="$emit('paste', $event)"
          ></textarea>

          <!-- 单行输入框 -->
          <input
            v-else
            ref="singleInputRef"
            :value="inputText"
            :data-agent-id="agent?.agent_id || ''"
            :type="isPassword ? 'password' : 'text'"
            :placeholder="isInputDisabled ? 'Agent 未运行' : (inputTip || '输入内容 (Enter 发送)')"
            :disabled="isInputDisabled"
            @input="$emit('input-change', $event)"
            @keydown="handleInputKeydown($event)"
            @keyup="handleInputKeyup($event)"
            @paste="$emit('paste', $event)"
          />
          <!-- 缓冲区指示器 -->
          <div class="buffer-indicator" v-if="hasBufferedInput && (agentStatus?.execution_status ?? 'running') !== 'waiting_multi'" @click="$emit('show-buffer')">
            <span class="buffer-icon">📝</span>
            <span class="buffer-text">缓冲区有内容</span>
          </div>

          <!-- 操作按钮 -->
          <div class="input-actions">
            <button
              v-if="hasBufferedInput && (agentStatus?.execution_status ?? 'running') !== 'waiting_multi'"
              class="action-btn clear-buffer-btn"
              @click="$emit('clear-buffer')"
              :disabled="isInputDisabled"
              title="清空缓冲区"
            >
              清空
            </button>
            <button
              class="complete-btn"
              @click="$emit('complete')"
              :disabled="isWaitingMultiDisabled"
              title="完成（发送空消息）"
            >
              完成
            </button>
            <button
              class="action-btn completion-btn"
              @click="$emit('open-completions')"
              :disabled="isWaitingMultiDisabled"
              title="插入补全 (@)"
            >
              @
            </button>
            <button
              v-if="asrSupported"
              class="action-btn asr-btn"
              :class="{ 'recording': isRecording }"
              @click="toggleRecord"
              :disabled="isInputDisabled"
              :title="isRecording ? '停止语音输入' : '语音输入'"
            >
              {{ isRecording ? '⏹' : '🎤' }}
            </button>
            <button
              class="send-btn"
              @click="$emit('send')"
              :disabled="isInputDisabled || (!inputText.trim() && (!hasBufferedInput || (agentStatus?.execution_status ?? 'running') === 'waiting_multi'))"
            >
              {{ hasBufferedInput && (agentStatus?.execution_status ?? 'running') !== 'waiting_multi' ? '发送缓冲区' : '发送' }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onBeforeUnmount } from 'vue'

const props = defineProps({
  agent: { type: Object, default: null },
  messages: { type: Array, default: () => [] },
  inputText: { type: String, default: '' },
  inputMode: { type: String, default: 'multi' },
  inputTip: { type: String, default: '' },
  isPassword: { type: Boolean, default: false },
  isInputDisabled: { type: Boolean, default: true },
  isWaitingMultiDisabled: { type: Boolean, default: true },
  hasBufferedInput: { type: Boolean, default: false },
  agentStatus: { type: Object, default: null },
  active: { type: Boolean, default: false },
  confirmData: { type: Object, default: null },
  embedded: { type: Boolean, default: false },
  interaction: { type: Object, default: null },
  resizeDirections: { type: Array, default: () => [] },
  panelStyle: { type: Object, default: null },
})

const emit = defineEmits([
  'activate', 'detach', 'close-agent', 'close-panel',
  'send', 'complete', 'open-completions',
  'input-change', 'keydown', 'paste',
  'show-buffer', 'clear-buffer',
  'set-output-list', 'set-terminal-ref',
  'show-toast',
  'confirm', 'cancel-confirm',
  'startMove', 'startResize',
])

function handlePanelClick() {
  // 浮动模式下不触发 activate（不在 grid 内，激活无意义）
  if (!props.embedded) {
    return
  }
  // 当前已激活的 Panel 不重复触发 activate
  if (props.active) {
    return
  }
  // 若用户正在选中文本，不触发 activate
  const selection = window.getSelection()
  if (selection && selection.toString().trim()) {
    return
  }
  emit('activate')
}

const outputListRef = ref(null)
const inputCollapsed = ref(false)
const multiInputRef = ref(null)
const singleInputRef = ref(null)

// 判断当前焦点是否允许被本面板输入框接管：
// 无焦点(body)、焦点已在本面板输入框内、或焦点在页面其他非输入控件上时才允许，
// 避免轮询刷新状态时抢走用户正在使用的输入框（如命令面板搜索框）焦点。
function canStealFocus() {
  // 有模态弹窗打开时，用户正在弹窗内操作，不抢焦点
  if (hasVisibleModalOverlay()) return false
  const active = document.activeElement
  if (!active || active === document.body) return true
  const currentEl = props.inputMode === 'multi' ? multiInputRef.value : singleInputRef.value
  if (currentEl && active === currentEl) return true
  const tagName = String(active.tagName || '').toLowerCase()
  // 用户正在其他输入控件（input/textarea/contenteditable）中操作，不抢焦点
  if (tagName === 'input' || tagName === 'textarea' || active.isContentEditable) return false
  return true
}

// 检测页面是否存在可见的模态遮罩（Element Plus 弹窗/对话框等）。
// 有弹窗打开时，用户正在弹窗内操作，不应被自动聚焦抢走焦点。
function hasVisibleModalOverlay() {
  const overlays = document.querySelectorAll('.el-overlay, .modal-overlay, .dialog-overlay, .diff-modal-overlay')
  for (const el of overlays) {
    const style = window.getComputedStyle(el)
    if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
      return true
    }
  }
  return false
}

// 聚焦输入框
// force=true 时用于显式切换焦点（如切换 Panel），跳过“用户正在其他输入框”这一保护
function focusInput(force = false) {
  inputCollapsed.value = false
  if (!force && !canStealFocus()) return
  // 等待 DOM 更新后再聚焦
  setTimeout(() => {
    if (!force && !canStealFocus()) return
    const el = props.inputMode === 'multi' ? multiInputRef.value : singleInputRef.value
    if (el) {
      el.focus()
    }
  }, 50)
}

defineExpose({ focusInput, speakMessage, speakText, stopSpeak })

function setOutputListRef(el) {
  outputListRef.value = el
  emit('set-output-list', el)
}

function setTerminalRef(executionId, el, agentId) {
  emit('set-terminal-ref', executionId, el, agentId)
}

async function copyToClipboard(text, index) {
  if (!text) {
    console.warn('[COPY] No text to copy')
    return
  }

  try {
    await navigator.clipboard.writeText(text)

    emit('show-toast', '已复制到剪贴板', 'success')
  } catch (err) {
    console.error('[COPY] Failed to copy text:', err)
    // 降级方案
    try {
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.opacity = '0'
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)

      emit('show-toast', '已复制到剪贴板', 'success')
    } catch (fallbackErr) {
      console.error('[COPY] Fallback also failed:', fallbackErr)
      emit('show-toast', '复制失败，请手动复制', 'error')
    }
  }
}

function formatMessageTime(timestamp) {
  return timestamp || ''
}

// ---- 语音朗读（浏览器内置 SpeechSynthesis） ----
const ttsSupported = typeof window !== 'undefined' && 'speechSynthesis' in window
const speakingKey = ref(null)

function messageKey(item, index) {
  return item._stableId != null ? String(item._stableId) : `idx-${index}`
}

function isSpeaking(item) {
  if (!ttsSupported || speakingKey.value === null) return false
  return speakingKey.value === messageKey(item, props.messages.indexOf(item))
}

// 从渲染后的 HTML 提取纯文本，避免把 Markdown 标记（##、**、``` 等）念出来
function extractSpeakText(item) {
  if (item.html) {
    const tmp = document.createElement('div')
    tmp.innerHTML = item.html
    return (tmp.textContent || '').replace(/\s+/g, ' ').trim()
  }
  return (item.text || '').trim()
}

function stopSpeak() {
  if (!ttsSupported) return
  window.speechSynthesis.cancel()
  speakingKey.value = null
}

function toggleSpeak(item) {
  if (!ttsSupported) return
  // 再次点击同一条消息：停止
  if (isSpeaking(item)) {
    stopSpeak()
    return
  }
  const text = extractSpeakText(item)
  if (!text) return
  const key = messageKey(item, props.messages.indexOf(item))
  // 先停掉正在播放的
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'
  utterance.rate = 2.0
  utterance.onend = () => {
    if (speakingKey.value === key) speakingKey.value = null
  }
  utterance.onerror = () => {
    if (speakingKey.value === key) speakingKey.value = null
  }
  speakingKey.value = key
  window.speechSynthesis.speak(utterance)
}

// 供外部（如自动朗读）直接朗读指定消息，复用同一套图标状态
function speakMessage(item) {
  if (!ttsSupported || !item) return
  const text = extractSpeakText(item)
  if (!text) return
  const key = messageKey(item, props.messages.indexOf(item))
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'
  utterance.rate = 2.0
  utterance.onend = () => {
    if (speakingKey.value === key) speakingKey.value = null
  }
  utterance.onerror = () => {
    if (speakingKey.value === key) speakingKey.value = null
  }
  speakingKey.value = key
  window.speechSynthesis.speak(utterance)
}

// 供外部直接朗读任意文本（无对应消息时使用），不占用消息图标状态
function speakText(text) {
  if (!ttsSupported) return
  const content = String(text || '').replace(/\s+/g, ' ').trim()
  if (!content) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(content)
  utterance.lang = 'zh-CN'
  utterance.rate = 2.0
  window.speechSynthesis.speak(utterance)
}


onBeforeUnmount(() => {
  if (ttsSupported) {
    window.speechSynthesis.cancel()
  }
  stopRecord()
})

// ---- 语音输入（Web Speech API，仅 Chromium 系 + 安全上下文可用） ----
// 麦克风受安全上下文限制：https、localhost、127.0.0.1 可用；http + 其他 IP 会被浏览器拒绝。
// isSecureContext 由浏览器直接判定，比手动解析地址更可靠。
const SpeechRecognitionImpl =
  typeof window !== 'undefined'
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null
const asrSupported =
  !!SpeechRecognitionImpl &&
  typeof window !== 'undefined' &&
  window.isSecureContext
const isRecording = ref(false)
let recognizer = null
// 识别前输入框已有内容，作为前缀保留
let recordPrefix = ''
// 标记本次结束是否由用户主动停止（用于区分浏览器自动结束）
let userStopped = false

function stopRecord() {
  userStopped = true
  if (recognizer) {
    try {
      recognizer.stop()
    } catch (e) {
      // 忽略重复停止的异常
    }
  }
  isRecording.value = false
}

function toggleRecord() {
  if (!asrSupported) return
  if (isRecording.value) {
    stopRecord()
    return
  }
  startRecord()
}

function startRecord() {
  if (!asrSupported || isRecording.value) return
  recordPrefix = props.inputText || ''
  userStopped = false
  recognizer = new SpeechRecognitionImpl()
  recognizer.lang = 'zh-CN'
  recognizer.continuous = true
  recognizer.interimResults = true

  recognizer.onresult = (event) => {
    let finalText = ''
    let interimText = ''
    for (let i = 0; i < event.results.length; i++) {
      const result = event.results[i]
      if (result.isFinal) {
        finalText += result[0].transcript
      } else {
        interimText += result[0].transcript
      }
    }
    const merged = recordPrefix + finalText + interimText
    emit('input-change', { target: { value: merged, selectionStart: merged.length } })
  }

  recognizer.onerror = (event) => {
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      emit('show-toast', '麦克风未授权，请在浏览器中允许麦克风访问', 'error')
    } else if (event.error !== 'aborted') {
      emit('show-toast', `语音识别失败：${event.error}`, 'error')
    }
    isRecording.value = false
  }

  recognizer.onend = () => {
    // 移动端浏览器不支持真正的 continuous，会自动结束识别。
    // 若非用户主动停止，则自动重启，保持“连续”体验。
    if (!userStopped && isRecording.value) {
      try {
        recognizer.start()
        return
      } catch (e) {
        // 重启失败则回落到停止状态
      }
    }
    isRecording.value = false
  }

  try {
    recognizer.start()
    isRecording.value = true
  } catch (e) {
    emit('show-toast', '无法启动语音识别', 'error')
    isRecording.value = false
  }
}

// 右 Ctrl 按住说话：keydown 开始，keyup 停止（左 Ctrl 不生效）
// 右 Ctrl 快速双击：发送
// 输入框已有 keydown 监听（发送等），此处保留原有事件转发
const DOUBLE_TAP_MS = 300 // 双击判定窗口
const QUICK_TAP_MS = 250  // 单次“快速按下”判定（区别于长按说话）
let ctrlDownTime = 0
let lastQuickTapTime = 0

function handleInputKeydown(event) {
  if (event.code === 'ControlRight') {
    event.preventDefault()
    const now = Date.now()
    // 上一轮是快速单击，且间隔在双击窗口内 → 判定为双击发送
    if (lastQuickTapTime && now - lastQuickTapTime < DOUBLE_TAP_MS) {
      lastQuickTapTime = 0
      emit('send')
      return
    }
    ctrlDownTime = now
    if (!isRecording.value) startRecord()
    return
  }
  emit('keydown', event)
}

function handleInputKeyup(event) {
  if (event.code === 'ControlRight') {
    event.preventDefault()
    // 按下时间很短视为“快速单击”，为下一次双击判定做记录
    if (ctrlDownTime && Date.now() - ctrlDownTime < QUICK_TAP_MS) {
      lastQuickTapTime = Date.now()
    } else {
      lastQuickTapTime = 0
    }
    ctrlDownTime = 0
    if (isRecording.value) stopRecord()
  }
}

function getStatusClass(agent) {
  if (!agent) return 'stopped'
  return agent.status || 'stopped'
}

function getStatusLabel(agent) {
  if (!agent) return ''
  const statusMap = {
    running: '运行中',
    stopped: '已停止',
    waiting_multi: '等待输入',
    waiting_single: '等待输入',
    waiting_confirm: '等待确认',
  }
  return statusMap[agent.status] || agent.status || ''
}

function getTerminalStyle(terminalContent) {
  if (!terminalContent) return {}
  const lineCount = terminalContent.split('\n').length
  const fontSize = 12
  const lineHeight = 1.4
  const maxLines = 30
  const headerHeight = 41
  const contentPadding = 32
  const contentHeight = lineCount * fontSize * lineHeight
  const totalHeight = contentHeight + headerHeight + contentPadding
  if (lineCount <= maxLines) {
    return { fontFamily: "'Consolas', 'Microsoft YaHei', monospace", fontSize: `${fontSize}px`, lineHeight: lineHeight, height: `${totalHeight}px` }
  }
  const maxHeight = maxLines * fontSize * lineHeight + headerHeight + contentPadding
  return { fontFamily: "'Consolas', 'Microsoft YaHei', monospace", fontSize: `${fontSize}px`, lineHeight: lineHeight, height: `${maxHeight}px` }
}
</script>

<style scoped>
.session-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  position: fixed;
  background: rgba(9, 16, 28, 0.86);
  border: 1px solid var(--color-border-subtle);
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(32, 200, 255, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.session-panel.active {
  border-color: rgba(32, 200, 255, 0.55);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(32, 200, 255, 0.5),
    0 0 24px rgba(32, 200, 255, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.session-panel-embedded {
  position: relative !important;
  width: 100% !important;
  height: 100% !important;
  top: auto !important;
  left: auto !important;
}

.session-panel-dragging {
  cursor: grabbing !important;
  user-select: none;
}

.session-resize-handle {
  position: absolute;
  z-index: 10;
}

.session-resize-n {
  top: -3px;
  left: 8px;
  right: 8px;
  height: 6px;
  cursor: ns-resize;
}

.session-resize-s {
  bottom: -3px;
  left: 8px;
  right: 8px;
  height: 6px;
  cursor: ns-resize;
}

.session-resize-e {
  right: -3px;
  top: 8px;
  bottom: 8px;
  width: 6px;
  cursor: ew-resize;
}

.session-resize-w {
  left: -3px;
  top: 8px;
  bottom: 8px;
  width: 6px;
  cursor: ew-resize;
}

.session-resize-ne {
  top: -3px;
  right: -3px;
  width: 10px;
  height: 10px;
  cursor: nesw-resize;
}

.session-resize-nw {
  top: -3px;
  left: -3px;
  width: 10px;
  height: 10px;
  cursor: nwse-resize;
}

.session-resize-se {
  bottom: -3px;
  right: -3px;
  width: 10px;
  height: 10px;
  cursor: nwse-resize;
}

.session-resize-sw {
  bottom: -3px;
  left: -3px;
  width: 10px;
  height: 10px;
  cursor: nesw-resize;
}

.session-panel-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-secondary);
  position: relative;
}

.empty-icon {
  font-size: 36px;
  opacity: 0.4;
}

.empty-text {
  font-size: 13px;
  opacity: 0.6;
}

.empty-close-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 4px;
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-close-btn:hover {
  background: rgba(255, 60, 72, 0.2);
  color: var(--color-error);
}

.session-panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background:
    linear-gradient(160deg, rgba(32, 200, 255, 0.10) 0%, transparent 46%),
    var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border-subtle);
  border-left: 2px solid var(--color-accent);
  flex-shrink: 0;
}

.session-agent-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.session-agent-status {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--color-bg-secondary);
  flex-shrink: 0;
}

.session-agent-status.running {
  background: rgba(32, 200, 255, 0.2);
  color: var(--color-accent);
}

.session-agent-status.stopped {
  background: rgba(255, 60, 72, 0.2);
  color: var(--color-error);
}

.session-agent-status.waiting_multi,
.session-agent-status.waiting_single,
.session-agent-status.waiting_confirm {
  background: rgba(255, 133, 32, 0.2);
  color: var(--color-warning);
}

.session-header-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.session-close-agent-btn,
.session-close-panel-btn {
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 3px;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}

.session-close-agent-btn:hover {
  background: rgba(255, 60, 72, 0.2);
  color: var(--color-error);
}

.session-close-panel-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.messages {
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--color-bg-tile);
  min-height: 0;
}

.message {
  position: relative;
  background: rgba(18, 30, 50, 0.45);
  border-radius: var(--tile-radius);
  padding: 6px 10px;
  border: 1px solid var(--color-border-subtle);
  border-left: 2px solid var(--color-accent);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.message:hover {
  border-color: var(--color-border);
  box-shadow: 0 6px 20px rgba(0, 120, 190, 0.18);
}

.message-user_input {
  background: rgba(32, 200, 255, 0.35);
  border-left: 3px solid var(--color-accent);
}

.message-STREAM {
  background: rgba(18, 30, 50, 0.45);
  border-left: 3px solid var(--color-border-subtle);
}

.message-content {
  position: relative;
}

.message-body {
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
  font-family: 'Consolas', 'Microsoft YaHei', sans-serif;
}

/* 流式输出末尾的打字机光标（宠物缩略图） */
.stream-caret {
  display: inline-block;
  vertical-align: text-bottom;
  margin-left: 2px;
  padding-bottom: 1px;
  animation: stream-caret-blink 1s steps(2, start) infinite;
}

.stream-caret-pet {
  position: relative;
  display: block;
  width: 12px;
  height: 11px;
  border-radius: 50% 50% 46% 46%;
  background: linear-gradient(180deg, #7ee7ff 0%, #20c8ff 100%);
  box-shadow: 0 0 6px rgba(32, 200, 255, 0.65), 0 0 2px rgba(126, 231, 255, 0.9);
}

.stream-caret-pet .stream-caret-ear {
  position: absolute;
  top: -3px;
  width: 5px;
  height: 5px;
  background: #20c8ff;
  border-radius: 2px 2px 0 0;
}

.stream-caret-pet .stream-caret-ear.l {
  left: 0;
  transform: rotate(-18deg);
}

.stream-caret-pet .stream-caret-ear.r {
  right: 0;
  transform: rotate(18deg);
}

.stream-caret-pet .stream-caret-eye {
  position: absolute;
  top: 4px;
  width: 2.5px;
  height: 2.5px;
  background: #08243a;
  border-radius: 50%;
}

.stream-caret-pet .stream-caret-eye.l {
  left: 2px;
}

.stream-caret-pet .stream-caret-eye.r {
  right: 2px;
}

@keyframes stream-caret-blink {
  0%,
  49% {
    opacity: 1;
  }
  50%,
  100% {
    opacity: 0.25;
  }
}

@media (prefers-reduced-motion: reduce) {
  .stream-caret {
    animation: none;
  }
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-top: 4px;
}

.message-agent {
  color: var(--color-accent);
}

.message-agent-list {
  color: var(--color-text-secondary);
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 40ch;
}

.message-separator {
  opacity: 0.5;
}

.message-silent {
  font-size: 10px;
}

.message-speak-btn {
  background: none;
  border: none;
  padding: 0;
  margin-left: 4px;
  font-size: 10px;
  line-height: 1;
  cursor: pointer;
  color: var(--color-text-secondary);
  opacity: 0.7;
  transition: opacity 0.2s ease;
}

.message-speak-btn:hover {
  opacity: 1;
  color: var(--color-text-primary);
}

.message-speak-btn.speaking {
  opacity: 1;
  color: var(--color-accent, #4a9eff);
}

.copy-message-btn {
  position: absolute;
  top: 0;
  right: 0;
  background: var(--color-bg-hover);
  border: none;
  border-radius: var(--tile-radius-xs);
  padding: 4px 8px;
  color: var(--color-text-secondary);
  opacity: 0;
  transition: opacity 0.2s ease;
  z-index: 10;
}

.copy-message-btn svg {
  width: 14px;
  height: 14px;
}

.message-content:hover .copy-message-btn {
  opacity: 1;
}

.copy-message-btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.terminal-wrapper {
  margin-top: 6px;
}

.terminal-host {
  width: 100%;
  height: 100%;
  user-select: text;
}

.terminal-history {
  margin-top: 6px;
  background: var(--color-bg-primary);
  border-radius: var(--tile-radius-xs);
  overflow: hidden;
  max-height: 400px;
  display: flex;
  flex-direction: column;
}

.terminal-history-header {
  padding: 4px 8px;
  font-size: 11px;
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border-subtle);
}

.terminal-history-content {
  padding: 8px;
  font-size: 12px;
  line-height: 1.4;
  overflow-x: auto;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  flex: 1;
  min-height: 0;
}

.input-area {
  flex-shrink: 0;
  padding: 0;
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border-subtle);
  width: 100%;
}

.input-toggle-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 8px;
}

.input-toggle-btn {
  background: transparent;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
}

.input-toggle-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  padding: 0 8px 8px 8px;
  box-sizing: border-box;
}
.agent-thinking-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--color-text-secondary);
}

.thinking-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--color-border-subtle);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.thinking-text {
  font-size: 11px;
}

.input-wrapper textarea,
.input-wrapper input[type="text"] {
  width: 100%;
  padding: 8px 10px;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-xs);
  color: var(--color-text-primary);
  font-size: 14px;
  font-family: 'Consolas', 'Microsoft YaHei', sans-serif;
  box-sizing: border-box;
}

.input-wrapper textarea {
  resize: vertical;
  min-height: 96px;
}

.input-wrapper input[type="text"] {
  min-height: 36px;
}

.input-wrapper textarea:focus,
.input-wrapper input[type="text"]:focus {
  outline: none;
  border-color: var(--color-accent);
}

.input-wrapper textarea::placeholder,
.input-wrapper input[type="text"]::placeholder {
  color: var(--color-text-secondary);
}

.buffer-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-warning);
  cursor: pointer;
}

.buffer-icon {
  font-size: 12px;
}

.buffer-text {
  font-size: 11px;
}

.input-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.action-btn,
.complete-btn,
.send-btn {
  padding: 8px 16px;
  border: none;
  border-radius: var(--tile-radius-xs);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.action-btn {
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.action-btn:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.asr-btn.recording {
  background: rgba(255, 80, 80, 0.2);
  color: #ff5050;
  animation: asr-pulse 1.2s ease-in-out infinite;
}

@keyframes asr-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.complete-btn {
  background: rgba(54, 255, 124, 0.15);
  color: var(--color-success);
}

.complete-btn:hover:not(:disabled) {
  background: rgba(54, 255, 124, 0.25);
}

.send-btn {
  background: rgba(32, 200, 255, 0.15);
  color: var(--color-accent);
  border: 1px solid var(--color-accent);
  min-width: 64px;
  min-height: 36px;
}

.send-btn:hover:not(:disabled) {
  background: rgba(32, 200, 255, 0.25);
}

.action-btn:disabled,
.complete-btn:disabled,
.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 移动端适配：发送按钮加大 */
@media (max-width: 768px) {
  .send-btn {
    min-width: 144px;
    min-height: 44px;
    padding: 10px 20px;
    font-size: 15px;
  }

  /* 移动端：头部图标过多时自动换行显示 */
  .session-panel-header {
    flex-wrap: wrap;
    row-gap: 4px;
  }

  .session-agent-name {
    flex: 1 1 auto;
    min-width: 60px;
  }

  .session-agent-status {
    flex-shrink: 0;
  }

  .session-header-actions {
    margin-left: auto;
  }
}

/* 内嵌确认区域 */
.panel-confirm-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(32, 200, 255, 0.08);
  border: 1px solid rgba(32, 200, 255, 0.3);
  border-radius: var(--tile-radius-xs);
  margin: 0 8px 8px;
}

.panel-confirm-message {
  flex: 1;
  font-size: 12px;
  color: var(--color-text-primary);
  line-height: 1.4;
  word-break: break-all;
}

.panel-confirm-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.panel-confirm-btn {
  padding: 4px 12px;
  border: none;
  border-radius: var(--tile-radius-xs);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.panel-confirm-yes {
  background: rgba(32, 200, 255, 0.15);
  color: var(--color-accent);
  border: 1px solid var(--color-accent);
}

.panel-confirm-yes:hover {
  background: rgba(32, 200, 255, 0.25);
}

.panel-confirm-no {
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.panel-confirm-no:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.panel-confirm-btn.default {
  background: var(--color-accent);
  color: #fff;
  border-color: var(--color-accent);
  box-shadow: 0 0 8px rgba(32, 200, 255, 0.3);
}
</style>
