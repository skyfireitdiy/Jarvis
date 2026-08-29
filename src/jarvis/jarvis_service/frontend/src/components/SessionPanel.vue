<template>
  <div class="session-panel" :class="{ 'active': active }" @click="$emit('activate')">
    <!-- 空白占位 -->
    <div v-if="!agent" class="session-panel-empty">
      <div class="empty-icon">▦</div>
      <div class="empty-text">点击左侧 Agent 在此打开</div>
      <button class="empty-close-btn" @click.stop="$emit('close-panel')" title="关闭面板">✕</button>
    </div>

    <!-- 有 Agent 的会话 -->
    <template v-else>
      <!-- 会话头部 -->
      <div class="session-panel-header">
        <span class="session-agent-name">{{ agent.name || agent.agent_id }}</span>
        <span class="session-agent-status" :class="getStatusClass(agent)">{{ getStatusLabel(agent) }}</span>
        <div class="session-header-actions">
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
            <div class="message-meta" v-if="item.agent_name || item.timestamp || item.non_interactive">
              <span class="message-agent" v-if="item.agent_name">{{ item.agent_name }}</span>
              <span class="message-separator" v-if="item.agent_name && item.timestamp"> · </span>
              <span class="message-time" v-if="item.timestamp">{{ formatMessageTime(item.timestamp) }}</span>
              <span class="message-separator" v-if="(item.agent_name || item.timestamp) && (item.non_interactive !== undefined)"> · </span>
              <span class="message-silent" v-if="item.non_interactive === true" title="静默模式">🔇</span>
              <span class="message-silent" v-if="item.non_interactive === false" title="交互模式">🔊</span>
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

      <!-- 内嵌确认区域 -->
      <div v-if="confirmData" class="panel-confirm-bar">
        <div class="panel-confirm-message">{{ confirmData.message }}</div>
        <div class="panel-confirm-actions">
          <button class="panel-confirm-btn panel-confirm-yes" @click="$emit('confirm')">确认</button>
          <button class="panel-confirm-btn panel-confirm-no" @click="$emit('cancel-confirm')">取消</button>
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
            :value="inputText"
            :data-agent-id="agent?.agent_id || ''"
            :placeholder="isInputDisabled ? 'Agent 未运行' : (inputTip || '输入内容 (Ctrl+Enter / Ctrl+D 发送)')"
            :disabled="isInputDisabled"
            @input="$emit('input-change', $event)"
            @keydown="$emit('keydown', $event)"
            @paste="$emit('paste', $event)"
          ></textarea>

          <!-- 单行输入框 -->
          <input
            v-else
            :value="inputText"
            :data-agent-id="agent?.agent_id || ''"
            type="text"
            :placeholder="isInputDisabled ? 'Agent 未运行' : (inputTip || '输入内容 (Enter 发送)')"
            :disabled="isInputDisabled"
            @input="$emit('input-change', $event)"
            @keydown="$emit('keydown', $event)"
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
import { ref } from 'vue'

const props = defineProps({
  agent: { type: Object, default: null },
  messages: { type: Array, default: () => [] },
  inputText: { type: String, default: '' },
  inputMode: { type: String, default: 'multi' },
  inputTip: { type: String, default: '' },
  isInputDisabled: { type: Boolean, default: true },
  isWaitingMultiDisabled: { type: Boolean, default: true },
  hasBufferedInput: { type: Boolean, default: false },
  agentStatus: { type: Object, default: null },
  active: { type: Boolean, default: false },
  confirmData: { type: Object, default: null },
})

const emit = defineEmits([
  'activate', 'close-agent', 'close-panel',
  'send', 'complete', 'open-completions',
  'input-change', 'keydown', 'paste',
  'show-buffer', 'clear-buffer',
  'set-output-list', 'set-terminal-ref',
  'show-toast',
  'confirm', 'cancel-confirm',
])

const outputListRef = ref(null)
const inputCollapsed = ref(false)

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
    console.log('[COPY] Successfully copied text to clipboard')
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
      console.log('[COPY] Fallback: Successfully copied using execCommand')
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
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.session-panel.active {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 1px var(--color-accent), 0 0 12px rgba(32, 200, 255, 0.15);
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
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border-subtle);
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
  background: var(--color-bg-tertiary);
  border-radius: var(--tile-radius);
  padding: 6px 10px;
  border: none;
}

.message-user_input {
  background: rgba(32, 200, 255, 0.35);
  border-left: 3px solid var(--color-accent);
}

.message-STREAM {
  background: var(--color-bg-tertiary);
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

.message-separator {
  opacity: 0.5;
}

.message-silent {
  font-size: 10px;
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
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
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
</style>
