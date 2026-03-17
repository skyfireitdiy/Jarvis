<template>
  <div class="app">
    <!-- Agent 侧边栏 -->
    <aside class="agent-sidebar" :class="{ collapsed: !showAgentSidebar }">
      <div class="agent-sidebar-header">
        <h3>Agent 列表</h3>
        <div class="sidebar-header-actions">
          <button class="icon-btn" @click="showCreateAgentModal = true" title="创建新 Agent">➕</button>
          <button class="icon-btn" @click="showAgentSidebar = false" title="关闭侧边栏">✕</button>
        </div>
      </div>
      <div class="agent-list">
        <div v-for="agent in agentList" :key="agent.agent_id" 
             class="agent-item" 
             :class="{ active: currentAgentId === agent.agent_id }"
             @click="switchAgent(agent)">
          <div class="agent-info">
            <span class="agent-type">{{ agent.name || (agent.agent_type === 'agent' ? '🤖' : '💻') }}</span>
            <span class="agent-status" :class="getStatusClass(agent)">{{ getStatusText(agent) }}</span>
          </div>
          <div class="agent-dir">{{ agent.working_dir }}</div>
          <div class="agent-actions">
            <button class="icon-btn-small" @click.stop="renameAgent(agent)" title="重命名">✏️</button>
            <button class="icon-btn-small" @click.stop="copyAgent(agent)" title="复制 Agent">📋</button>
            <button class="icon-btn-small stop-btn" @click.stop="deleteAgent(agent.agent_id)" title="删除 Agent">✕</button>
          </div>
        </div>
        <div v-if="agentList.length === 0" class="agent-empty">
          暂无 Agent，点击 + 创建
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="main-content-wrapper">
      <!-- 顶部栏 -->
      <header class="app-header">
        <!-- 移动端快捷按钮 -->
        <div class="mobile-header-actions">
          <button class="icon-btn" @click="toggleAgentSidebar()" title="Agent列表">
            📋
          </button>
          <button class="icon-btn" @click="toggleTerminalPanel()" :disabled="!socket" title="终端面板">
            💻
          </button>
          <button class="icon-btn" v-if="agentStatuses.get(currentAgent?.agent_id)?.execution_status === 'running'" @click="sendManualInterrupt" :disabled="!socket" title="人工介入">
            👤
          </button>
          <button class="icon-btn" @click="showSettingsModal = true; pushOverlayState()" :disabled="!socket" title="设置">
            ⚙️
          </button>
        </div>
        
        <div class="header-title">
          <button class="icon-btn desktop-only" @click="toggleAgentSidebar()" title="切换 Agent 侧边栏">
            📋
          </button>
        </div>
        
        <div class="current-agent-info desktop-only" v-if="currentAgent">
          <span class="agent-type">{{ currentAgent.name || (currentAgent.agent_type === 'agent' ? '🤖' : '💻') }}</span>
          <span class="agent-status" :class="getStatusClass(currentAgent)">{{ getStatusText(currentAgent) }}</span>
          <span class="agent-dir">{{ currentAgent.working_dir }}</span>
        </div>
        
        <div class="header-actions desktop-only">
          <button class="icon-btn" @click="toggleTerminalPanel()" :disabled="!socket" title="终端面板">
            💻
          </button>
          <button class="icon-btn" v-if="agentStatuses.get(currentAgent?.agent_id)?.execution_status === 'running'" @click="sendManualInterrupt" :disabled="!socket" title="人工介入">
            👤
          </button>
          <button class="icon-btn" @click="showSettingsModal = true; pushOverlayState()" :disabled="!socket">
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
              <span class="agent-name">{{ item.agent_name || '' }}</span>
              <span class="non-interactive" v-if="item.non_interactive">🔕</span>
              <span class="interactive" v-if="item.non_interactive === false">💬</span>
              <span class="interactive" v-if="item.non_interactive === undefined"></span>
              <span class="timestamp">{{ item.timestamp || '' }}</span>
            </div>
            <button class="icon-btn copy-message-btn" @click="copyToClipboard(item.text, index)" title="复制到剪贴板" v-if="item.text">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
            </button>
            <div class="message-body markdown-content" v-html="item.html"></div>
          </div>
          <!-- 终端嵌入 -->
          <div v-if="item.output_type === 'execution' && item.execution_id && !item.is_finished" class="terminal-wrapper">
            <div :ref="el => setTerminalRef(item.execution_id, el)" class="terminal-host"></div>
          </div>
          <!-- 终端内容（历史记录） -->
          <div v-if="item.output_type === 'execution' && item.is_finished && item.terminal_content" class="terminal-history">
            <div class="terminal-history-header">Terminal Output ({{ item.execution_id }})</div>
            <pre class="terminal-history-content" :style="getTerminalStyle(item.terminal_content)">{{ item.terminal_content }}</pre>
          </div>
        </article>
        <!-- 确认对话框 -->
        <article v-if="confirmDialog" class="message message-confirm">
          <div class="confirm-box">
            <p class="confirm-message">{{ confirmDialog.message }}</p>
            <div class="confirm-actions">
              <template v-if="confirmDialog.defaultConfirm">
                <button class="confirm-btn cancel" @click="confirmDialog.cancelCallback">取消</button>
                <button class="confirm-btn confirm" @click="confirmDialog.confirmCallback">确认</button>
              </template>
              <template v-else>
                <button class="confirm-btn confirm" @click="confirmDialog.confirmCallback">确认</button>
                <button class="confirm-btn cancel" @click="confirmDialog.cancelCallback">取消</button>
              </template>
            </div>
          </div>
        </article>
      </div>
    </main>

    <!-- 终端面板 -->
    <aside 
      v-show="showTerminalPanel" 
      class="terminal-panel"
      :style="windowWidth.value > 768 ? { width: terminalPanelSize.width + 'px', height: terminalPanelSize.height + 'px' } : {}"
    >
      <div class="terminal-panel-header">
        <h3>终端</h3>
        <div class="terminal-panel-actions">
          <button class="icon-btn" @click="createTerminal" :disabled="terminalSessions.length >= 5" title="新建终端">➕</button>
          <button class="icon-btn" @click="showTerminalPanel = false" title="关闭面板">✕</button>
        </div>
      </div>
      
      <!-- 终端标签栏 -->
      <div class="terminal-tabs" v-if="terminalSessions.length > 0">
        <div 
          v-for="session in terminalSessions" 
          :key="session.terminal_id"
          class="terminal-tab"
          :class="{ active: activeTerminalId === session.terminal_id }"
          @click="switchTerminal(session.terminal_id)"
        >
          <span class="terminal-tab-title">{{ session.interpreter }}</span>
          <button class="terminal-tab-close" @click.stop="closeTerminal(session.terminal_id)">✕</button>
        </div>
      </div>
      
      <!-- 终端内容区域 -->
      <div class="terminal-content">
        <div v-if="terminalSessions.length === 0" class="terminal-empty">
          暂无终端，点击 + 创建
        </div>
        <div 
          v-else 
          v-for="session in terminalSessions" 
          :key="session.terminal_id"
          v-show="activeTerminalId === session.terminal_id"
          class="terminal-host-wrapper"
        >
          <div :ref="el => setTerminalHostRef(session.terminal_id, el)" class="terminal-host"></div>
        </div>
      </div>
      
      <!-- 调整大小手柄（仅在PC端显示） -->
      <div 
        v-show="windowWidth.value > 768"
        class="terminal-resize-handle"
        @mousedown="startResizeTerminal"
      ></div>
    </aside>

    <!-- 底部输入区 -->
    <footer class="input-area">
      <!-- 输入框 -->
      <div class="input-wrapper">
        <!-- Agent 运行中进度指示器 -->
        <div class="agent-thinking-indicator" v-if="currentAgent?.status === 'running' && (agentStatuses.get(currentAgentId)?.execution_status ?? 'running') === 'running'">
          <div class="thinking-spinner"></div>
          <span class="thinking-text">Agent 正在思考...</span>
        </div>
        
        <textarea 
          v-model="inputText" 
          :placeholder="isInputDisabled ? '没有激活的 Agent 或 Agent 未运行' : (inputTip || '输入内容 (Ctrl+Enter 发送)')"
          :disabled="isInputDisabled"
          @keydown.ctrl.enter="submitInput"
        ></textarea>
        
        <!-- 缓冲区指示器 -->
        <div class="buffer-indicator" v-if="hasBufferedInput && (agentStatuses.get(currentAgentId)?.execution_status ?? 'running') !== 'waiting_multi'" @click="sendBufferedInput">
          <span class="buffer-icon">📝</span>
          <span class="buffer-text">缓冲区有内容，点击发送</span>
        </div>
        
        <!-- 操作按钮 -->
        <div class="input-actions">
          <button 
            v-if="hasBufferedInput && (agentStatuses.get(currentAgentId)?.execution_status ?? 'running') !== 'waiting_multi'" 
            class="action-btn clear-buffer-btn" 
            @click="clearBuffer"
            :disabled="isInputDisabled"
            title="清空缓冲区"
          >
            清空
          </button>
          <button 
            class="complete-btn" 
            @click="submitCompletion" 
            :disabled="isInputDisabled"
            title="完成（发送空消息）"
          >
            完成
          </button>
          <button 
            class="action-btn completion-btn" 
            @click="openCompletions" 
            :disabled="isInputDisabled"
            title="插入补全 (@)"
          >
            @
          </button>
          <button 
            class="send-btn" 
            @click="submitInput" 
            :disabled="isInputDisabled || (!inputText.trim() && (!hasBufferedInput || (agentStatuses.get(currentAgentId)?.execution_status ?? 'running') === 'waiting_multi'))"
          >
            {{ hasBufferedInput && (agentStatuses.get(currentAgentId)?.execution_status ?? 'running') !== 'waiting_multi' ? '发送缓冲区' : '发送 (Ctrl+Enter)' }}
          </button>
        </div>
      </div>
    </footer>
    </div> <!-- 结束 main-content-wrapper -->

    <!-- 补全列表弹窗 -->
    <div class="modal-overlay" v-if="showCompletions">
      <div class="modal completions-modal">
        <div class="modal-header">
          <h3>插入补全</h3>
          <button class="icon-btn" @click="showCompletions = false">✕</button>
        </div>
        <div class="completions-search">
          <input 
            type="text" 
            v-model="completionSearch" 
            placeholder="搜索补全..." 
            ref="completionSearchInput"
            @keydown="handleCompletionKeydown"
          />
        </div>
        <div class="completions-list" ref="completionsListRef">
          <div 
            v-for="(item, index) in filteredCompletions" 
            :key="index" 
            :ref="el => { if (el) completionItemsRef[index] = el }"
            class="completion-item"
            :class="[`completion-${item.type}`, { 'selected': selectedIndex === index }]"
            @click="insertCompletion(item)"
          >
            <div class="completion-value">{{ item.display }}</div>
            <div class="completion-desc">{{ item.description }}</div>
          </div>
          <div v-if="filteredCompletions.length === 0" class="completion-empty">
            没有找到匹配的补全
          </div>
        </div>
      </div>
    </div>

    <!-- 创建 Agent 弹窗 -->
    <div class="modal-overlay" v-if="showCreateAgentModal">
      <div class="modal create-agent-modal">
        <h2>创建 Agent</h2>
        <div class="form-group">
          <label>Agent 类型</label>
          <div class="radio-group">
            <label class="radio-label">
              <input type="radio" v-model="newAgentType" value="agent" />
              <span class="radio-text">通用 Agent</span>
              <span class="radio-desc">适用于日常任务和通用操作</span>
            </label>
            <label class="radio-label">
              <input type="radio" v-model="newAgentType" value="codeagent" />
              <span class="radio-text">代码 Agent</span>
              <span class="radio-desc">专注于代码分析和开发任务</span>
            </label>
          </div>
        </div>
        <div class="form-group">
          <label>Agent 名称（可选）</label>
          <input v-model="newAgentName" type="text" class="form-control" placeholder="例如：开发环境Agent" />
        </div>
        <div class="form-group">
          <label>工作目录</label>
          <div class="input-with-button">
            <input v-model="newAgentDir" type="text" class="form-control" placeholder="/path/to/workspace" />
            <button class="btn select-dir-btn" @click="openDirDialog">选择目录</button>
          </div>
        </div>
        <div class="form-group">
          <label>模型组</label>
          <select v-model="newAgentModelGroup" class="form-control">
            <option v-for="group in modelGroups" :key="group.name" :value="group.name">
              {{ group.name }} ({{ group.smart_model }}, {{ group.normal_model }}, {{ group.cheap_model }})
            </option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn secondary" @click="showCreateAgentModal = false">取消</button>
          <button class="btn primary" @click="createAgent" :disabled="!newAgentDir.trim()">创建</button>
        </div>
      </div>
    </div>

    <!-- 重命名 Agent 弹窗 -->
    <div class="modal-overlay" v-if="showRenameAgentModal">
      <div class="modal create-agent-modal">
        <h2>重命名 Agent</h2>
        <div class="form-group">
          <label>Agent 名称（可选）</label>
          <input 
            v-model="renameAgentName" 
            type="text" 
            class="form-control" 
            placeholder="留空则使用默认名称"
            ref="renameInput"
            @keydown.enter="confirmRename"
          />
        </div>
        <div class="modal-actions">
          <button class="btn secondary" @click="showRenameAgentModal = false">取消</button>
          <button class="btn primary" @click="confirmRename">确认</button>
        </div>
      </div>
    </div>

    <!-- 目录选择对话框 -->
    <div class="modal-overlay" v-if="showDirDialog">
      <div class="modal dir-modal">
        <div class="modal-header">
          <h2>选择工作目录</h2>
          <button class="close-btn" @click="cancelDirDialog">×</button>
        </div>
        <div class="path-header">
          <button class="path-btn" @click="fetchDirectories(currentDirPath)">🔄 刷新</button>
          <button class="path-btn" @click="goToParentDir">⬆️ 返回上级</button>
        </div>
        <div class="current-path">{{ currentDirPath }}</div>
        <div class="dir-search">
          <input 
            ref="dirSearchInput"
            v-model="dirSearchText"
            type="text" 
            class="dir-search-input"
            placeholder="🔍 搜索目录..."
            @keydown="handleDirSearchKeydown"
          />
        </div>
        <div class="dir-list" v-if="filteredDirList.length > 0">
          <div
            v-for="dir in filteredDirList"
            :key="dir.path"
            class="dir-item"
            :class="{ selected: selectedDir === dir.path }"
            @click="windowWidth.value <= 768 ? enterDirectory(dir.path, false) : selectDirectory(dir.path)"
            @dblclick="enterDirectory(dir.path, false)"
          >
            <div class="dir-icon">📁</div>
            <div class="dir-name">{{ dir.name }}</div>
            <div class="dir-path">{{ dir.path }}</div>
          </div>
        </div>
        <div class="empty-state" v-else>
          <p>该目录下没有子目录</p>
        </div>
        <div class="modal-actions">
          <button class="btn secondary" @click="cancelDirDialog">取消</button>
          <button class="btn primary" @click="confirmDirectory">确认</button>
        </div>
      </div>
    </div>

    <!-- 连接弹窗 -->
    <div class="modal-overlay" v-if="showConnectModal">
      <div class="modal connect-modal">
        <h2>连接到 Jarvis</h2>
        <div v-if="connectErrorMessage" class="error-message">
          {{ connectErrorMessage }}
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="auth.password" type="password" placeholder="可选" />
        </div>
        <div class="form-group">
          <label>网关地址</label>
          <input v-model="gatewayUrl" placeholder="127.0.0.1:8000 或 ws://example.com:8080/ws" />
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
          <label>密码</label>
          <input v-model="auth.password" type="password" placeholder="可选" />
        </div>
        <div class="form-group">
          <label>网关地址</label>
          <input v-model="gatewayUrl" placeholder="127.0.0.1:8000 或 ws://example.com:8080/ws" />
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

    <!-- Session 选择对话框 -->
    <div class="modal-overlay" v-if="showSessionDialog">
      <div class="modal session-modal">
        <div class="modal-header">
          <h2>选择会话恢复</h2>
          <button class="close-btn" @click="cancelSessionDialog">×</button>
        </div>
        <div class="session-list" v-if="availableSessions.length > 0">
          <div
            v-for="session in availableSessions"
            :key="session.file"
            class="session-item"
            :class="{ active: selectedSession === session.file }"
            @click="selectedSession = session.file"
          >
            <div class="session-name">{{ session.name || '未命名会话' }}</div>
            <div class="session-time">{{ session.timestamp }}</div>
          </div>
        </div>
        <div class="empty-state" v-else>
          <p>没有可恢复的会话</p>
        </div>
        <div class="modal-actions">
          <button class="ghost-btn" @click="cancelSessionDialog">跳过</button>
          <button class="primary-btn" @click="restoreSession(selectedSession)" :disabled="!selectedSession">
            恢复会话
          </button>
        </div>
      </div>
    </div>
    
    <!-- Toast 提示 -->
    <transition name="toast-fade">
      <div v-if="toast.show" class="toast" :class="`toast-${toast.type}`">
        <span class="toast-icon">{{ toast.type === 'success' ? '✓' : toast.type === 'error' ? '✕' : 'ℹ' }}</span>
        <span class="toast-message">{{ toast.message }}</span>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
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

// 计算终端历史显示样式（高度自适应）
function getTerminalStyle(terminalContent) {
  if (!terminalContent) return {}
  
  const lineCount = terminalContent.split('\n').length
  const fontSize = 14
  const lineHeight = 1.4
  const maxLines = 30
  
  const baseStyle = {
    fontFamily: "'Fira Code', 'Consolas', 'Monaco', 'Courier New', monospace",
    fontSize: `${fontSize}px`,
    lineHeight: lineHeight
  }
  
  if (lineCount <= maxLines) {
    return { ...baseStyle, maxHeight: 'none' }
  } else {
    return { ...baseStyle, maxHeight: `${maxLines * fontSize * lineHeight}px` }
  }
}

// 拖拽相关函数
function startDragSidebar(event) {
  isDraggingSidebar.value = true
  dragOffset.value = {
    x: event.clientX - sidebarPosition.value.x,
    y: event.clientY - sidebarPosition.value.y
  }
  document.addEventListener('mousemove', onDragSidebar)
  document.addEventListener('mouseup', stopDragSidebar)
}

function onDragSidebar(event) {
  if (!isDraggingSidebar.value) return
  sidebarPosition.value = {
    x: event.clientX - dragOffset.value.x,
    y: event.clientY - dragOffset.value.y
  }
}

function stopDragSidebar() {
  isDraggingSidebar.value = false
  document.removeEventListener('mousemove', onDragSidebar)
  document.removeEventListener('mouseup', stopDragSidebar)
}

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
const auth = ref({ password: '' })
const gatewayUrl = ref(localStorage.getItem('jarvis_gateway_url') || '127.0.0.1:8000')
const socket = ref(null) // Gateway 连接
const sockets = ref(new Map()) // 多 Agent 连接存储：agent_id -> WebSocket
const connecting = ref(false)
const connectErrorMessage = ref('')  // 连接错误信息

// URL 解析辅助函数：支持 HTTPS 协议和域名

// 获取当前页面的 HTTP 协议（http:// 或 https://）
function getHttpProtocol() {
  return window.location.protocol === 'https:' ? 'https' : 'http'
}

// 获取当前页面的 WebSocket 协议（ws:// 或 wss://）
function getWebSocketProtocol() {
  return window.location.protocol === 'https:' ? 'wss' : 'ws'
}

// 解析网关地址，支持完整URL格式（如 ws://example.com:8080/ws 或 example.com:8080）
function parseGatewayAddress(address) {
  // 移除首尾空格
  address = address.trim()
  
  // 如果是完整URL（包含协议）
  if (address.includes('://')) {
    try {
      const url = new URL(address)
      return {
        protocol: url.protocol.replace(':', ''),  // 'ws', 'wss', 'http', 'https'
        host: url.hostname,
        port: url.port || (url.protocol === 'https:' || url.protocol === 'wss:' ? '443' : '80'),
        path: url.pathname
      }
    } catch (e) {
      console.error('[URL] Failed to parse address:', address, e)
      return null
    }
  }
  
  // 如果是 host:port 格式
  if (address.includes(':')) {
    const parts = address.split(':')
    if (parts.length === 2) {
      return {
        protocol: null,  // 使用默认协议
        host: parts[0],
        port: parts[1],
        path: ''
      }
    }
  }
  
  // 如果只有主机名（使用默认端口）
  return {
    protocol: null,
    host: address,
    port: '8000',
    path: ''
  }
}

// 构建 WebSocket URL
function buildWebSocketUrl(host, port, protocol = null) {
  // 如果没有指定协议，根据当前页面自动检测
  const wsProtocol = protocol || getWebSocketProtocol()
  return `${wsProtocol}://${host}:${port}/ws`
}

// 构建 HTTP URL
function buildHttpUrl(host, port, path, protocol = null) {
  // 如果没有指定协议，根据当前页面自动检测
  const httpProtocol = protocol || getHttpProtocol()
  return `${httpProtocol}://${host}:${port}${path}`
}

// 获取网关地址（host和port）
function getGatewayAddress() {
  const parsed = parseGatewayAddress(gatewayUrl.value)
  if (!parsed) {
    return {
      host: '127.0.0.1',
      port: '8000'
    }
  }
  return {
    host: parsed.host || '127.0.0.1',
    port: parsed.port || '8000'
  }
}

// 弹窗控制
const showConnectModal = ref(true)  // 首次打开显示欢迎界面
const showSettingsModal = ref(false) // 设置弹窗
const showAgentSidebar = ref(true)    // Agent 侧边栏
const showTerminalPanel = ref(false)  // 终端面板
const showMobileMenu = ref(false)     // 移动端菜单
const windowWidth = ref(window.innerWidth)  // 窗口宽度，用于响应式检测
const showCreateAgentModal = ref(false) // 创建 Agent 弹窗
const showRenameAgentModal = ref(false) // 重命名 Agent 弹窗
const renamingAgent = ref(null)          // 正在重命名的 Agent
const renameAgentName = ref('')           // 重命名的新名称
const showSessionDialog = ref(false)   // Session 选择对话框
const availableSessions = ref([])         // 可恢复的 session 列表
const selectedSession = ref(null)         // 选中的 session
const showDirDialog = ref(false)           // 目录选择对话框
const currentDirPath = ref('')             // 当前浏览的目录路径
const dirList = ref([])                    // 目录列表
const selectedDir = ref(null)              // 选中的目录
const dirSearchText = ref('')              // 目录搜索文本
const dirSearchInput = ref(null)           // 目录搜索输入框引用
const selectedDirIndex = ref(-1)           // 当前选中的目录索引，-1 表示未选中
const renameInput = ref(null)               // 重命名输入框引用

// 过滤后的目录列表（支持模糊搜索）
const filteredDirList = computed(() => {
  if (!dirSearchText.value.trim()) {
    return dirList.value
  }
  const searchText = dirSearchText.value.toLowerCase().trim()
  return dirList.value.filter(dir => 
    dir.name.toLowerCase().includes(searchText) ||
    dir.path.toLowerCase().includes(searchText)
  )
})

// 浮动窗口位置
const sidebarPosition = ref({ x: 20, y: 100 }) // 侧边栏浮动位置
const isDraggingSidebar = ref(false) // 是否正在拖拽侧边栏
const dragOffset = ref({ x: 0, y: 0 }) // 拖拽偏移量

// 消息和终端
const allOutputs = ref(new Map()) // 按 agent_id 存储消息：agent_id -> outputs array
const outputs = computed(() => allOutputs.value.get(currentAgentId.value) || []) // 当前 Agent 的消息
const outputList = ref(null)
const terminalHosts = ref(new Map())
const terminals = ref([]) // [{ executionId, terminal, active, hostEl, resizeObserver, lastSize, pendingChunks, ended }]

// 独立终端会话
const terminalSessions = ref([]) // [{ terminal_id, interpreter, working_dir, terminal, hostEl, fitAddon }]
const activeTerminalId = ref(null) // 当前激活的终端ID
const independentTerminalHosts = ref(new Map()) // terminal_id -> hostEl

// 输入控制
const inputText = ref('')
const inputMode = ref('single')
const inputTip = ref('')
const lastInputRequest = ref(null) // 保存最后一次的输入请求，用于重连后恢复
const inputBuffers = ref(new Map()) // 每个 Agent 的输入缓冲区（key: agentId, value：内容）

// Toast 提示
const toast = ref({
  show: false,
  message: '',
  type: 'success' // success | error | info
})

let toastTimer = null

function showToast(message, type = 'success') {
  toast.value = {
    show: true,
    message,
    type
  }
  
  if (toastTimer) {
    clearTimeout(toastTimer)
  }
  
  toastTimer = setTimeout(() => {
    toast.value.show = false
  }, 2000)
}
const hasBufferedInput = computed(() => {
  const agentId = currentAgentId.value
  return agentId ? inputBuffers.value.has(agentId) : false
})

// Agent 管理
const agentList = ref([])        // Agent 列表
const currentAgentId = ref(null) // 当前连接的 Agent ID
const agentStatuses = ref(new Map()) // Agent 状态映射 (agent_id -> {execution_status, agent_status})
const currentAgent = computed(() => {
  return agentList.value.find(agent => agent.agent_id === currentAgentId.value) || null
})

// 判断输入框是否应该禁用（没有激活的 agent 或 agent 状态不是 running）
const isInputDisabled = computed(() => {
  if (!currentAgentId.value) {
    return true // 没有激活的 agent
  }
  if (!currentAgent.value || currentAgent.value.status !== 'running') {
    return true // agent 状态不是 running
  }
  return false
})
const newAgentType = ref('agent') // 新 Agent 类型
const newAgentDir = ref('~')       // 新 Agent 工作目录（默认用户目录）
const newAgentName = ref('通用Agent') // 新 Agent 名称（可选，默认为'通用Agent'）
const modelGroups = ref([])        // 模型组列表
const newAgentModelGroup = ref('default') // 新 Agent 模型组（默认为 default）

// 监听 Agent 类型变化，自动填充默认名称
watch(newAgentType, (newType) => {
  if (newType === 'agent') {
    newAgentName.value = '通用Agent'
  } else if (newType === 'codeagent') {
    newAgentName.value = '代码Agent'
  }
}, { immediate: true })

// 确认对话框
const confirmDialog = ref(null) // { message, confirmCallback, cancelCallback, defaultConfirm }

// 显示确认对话框（自动滚动到底部）
function showConfirm(message, confirmCallback, cancelCallback, defaultConfirm = true) {
  // 先设置 confirmDialog，让对话框显示
  confirmDialog.value = {
    message,
    defaultConfirm,
    confirmCallback: () => {
      confirmCallback()
      confirmDialog.value = null
    },
    cancelCallback: cancelCallback ? () => {
      cancelCallback()
      confirmDialog.value = null
    } : () => {
      confirmDialog.value = null
    }
  }
  
  // 等待 DOM 更新后滚动到底部，确保用户能看到确认对话框
  nextTick(() => {
    if (outputList.value) {
      outputList.value.scrollTop = outputList.value.scrollHeight
    }
  })
}

// 补全列表
const showCompletions = ref(false) // 是否显示补全列表
const completions = ref([]) // 补全列表数据
const completionSearch = ref('') // 补全搜索关键词

// 监听搜索输入变化，重置选中状态
watch(completionSearch, () => {
  selectedIndex.value = -1
})
const completionSearchInput = ref(null) // 补全搜索输入框引用
const completionsListRef = ref(null) // 补全列表容器引用
const completionItemsRef = ref([]) // 补全条目元素引用数组
const selectedIndex = ref(-1) // 当前选中的补全条目索引，-1 表示未选中

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
  // 没有激活的 agent 时，不加载历史记录
  if (!currentAgentId.value) {
    console.log('[HISTORY] No active agent, skip loading history')
    return
  }
  
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
    const historyMessages = historyStorage.loadHistory(historyStorage.MAX_MESSAGES_PER_PAGE, historyOffset.value, currentAgentId.value)
    
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
    console.log(`🚨 [loadHistoryMessages] Loaded ${historyMessages.length} history messages`)
    const executionMessages = historyMessages.filter(msg => msg.output_type === 'execution')
    if (executionMessages.length > 0) {
      console.log(`🚨 [loadHistoryMessages] Found ${executionMessages.length} execution messages in history`, executionMessages.map(m => ({execution_id: m.execution_id, is_finished: m.is_finished, has_content: !!m.terminal_content})))
    }
    // 不再过滤 execution 类型，因为它现在带有 is_finished 标记，可以显示历史内容
    const processedMessages = historyMessages.map(msg => {
        const html = renderMessageHtml(msg)
        return {
          ...msg,
          html,
          timestamp: msg.timestamp || '',
          agent_name: msg.agent_name || '',
          non_interactive: msg.non_interactive !== undefined ? msg.non_interactive : false
        }
      })
    console.log(`🚨 [loadHistoryMessages] After filtering: ${processedMessages.length} messages`)
    
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
    const totalCount = historyStorage.getTotalCount(currentAgentId.value)
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
  // 清空之前的错误信息
  connectErrorMessage.value = ''
  if (socket.value) return
  
  // 解析网关地址
  const parsed = parseGatewayAddress(gatewayUrl.value)
  if (!parsed) {
    connectErrorMessage.value = '无效的网关地址格式'
    return
  }
  
  const host = parsed.host || window.location.hostname || '127.0.0.1'
  const port = parsed.port || '8000'
  const url = buildWebSocketUrl(host, port, parsed.protocol)
  connecting.value = true
  const ws = new WebSocket(url)
  ws.onopen = () => {
    console.log('[ws] open')
    connecting.value = false
    socket.value = ws
    showConnectModal.value = false
    
    // 保存连接信息到 localStorage
    localStorage.setItem('jarvis_gateway_url', gatewayUrl.value)
    console.log('[ws] Connection info saved:', gatewayUrl.value)
    // 获取模型组列表
    fetchModelGroups()
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
    // 始终发送 auth 消息，即使没有密码
    // 这样后端可以立即检测到认证失败，而不需要等待超时
    ws.send(JSON.stringify({ type: 'auth', payload }))
    console.log('[ws] auth sent', payload)
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
    // 连接断开，销毁所有独立终端
    console.log('[ws] Closing all independent terminals due to connection close')
    const allTerminalIds = terminalSessions.value.map(t => t.terminal_id)
    allTerminalIds.forEach(terminalId => closeTerminal(terminalId))
    // 连接断开，重新显示连接对话框
    showConnectModal.value = true
    // 不清空连接错误信息，保留错误提示
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
async function connectToAgent(agent, retryCount = 0) {
  const agentId = agent.agent_id
  const maxRetries = 3
  const retryDelay = 1000 // 1秒重试间隔
  const connectionTimeout = 5000 // 5秒连接超时
  
  // 检查是否已有连接
  if (sockets.value.has(agentId)) {
    const existingWs = sockets.value.get(agentId)
    // 检查现有连接是否仍然有效
    if (existingWs && existingWs.readyState === WebSocket.OPEN) {
      console.log(`[AGENT] Already connected to ${agent.name || agentId}`)
      // 已连接，发送 get_status 请求以同步当前状态
      console.log(`[AGENT] Requesting status update for ${agent.name || agentId}`)
      existingWs.send(JSON.stringify({ type: 'get_status', payload: {} }))
      return
    }
    // 连接已断开或正在关闭，确保完全关闭后再清理
    console.log(`[AGENT] Previous connection to ${agent.name || agentId} was not OPEN, cleaning up...`)
    
    // 等待旧连接完全关闭（避免与后端连接冲突）
    if (existingWs && existingWs.readyState !== WebSocket.CLOSED) {
      console.log(`[AGENT] Waiting for old connection to close (state: ${existingWs.readyState})`)
      existingWs.close()
      // 等待最多 1 秒让连接完全关闭
      await new Promise((resolve) => {
        if (existingWs.readyState === WebSocket.CLOSED) {
          resolve()
          return
        }
        const checkInterval = setInterval(() => {
          if (existingWs.readyState === WebSocket.CLOSED) {
            clearInterval(checkInterval)
            resolve()
          }
        }, 50)
        // 最多等待 1 秒
        setTimeout(() => {
          clearInterval(checkInterval)
          resolve()
        }, 1000)
      })
    }
    
    // 清理旧连接
    sockets.value.delete(agentId)
    console.log(`[AGENT] Old connection cleaned up`)
  }
  
  console.log(`[AGENT] Connecting to ${agent.name || agentId}`)
  
  const { host } = getGatewayAddress()
  const agentPort = agent.port
  const url = buildWebSocketUrl(host, agentPort)
  
  connecting.value = true
  
  // 返回 Promise，等待连接真正建立
  return new Promise((resolve, reject) => {
    try {
      const ws = new WebSocket(url)
      let connectionHandled = false // 防止重复处理连接结果
      
      // 设置连接超时
      const timeoutId = setTimeout(() => {
        if (connectionHandled) return
        connectionHandled = true
        
        console.error(`[AGENT ${agentId}] Connection timeout after ${connectionTimeout}ms`)
        ws.close()
        
        // 等待连接关闭后再重试
        const retryWithCleanup = async () => {
          // 清理可能存在的旧连接
          const oldWs = sockets.value.get(agentId)
          if (oldWs && oldWs !== ws && oldWs.readyState !== WebSocket.CLOSED) {
            console.log(`[AGENT ${agentId}] Cleaning up old connection before retry`)
            oldWs.close()
            await new Promise(resolve => {
              const check = setInterval(() => {
                if (oldWs.readyState === WebSocket.CLOSED) {
                  clearInterval(check)
                  resolve()
                }
              }, 50)
              setTimeout(() => {
                clearInterval(check)
                resolve()
              }, 500)
            })
            sockets.value.delete(agentId)
          }
          
          if (retryCount < maxRetries) {
            console.log(`[AGENT ${agentId}] Retrying... (${retryCount + 1}/${maxRetries})`)
            connecting.value = false
            setTimeout(() => {
              connectToAgent(agent, retryCount + 1).then(resolve).catch(reject)
            }, retryDelay)
          } else {
            connecting.value = false
            const error = new Error(`Connection failed after ${maxRetries} retries`)
            console.error(`[AGENT ${agentId}]`, error.message)
            reject(error)
          }
        }
        
        retryWithCleanup()
      }, connectionTimeout) // 结束 setTimeout
      
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
        if (connectionHandled) {
          console.log(`[AGENT ${agentId}] Connection already handled, ignoring onopen`)
          return
        }
        connectionHandled = true
        
        clearTimeout(timeoutId)
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
        
        // 连接成功，resolve Promise
        resolve(ws)
      }
      
      ws.onclose = (event) => {
        if (connectionHandled) {
          console.log(`[AGENT ${agentId}] Connection already handled, ignoring onclose`)
          return
        }
        connectionHandled = true
        
        clearTimeout(timeoutId)
        console.log(`[AGENT ${agentId}] Disconnected, code: ${event.code}, reason: ${event.reason}`)
        sockets.value.delete(agentId)
        if (connecting.value) connecting.value = false
        
        // 如果连接未完成就关闭，视为失败，触发重试
        if (!ws._connectionCompleted && retryCount < maxRetries) {
          console.log(`[AGENT ${agentId}] Connection closed before completion, retrying... (${retryCount + 1}/${maxRetries})`)
          
          // 等待当前连接完全关闭后再重试（避免与后端连接冲突）
          const retryAfterClose = async () => {
            if (ws.readyState !== WebSocket.CLOSED) {
              console.log(`[AGENT ${agentId}] Waiting for connection to fully close...`)
              await new Promise(resolve => {
                const check = setInterval(() => {
                  if (ws.readyState === WebSocket.CLOSED) {
                    clearInterval(check)
                    resolve()
                  }
                }, 50)
                setTimeout(() => {
                  clearInterval(check)
                  resolve()
                }, 500)
              })
            }
            
            console.log(`[AGENT ${agentId}] Retrying... (${retryCount + 1}/${maxRetries})`)
            connectToAgent(agent, retryCount + 1).then(resolve).catch(reject)
          }
          
          setTimeout(retryAfterClose, retryDelay)
        }
      }
      
      ws.onerror = (error) => {
        if (connectionHandled) {
          console.log(`[AGENT ${agentId}] Connection already handled, ignoring onerror`)
          return
        }
        connectionHandled = true
        
        clearTimeout(timeoutId)
        console.error(`[AGENT ${agentId}] Connection error:`, error)
        if (connecting.value) connecting.value = false
        
        // 触发重试
        if (retryCount < maxRetries) {
          console.log(`[AGENT ${agentId}] Error occurred, retrying... (${retryCount + 1}/${maxRetries})`)
          
          // 关闭并等待连接完全关闭后再重试
          const retryAfterError = async () => {
            ws.close()
            if (ws.readyState !== WebSocket.CLOSED) {
              console.log(`[AGENT ${agentId}] Waiting for connection to fully close...`)
              await new Promise(resolve => {
                const check = setInterval(() => {
                  if (ws.readyState === WebSocket.CLOSED) {
                    clearInterval(check)
                    resolve()
                  }
                }, 50)
                setTimeout(() => {
                  clearInterval(check)
                  resolve()
                }, 500)
              })
            }
            
            connectToAgent(agent, retryCount + 1).then(resolve).catch(reject)
          }
          
          setTimeout(retryAfterError, retryDelay)
        } else {
          const err = new Error(`Connection failed after ${maxRetries} retries`)
          reject(err)
        }
      }
      
    } catch (error) {
      console.error(`[AGENT ${agentId}] Failed to connect:`, error)
      connecting.value = false
      
      if (retryCount < maxRetries) {
        console.log(`[AGENT ${agentId}] Exception occurred, retrying... (${retryCount + 1}/${maxRetries})`)
        setTimeout(() => {
          connectToAgent(agent, retryCount + 1).then(resolve).catch(reject)
        }, retryDelay)
      } else {
        reject(error)
      }
    }
  })
}

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
    'waiting_single': '等待确认'
  }
  const executionStatusText = labels[executionStatus] || '运行中'
  
  // 组合显示：运行中（等待状态）
  return `运行中（${executionStatusText}）`
}

// 获取状态 CSS 类名
function getStatusClass(agent) {
  const statusData = agentStatuses.value.get(agent.agent_id)
  
  // 如果 Agent 已停止
  if (agent.status === 'stopped') {
    return 'stopped'
  }
  
  // 如果没有运行状态数据，默认 running
  if (!statusData) {
    return 'running'
  }
  
  // 返回运行状态的类名
  return statusData.execution_status || 'running'
}

// 查询 Agent 状态
async function fetchAgentStatus(agent) {
  if (!agent || !agent.port) {
    console.warn('[AGENT STATUS] Invalid agent:', agent)
    return 'running' // 默认返回 running
  }
  
  try {
    const { host } = getGatewayAddress()
    const port = agent.port
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/status`)
    
    if (!response.ok) {
      console.warn(`[AGENT STATUS] Failed to fetch status for agent ${agent.agent_id}:`, response.status)
      return 'running' // 默认返回 running
    }
    
    const result = await response.json()
    // execution_status 是任务级别状态（running/waiting_multi/waiting_single）
    const executionStatus = result.execution_status || 'running'
    
    // 更新状态映射（存储对象格式）
    agentStatuses.value.set(agent.agent_id, {execution_status: executionStatus})
    
    console.log(`[AGENT STATUS] Agent ${agent.agent_id} execution_status:`, executionStatus)
    return executionStatus
  } catch (error) {
    console.error(`[AGENT STATUS] Error fetching status for agent ${agent.agent_id}:`, error)
    return 'running' // 错误时返回默认状态
  }
}

// Session 恢复相关函数
async function restoreSession(sessionFile) {
  if (!sessionFile || !currentAgentId.value) {
    console.error('[SESSION] Invalid parameters:', { sessionFile, agentId: currentAgentId.value })
    return
  }

  try {
    const response = await fetch(`${apiBase.value}/api/agents/${currentAgentId.value}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_file: sessionFile })
    })

    const result = await response.json()
    if (result.success) {
      console.log('[SESSION] Session restored successfully:', result)
      showSessionDialog.value = false
      // 加载历史消息
      loadHistoryMessages(false)
    } else {
      console.error('[SESSION] Failed to restore session:', result.error)
      alert(`恢复会话失败: ${result.error}`)
    }
  } catch (error) {
    console.error('[SESSION] Error restoring session:', error)
    alert(`恢复会话失败: ${error.message}`)
  }
}

function cancelSessionDialog() {
  console.log('[SESSION] User cancelled session selection')
  showSessionDialog.value = false
  // 加载历史消息（用户不恢复 session）
  loadHistoryMessages(false)
}

// 创建 Agent
// 目录选择相关函数
async function openDirDialog() {
  showDirDialog.value = true
  selectedDir.value = newAgentDir.value || '~'
  dirSearchText.value = '' // 清空搜索
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
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/directories?path=${encodeURIComponent(path)}`)
    
    if (!response.ok) {
      const error = await response.json()
      console.error('[DIR] 获取目录列表失败:', error)
      alert(`获取目录列表失败: ${error.error?.message || '未知错误'}`)
      return
    }
    
    const result = await response.json()
    if (result.success && result.data) {
      currentDirPath.value = result.data.current_path
      dirList.value = result.data.directories || []
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
    // ESC 键关闭对话框
    cancelDirDialog()
    event.preventDefault()
    return
  }
  
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
      selectedDirIndex.value = -1
    }
    // 选中的目录同时设置为 selectedDir
    if (selectedDirIndex.value >= 0 && selectedDirIndex.value <= maxIndex) {
      selectedDir.value = filteredDirList.value[selectedDirIndex.value].path
    }
    event.preventDefault()
    return
  }
  
  if (event.key === 'Enter') {
    // 回车键：如果选中了列表项，则进入该目录；否则确认当前选择
    if (selectedDirIndex.value >= 0 && selectedDirIndex.value <= maxIndex) {
      // 有选中列表项，进入该目录
      enterDirectory(filteredDirList.value[selectedDirIndex.value].path)
      event.preventDefault()
    } else if (selectedDir.value) {
      // 没有选中列表项，但已经有选中的目录，确认并关闭
      confirmDirectory()
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
    newAgentDir.value = selectedDir.value
    showDirDialog.value = false
  }
}

function cancelDirDialog() {
  showDirDialog.value = false
  selectedDir.value = null
}

// 获取模型组列表
async function fetchModelGroups() {
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/model-groups`)
    
    if (!response.ok) {
      console.error('[MODEL GROUP] 获取模型组列表失败:', response.status)
      return
    }
    
    const result = await response.json()
    if (result.success && result.data) {
      modelGroups.value = result.data
      // 如果模型组列表不为空，优先使用配置的默认模型组
      if (modelGroups.value.length > 0) {
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

async function createAgent() {
  if (!newAgentDir.value.trim()) return
  
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/agents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_type: newAgentType.value,
        working_dir: newAgentDir.value,
        name: newAgentName.value || undefined,
        llm_group: newAgentModelGroup.value
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
      
      // 添加到列表开头（让后创建的 agent 排在前面）
      agentList.value.unshift(agent)
      
      // 关闭创建弹窗
      showCreateAgentModal.value = false
      newAgentDir.value = '~' // 重置为默认值
      // 重置为默认名称（根据当前选中的 agent 类型）
      newAgentName.value = newAgentType.value === 'agent' ? '通用Agent' : '代码Agent'
      
      // 立即切换到新创建的 agent
      await switchAgent(agent)
      
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

// 打开补全列表
async function openCompletions() {
  if (!currentAgent.value) {
    alert('请先选择一个 Agent')
    return
  }
  
  completionSearch.value = ''
  selectedIndex.value = -1
  showCompletions.value = true
  
  // 获取补全列表
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/completions/${currentAgent.value.agent_id}`)
    
    const result = await response.json()
    console.log('[COMPLETIONS] API response:', result)
    
    if (!response.ok) {
      alert(`获取补全列表失败: ${result.error?.message || result.detail || '未知错误'}`)
      return
    }
    
    if (result.success && result.data) {
      completions.value = result.data
      console.log('[COMPLETIONS] Loaded', result.data.length, 'completions')
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
    return completions.value
  }
  
  const search = completionSearch.value.toLowerCase()
  return completions.value.filter(item => 
    item.display.toLowerCase().includes(search) || 
    item.description.toLowerCase().includes(search)
  )
})

// 处理补全对话框的键盘事件
function handleCompletionKeydown(event) {
  const maxIndex = filteredCompletions.value.length - 1
  
  if (event.key === 'Escape') {
    // ESC 键关闭对话框
    showCompletions.value = false
    selectedIndex.value = -1
    event.preventDefault()
    return
  }
  
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
      insertCompletion(filteredCompletions.value[selectedIndex.value])
      event.preventDefault()
    }
    return
  }
}

// 滚动到选中的条目
function scrollToSelected() {
  nextTick(() => {
    const selectedItem = completionItemsRef.value[selectedIndex.value]
    const listContainer = completionsListRef.value
    
    if (selectedItem && listContainer) {
      const containerRect = listContainer.getBoundingClientRect()
      const itemRect = selectedItem.getBoundingClientRect()
      
      // 计算相对位置（考虑到可能的滚动偏移）
      const itemTop = selectedItem.offsetTop
      const itemBottom = itemTop + selectedItem.offsetHeight
      const containerScrollTop = listContainer.scrollTop
      const containerBottom = containerScrollTop + containerRect.height
      
      // 如果选中条目在可视区域上方，滚动到显示它
      if (itemTop < containerScrollTop) {
        listContainer.scrollTop = itemTop
      }
      // 如果选中条目在可视区域下方，滚动到显示它
      else if (itemBottom > containerBottom) {
        listContainer.scrollTop = itemBottom - containerRect.height
      }
    }
  })
}

// 插入选中的补全
function insertCompletion(item) {
  const textarea = document.querySelector('.input-wrapper textarea')
  if (!textarea) return
  
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const text = textarea.value
  
  // 在光标位置插入补全（添加单引号包裹）
  const valueToInsert = `'${item.value}'`
  const newText = text.substring(0, start) + valueToInsert + text.substring(end)
  inputText.value = newText
  
  // 设置新的光标位置
  textarea.value = newText
  const newCursorPos = start + valueToInsert.length
  textarea.setSelectionRange(newCursorPos, newCursorPos)
  textarea.focus()
  
  // 关闭弹窗
  showCompletions.value = false
  selectedIndex.value = -1
}

// 获取 Agent 列表
async function fetchAgentList() {
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/agents`)
    
    if (!response.ok) return
    
    const result = await response.json()
    console.log('[AGENT] List:', result)
    
    // 更新列表（后端返回格式: { success: true, data: agents }）
    if (result.success && result.data) {
      // 反转数组，让后创建的 agent 排在前面
      agentList.value = result.data.slice().reverse()
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
// 复制 Agent
async function copyAgent(agent) {
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/agents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_type: agent.agent_type,
        working_dir: agent.working_dir,
        name: agent.name || undefined
      })
    })
    
    if (!response.ok) {
      const error = await response.json()
      alert(`复制失败: ${error.error?.message || error.detail || '未知错误'}`)
      return
    }
    
    const result = await response.json()
    console.log('[AGENT] Copied:', result)
    
    // 后端返回格式: { success: true, data: agent }
    if (result.success && result.data) {
      const newAgent = result.data
      
      // 添加到列表开头
      agentList.value.unshift(newAgent)
      
      // 立即切换到新复制的 agent
      await switchAgent(newAgent)
      
      // 刷新列表
      await fetchAgentList()
      
      console.log(`[AGENT] Successfully copied agent ${agent.agent_id}`)
    } else {
      alert('复制失败：返回数据格式错误')
    }
  } catch (error) {
    console.error('[AGENT] Copy failed:', error)
    alert(`复制失败: ${error.message}`)
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
    
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/agents/${agent.agent_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    
    if (!response.ok) {
      const error = await response.json()
      alert(`重命名失败: ${error.error?.message || error.detail || '未知错误'}`)
      return
    }
    
    await fetchAgentList()
    console.log(`[AGENT] Successfully renamed agent ${agent.agent_id}`)
    showToast('重命名成功', 'success')
    showRenameAgentModal.value = false
  } catch (error) {
    console.error('[AGENT] Rename failed:', error)
    alert(`重命名失败: ${error.message}`)
  }
}

// 删除 Agent
async function deleteAgent(agentId) {
  // 隐藏 agent 侧边栏，避免遮挡确认对话框（仅移动端）
  if (windowWidth.value <= 768) showAgentSidebar.value = false
  showConfirm(
    '确认删除该 Agent？删除后将无法恢复，且会清除所有历史记录。',
    async () => {
      try {
        const { host, port } = getGatewayAddress()
        const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/agents/${agentId}`, {
          method: 'DELETE'
        })
        
        const result = await response.json()
        
        if (!response.ok || !result.success) {
          alert(`删除失败: ${result.error?.message || '未知错误'}`)
          return
        }
        
        console.log('[AGENT] Deleted:', agentId)
        
        // 清除该 Agent 的历史记录
        historyStorage.clearHistoryForAgent(agentId)
        
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

// 切换当前工作的 Agent
async function switchAgent(agent) {
  console.log('[AGENT] switchAgent called with:', agent)
  if (agent.agent_id === currentAgentId.value) {
    console.log('[AGENT] Already on this agent, checking connection...')
    // 检查 WebSocket 连接是否存在
    const ws = sockets.value.get(agent.agent_id)
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.log('[AGENT] WebSocket not connected, reconnecting...')
      try {
        await connectToAgent(agent)
        // 重连成功后加载历史消息
        const currentOutputs = allOutputs.value.get(agent.agent_id) || []
        if (currentOutputs.length === 0) {
          console.log(`[AGENT] Loading history after reconnect`)
          loadHistoryMessages(false)
        }
      } catch (error) {
        console.error(`[AGENT] Failed to reconnect:`, error)
        // 不中断流程，让用户看到错误
      }
    } else {
      console.log('[AGENT] WebSocket already connected, skipping')
    }
    return
  }
  
  console.log('[AGENT] Switching to:', agent)
  
  // 清空输入状态
  lastInputRequest.value = null
  inputText.value = ''
  inputTip.value = ''
  
  // 更新当前 Agent ID
  currentAgentId.value = agent.agent_id
  console.log('[AGENT] Current agent ID updated to:', currentAgentId.value)
  
  // 重置历史偏移量和消息状态
  historyOffset.value = 0
  hasMoreHistory.value = true
  
  // 清空当前 Agent 的消息列表
  allOutputs.value.set(agent.agent_id, [])
  
  // 连接到目标 Agent（等待连接真正建立）
  try {
    // 切换后立即查询一次状态（即使 WebSocket 未连接）
    console.log('[AGENT] Fetching status after switch...')
    await fetchAgentStatus(agent)
    
    // 如果 Agent 已停止（已完成），不尝试连接 WebSocket
    if (agent.status === 'stopped') {
      console.log('[AGENT] Agent is stopped (completed), skipping WebSocket connection')
      // 直接加载历史消息
      const currentOutputs = allOutputs.value.get(agent.agent_id) || []
      if (currentOutputs.length === 0) {
        console.log('[AGENT] Loading history messages...')
        loadHistoryMessages(false)
      } else {
        console.log('[AGENT] Messages already exist, skip loading history')
      }
      return
    }
    
    await connectToAgent(agent)
    
    // 验证连接是否真的成功
    const ws = sockets.value.get(agent.agent_id)
    if (ws && ws.readyState === WebSocket.OPEN) {
      console.log('[AGENT] Connection verified successfully')
      // 连接成功后再次查询状态，确保同步
      console.log('[AGENT] Fetching status after connection...')
      await fetchAgentStatus(agent)
      
      // 检测可恢复的 session（仅新创建的 Agent）
      const currentOutputs = allOutputs.value.get(agent.agent_id) || []
      if (currentOutputs.length === 0) {
        console.log('[AGENT] New agent, checking for recoverable sessions...')
        try {
          const sessionsResponse = await fetch(`${apiBase.value}/api/agents/${agent.agent_id}/sessions`)
          const sessionsData = await sessionsResponse.json()
          if (sessionsData.success && sessionsData.data && sessionsData.data.length > 0) {
            console.log('[AGENT] Found recoverable sessions:', sessionsData.data)
            // 显示 session 选择对话框
            availableSessions.value = sessionsData.data
            showSessionDialog.value = true
          } else {
            console.log('[AGENT] No recoverable sessions found')
            loadHistoryMessages(false)
          }
        } catch (error) {
          console.error('[AGENT] Failed to fetch sessions:', error)
          // 加载历史消息（即使在获取 session 列表失败时）
          loadHistoryMessages(false)
        }
      } else {
        console.log('[AGENT] Agent has existing messages, skipping session detection')
      }
    } else {
      console.warn('[AGENT] Connection verification failed, WebSocket not in OPEN state')
      // WebSocket 未连接，但已经通过 HTTP 查询了状态
      console.log('[AGENT] Status fetched via HTTP, but WebSocket not connected')
    }
  } catch (error) {
    console.error('[AGENT] Failed to connect to agent:', error)
    // 连接失败，不加载历史消息，但保持当前状态
    // 用户可以看到错误并手动重试
    // 即使连接失败，状态已通过 HTTP 查询
  }
  
  // 移动端：切换agent后自动隐藏侧边栏
  if (windowWidth.value <= 768) {
    showAgentSidebar.value = false
    console.log('[AGENT] Mobile mode: auto hide sidebar after switching agent')
  }
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
  
  // 调试：记录所有收到的消息类型
  console.log(`[ws] Received message type: ${type}`, {execution_id: payload?.execution_id})
  
  // 确定目标 Agent ID：优先使用传入的 agentId，否则使用 currentAgentId
  const targetAgentId = agentId || currentAgentId.value
  if (type === 'ready') {
    console.log('[ws] ready payload', payload)
    // 恢复之前的输入请求状态
    if (lastInputRequest.value) {
      console.log('[ws] Restoring input request from previous session')
      inputTip.value = lastInputRequest.value.tip || ''
      inputMode.value = lastInputRequest.value.mode || 'multi'
      inputText.value = lastInputRequest.value.preset || ''
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
        // 使用 renderMessageHtml 确保流式消息和历史消息使用相同的渲染逻辑
        streamingMessage.value.html = renderMessageHtml(streamingMessage.value)
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
        // 保存流式消息到历史记录（在删除之前）
        try {
          const messageToSave = {
            agent_id: targetAgentId,
            output_type: 'text', // 保存为普通文本消息
            text: streamingMessage.value.text,
            lang: streamingMessage.value.lang,
            agent_name: streamingMessage.value.agent_name,
            model_name: streamingMessage.value.model_name,
            non_interactive: false,
            timestamp: streamingMessage.value.timestamp,
            context: streamingMessage.value.context || {},
          }
          console.log(`🚨 [STREAM] Saving streaming message to history: text_length=${messageToSave.text.length}, agent_id=${targetAgentId}`)
          historyStorage.saveMessage(messageToSave)
        } catch (error) {
          console.warn('[STREAM] Failed to save streaming message to history:', error)
        }
        
        // 从 outputs 数组中删除流式消息
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
    const agentId = currentAgentId.value
    
    // 检查缓冲区是否有内容
    if (agentId && inputBuffers.value.has(agentId)) {
      // 完成信号 (__CTRL_C_PRESSED__) 只发送给多行输入
      const bufferedText = inputBuffers.value.get(agentId)
      const isCompletionSignal = bufferedText === '__CTRL_C_PRESSED__'
      const isMultiLineRequest = payload.mode === 'multi'
      
      if (isCompletionSignal && !isMultiLineRequest) {
        // 完成信号不能发送给单行输入（如确认对话框），清空缓冲区
        console.log('[INPUT_REQUEST] Completion signal in buffer but request is single-line, discarding')
        inputBuffers.value.delete(agentId)
      } else {
        // 普通输入或匹配的多行输入，发送缓冲区内容
        console.log('[INPUT_REQUEST] Found buffered input, auto-sending')
        inputBuffers.value.delete(agentId)
        sendInputResult(bufferedText, payload.request_id)
      }
      return
    }
    
    // 保存输入请求，用于重连后恢复
    lastInputRequest.value = payload
    inputTip.value = payload.tip || ''
    inputMode.value = payload.mode || 'multi'  // 默认多行
    inputText.value = payload.preset || ''
    
    // 检查是否在底部（用于判断是否需要在显示输入框后滚动）
    const SCROLL_THRESHOLD = 50 // 50px 的容差
    let shouldScrollAfterInputShow = false
    if (outputList.value) {
      const scrollTop = outputList.value.scrollTop
      const scrollHeight = outputList.value.scrollHeight
      const clientHeight = outputList.value.clientHeight
      // 如果已经接近底部，则记录需要在显示输入框后滚动
      shouldScrollAfterInputShow = (scrollTop + clientHeight >= scrollHeight - SCROLL_THRESHOLD)
      console.log('[INPUT_REQUEST] Before show - scrollTop:', scrollTop, 'scrollHeight:', scrollHeight, 'clientHeight:', clientHeight, 'shouldScroll:', shouldScrollAfterInputShow)
    }
    
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
    showConfirm(
      payload.message || '请确认',
      () => {
        sendConfirmResult(true)
      },
      () => {
        sendConfirmResult(false)
      },
      payload.default !== undefined ? payload.default : true
    )
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
    // 独立终端（execution_id 以 'terminal_' 开头）不需要创建聊天消息
    // 因为它们的输出会直接写入终端面板，由 appendExecution 处理
    if (!existingItem && !executionId.startsWith('terminal_')) {
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
  } else if (type === 'terminal_created') {
    // 独立终端创建成功
    console.log('[ws] terminal_created', payload)
    const terminalId = payload?.terminal_id
    if (terminalId) {
      terminalSessions.value.push({
        terminal_id: terminalId,
        interpreter: payload?.interpreter || 'bash',
        working_dir: payload?.working_dir || '.',
        terminal: null,
        hostEl: null,
        fitAddon: null,
        resizeObserver: null,  // ResizeObserver 实例
        history: []  // 保存历史输出，用于面板隐藏后再显示时恢复
      })
      // 自动切换到新创建的 terminal
      activeTerminalId.value = terminalId
      // 初始化终端
      nextTick(() => {
        const hostEl = independentTerminalHosts.value.get(terminalId)
        if (hostEl) {
          initIndependentTerminal(terminalId, hostEl)
        }
      })
    }
  } else if (type === 'terminal_closed') {
    // 独立终端关闭
    console.log('[ws] terminal_closed', payload)
    const terminalId = payload?.terminal_id
    if (terminalId) {
      // 检查终端是否还存在，避免重复关闭导致无限循环
      const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
      if (session) {
        closeTerminal(terminalId)
      } else {
        console.log(`[ws] terminal ${terminalId} already closed, ignoring`)
      }
    }
  } else if (type === 'error') {
    console.warn('[ws] error payload', payload)
    const errorMessage = payload?.message || '未知错误'
    const errorCode = payload?.code || ''
    
    // 如果是认证失败或连接被拒绝，重新显示连接对话框
    if (errorCode === 'AUTH_FAILED' || errorCode === 'CONNECTION_REJECTED') {
      // 显示错误信息
      connectErrorMessage.value = errorMessage
      // 清空密码输入框
      auth.value.password = ''
      // 重新显示连接对话框
      showConnectModal.value = true
    }
    
    appendOutput({
      output_type: 'ERROR',
      text: errorMessage,
      lang: 'text',
    })
  } else if (type === 'status_update') {
    console.log('[ws] status_update payload', payload)
    // 更新 Agent 执行状态
    if (payload?.execution_status) {
      agentStatuses.value.set(targetAgentId, {execution_status: payload.execution_status})
      console.log('[ws] Agent execution status updated:', payload.execution_status)
      // 当 Agent 开始思考时，自动滚动到底部
      if (payload.execution_status === 'running') {
        nextTick(() => {
          if (outputList.value) {
            outputList.value.scrollTop = outputList.value.scrollHeight
          }
        })
      }
    }
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
      const oldNumClass = (type === 'replace' || type === 'delete') ? 'diff-deleted' : ''
      html += `<td class="diff-line-num diff-old-num ${oldNumClass}">${escapeHtml(String(old_line_num || ''))}</td>`
      
      // 统计并保留缩进
      let oldContent = ''
      if (old_line) {
        const leadingSpaces = old_line.match(/^(\s*)/)[0]
        let highlighted
        try {
          highlighted = hljs.highlight(old_line, { language }).value
          // 在高亮结果前添加显式的 &nbsp; 来保留缩进
          oldContent = '&nbsp;'.repeat(leadingSpaces.length) + highlighted.replace(/^(\s+)/, '')
        } catch (e) {
          // 如果语法高亮不支持该语言，降级为纯文本显示
          console.warn('[highlight.js] Language not supported:', language, e)
          oldContent = '&nbsp;'.repeat(leadingSpaces.length) + escapeHtml(old_line)
        }
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
      const newNumClass = (type === 'replace' || type === 'insert') ? 'diff-added' : ''
      html += `<td class="diff-line-num diff-new-num ${newNumClass}">${escapeHtml(String(new_line_num || ''))}</td>`
      
      // 统计并保留缩进
      let newContent = ''
      if (new_line) {
        const leadingSpaces = new_line.match(/^(\s*)/)[0]
        let highlighted
        try {
          highlighted = hljs.highlight(new_line, { language }).value
          // 在高亮结果前添加显式的 &nbsp; 来保留缩进
          newContent = '&nbsp;'.repeat(leadingSpaces.length) + highlighted.replace(/^(\s+)/, '')
        } catch (e) {
          // 如果语法高亮不支持该语言，降级为纯文本显示
          console.warn('[highlight.js] Language not supported:', language, e)
          newContent = '&nbsp;'.repeat(leadingSpaces.length) + escapeHtml(new_line)
        }
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
      console.error('[DIFF] Failed to parse side by side diff:', e)
      return escapeHtml(payload.text || '')
    }
  }
  if (payload?.lang === 'markdown') {
    return marked.parse(payload.text || '')
  } else if (payload?.lang === 'diff') {
    // 将 diff 包装在 markdown 代码块中，以便语法高亮
    return marked.parse(`\`\`\`diff\n${payload.text || ''}\n\`\`\``)
  } else {
    return escapeHtml(payload.text || '')
  }
}

function appendOutput(payload, agentId = null) {
  const html = renderMessageHtml(payload)
  
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
    // 未完成的 execution 消息不保存，只在结束时保存一次
    const isUnfinishedExecution = outputItem.output_type === 'execution' && !outputItem.is_finished
    
    if (!isUnfinishedExecution) {
      // 只保存必要的数据，避免存储过大的内容
      const messageToSave = {
        agent_id: targetAgentId, // 保存当前 Agent ID
        output_type: outputItem.output_type,
        text: outputItem.text,
        lang: outputItem.lang,
        agent_name: outputItem.agent_name,
        non_interactive: outputItem.non_interactive,
        timestamp: outputItem.timestamp,
        execution_id: outputItem.execution_id,
        context: outputItem.context,
        is_finished: outputItem.is_finished,
        terminal_content: outputItem.terminal_content,
      }
      console.log(`🚨 [appendOutput] Saving message: type=${outputItem.output_type}, execution_id=${outputItem.execution_id}, agent_id=${targetAgentId}`)
      historyStorage.saveMessage(messageToSave)
    } else {
      console.log(`🚨 [appendOutput] Skipping unfinished execution: execution_id=${outputItem.execution_id}`)
    }
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

// 复制消息内容到剪贴板
async function copyToClipboard(text, index) {
  if (!text) {
    console.warn('[COPY] No text to copy')
    return
  }
  
  try {
    await navigator.clipboard.writeText(text)
    console.log('[COPY] Successfully copied text to clipboard')
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
      console.log('[COPY] Fallback: Successfully copied using execCommand')
    } catch (fallbackErr) {
      console.error('[COPY] Fallback also failed:', fallbackErr)
      alert('复制失败，请手动复制')
    }
  }
}

function appendExecution(payload) {
  const executionId = payload?.execution_id || 'default'
  const eventType = payload?.event_type
  
  console.log(`[terminal DEBUG] appendExecution: executionId=${executionId}, eventType=${eventType}, hasData=${!!payload?.data}, encoded=${payload?.encoded}`)
  
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
      console.log(`[independent-terminal] Terminal not ready, buffering output for ${terminalId}`)
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
    
    // 保存终端内容到消息列表
    if (termInfo.terminal) {
      termInfo.terminal.writeln('\r\n[status] Execution completed - terminal is now read-only')
      
      // 获取终端内容并保存
      try {
        const buffer = termInfo.terminal.buffer.active
        const lines = []
        for (let i = 0; i < buffer.length; i++) {
          const line = buffer.getLine(i)
          if (line) {
            const lineText = line.translateToString(true)
            lines.push(lineText)
          }
        }
        const terminalContent = lines.join('\n')
        
        console.log(`[terminal] Saving terminal content, length: ${terminalContent.length} chars`)
        
        // 找到并更新 execution 消息，添加 is_finished 标记和 terminal_content
        const targetAgentId = currentAgentId.value
        const currentOutputs = allOutputs.value.get(targetAgentId) || []
        console.log(`🚨 [terminal] Looking for execution message: ${executionId}`)
        
        const execIndex = currentOutputs.findIndex(
          item => item.output_type === 'execution' && item.execution_id === executionId
        )
        
        if (execIndex !== -1) {
          // 标记 execution 消息为已结束，并保存终端内容
          currentOutputs[execIndex].is_finished = true
          currentOutputs[execIndex].terminal_content = terminalContent
          currentOutputs[execIndex].timestamp = new Date().toISOString()
          console.log(`🚨 [terminal] Marked execution ${executionId} as finished, content length: ${terminalContent.length}`)
          
          // 触发响应式更新
          allOutputs.value.set(targetAgentId, [...currentOutputs])
          
          // 保存到历史记录（更新原有的 execution 消息）
          try {
            const updatedMessage = {
              agent_id: targetAgentId,
              output_type: 'execution',
              text: '',
              lang: 'text',
              non_interactive: false,
              timestamp: currentOutputs[execIndex].timestamp,
              execution_id: executionId,
              is_finished: true,
              terminal_content: terminalContent,
            }
            historyStorage.saveMessage(updatedMessage)
            console.log(`🚨 [terminal] Saved to history: is_finished=true, content_length=${terminalContent.length}`)
          } catch (error) {
            console.warn('[HISTORY] Failed to save terminal content:', error)
          }
        } else {
          console.warn(`🚨 [terminal] execution message ${executionId} not found`)
        }
        
        console.log(`[terminal] Terminal content saved to message list and history for agent: ${targetAgentId}`)
      } catch (error) {
        console.error(`[terminal] Failed to save terminal content:`, error)
      }
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
  
  const userInput = inputText.value.trim()
  if (!userInput) {
    return
  }
  
  // 获取当前运行状态
  const statusData = agentStatuses.value.get(agentId)
  const executionStatus = statusData?.execution_status || 'running'
  
  // 判断是发送到缓冲区还是直接发送
  // 只有当运行状态是 waiting_multi（等待多行输入）时，才直接发送
  // 其他情况（running、waiting_single）都保存到缓冲区
  if (executionStatus === 'waiting_multi') {
    // 后端正在等待多行输入，直接发送
    console.log('[SUBMIT] Sending input directly to backend (execution_status: waiting_multi)')
    sendInputDirectly(userInput)
  } else {
    // 后端没有等待输入，保存到缓冲区
    console.log('[SUBMIT] Saving input to buffer (execution_status:', executionStatus, ')')
    inputBuffers.value.set(agentId, userInput)
    appendOutput({
      output_type: 'system',
      agent_name: 'system',
      text: '✓ 输入已保存到缓冲区，等待后端请求',
      lang: 'text',
    })
  }
  
  inputText.value = ''
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
  
  // 发送 Ctrl+C 信号作为完成信号（与 CLI 模式按 Ctrl+C 行为一致）
  // 注意：完成信号只针对多行输入，单行输入（如确认对话框）不使用完成按钮
  if (executionStatus === 'waiting_multi') {
    // 后端正在等待多行输入，直接发送 Ctrl+C 信号
    console.log('[SUBMIT] Sending Ctrl+C signal (__CTRL_C_PRESSED__) to backend (execution_status: waiting_multi)')
    sendInputDirectly('__CTRL_C_PRESSED__')
  } else {
    // 后端没有等待输入或正在等待单行输入，将完成信号保存到缓冲区（与普通输入统一机制）
    console.log('[SUBMIT] Caching completion signal to buffer (execution_status:', executionStatus, ')')
    inputBuffers.value.set(agentId, '__CTRL_C_PRESSED__')
    appendOutput({
      output_type: 'system',
      agent_name: 'system',
      text: '✅ 完成信号已保存到缓冲区，下次需要输入时自动触发',
      lang: 'text',
    })
  }
}

function sendInputDirectly(text) {
  const agentId = currentAgentId.value
  
  // 先将用户输入回显到聊天窗口（空消息或完成信号不显示）
  if (text && text !== '__CTRL_C_PRESSED__') {
    console.log('[DEBUG] User input payload:', {
      output_type: 'user_input',
      agent_name: 'user',
      text: text,
      lang: 'text',
    })
    appendOutput({
      output_type: 'user_input',
      agent_name: 'user',
      text: text,
      lang: 'text',
    })
  }
  
  const message = {
    type: 'input_result',
    payload: {
      text: text,
    },
  }
  console.log('[ws] send input_result', message)
  sendMessageToAgent(message)
  
  // 输入框现在是永久显示的，不需要隐藏
  lastInputRequest.value = null // 清空保存的输入请求
}

function sendInputResult(text, requestId) {
  const agentId = currentAgentId.value
  
  // 先将用户输入回显到聊天窗口
  console.log('[DEBUG] Buffered input payload:', {
    output_type: 'user_input',
    agent_name: 'user',
    text: text,
    lang: 'text',
  })
  appendOutput({
    output_type: 'user_input',
    agent_name: 'user',
    text: text,
    lang: 'text',
  })
  
  const message = {
    type: 'input_result',
    payload: {
      text: text,
      request_id: requestId,
    },
  }
  console.log('[ws] send input_result (from buffer)', message)
  sendMessageToAgent(message)
}

function sendBufferedInput() {
  const agentId = currentAgentId.value
  if (!agentId || !inputBuffers.value.has(agentId)) {
    return
  }
  const bufferedText = inputBuffers.value.get(agentId)
  // 清空缓冲区
  inputBuffers.value.delete(agentId)
  // 发送缓冲区内容
  sendInputDirectly(bufferedText)
}

function clearBuffer() {
  const agentId = currentAgentId.value
  if (!agentId) {
    return
  }
  inputBuffers.value.delete(agentId)
  appendOutput({
    output_type: 'system',
    agent_name: 'system',
    text: '🗑️ 缓冲区已清空',
    lang: 'text',
  })
}

function sendConfirmResult(confirmed) {
  const message = {
    type: 'confirm_result',
    payload: {
      confirmed,
    },
  }
  console.log('[ws] send confirm_result', message)
  sendMessageToAgent(message)
}

function sendInterrupt() {
  const message = {
    type: 'interrupt',
    payload: {},
  }
  console.log('[ws] send interrupt', message)
  sendMessageToAgent(message)
}

function sendManualInterrupt() {
  const message = {
    type: 'manual_interrupt',
    payload: {},
  }
  console.log('[ws] send manual interrupt', message)
  sendMessageToAgent(message)
}

function confirmClearHistory() {
  // 先关闭设置弹窗
  showSettingsModal.value = false
  
  showConfirm(
    '确定要清除所有历史记录吗？此操作不可撤销。',
    () => {
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
    }
  )
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

// 独立终端相关函数
function setTerminalHostRef(terminalId, el) {
  const session = terminalSessions.value.find(t => t.terminal_id === terminalId)
  if (el) {
    console.log(`[independent-terminal] Setting ref for terminal ${terminalId}`)
    independentTerminalHosts.value.set(terminalId, el)
    if (session) {
      session.hostEl = el
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
  
  // 如果 terminal 实例已存在（面板隐藏后又显示），重新打开并恢复历史输出
  if (session.terminal) {
    console.log(`[independent-terminal] Reopening terminal ${terminalId} with ${session.history.length} history entries`)
    try {
      session.terminal.open(el)
      session.hostEl = el
      
      // 等待 DOM 更新后再恢复内容
      nextTick(() => {
        // 先 fit 一次，确保终端大小正确
        session.fitAddon.fit()
        console.log(`[independent-terminal] Terminal size before reset: ${session.terminal.cols} cols x ${session.terminal.rows} rows`)
        // 清空终端，避免历史输出重复显示
        session.terminal.reset()
        // reset 后需要再次 fit，确保终端大小适应容器
        session.fitAddon.fit()
        console.log(`[independent-terminal] Terminal size after reset: ${session.terminal.cols} cols x ${session.terminal.rows} rows`)
        // 恢复 ResizeObserver
        if (typeof ResizeObserver !== 'undefined') {
          const resizeObserver = new ResizeObserver(() => {
            if (session.fitAddon && session.terminal) {
              session.fitAddon.fit()
              sendTerminalResize(terminalId, session.terminal.rows, session.terminal.cols)
            }
          })
          resizeObserver.observe(el)
        }
        // 恢复历史输出
        console.log(`[independent-terminal] Restoring ${session.history.length} history entries`)
        session.history.forEach((item, index) => {
          if (session.terminal) {
            console.log(`[independent-terminal] History [${index}]: ${JSON.stringify(item.data.substring(0, 50))}...`)
            session.terminal.write(item.data)
          }
        })
        console.log(`[independent-terminal] Terminal ${terminalId} reopened successfully`)
      })
    } catch (error) {
      console.error(`[independent-terminal] Failed to reopen terminal ${terminalId}:`, error)
    }
    return
  }
  
  console.log(`[independent-terminal] Initializing terminal ${terminalId}`)
  
  // 创建终端实例
  // 注意：这里不调用 fitAddon.fit()，因为初始时元素可能不可见（v-show）
  // 会在 ResizeObserver 回调中自动调整尺寸
  session.terminal = new Terminal({
    theme: {
      background: '#0b1220',
    },
    fontSize: 12,
    cols: 80,
    rows: 24,
  })
  session.terminal.open(el)
  
  // 创建并加载 FitAddon
  session.fitAddon = new FitAddon()
  session.terminal.loadAddon(session.fitAddon)
  
  // 使用 FitAddon 适配终端尺寸（仅当元素可见时）
  if (el.offsetParent !== null) {
    session.fitAddon.fit()
    console.log(`[independent-terminal] FitAddon fit: cols=${session.terminal.cols}, rows=${session.terminal.rows}`)
  } else {
    console.log(`[independent-terminal] Element is hidden, skipping fit`)
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
    sendTerminalInput(terminalId, data)
  })
  
  // 初始化后发送 resize
  setTimeout(() => {
    if (session.fitAddon && session.terminal) {
      session.fitAddon.fit()
      sendTerminalResize(terminalId, session.terminal.rows, session.terminal.cols)
      session.terminal.focus()
      
      // 写入缓冲的输出
      if (session.pending_output && session.pending_output.length > 0) {
        console.log(`[independent-terminal] Writing ${session.pending_output.length} buffered outputs to terminal ${terminalId}`)
        try {
          for (const bufferedData of session.pending_output) {
            session.terminal.write(bufferedData)
          }
          console.log(`[independent-terminal] Successfully wrote buffered outputs`)
        } catch (error) {
          console.error('[independent-terminal] Failed to write buffered outputs:', error)
        }
        // 清空缓冲区
        session.pending_output = []
      }
    }
  }, 300)
}

function createTerminal() {
  if (!socket.value) {
    console.warn('[independent-terminal] No socket connection')
    return
  }
  
  console.log('[independent-terminal] Creating new terminal')
  const message = {
    type: 'terminal_create',
    payload: {},
  }
  socket.value.send(JSON.stringify(message))
}

function closeTerminal(terminalId) {
  console.log(`[independent-terminal] Closing terminal ${terminalId}`)
  
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
  
  // 发送关闭消息到后端
  if (socket.value) {
    const message = {
      type: 'terminal_close',
      payload: {
        terminal_id: terminalId,
      },
    }
    socket.value.send(JSON.stringify(message))
  }
  
  // 清理 ref
  independentTerminalHosts.value.delete(terminalId)
}

// 终端面板大小调整
const terminalPanelSize = ref({
  width: 800,
  height: 500,
})

// 监听面板显示状态
watch(showTerminalPanel, (newValue, oldValue) => {
  if (!newValue && oldValue) {
    // 面板隐藏时，禁用所有终端的 ResizeObserver
    console.log('[independent-terminal] Panel hiding, disabling ResizeObserver for all terminals')
    terminalSessions.value.forEach(session => {
      if (session.resizeObserver) {
        session.resizeObserver.disconnect()
      }
    })
  } else if (newValue && !oldValue) {
    // 面板显示时，只启用当前活跃终端的 ResizeObserver
    console.log('[independent-terminal] Panel showing, enabling ResizeObserver for active terminal')
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
    console.log(`[independent-terminal] Switching terminal: ${oldId} -> ${newId}`)
    
    // 禁用旧终端的 ResizeObserver
    const oldSession = terminalSessions.value.find(s => s.terminal_id === oldId)
    if (oldSession && oldSession.resizeObserver) {
      oldSession.resizeObserver.disconnect()
      console.log(`[independent-terminal] Disabled ResizeObserver for terminal ${oldId}`)
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
        console.log(`[independent-terminal] Enabled ResizeObserver for terminal ${newId}: ${newSession.terminal.cols} cols x ${newSession.terminal.rows} rows`)
      })
    }
  }
})

let isResizing = false
let resizeStartX = 0
let resizeStartY = 0
let resizeStartWidth = 0
let resizeStartHeight = 0

function startResizeTerminal(event) {
  isResizing = true
  resizeStartX = event.clientX
  resizeStartY = event.clientY
  resizeStartWidth = terminalPanelSize.value.width
  resizeStartHeight = terminalPanelSize.value.height
  
  document.addEventListener('mousemove', onResizeTerminal)
  document.addEventListener('mouseup', stopResizeTerminal)
  event.preventDefault()
}

function onResizeTerminal(event) {
  if (!isResizing) return
  
  const deltaX = event.clientX - resizeStartX
  const deltaY = event.clientY - resizeStartY
  
  // 计算新尺寸（固定右侧的面板）
  // 手柄向左拖（deltaX < 0）：面板变宽
  // 手柄向右拖（deltaX > 0）：面板变窄
  // 手柄向下拖（deltaY > 0）：面板变高
  // 手柄向上拖（deltaY < 0）：面板变矮
  const newWidth = Math.max(400, resizeStartWidth - deltaX)  // 最小宽度 400
  const newHeight = Math.max(300, resizeStartHeight + deltaY)  // 最小高度 300
  
  terminalPanelSize.value.width = newWidth
  terminalPanelSize.value.height = newHeight
}

function stopResizeTerminal() {
  isResizing = false
  document.removeEventListener('mousemove', onResizeTerminal)
  document.removeEventListener('mouseup', stopResizeTerminal)
}

function switchTerminal(terminalId) {
  console.log(`[independent-terminal] Switching to terminal ${terminalId}`)
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
  
  const message = {
    type: 'terminal_session_input',
    payload: {
      terminal_id: terminalId,
      data,
    },
  }
  socket.value.send(JSON.stringify(message))
}

function sendTerminalResize(terminalId, rows, cols) {
  if (!socket.value) {
    console.warn('[independent-terminal] No socket connection')
    return
  }
  
  const message = {
    type: 'terminal_session_resize',
    payload: {
      terminal_id: terminalId,
      rows,
      cols,
    },
  }
  socket.value.send(JSON.stringify(message))
}

// 全局键盘事件处理
function handleGlobalKeydown(event) {
  // Ctrl + A 打开/隐藏 Agent 侧边栏
  if (event.ctrlKey && event.key === 'a') {
    event.preventDefault()
    
    // 如果在输入框中，不触发快捷键
    const tagName = event.target.tagName.toLowerCase()
    if (tagName === 'textarea' || tagName === 'input') {
      return
    }
    
    // 切换 Agent 侧边栏显示状态
    showAgentSidebar.value = !showAgentSidebar.value
    console.log('[app] Toggle agent sidebar:', showAgentSidebar.value)
  }
  
  // Ctrl + ` 打开/隐藏终端面板
  if (event.ctrlKey && event.key === '`') {
    event.preventDefault()
    
    // 如果在输入框中，不触发快捷键
    const tagName = event.target.tagName.toLowerCase()
    if (tagName === 'textarea' || tagName === 'input') {
      return
    }
    
    // 切换终端面板显示状态
    if (socket.value) {
      showTerminalPanel.value = !showTerminalPanel.value
      console.log('[app] Toggle terminal panel:', showTerminalPanel.value)
    }
  }
  
  // ESC 键关闭所有对话框
  if (event.key === 'Escape') {
    // 如果对话框打开，关闭对话框
    if (showSettingsModal.value) {
      showSettingsModal.value = false
      console.log('[app] Close settings modal')
    } else if (showCreateAgentModal.value) {
      showCreateAgentModal.value = false
      console.log('[app] Close create agent modal')
    } else if (showSessionDialog.value) {
      cancelSessionDialog()
      console.log('[app] Close session dialog')
    } else if (showDirDialog.value) {
      cancelDirDialog()
      console.log('[app] Close dir dialog')
    }
    
    // ESC 键也关闭移动端菜单
    if (showMobileMenu.value) {
      showMobileMenu.value = false
      console.log('[app] Close mobile menu')
    }
    
    // ESC 键也关闭Agent侧边栏和终端面板（移动端）
    if (showAgentSidebar.value && windowWidth.value <= 768) {
      showAgentSidebar.value = false
      console.log('[app] Close agent sidebar (mobile)')
    }
    if (showTerminalPanel.value && windowWidth.value <= 768) {
      showTerminalPanel.value = false
      console.log('[app] Close terminal panel (mobile)')
    }
  }
}

// 移动端历史管理变量
let historyStateCount = 0

// 监听页面刷新/跳转，如果连接到gateway则提示用户
const handleBeforeUnload = (e) => {
  if (socket.value) {
    // 有socket连接，提示用户
    e.preventDefault()
    e.returnValue = '' // Chrome需要returnValue
    console.log('[app] Preventing page unload, socket is connected')
  }
}

// 移动端：打开浮层时推送历史状态
const pushOverlayState = () => {
  if (windowWidth.value <= 768) {
    history.pushState({ overlay: true }, '', '')
    historyStateCount++
    console.log('[app] Push history state, count:', historyStateCount)
  }
}

// 打开/关闭Agent侧边栏（移动端处理history）
const toggleAgentSidebar = () => {
  const newState = !showAgentSidebar.value
  showAgentSidebar.value = newState
  if (newState && windowWidth.value <= 768) {
    pushOverlayState()
  }
}

// 打开/关闭终端面板（移动端处理history）
const toggleTerminalPanel = () => {
  const newState = !showTerminalPanel.value
  showTerminalPanel.value = newState
  if (newState && windowWidth.value <= 768) {
    pushOverlayState()
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
  
  // 添加全局键盘事件监听
  document.addEventListener('keydown', handleGlobalKeydown)
  console.log('[app] Global keyboard listener added')
  
  // 监听窗口resize事件
  const handleResize = () => {
    windowWidth.value = window.innerWidth
  }
  window.addEventListener('resize', handleResize)
  console.log('[app] Resize listener added')
  
  // 添加beforeunload监听
  window.addEventListener('beforeunload', handleBeforeUnload)
  console.log('[app] Beforeunload listener added')
  
  // 移动端：监听返回键（popstate事件）
  const handlePopState = () => {
    console.log('[app] Back button pressed, historyStateCount:', historyStateCount)
    
    if (historyStateCount > 0) {
      // 有推送的历史状态，只是关闭浮层，不做真正的后退
      historyStateCount--
      
      // 关闭所有打开的浮层
      if (showSettingsModal.value) {
        showSettingsModal.value = false
        console.log('[app] Close settings modal via back button')
      } else if (showCreateAgentModal.value) {
        showCreateAgentModal.value = false
        console.log('[app] Close create agent modal via back button')
      } else if (showSessionDialog.value) {
        cancelSessionDialog()
        console.log('[app] Close session dialog via back button')
      } else if (showDirDialog.value) {
        cancelDirDialog()
        console.log('[app] Close dir dialog via back button')
      } else if (showAgentSidebar.value && windowWidth.value <= 768) {
        showAgentSidebar.value = false
        console.log('[app] Close agent sidebar via back button')
      } else if (showTerminalPanel.value && windowWidth.value <= 768) {
        showTerminalPanel.value = false
        console.log('[app] Close terminal panel via back button')
      } else if (showMobileMenu.value) {
        showMobileMenu.value = false
        console.log('[app] Close mobile menu via back button')
      } else {
        console.log('[app] No overlay to close')
      }
    } else {
      // 没有推送的历史状态，允许默认后退行为
      console.log('[app] No pushed history, allow default back')
    }
  }
  window.addEventListener('popstate', handlePopState)
  console.log('[app] Popstate listener added')
})

onUnmounted(() => {
  // 移除全局键盘事件监听
  document.removeEventListener('keydown', handleGlobalKeydown)
  console.log('[app] Global keyboard listener removed')
  
  // 移除窗口resize监听
  window.removeEventListener('resize', handleResize)
  console.log('[app] Resize listener removed')
  
  // 移除beforeunload监听
  window.removeEventListener('beforeunload', handleBeforeUnload)
  console.log('[app] Beforeunload listener removed')
  
  // 移除返回键监听
  window.removeEventListener('popstate', handlePopState)
  console.log('[app] Popstate listener removed')
})
</script>

<style>
/* 全局样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body {
  width: 100vw;
  height: 100vh;
  margin: 0;
  padding: 0;
  overflow: hidden;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

#app {
  width: 100vw;
  height: 100vh;
  margin: 0;
  padding: 0;
}

/* 全局滚动条样式 - 适用于所有可滚动元素 */
*::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

*::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.1);
  border-radius: 3px;
}

*::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}

*::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25);
}

*::-webkit-scrollbar-thumb:active {
  background: rgba(255, 255, 255, 0.3);
}

*::-webkit-scrollbar-corner {
  background: transparent;
}

/* html 和 body 不显示滚动条（使用应用内部滚动） */
html::-webkit-scrollbar,
body::-webkit-scrollbar {
  display: none;
}
</style>

<style scoped>
/* 动画定义 */

/* 全局布局 */
.app {
  display: flex;
  flex-direction: row; /* 改为左右布局 */
  height: 100vh;
  width: 100vw;
  margin: 0;
  padding: 0;
  background: #0d1117;
  color: #e6edf3;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Noto Sans', Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  overflow: hidden;
}

/* 主内容区 */
.main-content-wrapper {
  display: flex;
  flex-direction: column;
  flex: 1; /* 占据剩余宽度 */
  overflow: hidden;
  min-width: 0; /* 防止 flex 子元素溢出 */
}

/* 顶部栏 */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  background: rgba(22, 27, 34, 0.85);
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.mobile-header-actions {
  display: none;
  gap: 8px;
}

/* 桌面端显示，移动端隐藏 */
.desktop-only {
  display: flex;
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

/* 当前 Agent 信息 */
.current-agent-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 16px;
  background: rgba(35, 134, 54, 0.15);
  border: 1px solid rgba(56, 139, 253, 0.2);
  border-radius: 6px;
  font-size: 13px;
}

.current-agent-info .agent-type {
  font-weight: 600;
}

.current-agent-info .agent-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.1);
}

.current-agent-info .agent-status.running {
  background: rgba(56, 139, 253, 0.2);
  color: #58a6ff;
}

.current-agent-info .agent-status.stopped {
  background: rgba(63, 185, 80, 0.2);
  color: #3fb950;
}

.current-agent-info .agent-status.waiting_multi {
  background: rgba(210, 153, 34, 0.2);
  color: #d29922;
}

.current-agent-info .agent-status.waiting_single {
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
}

.current-agent-info .agent-port {
  color: #8b949e;
}

.current-agent-info .agent-dir {
  color: #8b949e;
  font-size: 12px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.icon-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  font-size: 18px;
  cursor: pointer;
  padding: 6px 10px;
  color: #8b949e;
}

.icon-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
  transform: translateY(-1px);
}

.icon-btn:active:not(:disabled) {
  transform: translateY(0);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.manual-interrupt-btn {
  background: #f0883e;
  border: 0.5px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.manual-interrupt-btn:hover:not(:disabled) {
  background: #f0883e;
  transform: translateY(-1px);
}

.manual-interrupt-btn:active:not(:disabled) {
  transform: translateY(0);
}

.manual-interrupt-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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
}

.dot.offline {
  background: #f85149;
  color: #f85149;
}

.dot.connecting {
  background: #d29922;
  color: #d29922;
}

.dot.online {
  background: #3fb950;
  color: #3fb950;
}

/* Agent 浮动窗口 */
.agent-sidebar {
  width: 320px;
  background: rgba(22, 27, 34, 0.95);
  border-right: 0.5px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0; /* 防止被压缩 */
}

.agent-sidebar.collapsed {
  width: 0;
  border-right: none;
  overflow: hidden;
}

.agent-sidebar-header {
  padding: 16px;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.08);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255, 255, 255, 0.02);
}

.sidebar-header-actions {
  display: flex;
  gap: 8px;
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
  position: relative;
}

.agent-item:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.12);
}

.agent-item.active {
  background: rgba(56, 139, 253, 0.15);
  border-color: rgba(56, 139, 253, 0.4);
}

.agent-item .agent-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.1);
  margin-left: 8px;
}

.agent-item .agent-status.running {
  background: rgba(56, 139, 253, 0.2);
  color: #58a6ff;
}

.agent-item .agent-status.stopped {
  background: rgba(63, 185, 80, 0.2);
  color: #3fb950;
}

.agent-item .agent-status.waiting_multi {
  background: rgba(210, 153, 34, 0.2);
  color: #d29922;
}

.agent-item .agent-status.waiting_single {
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
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

.agent-actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  justify-content: flex-end;
}

.icon-btn-small {
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  padding: 4px 8px;
  color: #8b949e;
  transition: all 0.2s ease;
}

.icon-btn-small:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
  transform: translateY(-1px);
}

.icon-btn-small:active {
  transform: translateY(0);
}

.agent-actions .icon-btn-small.stop-btn:hover {
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
  border-color: rgba(248, 81, 73, 0.3);
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
  background: #3fb950;
  color: white;
}

.create-agent-modal .btn.primary:hover {
  transform: translateY(-1px);
}

.create-agent-modal .btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none !important;
}

/* 单选框组样式 */
.create-agent-modal .radio-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.create-agent-modal .radio-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  background: rgba(13, 17, 23, 0.6);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  cursor: pointer;
}

.create-agent-modal .radio-label:hover {
  background: rgba(13, 17, 23, 0.8);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.create-agent-modal .radio-label:has(input:checked) {
  background: rgba(56, 139, 253, 0.12);
  border-color: rgba(56, 139, 253, 0.4);
}

.create-agent-modal .radio-label input[type="radio"] {
  appearance: none;
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  background: rgba(13, 17, 23, 0.8);
  cursor: pointer;
  position: relative;
}

.create-agent-modal .radio-label input[type="radio"]:hover {
  border-color: rgba(255, 255, 255, 0.5);
}

.create-agent-modal .radio-label input[type="radio"]:checked {
  border-color: #58a6ff;
  background: rgba(56, 139, 253, 0.1);
}

.create-agent-modal .radio-label input[type="radio"]:checked::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 8px;
  height: 8px;
  background: #58a6ff;
  border-radius: 50%;
}

.create-agent-modal .radio-text {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

.create-agent-modal .radio-desc {
  font-size: 12px;
  color: #8b949e;
  line-height: 1.4;
}

/* Session 恢复弹窗 */
.session-modal {
  max-width: 450px;
  width: 90%;
}

.session-modal h2 {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: #e6edf3;
}

.session-modal .modal-description {
  margin-bottom: 16px;
  font-size: 13px;
  color: #8b949e;
  line-height: 1.5;
}

.session-list {
  max-height: 300px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 20px;
}

.session-list::-webkit-scrollbar {
  width: 6px;
}

.session-list::-webkit-scrollbar-track {
  background: transparent;
}

.session-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}

.session-list::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25);
}

.session-item {
  padding: 12px 14px;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
  border-radius: 6px;
  margin: 4px;
}

.session-item:last-child {
  border-bottom: none;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.session-item.selected {
  background: rgba(63, 185, 80, 0.15);
  border-color: rgba(63, 185, 80, 0.3);
}

.session-item.selected:hover {
  background: rgba(63, 185, 80, 0.2);
}

.session-name {
  font-size: 14px;
  color: #e6edf3;
  font-weight: 500;
  margin-bottom: 4px;
}

.session-path {
  font-size: 11px;
  color: #8b949e;
  word-break: break-all;
  line-height: 1.4;
}

.session-date {
  font-size: 11px;
  color: #6e7681;
  margin-top: 6px;
}

.session-empty {
  padding: 40px 20px;
  text-align: center;
  color: #8b949e;
  font-size: 13px;
}

/* 目录选择对话框 */
.dir-modal {
  max-width: 700px;
  width: 95%;
  min-height: 500px;
}

.path-header {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.path-btn {
  flex: 1;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.path-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.current-path {
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  color: #e6edf3;
  margin-bottom: 16px;
  word-break: break-all;
  line-height: 1.4;
}

.dir-search {
  margin-bottom: 16px;
}

.dir-search-input {
  width: 100%;
  padding: 12px 16px;
  background: rgba(13, 17, 23, 0.8);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
}

.dir-search-input:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
}

.dir-search-input::placeholder {
  color: #8b949e;
}

.dir-list {
  max-height: 350px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 20px;
}

.dir-list::-webkit-scrollbar {
  width: 6px;
}

.dir-list::-webkit-scrollbar-track {
  background: transparent;
}

.dir-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}

.dir-list::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25);
}

.dir-item {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  cursor: pointer;
  border-radius: 6px;
  margin: 4px;
}

.dir-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.dir-item.selected {
  background: rgba(63, 185, 80, 0.15);
  border-color: rgba(63, 185, 80, 0.3);
}

.dir-item.selected:hover {
  background: rgba(63, 185, 80, 0.2);
}

.dir-icon {
  font-size: 18px;
  margin-right: 12px;
}

.dir-name {
  font-size: 14px;
  color: #e6edf3;
  font-weight: 500;
}

.dir-path {
  font-size: 11px;
  color: #8b949e;
  word-break: break-all;
  line-height: 1.4;
}

/* 输入框带按钮 */
.input-with-button {
  display: flex;
  gap: 10px;
}

.input-with-button .form-control {
  flex: 1;
}

.select-dir-btn {
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
}

.select-dir-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

/* 聊天容器 */
.chat-container {
  flex: 1;
  width: 100%;
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
  border-radius: 12px;
  padding: 14px 16px;
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message:hover {
  border-color: rgba(255, 255, 255, 0.12);
}

/* 用户输入消息 - 右对齐样式（必须放在 .message 之后以覆盖） */
.message.message-user_input {
  background: #1f6feb !important;
  border: 0.5px solid rgba(255, 255, 255, 0.2) !important;
  align-self: flex-end;
  max-width: 75%;
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
  position: relative;
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
  padding: 14px;
  border-radius: 8px;
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  overflow-x: auto;
  margin: 10px 0;
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
  background: rgba(13, 17, 23, 0.6);
}

.terminal-host {
  background: #0a0d12;
  flex: 1;
  min-height: 400px;
  overflow: hidden;
}

.terminal-history {
  margin-top: 14px;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  overflow: hidden;
  max-height: 600px;
  display: flex;
  flex-direction: column;
  background: rgba(13, 17, 23, 0.6);
}

.terminal-history-header {
  padding: 10px 16px;
  background: rgba(22, 27, 34, 0.9);
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.1);
  color: #8b949e;
  font-size: 13px;
  font-weight: 500;
}

.terminal-history-content {
  background: #0a0d12;
  padding: 16px;
  margin: 0;
  overflow: auto;
  color: #c9d1d9;
  /* 字体由动态样式控制 */
  white-space: pre-wrap;
  word-break: break-all;
}

/* 确认对话框 */
.message-confirm {
  background: rgba(33, 38, 45, 0.85);
  border: 0.5px solid rgba(88, 166, 255, 0.3);
}

.confirm-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.confirm-message {
  margin: 0;
  color: #e6edf3;
  font-size: 13px;
}

.confirm-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.confirm-btn {
  padding: 9px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  background: rgba(33, 38, 45, 0.8);
  color: #e6edf3;
}

.confirm-btn:hover {
  background: rgba(48, 54, 61, 0.9);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.confirm-btn.confirm {
  background: #238636;
  border-color: rgba(255, 255, 255, 0.2);
}

.confirm-btn.confirm:hover {
  background: #2ea043;
  border-color: rgba(255, 255, 255, 0.25);
}

/* 输入区 */
.input-area {
  background: rgba(22, 27, 34, 0.9);
  border-top: 0.5px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  width: 100%;
  box-sizing: border-box;
}

/* 单行输入模式（已废弃，统一使用多行） */
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
}

.input-wrapper.single-line input:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
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
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  padding: 11px 22px;
  cursor: pointer;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  background: #2ea043;
  transform: translateY(-1px);
}

.send-btn:active:not(:disabled) {
  transform: translateY(0);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.complete-btn {
  background: #0969da;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  padding: 11px 22px;
  cursor: pointer;
  white-space: nowrap;
}

.complete-btn:hover:not(:disabled) {
  background: #1f6feb;
  transform: translateY(-1px);
}

.complete-btn:active:not(:disabled) {
  transform: translateY(0);
}

.complete-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 输入框统一样式 */
.input-wrapper textarea {
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
}

.input-wrapper textarea:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
}

/* 缓冲区指示器 */
/* Agent 运行中进度指示器 */
.agent-thinking-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
  margin: 8px 0;
  animation: fadeIn 0.3s ease-in-out;
}

.thinking-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(59, 130, 246, 0.3);
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.thinking-text {
  font-size: 14px;
  color: #3b82f6;
  font-weight: 500;
}

/* 旋转动画 */
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 淡入动画 */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-5px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.buffer-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(35, 134, 54, 0.15);
  border: 1px solid rgba(35, 134, 54, 0.4);
  border-radius: 8px;
  margin: 8px 0;
  cursor: pointer;
}

.buffer-indicator:hover {
  background: rgba(35, 134, 54, 0.25);
  border-color: rgba(35, 134, 54, 0.6);
  transform: translateY(-1px);
}

.buffer-icon {
  font-size: 18px;
}

.buffer-text {
  font-size: 13px;
  color: #3fb950;
  font-weight: 500;
}

/* 操作按钮 */
.action-btn {
  padding: 11px 20px;
  background: rgba(48, 54, 61, 0.8);
  border: 1px solid #30363d;
  border-radius: 8px;
  color: #8b949e;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.action-btn:hover {
  background: rgba(56, 139, 253, 0.15);
  border-color: #58a6ff;
  color: #58a6ff;
  transform: translateY(-1px);
}

.action-btn:active {
  transform: translateY(0);
}

.clear-buffer-btn:hover {
  background: rgba(248, 81, 73, 0.15);
  border-color: #f85149;
  color: #f85149;
}

/* 输入操作按钮组 */
.input-wrapper .input-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
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
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal {
  background: rgba(22, 27, 34, 0.95);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  padding: 28px;
  width: 100%;
  max-width: 420px;
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
}

.form-group input:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
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
  background: #238636;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 9px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.primary-btn:hover:not(:disabled) {
  background: #2ea043;
  transform: translateY(-1px);
}

.primary-btn:active:not(:disabled) {
  transform: translateY(0);
}

.primary-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.danger-btn {
  padding: 10px 20px;
  background: #f85149;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 9px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
}

.danger-btn:hover:not(:disabled) {
  background: #ff6b6b;
  transform: translateY(-1px);
}

.danger-btn:active:not(:disabled) {
  transform: translateY(0);
}

.danger-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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
}

.ghost-btn:hover {
  background: rgba(48, 54, 61, 0.7);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
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
    background: #0d1117;
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

/* 补全按钮 */
.completion-btn {
  min-width: 44px;
  background: rgba(88, 166, 255, 0.1);
  border-color: rgba(88, 166, 255, 0.3);
  color: #58a6ff;
}

.completion-btn:hover:not(:disabled) {
  background: rgba(88, 166, 255, 0.2);
  border-color: #58a6ff;
}

.completion-btn:disabled {
  opacity: 0.3;
}

/* 补全列表弹窗 */
.completions-modal {
  max-width: 520px;
  max-height: 600px;
  display: flex;
  flex-direction: column;
}

.completions-modal .modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #e6edf3;
}

.completions-search {
  margin-bottom: 16px;
}

.completions-search input {
  width: 100%;
  padding: 12px 16px;
  background: rgba(13, 17, 23, 0.8);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
}

.completions-search input:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
}

.completions-list {
  flex: 1;
  overflow-y: auto;
  max-height: 400px;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  background: rgba(13, 17, 23, 0.6);
}

.completion-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
}

.completion-item:last-child {
  border-bottom: none;
}

.completion-item:hover {
  background: rgba(88, 166, 255, 0.1);
}

.completion-item.selected {
  background: rgba(88, 166, 255, 0.25);
}

.completion-value {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
}

.completion-desc {
  font-size: 12px;
  color: #8b949e;
}

.completion-item.completion-replace .completion-desc {
  color: #58a6ff;
}

.completion-item.completion-command .completion-desc {
  color: #d29922;
}

.completion-item.completion-rule .completion-desc {
  color: #3fb950;
}

.completion-empty {
  padding: 24px;
  text-align: center;
  color: #8b949e;
  font-size: 14px;
}

.error-message {
  background-color: #f85149;
  color: white;
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
  text-align: center;
}

/* 终端面板 */
.terminal-panel {
  position: fixed;
  top: 60px;
  right: 20px;
  width: 800px;
  height: 500px;
  background: rgba(13, 17, 23, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  z-index: 1000;
}

.terminal-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: rgba(22, 27, 34, 0.95);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px 8px 0 0;
}

.terminal-panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

.terminal-panel-actions {
  display: flex;
  gap: 8px;
}

.terminal-tabs {
  display: flex;
  gap: 2px;
  padding: 4px;
  background: rgba(0, 0, 0, 0.3);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.terminal-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(48, 54, 61, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  font-size: 12px;
  color: #8b949e;
  cursor: pointer;
}

.terminal-tab:hover {
  background: rgba(56, 139, 253, 0.1);
  color: #58a6ff;
}

.terminal-tab.active {
  background: rgba(56, 139, 253, 0.2);
  color: #58a6ff;
  border-color: rgba(56, 139, 253, 0.3);
}

.terminal-tab-title {
  font-weight: 500;
}

.terminal-tab-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
  border-radius: 3px;
  cursor: pointer;
}

.terminal-tab-close:hover {
  background: rgba(248, 81, 73, 0.4);
}

.terminal-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.copy-message-btn {
  position: absolute;
  top: 0;
  right: 0;
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 4px 8px;
  color: #8b949e;
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
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
}

/* Toast 提示 */
.toast {
  position: fixed;
  top: 80px;
  right: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: rgba(22, 27, 34, 0.95);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: #e6edf3;
  font-size: 14px;
  z-index: 9999;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(10px);
}

.toast-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  font-weight: bold;
  border-radius: 50%;
}

.toast-success .toast-icon {
  background: rgba(63, 185, 80, 0.2);
  color: #3fb950;
}

.toast-error .toast-icon {
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
}

.toast-info .toast-icon {
  background: rgba(88, 166, 255, 0.2);
  color: #58a6ff;
}

.toast-message {
  white-space: nowrap;
}

/* Toast 过渡动画 */
.toast-fade-enter-active,
.toast-fade-leave-active {
  transition: all 0.3s ease;
}

.toast-fade-enter-from {
  opacity: 0;
  transform: translateX(20px);
}

.toast-fade-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.terminal-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #8b949e;
  font-size: 14px;
}

.terminal-host-wrapper {
  flex: 1;
  overflow: hidden;
}

.terminal-host {
  width: 100%;
  height: 100%;
}

/* 终端调整大小手柄 */
.terminal-resize-handle {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 20px;
  height: 20px;
  cursor: nesw-resize;
  border-radius: 0 0 0 8px;
  z-index: 10;
}

.terminal-resize-handle:hover {
}

/* ==================== 响应式适配（方案一：渐进式） ==================== */

/* 平板端适配 (768px - 1024px) */
@media (min-width: 769px) and (max-width: 1024px) {
  /* 侧边栏宽度调整 */
  .agent-sidebar {
    width: 280px;
  }
  
  /* 顶部栏优化 */
  .app-header {
    padding: 12px 18px;
  }
  
  .header-title h1 {
    font-size: 16px;
  }
  
  /* 按钮优化 */
  .icon-btn {
    padding: 8px 12px;
    font-size: 17px;
  }
  
  /* 消息区域 */
  .messages {
    padding: 18px;
  }
}

/* 移动端适配 (< 768px) */
@media (max-width: 768px) {
  .desktop-only {
    display: none !important;
  }
  
  .mobile-header-actions {
    display: flex !important;
  }
  
  .mobile-header-actions .icon-btn {
    padding: 12px !important;
    min-width: 44px !important;
    min-height: 44px !important;
  }
  
  .header-actions {
    display: none !important;
  }
  
  /* ========== 终端面板优化 ========== */
  .terminal-panel {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    width: 100% !important;
    height: 100% !important;
    border-radius: 0 !important;
    z-index: 2000 !important;
  }
  
  .terminal-resize-handle {
    display: none !important;
  }
  
  /* ========== 侧边栏优化 ========== */
  .agent-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 999;
    background: rgba(22, 27, 34, 0.98);
  }
  
  .agent-sidebar.collapsed {
    width: 0;
  }
  
  .agent-sidebar-header {
    padding: 12px 16px;
  }
  
  .agent-sidebar-header h3 {
    font-size: 13px;
  }
  
  .agent-list {
    padding: 8px 12px;
  }
  
  .agent-item {
    padding: 10px;
  }
  
  /* ========== 顶部栏优化 ========== */
  .app-header {
    padding: 10px 14px;
  }
  
  .header-title h1 {
    font-size: 15px;
  }
  
  /* 隐藏非必要信息 */
  .current-agent-info .agent-dir {
    display: none;
  }
  
  .current-agent-info .agent-port {
    display: none;
  }
  
  /* ========== 按钮优化 ========== */
  .icon-btn {
    padding: 12px;
    min-width: 44px;
    min-height: 44px;
    font-size: 18px;
  }
  
  .manual-interrupt-btn {
    padding: 10px 14px;
    min-height: 44px;
    font-size: 13px;
  }
  
  /* ========== 消息区域优化 ========== */
  .messages {
    padding: 12px 10px;
  }
  
  .message {
    padding: 10px 12px;
    border-radius: 10px;
  }
  
  .message-content {
    gap: 6px;
  }
  
  .message-content .message-body {
    font-size: 13px;
  }
  
  .message-content .message-meta-left {
    gap: 6px 8px;
    flex-wrap: wrap;
  }
  
  .message-meta-left .badge {
    font-size: 9px;
    padding: 2px 6px;
  }
  
  .message-meta-left .agent-name {
    font-size: 9px;
  }
  
  .message-meta-left .timestamp {
    font-size: 9px;
  }
  
  /* 用户输入消息优化 */
  .message.message-user_input {
    max-width: 85%;
  }
  
  .message.message-user_input .message-meta-left {
    min-width: auto;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  
  /* ========== 输入区优化 ========== */
  .input-wrapper {
    padding: 12px;
  }
  
  .input-wrapper textarea {
    min-height: 100px;
    padding: 12px;
    font-size: 14px;
  }
  
  .input-wrapper .input-hint {
    font-size: 12px;
  }
  
  /* 操作按钮优化 */
  .send-btn,
  .complete-btn,
  .action-btn {
    padding: 10px 16px;
    min-height: 44px;
    font-size: 13px;
  }
  
  /* ========== 模态框优化 ========== */
  .modal {
    padding: 20px;
    max-width: 95%;
    border-radius: 12px;
  }
  
  .modal-header h2,
  .connect-modal h2,
  .settings-modal h2 {
    font-size: 18px;
  }
  
  .form-group label {
    font-size: 12px;
  }
  
  /* ========== 字体优化 ========== */
  body {
    font-size: 14px;
  }
  
  /* ========== 终端优化 ========== */
  .terminal-wrapper {
    margin-top: 12px;
    max-height: 400px;
  }
  
  .terminal-host {
    min-height: 300px;
  }
  
  /* ========== Diff 优化 ========== */
  .diff-header {
    padding: 6px 10px;
  }
  
  .diff-file-path {
    font-size: 13px;
  }
  
  .diff-content {
    font-size: 11px;
    padding: 2px 4px;
  }
  
  .diff-line-num {
    width: 40px;
    font-size: 10px;
  }
}
</style>
