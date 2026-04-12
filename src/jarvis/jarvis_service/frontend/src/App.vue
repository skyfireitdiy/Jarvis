<template>
  <div class="app">
    <!-- Agent 侧边栏 -->
    <aside
      class="agent-sidebar"
      :class="{ collapsed: !showAgentSidebar, 'agent-sidebar-resizing': agentSidebarResizeState.active }"
      :style="agentSidebarStyle"
    >
      <div class="agent-sidebar-header">
        <h3>Agent 列表</h3>
        <div class="sidebar-header-actions">
          <button class="icon-btn" :class="{ active: isBatchMode }" @click="toggleBatchMode" title="批量选择模式">☑</button>
          <button class="icon-btn" @click="openCreateAgentModal" title="创建新 Agent">➕</button>
          <button class="icon-btn" @click="showAgentSidebar = false" title="关闭侧边栏">✕</button>
        </div>
      </div>
      <div class="agent-list">
        <div v-for="agent in agentList" :key="agent.agent_id" 
             class="agent-item" 
             :class="{ active: currentAgentId === agent.agent_id, selected: isAgentSelected(agent.agent_id) }"
             @click="handleAgentItemClick(agent, $event)">
          <div v-if="isBatchMode" class="agent-checkbox" @click.stop>
            <input type="checkbox" :checked="isAgentSelected(agent.agent_id)" @change="toggleSelectAgent(agent.agent_id)">
          </div>
          <div class="agent-info">
            <span class="agent-type">{{ agent.name || (agent.agent_type === 'agent' ? '🤖' : '💻') }}</span>
            <span class="agent-status-dot" :class="getStatusClass(agent)" :title="getStatusText(agent)"></span>
            <span class="agent-node" v-if="getAgentNodeLabel(agent)" :title="`节点: ${getAgentNodeLabel(agent)}`">🧭 {{ getAgentNodeLabel(agent) }}</span>
            <span class="agent-llm-group" v-if="agent.llm_group">🔹 {{ agent.llm_group }}</span>
            <span class="agent-worktree" v-if="agent.worktree" title="已启用 worktree">🌿</span>
            <span class="agent-quick-mode" v-if="agent.quick_mode" title="极速模式">⚡</span>
          </div>
          <div class="agent-dir">{{ agent.working_dir || '未提供工作目录' }}</div>
          <div class="agent-actions">
            <button class="icon-btn-small" @click.stop="renameAgent(agent)" title="重命名">✏️</button>
            <button class="icon-btn-small" @click.stop="copyAgent(agent)" title="复制 Agent">📋</button>
            <button class="icon-btn-small stop-btn" @click.stop="deleteAgent(agent.agent_id)" title="删除 Agent">🗑</button>
          </div>
        </div>
        <!-- 批量操作按钮栏 -->
        <div v-if="isBatchMode && agentList.length > 0" class="batch-actions-bar">
          <div class="batch-actions-info">
            已选 {{ selectedAgents.size }} 个
          </div>
          <div class="batch-actions-buttons">
            <button class="icon-btn-small" @click="toggleSelectAll" :title="isAllSelected ? '取消全选' : '全选'">
              {{ isAllSelected ? '⬜' : '☑' }}
            </button>
            <button class="icon-btn-small" @click="batchCopyAgents" title="批量复制">
              📋
            </button>
            <button class="icon-btn-small stop-btn" @click="batchDeleteAgents" title="批量删除">
              🗑️
            </button>
            <button class="icon-btn-small" @click="toggleBatchMode" title="退出批量模式">
              ✕
            </button>
          </div>
        </div>
        <div v-if="agentList.length === 0" class="agent-empty">
          暂无 Agent，点击 + 创建
        </div>
      </div>
      <div
        v-if="showAgentSidebar && windowWidth > 768"
        class="agent-sidebar-resize-handle"
        @mousedown="startAgentSidebarResize"
      ></div>
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
          <button class="icon-btn" @click="showEditorPanel = !showEditorPanel" :disabled="!socket" title="编辑器">
            📝
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
          <span class="agent-status-dot" :class="getStatusClass(currentAgent)" :title="getStatusText(currentAgent)"></span>
          <span class="agent-node" v-if="getAgentNodeLabel(currentAgent)">🧭 {{ getAgentNodeLabel(currentAgent) }}</span>
          <span class="agent-dir">{{ currentAgent.working_dir }}</span>
        </div>
        
        <div class="header-actions desktop-only">
          <button class="icon-btn" @click="toggleTerminalPanel()" :disabled="!socket" title="终端面板">
            💻
          </button>
          <button class="icon-btn" @click="showEditorPanel = !showEditorPanel" :disabled="!socket" title="编辑器">
            📝
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
          <div v-if="item.output_type === 'execution' && item.is_finished && item.terminal_content" class="terminal-history" :style="getTerminalStyle(item.terminal_content)">
            <div class="terminal-history-header">Terminal Output ({{ item.execution_id }})</div>
            <pre class="terminal-history-content">{{ item.terminal_content }}</pre>
          </div>
        </article>
        <!-- 确认对话框 -->
        <article v-if="confirmDialog" class="message message-confirm">
          <div class="confirm-box">
            <p class="confirm-message">{{ confirmDialog.message }}</p>
            <div class="confirm-actions">
              <template v-if="confirmDialog.defaultConfirm">
                <button ref="confirmCancelBtn" class="confirm-btn" @click="confirmDialog.cancelCallback">取消</button>
                <button ref="confirmConfirmBtn" class="confirm-btn default" @click="confirmDialog.confirmCallback">确认</button>
              </template>
              <template v-else>
                <button ref="confirmCancelBtn" class="confirm-btn default" @click="confirmDialog.confirmCallback">确认</button>
                <button ref="confirmConfirmBtn" @click="confirmDialog.cancelCallback">取消</button>
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
      :class="{ 'terminal-panel-dragging': terminalPanelInteraction.active }"
      :style="terminalPanelStyle"
      @mousedown="focusWindow('terminal')"
    >
      <div class="terminal-panel-header" @mousedown="startTerminalPanelMove" @dblclick.stop="toggleTerminalMaximize">
        <h3>终端</h3>
        <div class="terminal-panel-actions">
          <button class="icon-btn" @click="createTerminal" :disabled="!socket" title="新建终端">➕</button>
          <button class="icon-btn maximize-btn" @click="toggleTerminalMaximize" :title="isTerminalMaximized ? '还原' : '最大化'">
            {{ isTerminalMaximized ? '🗗' : '🗖' }}
          </button>
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
      <div
        v-for="direction in terminalResizeDirections"
        :key="direction"
        :class="['terminal-resize-handle', `terminal-resize-${direction}`]"
        @mousedown="startTerminalPanelResize($event, direction)"
      ></div>
    </aside>

    <!-- 浮动编辑器面板 -->
    <aside
      v-show="showEditorPanel"
      class="editor-panel"
      :class="{ 'editor-panel-dragging': editorPanelInteraction.active }"
      :style="editorPanelStyle"
      @mousedown="focusWindow('editor')"
    >
      <div
        class="editor-panel-header"
        @mousedown="startEditorPanelMove"
        @dblclick.stop="toggleEditorMaximize"
      >
        <div class="editor-panel-title-group">
          <h3>编辑器</h3>
          <span v-if="activeEditorTab" class="editor-panel-subtitle">{{ activeEditorTab.path }}</span>
        </div>
        <div class="editor-panel-actions">
          <button class="icon-btn" @click.stop="saveActiveEditorTab" :disabled="!activeEditorTab || activeEditorTab.loading" title="保存文件">💾</button>
          <button class="icon-btn maximize-btn" @click="toggleEditorMaximize" :title="isEditorMaximized ? '还原' : '最大化'">
            {{ isEditorMaximized ? '🗗' : '🗖' }}
          </button>
          <button class="icon-btn" @click="closeEditorPanel" title="关闭编辑器">✕</button>
        </div>
      </div>
      <div class="editor-tabs" v-if="editorTabs.length > 0">
        <div
          v-for="tab in editorTabs"
          :key="tab.path"
          class="editor-tab"
          :class="{ active: activeEditorTabPath === tab.path }"
          @click="activateEditorTab(tab.path)"
        >
          <span class="editor-tab-name">{{ tab.name }}</span>
          <span v-if="tab.isDirty" class="editor-tab-dirty">●</span>
          <button class="editor-tab-close" @click.stop="closeEditorTab(tab.path)">✕</button>
        </div>
      </div>
      <div class="editor-panel-toolbar">
        <span class="editor-toolbar-status" v-if="activeEditorTab?.loading">加载中...</span>
        <span class="editor-toolbar-status error" v-else-if="activeEditorTab?.error">{{ activeEditorTab.error }}</span>
        <span class="editor-toolbar-status" v-else-if="activeEditorTab">{{ activeEditorTab.isDirty ? '未保存修改' : '已保存' }}</span>
        <span class="editor-toolbar-status" v-else>点击文件树中的文件打开编辑器</span>
        <div class="editor-toolbar-spacer"></div>
        <button
          v-if="editorTabs.length > 0"
          class="editor-edit-toggle"
          :class="{ 'editable': isEditorEditable }"
          @click="toggleEditorEditable"
          :title="isEditorEditable ? '切换到只读模式' : '切换到编辑模式'"
        >
          <span class="editor-edit-toggle-icon">{{ isEditorEditable ? '🔓' : '🔒' }}</span>
          <span class="editor-edit-toggle-text">{{ isEditorEditable ? '可编辑' : '只读' }}</span>
        </button>
      </div>
      <div class="editor-workspace">
        <div class="editor-activity-bar">
          <button
            class="editor-activity-button"
            :class="{ active: showEditorSidebar && editorSidebarView === 'files' }"
            @click="setEditorSidebarView('files')"
            title="目录树"
          >📁</button>
          <button
            class="editor-activity-button"
            :class="{ active: showEditorSidebar && editorSidebarView === 'search' }"
            @click="setEditorSidebarView('search')"
            title="全局搜索"
          >🔎</button>
        </div>
        <aside v-if="showEditorSidebar" class="editor-sidebar">
          <div class="editor-sidebar-header">
            <span class="editor-sidebar-title">{{ editorSidebarView === 'search' ? '全局搜索' : '目录树' }}</span>
            <button class="icon-btn-small" @click="closeEditorSidebar" title="关闭侧边栏">✕</button>
          </div>
          <div v-if="editorSidebarView === 'files'" class="editor-sidebar-content">
            <div v-if="currentAgent" class="editor-file-tree-panel">
              <div class="editor-file-tree-root" @click.stop="ensureEditorSidebarFileTree(currentAgent)">
                {{ currentAgent.working_dir }}
              </div>
              <div v-if="!hasEditorSidebarFileTree" class="editor-file-tree-empty">
                当前工作目录下暂无可显示内容
              </div>
              <div v-else class="editor-file-tree-list">
                <div
                  v-for="visibleNode in getVisibleFileTreeNodes(currentAgent.agent_id)"
                  :key="visibleNode.node.path"
                  class="tree-node editor-tree-node"
                >
                  <div
                    class="tree-node-content"
                    :style="{ paddingLeft: `${8 + visibleNode.depth * 20}px` }"
                    @click.stop="handleFileTreeNodeClick(currentAgent.agent_id, visibleNode.node)"
                  >
                    <span
                      v-if="visibleNode.node.type === 'directory'"
                      class="tree-node-icon expand-arrow"
                      :class="{ expanded: visibleNode.node.expanded }"
                    >▶</span>
                    <span v-else class="tree-node-icon"></span>
                    <span
                      class="tree-node-icon"
                      :class="visibleNode.node.type === 'directory' ? 'folder-icon' : 'file-icon'"
                    >{{ visibleNode.node.type === 'directory' ? '📁' : '📄' }}</span>
                    <span
                      class="tree-node-text"
                      :class="visibleNode.node.type === 'directory' ? 'directory' : 'file'"
                    >{{ visibleNode.node.name }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="editor-sidebar-content editor-sidebar-placeholder">
              <div class="editor-sidebar-placeholder-icon">📁</div>
              <div class="editor-sidebar-placeholder-text">请先选择一个 Agent 以查看工作目录树。</div>
            </div>
          </div>
          <div v-else class="editor-sidebar-content">
            <div class="editor-global-search-panel">
              <input
                v-model="globalSearchQuery"
                class="editor-global-search-input"
                type="text"
                placeholder="全局搜索文件内容..."
                :disabled="globalSearchLoading || !currentAgentId"
                @keydown.enter.prevent="runGlobalSearch"
              >
              <input
                v-model="globalSearchFileGlob"
                class="editor-global-search-input editor-global-search-glob-input"
                type="text"
                placeholder="文件过滤，如 *.py,!tests/**"
                :disabled="globalSearchLoading || !currentAgentId"
                @keydown.enter.prevent="runGlobalSearch"
              >
              <div class="editor-global-search-toolbar">
                <label class="editor-global-search-toggle">
                  <input v-model="globalSearchCaseSensitive" type="checkbox">
                  <span>区分大小写</span>
                </label>
                <label class="editor-global-search-toggle">
                  <input v-model="globalSearchWholeWord" type="checkbox">
                  <span>全词匹配</span>
                </label>
                <div class="editor-global-search-actions">
                  <button class="icon-btn editor-global-search-btn" @click="runGlobalSearch" :disabled="globalSearchLoading || !currentAgentId || !globalSearchQuery.trim()" title="全局搜索">🔍</button>
                  <button class="icon-btn editor-global-search-btn" @click="clearGlobalSearch" :disabled="globalSearchLoading" title="清空搜索">✕</button>
                </div>
              </div>
            </div>
            <div class="editor-global-search-results">
              <div class="editor-global-search-summary">
                <span v-if="globalSearchLoading">搜索中...</span>
                <span v-else-if="globalSearchError" class="error">{{ globalSearchError }}</span>
                <span v-else-if="globalSearchExecuted">找到 {{ globalSearchTotalMatches }} 处匹配，分布在 {{ globalSearchTotalFiles }} 个文件</span>
                <span v-else>输入关键词并回车，可在当前 Agent 工作目录中全局搜索</span>
              </div>
              <div v-if="!globalSearchLoading && globalSearchExecuted && globalSearchResults.length === 0 && !globalSearchError" class="editor-global-search-empty">
                未找到匹配结果
              </div>
              <div v-for="result in globalSearchResults" :key="result.file_path" class="editor-global-search-file-group">
                <div class="editor-global-search-file-path" @click="openEditorFile(resolveAgentRelativePath(result.file_path))">
                  {{ result.file_path }}
                  <span class="editor-global-search-file-count">({{ result.matches.length }})</span>
                </div>
                <button
                  v-for="match in result.matches"
                  :key="`${result.file_path}:${match.line_number}:${match.match_start}`"
                  class="editor-global-search-match"
                  @click="openGlobalSearchResult(result.file_path, match.line_number, match.match_start, match.match_end)"
                >
                  <span class="editor-global-search-line">{{ match.line_number }}</span>
                  <span class="editor-global-search-text">
                    {{ match.line_content.slice(0, match.match_start) }}<mark>{{ match.line_content.slice(match.match_start, match.match_end) }}</mark>{{ match.line_content.slice(match.match_end) }}
                  </span>
                </button>
              </div>
            </div>
          </div>
        </aside>
        <div class="editor-panel-content editor-panel-content-main">
          <div v-if="editorTabs.length === 0" class="editor-placeholder">
            <div class="editor-placeholder-icon">📝</div>
            <div class="editor-placeholder-title">点击文件树中的文件打开代码编辑器</div>
            <div class="editor-placeholder-text">支持 Monaco 语法高亮、代码折叠、多标签切换与保存。</div>
          </div>
          <div v-else ref="editorContainerRef" class="editor-monaco-container"></div>
        </div>
      </div>
      <div
        v-for="direction in editorResizeDirections"
        :key="direction"
        :class="['editor-resize-handle', `editor-resize-${direction}`]"
        @mousedown="startEditorPanelResize($event, direction)"
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
        
        <!-- 多行输入框 -->
        <textarea 
          v-if="inputMode === 'multi'"
          v-model="inputText" 
          :placeholder="isInputDisabled ? '没有激活的 Agent 或 Agent 未运行' : (inputTip || '输入内容 (Ctrl+Enter 发送)')"
          :disabled="isInputDisabled"
          @keydown="handleTextareaKeydown"
          ref="multilineInput"
        ></textarea>
        
        <!-- 单行输入框 -->
        <input 
          v-else
          v-model="inputText" 
          type="text"
          :placeholder="isInputDisabled ? '没有激活的 Agent 或 Agent 未运行' : (inputTip || '输入内容 (Enter 发送)')"
          :disabled="isInputDisabled"
          @keydown="handleSinglelineKeydown"
          ref="singlelineInput"
        />
        
        <!-- 缓冲区指示器 -->
        <div class="buffer-indicator" v-if="hasBufferedInput && (agentStatuses.get(currentAgentId)?.execution_status ?? 'running') !== 'waiting_multi'" @click="showBufferPanel = true">
          <span class="buffer-icon">📝</span>
          <span class="buffer-text">缓冲区有内容，点击管理</span>
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
            :disabled="isWaitingMultiDisabled"
            title="完成（发送空消息）"
          >
            完成
          </button>
          <button 
            class="action-btn completion-btn" 
            @click="openCompletions" 
            :disabled="isWaitingMultiDisabled"
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

    <!-- 缓存管理弹窗 -->
    <div class="modal-overlay" v-if="hasBufferedInput && showBufferPanel" @click.self="showBufferPanel = false">
      <div class="modal buffer-modal">
        <div class="buffer-panel-header">
          <span class="buffer-panel-title">📝 输入缓存</span>
          <div class="buffer-panel-actions">
            <button
              class="buffer-panel-btn"
              @click="loadBufferToInput"
              title="加载到输入框"
            >
              ↙ 加载
            </button>
            <button
              class="buffer-panel-btn"
              @click="clearBuffer"
              title="清空缓存"
            >
              🗑
            </button>
            <button
              class="buffer-panel-btn close-btn"
              @click="showBufferPanel = false"
              title="关闭面板"
            >
              ✕
            </button>
          </div>
        </div>
        <div class="buffer-panel-content">
          <textarea
            v-model="bufferEditText"
            class="buffer-edit-textarea"
            placeholder="缓存内容..."
            @keydown.ctrl.enter="saveBufferEdit"
          ></textarea>
          <div class="buffer-panel-footer">
            <button
              class="buffer-save-btn"
              @click="saveBufferEdit"
              :disabled="!bufferEditText.trim()"
            >
              保存修改 (Ctrl+Enter)
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 补全列表弹窗 -->
    <div class="modal-overlay" v-if="showCompletions">
      <div class="modal completions-modal">
        <div class="modal-header">
          <h3>插入补全</h3>
          <button class="icon-btn" @click="insertAtPosition('@', completionCursorPos.value); showCompletions = false; completionCursorPos.value = -1">✕</button>
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
        <div class="form-group" v-if="availableNodeOptions.length > 0">
          <label>目标节点</label>
          <select v-model="newAgentNodeId" class="form-control">
            <option value="">默认节点（当前网关决定）</option>
            <option v-for="node in availableNodeOptions" :key="node.node_id" :value="node.node_id">
              {{ formatNodeOptionLabel(node) }}
            </option>
          </select>
          <div class="form-help">未选择时使用默认节点；复制 Agent 时默认继承源节点。</div>
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
        <div v-if="newAgentType === 'codeagent'" class="form-group">
          <div class="toggle-wrapper">
            <label class="toggle-switch">
              <input v-model="newCodeAgentWorktree" type="checkbox" class="toggle-input" />
              <span class="toggle-slider"></span>
            </label>
            <div class="toggle-info">
              <span class="toggle-label-text">启用 worktree</span>
              <span class="form-help">为代码 Agent 使用独立 git worktree 进行隔离开发。</span>
            </div>
          </div>
        </div>
        <div class="form-group">
          <div class="toggle-wrapper">
            <label class="toggle-switch">
              <input v-model="newAgentQuickMode" type="checkbox" class="toggle-input" />
              <span class="toggle-slider"></span>
            </label>
            <div class="toggle-info">
              <span class="toggle-label-text">极速模式</span>
              <span class="form-help">跳过任务分类、规则加载、上下文推荐等，直接执行任务。</span>
            </div>
          </div>
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
          <input v-model="auth.password" type="password" placeholder="可选" @keydown.enter="connect" />
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
          <h2>设置</h2>
          <button class="close-btn" @click="showSettingsModal = false">×</button>
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="auth.password" type="password" placeholder="可选" @keydown.enter="connect" />
        </div>
        <div class="form-group">
          <label>网关地址</label>
          <input v-model="gatewayUrl" placeholder="127.0.0.1:8000 或 ws://example.com:8080/ws" />
        </div>
        <div class="form-group">
          <div class="toggle-wrapper">
            <label class="toggle-switch">
              <input type="checkbox" v-model="connectionLockEnabled" @change="saveConnectionLockSetting" class="toggle-input" />
              <span class="toggle-slider"></span>
            </label>
            <div class="toggle-info">
              <span class="toggle-label-text">锁定连接（拒绝新连接）</span>
              <span class="form-help">启用后，当已有活跃连接时，新连接将被拒绝。禁用后，新连接会替换旧连接。</span>
            </div>
          </div>
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
        <div class="form-group" v-if="availableNodeOptions.length > 0">
          <label>重启节点服务</label>
          <select v-model="restartNodeId" class="node-select">
            <option value="">本节点 (master)</option>
            <option v-for="node in availableNodeOptions" :key="node.node_id" :value="node.node_id">
              {{ formatNodeOptionLabel(node) }}
            </option>
          </select>
          <span class="form-help">选择要重启服务的节点，默认为本节点</span>
        </div>
        <div class="form-group" v-if="!restartNodeId || restartNodeId === 'master'">
          <label class="checkbox-label">
            <input type="checkbox" v-model="restartFrontendService" />
            <span>同时重启前端服务</span>
          </label>
          <span class="form-help">前端服务重启时间较长，通常只需重启后端</span>
        </div>
        <div class="form-group">
          <button class="ghost-btn" @click="confirmRestartGateway" :disabled="isRestartingGateway">
            {{ isRestartingGateway ? '请稍候...' : (restartNodeId ? `重启节点 ${restartNodeId} 服务` : '重启本节点服务') }}
          </button>
        </div>

        <!-- 配置同步 -->
        <div class="form-group" v-if="availableNodeOptions.length > 0">
          <label>配置同步</label>
          <div class="config-sync-section">
            <div class="config-sync-row">
              <span class="config-sync-label">源节点:</span>
              <select v-model="syncConfigSourceNode" class="node-select">
                <option value="">本节点 (master)</option>
                <option v-for="node in availableNodeOptions" :key="node.node_id" :value="node.node_id">
                  {{ formatNodeOptionLabel(node) }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <button class="ghost-btn" @click="syncConfig" :disabled="isSyncingConfig">
                {{ isSyncingConfig ? '同步中...' : '同步配置到其他节点' }}
              </button>
            </div>
          </div>
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
import * as monaco from 'monaco-editor'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import { Terminal } from 'xterm'
import { FitAddon } from '@xterm/addon-fit'
import 'xterm/css/xterm.css'
import plantumlEncoder from 'plantuml-encoder'
import historyStorage from './historyStorage.js'

const PLANTUML_SERVER_URL = 'https://www.plantuml.com/plantuml/svg/'
const PLANTUML_BLOCK_LANGUAGE = 'plantuml'

function encodePlantUmlText(plantUmlSource) {
  return plantumlEncoder.encode(String(plantUmlSource || '').trim())
}

function isPlantUmlLanguage(language) {
  return String(language || '').trim().toLowerCase() === PLANTUML_BLOCK_LANGUAGE
}

/**
 * 检查 PlantUML 代码是否完整（包含 @startuml 和 @enduml 标记）
 * @param {string} source - PlantUML 源码
 * @returns {boolean} - 返回 true 表示完整
 */
function isPlantUmlComplete(source) {
  const trimmedSource = String(source || '').trim()
  const lowerSource = trimmedSource.toLowerCase()
  return lowerSource.includes('@startuml') && lowerSource.includes('@enduml')
}

function renderPlantUmlBlock(plantUmlSource) {
  const trimmedSource = String(plantUmlSource || '').trim()
  if (!trimmedSource) {
    return '<pre><code class="language-plantuml"></code></pre>'
  }

  // 检查 PlantUML 代码是否完整，不完整时不请求远端渲染
  if (!isPlantUmlComplete(trimmedSource)) {
    return `<pre><code class="language-plantuml">${escapeHtml(trimmedSource)}</code></pre>`
  }

  try {
    const escapedSource = escapeHtml(trimmedSource)
    const encodedSource = encodePlantUmlText(trimmedSource)
    const plantUmlUrl = `${PLANTUML_SERVER_URL}${encodedSource}`

    return [
      '<div class="plantuml-block">',
      '  <div class="plantuml-notice">',
      '    当前前端使用 PlantUML 在线服务渲染，若图片加载失败可展开查看源码。',
      '  </div>',
      `  <a class="plantuml-link" href="${plantUmlUrl}" target="_blank" rel="noopener noreferrer">`,
      `    <img class="plantuml-image" src="${plantUmlUrl}" alt="PlantUML diagram" loading="lazy" />`,
      '  </a>',
      '  <details class="plantuml-source">',
      '    <summary>查看 PlantUML 源码</summary>',
      `    <pre><code class="language-plantuml">${escapedSource}</code></pre>`,
      '  </details>',
      '</div>'
    ].join('\n')
  } catch (error) {
    console.error('[PlantUML] Failed to render PlantUML block:', error)
    return `<pre><code class="language-plantuml">${escapeHtml(trimmedSource)}</code></pre>`
  }
}

const markedRenderer = new marked.Renderer()
const defaultCodeRenderer = markedRenderer.code.bind(markedRenderer)

markedRenderer.code = function(code, language, isEscaped) {
  if (isPlantUmlLanguage(language)) {
    return renderPlantUmlBlock(code)
  }
  return defaultCodeRenderer(code, language, isEscaped)
}

// 配置 marked 使用 highlight.js 进行语法高亮
marked.setOptions({
  renderer: markedRenderer,
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
  const fontSize = 12
  const lineHeight = 1.4
  const maxLines = 30
  const headerHeight = 41 // header的高度
  const contentPadding = 32 // content的padding
  
  const baseStyle = {
    fontFamily: "'Fira Code', 'Consolas', 'Monaco', 'Courier New', monospace",
    fontSize: `${fontSize}px`,
    lineHeight: lineHeight
  }
  
  const contentHeight = lineCount * fontSize * lineHeight
  const totalHeight = contentHeight + headerHeight + contentPadding
  
  if (lineCount <= maxLines) {
    // 行数少时，计算实际高度：内容高度 + header高度 + padding
    return { ...baseStyle, height: `${totalHeight}px` }
  } else {
    // 行数多时，使用最大高度
    const maxHeight = maxLines * fontSize * lineHeight + headerHeight + contentPadding
    return { ...baseStyle, height: `${maxHeight}px` }
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
const auth = ref({ 
  password: '',
  token: ''
})
const gatewayUrl = ref(localStorage.getItem('jarvis_gateway_url') || '127.0.0.1:8000')
const socket = ref(null) // Gateway 连接
const sockets = ref(new Map()) // 多 Agent 连接存储：agent_id -> WebSocket
const connecting = ref(false)
const connectErrorMessage = ref('')  // 连接错误信息
const connectionLockEnabled = ref(localStorage.getItem('connection_lock_enabled') === 'true')  // 连接锁定开关
const isRestartingGateway = ref(false)
const restartNodeId = ref('') // 重启服务时选择的节点ID
const restartFrontendService = ref(false) // 是否同时重启前端服务

// 配置同步相关状态
const syncConfigSourceNode = ref('') // 配置同步的源节点ID
const syncConfigTargetNodes = ref([]) // 配置同步的目标节点ID数组
const syncConfigSections = ref(['llms', 'llm_groups']) // 要同步的配置类型数组（llms, llm_groups）
const isSyncingConfig = ref(false) // 是否正在同步配置

// 登录函数：使用密码获取 Token
async function loginWithPassword(password) {
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    })
    
    const result = await response.json()
    if (!response.ok || !result.success || !result.data?.token) {
      throw new Error(result.error?.message || '登录失败')
    }
    
    // 保存 Token（仅在内存中保存，页面刷新后会失效，需要重新登录）
    auth.value.token = result.data.token
    
    // 登录成功后立即清除密码（安全最佳实践：密码只用一次，后续使用 Token）
    auth.value.password = ''
    
    console.log('[AUTH] Login successful, token saved, password cleared')
    return true
  } catch (error) {
    console.error('[AUTH] Login failed:', error)
    throw error
  }
}

// 通用的带认证的 fetch 函数
function hasAuthToken() {
  return Boolean(auth.value.token)
}

async function fetchWithAuth(url, options = {}) {
  if (!hasAuthToken()) {
    throw new Error('尚未登录，已阻止向后端发送请求')
  }

  // 复制 options 避免修改原始对象
  const fetchOptions = {
    ...options,
    headers: {
      ...options.headers,
      'Content-Type': 'Content-Type' in (options.headers || {}) ? options.headers['Content-Type'] : 'application/json'
    }
  }
  
  // 如果有 Token，添加到 Authorization Header
  if (auth.value.token) {
    fetchOptions.headers['Authorization'] = `Bearer ${auth.value.token}`
  }
  
  return fetch(url, fetchOptions)
}

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

// 构建节点 HTTP 基础路径
function buildNodeHttpUrl(host, port, nodeId = 'master', path = '', protocol = null) {
  const httpProtocol = protocol || getHttpProtocol()
  const normalizedNodeId = String(nodeId || 'master').trim() || 'master'
  const normalizedPath = `/${String(path || '').replace(/^\/+/, '')}`
  return `${httpProtocol}://${host}:${port}/api/node/${encodeURIComponent(normalizedNodeId)}${normalizedPath}`
}

// 构建节点 WebSocket 基础路径
function buildNodeWebSocketUrl(host, port, nodeId = 'master', path = '', protocol = null) {
  const wsProtocol = protocol || getWebSocketProtocol()
  const normalizedNodeId = String(nodeId || 'master').trim() || 'master'
  const normalizedPath = `/${String(path || '').replace(/^\/+/, '')}`
  return `${wsProtocol}://${host}:${port}/api/node/${encodeURIComponent(normalizedNodeId)}${normalizedPath}`
}

// 构建 WebSocket URL（用于网关连接）
function buildWebSocketUrl(host, port, protocol = null) {
  return buildNodeWebSocketUrl(host, port, 'master', 'ws', protocol)
}

// 构建 Agent WebSocket URL（通过统一节点代理）
function buildAgentWebSocketUrl(host, agentId, protocol = null, port = null, nodeId = '') {
  const normalizedNodeId = String(nodeId || 'master').trim() || 'master'
  return buildNodeWebSocketUrl(host, port, normalizedNodeId, `agent/${agentId}/ws`, protocol)
}

// 构建 HTTP URL
function buildHttpUrl(host, port, path, protocol = null) {
  const normalizedPath = String(path || '').replace(/^\/+/, '')
  return buildNodeHttpUrl(host, port, 'master', normalizedPath, protocol)
}

function buildWebSocketProtocols() {
  const token = String(auth.value?.token || '').trim()
  if (!token) {
    return ['jarvis-ws']
  }
  return ['jarvis-ws', `jarvis-token.${encodeURIComponent(token)}`]
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
const showEditorPanel = ref(false)    // 编辑器浮动面板
const showMobileMenu = ref(false)     // 移动端菜单
const activeWindow = ref(null)        // 当前焦点窗口: 'terminal' | 'editor' | null

// 窗口z-index常量
const BASE_Z_INDEX = 1000
const ACTIVE_Z_INDEX = 1100

const AGENT_SIDEBAR_DEFAULT_WIDTH = 320
const AGENT_SIDEBAR_MIN_WIDTH = 240
const AGENT_SIDEBAR_MAX_WIDTH = 560
const AGENT_SIDEBAR_STORAGE_KEY = 'jarvis_agent_sidebar_width'

function normalizeAgentSidebarWidth(width) {
  return clamp(width, AGENT_SIDEBAR_MIN_WIDTH, AGENT_SIDEBAR_MAX_WIDTH)
}

function loadAgentSidebarWidth() {
  const savedValue = localStorage.getItem(AGENT_SIDEBAR_STORAGE_KEY)
  if (!savedValue) {
    return AGENT_SIDEBAR_DEFAULT_WIDTH
  }

  const parsedWidth = Number(savedValue)
  if (!Number.isFinite(parsedWidth)) {
    return AGENT_SIDEBAR_DEFAULT_WIDTH
  }

  return normalizeAgentSidebarWidth(parsedWidth)
}

function saveAgentSidebarWidth() {
  localStorage.setItem(AGENT_SIDEBAR_STORAGE_KEY, String(agentSidebarWidth.value))
}

const agentSidebarWidth = ref(loadAgentSidebarWidth())
const agentSidebarResizeState = ref({
  active: false,
  startX: 0,
  startWidth: AGENT_SIDEBAR_DEFAULT_WIDTH,
})
const EDITOR_PANEL_MIN_WIDTH = 360
const EDITOR_PANEL_MIN_HEIGHT = 260
const EDITOR_PANEL_STORAGE_KEY = 'jarvis_editor_panel_rect'
const editorResizeDirections = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
const PANEL_DRAG_ACTIVATION_DISTANCE = 4

// 窗口最大化状态
const isEditorMaximized = ref(false)
const isTerminalMaximized = ref(false)
const editorPanelRectBeforeMaximize = ref(null)
const terminalPanelRectBeforeMaximize = ref(null)

function getDefaultEditorPanelRect() {
  return {
    top: 88,
    left: Math.max(window.innerWidth - 824, 16),
    width: 800,
    height: 600,
  }
}

function loadEditorPanelRect() {
  const defaultEditorPanelRect = getDefaultEditorPanelRect()
  const savedValue = localStorage.getItem(EDITOR_PANEL_STORAGE_KEY)
  if (!savedValue) {
    return defaultEditorPanelRect
  }

  try {
    const parsedValue = JSON.parse(savedValue)
    if (
      typeof parsedValue.top !== 'number' ||
      typeof parsedValue.left !== 'number' ||
      typeof parsedValue.width !== 'number' ||
      typeof parsedValue.height !== 'number'
    ) {
      return defaultEditorPanelRect
    }

    return parsedValue
  } catch {
    return defaultEditorPanelRect
  }
}

function saveEditorPanelRect() {
  localStorage.setItem(EDITOR_PANEL_STORAGE_KEY, JSON.stringify(editorPanelRect.value))
}

const editorPanelRect = ref(loadEditorPanelRect())
const editorPanelInteraction = ref({
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
const editorContainerRef = ref(null)
const editorTabs = ref([])
const activeEditorTabPath = ref(null)
const editorModels = new Map()
let monacoEditor = null
let editorFileHeartbeatTimer = null
const isEditorEditable = ref(false)  // 编辑器可编辑开关，默认只读
const EDITOR_FILE_HEARTBEAT_INTERVAL = 3000
const globalSearchQuery = ref('')
const globalSearchFileGlob = ref('')
const globalSearchCaseSensitive = ref(false)
const globalSearchWholeWord = ref(false)
const globalSearchLoading = ref(false)
const globalSearchError = ref('')
const globalSearchResults = ref([])
const globalSearchTotalFiles = ref(0)
const globalSearchTotalMatches = ref(0)
const globalSearchExecuted = ref(false)
const showEditorSidebar = ref(true)
const editorSidebarView = ref('files')
const windowWidth = ref(window.innerWidth)  // 窗口宽度，用于响应式检测
const showCreateAgentModal = ref(false) // 创建 Agent 弹窗
const showRenameAgentModal = ref(false) // 重命名 Agent 弹窗
const renamingAgent = ref(null)          // 正在重命名的 Agent
const renameAgentName = ref('')           // 重命名的新名称
const showSessionDialog = ref(false)   // Session 选择对话框
const availableSessions = ref([])         // 可恢复的 session 列表
const selectedSession = ref(null)         // 选中的 session
const showBufferPanel = ref(false)        // 缓存管理面板显示状态
const bufferEditText = ref('')            // 缓存编辑文本
const showDirDialog = ref(false)           // 目录选择对话框
let handleResize = null
let handlePopState = null
let visualViewportResizeHandler = null

function updateViewportHeight() {
  const viewportHeight = window.visualViewport?.height || window.innerHeight
  document.documentElement.style.setProperty('--app-height', `${viewportHeight}px`)
}
const currentDirPath = ref('')             // 当前浏览的目录路径
const dirList = ref([])                    // 目录列表
const selectedDir = ref(null)              // 选中的目录
const dirSearchText = ref('')              // 目录搜索文本
const dirSearchInput = ref(null)           // 目录搜索输入框引用
const selectedDirIndex = ref(-1)           // 当前选中的目录索引，-1 表示未选中
const renameInput = ref(null)               // 重命名输入框引用

// 文件树状态管理
const fileTreeState = ref(new Map())        // 每个 Agent 的文件树数据：agent_id -> treeData
const fileTreeExpanded = ref(new Map())     // 每个 Agent 的展开状态：agent_id -> Set(expandedPaths)
const fileTreeLoading = ref(new Map())      // 每个 Agent 的加载状态：agent_id -> Set(loadingPaths)

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

const agentSidebarStyle = computed(() => {
  if (!showAgentSidebar.value) {
    return {}
  }

  if (windowWidth.value <= 768) {
    return { width: '100vw' }
  }

  return { width: `${agentSidebarWidth.value}px` }
})

const editorPanelStyle = computed(() => {
  if (windowWidth.value <= 768) {
    return {
      top: '0',
      left: '0',
      width: '100vw',
      height: 'var(--app-height, 100vh)',
      zIndex: 2000,
    }
  }

  return {
    top: `${editorPanelRect.value.top}px`,
    left: `${editorPanelRect.value.left}px`,
    width: `${editorPanelRect.value.width}px`,
    height: `${editorPanelRect.value.height}px`,
    zIndex: activeWindow.value === 'editor' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
  }
})

const activeEditorTab = computed(() => {
  return editorTabs.value.find(tab => tab.path === activeEditorTabPath.value) || null
})

function clamp(value, min, max) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

function ensureAgentSidebarWidthInBounds() {
  agentSidebarWidth.value = normalizeAgentSidebarWidth(agentSidebarWidth.value)
}

function startAgentSidebarResize(event) {
  if (windowWidth.value <= 768 || !showAgentSidebar.value) return

  agentSidebarResizeState.value = {
    active: true,
    startX: event.clientX,
    startWidth: agentSidebarWidth.value,
  }

  document.addEventListener('mousemove', onAgentSidebarResize)
  document.addEventListener('mouseup', stopAgentSidebarResize)
  event.preventDefault()
  event.stopPropagation()
}

function onAgentSidebarResize(event) {
  if (!agentSidebarResizeState.value.active) return

  const deltaX = event.clientX - agentSidebarResizeState.value.startX
  const nextWidth = agentSidebarResizeState.value.startWidth + deltaX
  agentSidebarWidth.value = normalizeAgentSidebarWidth(nextWidth)
}

function stopAgentSidebarResize() {
  if (!agentSidebarResizeState.value.active) {
    document.removeEventListener('mousemove', onAgentSidebarResize)
    document.removeEventListener('mouseup', stopAgentSidebarResize)
    return
  }

  agentSidebarResizeState.value = {
    active: false,
    startX: 0,
    startWidth: agentSidebarWidth.value,
  }

  document.removeEventListener('mousemove', onAgentSidebarResize)
  document.removeEventListener('mouseup', stopAgentSidebarResize)
  saveAgentSidebarWidth()
}

// 设置焦点窗口
function focusWindow(windowType) {
  activeWindow.value = windowType
}

// 编辑器窗口最大化/还原
function toggleEditorMaximize() {
  if (isEditorMaximized.value) {
    // 还原
    if (editorPanelRectBeforeMaximize.value) {
      editorPanelRect.value = { ...editorPanelRectBeforeMaximize.value }
    }
    isEditorMaximized.value = false
  } else {
    // 最大化
    editorPanelRectBeforeMaximize.value = { ...editorPanelRect.value }
    editorPanelRect.value = {
      top: 0,
      left: 0,
      width: window.innerWidth,
      height: window.innerHeight,
    }
    isEditorMaximized.value = true
  }
  nextTick(() => {
    layoutMonacoEditor()
  })
}

// 终端窗口最大化/还原
function toggleTerminalMaximize() {
  if (isTerminalMaximized.value) {
    // 还原
    if (terminalPanelRectBeforeMaximize.value) {
      terminalPanelRect.value = { ...terminalPanelRectBeforeMaximize.value }
    }
    isTerminalMaximized.value = false
  } else {
    // 最大化
    terminalPanelRectBeforeMaximize.value = { ...terminalPanelRect.value }
    terminalPanelRect.value = {
      top: 0,
      left: 0,
      width: window.innerWidth,
      height: window.innerHeight,
    }
    isTerminalMaximized.value = true
  }
}

function getEditorPanelBounds() {
  const KEEP_VISIBLE = 100 // 至少保留100px可见区域
  return {
    minTop: KEEP_VISIBLE - editorPanelRect.value.height, // 允许向上拖出，但保留底部100px
    minLeft: KEEP_VISIBLE - editorPanelRect.value.width, // 允许向左拖出，但保留右侧100px
    maxLeft: window.innerWidth - KEEP_VISIBLE, // 允许向右拖出，但保留左侧100px
    maxTop: window.innerHeight - KEEP_VISIBLE, // 允许向下拖出，但保留顶部100px
    maxWidth: window.innerWidth,
    maxHeight: window.innerHeight,
  }
}

function ensureEditorPanelInViewport() {
  const KEEP_VISIBLE = 100 // 至少保留100px可见区域
  const maxWidth = Math.max(window.innerWidth, EDITOR_PANEL_MIN_WIDTH)
  const maxHeight = Math.max(window.innerHeight, EDITOR_PANEL_MIN_HEIGHT)

  editorPanelRect.value.width = clamp(editorPanelRect.value.width, EDITOR_PANEL_MIN_WIDTH, maxWidth)
  editorPanelRect.value.height = clamp(editorPanelRect.value.height, EDITOR_PANEL_MIN_HEIGHT, maxHeight)

  // 允许部分拖出屏幕，但保留至少100px可见区域
  editorPanelRect.value.left = clamp(
    editorPanelRect.value.left,
    KEEP_VISIBLE - editorPanelRect.value.width, // 允许向左拖出
    window.innerWidth - KEEP_VISIBLE // 允许向右拖出
  )
  editorPanelRect.value.top = clamp(
    editorPanelRect.value.top,
    KEEP_VISIBLE - editorPanelRect.value.height, // 允许向上拖出
    window.innerHeight - KEEP_VISIBLE // 允许向下拖出
  )
}

function startEditorPanelMove(event) {
  if (windowWidth.value <= 768) return
  if (event.target.closest('.editor-panel-actions')) return

  focusWindow('editor')

  editorPanelInteraction.value = {
    active: false,
    mode: 'move',
    direction: null,
    startX: event.clientX,
    startY: event.clientY,
    startTop: editorPanelRect.value.top,
    startLeft: editorPanelRect.value.left,
    startWidth: editorPanelRect.value.width,
    startHeight: editorPanelRect.value.height,
  }

  document.addEventListener('mousemove', onEditorPanelPointerMove)
  document.addEventListener('mouseup', stopEditorPanelInteraction)
}

function startEditorPanelResize(event, direction) {
  if (windowWidth.value <= 768) return

  editorPanelInteraction.value = {
    active: true,
    mode: 'resize',
    direction,
    startX: event.clientX,
    startY: event.clientY,
    startTop: editorPanelRect.value.top,
    startLeft: editorPanelRect.value.left,
    startWidth: editorPanelRect.value.width,
    startHeight: editorPanelRect.value.height,
  }

  document.addEventListener('mousemove', onEditorPanelPointerMove)
  document.addEventListener('mouseup', stopEditorPanelInteraction)
  event.preventDefault()
  event.stopPropagation()
}

function onEditorPanelPointerMove(event) {
  const deltaX = event.clientX - editorPanelInteraction.value.startX
  const deltaY = event.clientY - editorPanelInteraction.value.startY

  if (editorPanelInteraction.value.mode === 'move' && !editorPanelInteraction.value.active) {
    const dragDistance = Math.hypot(deltaX, deltaY)
    if (dragDistance < PANEL_DRAG_ACTIVATION_DISTANCE) {
      return
    }

    editorPanelInteraction.value = {
      ...editorPanelInteraction.value,
      active: true,
    }
    event.preventDefault()
  }

  if (!editorPanelInteraction.value.active) return

  if (editorPanelInteraction.value.mode === 'move') {
    const bounds = getEditorPanelBounds()
    editorPanelRect.value.left = clamp(editorPanelInteraction.value.startLeft + deltaX, bounds.minLeft, bounds.maxLeft)
    editorPanelRect.value.top = clamp(editorPanelInteraction.value.startTop + deltaY, bounds.minTop, bounds.maxTop)
    return
  }

  const direction = editorPanelInteraction.value.direction || ''
  const startLeft = editorPanelInteraction.value.startLeft
  const startTop = editorPanelInteraction.value.startTop
  const startWidth = editorPanelInteraction.value.startWidth
  const startHeight = editorPanelInteraction.value.startHeight

  let nextLeft = startLeft
  let nextTop = startTop
  let nextWidth = startWidth
  let nextHeight = startHeight

  if (direction.includes('e')) {
    nextWidth = clamp(startWidth + deltaX, EDITOR_PANEL_MIN_WIDTH, Math.max(window.innerWidth - startLeft, EDITOR_PANEL_MIN_WIDTH))
  }

  if (direction.includes('s')) {
    nextHeight = clamp(startHeight + deltaY, EDITOR_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - startTop, EDITOR_PANEL_MIN_HEIGHT))
  }

  if (direction.includes('w')) {
    const desiredLeft = clamp(startLeft + deltaX, 0, startLeft + startWidth - EDITOR_PANEL_MIN_WIDTH)
    nextLeft = desiredLeft
    nextWidth = startWidth - (desiredLeft - startLeft)
  }

  if (direction.includes('n')) {
    const desiredTop = clamp(startTop + deltaY, 0, startTop + startHeight - EDITOR_PANEL_MIN_HEIGHT)
    nextTop = desiredTop
    nextHeight = startHeight - (desiredTop - startTop)
  }

  if (nextLeft + nextWidth > window.innerWidth) {
    nextWidth = Math.max(EDITOR_PANEL_MIN_WIDTH, window.innerWidth - nextLeft)
  }

  if (nextTop + nextHeight > window.innerHeight) {
    nextHeight = Math.max(EDITOR_PANEL_MIN_HEIGHT, window.innerHeight - nextTop)
  }

  editorPanelRect.value.left = clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0))
  editorPanelRect.value.top = clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0))
  editorPanelRect.value.width = clamp(nextWidth, EDITOR_PANEL_MIN_WIDTH, Math.max(window.innerWidth - editorPanelRect.value.left, EDITOR_PANEL_MIN_WIDTH))
  editorPanelRect.value.height = clamp(nextHeight, EDITOR_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - editorPanelRect.value.top, EDITOR_PANEL_MIN_HEIGHT))
}

function stopEditorPanelInteraction() {
  editorPanelInteraction.value = {
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

  document.removeEventListener('mousemove', onEditorPanelPointerMove)
  document.removeEventListener('mouseup', stopEditorPanelInteraction)
  saveEditorPanelRect()
}

function getEditorTabByPath(path) {
  return editorTabs.value.find(tab => tab.path === path) || null
}

function syncEditorTabDirtyState(path, value) {
  const tab = getEditorTabByPath(path)
  if (tab) {
    tab.isDirty = value
  }
}

function updateEditorTabFileStat(tab, fileStat = {}) {
  if (!tab) return
  tab.mtimeNs = fileStat.mtime_ns ?? null
  tab.fileSize = fileStat.size ?? null
}

function markEditorTabExternalModified(path, value) {
  const tab = getEditorTabByPath(path)
  if (tab) {
    tab.externalModified = value
  }
}

function ensureMonacoEditor() {
  if (monacoEditor || !editorContainerRef.value) return

  monacoEditor = monaco.editor.create(editorContainerRef.value, {
    value: '',
    language: 'plaintext',
    theme: 'vs-dark',
    automaticLayout: true,
    minimap: { enabled: false },
    folding: true,
    scrollBeyondLastLine: false,
    fontSize: 13,
    tabSize: 2,
    wordWrap: 'off',
    renderWhitespace: 'selection',
    readOnly: !isEditorEditable.value,
  })

  monacoEditor.onDidChangeModel(() => {
    const model = monacoEditor.getModel()
    if (!model) return
    const path = model.uri.path
    const tab = getEditorTabByPath(path)
    if (!tab) return
    tab.content = model.getValue()
    tab.isDirty = tab.content !== tab.originalContent
  })
}

function layoutMonacoEditor() {
  if (monacoEditor) {
    monacoEditor.layout()
  }
}

function activateEditorTab(path) {
  activeEditorTabPath.value = path
  const model = editorModels.get(path)
  if (monacoEditor && model) {
    monacoEditor.setModel(model)
    monaco.editor.setModelLanguage(model, getLanguageFromFilename(path))
    nextTick(() => {
      layoutMonacoEditor()
      monacoEditor.focus()
    })
  }
}

function resolveAgentRelativePath(relativePath) {
  if (!relativePath) return ''
  const workingDir = currentAgent.value?.working_dir || ''
  if (!workingDir) return relativePath
  return `${workingDir.replace(/\/$/, '')}/${String(relativePath).replace(/^\//, '')}`
}

async function fetchGlobalSearchResults(agentId, payload) {
  const { host, port } = getGatewayAddress()
  const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `global-search/${agentId}`), {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      node_id: targetNodeId,
    })
  })
  const result = await response.json()
  if (!response.ok || !result.success || !result.data) {
    throw new Error(result.error?.message || '全局搜索失败')
  }
  return result.data
}

const hasEditorSidebarFileTree = computed(() => {
  const agentId = currentAgentId.value
  if (!agentId) return false
  return getVisibleFileTreeNodes(agentId).length > 0
})

async function ensureEditorSidebarFileTree(agent = currentAgent.value) {
  if (!agent?.agent_id || !agent.working_dir) return
  const treeNodes = fileTreeState.value.get(agent.agent_id) || []
  if (treeNodes.length === 0) {
    await initFileTree(agent.agent_id, agent.working_dir)
  }
}

function setEditorSidebarView(view) {
  editorSidebarView.value = view
  showEditorSidebar.value = true
  if (view === 'files') {
    nextTick(() => {
      ensureEditorSidebarFileTree()
      layoutMonacoEditor()
    })
    return
  }
  nextTick(() => {
    layoutMonacoEditor()
  })
}

function toggleEditorSearchSidebar() {
  if (showEditorSidebar.value && editorSidebarView.value === 'search') {
    closeEditorSidebar()
    return
  }
  setEditorSidebarView('search')
}

function closeEditorSidebar() {
  showEditorSidebar.value = false
  nextTick(() => {
    layoutMonacoEditor()
  })
}

function clearGlobalSearch() {
  globalSearchQuery.value = ''
  globalSearchFileGlob.value = ''
  globalSearchCaseSensitive.value = false
  globalSearchWholeWord.value = false
  globalSearchError.value = ''
  globalSearchResults.value = []
  globalSearchTotalFiles.value = 0
  globalSearchTotalMatches.value = 0
  globalSearchExecuted.value = false
}

async function runGlobalSearch() {
  if (!currentAgentId.value) {
    showToast('请先选择 Agent', 'error')
    return
  }

  const query = globalSearchQuery.value.trim()
  if (!query) {
    globalSearchError.value = '请输入搜索关键词'
    globalSearchExecuted.value = false
    globalSearchResults.value = []
    setEditorSidebarView('search')
    return
  }

  setEditorSidebarView('search')
  globalSearchLoading.value = true
  globalSearchError.value = ''
  globalSearchExecuted.value = false

  try {
    const data = await fetchGlobalSearchResults(currentAgentId.value, {
      query,
      case_sensitive: globalSearchCaseSensitive.value,
      whole_word: globalSearchWholeWord.value,
      max_results: 100,
      file_glob: globalSearchFileGlob.value.trim(),
    })
    globalSearchResults.value = Array.isArray(data.results) ? data.results : []
    globalSearchTotalFiles.value = Number(data.total_files || 0)
    globalSearchTotalMatches.value = Number(data.total_matches || 0)
    globalSearchExecuted.value = true
  } catch (error) {
    globalSearchError.value = error.message || '全局搜索失败'
    globalSearchResults.value = []
    globalSearchTotalFiles.value = 0
    globalSearchTotalMatches.value = 0
    globalSearchExecuted.value = true
    showToast(globalSearchError.value, 'error')
  } finally {
    globalSearchLoading.value = false
  }
}

async function openGlobalSearchResult(filePath, lineNumber, matchStart = 0, matchEnd = matchStart) {
  const absolutePath = resolveAgentRelativePath(filePath)
  await openEditorFile(absolutePath)
  await nextTick()
  const model = editorModels.get(absolutePath)
  if (!monacoEditor || !model) {
    return
  }

  monacoEditor.setModel(model)
  const column = Number(matchStart || 0) + 1
  const endColumn = Math.max(column, Number(matchEnd || matchStart || 0) + 1)
  monacoEditor.revealLineInCenter(Number(lineNumber || 1))
  monacoEditor.setPosition({ lineNumber: Number(lineNumber || 1), column })
  monacoEditor.setSelection({
    startLineNumber: Number(lineNumber || 1),
    startColumn: column,
    endLineNumber: Number(lineNumber || 1),
    endColumn,
  })
  monacoEditor.focus()
}

async function fetchFileContent(path) {
  const { host, port } = getGatewayAddress()
  const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-content'), {
    method: 'POST',
    body: JSON.stringify({ path, node_id: targetNodeId })
  })

  const result = await response.json()
  if (!response.ok || !result.success || !result.data) {
    throw new Error(result.error?.message || '读取文件失败')
  }
  return result.data.content || ''
}

async function fetchFileStat(path) {
  const { host, port } = getGatewayAddress()
  const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-stat'), {
    method: 'POST',
    body: JSON.stringify({ path, node_id: targetNodeId })
  })

  const result = await response.json()
  if (!response.ok || !result.success || !result.data) {
    throw new Error(result.error?.message || '读取文件状态失败')
  }
  return result.data
}

async function refreshEditorTabFromRemote(path, showAutoRefreshToast = false) {
  const tab = getEditorTabByPath(path)
  if (!tab) return

  const [content, fileStat] = await Promise.all([
    fetchFileContent(path),
    fetchFileStat(path),
  ])

  tab.content = content
  tab.originalContent = content
  tab.isDirty = false
  tab.error = ''
  tab.externalModified = false
  updateEditorTabFileStat(tab, fileStat)

  const model = editorModels.get(path)
  if (model && model.getValue() !== content) {
    model.setValue(content)
  }

  if (showAutoRefreshToast) {
    showToast('检测到文件已更新，已自动刷新', 'info')
  }
}

async function checkActiveEditorFileHeartbeat() {
  if (!showEditorPanel.value) return

  const tab = activeEditorTab.value
  if (!tab || tab.loading || !tab.path) return

  try {
    const remoteFileStat = await fetchFileStat(tab.path)
    const remoteMtimeNs = remoteFileStat.mtime_ns ?? null
    const remoteFileSize = remoteFileStat.size ?? null
    const localMtimeNs = tab.mtimeNs ?? null
    const localFileSize = tab.fileSize ?? null
    const hasRemoteChange =
      remoteMtimeNs !== localMtimeNs || remoteFileSize !== localFileSize

    if (!hasRemoteChange) {
      if (!tab.isDirty && tab.externalModified) {
        tab.externalModified = false
      }
      return
    }

    if (tab.isDirty) {
      if (!tab.externalModified) {
        tab.externalModified = true
        tab.error = '文件已被外部修改，请先处理冲突后再保存'
        showToast('检测到文件外部变更，当前标签有未保存修改', 'error')
      }
      return
    }

    await refreshEditorTabFromRemote(tab.path, true)
  } catch (error) {
    console.error('[EDITOR] File heartbeat check failed:', error)
  }
}

function stopEditorFileHeartbeat() {
  if (editorFileHeartbeatTimer) {
    clearInterval(editorFileHeartbeatTimer)
    editorFileHeartbeatTimer = null
  }
}

function startEditorFileHeartbeat() {
  stopEditorFileHeartbeat()

  if (!showEditorPanel.value || !activeEditorTab.value) {
    return
  }

  editorFileHeartbeatTimer = setInterval(() => {
    checkActiveEditorFileHeartbeat()
  }, EDITOR_FILE_HEARTBEAT_INTERVAL)
}

async function openEditorFile(path) {
  if (!path) return

  showEditorPanel.value = true

  const existingTab = getEditorTabByPath(path)
  if (existingTab) {
    activateEditorTab(path)
    return
  }

  const tab = {
    path,
    name: path.split('/').pop() || path,
    content: '',
    originalContent: '',
    language: getLanguageFromFilename(path),
    isDirty: false,
    loading: true,
    error: '',
    externalModified: false,
    mtimeNs: null,
    fileSize: null,
  }
  editorTabs.value.push(tab)
  activeEditorTabPath.value = path

  try {
    const [content, fileStat] = await Promise.all([
      fetchFileContent(path),
      fetchFileStat(path),
    ])
    tab.content = content
    tab.originalContent = content
    tab.externalModified = false
    updateEditorTabFileStat(tab, fileStat)
    tab.loading = false

    let model = editorModels.get(path)
    if (!model) {
      model = monaco.editor.createModel(content, tab.language, monaco.Uri.file(path))
      editorModels.set(path, model)
    }
    model.setValue(content)

    await nextTick()
    ensureMonacoEditor()
    activateEditorTab(path)
  } catch (error) {
    tab.loading = false
    tab.error = error.message || '读取文件失败'
  }
}

async function saveEditorTab(path) {
  const tab = getEditorTabByPath(path)
  if (!tab) return

  const model = editorModels.get(path)
  const content = model ? model.getValue() : tab.content

  const { host, port } = getGatewayAddress()
  const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-write'), {
    method: 'POST',
    body: JSON.stringify({ path, content, node_id: targetNodeId })
  })
  const result = await response.json()

  if (!response.ok || !result.success) {
    const message = result.error?.message || '保存文件失败'
    tab.error = message
    showToast(message, 'error')
    return
  }

  tab.originalContent = content
  tab.content = content
  tab.isDirty = false
  tab.error = ''
  tab.externalModified = false

  try {
    const fileStat = await fetchFileStat(path)
    updateEditorTabFileStat(tab, fileStat)
  } catch (error) {
    console.error('[EDITOR] Failed to refresh file stat after save:', error)
  }

  showToast('文件已保存', 'success')
}

async function saveActiveEditorTab() {
  if (!activeEditorTab.value) return
  await saveEditorTab(activeEditorTab.value.path)
}

function toggleEditorEditable() {
  isEditorEditable.value = !isEditorEditable.value
  if (monacoEditor) {
    monacoEditor.updateOptions({ readOnly: !isEditorEditable.value })
  }
}

function hasDirtyEditorTabs() {
  return editorTabs.value.some(tab => tab.isDirty)
}

function confirmCloseEditorPanel() {
  return new Promise((resolve) => {
    showConfirm(
      '存在未保存标签，确定关闭编辑器吗？',
      () => resolve(true),
      () => resolve(false),
      false
    )
  })
}

async function closeEditorPanel() {
  if (hasDirtyEditorTabs()) {
    const confirmed = await confirmCloseEditorPanel()
    if (!confirmed) return
  }

  showEditorPanel.value = false
}

function confirmCloseDirtyEditorTab(path) {
  return new Promise((resolve) => {
    showConfirm(
      '该标签存在未保存修改，确定关闭吗？',
      () => resolve(true),
      () => resolve(false),
      false
    )
  })
}

async function closeEditorTab(path) {
  const tab = getEditorTabByPath(path)
  if (!tab) return

  if (tab.isDirty) {
    const confirmed = await confirmCloseDirtyEditorTab(path)
    if (!confirmed) return
  }

  const index = editorTabs.value.findIndex(item => item.path === path)
  if (index === -1) return

  const wasActive = activeEditorTabPath.value === path
  editorTabs.value.splice(index, 1)

  const model = editorModels.get(path)
  if (model) {
    model.dispose()
    editorModels.delete(path)
  }

  if (wasActive) {
    const nextTab = editorTabs.value[index] || editorTabs.value[index - 1] || null
    if (nextTab) {
      activateEditorTab(nextTab.path)
    } else {
      activeEditorTabPath.value = null
      if (monacoEditor) {
        monacoEditor.dispose()
        monacoEditor = null
      }
    }
  }
}

async function handleFileTreeNodeClick(agentId, node) {
  if (node.type === 'directory') {
    await toggleNodeExpand(agentId, node)
    return
  }

  await openEditorFile(node.path)
}

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
const isCreatingTerminalSession = ref(false)

// 输入控制
const inputText = ref('')
const inputMode = ref('multi')
const inputTip = ref('')
const multilineInput = ref(null)
const singlelineInput = ref(null)
const lastInputRequest = ref(null) // 保存最后一次的输入请求，用于重连后恢复
const pendingInputAgentId = ref(null) // 当前待响应输入请求所属 Agent
const pendingConfirmAgentId = ref(null) // 当前待响应确认请求所属 Agent
const inputBuffers = ref(new Map()) // 每个 Agent 的输入缓冲区（key: agentId, value：内容）

// 历史输入记录
const INPUT_HISTORY_STORAGE_KEY = 'jarvis_input_history'
const MAX_INPUT_HISTORY_COUNT = 100
const COMPLETION_USAGE_STORAGE_KEY = 'jarvis_completion_usage_stats'

const inputHistory = ref([]) // 历史输入记录数组
const historyIndex = ref(-1) // 当前浏览的历史记录索引（-1 表示未浏览历史）
const currentTempInput = ref('') // 用户正在编辑的临时内容

function loadCompletionUsageStats() {
  const savedValue = localStorage.getItem(COMPLETION_USAGE_STORAGE_KEY)
  if (!savedValue) {
    return {}
  }

  try {
    const parsedValue = JSON.parse(savedValue)
    if (!parsedValue || typeof parsedValue !== 'object' || Array.isArray(parsedValue)) {
      return {}
    }

    return Object.fromEntries(
      Object.entries(parsedValue).filter(([, count]) => Number.isInteger(count) && count > 0)
    )
  } catch {
    return {}
  }
}

function saveCompletionUsageStats(completionUsageStats) {
  localStorage.setItem(COMPLETION_USAGE_STORAGE_KEY, JSON.stringify(completionUsageStats))
}

function getCompletionUsageKey(item) {
  if (!item || typeof item.value !== 'string') {
    return ''
  }

  const normalizedValue = item.value.trim()
  if (!normalizedValue) {
    return ''
  }

  const normalizedType = typeof item.type === 'string' && item.type.trim()
    ? item.type.trim()
    : 'unknown'

  return `${normalizedType}:${normalizedValue}`
}

function getCompletionUsageCount(item) {
  const completionUsageKey = getCompletionUsageKey(item)
  if (!completionUsageKey) {
    return 0
  }

  return completionUsageStats.value[completionUsageKey] || 0
}

function getCompletionRecommendationScore(item, originalIndex = 0) {
  if (!item || typeof item !== 'object') {
    return -originalIndex
  }

  const scoreMatch = typeof item.display === 'string'
    ? item.display.match(/\((\d+)%\)$/)
    : null

  if (scoreMatch) {
    return Number(scoreMatch[1])
  }

  return -originalIndex
}

function sortCompletionItems(items = []) {
  return items
    .map((item, index) => ({
      item,
      usageCount: getCompletionUsageCount(item),
      recommendationScore: getCompletionRecommendationScore(item, index),
      originalIndex: index,
    }))
    .sort((leftItem, rightItem) => {
      if (rightItem.usageCount !== leftItem.usageCount) {
        return rightItem.usageCount - leftItem.usageCount
      }

      if (rightItem.recommendationScore !== leftItem.recommendationScore) {
        return rightItem.recommendationScore - leftItem.recommendationScore
      }

      return leftItem.originalIndex - rightItem.originalIndex
    })
    .map(({ item }) => item)
}

function recordCompletionSelection(item) {
  const completionUsageKey = getCompletionUsageKey(item)
  if (!completionUsageKey) {
    return
  }

  const nextCompletionUsageStats = {
    ...completionUsageStats.value,
    [completionUsageKey]: (completionUsageStats.value[completionUsageKey] || 0) + 1,
  }

  completionUsageStats.value = nextCompletionUsageStats
  saveCompletionUsageStats(nextCompletionUsageStats)
}

function loadInputHistory() {
  const savedValue = localStorage.getItem(INPUT_HISTORY_STORAGE_KEY)
  if (!savedValue) {
    return []
  }

  try {
    const parsedValue = JSON.parse(savedValue)
    if (!Array.isArray(parsedValue)) {
      return []
    }

    return parsedValue
      .filter(historyItem => typeof historyItem === 'string' && historyItem.trim())
      .slice(0, MAX_INPUT_HISTORY_COUNT)
  } catch {
    return []
  }
}

function saveInputHistory() {
  localStorage.setItem(
    INPUT_HISTORY_STORAGE_KEY,
    JSON.stringify(inputHistory.value.slice(0, MAX_INPUT_HISTORY_COUNT))
  )
}

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

// 监听缓存面板打开，自动加载缓存内容
watch(showBufferPanel, (newVal) => {
  if (newVal && hasBufferedInput.value) {
    const agentId = currentAgentId.value
    if (agentId && inputBuffers.value.has(agentId)) {
      bufferEditText.value = inputBuffers.value.get(agentId)
    }
  }
})

// 监听设置面板打开，自动获取节点状态
watch(showSettingsModal, (newVal) => {
  if (newVal) {
    fetchNodeStatus()
  }
})

// Agent 管理
const agentList = ref([])        // Agent 列表
const currentAgentId = ref(null) // 当前连接的 Agent ID
const agentStatuses = ref(new Map()) // Agent 状态映射 (agent_id -> {execution_status, agent_status})
const currentAgent = computed(() => {
  return agentList.value.find(agent => agent.agent_id === currentAgentId.value) || null
})

watch([showEditorPanel, currentAgentId, editorSidebarView], ([isEditorPanelVisible, agentId, sidebarView]) => {
  if (!isEditorPanelVisible || !agentId || sidebarView !== 'files') {
    return
  }

  nextTick(() => {
    ensureEditorSidebarFileTree()
  })
})

// Agent 批量选择管理
const selectedAgents = ref(new Set()) // 选中的 Agent ID 集合
const isBatchMode = ref(false)        // 是否处于批量选择模式

// 切换批量选择模式
function toggleBatchMode() {
  isBatchMode.value = !isBatchMode.value
  if (!isBatchMode.value) {
    // 退出批量模式时清空选中状态
    selectedAgents.value.clear()
  }
}

// 处理 Agent item 点击事件
function handleAgentItemClick(agent, event) {
  if (isBatchMode.value) {
    // 多选模式下，点击整个 item 只切换选择状态，不切换 agent
    toggleSelectAgent(agent.agent_id)
  } else {
    // 正常模式下，切换 agent
    switchAgent(agent)
  }
}

// 切换单个 Agent 的选中状态
function toggleSelectAgent(agentId) {
  if (selectedAgents.value.has(agentId)) {
    selectedAgents.value.delete(agentId)
  } else {
    selectedAgents.value.add(agentId)
  }
  // 触发响应式更新
  selectedAgents.value = new Set(selectedAgents.value)
}

// 判断 Agent 是否被选中
function isAgentSelected(agentId) {
  return selectedAgents.value.has(agentId)
}

// 判断是否全选
const isAllSelected = computed(() => {
  return agentList.value.length > 0 && agentList.value.every(agent => selectedAgents.value.has(agent.agent_id))
})

// 切换全选/取消全选
function toggleSelectAll() {
  if (isAllSelected.value) {
    // 取消全选
    selectedAgents.value.clear()
  } else {
    // 全选
    agentList.value.forEach(agent => {
      selectedAgents.value.add(agent.agent_id)
    })
  }
  // 触发响应式更新
  selectedAgents.value = new Set(selectedAgents.value)
}

function isCurrentAgent(agentId) {
  return agentId === currentAgentId.value
}

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

// 判断完成和补全按钮是否应该禁用（只在等待多行输入时使能）
const isWaitingMultiDisabled = computed(() => {
  console.log('[DEBUG isWaitingMultiDisabled]', {
    currentAgentId: currentAgentId.value,
    executionStatus: agentStatuses.value.get(currentAgentId.value)?.execution_status,
    agentStatusesKeys: [...agentStatuses.value.keys()],
    agentStatusesValues: [...agentStatuses.value.entries()]
  })
  if (!currentAgentId.value) {
    return true // 没有激活的 agent
  }
  const executionStatus = agentStatuses.value.get(currentAgentId.value)?.execution_status
  return executionStatus !== 'waiting_multi' // 只有在等待多行输入时才使能
})
const newAgentType = ref('agent') // 新 Agent 类型
const newAgentDir = ref('~')       // 新 Agent 工作目录（默认用户目录）
const newAgentName = ref('通用Agent') // 新 Agent 名称（可选，默认为'通用Agent'）
const modelGroups = ref([])        // 模型组列表
const newAgentModelGroup = ref('default') // 新 Agent 模型组（默认为 default）
const newCodeAgentWorktree = ref(false) // 新代码 Agent 是否启用 worktree
const newAgentQuickMode = ref(false) // 新 Agent 是否启用极速模式
const availableNodeOptions = ref([])
const newAgentNodeId = ref('')

// 监听 Agent 类型变化，自动填充默认名称
watch(newAgentType, (newType) => {
  if (newType === 'agent') {
    newAgentName.value = '通用Agent'
    newCodeAgentWorktree.value = false
  } else if (newType === 'codeagent') {
    newAgentName.value = '代码Agent'
  }
}, { immediate: true })

// 确认对话框
const confirmDialog = ref(null) // { message, confirmCallback, cancelCallback, defaultConfirm }
const confirmConfirmBtn = ref(null) // 确认按钮引用
const confirmCancelBtn = ref(null) // 取消按钮引用

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
    // 根据 defaultConfirm 聚焦默认按钮
    if (defaultConfirm && confirmConfirmBtn.value) {
      confirmConfirmBtn.value.focus()
    } else if (!defaultConfirm && confirmCancelBtn.value) {
      confirmCancelBtn.value.focus()
    }
  })
}

// 处理确认对话框的键盘事件
function handleConfirmKeydown(event) {
  if (event.key === 'Enter' && confirmDialog.value) {
    const activeElement = document.activeElement
    // 根据当前焦点元素决定调用哪个回调
    if (activeElement === confirmConfirmBtn.value) {
      confirmDialog.value.confirmCallback()
    } else if (activeElement === confirmCancelBtn.value) {
      confirmDialog.value.cancelCallback()
    }
  }
}

// 监听确认对话框的显示状态，动态添加/移除键盘事件监听
watch(confirmDialog, (newVal) => {
  if (newVal) {
    document.addEventListener('keydown', handleConfirmKeydown)
  } else {
    document.removeEventListener('keydown', handleConfirmKeydown)
  }
})

// 补全列表
const showCompletions = ref(false) // 是否显示补全列表
const completionCursorPos = ref(-1) // 记录打开补全列表时的光标位置
const completions = ref([]) // 补全列表数据
const completionSearch = ref('') // 补全搜索关键词
const fileCompletions = ref([]) // 文件补全搜索结果
const completionUsageStats = ref(loadCompletionUsageStats()) // 补全项本地使用统计

// 监听搜索输入变化，触发文件搜索
watch(completionSearch, async (newSearch) => {
  selectedIndex.value = -1
  
  // 如果有搜索内容，加载文件补全
  if (newSearch.trim()) {
    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(
        buildNodeHttpUrl(host, port, targetNodeId, `completions/${currentAgent.value.agent_id}/search?query=${encodeURIComponent(newSearch)}`)
      )
      
      const result = await response.json()
      
      if (response.ok && result.success && result.data) {
        fileCompletions.value = sortCompletionItems(result.data)
        console.log('[FILE COMPLETIONS] Loaded', result.data.length, 'files')
      } else {
        fileCompletions.value = []
      }
    } catch (error) {
      console.error('[FILE COMPLETIONS] Fetch failed:', error)
      fileCompletions.value = []
    }
  } else {
    fileCompletions.value = []
  }
})
const completionSearchInput = ref(null) // 补全搜索输入框引用
const completionsListRef = ref(null) // 补全列表容器引用
const completionItemsRef = ref([]) // 补全条目元素引用数组
const selectedIndex = ref(-1) // 当前选中的补全条目索引，-1 表示未选中

// 流式消息跟踪
const streamingMessages = ref(new Map()) // 按 agent_id 跟踪当前流式消息

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
async function loadHistoryMessages(prepend = false) {
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

// 保存连接锁定设置
function saveConnectionLockSetting() {
  localStorage.setItem('connection_lock_enabled', connectionLockEnabled.value)
  console.log('[SETTINGS] Connection lock setting saved:', connectionLockEnabled.value)
  // 如果已连接，发送设置更新消息
  if (socket.value && socket.value.readyState === WebSocket.OPEN) {
    try {
      socket.value.send(JSON.stringify({
        type: 'connection_lock',
        payload: { enabled: connectionLockEnabled.value }
      }))
      console.log('[SETTINGS] Connection lock setting sent to server')
    } catch (error) {
      console.error('[SETTINGS] Failed to send connection lock setting:', error)
    }
  }
}

// 连接到 Gateway
async function connect() {
  console.log('[ws] connect() called', {
    hasSocket: !!socket.value,
    socketState: socket.value?.readyState,
    connecting: connecting.value,
    gatewayUrl: gatewayUrl.value,
  })
  // 清空之前的错误信息
  connectErrorMessage.value = ''
  if (socket.value) return
  
  // 解析网关地址
  const parsed = parseGatewayAddress(gatewayUrl.value)
  if (!parsed) {
    connectErrorMessage.value = '无效的网关地址格式'
    return
  }
  
  const password = String(auth.value.password || '').trim()

  try {
    await loginWithPassword(password)
  } catch (error) {
    connectErrorMessage.value = error.message || '登录失败'
    return
  }
  
  if (!hasAuthToken()) {
    connectErrorMessage.value = '登录失败，请重试'
    return
  }
  
  const host = parsed.host || window.location.hostname || '127.0.0.1'
  const port = parsed.port || '8000'
  const url = buildWebSocketUrl(host, port, parsed.protocol)
  connecting.value = true
  const ws = new WebSocket(url, buildWebSocketProtocols())
  console.log('[ws] new WebSocket created', { url, readyState: ws.readyState })
  ws.onopen = () => {
    console.log('[ws] open', { url, readyState: ws.readyState })
    connecting.value = false
    socket.value = ws
    showConnectModal.value = false
    
    // 保存连接信息到 localStorage
    localStorage.setItem('jarvis_gateway_url', gatewayUrl.value)
    console.log('[ws] Connection info saved:', gatewayUrl.value)
    startAgentListRefresh()
    // 获取模型组列表
    fetchModelGroups()
    fetchNodeStatus()
    const currentOutputs = allOutputs.value.get(currentAgentId.value) || []
    if (currentOutputs.length === 0) {
      console.log('[HISTORY] Loading history on first connect')
      loadHistoryMessages(false)
    } else {
      console.log('[HISTORY] Skip loading history, messages already exist')
    }
    // 发送连接锁定设置
    ws.send(JSON.stringify({
      type: 'connection_lock',
      payload: { enabled: connectionLockEnabled.value }
    }))
    console.log('[ws] connection_lock sent', connectionLockEnabled.value)
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
  ws.onclose = (event) => {
    console.log('[ws] close', {
      code: event?.code,
      reason: event?.reason,
      wasClean: event?.wasClean,
      readyState: ws.readyState,
      currentSocketMatched: socket.value === ws,
    })
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
  ws.onerror = (event) => {
    console.error('[ws] error', {
      event,
      readyState: ws.readyState,
      currentSocketMatched: socket.value === ws,
    })
    connecting.value = false
  }
}

function disconnect() {
  if (socket.value) {
    socket.value.close()
  }
}

function confirmRestartGateway() {
  if (isRestartingGateway.value) {
    return
  }

  showSettingsModal.value = false
  const targetNodeId = restartNodeId.value
  const confirmMessage = targetNodeId
    ? `确认重启节点 "${targetNodeId}" 的服务吗？这将短暂中断该节点的连接。`
    : '确认重启本节点服务吗？这将短暂中断当前连接。'
  showConfirm(
    confirmMessage,
    () => {
      restartGateway()
    },
    () => {},
    false
  )
}

async function restartGateway() {
  if (isRestartingGateway.value) {
    return
  }

  const targetNodeId = restartNodeId.value || 'master'
  
  try {
    isRestartingGateway.value = true
    const { host, port } = getGatewayAddress()
    
    // 发送重启请求，不等待响应结果
    fetchWithAuth(buildNodeHttpUrl(host, port, 'master', 'service/restart'), {
      method: 'POST',
      body: JSON.stringify({ 
        node_id: targetNodeId,
        restart_frontend: restartFrontendService.value
      })
    }).catch(() => {
      // 忽略请求错误（服务重启会导致连接中断）
    })
    
    // 请求发出即视为成功
    showToast(`已向节点 "${targetNodeId}" 发送重启请求`, 'success')
  } catch (error) {
    console.error('[SETTINGS] Failed to restart gateway:', error)
    showToast(error.message || '重启服务失败', 'error')
  } finally {
    // 延迟重置状态，防止用户重复点击
    setTimeout(() => {
      isRestartingGateway.value = false
    }, 3000)
  }
}

async function syncConfig() {
  if (isSyncingConfig.value) {
    return
  }

  try {
    isSyncingConfig.value = true
    const { host, port } = getGatewayAddress()
    const sourceNodeId = syncConfigSourceNode.value || 'master'

    // 自动选择除源节点外的所有节点作为目标
    const targetNodeIds = availableNodeOptions.value
      .map(node => node.node_id)
      .filter(id => id !== sourceNodeId)

    // 如果源节点不是 master，将 master 加入目标节点列表
    if (sourceNodeId !== 'master' && !targetNodeIds.includes('master')) {
      targetNodeIds.unshift('master')
    }

    if (targetNodeIds.length === 0) {
      showToast('没有其他节点可以同步', 'warning')
      return
    }
    
    const response = await fetchWithAuth(buildHttpUrl(host, port, 'config/sync'), {
      method: 'POST',
      body: JSON.stringify({
        source_node_id: sourceNodeId,
        target_node_ids: targetNodeIds,
        config_sections: syncConfigSections.value
      })
    })
    const result = await response.json()

    if (!response.ok || !result.success) {
      throw new Error(result.error?.message || '配置同步失败')
    }

    const successCount = result.data?.success_count || 0
    const totalCount = targetNodeIds.length
    
    if (successCount === totalCount) {
      showToast(`配置同步成功，已同步到 ${successCount} 个节点`, 'success')
    } else {
      showToast(`配置同步部分成功，成功 ${successCount}/${totalCount} 个节点`, 'warning')
    }
  } catch (error) {
    console.error('[SETTINGS] Failed to sync config:', error)
    showToast(error.message || '配置同步失败', 'error')
  } finally {
    isSyncingConfig.value = false
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
  const maxRetries = 12  // 最多重试12次
  const retryDelay = 2000 // 2秒重试间隔
  const connectionTimeout = 10000 // 10秒连接超时（适应Agent启动时间）
  
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
  
  const { host, port } = getGatewayAddress()
  const url = buildAgentWebSocketUrl(host, agentId, null, port, String(agent?.node_id || 'master').trim())
  
  connecting.value = true
  
  // 返回 Promise，等待连接真正建立
  return new Promise((resolve, reject) => {
    try {
      const ws = new WebSocket(url, buildWebSocketProtocols())
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
        
        
        // 标记连接已完成（在onclose中用于判断是否需要重试）
        ws._connectionCompleted = true
        
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

// 查询 Agent 状态（通过网关代理）
async function fetchAgentStatus(agent) {
  if (!agent || !agent.agent_id) {
    console.warn('[AGENT STATUS] Invalid agent:', agent)
    return 'running' // 默认返回 running
  }
  
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/status`))
    
    if (!response.ok) {
      console.warn(`[AGENT STATUS] Failed to fetch status for agent ${agent.agent_id}:`, response.status)
      return 'running' // 默认返回 running
    }
    
    const result = await response.json()
    // execution_status 是任务级别状态（running/waiting_multi/waiting_single）
    const executionStatus = result.execution_status || 'running'
    
    // 更新状态映射（存储对象格式）
    agentStatuses.value.set(agent.agent_id, {execution_status: executionStatus})

    // 当前 Agent 连接后根据 execution_status 恢复输入 UI
    if (agent.agent_id === currentAgentId.value) {
      if (executionStatus === 'waiting_single') {
        inputMode.value = 'single'
        nextTick(() => {
          singlelineInput.value?.focus()
        })
      } else if (executionStatus === 'waiting_multi') {
        inputMode.value = 'multi'
        nextTick(() => {
          multilineInput.value?.focus()
        })
      } else {
        inputMode.value = 'multi'
      }
    }
    
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
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${currentAgentId.value}/sessions`), {
      method: 'POST',
      body: JSON.stringify({ session_file: sessionFile, node_id: targetNodeId })
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
function getCreateAgentDirectoryNodeId() {
  return (newAgentNodeId.value || '').trim()
}

function resetDirectorySelectionState() {
  showDirDialog.value = false
  currentDirPath.value = ''
  dirList.value = []
  selectedDir.value = null
  dirSearchText.value = ''
  selectedDirIndex.value = -1
}

watch(newAgentNodeId, (newNodeId) => {
  newAgentDir.value = '~'
  resetDirectorySelectionState()
  // 切换节点时重新获取对应节点的模型组列表
  fetchModelGroups(newNodeId || 'master')
})

async function openDirDialog() {
  showDirDialog.value = true
  selectedDir.value = newAgentDir.value || '~'
  dirSearchText.value = '' // 清空搜索
  selectedDirIndex.value = -1
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
    const params = new URLSearchParams({ path })
    const nodeId = String(getCreateAgentDirectoryNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, nodeId, `directories?${params.toString()}`))
    
    if (!response.ok) {
      const error = await response.json()
      console.error('[DIR] 获取目录列表失败:', error)
      alert(`获取目录列表失败: ${error.error?.message || '未知错误'}`)
      return
    }
    
    const result = await response.json()
    if (result.success && result.data) {
      currentDirPath.value = result.data.current_path
      // 只显示目录，过滤掉文件（工作目录选择不需要显示文件）
      dirList.value = (result.data.items || []).filter(item => item.type === 'directory')
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
  dirSearchText.value = ''
  selectedDirIndex.value = -1
}

// 打开创建 Agent 弹窗
async function openCreateAgentModal() {
  // 先刷新模型组列表，确保获取最新的配置
  await Promise.all([
    fetchModelGroups(),
    fetchNodeStatus(),
  ])
  newAgentNodeId.value = ''
  newAgentDir.value = '~'
  resetDirectorySelectionState()
  showCreateAgentModal.value = true
}

// 获取模型组列表
async function fetchModelGroups(nodeId = 'master') {
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(nodeId || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'model-groups'))
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

async function fetchNodeStatus() {
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, 'master', 'node/status'))
    if (!response.ok) {
      console.warn('[NODE] 获取节点状态失败:', response.status)
      availableNodeOptions.value = []
      return
    }
    const result = await response.json()
    const nodes = Array.isArray(result?.data?.nodes) ? result.data.nodes : []
    availableNodeOptions.value = nodes
      .filter(node => node && String(node.node_id || '').trim())
      .map(node => ({
        ...node,
        node_id: String(node.node_id || '').trim(),
      }))
  } catch (error) {
    console.error('[NODE] 获取节点状态出错:', error)
    availableNodeOptions.value = []
  }
}

function formatNodeOptionLabel(node) {
  const nodeId = String(node?.node_id || '').trim()
  const status = String(node?.status || node?.runtime_status || '').trim()
  return status ? `${nodeId} (${status})` : nodeId
}

function getAgentNodeLabel(agent) {
  return String(agent?.node_id || '').trim() || 'master'
}

function getCurrentAgentNodeId() {
  return String(currentAgent.value?.node_id || '').trim()
}

async function createAgent() {
  if (!newAgentDir.value.trim()) return
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(newAgentNodeId.value || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'), {
      method: 'POST',
      body: JSON.stringify({
        agent_type: newAgentType.value,
        working_dir: newAgentDir.value,
        name: newAgentName.value || undefined,
        llm_group: newAgentModelGroup.value,
        worktree: newAgentType.value === 'codeagent' ? newCodeAgentWorktree.value : false,
        quick_mode: newAgentQuickMode.value,
        node_id: targetNodeId,
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
      const agent = {
        ...result.data,
        node_id: String(result.data?.node_id || '').trim() || 'master',
      }
      // 添加到列表开头（让后创建的 agent 排在前面）
      agentList.value.unshift(agent)
      // 关闭创建弹窗
      showCreateAgentModal.value = false
      newAgentDir.value = '~' // 重置为默认值
      newCodeAgentWorktree.value = false
      newAgentQuickMode.value = false
      newAgentNodeId.value = ''
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
    const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `completions/${currentAgent.value.agent_id}`))
    
    const result = await response.json()
    console.log('[COMPLETIONS] API response:', result)
    
    if (!response.ok) {
      alert(`获取补全列表失败: ${result.error?.message || result.detail || '未知错误'}`)
      return
    }
    
    if (result.success && result.data) {
      completions.value = sortCompletionItems(result.data)
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
    return sortCompletionItems(completions.value)
  }
  
  const search = completionSearch.value.toLowerCase()
  // 过滤原始补全项
  const filteredOriginal = completions.value.filter(item => {
    const displayText = String(item.display || '').toLowerCase()
    const descriptionText = String(item.description || '').toLowerCase()
    const valueText = String(item.value || '').toLowerCase()
    return displayText.includes(search) || descriptionText.includes(search) || valueText.includes(search)
  })
  
  // 合并文件补全结果（如果有搜索内容）
  if (fileCompletions.value.length > 0) {
    return sortCompletionItems([...filteredOriginal, ...fileCompletions.value])
  }
  
  return sortCompletionItems(filteredOriginal)
})

// 处理补全对话框的键盘事件
function handleCompletionKeydown(event) {
  const maxIndex = filteredCompletions.value.length - 1
  
  if (event.key === 'Escape') {
    // ESC 键关闭对话框，插入 @ 符号
    insertAtPosition('@', completionCursorPos.value)
    showCompletions.value = false
    selectedIndex.value = -1
    completionCursorPos.value = -1
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

// 在指定位置插入文本
function insertAtPosition(text, position) {
  const textarea = document.querySelector('.input-wrapper textarea')
  if (!textarea || position === -1) return
  
  const currentText = textarea.value
  // 在指定位置插入文本
  const newText = currentText.substring(0, position) + text + currentText.substring(position)
  inputText.value = newText
  
  // 更新 textarea 并设置光标位置
  textarea.value = newText
  const newCursorPos = position + text.length
  textarea.setSelectionRange(newCursorPos, newCursorPos)
  textarea.focus()
}

// 插入选中的补全
function insertCompletion(item) {
  const textarea = document.querySelector('.input-wrapper textarea')
  if (!textarea) return
  
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const text = textarea.value

  recordCompletionSelection(item)
  
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
  completionCursorPos.value = -1
}

// 获取 Agent 列表
async function fetchAgentList() {
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'))
    
    if (!response.ok) return
    
    const result = await response.json()
    console.log('[AGENT] List:', result)
    
    // 更新列表（后端返回格式: { success: true, data: agents }）
    if (result.success && result.data) {
      // 反转数组，让后创建的 agent 排在前面
      agentList.value = result.data.slice().reverse().map(agent => ({
        ...agent,
        node_id: String(agent?.node_id || '').trim() || 'master',
      }))
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

// 构造复制 Agent 的请求参数
function buildCopiedAgentPayload(agent, copiedName, targetNodeId = undefined) {
  return {
    agent_type: agent.agent_type,
    working_dir: agent.working_dir,
    name: copiedName,
    llm_group: agent.llm_group || 'default',
    worktree: agent.agent_type === 'codeagent' ? Boolean(agent.worktree) : false,
    quick_mode: Boolean(agent.quick_mode),
    node_id: targetNodeId || agent.node_id || undefined,
  }
}

// 复制 Agent
async function copyAgent(agent) {
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'), {
      method: 'POST',
      body: JSON.stringify(buildCopiedAgentPayload(agent, agent.name || undefined, targetNodeId))
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

// 批量复制 Agent
async function batchCopyAgents() {
  const selectedIds = Array.from(selectedAgents.value)
  if (selectedIds.length === 0) {
    showToast('请先选择要复制的 Agent', 'warning')
    return
  }
  const selectedAgentList = agentList.value.filter(agent => selectedAgents.value.has(agent.agent_id))
  try {
    let successCount = 0
    let failCount = 0
    for (const agent of selectedAgentList) {
      try {
        const { host, port } = getGatewayAddress()
        const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
        const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'), {
          method: 'POST',
          body: JSON.stringify(
            buildCopiedAgentPayload(agent, agent.name ? `${agent.name}_copy` : undefined, targetNodeId)
          )
        })
        if (response.ok) {
          successCount++
        } else {
          failCount++
        }
      } catch (error) {
        console.error(`[AGENT] Failed to copy agent ${agent.agent_id}:`, error)
        failCount++
      }
    }
    await fetchAgentList()
    selectedAgents.value.clear()
    selectedAgents.value = new Set()
    isBatchMode.value = false
    if (failCount === 0) {
      showToast(`成功复制 ${successCount} 个 Agent`, 'success')
    } else {
      showToast(`复制完成：成功 ${successCount} 个，失败 ${failCount} 个`, 'warning')
    }
  } catch (error) {
    console.error('[AGENT] Batch copy failed:', error)
    showToast('批量复制失败', 'error')
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
    
    const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agent.agent_id}`), {
      method: 'PATCH',
      body: JSON.stringify({ ...body, node_id: targetNodeId })
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
        const agent = agentList.value.find(item => item.agent_id === agentId)
        const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
        const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agentId}`), {
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
        
        // 清除该 Agent 的文件树状态
        fileTreeState.value.delete(agentId)
        fileTreeExpanded.value.delete(agentId)
        fileTreeLoading.value.delete(agentId)
        
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

// 批量删除 Agent
async function batchDeleteAgents() {
  const selectedIds = Array.from(selectedAgents.value)
  if (selectedIds.length === 0) {
    showToast('请先选择要删除的 Agent', 'warning')
    return
  }
  // 隐藏 agent 侧边栏，避免遮挡确认对话框（仅移动端）
  if (windowWidth.value <= 768) showAgentSidebar.value = false
  showConfirm(
    `确认删除选中的 ${selectedIds.length} 个 Agent？删除后将无法恢复，且会清除所有历史记录。`,
    async () => {
      try {
        let successCount = 0
        let failCount = 0
        for (const agentId of selectedIds) {
          try {
            const { host, port } = getGatewayAddress()
            const agent = agentList.value.find(item => item.agent_id === agentId)
            const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
            const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agentId}`), {
              method: 'DELETE'
            })
            const result = await response.json()
            if (response.ok && result.success) {
              successCount++
              // 清除该 Agent 的历史记录
              historyStorage.clearHistoryForAgent(agentId)
              // 清除该 Agent 的文件树状态
              fileTreeState.value.delete(agentId)
              fileTreeExpanded.value.delete(agentId)
              fileTreeLoading.value.delete(agentId)
              // 如果是当前 Agent，清空当前 Agent ID
              if (currentAgentId.value === agentId) {
                currentAgentId.value = null
                outputs.value = []
                historyOffset.value = 0
                hasMoreHistory.value = true
              }
            } else {
              failCount++
            }
          } catch (error) {
            console.error(`[AGENT] Failed to delete agent ${agentId}:`, error)
            failCount++
          }
        }
        // 刷新列表
        await fetchAgentList()
        // 清空选中状态并退出批量模式
        selectedAgents.value.clear()
        selectedAgents.value = new Set()
        isBatchMode.value = false
        // 显示结果提示
        if (failCount === 0) {
          showToast(`成功删除 ${successCount} 个 Agent`, 'success')
        } else {
          showToast(`删除完成：成功 ${successCount} 个，失败 ${failCount} 个`, 'warning')
        }
      } catch (error) {
        console.error('[AGENT] Batch delete failed:', error)
        showToast('批量删除失败', 'error')
      }
    }
  )
}

// 初始化 Agent 的文件树状态
function initFileTreeState(agentId) {
  if (!fileTreeState.value.has(agentId)) {
    fileTreeState.value.set(agentId, [])
    fileTreeExpanded.value.set(agentId, new Set())
    fileTreeLoading.value.set(agentId, new Set())
  }
}

// 加载文件树节点的子目录
async function loadFileTreeNode(agentId, node) {
  const loadingSet = fileTreeLoading.value.get(agentId)
  if (!loadingSet) return
  
  // 标记为加载中
  loadingSet.add(node.path)
  
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `directories?path=${encodeURIComponent(node.path)}`))
    
    if (!response.ok) {
      const error = await response.json()
      console.error('[FILETREE] 加载目录失败:', error)
      return
    }
    
    const result = await response.json()
    if (result.success && result.data) {
      // 转换为树节点格式
      const children = (result.data.items || []).map(item => {
        // 文件节点不需要 children 和 loaded 字段
        if (item.type === 'file') {
          return {
            name: item.name,
            path: item.path,
            type: 'file'
          }
        }
        // 目录节点需要 children 和 loaded 字段
        return {
          name: item.name,
          path: item.path,
          type: 'directory',
          expanded: false,
          loaded: false,
          children: []
        }
      })
      
      // 更新节点的子节点
      node.children = children
      node.loaded = true
    }
  } catch (error) {
    console.error('[FILETREE] 加载目录出错:', error)
  } finally {
    // 移除加载状态
    loadingSet.delete(node.path)
  }
}

// 初始化文件树（加载根目录）
async function initFileTree(agentId, rootPath) {
  initFileTreeState(agentId)
  
  // 创建根节点
  const rootNode = {
    name: rootPath.split('/').pop() || rootPath,
    path: rootPath,
    type: 'directory',
    expanded: false,
    loaded: false,
    children: []
  }
  
  // 加载根目录的内容
  await loadFileTreeNode(agentId, rootNode)
  
  // 保存到状态
  fileTreeState.value.set(agentId, [rootNode])
}

function flattenVisibleFileTreeNodes(nodes, depth = 0) {
  const visibleNodes = []

  for (const node of nodes) {
    visibleNodes.push({ node, depth })

    if (node.expanded && node.children && node.children.length > 0) {
      visibleNodes.push(...flattenVisibleFileTreeNodes(node.children, depth + 1))
    }
  }

  return visibleNodes
}

function getVisibleFileTreeNodes(agentId) {
  const treeNodes = fileTreeState.value.get(agentId) || []
  return flattenVisibleFileTreeNodes(treeNodes)
}

// 递归查找节点
function findNode(nodes, path) {
  for (const node of nodes) {
    if (node.path === path) {
      return node
    }
    if (node.children && node.children.length > 0) {
      const found = findNode(node.children, path)
      if (found) return found
    }
  }
  return null
}

// 切换节点展开/收缩
async function toggleNodeExpand(agentId, node) {
  const expandedSet = fileTreeExpanded.value.get(agentId)
  if (!expandedSet) return
  
  if (node.expanded) {
    // 收缩
    node.expanded = false
    expandedSet.delete(node.path)
  } else {
    // 展开
    node.expanded = true
    expandedSet.add(node.path)
    
    // 如果未加载过子节点，则加载
    if (!node.loaded) {
      await loadFileTreeNode(agentId, node)
    }
  }
}

// 切换当前工作的 Agent
async function switchAgent(agent) {
  console.log('[AGENT] switchAgent called with:', agent)
  
  // 移动端：切换agent后自动隐藏侧边栏（放在最前面，确保无论什么情况都执行）
  if (windowWidth.value <= 768) {
    console.log('[AGENT] Mobile mode: hiding sidebar')
    showAgentSidebar.value = false
  }
  
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
  console.log('[AGENT] Current sockets before switch:', [...sockets.value.keys()])
  console.log('[AGENT] Current agent statuses:', [...agentStatuses.value.keys()])
  
  // 清空输入状态
  lastInputRequest.value = null
  inputText.value = ''
  inputTip.value = ''
  inputMode.value = 'multi'
  
  // 更新当前 Agent ID
  currentAgentId.value = agent.agent_id
  console.log('[AGENT] Current agent ID updated to:', currentAgentId.value)
  
  // 重置历史偏移量和消息状态
  historyOffset.value = 0
  hasMoreHistory.value = true
  
  // 清空当前 Agent 的消息列表
  allOutputs.value.set(agent.agent_id, [])

  // 先加载历史消息，再连接 Agent
  console.log('[AGENT] Loading history before connecting...')
  await loadHistoryMessages(false)

  // 连接到目标 Agent（等待连接真正建立）
  try {
    // 切换后立即查询一次状态（即使 WebSocket 未连接）
    console.log('[AGENT] Fetching status after switch...')
    await fetchAgentStatus(agent)
    // 如果 Agent 已停止（已完成），不尝试连接 WebSocket
    console.log('[AGENT DEBUG] Checking agent.status:', agent.status)
    if (agent.status === 'stopped') {
      console.log('[AGENT] Agent is stopped (completed), skipping WebSocket connection')
      console.log('[AGENT DEBUG] windowWidth.value:', windowWidth.value, ', 768 threshold:', windowWidth.value <= 768)
      return
    }
    // 等待连接稳定（Agent启动需要时间，持续重试直到成功）
    let stableConnection = false
    let retryCount = 0
    // 移除重试次数限制，等待Agent完全启动
    
    while (!stableConnection) {
      await connectToAgent(agent)
      
      // 验证连接是否真的成功，并等待一小段时间确保连接稳定
      const ws = sockets.value.get(agent.agent_id)
      if (ws && ws.readyState === WebSocket.OPEN) {
        // 等待2000ms，确保连接稳定（Agent启动需要更长时间）
        await new Promise(resolve => setTimeout(resolve, 2000))
        
        // 再次检查连接是否仍然有效
        if (ws.readyState === WebSocket.OPEN) {
          console.log('[AGENT] Connection verified successfully')
          stableConnection = true
        } else {
          retryCount++
          console.warn(`[AGENT] Connection closed after ${retryCount} tries, retrying...`)
          // 等待2秒后继续重试
          await new Promise(resolve => setTimeout(resolve, 2000))
        }
      } else {
        retryCount++
        console.warn(`[AGENT] Connection failed after ${retryCount} tries, retrying...`)
        // 等待2秒后继续重试
        await new Promise(resolve => setTimeout(resolve, 2000))
      }
    }
    
    console.log(`[AGENT] Stable connection established after ${retryCount} retries`)
    console.log('[AGENT] Current sockets after connection:', [...sockets.value.keys()])
    
    // 最终检查WebSocket是否真正连接成功
    const ws = sockets.value.get(agent.agent_id)
    if (ws && ws.readyState === WebSocket.OPEN) {
      // 连接成功后再次查询状态，确保同步
      console.log('[AGENT] Fetching status after connection...')
      await fetchAgentStatus(agent)
      
      // 若历史为空，则检测可恢复的 session（通常是新创建的 Agent）
      const currentOutputs = allOutputs.value.get(agent.agent_id) || []
      if (currentOutputs.length === 0) {
        console.log('[AGENT] No history found, checking for recoverable sessions...')
        try {
          const { host, port } = getGatewayAddress()
          const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
          const sessionsResponse = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agent.agent_id}/sessions`))
          const sessionsData = await sessionsResponse.json()
          if (sessionsData.success && sessionsData.data && sessionsData.data.length > 0) {
            console.log('[AGENT] Found recoverable sessions:', sessionsData.data)
            // 显示 session 选择对话框
            availableSessions.value = sessionsData.data
            showSessionDialog.value = true
          } else {
            console.log('[AGENT] No recoverable sessions found')
          }
        } catch (error) {
          console.error('[AGENT] Failed to fetch sessions:', error)
        }
      } else {
        console.log('[AGENT] History already loaded, skipping session detection')
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
      // 创建当前 Agent 的流式消息
      const currentOutputs = allOutputs.value.get(targetAgentId) || []
      const streamingMessage = {
        output_type: 'STREAM',
        text: '',
        lang: 'markdown',
        agent_name: payload?.context?.agent_name || payload?.agent_name || '',
        model_name: payload?.context?.model_name || '',
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        context: payload?.context || {},
        isStreaming: true
      }
      streamingMessages.value.set(targetAgentId, streamingMessage)
      currentOutputs.push(streamingMessage)
      console.log('[STREAM] Created streaming message, total:', currentOutputs.length, 'agent:', targetAgentId)
    } else if (outputType === 'STREAM_CHUNK') {
      console.log('[STREAM] Chunk event:', payload)
      // 追加到当前 Agent 的流式消息
      const streamingMessage = streamingMessages.value.get(targetAgentId)
      if (streamingMessage) {
        streamingMessage.text += payload.text || ''
        // 使用 renderMessageHtml 确保流式消息和历史消息使用相同的渲染逻辑
        streamingMessage.html = renderMessageHtml(streamingMessage)
        // 仅当前 Agent 的流式消息触发滚动
        nextTick(() => {
          if (isCurrentAgent(targetAgentId) && outputList.value) {
            outputList.value.scrollTop = outputList.value.scrollHeight
          }
        })
      } else {
        console.warn('[STREAM] Received chunk but no streaming message found for agent:', targetAgentId)
      }
    } else if (outputType === 'STREAM_END') {
      console.log('[STREAM] End event:', payload)
      const streamingMessage = streamingMessages.value.get(targetAgentId)
      if (streamingMessage) {
        // 从当前 Agent 的 outputs 数组中删除流式消息
        const currentOutputs = allOutputs.value.get(targetAgentId) || []
        const index = currentOutputs.indexOf(streamingMessage)
        if (index !== -1) {
          currentOutputs.splice(index, 1)
          console.log('[STREAM] Removed streaming message from outputs for agent:', targetAgentId)
        }
        // 清除当前 Agent 的流式消息引用
        streamingMessages.value.delete(targetAgentId)
      } else {
        console.warn('[STREAM] Received end but no streaming message found for agent:', targetAgentId)
      }
    } else {
      // 普通输出
      appendOutput(payload, targetAgentId)
    }
  } else if (type === 'input_request') {
    console.log('[ws] input_request', payload)
    const requestAgentId = targetAgentId
    pendingInputAgentId.value = requestAgentId
    
    // 根据 mode 设置 agentStatuses
    if (requestAgentId && payload.mode) {
      const statusKey = payload.mode === 'multi' ? 'waiting_multi' : 'waiting_single'
      agentStatuses.value.set(requestAgentId, {execution_status: statusKey})
      console.log('[ws] Set agentStatuses based on input_request mode:', statusKey, 'for agent:', requestAgentId)
    }
    
    // 检查缓冲区是否有内容
    if (requestAgentId && inputBuffers.value.has(requestAgentId)) {
      // 完成信号 (__CTRL_C_PRESSED__) 只发送给多行输入
      const bufferedText = inputBuffers.value.get(requestAgentId)
      const isCompletionSignal = bufferedText === '__CTRL_C_PRESSED__'
      const isMultiLineRequest = payload.mode === 'multi'
      
      if (isCompletionSignal && !isMultiLineRequest) {
        // 完成信号不能发送给单行输入（如确认对话框），清空缓冲区
        console.log('[INPUT_REQUEST] Completion signal in buffer but request is single-line, discarding')
        inputBuffers.value.delete(requestAgentId)
      } else {
        // 普通输入或匹配的多行输入，发送缓冲区内容
        console.log('[INPUT_REQUEST] Found buffered input, auto-sending')
        inputBuffers.value.delete(requestAgentId)
        sendInputResult(bufferedText, payload.request_id, requestAgentId)
      }
      return
    }
    
    // 保存输入请求，用于重连后恢复
    lastInputRequest.value = payload
    inputTip.value = payload.tip || ''
    inputMode.value = payload.mode || 'multi'  // 默认多行
    inputText.value = payload.preset || inputText.value
    
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
      if (inputMode.value === 'multi') {
        multilineInput.value?.focus()
      } else {
        singlelineInput.value?.focus()
      }
      
      // 输入框显示后，如果之前在底部且请求属于当前 Agent，就滚动到底部
      if (isCurrentAgent(requestAgentId) && shouldScrollAfterInputShow && outputList.value) {
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
    pendingConfirmAgentId.value = targetAgentId
    showConfirm(
      payload.message || '请确认',
      () => {
        sendConfirmResult(true, targetAgentId)
      },
      () => {
        sendConfirmResult(false, targetAgentId)
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
    isCreatingTerminalSession.value = false
    const terminalId = payload?.terminal_id
    if (terminalId) {
      terminalSessions.value.push({
        terminal_id: terminalId,
        node_id: payload?.node_id || getCurrentAgentNodeId() || '',
        interpreter: payload?.interpreter || 'bash',
        working_dir: payload?.working_dir || '.',
        terminal: null,
        hostEl: null,
        fitAddon: null,
        resizeObserver: null,  // ResizeObserver 实例
        history: [],  // 保存历史输出，用于面板隐藏后再显示时恢复
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
    console.log('[ws] status_update targetAgentId:', targetAgentId, 'currentAgentId:', currentAgentId.value)
    // 更新 Agent 执行状态
    if (payload?.execution_status) {
      agentStatuses.value.set(targetAgentId, {execution_status: payload.execution_status})
      console.log('[ws] Agent execution status updated:', payload.execution_status, 'for agent:', targetAgentId)
      // 当当前 Agent 开始思考时，自动滚动到底部
      if (payload.execution_status === 'running' && isCurrentAgent(targetAgentId)) {
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
      html += `<td class="diff-line-num diff-old-num">${escapeHtml(String(old_line_num || ''))}</td>`
      
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
      html += `<td class="diff-line-num diff-new-num">${escapeHtml(String(new_line_num || ''))}</td>`
      
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
  const resolvedAgentId = agentId || payload?.agent_id || context.agent_id || currentAgentId.value
  
  const outputItem = {
    ...payload,
    html,
    timestamp: now,
    agent_name: agentName,
    non_interactive: nonInteractive,
    agent_id: resolvedAgentId,
  }
  
  console.log('[DEBUG] appendOutput outputItem:', outputItem)
  console.log('[DEBUG] output_type:', outputItem.output_type)
  console.log('[DEBUG] agent_name:', outputItem.agent_name)
  console.log('[DEBUG] Generated class:', `message-${outputItem.output_type?.toLowerCase()}`)
  
  // 确定目标 Agent ID：优先使用传入参数，其次使用消息自带 agent_id，最后回退到当前 Agent
  const targetAgentId = resolvedAgentId
  // 仅当前 Agent 的消息自动滚动到底部
  const shouldAutoScroll = isCurrentAgent(targetAgentId)
  
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
  
  // DOM更新后，仅当前 Agent 的消息自动滚动到底部
  // 使用双 nextTick + requestAnimationFrame 确保布局完全计算后再滚动
  nextTick(() => {
    nextTick(() => {
      requestAnimationFrame(() => {
        if (shouldAutoScroll && outputList.value) {
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
      const terminalContent = getTerminalBufferContent(termInfo.terminal, true)
      
      // 获取终端内容并保存
      try {
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

// ============ 历史输入记录管理 ============

// 保存输入到历史记录
function saveToHistory(text) {
  if (!text || !text.trim()) return
  
  // 避免保存重复的历史记录
  const lastHistory = inputHistory.value[0]
  if (lastHistory && lastHistory.trim() === text.trim()) {
    return
  }
  
  // 将新输入添加到历史记录开头
  inputHistory.value.unshift(text)
  
  // 限制历史记录数量
  if (inputHistory.value.length > MAX_INPUT_HISTORY_COUNT) {
    inputHistory.value.pop()
  }

  saveInputHistory()
  
  // 重置历史浏览状态
  historyIndex.value = -1
  currentTempInput.value = ''
}

// 翻阅历史记录
function navigateHistory(direction) {
  // direction: 'up' 或 'down'
  
  if (direction === 'up') {
    // 向上翻阅：加载更早的历史记录
    if (historyIndex.value < inputHistory.value.length - 1) {
      // 第一次翻阅时，保存当前正在编辑的内容
      if (historyIndex.value === -1) {
        currentTempInput.value = inputText.value
      }
      historyIndex.value++
      inputText.value = inputHistory.value[historyIndex.value]
    }
  } else if (direction === 'down') {
    // 向下翻阅：加载更新的历史记录
    if (historyIndex.value > -1) {
      historyIndex.value--
      if (historyIndex.value === -1) {
        // 回到最新状态，恢复临时编辑的内容
        inputText.value = currentTempInput.value
      } else {
        inputText.value = inputHistory.value[historyIndex.value]
      }
    }
  }
}

// 检查光标是否在第一行
function isCursorAtFirstLine(textarea) {
  const cursorPosition = textarea.selectionStart
  const textBeforeCursor = textarea.value.substring(0, cursorPosition)
  return !textBeforeCursor.includes('\n')
}

// 处理单行输入框的键盘事件
function handleSinglelineKeydown(event) {
  // Enter 键提交输入
  if (event.key === 'Enter') {
    event.preventDefault()
    submitInput()
    // 提交后自动切换回多行输入模式
    inputMode.value = 'multi'
    return
  }
}

// 检查光标是否在最后一行
function isCursorAtLastLine(textarea) {
  const cursorPosition = textarea.selectionEnd
  const textAfterCursor = textarea.value.substring(cursorPosition)
  return !textAfterCursor.includes('\n')
}

// 处理 textarea 的键盘事件
function handleTextareaKeydown(event) {
  // @ 键：打开补全列表
  if (event.key === '@') {
    event.preventDefault()
    completionCursorPos.value = event.target.selectionStart
    openCompletions()
    return
  }
  
  // Ctrl+Enter 提交输入
  if (event.ctrlKey && event.key === 'Enter') {
    event.preventDefault()
    submitInput()
    return
  }
  
  // Alt+T 触发终端命令执行
  // 使用 event.code 而不是 event.key 来避免大小写问题
  // event.code 在按键位置相同的情况下返回相同的值，不受大小写影响
  if (event.altKey && (event.code === 'KeyT' || event.key === 't' || event.key === 'T')) {
    event.preventDefault()
    event.stopPropagation() // 阻止事件冒泡
    inputText.value = '__ALT_T_PRESSED__'
    submitInput()
    return
  }
  
  // Ctrl+C 在等待多行输入且输入框为空时，触发完成功能
  if (event.ctrlKey && event.key === 'c') {
    const userInput = inputText.value.trim()
    const agentId = currentAgentId.value
    const statusData = agentStatuses.value.get(agentId)
    const executionStatus = statusData?.execution_status || 'running'
    
    // 只有在等待多行输入且输入框为空时才触发
    if (executionStatus === 'waiting_multi' && !userInput) {
      event.preventDefault()
      submitCompletion()
      return
    }
  }
  
  // 向上箭头：检查是否在第一行，是才触发历史
  if (event.key === 'ArrowUp') {
    const textarea = event.target
    if (isCursorAtFirstLine(textarea)) {
      event.preventDefault()
      navigateHistory('up')
    }
    return
  }
  
  // 向下箭头：检查是否在最后一行，是才触发历史
  if (event.key === 'ArrowDown') {
    const textarea = event.target
    if (isCursorAtLastLine(textarea)) {
      event.preventDefault()
      navigateHistory('down')
    }
    return
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

function submitInput() {
  const agentId = currentAgentId.value
  if (!agentId) {
    console.warn('[SUBMIT] No current agent ID, cannot submit input')
    return
  }
  
  // 单行输入模式：允许发送空字符串
  // 多行输入模式：不允许发送空字符串
  let userInput
  if (inputMode.value === 'single') {
    // 单行输入：不trim，允许空字符串
    userInput = inputText.value
  } else {
    // 多行输入：trim并检查空值
    userInput = inputText.value.trim()
    if (!userInput) {
      return
    }
  }
  
  // 获取当前运行状态
  const statusData = agentStatuses.value.get(agentId)
  const executionStatus = statusData?.execution_status || 'running'
  
  // 判断是发送到缓冲区还是直接发送
  // 单行输入模式：直接发送（后端正在等待）
  // 多行输入模式：只有当运行状态是 waiting_multi 时，才直接发送
  // 其他情况（running）保存到缓冲区
  if (inputMode.value === 'single' || executionStatus === 'waiting_multi') {
    // 后端正在等待输入，直接发送
    console.log('[SUBMIT] Sending input directly to backend (inputMode:', inputMode.value, ', execution_status:', executionStatus, ')')
    sendInputDirectly(userInput)
  } else {
    // 后端没有等待输入，保存到缓冲区
    console.log('[SUBMIT] Saving input to buffer (execution_status:', executionStatus, ')')
    appendToInputBuffer(agentId, userInput)
    appendOutput({
      output_type: 'system',
      agent_name: 'system',
      text: '✓ 输入已追加到缓冲区，等待后端请求',
      lang: 'text',
    })
  }
  
  // 保存到历史记录
  saveToHistory(userInput)
  
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
  
  // 添加确认对话框，防止误触
  showConfirm(
    '确定要发送完成信号吗？',
    () => {
      // 用户确认，发送 Ctrl+C 信号作为完成信号（与 CLI 模式按 Ctrl+C 行为一致）
      // 注意：完成信号只针对多行输入，单行输入（如确认对话框）不使用完成按钮
      if (executionStatus === 'waiting_multi') {
        // 后端正在等待多行输入，直接发送 Ctrl+C 信号
        console.log('[SUBMIT] Sending Ctrl+C signal (__CTRL_C_PRESSED__) to backend (execution_status: waiting_multi)')
        sendInputDirectly('__CTRL_C_PRESSED__')
      } else {
        // 后端没有等待输入或正在等待单行输入，将完成信号保存到缓冲区（与普通输入统一机制）
        console.log('[SUBMIT] Caching completion signal to buffer (execution_status:', executionStatus, ')')
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

function sendInputResult(text, requestId, agentId = null) {
  const targetAgentId = agentId || pendingInputAgentId.value || currentAgentId.value
  
  // 先将用户输入回显到聊天窗口
  console.log('[DEBUG] Buffered input payload:', {
    output_type: 'user_input',
    agent_name: 'user',
    text: text,
    lang: 'text',
    agent_id: targetAgentId,
  })
  appendOutput({
    output_type: 'user_input',
    agent_name: 'user',
    text: text,
    lang: 'text',
  }, targetAgentId)
  
  const message = {
    type: 'input_result',
    payload: {
      text: text,
      request_id: requestId,
    },
  }
  console.log('[ws] send input_result (from buffer)', message, 'agent:', targetAgentId)
  if (targetAgentId) {
    const ws = sockets.value.get(targetAgentId)
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
    } else {
      console.warn(`[SEND] No open WebSocket for agent ${targetAgentId}`)
    }
  }
  pendingInputAgentId.value = null
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

function loadBufferToInput() {
  const agentId = currentAgentId.value
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
  const agentId = currentAgentId.value
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
  console.log('[ws] send confirm_result', message, 'agent:', targetAgentId)
  if (targetAgentId) {
    const ws = sockets.value.get(targetAgentId)
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
    } else {
      console.warn(`[SEND] No open WebSocket for agent ${targetAgentId}`)
    }
  }
  pendingConfirmAgentId.value = null
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
        getTerminalBufferContent(termInfo.terminal, true)
      }
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
}

function closeTerminal(terminalId) {
  console.log(`[independent-terminal] Closing terminal ${terminalId}`)

  // 先获取 node_id（清理前）
  const closingSession = terminalSessions.value.find(t => t.terminal_id === terminalId)
  const nodeId = closingSession?.node_id || ""
  
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
    const payload = { terminal_id: terminalId }
    if (nodeId) {
      payload.node_id = nodeId
    }
    const message = {
      type: 'terminal_close',
      payload,
    }
    socket.value.send(JSON.stringify(message))
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
  const KEEP_VISIBLE = 100 // 至少保留100px可见区域
  return {
    minTop: KEEP_VISIBLE - terminalPanelRect.value.height, // 允许向上拖出，但保留底部100px
    minLeft: KEEP_VISIBLE - terminalPanelRect.value.width, // 允许向左拖出，但保留右侧100px
    maxLeft: window.innerWidth - KEEP_VISIBLE, // 允许向右拖出，但保留左侧100px
    maxTop: window.innerHeight - KEEP_VISIBLE, // 允许向下拖出，但保留顶部100px
  }
}

function ensureTerminalPanelInViewport() {
  const KEEP_VISIBLE = 100 // 至少保留100px可见区域
  const maxWidth = Math.max(window.innerWidth, TERMINAL_PANEL_MIN_WIDTH)
  const maxHeight = Math.max(window.innerHeight, TERMINAL_PANEL_MIN_HEIGHT)

  terminalPanelRect.value.width = clamp(terminalPanelRect.value.width, TERMINAL_PANEL_MIN_WIDTH, maxWidth)
  terminalPanelRect.value.height = clamp(terminalPanelRect.value.height, TERMINAL_PANEL_MIN_HEIGHT, maxHeight)

  // 允许部分拖出屏幕，但保留至少100px可见区域
  terminalPanelRect.value.left = clamp(
    terminalPanelRect.value.left,
    KEEP_VISIBLE - terminalPanelRect.value.width, // 允许向左拖出
    window.innerWidth - KEEP_VISIBLE // 允许向右拖出
  )
  terminalPanelRect.value.top = clamp(
    terminalPanelRect.value.top,
    KEEP_VISIBLE - terminalPanelRect.value.height, // 允许向上拖出
    window.innerHeight - KEEP_VISIBLE // 允许向下拖出
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

// 监听面板显示状态
watch(showEditorPanel, (visible) => {
  if (visible) {
    startEditorFileHeartbeat()
    return
  }

  stopEditorFileHeartbeat()
})

watch(activeEditorTabPath, () => {
  startEditorFileHeartbeat()
})

watch(showTerminalPanel, (newValue, oldValue) => {
  if (!newValue && oldValue) {
    stopTerminalPanelInteraction()
    console.log('[independent-terminal] Panel hiding, disabling ResizeObserver for all terminals')
    terminalSessions.value.forEach(session => {
      if (session.resizeObserver) {
        session.resizeObserver.disconnect()
      }
    })
  } else if (newValue && !oldValue) {
    ensureTerminalPanelInViewport()
    saveTerminalPanelRect()
    if (terminalSessions.value.length === 0 && !isCreatingTerminalSession.value) {
      createTerminal()
    }
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

// 全局键盘事件处理
function handleGlobalKeydown(event) {
  const isModifierPressed = event.ctrlKey || event.metaKey

  // Ctrl/Cmd + S 保存当前编辑器标签
  if (isModifierPressed && event.key === 's') {
    if (showEditorPanel.value && activeEditorTab.value && !activeEditorTab.value.loading) {
      event.preventDefault()
      saveActiveEditorTab()
    }
    return
  }

  // Ctrl/Cmd + E 打开/隐藏编辑器面板
  if (isModifierPressed && event.code === 'KeyE') {
    event.preventDefault()
    if (showEditorPanel.value) {
      closeEditorPanel()
    } else {
      showEditorPanel.value = true
    }
    return
  }

  // Ctrl + A 打开/隐藏 Agent 侧边栏
  if (event.ctrlKey && event.key === 'a') {
    // 如果在输入框中，不触发快捷键（允许默认的全选行为）
    const tagName = event.target.tagName.toLowerCase()
    if (tagName === 'textarea' || tagName === 'input') {
      return
    }
    
    event.preventDefault()
    
    // 切换 Agent 侧边栏显示状态
    showAgentSidebar.value = !showAgentSidebar.value
    console.log('[app] Toggle agent sidebar:', showAgentSidebar.value)
  }
  
  // Ctrl + ` 打开/隐藏终端面板
  if (event.ctrlKey && event.key === '`') {
    event.preventDefault()
    
    // 切换终端面板显示状态
    if (socket.value) {
      showTerminalPanel.value = !showTerminalPanel.value
      console.log('[app] Toggle terminal panel:', showTerminalPanel.value)
    }
  }

  // Alt + T 在 textarea 中切换代码编辑器
  if (event.altKey && event.key === 't') {
    const tagName = event.target.tagName.toLowerCase()
    if (tagName === 'textarea') {
      event.preventDefault()
      event.stopPropagation()
      // 手动调用 textarea 的 keydown 处理
      handleTextareaKeydown(event)
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

watch(showEditorPanel, async (visible) => {
  if (visible) {
    ensureEditorPanelInViewport()
    await nextTick()
    ensureMonacoEditor()
    if (activeEditorTabPath.value) {
      activateEditorTab(activeEditorTabPath.value)
    }
    nextTick(() => layoutMonacoEditor())
  } else {
    stopEditorPanelInteraction()
  }
})

watch(activeEditorTabPath, async (path) => {
  if (!path) return
  await nextTick()
  ensureMonacoEditor()
  activateEditorTab(path)
})

onMounted(() => {
  // 不再在页面加载时创建终端，改为动态创建
  console.log('[app] Mounted')

  updateViewportHeight()
  visualViewportResizeHandler = () => {
    updateViewportHeight()
  }
  window.visualViewport?.addEventListener('resize', visualViewportResizeHandler)

  inputHistory.value = loadInputHistory()
  
  // 已登录时才启动 Agent 列表刷新，避免未获取 token 前向后端发送请求
  if (hasAuthToken()) {
    startAgentListRefresh()
  }
  
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
  
  // 添加全局键盘事件监听（在捕获阶段处理 Ctrl+T 等快捷键）
  document.addEventListener('keydown', handleGlobalKeydown, { capture: true })
  console.log('[app] Global keyboard listener added (capture mode)')
  
  // 监听窗口resize事件
  handleResize = () => {
    windowWidth.value = window.innerWidth
    updateViewportHeight()
    ensureAgentSidebarWidthInBounds()
    ensureEditorPanelInViewport()
    ensureTerminalPanelInViewport()
    saveAgentSidebarWidth()
    saveEditorPanelRect()
    saveTerminalPanelRect()
    layoutMonacoEditor()

    const activeSession = terminalSessions.value.find(session => session.terminal_id === activeTerminalId.value)
    if (activeSession && activeSession.fitAddon && activeSession.terminal) {
      activeSession.fitAddon.fit()
      sendTerminalResize(activeSession.terminal_id, activeSession.terminal.rows, activeSession.terminal.cols)
    }
  }
  window.addEventListener('resize', handleResize)
  console.log('[app] Resize listener added')
  
  // 添加beforeunload监听
  window.addEventListener('beforeunload', handleBeforeUnload)
  console.log('[app] Beforeunload listener added')
  
  // 移动端：监听返回键（popstate事件）
  handlePopState = () => {
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
  console.log('[app] onUnmounted', {
    hasSocket: !!socket.value,
    socketState: socket.value?.readyState,
    connecting: connecting.value,
  })
  stopAgentSidebarResize()
  stopEditorPanelInteraction()
  stopEditorFileHeartbeat()
  window.visualViewport?.removeEventListener('resize', visualViewportResizeHandler)

  if (monacoEditor) {
    monacoEditor.dispose()
    monacoEditor = null
  }
  editorModels.forEach(model => model.dispose())
  editorModels.clear()

  // 移除全局键盘事件监听
  document.removeEventListener('keydown', handleGlobalKeydown, { capture: true })
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
  height: var(--app-height, 100vh);
  min-height: 100vh;
  min-height: 100dvh;
  margin: 0;
  padding: 0;
  overflow: hidden;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

#app {
  width: 100vw;
  height: var(--app-height, 100vh);
  min-height: 100vh;
  min-height: 100dvh;
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

/* Side by side Diff 样式 */
.diff-side-by-side {
  background: #1a1f2e;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
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
  table-layout: fixed;
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
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  width: 50%;
  max-width: 50%;
  vertical-align: top;
  box-sizing: border-box;
}

.diff-content code {
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.2;
  background: transparent;
  padding: 0;
  white-space: inherit;
  word-break: inherit;
  overflow-wrap: inherit;
}

.diff-deleted {
  background: rgba(248, 81, 73, 0.7);
  color: #fff;
}

.diff-deleted code {
  background: inherit;
}

.diff-added {
  background: rgba(63, 185, 80, 0.7);
  color: #fff;
}

.diff-added code {
  background: inherit;
}

.diff-error {
  color: #f85149;
  padding: 8px 12px;
  font-weight: 600;
}

/* 移动端 Diff 适配 */
@media (max-width: 768px) {
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

<style scoped>
/* 动画定义 */

/* 全局布局 */
.app {
  display: flex;
  flex-direction: row; /* 改为左右布局 */
  height: var(--app-height, 100vh);
  min-height: 100vh;
  min-height: 100dvh;
  width: 100vw;
  margin: 0;
  padding: 0;
  padding-left: env(safe-area-inset-left, 0px);
  padding-right: env(safe-area-inset-right, 0px);
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
  padding-top: calc(14px + env(safe-area-inset-top, 0px));
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

.editor-panel {
  position: fixed;
  background: rgba(22, 27, 34, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  user-select: none;
}

.editor-panel-dragging {
  transition: none;
}

.editor-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(13, 17, 23, 0.9);
  cursor: move;
  gap: 10px;
  min-height: 36px;
}

.editor-panel-title-group {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.editor-panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.editor-panel-subtitle {
  font-size: 11px;
  color: #8b949e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}

.editor-panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.editor-tabs {
  display: flex;
  align-items: stretch;
  gap: 2px;
  padding: 4px 4px 0;
  background: rgba(13, 17, 23, 0.92);
  overflow-x: auto;
}

.editor-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 220px;
  padding: 6px 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-bottom: none;
  border-radius: 6px 6px 0 0;
  background: rgba(110, 118, 129, 0.16);
  color: #8b949e;
  cursor: pointer;
  font-size: 12px;
  line-height: 1.2;
}

.editor-tab.active {
  background: #0d1117;
  color: #e6edf3;
}

.editor-tab-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.editor-tab-dirty {
  color: #f2cc60;
  font-size: 10px;
}

.editor-tab-close {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  padding: 0;
}

.editor-panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 34px;
  padding: 0 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(22, 27, 34, 0.98);
}

.editor-toolbar-status {
  font-size: 12px;
  color: #8b949e;
}

.editor-toolbar-status.error {
  color: #f85149;
}

.editor-toolbar-spacer {
  flex: 1;
}

.editor-edit-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: none;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease-out;
  background: rgba(110, 118, 129, 0.2);
  color: #8b949e;
  backdrop-filter: blur(20px);
}

.editor-edit-toggle:hover {
  background: rgba(110, 118, 129, 0.3);
}

.editor-edit-toggle:active {
  transform: scale(0.96);
}

.editor-edit-toggle.editable {
  background: rgba(35, 197, 94, 0.2);
  color: #4ade80;
}

.editor-edit-toggle.editable:hover {
  background: rgba(35, 197, 94, 0.3);
}

.editor-edit-toggle-icon {
  font-size: 12px;
}

.editor-edit-toggle-text {
  font-size: 11px;
  letter-spacing: 0.02em;
}

.editor-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  background: #0d1117;
}

.editor-activity-bar {
  width: 44px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(1, 4, 9, 0.96);
}

.editor-activity-button {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #8b949e;
  cursor: pointer;
  transition: all 0.15s ease-out;
}

.editor-activity-button:hover,
.editor-activity-button.active {
  color: #e6edf3;
  background: rgba(56, 139, 253, 0.18);
  border-color: rgba(56, 139, 253, 0.32);
}

.editor-sidebar {
  width: 320px;
  min-width: 280px;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(13, 17, 23, 0.98);
}

.editor-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.editor-sidebar-title {
  font-size: 12px;
  font-weight: 600;
  color: #e6edf3;
}

.editor-sidebar-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor-file-tree-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.editor-file-tree-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.editor-sidebar-placeholder {
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 10px;
  padding: 20px;
  color: #8b949e;
}

.editor-sidebar-placeholder-icon {
  font-size: 22px;
}

.editor-sidebar-placeholder-text {
  font-size: 12px;
  line-height: 1.6;
}

.editor-global-search-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.editor-global-search-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid rgba(139, 148, 158, 0.35);
  border-radius: 6px;
  background: rgba(22, 27, 34, 0.9);
  color: #e6edf3;
  font-size: 12px;
  box-sizing: border-box;
}

.editor-global-search-input:focus {
  outline: none;
  border-color: rgba(56, 139, 253, 0.72);
}

.editor-global-search-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.editor-global-search-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #c9d1d9;
}

.editor-global-search-actions {
  display: flex;
  gap: 8px;
}

.editor-global-search-btn {
  min-width: 30px;
  width: 30px;
  height: 30px;
  font-size: 15px;
}

.editor-global-search-results {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

.editor-global-search-summary {
  margin-bottom: 10px;
  font-size: 12px;
  color: #8b949e;
}

.editor-global-search-empty {
  font-size: 12px;
  color: #8b949e;
}

.editor-global-search-file-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.editor-global-search-file-path {
  font-size: 12px;
  font-weight: 600;
  color: #79c0ff;
  cursor: pointer;
  word-break: break-all;
}

.editor-global-search-file-count {
  margin-left: 4px;
  color: #8b949e;
}

.editor-global-search-match {
  width: 100%;
  display: flex;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  background: rgba(22, 27, 34, 0.85);
  color: #c9d1d9;
  text-align: left;
  cursor: pointer;
}

.editor-global-search-match:hover {
  border-color: rgba(56, 139, 253, 0.3);
  background: rgba(30, 41, 59, 0.72);
}

.editor-global-search-line {
  flex: 0 0 auto;
  min-width: 32px;
  font-size: 11px;
  color: #8b949e;
}

.editor-global-search-text {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.editor-global-search-text mark {
  background: rgba(242, 204, 96, 0.32);
  color: #f2cc60;
}

.editor-panel-content {
  flex: 1;
  display: flex;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  user-select: text;
}

.editor-panel-content-main {
  flex: 1;
  padding: 0;
  min-width: 0;
  min-height: 0;
  background: #0d1117;
}

.editor-monaco-container {
  width: 100%;
  height: 100%;
}

.editor-placeholder {
  margin: auto;
  text-align: center;
  color: #8b949e;
  max-width: 280px;
  padding: 24px;
}

.editor-placeholder-icon {
  font-size: 36px;
  margin-bottom: 12px;
}

.editor-placeholder-title {
  font-size: 15px;
  font-weight: 600;
  color: #e6edf3;
  margin-bottom: 8px;
}

.editor-placeholder-text {
  font-size: 13px;
  line-height: 1.6;
}

.editor-resize-handle {
  position: absolute;
  z-index: 2;
}

.editor-resize-n,
.editor-resize-s {
  left: 10px;
  right: 10px;
  height: 10px;
}

.editor-resize-e,
.editor-resize-w {
  top: 10px;
  bottom: 10px;
  width: 10px;
}

.editor-resize-n {
  top: -5px;
  cursor: n-resize;
}

.editor-resize-s {
  bottom: -5px;
  cursor: s-resize;
}

.editor-resize-e {
  right: -5px;
  cursor: e-resize;
}

.editor-resize-w {
  left: -5px;
  cursor: w-resize;
}

.editor-resize-ne,
.editor-resize-nw,
.editor-resize-se,
.editor-resize-sw {
  width: 14px;
  height: 14px;
}

.editor-resize-ne {
  top: -6px;
  right: -6px;
  cursor: ne-resize;
}

.editor-resize-nw {
  top: -6px;
  left: -6px;
  cursor: nw-resize;
}

.editor-resize-se {
  right: -6px;
  bottom: -6px;
  cursor: se-resize;
}

.editor-resize-sw {
  left: -6px;
  bottom: -6px;
  cursor: sw-resize;
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
  padding: 0;
  color: #8b949e;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
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
  position: relative;
  width: 320px;
  min-width: 0;
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

.agent-sidebar-resizing {
  user-select: none;
}

.agent-sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: -4px;
  width: 8px;
  height: 100%;
  cursor: ew-resize;
  z-index: 5;
}

.agent-sidebar-resize-handle::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 2px;
  transform: translateX(-50%);
  background: transparent;
  transition: background 0.15s ease;
}

.agent-sidebar-resize-handle:hover::after,
.agent-sidebar-resizing .agent-sidebar-resize-handle::after {
  background: rgba(88, 166, 255, 0.6);
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

.agent-item.selected {
  background: rgba(139, 92, 246, 0.15);
  border-color: rgba(139, 92, 246, 0.4);
}

.agent-checkbox {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.agent-checkbox input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: #58a6ff;
}

.batch-actions-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: rgba(22, 27, 34, 0.9);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  gap: 12px;
}

.batch-actions-info {
  font-size: 13px;
  color: #8b949e;
}

.batch-actions-buttons {
  display: flex;
  gap: 8px;
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

.agent-status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-left: 8px;
  flex-shrink: 0;
}

.agent-status-dot.running {
  background: #3fb950;
  box-shadow: 0 0 0 2px rgba(63, 185, 80, 0.2);
}

.agent-status-dot.stopped {
  background: #f85149;
  box-shadow: 0 0 0 2px rgba(248, 81, 73, 0.2);
}

.agent-status-dot.waiting_multi {
  background: #d29922;
  box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.2);
}

.agent-status-dot.waiting_single {
  background: #f85149;
  box-shadow: 0 0 0 2px rgba(248, 81, 73, 0.2);
}

.agent-llm-group {
  font-size: 11px;
  color: #666;
  background: rgba(108, 117, 125, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
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

.tree-node {
  margin: 2px 0;
}

.tree-node-content {
  display: flex;
  align-items: center;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.2s ease;
  user-select: none;
}

.tree-node-content:hover {
  background: rgba(255, 255, 255, 0.08);
}

.tree-node-icon {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 6px;
  color: #6e7681;
  transition: transform 0.2s ease;
  font-size: 12px;
}

.tree-node-icon.expand-arrow {
  margin-right: 4px;
  color: #8b949e;
}

.tree-node-icon.expand-arrow.expanded {
  transform: rotate(90deg);
}

.tree-node-icon.folder-icon {
  color: #58a6ff;
}

.tree-node-icon.file-icon {
  color: #8b949e;
}

.tree-node-text {
  font-size: 13px;
  color: #e6edf3;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tree-node-text.directory {
  color: #58a6ff;
  font-weight: 500;
}

.tree-node-text.file {
  color: #c9d1d9;
}

.tree-children {
  margin-left: 16px;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  padding-left: 4px;
}

.tree-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: #8b949e;
  font-size: 12px;
}

.tree-loading-icon {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(139, 148, 158, 0.3);
  border-top-color: #8b949e;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.tree-empty {
  padding: 12px;
  text-align: center;
  color: #6e7681;
  font-size: 12px;
  font-style: italic;
}

@media (max-width: 768px) {
  .tree-node-content {
    padding: 5px 6px;
  }
  .tree-node-icon {
    width: 14px;
    height: 14px;
    font-size: 11px;
  }
  .tree-node-text {
    font-size: 12px;
  }
  .tree-children {
    margin-left: 12px;
  }
}

/* 创建 Agent 弹窗 */
.create-agent-modal {
  max-width: 400px;
  width: 90%;
  max-height: calc(var(--app-height, 100vh) - 40px);
  overflow-y: auto;
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
  padding-left: max(20px, env(safe-area-inset-left, 0px));
  padding-right: max(20px, env(safe-area-inset-right, 0px));
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
  align-items: stretch;
  text-align: left;
  position: relative;
  min-width: 0;
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

.message-body.markdown-content :deep(.plantuml-block) {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 12px 0;
  padding: 12px;
  border: 1px solid rgba(139, 148, 158, 0.25);
  border-radius: 10px;
  background: rgba(13, 17, 23, 0.35);
}

.message-body.markdown-content :deep(.plantuml-notice) {
  font-size: 12px;
  color: #8b949e;
}

.message-body.markdown-content :deep(.plantuml-link) {
  display: inline-flex;
  align-self: flex-start;
  max-width: 100%;
  color: #58a6ff;
  text-decoration: none;
}

.message-body.markdown-content :deep(.plantuml-link:hover) {
  text-decoration: underline;
}

.message-body.markdown-content :deep(.plantuml-image) {
  display: block;
  max-width: 100%;
  height: auto;
  background: #ffffff;
  border-radius: 6px;
}

.message-body.markdown-content :deep(.plantuml-source summary) {
  cursor: pointer;
  color: #8b949e;
}

/* 表格样式 - 排除 diff-table */
.message-body.markdown-content :deep(table:not(.diff-table)) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.message-body.markdown-content :deep(table:not(.diff-table) th),
.message-body.markdown-content :deep(table:not(.diff-table) td) {
  border: 1px solid rgba(255, 255, 255, 0.2);
  padding: 8px 12px;
  text-align: left;
}

.message-body.markdown-content :deep(table:not(.diff-table) th) {
  background: rgba(255, 255, 255, 0.05);
  font-weight: 600;
}

.message-body.markdown-content :deep(table:not(.diff-table) tr:nth-child(even)) {
  background: rgba(255, 255, 255, 0.02);
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
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: rgba(13, 17, 23, 0.6);
  /* max-height 由动态样式控制 */
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
  display: block;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 16px;
  margin: 0;
  overflow-x: auto;
  overflow-y: auto;
  color: #c9d1d9;
  /* 字体由父容器的动态样式控制 */
  white-space: pre;
  /* 移除 word-break: break-all，让长行可以横向滚动 */
  /* 移除 flex: 1，高度由父容器控制 */
  /* 继承父容器的字体设置 */
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
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

.confirm-btn.default {
  background: #238636;
  border-color: rgba(255, 255, 255, 0.2);
  font-weight: 700;
}

.confirm-btn.default:hover {
  background: #2ea043;
  border-color: rgba(255, 255, 255, 0.25);
}

/* 输入区 */
.input-area {
  background: rgba(22, 27, 34, 0.9);
  border-top: 0.5px solid rgba(255, 255, 255, 0.08);
  padding-bottom: env(safe-area-inset-bottom, 0px);
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

/* 缓存管理面板 */
.buffer-modal {
  max-width: min(720px, 100%);
  padding: 0;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
  animation: slideDown 0.2s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.buffer-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: rgba(35, 134, 54, 0.1);
  border-bottom: 1px solid rgba(48, 54, 61, 0.6);
}

.buffer-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #3fb950;
  display: flex;
  align-items: center;
  gap: 6px;
}

.buffer-panel-actions {
  display: flex;
  gap: 8px;
}

.buffer-panel-btn {
  padding: 6px 12px;
  background: rgba(48, 54, 61, 0.8);
  border: 1px solid rgba(48, 54, 61, 0.8);
  border-radius: 6px;
  color: #8b949e;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.buffer-panel-btn:hover {
  background: rgba(56, 139, 253, 0.15);
  border-color: rgba(56, 139, 253, 0.5);
  color: #58a6ff;
}

.buffer-panel-btn.close-btn:hover {
  background: rgba(248, 81, 73, 0.15);
  border-color: rgba(248, 81, 73, 0.5);
  color: #f85149;
}

.buffer-panel-content {
  padding: 0;
  display: flex;
  flex-direction: column;
}

.buffer-edit-textarea {
  width: 100%;
  min-height: 220px;
  max-height: min(60vh, 520px);
  background: rgba(13, 17, 23, 0.8);
  border: none;
  padding: 14px 16px;
  color: #e6edf3;
  font-size: 14px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  resize: vertical;
  box-sizing: border-box;
  outline: none;
}

.buffer-edit-textarea::placeholder {
  color: #8b949e;
}

.buffer-panel-footer {
  padding: 12px 16px;
  background: rgba(13, 17, 23, 0.6);
  border-top: 1px solid rgba(48, 54, 61, 0.6);
  display: flex;
  justify-content: flex-end;
}

.buffer-save-btn {
  padding: 8px 16px;
  background: rgba(56, 139, 253, 0.15);
  border: 1px solid rgba(56, 139, 253, 0.5);
  border-radius: 6px;
  color: #58a6ff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.buffer-save-btn:hover:not(:disabled) {
  background: rgba(56, 139, 253, 0.25);
  border-color: rgba(56, 139, 253, 0.8);
  transform: translateY(-1px);
}

.buffer-save-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .buffer-panel {
    margin-top: 6px;
    border-radius: 10px;
  }
  
  .buffer-modal {
    width: 100%;
    max-width: 100%;
    max-height: min(80vh, 100%);
    border-radius: 12px;
  }

  .buffer-panel-header {
    padding: 10px 12px;
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }
  
  .buffer-panel-actions {
    width: 100%;
    justify-content: space-between;
  }
  
  .buffer-panel-btn {
    padding: 8px 12px;
    font-size: 13px;
    flex: 1;
    text-align: center;
  }
  
  .buffer-edit-textarea {
    min-height: 180px;
    max-height: min(55vh, 420px);
    font-size: 14px;
  }
  
  .buffer-panel-footer {
    padding: 10px 12px;
  }
  
  .buffer-save-btn {
    width: 100%;
    padding: 10px 16px;
  }
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

.connect-modal h2 {
  margin: 0 0 24px 0;
  font-size: 21px;
  font-weight: 600;
  color: #e6edf3;
  letter-spacing: -0.02em;
}

/* Settings Modal - 更宽的布局以容纳更多配置项 */
.settings-modal {
  max-width: 640px;
  max-height: 80vh;
  overflow-y: auto;
}

.settings-modal h2 {
  margin: 0 0 24px 0;
  font-size: 24px;
  font-weight: 700;
  color: #e6edf3;
  letter-spacing: -0.03em;
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

.form-group select {
  width: 100%;
  padding: 11px 14px;
  background: rgba(13, 17, 23, 0.8);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%239ca3af' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
  padding-right: 36px;
}

.form-group select:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background-color: rgba(13, 17, 23, 0.9);
}

.form-group select option {
  background: #161b22;
  color: #e6edf3;
  padding: 8px;
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



/* 移动端适配 */
@media (max-width: 768px) {
  .app {
    background: #0d1117;
  }
  
  .app-header {
    padding: 12px 16px;
    padding-top: calc(12px + env(safe-area-inset-top, 0px));
    padding-left: max(16px, env(safe-area-inset-left, 0px));
    padding-right: max(16px, env(safe-area-inset-right, 0px));
  }
  .header-title h1 {
    font-size: 16px;
  }
  
  .messages {
    padding: 12px;
    padding-left: max(12px, env(safe-area-inset-left, 0px));
    padding-right: max(12px, env(safe-area-inset-right, 0px));
    padding-bottom: max(12px, env(safe-area-inset-bottom, 0px));
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

  .input-area {
    padding-left: env(safe-area-inset-left, 0px);
    padding-right: env(safe-area-inset-right, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
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
  background: rgba(13, 17, 23, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.terminal-panel-dragging {
  user-select: none;
}

.terminal-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(22, 27, 34, 0.95);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px 8px 0 0;
  cursor: move;
  min-height: 36px;
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
  position: relative;
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
  color: #8b949e;
  font-size: 14px;
}

.terminal-host-wrapper {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.terminal-host {
  width: 100%;
  height: 100%;
}

/* 终端调整大小手柄 */
.terminal-resize-handle {
  position: absolute;
  z-index: 2;
}

.terminal-resize-n,
.terminal-resize-s {
  left: 8px;
  right: 8px;
  height: 8px;
}

.terminal-resize-n {
  top: -4px;
  cursor: ns-resize;
}

.terminal-resize-s {
  bottom: -4px;
  cursor: ns-resize;
}

.terminal-resize-e,
.terminal-resize-w {
  top: 8px;
  bottom: 8px;
  width: 8px;
}

.terminal-resize-e {
  right: -4px;
  cursor: ew-resize;
}

.terminal-resize-w {
  left: -4px;
  cursor: ew-resize;
}

.terminal-resize-ne,
.terminal-resize-nw,
.terminal-resize-se,
.terminal-resize-sw {
  width: 12px;
  height: 12px;
}

.terminal-resize-ne {
  top: -6px;
  right: -6px;
  cursor: nesw-resize;
}

.terminal-resize-nw {
  top: -6px;
  left: -6px;
  cursor: nwse-resize;
}

.terminal-resize-se {
  right: -6px;
  bottom: -6px;
  cursor: nwse-resize;
}

.terminal-resize-sw {
  left: -6px;
  bottom: -6px;
  cursor: nesw-resize;
}

/* 移动端隐藏调整大小手柄 */
@media (max-width: 768px) {
  .terminal-resize-handle {
    display: none !important;
  }
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
  .create-agent-modal {
    max-height: calc(100vh - 32px);
    -webkit-overflow-scrolling: touch;
  }

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
  
  .editor-panel {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    width: 100vw !important;
    height: var(--app-height, 100vh) !important;
    border-radius: 0 !important;
    border: none !important;
    z-index: 2000 !important;
  }

  .editor-panel-header {
    cursor: default;
    padding: 10px 12px;
  }

  .editor-panel-subtitle {
    max-width: none;
  }

  .editor-panel-toolbar {
    padding: 0 10px;
  }

  .editor-panel-content,
  .editor-panel-content-main {
    min-height: 0;
  }

  .editor-resize-handle {
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
  .agent-checkbox input[type="checkbox"] {
    width: 20px;
    height: 20px;
  }

  .batch-actions-bar {
    padding: 10px 12px;
    flex-direction: column;
    gap: 8px;
  }

  .batch-actions-info {
    font-size: 12px;
  }

  .batch-actions-buttons {
    width: 100%;
    justify-content: flex-end;
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
  /* 已移到全局样式中，因v-html插入的内容无法使用scoped样式 */
}

/* ========== Toggle Switch 样式 ========== */
.toggle-wrapper {
  display: flex !important;
  align-items: center !important;
  justify-content: flex-start;
  gap: 16px;
  padding: 16px 20px;
  background: rgba(28, 28, 30, 0.6);
  backdrop-filter: blur(40px) saturate(150%);
  -webkit-backdrop-filter: blur(40px) saturate(150%);
  border: 1px solid rgba(0, 0, 0, 0.6);
  outline: 1px solid rgba(113, 113, 122, 0.4);
  outline-offset: -1px;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toggle-wrapper:hover {
  backdrop-filter: blur(60px) saturate(180%);
  -webkit-backdrop-filter: blur(60px) saturate(180%);
  border-color: rgba(0, 122, 255, 0.3);
  outline-color: rgba(0, 122, 255, 0.4);
}

.toggle-wrapper:active {
  transform: scale(0.98);
}

.toggle-switch {
  position: relative;
  display: block;
  width: 52px;
  height: 30px;
  flex-shrink: 0;
  cursor: pointer;
  margin: 0;
  padding: 0;
  line-height: 0;
}

.toggle-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(28, 28, 30, 0.6);
  backdrop-filter: blur(40px) saturate(150%);
  -webkit-backdrop-filter: blur(40px) saturate(150%);
  border: 1px solid rgba(0, 0, 0, 0.6);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  border-radius: 15px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  
  /* 外描边效果 */
  outline: 1px solid rgba(113, 113, 122, 0.4);
  outline-offset: -1px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 24px;
  width: 24px;
  left: 3px;
  bottom: 3px;
  background-color: rgba(255, 255, 255, 0.4);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 50%;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.toggle-input:checked + .toggle-slider {
  background: linear-gradient(135deg, #007AFF 0%, #0056CC 100%);
  border-color: rgba(0, 122, 255, 0.6);
  box-shadow: 0 4px 16px rgba(0, 122, 255, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  outline-color: rgba(0, 122, 255, 0.5);
}

.toggle-input:checked + .toggle-slider:before {
  transform: translateX(22px);
  background-color: #ffffff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  border-color: rgba(0, 122, 255, 0.3);
}

/* Hover 状态 */
.toggle-switch:hover .toggle-slider {
  backdrop-filter: blur(60px) saturate(180%);
  -webkit-backdrop-filter: blur(60px) saturate(180%);
}

/* 配置同步样式 */
.config-sync-section {
  margin-top: 16px;
  padding: 16px;
  background: rgba(28, 28, 30, 0.4);
  border-radius: 12px;
  border: 1px solid rgba(113, 113, 122, 0.3);
}

.config-sync-row {
  margin-bottom: 16px;
}

.config-sync-row:last-child {
  margin-bottom: 0;
}

.config-sync-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
}

.config-sync-section .node-select {
  width: 100%;
  padding: 8px 12px;
  background: rgba(28, 28, 30, 0.6);
  border: 1px solid rgba(113, 113, 122, 0.4);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.9);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.config-sync-section .node-select:hover {
  border-color: rgba(113, 113, 122, 0.6);
}

.config-sync-section .node-select:focus {
  outline: none;
  border-color: #007AFF;
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.2);
}

.config-sync-targets {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
  padding: 4px;
  background: rgba(28, 28, 30, 0.3);
  border-radius: 8px;
}

.config-sync-types {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-sync-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(28, 28, 30, 0.4);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.85);
}

.config-sync-checkbox:hover {
  background: rgba(28, 28, 30, 0.6);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(28, 28, 30, 0.4);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.85);
}

.checkbox-label:hover {
  background: rgba(28, 28, 30, 0.6);
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #007AFF;
}

.config-sync-checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #007AFF;
}

.toggle-switch:hover .toggle-slider:before {
  background-color: rgba(255, 255, 255, 0.5);
}

/* Active 状态 - 物理回弹反馈 */
.toggle-switch:active .toggle-slider {
  transform: scale(0.95);
}

.toggle-switch:active .toggle-slider:before {
  transform: translateX(22px) scale(0.95);
}

/* 禁用状态 */
.toggle-input:disabled + .toggle-slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-info {
  flex: 1 !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
  gap: 4px;
}

.toggle-label-text {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
  letter-spacing: -0.01em;
  line-height: 1.4;
  margin: 0;
  padding: 0;
}

.form-help {
  display: block;
  margin: 0;
  padding: 0;
  font-size: 12px;
  color: rgba(139, 148, 158, 0.85);
  line-height: 1.4;
}

/* ========== Toggle Switch 样式结束 ========== */
</style>
