<template>
  <div class="app" :class="{ 'not-connected': showConnectModal }">
<!-- Agent 侧边栏 -->
    <AgentSidebar
      ref="agentSidebarRef"
      :visible="showAgentSidebar"
      :resizeState="agentSidebarResizeState"
      :sidebarStyle="agentSidebarStyle"
      :isBatchMode="isBatchMode"
      :displayGroups="agentDisplayGroups"
      :currentAgentId="currentAgentId"
      :selectedCount="selectedAgents.size"
      :agentList="agentList"
      :windowWidth="windowWidth"
      :isAllSelected="isAllSelected"
      :agentStatuses="agentStatuses"
      :getStatusClass="getStatusClass"
      :getStatusText="getStatusText"
      :getNodeLabel="getAgentNodeLabel"
      :getNodeDisplayLabel="getAgentNodeDisplayLabel"
      :getProxyNodeLabel="getAgentProxyNodeLabel"
      :getWorkingDirDisplay="getWorkingDirDisplay"
      :isSelected="isAgentSelected"
      :isWaitingInput="isWaitingInput"
      :agentGroups="agentGroups"
      :nodes="availableNodeOptions"
      :currentUserId="auth.userInfo?.user_id || ''"
      :currentUserName="auth.userInfo?.display_name || auth.userInfo?.username || ''"
      :isConnected="!!socket && !showConnectModal"
      @close="showAgentSidebar = false"
      @toggleBatchMode="toggleBatchMode"
      @createAgent="openCreateAgentModal"
      @agentClick="handleAgentItemClick"
      @toggleSelectAgent="toggleSelectAgent"
      @renameAgent="renameAgent"
      @copyAgent="copyAgent"
      @deleteAgent="deleteAgent"
      @regenerateAgent="regenerateAgent"
      @toggleSelectAll="toggleSelectAll"
      @batchCopy="batchCopyAgents"
      @batchDelete="batchDeleteAgents"
      @addToGroup="addSelectedToGroup"
      @createGroupWithAgents="createGroupWithAgents"
      @startResize="startAgentSidebarResize"
      @editAccess="editAgentAccess"
      @petSyncStatus="petSyncAllStatus"
      @petInterruptCurrent="petInterruptCurrent"
      @petGotoWaiting="petGotoWaitingAgent"
      @petToggleSidebar="toggleAgentSidebar"
      @petOpenTopology="openTopologyOverlay"
      @petOpenCommandPalette="openCommandPalette()"
      :radial-actions="petRadialActions"
      @petRadialRun="onPetRadialRun"
    />

    <!-- 主内容区 -->
    <div class="main-content-wrapper">
      <!-- 桌面端顶部感应区：鼠标移入唤出标题栏 -->
      <div
        v-if="!isMobileLayout"
        class="top-hover-zone"
        @mouseenter="showHeader"
      ></div>
      <!-- 顶部栏 -->
      <header
        ref="headerRef"
        class="app-header"
        :class="{ 'is-hidden': headerHidden }"
        :style="{ '--app-header-h': headerHeight + 'px' }"
        @mouseenter="showHeader"
        @mouseleave="scheduleHideHeader"
      >
        <!-- 移动端快捷按钮 -->
        <div class="mobile-header-actions">
          <button class="icon-btn" @click="toggleAgentSidebar()" title="Agent列表">
            📋
          </button>
          <button class="icon-btn chat-btn-wrapper" @click="toggleChatPanel()" :disabled="!socket" title="聊天室">
            💬
            <span v-if="chatUnreadCount > 0" class="chat-unread-badge">{{ chatUnreadCount > 99 ? '99+' : chatUnreadCount }}</span>
          </button>
          <button class="icon-btn" @click="toggleTerminalPanel()" :disabled="!socket" title="终端面板">
            💻
          </button>

          <button class="icon-btn" @click="openCommandPalette()" title="命令面板">
            ⌘
          </button>

          <button class="icon-btn" @click="showSettingsModal = true; pushOverlayState()" :disabled="!socket" title="设置">
            ⚙
          </button>
          <button class="icon-btn" v-if="auth.userInfo?.is_admin" @click="showAdminPanel = true; pushOverlayState()" :disabled="!socket" title="管理">
            🛡️
          </button>
        </div>
        
        <div class="header-title">
          <img src="/icons/jarvis-pet.svg" alt="Jarvis" class="header-logo" />
          <span class="header-brand">JARVIS</span>
          <div class="status mobile-only">
            <span :class="['dot', connectionStatus]"></span>
            {{ connectionLabel }}
          </div>
          <button class="icon-btn desktop-only" @click="toggleAgentSidebar()" title="切换 Agent 侧边栏">
            📋
          </button>
        </div>
        
        <div class="current-agent-info desktop-only" v-if="currentAgent">
          <span class="agent-type">{{ currentAgent.name || (currentAgent.agent_type === 'agent' ? '🤖' : currentAgent.agent_type === 'code_agent' ? '💻' : '❓') }}</span>
          <span class="agent-status-dot" :class="getStatusClass(currentAgent)" :title="getStatusText(currentAgent)"></span>
          <span class="agent-node" v-if="getAgentNodeLabel(currentAgent)">🧭 {{ getAgentNodeDisplayLabel(currentAgent) }}</span>
          <span class="agent-dir">{{ getWorkingDirDisplay(currentAgent.working_dir) }}</span>
        </div>
        
        <div class="header-actions desktop-only">
          <span v-if="auth.userInfo" class="user-info-display" :title="'当前用户: ' + auth.userInfo.username">
            👤 {{ auth.userInfo.display_name || auth.userInfo.username }}
          </span>
          <button class="icon-btn chat-btn-wrapper" @click="toggleChatPanel()" :disabled="!socket" title="聊天室">
            💬
            <span v-if="chatUnreadCount > 0" class="chat-unread-badge">{{ chatUnreadCount > 99 ? '99+' : chatUnreadCount }}</span>
          </button>
          <button class="icon-btn" @click="toggleTerminalPanel()" :disabled="!socket" title="终端面板">
            💻
          </button>
          <button class="icon-btn" @click="openCommandPalette()" title="命令面板 (Ctrl+P)">
            ⌘
          </button>
          <button class="icon-btn" @click="showSettingsModal = true; pushOverlayState()" :disabled="!socket">
            ⚙
          </button>
          <button class="icon-btn" v-if="auth.userInfo?.is_admin" @click="showAdminPanel = true; pushOverlayState()" :disabled="!socket" title="管理">
            🛡️
          </button>
          <button v-if="auth.token" class="icon-btn logout-btn" @click="logout()" title="登出">
            🚪
          </button>
        </div>
      </header>

    <!-- Panel 网格布局 -->
    <main class="panel-grid" :style="panelGridStyle">
      <SessionPanel
        :ref="(el) => setSessionPanelRef(panel.id, el)"
        v-for="panel in panels"
        v-show="!sessionDetachedPanels.has(panel.id)"
        :key="panel.id"
        :embedded="!sessionDetachedPanels.has(panel.id)"
        :agent="getPanelAgent(panel)"
        :messages="getPanelMessages(panel)"
        :input-text="getPanelInputText(panel)"
        :input-mode="getPanelInputMode(panel)"
        :input-tip="getPanelInputTip(panel)"
        :is-password="getPanelInputPassword(panel)"
        :is-input-disabled="getPanelInputDisabled(panel)"
        :is-waiting-multi-disabled="getPanelWaitingMultiDisabled(panel)"
        :has-buffered-input="getPanelHasBufferedInput(panel)"
        :agent-status="getPanelAgentStatus(panel)"
        :active="panel.id === activePanelId"
        :confirm-data="getPanelConfirmData(panel)"
        @confirm="handlePanelConfirm(panel)"
        @cancel-confirm="handlePanelCancelConfirm(panel)"
        @activate="activatePanel(panel.id)"
        @close-agent="closeAgentInPanel(panel.id)"
        @close-panel="closePanel(panel.id)"
        @send="sendFromPanel(panel)"
        @complete="completeFromPanel(panel)"
        @open-completions="openCompletionsFromPanel(panel)"
        @input-change="handlePanelInputChange(panel, $event)"
        @keydown="handlePanelKeydown(panel, $event)"
        @paste="handlePanelPaste(panel, $event)"
        @show-buffer="showBufferPanel = true"
        @clear-buffer="clearBufferFromPanel(panel)"
        @set-output-list="setPanelOutputList(panel, $event)"
        @set-terminal-ref="(executionId, el, agentId) => setPanelTerminalRef(panel, executionId, el, agentId)"
        @show-toast="showToast"
        @detach="detachPanel('session', panel.id)"
      />

      <!-- 内嵌终端面板 -->
      <TerminalPanel
        v-if="showTerminalPanel && !terminalDetached"
        :visible="showTerminalPanel"
        :active="activeWindow === 'terminal'"
        :interaction="terminalPanelInteraction"
        :panelStyle="terminalPanelStyle"
        :nodeOptions="filteredNodeOptionsForCreateAgent"
        :selectedNodeId="selectedTerminalNodeId"
        :socket="socket"
        :isMaximized="isTerminalMaximized"
        :sessions="terminalSessions"
        :activeId="activeTerminalId"
        :resizeDirections="terminalResizeDirections"
        :formatNodeLabel="formatNodeOptionLabel"
        :embedded="true"
        @focus="focusWindow"
        @startMove="startTerminalPanelMove"
        @toggleMaximize="toggleTerminalMaximize"
        @update:selectedNodeId="selectedTerminalNodeId = $event"
        @createTerminal="createTerminalForSelectedNode"
        @close="showTerminalPanel = false"
        @switch="switchTerminal"
        @closeTerminal="closeTerminal"
        @setHostRef="setTerminalHostRef"
        @startResize="startTerminalPanelResize"
        @detach="detachPanel('terminal')"
      />

      <!-- 内嵌聊天室面板 -->
      <ChatPanel
        v-if="showChatPanel && !chatDetached"
        :visible="showChatPanel"
        :interaction="chatPanelInteraction"
        :panelStyle="chatPanelStyle"
        :socket="socket"
        :isMaximized="isChatMaximized"
        :rooms="chatRooms"
        :clients="chatClients"
        :roomMembers="chatRoomMembers"
        :myClientId="myClientId"
        :isAdmin="auth.userInfo?.is_admin"
        :currentUserId="auth.userInfo?.user_id"
        :activeRoomId="activeChatRoomId"
        :activePrivateId="activePrivateClientId"
        :resizeDirections="chatResizeDirections"
        :unreadCount="chatUnreadCount" :unreadMap="chatUnreadMap" :joinedRooms="chatJoinedRooms"
        :myName="chatName"
        :collapsed="chatPanelCollapsed"
        :sidebarWidth="chatSidebarWidth"
        :messages="activePrivateClientId ? (chatMessages['private_' + activePrivateClientId] || []) : (chatMessages[activeChatRoomId] || [])"
        :embedded="true"
        @focus="focusWindow"
        @startMove="startChatPanelMove"
        @toggleMaximize="toggleChatMaximize"
        @close="showChatPanel = false"
        @createRoom="createChatRoom"
        @joinRoom="joinChatRoom"
        @sendMessage="sendChatMessage"
        @selectPrivate="selectPrivateClient"
        @startResize="startChatPanelResize"
        @toggleCollapse="toggleChatPanelCollapse"
        @leaveRoom="leaveChatRoom"
        @deleteRoom="deleteChatRoom"
        @renameRoom="renameChatRoom"
        @startSidebarResize="startChatSidebarResize"
        @clearMessages="clearChatMessages"
        @detach="detachPanel('chat')"
      />

      <!-- 内嵌编辑器面板 -->
      <EditorPanel
        v-if="showEditorPanel && !editorDetached"
        ref="editorPanelRef"
        :visible="showEditorPanel"
        :active="activeWindow === 'editor'"
        :interaction="editorPanelInteraction"
        :panelStyle="editorPanelStyle"
        :agentName="activeEditorSession?.agent_name"
        :activeTab="activeEditorTab"
        :activeTabPath="activeEditorTabPath"
        :tabs="editorTabs"
        :isMaximized="isEditorMaximized"
        :isEditable="isEditorEditable"
        :showSidebar="showEditorSidebar"
        :sidebarView="editorSidebarView"
        :resizeDirections="editorResizeDirections"
        :embedded="true"
        @focus="focusWindow('editor')"
        @startMove="startEditorPanelMove"
        @toggleMaximize="toggleEditorMaximize"
        @save="saveActiveEditorTab"
        @close="closeEditorPanel"
        @activateTab="activateEditorTab"
        @closeTab="closeEditorTab"
        @toggleEditable="toggleEditorEditable"
        @setSidebarView="setEditorSidebarView"
        @startResize="startEditorPanelResize"
        @detach="detachPanel('editor')"
      >
        <template #sidebar>
          <aside v-if="showEditorSidebar" class="editor-sidebar" :style="{ width: editorSidebarWidth + 'px' }">
            <div class="editor-sidebar-resize-handle" @mousedown="startEditorSidebarResize($event)"></div>
            <div class="editor-sidebar-header">
              <span class="editor-sidebar-title">{{ editorSidebarView === 'search' ? '全局搜索' : '目录树' }}</span>
              <button class="icon-btn-small" @click="closeEditorSidebar" title="关闭侧边栏">✕</button>
            </div>
            <div v-if="editorSidebarView === 'files'" class="editor-sidebar-content">
              <div class="editor-file-tree-panel">
                <!-- 活跃 Agent 节点列表 -->
                <div
                  v-for="agent in activeAgents"
                  :key="agent.agent_id"
                  class="editor-agent-node"
                  :class="{
                    'selected': selectedAgentId === agent.agent_id,
                    'waiting-input': isWaitingInput(agent)
                  }"
                >
                  <div
                    class="tree-node-content agent-node-content"
                    @click.stop="toggleAgentExpanded(agent.agent_id)"
                  >
                    <span
                      class="tree-node-icon expand-arrow"
                      :class="{ expanded: expandedAgents.has(agent.agent_id) }"
                    >▶</span>
                    <span class="tree-node-icon agent-icon">{{ agent.agent_type === 'agent' ? '🤖' : agent.agent_type === 'code_agent' ? '💻' : '🤖' }}</span>
                    <span class="tree-node-text agent-name">{{ agent.name || agent.agent_id }}</span>
                    <span class="agent-status" :class="getStatusClass(agent)">{{ getStatusClass(agent) === 'stopped' ? '⏹' : getStatusClass(agent) === 'running' ? '▶' : '⏸' }}</span>
                    <span class="agent-node-id">{{ getNodeDisplayName(agent.node_id) }}</span>
                  </div>
                  <!-- Agent 的文件树 -->
                  <div v-if="expandedAgents.has(agent.agent_id)" class="agent-file-tree">
                    <div
                      class="editor-file-tree-root"
                      @click.stop="ensureEditorSidebarFileTree(agent)"
                    >
                      {{ getWorkingDirDisplay(agent.working_dir) }}
                    </div>
                    <div v-if="!(fileTreeState.get(agent.agent_id)?.length > 0)" class="editor-file-tree-empty">
                      当前工作目录下暂无可显示内容
                    </div>
                    <div v-else class="editor-file-tree-list">
                      <div
                        v-for="visibleNode in getVisibleFileTreeNodes(agent.agent_id)"
                        :key="visibleNode.node.path"
                        class="tree-node editor-tree-node"
                      >
                        <div
                          class="tree-node-content"
                          :style="{ paddingLeft: `${8 + visibleNode.depth * 20}px` }"
                          @click.stop="handleFileTreeNodeClick(agent.agent_id, visibleNode.node)"
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
                </div>
                <!-- 已停止 Agent 按节点分组 -->
                <template v-for="(agents, nodeId) in stoppedAgentsByNode" :key="nodeId">
                  <div class="stopped-agents-group">
                    <div
                      class="stopped-agents-header"
                      @click="toggleStoppedNodeCollapse(nodeId)"
                    >
                      <span class="expand-arrow" :class="{ expanded: !isStoppedNodeCollapsed(nodeId) }">▶</span>
                      <span class="stopped-agents-title">{{ getNodeDisplayName(nodeId) }}已停止的Agent ({{ agents.length }})</span>
                    </div>
                    <div v-if="!isStoppedNodeCollapsed(nodeId)" class="stopped-agents-list">
                      <div
                        v-for="agent in agents"
                        :key="agent.agent_id"
                        class="editor-agent-node stopped"
                        :class="{ 'selected': selectedAgentId === agent.agent_id }"
                      >
                        <div
                          class="tree-node-content agent-node-content"
                          @click.stop="toggleAgentExpanded(agent.agent_id)"
                        >
                          <span
                            class="tree-node-icon expand-arrow"
                            :class="{ expanded: expandedAgents.has(agent.agent_id) }"
                          >▶</span>
                          <span class="tree-node-icon agent-icon">{{ agent.agent_type === 'agent' ? '🤖' : agent.agent_type === 'code_agent' ? '💻' : '🤖' }}</span>
                          <span class="tree-node-text agent-name">{{ agent.name || agent.agent_id }}</span>
                          <span class="agent-status" :class="getStatusClass(agent)">{{ getStatusClass(agent) === 'stopped' ? '⏹' : getStatusClass(agent) === 'running' ? '▶' : '⏸' }}</span>
                          <span class="agent-node-id">{{ getNodeDisplayName(agent.node_id) }}</span>
                        </div>
                        <!-- Agent 的文件树 -->
                        <div v-if="expandedAgents.has(agent.agent_id)" class="agent-file-tree">
                          <div
                            class="editor-file-tree-root"
                            @click.stop="ensureEditorSidebarFileTree(agent)"
                          >
                            {{ getWorkingDirDisplay(agent.working_dir) }}
                          </div>
                          <div v-if="!(fileTreeState.get(agent.agent_id)?.length > 0)" class="editor-file-tree-empty">
                            当前工作目录下暂无可显示内容
                          </div>
                          <div v-else class="editor-file-tree-list">
                            <div
                              v-for="visibleNode in getVisibleFileTreeNodes(agent.agent_id)"
                              :key="visibleNode.node.path"
                              class="tree-node editor-tree-node"
                            >
                              <div
                                class="tree-node-content"
                                :style="{ paddingLeft: `${8 + visibleNode.depth * 20}px` }"
                                @click.stop="handleFileTreeNodeClick(agent.agent_id, visibleNode.node)"
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
                      </div>
                    </div>
                  </div>
                </template>
                <!-- 无 Agent 提示 -->
                <div v-if="agentList.length === 0" class="editor-file-tree-empty">
                  暂无 Agent，请先创建 Agent
                </div>
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
        </template>
      </EditorPanel>

      <!-- 空状态：无任何可见 Panel 时的宠物大厅（所有 Agent 的迷你宠物自由游动） -->
      <div v-if="hasNoPanel" class="empty-stage">
        <PetLobby
          ref="petLobbyRef"
          :agents="agentList"
          :nodes="availableNodeOptions"
          :getStatusClass="getStatusClass"
          :getInputState="getLobbyInputState"
          :getLatestOutput="getLobbyLatestOutput"
          :historyNav="onLobbyHistoryNav"
          :getNodeDisplayName="getNodeDisplayName"
          @selectAgent="onLobbySelectAgent"
          @sendInput="sendLobbyInput"
          @complete="onLobbyComplete"
          @openCompletions="onLobbyOpenCompletions"
          @activePetChange="lobbyActiveAgentId = $event"
        />
      </div>
    </main>
    <template v-for="panel in panels" :key="'floating-' + panel.id">
      <SessionPanel
        :ref="(el) => setSessionPanelRef(panel.id, el)"
        v-if="sessionDetachedPanels.has(panel.id)"
        :embedded="false"
        :agent="getPanelAgent(panel)"
        :messages="getPanelMessages(panel)"
        :input-text="getPanelInputText(panel)"
        :input-mode="getPanelInputMode(panel)"
        :input-tip="getPanelInputTip(panel)"
        :is-password="getPanelInputPassword(panel)"
        :is-input-disabled="getPanelInputDisabled(panel)"
        :is-waiting-multi-disabled="getPanelWaitingMultiDisabled(panel)"
        :has-buffered-input="getPanelHasBufferedInput(panel)"
        :agent-status="getPanelAgentStatus(panel)"
        :active="panel.id === activePanelId"
        :confirm-data="getPanelConfirmData(panel)"
        :interaction="sessionPanelInteraction"
        :resizeDirections="sessionResizeDirections"
        :panelStyle="getSessionPanelStyle(panel.id)"
        @confirm="handlePanelConfirm(panel)"
        @cancel-confirm="handlePanelCancelConfirm(panel)"
        @activate="activatePanel(panel.id)"
        @close-agent="closeAgentInPanel(panel.id)"
        @close-panel="closePanel(panel.id)"
        @send="sendFromPanel(panel)"
        @complete="completeFromPanel(panel)"
        @open-completions="openCompletionsFromPanel(panel)"
        @input-change="handlePanelInputChange(panel, $event)"
        @keydown="handlePanelKeydown(panel, $event)"
        @paste="handlePanelPaste(panel, $event)"
        @show-buffer="showBufferPanel = true"
        @clear-buffer="clearBufferFromPanel(panel)"
        @set-output-list="setPanelOutputList(panel, $event)"
        @set-terminal-ref="(executionId, el, agentId) => setPanelTerminalRef(panel, executionId, el, agentId)"
        @show-toast="showToast"
        @detach="detachPanel('session', panel.id)"
        @startMove="startSessionPanelMove($event, panel.id)"
        @startResize="(event, direction) => startSessionPanelResize(event, direction, panel.id)"
        @viewDiff="viewDiff(getPanelAgent(panel))"
        @viewRules="viewRules(getPanelAgent(panel))"
        @viewTools="viewTools(getPanelAgent(panel))"
        @createTerminal="createTerminalForAgent(getPanelAgent(panel))"
        @openEditor="createEditorForAgent(getPanelAgent(panel))"
      />
    </template>

    <!-- 确认对话框（弹出式） -->
    <ConfirmDialog
      :visible="!!confirmDialog"
      :message="confirmDialog?.message || ''"
      :defaultConfirm="confirmDialog?.defaultConfirm ?? true"
      @confirm="handleConfirmDialogConfirm"
      @cancel="handleConfirmDialogCancel"
    />

<!-- 终端面板（浮动模式） -->
    <TerminalPanel
      v-if="terminalDetached"
      :visible="showTerminalPanel"
      :active="activeWindow === 'terminal'"
      :interaction="terminalPanelInteraction"
      :panelStyle="terminalPanelStyle"
      :nodeOptions="filteredNodeOptionsForCreateAgent"
      :selectedNodeId="selectedTerminalNodeId"
      :socket="socket"
      :isMaximized="isTerminalMaximized"
      :sessions="terminalSessions"
      :activeId="activeTerminalId"
      :resizeDirections="terminalResizeDirections"
      :formatNodeLabel="formatNodeOptionLabel"
      @focus="focusWindow"
      @startMove="startTerminalPanelMove"
      @toggleMaximize="toggleTerminalMaximize"
      @update:selectedNodeId="selectedTerminalNodeId = $event"
      @createTerminal="createTerminalForSelectedNode"
      @close="showTerminalPanel = false"
      @switch="switchTerminal"
      @closeTerminal="closeTerminal"
      @setHostRef="setTerminalHostRef"
      @startResize="startTerminalPanelResize"
      @detach="detachPanel('terminal')"
    />

    <!-- 聊天室面板（浮动模式） -->
    <ChatPanel
      v-if="chatDetached"
      :visible="showChatPanel"
      :interaction="chatPanelInteraction"
      :panelStyle="chatPanelStyle"
      :socket="socket"
      :isMaximized="isChatMaximized"
      :rooms="chatRooms"
      :clients="chatClients"
      :roomMembers="chatRoomMembers"
      :myClientId="myClientId"
      :isAdmin="auth.userInfo?.is_admin"
      :currentUserId="auth.userInfo?.user_id"
      :activeRoomId="activeChatRoomId"
      :activePrivateId="activePrivateClientId"
      :resizeDirections="chatResizeDirections"
      :unreadCount="chatUnreadCount" :unreadMap="chatUnreadMap" :joinedRooms="chatJoinedRooms"
      :myName="chatName"
      :collapsed="chatPanelCollapsed"
      :sidebarWidth="chatSidebarWidth"
      :messages="activePrivateClientId ? (chatMessages['private_' + activePrivateClientId] || []) : (chatMessages[activeChatRoomId] || [])"
      @focus="focusWindow"
      @startMove="startChatPanelMove"
      @toggleMaximize="toggleChatMaximize"
      @close="showChatPanel = false"
      @createRoom="createChatRoom"
      @joinRoom="joinChatRoom"
      @sendMessage="sendChatMessage"
      @selectPrivate="selectPrivateClient"
      @startResize="startChatPanelResize"
      @toggleCollapse="toggleChatPanelCollapse"
      @leaveRoom="leaveChatRoom"
      @deleteRoom="deleteChatRoom"
      @renameRoom="renameChatRoom"
      @startSidebarResize="startChatSidebarResize"
      @clearMessages="clearChatMessages"
      @detach="detachPanel('chat')"
    />

    <!-- 浮动编辑器面板 -->
    <EditorPanel
      v-if="editorDetached"
      ref="editorPanelRef"
      :visible="showEditorPanel"
      :active="activeWindow === 'editor'"
      :interaction="editorPanelInteraction"
      :panelStyle="editorPanelStyle"
      :agentName="activeEditorSession?.agent_name"
      :activeTab="activeEditorTab"
      :activeTabPath="activeEditorTabPath"
      :tabs="editorTabs"
      :isMaximized="isEditorMaximized"
      :isEditable="isEditorEditable"
      :showSidebar="showEditorSidebar"
      :sidebarView="editorSidebarView"
      :resizeDirections="editorResizeDirections"
      @focus="focusWindow('editor')"
      @startMove="startEditorPanelMove"
      @toggleMaximize="toggleEditorMaximize"
      @save="saveActiveEditorTab"
      @close="closeEditorPanel"
      @activateTab="activateEditorTab"
      @closeTab="closeEditorTab"
      @toggleEditable="toggleEditorEditable"
      @setSidebarView="setEditorSidebarView"
      @startResize="startEditorPanelResize"
      @detach="detachPanel('editor')"
    >
      <template #sidebar>
        <aside v-if="showEditorSidebar" class="editor-sidebar" :style="{ width: editorSidebarWidth + 'px' }">
          <div class="editor-sidebar-resize-handle" @mousedown="startEditorSidebarResize($event)"></div>
          <div class="editor-sidebar-header">
            <span class="editor-sidebar-title">{{ editorSidebarView === 'search' ? '全局搜索' : '目录树' }}</span>
            <button class="icon-btn-small" @click="closeEditorSidebar" title="关闭侧边栏">✕</button>
          </div>
          <div v-if="editorSidebarView === 'files'" class="editor-sidebar-content">
            <div class="editor-file-tree-panel">
              <!-- 活跃 Agent 节点列表 -->
              <div
                v-for="agent in activeAgents"
                :key="agent.agent_id"
                class="editor-agent-node"
                :class="{ 
                  'selected': selectedAgentId === agent.agent_id,
                  'waiting-input': isWaitingInput(agent)
                }"
              >
                <div
                  class="tree-node-content agent-node-content"
                  @click.stop="toggleAgentExpanded(agent.agent_id)"
                >
                  <span
                    class="tree-node-icon expand-arrow"
                    :class="{ expanded: expandedAgents.has(agent.agent_id) }"
                  >▶</span>
                  <span class="tree-node-icon agent-icon">{{ agent.agent_type === 'agent' ? '🤖' : agent.agent_type === 'code_agent' ? '💻' : '🤖' }}</span>
                  <span class="tree-node-text agent-name">{{ agent.name || agent.agent_id }}</span>
                  <span class="agent-status" :class="getStatusClass(agent)">{{ getStatusClass(agent) === 'stopped' ? '⏹️' : '▶️' }}</span>
                  <span class="agent-node-id">{{ getNodeDisplayName(agent.node_id) }}</span>
                </div>
                <!-- Agent 的文件树 -->
                <div v-if="expandedAgents.has(agent.agent_id)" class="agent-file-tree">
                  <div
                    class="editor-file-tree-root"
                    @click.stop="ensureEditorSidebarFileTree(agent)"
                  >
                    {{ getWorkingDirDisplay(agent.working_dir) }}
                  </div>
                  <div v-if="!(fileTreeState.get(agent.agent_id)?.length > 0)" class="editor-file-tree-empty">
                    当前工作目录下暂无可显示内容
                  </div>
                  <div v-else class="editor-file-tree-list">
                    <div
                      v-for="visibleNode in getVisibleFileTreeNodes(agent.agent_id)"
                      :key="visibleNode.node.path"
                      class="tree-node editor-tree-node"
                    >
                      <div
                        class="tree-node-content"
                        :style="{ paddingLeft: `${8 + visibleNode.depth * 20}px` }"
                        @click.stop="handleFileTreeNodeClick(agent.agent_id, visibleNode.node)"
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
              </div>
              <!-- 已停止 Agent 按节点分组 -->
              <template v-for="(agents, nodeId) in stoppedAgentsByNode" :key="nodeId">
                <div class="stopped-agents-group">
                  <div
                    class="stopped-agents-header"
                    @click="toggleStoppedNodeCollapse(nodeId)"
                  >
                    <span class="expand-arrow" :class="{ expanded: !isStoppedNodeCollapsed(nodeId) }">▶</span>
                    <span class="stopped-agents-title">{{ getNodeDisplayName(nodeId) }}已停止的Agent ({{ agents.length }})</span>
                  </div>
                  <div v-if="!isStoppedNodeCollapsed(nodeId)" class="stopped-agents-list">
                    <div
                      v-for="agent in agents"
                      :key="agent.agent_id"
                      class="editor-agent-node stopped"
                      :class="{ 'selected': selectedAgentId === agent.agent_id }"
                    >
                      <div
                        class="tree-node-content agent-node-content"
                        @click.stop="toggleAgentExpanded(agent.agent_id)"
                      >
                        <span
                          class="tree-node-icon expand-arrow"
                          :class="{ expanded: expandedAgents.has(agent.agent_id) }"
                        >▶</span>
                        <span class="tree-node-icon agent-icon">{{ agent.agent_type === 'agent' ? '🤖' : agent.agent_type === 'code_agent' ? '💻' : '🤖' }}</span>
                        <span class="tree-node-text agent-name">{{ agent.name || agent.agent_id }}</span>
                        <span class="agent-status" :class="getStatusClass(agent)">{{ getStatusClass(agent) === 'stopped' ? '⏹️' : '🟢' }}</span>
                        <span class="agent-node-id">{{ getNodeDisplayName(agent.node_id) }}</span>
                      </div>
                      <!-- Agent 的文件树 -->
                      <div v-if="expandedAgents.has(agent.agent_id)" class="agent-file-tree">
                        <div
                          class="editor-file-tree-root"
                          @click.stop="ensureEditorSidebarFileTree(agent)"
                        >
                          {{ getWorkingDirDisplay(agent.working_dir) }}
                        </div>
                        <div v-if="!(fileTreeState.get(agent.agent_id)?.length > 0)" class="editor-file-tree-empty">
                          当前工作目录下暂无可显示内容
                        </div>
                        <div v-else class="editor-file-tree-list">
                          <div
                            v-for="visibleNode in getVisibleFileTreeNodes(agent.agent_id)"
                            :key="visibleNode.node.path"
                            class="tree-node editor-tree-node"
                          >
                            <div
                              class="tree-node-content"
                              :style="{ paddingLeft: `${8 + visibleNode.depth * 20}px` }"
                              @click.stop="handleFileTreeNodeClick(agent.agent_id, visibleNode.node)"
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
                    </div>
                  </div>
                </div>
              </template>
              <!-- 无 Agent 提示 -->
              <div v-if="agentList.length === 0" class="editor-file-tree-empty">
                暂无 Agent，请先创建 Agent
              </div>
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
      </template>
    </EditorPanel>

    <!-- 底部输入区 -->

    </div> <!-- 结束 main-content-wrapper -->

    <!-- 缓存管理弹窗 -->
    <BufferPanel
      :visible="showBufferPanel"
      :hasBufferedInput="hasBufferedInput"
      :editText="bufferEditText"
      @update:editText="bufferEditText = $event"
      @close="showBufferPanel = false"
      @load="loadBufferToInput"
      @clear="clearBuffer"
      @save="saveBufferEdit"
    />

    <!-- 补全列表弹窗 -->
    <CompletionsModal
      ref="completionsModalRef"
      :visible="showCompletions"
      :searchText="completionSearch"
      :filteredCompletions="filteredCompletions"
      :selectedIndex="selectedIndex"
      @update:searchText="completionSearch = $event"
      @close="closeCompletionsWithoutSelect()"
      @select="(item) => insertCompletion(item, completionAgentId)"
      @keydown="handleCompletionKeydown"
    />

    <!-- 创建 Agent 弹窗 -->
    <CreateAgentModal
      :visible="showCreateAgentModal"
      :nodeOptions="filteredNodeOptionsForCreateAgent"
      :nodeId="newAgentNodeId"
      @update:nodeId="newAgentNodeId = $event"
      :agentType="newAgentType"
      @update:agentType="newAgentType = $event"
      :agentName="newAgentName"
      @update:agentName="newAgentName = $event"
      :modelGroups="modelGroups"
      :modelGroup="newAgentModelGroup"
      @update:modelGroup="newAgentModelGroup = $event"
      :workDir="newAgentDir"
      @update:workDir="newAgentDir = $event"
      :codeAgentWorktree="newCodeAgentWorktree"
      @update:codeAgentWorktree="newCodeAgentWorktree = $event"
      :quickMode="newAgentQuickMode"
      @update:quickMode="newAgentQuickMode = $event"
      :restoreSession="newAgentRestoreSession"
      @update:restoreSession="newAgentRestoreSession = $event"
      :noInteractionMode="newAgentNoInteractionMode"
      @update:noInteractionMode="newAgentNoInteractionMode = $event"
      :taskDescription="newAgentTaskDescription"
      @update:taskDescription="newAgentTaskDescription = $event"
      :proxyNode="newAgentProxyNode"
      @update:proxyNode="newAgentProxyNode = $event"
      :formatNodeLabel="formatNodeOptionLabel"
      :noNodeAccess="userAccessibleNodes !== null && userAccessibleNodes.length === 0"
      :createError="newAgentCreateError"
      :accessAclRead="newAgentAccessAclRead"
      @update:accessAclRead="newAgentAccessAclRead = $event"
      :accessAclInteract="newAgentAccessAclInteract"
      :userOptions="availableUserOptions.filter(u => !u.is_admin && u.user_id !== auth.userInfo?.user_id)"
      :recentWorkDirs="recentWorkDirs"
      :currentNodeId="newAgentNodeId"
      @cancel="showCreateAgentModal = false"
      @create="createAgent"
      @selectDir="openDirDialog"
    />

    <!-- 重命名 Agent 弹窗 -->
    <RenameAgentModal
      :visible="showRenameAgentModal"
      :name="renameAgentName"
      @update:name="renameAgentName = $event"
      @cancel="showRenameAgentModal = false"
      @confirm="confirmRename"
    />

    <!-- Agent ACL编辑弹窗 -->
    <div v-if="showEditAccessModal" class="modal-overlay" @click.self="showEditAccessModal = false">
      <div class="modal-content" style="max-width: 480px;">
        <h3>权限管理 - {{ editingAccessAgent?.name || editingAccessAgent?.agent_id }}</h3>
        <div class="form-group">
          <label>可查看用户 (read)</label>
          <div class="acl-user-list">
            <label v-for="user in filteredUserOptionsForAcl" :key="user.user_id" class="checkbox-label">
              <input type="checkbox" :value="user.user_id" v-model="editAccessRead" />
              {{ user.display_name || user.user_id }}
            </label>
            <div v-if="filteredUserOptionsForAcl.length === 0" class="form-help">暂无可选用户</div>
          </div>
        </div>
        <div class="form-group">
          <label>可交互用户 (interact)</label>
          <div class="acl-user-list">
            <label v-for="user in filteredUserOptionsForAcl" :key="user.user_id" class="checkbox-label">
              <input type="checkbox" :value="user.user_id" v-model="editAccessInteract" />
              {{ user.display_name || user.user_id }}
            </label>
            <div v-if="filteredUserOptionsForAcl.length === 0" class="form-help">暂无可选用户</div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn secondary" @click="showEditAccessModal = false">取消</button>
          <button class="btn primary" @click="saveAgentAccess">保存</button>
        </div>
      </div>
    </div>

    <!-- 目录选择对话框 -->
    <DirectoryDialog
      ref="dirDialogRef"
      :visible="showDirDialog"
      :currentPath="currentDirPath"
      :selectedDir="selectedDir"
      :searchText="dirSearchText"
      :filteredDirs="filteredDirList"
      @update:searchText="dirSearchText = $event"
      @cancel="cancelDirDialog"
      @confirm="confirmDirectory"
      @refresh="fetchDirectories"
      @go-parent="goToParentDir"
      @select="selectDirectory"
      @enter="enterDirectory"
      @search-keydown="handleDirSearchKeydown"
    />

    <!-- 连接弹窗 -->
    <ConnectModal
      :visible="showConnectModal"
      :connecting="connecting"
      :errorMessage="connectErrorMessage"
      :gatewayUrl="gatewayUrl"
      :password="auth.password"
      :username="username"
      @update:gatewayUrl="gatewayUrl = $event"
      @update:password="auth.password = $event"
      @update:username="username = $event"
      @connect="connect"
    />

    <!-- 设置弹窗 -->
    <SettingsModal
      :visible="showSettingsModal"
      :autoLoginEnabled="autoLoginEnabled"
      :notifyOnExit="notifyOnExit"
      :notifyOnInput="notifyOnInput"
      :historyStorage="historyStorage"
      :socket="socket"
      :auth="auth"
      :fetchWithAuth="fetchWithAuth"
      :gatewayUrl="gatewayUrl"
      :getHttpProtocol="getHttpProtocol"
      :showToast="showToast"
      :nodeOptions="availableNodeOptions"
      :nodeDisplayNames="nodeDisplayNames"
      :hideWorkingDir="hideWorkingDir"
      @update:visible="showSettingsModal = $event"
      @update:autoLoginEnabled="autoLoginEnabled = $event"
      @saveAutoLoginSetting="saveAutoLoginSetting"
      @update:notifyOnExit="notifyOnExit = $event"
      @update:notifyOnInput="notifyOnInput = $event"
      @saveNotifySettings="saveNotifySettings"
      @saveNodeDisplayNames="saveNodeDisplayNames"
      @update:hideWorkingDir="hideWorkingDir = $event"
      @saveHideWorkingDirSetting="saveHideWorkingDirSetting"
      @confirmClearHistory="confirmClearHistory"
      @disconnectAll="disconnectAll"
    />

    <!-- 管理面板 -->
    <AdminPanel
      :visible="showAdminPanel"
      :auth="auth"
      :fetchWithAuth="fetchWithAuth"
      :gatewayUrl="gatewayUrl"
      :showToast="showToast"
      :getHttpProtocol="getHttpProtocol"
      :availableNodeOptions="availableNodeOptions"
      :isRestartingGateway="isRestartingGateway"
      :isSyncingConfig="isSyncingConfig"
      :isUpdatingCode="isUpdatingCode"
      :getToken="getAuthToken"
      @update:visible="showAdminPanel = $event"
      @confirmRestartGateway="handleRestartGateway"
      @confirmRestartAllNodes="confirmRestartAllNodes"
      @syncConfig="handleSyncConfig"
      @updateCodeToMain="handleUpdateCodeToMain"
      @confirmUpdateCodeToMain="confirmUpdateCodeToMain"
    />

    <!-- Session 选择对话框 -->
    <SessionDialog
      :visible="showSessionDialog"
      :sessions="availableSessions"
      :selectedSession="selectedSession"
      @update:selectedSession="selectedSession = $event"
      @restore="restoreSession"
      @cancel="cancelSessionDialog"
    />

    <!-- Diff 浮动窗口 -->
    <div v-if="showDiffModal" class="diff-modal-overlay" @click.self="showDiffModal = false">
      <div class="diff-modal">
        <div class="diff-modal-header">
          <h3>代码变更</h3>
          <button class="icon-btn" @click="showDiffModal = false" title="关闭">✕</button>
        </div>
        <div class="diff-modal-content">
          <div v-if="diffLoading" class="diff-loading">加载中...</div>
          <div v-else v-html="diffContent"></div>
        </div>
      </div>
    </div>

    <!-- Rules 浮动窗口 -->
    <div v-if="showRulesModal" class="diff-modal-overlay" @click.self="showRulesModal = false">
      <div class="diff-modal rules-modal">
        <div class="diff-modal-header">
          <h3>规则信息</h3>
          <button class="icon-btn" @click="showRulesModal = false" title="关闭">✕</button>
        </div>
        <div class="diff-modal-content">
          <div v-if="rulesLoading" class="diff-loading">加载中...</div>
          <div v-else-if="rulesContent.length === 0" class="diff-empty">暂无规则</div>
          <table v-else class="rules-table">
            <thead>
              <tr>
                <th>规则名称</th>
                <th>状态</th>
                <th>文件路径</th>
                <th>预览</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rule in rulesContent" :key="rule.name" :title="rule.preview">
                <td>{{ rule.name }}</td>
                <td>
                  <span :class="rule.is_loaded ? 'rule-loaded' : 'rule-not-loaded'">
                    {{ rule.is_loaded ? '已加载' : '未加载' }}
                  </span>
                </td>
                <td class="rule-file-path">{{ rule.file_path || '--' }}</td>
                <td class="rule-preview">{{ rule.preview }}</td>
              </tr>
            </tbody>
          </table>
          <!-- 已加载规则内容 -->
          <div v-if="rulesLoadedContent" class="rules-loaded-content-section">
            <h4 class="rules-section-title">已加载规则内容</h4>
            <pre class="rules-loaded-content">{{ rulesLoadedContent }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- Tools 浮动窗口 -->
    <div v-if="showToolsModal" class="diff-modal-overlay" @click.self="showToolsModal = false">
      <div class="diff-modal rules-modal">
        <div class="diff-modal-header">
          <h3>工具信息</h3>
          <button class="icon-btn" @click="showToolsModal = false" title="关闭">✕</button>
        </div>
        <div class="diff-modal-content">
          <div v-if="toolsLoading" class="diff-loading">加载中...</div>
          <div v-else>
            <h4 class="tools-section-title">允许使用的工具</h4>
            <div v-if="!toolsContent.allowed_tools" class="diff-empty">使用全部工具</div>
            <table v-else-if="toolsContent.allowed_tools.length > 0" class="rules-table">
              <thead>
                <tr>
                  <th>工具名称</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="tool in toolsContent.allowed_tools" :key="tool">
                  <td>{{ tool }}</td>
                </tr>
              </tbody>
            </table>
            <div v-else class="diff-empty">无允许的工具</div>

            <h4 class="tools-section-title">全量工具 ({{ toolsContent.all_tools.length }})</h4>
            <div v-if="toolsContent.all_tools.length === 0" class="diff-empty">暂无工具</div>
            <table v-else class="rules-table">
              <thead>
                <tr>
                  <th>工具名称</th>
                  <th>描述</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="tool in toolsContent.all_tools" :key="tool.name" :title="tool.description">
                  <td>{{ tool.name }}</td>
                  <td class="rule-preview">{{ tool.description }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- 网络拓扑大图 -->
    <TopologyOverlay
      :visible="showTopologyOverlay"
      :nodes="availableNodeOptions"
      :agents="agentList"
      :getStatusClass="getStatusClass"
      :nodeDisplayNames="nodeDisplayNames"
      @update:visible="showTopologyOverlay = $event"
      @close="showTopologyOverlay = false"
    />

    <!-- 命令面板（Ctrl+P） -->
    <CommandPalette
      :visible="showCommandPalette"
      :actions="appActions"
      :ctx="commandPaletteCtx"
      :initial-query="commandPaletteInitialQuery"
      title="命令面板"
      @update:visible="showCommandPalette = $event"
      @run="onCommandRun"
      @close="showCommandPalette = false"
    />

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
import { computed, nextTick, onMounted, onUnmounted, ref, triggerRef, watch } from 'vue'
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightSpecialChars, drawSelection, rectangularSelection, crosshairCursor, placeholder } from '@codemirror/view'
import { EditorState, Compartment } from '@codemirror/state'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { syntaxHighlighting, defaultHighlightStyle, bracketMatching, foldGutter, indentOnInput } from '@codemirror/language'
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete'
import { highlightSelectionMatches, searchKeymap } from '@codemirror/search'
import { EditorView as CMEditorView } from '@codemirror/view'
import { HighlightStyle as CMHighlightStyle, syntaxHighlighting as CMSyntaxHighlighting } from '@codemirror/language'
import { tags as cmTags } from '@lezer/highlight'
import { javascript } from '@codemirror/lang-javascript'
import { python } from '@codemirror/lang-python'
import { json } from '@codemirror/lang-json'
import { html } from '@codemirror/lang-html'
import { css } from '@codemirror/lang-css'
import { markdown } from '@codemirror/lang-markdown'
import { xml } from '@codemirror/lang-xml'
import { sql } from '@codemirror/lang-sql'
import { rust } from '@codemirror/lang-rust'
import { cpp } from '@codemirror/lang-cpp'
import { java } from '@codemirror/lang-java'
import { go } from '@codemirror/lang-go'
import { php } from '@codemirror/lang-php'
import { yaml } from '@codemirror/lang-yaml'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import { Terminal } from 'xterm'
import { FitAddon } from '@xterm/addon-fit'
import 'xterm/css/xterm.css'
import './diff.css'
import plantumlEncoder from 'plantuml-encoder'
import mermaid from 'mermaid'
import { graphviz } from 'd3-graphviz'
import historyStorage from './historyStorage.js'
import ConnectModal from './components/ConnectModal.vue'
import BufferPanel from './components/BufferPanel.vue'
import DirectoryDialog from './components/DirectoryDialog.vue'
import SessionDialog from './components/SessionDialog.vue'
import AgentSidebar from './components/AgentSidebar.vue'
import CompletionsModal from './components/CompletionsModal.vue'
import TerminalPanel from './components/TerminalPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import EditorPanel from './components/EditorPanel.vue'
import SettingsModal from './components/SettingsModal.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import CreateAgentModal from './components/CreateAgentModal.vue'
import SessionPanel from './components/SessionPanel.vue'
import { renderSideBySideDiff, escapeHtml } from './diffRenderer.js'
import RenameAgentModal from './components/RenameAgentModal.vue'
import AdminPanel from './components/AdminPanel.vue'
import CommandPalette from './components/CommandPalette.vue'
import TopologyOverlay from './components/TopologyOverlay.vue'
import PetLobby from './components/PetLobby.vue'
import { ACTIONS as actionDefs } from './actions/registry.js'

const PLANTUML_SERVER_URL = 'https://www.plantuml.com/plantuml/svg/'
const PLANTUML_BLOCK_LANGUAGE = 'plantuml'
const MERMAID_BLOCK_LANGUAGE = 'mermaid'
const DOT_BLOCK_LANGUAGES = ['dot', 'graphviz']

// Mermaid 渲染计数器，用于生成唯一 ID
let mermaidRenderCounter = 0
// Dot 渲染计数器，用于生成唯一 ID
let dotRenderCounter = 0

// 格式化消息时间 - 直接显示后端传递的时间戳
function formatMessageTime(timestamp) {
  if (!timestamp) return ''
  return timestamp
}

// 初始化 Mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
  fontFamily: 'inherit'
})

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

function isDotLanguage(language) {
  return DOT_BLOCK_LANGUAGES.includes(String(language || '').trim().toLowerCase())
}

function isMermaidLanguage(language) {
  return String(language || '').trim().toLowerCase() === MERMAID_BLOCK_LANGUAGE
}

/**
 * 渲染 dot/Graphviz 代码块
 * 使用 d3-graphviz 在浏览器端渲染
 */
function renderDotBlock(dotSource) {
  const trimmedSource = String(dotSource || '').trim()
  if (!trimmedSource) {
    return '<pre><code class="language-dot"></code></pre>'
  }

  const id = `dot-diagram-${++dotRenderCounter}`
  const escapedSource = escapeHtml(trimmedSource)

  // 返回占位 HTML，后续由 renderDotDiagrams 函数在 DOM 插入后异步渲染
  return [
    '<div class="diagram-block">',
    '  <div class="diagram-notice">',
    '    Graphviz 图形（浏览器端渲染）。',
    '  </div>',
    `  <div class="dot-container" data-dot-id="${id}" data-dot-source="${encodeURIComponent(trimmedSource)}">`,
    '    <div class="dot-loading">渲染中...</div>',
    '  </div>',
    '  <details class="diagram-source">',
    '    <summary>查看 dot 源码</summary>',
    `    <pre><code class="language-dot">${escapedSource}</code></pre>`,
    '  </details>',
    '</div>'
  ].join('\n')
}

/**
 * 渲染 Mermaid 代码块
 * 使用 mermaid 库在浏览器端渲染
 */
function renderMermaidBlock(mermaidSource) {
  const trimmedSource = String(mermaidSource || '').trim()
  if (!trimmedSource) {
    return '<pre><code class="language-mermaid"></code></pre>'
  }

  const id = `mermaid-diagram-${++mermaidRenderCounter}`
  const escapedSource = escapeHtml(trimmedSource)

  // 返回占位 HTML，后续由 renderMermaidDiagrams 函数在 DOM 插入后异步渲染
  return [
    '<div class="diagram-block">',
    '  <div class="diagram-notice">',
    '    Mermaid 流程图（浏览器端渲染）。',
    '  </div>',
    `  <div class="mermaid-container" data-mermaid-id="${id}" data-mermaid-source="${encodeURIComponent(trimmedSource)}">`,
    '    <div class="mermaid-loading">渲染中...</div>',
    '  </div>',
    '  <details class="diagram-source">',
    '    <summary>查看 Mermaid 源码</summary>',
    `    <pre><code class="language-mermaid">${escapedSource}</code></pre>`,
    '  </details>',
    '</div>'
  ].join('\n')
}

/**
 * 异步渲染页面中所有未渲染的 Mermaid 图形
 * 在消息内容更新后调用
 */
async function renderMermaidDiagrams(containerEl) {
  if (!containerEl) return
  const elements = containerEl.querySelectorAll('.mermaid-container[data-mermaid-source]')
  for (const el of elements) {
    const source = decodeURIComponent(el.getAttribute('data-mermaid-source') || '')
    const id = el.getAttribute('data-mermaid-id') || 'mermaid-diagram'
    if (!source) continue

    try {
      const { svg } = await mermaid.render(id, source)
      el.innerHTML = svg
      el.removeAttribute('data-mermaid-source')
    } catch (error) {
      console.error('[Mermaid] Failed to render diagram:', error)
      el.innerHTML = `<pre><code class="language-mermaid">${escapeHtml(source)}</code></pre>`
      el.removeAttribute('data-mermaid-source')
    }
  }
}

/**
 * 异步渲染页面中所有未渲染的 dot/Graphviz 图形
 * 在消息内容更新后调用
 */
async function renderDotDiagrams(containerEl) {
  if (!containerEl) return
  const elements = containerEl.querySelectorAll('.dot-container[data-dot-source]')
  for (const el of elements) {
    const source = decodeURIComponent(el.getAttribute('data-dot-source') || '')
    if (!source) continue

    try {
      await new Promise((resolve, reject) => {
        graphviz(el, { useWorker: false })
          .renderDot(source)
          .on('end', resolve)
          .on('error', reject)
      })
      el.removeAttribute('data-dot-source')
    } catch (error) {
      console.error('[Dot] Failed to render diagram:', error)
      el.innerHTML = `<pre><code class="language-dot">${escapeHtml(source)}</code></pre>`
      el.removeAttribute('data-dot-source')
    }
  }
}

const markedRenderer = new marked.Renderer()
const defaultCodeRenderer = markedRenderer.code.bind(markedRenderer)

markedRenderer.code = function(code, language, isEscaped) {
  if (isPlantUmlLanguage(language)) {
    return renderPlantUmlBlock(code)
  }
  if (isDotLanguage(language)) {
    return renderDotBlock(code)
  }
  if (isMermaidLanguage(language)) {
    return renderMermaidBlock(code)
  }
  return defaultCodeRenderer(code, language, isEscaped)
}

// 配置 marked 使用 highlight.js 进行语法高亮
marked.setOptions({
  renderer: markedRenderer,
  breaks: true, // 将单个换行符转换为 <br> 标签
  highlight: function(code, lang) {
    // vue SFC 降级为 xml 高亮
    const effectiveLang = (lang === 'vue') ? 'xml' : lang
    if (effectiveLang && hljs.getLanguage(effectiveLang)) {
      try {
        return hljs.highlight(code, { language: effectiveLang }).value
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
    fontFamily: "'Consolas', 'Microsoft YaHei', monospace",
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

// CodeMirror 6 语言扩展映射
function getLanguageExtension(language) {
  const extMap = {
    'javascript': javascript,
    'typescript': javascript,
    'python': python,
    'json': json,
    'html': html,
    'css': css,
    'markdown': markdown,
    'xml': xml,
    'sql': sql,
    'rust': rust,
    'cpp': cpp,
    'c': cpp,
    'java': java,
    'go': go,
    'php': php,
    'yaml': yaml,
    'vue': xml,
    'scss': css,
    'less': css,
  }
  const ext = extMap[language]
  return ext ? ext() : []
}

// 认证和连接配置
const auth = ref({
  password: '',
  token: '',
  userInfo: null
})
const username = ref(localStorage.getItem('jarvis_username') || '')
const gatewayUrl = ref(localStorage.getItem('jarvis_gateway_url') || '127.0.0.1:8000')
const socket = ref(null) // Gateway 连接
const sockets = ref(new Map()) // 多 Agent 连接存储：agent_id -> WebSocket

// Agent 心跳检测相关状态
const lastPongTime = ref(new Map()) // agentId -> 最后收到 pong 的时间戳
const HEARTBEAT_INTERVAL = 5000 // 心跳间隔：5 秒发送一次 ping
const HEARTBEAT_TIMEOUT = 15000 // 心跳超时时间：15 秒（3 次）未收到 pong 就重连
const connecting = ref(false)
const agentConnecting = ref(false) // Agent 连接状态（独立于主网关连接状态）
const connectingAgents = ref(new Set()) // Agent 连接锁：防止同一 agent 并发重连建多连接
const connectErrorMessage = ref('')  // 连接错误信息
const autoLoginEnabled = ref(localStorage.getItem('jarvis_auto_login') === 'true')  // 免登录开关
// 通知开关仅控制系统通知弹窗，不影响提示音（提示音由自动朗读等逻辑独立触发）
const notifyOnExit = ref(localStorage.getItem('jarvis_notify_on_exit') === 'true')  // Agent 退出通知开关（默认关闭）
const notifyOnInput = ref(localStorage.getItem('jarvis_notify_on_input') === 'true')  // 需要输入通知开关（默认关闭）
const isRestartingGateway = ref(false)
const restartNodeId = ref('') // 重启服务时选择的节点ID
const restartFrontendService = ref(false) // 是否同时重启前端服务

// WebSocket重连相关状态
const reconnecting = ref(false) // 是否正在重连
const reconnectAttempts = ref(0) // 当前重连尝试次数
const reconnectTimer = ref(null) // 重连定时器
const switchGeneration = ref(0) // 切换代数，用于取消旧的switchAgent操作
const reconnectInterval = 5000 // 固定重连间隔（毫秒）
const userDisconnected = ref(false) // 用户主动断开连接标志
const isAutoConnecting = ref(false) // 自动连接（免登录）阶段标志

// 配置同步相关状态
const syncConfigSourceNode = ref('') // 配置同步的源节点ID
const syncConfigTargetNodes = ref([]) // 配置同步的目标节点ID数组
const syncConfigSections = ref(['llms', 'llm_groups']) // 要同步的配置类型数组（llms, llm_groups）
const isSyncingConfig = ref(false) // 是否正在同步配置
const isUpdatingCode = ref(false) // 是否正在更新代码

// 登录函数：使用用户名+密码获取 JWT Token
async function loginWithPassword(password) {
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetch(`${getHttpProtocol()}://${host}:${port}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password })
    })

    const result = await response.json()
    if (!response.ok || !result.success || !result.data?.token) {
      throw new Error(result.error?.message || '登录失败')
    }

    // 保存 Token（仅在内存中保存，页面刷新后会失效，需要重新登录）
    auth.value.token = result.data.token

    // 保存用户信息
    if (result.data.user) {
      auth.value.userInfo = result.data.user
      localStorage.setItem('jarvis_user_info', JSON.stringify(result.data.user))
    }

    // 如果免登录开启，将 Token 保存到 localStorage
    if (autoLoginEnabled.value) {
      localStorage.setItem('jarvis_auth_token', result.data.token)
    }

    // 登录成功后立即清除密码（安全最佳实践：密码只用一次，后续使用 Token）
    auth.value.password = ''

    return true
  } catch (error) {
    console.error('[AUTH] Login failed:', error)
    throw error
  }
}

// 登出函数
async function logout() {
  try {
    // 尝试调用后端登出API（撤销token）
    if (hasAuthToken()) {
      const { host, port } = getGatewayAddress()
      await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/auth/logout`, {
        method: 'POST'
      }).catch(() => {}) // 忽略网络错误
    }
  } finally {
    // 无论后端是否成功，都清除本地状态
    auth.value.token = ''
    auth.value.userInfo = null
    auth.value.password = ''
    userAccessibleNodes.value = null
    localStorage.removeItem('jarvis_auth_token')
    localStorage.removeItem('jarvis_user_info')

    // 断开所有WebSocket连接
    stopAgentListRefresh()
    sockets.value.forEach((ws, agentId) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    })
    sockets.value.clear()
    if (socket.value) {
      socket.value.close()
      socket.value = null
    }
    currentAgentId.value = null
    agentList.value = []
    agentStatuses.value.clear()

    // 清理聊天室状态
    chatClients.value = []
    chatRooms.value = []
    chatRoomMembers.value = []
    chatMessages.value = []
    myClientId.value = ''
    activeChatRoomId.value = ''
    activePrivateClientId.value = ''
    chatUnreadCount.value = 0
    chatUnreadMap.value = {}
    chatJoinedRooms.value = []
    saveChatJoinedRooms()

    showConnectModal.value = true
    connectErrorMessage.value = ''
  }
}

// 通用的带认证的 fetch 函数
function hasAuthToken() {
  return Boolean(auth.value.token)
}

// 获取当前有效的 Token（优先返回内存中的，其次返回 localStorage 的）
function getAuthToken() {
  // 优先返回内存中的 Token
  if (auth.value.token) {
    return auth.value.token
  }
  // 其次尝试从 localStorage 获取
  const savedToken = localStorage.getItem('jarvis_auth_token')
  if (savedToken) {
    auth.value.token = savedToken
    return savedToken
  }
  return null
}

// 刷新用户信息（确保display_name等字段最新）
async function refreshUserInfo() {
  if (!hasAuthToken()) return
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/auth/me`)
    if (response.ok) {
      const result = await response.json()
      if (result.success && result.data) {
        const userData = result.data.user || result.data
        auth.value.userInfo = userData
        localStorage.setItem('jarvis_user_info', JSON.stringify(userData))
      }
    }
  } catch (e) {
    console.warn('[AUTH] Failed to refresh user info:', e)
  }
}

// 尝试从 localStorage 加载已保存的 token 和用户信息
function loadSavedToken() {
  const savedToken = localStorage.getItem('jarvis_auth_token')
  if (savedToken) {
    auth.value.token = savedToken
    // 加载用户信息
    const savedUserInfo = localStorage.getItem('jarvis_user_info')
    if (savedUserInfo) {
      try {
        auth.value.userInfo = JSON.parse(savedUserInfo)
        if (auth.value.userInfo?.username) {
          username.value = auth.value.userInfo.username
        }
      } catch (e) {
        console.warn('[AUTH] Failed to parse saved user info')
      }
    }
    return true
  }
  return false
}

async function fetchWithAuth(url, options = {}) {
  if (!hasAuthToken()) {
    // 返回模拟401响应，触发统一401处理流程
    return new Response(
      JSON.stringify({success: false, error: {message: '未登录', code: 'UNAUTHORIZED'}}),
      {
        status: 401,
        headers: { 'Content-Type': 'application/json' }
      }
    )
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
  
  const response = await fetch(url, fetchOptions)
  
  // 检查401未授权错误
  if (response.status === 401) {
    auth.value.token = ''
    auth.value.userInfo = null
    userAccessibleNodes.value = null
    localStorage.removeItem('jarvis_auth_token')
    localStorage.removeItem('jarvis_user_info')
    showConnectModal.value = true
    connectErrorMessage.value = '登录已过期，请重新登录'
    stopAgentListRefresh()
  }
  
  return response
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
const showAdminPanel = ref(false) // 管理面板
const showAgentSidebar = ref(false)    // Agent 侧边栏（默认收起）
const agentSidebarRef = ref(null)     // Agent 侧边栏组件引用（用于调用宠物显隐）
const showTerminalPanel = ref(false)  // 终端面板
const showChatPanel = ref(false)     // 聊天室面板
const showEditorPanel = ref(false)    // 编辑器浮动面板
const terminalDetached = ref(false)  // 终端面板是否已分离为浮动模式
const chatDetached = ref(false)     // 聊天室面板是否已分离为浮动模式
const editorDetached = ref(false)   // 编辑器面板是否已分离为浮动模式
const sessionDetachedPanels = ref(new Set())  // 已分离为浮动模式的 SessionPanel ID 集合
const sessionPanelRefs = new Map()  // panelId -> SessionPanel 组件实例

function setSessionPanelRef(panelId, el) {
  if (el) {
    sessionPanelRefs.set(panelId, el)
  } else {
    sessionPanelRefs.delete(panelId)
  }
}

const showMobileMenu = ref(false)     // 移动端菜单
const activeWindow = ref(null)        // 当前焦点窗口: 'terminal' | 'editor' | 'chat' | 'session' | null

// Diff 浮动窗口状态
const showDiffModal = ref(false)      // 显示diff浮动窗口
const diffContent = ref('')           // diff内容
const diffLoading = ref(false)        // 加载状态

// Rules 浮动窗口状态
const showRulesModal = ref(false)     // 显示rules浮动窗口
const rulesContent = ref([])          // rules内容（规则列表）
const rulesLoading = ref(false)       // 加载状态
const rulesLoadedContent = ref('')    // 已加载规则的具体内容

// 窗口z-index常量
const BASE_Z_INDEX = 1000
const ACTIVE_Z_INDEX = 1100

const AGENT_SIDEBAR_DEFAULT_WIDTH = 320
const AGENT_SIDEBAR_MIN_WIDTH = 240
const AGENT_SIDEBAR_MAX_WIDTH = 560
const AGENT_SIDEBAR_STORAGE_KEY = 'jarvis_agent_sidebar_width'
const EDITOR_SIDEBAR_DEFAULT_WIDTH = 320
const EDITOR_SIDEBAR_MIN_WIDTH = 200
const EDITOR_SIDEBAR_MAX_WIDTH = 560
const EDITOR_SIDEBAR_STORAGE_KEY = 'jarvis_editor_sidebar_width'

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

function normalizeEditorSidebarWidth(width) {
  return clamp(width, EDITOR_SIDEBAR_MIN_WIDTH, EDITOR_SIDEBAR_MAX_WIDTH)
}

function loadEditorSidebarWidth() {
  const savedValue = localStorage.getItem(EDITOR_SIDEBAR_STORAGE_KEY)
  if (!savedValue) {
    return EDITOR_SIDEBAR_DEFAULT_WIDTH
  }

  const parsedWidth = Number(savedValue)
  if (!Number.isFinite(parsedWidth)) {
    return EDITOR_SIDEBAR_DEFAULT_WIDTH
  }

  return normalizeEditorSidebarWidth(parsedWidth)
}

function saveEditorSidebarWidth() {
  localStorage.setItem(EDITOR_SIDEBAR_STORAGE_KEY, String(editorSidebarWidth.value))
}

const agentSidebarWidth = ref(loadAgentSidebarWidth())
const agentSidebarResizeState = ref({
  active: false,
  startX: 0,
  startWidth: AGENT_SIDEBAR_DEFAULT_WIDTH,
})
const editorSidebarWidth = ref(loadEditorSidebarWidth())
const editorSidebarResizeState = ref({
  active: false,
  startX: 0,
  startWidth: EDITOR_SIDEBAR_DEFAULT_WIDTH,
})
const EDITOR_PANEL_MIN_WIDTH = 360
const EDITOR_PANEL_MIN_HEIGHT = 260
const EDITOR_PANEL_STORAGE_KEY = 'jarvis_editor_panel_rect'
const editorResizeDirections = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
const PANEL_DRAG_ACTIVATION_DISTANCE = 4

// 窗口最大化状态
const isEditorMaximized = ref(false)
const isTerminalMaximized = ref(false)
const isChatMaximized = ref(false)
const editorPanelRectBeforeMaximize = ref(null)
const terminalPanelRectBeforeMaximize = ref(null)
const chatPanelRectBeforeMaximize = ref(null)

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
const editorPanelRef = ref(null)
const editorContainerRef = computed(() => editorPanelRef.value?.editorContainerRef || null)
// 编辑器多实例管理（类似 terminalSessions）
const editorSessions = ref([])  // [{ agent_id, agent_name, tabs: [], activeTabPath: null, editorModels: new Map(), cmEditorView: null }]
const activeEditorSessionId = ref(null)  // 当前激活的编辑器会话 agent_id

// 保持向后兼容的计算属性
const editorTabs = computed(() => {
  const session = editorSessions.value.find(s => s.agent_id === activeEditorSessionId.value)
  return session ? session.tabs : []
})
const activeEditorTabPath = computed(() => {
  const session = editorSessions.value.find(s => s.agent_id === activeEditorSessionId.value)
  return session ? session.activeTabPath : null
})
const activeEditorSession = computed(() => {
  return editorSessions.value.find(s => s.agent_id === activeEditorSessionId.value) || null
})
const editorModels = new Map() // path -> { state: EditorState, content: string }
let cmEditorView = null // CodeMirror 6 EditorView instance
let editorFileHeartbeatTimer = null
// Compartment 实例用于动态重配置编辑器的可编辑状态
const editableCompartment = new Compartment()
const readOnlyCompartment = new Compartment()
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
// 顶部标题栏自动隐藏：默认隐藏，桌面端鼠标移到顶部感应区唤出，移动端经宠物菜单唤出
const isMobileLayout = computed(() => windowWidth.value <= 768)
const headerHidden = ref(true)
const headerHeight = ref(0)
let headerHideTimer = 0
const headerRef = ref(null)

function measureHeaderHeight() {
  if (headerRef.value) headerHeight.value = headerRef.value.offsetHeight
}
function showHeader() {
  clearTimeout(headerHideTimer)
  headerHidden.value = false
  requestAnimationFrame(measureHeaderHeight)
}
function hideHeader() {
  clearTimeout(headerHideTimer)
  measureHeaderHeight()
  headerHidden.value = true
}
function toggleHeader() {
  if (headerHidden.value) showHeader()
  else hideHeader()
}
// 鼠标移出标题栏后延时缩回（给用户移动到感应区的时间）
function scheduleHideHeader() {
  if (isMobileLayout.value) return
  clearTimeout(headerHideTimer)
  headerHideTimer = setTimeout(() => { headerHidden.value = true }, 300)
}
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
let diagramObserver = null

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

const recentWorkDirs = ref([])             // 最近使用的工作目录列表（最多20个，去重）
const renameInput = ref(null)               // 重命名输入框引用

// 最近使用的工作目录管理（localStorage持久化存储）
// 元素格式：{ path: string, nodeId: string }，按节点区分
function loadRecentWorkDirs() {
  try {
    const stored = localStorage.getItem('jarvis_recent_work_dirs')
    if (stored) {
      const parsed = JSON.parse(stored)
      // 兼容旧数据：旧格式为纯字符串数组，类型不匹配则清空
      const isValid = Array.isArray(parsed) && parsed.every(item =>
        item && typeof item === 'object' && typeof item.path === 'string' && typeof item.nodeId === 'string'
      )
      recentWorkDirs.value = isValid ? parsed : []
    } else {
      recentWorkDirs.value = []
    }
  } catch (error) {
    console.error('[HISTORY DIR] 加载历史记录失败:', error)
    recentWorkDirs.value = []
  }
}

function saveRecentWorkDir(path, nodeId) {
  try {
    const normalizedNodeId = String(nodeId || '').trim() || 'master'
    // 去重：过滤掉已存在的同节点同路径
    const filtered = recentWorkDirs.value.filter(item =>
      !(item.path === path && item.nodeId === normalizedNodeId)
    )
    // 新路径加到最前面
    const updated = [{ path, nodeId: normalizedNodeId }, ...filtered]
    // 只保留最近20个
    recentWorkDirs.value = updated.slice(0, 20)
    // 保存到localStorage
    localStorage.setItem('jarvis_recent_work_dirs', JSON.stringify(recentWorkDirs.value))
  } catch (error) {
    console.error('[HISTORY DIR] 保存历史记录失败:', error)
  }
}
// 文件树状态管理
const fileTreeState = ref(new Map())        // 每个 Agent 的文件树数据：agent_id -> treeData
const fileTreeExpanded = ref(new Map())     // 每个 Agent 的展开状态：agent_id -> Set(expandedPaths)
const fileTreeLoading = ref(new Map())      // 每个 Agent 的加载状态：agent_id -> Set(loadingPaths)
const expandedAgents = ref(new Set())       // 编辑器目录树中展开的 Agent 集合
const selectedAgentId = ref(null)         // 编辑器目录树中选中的 Agent ID
const showStoppedAgents = ref(false)      // 是否显示已停止的 Agent
const stoppedNodeCollapseState = ref(new Map()) // 已停止 Agent 节点分组的折叠状态：nodeId -> boolean (true表示折叠)

// 切换 Agent 在目录树中的展开状态
function toggleAgentExpanded(agentId) {
  // 设置选中的 Agent
  selectedAgentId.value = agentId
  
  if (expandedAgents.value.has(agentId)) {
    expandedAgents.value.delete(agentId)
  } else {
    expandedAgents.value.add(agentId)
    // 展开时确保该 Agent 的文件树已初始化
    const agent = agentList.value.find(a => a.agent_id === agentId)
    if (agent && !fileTreeState.value.has(agentId)) {
      initFileTree(agentId, agent.working_dir)
    }
  }
  // 手动触发响应式更新
  triggerRef(expandedAgents)
}

// 切换已停止 Agent 节点分组的折叠状态
function toggleStoppedNodeCollapse(nodeId) {
  const currentState = stoppedNodeCollapseState.value.get(nodeId) || false
  stoppedNodeCollapseState.value.set(nodeId, !currentState)
  triggerRef(stoppedNodeCollapseState)
}

// 检查已停止 Agent 节点分组是否折叠
function isStoppedNodeCollapsed(nodeId) {
  return stoppedNodeCollapseState.value.get(nodeId) || false
}

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

function startEditorSidebarResize(event) {
  if (windowWidth.value <= 768 || !showEditorSidebar.value) return

  editorSidebarResizeState.value = {
    active: true,
    startX: event.clientX,
    startWidth: editorSidebarWidth.value,
  }

  document.addEventListener('mousemove', onEditorSidebarResize)
  document.addEventListener('mouseup', stopEditorSidebarResize)
  event.preventDefault()
  event.stopPropagation()
}

function onEditorSidebarResize(event) {
  if (!editorSidebarResizeState.value.active) return

  const deltaX = event.clientX - editorSidebarResizeState.value.startX
  const nextWidth = editorSidebarResizeState.value.startWidth + deltaX
  editorSidebarWidth.value = normalizeEditorSidebarWidth(nextWidth)
}

function stopEditorSidebarResize() {
  if (!editorSidebarResizeState.value.active) {
    document.removeEventListener('mousemove', onEditorSidebarResize)
    document.removeEventListener('mouseup', stopEditorSidebarResize)
    return
  }

  editorSidebarResizeState.value = {
    active: false,
    startX: 0,
    startWidth: editorSidebarWidth.value,
  }

  document.removeEventListener('mousemove', onEditorSidebarResize)
  document.removeEventListener('mouseup', stopEditorSidebarResize)
  saveEditorSidebarWidth()
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
    layoutCodeMirrorEditor()
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

// 聊天室窗口最大化/还原
function toggleChatMaximize() {
  if (isChatMaximized.value) {
    // 还原
    if (chatPanelRectBeforeMaximize.value) {
      chatPanelRect.value = { ...chatPanelRectBeforeMaximize.value }
    }
    isChatMaximized.value = false
  } else {
    // 最大化
    chatPanelRectBeforeMaximize.value = { ...chatPanelRect.value }
    chatPanelRect.value = {
      top: 0,
      left: 0,
      width: window.innerWidth,
      height: window.innerHeight,
    }
    isChatMaximized.value = true
  }
}

function toggleChatPanelCollapse() {
  chatPanelCollapsed.value = !chatPanelCollapsed.value
}

function getEditorPanelBounds() {
  const HEADER_HEIGHT = 32 // 标题栏高度
  const MIN_VISIBLE_WIDTH = 100 // 至少保留100px面板宽度可见
  return {
    minTop: 0, // 标题栏不能拖到窗口顶部之外
    minLeft: 0, // 标题栏不能拖到窗口左侧之外
    maxLeft: window.innerWidth - MIN_VISIBLE_WIDTH, // 保留至少100px面板宽度可见
    maxTop: window.innerHeight - HEADER_HEIGHT, // 保留标题栏高度可见
    maxWidth: window.innerWidth,
    maxHeight: window.innerHeight,
  }
}

function ensureEditorPanelInViewport() {
  const HEADER_HEIGHT = 32 // 标题栏高度
  const MIN_VISIBLE_WIDTH = 100 // 至少保留100px面板宽度可见
  const maxWidth = Math.max(window.innerWidth, EDITOR_PANEL_MIN_WIDTH)
  const maxHeight = Math.max(window.innerHeight, EDITOR_PANEL_MIN_HEIGHT)

  editorPanelRect.value.width = clamp(editorPanelRect.value.width, EDITOR_PANEL_MIN_WIDTH, maxWidth)
  editorPanelRect.value.height = clamp(editorPanelRect.value.height, EDITOR_PANEL_MIN_HEIGHT, maxHeight)

  // 标题栏不能移出窗口
  editorPanelRect.value.left = clamp(
    editorPanelRect.value.left,
    0, // 标题栏不能拖到窗口左侧之外
    window.innerWidth - MIN_VISIBLE_WIDTH // 保留至少100px面板宽度可见
  )
  editorPanelRect.value.top = clamp(
    editorPanelRect.value.top,
    0, // 标题栏不能拖到窗口顶部之外
    window.innerHeight - HEADER_HEIGHT // 保留标题栏高度可见
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

// ===== 蓝色系 CodeMirror 主题 =====
const blueDarkTheme = CMEditorView.theme({
  '&': {
    color: '#a8c8e8',
    backgroundColor: '#0d1b2a',
    fontFamily: "'Consolas', 'Microsoft YaHei', monospace",
  },
  '.cm-content': {
    caretColor: '#528bff',
    fontFamily: "'Consolas', 'Microsoft YaHei', monospace",
  },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: '#528bff' },
  '&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': { backgroundColor: '#264f78' },
  '.cm-panels': { backgroundColor: '#0a1522', color: '#a8c8e8' },
  '.cm-panels.cm-panels-top': { borderBottom: '2px solid #1a2a3a' },
  '.cm-panels.cm-panels-bottom': { borderTop: '2px solid #1a2a3a' },
  '.cm-searchMatch': {
    backgroundColor: '#72a1ff59',
    outline: '1px solid #457dff',
  },
  '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: '#6199ff2f' },
  '.cm-activeLine': { backgroundColor: '#1a2a3a55' },
  '.cm-selectionMatch': { backgroundColor: '#264f7855' },
  '&.cm-focused .cm-matchingBracket, &.cm-focused .cm-nonmatchingBracket': {
    backgroundColor: '#264f78aa',
  },
  '.cm-gutters': {
    backgroundColor: '#0d1b2a',
    color: '#5a7a9a',
    border: 'none',
    fontFamily: "'Consolas', 'Microsoft YaHei', monospace",
  },
  '.cm-activeLineGutter': { backgroundColor: '#1a2a3a' },
  '.cm-foldPlaceholder': {
    backgroundColor: 'transparent',
    border: 'none',
    color: '#5a7a9a',
  },
  '.cm-tooltip': {
    border: 'none',
    backgroundColor: '#16263a',
    fontFamily: "'Consolas', 'Microsoft YaHei', monospace",
  },
  '.cm-tooltip .cm-tooltip-arrow:before': {
    borderTopColor: 'transparent',
    borderBottomColor: 'transparent',
  },
  '.cm-tooltip .cm-tooltip-arrow:after': {
    borderTopColor: '#16263a',
    borderBottomColor: '#16263a',
  },
  '.cm-tooltip-autocomplete': {
    '& > ul > li[aria-selected]': {
      backgroundColor: '#1a2a3a',
      color: '#a8c8e8',
    },
  },
}, { dark: true })

const blueDarkHighlightStyle = CMHighlightStyle.define([
  { tag: cmTags.keyword, color: '#7aa2f7' },
  { tag: [cmTags.name, cmTags.deleted, cmTags.character, cmTags.propertyName, cmTags.macroName], color: '#f7768e' },
  { tag: [cmTags.function(cmTags.variableName), cmTags.labelName], color: '#82aaff' },
  { tag: [cmTags.color, cmTags.constant(cmTags.name), cmTags.standard(cmTags.name)], color: '#ff9e64' },
  { tag: [cmTags.definition(cmTags.name), cmTags.separator], color: '#a8c8e8' },
  { tag: [cmTags.typeName, cmTags.className, cmTags.number, cmTags.changed, cmTags.annotation, cmTags.modifier, cmTags.self, cmTags.namespace], color: '#e0af68' },
  { tag: [cmTags.operator, cmTags.operatorKeyword, cmTags.url, cmTags.escape, cmTags.regexp, cmTags.link, cmTags.special(cmTags.string)], color: '#56b6c2' },
  { tag: [cmTags.meta, cmTags.comment], color: '#5a7a9a' },
  { tag: cmTags.strong, fontWeight: 'bold' },
  { tag: cmTags.emphasis, fontStyle: 'italic' },
  { tag: cmTags.strikethrough, textDecoration: 'line-through' },
  { tag: cmTags.link, color: '#5a7a9a', textDecoration: 'underline' },
  { tag: cmTags.heading, fontWeight: 'bold', color: '#f7768e' },
  { tag: [cmTags.atom, cmTags.bool, cmTags.special(cmTags.variableName)], color: '#ff9e64' },
  { tag: [cmTags.processingInstruction, cmTags.string, cmTags.inserted], color: '#9ece6a' },
  { tag: cmTags.invalid, color: '#ffffff' },
])

const blueDark = [blueDarkTheme, CMSyntaxHighlighting(blueDarkHighlightStyle)]

function ensureCodeMirrorEditor() {
  if (cmEditorView || !editorContainerRef.value) return

  const updateListener = EditorView.updateListener.of((update) => {
    if (update.docChanged) {
      const path = activeEditorTabPath.value
      if (!path) return
      const tab = getEditorTabByPath(path)
      if (!tab) return
      tab.content = update.state.doc.toString()
      tab.isDirty = tab.content !== tab.originalContent
    }
  })

  cmEditorView = new EditorView({
    state: EditorState.create({
      doc: '',
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        highlightSpecialChars(),
        drawSelection(),
        rectangularSelection(),
        crosshairCursor(),
        syntaxHighlighting(defaultHighlightStyle),
        bracketMatching(),
        closeBrackets(),
        indentOnInput(),
        foldGutter(),
        highlightSelectionMatches(),
        history(),
        keymap.of([
          ...defaultKeymap,
          ...historyKeymap,
          ...closeBracketsKeymap,
          ...searchKeymap,
          indentWithTab,
        ]),
        blueDark,
        editableCompartment.of(EditorView.editable.of(isEditorEditable.value)),
        readOnlyCompartment.of(EditorState.readOnly.of(!isEditorEditable.value)),
        updateListener,
      ],
    }),
    parent: editorContainerRef.value,
  })
}

function layoutCodeMirrorEditor() {
  if (cmEditorView) {
    cmEditorView.requestMeasure()
  }
}

function activateEditorTab(path) {
  const session = activeEditorSession.value
  if (session) session.activeTabPath = path
  const modelData = editorModels.get(path)
  if (cmEditorView && modelData) {
    // 切换编辑器内容：通过 dispatch 替换整个 state
    const language = getLanguageFromFilename(path)
    const langExt = getLanguageExtension(language)
    const newState = EditorState.create({
      doc: modelData.content,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        highlightSpecialChars(),
        drawSelection(),
        rectangularSelection(),
        crosshairCursor(),
        syntaxHighlighting(defaultHighlightStyle),
        bracketMatching(),
        closeBrackets(),
        indentOnInput(),
        foldGutter(),
        highlightSelectionMatches(),
        history(),
        keymap.of([
          ...defaultKeymap,
          ...historyKeymap,
          ...closeBracketsKeymap,
          ...searchKeymap,
          indentWithTab,
        ]),
        blueDark,
        langExt,
        editableCompartment.of(EditorView.editable.of(isEditorEditable.value)),
        readOnlyCompartment.of(EditorState.readOnly.of(!isEditorEditable.value)),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            const currentPath = activeEditorTabPath.value
            if (!currentPath) return
            const tab = getEditorTabByPath(currentPath)
            if (!tab) return
            tab.content = update.state.doc.toString()
            tab.isDirty = tab.content !== tab.originalContent
          }
        }),
      ],
    })
    cmEditorView.setState(newState)
    nextTick(() => {
      layoutCodeMirrorEditor()
      cmEditorView.focus()
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
  // 使用传入的agentId对应的node_id
  const agent = agentList.value.find(a => a.agent_id === agentId)
  if (!agent) {
    throw new Error(`找不到Agent: ${agentId}`)
  }
  if (!agent.node_id) {
    throw new Error(`Agent没有node_id: ${agentId}`)
  }
  const targetNodeId = String(agent.node_id).trim()
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
  const agentId = activeEditorSessionId.value
  if (!agentId) return false
  return getVisibleFileTreeNodes(agentId).length > 0
})

async function ensureEditorSidebarFileTree(agent = activeEditorSession.value?.agent) {
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
      layoutCodeMirrorEditor()
    })
    return
  }
  nextTick(() => {
    layoutCodeMirrorEditor()
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
    layoutCodeMirrorEditor()
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
  // 使用当前Agent的agentId
  await openEditorFile(absolutePath, currentAgentId.value)
  await nextTick()
  const modelData = editorModels.get(absolutePath)
  if (!cmEditorView || !modelData) {
    return
  }

  const line = Number(lineNumber || 1)
  const col = Number(matchStart || 0) + 1
  const endCol = Math.max(col, Number(matchEnd || matchStart || 0) + 1)

  // CodeMirror 6: 使用 dispatch 设置选区
  const doc = cmEditorView.state.doc
  const lineObj = doc.line(line)
  const from = lineObj.from + (col - 1)
  const to = lineObj.from + (endCol - 1)

  cmEditorView.dispatch({
    selection: { anchor: from, head: to },
    scrollIntoView: true,
  })
  cmEditorView.focus()
}

async function fetchFileContent(path, agentId = null) {
  const { host, port } = getGatewayAddress()
  // 如果提供了agentId，使用对应的node_id；否则使用当前激活编辑器会话的node_id
  let targetNodeId
  if (agentId) {
    const agent = agentList.value.find(a => a.agent_id === agentId)
    if (!agent) {
      throw new Error(`找不到Agent: ${agentId}`)
    }
    if (!agent.node_id) {
      throw new Error(`Agent没有node_id: ${agentId}`)
    }
    targetNodeId = String(agent.node_id).trim()
  } else {
    targetNodeId = getEditorTargetNodeId()
  }
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

async function fetchFileStat(path, agentId = null) {
  const { host, port } = getGatewayAddress()
  // 如果提供了agentId，使用对应的node_id；否则使用当前激活编辑器会话的node_id
  let targetNodeId
  if (agentId) {
    const agent = agentList.value.find(a => a.agent_id === agentId)
    if (!agent) {
      throw new Error(`找不到Agent: ${agentId}`)
    }
    if (!agent.node_id) {
      throw new Error(`Agent没有node_id: ${agentId}`)
    }
    targetNodeId = String(agent.node_id).trim()
  } else {
    targetNodeId = getEditorTargetNodeId()
  }
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

  const modelData = editorModels.get(path)
  if (modelData && modelData.content !== content) {
    modelData.content = content
    // 如果当前激活的标签是这个文件，更新编辑器内容
    if (activeEditorTabPath.value === path && cmEditorView) {
      cmEditorView.dispatch({
        changes: { from: 0, to: cmEditorView.state.doc.length, insert: content },
      })
    }
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

async function openEditorFile(path, agentId = null) {
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
  const session = activeEditorSession.value
  if (!session) return
  session.tabs.push(tab)
  session.activeTabPath = path

  try {
    const [content, fileStat] = await Promise.all([
      fetchFileContent(path, agentId),
      fetchFileStat(path, agentId),
    ])
    tab.content = content
    tab.originalContent = content
    tab.externalModified = false
    updateEditorTabFileStat(tab, fileStat)
    tab.loading = false

    let modelData = editorModels.get(path)
    if (!modelData) {
      modelData = { content, language: tab.language }
      editorModels.set(path, modelData)
    }
    modelData.content = content

    await nextTick()
    // 确保编辑器容器存在（当从无标签状态打开时需要等待DOM更新）
    let retryCount = 0
    while (!editorContainerRef.value && retryCount < 10) {
      await new Promise(resolve => setTimeout(resolve, 50))
      retryCount++
    }
    // 如果 cmEditorView 已不在 DOM 中（tabs 从空变为非空时 v-else 重建了容器），
    // 需要销毁旧实例并重新创建，否则编辑器无法挂载到新容器。
    if (cmEditorView && !cmEditorView.dom.isConnected) {
      cmEditorView.destroy()
      cmEditorView = null
    }
    ensureCodeMirrorEditor()
    activateEditorTab(path)
  } catch (error) {
    tab.loading = false
    tab.error = error.message || '读取文件失败'
  }
}

async function saveEditorTab(path) {
  const tab = getEditorTabByPath(path)
  if (!tab) return

  const modelData = editorModels.get(path)
  const content = modelData ? modelData.content : tab.content

  const { host, port } = getGatewayAddress()
  const targetNodeId = getEditorTargetNodeId()
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
  if (cmEditorView) {
    // CodeMirror 6: 通过 compartment 的 reconfigure 方法动态切换 editable 和 readOnly
    cmEditorView.dispatch({
      effects: [
        editableCompartment.reconfigure(EditorView.editable.of(isEditorEditable.value)),
        readOnlyCompartment.reconfigure(EditorState.readOnly.of(!isEditorEditable.value)),
      ],
    })
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

// 为 Agent 创建/打开编辑器会话
function createEditorForAgent(agent) {
  if (!socket.value) {
    console.warn('[editor-session] No socket connection')
    return
  }

  const agentId = agent.agent_id
  const agentName = agent.name || agent.agent_type

  // 检查是否已存在该 Agent 的编辑器会话
  let session = editorSessions.value.find(s => s.agent_id === agentId)
  if (!session) {
    // 创建新的编辑器会话
    session = {
      agent_id: agentId,
      agent_name: agentName,
      agent: agent,
      tabs: [],
      activeTabPath: null,
      editorModels: new Map(),
      cmEditorView: null,
      isEditable: false,
      showSidebar: true,
      sidebarView: 'files'
    }
    editorSessions.value.push(session)
  }

  // 切换到该会话
  activeEditorSessionId.value = agentId
  showEditorPanel.value = true

}

// 关闭编辑器会话
async function closeEditorSession(agentId) {
  const sessionIndex = editorSessions.value.findIndex(s => s.agent_id === agentId)
  if (sessionIndex === -1) return

  const session = editorSessions.value[sessionIndex]

  // 检查是否有未保存的标签
  const hasDirty = session.tabs.some(tab => tab.isDirty)
  if (hasDirty) {
    const confirmed = await new Promise((resolve) => {
      showConfirm(
        `${session.agent_name} 的编辑器存在未保存修改，确定关闭吗？`,
        () => resolve(true),
        () => resolve(false),
        false
      )
    })
    if (!confirmed) return
  }

  // 清理编辑器模型
  session.editorModels.clear()

  // 清理 CodeMirror 编辑器
  if (session.cmEditorView) {
    session.cmEditorView.destroy()
    session.cmEditorView = null
  }

  // 从数组中移除
  editorSessions.value.splice(sessionIndex, 1)

  // 如果关闭的是当前激活的会话，切换到另一个
  if (activeEditorSessionId.value === agentId) {
    activeEditorSessionId.value = editorSessions.value.length > 0 ? editorSessions.value[0].agent_id : null
    if (!activeEditorSessionId.value) {
      showEditorPanel.value = false
    }
  }

}

// 切换编辑器会话
function switchEditorSession(agentId) {
  const session = editorSessions.value.find(s => s.agent_id === agentId)
  if (!session) return

  activeEditorSessionId.value = agentId
  showEditorPanel.value = true
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

  const session = activeEditorSession.value
  if (!session) return
  const index = session.tabs.findIndex(item => item.path === path)
  if (index === -1) return

  const wasActive = session.activeTabPath === path
  session.tabs.splice(index, 1)

  const modelData = editorModels.get(path)
  if (modelData) {
    editorModels.delete(path)
  }

  if (wasActive) {
    const nextTab = session.tabs[index] || session.tabs[index - 1] || null
    if (nextTab) {
      activateEditorTab(nextTab.path)
    } else {
      session.activeTabPath = null
      // 不销毁 cmEditorView，保留编辑器实例和容器 DOM，
      // 否则 v-if/v-else 切换会导致 editorContainerRef 消失，
      // 后续打开文件时无法重新创建编辑器。
      // 仅清空内容即可。
      if (cmEditorView) {
        cmEditorView.dispatch({
          changes: { from: 0, to: cmEditorView.state.doc.length, insert: '' },
        })
      }
    }
  }
}

async function handleFileTreeNodeClick(agentId, node) {
  if (node.type === 'directory') {
    await toggleNodeExpand(agentId, node)
    return
  }

  await openEditorFile(node.path, agentId)
}

// 消息和终端
const allOutputs = ref(new Map()) // 按 agent_id 存储消息：agent_id -> outputs array
const outputs = computed(() => allOutputs.value.get(currentAgentId.value) || []) // 当前 Agent 的消息
const outputList = ref(null)
const panelOutputLists = new Map() // panelId -> outputList element
let historyScrollListenerEl = null // 当前绑定滚动监听的元素
let historyScrollHandler = null // 滚动监听处理函数
let historyScrollDebounceTimer = null // 滚动防抖定时器

// 从历史记录中获取指定 agent 的最后一条消息的 seq
function getAgentLastSeq(agentId) {
  try {
    const messages = historyStorage.getHistoryForAgent(agentId)
    if (messages.length === 0) return -1
    // 消息已按时间排序，取最后一条有 seq 的消息
    for (let i = messages.length - 1; i >= 0; i--) {
      if (typeof messages[i].seq === 'number') {
        return messages[i].seq
      }
    }
    return -1
  } catch (error) {
    console.error('[SYNC] Failed to get last seq for agent:', agentId, error)
    return -1
  }
}
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

// 输入控制
const inputText = ref('')
const inputMode = ref('multi') // 当前显示Agent的输入模式
const inputRequests = ref(new Map()) // 每个 Agent 的输入请求（key: agentId, value: {tip, mode, preset, request_id}）
const inputTip = ref('') // 当前显示Agent的输入提示
const panelInputTexts = ref(new Map()) // 每个 Panel 的输入文本（key: agentId, value: string）
const panelInputModes = ref(new Map()) // 每个 Panel 的输入模式（key: agentId, value: 'multi'|'single'）
const panelInputTips = ref(new Map()) // 每个 Panel 的输入提示（key: agentId, value: string）
const panelInputPasswords = ref(new Map()) // 每个 Panel 的密码输入标志（key: agentId, value: boolean）

const pendingInputAgentId = ref(null) // 当前待响应输入请求所属 Agent（用于聚焦正确的输入框）
const pendingConfirmAgentId = ref(null) // 当前待响应确认请求所属 Agent
const panelConfirmData = ref(new Map()) // 每个 Panel 的确认数据（key: agentId, value: {message, defaultConfirm}）
const panelAutoScrolls = ref(new Map()) // 每个 Panel 的自动滚动开关（key: agentId, value: boolean，默认 true）
const panelAutoReads = ref(new Map()) // 每个 Panel 的自动朗读开关（key: agentId, value: boolean，默认 false）
const inputBuffers = ref(new Map()) // 每个 Agent 的输入缓冲区（key: agentId, value：内容）

// 历史输入记录
const INPUT_HISTORY_STORAGE_KEY = 'jarvis_input_history'
const MAX_INPUT_HISTORY_COUNT = 100
const COMPLETION_USAGE_STORAGE_KEY = 'jarvis_completion_usage_stats'

const inputHistory = ref([]) // 历史输入记录数组
const historyIndex = ref(-1) // 当前浏览的历史记录索引（-1 表示未浏览历史）
const currentTempInput = ref('') // 用户正在编辑的临时内容
const panelTempInputs = ref(new Map()) // 每个 Panel 的临时编辑内容 (key: agentId, value: 内容)

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

// Panel 布局管理
const panels = ref([]) // [{ id, agentId: null }]
const activePanelId = ref(null)
const MAX_PANELS = 6

// 创建新 Panel
function createPanel() {
  if (panels.value.length >= MAX_PANELS) {
    showToast(`最多支持 ${MAX_PANELS} 个 Panel`, 'warning')
    return
  }
  const panel = {
    id: `panel-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    agentId: null
  }
  panels.value.push(panel)
  activePanelId.value = panel.id
}

// 关闭 Panel
function closePanel(panelId) {
  const index = panels.value.findIndex(p => p.id === panelId)
  if (index === -1) return
  const panel = panels.value[index]
  // 如果 Panel 中有 Agent，关闭 Agent 会话
  if (panel.agentId) {
    closeAgentInPanel(panelId)
  }
  panels.value.splice(index, 1)
  panelOutputLists.delete(panelId)
  sessionPanelRefs.delete(panelId)
  // 如果该 Panel 已 detach，同时从 detach 集合中移除
  if (sessionDetachedPanels.value.has(panelId)) {
    sessionDetachedPanels.value.delete(panelId)
    triggerRef(sessionDetachedPanels)
  }
  // 如果关闭的是当前激活的 Panel，激活相邻 Panel
  if (activePanelId.value === panelId) {
    if (panels.value.length > 0) {
      const newIndex = Math.min(index, panels.value.length - 1)
      const nextPanel = panels.value[newIndex]
      activePanelId.value = nextPanel.id
      // 关闭当前 Panel 时 currentAgentId 会被清空，需切回新激活 Panel 的 Agent
      if (nextPanel.agentId && currentAgentId.value !== nextPanel.agentId) {
        const nextAgent = agentList.value.find(a => a.agent_id === nextPanel.agentId)
        if (nextAgent) switchAgent(nextAgent)
      }
    } else {
      activePanelId.value = null
    }
  }
}

// 关闭 Panel 中的 Agent（保留 Panel）
function closeAgentInPanel(panelId) {
  const panel = panels.value.find(p => p.id === panelId)
  if (!panel || !panel.agentId) return
  const agentId = panel.agentId
  panel.agentId = null
  panelOutputLists.delete(panelId)
  // 清除该 Agent 的 Panel 内嵌确认数据
  panelConfirmData.value.delete(agentId)
  // 清除该 Agent 的 Panel 自动滚动开关
  panelAutoScrolls.value.delete(agentId)
  // 清除该 Agent 的 Panel 自动朗读开关
  panelAutoReads.value.delete(agentId)
  // 清除该 Agent 的 Panel 输入状态
  panelInputTexts.value.delete(agentId)
  panelInputTips.value.delete(agentId)
  panelInputModes.value.delete(agentId)
  // 如果关闭的是当前 Agent，清空当前 Agent ID
  if (currentAgentId.value === agentId) {
    currentAgentId.value = null
  }
}

// 激活 Panel
function activatePanel(panelId) {
  activePanelId.value = panelId
  const panel = panels.value.find(p => p.id === panelId)
  if (panel && panel.agentId) {
    // 如果 Panel 中有 Agent，切换当前 Agent
    const agent = agentList.value.find(a => a.agent_id === panel.agentId)
    if (agent) {
      switchAgent(agent)
    }
  }
}

// 在 Panel 中打开 Agent（替代 switchAgent）
function openAgentInPanel(agent, panelId = null) {
  // 移动端不支持多 Panel，直接切换
  if (windowWidth.value <= 768) {
    // 确保至少有一个 Panel 存在
    if (panels.value.length === 0) {
      createPanel()
    }
    // 将 Agent 放入当前激活的 Panel
    const targetPanel = panels.value.find(p => p.id === activePanelId.value) || panels.value[0]
    if (targetPanel) {
      targetPanel.agentId = agent.agent_id
    }
    switchAgent(agent)
    return
  }
  // 如果该 Agent 已在某个 Panel 中打开，直接激活该 Panel
  const existingPanel = panels.value.find(p => p.agentId === agent.agent_id)
  if (existingPanel) {
    activePanelId.value = existingPanel.id
    switchAgent(agent)
    return
  }
  // 如果没有指定 Panel，使用当前激活的 Panel
  let targetPanel = null
  if (panelId) {
    targetPanel = panels.value.find(p => p.id === panelId)
  } else {
    targetPanel = panels.value.find(p => p.id === activePanelId.value)
  }
  // 如果当前激活的 Panel 已有 Agent，创建新 Panel
  if (!targetPanel || targetPanel.agentId) {
    if (panels.value.length >= MAX_PANELS) {
      showToast(`最多支持 ${MAX_PANELS} 个 Panel`, 'warning')
      return
    }
    targetPanel = {
      id: `panel-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      agentId: null
    }
    panels.value.push(targetPanel)
  }
  targetPanel.agentId = agent.agent_id
  activePanelId.value = targetPanel.id
  // 切换当前 Agent
  switchAgent(agent)
}

// 「在当前 Panel 中打开 Agent」：命令面板按 Enter 时使用
// - Agent 已在某个 Panel 中：激活该 Panel
// - 否则放入当前激活的 Panel（覆盖其中已有的 Agent）；没有 Panel 时创建
function openAgentInCurrentPanel(agent) {
  if (!agent) return
  // 移动端不支持多 Panel，直接切换
  if (windowWidth.value <= 768) {
    openAgentInPanel(agent)
    return
  }
  const existingPanel = panels.value.find(p => p.agentId === agent.agent_id)
  if (existingPanel) {
    activePanelId.value = existingPanel.id
    switchAgent(agent)
    return
  }
  let targetPanel = panels.value.find(p => p.id === activePanelId.value)
  if (!targetPanel) {
    if (panels.value.length >= MAX_PANELS) {
      showToast(`最多支持 ${MAX_PANELS} 个 Panel`, 'warning')
      return
    }
    targetPanel = { id: `panel-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, agentId: null }
    panels.value.push(targetPanel)
  } else if (targetPanel.agentId && targetPanel.agentId !== agent.agent_id) {
    // 复用当前 Panel：先清掉其中已有 Agent 的 Panel 级状态，避免残留
    closeAgentInPanel(targetPanel.id)
  }
  targetPanel.agentId = agent.agent_id
  activePanelId.value = targetPanel.id
  switchAgent(agent)
}

// 「在新的 Panel 中打开 Agent」：命令面板按 Tab 时使用
// - Agent 已在某个 Panel 中：激活它（避免重复打开同一 Agent）
// - 否则始终新建 Panel；达到数量上限时回退到在当前 Panel 中打开
function openAgentInNewPanel(agent) {
  if (!agent) return
  if (windowWidth.value <= 768) {
    openAgentInPanel(agent)
    return
  }
  const existingPanel = panels.value.find(p => p.agentId === agent.agent_id)
  if (existingPanel) {
    activePanelId.value = existingPanel.id
    switchAgent(agent)
    return
  }
  if (panels.value.length >= MAX_PANELS) {
    showToast(`最多支持 ${MAX_PANELS} 个 Panel，已在当前面板打开`, 'warning')
    openAgentInCurrentPanel(agent)
    return
  }
  const targetPanel = { id: `panel-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, agentId: null }
  panels.value.push(targetPanel)
  targetPanel.agentId = agent.agent_id
  activePanelId.value = targetPanel.id
  switchAgent(agent)
}

// 获取 Panel 中的 Agent
function getPanelAgent(panel) {
  if (!panel || !panel.agentId) return null
  return agentList.value.find(a => a.agent_id === panel.agentId) || null
}

// 获取 Panel 的消息列表
function getPanelMessages(panel) {
  if (!panel || !panel.agentId) return []
  return allOutputs.value.get(panel.agentId) || []
}

// 获取 Panel 的输入文本
function getPanelInputText(panel) {
  if (!panel || !panel.agentId) return ''
  return panelInputTexts.value.get(panel.agentId) || ''
}

// 获取 Panel 的输入模式
function getPanelInputMode(panel) {
  if (!panel || !panel.agentId) return 'multi'
  return panelInputModes.value.get(panel.agentId) || 'multi'
}

// 获取 Panel 的输入提示
function getPanelInputTip(panel) {
  if (!panel || !panel.agentId) return ''
  return panelInputTips.value.get(panel.agentId) || ''
}

// 获取 Panel 的密码输入标志
function getPanelInputPassword(panel) {
  if (!panel || !panel.agentId) return false
  return panelInputPasswords.value.get(panel.agentId) || false
}

// 获取 Panel 的输入请求
function getPanelInputRequest(panel) {
  if (!panel || !panel.agentId) return null
  return inputRequests.value.get(panel.agentId) || null
}

// 获取 Panel 的 Agent 状态
function getPanelAgentStatus(panel) {
  if (!panel || !panel.agentId) return null
  return agentStatuses.value.get(panel.agentId) || null
}

// 获取 Panel 的确认数据
function getPanelConfirmData(panel) {
  if (!panel || !panel.agentId) return null
  return panelConfirmData.value.get(panel.agentId) || null
}

// 获取 Panel 的自动滚动开关状态
function getPanelAutoScroll(panel) {
  if (!panel || !panel.agentId) return true
  return panelAutoScrolls.value.get(panel.agentId) !== false
}

// 切换 Panel 的自动滚动开关
function togglePanelAutoScroll(panel, value) {
  if (!panel || !panel.agentId) return
  panelAutoScrolls.value.set(panel.agentId, value)
}

// 判断指定 Agent 是否启用自动滚动（默认 true）
function isAutoScrollEnabled(agentId) {
  if (!agentId) return true
  return panelAutoScrolls.value.get(agentId) !== false
}

// 获取 Panel 的自动朗读开关状态（默认 false）
function getPanelAutoRead(panel) {
  if (!panel || !panel.agentId) return false
  return panelAutoReads.value.get(panel.agentId) === true
}

// 切换 Panel 的自动朗读开关
function togglePanelAutoRead(panel, value) {
  if (!panel || !panel.agentId) return
  panelAutoReads.value.set(panel.agentId, value)
  if (!value) {
    stopAutoRead()
  }
}

// 判断指定 Agent 是否启用自动朗读（默认 false）
function isAutoReadEnabled(agentId) {
  if (!agentId) return false
  return panelAutoReads.value.get(agentId) === true
}

// 获取 Panel 的终端列表
function getPanelTerminals(panel) {
  if (!panel || !panel.agentId) return []
  return terminals.value.filter(t => t.agentId === panel.agentId)
}

// 获取 Panel 的终端宿主
function getPanelTerminalHosts(panel) {
  if (!panel || !panel.agentId) return new Map()
  const hosts = new Map()
  for (const [sessionKey, hostEl] of terminalHosts.value.entries()) {
    const [agentId] = sessionKey.split(':')
    if (agentId === panel.agentId) {
      hosts.set(sessionKey, hostEl)
    }
  }
  return hosts
}

// 获取 Panel 的输入禁用状态
function getPanelInputDisabled(panel) {
  if (!panel || !panel.agentId) return true
  const agent = getPanelAgent(panel)
  if (!agent || agent.status !== 'running') return true
  return false
}

// 获取 Panel 的等待多行禁用状态
function getPanelWaitingMultiDisabled(panel) {
  if (!panel || !panel.agentId) return true
  const statusData = agentStatuses.value.get(panel.agentId)
  const executionStatus = statusData?.execution_status || 'running'
  // 等待多行输入时不禁用（允许输入），其他状态禁用
  return executionStatus !== 'waiting_multi'
}

// 获取 Panel 的流式消息
function getPanelStreamingMessages(panel) {
  if (!panel || !panel.agentId) return new Map()
  const msgs = new Map()
  for (const [agentId, msg] of streamingMessages.value.entries()) {
    if (agentId === panel.agentId) {
      msgs.set(agentId, msg)
    }
  }
  return msgs
}

// 获取 Panel 的历史加载状态
function getPanelHistoryState(panel) {
  if (!panel || !panel.agentId) return { isLoading: false, hasMore: false }
  return {
    isLoading: isLoadingHistory.value,
    hasMore: hasMoreHistory.value
  }
}

// 内嵌面板数量（非 detach 且可见的面板）
const embeddedPanelCount = computed(() => {
  let count = 0
  if (showTerminalPanel.value && !terminalDetached.value) count++
  if (showChatPanel.value && !chatDetached.value) count++
  if (showEditorPanel.value && !editorDetached.value) count++
  // 内嵌 SessionPanel 数量 = 总面板数 - 已 detach 的面板数
  count += panels.value.filter(p => !sessionDetachedPanels.value.has(p.id)).length
  return count
})

// 当前是否没有任何可见的内嵌 Panel（用于展示空状态欢迎背景）
const hasNoPanel = computed(() => embeddedPanelCount.value === 0)

// 获取 Panel 的布局样式
function getPanelLayout() {
  const count = embeddedPanelCount.value
  if (count === 0) return {}
  if (count === 1) return { gridTemplateColumns: '1fr', gridTemplateRows: '1fr' }
  if (count === 2) return { gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr' }
  if (count === 3) return { gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr' }
  if (count === 4) return { gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr' }
  if (count === 5) return { gridTemplateColumns: '1fr 1fr 1fr', gridTemplateRows: '1fr 1fr' }
  return { gridTemplateColumns: '1fr 1fr 1fr', gridTemplateRows: '1fr 1fr' }
}

// 切换面板的 detach 状态（内嵌 <-> 浮动）
function detachPanel(type, panelId = null) {
  if (type === 'terminal') {
    terminalDetached.value = !terminalDetached.value
  } else if (type === 'chat') {
    chatDetached.value = !chatDetached.value
  } else if (type === 'editor') {
    editorDetached.value = !editorDetached.value
  } else if (type === 'session' && panelId) {
    if (sessionDetachedPanels.value.has(panelId)) {
      sessionDetachedPanels.value.delete(panelId)
    } else {
      sessionDetachedPanels.value.add(panelId)
      // 初始化该面板的浮动位置
      if (!sessionPanelRects.value[panelId]) {
        sessionPanelRects.value[panelId] = loadSessionPanelRect(panelId)
      }
    }
    triggerRef(sessionDetachedPanels)
  }
}

// Panel 网格布局样式（计算属性）
const panelGridStyle = computed(() => {
  return getPanelLayout()
})

// 获取 Panel 的缓冲输入状态
function getPanelHasBufferedInput(panel) {
  if (!panel || !panel.agentId) return false
  return inputBuffers.value.has(panel.agentId)
}

// 从 Panel 发送消息
function sendFromPanel(panel) {
  if (!panel || !panel.agentId) return
  const agentId = panel.agentId
  const agent = getPanelAgent(panel)
  if (!agent || agent.status !== 'running') return

  // 单行输入模式：允许发送空字符串
  // 多行输入模式：不允许发送空字符串（但缓冲区有内容时除外）
  const panelInput = panelInputTexts.value.get(agentId) || ''
  const panelInputMode = getPanelInputMode(panel)
  const hasBuffered = inputBuffers.value.has(agentId) && (inputBuffers.value.get(agentId) || '').trim()
  let userInput
  if (panelInputMode === 'single') {
    userInput = panelInput
  } else {
    userInput = panelInput.trim()
    if (!userInput && !hasBuffered) return
  }

  // 获取当前运行状态
  const statusData = agentStatuses.value.get(agentId)
  const executionStatus = statusData?.execution_status || 'running'

  // 等待确认状态：Enter 发送确认结果
  if (executionStatus === 'waiting_confirm') {
    const trimmedInput = userInput.trim().toLowerCase()
    // 空输入或 y/yes/确认 视为确认，n/no/取消 视为取消
    const confirmed = trimmedInput === '' || trimmedInput === 'y' || trimmedInput === 'yes' || trimmedInput === '确认' || trimmedInput === '是'
    sendConfirmResult(confirmed, agentId)
    // 清空输入框
    panelInputTexts.value.set(agentId, '')
    inputText.value = ''
    return
  }

  // 判断是发送到缓冲区还是直接发送
  if (panelInputMode === 'single' || executionStatus === 'waiting_multi') {
    // 后端正在等待输入，直接发送
    // 如果有缓冲区内容，先发送缓冲区内容
    let sendText = userInput
    if (hasBuffered) {
      const bufferedText = inputBuffers.value.get(agentId)
      inputBuffers.value.delete(agentId)
      sendText = bufferedText
      // 如果输入框也有内容，追加到缓冲区内容后面
      if (userInput) {
        sendText = `${bufferedText}\n${userInput}`
      }
    }
    const message = {
      type: 'input_result',
      payload: {
        text: sendText,
        agent_id: agentId,
        display_name: chatName.value || username.value || '',
        input_mode: panelInputMode,
      },
    }
    sendMessageToAgent(message, agentId)
    // 从Map中删除该Agent的输入请求
    inputRequests.value.delete(agentId)
  } else if (hasBuffered) {
    // 有缓冲区内容且后端没有等待输入，发送缓冲区内容
    sendBufferedInput(agentId)
    // 如果输入框也有内容，追加到缓冲区
    if (userInput) {
      const existingText = inputBuffers.value.get(agentId) || ''
      const nextValue = existingText ? `${existingText}\n${userInput}` : userInput
      inputBuffers.value.set(agentId, nextValue)
      appendOutput({
        output_type: 'system',
        agent_name: 'system',
        text: '✓ 输入已追加到缓冲区，等待后端请求',
        lang: 'text',
      }, agentId)
    }
  } else {
    // 后端没有等待输入，保存到缓冲区
    const existingText = inputBuffers.value.get(agentId) || ''
    const nextValue = existingText ? `${existingText}\n${userInput}` : userInput
    inputBuffers.value.set(agentId, nextValue)
    appendOutput({
      output_type: 'system',
      agent_name: 'system',
      text: '✓ 输入已追加到缓冲区，等待后端请求',
      lang: 'text',
    }, agentId)
  }

  // 保存到历史记录
  saveToHistory(userInput)
  panelInputTexts.value.set(agentId, '')
  inputText.value = ''
}

// 从 Panel 完成输入
function completeFromPanel(panel) {
  if (!panel || !panel.agentId) return
  const agentId = panel.agentId
  const statusData = agentStatuses.value.get(agentId)
  const executionStatus = statusData?.execution_status || 'running'
  // 记住原始状态，确认/取消后恢复
  const originalStatus = executionStatus

  // 使用 Panel 内嵌确认，而非全局弹出对话框
  panelConfirmData.value.set(agentId, {
    message: '确定要发送完成信号吗？',
    defaultConfirm: true,
    onConfirm: () => {
      if (executionStatus === 'waiting_multi') {
        // 后端正在等待多行输入，直接发送 Ctrl+C 信号
        const message = {
          type: 'input_result',
          payload: {
            text: '__CTRL_C_PRESSED__',
            agent_id: agentId,
            display_name: chatName.value || username.value || '',
            input_mode: 'single',
          },
        }
        sendMessageToAgent(message, agentId)
      } else {
        // 后端没有等待输入，将完成信号保存到缓冲区
        inputBuffers.value.set(agentId, '__CTRL_C_PRESSED__')
        appendOutput({
          output_type: 'system',
          agent_name: 'system',
          text: '✅ 完成信号已保存到缓冲区，下次需要输入时自动触发',
          lang: 'text',
        }, agentId)
      }
      // 恢复输入模式为多行
      inputMode.value = 'multi'
      panelInputModes.value.set(agentId, 'multi')
      inputTip.value = ''
      panelInputTips.value.set(agentId, '')
      // 恢复 Agent 状态为原始状态
      agentStatuses.value.set(agentId, {execution_status: originalStatus})
    },
    onCancel: () => {
      // 取消时恢复输入模式为多行
      inputMode.value = 'multi'
      panelInputModes.value.set(agentId, 'multi')
      inputTip.value = ''
      panelInputTips.value.set(agentId, '')
      // 恢复 Agent 状态为原始状态
      agentStatuses.value.set(agentId, {execution_status: originalStatus})
    },
  })

  // 同步设置 waiting_confirm 状态，使 handlePanelKeydown 中 Enter/y/n 键可响应
  agentStatuses.value.set(agentId, {execution_status: 'waiting_confirm'})
  // 确认请求使用单行输入模式，避免多行输入框抢占焦点
  inputMode.value = 'single'
  panelInputModes.value.set(agentId, 'single')
  inputTip.value = '确定要发送完成信号吗？ (Enter/y 确认, n 取消)'
  panelInputTips.value.set(agentId, '确定要发送完成信号吗？ (Enter/y 确认, n 取消)')

  // 聚焦输入框
  const sessionPanel = sessionPanelRefs.get(panel.id)
  if (sessionPanel?.focusInput) {
    sessionPanel.focusInput()
  }
}

// 从 Panel 打开补全
// 从 Panel 打开补全
async function openCompletionsFromPanel(panel) {
  if (!panel || !panel.agentId) return
  const agent = getPanelAgent(panel)
  if (!agent) {
    alert('请先选择一个 Agent')
    return
  }

  completionAgentId.value = panel.agentId
  completionSource.value = 'panel'
  // 由 @ 按钮触发时（未经过 handlePanelInputChange / handlePanelKeydown），
  // 输入框中并没有 @ 符号，需记录当前光标位置作为插入点，并标记无需删除 @
  if (completionCursorPos.value === -1) {
    const textarea = document.querySelector(`.input-wrapper textarea[data-agent-id="${panel.agentId}"]`) || document.querySelector('.input-wrapper textarea')
    if (textarea) {
      completionCursorPos.value = textarea.selectionStart
    }
    completionHasAtSymbol.value = false
  }
  completionSearch.value = ''
  selectedIndex.value = -1
  showCompletions.value = true
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(agent?.node_id || '').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `completions/${agent.agent_id}`))

    const result = await response.json()

    if (!response.ok) {
      alert(`获取补全列表失败: ${result.error?.message || result.detail || '未知错误'}`)
      return
    }

    if (result.success && result.data) {
      completions.value = sortCompletionItems(result.data)
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

// 从宠物大厅输入框打开补全：agentId 为大厅中对应宠物，cursorPos 为 @ 符号位置
async function onLobbyOpenCompletions(agentId, cursorPos) {
  if (!agentId) return
  const agent = agentList.value.find(a => a.agent_id === agentId)
  if (!agent) return

  completionAgentId.value = agentId
  completionSource.value = 'lobby'
  completionCursorPos.value = typeof cursorPos === 'number' ? cursorPos : -1
  completionHasAtSymbol.value = true
  completionSearch.value = ''
  selectedIndex.value = -1
  showCompletions.value = true
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(agent?.node_id || '').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `completions/${agentId}`))

    const result = await response.json()

    if (!response.ok) {
      alert(`获取补全列表失败: ${result.error?.message || result.detail || '未知错误'}`)
      return
    }

    if (result.success && result.data) {
      completions.value = sortCompletionItems(result.data)
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

// 处理 Panel 输入变化
function handlePanelInputChange(panel, event) {
  if (!panel || !panel.agentId) return
  const target = event.target
  // 更新该 Panel 的输入文本
  panelInputTexts.value.set(panel.agentId, target.value)
  // 同步全局输入文本（保持兼容）
  inputText.value = target.value
  const cursorPosition = target.selectionStart
  const textBeforeCursor = target.value.substring(0, cursorPosition)

  // 检测是否刚刚输入了@符号（包括中文输入法）
  if (textBeforeCursor.endsWith('@')) {
    const lastChar = textBeforeCursor.slice(-1)
    if (lastChar === '@') {
      completionCursorPos.value = cursorPosition - 1
      completionHasAtSymbol.value = true
      openCompletionsFromPanel(panel)
    }
  }
}

// 处理 Panel 键盘事件
function handlePanelKeydown(panel, event) {
  if (!panel || !panel.agentId) return
  const agentId = panel.agentId

  // @ 键：打开补全列表
  if (event.key === '@') {
    event.preventDefault()
    completionCursorPos.value = event.target.selectionStart
    completionHasAtSymbol.value = true
    openCompletionsFromPanel(panel)
    return
  }

  // waiting_confirm 状态：y/n 键直接发送确认结果，Enter 键触发默认操作
  const statusData = agentStatuses.value.get(agentId)
  const executionStatus = statusData?.execution_status || 'running'
  if (executionStatus === 'waiting_confirm') {
    if (event.key === 'y' || event.key === 'Y') {
      event.preventDefault()
      // 优先走 panelConfirmData 的 onConfirm 回调（如 completeFromPanel 场景）
      const confirmData = panelConfirmData.value.get(agentId)
      if (confirmData?.onConfirm) {
        handlePanelConfirm(panel)
      } else {
        sendConfirmResult(true, agentId)
      }
      return
    }
    if (event.key === 'n' || event.key === 'N') {
      event.preventDefault()
      // 优先走 panelConfirmData 的 onCancel 回调（如 completeFromPanel 场景）
      const confirmData = panelConfirmData.value.get(agentId)
      if (confirmData?.onCancel) {
        handlePanelCancelConfirm(panel)
      } else {
        sendConfirmResult(false, agentId)
      }
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const confirmData = panelConfirmData.value.get(agentId)
      const defaultConfirm = confirmData?.defaultConfirm !== false
      if (defaultConfirm) {
        handlePanelConfirm(panel)
      } else {
        handlePanelCancelConfirm(panel)
      }
      return
    }
  }

  // 单行输入模式：Enter 键直接提交
  if (event.key === 'Enter' && !event.ctrlKey && getPanelInputMode(panel) === 'single') {
    event.preventDefault()
    sendFromPanel(panel)
    return
  }

  // Ctrl+Enter / Ctrl+D 提交输入
  if (event.ctrlKey && (event.key === 'Enter' || event.key.toLowerCase() === 'd')) {
    event.preventDefault()
    sendFromPanel(panel)
    return
  }

  // Alt+T 触发终端命令执行
  if (event.altKey && (event.code === 'KeyT' || event.key === 't' || event.key === 'T')) {
    event.preventDefault()
    event.stopPropagation()
    panelInputTexts.value.set(agentId, '__ALT_T_PRESSED__')
    sendFromPanel(panel)
    return
  }

  // Ctrl+C 在等待多行输入且输入框为空时，触发完成功能
  // Ctrl+C 在非输入模式下且输入框为空时，发送人工介入消息
  if (event.ctrlKey && event.key === 'c') {
    const userInput = (panelInputTexts.value.get(agentId) || '').trim()
    const statusData = agentStatuses.value.get(agentId)
    const executionStatus = statusData?.execution_status || 'running'

    // 场景1：在等待多行输入且输入框为空时，触发完成功能
    if (executionStatus === 'waiting_multi' && !userInput) {
      event.preventDefault()
      completeFromPanel(panel)
      return
    }

    // 场景2：在非输入模式下（running）且输入框为空时，发送人工介入消息
    if (executionStatus === 'running' && !userInput) {
      event.preventDefault()
      const message = {
        type: 'manual_interrupt',
        payload: {},
      }
      sendMessageToAgent(message, agentId)
      return
    }
  }

  // 向上箭头：检查是否在第一行，是才触发历史
  // 带 Ctrl/Alt/Meta 修饰键时交由全局快捷键处理，不做历史导航
  if (event.key === 'ArrowUp') {
    if (event.ctrlKey || event.altKey || event.metaKey) return
    const textarea = event.target
    if (isCursorAtFirstLine(textarea)) {
      event.preventDefault()
      navigateHistory('up', agentId)
    }
    return
  }

  // 向下箭头：检查是否在最后一行，是才触发历史
  if (event.key === 'ArrowDown') {
    if (event.ctrlKey || event.altKey || event.metaKey) return
    const textarea = event.target
    if (isCursorAtLastLine(textarea)) {
      event.preventDefault()
      navigateHistory('down', agentId)
    }
    return
  }
}

// 处理 Panel 粘贴事件
function handlePanelPaste(panel, event) {
  if (!panel || !panel.agentId) return
  const items = event.clipboardData?.items
  if (!items) return

  for (const item of items) {
    if (item.type.startsWith('image/')) {
      event.preventDefault()
      const file = item.getAsFile()
      if (file) {
        uploadImageToNode(file, panel.agentId)
      }
      break
    }
  }
}

// 从 Panel 清空缓冲
function clearBufferFromPanel(panel) {
  if (!panel || !panel.agentId) return
  const agentId = panel.agentId
  inputBuffers.value.delete(agentId)
  appendOutput({
    output_type: 'system',
    agent_name: 'system',
    text: '🗑 缓冲区已清空',
    lang: 'text',
  }, agentId)
}

// 设置滚动监听，实现滚动到顶部时加载更多历史
// 支持动态切换滚动容器（Panel 创建/切换时调用）
function setupHistoryScrollListener(el) {
  const SCROLL_THRESHOLD = 50 // 滚动到顶部50px以内触发
  const DEBOUNCE_DELAY = 500 // 防抖延迟500ms

  // 移除旧元素上的监听
  if (historyScrollListenerEl && historyScrollHandler) {
    historyScrollListenerEl.removeEventListener('scroll', historyScrollHandler)
  }

  // 清除旧的防抖定时器
  if (historyScrollDebounceTimer) {
    clearTimeout(historyScrollDebounceTimer)
    historyScrollDebounceTimer = null
  }

  if (!el) {
    historyScrollListenerEl = null
    historyScrollHandler = null
    return
  }

  historyScrollListenerEl = el
  historyScrollHandler = () => {
    // 清除之前的定时器
    if (historyScrollDebounceTimer) {
      clearTimeout(historyScrollDebounceTimer)
    }

    // 设置新的定时器
    historyScrollDebounceTimer = setTimeout(() => {
      const scrollTop = el.scrollTop
      if (scrollTop <= SCROLL_THRESHOLD && !isLoadingHistory.value && hasMoreHistory.value) {
        loadHistoryMessages(true) // prepend = true, 插入到开头
      }
    }, DEBOUNCE_DELAY)
  }

  el.addEventListener('scroll', historyScrollHandler)
}

// 设置 Panel 的输出列表引用
function setPanelOutputList(panel, el) {
  if (!panel || !panel.agentId) return
  panelOutputLists.set(panel.id, el)
  if (panel.agentId === currentAgentId.value) {
    outputList.value = el
    // Panel 动态创建后补绑滚动监听，确保滚动到顶部可加载历史
    setupHistoryScrollListener(el)
  }
}

// 设置 Panel 的终端引用
function setPanelTerminalRef(panel, executionId, el, agentId) {
  if (!panel || !panel.agentId) return
  const targetAgentId = agentId || panel.agentId
  if (!executionId) return
  // 委托给 setTerminalRef：统一处理 xterm 的初始化/重建/清理
  setTerminalRef(executionId, el, targetAgentId)
}

// 发送消息到指定 Agent
function sendMessageToAgent(message, agentId = null) {
  const targetAgentId = agentId || currentAgentId.value
  if (!targetAgentId) {
    console.warn('[SEND] No agent ID, cannot send message')
    return
  }

  const ws = sockets.value.get(targetAgentId)
  if (!ws) {
    console.warn(`[SEND] No WebSocket connection for agent ${targetAgentId}`)
    return
  }

  if (ws.readyState !== WebSocket.OPEN) {
    console.warn(`[SEND] WebSocket for agent ${targetAgentId} is not open, state: ${ws.readyState}`)
    return
  }

  ws.send(JSON.stringify(message))
}

// 加载指定 Agent 的历史消息
async function loadHistoryMessages(prepend = false, agentId = null) {
  const targetAgentId = agentId || currentAgentId.value
  // 没有激活的 agent 时，不加载历史记录
  if (!targetAgentId) {
    return
  }

  if (isLoadingHistory.value) {
    return
  }

  if (!hasMoreHistory.value) {
    return
  }

  isLoadingHistory.value = true

  try {
    const historyMessages = historyStorage.loadHistory(historyStorage.MAX_MESSAGES_PER_PAGE, historyOffset.value, targetAgentId)

    if (historyMessages.length === 0) {
      hasMoreHistory.value = false
      isLoadingHistory.value = false
      return
    }

    // 保存当前的滚动位置（用于 prepend 时）
    let scrollPosition = 0
    if (prepend && outputList.value) {
      scrollPosition = outputList.value.scrollHeight - outputList.value.scrollTop
    }

    // stream 消息合并：将 STREAM_START/STREAM_CHUNK/STREAM_END 合并为一条消息
    const streamAccumulator = new Map() // agent_id -> accumulated message
    const mergedHistoryMessages = []
    for (const msg of historyMessages) {
          // 过滤内部控制信号，防止在 UI 中显示
          if (msg.text === '__CTRL_C_PRESSED__') {
            continue;
          }
      const outputType = msg.output_type
      if (outputType === 'STREAM_START') {
        const msgAgentId = msg.agent_id || targetAgentId
        streamAccumulator.set(msgAgentId, {
          ...msg,
          output_type: 'STREAM',
          text: '',
          isStreaming: false,
        })
        continue
      } else if (outputType === 'STREAM_CHUNK') {
        const msgAgentId = msg.agent_id || targetAgentId
        const acc = streamAccumulator.get(msgAgentId)
        if (acc) {
          acc.text += msg.text || ''
          if (typeof msg.seq === 'number') acc.seq = msg.seq
        } else {
          // 孤立的 CHUNK（没有 STREAM_START），保留为独立消息
          mergedHistoryMessages.push(msg)
        }
        continue
      } else if (outputType === 'STREAM_END') {
        const msgAgentId = msg.agent_id || targetAgentId
        const acc = streamAccumulator.get(msgAgentId)
        if (acc) {
          if (typeof msg.seq === 'number') acc.seq = msg.seq
          mergedHistoryMessages.push(acc)
          streamAccumulator.delete(msgAgentId)
        }
        continue
      }
      mergedHistoryMessages.push(msg)
    }

    // 处理未收到 STREAM_END 的残留流式消息（异常情况）
    for (const acc of streamAccumulator.values()) {
      mergedHistoryMessages.push(acc)
    }
    historyMessages.length = 0
    historyMessages.push(...mergedHistoryMessages)

    // 处理每条历史消息
    const executionMessages = historyMessages.filter(msg => msg.output_type === 'execution')
    if (executionMessages.length > 0) {
    }
    // 不再过滤 execution 类型，因为它现在带有 is_finished 标记，可以显示历史内容
    // 修复execution消息的is_finished标记：终端执行是串行的，同一agent同一时间只有一个execution在运行
    // 从后往前扫描：最后一条execution信任历史中的is_finished值；前面所有execution强制is_finished=true
    const executionIndices = []
    historyMessages.forEach((msg, idx) => {
      if (msg.output_type === 'execution') executionIndices.push(idx)
    })
    const processedMessages = historyMessages.map((msg, idx) => {
        if (msg.output_type === 'execution') {
          const isLast = executionIndices.length > 0 && idx === executionIndices[executionIndices.length - 1]
          if (!isLast && !msg.is_finished) {
            // 非最后一条execution：强制标记为已完成
            msg.is_finished = true
            // 如果没有terminal_content，添加占位文本，避免显示空白区域
            if (!msg.terminal_content) {
              msg.terminal_content = '(终端输出未保存或执行被中断)'
            }
          }
          // 对于最后一条execution：不强制标记为已完成，保留原始状态
          // 只有在收到后端的tool_stream_end事件时才会标记为已完成
          // 这样切换回Agent时，如果执行还在进行中，xterm可以正常渲染
          if (isLast && !msg.is_finished) {
          }
        }
        const html = renderMessageHtml(msg)
        // 生成稳定ID，避免v-for使用index作为key导致DOM重建
        const stableId = msg.execution_id
          ? `exec_${msg.execution_id}`
          : msg._stableId || `msg_${msg.timestamp || Date.now()}_${Math.random().toString(36).slice(2, 8)}`
        return {
          ...msg,
          html,
          timestamp: msg.timestamp || '',
          agent_name: msg.agent_name || '',
          non_interactive: msg.non_interactive !== undefined ? msg.non_interactive : false,
          agent_list: msg.agent_list || msg.context?.agent_list || '',
          _stableId: stableId,
        }
      })

    // 获取目标 Agent 的消息列表
    const currentOutputs = allOutputs.value.get(targetAgentId) || []
    if (prepend) {
      // 插入到消息列表开头
      allOutputs.value.set(targetAgentId, [...processedMessages, ...currentOutputs])
    } else {
      // 合并历史消息与现有消息，去重（避免重复）
      // 现有消息（可能来自 WebSocket 推送）优先级更高，历史消息补充缺失的
      const merged = [...currentOutputs]
      const existingIds = new Set()
      for (const msg of currentOutputs) {
        if (msg.execution_id) existingIds.add('exec_' + msg.execution_id)
        if (typeof msg.seq === 'number') existingIds.add('seq_' + msg.seq)
      }
      for (const msg of processedMessages) {
        const execKey = msg.execution_id ? 'exec_' + msg.execution_id : null
        const seqKey = typeof msg.seq === 'number' ? 'seq_' + msg.seq : null
        if ((execKey && existingIds.has(execKey)) || (seqKey && existingIds.has(seqKey))) continue
        merged.push(msg)
        if (execKey) existingIds.add(execKey)
        if (seqKey) existingIds.add(seqKey)
      }
      allOutputs.value.set(targetAgentId, merged)
    }

    // 更新偏移量
    historyOffset.value += historyMessages.length

    // 检查是否还有更多历史
    const totalCount = historyStorage.getTotalCount(targetAgentId)
    hasMoreHistory.value = historyOffset.value < totalCount


    // 恢复滚动位置
    if (prepend && outputList.value) {
      nextTick(() => {
        requestAnimationFrame(() => {
          const newScrollHeight = outputList.value.scrollHeight
          outputList.value.scrollTop = newScrollHeight - scrollPosition
        })
      })
    } else {
      // 首次加载历史，滚动到底部（仅当自动滚动开启时）
      nextTick(() => {
        if (outputList.value && isAutoScrollEnabled(targetAgentId)) {
          outputList.value.scrollTop = outputList.value.scrollHeight
        }
      })
    }
  } catch (error) {
    console.error('[HISTORY] Failed to load history:', error)
  } finally {
    isLoadingHistory.value = false
  }
}

// Agent 管理
const agentList = ref([])        // Agent 列表
const currentAgentId = ref(null) // 当前连接的 Agent ID
const agentStatuses = ref(new Map()) // Agent 状态映射 (agent_id -> {execution_status, agent_status})
function isStoppedAgent(agent) {
  if (!agent) return false
  return getStatusClass(agent) === 'stopped'
}

const activeAgents = computed(() => {
  return agentList.value.filter(agent => !isStoppedAgent(agent))
})
const stoppedAgents = computed(() => {
  return agentList.value.filter(agent => isStoppedAgent(agent))
})
// 排序后的 Agent 列表（活跃的在前，停止的在后）
const sortedAgentList = computed(() => {
  return [...activeAgents.value, ...stoppedAgents.value]
})
// 按节点分组的已停止 Agent（保留用于其他可能的引用）
const stoppedAgentsByNode = computed(() => {
  const grouped = {}
  stoppedAgents.value.forEach(agent => {
    const nodeId = getAgentNodeLabel(agent)
    if (!grouped[nodeId]) {
      grouped[nodeId] = []
    }
    grouped[nodeId].push(agent)
  })
  return grouped
})
// 按节点分组所有 Agent，每个节点组内非停止 Agent 置顶
const agentsByNode = computed(() => {
  const grouped = {}
  // 创建 agent_id 到索引的映射，用于保持时间倒序
  const agentIndexMap = new Map()
  agentList.value.forEach((agent, index) => {
    agentIndexMap.set(agent.agent_id, index)
  })
  
  agentList.value.forEach(agent => {
    const nodeId = getAgentNodeLabel(agent)
    if (!grouped[nodeId]) {
      grouped[nodeId] = { active: [], stopped: [] }
    }
    if (isStoppedAgent(agent)) {
      grouped[nodeId].stopped.push(agent)
    } else {
      grouped[nodeId].active.push(agent)
    }
  })
  
  // 对每个分组的 agent 按照在 agentList 中的索引排序（保持时间倒序，最新的在顶部）
  Object.keys(grouped).forEach(nodeId => {
    grouped[nodeId].active.sort((a, b) => agentIndexMap.get(a.agent_id) - agentIndexMap.get(b.agent_id))
    grouped[nodeId].stopped.sort((a, b) => agentIndexMap.get(a.agent_id) - agentIndexMap.get(b.agent_id))
  })
  
  return grouped
})
const agentDisplayGroups = computed(() => {
  const groups = []

  // 已分组的 agent_id 集合（去重，保持定义顺序）
  const groupedAgentIds = new Set()

  // 先收集自定义分组中的 agent_id，用于排除
  agentGroups.value.forEach(group => {
    if (!group.agentIds) group.agentIds = []
    group.agentIds.forEach(id => groupedAgentIds.add(id))
  })

  const sortedNodeIds = Object.keys(agentsByNode.value).sort()

  // 第一轮：所有节点的活跃 Agent（排除已分组的）
  sortedNodeIds.forEach(nodeId => {
    const nodeAgents = agentsByNode.value[nodeId]
    const active = nodeAgents.active.filter(agent => !groupedAgentIds.has(agent.agent_id))
    if (active.length > 0) {
      groups.push({
        key: `node-${nodeId}`,
        title: nodeId,
        agents: active,
        isCollapsible: false,
      })
    }
  })

  // 第二轮：自定义分组（可折叠）
  agentGroups.value.forEach(group => {
    if (!group.agentIds) group.agentIds = []
    const agents = agentList.value.filter(agent =>
      group.agentIds.includes(agent.agent_id) && !isStoppedAgent(agent)
    )
    if (agents.length > 0) {
      agents.forEach(agent => groupedAgentIds.add(agent.agent_id))
      groups.push({
        key: `group-${group.id}`,
        title: group.name,
        agents,
        isCollapsible: true,
      })
    }
  })

  // 第三轮：所有节点的已停止 Agent（排除已分组的）
  sortedNodeIds.forEach(nodeId => {
    const nodeAgents = agentsByNode.value[nodeId]
    const stopped = nodeAgents.stopped.filter(agent => !groupedAgentIds.has(agent.agent_id))
    if (stopped.length > 0) {
      groups.push({
        key: `stopped-${nodeId}`,
        title: `${nodeId}已停止的 Agent`,
        agents: stopped,
        isCollapsible: true,
      })
    }
  })

  return groups
})
const currentAgent = computed(() => {
  return agentList.value.find(agent => agent.agent_id === currentAgentId.value) || null
})

// 注意：已停止Agent的折叠状态现在由AgentSidebar组件内部管理

watch([showEditorPanel, currentAgentId, editorSidebarView], ([isEditorPanelVisible, agentId, sidebarView]) => {
  if (!isEditorPanelVisible || !agentId || sidebarView !== 'files') {
    return
  }

  nextTick(() => {
    ensureEditorSidebarFileTree()
  })
})

// Agent 分组管理
const AGENT_GROUPS_STORAGE_KEY = 'jarvis_agent_groups'
const agentGroups = ref([]) // 自定义分组 [{ id, name, agentIds: [] }]

function loadAgentGroups() {
  try {
    const saved = localStorage.getItem(AGENT_GROUPS_STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed)) {
        agentGroups.value = parsed
        return
      }
    }
  } catch (e) {
    console.warn('[AGENT_GROUPS] Failed to load groups:', e)
  }
  agentGroups.value = []
}

function saveAgentGroups() {
  try {
    localStorage.setItem(AGENT_GROUPS_STORAGE_KEY, JSON.stringify(agentGroups.value))
  } catch (e) {
    console.warn('[AGENT_GROUPS] Failed to save groups:', e)
  }
}

function removeStoppedAgentsFromGroups() {
  let changed = false
  agentGroups.value.forEach(group => {
    if (!group.agentIds) group.agentIds = []
    const before = group.agentIds.length
    group.agentIds = group.agentIds.filter(agentId => {
      const agent = agentList.value.find(a => a.agent_id === agentId)
      return !agent || !isStoppedAgent(agent)
    })
    if (group.agentIds.length !== before) changed = true
  })
  if (changed) saveAgentGroups()
}

// 监听 agent 状态/列表变化，自动移除已停止或已删除的 agent
watch(
  [agentStatuses, agentList],
  () => {
    removeStoppedAgentsFromGroups()
  },
  { deep: true }
)

// 初始化加载
loadAgentGroups()

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
    // 正常模式下，在 Panel 中打开 agent
    openAgentInPanel(agent)
  }
}

// ========== 宠物网关操作 ==========
// 同步所有已连接 Agent 的状态
function petSyncAllStatus() {
  let count = 0
  sockets.value.forEach((ws) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'get_status', payload: {} }))
      count++
    }
  })
  if (count > 0) {
    showToast(`已同步 ${count} 个 Agent 的状态`, 'success')
  } else {
    showToast('没有已连接的 Agent', 'error')
  }
}

// 中断当前 Agent（人工介入）
function petInterruptCurrent() {
  const agentId = currentAgentId.value
  if (!agentId) {
    showToast('没有选中的 Agent', 'error')
    return
  }
  sendMessageToAgent({ type: 'manual_interrupt', payload: {} }, agentId)
  showToast('已发送中断信号', 'success')
}

// 奔赴等待输入的 Agent
function petGotoWaitingAgent() {
  const list = agentList.value || []
  const waiting = list.filter(a => isWaitingInput(a))
  if (waiting.length === 0) {
    showToast('没有等待输入的 Agent', 'info')
    return
  }
  // 循环切换：从当前 Agent 之后找下一个等待的，找不到则回到第一个
  const currentIdx = waiting.findIndex(a => a.agent_id === currentAgentId.value)
  const target = currentIdx >= 0 ? waiting[(currentIdx + 1) % waiting.length] : waiting[0]
  openAgentInPanel(target)
  showToast(`已切换到等待输入的 Agent：${target.name || target.agent_id}`, 'success')
}

// 打开网络拓扑大图（点击宠物旁迷你图或右键菜单触发）
function openTopologyOverlay() {
  showTopologyOverlay.value = true
}

// 打开命令面板时，记录"打开前"焦点所在的面板区域
// （命令面板会抢走焦点，导致执行关闭/分离时无法从活动元素推断目标）
let commandPaletteFocusKey = null
// 打开命令面板（双击宠物触发）；可传入预输入内容（如 'a>' 直接进入 Agent 列表）
function openCommandPalette(initialQuery = '') {
  if (showConnectModal.value) return
  commandPaletteFocusKey = getFocusedZoneKey()
  commandPaletteInitialQuery.value = initialQuery
  showCommandPalette.value = true
}

// 打开命令面板并预输入 a>，直接展示 Agent 列表
function openAgentListPalette() {
  openCommandPalette('a>')
}

// 切换宠物显示/隐藏（命令面板触发，代理到 AgentSidebar 内部逻辑）
function togglePetVisibility() {
  agentSidebarRef.value?.togglePet?.()
}

// ===== 当前 Agent 菜单动作（命令面板「当前 Agent」组）=====
// 取当前激活 Panel，回退到承载当前 Agent 的 Panel
function getCurrentPanel() {
  const activePanel = panels.value.find(p => p.id === activePanelId.value)
  if (activePanel && activePanel.agentId) return activePanel
  return panels.value.find(p => p.agentId === currentAgentId.value)
    || panels.value.find(p => p.agentId)
    || activePanel
    || null
}
// 命令面板「当前 Agent」组使用的 Agent ID：
// 优先当前激活 Panel 内的 Agent；其次宠物大厅中选中的宠物对应的 Agent；最后回退到 currentAgentId
const commandPaletteCurrentAgentId = computed(() => {
  const panel = getCurrentPanel()
  if (panel && panel.agentId) return panel.agentId
  if (lobbyActiveAgentId.value) return lobbyActiveAgentId.value
  return currentAgentId.value || null
})
// 当前 Agent 对象（无选中时为 null）
function getCurrentAgentOrNull() {
  const agentId = commandPaletteCurrentAgentId.value
  if (agentId) {
    const agent = agentList.value.find(a => a.agent_id === agentId)
    if (agent) return agent
  }
  return currentAgent.value || null
}
// 切换当前 Agent 面板的自动滚动
function toggleCurrentAutoScroll() {
  const panel = getCurrentPanel()
  if (!panel || !panel.agentId) return
  togglePanelAutoScroll(panel, !getPanelAutoScroll(panel))
}
// 切换当前 Agent 面板的自动朗读
function toggleCurrentAutoRead() {
  const panel = getCurrentPanel()
  if (!panel || !panel.agentId) return
  togglePanelAutoRead(panel, !getPanelAutoRead(panel))
}
// 退出当前 Agent 的非交互模式
function exitCurrentNonInteractive() {
  const agent = getCurrentAgentOrNull()
  if (agent) exitNonInteractiveMode(agent)
}
// 对当前 Agent 发送人工介入信号
function interruptCurrentAgent() {
  const panel = getCurrentPanel()
  if (panel && panel.agentId) {
    sendManualInterruptToPanel(panel)
  } else {
    petInterruptCurrent()
  }
}

// 判断某个焦点区域 key 当前是否有效（面板仍存在/可见）
function isFocusKeyAvailable(key) {
  if (!key) return false
  if (key === 'terminal') return !!(showTerminalPanel.value && !terminalDetached.value && document.querySelector('.terminal-panel'))
  if (key === 'editor') return !!(showEditorPanel.value && !editorDetached.value && document.querySelector('.editor-panel'))
  if (key === 'chat') return !!(showChatPanel.value && !chatDetached.value && document.querySelector('.chat-panel'))
  if (key.startsWith('session:')) {
    const panelId = key.slice('session:'.length)
    return panels.value.some(p => p.id === panelId && p.agentId)
  }
  return false
}

// 当前焦点所处面板的 key（session:<id> / terminal / editor / chat）
// 命令面板打开时会抢走焦点，此时优先用"打开前"记录的快照（且该面板须仍有效）；
// 否则依据真实 DOM 焦点，最后回退到当前激活 Panel
function getFocusedPanelKey() {
  if (showCommandPalette.value && isFocusKeyAvailable(commandPaletteFocusKey)) {
    return commandPaletteFocusKey
  }
  const focusedKey = getFocusedZoneKey()
  if (focusedKey) return focusedKey
  if (isFocusKeyAvailable(commandPaletteFocusKey)) return commandPaletteFocusKey
  const panel = getCurrentPanel()
  if (panel && panel.agentId) return `session:${panel.id}`
  return null
}
// 关闭当前焦点所在的面板（会话/终端/编辑器/聊天）
function closeFocusedPanel() {
  const key = getFocusedPanelKey()
  if (!key) return
  if (key === 'terminal') {
    showTerminalPanel.value = false
  } else if (key === 'editor') {
    showEditorPanel.value = false
  } else if (key === 'chat') {
    showChatPanel.value = false
  } else if (key.startsWith('session:')) {
    closePanel(key.slice('session:'.length))
  }
}
// 分离/停靠当前焦点所在的面板
function detachFocusedPanel() {
  const key = getFocusedPanelKey()
  if (!key) return
  if (key === 'terminal') {
    detachPanel('terminal')
  } else if (key === 'editor') {
    detachPanel('editor')
  } else if (key === 'chat') {
    detachPanel('chat')
  } else if (key.startsWith('session:')) {
    detachPanel('session', key.slice('session:'.length))
  }
}
// 命令面板上下文：统一暴露宠物菜单与命令面板共用的动作回调
const commandPaletteCtx = computed(() => ({
  currentAgentId: commandPaletteCurrentAgentId.value,
  agentList: agentList.value,
  waitingAgents: (agentList.value || []).filter(a => isWaitingInput(a)),
  currentAgent: getCurrentAgentOrNull(),
  petInterruptCurrent,
  petGotoWaitingAgent,
  syncAllStatus: petSyncAllStatus,
  openCreateAgentModal,
  refreshAgentList: fetchAgentList,
  restartGateway,
  restartAllNodes,
  toggleAgentSidebar,
  toggleTerminalPanel,
  toggleChatPanel,
  openTopology: openTopologyOverlay,
  openSettings: () => { showSettingsModal.value = true },
  togglePetVisibility,
  toggleHeader,
  openAgentList: openAgentListPalette,
  // 当前 Agent 组
  viewCurrentDiff: () => { const a = getCurrentAgentOrNull(); if (a) viewDiff(a) },
  viewCurrentRules: () => { const a = getCurrentAgentOrNull(); if (a) viewRules(a) },
  viewCurrentTools: () => { const a = getCurrentAgentOrNull(); if (a) viewTools(a) },
  createTerminalForCurrent: () => { const a = getCurrentAgentOrNull(); if (a) createTerminalForAgent(a) },
  openEditorForCurrent: () => { const a = getCurrentAgentOrNull(); if (a) createEditorForAgent(a) },
  toggleCurrentAutoScroll,
  toggleCurrentAutoRead,
  exitCurrentNonInteractive,
  interruptCurrentAgent,
  // 当前 Agent 侧边栏操作（重命名/复制/权限管理/无损重生/删除）
  renameCurrentAgent: () => { const a = getCurrentAgentOrNull(); if (a) renameAgent(a) },
  copyCurrentAgent: () => { const a = getCurrentAgentOrNull(); if (a) copyAgent(a) },
  editCurrentAgentAccess: () => { const a = getCurrentAgentOrNull(); if (a) editAgentAccess(a) },
  regenerateCurrentAgent: () => { const a = getCurrentAgentOrNull(); if (a) regenerateAgent(a) },
  deleteCurrentAgent: () => { const a = getCurrentAgentOrNull(); if (a) deleteAgent(a.agent_id) },
  // 当前焦点面板：分离 / 关闭（面板头部图标保留不变）
  detachFocusedPanel,
  closeFocusedPanel,
  // 侧边栏中「权限管理」「无损重生」仅对 Agent 属主可见，这里保持一致
  isCurrentAgentOwner: (() => {
    const a = getCurrentAgentOrNull()
    return !!a && a.owner_id === (auth.value.userInfo?.user_id || '')
  })(),
  // 命令面板「切换 Agent」（a> / A> 前缀）所需
  // Enter（不带 openMode / 'current'）：在当前 Panel 中打开；Tab（'new'）：在新的 Panel 中打开
  switchToAgent: (agent, openMode) => {
    if (!agent) return
    if (openMode === 'new') {
      openAgentInNewPanel(agent)
    } else {
      openAgentInCurrentPanel(agent)
    }
  },
  getAgentNodeLabel,
  getStatusClass,
  isWaitingInput,
  // 已在某个 Panel 中打开的 Agent（用于把“激活”的 Agent 排在列表上方）
  openedAgentIds: new Set(panels.value.filter(p => p.agentId).map(p => p.agentId)),
}))

// 命令面板动作清单（来自统一注册表）
const appActions = computed(() => actionDefs)

// 宠物环形菜单动作：取命令面板「当前 Agent」组的命令，内圈放常用项
const PET_RADIAL_INNER_IDS = [
  'current-view-diff',
  'current-create-terminal',
  'current-open-editor',
  'current-manual-interrupt',
  'current-rename',
  'current-delete',
]
// 宠物菜单额外纳入的界面项（不属于「当前 Agent」组，但移动端也需要）
const PET_RADIAL_EXTRA_IDS = [
  'toggle-header',
  'open-agent-list',
]
const petRadialActions = computed(() => {
  const ctx = commandPaletteCtx.value
  return actionDefs
    .filter(a => a.group === '当前 Agent' || PET_RADIAL_EXTRA_IDS.includes(a.id))
    .map(a => ({
      id: a.id,
      label: a.label,
      icon: a.icon,
      inner: PET_RADIAL_INNER_IDS.includes(a.id),
      enabled: typeof a.enabled === 'function' ? a.enabled(ctx) : true,
    }))
})

// 宠物环形菜单点击：关闭菜单后按命令面板同款逻辑执行
function onPetRadialRun(action) {
  if (!action) return
  const def = actionDefs.find(a => a.id === action.id)
  if (def) onCommandRun(def)
}

// 执行命令面板中的动作
function onCommandRun(action, openMode) {
  showCommandPalette.value = false
  if (!action || typeof action.run !== 'function') return
  try {
    action.run(commandPaletteCtx.value, openMode)
  } catch (err) {
    console.error('命令执行失败', err)
    showToast('命令执行失败', 'error')
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

// 弹窗刚关闭后的静默窗口：这段时间内抑制自动聚焦。
// 弹窗关闭后，此前挂起的异步状态同步（如 fetchAgentStatus）可能才 resolve，
// 若此时直接聚焦输入框，会把焦点从用户刚操作完的位置抢走。
let modalAutoFocusSuppressUntil = 0
const MODAL_AUTOFOCUS_SUPPRESS_MS = 600

// 是否有任何模态弹窗/浮层处于打开状态。
// 用于阻止 Agent 推送的 input_request/confirm/ready 抢占用户焦点：
// 用户正在弹窗中操作（如创建 Agent）时，焦点不应被自动聚焦逻辑夺走。
function isAutoFocusSuppressed() {
  return isAnyModalOpen() || Date.now() < modalAutoFocusSuppressUntil
}

function isAnyModalOpen() {
  return Boolean(
    showConnectModal.value ||
    showSettingsModal.value ||
    showDiffModal.value ||
    showRulesModal.value ||
    showCreateAgentModal.value ||
    showRenameAgentModal.value ||
    showSessionDialog.value ||
    showDirDialog.value ||
    showCommandPalette.value ||
    showToolsModal.value ||
    showEditAccessModal.value ||
    showTopologyOverlay.value ||
    confirmDialog.value
  )
}

// 宠物环形菜单是否展开（展开时不应自动抢占输入框焦点，避免移动端软键盘顶走页面）
function isPetMenuOpen() {
  return Boolean(agentSidebarRef.value?.isPetMenuOpen?.())
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
  // @ 按钮永远启用，不再根据输入模式禁用
  if (!currentAgentId.value) {
    return true // 没有激活的 agent
  }
  return false // 永远启用
})
const newAgentType = ref('code_agent') // 新 Agent 类型
const newAgentDir = ref('~')       // 新 Agent 工作目录（默认用户目录）
const newAgentName = ref('通用Agent') // 新 Agent 名称（可选，默认为'通用Agent'）
const modelGroups = ref([])        // 模型组列表
const newAgentModelGroup = ref('default') // 新 Agent 模型组（默认为 default）
const newCodeAgentWorktree = ref(false) // 新代码 Agent 是否启用 worktree
const newAgentQuickMode = ref(false) // 新 Agent 是否启用极速模式
const newAgentRestoreSession = ref(false) // 新 Agent 是否启用恢复会话
const newAgentNoInteractionMode = ref(false) // 新 Agent 是否启用无交互模式
const newAgentTaskDescription = ref('') // 新 Agent 任务描述
const newAgentCreateError = ref('') // 创建 Agent 时的错误信息
const newAgentProxyNode = ref('') // 新 Agent 代理节点
const newAgentAccessAclRead = ref([]) // 新 Agent ACL read用户ID数组
const newAgentAccessAclInteract = ref([]) // 新 Agent ACL interact用户ID数组
const availableUserOptions = ref([]) // 用户列表（用于ACL选择）
// ACL用户列表：排除owner和admin用户（他们有完全控制权限，无需ACL授权）
const filteredUserOptionsForAcl = computed(() => {
  const agent = editingAccessAgent.value
  const ownerId = agent?.owner_id || ''
  // 从用户列表中过滤掉owner和所有管理员（管理员有完全控制权限，无需ACL授权）
  return availableUserOptions.value.filter(user => {
    if (user.user_id === ownerId) return false
    if (user.is_admin) return false
    return true
  })
})
const availableNodeOptions = ref([])
const userAccessibleNodes = ref(null) // null=未加载, []=无权限, ["*"]=所有, ["id1","id2"]=限定节点

// 节点显示名映射（仅前端本地）：nodeId -> 自定义显示名，未设置时回退到原始 nodeId
const NODE_DISPLAY_NAMES_STORAGE_KEY = 'jarvis_node_display_names'
function loadNodeDisplayNames() {
  try {
    const savedValue = localStorage.getItem(NODE_DISPLAY_NAMES_STORAGE_KEY)
    if (!savedValue) return {}
    const parsedValue = JSON.parse(savedValue)
    if (!parsedValue || typeof parsedValue !== 'object' || Array.isArray(parsedValue)) return {}
    return Object.fromEntries(
      Object.entries(parsedValue).filter(([, name]) => typeof name === 'string' && name.trim())
    )
  } catch (error) {
    console.warn('[NODE] Failed to load node display names:', error)
    return {}
  }
}
const nodeDisplayNames = ref(loadNodeDisplayNames())
function saveNodeDisplayNames(nextNames = nodeDisplayNames.value) {
  nodeDisplayNames.value = nextNames
  localStorage.setItem(NODE_DISPLAY_NAMES_STORAGE_KEY, JSON.stringify(nextNames))
}
// 获取节点的展示名：优先自定义名，否则回退原始 nodeId
function getNodeDisplayName(nodeId) {
  const normalizedNodeId = String(nodeId || '').trim() || 'master'
  const customName = nodeDisplayNames.value[normalizedNodeId]
  return typeof customName === 'string' && customName.trim() ? customName.trim() : normalizedNodeId
}
// 隐藏工作目录（录屏/截图时避免暴露目录）
const HIDE_WORKING_DIR_STORAGE_KEY = 'jarvis_hide_working_dir'
function loadHideWorkingDir() {
  try {
    return localStorage.getItem(HIDE_WORKING_DIR_STORAGE_KEY) === '1'
  } catch (error) {
    console.warn('[WORKDIR] Failed to load hide working dir setting:', error)
    return false
  }
}
const hideWorkingDir = ref(loadHideWorkingDir())
function saveHideWorkingDirSetting(nextValue = hideWorkingDir.value) {
  hideWorkingDir.value = !!nextValue
  try {
    localStorage.setItem(HIDE_WORKING_DIR_STORAGE_KEY, hideWorkingDir.value ? '1' : '0')
  } catch (error) {
    console.warn('[WORKDIR] Failed to save hide working dir setting:', error)
  }
}
// 工作目录展示：开启隐藏时返回占位符，否则返回原始目录
const WORKING_DIR_HIDDEN_PLACEHOLDER = '••••••'
function getWorkingDirDisplay(workingDir) {
  if (hideWorkingDir.value) return WORKING_DIR_HIDDEN_PLACEHOLDER
  return workingDir || ''
}
const newAgentNodeId = ref('')
const selectedTerminalNodeId = ref('master')

// 创建Agent弹窗：按用户可访问节点过滤节点选项
const filteredNodeOptionsForCreateAgent = computed(() => {
  const accessible = userAccessibleNodes.value
  // null=未加载（权限系统未启用或未获取），显示全部节点
  if (accessible === null) return availableNodeOptions.value
  // ["*"]=所有节点权限
  if (accessible.includes('*')) return availableNodeOptions.value
  // 限定节点列表：只显示有权限的节点
  return availableNodeOptions.value.filter(node => accessible.includes(node.node_id))
})

// 生成 Agent 名称：Agent类型-创建时间（如：代码Agent-20261213-140013）
function generateAgentName(agentType) {
  const typeName = agentType === 'agent' ? '通用Agent' : '代码Agent'
  const now = new Date()
  const date = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
  const time = `${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`
  return `${username.value}-${typeName}-${date}-${time}`
}

// 复制 Agent 时跳过 watch 中的名称设置
let skipNameWatch = false

// 监听 Agent 类型变化，自动填充默认名称
watch(newAgentType, (newType) => {
  if (skipNameWatch) return
  if (newType === 'agent') {
    newAgentName.value = generateAgentName('agent')
    newCodeAgentWorktree.value = false
  } else if (newType === 'code_agent') {
    newAgentName.value = generateAgentName('code_agent')
  }
}, { immediate: true, flush: 'sync' })

// 确认对话框
const confirmDialog = ref(null) // { message, confirmCallback, cancelCallback, defaultConfirm }


// 显示确认对话框（自动滚动到底部）
function showConfirm(message, confirmCallback, cancelCallback, defaultConfirm = true) {
  confirmDialog.value = {
    message,
    defaultConfirm,
    confirmCallback,
    cancelCallback
  }

  // 等待 DOM 更新后滚动到底部，确保用户能看到确认对话框
  nextTick(() => {
    if (outputList.value) {
      outputList.value.scrollTop = outputList.value.scrollHeight
    }
  })
}

// 处理确认对话框确认事件
function handleConfirmDialogConfirm() {
  if (confirmDialog.value?.confirmCallback) {
    confirmDialog.value.confirmCallback()
  }
  confirmDialog.value = null
}

// 处理确认对话框取消事件
function handleConfirmDialogCancel() {
  if (confirmDialog.value?.cancelCallback) {
    confirmDialog.value.cancelCallback()
  }
  confirmDialog.value = null
}

// 补全列表
const showCompletions = ref(false) // 是否显示补全列表
const completionCursorPos = ref(-1) // 记录打开补全列表时的光标位置
const completionHasAtSymbol = ref(false) // 打开补全时输入框中是否已存在待替换的 @ 符号
const completionAgentId = ref(null) // 记录打开补全列表时的 Panel agentId
const completionSource = ref('panel') // 补全来源：'panel' 或 'lobby'（宠物大厅）
const petLobbyRef = ref(null) // 宠物大厅组件引用（用于写回大厅输入框补全文本）
const lobbyActiveAgentId = ref(null) // 宠物大厅中当前选中的宠物对应的 agentId
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
      // 优先使用打开补全时记录的 agent（可能是宠物大厅中的 agent），否则回退到当前 agent
      const searchAgentId = completionAgentId.value || currentAgent.value?.agent_id
      if (!searchAgentId) {
        fileCompletions.value = []
        return
      }
      const searchAgent = agentList.value.find(a => a.agent_id === searchAgentId)
      const targetNodeId = String(searchAgent?.node_id || getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(
        buildNodeHttpUrl(host, port, targetNodeId, `completions/${searchAgentId}/search?query=${encodeURIComponent(newSearch)}`)
      )
      
      const result = await response.json()
      
      if (response.ok && result.success && result.data) {
        fileCompletions.value = sortCompletionItems(result.data)
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
const completionsModalRef = ref(null) // CompletionsModal组件引用
const dirDialogRef = ref(null) // DirectoryDialog组件引用
const selectedIndex = ref(-1) // 当前选中的补全条目索引，-1 表示未选中

// 流式消息跟踪
const streamingMessages = ref(new Map()) // 按 agent_id 跟踪当前流式消息

// 命令面板（Ctrl+P）
const showCommandPalette = ref(false)
// 命令面板打开时的预输入内容（如 'a>' 直接展示 Agent 列表）
const commandPaletteInitialQuery = ref('')
const showTopologyOverlay = ref(false) // 网络拓扑大图浮层

// 命令面板关闭后，若没有其它弹窗接管焦点，则把焦点交还给当前 Agent 的输入框
function focusCurrentPanelInput(force = false) {
  const panel = getCurrentPanel()
  if (!panel || !panel.agentId) return
  const sessionPanel = sessionPanelRefs.get(panel.id)
  if (sessionPanel?.focusInput) {
    sessionPanel.focusInput(force)
  }
}

watch(showCommandPalette, (visible, wasVisible) => {
  if (visible || !wasVisible) return
  // 面板关闭动作可能同时打开了其它弹窗（如命令执行打开设置/拓扑），此时不抢焦点
  if (isAnyModalOpen()) return
  nextTick(() => {
    if (isAnyModalOpen()) return
    focusCurrentPanelInput()
  })
})

// 执行状态
const isExecuting = ref(false)

const connectionStatus = computed(() => {
  if (connecting.value) return 'connecting'
  if (reconnecting.value) return 'reconnecting'
  return socket.value ? 'online' : 'offline'
})

const connectionLabel = computed(() => {
  if (connecting.value) return '连接中'
  if (reconnecting.value) return '重连中'
  return socket.value ? '已连接' : '未连接'
})

const inputModeLabel = computed(() => (inputMode.value === 'multi' ? '多行' : '单行'))

// 历史消息加载状态
const isLoadingHistory = ref(false)
const historyOffset = ref(0)
const hasMoreHistory = ref(true)

// 保存免登录设置
function saveAutoLoginSetting() {
  localStorage.setItem('jarvis_auto_login', autoLoginEnabled.value)
  // 如果关闭免登录，清除已保存的 token
  if (!autoLoginEnabled.value) {
    localStorage.removeItem('jarvis_auth_token')
  }
}

// 保存通知开关设置（仅控制弹窗，不影响提示音）
function saveNotifySettings() {
  localStorage.setItem('jarvis_notify_on_exit', notifyOnExit.value)
  localStorage.setItem('jarvis_notify_on_input', notifyOnInput.value)
}

// 连接到 Gateway
async function connect() {
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

  // 如果已有 token（从 localStorage 加载的），跳过密码登录
  if (!hasAuthToken()) {
    try {
      await loginWithPassword(password)
    } catch (error) {
      connectErrorMessage.value = error.message || '登录失败'
      return
    }
  } else {
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
  ws.onopen = () => {
    connecting.value = false
    socket.value = ws
    showConnectModal.value = false
    
    // 重置重连状态
    reconnecting.value = false
    reconnectAttempts.value = 0
    userDisconnected.value = false
    isAutoConnecting.value = false  // 连接成功，自动连接阶段结束
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value)
      reconnectTimer.value = null
    }

    // 保存连接信息到 localStorage
    localStorage.setItem('jarvis_gateway_url', gatewayUrl.value)
    startAgentListRefresh()
    // 刷新用户信息（确保display_name等字段最新）
    refreshUserInfo()
    // 登录成功后自动连接所有在线的 agent
    autoConnectToOnlineAgents()
    // 获取模型组列表
    fetchModelGroups()
    fetchNodeStatus()
    fetchUserAccessibleNodes()
    // 自动注册聊天室（避免丢消息，不依赖用户手动打开聊天面板）
    if (!myClientId.value) {
      myClientId.value = getOrCreateClientId()
    }
    sendChatMessageToServer('chat_register', { client_id: myClientId.value, name: username.value })
    const currentOutputs = allOutputs.value.get(currentAgentId.value) || []
    if (currentOutputs.length === 0) {
      loadHistoryMessages(false)
    } else {
    }
    // 心跳机制已移除
  }
  ws.onmessage = (event) => {
    // 忽略非当前连接的消息（重连时旧连接可能仍收到消息）
    if (socket.value !== ws) {
      return
    }
    let message = null
    try {
      message = JSON.parse(event.data)
    } catch (error) {
      console.warn('[ws] message parse failed', event.data)
      return
    }

    // pong 消息处理已移除

    handleMessage(message)
  }
  ws.onclose = (event) => {
    socket.value = null
    connecting.value = false
    // 连接断开，销毁所有独立终端
    const allTerminalIds = terminalSessions.value.map(t => t.terminal_id)
    allTerminalIds.forEach(terminalId => closeTerminal(terminalId))
    
    // 判断是否需要自动重连（token存在时才重连）
    const shouldReconnect = !userDisconnected.value && !isAutoConnecting.value && hasAuthToken()

    if (shouldReconnect) {
      // 启动自动重连（固定间隔，无上限）
      reconnecting.value = true
      reconnectAttempts.value++


      // 设置重连定时器（固定5秒间隔）
      reconnectTimer.value = setTimeout(() => {
        connect()
      }, reconnectInterval)
    } else {
      // 不需要重连
      reconnecting.value = false

      if (isAutoConnecting.value) {
        // 自动连接阶段失败，显示登录弹窗
        isAutoConnecting.value = false
        showConnectModal.value = true
        // 清除失效的 token
        localStorage.removeItem('jarvis_auth_token')
        auth.value.token = ''
        connectErrorMessage.value = '自动登录失败，请重新登录'
      } else if (userDisconnected.value) {
        // 用户主动断开，不重连
        userDisconnected.value = false // 重置标志
      }
    }
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
  // 设置用户主动断开标志，防止自动重连
  userDisconnected.value = true
  
  // 清理重连定时器
  if (reconnectTimer.value) {
    clearTimeout(reconnectTimer.value)
    reconnectTimer.value = null
  }
  reconnecting.value = false
  reconnectAttempts.value = 0
  
  if (socket.value) {
    socket.value.close()
  }
}

// 处理 SettingsModal 组件的重启事件
function handleRestartGateway({ nodeId, restartFrontend }) {
  restartNodeId.value = nodeId || ''
  restartFrontendService.value = restartFrontend || false
  confirmRestartGateway()
}

// 处理 SettingsModal 组件的同步配置事件
function handleSyncConfig({ sourceNodeId }) {
  syncConfigSourceNode.value = sourceNodeId || ''
  
  // 显示确认框
  showConfirm(
    '确定要同步配置到其他节点吗？此操作将覆盖目标节点的配置。',
    () => {
      syncConfig()
    },
    () => {},
    false
  )
}

// 处理 SettingsModal 组件的更新代码事件
function handleUpdateCodeToMain() {
  updateCodeToMain()
}

// 确认更新代码到 main 分支
function confirmUpdateCodeToMain() {
  showConfirm(
    '确定要更新所有节点的代码到 main 分支吗？\n\n此操作将：\n1. 切换所有节点到 main 分支\n2. 拉取最新代码\n3. 可能需要重启服务',
    () => {
      updateCodeToMain()
    },
    () => {},
    false
  )
}

function confirmRestartGateway() {
  if (isRestartingGateway.value) {
    return
  }

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

// 确认重启所有节点（依次重启子节点，最后 master）
async function confirmRestartAllNodes() {
  showConfirm(
    '确认要一键重启所有节点吗？\n\n操作顺序：\n1. 依次重启所有子节点\n2. 最后重启 master 节点\n\n这将短暂中断所有节点的连接。',
    () => {
      restartAllNodes()
    },
    () => {},
    false
  )
}

async function restartAllNodes() {
  try {
    isRestartingGateway.value = true
    const { host, port } = getGatewayAddress()

    // 获取所有节点列表（排除 master）
    const childNodes = (availableNodeOptions.value || []).filter(node => node.node_id !== 'master')
    const allNodes = [...childNodes, { node_id: 'master', label: 'Master' }]

    for (const node of allNodes) {
      const nodeId = node.node_id
      const normalizedNodeId = nodeId || 'master'

      // 再次检查该节点是否有运行中的 agent（双重保险）
      const nodeRunningAgents = agentList.value.filter(agent => {
        const agentNodeId = agent.node_id || 'master'
        return agent.status === 'running' && agentNodeId === normalizedNodeId
      })

      if (nodeRunningAgents.length > 0) {
        const agentNames = nodeRunningAgents.map(agent => agent.name || agent.agent_id).join(', ')
        showToast(`节点 "${normalizedNodeId}" 仍有运行中的 Agent：${agentNames}，跳过该节点`, 'warning')
        continue
      }

      try {
        // 发送重启请求
        const response = await fetchWithAuth(buildNodeHttpUrl(host, port, normalizedNodeId, 'service/restart'), {
          method: 'POST',
          body: JSON.stringify({
            node_id: normalizedNodeId,
            restart_frontend: restartFrontendService.value
          })
        })

        if (response.ok) {
          const data = await response.json().catch(() => ({}))
          if (data.success === false) {
            showToast(`节点 "${normalizedNodeId}" 重启失败：${data.error?.message || '未知错误'}`, 'error')
          } else {
            showToast(`已向节点 "${normalizedNodeId}" 发送重启请求`, 'success')
          }
        } else {
          showToast(`节点 "${normalizedNodeId}" 重启失败：HTTP ${response.status}`, 'error')
        }
      } catch (error) {
        console.error(`[SETTINGS] Failed to restart node ${normalizedNodeId}:`, error)
        showToast(`节点 "${normalizedNodeId}" 重启失败：${error.message || '未知错误'}`, 'error')
      }

      // 每个节点之间间隔 1 秒，避免请求过于密集
      if (node.node_id !== 'master') {
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
    }

    showToast('所有节点重启命令已发送完成', 'success')
  } catch (error) {
    console.error('[SETTINGS] Failed to restart all nodes:', error)
    showToast(error.message || '重启所有节点失败', 'error')
  } finally {
    setTimeout(() => {
      isRestartingGateway.value = false
    }, 3000)
  }
}

async function restartGateway() {
  if (isRestartingGateway.value) {
    return
  }

  const targetNodeId = restartNodeId.value || 'master'
  
  try {
    isRestartingGateway.value = true
    const { host, port } = getGatewayAddress()
    
    // 发送重启请求，等待响应结果
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'service/restart'), {
      method: 'POST',
      body: JSON.stringify({
        node_id: targetNodeId,
        restart_frontend: restartFrontendService.value
      })
    })

    // 检查响应状态
    if (response.ok) {
      const data = await response.json().catch(() => ({}))
      if (data.success === false) {
        showToast(data.error?.message || '重启请求失败', 'error')
      } else {
        showToast(data.data?.message || `已向节点 "${targetNodeId}" 发送重启请求`, 'success')
      }
    } else {
      showToast(`重启请求失败: HTTP ${response.status}`, 'error')
    }
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

    // 1. 从源节点获取配置
    const getResponse = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/nodes/${sourceNodeId}/config`, {
      method: 'GET'
    })
    const getResult = await getResponse.json()

    if (!getResponse.ok || !getResult.success) {
      throw new Error(getResult.error?.message || '获取源节点配置失败')
    }

    const sourceConfig = getResult.data?.config || {}
    
    // 提取要同步的配置
    const configData = {}
    for (const section of syncConfigSections.value) {
      if (sourceConfig[section]) {
        configData[section] = sourceConfig[section]
      }
    }

    if (Object.keys(configData).length === 0) {
      showToast('没有可同步的配置数据', 'warning')
      return
    }

    // 2. 对每个目标节点设置配置
    let successCount = 0
    const totalCount = targetNodeIds.length
    const results = []

    for (const targetNodeId of targetNodeIds) {
      try {
        const setResponse = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/nodes/${targetNodeId}/config`, {
          method: 'POST',
          body: JSON.stringify({
            config_sections: syncConfigSections.value,
            config_data: configData
          })
        })
        const setResult = await setResponse.json()

        if (setResponse.ok && setResult.success) {
          successCount++
          results.push({
            node_id: targetNodeId,
            success: true,
            data: setResult.data
          })
        } else {
          results.push({
            node_id: targetNodeId,
            success: false,
            error: setResult.error || { message: '设置配置失败' }
          })
        }
      } catch (error) {
        console.error(`[SETTINGS] Failed to set config for node ${targetNodeId}:`, error)
        results.push({
          node_id: targetNodeId,
          success: false,
          error: { message: error.message || '设置配置失败' }
        })
      }
    }

    // 3. 显示结果
    if (successCount === totalCount) {
      showToast(`配置同步成功，已同步到 ${successCount} 个节点`, 'success')
    } else {
      showToast(`配置同步部分成功，成功 ${successCount}/${totalCount} 个节点`, 'warning')
    }

    // 记录详细结果
  } catch (error) {
    console.error('[SETTINGS] Failed to sync config:', error)
    showToast(error.message || '配置同步失败', 'error')
  } finally {
    isSyncingConfig.value = false
  }
}

async function updateCodeToMain() {
  if (isUpdatingCode.value) {
    return
  }

  // 调试日志

  try {
    isUpdatingCode.value = true
    const { host, port } = getGatewayAddress()

    // 获取所有在线节点
    const nodeOptions = availableNodeOptions.value || []
    if (nodeOptions.length === 0) {
      showToast('没有在线节点可更新', 'warning')
      return
    }

    // 对每个节点执行更新
    let successCount = 0
    const totalCount = nodeOptions.length
    const results = []

    for (const node of nodeOptions) {
      const nodeId = node.node_id
      try {
        const response = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/nodes/${nodeId}/code-update`, {
          method: 'POST'
        })
        const result = await response.json()

        if (response.ok && result.success) {
          successCount++
          results.push({
            node_id: nodeId,
            success: true,
            message: result.data?.message || '更新成功'
          })
          showToast(`已向节点 "${nodeId}" 发送更新请求`, 'success')
        } else {
          results.push({
            node_id: nodeId,
            success: false,
            message: result.error?.message || '更新失败'
          })
          showToast(`节点 "${nodeId}" 更新失败：${result.error?.message || '未知错误'}`, 'error')
        }
      } catch (error) {
        console.error(`[SETTINGS] Failed to update code for node ${nodeId}:`, error)
        results.push({
          node_id: nodeId,
          success: false,
          message: error.message || '更新失败'
        })
        showToast(`节点 "${nodeId}" 更新失败：${error.message || '未知错误'}`, 'error')
      }
    }

    // 显示结果

    if (successCount === totalCount) {
      showToast(`代码更新成功，已更新 ${successCount}/${totalCount} 个节点`, 'success')
    } else if (successCount > 0) {
      showToast(`代码更新部分成功，成功 ${successCount}/${totalCount} 个节点`, 'warning')
    } else {
      showToast('代码更新失败，没有节点更新成功', 'error')
    }
  } catch (error) {
    console.error('[SETTINGS] Failed to update code:', error)
    showToast(error.message || '代码更新失败', 'error')
  } finally {
    isUpdatingCode.value = false
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

function disconnectAll() {
  if (!confirm('确定要断开与网关的连接吗？这将清除所有认证信息并断开所有Agent连接。')) {
    return
  }
  
  // 关闭设置弹窗
  showSettingsModal.value = false
  
  // 关闭所有Agent WebSocket连接
  sockets.value.forEach((ws, agentId) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close()
    }
  })
  sockets.value.clear()
  
  // 关闭主Gateway连接
  if (socket.value) {
    socket.value.close()
    socket.value = null
  }
  
  // 清空连接状态
  currentAgentId.value = null
  agentList.value = []
  agentStatuses.value.clear()
  
  // 清除保存的 token 和免登录状态
  localStorage.removeItem('jarvis_auth_token')
  localStorage.removeItem('jarvis_auto_login')
  auth.value.token = ''
  userAccessibleNodes.value = null
  autoLoginEnabled.value = false
  // 强制刷新页面确保状态重置
  setTimeout(() => {
    window.location.reload()
  }, 500)
}

// ========== Agent 管理方法 ==========

// 连接到指定的 Agent（建立独立的 WebSocket 连接）
async function connectToAgent(agent, retryCount = 0) {
  const agentId = agent.agent_id
  const maxRetries = 12  // 最多重试12次
  const retryDelay = 2000 // 2秒重试间隔
  const connectionTimeout = 10000 // 10秒连接超时（适应Agent启动时间）
  
  // 连接锁检查：防止同一 agent 并发重连建多连接
  if (connectingAgents.value.has(agentId)) {
    return Promise.resolve(null)
  }

  // 检查是否已有连接
  if (sockets.value.has(agentId)) {
    const existingWs = sockets.value.get(agentId)
    // 检查现有连接是否仍然有效
    if (existingWs && existingWs.readyState === WebSocket.OPEN) {
      // 已连接，发送 get_status 请求以同步当前状态
      existingWs.send(JSON.stringify({ type: 'get_status', payload: {} }))
      return Promise.resolve(existingWs)
    }
    // 连接已断开或正在关闭，确保完全关闭后再清理
    
    // 等待旧连接完全关闭（避免与后端连接冲突）
    if (existingWs && existingWs.readyState !== WebSocket.CLOSED) {
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
  }
  

  // 加连接锁
  connectingAgents.value.add(agentId)

  const { host, port } = getGatewayAddress()
  const url = buildAgentWebSocketUrl(host, agentId, null, port, String(agent?.node_id || 'master').trim())

  agentConnecting.value = true
  
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
        sockets.value.delete(agentId)
        connectingAgents.value.delete(agentId) // 释放连接锁
        if (agentConnecting.value) agentConnecting.value = false

        // 只通知超时，不重连
        // 重连由switchAgent的稳定性循环统一管理
        reject(new Error(`Connection timeout after ${connectionTimeout}ms`))
      }, connectionTimeout)
      
      // 绑定消息处理
      ws.onmessage = (event) => {
        let message = null
        try {
          message = JSON.parse(event.data)
        } catch (error) {
          console.warn(`[AGENT ${agentId}] message parse failed`, event.data)
          return
        }
        
        // 处理 pong 响应（心跳机制）
        if (message.type === 'pong' || (message.success && message.pong)) {
          lastPongTime.value.set(agentId, Date.now())
          return // pong 消息不需要继续处理
        }
        
        handleMessage(message, agentId)
      }
      
      ws.onopen = () => {
        if (connectionHandled) {
          return
        }
        connectionHandled = true

        clearTimeout(timeoutId)
        connectingAgents.value.delete(agentId) // 释放连接锁
        agentConnecting.value = false

        // 保存连接
        sockets.value.set(agentId, ws)

        // 初始化消息记录
        if (!allOutputs.value.has(agentId)) {
          allOutputs.value.set(agentId, [])
        }

        // 发送该 Agent 的增量同步请求
        const lastSeq = getAgentLastSeq(agentId)
        const agent_seqs = { [agentId]: lastSeq }
        ws.send(JSON.stringify({
          type: 'sync_request',
          payload: { agent_seqs }
        }))

        // 标记连接已完成（在onclose中用于判断是否需要重试）
        ws._connectionCompleted = true

        // Agent 心跳机制已移除

        // 连接成功，resolve Promise
        resolve(ws)
      }

      
      ws.onclose = (event) => {
        // 心跳定时器清理代码已移除

        // 已建立的连接断开（connectionHandled=true 且 _connectionCompleted=true）
        // 需要触发重连，而不是忽略
        if (connectionHandled && !ws._connectionCompleted) {
          return
        }

        if (!connectionHandled) {
          connectionHandled = true
          clearTimeout(timeoutId)
        }

        sockets.value.delete(agentId)
        connectingAgents.value.delete(agentId) // 释放连接锁
        if (agentConnecting.value) agentConnecting.value = false

        // 如果断开的Agent不是当前活跃的Agent，静默重连（后台Agent需要保持消息接收）
        if (agentId !== currentAgentId.value) {
          // 检查主网关连接状态，如果主网关断开则不重连Agent
          if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
            if (!ws._connectionCompleted) {
              reject(new Error('Background agent disconnected (gateway offline)'))
            }
            return
          }
          if (retryCount < maxRetries) {
            setTimeout(() => {
              connectToAgent({ agent_id: agentId, name: agentId, node_id: agent?.node_id }, retryCount + 1)
                .catch(e => console.warn(`[AGENT ${agentId}] Background reconnect failed:`, e.message))
            }, retryDelay)
          }
          if (!ws._connectionCompleted) {
            reject(new Error('Background agent disconnected'))
          }
          return
        }

        // 当前Agent断开：自动重连
        // 检查主网关连接状态，如果主网关断开则不重连Agent
        if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
          if (!ws._connectionCompleted) {
            reject(new Error('Agent disconnected (gateway offline)'))
          }
          return
        }
        setTimeout(() => {
          // 检查是否已有新连接，避免重复重连
          const currentWs = sockets.value.get(agentId)
          if (currentWs && currentWs.readyState === WebSocket.OPEN) {
            return
          }
          connectToAgent({ agent_id: agentId, name: agentId, node_id: agent?.node_id }, 0)
            .catch(e => console.warn(`[AGENT ${agentId}] Auto-reconnect failed:`, e.message))
        }, retryDelay)

        if (!ws._connectionCompleted) {
          reject(new Error(`Connection closed: code=${event.code}, reason=${event.reason || 'unknown'}`))
        }
      }
      
      ws.onerror = (error) => {
        if (connectionHandled) {
          return
        }
        connectionHandled = true

        clearTimeout(timeoutId)
        console.error(`[AGENT ${agentId}] Connection error:`, error)
        connectingAgents.value.delete(agentId) // 释放连接锁
        if (agentConnecting.value) agentConnecting.value = false

        // 只清理和通知，不重连
        // 重连由switchAgent的稳定性循环统一管理
        ws.close()
        sockets.value.delete(agentId)
        reject(new Error('Connection error'))
      }
      
    } catch (error) {
      console.error(`[AGENT ${agentId}] Failed to connect:`, error)
      connectingAgents.value.delete(agentId) // 释放连接锁
      agentConnecting.value = false
      
      if (retryCount < maxRetries) {
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
    'waiting_single': '等待确认',
    'waiting_confirm': '等待确认'
  }
  const executionStatusText = labels[executionStatus] || '运行中'
  
  // 组合显示：运行中（等待状态）
  return `运行中（${executionStatusText}）`
}

// 获取状态 CSS 类名
function getStatusClass(agent) {
  const statusData = agentStatuses.value.get(agent.agent_id)

  // 优先使用 agent 状态：如果 agent 已停止，直接显示 stopped
  if (agent.status === 'stopped') {
    return 'stopped'
  }

  // 非 stopped 状态：使用 execution_status
  if (statusData && statusData.execution_status) {
    return statusData.execution_status
  }

  // 默认 running
  return 'running'
}

// 判断是否处于等待输入状态
function isWaitingInput(agent) {
  const statusClass = getStatusClass(agent)
  return statusClass === 'waiting_multi' || statusClass === 'waiting_single' || statusClass === 'waiting_confirm'
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
    agentStatuses.value.set(agent.agent_id, {execution_status: executionStatus, non_interactive: !!result.non_interactive})

    // 当前 Agent 连接后根据 execution_status 恢复输入 UI
    if (agent.agent_id === currentAgentId.value) {
      if (executionStatus === 'waiting_single') {
        inputMode.value = 'single'
        panelInputModes.value.set(agent.agent_id, 'single')
        // 聚焦输入框（弹窗或宠物环形菜单打开时不抢焦点）
        const targetPanel = panels.value.find(p => p.agentId === agent.agent_id)
        const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
        if (sp?.focusInput && !isAutoFocusSuppressed() && !isPetMenuOpen()) sp.focusInput()
      } else if (executionStatus === 'waiting_multi') {
        inputMode.value = 'multi'
        panelInputModes.value.set(agent.agent_id, 'multi')
        // 聚焦输入框（弹窗或宠物环形菜单打开时不抢焦点）
        const targetPanel = panels.value.find(p => p.agentId === agent.agent_id)
        const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
        if (sp?.focusInput && !isAutoFocusSuppressed() && !isPetMenuOpen()) sp.focusInput()
      } else if (executionStatus === 'waiting_confirm') {
        // 从 status 响应中获取 pending_confirm 并显示对话框
        const pendingConfirm = result.pending_confirm
        if (pendingConfirm && pendingConfirm.payload) {
          const payload = pendingConfirm.payload
          pendingConfirmAgentId.value = agent.agent_id
          // 更新 Panel 内嵌确认数据（按 agentId 隔离）
          panelConfirmData.value.set(agent.agent_id, {
            message: payload.message || '请确认',
            defaultConfirm: payload.default !== undefined ? payload.default : true
          })
          // 确认请求使用单行输入模式
          inputMode.value = 'single'
          panelInputModes.value.set(agent.agent_id, 'single')
          inputTip.value = payload.message || '请确认 (y/n/Enter)'
          panelInputTips.value.set(agent.agent_id, payload.message || '请确认 (y/n/Enter)')
          // 聚焦输入框（弹窗或宠物环形菜单打开时不抢焦点）
          const targetPanel = panels.value.find(p => p.agentId === agent.agent_id)
          const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
          if (sp?.focusInput && !isAutoFocusSuppressed() && !isPetMenuOpen()) sp.focusInput()
          // 无 Panel 时不弹全局对话框，确认请求静默等待，用户打开 Panel 后可见 confirm 控件
        } else {
          console.warn('[AGENT STATUS] waiting_confirm but no pending_confirm payload found')
        }
      } else {
        inputMode.value = 'multi'
        panelInputModes.value.set(agent.agent_id, 'multi')
      }
    } else {
    }
    
    return executionStatus
  } catch (error) {
    console.error(`[AGENT STATUS] Error fetching status for agent ${agent.agent_id}:`, error)
    return 'running' // 错误时返回默认状态
  }
}

// 主动同步在线 agent 的执行状态（避免仅靠 WebSocket 推送，错过等待输入状态）
const syncingAgentStatuses = new Set()
let lastStatusSyncAt = 0
const STATUS_SYNC_INTERVAL = 5000 // 状态同步最小间隔（毫秒）

function syncOnlineAgentStatuses() {
  const now = Date.now()
  if (now - lastStatusSyncAt < STATUS_SYNC_INTERVAL) {
    return
  }
  lastStatusSyncAt = now

  for (const agent of agentList.value) {
    if (agent.status !== 'running') continue
    if (syncingAgentStatuses.has(agent.agent_id)) continue
    syncingAgentStatuses.add(agent.agent_id)
    fetchAgentStatus(agent)
      .catch((error) => {
        console.warn(`[AGENT STATUS] Sync failed for ${agent.agent_id}:`, error?.message)
      })
      .finally(() => {
        syncingAgentStatuses.delete(agent.agent_id)
      })
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
  // 切换节点时重新获取对应节点的模型组列表（复制 Agent 时跳过）
  if (!skipNameWatch) {
    fetchModelGroups(newNodeId || 'master')
  }
}, { flush: 'sync' })

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

  // 带 Ctrl/Alt/Meta 修饰键时交由全局快捷键处理，不做列表导航
  if (event.ctrlKey || event.altKey || event.metaKey) return

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
    // 滚动到选中项
    scrollToDirSelected()
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
    // 滚动到选中项
    scrollToDirSelected()
    event.preventDefault()
    return
  }
  
  if (event.key === 'Enter') {
    // 回车键：如果选中了列表项，则进入该目录；否则确认当前选择
    if (selectedDirIndex.value >= 0 && selectedDirIndex.value <= maxIndex) {
      // 有选中列表项，进入该目录
      const selectedPath = filteredDirList.value[selectedDirIndex.value].path
      selectDirectory(selectedPath)
      enterDirectory(selectedPath)
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
    // 保存工作目录到历史记录（按节点区分）
    saveRecentWorkDir(selectedDir.value, getCreateAgentDirectoryNodeId())
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
    fetchUserList(),
    fetchUserAccessibleNodes(),
  ])
  // 加载最近使用的工作目录
  loadRecentWorkDirs()
  newAgentNodeId.value = ''
  newAgentDir.value = '~'
  newAgentCreateError.value = ''
  resetDirectorySelectionState()
  showCreateAgentModal.value = true
}

// 获取模型组列表
async function fetchModelGroups(nodeId = 'master', autoSelect = true) {
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
      if (autoSelect && modelGroups.value.length > 0) {
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

async function fetchUserAccessibleNodes() {
  try {
    const { host, port } = getGatewayAddress()
    const userId = auth.value.userInfo?.user_id
    if (!userId) { userAccessibleNodes.value = []; return }
    const response = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/permissions/user/${encodeURIComponent(userId)}/accessible-nodes`)
    if (!response.ok) {
      console.warn('[PERM] 获取可访问节点失败:', response.status)
      userAccessibleNodes.value = []
      return
    }
    const result = await response.json()
    if (result.success && result.data) {
      userAccessibleNodes.value = result.data.accessible_nodes || []
    } else {
      userAccessibleNodes.value = []
    }
  } catch (error) {
    console.error('[PERM] 获取可访问节点出错:', error)
    userAccessibleNodes.value = []
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
    const processedNodes = nodes
      .filter(node => node && String(node.node_id || '').trim())
      .map(node => ({
        ...node,
        node_id: String(node.node_id || '').trim(),
      }))
    // 确保 master 节点始终在选项列表中
    if (!processedNodes.some(n => n.node_id === 'master')) {
      processedNodes.unshift({ node_id: 'master', status: 'running' })
    }
    availableNodeOptions.value = processedNodes
  } catch (error) {
    console.error('[NODE] 获取节点状态出错:', error)
    availableNodeOptions.value = []
  }
}

async function fetchUserList() {
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/users/brief`)
    if (!response.ok) {
      console.warn('[USER] 获取用户列表失败:', response.status)
      availableUserOptions.value = []
      return
    }
    const result = await response.json()
    availableUserOptions.value = result?.data?.users || []
  } catch (err) {
    console.warn('[USER] 获取用户列表异常:', err)
    availableUserOptions.value = []
  }
}

function formatNodeOptionLabel(node) {
  const nodeId = String(node?.node_id || '').trim()
  const displayName = getNodeDisplayName(nodeId)
  const status = String(node?.status || node?.runtime_status || '').trim()
  return status ? `${displayName} (${status})` : displayName
}

function getDefaultTerminalNodeId(nodes = []) {
  if (nodes.some(node => node.node_id === 'master')) {
    return 'master'
  }
  return nodes[0]?.node_id || ''
}

watch(availableNodeOptions, (nodes) => {
  const hasSelectedNode = nodes.some(node => node.node_id === selectedTerminalNodeId.value)
  if (!hasSelectedNode) {
    selectedTerminalNodeId.value = getDefaultTerminalNodeId(nodes)
  }
}, { immediate: true })

function getAgentNodeLabel(agent) {
  return String(agent?.node_id || '').trim() || 'master'
}

// Agent 所属节点的展示名（优先自定义显示名），仅用于界面展示
function getAgentNodeDisplayLabel(agent) {
  return getNodeDisplayName(getAgentNodeLabel(agent))
}

function getAgentProxyNodeLabel(agent) {
  return String(agent?.proxy_node || '').trim()
}

function getCurrentAgentNodeId() {
  return String(currentAgent.value?.node_id || '').trim()
}

// 获取编辑器目标节点ID（优先使用编辑器对应agent的节点ID）
function getEditorTargetNodeId() {
  const editorAgentNodeId = activeEditorSession.value?.agent?.node_id
  return String(editorAgentNodeId || getCurrentAgentNodeId() || 'master').trim() || 'master'
}

async function createAgent() {
  if (!newAgentDir.value.trim()) return
  // 无交互模式下必须提供任务描述
  if (newAgentNoInteractionMode.value && !newAgentTaskDescription.value.trim()) {
    alert('无交互模式下必须提供任务描述')
    return
  }
  // 校验：同一节点同一工作目录不允许同时有两个未启用 worktree 的 code_agent
  if (newAgentType.value === 'code_agent' && !newCodeAgentWorktree.value) {
    const targetNodeId = String(newAgentNodeId.value || 'master').trim() || 'master'
    const normalizedDir = newAgentDir.value.trim()
    const conflictingAgent = agentList.value.find(agent => {
      if (isStoppedAgent(agent)) return false  // 已停止的 agent 不冲突
      if (agent.agent_type !== 'code_agent') return false
      if (agent.worktree) return false  // 启用了 worktree 的不冲突
      const agentNodeId = String(agent.node_id || '').trim() || 'master'
      if (agentNodeId !== targetNodeId) return false
      if (agent.working_dir?.trim() !== normalizedDir) return false
      return true
    })
    if (conflictingAgent) {
      const conflictName = conflictingAgent.name || conflictingAgent.agent_id || '未命名'
      newAgentCreateError.value = `工作目录冲突：节点 ${targetNodeId} 下已存在未启用 worktree 的代码 Agent「${conflictName}」。\n同一工作目录下只能有一个未启用 worktree 的代码 Agent。\n请启用 worktree 或选择其他工作目录。`
      return
    }
  }
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
        worktree: newAgentType.value === 'code_agent' ? newCodeAgentWorktree.value : false,
        quick_mode: newAgentQuickMode.value,
        restore_session: newAgentRestoreSession.value,
        no_interaction_mode: newAgentNoInteractionMode.value,
        task: newAgentNoInteractionMode.value && newAgentTaskDescription.value.trim() ? newAgentTaskDescription.value.trim() : undefined,
        node_id: targetNodeId,
        proxy_node: newAgentProxyNode.value || undefined,
        access_acl: (newAgentAccessAclRead.value.length || newAgentAccessAclInteract.value.length) ? {
          read: newAgentAccessAclRead.value,
          interact: newAgentAccessAclInteract.value,
        } : undefined,
      })
    })
    if (!response.ok) {
      const error = await response.json()
      alert(`创建失败: ${error.error?.message || error.detail || '未知错误'}`)
      return
    }
    const result = await response.json()
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
      newAgentCreateError.value = '' // 重置错误信息
      newCodeAgentWorktree.value = false
      newAgentQuickMode.value = false
      newAgentRestoreSession.value = false
      newAgentNoInteractionMode.value = false
      newAgentTaskDescription.value = ''
      newAgentNodeId.value = ''
      newAgentAccessAclRead.value = []
      newAgentAccessAclInteract.value = []
      // 重置为默认名称（根据当前选中的 agent 类型）
      newAgentName.value = generateAgentName(newAgentType.value)
      // 若当前处于宠物大厅（无任何可见 Panel），保持在大厅，不切换到 Panel；
      // 否则（已有 Panel 打开）按原逻辑在新 Panel 中打开该 Agent
      if (!hasNoPanel.value) {
        await openAgentInPanel(agent)
      }
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

  completionAgentId.value = currentAgentId.value
  completionSearch.value = ''
  selectedIndex.value = -1
  showCompletions.value = true

  // 获取补全列表
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `completions/${currentAgent.value.agent_id}`))
    
    const result = await response.json()
    
    if (!response.ok) {
      alert(`获取补全列表失败: ${result.error?.message || result.detail || '未知错误'}`)
      return
    }
    
    if (result.success && result.data) {
      completions.value = sortCompletionItems(result.data)
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

// 关闭补全对话框（取消选择）：键盘输入 @ 触发时保留 @ 符号，按钮触发时无需插入任何字符
function closeCompletionsWithoutSelect() {
  if (completionHasAtSymbol.value && completionSource.value !== 'lobby') {
    insertAtPosition('@', completionCursorPos.value, completionAgentId.value)
  }
  showCompletions.value = false
  selectedIndex.value = -1
  completionCursorPos.value = -1
  completionHasAtSymbol.value = false
  completionAgentId.value = null
  completionSource.value = 'panel'
}

// 处理补全对话框的键盘事件
function handleCompletionKeydown(event) {
  const maxIndex = filteredCompletions.value.length - 1

  if (event.key === 'Escape') {
    // ESC 键关闭对话框
    closeCompletionsWithoutSelect()
    event.preventDefault()
    return
  }

  // 带 Ctrl/Alt/Meta 修饰键时交由全局快捷键处理，不做列表导航
  if (event.ctrlKey || event.altKey || event.metaKey) return

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
      insertCompletion(filteredCompletions.value[selectedIndex.value], completionAgentId.value)
      event.preventDefault()
    }
    return
  }
}

// 滚动到选中的条目
function scrollToSelected() {
  nextTick(() => {
    const modal = completionsModalRef.value
    if (!modal) return
    const selectedItem = modal.itemRefs?.[selectedIndex.value]
    if (selectedItem) {
      selectedItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  })
}

// 滚动到选中的目录项
function scrollToDirSelected() {
  nextTick(() => {
    const dialog = dirDialogRef.value
    if (!dialog) return
    const listContainer = dialog.dirListRef
    if (!listContainer) return

    // 找到选中项的DOM元素
    const items = listContainer.querySelectorAll('.dir-item')
    const selectedItem = items[selectedDirIndex.value]
    if (selectedItem) {
      selectedItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  })
}

// 在指定位置插入文本
function insertAtPosition(text, position, agentId = null) {
  const targetAgentId = agentId || currentAgentId.value
  const textarea = targetAgentId
    ? document.querySelector(`.input-wrapper textarea[data-agent-id="${targetAgentId}"]`) || document.querySelector('.input-wrapper textarea')
    : document.querySelector('.input-wrapper textarea')
  if (!textarea || position === -1) return

  const currentText = targetAgentId
    ? (panelInputTexts.value.get(targetAgentId) || '')
    : inputText.value
  // 在指定位置插入文本
  const newText = currentText.substring(0, position) + text + currentText.substring(position)
  if (targetAgentId) {
    panelInputTexts.value.set(targetAgentId, newText)
  }
  inputText.value = newText

  // 更新 textarea 并设置光标位置
  textarea.value = newText
  const newCursorPos = position + text.length
  textarea.setSelectionRange(newCursorPos, newCursorPos)
  textarea.focus()
}
// 插入选中的补全
function insertCompletion(item, agentId = null) {
  const targetAgentId = agentId || currentAgentId.value

  // 来自宠物大厅：写回 PetLobby 内部输入框
  if (completionSource.value === 'lobby') {
    recordCompletionSelection(item)
    petLobbyRef.value?.insertCompletionText?.(
      targetAgentId,
      item.value,
      completionCursorPos.value,
      completionHasAtSymbol.value,
    )
    showCompletions.value = false
    selectedIndex.value = -1
    completionCursorPos.value = -1
    completionHasAtSymbol.value = false
    completionAgentId.value = null
    completionSource.value = 'panel'
    return
  }

  const textarea = targetAgentId
    ? document.querySelector(`.input-wrapper textarea[data-agent-id="${targetAgentId}"]`) || document.querySelector('.input-wrapper textarea')
    : document.querySelector('.input-wrapper textarea')

  // 数据源以 panelInputTexts / inputText 为准，textarea 仅用于同步光标；
  // 移动端点击补全项时 textarea 可能已失焦甚至查询不到，不能因此直接放弃插入
  const text = targetAgentId
    ? (panelInputTexts.value.get(targetAgentId) || '')
    : (textarea ? textarea.value : inputText.value)

  recordCompletionSelection(item)

  // 键盘输入 @ 触发的补全：删除 @ 符号；按钮触发的补全：输入框中没有 @，直接在光标处插入
  let deleteStart
  if (completionHasAtSymbol.value && completionCursorPos.value !== -1) {
    deleteStart = completionCursorPos.value
  } else {
    // 无 @ 可删：优先用打开补全时记录的光标位置，否则退回到末尾
    deleteStart = completionCursorPos.value === -1 ? text.length : completionCursorPos.value
  }
  if (deleteStart > text.length) deleteStart = text.length

  // 在 deleteStart 位置插入补全（添加单引号包裹）
  const valueToInsert = `'${item.value}'`
  const newText = text.substring(0, deleteStart) + valueToInsert + text.substring(deleteStart)
  if (targetAgentId) {
    // 替换整个 Map 以触发 Vue 响应式更新（Map.set 不会）
    const nextMap = new Map(panelInputTexts.value)
    nextMap.set(targetAgentId, newText)
    panelInputTexts.value = nextMap
  }
  inputText.value = newText

  // 同步 DOM 与光标位置（textarea 存在时才操作）
  if (textarea) {
    textarea.value = newText
    const newCursorPos = deleteStart + valueToInsert.length
    textarea.setSelectionRange(newCursorPos, newCursorPos)
    textarea.focus()
  }

  // 关闭弹窗
  showCompletions.value = false
  selectedIndex.value = -1
  completionCursorPos.value = -1
  completionHasAtSymbol.value = false
  completionAgentId.value = null
}

// 获取 Agent 列表
async function fetchAgentList() {
  try {
    const { host, port } = getGatewayAddress()
    // 始终使用 'master' 节点来获取所有节点的 agent 列表
    const targetNodeId = 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'))
    
    if (!response.ok) return
    
    const result = await response.json()

    
    // 更新列表（后端返回格式: { success: true, data: agents }）
    if (result.success && result.data) {
      // 反转数组，让后创建的 agent 排在前面
      agentList.value = result.data.slice().reverse().map(agent => ({
        ...agent,
        node_id: String(agent?.node_id || '').trim() || 'master',
      }))

      // 确保所有在线 agent 都已建立连接（内部会跳过已连接的，重复调用安全），
      // 这样未被点击过的 agent 也能实时接收状态更新。
      autoConnectToOnlineAgents()

      // 主动同步在线 agent 的执行状态（如等待输入），
      // 避免因错过 WebSocket 推送导致状态停留在 running。
      syncOnlineAgentStatuses()
    }
    
    // 更新当前 Agent 状态
    const currentAgent = agentList.value.find(a => a.agent_id === currentAgentId.value)
    if (currentAgent && currentAgent.status !== 'running') {
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
    worktree: agent.agent_type === 'code_agent' ? Boolean(agent.worktree) : false,
    quick_mode: Boolean(agent.quick_mode),
    restore_session: Boolean(agent.restore_session),
    no_interaction_mode: Boolean(agent.no_interaction_mode),
    task: agent.task || '',
    node_id: targetNodeId || agent.node_id || undefined,
    proxy_node: agent.proxy_node || undefined,
  }

}

// 复制 Agent - 弹出创建面板并预填充参数
async function copyAgent(agent) {
  // 先设置标志位，跳过 watch 中的名称设置和模型组自动选择
  skipNameWatch = true

  // 刷新模型组列表和节点状态（不自动选择模型组）
  await Promise.all([
    fetchModelGroups(agent?.node_id || 'master', false),
    fetchNodeStatus(),
    fetchUserList(),
    fetchUserAccessibleNodes(),
  ])

  // 填充表单变量
  newAgentType.value = agent.agent_type || 'code_agent'
  newAgentModelGroup.value = agent.llm_group || 'default'
  newCodeAgentWorktree.value = agent.agent_type === 'code_agent' ? Boolean(agent.worktree) : false
  newAgentQuickMode.value = Boolean(agent.quick_mode)
  newAgentRestoreSession.value = Boolean(agent.restore_session)
  newAgentNoInteractionMode.value = Boolean(agent.no_interaction_mode)
  newAgentTaskDescription.value = agent.task || ''
  newAgentProxyNode.value = agent.proxy_node || ''
  // 先设置 node_id（会触发 watch 重置目录），再设置正确的目录
  newAgentNodeId.value = String(agent?.node_id || '').trim()
  newAgentDir.value = agent.working_dir || '~'
  // 设置正确的名称（Agent类型-创建时间格式）
  newAgentName.value = generateAgentName(agent.agent_type || 'code_agent')

  // 重置目录选择状态
  resetDirectorySelectionState()
  newAgentCreateError.value = ''

  // 打开创建弹窗
  showCreateAgentModal.value = true

  // 等待 DOM 更新后重置标志位
  await nextTick()
  skipNameWatch = false
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
            buildCopiedAgentPayload(agent, generateAgentName(agent.agent_type || 'code_agent'), targetNodeId)
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

// Agent 分组操作
function addSelectedToGroup(groupId) {
  const group = agentGroups.value.find(g => g.id === groupId)
  if (!group) return
  if (!group.agentIds) group.agentIds = []
  // 只添加活跃的 agent，过滤已停止的
  const selectedIds = Array.from(selectedAgents.value).filter(agentId => {
    const agent = agentList.value.find(a => a.agent_id === agentId)
    return agent && !isStoppedAgent(agent)
  })
  if (selectedIds.length === 0) {
    showToast('没有可加入分组的活跃 Agent', 'warning')
    return
  }
  let added = 0
  selectedIds.forEach(agentId => {
    if (!group.agentIds.includes(agentId)) {
      group.agentIds.push(agentId)
      added++
    }
  })
  saveAgentGroups()
  selectedAgents.value.clear()
  selectedAgents.value = new Set()
  isBatchMode.value = false
  showToast(`已加入 ${added} 个 Agent 到「${group.name}」`, 'success')
}

function createGroupWithAgents(name) {
  const trimmedName = String(name || '').trim()
  if (!trimmedName) {
    showToast('请输入分组名称', 'warning')
    return
  }
  const group = {
    id: `group-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: trimmedName,
    agentIds: [],
  }
  const selectedIds = Array.from(selectedAgents.value).filter(agentId => {
    const agent = agentList.value.find(a => a.agent_id === agentId)
    return agent && !isStoppedAgent(agent)
  })
  selectedIds.forEach(agentId => {
    if (!group.agentIds.includes(agentId)) {
      group.agentIds.push(agentId)
    }
  })
  agentGroups.value.push(group)
  saveAgentGroups()
  selectedAgents.value.clear()
  selectedAgents.value = new Set()
  isBatchMode.value = false
  showToast(`已创建分组「${group.name}」并加入 ${group.agentIds.length} 个 Agent`, 'success')
}

// 查看 Agent 的 Diff
async function viewDiff(agent) {
  if (!agent || !agent.agent_id) {
    console.warn('[DIFF] Invalid agent:', agent)
    return
  }

  diffLoading.value = true
  showDiffModal.value = true
  diffContent.value = ''

  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/diff`))

    if (!response.ok) {
      console.warn(`[DIFF] Failed to fetch diff for agent ${agent.agent_id}:`, response.status)
      diffContent.value = '<div class="diff-error">获取 diff 失败</div>'
      return
    }

    const result = await response.json()
    
    // 使用后端返回的结构化数据，添加数据验证
    if (result.files && Array.isArray(result.files) && result.files.length > 0) {
      // 验证并过滤有效的文件数据
      const validFiles = result.files.filter(file => {
        // 验证文件对象包含必要字段
        if (!file || typeof file !== 'object') return false
        if (!file.rows || !Array.isArray(file.rows)) return false
        // 验证 rows 中的每个元素
        return file.rows.every(row => {
          return row && typeof row === 'object' && 
                 ['equal', 'insert', 'delete', 'replace'].includes(row.type)
        })
      })
      
      if (validFiles.length > 0) {
        diffContent.value = validFiles.map(f => renderSideBySideDiff(f)).join('')
      } else {
        diffContent.value = '<div class="diff-empty">暂无有效变更数据</div>'
      }
    } else {
      diffContent.value = '<div class="diff-empty">暂无变更</div>'
    }
  } catch (error) {
    console.error('[DIFF] Error fetching diff:', error)
    diffContent.value = '<div class="diff-error">获取 diff 失败: ' + escapeHtml(error.message) + '</div>'
  } finally {
    diffLoading.value = false
  }
}

// 查看规则
async function viewRules(agent) {
  if (!agent || !agent.agent_id) {
    console.warn('[RULES] Invalid agent:', agent)
    return
  }

  rulesLoading.value = true
  showRulesModal.value = true
  rulesContent.value = []
  rulesLoadedContent.value = ''

  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/rules`))

    if (!response.ok) {
      console.warn(`[RULES] Failed to fetch rules for agent ${agent.agent_id}:`, response.status)
      rulesContent.value = []
      rulesLoadedContent.value = ''
      return
    }

    const result = await response.json()
    const rules = result.rules || []
    // 已加载的规则置顶
    rulesContent.value = rules.sort((a, b) => {
      if (a.is_loaded === b.is_loaded) return 0
      return a.is_loaded ? -1 : 1
    })
    rulesLoadedContent.value = result.loaded_rules_content || ''
  } catch (error) {
    console.error('[RULES] Error fetching rules:', error)
    rulesContent.value = []
    rulesLoadedContent.value = ''
  } finally {
    rulesLoading.value = false
  }
}

async function exitNonInteractiveMode(agent) {
  if (!agent || !agent.agent_id) {
    console.warn('[EXIT NON-INTERACTIVE] Invalid agent:', agent)
    return
  }

  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/exit_non_interactive`), {
      method: 'POST'
    })

    if (!response.ok) {
      console.warn(`[EXIT NON-INTERACTIVE] Failed for agent ${agent.agent_id}:`, response.status)
      return
    }

    const result = await response.json()
    if (result.success) {
      // 更新本地状态
      const current = agentStatuses.value.get(agent.agent_id) || {}
      agentStatuses.value.set(agent.agent_id, {...current, non_interactive: false})
    } else {
      console.warn(`[EXIT NON-INTERACTIVE] Failed for agent ${agent.agent_id}:`, result.error || 'Unknown error')
    }
  } catch (error) {
    console.error(`[EXIT NON-INTERACTIVE] Error for agent ${agent.agent_id}:`, error)
  }
}

// 查看工具
const showToolsModal = ref(false)
const toolsContent = ref({ all_tools: [], allowed_tools: null })
const toolsLoading = ref(false)

async function viewTools(agent) {
  if (!agent || !agent.agent_id) {
    console.warn('[TOOLS] Invalid agent:', agent)
    return
  }

  toolsLoading.value = true
  showToolsModal.value = true
  toolsContent.value = { all_tools: [], allowed_tools: null }

  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/tools`))

    if (!response.ok) {
      console.warn(`[TOOLS] Failed to fetch tools for agent ${agent.agent_id}:`, response.status)
      toolsContent.value = { all_tools: [], allowed_tools: null }
      return
    }

    const result = await response.json()
    const allTools = result.all_tools || []
    const allowedTools = result.allowed_tools
    
    // 如果有allowed_tools，将允许的工具排到顶部
    if (allowedTools && allowedTools.length > 0) {
      const allowedSet = new Set(allowedTools)
      allTools.sort((a, b) => {
        const aAllowed = allowedSet.has(a.name)
        const bAllowed = allowedSet.has(b.name)
        if (aAllowed && !bAllowed) return -1
        if (!aAllowed && bAllowed) return 1
        return 0
      })
    }
    
    toolsContent.value = {
      all_tools: allTools,
      allowed_tools: allowedTools
    }
  } catch (error) {
    console.error('[TOOLS] Error fetching tools:', error)
    toolsContent.value = { all_tools: [], allowed_tools: null }
  } finally {
    toolsLoading.value = false
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
      showRenameAgentModal.value = false
      return
    }
    
    await fetchAgentList()
    showToast('重命名成功', 'success')
    showRenameAgentModal.value = false
  } catch (error) {
    console.error('[AGENT] Rename failed:', error)
    alert(`重命名失败: ${error.message}`)
    showRenameAgentModal.value = false
  }
}

// Agent ACL编辑
const showEditAccessModal = ref(false)
const editingAccessAgent = ref(null)
const editAccessRead = ref([])
const editAccessInteract = ref([])

// 弹窗关闭后开启自动聚焦静默窗口：
// 避免关闭瞬间挂起的异步状态同步（fetchAgentStatus）把焦点抢回输入框。
// 注意：必须放在所有被监听的 ref 与 modalAutoFocusSuppressUntil 声明之后，
// 否则 watch 注册时立即求值 getter 会命中 let/const 的暂时性死区（TDZ）而报错。
watch([showRenameAgentModal, showEditAccessModal, showCreateAgentModal, showSettingsModal], (values, prevValues) => {
  const anyClosed = values.some((v, i) => !v && prevValues[i])
  if (anyClosed) {
    modalAutoFocusSuppressUntil = Date.now() + MODAL_AUTOFOCUS_SUPPRESS_MS
  }
})

async function editAgentAccess(agent) {
  editingAccessAgent.value = agent
  const acl = agent.access_acl || {}
  editAccessRead.value = Array.isArray(acl.read) ? [...acl.read] : []
  editAccessInteract.value = Array.isArray(acl.interact) ? [...acl.interact] : []
  showEditAccessModal.value = true
  // 获取用户列表供选择
  await fetchUserList()
}

async function saveAgentAccess() {
  const agent = editingAccessAgent.value
  if (!agent) return
  try {
    const { host, port } = getGatewayAddress()
    const targetNodeId = String(agent?.node_id || '').trim() || 'master'
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agent.agent_id}/access`), {
      method: 'PUT',
      body: JSON.stringify({
        access_acl: {
          read: editAccessRead.value,
          interact: editAccessInteract.value,
        }
      })
    })
    if (!response.ok) {
      const error = await response.json()
      alert(`权限更新失败: ${error.error?.message || error.detail || '未知错误'}`)
      return
    }
    await fetchAgentList()
    showToast('权限更新成功', 'success')
    showEditAccessModal.value = false
  } catch (error) {
    console.error('[AGENT] Access update failed:', error)
    alert(`权限更新失败: ${error.message}`)
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

        // 先删除服务端的 Agent 历史数据
        try {
          const historyKey = `agent_history_${agentId}`
          await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `data/${historyKey}`), {
            method: 'DELETE'
          })
        } catch (historyError) {
          console.warn('[HISTORY] Failed to delete server history for', agentId, ':', historyError.message)
          // 历史删除失败不影响后续 agent 删除流程
        }

        // 删除 Agent
        const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agentId}`), {
          method: 'DELETE'
        })

        const result = await response.json()

        if (!response.ok || !result.success) {
          alert(`删除失败：${result.error?.message || '未知错误'}`)
          return
        }

        
        // 清除该 Agent 的历史记录
        historyStorage.clearHistoryForAgent(agentId)
        
        // 清除该 Agent 的文件树状态
        fileTreeState.value.delete(agentId)
        fileTreeExpanded.value.delete(agentId)
        fileTreeLoading.value.delete(agentId)

        // 销毁该 Agent 对应的 Panel
        for (const panel of [...panels.value]) {
          if (panel.agentId === agentId) {
            closePanel(panel.id)
          }
        }
        
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

// 无损重生 Agent - 保存会话 → 删除 → 重建 → 恢复会话
async function regenerateAgent(agent) {
  if (!agent || !agent.agent_id) return
  // 隐藏 agent 侧边栏，避免遮挡确认对话框（仅移动端）
  if (windowWidth.value <= 768) showAgentSidebar.value = false
  showConfirm(
    `确认无损重生 Agent「${agent.name || agent.agent_id}」？\n\n将保存当前会话后删除并重建，配置（模型组/工具组/任务等）将保留。`,
    async () => {
      try {
        const { host, port } = getGatewayAddress()
        const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'

        // 第一步：保存会话
        let sessionFile = null
        try {
          const saveResp = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/sessions/save`), {
            method: 'POST'
          })
          const saveResult = await saveResp.json()
          if (saveResp.ok && saveResult.success) {
            sessionFile = saveResult.session_file || saveResult.data?.session_file || null
          } else {
            console.warn('[REGENERATE] Session save failed:', saveResult)
          }
        } catch (saveError) {
          console.warn('[REGENERATE] Session save error:', saveError.message)
        }

        // 第二步：删除旧 Agent
        const delResp = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agent.agent_id}`), {
          method: 'DELETE'
        })
        const delResult = await delResp.json()
        if (!delResp.ok || !delResult.success) {
          alert(`重生失败（删除阶段）：${delResult.error?.message || '未知错误'}`)
          return
        }

        // 清除本地状态
        historyStorage.clearHistoryForAgent(agent.agent_id)
        fileTreeState.value.delete(agent.agent_id)
        fileTreeExpanded.value.delete(agent.agent_id)
        fileTreeLoading.value.delete(agent.agent_id)
        for (const panel of [...panels.value]) {
          if (panel.agentId === agent.agent_id) {
            closePanel(panel.id)
          }
        }
        if (currentAgentId.value === agent.agent_id) {
          currentAgentId.value = null
          outputs.value = []
          historyOffset.value = 0
          hasMoreHistory.value = true
        }

        // 第三步：用原配置重建（含恢复会话）
        const payload = {
          agent_type: agent.agent_type,
          working_dir: agent.working_dir,
          name: agent.name || undefined,
          llm_group: agent.llm_group || 'default',
          tool_group: agent.tool_group || 'default',
          config_file: agent.config_file || undefined,
          worktree: agent.agent_type === 'code_agent' ? Boolean(agent.worktree) : false,
          quick_mode: Boolean(agent.quick_mode),
          restore_session: sessionFile || Boolean(agent.restore_session),
          no_interaction_mode: Boolean(agent.no_interaction_mode),
          task: agent.task || undefined,
          node_id: targetNodeId,
          proxy_node: agent.proxy_node || undefined,
          access_acl: agent.access_acl || undefined,
        }
        const createResp = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'agents'), {
          method: 'POST',
          body: JSON.stringify(payload)
        })
        const createResult = await createResp.json()
        if (!createResp.ok || !createResult.success) {
          alert(`重生失败（重建阶段）：${createResult.error?.message || createResult.detail || '未知错误'}`)
          return
        }

        showToast('Agent 无损重生成功', 'success')
        // 刷新列表
        await fetchAgentList()
        // 打开新 Agent
        if (createResult.data) {
          const newAgent = {
            ...createResult.data,
            node_id: String(createResult.data?.node_id || '').trim() || 'master',
          }
          await openAgentInPanel(newAgent)
        }
      } catch (error) {
        console.error('[REGENERATE] Failed:', error)
        alert(`重生失败: ${error.message}`)
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

            // 先删除服务端的 Agent 历史数据
            try {
              const historyKey = `agent_history_${agentId}`
              await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `data/${historyKey}`), {
                method: 'DELETE'
              })
            } catch (historyError) {
              console.warn('[HISTORY] Failed to delete server history for', agentId, ':', historyError.message)
              // 历史删除失败不影响后续 agent 删除流程
            }

            // 删除 Agent
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
              // 销毁该 Agent 对应的 Panel
              for (const panel of [...panels.value]) {
                if (panel.agentId === agentId) {
                  closePanel(panel.id)
                }
              }
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
    // 使用当前Agent的node_id，而不是编辑器会话的node_id
    const agent = agentList.value.find(a => a.agent_id === agentId)
    if (!agent) {
      console.error('[FILETREE] 找不到Agent:', agentId)
      return
    }
    if (!agent.node_id) {
      console.error('[FILETREE] Agent没有node_id:', agent)
      return
    }
    const targetNodeId = String(agent.node_id).trim()
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

// 宠物大厅：点击某只宠物，进入该 Agent 的详细视图（打开面板）
function onLobbySelectAgent(agentId) {
  const agent = agentList.value.find(a => a.agent_id === agentId)
  if (!agent) return
  openAgentInPanel(agent)
}

// 宠物大厅：获取某 Agent 的输入态（供大厅宠物输入框使用）
// 返回 { mode: 'multi'|'single'|'confirm', tip, preset, isPassword, confirmMessage, confirmDefault }
function getLobbyInputState(agentId) {
  const statusData = agentStatuses.value.get(agentId)
  const executionStatus = statusData?.execution_status || 'running'
  const confirmData = panelConfirmData.value.get(agentId)
  if (executionStatus === 'waiting_confirm' || confirmData) {
    return {
      mode: 'confirm',
      tip: confirmData?.message || '请确认 (y/n)',
      preset: '',
      isPassword: false,
      confirmMessage: confirmData?.message || '请确认',
      confirmDefault: confirmData?.defaultConfirm !== false,
    }
  }
  const request = inputRequests.value.get(agentId)
  if (request) {
    return {
      mode: request.mode === 'single' ? 'single' : 'multi',
      tip: request.tip || '',
      preset: request.preset || '',
      isPassword: !!request.is_password,
      confirmMessage: '',
      confirmDefault: true,
    }
  }
  return { mode: 'multi', tip: '', preset: '', isPassword: false, confirmMessage: '', confirmDefault: true }
}

// 宠物大厅：发送输入到指定 Agent
// mode: 'multi'|'single' 时走 input_result；'confirm' 时走 confirm_result
// 判断逻辑与 panel 的 sendFromPanel 保持一致：依据 execution_status 决定直接发送还是写入缓冲区
function sendLobbyInput(agentId, text, mode = 'multi') {
  if (!agentId) return
  if (mode === 'confirm') {
    // 空输入视为确认（与 panel 行为一致）
    const trimmed = String(text || '').trim().toLowerCase()
    const confirmed = trimmed === '' || trimmed === 'y' || trimmed === 'yes' || trimmed === '确认' || trimmed === '是'
    sendConfirmResult(confirmed, agentId)
    return
  }
  const statusData = agentStatuses.value.get(agentId)
  const executionStatus = statusData?.execution_status || 'running'
  const hasBuffered = inputBuffers.value.has(agentId) && (inputBuffers.value.get(agentId) || '').trim()
  // 单行输入或后端正在等待多行输入：直接发送
  if (mode === 'single' || executionStatus === 'waiting_multi') {
    let sendText = text
    if (hasBuffered) {
      const bufferedText = inputBuffers.value.get(agentId)
      inputBuffers.value.delete(agentId)
      sendText = text ? `${bufferedText}\n${text}` : bufferedText
    }
    sendInputDirectly(sendText, mode, agentId)
    return
  }
  // 有缓冲区内容且后端未等待输入：先发送缓冲区内容
  if (hasBuffered) {
    sendBufferedInput(agentId)
    if (text) {
      const existingText = inputBuffers.value.get(agentId) || ''
      const nextValue = existingText ? `${existingText}\n${text}` : text
      inputBuffers.value.set(agentId, nextValue)
      appendOutput({
        output_type: 'system',
        agent_name: 'system',
        text: '✓ 输入已追加到缓冲区，等待后端请求',
        lang: 'text',
      }, agentId)
    }
    return
  }
  // 后端未在等待输入：保存到缓冲区（与 panel 行为一致）
  const existingText = inputBuffers.value.get(agentId) || ''
  const nextValue = existingText ? `${existingText}\n${text}` : text
  inputBuffers.value.set(agentId, nextValue)
  appendOutput({
    output_type: 'system',
    agent_name: 'system',
    text: '✓ 输入已追加到缓冲区，等待后端请求',
    lang: 'text',
  }, agentId)
}

// 宠物大厅：获取某 Agent 的最新一条可显示输出（markdown 渲染后的 html）
function getLobbyLatestOutput(agentId) {
  const list = allOutputs.value.get(agentId)
  if (list && list.length > 0) {
    // 优先展示 Agent 的回复（STREAM）
    for (let i = list.length - 1; i >= 0; i--) {
      const item = list[i]
      if (item.output_type !== 'STREAM') continue
      if (!item.text) continue
      return { html: item.html || escapeHtml(item.text), outputType: item.output_type }
    }
    // 没有 STREAM 时，回退到最新一条有文本的消息（连接后即可见）
    for (let i = list.length - 1; i >= 0; i--) {
      const item = list[i]
      if (!item.text) continue
      return { html: item.html || escapeHtml(item.text), outputType: item.output_type }
    }
  }
  // 后台 Agent 的历史只写入 historyStorage，未同步到 allOutputs，这里回退读取
  const history = historyStorage.getHistoryForAgent(agentId)
  if (history && history.length > 0) {
    for (let i = history.length - 1; i >= 0; i--) {
      const item = history[i]
      if (!item.text) continue
      return { html: item.html || renderMessageHtml(item), outputType: item.output_type }
    }
  }
  return null
}

// 宠物大厅：输入历史翻阅（与 Panel 行为一致，返回翻阅后的文本）
const lobbyHistoryIndex = new Map() // agentId -> index（-1 表示回到最新）
const lobbyHistoryTemp = new Map() // agentId -> 翻阅前暂存的内容
function onLobbyHistoryNav(agentId, direction, currentText = '') {
  const current = currentText || ''
  let index = lobbyHistoryIndex.has(agentId) ? lobbyHistoryIndex.get(agentId) : -1
  if (direction === 'up') {
    if (index < inputHistory.value.length - 1) {
      if (index === -1) lobbyHistoryTemp.set(agentId, current)
      index++
      lobbyHistoryIndex.set(agentId, index)
      return inputHistory.value[index]
    }
    return current
  } else {
    if (index > -1) {
      index--
      lobbyHistoryIndex.set(agentId, index)
      if (index === -1) return lobbyHistoryTemp.get(agentId) || ''
      return inputHistory.value[index]
    }
    return current
  }
}

// 宠物大厅：发送完成信号（与 Panel 的 completeFromPanel 行为一致）
function onLobbyComplete(agentId) {
  if (!agentId) return
  const statusData = agentStatuses.value.get(agentId)
  const executionStatus = statusData?.execution_status || 'running'
  if (executionStatus === 'waiting_multi') {
    const message = {
      type: 'input_result',
      payload: {
        text: '__CTRL_C_PRESSED__',
        agent_id: agentId,
        display_name: chatName.value || username.value || '',
        input_mode: 'single',
      },
    }
    sendMessageToAgent(message, agentId)
  } else {
    inputBuffers.value.set(agentId, '__CTRL_C_PRESSED__')
    appendOutput({
      output_type: 'system',
      agent_name: 'system',
      text: '✅ 完成信号已保存到缓冲区，下次需要输入时自动触发',
      lang: 'text',
    }, agentId)
  }
}

// 切换当前工作的 Agent
async function switchAgent(agent) {
  // 递增切换代数，使旧的switchAgent操作失效
  const thisGeneration = ++switchGeneration.value

  // 移动端：切换 agent 后自动隐藏侧边栏（放在最前面，确保无论什么情况都执行）
  if (windowWidth.value <= 768) {
    showAgentSidebar.value = false
  }

  // 如果 Agent 已停止，不触发任何网络活动（不查询状态、不连接 WebSocket）
  if (agent.status === 'stopped') {
    // 只更新当前 agent ID，让用户可以看到该 agent 的本地历史记录
    currentAgentId.value = agent.agent_id
    // 更新 outputList 指向新 Panel 的 .messages 元素，并补绑滚动监听
    const stoppedTargetPanel = panels.value.find(p => p.agentId === agent.agent_id)
    const stoppedTargetOutputList = stoppedTargetPanel ? panelOutputLists.get(stoppedTargetPanel.id) : null
    if (stoppedTargetOutputList) {
      outputList.value = stoppedTargetOutputList
      setupHistoryScrollListener(stoppedTargetOutputList)
    }
    historyOffset.value = 0
    hasMoreHistory.value = true
    // 从本地存储加载历史消息（不涉及网络请求）
    loadHistoryMessages(false)
    return
  }

  if (agent.agent_id === currentAgentId.value) {
    const ws = sockets.value.get(agent.agent_id)
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      try {
        await connectToAgent(agent)
        // 重连后消息同步完全依赖 sync_request 机制，不再手动加载历史
      } catch (error) {
        console.error(`[AGENT] Failed to reconnect:`, error)
        // 不中断流程，让用户看到错误
      }
    } else {
      // 检查本地记录的状态，如果需要恢复UI则恢复
      const localStatus = agentStatuses.value.get(agent.agent_id)
      if (localStatus?.execution_status) {
        // 恢复各种需要用户交互的状态
        if (localStatus.execution_status === 'waiting_confirm') {
          restoreWaitingConfirmUI(agent.agent_id)
        } else if (localStatus.execution_status === 'waiting_single' || localStatus.execution_status === 'waiting_multi') {
          // 从Map中获取该Agent的输入请求
          const inputRequest = inputRequests.value.get(agent.agent_id)
          if (inputRequest) {
            inputTip.value = inputRequest.tip || ''
            inputMode.value = inputRequest.mode || 'multi'
            inputText.value = inputText.value || inputRequest.preset || ''
            pendingInputAgentId.value = agent.agent_id
            if (!isAnyModalOpen()) {
              nextTick(() => {
                if (isAnyModalOpen()) return
                const inputEl = document.querySelector(inputMode.value === 'multi' ? 'textarea' : 'input[type="text"]')
                inputEl?.focus()
              })
            }
          } else {
            console.warn('[AGENT] No input request found in Map for this agent')
          }
        }
      }
    }
    return
  }
  
  // 注意：不关闭旧Agent的WebSocket连接，保留以便切回时复用
  // 旧连接断开时，onclose会检查currentAgentId，如果不是当前Agent则不重连
  const previousAgentId = currentAgentId.value

  // 清理当前agent的终端实例（切换离开时，从历史execution_chunks重建）
  if (previousAgentId) {
    let cleanedCount = 0
    terminals.value.forEach((termInfo) => {
      if (termInfo.agentId === previousAgentId && termInfo.terminal) {
        disposeExecutionTerminal(termInfo)
        cleanedCount++
      }
    })
  }

  // 清理前一个Agent的terminalHosts引用
  if (previousAgentId) {
    let cleanedHostsCount = 0
    for (const [sessionKey, hostEl] of terminalHosts.value.entries()) {
      // sessionKey格式为 agentId:executionId
      const [agentId] = sessionKey.split(':')
      if (agentId === previousAgentId) {
        terminalHosts.value.delete(sessionKey)
        cleanedHostsCount++
      }
    }
  }

  
  // 清空当前Agent的输入状态（从Map中删除）
  const oldAgentId = currentAgentId.value
  if (oldAgentId) {
    inputRequests.value.delete(oldAgentId)
  }
  inputText.value = ''
  inputTip.value = ''
  inputMode.value = 'multi'
  
  // 更新当前 Agent ID
  currentAgentId.value = agent.agent_id

  // 更新 outputList 指向新 Panel 的 .messages 元素，并补绑滚动监听
  const targetPanel = panels.value.find(p => p.agentId === agent.agent_id)
  const targetOutputList = targetPanel ? panelOutputLists.get(targetPanel.id) : null
  if (targetOutputList) {
    outputList.value = targetOutputList
    setupHistoryScrollListener(targetOutputList)
  }
  
  // 重置历史偏移量和消息状态
  historyOffset.value = 0
  hasMoreHistory.value = true
  // 立即从本地加载该Agent 的历史消息，避免切换时页面空白
  loadHistoryMessages(false)

  // 先连接 Agent，在收到 ready 事件后再加载历史
  // 这样可以避免历史消息和 WebSocket 推送的缓存消息重复渲染
  try {
    // 切换后立即查询一次状态（即使 WebSocket 未连接）
    await fetchAgentStatus(agent)
    // 如果 Agent 已停止（已完成），不尝试连接 WebSocket
    if (agent.status === 'stopped') {
      return
    }
    // 等待连接稳定（Agent启动需要时间，有限重试）
    let stableConnection = false
    let retryCount = 0
    const maxStabilityRetries = 20 // 最大稳定性验证重试次数

    while (!stableConnection && retryCount < maxStabilityRetries) {
      // 检查是否有新的switchAgent调用
      if (switchGeneration.value !== thisGeneration) {
        return
      }

      // 只在连接不存在或已断开时才创建新连接
      const existingWs = sockets.value.get(agent.agent_id)
      if (!existingWs || existingWs.readyState !== WebSocket.OPEN) {
        // 清理已断开的旧连接
        if (existingWs && existingWs.readyState !== WebSocket.CLOSED) {
          existingWs.close()
        }
        if (existingWs) {
          sockets.value.delete(agent.agent_id)
        }
        try {
          await connectToAgent(agent)
        } catch (e) {
          console.warn(`[AGENT] connectToAgent failed: ${e.message}`)
        }

        // 检查代数是否变化
        if (switchGeneration.value !== thisGeneration) {
          return
        }
      }

      // 验证连接是否稳定
      const ws = sockets.value.get(agent.agent_id)
      if (ws && ws.readyState === WebSocket.OPEN) {
        // 等待2000ms，确保连接稳定
        await new Promise(resolve => setTimeout(resolve, 2000))

        // 检查代数是否变化
        if (switchGeneration.value !== thisGeneration) {
          return
        }

        // 再次检查连接是否仍然有效
        if (ws.readyState === WebSocket.OPEN) {
          stableConnection = true
        } else {
          retryCount++
          console.warn(`[AGENT] Connection not stable after ${retryCount} tries, retrying...`)
          await new Promise(resolve => setTimeout(resolve, 2000))
        }
      } else {
        retryCount++
        console.warn(`[AGENT] Connection not established after ${retryCount} tries, retrying...`)
        await new Promise(resolve => setTimeout(resolve, 2000))
      }
    }

    if (!stableConnection) {
      console.warn(`[AGENT] Failed to establish stable connection after ${maxStabilityRetries} retries`)
    }
    
    
    // 最终检查WebSocket是否真正连接成功
    const ws = sockets.value.get(agent.agent_id)
    if (ws && ws.readyState === WebSocket.OPEN) {
      // 连接成功后再次查询状态，确保同步
      await fetchAgentStatus(agent)
      
      // 会话恢复对话框已禁用（用户反馈莫名弹出列表选择框）
      // 原逻辑：若历史为空则检测可恢复 session 并弹出 SessionDialog
      // 如需恢复，取消下方注释即可
      /*
      const currentOutputs = allOutputs.value.get(agent.agent_id) || []
      if (currentOutputs.length === 0) {
        try {
          const { host, port } = getGatewayAddress()
          const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
          const sessionsResponse = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${agent.agent_id}/sessions`))
          const sessionsData = await sessionsResponse.json()
          if (sessionsData.success && sessionsData.data && sessionsData.data.length > 0) {
            availableSessions.value = sessionsData.data
            showSessionDialog.value = true
          } else {
          }
        } catch (error) {
          console.error('[AGENT] Failed to fetch sessions:', error)
        }
      } else {
      }
      */
    } else {
      console.warn('[AGENT] Connection verification failed, WebSocket not in OPEN state')
      // WebSocket 未连接，但已经通过 HTTP 查询了状态
    }
  } catch (error) {
    console.error('[AGENT] Failed to connect to agent:', error)
    // 连接失败，不加载历史消息，但保持当前状态
    // 用户可以看到错误并手动重试
    // 即使连接失败，状态已通过 HTTP 查询
  }
}

// 自动连接所有在线的 Agent（不切换当前选中的 Agent）
async function autoConnectToOnlineAgents() {
  // 获取所有在线的 agent（status 为 running）
  const onlineAgents = agentList.value.filter(agent => agent.status === 'running')
  
  if (onlineAgents.length === 0) {
    return
  }
  
  
  // 记录当前选中的 agent，确保不切换
  const savedCurrentAgentId = currentAgentId.value
  
  // 逐个连接在线 agent，添加延迟避免同时建立过多连接
  for (const agent of onlineAgents) {
    // 检查是否已经连接
    if (sockets.value.has(agent.agent_id)) {
      const existingWs = sockets.value.get(agent.agent_id)
      if (existingWs && existingWs.readyState === WebSocket.OPEN) {
        continue
      }
    }
    
    try {
      await connectToAgent(agent)
      // 连接间隔 500ms，避免同时建立过多连接
      await new Promise(resolve => setTimeout(resolve, 500))
    } catch (error) {
      console.warn(`[AUTO_CONNECT] Failed to connect to ${agent.name || agent.agent_id}:`, error.message)
      // 单个连接失败不影响其他连接
    }
  }
  
  // 确保当前选中的 agent 没有被改变
  if (currentAgentId.value !== savedCurrentAgentId) {
    currentAgentId.value = savedCurrentAgentId
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
      inputTip.value = payload.tip || ''
      inputMode.value = payload.mode || 'multi'
      inputText.value = payload.preset || inputText.value
      // 同步到 Panel 隔离状态
      panelInputTips.value.set(targetAgentId, payload.tip || '')
      panelInputModes.value.set(targetAgentId, payload.mode || 'multi')
      panelInputPasswords.value.set(targetAgentId, payload.is_password || false)
      if (payload.preset) {
        panelInputTexts.value.set(targetAgentId, payload.preset)
      }
      pendingInputAgentId.value = targetAgentId

      // 聚焦输入框（弹窗或宠物环形菜单打开时不抢焦点）
      const targetPanel = panels.value.find(p => p.agentId === targetAgentId)
      const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
      if (sp?.focusInput && !isAnyModalOpen() && !isPetMenuOpen()) sp.focusInput()

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
    if (sp?.focusInput && isCurrentAgent(targetAgentId) && !isAnyModalOpen() && !isPetMenuOpen()) sp.focusInput()
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
      terminalSessions.value.push({
        terminal_id: terminalId,
        node_id: nodeId,
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
      connectErrorMessage.value = errorMessage
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
  if (text.length > 1048576) text = text.slice(0, 1048576) + '...[truncated]'
  return text
}

// 聊天室消息处理
function handleChatMessage(type, payload) {
  switch (type) {
    case 'chat_register_response':
      if (payload?.success) {
        myClientId.value = payload.client_id || myClientId.value
        // 将自身加入在线用户列表（使用display_name，按user_id去重）
        if (payload.client_id) {
          const uid = payload.user_id || payload.client_id
          const existing = chatClients.value.find(c => (c.user_id || c.client_id) === uid)
          if (existing) {
            existing.client_id = payload.client_id
            existing.name = payload.name
            existing.display_name = payload.display_name || payload.name
          } else {
            chatClients.value = [...chatClients.value, { client_id: payload.client_id, user_id: uid, name: payload.name, display_name: payload.display_name || payload.name }]
          }
        }
        // 从API恢复用户已加入的房间（优先于localStorage缓存）
        restoreChatRoomsFromServer()
      } else {
        // 注册失败，清空缓存
        chatJoinedRooms.value = []
        saveChatJoinedRooms()
      }
      break
    case 'chat_get_rooms_response':
      chatRooms.value = payload?.rooms || []
      break
    case 'chat_create_room_response':
      if (payload?.success && payload.room_id) {
        chatRooms.value.push({
          room_id: payload.room_id,
          name: payload.name || '未命名聊天室',
          member_count: 1,
          created_by: auth.value.userInfo?.user_id || '',
        })
        if (!chatJoinedRooms.value.includes(payload.room_id)) { chatJoinedRooms.value = [...chatJoinedRooms.value, payload.room_id]; saveChatJoinedRooms() }
        showToast('聊天室创建成功', 'success')
      } else {
        showToast(payload?.error || '创建聊天室失败', 'error')
      }
      break
    case 'chat_join_room_response':
      if (payload?.success) {
        if (!chatAutoRejoining) showToast('已加入聊天室', 'success')
        const joinedRoomId = payload?.room_id || activeChatRoomId.value
        if (joinedRoomId && !chatJoinedRooms.value.includes(joinedRoomId)) { chatJoinedRooms.value = [...chatJoinedRooms.value, joinedRoomId]; saveChatJoinedRooms() }
        // 获取聊天室成员列表
        if (joinedRoomId) sendChatMessageToServer('chat_get_room_members', { room_id: joinedRoomId })
      } else {
        if (!chatAutoRejoining) showToast(payload?.error || '加入聊天室失败', 'error')
        // 加入失败（房间可能已删除），从缓存中移除
        const failedRoomId = payload?.room_id || activeChatRoomId.value
        if (failedRoomId && chatJoinedRooms.value.includes(failedRoomId)) {
          chatJoinedRooms.value = chatJoinedRooms.value.filter(r => r !== failedRoomId)
          saveChatJoinedRooms()
        }
      }
      // 自动重连加入完成计数
      if (chatAutoRejoining) {
        chatAutoRejoinCount--
        if (chatAutoRejoinCount <= 0) chatAutoRejoining = false
      }
      break
    case 'chat_get_clients_response':
      chatClients.value = payload?.clients || []
      break
    case 'chat_client_joined':
      if (payload?.client_id && payload?.client_id !== myClientId.value) {
        const uid = payload.user_id || payload.client_id
        const existing = chatClients.value.find(c => (c.user_id || c.client_id) === uid)
        if (existing) {
          existing.client_id = payload.client_id
          existing.name = payload.name
          existing.display_name = payload.display_name || payload.name
        } else {
          chatClients.value = [...chatClients.value, { client_id: payload.client_id, user_id: uid, name: payload.name, display_name: payload.display_name || payload.name }]
        }
      }
      break
    case 'chat_client_left':
      if (payload?.client_id && !payload?.still_online) {
        const uid = payload.user_id || payload.client_id
        chatClients.value = chatClients.value.filter(c => (c.user_id || c.client_id) !== uid)
      }
      break
    case 'chat_get_room_members_response':
      chatRoomMembers.value = payload?.members || []
      break
    case 'chat_message':
      // 聊天室广播消息（过滤自己发送的，本地已追加）
      if (payload?.client_id === myClientId.value) break
      const roomId = payload?.room_id || 'general'
      if (!chatMessages.value[roomId]) chatMessages.value[roomId] = []
      const roomMsg = {
        client_id: payload?.client_id,
        client_name: payload?.sender_display_name || payload?.sender_name || payload?.client_id,
        sender_name: payload?.sender_name || payload?.client_id,
        sender_display_name: payload?.sender_display_name || payload?.sender_name,
        content: payload?.content,
        room_id: roomId,
        timestamp: payload?.timestamp || Date.now(),
      }
      if (payload?.image_url) roomMsg.image_url = resolveImageUrl(payload.image_url)
      chatMessages.value[roomId].push(roomMsg)
      saveChatMessages()
      // 新消息提醒：非自己发送的消息触发提醒
      if (payload?.client_id !== myClientId.value) {
        playChatNotificationSound()
        if (!showChatPanel.value || activeWindow.value !== 'chat') {
          chatUnreadCount.value++
        }
        // 按房间维度记录未读数
        const roomKey = payload?.room_id || 'general'
        if (activeChatRoomId.value !== roomKey || activePrivateClientId.value) {
          chatUnreadMap.value = { ...chatUnreadMap.value, [roomKey]: (chatUnreadMap.value[roomKey] || 0) + 1 }
        }
      }
      break
    case 'chat_private_message':
      // 私聊消息（过滤自己发送的，本地已追加）
      if (payload?.message?.sender_id === myClientId.value) break
      const privPeerId = payload?.message?.sender_user_id || payload?.sender_user_id || payload?.message?.sender_id
      const privMsgKey = `private_${privPeerId}`
      if (!chatMessages.value[privMsgKey]) chatMessages.value[privMsgKey] = []
      const privMsg = {
        client_id: payload?.message?.sender_id,
        client_name: payload?.message?.sender_display_name || payload?.message?.sender_name || payload?.message?.sender_id,
        sender_name: payload?.message?.sender_name || payload?.message?.sender_id,
        sender_display_name: payload?.message?.sender_display_name || payload?.message?.sender_name,
        content: payload?.message?.content,
        private: true,
        timestamp: payload?.message?.timestamp || Date.now(),
      }
      if (payload?.message?.image_url) privMsg.image_url = resolveImageUrl(payload.message.image_url)
      chatMessages.value[privMsgKey].push(privMsg)
      saveChatMessages()
      // 新消息提醒：非自己发送的消息触发提醒
      if (payload?.message?.sender_id !== myClientId.value) {
        playChatNotificationSound()
        if (!showChatPanel.value || activeWindow.value !== 'chat') {
          chatUnreadCount.value++
        }
        // 按私聊维度记录未读数
        const privUnreadKey = `private_${privPeerId}`
        if (activePrivateClientId.value !== privPeerId) {
          chatUnreadMap.value = { ...chatUnreadMap.value, [privUnreadKey]: (chatUnreadMap.value[privUnreadKey] || 0) + 1 }
        }
      }
      break
    case 'chat_get_private_history_response':
      if (payload?.messages) {
        const histKey = `private_${payload?.other_id || activePrivateClientId.value}`
        chatMessages.value[histKey] = payload.messages.map(msg => {
          const m = {
            client_id: msg.sender_id,
            client_name: msg.sender_name || msg.sender_id,
            sender_name: msg.sender_name || msg.sender_id,
            content: msg.content,
            private: true,
            timestamp: msg.timestamp || Date.now(),
          }
          if (msg.image_url) m.image_url = resolveImageUrl(msg.image_url)
          return m
        })
        saveChatMessages()
      }
      break
    case 'chat_leave_room_response':
      if (payload?.success) {
        showToast('已退出聊天室', 'success')
        const leftRoomId = payload?.room_id || activeChatRoomId.value
        chatJoinedRooms.value = chatJoinedRooms.value.filter(r => r !== leftRoomId)
        saveChatJoinedRooms()
        delete chatMessages.value[leftRoomId]
        if (activeChatRoomId.value === leftRoomId) {
          activeChatRoomId.value = ''
        }
        saveChatMessages()
      } else {
        showToast(payload?.error || '退出聊天室失败', 'error')
      }
      break
    case 'chat_delete_room_response':
      if (payload?.success) {
        showToast('聊天室已删除', 'success')
        const deletedRoomId = payload?.room_id || activeChatRoomId.value
        chatJoinedRooms.value = chatJoinedRooms.value.filter(r => r !== deletedRoomId)
        saveChatJoinedRooms()
        delete chatMessages.value[deletedRoomId]
        chatRooms.value = chatRooms.value.filter(r => r.room_id !== deletedRoomId)
        if (activeChatRoomId.value === deletedRoomId) {
          activeChatRoomId.value = ''
        }
        saveChatMessages()
      } else {
        showToast(payload?.error || '删除聊天室失败', 'error')
      }
      break
    case 'chat_room_created':
      // 其他用户创建的新房间通知
      if (payload?.room_id) {
        chatRooms.value = [...chatRooms.value, {
          room_id: payload.room_id,
          name: payload.name || '未命名聊天室',
          member_count: payload.member_count || 1,
          created_by: payload.created_by || '',
        }]
      }
      break
    case 'chat_rename_room_response':
      if (payload?.success) {
        showToast('聊天室已重命名', 'success')
      } else {
        showToast(payload?.error || '重命名聊天室失败', 'error')
      }
      break
    case 'chat_room_renamed':
      // 广播通知：更新本地房间名
      if (payload?.room_id && payload?.new_name) {
        chatRooms.value = chatRooms.value.map(r =>
          r.room_id === payload.room_id ? { ...r, name: payload.new_name } : r
        )
      }
      break
    case 'chat_room_deleted':
      const removedRoomId = payload?.room_id
      if (removedRoomId) {
        chatJoinedRooms.value = chatJoinedRooms.value.filter(r => r !== removedRoomId)
        saveChatJoinedRooms()
        delete chatMessages.value[removedRoomId]
        chatRooms.value = chatRooms.value.filter(r => r.room_id !== removedRoomId)
        if (activeChatRoomId.value === removedRoomId) {
          activeChatRoomId.value = ''
        }
        saveChatMessages()
        showToast('聊天室已被创建者删除', 'warning')
      }
      break
    case 'chat_error':
      showToast(payload?.error || '聊天室操作失败', 'error')
      break
  }
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
          terminal_content: msg.terminal_content || '',
          execution_chunks: msg.execution_chunks || [],
          seq: msg.seq,
        })
      } catch (e) {
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
            terminal_content: terminalContent,
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
function navigateHistory(direction, agentId = null) {
  // direction: 'up' 或 'down'
  // agentId: 指定 Panel 的 agentId，传入时操作 Panel 隔离的输入

  const isPanel = agentId !== null
  const getInput = () => isPanel ? (panelInputTexts.value.get(agentId) || '') : inputText.value
  const setInput = (val) => {
    if (isPanel) {
      panelInputTexts.value.set(agentId, val)
    } else {
      inputText.value = val
    }
  }
  const getTemp = () => isPanel ? (panelTempInputs.value.get(agentId) || '') : currentTempInput.value
  const setTemp = (val) => {
    if (isPanel) {
      panelTempInputs.value.set(agentId, val)
    } else {
      currentTempInput.value = val
    }
  }

  if (direction === 'up') {
    // 向上翻阅：加载更早的历史记录
    if (historyIndex.value < inputHistory.value.length - 1) {
      // 第一次翻阅时，保存当前正在编辑的内容
      if (historyIndex.value === -1) {
        setTemp(getInput())
      }
      historyIndex.value++
      setInput(inputHistory.value[historyIndex.value])
    }
  } else if (direction === 'down') {
    // 向下翻阅：加载更新的历史记录
    if (historyIndex.value > -1) {
      historyIndex.value--
      if (historyIndex.value === -1) {
        // 回到最新状态，恢复临时编辑的内容
        setInput(getTemp())
      } else {
        setInput(inputHistory.value[historyIndex.value])
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
  if (targetAgentId) {
    const ws = sockets.value.get(targetAgentId)
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
    } else {
      console.warn(`[SEND] No open WebSocket for agent ${targetAgentId}`)
    }
    // 清除 Panel 内嵌确认数据
    panelConfirmData.value.delete(targetAgentId)
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

function sendInterrupt() {
  const message = {
    type: 'interrupt',
    payload: {},
  }
  sendMessageToAgent(message)
}

function sendManualInterruptToPanel(panel) {
  if (!panel || !panel.agentId) {
    console.warn('[SEND] Invalid panel for manual interrupt')
    return
  }
  const message = {
    type: 'manual_interrupt',
    payload: {},
  }
  sendMessageToAgentById(panel.agentId, message)
}

function confirmClearHistory() {
  // 先关闭设置弹窗
  showSettingsModal.value = false
  
  showConfirm(
    '确定要清除所有历史记录吗？此操作不可撤销。',
    () => {
      if (historyStorage.clearHistory()) {
        // 清除当前 Agent 的消息
        allOutputs.value.set(currentAgentId.value, [])
        // 重置历史加载状态
        historyOffset.value = 0
        hasMoreHistory.value = true
        // seq 由 getAgentLastSeq() 从历史记录获取，清除历史后自动返回 -1
      } else {
        console.error('[HISTORY] Failed to clear history')
      }
      // 无论清除是否成功，都关闭设置弹窗
      showSettingsModal.value = false
    }
  )
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
      // 如果 terminal 实例已存在（面板 detach 切换导致组件重建），重新打开
      if (session.terminal) {
        initIndependentTerminal(terminalId, el)
      }
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
  
  // 如果 terminal 实例已存在（面板 detach 切换导致组件重建），先 dispose 旧实例再创建新的
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
  
  // 自动打开终端面板
  showTerminalPanel.value = true
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

  // 自动打开终端面板
  showTerminalPanel.value = true
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
  
  // 自动打开终端面板
  showTerminalPanel.value = true
}

function closeTerminal(terminalId) {

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
// SessionPanel 浮动面板
const SESSION_PANEL_MIN_WIDTH = 400
const SESSION_PANEL_MIN_HEIGHT = 300
const SESSION_PANEL_STORAGE_KEY_PREFIX = 'jarvis_session_panel_rect_'
const sessionResizeDirections = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

function getDefaultSessionPanelRect(panelId) {
  // 按 panelId 偏移位置，避免多个浮动面板重叠
  const index = Array.from(sessionDetachedPanels.value).indexOf(panelId)
  const offset = index * 40
  return {
    top: 80 + offset,
    left: Math.max(window.innerWidth - 824 - offset, 16),
    width: 600,
    height: 500,
  }
}

function loadSessionPanelRect(panelId) {
  const defaultRect = getDefaultSessionPanelRect(panelId)
  const savedValue = localStorage.getItem(SESSION_PANEL_STORAGE_KEY_PREFIX + panelId)
  if (!savedValue) {
    return defaultRect
  }

  try {
    const parsedValue = JSON.parse(savedValue)
    if (
      typeof parsedValue.top !== 'number' ||
      typeof parsedValue.left !== 'number' ||
      typeof parsedValue.width !== 'number' ||
      typeof parsedValue.height !== 'number'
    ) {
      return defaultRect
    }

    return parsedValue
  } catch {
    return defaultRect
  }
}

function saveSessionPanelRect(panelId) {
  const rect = sessionPanelRects.value[panelId]
  if (rect) {
    localStorage.setItem(SESSION_PANEL_STORAGE_KEY_PREFIX + panelId, JSON.stringify(rect))
  }
}

const sessionPanelRects = ref({})  // panelId -> rect
const sessionPanelInteraction = ref({
  active: false,
  mode: null,
  direction: null,
  panelId: null,
  startX: 0,
  startY: 0,
  startTop: 0,
  startLeft: 0,
  startWidth: 0,
  startHeight: 0,
})

function getSessionPanelStyle(panelId) {
  const rect = sessionPanelRects.value[panelId]
  if (!rect) return {}
  return {
    top: `${rect.top}px`,
    left: `${rect.left}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    zIndex: activeWindow.value === 'session' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
  }
}

function getSessionPanelBounds() {
  const HEADER_HEIGHT = 32
  const MIN_VISIBLE_WIDTH = 100
  return {
    minTop: 0,
    minLeft: 0,
    maxLeft: window.innerWidth - MIN_VISIBLE_WIDTH,
    maxTop: window.innerHeight - HEADER_HEIGHT,
  }
}

function ensureSessionPanelInViewport(panelId) {
  const rect = sessionPanelRects.value[panelId]
  if (!rect) return
  const HEADER_HEIGHT = 32
  const MIN_VISIBLE_WIDTH = 100
  const maxWidth = Math.max(window.innerWidth, SESSION_PANEL_MIN_WIDTH)
  const maxHeight = Math.max(window.innerHeight, SESSION_PANEL_MIN_HEIGHT)

  rect.width = clamp(rect.width, SESSION_PANEL_MIN_WIDTH, maxWidth)
  rect.height = clamp(rect.height, SESSION_PANEL_MIN_HEIGHT, maxHeight)

  rect.left = clamp(
    rect.left,
    0,
    window.innerWidth - MIN_VISIBLE_WIDTH
  )
  rect.top = clamp(
    rect.top,
    0,
    window.innerHeight - HEADER_HEIGHT
  )
}

function startSessionPanelMove(event, panelId) {
  if (windowWidth.value <= 768) return
  if (event.target.closest('.session-header-actions')) return

  focusWindow('session')

  const rect = sessionPanelRects.value[panelId]
  if (!rect) return

  sessionPanelInteraction.value = {
    active: false,
    mode: 'move',
    direction: null,
    panelId,
    startX: event.clientX,
    startY: event.clientY,
    startTop: rect.top,
    startLeft: rect.left,
    startWidth: rect.width,
    startHeight: rect.height,
  }

  document.addEventListener('mousemove', onSessionPanelPointerMove)
  document.addEventListener('mouseup', stopSessionPanelInteraction)
}

function startSessionPanelResize(event, direction, panelId) {
  if (windowWidth.value <= 768) return

  const rect = sessionPanelRects.value[panelId]
  if (!rect) return

  sessionPanelInteraction.value = {
    active: true,
    mode: 'resize',
    direction,
    panelId,
    startX: event.clientX,
    startY: event.clientY,
    startTop: rect.top,
    startLeft: rect.left,
    startWidth: rect.width,
    startHeight: rect.height,
  }

  document.addEventListener('mousemove', onSessionPanelPointerMove)
  document.addEventListener('mouseup', stopSessionPanelInteraction)
  event.preventDefault()
  event.stopPropagation()
}

function onSessionPanelPointerMove(event) {
  const interaction = sessionPanelInteraction.value
  const panelId = interaction.panelId
  const rect = sessionPanelRects.value[panelId]
  if (!rect) return

  const deltaX = event.clientX - interaction.startX
  const deltaY = event.clientY - interaction.startY

  if (interaction.mode === 'move' && !interaction.active) {
    const dragDistance = Math.hypot(deltaX, deltaY)
    if (dragDistance < PANEL_DRAG_ACTIVATION_DISTANCE) {
      return
    }

    sessionPanelInteraction.value = {
      ...interaction,
      active: true,
    }
    event.preventDefault()
  }

  if (!sessionPanelInteraction.value.active) return

  if (sessionPanelInteraction.value.mode === 'move') {
    const bounds = getSessionPanelBounds()
    rect.left = clamp(interaction.startLeft + deltaX, bounds.minLeft, bounds.maxLeft)
    rect.top = clamp(interaction.startTop + deltaY, bounds.minTop, bounds.maxTop)
    return
  }

  const direction = sessionPanelInteraction.value.direction || ''
  const startLeft = sessionPanelInteraction.value.startLeft
  const startTop = sessionPanelInteraction.value.startTop
  const startWidth = sessionPanelInteraction.value.startWidth
  const startHeight = sessionPanelInteraction.value.startHeight

  let nextLeft = startLeft
  let nextTop = startTop
  let nextWidth = startWidth
  let nextHeight = startHeight

  if (direction.includes('e')) {
    nextWidth = clamp(startWidth + deltaX, SESSION_PANEL_MIN_WIDTH, Math.max(window.innerWidth - startLeft, SESSION_PANEL_MIN_WIDTH))
  }

  if (direction.includes('s')) {
    nextHeight = clamp(startHeight + deltaY, SESSION_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - startTop, SESSION_PANEL_MIN_HEIGHT))
  }

  if (direction.includes('w')) {
    const desiredLeft = clamp(startLeft + deltaX, 0, startLeft + startWidth - SESSION_PANEL_MIN_WIDTH)
    nextLeft = desiredLeft
    nextWidth = startWidth - (desiredLeft - startLeft)
  }

  if (direction.includes('n')) {
    const desiredTop = clamp(startTop + deltaY, 0, startTop + startHeight - SESSION_PANEL_MIN_HEIGHT)
    nextTop = desiredTop
    nextHeight = startHeight - (desiredTop - startTop)
  }

  if (nextLeft + nextWidth > window.innerWidth) {
    nextWidth = Math.max(SESSION_PANEL_MIN_WIDTH, window.innerWidth - nextLeft)
  }

  if (nextTop + nextHeight > window.innerHeight) {
    nextHeight = Math.max(SESSION_PANEL_MIN_HEIGHT, window.innerHeight - nextTop)
  }

  rect.left = clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0))
  rect.top = clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0))
  rect.width = clamp(nextWidth, SESSION_PANEL_MIN_WIDTH, Math.max(window.innerWidth - rect.left, SESSION_PANEL_MIN_WIDTH))
  rect.height = clamp(nextHeight, SESSION_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - rect.top, SESSION_PANEL_MIN_HEIGHT))
}

function stopSessionPanelInteraction() {
  const panelId = sessionPanelInteraction.value.panelId
  sessionPanelInteraction.value = {
    active: false,
    mode: null,
    direction: null,
    panelId: null,
    startX: 0,
    startY: 0,
    startTop: 0,
    startLeft: 0,
    startWidth: 0,
    startHeight: 0,
  }

  document.removeEventListener('mousemove', onSessionPanelPointerMove)
  document.removeEventListener('mouseup', stopSessionPanelInteraction)
  if (panelId) {
    saveSessionPanelRect(panelId)
  }
}

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

// 聊天室面板
const CHAT_PANEL_MIN_WIDTH = 400
const CHAT_PANEL_MIN_HEIGHT = 300
const CHAT_PANEL_STORAGE_KEY = 'jarvis_chat_panel_rect'
const chatResizeDirections = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

function getDefaultChatPanelRect() {
  return {
    top: 88,
    left: Math.max(window.innerWidth - 824, 16),
    width: 800,
    height: 500,
  }
}

function loadChatPanelRect() {
  const defaultChatPanelRect = getDefaultChatPanelRect()
  const savedValue = localStorage.getItem(CHAT_PANEL_STORAGE_KEY)
  if (!savedValue) {
    return defaultChatPanelRect
  }

  try {
    const parsedValue = JSON.parse(savedValue)
    if (
      typeof parsedValue.top !== 'number' ||
      typeof parsedValue.left !== 'number' ||
      typeof parsedValue.width !== 'number' ||
      typeof parsedValue.height !== 'number'
    ) {
      return defaultChatPanelRect
    }

    return parsedValue
  } catch {
    return defaultChatPanelRect
  }
}

function saveChatPanelRect() {
  localStorage.setItem(CHAT_PANEL_STORAGE_KEY, JSON.stringify(chatPanelRect.value))
}

const chatPanelRect = ref(loadChatPanelRect())
const chatPanelCollapsed = ref(false)
const chatPanelInteraction = ref({
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

const chatPanelStyle = computed(() => {
  // 移动端全屏显示
  if (windowWidth.value <= 768) {
    return {
      top: '0',
      left: '0',
      width: '100vw',
      height: 'var(--app-height, 100vh)',
      zIndex: activeWindow.value === 'chat' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
    }
  }
  // 折叠状态：只显示窄条
  if (chatPanelCollapsed.value) {
    return {
      top: `${chatPanelRect.value.top}px`,
      left: `${chatPanelRect.value.left}px`,
      width: '40px',
      height: `${chatPanelRect.value.height}px`,
      zIndex: activeWindow.value === 'chat' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
    }
  }
  return {
    top: `${chatPanelRect.value.top}px`,
    left: `${chatPanelRect.value.left}px`,
    width: `${chatPanelRect.value.width}px`,
    height: `${chatPanelRect.value.height}px`,
    zIndex: activeWindow.value === 'chat' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
  }
})

// 聊天室数据状态
const CHAT_MESSAGES_STORAGE_KEY = 'jarvis_chat_messages'

function loadChatMessages() {
  try {
    const saved = localStorage.getItem(CHAT_MESSAGES_STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      // 兼容旧格式（数组）和新格式（对象）
      if (Array.isArray(parsed)) {
        const map = {}
        parsed.forEach(msg => {
          const key = msg.room_id || 'private'
          if (!map[key]) map[key] = []
          map[key].push(msg)
        })
        return map
      }
      return parsed
    }
    return {}
  } catch {
    return {}
  }
}

function saveChatMessages() {
  try {
    const toSave = {}
    for (const [roomId, msgs] of Object.entries(chatMessages.value)) {
      toSave[roomId] = msgs.slice(-200)
    }
    localStorage.setItem(CHAT_MESSAGES_STORAGE_KEY, JSON.stringify(toSave))
  } catch (e) {
    console.warn('[CHAT] Failed to save messages:', e)
  }
}

const chatRooms = ref([])
const chatMessages = ref(loadChatMessages())
const chatClients = ref([])
const chatRoomMembers = ref([])
const myClientId = ref('')
const activeChatRoomId = ref('')
const activePrivateClientId = ref('')
const chatUnreadCount = ref(0)
const chatName = computed(() => auth.value.userInfo?.display_name || username.value)
const myUserId = computed(() => auth.value.userInfo?.user_id || myClientId.value)
const chatSidebarWidth = ref(parseInt(localStorage.getItem('jarvis_chat_sidebar_width') || '160'))
const chatUnreadMap = ref({})
const CHAT_JOINED_ROOMS_KEY = 'jarvis_chat_joined_rooms'
const chatJoinedRooms = ref(JSON.parse(localStorage.getItem(CHAT_JOINED_ROOMS_KEY) || '[]'))

function saveChatJoinedRooms() {
  localStorage.setItem(CHAT_JOINED_ROOMS_KEY, JSON.stringify(chatJoinedRooms.value))
}

async function restoreChatRoomsFromServer() {
  // 从API获取用户已加入的房间，用于登录后恢复
  try {
    const resp = await fetch('/api/chat/user-rooms', { headers: { 'Authorization': `Bearer ${auth.value.token}` } })
    const data = await resp.json()
    if (data.success && data.rooms) {
      const serverRoomIds = data.rooms.map(r => r.room_id)
      // 合并服务端房间与本地缓存
      const merged = [...new Set([...serverRoomIds, ...chatJoinedRooms.value.filter(rid => rid)])]
      chatJoinedRooms.value = merged
      saveChatJoinedRooms()
      // 自动重新加入所有房间
      if (merged.length > 0) {
        chatAutoRejoining = true
        chatAutoRejoinCount = merged.length
        merged.forEach(rid => {
          sendChatMessageToServer('chat_join_room', { room_id: rid, client_id: myClientId.value })
        })
      }
    }
  } catch (e) {
    // API失败时回退到localStorage缓存
    const savedRooms = chatJoinedRooms.value.filter(rid => rid)
    if (savedRooms.length > 0) {
      chatAutoRejoining = true
      chatAutoRejoinCount = savedRooms.length
      savedRooms.forEach(rid => {
        sendChatMessageToServer('chat_join_room', { room_id: rid, client_id: myClientId.value })
      })
    }
  }
}

let chatAutoRejoining = false
let chatAutoRejoinCount = 0

function startChatSidebarResize(event) {
  const startX = event.clientX
  const startWidth = chatSidebarWidth.value
  const onMove = (e) => {
    const delta = e.clientX - startX
    chatSidebarWidth.value = Math.max(120, Math.min(400, startWidth + delta))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    localStorage.setItem('jarvis_chat_sidebar_width', String(chatSidebarWidth.value))
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function getOrCreateClientId() {
  let clientId = localStorage.getItem('jarvis_chat_client_id')
  if (!clientId) {
    clientId = 'client_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
    localStorage.setItem('jarvis_chat_client_id', clientId)
  }
  return clientId
}

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

// 聊天室面板交互
function getChatPanelBounds() {
  const HEADER_HEIGHT = 32 // 标题栏高度
  const MIN_VISIBLE_WIDTH = 100 // 至少保留100px面板宽度可见
  return {
    minTop: 0,
    minLeft: 0,
    maxLeft: window.innerWidth - MIN_VISIBLE_WIDTH,
    maxTop: window.innerHeight - HEADER_HEIGHT,
    maxWidth: window.innerWidth,
    maxHeight: window.innerHeight,
  }
}

function ensureChatPanelInViewport() {
  const HEADER_HEIGHT = 32
  const MIN_VISIBLE_WIDTH = 100
  const maxWidth = Math.max(window.innerWidth, CHAT_PANEL_MIN_WIDTH)
  const maxHeight = Math.max(window.innerHeight, CHAT_PANEL_MIN_HEIGHT)

  chatPanelRect.value.width = clamp(chatPanelRect.value.width, CHAT_PANEL_MIN_WIDTH, maxWidth)
  chatPanelRect.value.height = clamp(chatPanelRect.value.height, CHAT_PANEL_MIN_HEIGHT, maxHeight)

  chatPanelRect.value.left = clamp(
    chatPanelRect.value.left,
    0,
    window.innerWidth - MIN_VISIBLE_WIDTH
  )
  chatPanelRect.value.top = clamp(
    chatPanelRect.value.top,
    0,
    window.innerHeight - HEADER_HEIGHT
  )
}

function startChatPanelMove(event) {
  if (windowWidth.value <= 768) return
  if (event.target.closest('.chat-panel-actions')) return

  focusWindow('chat')

  chatPanelInteraction.value = {
    active: false,
    mode: 'move',
    direction: null,
    startX: event.clientX,
    startY: event.clientY,
    startTop: chatPanelRect.value.top,
    startLeft: chatPanelRect.value.left,
    startWidth: chatPanelRect.value.width,
    startHeight: chatPanelRect.value.height,
  }

  document.addEventListener('mousemove', onChatPanelPointerMove)
  document.addEventListener('mouseup', stopChatPanelInteraction)
}

function startChatPanelResize(event, direction) {
  if (windowWidth.value <= 768) return

  chatPanelInteraction.value = {
    active: true,
    mode: 'resize',
    direction,
    startX: event.clientX,
    startY: event.clientY,
    startTop: chatPanelRect.value.top,
    startLeft: chatPanelRect.value.left,
    startWidth: chatPanelRect.value.width,
    startHeight: chatPanelRect.value.height,
  }

  document.addEventListener('mousemove', onChatPanelPointerMove)
  document.addEventListener('mouseup', stopChatPanelInteraction)
  event.preventDefault()
  event.stopPropagation()
}

function onChatPanelPointerMove(event) {
  const deltaX = event.clientX - chatPanelInteraction.value.startX
  const deltaY = event.clientY - chatPanelInteraction.value.startY

  if (chatPanelInteraction.value.mode === 'move' && !chatPanelInteraction.value.active) {
    const dragDistance = Math.hypot(deltaX, deltaY)
    if (dragDistance < PANEL_DRAG_ACTIVATION_DISTANCE) {
      return
    }

    chatPanelInteraction.value = {
      ...chatPanelInteraction.value,
      active: true,
    }
    event.preventDefault()
  }

  if (!chatPanelInteraction.value.active) return

  if (chatPanelInteraction.value.mode === 'move') {
    const bounds = getChatPanelBounds()
    chatPanelRect.value.left = clamp(chatPanelInteraction.value.startLeft + deltaX, bounds.minLeft, bounds.maxLeft)
    chatPanelRect.value.top = clamp(chatPanelInteraction.value.startTop + deltaY, bounds.minTop, bounds.maxTop)
    return
  }

  const direction = chatPanelInteraction.value.direction || ''
  const startLeft = chatPanelInteraction.value.startLeft
  const startTop = chatPanelInteraction.value.startTop
  const startWidth = chatPanelInteraction.value.startWidth
  const startHeight = chatPanelInteraction.value.startHeight

  let nextLeft = startLeft
  let nextTop = startTop
  let nextWidth = startWidth
  let nextHeight = startHeight

  if (direction.includes('e')) {
    nextWidth = clamp(startWidth + deltaX, CHAT_PANEL_MIN_WIDTH, Math.max(window.innerWidth - startLeft, CHAT_PANEL_MIN_WIDTH))
  }

  if (direction.includes('s')) {
    nextHeight = clamp(startHeight + deltaY, CHAT_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - startTop, CHAT_PANEL_MIN_HEIGHT))
  }

  if (direction.includes('w')) {
    const desiredLeft = clamp(startLeft + deltaX, 0, startLeft + startWidth - CHAT_PANEL_MIN_WIDTH)
    nextLeft = desiredLeft
    nextWidth = startWidth - (desiredLeft - startLeft)
  }

  if (direction.includes('n')) {
    const desiredTop = clamp(startTop + deltaY, 0, startTop + startHeight - CHAT_PANEL_MIN_HEIGHT)
    nextTop = desiredTop
    nextHeight = startHeight - (desiredTop - startTop)
  }

  if (nextLeft + nextWidth > window.innerWidth) {
    nextWidth = Math.max(CHAT_PANEL_MIN_WIDTH, window.innerWidth - nextLeft)
  }

  if (nextTop + nextHeight > window.innerHeight) {
    nextHeight = Math.max(CHAT_PANEL_MIN_HEIGHT, window.innerHeight - nextTop)
  }

  chatPanelRect.value.left = clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0))
  chatPanelRect.value.top = clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0))
  chatPanelRect.value.width = clamp(nextWidth, CHAT_PANEL_MIN_WIDTH, Math.max(window.innerWidth - chatPanelRect.value.left, CHAT_PANEL_MIN_WIDTH))
  chatPanelRect.value.height = clamp(nextHeight, CHAT_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - chatPanelRect.value.top, CHAT_PANEL_MIN_HEIGHT))
}

function stopChatPanelInteraction() {
  chatPanelInteraction.value = {
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

  document.removeEventListener('mousemove', onChatPanelPointerMove)
  document.removeEventListener('mouseup', stopChatPanelInteraction)
  saveChatPanelRect()
}

// 聊天室功能方法
function toggleChatPanel() {
  showChatPanel.value = !showChatPanel.value
  if (showChatPanel.value) {
    focusWindow('chat')
    chatUnreadCount.value = 0
    // 首次打开时注册客户端并获取聊天室列表
    if (!myClientId.value) {
      myClientId.value = getOrCreateClientId()
      sendChatMessageToServer('chat_register', { client_id: myClientId.value, name: username.value })
    }
    sendChatMessageToServer('chat_get_rooms', {})
    sendChatMessageToServer('chat_get_clients', {})
  }
}

// username变更时同步更新聊天室注册名
watch(username, (val) => {
  if (myClientId.value && val) {
    sendChatMessageToServer('chat_register', { client_id: myClientId.value, name: val })
    sendChatMessageToServer('chat_get_clients', {})
    if (activeChatRoomId.value) {
      sendChatMessageToServer('chat_get_room_members', { room_id: activeChatRoomId.value })
    }
  }
})

function sendChatMessageToServer(type, payload) {
  if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
    console.warn('[CHAT] No socket connection')
    return
  }
  socket.value.send(JSON.stringify({ type, payload }))
}

function createChatRoom(roomName) {
  if (!roomName || !roomName.trim()) return
  sendChatMessageToServer('chat_create_room', { name: roomName.trim(), client_id: myClientId.value })
}

function joinChatRoom(roomId) {
  activeChatRoomId.value = roomId
  // 切换到群聊时清空私聊选中
  activePrivateClientId.value = ''
  // 清除房间未读计数
  const { [roomId]: _, ...rest } = chatUnreadMap.value
  chatUnreadMap.value = rest
  // 已加入的房间仅切换查看，未加入的才发送join请求
  if (!chatJoinedRooms.value.includes(roomId)) {
    sendChatMessageToServer('chat_join_room', { room_id: roomId, client_id: myClientId.value })
  } else {
    sendChatMessageToServer('chat_get_room_members', { room_id: roomId })
  }
}

function leaveChatRoom(roomId) {
  sendChatMessageToServer('chat_leave_room', { room_id: roomId, client_id: myClientId.value })
}

function deleteChatRoom(roomId) {
  showConfirm('确定要删除此聊天室吗？此操作不可撤销。', () => {
    sendChatMessageToServer('chat_delete_room', { room_id: roomId, client_id: myClientId.value })
  })
}

function renameChatRoom(roomId, newName) {
  sendChatMessageToServer('chat_rename_room', { room_id: roomId, client_id: myClientId.value, new_name: newName })
}

function clearChatMessages(scope) {
  if (scope === 'all') {
    showConfirm('确定要清空全部聊天记录吗？此操作不可撤销。', () => {
      chatMessages.value = {}
      saveChatMessages()
    })
  } else if (scope === 'current') {
    const key = activePrivateClientId.value
      ? `private_${activePrivateClientId.value}`
      : activeChatRoomId.value
    if (key) {
      showConfirm('确定要清空当前聊天记录吗？此操作不可撤销。', () => {
        const { [key]: _, ...rest } = chatMessages.value
        chatMessages.value = rest
        saveChatMessages()
      })
    }
  }
}

// 将相对路径的图片 URL 转换为完整 URL（uploads 挂载在后端网关）
function resolveImageUrl(url) {
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  if (url.startsWith('/uploads/')) {
    const { host, port } = getGatewayAddress()
    const protocol = window.location.protocol === 'https:' ? 'https' : 'http'
    return `${protocol}://${host}:${port}${url}`
  }
  return url
}

function sendChatMessage(content, imageUrl) {
  if ((!content || !content.trim()) && !imageUrl) return
  const trimmed = (content || '').trim()
  if (activePrivateClientId.value) {
    // 私聊模式
    const payload = {
      sender_id: myClientId.value,
      receiver_id: activePrivateClientId.value,
      content: trimmed,
    }
    if (imageUrl) payload.image_url = resolveImageUrl(imageUrl)
    sendChatMessageToServer('chat_send_private', payload)
    // 本地追加自己的消息
    const selfMsgKey = `private_${activePrivateClientId.value}`
    if (!chatMessages.value[selfMsgKey]) chatMessages.value[selfMsgKey] = []
    const selfMsg = {
      client_id: myClientId.value,
      client_name: chatName.value || myClientId.value,
      sender_name: username.value || myClientId.value,
      sender_display_name: chatName.value || username.value,
      content: trimmed,
      private: true,
      timestamp: Date.now(),
    }
    if (imageUrl) selfMsg.image_url = resolveImageUrl(imageUrl)
    chatMessages.value[selfMsgKey].push(selfMsg)
    saveChatMessages()
  } else if (activeChatRoomId.value) {
    // 聊天室模式
    const payload = {
      room_id: activeChatRoomId.value,
      client_id: myClientId.value,
      content: trimmed,
    }
    if (imageUrl) payload.image_url = resolveImageUrl(imageUrl)
    sendChatMessageToServer('chat_send_message', payload)
    // 本地追加自己的消息
    if (!chatMessages.value[activeChatRoomId.value]) chatMessages.value[activeChatRoomId.value] = []
    const selfMsg = {
      client_id: myClientId.value,
      client_name: chatName.value || myClientId.value,
      sender_name: username.value || myClientId.value,
      sender_display_name: chatName.value || username.value,
      content: trimmed,
      room_id: activeChatRoomId.value,
      timestamp: Date.now(),
    }
    if (imageUrl) selfMsg.image_url = resolveImageUrl(imageUrl)
    chatMessages.value[activeChatRoomId.value].push(selfMsg)
    saveChatMessages()
  } else {
    showToast('请先加入聊天室或选择私聊对象', 'warning')
  }
}

function selectPrivateClient(clientId) {
  if (activePrivateClientId.value === clientId) {
    activePrivateClientId.value = ''
  } else {
    activePrivateClientId.value = clientId
    // 不清空activeChatRoomId，保持群聊加入状态
    // 清除私聊未读计数
    const privKey = `private_${clientId}`
    const { [privKey]: _, ...rest } = chatUnreadMap.value
    chatUnreadMap.value = rest
    // 获取私聊历史
    sendChatMessageToServer('chat_get_private_history', {
      client_id: myUserId.value,
      other_id: clientId,
    })
  }
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

// 全局键盘事件处理
function handleGlobalKeydown(event) {
  const isModifierPressed = event.ctrlKey || event.metaKey

  // Ctrl/Cmd + P 打开/关闭命令面板（登录界面不响应）
  if (isModifierPressed && event.code === 'KeyP') {
    if (showConnectModal.value) return
    event.preventDefault()
    if (!showCommandPalette.value) {
      // 打开前记录焦点所在区域，供"关闭/分离当前焦点面板"使用
      commandPaletteFocusKey = getFocusedZoneKey()
      // 快捷键打开时清空预输入，避免沿用上次宠物菜单带入的查询
      commandPaletteInitialQuery.value = ''
    }
    showCommandPalette.value = !showCommandPalette.value
    return
  }

  // Ctrl/Cmd + L 打开命令面板并直接展示 Agent 列表（预输入 a>）
  if (isModifierPressed && event.code === 'KeyL') {
    if (showConnectModal.value) return
    event.preventDefault()
    commandPaletteFocusKey = getFocusedZoneKey()
    commandPaletteInitialQuery.value = 'a>'
    showCommandPalette.value = true
    return
  }

  // Ctrl/Cmd + Alt + 方向键：依据当前布局，向对应方向切换到最近的焦点区域（Session Panel / 集成终端 / 编辑器）
  // 使用 Ctrl+Alt 组合，避免与输入框/其它控件的方向键行为冲突
  if (event.ctrlKey && event.altKey && !event.shiftKey &&
      (event.key === 'ArrowLeft' || event.key === 'ArrowRight' || event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
    event.preventDefault()
    showCommandPalette.value = false
    const dirMap = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' }
    moveFocusInDirection(dirMap[event.key])
    return
  }

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
  }
  
  // Ctrl + ` 打开/隐藏终端面板
  if (event.ctrlKey && event.key === '`') {
    event.preventDefault()
    
    // 切换终端面板显示状态
    if (socket.value) {
      showTerminalPanel.value = !showTerminalPanel.value
    }
  }



  // Ctrl + Alt + Enter 发送缓冲区内容（当缓冲区有内容时生效）
  if (event.ctrlKey && event.altKey && event.key === 'Enter') {
    if (hasBufferedInput.value) {
      event.preventDefault()
      sendBufferedInput()
    }
  }

  // ESC 键关闭所有对话框
  if (event.key === 'Escape') {
    // 补全面板打开时优先关闭它（焦点可能仍在输入框，需在此统一处理）
    if (showCompletions.value) {
      closeCompletionsWithoutSelect()
      return
    }
    // 命令面板打开时优先关闭它
    if (showCommandPalette.value) {
      showCommandPalette.value = false
      return
    }
    // 网络拓扑大图打开时优先关闭它
    if (showTopologyOverlay.value) {
      showTopologyOverlay.value = false
      return
    }
    // 弹出面板（diff/rules/tools/缓存/重命名/权限管理）：Esc 关闭
    if (showDiffModal.value) {
      showDiffModal.value = false
      return
    }
    if (showRulesModal.value) {
      showRulesModal.value = false
      return
    }
    if (showToolsModal.value) {
      showToolsModal.value = false
      return
    }
    if (showRenameAgentModal.value) {
      showRenameAgentModal.value = false
      return
    }
    if (showEditAccessModal.value) {
      showEditAccessModal.value = false
      return
    }
    if (showBufferPanel.value) {
      showBufferPanel.value = false
      return
    }
    // 如果对话框打开，关闭对话框
    if (showSettingsModal.value) {
      showSettingsModal.value = false
    } else if (showCreateAgentModal.value) {
      showCreateAgentModal.value = false
    } else if (showSessionDialog.value) {
      cancelSessionDialog()
    } else if (showDirDialog.value) {
      cancelDirDialog()
    }
    
    // ESC 键也关闭移动端菜单
    if (showMobileMenu.value) {
      showMobileMenu.value = false
    }
    
    // ESC 键也关闭Agent侧边栏和终端面板（移动端）
    if (showAgentSidebar.value && windowWidth.value <= 768) {
      showAgentSidebar.value = false
    }
    if (showTerminalPanel.value && windowWidth.value <= 768) {
      showTerminalPanel.value = false
    }
  }
}


// 聚焦集成终端内的活动终端
function focusActiveTerminal() {
  const session = terminalSessions.value.find(s => s.terminal_id === activeTerminalId.value)
    || terminalSessions.value[0]
  if (session?.terminal) {
    session.terminal.focus()
    return true
  }
  return false
}

// 区域容器兜底聚焦：当区域内部没有可聚焦元素时（如空终端/空编辑器），
// 让焦点落到区域容器上，保证方向键导航有落地反馈、且后续导航起点正确
function focusZoneContainer(el) {
  if (!el) return
  if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1')
  if (typeof el.focus === 'function') el.focus({ preventScroll: true })
}

// 是否是真正可聚焦的元素（排除 disabled / 不可见）
function isFocusableTarget(el) {
  if (!el || typeof el.focus !== 'function') return false
  if (el.disabled) return false
  if (el.hasAttribute && el.hasAttribute('disabled')) return false
  return true
}

// 在区域内查找首个可聚焦元素并聚焦；找不到则回退聚焦容器
function focusFirstIn(el, selector) {
  if (!el) return
  const defaultSel = 'textarea, input, [contenteditable="true"], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
  const list = selector ? el.querySelectorAll(`${selector}:not([disabled])`) : el.querySelectorAll(defaultSel)
  for (const target of list) {
    if (isFocusableTarget(target)) {
      target.focus({ preventScroll: true })
      return
    }
  }
  focusZoneContainer(el)
}

// 构建可聚焦区域列表（仅当前可见项），并附上其屏幕矩形用于几何导航
// 顺序：各 Session Panel → 集成终端 → 编辑器 → 聊天室
function getFocusZones() {
  const zones = []
  for (const panel of panels.value) {
    if (!panel.agentId) continue
    zones.push({
      key: `session:${panel.id}`,
      kind: 'session',
      focus: () => {
        activatePanel(panel.id)
        nextTick(() => {
          if (isAnyModalOpen()) return
          focusCurrentPanelInput(true)
        })
      },
    })
  }
  if (showTerminalPanel.value && !terminalDetached.value) {
    zones.push({
      key: 'terminal',
      kind: 'terminal',
      focus: () => {
        focusWindow('terminal')
        nextTick(() => {
          if (focusActiveTerminal()) return
          // 无活跃终端时，回退聚焦终端内首个可聚焦控件（如"新建终端"按钮），
          // 避免聚焦到不可交互的容器后被框架重置焦点
          focusFirstIn(document.querySelector('.terminal-panel'))
        })
      },
    })
  }
  if (showEditorPanel.value && !editorDetached.value) {
    zones.push({
      key: 'editor',
      kind: 'editor',
      focus: () => {
        focusWindow('editor')
        nextTick(() => {
          if (cmEditorView) {
            cmEditorView.focus()
            return
          }
          // 无编辑器内容时，回退聚焦编辑器内首个可聚焦控件（如活动栏按钮），
          // 避免聚焦到不可交互的容器后被框架重置焦点
          focusFirstIn(document.querySelector('.editor-panel'))
        })
      },
    })
  }
  if (showChatPanel.value && !chatDetached.value) {
    zones.push({
      key: 'chat',
      kind: 'chat',
      focus: () => {
        focusWindow('chat')
        nextTick(() => {
          focusFirstIn(document.querySelector('.chat-panel'), '.chat-input')
        })
      },
    })
  }
  return zones
}

// 根据真实 DOM 焦点推断当前所处区域 key（比 activeWindow 更可靠：
// activeWindow 仅在显式调用 focusWindow 时更新，用户点击面板输入框时不会同步）
function getFocusedZoneKey() {
  const el = document.activeElement
  if (!el) return null
  const termEl = document.querySelector('.terminal-panel')
  if (termEl && termEl.contains(el)) return 'terminal'
  const editorEl = document.querySelector('.editor-panel')
  if (editorEl && editorEl.contains(el)) return 'editor'
  const chatEl = document.querySelector('.chat-panel')
  if (chatEl && chatEl.contains(el)) return 'chat'
  for (const panel of panels.value) {
    if (!panel.agentId) continue
    const root = sessionPanelRefs.get(panel.id)?.$el
    if (root && root.contains(el)) return `session:${panel.id}`
  }
  return null
}

// 当前所处的焦点区域 key（用于几何导航定位起点）
function getActiveFocusZoneKey() {
  // 优先依据真实焦点位置
  const focusedKey = getFocusedZoneKey()
  if (focusedKey) return focusedKey
  // 回退：依据显式记录的当前窗口
  if (activeWindow.value === 'terminal' && showTerminalPanel.value && !terminalDetached.value) {
    return 'terminal'
  }
  if (activeWindow.value === 'editor' && showEditorPanel.value && !editorDetached.value) {
    return 'editor'
  }
  if (activeWindow.value === 'chat' && showChatPanel.value && !chatDetached.value) {
    return 'chat'
  }
  const panel = getCurrentPanel()
  if (panel && panel.agentId) return `session:${panel.id}`
  return null
}

// 取焦点区域的屏幕矩形；不可见/无 DOM 时返回 null
function getFocusZoneRect(zone) {
  if (!zone) return null
  let el = null
  if (zone.kind === 'session') {
    const panelId = zone.key.slice('session:'.length)
    el = sessionPanelRefs.get(panelId)?.$el || null
  } else if (zone.kind === 'terminal') {
    el = document.querySelector('.terminal-panel')
  } else if (zone.kind === 'editor') {
    el = document.querySelector('.editor-panel')
  } else if (zone.kind === 'chat') {
    el = document.querySelector('.chat-panel')
  }
  if (!el || typeof el.getBoundingClientRect !== 'function') return null
  const rect = el.getBoundingClientRect()
  if (rect.width <= 0 && rect.height <= 0) return null
  return rect
}

// 判断候选区域相对当前区域是否位于给定方向，并返回排序打分（越小越优先）
// dir: 'left' | 'right' | 'up' | 'down'
function scoreFocusZoneByDirection(curRect, candRect, dir) {
  const curCenterX = curRect.left + curRect.width / 2
  const curCenterY = curRect.top + curRect.height / 2
  const candCenterX = candRect.left + candRect.width / 2
  const candCenterY = candRect.top + candRect.height / 2

  if (dir === 'left') {
    if (candCenterX >= curCenterX) return null
    const primary = curRect.left - candRect.right
    // 垂直方向中心线位移越小越优先
    const secondary = Math.abs(candCenterY - curCenterY)
    return primary * 1000 + secondary
  }
  if (dir === 'right') {
    if (candCenterX <= curCenterX) return null
    const primary = candRect.left - curRect.right
    const secondary = Math.abs(candCenterY - curCenterY)
    return primary * 1000 + secondary
  }
  if (dir === 'up') {
    if (candCenterY >= curCenterY) return null
    const primary = curRect.top - candRect.bottom
    const secondary = Math.abs(candCenterX - curCenterX)
    return primary * 1000 + secondary
  }
  if (dir === 'down') {
    if (candCenterY <= curCenterY) return null
    const primary = candRect.top - curRect.bottom
    const secondary = Math.abs(candCenterX - curCenterX)
    return primary * 1000 + secondary
  }
  return null
}

// 按几何布局在可聚焦区域之间移动：根据当前区域矩形，选择该方向上最贴近的区域
function moveFocusInDirection(dir) {
  const zones = getFocusZones()
  if (zones.length === 0) return
  const activeKey = getActiveFocusZoneKey()
  const currentZone = zones.find(z => z.key === activeKey)
  const curRect = getFocusZoneRect(currentZone)
  if (!curRect) return

  let bestZone = null
  let bestScore = Infinity
  for (const zone of zones) {
    if (zone.key === activeKey) continue
    const candRect = getFocusZoneRect(zone)
    if (!candRect) continue
    const score = scoreFocusZoneByDirection(curRect, candRect, dir)
    if (score === null) continue
    if (score < bestScore) {
      bestScore = score
      bestZone = zone
    }
  }
  if (bestZone) bestZone.focus()
}
// 移动端历史管理变量
let historyStateCount = 0

// 监听页面刷新/跳转，如果连接到gateway则提示用户
const handleBeforeUnload = (e) => {
  if (socket.value) {
    // 有socket连接，提示用户
    e.preventDefault()
    e.returnValue = '' // Chrome需要returnValue
  }
}

// 移动端：打开浮层时推送历史状态
const pushOverlayState = () => {
  if (windowWidth.value <= 768) {
    history.pushState({ overlay: true }, '', '')
    historyStateCount++
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
    nextTick(() => layoutCodeMirrorEditor())
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

// Agent 心跳定时器
let heartbeatTimer = null

// 检查心跳超时并触发重连
function checkHeartbeatTimeout() {
  const now = Date.now()
  sockets.value.forEach((ws, agentId) => {
    const lastPong = lastPongTime.value.get(agentId)
    // 如果超过超时时间未收到 pong，认为连接已断
    if (!lastPong || (now - lastPong > HEARTBEAT_TIMEOUT)) {
      console.warn(`[HEARTBEAT] Timeout for agent ${agentId}, last pong: ${lastPong ? new Date(lastPong).toLocaleTimeString() : 'never'}, triggering reconnect...`)
      // 关闭旧连接，触发重连
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
      sockets.value.delete(agentId)
      connectingAgents.value.delete(agentId) // 释放连接锁
      lastPongTime.value.delete(agentId)
      // 如果是当前活跃 Agent，触发重连
      if (agentId === currentAgentId.value) {
        const agent = agentMap.value.get(agentId)
        if (agent && !connectingAgents.value.has(agentId)) {
          connectToAgent(agent).catch(e => console.warn(`[HEARTBEAT] Reconnect failed for ${agentId}:`, e.message))
        }
      }
    }
  })
}

// 发送心跳到所有 Agent 连接
function sendHeartbeat() {
  const now = Date.now()
  sockets.value.forEach((ws, agentId) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      // 记录发送时间（用于超时检测）
      lastPongTime.value.set(agentId, now) // 先更新为发送时间，收到 pong 后会再次更新
      ws.send(JSON.stringify({ type: 'ping' }))
    }
  })
  
  // 检查是否有连接超时
  checkHeartbeatTimeout()
}

onMounted(() => {
  // 不再在页面加载时创建终端，改为动态创建

  // 启动心跳机制
  heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL)

  // seq 由 getAgentLastSeq() 从历史记录动态获取，无需初始化加载

  // 尝试从 localStorage 加载已保存的 token（免登录功能）
  loadSavedToken()

  // 如果 token 加载成功，隐藏登录框并自动连接
  if (hasAuthToken()) {
    showConnectModal.value = false
    isAutoConnecting.value = true
    connect()
  }

  updateViewportHeight()
  visualViewportResizeHandler = () => {
    updateViewportHeight()
  }
  window.visualViewport?.addEventListener('resize', visualViewportResizeHandler)

  // 测量标题栏高度（用于自动隐藏时的位移量）
  measureHeaderHeight()

  inputHistory.value = loadInputHistory()
  
  // 已登录时才启动 Agent 列表刷新，避免未获取 token 前向后端发送请求
  if (hasAuthToken()) {
    startAgentListRefresh()
  }
  
  // 添加滚动事件监听，实现滚动到顶部时加载更多历史
  setupHistoryScrollListener(outputList.value)
  
  // 添加全局键盘事件监听（在捕获阶段处理 Ctrl+T 等快捷键）
  document.addEventListener('keydown', handleGlobalKeydown, { capture: true })
  
  // 监听窗口resize事件
  handleResize = () => {
    windowWidth.value = window.innerWidth
    updateViewportHeight()
    measureHeaderHeight()
    ensureAgentSidebarWidthInBounds()
    ensureEditorPanelInViewport()
    ensureTerminalPanelInViewport()
    sessionDetachedPanels.value.forEach(panelId => {
      ensureSessionPanelInViewport(panelId)
      saveSessionPanelRect(panelId)
    })
    saveAgentSidebarWidth()
    saveEditorPanelRect()
    saveTerminalPanelRect()
    layoutCodeMirrorEditor()

    const activeSession = terminalSessions.value.find(session => session.terminal_id === activeTerminalId.value)
    if (activeSession && activeSession.fitAddon && activeSession.terminal) {
      activeSession.fitAddon.fit()
      sendTerminalResize(activeSession.terminal_id, activeSession.terminal.rows, activeSession.terminal.cols)
    }
  }
  window.addEventListener('resize', handleResize)
  
  // 添加beforeunload监听
  window.addEventListener('beforeunload', handleBeforeUnload)
  
  // 移动端：监听返回键（popstate事件）
  handlePopState = () => {
    
    if (historyStateCount > 0) {
      // 有推送的历史状态，只是关闭浮层，不做真正的后退
      historyStateCount--
      
      // 关闭所有打开的浮层
      if (showSettingsModal.value) {
        showSettingsModal.value = false
      } else if (showCreateAgentModal.value) {
        showCreateAgentModal.value = false
      } else if (showSessionDialog.value) {
        cancelSessionDialog()
      } else if (showDirDialog.value) {
        cancelDirDialog()
      } else if (showAgentSidebar.value && windowWidth.value <= 768) {
        showAgentSidebar.value = false
      } else if (showTerminalPanel.value && windowWidth.value <= 768) {
        showTerminalPanel.value = false
      } else if (showMobileMenu.value) {
        showMobileMenu.value = false
      } else {
      }
    } else {
      // 没有推送的历史状态，允许默认后退行为
    }
  }
  window.addEventListener('popstate', handlePopState)

  // MutationObserver: 监听 outputList DOM 变化，自动渲染 mermaid/dot 图表
  if (outputList.value) {
    let diagramRenderTimer = null
    diagramObserver = new MutationObserver(() => {
      // 防抖：避免流式更新时频繁触发
      if (diagramRenderTimer) clearTimeout(diagramRenderTimer)
      diagramRenderTimer = setTimeout(async () => {
        const hasMermaid = outputList.value?.querySelector('.mermaid-container[data-mermaid-source]')
        const hasDot = outputList.value?.querySelector('.dot-container[data-dot-source]')
        if (hasMermaid) await renderMermaidDiagrams(outputList.value)
        if (hasDot) await renderDotDiagrams(outputList.value)
      }, 50)
    })
    diagramObserver.observe(outputList.value, { childList: true, subtree: true })
  }
})

onUnmounted(() => {

  // 清理标题栏自动隐藏定时器
  clearTimeout(headerHideTimer)

  // 清理滚动监听
  if (historyScrollListenerEl && historyScrollHandler) {
    historyScrollListenerEl.removeEventListener('scroll', historyScrollHandler)
    historyScrollListenerEl = null
    historyScrollHandler = null
  }
  if (historyScrollDebounceTimer) {
    clearTimeout(historyScrollDebounceTimer)
    historyScrollDebounceTimer = null
  }
  
  // 清理心跳定时器
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
  
  stopAgentSidebarResize()
  stopEditorPanelInteraction()
  stopEditorFileHeartbeat()
  window.visualViewport?.removeEventListener('resize', visualViewportResizeHandler)

  if (cmEditorView) {
    cmEditorView.destroy()
    cmEditorView = null
  }
  editorModels.clear()

  // 移除全局键盘事件监听
  document.removeEventListener('keydown', handleGlobalKeydown, { capture: true })
  
  // 移除窗口resize监听
  window.removeEventListener('resize', handleResize)
  
  // 移除beforeunload监听
  window.removeEventListener('beforeunload', handleBeforeUnload)
  
  // 移除返回键监听
  window.removeEventListener('popstate', handlePopState)

  // 断开图表渲染 MutationObserver
  if (diagramObserver) {
    diagramObserver.disconnect()
    diagramObserver = null
  }
})

// 播放单次提示音
function playSingleBeep(audioContext, startTime) {
  const oscillator = audioContext.createOscillator()
  const gainNode = audioContext.createGain()

  oscillator.connect(gainNode)
  gainNode.connect(audioContext.destination)

  oscillator.frequency.value = 800
  oscillator.type = 'sine'

  gainNode.gain.setValueAtTime(0.3, startTime)
  gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + 0.2)

  oscillator.start(startTime)
  oscillator.stop(startTime + 0.2)
}

// 播放聊天室新消息提示音（双音阶，区别于普通提示音）
function playChatNotificationSound() {
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)()
    const now = audioContext.currentTime

    // 播放两个不同频率的音符，形成"叮咚"效果
    playChatSingleTone(audioContext, now, 880, 'triangle', 0.25)
    playChatSingleTone(audioContext, now + 0.18, 1320, 'triangle', 0.3)
  } catch (e) {
  }
}

// 播放单次聊天提示音
function playChatSingleTone(audioContext, startTime, frequency, type, duration) {
  const oscillator = audioContext.createOscillator()
  const gainNode = audioContext.createGain()

  oscillator.connect(gainNode)
  gainNode.connect(audioContext.destination)

  oscillator.frequency.value = frequency
  oscillator.type = type

  gainNode.gain.setValueAtTime(0.25, startTime)
  gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duration)

  oscillator.start(startTime)
  oscillator.stop(startTime + duration)
}

// 播放提示音（连续三次），返回在最后一声结束后 resolve 的 Promise
function playNotificationSound() {
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)()
    const now = audioContext.currentTime

    // 连续播放三次提示音，每次间隔0.25秒
    playSingleBeep(audioContext, now)
    playSingleBeep(audioContext, now + 0.25)
    playSingleBeep(audioContext, now + 0.5)

    // 最后一声在 now + 0.5 开始、持续 0.2s，留出少量余量
    return new Promise(resolve => setTimeout(resolve, 750))
  } catch (e) {
    return Promise.resolve()
  }
}

// 收到输入请求时播放提示音（不受自动朗读开关限制，任何情况下都播放）
function notifyInputRequest() {
  playNotificationSound()
}

// ---- 自动朗读（浏览器内置 SpeechSynthesis） ----
const autoReadSupported = typeof window !== 'undefined' && 'speechSynthesis' in window
// 停止自动朗读（复用 SessionPanel 的停止逻辑，保证图标状态同步）
function stopAutoRead() {
  if (!autoReadSupported) return
  for (const sp of sessionPanelRefs.values()) {
    sp?.stopSpeak?.()
  }
}

// 从渲染后的 HTML 提取纯文本，避免把 Markdown 标记念出来
function extractAutoReadText(item) {
  if (!item) return ''
  if (item.html) {
    const tmp = document.createElement('div')
    tmp.innerHTML = item.html
    return (tmp.textContent || '').replace(/\s+/g, ' ').trim()
  }
  return String(item.text || '').trim()
}

// 获取自动朗读目标：多行输入取最后一条有文本的消息，单行/确认取输入提示
function getAutoReadTarget(agentId, executionStatus) {
  if (executionStatus === 'waiting_multi') {
    const messages = allOutputs.value.get(agentId) || []
    for (let i = messages.length - 1; i >= 0; i--) {
      if (extractAutoReadText(messages[i])) return { message: messages[i] }
    }
  }
  const tip = panelInputTips.value.get(agentId) || ''
  return { text: tip || '等待输入' }
}

// 进入等待输入状态时触发对应消息的朗读按钮逻辑（提示音由 notifyInputRequest 独立播放）
async function handleAutoRead(agentId, executionStatus) {
  if (!isAutoReadEnabled(agentId)) return
  const target = getAutoReadTarget(agentId, executionStatus)
  const panel = panels.value.find(p => p.agentId === agentId)
  const sp = panel ? sessionPanelRefs.get(panel.id) : null
  if (target.message && sp?.speakMessage) {
    // 复用消息列表的朗读逻辑，图标状态自动同步
    sp.speakMessage(target.message)
  } else if (sp?.speakText) {
    sp.speakText(target.text)
  }
}

// 通知权限状态
let notificationPermissionRequested = false

// 发送系统通知（仅弹窗，不播放提示音）
function sendSystemNotification(message) {
  // 检查浏览器是否支持 Notification API
  if (!('Notification' in window)) {
    return
  }

  // 如果已经获得权限，直接发送通知
  if (Notification.permission === 'granted') {
    new Notification('Jarvis', {
      body: message,
      icon: '/icons/jarvis-pet.svg'
    })
  }
  // 如果还没有拒绝且尚未请求过权限，请求权限
  else if (Notification.permission !== 'denied' && !notificationPermissionRequested) {
    notificationPermissionRequested = true
    Notification.requestPermission().then(permission => {
      if (permission === 'granted') {
        new Notification('Jarvis', {
          body: message,
          icon: '/icons/jarvis-pet.svg'
        })
      }
    })
  }
}
</script>

<style>
/* 全局样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

/* Agent 等待输入状态的背景高亮 */
.editor-agent-node.waiting-input {
  background: rgba(210, 153, 34, 0.15);
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
  background: var(--color-bg-primary);
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
  height: var(--app-height, 100vh);
  min-height: 100vh;
  min-height: 100dvh;
  width: 100vw;
  margin: 0;
  padding: 0;
  padding-left: env(safe-area-inset-left, 0px);
  padding-right: env(safe-area-inset-right, 0px);
  background: transparent;
  color: var(--color-text-primary);
  font-family: 'Consolas', 'Microsoft YaHei', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  overflow: hidden;
}

/* 未登录时隐藏后台界面，仅保留登录弹窗与背景 */
.app.not-connected :deep(.agent-sidebar),
.app.not-connected > .main-content-wrapper {
  visibility: hidden;
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
  padding: 10px 16px;
  padding-top: calc(10px + env(safe-area-inset-top, 0px));
  background: var(--color-bg-secondary);
  border-bottom: 0.5px solid var(--color-border-subtle);
  flex-shrink: 0;
  transition: margin-top 0.25s ease, opacity 0.25s ease;
}

/* 自动隐藏：向上缩回（保留过渡动画，不用 display:none） */
.app-header.is-hidden {
  margin-top: calc(-1 * (var(--app-header-h, 0px) + env(safe-area-inset-top, 0px)));
  opacity: 0;
  pointer-events: none;
}

/* 桌面端顶部感应区：鼠标移入唤出标题栏 */
.top-hover-zone {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 8px;
  z-index: 1200;
}

.mobile-header-actions {
  display: none;
  gap: 8px;
}

/* 桌面端显示，移动端隐藏 */
.desktop-only {
  display: flex;
}

/* 移动端显示，桌面端隐藏 */
.mobile-only {
  display: none;
}

.header-title h1 {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-info-display {
  font-size: 13px;
  color: var(--color-text-secondary);
  padding: 0 8px;
  border-right: 1px solid var(--color-border);
  margin-right: 4px;
  white-space: nowrap;
}

.logout-btn:hover {
  color: var(--color-error) !important;
}

.editor-panel {
  position: fixed;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  user-select: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.editor-panel-active {
  border-color: var(--color-accent) !important;
  box-shadow: 0 0 0 1px var(--color-accent), 0 0 20px rgba(32, 200, 255, 0.15) !important;
}

.editor-panel-dragging {
  transition: none;
}

.editor-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  border-bottom: 1px solid var(--color-border-subtle);
  background: transparent;
  cursor: move;
  gap: 8px;
  min-height: 32px;
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
  color: var(--color-text-secondary);
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
  background: transparent;
  overflow-x: auto;
}

.editor-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 220px;
  padding: 6px 10px;
  border: none;
  border-bottom: none;
  border-radius: 6px 6px 0 0;
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 12px;
  line-height: 1.2;
}

.editor-tab.active {
  background: transparent;
  color: var(--color-text-primary);
}

.editor-tab-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.editor-tab-dirty {
  color: #ff8520;
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
  gap: 8px;
  min-height: 30px;
  padding: 0 10px;
  border-top: 1px solid var(--color-border-subtle);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-secondary);
}

.editor-toolbar-status {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.editor-toolbar-status.error {
  color: var(--color-error);
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
  border-radius: var(--tile-radius-xs);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease-out;
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);

}

.editor-edit-toggle:hover {
  background: var(--color-bg-hover);
}

.editor-edit-toggle:active {
  transform: scale(0.96);
}

.editor-edit-toggle.editable {
  background: rgba(54, 255, 124, 0.15);
  color: var(--color-success);
}

.editor-edit-toggle.editable:hover {
  background: rgba(54, 255, 124, 0.25);
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
  background: transparent;
}

.editor-activity-bar {
  width: 44px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  border-right: 1px solid var(--color-border-subtle);
  background: transparent;
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
  border-radius: var(--tile-radius);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s ease-out;
}

.editor-activity-button:hover,
.editor-activity-button.active {
  color: var(--color-text-primary);
  background: var(--color-accent-subtle);
  border-color: var(--color-border-active);
}

.editor-sidebar {
  position: relative;
  min-width: 200px;
  max-width: 560px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid var(--color-border-subtle);
  background: transparent;
  flex-shrink: 0;
}

.editor-sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: -4px;
  width: 8px;
  height: 100%;
  cursor: ew-resize;
  z-index: 5;
}

.editor-sidebar-resize-handle::after {
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

.editor-sidebar-resize-handle:hover::after {
  background: #20c8ff;
}

.editor-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.editor-sidebar-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary);
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
  overflow-y: auto;
}

.editor-file-tree-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.editor-file-tree-empty {
  padding: 12px;
  color: var(--color-text-secondary);
  font-size: 12px;
  text-align: center;
}

/* Agent 节点样式 */
.editor-agent-node {
  border-bottom: 1px solid var(--color-border-subtle);
}

.editor-agent-node.selected {
  background: var(--color-bg-tertiary);
}

.editor-agent-node.selected .agent-node-content {
  background: var(--color-bg-tertiary);
}

.stopped-agents-group {
  border-top: 1px solid var(--color-border-subtle);
}

.stopped-agents-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  background: var(--color-bg-secondary);
  font-weight: 500;
  gap: 6px;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.stopped-agents-header:hover {
  background: var(--color-bg-tertiary);
}

.stopped-agents-title {
  flex: 1;
}

.expand-arrow {
  transition: transform 0.2s ease;
  display: inline-block;
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.stopped-agents-list {
  border-top: 1px solid var(--color-border-subtle);
}

.editor-agent-node.stopped {
  opacity: 0.7;
}

.agent-node-content {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  background: var(--color-bg-secondary);
  font-weight: 500;
  gap: 6px;
}

.agent-node-content:hover {
  background: var(--color-bg-hover);
}

.agent-icon {
  font-size: 14px;
}

.agent-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-node-id {
  font-size: 10px;
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}

.agent-file-tree {
  border-left: 2px solid var(--color-border-subtle);
  margin-left: 12px;
}

.editor-sidebar-placeholder {
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 10px;
  padding: 20px;
  color: var(--color-text-secondary);
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
  border-bottom: 1px solid var(--color-border-subtle);
}

.editor-global-search-input {
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: var(--tile-radius-xs);
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  font-size: 12px;
  box-sizing: border-box;
}

.editor-global-search-input:focus {
  outline: none;
  border-color: var(--color-accent);
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
  color: var(--color-text-primary);
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
  color: var(--color-text-secondary);
}

.editor-global-search-empty {
  font-size: 12px;
  color: var(--color-text-secondary);
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
  color: var(--color-accent);
  cursor: pointer;
  word-break: break-all;
}

.editor-global-search-file-count {
  margin-left: 4px;
  color: var(--color-text-secondary);
}

.editor-global-search-match {
  width: 100%;
  display: flex;
  gap: 10px;
  padding: 8px 10px;
  border: none;
  border-radius: var(--tile-radius-xs);
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  text-align: left;
  cursor: pointer;
}

.editor-global-search-match:hover {
  border-color: var(--color-border-active);
  background: var(--color-bg-hover);
}

.editor-global-search-line {
  flex: 0 0 auto;
  min-width: 32px;
  font-size: 11px;
  color: var(--color-text-secondary);
}

.editor-global-search-text {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.editor-global-search-text mark {
  background: rgba(255, 133, 32, 0.32);
  color: #ff8520;
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
  background: var(--color-bg-secondary);
}

.editor-codemirror-container {
  width: 100%;
  height: 100%;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
}

.editor-placeholder {
  margin: auto;
  text-align: center;
  color: #8ba3b8;
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
  background: rgba(54, 255, 124, 0.15);
  border: none;
  border-radius: var(--tile-radius-xs);
  font-size: 13px;
}

.current-agent-info .agent-type {
  font-weight: 600;
}

.current-agent-info .agent-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--color-bg-tertiary);
}

.current-agent-info .agent-status.running {
  background: rgba(32, 200, 255, 0.2);
  color: #20c8ff;
}

.current-agent-info .agent-status.stopped {
  background: rgba(63, 185, 80, 0.2);
  color: #36ff7c;
}

.current-agent-info .agent-status.waiting_multi {
  background: rgba(210, 153, 34, 0.2);
  color: #ff8520;
}

.current-agent-info .agent-status.waiting_single {
  background: rgba(255, 60, 72, 0.2);
  color: #ff3c48;
}

.current-agent-info .agent-port {
  color: #8ba3b8;
}

.current-agent-info .agent-dir {
  color: #8ba3b8;
  font-size: 12px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.icon-btn {
  background: var(--color-bg-hover);
  border: none;
  border-radius: var(--tile-radius);
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  color: #8ba3b8;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-btn:hover:not(:disabled) {
  background: var(--color-bg-tertiary);
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

.chat-btn-wrapper {
  position: relative;
  overflow: visible;
}

.chat-unread-badge {
  position: absolute;
  top: -6px;
  right: -8px;
  background: #ff3c48;
  color: #d6e4f0;
  font-size: 10px;
  font-weight: 600;
  min-width: 16px;
  height: 16px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  line-height: 1;
  pointer-events: none;
  z-index: 10;
  white-space: nowrap;
}

.manual-interrupt-btn {
  background: #f0883e;
  border: none;
  border-radius: var(--tile-radius);
  color: #d6e4f0;
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
  color: #8ba3b8;
  padding: 4px 10px;
  background: var(--color-bg-tertiary);
  border-radius: 20px;
  border: none;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.dot.offline {
  background: #ff3c48;
  color: #ff3c48;
}

.dot.connecting {
  background: #ff8520;
  color: #ff8520;
}

.dot.reconnecting {
  background: #ff8520;
  color: #ff8520;
}

.dot.online {
  background: #36ff7c;
  color: #36ff7c;
}

/* Agent 浮动窗口 */
.agent-sidebar {
  position: relative;
  width: 320px;
  min-width: 0;
  background: var(--color-bg-secondary);
  border-right: 0.5px solid var(--color-border-subtle);
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
  background: #20c8ff;
}

.agent-sidebar-header {
  padding: 12px;
  border-bottom: 0.5px solid var(--color-border-subtle);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--color-bg-secondary);
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
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.agent-collapsed-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-collapsed-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: var(--color-bg-secondary);
  border: none;
  border-radius: var(--tile-radius-xs);
  color: #8ba3b8;
  cursor: pointer;
  text-align: left;
}

.agent-collapsed-toggle:hover {
  background: var(--color-bg-hover);
  color: #e6edf3;
}

.agent-collapsed-arrow {
  width: 16px;
  color: #20c8ff;
}

.agent-collapsed-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.agent-collapsed-count {
  font-size: 12px;
  color: #8ba3b8;
}

.agent-item {
  padding: 12px;
  background: var(--color-bg-secondary);
  border: none;
  border-radius: var(--tile-radius);
  cursor: pointer;
  position: relative;
}

.agent-item:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-subtle);
}

.agent-item.active {
  background: rgba(32, 200, 255, 0.15);
  border-color: var(--color-accent);
}

.agent-item.selected {
  background: rgba(32, 200, 255, 0.15);
  border-color: var(--color-accent-secondary);
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
  accent-color: #20c8ff;
}

.batch-actions-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border-subtle);
  gap: 12px;
}

.batch-actions-info {
  font-size: 13px;
  color: #8ba3b8;
}

.batch-actions-buttons {
  display: flex;
  gap: 8px;
}

.agent-item .agent-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--color-bg-tertiary);
  margin-left: 8px;
}

.agent-item .agent-status.running {
  background: rgba(32, 200, 255, 0.2);
  color: #20c8ff;
}

.agent-item .agent-status.stopped {
  background: rgba(63, 185, 80, 0.2);
  color: #36ff7c;
}

.agent-item .agent-status.waiting_multi {
  background: rgba(210, 153, 34, 0.2);
  color: #ff8520;
}

.agent-item .agent-status.waiting_single {
  background: rgba(255, 60, 72, 0.2);
  color: #ff3c48;
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
  color: #36ff7c;
}

.agent-status.stopped {
  background: rgba(255, 60, 72, 0.2);
  color: #ff3c48;
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
  background: #36ff7c;
  box-shadow: 0 0 0 2px rgba(63, 185, 80, 0.2);
}

.agent-status-dot.stopped {
  background: #ff3c48;
  box-shadow: 0 0 0 2px rgba(255, 60, 72, 0.2);
}

.agent-status-dot.waiting_multi {
  background: #ff8520;
  box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.2);
}

.agent-status-dot.waiting_single {
  background: #ff8520;
  box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.2);
}

.agent-status-dot.waiting_confirm {
  background: #ff8520;
  box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.2);
}

.agent-llm-group {
  font-size: 11px;
  color: #666;
  background: var(--color-bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}

.agent-port {
  font-size: 12px;
  color: #8ba3b8;
  margin-left: auto;
}

.agent-dir {
  font-size: 11px;
  color: #8ba3b8;
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
  background: var(--color-bg-hover);
  border: none;
  border-radius: var(--tile-radius-xs);
  font-size: 14px;
  cursor: pointer;
  padding: 4px 8px;
  color: #8ba3b8;
  transition: all 0.2s ease;
}

.icon-btn-small:hover {
  background: var(--color-bg-tertiary);
  color: #e6edf3;
  transform: translateY(-1px);
}

.icon-btn-small:active {
  transform: translateY(0);
}

.icon-btn-small:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.agent-actions .icon-btn-small.stop-btn:hover {
  background: rgba(255, 60, 72, 0.2);
  color: #ff3c48;
  border-color: var(--color-error);
}

.agent-empty {
  text-align: center;
  color: #8ba3b8;
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
  background: var(--color-bg-hover);
}

.tree-node-icon {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 6px;
  color: #8ba3b8;
  transition: transform 0.2s ease;
  font-size: 12px;
}

.tree-node-icon.expand-arrow {
  margin-right: 4px;
  color: #8ba3b8;
}

.tree-node-icon.expand-arrow.expanded {
  transform: rotate(90deg);
}

.tree-node-icon.folder-icon {
  color: #20c8ff;
}

.tree-node-icon.file-icon {
  color: #8ba3b8;
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
  color: #20c8ff;
  font-weight: 500;
}

.tree-node-text.file {
  color: #d6e4f0;
}

.tree-children {
  margin-left: 16px;
  border-left: 1px solid var(--color-border-subtle);
  padding-left: 4px;
}

.tree-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: #8ba3b8;
  font-size: 12px;
}

.tree-loading-icon {
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border-subtle);
  border-top-color: var(--color-text-secondary);
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
  color: #8ba3b8;
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
  color: #8ba3b8;
  line-height: 1.5;
}

.session-list {
  max-height: 300px;
  overflow-y: auto;
  background: var(--color-bg-tertiary);
  border-radius: var(--tile-radius);
  border: none;
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
  border-bottom: 0.5px solid var(--color-border-subtle);
  cursor: pointer;
  border-radius: var(--tile-radius-xs);
  margin: 4px;
}

.session-item:last-child {
  border-bottom: none;
}

.session-item:hover {
  background: var(--color-bg-hover);
}

.session-item.selected {
  background: rgba(63, 185, 80, 0.15);
  border-color: var(--color-success);
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
  color: #8ba3b8;
  word-break: break-all;
  line-height: 1.4;
}

.session-date {
  font-size: 11px;
  color: #8ba3b8;
  margin-top: 6px;
}

.session-empty {
  padding: 40px 20px;
  text-align: center;
  color: #8ba3b8;
  font-size: 13px;
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
  background: var(--color-bg-tertiary);
  color: #e6edf3;
  border: none;
  border-radius: var(--tile-radius-xs);
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
}

.select-dir-btn:hover {
  background: var(--color-bg-hover);
  transform: translateY(-1px);
}

/* Panel 网格布局 */
.panel-grid {
  flex: 1;
  width: 100%;
  overflow: hidden;
  display: grid;
  gap: 8px;
  padding: 8px;
  box-sizing: border-box;
  min-height: 0;
  min-width: 0;
}

/* 空状态：无任何可见 Panel 时的欢迎背景特效 */
.empty-stage {
  grid-column: 1 / -1;
  grid-row: 1 / -1;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 28px;
  overflow: hidden;
  min-height: 0;
  border-radius: var(--tile-radius);
}

/* 缓慢漂移的网格底板 */
.empty-stage-grid {
  position: absolute;
  inset: -20%;
  background-image:
    linear-gradient(rgba(32, 200, 255, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(32, 200, 255, 0.06) 1px, transparent 1px);
  background-size: 52px 52px, 52px 52px;
  mask-image: radial-gradient(circle at 50% 50%, #000 0%, transparent 72%);
  -webkit-mask-image: radial-gradient(circle at 50% 50%, #000 0%, transparent 72%);
  animation: emptyGridDrift 32s linear infinite;
}

/* 极光光斑 */
.empty-stage-glow {
  position: absolute;
  width: 60vmax;
  height: 60vmax;
  border-radius: 50%;
  filter: blur(40px);
  opacity: 0.5;
  pointer-events: none;
}

.empty-stage-glow-a {
  top: -18%;
  left: -12%;
  background: radial-gradient(circle, rgba(32, 200, 255, 0.28) 0%, transparent 62%);
  animation: emptyGlowPulse 9s ease-in-out infinite;
}

.empty-stage-glow-b {
  bottom: -22%;
  right: -14%;
  background: radial-gradient(circle, rgba(54, 255, 124, 0.22) 0%, transparent 62%);
  animation: emptyGlowPulse 11s ease-in-out infinite reverse;
}

/* 中心旋转光环 */
.empty-stage-orbit {
  position: relative;
  width: 168px;
  height: 168px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.empty-stage-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid rgba(32, 200, 255, 0.35);
  border-top-color: var(--color-accent);
  box-shadow: 0 0 24px rgba(32, 200, 255, 0.25);
  animation: emptySpin 14s linear infinite;
}

.empty-stage-ring-2 {
  inset: 18px;
  border-color: rgba(54, 255, 124, 0.3);
  border-bottom-color: var(--color-success);
  box-shadow: 0 0 20px rgba(54, 255, 124, 0.2);
  animation: emptySpin 9s linear infinite reverse;
}

.empty-stage-core {
  position: relative;
  width: 92px;
  height: 92px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle, rgba(32, 200, 255, 0.18) 0%, transparent 72%);
  box-shadow: inset 0 0 30px rgba(32, 200, 255, 0.25);
}

.empty-stage-logo {
  width: 64px;
  height: 64px;
  filter: drop-shadow(0 0 14px rgba(32, 200, 255, 0.6));
  animation: emptyFloat 6s ease-in-out infinite;
}

/* 文案区 */
.empty-stage-text {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
  padding: 0 24px;
}

.empty-stage-title {
  font-size: 34px;
  letter-spacing: 0.32em;
  font-weight: 700;
  color: var(--color-text-primary);
  text-shadow: 0 0 22px rgba(32, 200, 255, 0.55);
  margin: 0;
}

.empty-stage-slogan {
  font-size: 19px;
  font-weight: 600;
  letter-spacing: 0.12em;
  background: var(--gradient-accent);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
  margin: 0;
}

.empty-stage-sub {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0;
}

.empty-stage-quadrants {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 6px;
  max-width: 620px;
}

.empty-stage-quadrant {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 14px;
  border-radius: var(--tile-radius-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-subtle);
  font-size: 11px;
  color: var(--color-text-muted);
}

.empty-stage-quadrant b {
  font-size: 12px;
  color: var(--color-text-primary);
  font-weight: 600;
}

.empty-stage-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--color-text-muted);
}

.empty-stage-hint kbd {
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  font-family: inherit;
  font-size: 11px;
}

@keyframes emptyGridDrift {
  from { transform: translate3d(0, 0, 0); }
  to { transform: translate3d(-52px, -52px, 0); }
}

@keyframes emptySpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes emptyFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

@keyframes emptyGlowPulse {
  0%, 100% { opacity: 0.38; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.08); }
}

@media (prefers-reduced-motion: reduce) {
  .empty-stage-grid,
  .empty-stage-glow,
  .empty-stage-ring,
  .empty-stage-logo {
    animation: none;
  }
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
  padding: 8px;
  padding-left: max(8px, env(safe-area-inset-left, 0px));
  padding-right: max(8px, env(safe-area-inset-right, 0px));
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--color-bg-tile);
}

.message {
  background: var(--color-bg-tile);
  border-radius: var(--tile-radius);
  padding: 6px 10px;
  border: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.message:hover {
  border-color: var(--color-border-subtle);
}

/* 用户输入消息 - 右对齐样式（必须放在 .message 之后以覆盖） */
.message.message-user_input {
  background: var(--color-bg-tertiary) !important;
  border: 1px solid var(--color-accent) !important;
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
  background: rgba(32, 200, 255, 0.15);
  color: var(--color-accent);
  font-size: 10px;
  padding: 2px 6px;
}

.message.message-user_input .agent-name {
  color: var(--color-accent);
  font-size: 10px;
}

.message.message-user_input .timestamp {
  color: #8ba3b8;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 10px;
}

.message.message-user_input .message-body {
  color: #d6e4f0 !important;
  font-style: italic !important;
}

.message-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
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
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 10px;
}

.message-content .message-body {
  font-size: 13px;
  line-height: 1.5;
  color: #e6edf3;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  width: 100%;
}

.message-meta-left .badge {
  font-size: 10px;
  padding: 3px 8px;
  background: var(--color-bg-secondary);
  color: #8ba3b8;
  border-radius: var(--tile-radius-xs);
  font-weight: 600;
  letter-spacing: 0.02em;
  border: none;
}

.message-meta-left .agent-name {
  font-size: 10px;
  color: #20c8ff;
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
  color: #20c8ff;
}

.message-meta-left .timestamp {
  font-size: 10px;
  color: #8ba3b8;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: var(--tile-radius-sm);
  background: #0b1424;
  color: #8ba3b8;
}

.timestamp {
  font-size: 11px;
  color: #8ba3b8;
}

.message-body {
  color: #e6edf3;
  line-height: 1.6;
  word-wrap: break-word;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
}

/* 消息元信息样式（agent名称和时间戳） */
.message-meta {
  font-size: 11px;
  color: #8ba3b8;
  margin-top: 4px;
  opacity: 0.8;
}

.message-agent {
  color: #20c8ff;
}

.message-separator {
  color: #8ba3b8;
}

.message-time {
  color: #8ba3b8;
}

.message-silent {
  color: #f0883e;
  display: inline-flex;
  align-items: center;
  vertical-align: middle;
}

.message-silent svg {
  width: 12px;
  height: 12px;
}

.message-body.markdown-content :deep(pre) {
  background: var(--color-bg-secondary);
  padding: 14px;
  border-radius: var(--tile-radius);
  border: none;
  overflow-x: auto;
  margin: 10px 0;
}

.message-body.markdown-content :deep(code) {
  background: var(--color-bg-secondary);
  padding: 3px 7px;
  border-radius: 5px;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 12px;
  border: none;
}

.message-body.markdown-content :deep(p) {
  margin: 8px 0;
}

.message-body.markdown-content :deep(ol),
.message-body.markdown-content :deep(ul) {
  padding-left: 20px;
  margin: 8px 0;
}

.message-body.markdown-content :deep(li) {
  margin: 4px 0;
  list-style-position: inside;
}

.message-body.markdown-content :deep(.plantuml-block) {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 12px 0;
  padding: 12px;
  border: none;
  border-radius: 10px;
  background: var(--color-bg-tertiary);
}

.message-body.markdown-content :deep(.plantuml-notice) {
  font-size: 12px;
  color: #8ba3b8;
}

.message-body.markdown-content :deep(.plantuml-link) {
  display: inline-flex;
  align-self: flex-start;
  max-width: 100%;
  color: #20c8ff;
  text-decoration: none;
}

.message-body.markdown-content :deep(.plantuml-link:hover) {
  text-decoration: underline;
}

.message-body.markdown-content :deep(.plantuml-image) {
  display: block;
  max-width: 100%;
  height: auto;
  background: #16263a;
  border-radius: var(--tile-radius-xs);
}

.message-body.markdown-content :deep(.plantuml-source summary) {
  cursor: pointer;
  color: #8ba3b8;
}

/* 通用图表样式（dot/graphviz） */
.message-body.markdown-content :deep(.diagram-block) {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 12px 0;
  padding: 12px;
  border: none;
  border-radius: 10px;
  background: var(--color-bg-tertiary);
}

.message-body.markdown-content :deep(.diagram-notice) {
  font-size: 12px;
  color: #8ba3b8;
}

.message-body.markdown-content :deep(.diagram-link) {
  display: inline-flex;
  align-self: flex-start;
  max-width: 100%;
  color: #20c8ff;
  text-decoration: none;
}

.message-body.markdown-content :deep(.diagram-link:hover) {
  text-decoration: underline;
}

.message-body.markdown-content :deep(.diagram-image) {
  display: block;
  max-width: 100%;
  height: auto;
  background: #16263a;
  border-radius: var(--tile-radius-xs);
}

.message-body.markdown-content :deep(.diagram-source summary) {
  cursor: pointer;
  color: #8ba3b8;
}

/* Dot/Graphviz 图表样式 */
.message-body.markdown-content :deep(.dot-container) {
  min-height: 40px;
  display: block;
}

.message-body.markdown-content :deep(.dot-container svg) {
  max-width: 100%;
  height: auto;
}

.message-body.markdown-content :deep(.dot-loading) {
  color: #8ba3b8;
  font-size: 13px;
  padding: 8px 0;
}

/* Mermaid 图表样式 */
.message-body.markdown-content :deep(.mermaid-container) {
  min-height: 40px;
  display: block;
}

.message-body.markdown-content :deep(.mermaid-container svg) {
  max-width: 100%;
  height: auto;
}

.message-body.markdown-content :deep(.mermaid-loading) {
  color: #8ba3b8;
  font-size: 13px;
  padding: 8px 0;
}

/* 表格样式 - 排除 diff-table */
.message-body.markdown-content :deep(table:not(.diff-table)) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  border: none;
}

.message-body.markdown-content :deep(table:not(.diff-table) th),
.message-body.markdown-content :deep(table:not(.diff-table) td) {
  border: none;
  padding: 8px 12px;
  text-align: left;
}

.message-body.markdown-content :deep(table:not(.diff-table) th) {
  background: var(--color-bg-hover);
  font-weight: 600;
}

.message-body.markdown-content :deep(table:not(.diff-table) tr:nth-child(even)) {
  background: var(--color-bg-secondary);
}

/* 终端 */
.terminal-wrapper {
  margin-top: 14px;
  border: none;
  border-radius: 10px;
  overflow: hidden;
  max-height: 600px;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-tertiary);
}

.terminal-host {
  background: var(--color-bg-secondary);
  flex: 1;
  min-height: 400px;
  overflow: hidden;
  user-select: text;
}

.terminal-history {
  margin-top: 14px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  border: none;
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-tertiary);
  /* max-height 由动态样式控制 */
}

.terminal-history-header {
  padding: 10px 16px;
  background: var(--color-bg-secondary);
  border-bottom: 0.5px solid var(--color-border-subtle);
  color: #8ba3b8;
  font-size: 13px;
  font-weight: 500;
}

.terminal-history-content {
  background: var(--color-bg-secondary);
  display: block;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 16px;
  margin: 0;
  overflow-x: auto;
  overflow-y: auto;
  color: #d6e4f0;
  white-space: pre;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 12px;
  line-height: 1.5;
}


/* 输入区 */
.input-area {
  background: var(--color-bg-secondary);
  border-top: 0.5px solid var(--color-border-subtle);
  padding-bottom: env(safe-area-inset-bottom, 0px);
  flex-shrink: 0;
}

.input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
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
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: 10px;
  color: #e6edf3;
  font-size: 14px;
}

.input-wrapper.single-line input:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-secondary);
}

.input-wrapper.single-line .send-btn {
  padding: 10px 20px;
}

/* 通用 */
.input-hint {
  margin: 0;
  font-size: 13px;
  color: #8ba3b8;
}

.send-btn {
  background: #36ff7c;
  border: none;
  border-radius: var(--tile-radius);
  color: #d6e4f0;
  font-size: 14px;
  font-weight: 600;
  padding: 11px 22px;
  cursor: pointer;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  background: #36ff7c;
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
  background: #20c8ff;
  border: none;
  border-radius: var(--tile-radius);
  color: #d6e4f0;
  font-size: 14px;
  font-weight: 600;
  padding: 11px 22px;
  cursor: pointer;
  white-space: nowrap;
}

.complete-btn:hover:not(:disabled) {
  background: #20c8ff;
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
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: 10px;
  padding: 14px;
  color: #e6edf3;
  font-size: 14px;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  resize: vertical;
  box-sizing: border-box;
}

.input-wrapper textarea:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-secondary);
}

/* 缓冲区指示器 */
/* Agent 运行中进度指示器 */
.agent-thinking-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius);
  margin: 8px 0;
  animation: fadeIn 0.3s ease-in-out;
}

.thinking-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--color-accent-subtle);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.thinking-text {
  font-size: 14px;
  color: #20c8ff;
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
  background: rgba(54, 255, 124, 0.15);
  border: none;
  border-radius: var(--tile-radius);
  margin: 8px 0;
  cursor: pointer;
}

.buffer-indicator:hover {
  background: rgba(54, 255, 124, 0.25);
  border-color: var(--color-success);
  transform: translateY(-1px);
}

.buffer-icon {
  font-size: 18px;
}

.buffer-text {
  font-size: 13px;
  color: #36ff7c;
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
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border-subtle);
}

.buffer-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #36ff7c;
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
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius-xs);
  color: #8ba3b8;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.buffer-panel-btn:hover {
  background: rgba(32, 200, 255, 0.15);
  border-color: var(--color-accent);
  color: #20c8ff;
}

.buffer-panel-btn.close-btn:hover {
  background: rgba(255, 60, 72, 0.15);
  border-color: var(--color-error);
  color: #ff3c48;
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
  background: var(--color-bg-tertiary);
  border: none;
  padding: 14px 16px;
  color: #e6edf3;
  font-size: 14px;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  resize: vertical;
  box-sizing: border-box;
  outline: none;
}

.buffer-edit-textarea::placeholder {
  color: #8ba3b8;
}

.buffer-panel-footer {
  padding: 12px 16px;
  background: var(--color-bg-tertiary);
  border-top: 1px solid var(--color-border-subtle);
  display: flex;
  justify-content: flex-end;
}

.buffer-save-btn {
  padding: 8px 16px;
  background: rgba(32, 200, 255, 0.15);
  border: none;
  border-radius: var(--tile-radius-xs);
  color: #20c8ff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.buffer-save-btn:hover:not(:disabled) {
  background: rgba(32, 200, 255, 0.25);
  border-color: var(--color-accent);
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
    border-radius: var(--tile-radius-sm);
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
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius);
  color: #8ba3b8;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.action-btn:hover {
  background: rgba(32, 200, 255, 0.15);
  border-color: var(--color-accent);
  color: #20c8ff;
  transform: translateY(-1px);
}

.action-btn:active {
  transform: translateY(0);
}

.clear-buffer-btn:hover {
  background: rgba(255, 60, 72, 0.15);
  border-color: var(--color-error);
  color: #ff3c48;
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
  border: none;
  border-radius: var(--tile-radius-xs);
  color: #8ba3b8;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.cancel-btn:hover {
  background: #0b1424;
  color: #e6edf3;
}

.interrupt-wrapper {
  padding: 12px 16px;
}

.interrupt-btn {
  width: 100%;
  padding: 8px;
  background: #ff3c48;
  border: none;
  border-radius: var(--tile-radius-xs);
  color: #d6e4f0;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.interrupt-btn:hover {
  background: #ff3c48;
}

/* 模态框 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3000;
  padding: 20px;
}

.modal-content {
  background: var(--color-bg-secondary);
  border: none;
  border-radius: 14px;
  padding: 28px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.modal-content h3 {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 600;
  color: #e6edf3;
}

.modal {
  background: var(--color-bg-secondary);
  border: none;
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
  color: #8ba3b8;
  letter-spacing: 0.01em;
}

.form-group input {
  width: 100%;
  padding: 11px 14px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
}

.form-group input:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-secondary);
}

.form-group select {
  width: 100%;
  padding: 11px 14px;
  background: var(--color-bg-tertiary);
  border: none;
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
  border-color: var(--color-accent);
  background-color: var(--color-bg-secondary);
}

.form-group select option {
  background: #080c16;
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
  background: var(--color-bg-hover);
  border: none;
  border-radius: var(--tile-radius);
  font-size: 22px;
  color: #8ba3b8;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background: rgba(255, 60, 72, 0.15);
  color: #ff3c48;
  transform: rotate(90deg);
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 24px;
}
.acl-user-list {
  max-height: 150px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 12px;
  background: var(--color-bg-tertiary);
  border-radius: 8px;
}
.acl-user-list .checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #e6edf3;
  cursor: pointer;
  padding: 4px 0;
}
.acl-user-list .checkbox-label input[type="checkbox"] {
  margin: 0;
  cursor: pointer;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.primary-btn {
  padding: 10px 20px;
  background: #36ff7c;
  border: none;
  border-radius: 9px;
  color: #d6e4f0;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.primary-btn:hover:not(:disabled) {
  background: #36ff7c;
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
  background: #ff3c48;
  border: none;
  border-radius: 9px;
  color: #d6e4f0;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
}

.danger-btn:hover:not(:disabled) {
  background: #ff3c48;
  transform: translateY(-1px);
}

.danger-btn:active:not(:disabled) {
  transform: translateY(0);
}

.danger-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}



.ghost-btn {
  padding: 10px 20px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.ghost-btn:hover {
  background: var(--color-bg-secondary);
  border-color: var(--color-border-subtle);
  transform: translateY(-1px);
}



/* 移动端适配 */
@media (max-width: 768px) {
  .app {
    background: var(--color-bg-secondary);
  }
  
  .app-header {
    padding: 12px 16px;
    padding-top: calc(12px + env(safe-area-inset-top, 0px));
    padding-left: max(16px, env(safe-area-inset-left, 0px));
    padding-right: max(16px, env(safe-area-inset-right, 0px));
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .mobile-header-actions {
    order: 2;
  }

  .header-title {
    order: 1;
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
  background: var(--color-bg-tertiary);
  border-color: var(--color-accent-subtle);
  color: #20c8ff;
}

.completion-btn:hover:not(:disabled) {
  background: var(--color-bg-hover);
  border-color: var(--color-accent);
}

.completion-btn:disabled {
  opacity: 0.3;
}

.error-message {
  background-color: #ff3c48;
  color: white;
  padding: 12px 16px;
  border-radius: var(--tile-radius-xs);
  margin-bottom: 16px;
  font-size: 14px;
  text-align: center;
}

/* 终端面板 */
.terminal-panel {
  position: fixed;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.terminal-panel-active {
  border-color: var(--color-accent) !important;
  box-shadow: 0 0 0 1px var(--color-accent), 0 0 20px rgba(32, 200, 255, 0.15) !important;
}

.terminal-panel-dragging {
  user-select: none;
}

.terminal-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border-subtle);
  border-radius: 6px 6px 0 0;
  cursor: move;
  min-height: 32px;
}

.terminal-panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

.terminal-panel-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.terminal-node-select {
  height: 32px;
  min-width: 168px;
  max-width: 240px;
  padding: 0 32px 0 12px;
  border: none;
  border-radius: var(--tile-radius);
  background: var(--color-bg-hover);
  color: #d6e4f0;
  font-size: 13px;
  line-height: 32px;
  outline: none;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.terminal-node-select:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-subtle);
}

.terminal-node-select:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2px rgba(32, 200, 255, 0.2);
}

.terminal-node-select option {
  color: #d6e4f0;
}

.terminal-panel-actions {
  display: flex;
  gap: 8px;
}

.terminal-tabs {
  display: flex;
  gap: 2px;
  padding: 4px;
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border-subtle);
}

.terminal-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: 4px;
  font-size: 12px;
  color: #8ba3b8;
  cursor: pointer;
}

.terminal-tab:hover {
  background: var(--color-bg-hover);
  color: #20c8ff;
}

.terminal-tab.active {
  background: var(--color-bg-tertiary);
  color: #20c8ff;
  border-color: var(--color-accent-subtle);
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
  background: rgba(255, 60, 72, 0.2);
  color: #ff3c48;
  border-radius: 3px;
  cursor: pointer;
}

.terminal-tab-close:hover {
  background: rgba(255, 60, 72, 0.4);
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
  background: var(--color-bg-hover);
  border: none;
  border-radius: var(--tile-radius-xs);
  padding: 4px 8px;
  color: #8ba3b8;
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
  background: var(--color-bg-secondary);
  border: none;
  border-radius: var(--tile-radius);
  color: #e6edf3;
  font-size: 14px;
  z-index: 9999;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);

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
  color: #36ff7c;
}

.toast-error .toast-icon {
  background: rgba(255, 60, 72, 0.2);
  color: #ff3c48;
}

.toast-info .toast-icon {
  background: rgba(32, 200, 255, 0.2);
  color: #20c8ff;
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
  color: #8ba3b8;
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
  user-select: text;
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

  .mobile-only {
    display: flex !important;
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
    border: 1px solid var(--color-border-subtle) !important;
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
    background: var(--color-bg-secondary);
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
    border-radius: var(--tile-radius-sm);
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

  /* ========== Panel 移动端强制单 Panel ========== */
  .panel-grid {
    grid-template-columns: 1fr !important;
    grid-template-rows: 1fr !important;
    padding: 0 !important;
    gap: 0 !important;
    height: 100% !important;
    min-height: 0 !important;
  }

  .session-panel {
    border-radius: 0 !important;
    border: none !important;
  }
}

/* ========== Toggle Switch 样式 ========== */
.toggle-wrapper {
  display: flex !important;
  align-items: center !important;
  justify-content: flex-start;
  gap: 16px;
  padding: 16px 20px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toggle-wrapper:hover {

  border-color: var(--color-border-subtle);
  outline-color: rgba(32, 200, 255, 0.4);
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
  background-color: var(--color-bg-tertiary);
  border: none;
  box-shadow: var(--tile-shadow), var(--tile-shadow-inset);
  border-radius: var(--tile-radius);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  
  /* 外描边效果 */
  outline: 1px solid rgba(26, 42, 58, 0.4);
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


  border-radius: 50%;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  border: none;
}

.toggle-input:checked + .toggle-slider {
  background: linear-gradient(135deg, #20c8ff 0%, #0b6ea8 100%);
  border-color: var(--color-border-active);
  box-shadow: 0 4px 16px rgba(0, 122, 255, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  outline-color: rgba(32, 200, 255, 0.5);
}

.toggle-input:checked + .toggle-slider:before {
  transform: translateX(22px);
  background-color: #d6e4f0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  border-color: var(--color-border-subtle);
}

/* Hover 状态 */
.toggle-switch:hover .toggle-slider {

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
  color: #8ba3b8;
  line-height: 1.4;
}

/* ========== Toggle Switch 样式结束 ========== */

/* ========== Diff 浮动窗口样式 ========== */
.diff-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3000;
  padding: 20px;
}

.diff-modal {
  background: var(--color-bg-secondary);
  border: none;
  border-radius: 14px;
  width: 100%;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.diff-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 0.5px solid var(--color-border-subtle);
  background: var(--color-bg-secondary);
}

.diff-modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #e6edf3;
}

.diff-modal-content {
  flex: 1;
  overflow: auto;
  padding: 20px;
  background: var(--color-bg-tertiary);
}

.diff-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #8ba3b8;
  font-size: 14px;
}

.diff-error {
  color: #ff3c48;
  padding: 16px;
  text-align: center;
  font-size: 14px;
}

.diff-empty {
  color: #8ba3b8;
  padding: 16px;
  text-align: center;
  font-size: 14px;
}

.diff-raw {
  margin: 0;
  padding: 16px;
  background: var(--color-bg-tertiary);
  border-radius: var(--tile-radius);
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #e6edf3;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
}

/* ========== Diff 浮动窗口样式结束 ========== */

/* ========== Rules 浮动窗口样式 ========== */
.rules-modal {
  max-width: 90vw;
}

.rules-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.rules-table th,
.rules-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 0.5px solid var(--color-border-subtle);
}

.rules-table th {
  background: var(--color-bg-secondary);
  color: #8ba3b8;
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.rules-table td {
  color: #e6edf3;
}

.rules-table tr:hover td {
  background: var(--color-bg-secondary);
}

.rule-loaded {
  color: #36ff7c;
}

.rule-not-loaded {
  color: #8ba3b8;
}

.rules-loaded-content-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border-subtle);
}

.rules-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #8ba3b8;
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.rules-loaded-content {
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius-xs);
  padding: 12px;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: #e6edf3;
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 400px;
  overflow-y: auto;
}

.rule-not-loaded {
  color: #8ba3b8;
}

.rule-preview {
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #8ba3b8;
  font-size: 12px;
}

.tools-section-title {
  color: #e6edf3;
  font-size: 14px;
  font-weight: 600;
  margin: 16px 0 8px 0;
  padding: 0 12px;
}

.tools-section-title:first-child {
  margin-top: 0;
}

/* ========== Rules 浮动窗口样式结束 ========== */
</style>