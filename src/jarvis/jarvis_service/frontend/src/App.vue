<template>
  <div class="app" :class="{ 'not-connected': showConnectModal }">
    <!-- 主宠物挂件：全局浮动宠物（放技能/拖拽/贴边），长按可一句话创建 Agent -->
    <PetWidget
      ref="petWidgetRef"
      :isConnected="!!socket && !showConnectModal"
      :windowWidth="windowWidth"
      :agentList="agentList"
      :agentStatuses="agentStatuses"
      :isWaitingInput="isWaitingInput"
      :currentAgentId="currentAgentId"
      :nodes="availableNodeOptions"
      :getStatusClass="getStatusClass"
      :extensionSessions="topologyExtensionSessions"
      :daemonSessions="topologyDaemonSessions"
      :localDaemonOnline="localDaemonOnline"
      @petSyncStatus="petSyncAllStatus"
      @petInterruptCurrent="petInterruptCurrent"
      @petGotoWaiting="petGotoWaitingAgent"
      @petToggleSidebar="openWorkspaceAgentList"
      @petOpenTopology="openTopologyOverlay"
      @petOpenCommandPalette="openCommandPalette()"
      @openQuickCreate="openQuickCreateAgent"
    />

    <!-- 主内容区 -->

    <!-- 主内容区 -->

    <!-- 主内容区 -->
    <div class="main-content-wrapper">
    <!-- Panel 网格布局 -->
    <main class="panel-grid" :style="panelGridStyle">
      <!-- 唯一容器：编辑器面板（所有 panel 都在编辑器内部打开，不再平铺渲染） -->
      <!-- 内嵌编辑器面板 -->
      <WorkspacePanel
        v-if="showWorkspacePanel"
        ref="workspacePanelRef"
        :visible="showWorkspacePanel"
        :active="activeWindow === 'workspace'"
        :interaction="workspacePanelInteraction"
        :panelStyle="workspacePanelStyle"
        :agentName="activeWorkspaceSession?.agent_name"
        :activeTab="activeWorkspaceTab"
        :activeTabPath="activeWorkspaceTabPath"
        :tabs="workspaceTabs"
        :isMaximized="isWorkspaceMaximized"
        :showSidebar="showWorkspaceSidebar"
        :sidebarView="workspaceSidebarView"
        :mainView="workspaceMainView"
        :resizeDirections="workspaceResizeDirections"
        :embedded="true"
        :isAdmin="!!auth.userInfo?.is_admin"
        :isEditable="isWorkspaceEditable"
        :hasActiveTab="!!activeWorkspaceTabPath"
        :pluginSidebarViews="pluginSidebarViews"
        :pluginToolPanels="pluginToolPanels"
        @focus="focusWindow('workspace')"
        @startMove="startWorkspacePanelMove"
        @toggleMaximize="toggleWorkspaceMaximize"
        @save="saveActiveWorkspaceTab"
        @close="closeWorkspacePanel"
        @activateTab="activateWorkspaceTab"
        @closeTab="closeWorkspaceTab"
        @tabContextMenu="(path, event) => openTabContextMenu(null, path, event)"
        @toggleEditable="toggleWorkspaceEditable"
        @setSidebarView="toggleWorkspaceSidebarView"
        @setMainView="toggleWorkspaceMainView"
        @startResize="startWorkspacePanelResize"
        @openSettings="showSettingsModal = true; pushOverlayState()"
        @openDocs="openDocs()"
        @openAdmin="showAdminPanel = true; pushOverlayState()"
        @openAbout="openAbout()"
        @openTopology="openTopologyOverlay()"
      >
        <template #sidebar>
          <aside v-if="showWorkspaceSidebar" class="workspace-sidebar" :style="{ width: workspaceSidebarWidth + 'px' }">
            <div class="workspace-sidebar-resize-handle" @mousedown="startWorkspaceSidebarResize($event)"></div>
            <div class="workspace-sidebar-header">
              <span class="workspace-sidebar-title">{{ workspaceSidebarTitle }}</span>
              <button class="icon-btn-small workspace-sidebar-close-mobile" tabindex="-1" @mousedown.prevent @click="closeWorkspaceSidebar" title="关闭侧边栏">✕</button>
              <button class="icon-btn-small workspace-sidebar-close-desktop" tabindex="-1" @mousedown.prevent @click="closeWorkspaceSidebar" title="关闭侧边栏">✕</button>
            </div>
            <div v-if="workspaceSidebarView === 'agents'" class="workspace-sidebar-content workspace-sidebar-agents">
              <AgentSidebar
                :visible="true"
                :embedded="true"
                :resizeState="{ active: false }"
                :sidebarStyle="{ width: '100%' }"
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
                @close="setWorkspaceSidebarView('files')"
                @toggleBatchMode="toggleBatchMode"
                @createAgent="openCreateAgentModal"
                @orchestrate="openOrchestrateModal"
                @agentClick="onWorkspaceSidebarAgentClick"
                @agentContextMenu="onSidebarAgentContextMenu"
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
                @renameGroup="renameAgentGroup"
                @deleteGroup="deleteAgentGroup"
                @editAccess="editAgentAccess"
              />
            </div>
            <div v-else-if="workspaceSidebarView === 'files'" class="workspace-sidebar-content">
              <div class="workspace-file-tree-panel">
                <!-- 按节点打开任意目录（无需创建 Agent 即可浏览/编辑文件） -->
                <button class="workspace-open-dir-btn" @click="openOpenDirDialog" title="选择节点与目录并打开">
                  <span class="workspace-open-dir-icon" v-html="UI_ICONS.folder"></span>
                  <span>打开目录</span>
                </button>
                <!-- 活跃 Agent 节点列表 -->
                <div
                  v-for="agent in activeAgents"
                  :key="agent.agent_id"
                  class="workspace-agent-node"
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
                    <span class="tree-node-icon agent-icon">
                      <svg v-if="agent.agent_type === 'code_agent'" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M5.5 4.5 2.5 8l3 3.5M10.5 4.5l3 3.5-3 3.5"/>
                        <path d="M9.5 3.5l-3 9"/>
                      </svg>
                      <svg v-else viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <rect x="3" y="5" width="10" height="7" rx="2"/>
                        <circle cx="5.5" cy="8.5" r="0.7" fill="currentColor" stroke="none"/>
                        <circle cx="10.5" cy="8.5" r="0.7" fill="currentColor" stroke="none"/>
                        <path d="M6 3.5 8 5l2-1.5"/>
                        <path d="M5 12v1.5M11 12v1.5"/>
                        <path d="M3 10H1.5M14.5 10H13"/>
                      </svg>
                    </span>
                    <span class="tree-node-text agent-name">{{ agent.name || agent.agent_id }}</span>
                    <span class="agent-status" :class="getStatusClass(agent)">{{ getStatusClass(agent) === 'stopped' ? '⏹' : getStatusClass(agent) === 'running' ? '▶' : '⏸' }}</span>
                    <span class="agent-node-id">{{ getNodeDisplayName(agent.node_id) }}</span>
                  </div>
                  <!-- Agent 的文件树 -->
                  <div v-if="expandedAgents.has(agent.agent_id)" class="agent-file-tree">
                    <div
                      class="workspace-file-tree-root"
                      :class="{ 'drag-drop-target': fileTreeDropTargetPath === String(agent.working_dir || '').replace(/\/+$/, '') }"
                      @click.stop="ensureWorkspaceSidebarFileTree(agent)"
                      @contextmenu.prevent.stop="openFileTreeContextMenu(agent, null, $event)"
                      @dragover="handleFileTreeDragOver($event, agent.working_dir)"
                      @dragleave="handleFileTreeDragLeave(agent.working_dir)"
                      @drop="handleFileTreeDrop($event, agent.agent_id, agent.working_dir)"
                    >
                      {{ getWorkingDirDisplay(agent.working_dir) }}
                    </div>
                    <div v-if="!(fileTreeState.get(agent.agent_id)?.length > 0)" class="workspace-file-tree-empty">
                      当前工作目录下暂无可显示内容
                    </div>
                    <div v-else class="workspace-file-tree-list" tabindex="0" :data-agent-id="agent.agent_id" @keydown="handleFileTreeKeydown($event, agent.agent_id)">
                      <div
                        v-for="visibleNode in getVisibleFileTreeNodes(agent.agent_id)"
                        :key="visibleNode.node.path"
                        class="tree-node workspace-tree-node"
                        :data-node-path="visibleNode.node.path"
                      >
                        <div
                          class="tree-node-content"
                          :class="{
                            'keyboard-selected': fileTreeSelectedAgentId === agent.agent_id && fileTreeSelectedPath === visibleNode.node.path,
                            'drag-drop-target': visibleNode.node.type === 'directory' && fileTreeDropTargetPath === String(visibleNode.node.path).replace(/\/+$/, '')
                          }"
                          :style="{ paddingLeft: `${8 + visibleNode.depth * 20}px` }"
                          draggable="true"
                          @click.stop="selectFileTreeNode(agent.agent_id, visibleNode.node); handleFileTreeNodeClick(agent.agent_id, visibleNode.node)"
                          @contextmenu.prevent.stop="openFileTreeContextMenu(agent, visibleNode.node, $event)"
                          @dragstart="handleFileTreeDragStart($event, agent.agent_id, visibleNode.node)"
                          @dragend="handleFileTreeDragEnd"
                          @dragover="visibleNode.node.type === 'directory' && handleFileTreeDragOver($event, visibleNode.node.path)"
                          @dragleave="visibleNode.node.type === 'directory' && handleFileTreeDragLeave(visibleNode.node.path)"
                          @drop="visibleNode.node.type === 'directory' && handleFileTreeDrop($event, agent.agent_id, visibleNode.node.path)"
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
                            v-html="getFileTypeIcon(visibleNode.node)"
                          ></span>
                          <span
                            class="tree-node-text"
                            :class="visibleNode.node.type === 'directory' ? 'directory' : 'file'"
                          >{{ visibleNode.node.name }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- 虚拟目录会话（未创建 Agent 时直接打开的目录） -->
                <div
                  v-for="session in virtualWorkspaceSessions"
                  :key="session.agent_id"
                  class="workspace-agent-node virtual-dir"
                >
                  <div class="tree-node-content agent-node-content" @click.stop="toggleAgentExpanded(session.agent_id)">
                    <span
                      class="tree-node-icon expand-arrow"
                      :class="{ expanded: expandedAgents.has(session.agent_id) }"
                    >▶</span>
                    <span class="tree-node-icon agent-icon" v-html="UI_ICONS.monitor"></span>
                    <span class="tree-node-text agent-name">{{ session.agent.name }}</span>
                    <span class="agent-node-id">{{ getWorkingDirDisplay(session.agent.working_dir) }}</span>
                    <button
                      class="agent-node-remove"
                      title="移除该目录"
                      @click.stop="removeWorkspaceDir(session.agent_id)"
                    >✕</button>
                  </div>
                  <div v-if="expandedAgents.has(session.agent_id)" class="agent-file-tree">
                    <div class="workspace-file-tree-root"
                      :class="{ 'drag-drop-target': fileTreeDropTargetPath === String(session.agent.working_dir || '').replace(/\/+$/, '') }"
                      @click.stop="ensureWorkspaceSidebarFileTree(session.agent)" @contextmenu.prevent.stop="openFileTreeContextMenu(session.agent, null, $event)"
                      @dragover="handleFileTreeDragOver($event, session.agent.working_dir)"
                      @dragleave="handleFileTreeDragLeave(session.agent.working_dir)"
                      @drop="handleFileTreeDrop($event, session.agent_id, session.agent.working_dir)">
                      {{ getWorkingDirDisplay(session.agent.working_dir) }}
                    </div>
                    <div v-if="!(fileTreeState.get(session.agent_id)?.length > 0)" class="workspace-file-tree-empty">
                      当前工作目录下暂无可显示内容
                    </div>
                    <div v-else class="workspace-file-tree-list" tabindex="0" :data-agent-id="session.agent_id" @keydown="handleFileTreeKeydown($event, session.agent_id)">
                      <div
                        v-for="visibleNode in getVisibleFileTreeNodes(session.agent_id)"
                        :key="visibleNode.node.path"
                        class="tree-node workspace-tree-node"
                        :data-node-path="visibleNode.node.path"
                      >
                        <div
                          class="tree-node-content"
                          :class="{
                            'keyboard-selected': fileTreeSelectedAgentId === session.agent_id && fileTreeSelectedPath === visibleNode.node.path,
                            'drag-drop-target': visibleNode.node.type === 'directory' && fileTreeDropTargetPath === String(visibleNode.node.path).replace(/\/+$/, '')
                          }"
                          :style="{ paddingLeft: `${8 + visibleNode.depth * 20}px` }"
                          draggable="true"
                          @click.stop="selectFileTreeNode(session.agent_id, visibleNode.node); handleFileTreeNodeClick(session.agent_id, visibleNode.node)"
                          @contextmenu.prevent.stop="openFileTreeContextMenu(session.agent, visibleNode.node, $event)"
                          @dragstart="handleFileTreeDragStart($event, session.agent_id, visibleNode.node)"
                          @dragend="handleFileTreeDragEnd"
                          @dragover="visibleNode.node.type === 'directory' && handleFileTreeDragOver($event, visibleNode.node.path)"
                          @dragleave="visibleNode.node.type === 'directory' && handleFileTreeDragLeave(visibleNode.node.path)"
                          @drop="visibleNode.node.type === 'directory' && handleFileTreeDrop($event, session.agent_id, visibleNode.node.path)"
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
                            v-html="getFileTypeIcon(visibleNode.node)"
                          ></span>
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
                        class="workspace-agent-node stopped"
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
                          <span class="tree-node-icon agent-icon">
                            <svg v-if="agent.agent_type === 'code_agent'" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                              <path d="M5.5 4.5 2.5 8l3 3.5M10.5 4.5l3 3.5-3 3.5"/>
                              <path d="M9.5 3.5l-3 9"/>
                            </svg>
                            <svg v-else viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                              <rect x="3" y="5" width="10" height="7" rx="2"/>
                              <circle cx="5.5" cy="8.5" r="0.7" fill="currentColor" stroke="none"/>
                              <circle cx="10.5" cy="8.5" r="0.7" fill="currentColor" stroke="none"/>
                              <path d="M6 3.5 8 5l2-1.5"/>
                              <path d="M5 12v1.5M11 12v1.5"/>
                              <path d="M3 10H1.5M14.5 10H13"/>
                            </svg>
                          </span>
                          <span class="tree-node-text agent-name">{{ agent.name || agent.agent_id }}</span>
                          <span class="agent-status" :class="getStatusClass(agent)">{{ getStatusClass(agent) === 'stopped' ? '⏹' : getStatusClass(agent) === 'running' ? '▶' : '⏸' }}</span>
                          <span class="agent-node-id">{{ getNodeDisplayName(agent.node_id) }}</span>
                        </div>
                        <!-- Agent 的文件树 -->
                        <div v-if="expandedAgents.has(agent.agent_id)" class="agent-file-tree">
                          <div
                            class="workspace-file-tree-root"
                            :class="{ 'drag-drop-target': fileTreeDropTargetPath === String(agent.working_dir || '').replace(/\/+$/, '') }"
                            @click.stop="ensureWorkspaceSidebarFileTree(agent)"
                            @contextmenu.prevent.stop="openFileTreeContextMenu(agent, null, $event)"
                            @dragover="handleFileTreeDragOver($event, agent.working_dir)"
                            @dragleave="handleFileTreeDragLeave(agent.working_dir)"
                            @drop="handleFileTreeDrop($event, agent.agent_id, agent.working_dir)"
                          >
                            {{ getWorkingDirDisplay(agent.working_dir) }}
                          </div>
                          <div v-if="!(fileTreeState.get(agent.agent_id)?.length > 0)" class="workspace-file-tree-empty">
                            当前工作目录下暂无可显示内容
                          </div>
                          <div v-else class="workspace-file-tree-list" tabindex="0" :data-agent-id="agent.agent_id" @keydown="handleFileTreeKeydown($event, agent.agent_id)">
                            <div
                              v-for="visibleNode in getVisibleFileTreeNodes(agent.agent_id)"
                              :key="visibleNode.node.path"
                              class="tree-node workspace-tree-node"
                              :data-node-path="visibleNode.node.path"
                            >
                              <div
                                class="tree-node-content"
                                :class="{
                                  'keyboard-selected': fileTreeSelectedAgentId === agent.agent_id && fileTreeSelectedPath === visibleNode.node.path,
                                  'drag-drop-target': visibleNode.node.type === 'directory' && fileTreeDropTargetPath === String(visibleNode.node.path).replace(/\/+$/, '')
                                }"
                                :style="{ paddingLeft: `${8 + visibleNode.depth * 20}px` }"
                                draggable="true"
                                @click.stop="selectFileTreeNode(agent.agent_id, visibleNode.node); handleFileTreeNodeClick(agent.agent_id, visibleNode.node)"
                                @contextmenu.prevent.stop="openFileTreeContextMenu(agent, visibleNode.node, $event)"
                                @dragstart="handleFileTreeDragStart($event, agent.agent_id, visibleNode.node)"
                                @dragend="handleFileTreeDragEnd"
                                @dragover="visibleNode.node.type === 'directory' && handleFileTreeDragOver($event, visibleNode.node.path)"
                                @dragleave="visibleNode.node.type === 'directory' && handleFileTreeDragLeave(visibleNode.node.path)"
                                @drop="visibleNode.node.type === 'directory' && handleFileTreeDrop($event, agent.agent_id, visibleNode.node.path)"
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
                                  v-html="getFileTypeIcon(visibleNode.node)"
                                ></span>
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
                <!-- 无 Agent 提示（已通过「打开目录」打开虚拟目录时不再提示） -->
                <div v-if="agentList.length === 0 && virtualWorkspaceSessions.length === 0" class="workspace-file-tree-empty">
                  暂无 Agent，请先创建 Agent，或点击上方「打开目录」
                </div>
              </div>
            </div>
            <div v-else-if="workspaceSidebarView === 'search'" class="workspace-sidebar-content">
              <div class="workspace-global-search-panel">
                <select
                  v-if="activeAgents.length"
                  class="workspace-sidebar-agent-select"
                  :value="effectiveGlobalSearchAgentId || ''"
                  title="选择搜索的 Agent"
                  @change="globalSearchAgentId = $event.target.value"
                >
                  <option value="" disabled>选择 Agent</option>
                  <option v-for="agent in activeAgents" :key="agent.agent_id" :value="agent.agent_id">
                    {{ agent.name || agent.agent_id }}
                  </option>
                </select>
                <div class="workspace-global-search-mode-tabs">
                  <button
                    class="workspace-global-search-mode-tab"
                    :class="{ active: globalSearchMode === 'content' }"
                    :disabled="globalSearchLoading"
                    @click="setGlobalSearchMode('content')"
                  >内容</button>
                  <button
                    class="workspace-global-search-mode-tab"
                    :class="{ active: globalSearchMode === 'filename' }"
                    :disabled="globalSearchLoading"
                    @click="setGlobalSearchMode('filename')"
                  >文件名</button>
                </div>
                <input
                  v-model="globalSearchQuery"
                  class="workspace-global-search-input"
                  type="text"
                  :placeholder="globalSearchMode === 'filename' ? '按文件名模糊搜索...' : '全局搜索文件内容...'"
                  :disabled="globalSearchLoading || !effectiveGlobalSearchAgentId"
                  @keydown.enter.prevent="runGlobalSearch"
                >
                <input
                  v-model="globalSearchFileGlob"
                  class="workspace-global-search-input workspace-global-search-glob-input"
                  type="text"
                  placeholder="文件过滤，如 *.py,!tests/**"
                  :disabled="globalSearchLoading || !effectiveGlobalSearchAgentId"
                  @keydown.enter.prevent="runGlobalSearch"
                >
                <div class="workspace-global-search-toolbar">
                  <label class="workspace-global-search-toggle">
                    <input v-model="globalSearchCaseSensitive" type="checkbox">
                    <span>区分大小写</span>
                  </label>
                  <label v-if="globalSearchMode === 'content'" class="workspace-global-search-toggle">
                    <input v-model="globalSearchWholeWord" type="checkbox">
                    <span>全词匹配</span>
                  </label>
                  <div class="workspace-global-search-actions">
                    <button class="icon-btn workspace-global-search-btn" @click="runGlobalSearch" :disabled="globalSearchLoading || !effectiveGlobalSearchAgentId || !globalSearchQuery.trim()" :title="globalSearchMode === 'filename' ? '文件名搜索' : '全局搜索'" v-html="UI_ICONS.search"></button>
                    <button class="icon-btn workspace-global-search-btn" @click="clearGlobalSearch" :disabled="globalSearchLoading" title="清空搜索">✕</button>
                  </div>
                </div>
              </div>
              <div class="workspace-global-search-results">
                <div class="workspace-global-search-summary">
                  <span v-if="globalSearchLoading">搜索中...</span>
                  <span v-else-if="globalSearchError" class="error">{{ globalSearchError }}</span>
                  <span v-else-if="globalSearchExecuted && globalSearchMode === 'filename'">找到 {{ fileSearchResults.length }} 个文件（共扫描 {{ globalSearchTotalFiles }} 个）</span>
                  <span v-else-if="globalSearchExecuted">找到 {{ globalSearchTotalMatches }} 处匹配，分布在 {{ globalSearchTotalFiles }} 个文件</span>
                  <span v-else>{{ globalSearchMode === 'filename' ? '输入关键词并回车，可按文件名模糊搜索' : '输入关键词并回车，可在当前 Agent 工作目录中全局搜索' }}</span>
                </div>
                <template v-if="globalSearchMode === 'filename'">
                  <div v-if="!globalSearchLoading && globalSearchExecuted && fileSearchResults.length === 0 && !globalSearchError" class="workspace-global-search-empty">
                    未找到匹配文件
                  </div>
                  <button
                    v-for="result in fileSearchResults"
                    :key="result.file_path"
                    class="workspace-global-search-file-result"
                    @click="openFileSearchResult(result.file_path)"
                  >
                    <span class="workspace-global-search-file-result-name">{{ result.name }}</span>
                    <span class="workspace-global-search-file-result-path">{{ result.file_path }}</span>
                  </button>
                </template>
                <template v-else>
                  <div v-if="!globalSearchLoading && globalSearchExecuted && globalSearchResults.length === 0 && !globalSearchError" class="workspace-global-search-empty">
                    未找到匹配结果
                  </div>
                  <div v-for="result in globalSearchResults" :key="result.file_path" class="workspace-global-search-file-group">
                    <div class="workspace-global-search-file-path" @click="openWorkspaceFile(resolveAgentRelativePath(result.file_path, effectiveGlobalSearchAgentId.value))">
                      {{ result.file_path }}
                      <span class="workspace-global-search-file-count">({{ result.matches.length }})</span>
                    </div>
                    <button
                      v-for="match in result.matches"
                      :key="`${result.file_path}:${match.line_number}:${match.match_start}`"
                      class="workspace-global-search-match"
                      @click="openGlobalSearchResult(result.file_path, match.line_number, match.match_start, match.match_end)"
                    >
                      <span class="workspace-global-search-line">{{ match.line_number }}</span>
                      <span class="workspace-global-search-text">
                        {{ match.line_content.slice(0, match.match_start) }}<mark>{{ match.line_content.slice(match.match_start, match.match_end) }}</mark>{{ match.line_content.slice(match.match_end) }}
                      </span>
                    </button>
                  </div>
                </template>
              </div>
            </div>
            <div v-else-if="workspaceSidebarView === 'manage'" class="workspace-sidebar-content">
              <ManageSidebar
                view="manage"
                :daemonSessions="topologyDaemonSessions"
                :extensionSessions="topologyExtensionSessions"
                :installedScripts="manageInstalledScripts"
                :gatewayScripts="manageGatewayScripts"
                @refresh="refreshManageCapabilities"
              />
            </div>
            <div v-else-if="workspaceSidebarView === 'timers'" class="workspace-sidebar-content">
              <ManageSidebar
                view="timers"
                :timers="manageTimers"
              />
            </div>
            <div v-else-if="workspaceSidebarView === 'plugins'" class="workspace-sidebar-content">
              <PluginSidebar
                :fetchWithAuth="fetchWithAuth"
                :gatewayUrl="gatewayUrl"
                :getHttpProtocol="getHttpProtocol"
                :showToast="showToast"
                :availableNodeOptions="availableNodeOptions"
              />
            </div>
            <div v-else-if="isPluginSidebarView(workspaceSidebarView) && activePluginSidebarComp" class="workspace-sidebar-content">
              <component
                :is="activePluginSidebarComp"
                :workingDir="pluginSidebarWorkingDir"
                :agentInfo="pluginActiveAgentInfo"
                :userInfo="auth.userInfo || null"
                :nodes="availableNodeOptions"
                :gatewayUrl="gatewayUrl"
                :fetchWithAuth="fetchWithAuth"
                :getHttpProtocol="getHttpProtocol"
                :showToast="showToast"
              />
            </div>
            <div v-else-if="isPluginToolView(workspaceSidebarView) && activePluginToolPanelComp" class="workspace-sidebar-content">
              <component
                :is="activePluginToolPanelComp"
                :workingDir="pluginSidebarWorkingDir"
                :agentInfo="pluginActiveAgentInfo"
                :userInfo="auth.userInfo || null"
                :nodes="availableNodeOptions"
                :gatewayUrl="gatewayUrl"
                :fetchWithAuth="fetchWithAuth"
                :getHttpProtocol="getHttpProtocol"
                :showToast="showToast"
              />
            </div>
            <div v-else-if="workspaceSidebarView === 'orchestration'" class="workspace-sidebar-content workspace-sidebar-orchestration">
              <OrchestrationView
                :pipelines="pipelineList"
                :activeId="activePipelineId"
                mode="compact"
                @select="selectPipeline"
                @jump-agent="onOrchestrationJumpAgent"
                @expand="openOrchestrationOverlay"
                @remove="removePipeline"
                @approve="handleApproval('approve', $event)"
                @reject="handleApproval('reject', $event)"
                @retry="handleApproval('retry', $event)"
              />
            </div>
            <div v-else class="workspace-sidebar-content">
              <div class="workspace-git-panel">
                <select
                  v-if="activeAgents.length"
                  class="workspace-sidebar-agent-select"
                  :value="effectiveGitAgentId || ''"
                  title="选择 Git 的 Agent；选「跟随当前会话」则随编辑器会话联动"
                  @change="onGitAgentChange($event.target.value)"
                >
                  <option value="">跟随当前会话</option>
                  <option v-for="agent in activeAgents" :key="agent.agent_id" :value="agent.agent_id">
                    {{ agent.name || agent.agent_id }}
                  </option>
                </select>
                <!-- Git 管理目录：默认 Agent 根目录，也可指定任意 Git 目录（复用「打开目录」选择） -->
                <div class="workspace-git-dir-row">
                  <button class="workspace-open-dir-btn workspace-git-dir-btn" @click="openGitDirDialog" title="选择节点与目录作为 Git 管理目标">
                    <span class="workspace-open-dir-icon" v-html="UI_ICONS.folder"></span>
                    <span>选择 Git 目录</span>
                  </button>
                  <div v-if="gitCustomDir" class="workspace-git-dir-current" :title="gitCustomDir.path">
                    <span class="workspace-git-dir-label">目录</span>
                    <span class="workspace-git-dir-path">{{ gitCustomDir.path }}</span>
                    <button class="icon-btn-small" @click="clearGitCustomDir" title="清除自定义目录，回到 Agent 根目录">✕</button>
                  </div>
                </div>
                <div class="workspace-git-toolbar">
                  <span class="workspace-git-branch" :title="gitCurrentBranch || '未知分支'">
                    <svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M9.5 3.25a2.25 2.25 0 1 1 3 2.122V6A2.5 2.5 0 0 1 10 8.5H6a1 1 0 0 0-1 1v1.128a2.251 2.251 0 1 1-1.5 0V5.372a2.25 2.25 0 1 1 1.5 0v1.836A2.492 2.492 0 0 1 6 7h4a1 1 0 0 0 1-1v-.628A2.25 2.25 0 0 1 9.5 3.25Zm-6 0a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Zm8.25-.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5ZM4.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/></svg>
                    <span class="workspace-git-branch-name">{{ gitCurrentBranch || '无分支' }}</span>
                  </span>
                  <div class="workspace-git-toolbar-actions">
                    <template v-if="gitRangeSelectMode">
                      <span class="workspace-git-range-count" :title="'已选 ' + gitSelectedCommits.size + ' 个提交'">已选 {{ gitSelectedCommits.size }}</span>
                      <button class="icon-btn-small" @click="downloadGitPatch" :disabled="!gitSelectedCommits.size || gitPatchLoading" title="下载补丁（1 个为 .patch，多个为 .tar.gz）">⬇</button>
                      <button class="icon-btn-small" @click="exitGitRangeSelect" title="退出范围选择">✕</button>
                    </template>
                    <template v-else>
                      <button class="icon-btn-small" @click="viewGitTargetDiff" title="查看变更（当前 Git 目标 Agent 的 diff）">⇄</button>
                      <button class="icon-btn-small" @click="enterGitRangeSelect" title="选择范围生成下载补丁">☑</button>
                      <button class="icon-btn-small" @click="refreshGitView" :disabled="gitLogLoading" title="刷新">⟳</button>
                    </template>
                  </div>
                </div>
                <div class="workspace-git-summary">
                  <span v-if="gitLogLoading && !gitLog.length">加载中...</span>
                  <span v-else-if="gitLogError" class="error">{{ gitLogError }}</span>
                  <span v-else>{{ gitLogTotal !== null ? gitLogTotal : gitLog.length }} 个提交<span v-if="gitBranches.length"> · {{ gitBranches.length }} 分支</span><span v-if="gitTags.length"> · {{ gitTags.length }} 标签</span></span>
                </div>
                <div class="workspace-git-commit-list">
                  <template v-for="(commit, index) in gitLog" :key="commit.hash">
                    <div
                      class="workspace-git-commit"
                      :class="{ selected: gitSelectedCommit === commit.hash, 'range-selected': gitRangeSelectMode && gitSelectedCommits.has(commit.hash) }"
                      @click="gitRangeSelectMode ? toggleGitRangeSelect(commit) : toggleGitCommitDetail(commit)"
                      @contextmenu.prevent.stop="openGitCommitContextMenu(commit, $event)"
                    >
                      <div class="workspace-git-graph">
                        <svg viewBox="0 0 20 40" width="20" height="40" aria-hidden="true">
                          <line x1="10" y1="0" x2="10" y2="40" stroke="currentColor" stroke-width="1.5" class="git-graph-line" />
                          <circle cx="10" cy="20" :r="commit.parents && commit.parents.length > 1 ? 5 : 4" class="git-graph-dot" :class="{ 'git-graph-merge': commit.parents && commit.parents.length > 1 }" />
                        </svg>
                      </div>
                      <div class="workspace-git-commit-body">
                        <div class="workspace-git-commit-subject" :title="formatGitCommitTooltip(commit)">{{ commit.subject }}</div>
                        <div class="workspace-git-commit-meta">
                          <span class="workspace-git-refs" v-if="commit.refs && commit.refs.length">
                            <span v-for="ref in commit.refs" :key="ref" class="git-ref" :class="gitRefClass(ref)">{{ ref }}</span>
                          </span>
                          <span class="workspace-git-author">{{ commit.author }}</span>
                          <span class="workspace-git-hash">{{ shortGitHash(commit.hash) }}</span>
                          <span class="workspace-git-time">{{ formatGitRelativeTime(commit.date) }}</span>
                          <button
                            v-if="windowWidth < 768"
                            class="workspace-git-detail-btn"
                            title="查看完整 commit 信息"
                            @click.stop="showGitCommitInfoModal(commit)"
                          >详情</button>
                        </div>
                        <div v-if="gitSelectedCommit === commit.hash" class="workspace-git-commit-detail" @click.stop>
                          <div v-if="gitCommitDetailLoading" class="workspace-git-detail-empty">加载文件列表...</div>
                          <div v-else-if="!gitCommitFiles.length" class="workspace-git-detail-empty">无文件变更</div>
                          <template v-else>
                            <div class="workspace-git-detail-summary">共 {{ gitCommitFiles.length }} 个文件变更</div>
                            <button
                              v-for="file in gitCommitFiles"
                              :key="file.path"
                              class="workspace-git-file"
                              :class="{ active: gitSelectedFile === file.path }"
                              @click="viewGitFileDiff(commit.hash, file.path)"
                            >
                              <span class="workspace-git-file-status" :class="'git-status-' + gitFileStatus(file)">{{ gitFileStatus(file) }}</span>
                              <span class="workspace-git-file-path" :title="file.path">{{ file.path }}</span>
                              <span class="workspace-git-file-stat">
                                <span v-if="file.additions" class="git-add-stat">+{{ file.additions }}</span>
                                <span v-if="file.deletions" class="git-del-stat">-{{ file.deletions }}</span>
                              </span>
                            </button>

                          </template>
                        </div>
                      </div>
                    </div>
                  </template>
                  <div v-if="!gitLogLoading && !gitLogError && !gitLog.length" class="workspace-git-empty">暂无提交记录</div>
                  <button
                    v-if="gitLogHasMore && !gitLogLoading"
                    class="workspace-git-load-more"
                    @click="fetchGitLog(true)"
                  >加载更多</button>
                </div>
              </div>
            </div>
          </aside>
        </template>
        <!-- 工作区恒为 pane 树（分割数量≥1）：唯一 leaf 承载主区域视图，
             WorkspacePanel 恒走 pane 树渲染路径，不再存在未分割单例渲染。 -->
        <template #pane-tree>
          <WorkspacePaneTree
            :node="workspacePaneTree"
            :activePaneId="activePaneId"
            :maximizedPaneId="maximizedPaneId"
            :canSplit="windowWidth > 768"
            :getTitle="getWorkspacePaneTitle"
            :getStatus="getWorkspacePaneStatus"
            @activate="activateWorkspacePane"
            @split="splitWorkspacePane"
            @close="closeWorkspacePane"
            @maximize="toggleMaximizeWorkspacePane"
            @startResize="startWorkspacePaneResize"
          >
            <template #pane-content="{ pane, active }">
              <div class="workspace-pane-content-slot">
                <template v-if="pane.view === 'empty'">
                  <!-- 空 pane：新分割出来的区域不带任何属性（既非文件也非会话），
                       仅显示中性占位，等待用户显式打开文件/会话。 -->
                  <div class="workspace-pane-placeholder" @click="activateWorkspacePane(pane.id)">
                    <div class="workspace-placeholder-icon">▢</div>
                    <div class="workspace-placeholder-title">空区域</div>
                    <div class="workspace-placeholder-text">在左侧打开文件或点击 Agent，即可在此区域显示内容。</div>
                  </div>
                </template>
                <template v-else-if="pane.view === 'file'">
                  <!-- 文件标签：渲染在本 pane 内部顶部（不再横跨整个工作区）。
                       已分割时每个 pane 用自己独立的标签列表（getPaneTabs），
                       关闭某个 pane 的标签不会影响其他 pane。 -->
                  <div v-if="getPaneTabs(pane.id).length > 0" class="workspace-tabs workspace-pane-tabs" @mousedown="activateWorkspacePane(pane.id)">
                    <div
                      v-for="tab in getPaneTabs(pane.id)"
                      :key="tab.path"
                      class="workspace-tab"
                      :class="{ active: workspaceViewPanes.get(pane.id) === tab.path }"
                      @click="activateWorkspacePane(pane.id); activateWorkspaceTab(tab.path)"
                      @contextmenu.prevent.stop="openTabContextMenu(pane.id, tab.path, $event)"
                    >
                      <span class="workspace-tab-name">{{ tab.name }}</span>
                      <span v-if="tab.isDirty" class="workspace-tab-dirty">●</span>
                      <button class="workspace-tab-close" tabindex="-1" @mousedown.prevent @click.stop="closeWorkspaceTab(tab.path, pane.id)">✕</button>
                    </div>
                    <!-- 每个 pane 自己的保存 / 只读开关：作用于本 pane 当前文件 -->
                    <div class="workspace-pane-actions">
                      <button
                        class="workspace-pane-action"
                        :disabled="!workspaceViewPanes.get(pane.id)"
                        tabindex="-1"
                        @mousedown.prevent
                        @click.stop="savePaneWorkspaceFile(pane.id)"
                        title="保存本区域文件"
                      ><span v-html="UI_ICONS.save"></span></button>
                      <button
                        class="workspace-pane-action"
                        :class="{ editable: isWorkspaceEditable }"
                        :disabled="!workspaceViewPanes.get(pane.id)"
                        tabindex="-1"
                        @mousedown.prevent
                        @click.stop="toggleWorkspaceEditable()"
                        :title="isWorkspaceEditable ? '切换到只读模式' : '切换到编辑模式'"
                      ><span v-html="isWorkspaceEditable ? UI_ICONS.unlock : UI_ICONS.lock"></span></button>
                    </div>
                  </div>
                  <!-- Monaco 多实例：每个 file pane 各渲染一个真实编辑器容器（可编辑），
                       非激活 pane 只是没有焦点，不再是只读快照。 -->
                  <div
                    :ref="el => setSplitWorkspaceContainerRef(pane.id, el)"
                    :data-pane-id="pane.id"
                    class="workspace-monaco-container"
                    @mousedown="activateWorkspacePane(pane.id)"
                  ></div>
                </template>
                <template v-else-if="pane.view === 'diff'">
                  <!-- diff leaf：Git 提交文件 diff 作为独立 pane 内容（每个 pane 一个独立 DiffEditor 实例） -->
                  <div class="workspace-pane-diff-wrap" @mousedown="activateWorkspacePane(pane.id)">
                    <div v-if="pane.diff" class="workspace-diff-view">
                      <div class="workspace-diff-header">
                        <span class="workspace-diff-title" :title="(pane.diff.filePath || '') + '（点击可在编辑器中打开）'" @click="onDiffTitleClick($event, pane)">{{ pane.diff.filePath }}</span>
                        <span v-if="pane.diff.commitHash" class="workspace-diff-hash">{{ pane.diff.commitHash.slice(0, 7) }}</span>
                        <span v-if="pane.diff.truncated" class="workspace-diff-truncated">（已截断）</span>
                        <button class="workspace-diff-nav" @click.stop="navigatePaneDiff(pane.id, 'prev')" title="上一个差异">▲</button>
                        <button class="workspace-diff-nav" @click.stop="navigatePaneDiff(pane.id, 'next')" title="下一个差异">▼</button>
                        <button class="workspace-diff-toggle" @click.stop="togglePaneDiffShowFull(pane.id)" :title="pane.diff.showFull ? '只显示变更上下文区域' : '显示文件全文'">
                          {{ pane.diff.showFull ? '仅上下文' : '全文' }}
                        </button>
                        <button class="workspace-diff-toggle" @click.stop="togglePaneDiffSideBySide(pane.id)">
                          {{ pane.diff.sideBySide ? '内联' : '并排' }}
                        </button>
                        <button class="workspace-diff-close" @click.stop="closePaneDiff(pane.id)" title="关闭 diff">✕</button>
                      </div>
                      <div v-if="pane.diff.loading" class="workspace-diff-status">加载 diff...</div>
                      <div v-else-if="pane.diff.error" class="workspace-diff-status error">{{ pane.diff.error }}</div>
                      <div
                        v-else
                        :ref="el => setDiffContainerRef(pane.id, el)"
                        :data-diff-pane-id="pane.id"
                        class="workspace-diff-monaco"
                      ></div>
                    </div>
                    <div v-else class="workspace-pane-placeholder" @click="activateWorkspacePane(pane.id)">
                      <div class="workspace-placeholder-icon" v-html="UI_ICONS.receipt"></div>
                      <div class="workspace-placeholder-title">空 diff 区域</div>
                      <div class="workspace-placeholder-text">在左侧「Git」视图中点击提交里的文件，即可在此区域查看 diff。</div>
                    </div>
                  </div>
                </template>
                <template v-else-if="pane.view === 'chat'">
                  <!-- chat leaf：复用编辑器主区域 chat 的完整接线（host 单例，至多一个 pane 承载） -->
                  <div class="workspace-pane-embed-wrap" @mousedown="activateWorkspacePane(pane.id)">
                    <ChatPanel
                      :visible="true"
                      :interaction="chatPanelInteraction"
                      :panelStyle="{}"
                      :socket="socket"
                      :rooms="chatRooms"
                      :clients="chatClients"
                      :roomMembers="chatRoomMembers"
                      :myClientId="myClientId"
                      :isAdmin="auth.userInfo?.is_admin"
                      :currentUserId="auth.userInfo?.user_id"
                      :activeRoomId="activeChatRoomId"
                      :activePrivateId="activePrivateClientId"
                      :resizeDirections="[]"
                      :unreadCount="chatUnreadCount" :unreadMap="chatUnreadMap" :joinedRooms="chatJoinedRooms"
                      :myName="chatName"
                      :collapsed="chatPanelCollapsed"
                      :sidebarWidth="chatSidebarWidth"
                      :messages="activePrivateClientId ? (chatMessages['private_' + activePrivateClientId] || []) : (chatMessages[activeChatRoomId] || [])"
                      :embedded="true"
                      @focus="focusWindow"
                      @startMove="startChatPanelMove"
                      @close="setActivePaneView('file')"
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
                    />
                  </div>
                </template>
                <template v-else-if="pane.view === 'terminal'">
                  <!-- terminal leaf：复用编辑器主区域 terminal 的完整接线（host 单例，至多一个 pane 承载） -->
                  <div class="workspace-pane-embed-wrap" @mousedown="activateWorkspacePane(pane.id)">
                    <TerminalPanel
                      :visible="true"
                      :active="isPaneActive(pane)"
                      :interaction="terminalPanelInteraction"
                      :panelStyle="{}"
                      :nodeOptions="filteredNodeOptionsForCreateAgent"
                      :selectedNodeId="selectedTerminalNodeId"
                      :socket="socket"
                      :sessions="terminalSessions"
                      :activeId="activeTerminalId"
                      :resizeDirections="[]"
                      :formatNodeLabel="formatNodeOptionLabel"
                      :embedded="true"
                      @focus="focusWindow"
                      @startMove="startTerminalPanelMove"
                      @update:selectedNodeId="selectedTerminalNodeId = $event"
                      @createTerminal="createTerminalForSelectedNode"
                      @syncTerminals="restoreTerminalSessions"
                      @close="setActivePaneView('file')"
                      @switch="switchTerminal"
                      @closeTerminal="closeTerminal"
                      @shareTerminal="openTerminalShareDialog"
                      @setHostRef="setTerminalHostRef"
                      @startResize="startTerminalPanelResize"
                    />
                  </div>
                </template>
                <template v-else>
                  <!-- session leaf：渲染真实会话面板（复用与 #main-view 相同的接线） -->
                  <div v-if="getPanePanel(pane)" class="workspace-pane-session-wrap" @mousedown="activateWorkspacePane(pane.id)">
                    <SessionPanel
                      :ref="el => setSessionPanelRef(getPanePanel(pane)?.id, el)"
                      :embedded="true"
                      :agent="getPanelAgent(getPanePanel(pane))"
                      :messages="getPanelMessages(getPanePanel(pane))"
                      :input-text="getPanelInputText(getPanePanel(pane))"
                      :input-mode="getPanelInputMode(getPanePanel(pane))"
                      :input-tip="getPanelInputTip(getPanePanel(pane))"
                      :is-password="getPanelInputPassword(getPanePanel(pane))"
                      :is-input-disabled="getPanelInputDisabled(getPanePanel(pane))"
                      :is-waiting-multi-disabled="getPanelWaitingMultiDisabled(getPanePanel(pane))"
                      :has-buffered-input="getPanelHasBufferedInput(getPanePanel(pane))"
                      :agent-status="getPanelAgentStatus(getPanePanel(pane))"
                      :active="isPaneActive(pane)"
                      :confirm-data="getPanelConfirmData(getPanePanel(pane))"
                      :interaction="{ active: false }"
                      :resizeDirections="[]"
                      :panelStyle="{}"
                      @confirm="handlePanelConfirm(getPanePanel(pane))"
                      @cancel-confirm="handlePanelCancelConfirm(getPanePanel(pane))"
                      @activate="activateWorkspacePane(pane.id)"
                      @close-agent="closeAgentInPanel(getPanePanel(pane).id)"
                      @close-panel="setActivePaneView('file')"
                      @send="sendFromPanel(getPanePanel(pane))"
                      @complete="completeFromPanel(getPanePanel(pane))"
                      @open-completions="openCompletionsFromPanel(getPanePanel(pane))"
                      @input-change="handlePanelInputChange(getPanePanel(pane), $event)"
                      @keydown="handlePanelKeydown(getPanePanel(pane), $event)"
                      @paste="handlePanelPaste(getPanePanel(pane), $event)"
                      @show-buffer="openBufferPanel(getPanePanel(pane))"
                      @clear-buffer="clearBufferFromPanel(getPanePanel(pane))"
                      @set-output-list="setPanelOutputList(getPanePanel(pane), $event)"
                      @set-terminal-ref="(executionId, el, agentId) => setPanelTerminalRef(getPanePanel(pane), executionId, el, agentId)"
                      @show-toast="showToast"
                      @context-menu="onPanelContextMenu(getPanePanel(pane), $event)"
                      @open-diff-file="onOpenDiffFileFromMessage"
                    />
                  </div>
                  <div v-else class="workspace-pane-placeholder" @click="activateWorkspacePane(pane.id)">
                    <div class="workspace-placeholder-icon" v-html="UI_ICONS.folderStack"></div>
                    <div class="workspace-placeholder-title">空会话区域</div>
                    <div class="workspace-placeholder-text">在左侧「Agent 列表」中点击一个 Agent，即可在此区域打开会话。</div>
                  </div>
                </template>
              </div>
            </template>
          </WorkspacePaneTree>
        </template>
      </WorkspacePanel>

      <!-- 空状态：无任何可见 Panel 时的宠物大厅（所有 Agent 的迷你宠物自由游动） -->
      <div v-if="hasNoPanel" class="empty-stage">
        <PetLobby
          ref="petLobbyRef"
          :agents="agentList"
          :agentsLoaded="agentListLoaded"
          :nodes="availableNodeOptions"
          :getStatusClass="getStatusClass"
          :getInputState="getLobbyInputState"
          :getLatestOutput="getLobbyLatestOutput"
          :historyNav="onLobbyHistoryNav"
          :getNodeDisplayName="getNodeDisplayName"
          :getWorkingDirDisplay="getWorkingDirDisplay"
          :gatewayAddress="gatewayAddressDisplay"
          :connectionStatus="connectionStatus"
          :connectionLabel="connectionLabel"
          :currentUserName="auth.userInfo?.display_name || auth.userInfo?.username || ''"
          :downloadExtension="downloadBrowserExtension"
          :checkExtensionVersion="fetchBrowserExtensionVersion"
          :checkDaemonSessions="fetchDaemonSessions"
          :checkExtensionSessions="fetchBrowserExtensionSessions"
          :localDaemonOnline="localDaemonOnline"
          :contextActions="lobbyContextActions"
          :agentGroups="agentGroups"
          @selectAgent="onLobbySelectAgent"
          @sendInput="sendLobbyInput"
          @complete="onLobbyComplete"
          @openCompletions="onLobbyOpenCompletions"
          @activePetChange="lobbyActiveAgentId = $event"
          @activeNodeChange="lobbyActiveNodeId = $event"
          @createAgentOnNode="onLobbyCreateAgentOnNode"
          @openOnboarding="(tourId) => startOnboarding(tourId || 'welcome')"
          @contextAgent="onLobbyContextAgent"
          @contextRun="onLobbyContextRun"
          @nodeContextRun="onLobbyNodeContextRun"
          @renameNode="onLobbyRenameNode"
          @addAgentToGroup="onLobbyAddAgentToGroup"
          @removeAgentFromGroup="onLobbyRemoveAgentFromGroup"
        />
      </div>
    </main>

    <!-- 确认对话框（弹出式）：Teleport 到 body，避免被 .app 的 isolation 层叠上下文困住，确保高于其他弹窗 -->
    <Teleport to="body">
      <ConfirmDialog
        :visible="!!confirmDialog"
        :message="confirmDialog?.message || ''"
        :defaultConfirm="confirmDialog?.defaultConfirm ?? true"
        @confirm="handleConfirmDialogConfirm"
        @cancel="handleConfirmDialogCancel"
      />
    </Teleport>

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
      :dirDialogOpen="showDirDialog"
      @cancel="showCreateAgentModal = false"
      @create="createAgent"
      @selectDir="openDirDialog"
    />

    <!-- 一句话创建 Agent 弹窗 -->
    <QuickCreateAgentModal
      :visible="showQuickCreateAgentModal"
      :loading="quickCreateAgentLoading"
      :error="quickCreateAgentError"
      @close="showQuickCreateAgentModal = false"
      @submit="submitQuickCreateAgent"
      @open-full="openFullCreateAgentFromQuick"
    />

    <!-- 重命名 Agent 弹窗 -->
    <RenameAgentModal
      :visible="showRenameAgentModal"
      :name="renameAgentName"
      @update:name="renameAgentName = $event"
      @cancel="showRenameAgentModal = false"
      @confirm="confirmRename"
    />

    <!-- 通用输入弹窗（如新建文件/文件夹命名） -->
    <InputPromptModal
      :visible="inputPrompt.visible"
      :title="inputPrompt.title"
      :label="inputPrompt.label"
      :placeholder="inputPrompt.placeholder"
      :model-value="inputPrompt.value"
      :error="inputPrompt.error"
      @update:model-value="inputPrompt.value = $event"
      @cancel="cancelInputPrompt"
      @confirm="confirmInputPrompt"
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

    <!-- 终端分享弹窗：owner 分享终端给其他用户（只读 read / 可交互 interact） -->
    <div v-if="showTerminalShareModal" class="modal-overlay" @click.self="showTerminalShareModal = false">
      <div class="modal-content" style="max-width: 480px;">
        <h3>分享终端</h3>
        <div class="form-group">
          <label>可查看用户 (read)</label>
          <div class="acl-user-list">
            <label v-for="user in filteredUserOptionsForTerminalShare" :key="user.user_id" class="checkbox-label">
              <input type="checkbox" :value="user.user_id" v-model="terminalShareRead" />
              {{ user.display_name || user.user_id }}
            </label>
            <div v-if="filteredUserOptionsForTerminalShare.length === 0" class="form-help">暂无可选用户</div>
          </div>
        </div>
        <div class="form-group">
          <label>可交互用户 (interact)</label>
          <div class="acl-user-list">
            <label v-for="user in filteredUserOptionsForTerminalShare" :key="user.user_id" class="checkbox-label">
              <input type="checkbox" :value="user.user_id" v-model="terminalShareInteract" />
              {{ user.display_name || user.user_id }}
            </label>
            <div v-if="filteredUserOptionsForTerminalShare.length === 0" class="form-help">暂无可选用户</div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn secondary" @click="showTerminalShareModal = false">取消</button>
          <button class="btn primary" @click="saveTerminalShare">保存</button>
        </div>
      </div>
    </div>

    <!-- 目录选择对话框 -->
    <DirectoryDialog
      ref="dirDialogRef"
      :class="{ 'dir-dialog-above-orchestrate': dirDialogContext === 'orchestrate' }"
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
    <!-- 目录树：按节点打开目录（无需创建 Agent） -->
    <!-- 单弹窗布局：上方选节点 + 路径，下方内嵌目录筛选（复用创建 Agent 的 DirectoryDialog 逻辑） -->
    <div v-if="showOpenDirDialog" class="open-dir-overlay" @click.self="closeOpenDirDialog">
      <div class="open-dir-modal">
        <div class="open-dir-header">
          <h2>{{ openDirSource === 'git' ? '选择 Git 目录' : (openDirSource === 'plugin' ? '选择目录' : '打开目录') }}</h2>
          <button class="open-dir-close" @click="closeOpenDirDialog">×</button>
        </div>
        <div class="open-dir-body">
          <label class="open-dir-label">节点</label>
          <select
            class="open-dir-node-select"
            :value="openDirNodeId"
            @change="onOpenDirNodeChange($event.target.value)"
          >
            <option v-if="!filteredNodeOptionsForCreateAgent.length" value="" disabled>暂无可用节点</option>
            <option v-for="node in filteredNodeOptionsForCreateAgent" :key="node.node_id" :value="node.node_id">
              {{ getNodeDisplayName(node.node_id) }}
            </option>
          </select>
          <label class="open-dir-label">目录路径</label>
          <input
            ref="openDirInput"
            v-model="openDirPath"
            class="open-dir-path-input"
            type="text"
            placeholder="绝对路径，如 /home/user/project；也可在下方浏览选择"
            @keydown.enter.prevent="confirmOpenDir"
          >
          <!-- 目录筛选：内嵌 DirectoryDialog（与创建 Agent 的目录选择逻辑完全一致） -->
          <div class="open-dir-browse-wrap">
            <DirectoryDialog
              ref="openDirDialogRef"
              embedded
              :visible="showOpenDirDialog"
              :currentPath="currentDirPath"
              :selectedDir="selectedDir"
              :searchText="dirSearchText"
              :filteredDirs="filteredDirList"
              @update:searchText="dirSearchText = $event"
              @refresh="fetchDirectories"
              @go-parent="goToParentDir"
              @select="onOpenDirSelect"
              @enter="enterDirectory"
              @search-keydown="handleDirSearchKeydown"
            />
          </div>
        </div>
        <div class="open-dir-actions">
          <button class="btn secondary" @click="closeOpenDirDialog">取消</button>
          <button class="btn primary" @click="confirmOpenDir">{{ openDirSource === 'git' ? '确定' : (openDirSource === 'plugin' ? '选择' : '打开') }}</button>
        </div>
      </div>
    </div>
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
      :autoInstallBrowserExt="autoInstallBrowserExt"
      :terminalName="terminalName"
      :daemonPort="daemonPort"
      @update:visible="showSettingsModal = $event"
      @update:autoLoginEnabled="autoLoginEnabled = $event"
      @saveAutoLoginSetting="saveAutoLoginSetting"
      @update:notifyOnExit="notifyOnExit = $event"
      @update:notifyOnInput="notifyOnInput = $event"
      @saveNotifySettings="saveNotifySettings"
      @saveNodeDisplayNames="saveNodeDisplayNames"
      @update:hideWorkingDir="hideWorkingDir = $event"
      @saveHideWorkingDirSetting="saveHideWorkingDirSetting"
      @update:autoInstallBrowserExt="autoInstallBrowserExt = $event"
      @saveAutoInstallBrowserExtSetting="saveAutoInstallBrowserExtSetting"
      @update:terminalName="terminalName = $event"
      @saveTerminalNameSetting="saveTerminalNameSetting"
      @update:daemonPort="daemonPort = $event"
      @saveDaemonPortSetting="saveDaemonPortSetting"
      @confirmClearHistory="confirmClearHistory"
      @disconnectAll="disconnectAll"
    />

    <!-- 关于弹窗 -->
    <AboutModal
      :visible="showAboutModal"
      :frontendVersion="APP_VERSION"
      :backendVersion="aboutBackendVersion"
      :nodes="aboutNodes"
      :daemonSessions="aboutDaemonSessions"
      :browserExtSessions="aboutBrowserExtSessions"
      @update:visible="showAboutModal = $event"
    />

    <!-- 管理面板 -->
    <AdminPanel
      :visible="showAdminPanel"
      ref="adminPanelRef"
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
      :pluginAdminTabs="pluginAdminTabs"
      :pluginExtensions="pluginExtensions"
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

    <!-- Diff 浮动窗口：左侧文件列表 + 右侧选中文件的 diff 对比 -->
    <div v-if="showDiffModal" class="diff-modal-overlay" @click.self="showDiffModal = false">
      <div class="diff-modal">
        <div class="diff-modal-header">
          <h3>代码变更<span v-if="diffFiles.length" class="diff-modal-count">（{{ diffFiles.length }} 个文件）</span></h3>
          <button class="icon-btn" @click="showDiffModal = false" title="关闭">✕</button>
        </div>
        <div v-if="diffLoading" class="diff-loading">加载中...</div>
        <div v-else-if="diffError" class="diff-error">{{ diffError }}</div>
        <div v-else-if="diffFiles.length === 0" class="diff-empty">暂无变更</div>
        <div v-else class="diff-modal-body" :class="{ 'mobile-detail': diffMobileShowDetail }">
          <div class="diff-file-list">
            <div
              v-for="(file, index) in diffFiles"
              :key="file.file_path || index"
              class="diff-file-item"
              :class="{ active: index === diffActiveIndex }"
              :title="file.file_path"
              @click="selectDiffFile(index)"
            >
              <span class="diff-file-item-path">{{ file.file_path || 'Unknown' }}</span>
              <span class="diff-file-item-stats">
                <span class="diff-additions">+{{ file.additions || 0 }}</span>
                <span class="diff-deletions">-{{ file.deletions || 0 }}</span>
              </span>
            </div>
          </div>
          <div class="diff-file-view">
            <button class="diff-mobile-back" @click="diffMobileShowDetail = false">
              <span class="diff-mobile-back-icon">‹</span>
              <span class="diff-mobile-back-text">{{ diffFiles[diffActiveIndex]?.file_path || '文件列表' }}</span>
            </button>
            <div v-html="diffActiveHtml"></div>
          </div>
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
      :extensionSessions="topologyExtensionSessions"
      :daemonSessions="topologyDaemonSessions"
      @update:visible="showTopologyOverlay = $event"
      @close="closeTopologyOverlay"
    />

    <!-- 流水线编排大图 -->
    <OrchestrationOverlay
      :visible="showOrchestrationOverlay"
      :pipelines="pipelineList"
      :activeId="activePipelineId"
      @update:visible="showOrchestrationOverlay = $event"
      @close="closeOrchestrationOverlay"
      @select="selectPipeline"
      @jump-agent="onOrchestrationJumpAgent"
      @approve="handleApproval('approve', $event)"
      @reject="handleApproval('reject', $event)"
      @retry="handleApproval('retry', $event)"
    />

    <!-- 命令面板（Ctrl+P） -->
    <CommandPalette
      :visible="showCommandPalette"
      :actions="appActions"
      :ctx="commandPaletteCtx"
      :initial-query="commandPaletteInitialQuery"
      @update:visible="showCommandPalette = $event"
      @run="onCommandRun"
      @close="showCommandPalette = false"
    />

    <!-- 空格 Leader 序列提示浮窗：按空格进入后逐级显示下一级操作 -->
    <div v-if="spaceSeq.active" class="space-seq-popover" @mousedown.prevent>
      <div class="space-seq-title">
        <span class="space-seq-key">Space</span>
        <template v-for="(p, i) in spaceSeq.path" :key="i">
          <span class="space-seq-arrow">›</span>
          <span class="space-seq-key">{{ p }}</span>
        </template>
        <span class="space-seq-hint">选择下一级操作，ESC 取消</span>
      </div>
      <div class="space-seq-grid">
        <div
          v-for="group in spaceSeqOptions"
          :key="group.key"
          class="space-seq-group"
          :class="{ active: group.active }"
        >
          <div class="space-seq-group-head">
            <span class="space-seq-item-key">{{ group.key }}</span>
            <span class="space-seq-item-label">{{ group.label }}</span>
          </div>
          <div class="space-seq-children">
            <div
              v-for="cmd in group.children"
              :key="cmd.key"
              class="space-seq-item"
              :class="{ active: cmd.active }"
            >
              <span class="space-seq-item-key">{{ cmd.key }}</span>
              <span class="space-seq-item-label">{{ cmd.label }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Panel 右键菜单：与宠物右键一致，列出「当前 Agent」操作 -->
    <div
      v-if="panelContextMenu.visible"
      class="panel-context-menu"
      :style="{ left: panelContextMenu.x + 'px', top: panelContextMenu.y + 'px' }"
      @pointerdown.stop
      @click.stop
      @contextmenu.prevent.stop
    >
      <div class="panel-context-title">{{ panelContextMenu.name }}</div>
      <div class="panel-context-items">
        <button
          v-for="act in lobbyContextActions"
          :key="act.id"
          class="panel-context-item"
          :disabled="act.enabled === false"
          @click="onPanelContextAction(act)"
        >
          <span class="panel-context-icon" v-html="act.icon"></span>
          <span class="panel-context-label">{{ act.label }}</span>
        </button>
      </div>
    </div>

    <!-- 编辑器目录树右键菜单 -->
    <div
      v-if="fileTreeContextMenu.visible"
      class="file-tree-context-menu"
      :style="{ left: fileTreeContextMenu.x + 'px', top: fileTreeContextMenu.y + 'px' }"
      @pointerdown.stop
      @click.stop
      @contextmenu.prevent.stop
    >
      <button
        v-for="act in fileTreeContextActions"
        :key="act.id"
        class="file-tree-context-item"
        :disabled="act.enabled === false"
        @click="runFileTreeContextAction(act)"
      >
        <span class="file-tree-context-icon" v-html="act.icon"></span>
        <span class="file-tree-context-label">{{ act.label }}</span>
      </button>
    </div>

    <!-- Git 提交右键菜单 -->
    <div
      v-if="gitCommitContextMenu.visible"
      class="file-tree-context-menu"
      :style="{ left: gitCommitContextMenu.x + 'px', top: gitCommitContextMenu.y + 'px' }"
      @pointerdown.stop
      @click.stop
      @contextmenu.prevent.stop
    >
      <button
        class="file-tree-context-item"
        @click="copyGitCommit(gitCommitContextMenu.commit)"
      >
        <span class="file-tree-context-icon" v-html="UI_ICONS.copy"></span>
        <span class="file-tree-context-label">复制 commit 信息</span>
      </button>
      <button
        class="file-tree-context-item"
        @click="copyGitCommitId(gitCommitContextMenu.commit)"
      >
        <span class="file-tree-context-icon" v-html="UI_ICONS.copy"></span>
        <span class="file-tree-context-label">复制 commit ID</span>
      </button>
    </div>

    <!-- Git 提交完整信息弹窗（移动端无 hover，用「详情」按钮查看） -->
    <div v-if="gitCommitInfoModal" class="diff-modal-overlay" @click.self="gitCommitInfoModal = null">
      <div class="diff-modal git-commit-info-modal">
        <div class="diff-modal-header">
          <h3>Commit 信息</h3>
          <button class="icon-btn" @click="gitCommitInfoModal = null" title="关闭">✕</button>
        </div>
        <div class="diff-modal-content">
          <pre class="git-commit-info-pre">{{ formatGitCommitInfo(gitCommitInfoModal) }}</pre>
        </div>
      </div>
    </div>

    <!-- 目录树「上传」用的隐藏文件选择框 -->
    <input
      ref="fileTreeUploadInput"
      type="file"
      multiple
      style="display: none"
      @change="onFileTreeUploadInputChange"
    >

    <!-- 编辑器标签栏右键菜单：在文件树中显示 / 关闭右侧所有 / 关闭所有 / 仅保留当前 -->
    <div
      v-if="tabContextMenu.visible"
      class="file-tree-context-menu"
      :style="{ left: tabContextMenu.x + 'px', top: tabContextMenu.y + 'px' }"
      @pointerdown.stop
      @click.stop
      @contextmenu.prevent.stop
    >
      <button
        v-for="act in tabContextActions"
        :key="act.id"
        class="file-tree-context-item"
        :disabled="act.enabled === false"
        @click="runTabContextAction(act)"
      >
        <span class="file-tree-context-icon">{{ act.icon }}</span>
        <span class="file-tree-context-label">{{ act.label }}</span>
      </button>
    </div>

    <!-- 新手引导（按场景首次触发，可随时从命令面板重新查看） -->
    <OnboardingTour
      v-model:visible="showOnboarding"
      :steps="activeTourSteps"
      @close="finishTour"
      @finish="finishTour"
    />
    <!-- 编排弹窗：选节点 + 编排文件 → 解析出 Agent 列表（每个一个标签页，可编辑）→ 一键创建 -->
    <div v-if="showOrchestrateModal" class="orchestrate-overlay" @click.self="closeOrchestrateModal">
      <div class="orchestrate-modal">
        <div class="orchestrate-header">
          <h2>编排：批量创建 Agent</h2>
          <button class="orchestrate-close" @click="closeOrchestrateModal">×</button>
        </div>
        <div class="orchestrate-body">
          <!-- 顶部：节点 + 编排文件路径 + 解析 -->
          <div class="orchestrate-source">
            <div class="orchestrate-source-row">
              <label class="orchestrate-label">节点</label>
              <select v-model="orchestrateNodeId" class="orchestrate-node-select" @change="onOrchestrateNodeChange">
                <option v-if="!filteredNodeOptionsForCreateAgent.length" value="" disabled>暂无可用节点</option>
                <option v-for="node in filteredNodeOptionsForCreateAgent" :key="node.node_id" :value="node.node_id">
                  {{ getNodeDisplayName(node.node_id) }}
                </option>
              </select>
            </div>
            <div class="orchestrate-source-row">
              <label class="orchestrate-label">编排文件</label>
              <input
                v-model="orchestrateFilePath"
                class="orchestrate-path-input"
                type="text"
                placeholder="节点上的编排文件绝对路径（.yaml/.yml=组织编排，.flow=流程编排），如 /home/user/pipeline.flow"
                @keydown.enter.prevent="parseOrchestrationFile"
              >
              <button class="btn secondary" @click="toggleOrchestrateBrowser">
                {{ orchestrateShowBrowser ? '收起' : '浏览' }}
              </button>
              <button class="btn secondary" @click="onOrchestrateLocalSelect">
                本地选择
              </button>
              <button class="btn primary" :disabled="orchestrateLoading" @click="parseOrchestrationFile">
                {{ orchestrateLoading ? '解析中…' : '解析' }}
              </button>
            </div>
            <!-- 从本机选择编排文件用的隐藏文件选择框（选中后上传到所选节点并回填路径） -->
            <input
              ref="orchestrateLocalFileInput"
              type="file"
              accept=".yaml,.yml,.flow"
              style="display: none"
              @change="onOrchestrateLocalFileChange"
            >
            <!-- 最近使用过的编排文件：点击快速复用，hover 显示删除按钮 -->
            <div v-if="orchestrateRecentFiles.length" class="orchestrate-recent">
              <div class="orchestrate-recent-title">最近使用</div>
              <div class="orchestrate-recent-list">
                <button
                  v-for="(item, index) in orchestrateRecentFiles"
                  :key="index"
                  class="orchestrate-recent-tag"
                  :class="{ active: orchestrateFilePath === item.path }"
                  :title="item.path"
                  @click="selectOrchestrateRecentFile(item)"
                >
                  <span class="orchestrate-recent-name">{{ item.path }}</span>
                  <span class="orchestrate-recent-node">[{{ getNodeDisplayName(item.nodeId) }}]</span>
                  <span class="orchestrate-recent-remove" title="从最近使用中移除" @click.stop="removeOrchestrateRecentFile(item.path, item.nodeId)">✕</span>
                </button>
              </div>
            </div>
            <!-- 插件编排模板：自动发现已装插件声明的编排模板，点击直接选用 -->
            <div v-if="orchestratePluginTemplates.length" class="orchestrate-templates">
              <div class="orchestrate-templates-title">插件编排模板</div>
              <div class="orchestrate-templates-list">
                <button
                  v-for="(tpl, index) in orchestratePluginTemplates"
                  :key="index"
                  class="orchestrate-template-tag"
                  :class="{ active: orchestrateFilePath === tpl.file }"
                  :title="tpl.file"
                  @click="selectOrchestratePluginTemplate(tpl)"
                >
                  <span class="orchestrate-template-name">{{ tpl.name }}</span>
                  <span class="orchestrate-template-plugin">[{{ tpl.plugin }}]</span>
                  <span v-if="tpl.description" class="orchestrate-template-desc">{{ tpl.description }}</span>
                </button>
              </div>
            </div>
            <div v-else-if="orchestratePluginTemplatesLoading" class="orchestrate-templates-loading">正在加载插件编排模板…</div>
            <!-- 文件浏览面板：内嵌 DirectoryDialog（目录 + .yaml/.yml 文件，逻辑与「打开目录」一致） -->
            <div v-if="orchestrateShowBrowser" class="orchestrate-browse-wrap">
              <DirectoryDialog
                ref="orchestrateDialogRef"
                embedded
                :visible="orchestrateShowBrowser"
                :currentPath="orchestrateCurrentDirPath"
                :selectedDir="orchestrateHighlightedDir"
                :searchText="orchestrateDirSearchText"
                :filteredDirs="orchestrateFilteredDirs"
                fileSelectable
                :fileList="orchestrateFilteredFiles"
                :selectedFile="orchestrateHighlightedFile"
                @update:searchText="orchestrateDirSearchText = $event"
                @refresh="fetchOrchestrateEntries"
                @go-parent="goToOrchestrateParentDir"
                @enter="enterOrchestrateDir"
                @select-file="onOrchestrateSelectFile"
                @search-keydown="handleOrchestrateSearchKeydown"
              />
            </div>
          </div>

          <div v-if="orchestrateError" class="orchestrate-error">{{ orchestrateError }}</div>

          <!-- 标签页：每个 Agent 一个 -->
          <div v-if="orchestrateAgents.length" class="orchestrate-tabs">
            <button
              v-for="(agent, index) in orchestrateAgents"
              :key="index"
              class="orchestrate-tab"
              :class="{ active: index === orchestrateActiveIndex }"
              @click="orchestrateActiveIndex = index"
            >
              <span class="orchestrate-tab-name">{{ agent.name || ('Agent ' + (index + 1)) }}</span>
              <span class="orchestrate-tab-close" @click.stop="removeOrchestrateAgent(index)">×</span>
            </button>
            <button v-if="!orchestrateHasFlow" class="orchestrate-tab-add" title="新增一个 Agent" @click="addOrchestrateAgent">＋</button>
          </div>

          <!-- 当前标签页的表单 -->
          <div v-if="orchestrateAgents[orchestrateActiveIndex]" class="orchestrate-form">
            <div class="orchestrate-field">
              <label class="orchestrate-label">名称</label>
              <input v-model="orchestrateAgents[orchestrateActiveIndex].name" class="orchestrate-input" type="text" placeholder="留空自动生成">
            </div>
            <div class="orchestrate-field orchestrate-field-wide">
              <label class="orchestrate-label">工作目录</label>
              <div class="orchestrate-dir-row">
                <input v-model="orchestrateAgents[orchestrateActiveIndex].workingDir" class="orchestrate-input" type="text" placeholder="绝对路径">
                <button class="btn secondary" @click="openOrchestrateDirDialog">选择目录</button>
              </div>
            </div>
            <div class="orchestrate-field">
              <label class="orchestrate-label">模型组</label>
              <input v-model="orchestrateAgents[orchestrateActiveIndex].llmGroup" class="orchestrate-input" type="text" placeholder="default">
            </div>
            <div class="orchestrate-field">
              <label class="orchestrate-label">工具组</label>
              <input v-model="orchestrateAgents[orchestrateActiveIndex].toolGroup" class="orchestrate-input" type="text" placeholder="default">
            </div>
            <div class="orchestrate-field">
              <label class="orchestrate-label">目标节点</label>
              <select v-model="orchestrateAgents[orchestrateActiveIndex].nodeId" class="orchestrate-input">
                <option v-for="node in filteredNodeOptionsForCreateAgent" :key="node.node_id" :value="node.node_id">
                  {{ getNodeDisplayName(node.node_id) }}
                </option>
              </select>
            </div>
            <div class="orchestrate-field">
              <label class="orchestrate-label">代理节点</label>
              <select v-model="orchestrateAgents[orchestrateActiveIndex].proxyNode" class="orchestrate-input">
                <option value="">无代理（直接调用）</option>
                <option v-for="node in filteredNodeOptionsForCreateAgent" :key="node.node_id" :value="node.node_id">
                  {{ getNodeDisplayName(node.node_id) }}
                </option>
              </select>
            </div>
            <div class="orchestrate-field orchestrate-field-wide">
              <label class="orchestrate-label">任务描述</label>
              <textarea v-model="orchestrateAgents[orchestrateActiveIndex].task" class="orchestrate-textarea" rows="3" placeholder="无交互模式下必填"></textarea>
            </div>
            <div class="orchestrate-field orchestrate-field-wide orchestrate-checks">
              <label class="orchestrate-check"><input v-model="orchestrateAgents[orchestrateActiveIndex].quickMode" type="checkbox"> 极速模式</label>
              <label class="orchestrate-check"><input v-model="orchestrateAgents[orchestrateActiveIndex].restoreSession" type="checkbox"> 恢复会话</label>
              <label class="orchestrate-check"><input v-model="orchestrateAgents[orchestrateActiveIndex].noInteractionMode" type="checkbox"> 无交互模式</label>
            </div>
          </div>
          <div v-else class="orchestrate-empty">选择编排文件并解析，或点击 ＋ 新增 Agent</div>

          <!-- 创建结果 -->
          <div v-if="orchestrateResults.length" class="orchestrate-results">
            <div
              v-for="(r, index) in orchestrateResults"
              :key="index"
              class="orchestrate-result"
              :class="r.ok ? 'ok' : 'fail'"
            >
              <span>{{ r.ok ? '✓' : '✕' }}</span>
              <span class="orchestrate-result-name">{{ r.name }}</span>
              <span v-if="!r.ok" class="orchestrate-result-error">{{ r.error }}</span>
            </div>
          </div>

          <!-- 运行流水线：编排文件含 flow 时显示。与 Agent 调用 pipeline_runner 同一路径，运行进度驱动「编排查看」DAG 可视化 -->
          <div v-if="orchestrateHasFlow" class="orchestrate-run">
            <div class="orchestrate-run-title">运行流水线</div>
            <div class="orchestrate-run-hint">该编排文件含 flow 字段，将按流水线调度执行；运行进度将在「编排查看」中实时展示。</div>
            <div class="orchestrate-field orchestrate-field-wide">
              <label class="orchestrate-label">工作目录</label>
              <input
                v-model="orchestrateRunWorkingDir"
                class="orchestrate-input"
                type="text"
                placeholder="留空默认当前目录，产物 .jarvis/artifacts/ 在其中创建"
              >
            </div>
          </div>
        </div>
        <div class="orchestrate-actions">
          <button class="btn secondary" @click="closeOrchestrateModal">取消</button>
          <!-- 含 flow：提供「预览」静态 DAG 与「运行流水线」两个操作；否则一键创建 Agent -->
          <button
            v-if="orchestrateHasFlow"
            class="btn secondary"
            :disabled="!orchestrateFilePath || !orchestrateNodes.length"
            @click="previewOrchestration"
          >
            预览
          </button>
          <button
            v-if="orchestrateHasFlow"
            class="btn primary orchestrate-run-btn"
            :disabled="orchestrateRunning || !orchestrateFilePath"
            @click="runOrchestration"
          >
            {{ orchestrateRunning ? '启动中…' : '运行流水线' }}
          </button>
          <button
            v-else
            class="btn primary"
            :disabled="orchestrateCreating || !orchestrateAgents.length"
            @click="createAllOrchestrateAgents"
          >
            {{ orchestrateCreating ? '创建中…' : `一键创建（${orchestrateAgents.length}）` }}
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
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, reactive, ref, triggerRef, watch } from 'vue'
// 必须用 ESM 版入口：包根路径在打包时会被解析到 min/（AMD 格式），
// 拿不到 monaco.lsp（Monaco 内置的 LSP 客户端），也无法按 ESM 方式使用。
import * as monaco from 'monaco-editor/esm/vs/editor/editor.main.js'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker.js?worker'
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker.js?worker'
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker.js?worker'
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker.js?worker'
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker.js?worker'
// LSP 接入：语言清单来自后端 /api/lsp/servers，前端不含任何语言硬编码
import { loadLspServers, getServerByLanguage, getServerByPath } from './lsp/registry.js'
import { ensureClient, disposeClient, disposeAll as disposeAllLspClients, getDefinition } from './lsp/manager.js'

// Monaco 在 vite 下必须显式提供 worker 工厂，否则编辑器无法启动
self.MonacoEnvironment = {
  getWorker(_workerId, label) {
    if (label === 'json') return new jsonWorker()
    if (label === 'css' || label === 'scss' || label === 'less') return new cssWorker()
    if (label === 'html' || label === 'handlebars' || label === 'razor') return new htmlWorker()
    if (label === 'typescript' || label === 'javascript') return new tsWorker()
    return new editorWorker()
  },
}
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import 'xterm/css/xterm.css'
import './diff.css'
import historyStorage from './historyStorage.js'
import ConnectModal from './components/ConnectModal.vue'
import BufferPanel from './components/BufferPanel.vue'
import DirectoryDialog from './components/DirectoryDialog.vue'
import SessionDialog from './components/SessionDialog.vue'
import AgentSidebar from './components/AgentSidebar.vue'
import PetWidget from './components/PetWidget.vue'
import CompletionsModal from './components/CompletionsModal.vue'
import TerminalPanel from './components/TerminalPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import WorkspacePanel from './components/WorkspacePanel.vue'
import WorkspacePaneTree from './components/WorkspacePaneTree.vue'
import WorkspacePaneHeader from './components/WorkspacePaneHeader.vue'
import SettingsModal from './components/SettingsModal.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import CreateAgentModal from './components/CreateAgentModal.vue'
import QuickCreateAgentModal from './components/QuickCreateAgentModal.vue'
import SessionPanel from './components/SessionPanel.vue'
import { renderSideBySideDiff, escapeHtml } from './diffRenderer.js'
import { parseUnifiedDiff, extractDiffContext } from './gitDiffParser.js'
import { useDiff } from './composables/useDiff.js'
import RenameAgentModal from './components/RenameAgentModal.vue'
import InputPromptModal from './components/InputPromptModal.vue'
import AdminPanel from './components/AdminPanel.vue'
import AboutModal from './components/AboutModal.vue'
import CommandPalette from './components/CommandPalette.vue'
import TopologyOverlay from './components/TopologyOverlay.vue'
import OrchestrationView from './components/OrchestrationView.vue'
import OrchestrationOverlay from './components/OrchestrationOverlay.vue'
import { PipelineStore } from './stores/pipelineStore.js'
import PetLobby from './components/PetLobby.vue'
import OnboardingTour from './components/OnboardingTour.vue'
import ManageSidebar from './components/ManageSidebar.vue'
import PluginSidebar from './components/PluginSidebar.vue'
import { fetchPluginExtensions, loadExtensionComponent } from './pluginExtensions.js'
import { ACTIONS as actionDefs, SPACE_COMMANDS } from './actions/registry.js'
import { resolveCurrentAgentId } from './utils/currentAgentResolver.js'
import { useAudioNotifications } from './composables/useAudioNotifications.js'
import { useInputHistory } from './composables/useInputHistory.js'
import { useAuthBridge } from './composables/useAuthBridge.js'
import { useDaemonSync } from './composables/useDaemonSync.js'
import { useTerminal, useTerminalName } from './composables/useTerminal.js'
import { useDiagramRender } from './composables/useDiagramRender.js'
import { useSession } from './composables/useSession.js'
import { useChat } from './composables/useChat.js'
import { useFileTree } from './composables/useFileTree.js'
import { useTour } from './composables/useTour.js'
import { usePlugins } from './composables/usePlugins.js'
import { useTopology } from './composables/useTopology.js'
import { useSettings } from './composables/useSettings.js'
import { useGatewayConnection } from './composables/useGatewayConnection.js'
import { useAgents } from './composables/useAgents.js'
import { useOrchestrate } from './composables/useOrchestrate.js'
import { useGitView } from './composables/useGitView.js'
import { useWorkspacePane } from './composables/useWorkspacePane.js'

// 图表渲染（plantuml/mermaid/dot），拆自独立 composable
const {
  encodePlantUmlText,
  isPlantUmlLanguage,
  isPlantUmlComplete,
  renderPlantUmlBlock,
  isDotLanguage,
  isMermaidLanguage,
  renderDotBlock,
  renderMermaidBlock,
  renderMermaidDiagrams,
  renderDotDiagrams,
} = useDiagramRender()

// 前端版本号：由 vite.config.js 的 define 在构建时注入（与主版本保持一致）
const APP_VERSION = __APP_VERSION__

// 格式化消息时间 - 直接显示后端传递的时间戳
function formatMessageTime(timestamp) {
  if (!timestamp) return ''
  return timestamp
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

// Monaco 语言 ID 映射：Monaco 内置语言与 getLanguageFromFilename 基本同名，
// 仅少数需要归一化（如 vue 无内置支持，退回 html）。
const MONACO_LANGUAGE_ALIAS = {
  'vue': 'html',
  'toml': 'ini',
  'plaintext': 'plaintext',
}

function getLanguageExtension(language) {
  const normalized = MONACO_LANGUAGE_ALIAS[language] || language
  if (monaco.languages.getLanguages().some(lang => lang.id === normalized)) {
    return normalized
  }
  return 'plaintext'
}

// 认证和连接配置
const auth = ref({
  password: '',
  token: '',
  userInfo: null
})
const username = ref(localStorage.getItem('jarvis_username') || '')
const socket = ref(null) // Gateway 连接
const sockets = ref(new Map()) // 多 Agent 连接存储：agent_id -> WebSocket
const autoLoginEnabled = ref(localStorage.getItem('jarvis_auto_login') === 'true')  // 免登录开关
const switchGeneration = ref(0) // 切换代数，用于取消旧的switchAgent操作

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
    userPermissions.value = null
    localStorage.removeItem('jarvis_auth_token')
    localStorage.removeItem('jarvis_user_info')
    showConnectModal.value = true
    connectErrorMessage.value = '登录已过期，请重新登录'
    stopAgentListRefresh()
    stopNodeStatusRefresh()
  }
  
  return response
}

// 暴露统一的带认证请求函数给插件前端扩展（动态加载的独立 ES module）。
// 插件侧边栏/面板组件无法访问本组件的 auth.value.token，也不应直接接触 token，
// 故通过 window.__jarvisFetch 提供统一的认证请求入口：插件只需调用
//   window.__jarvisFetch(url, options)
// 即可自动携带 jarvis 认证信息，token 不暴露给插件。
try {
  window.__jarvisFetch = (url, options) => fetchWithAuth(url, options)
} catch (e) {
  /* ignore */
}

// 暴露「向当前活跃 Agent 发送提示词」的钩子给插件前端扩展（如 gh 插件的右键「处理」）。
// 目标 Agent 与插件侧边栏的工作目录保持一致：Git 目标 Agent（gitAgentId || currentAgentId），
// 保证提示词发给正在展示该仓库的 Agent。发送复用既有 input_result 通道：Agent 等待输入时
// 立即提交，否则进入输入缓冲区，待其下次请求输入时消费。
// 返回 { success, agentId } 或 { success: false, error }，供插件给出明确反馈。
try {
  window.__jarvisSendToActiveAgent = (text, options = {}) => {
    const content = String(text || '').trim()
    if (!content) return { success: false, error: '提示词为空' }
    const agentId = options.agentId || effectiveGitAgentId.value || currentAgentId.value
    if (!agentId) return { success: false, error: '当前没有活跃的 Agent' }
    const ws = sockets.value.get(agentId)
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return { success: false, error: '目标 Agent 未连接，请先在会话面板中打开该 Agent' }
    }
    sendInputDirectly(content, 'multi', agentId)
    return { success: true, agentId }
  }
} catch (e) {
  /* ignore */
}

// 暴露「获取当前活跃 Agent 信息」的钩子给插件前端扩展（如 gh 插件顶部展示目标 Agent）。
// 目标 Agent 与 __jarvisSendToActiveAgent 完全一致：Git 目标 Agent（gitAgentId || currentAgentId），
// 保证插件展示的 Agent 就是提示词实际发送的对象。
// 返回 { agentId, agentName, workingDir }；无活跃 Agent 时返回 null。
try {
  window.__jarvisGetActiveAgentInfo = () => {
    const agentId = effectiveGitAgentId.value
    const agent = agentId ? (agentList.value.find(a => a.agent_id === agentId) || null) : null
    return agent
      ? {
          agentId: agent.agent_id,
          agentName: agent.name || agent.agent_id,
          workingDir: agent.working_dir || '',
        }
      : null
  }
} catch (e) {
  /* ignore */
}

// 暴露「创建新普通 Agent 处理任务」的钩子给插件前端扩展（如 gh 插件的右键「创建新 Agent 处理」）。
// 使用普通 Agent（agent_type='agent'）而非代码 Agent，避免同工作目录下代码 Agent 的互斥限制。
// 以交互模式创建并把提示词作为初始任务，用户可随时干预；创建后自动打开该 Agent 面板。
// options.agentType 可指定 agent 类型（默认 'agent'，向后兼容；传 'code_agent' 时创建代码 Agent）。
// 返回 { success, agentId } 或 { success: false, error }。
try {
  window.__jarvisCreateAgentForTask = async (options = {}) => {
    const workingDir = String(options.workingDir || '').trim()
    const task = String(options.task || '').trim()
    if (!workingDir) return { success: false, error: '工作目录为空' }
    if (!task) return { success: false, error: '任务提示词为空' }
    const agentType = String(options.agentType || 'agent').trim() || 'agent'
    const result = await createAgentWithOptions({
      agentType,
      workingDir,
      name: options.name || '',
      task,
      noInteractionMode: false,
    })
    if (!result.ok) return { success: false, error: result.error }
    await afterAgentCreated(result.agent)
    return { success: true, agentId: result.agent.agent_id }
  }
} catch (e) {
  /* ignore */
}

// 暴露「选择目录」的钩子给插件前端扩展（如 gh 插件的「Fork 并创建 CodeAgent 处理」需先选目录）。
// 复用宿主已有的「打开目录」弹窗（含节点选择 + 目录浏览）；用户确认后返回选中的绝对路径，
// 取消则返回 null。返回 Promise<string|null>。
try {
  window.__jarvisPickDirectory = () => {
    return new Promise((resolve) => {
      // 已有未结束的选择请求时，先以 null 结束上一个，避免 Promise 悬挂
      if (pluginPickDirResolver) {
        const prev = pluginPickDirResolver
        pluginPickDirResolver = null
        prev(null)
      }
      pluginPickDirResolver = resolve
      openDirSource.value = 'plugin'
      openOpenDirDialog()
    })
  }
} catch (e) {
  /* ignore */
}
// ========== 插件统一接口族（Issue #97）==========
// 在既有 __jarvis* 单点接口之上，补齐一套「信息查询 + UI 控制」的统一接口族，
// 让插件扩展（sidebar_views / admin_tabs / tool_panels）不再依赖宿主逐个补函数。
// 所有接口沿用 try/catch 包裹模式：宿主环境异常时静默降级，不影响主界面。
// 事件订阅（__jarvisOn/__jarvisOff）见下方「插件事件订阅机制」小节。

// 获取当前登录用户信息（auth.userInfo）；未登录或未加载时返回 null。
try {
  window.__jarvisGetUserInfo = () => auth.value.userInfo || null
} catch (e) {
  /* ignore */
}

// 获取节点列表（availableNodeOptions，含 node_id/status 等字段；master 恒在列）。
// 返回数组副本，避免插件直接改动宿主响应式状态。
try {
  window.__jarvisGetNodes = () => (Array.isArray(availableNodeOptions.value) ? [...availableNodeOptions.value] : [])
} catch (e) {
  /* ignore */
}

// 显示 toast 通知（复用宿主 showToast）。
// message: 文本；type: 'success' | 'error' | 'info'（默认 success）。
try {
  window.__jarvisShowToast = (message, type = 'success') => showToast(String(message || ''), type)
} catch (e) {
  /* ignore */
}

// 切换工作区侧边栏视图（复用宿主 setWorkspaceSidebarView）。
// view: 内置视图名（agents/files/search/git/manage/timers/plugins/orchestration）
//       或插件视图（'plugin:<id>' / 'plugin-tool:<id>'）。
try {
  window.__jarvisSwitchSidebarView = (view) => {
    const target = String(view || '').trim()
    if (!target) return { success: false, error: '视图名为空' }
    setWorkspaceSidebarView(target)
    return { success: true }
  }
} catch (e) {
  /* ignore */
}

// 打开宿主面板/导航（复用宿主既有入口）。
// kind 支持：
//   'admin'        打开管理面板
//   'settings'     打开设置
//   'workspace'    打开工作区（并切到 Agent 列表）
//   'git'          打开工作区并切到 Git 侧边栏
//   'plugins'      打开工作区并切到插件管理侧边栏
//   'topology'     打开网络拓扑
//   'docs'         打开使用文档
// 返回 { success } 或 { success: false, error }。
try {
  window.__jarvisOpenPanel = (kind) => {
    const target = String(kind || '').trim()
    switch (target) {
      case 'admin':
        showAdminPanel.value = true
        pushOverlayState()
        return { success: true }
      case 'settings':
        showSettingsModal.value = true
        return { success: true }
      case 'workspace':
        openWorkspaceAgentList()
        return { success: true }
      case 'git':
        if (!showWorkspacePanel.value) {
          showWorkspacePanel.value = true
          if (windowWidth.value <= 768) pushOverlayState()
        }
        setWorkspaceSidebarView('git')
        return { success: true }
      case 'plugins':
        if (!showWorkspacePanel.value) {
          showWorkspacePanel.value = true
          if (windowWidth.value <= 768) pushOverlayState()
        }
        setWorkspaceSidebarView('plugins')
        return { success: true }
      case 'topology':
        openTopologyOverlay()
        return { success: true }
      case 'docs':
        openDocs()
        return { success: true }
      default:
        return { success: false, error: `未知面板: ${target}` }
    }
  }
} catch (e) {
  /* ignore */
}

// 获取当前网关信息（host/port/protocol），供插件构造 API 地址。
// 返回 { host, port, protocol }；解析失败时回退默认值。
try {
  window.__jarvisGetGatewayInfo = () => {
    const { host, port } = getGatewayAddress()
    return {
      host,
      port,
      protocol: getHttpProtocol(),
    }
  }
} catch (e) {
  /* ignore */
}

// ========== 插件事件订阅机制（Issue #97）==========
// 宿主在关键状态变化处 emit 事件，插件通过 window.__jarvisOn(event, handler) 订阅、
// window.__jarvisOff(event, handler) 取消订阅。handler 收到 (payload) 参数。
// 事件清单：
//   'agent_changed'  当前活跃 Agent 变化（payload: { agentId, agentName, workingDir } 或 null）
//   'token_changed'  token 变化（payload: { token }，登出为 null）
//   'user_changed'   当前用户信息变化（payload: { userInfo } 或 null）
//   'nodes_changed'  节点列表变化（payload: { nodes }）
const __jarvisEventListeners = new Map()
try {
  window.__jarvisOn = (event, handler) => {
    if (typeof handler !== 'function') return () => {}
    const key = String(event || '')
    if (!key) return () => {}
    if (!__jarvisEventListeners.has(key)) __jarvisEventListeners.set(key, new Set())
    __jarvisEventListeners.get(key).add(handler)
    // 返回取消订阅函数，便于插件在组件卸载时清理
    return () => window.__jarvisOff(key, handler)
  }
  window.__jarvisOff = (event, handler) => {
    const key = String(event || '')
    const set = __jarvisEventListeners.get(key)
    if (!set) return
    if (handler) {
      set.delete(handler)
    } else {
      set.clear()
    }
  }
} catch (e) {
  /* ignore */
}
// 宿主内部 emit 辅助函数（不暴露给插件，供本文件状态变化处调用）
function __jarvisEmit(event, payload) {
  try {
    const set = __jarvisEventListeners.get(String(event || ''))
    if (!set) return
    set.forEach((handler) => {
      try {
        handler(payload)
      } catch (e) {
        console.warn(`[PluginEvents] handler for "${event}" failed:`, e)
      }
    })
  } catch (e) {
    /* ignore */
  }
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
// 网关地址展示串（host:port），供大厅左上角仪表显示
const gatewayAddressDisplay = computed(() => {
  const { host, port } = getGatewayAddress()
  return `${host}:${port}`
})

// 下载浏览器扩展 zip 包：请求网关动态打包接口，触发浏览器下载
async function downloadBrowserExtension() {
  const { host, port } = getGatewayAddress()
  const url = `${getHttpProtocol()}://${host}:${port}/api/browser-ext/download`
  const response = await fetchWithAuth(url)
  if (!response.ok) {
    throw new Error(`下载失败（HTTP ${response.status}）`)
  }
  // 优先使用后端 Content-Disposition 中的文件名
  let filename = 'jarvis-browser-bridge.zip'
  const disposition = response.headers.get('Content-Disposition') || ''
  const matched = disposition.match(/filename="?([^";]+)"?/i)
  if (matched && matched[1]) filename = matched[1]
  const blob = await response.blob()
  const objectUrl = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(objectUrl)
}

// 查询浏览器扩展版本信息：返回网关打包版本与在线扩展版本，供前端提示升级
async function fetchBrowserExtensionVersion() {
  try {
    const { host, port } = getGatewayAddress()
    const url = `${getHttpProtocol()}://${host}:${port}/api/browser-ext/version`
    const response = await fetchWithAuth(url)
    if (!response.ok) return null
    const result = await response.json()
    if (!result || !result.success) return null
    return {
      latestVersion: result.latest_version || '',
      sessions: Array.isArray(result.sessions) ? result.sessions : []
    }
  } catch (e) {
    // 版本查询失败不应影响弹层展示
    return null
  }
}

// 查询本机后台服务（daemon）在线会话：返回会话数组，供大厅拓扑图展示接入的 daemon 节点。
// 非管理员仅返回自己（token 对应用户）的会话，由网关侧限制。
async function fetchDaemonSessions() {
  try {
    const { host, port } = getGatewayAddress()
    const url = `${getHttpProtocol()}://${host}:${port}/api/daemon/sessions`
    const response = await fetchWithAuth(url)
    if (!response.ok) return []
    const result = await response.json()
    if (!result || !result.success) return []
    return Array.isArray(result.sessions) ? result.sessions : []
  } catch (e) {
    // 查询失败不应影响拓扑图渲染，视为无在线 daemon
    return []
  }
}

// 查询定时任务列表（只读展示，任务由 Agent 直接控制）。
// GET /api/timers 返回 {success, data:[{task_id, run_at, interval_seconds,
//   is_recurring, cancelled, metadata:{action:{type,params}, schedule}}]}
async function fetchTimers() {
  try {
    const { host, port } = getGatewayAddress()
    const url = `${getHttpProtocol()}://${host}:${port}/api/timers`
    const response = await fetchWithAuth(url)
    if (!response.ok) return []
    const result = await response.json()
    if (!result || !result.success) return []
    return Array.isArray(result.data) ? result.data : []
  } catch (e) {
    return []
  }
}

// 刷新管理侧边栏的定时任务列表
async function refreshManageTimers() {
  manageTimers.value = await fetchTimers()
}
// 供拓扑图为每个接入的扩展渲染一个节点并显示名称。
// 注意：/api/browser-ext/version 的 sessions 只含 session_id/extension_version，
// 不含 name，故这里单独调 /api/browser-ext/sessions。
// 非管理员仅返回自己（token 对应用户）的会话，由网关侧限制。
async function fetchBrowserExtensionSessions() {
  try {
    const { host, port } = getGatewayAddress()
    const url = `${getHttpProtocol()}://${host}:${port}/api/browser-ext/sessions`
    const response = await fetchWithAuth(url)
    if (!response.ok) return []
    const result = await response.json()
    if (!result || !result.success) return []
    return Array.isArray(result.sessions) ? result.sessions : []
  } catch (e) {
    // 查询失败不应影响拓扑图渲染，视为无在线扩展
    return []
  }
}

// 打开「关于」弹窗并刷新版本信息（后端版本 / 节点 / daemon / 浏览器扩展）
async function openAbout() {
  showAboutModal.value = true
  pushOverlayState()
  const { host, port } = getGatewayAddress()
  // 后端版本与各节点版本
  try {
    const resp = await fetchWithAuth(buildNodeHttpUrl(host, port, 'master', 'node/status'))
    if (resp.ok) {
      const result = await resp.json()
      const data = result?.data
      aboutBackendVersion.value = data?.version || ''
      aboutNodes.value = Array.isArray(data?.nodes) ? data.nodes : []
    }
  } catch (e) {
    // 忽略，保持已有值
  }
  // daemon 与浏览器扩展版本
  aboutDaemonSessions.value = await fetchDaemonSessions()
  aboutBrowserExtSessions.value = await fetchBrowserExtensionSessions()
}

// 查询每个在线浏览器扩展会话已安装的自定义脚本（能力清单用）。
// GET /api/browser-ext/scripts/installed 返回 {success, sessions:[{session_id, name, scripts}]}
async function fetchInstalledScripts() {
  try {
    const { host, port } = getGatewayAddress()
    const url = `${getHttpProtocol()}://${host}:${port}/api/browser-ext/scripts/installed`
    const response = await fetchWithAuth(url)
    if (!response.ok) return []
    const result = await response.json()
    if (!result || !result.success) return []
    return Array.isArray(result.sessions) ? result.sessions : []
  } catch (e) {
    return []
  }
}

// 查询网关数据目录下保存的脚本（能力清单用）。
// GET /api/browser-ext/scripts/list 返回 {success, scripts:[{name, size, updated_at}]}
async function fetchGatewayScripts() {
  try {
    const { host, port } = getGatewayAddress()
    const url = `${getHttpProtocol()}://${host}:${port}/api/browser-ext/scripts/list`
    const response = await fetchWithAuth(url)
    if (!response.ok) return []
    const result = await response.json()
    if (!result || !result.success) return []
    return Array.isArray(result.scripts) ? result.scripts : []
  } catch (e) {
    return []
  }
}

// 网络拓扑大图（拆自 composable useTopology，见下方 useTopology 调用处）
const {
  topologyExtensionSessions,
  topologyDaemonSessions,
  refreshTopologyAccessSessions,
  startTopologyAccessPolling,
  stopTopologyAccessPolling,
  showTopologyOverlay,
  openTopologyOverlay,
  closeTopologyOverlay,
} = useTopology({
  fetchBrowserExtensionSessions,
  fetchDaemonSessions,
})
// 刷新能力清单数据（浏览器扩展会话 + daemon 会话 + 已安装脚本 + 网关脚本）。
// 能力清单缓存：仅在首次打开或手动点刷新按钮时调用，避免频繁请求。
async function refreshManageCapabilities() {
  const [extSessions, daemonSessions, installedScripts, gatewayScripts] = await Promise.all([
    fetchBrowserExtensionSessions(),
    fetchDaemonSessions(),
    fetchInstalledScripts(),
    fetchGatewayScripts(),
  ])
  topologyExtensionSessions.value = Array.isArray(extSessions) ? extSessions : []
  topologyDaemonSessions.value = Array.isArray(daemonSessions) ? daemonSessions : []
  manageInstalledScripts.value = Array.isArray(installedScripts) ? installedScripts : []
  manageGatewayScripts.value = Array.isArray(gatewayScripts) ? gatewayScripts : []
}

// 管理侧边栏展示的定时任务列表（只读，由 Agent 直接控制）
const manageTimers = ref([])
// 能力清单：浏览器扩展已安装脚本 + 网关脚本库（缓存，避免频繁请求，仅手动刷新）
const manageInstalledScripts = ref([])
const manageGatewayScripts = ref([])

// 弹窗控制
const showConnectModal = ref(true)  // 首次打开显示欢迎界面
const showSettingsModal = ref(false) // 设置弹窗
const showAdminPanel = ref(false) // 管理面板
const showAboutModal = ref(false) // 关于弹窗
// 「关于」面板数据：后端版本 / 节点 / daemon / 浏览器扩展
const aboutBackendVersion = ref('')
const aboutNodes = ref([])
const aboutDaemonSessions = ref([])
const aboutBrowserExtSessions = ref([])
const adminPanelRef = ref(null) // 管理面板组件引用（用于命令面板定位到系统配置）
const petWidgetRef = ref(null)        // 主宠物挂件组件引用（用于调用宠物显隐）
const showTerminalPanel = ref(false)  // 终端面板
const showChatPanel = ref(false)     // 聊天室面板
// 编辑器面板：唯一容器，默认打开。初始值取决于是否已有 Agent：
// 无 Agent 时保持关闭，露出宠物大厅（空状态）作为欢迎页；有 Agent 时打开编辑器承载会话。
const showWorkspacePanel = ref(false)
// 是否已因「首次拉取到 Agent」自动打开过编辑器（只自动打开一次，之后尊重用户手动关闭）
let workspaceAutoOpened = false
const sessionPanelRefs = new Map()  // panelId -> SessionPanel 组件实例

// 注册/注销 SessionPanel 组件实例（供 App 侧调用其暴露的 focusInput 等能力）。
// 说明：模板中同一 panel 可能由不同宿主（pane 叶子 / 编辑器主区域）渲染，
// 且 :ref 内联函数每次重渲染都会先以 null 注销、再以实例注册，故这里做幂等处理：
// - el 为空时仅当当前登记项确为该 panel 时才删除，避免误删其它宿主的有效引用；
// - panelId 为空（宿主已卸载、panel 已不存在）时直接忽略。
function setSessionPanelRef(panelId, el) {
  if (!panelId) return
  if (el) {
    sessionPanelRefs.set(panelId, el)
  } else if (sessionPanelRefs.has(panelId)) {
    sessionPanelRefs.delete(panelId)
  }
}

const showMobileMenu = ref(false)     // 移动端菜单
const activeWindow = ref(null)        // 当前焦点窗口: 'terminal' | 'workspace' | 'chat' | 'session' | null



// Rules 浮动窗口状态
const showRulesModal = ref(false)     // 显示rules浮动窗口
const rulesContent = ref([])          // rules内容（规则列表）
const rulesLoading = ref(false)       // 加载状态
const rulesLoadedContent = ref('')    // 已加载规则的具体内容

// 窗口z-index常量
const BASE_Z_INDEX = 1000
const ACTIVE_Z_INDEX = 1100

const EDITOR_SIDEBAR_DEFAULT_WIDTH = 360
const EDITOR_SIDEBAR_MIN_WIDTH = 200
const EDITOR_SIDEBAR_MAX_WIDTH = 560
const EDITOR_SIDEBAR_STORAGE_KEY = 'jarvis_workspace_sidebar_width'

function normalizeWorkspaceSidebarWidth(width) {
  return clamp(width, EDITOR_SIDEBAR_MIN_WIDTH, EDITOR_SIDEBAR_MAX_WIDTH)
}

function loadWorkspaceSidebarWidth() {
  const savedValue = localStorage.getItem(EDITOR_SIDEBAR_STORAGE_KEY)
  if (!savedValue) {
    return EDITOR_SIDEBAR_DEFAULT_WIDTH
  }

  const parsedWidth = Number(savedValue)
  if (!Number.isFinite(parsedWidth)) {
    return EDITOR_SIDEBAR_DEFAULT_WIDTH
  }

  return normalizeWorkspaceSidebarWidth(parsedWidth)
}

function saveWorkspaceSidebarWidth() {
  localStorage.setItem(EDITOR_SIDEBAR_STORAGE_KEY, String(workspaceSidebarWidth.value))
}

const workspaceSidebarWidth = ref(loadWorkspaceSidebarWidth())
const workspaceSidebarResizeState = ref({
  active: false,
  startX: 0,
  startWidth: EDITOR_SIDEBAR_DEFAULT_WIDTH,
})


const windowWidth = ref(window.innerWidth)  // 窗口宽度，用于响应式检测
const showCreateAgentModal = ref(false) // 创建 Agent 弹窗
const showQuickCreateAgentModal = ref(false) // 一句话创建 Agent 弹窗
const quickCreateAgentLoading = ref(false) // 一句话创建：请求中
const quickCreateAgentError = ref('') // 一句话创建：错误提示
const showRenameAgentModal = ref(false) // 重命名 Agent 弹窗
const renamingAgent = ref(null)          // 正在重命名的 Agent
const renameAgentName = ref('')           // 重命名的新名称
const selectedSession = ref(null)         // 选中的 session
const showBufferPanel = ref(false)        // 缓存管理面板显示状态
const bufferPanelAgentId = ref(null)      // 缓存管理面板对应的目标 Agent（点击的 Panel 所属 Agent）
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
// ===== 目录树：按节点打开任意目录（无需创建 Agent 即可浏览/编辑文件） =====
// 弹窗状态：节点 + 目录路径（手填或浏览选择）
const showOpenDirDialog = ref(false)
const openDirNodeId = ref('master')         // 目标节点
const openDirPath = ref('')                 // 目标目录（绝对路径）
const openDirInput = ref(null)              // 手填路径输入框引用
const openDirDialogRef = ref(null)          // 「打开目录」弹窗内嵌的 DirectoryDialog 引用
// 打开目录弹窗的来源：'workspace'=目录树打开工作区 / 'git'=Git 面板选择 Git 管理目录 / 'plugin'=插件请求选择目录
const openDirSource = ref('workspace')
// 插件请求选择目录时的 Promise resolver：确认时 resolve(路径)，取消时 resolve(null)
let pluginPickDirResolver = null
// Git 面板自定义 Git 管理目录（用户指定，优先于 Agent 根目录）：{ nodeId, path }
const gitCustomDir = ref(null)
// 自定义 Git 目录的持久化 key：刷新后自动恢复
const GIT_CUSTOM_DIR_STORAGE_KEY = 'jarvis_git_custom_dir'
function loadGitCustomDir() {
  try {
    const raw = localStorage.getItem(GIT_CUSTOM_DIR_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || !parsed.nodeId || !parsed.path) return null
    return { nodeId: String(parsed.nodeId), path: String(parsed.path) }
  } catch (e) {
    return null
  }
}
function saveGitCustomDir() {
  try {
    if (gitCustomDir.value?.nodeId && gitCustomDir.value?.path) {
      localStorage.setItem(GIT_CUSTOM_DIR_STORAGE_KEY, JSON.stringify(gitCustomDir.value))
    } else {
      localStorage.removeItem(GIT_CUSTOM_DIR_STORAGE_KEY)
    }
  } catch (e) {
    // localStorage 不可用（隐私模式 / 配额满）时静默降级
  }
}
// 目录浏览复用创建 Agent 的目录筛选状态（currentDirPath/dirList/selectedDir/dirSearchText）与逻辑
// 打开「按节点打开目录」弹窗（单弹窗：上选节点，下内嵌目录筛选）
// 目录浏览复用创建 Agent 的目录筛选逻辑（DirectoryDialog + fetchDirectories 等），仅节点来源不同
async function openOpenDirDialog() {
  showOpenDirDialog.value = true
  // 节点选项可能尚未加载（如未打开过创建 Agent 弹窗），这里补一次
  if (!availableNodeOptions.value.length) {
    try { await fetchNodeStatus() } catch (error) { /* 失败时保持空列表，弹窗内会提示 */ }
  }
  const allowed = filteredNodeOptionsForCreateAgent.value
  const preferred = allowed.some(n => n.node_id === openDirNodeId.value)
    ? openDirNodeId.value
    : (allowed[0]?.node_id || 'master')
  openDirNodeId.value = preferred
  openDirPath.value = ''
  // 内嵌目录筛选：从根目录开始浏览（不再弹独立弹窗）
  dirDialogContext.value = 'open-dir'
  selectedDir.value = '~'
  dirSearchText.value = ''
  selectedDirIndex.value = -1
  await fetchDirectories('~')
}
// 打开 Git 面板的「选择 Git 目录」弹窗（复用打开目录弹窗的节点+目录选择逻辑）
async function openGitDirDialog() {
  openDirSource.value = 'git'
  await openOpenDirDialog()
}
function closeOpenDirDialog() {
  showOpenDirDialog.value = false
  // 插件请求选择目录场景：取消时以 null 结束 Promise
  if (openDirSource.value === 'plugin' && pluginPickDirResolver) {
    const resolve = pluginPickDirResolver
    pluginPickDirResolver = null
    resolve(null)
  }
  // 复位场景，避免后续创建 Agent 的「选择目录」被误判为「打开目录」场景
  dirDialogContext.value = 'create-agent'
  openDirSource.value = 'workspace'
  resetDirectorySelectionState()
}
// 清除 Git 面板的自定义 Git 管理目录，回到按 Agent 根目录管理
function clearGitCustomDir() {
  gitCustomDir.value = null
  saveGitCustomDir()
  if (workspaceSidebarView.value === 'git') refreshGitView()
}
// Git 面板选择 Agent：清除自定义 Git 目录（回到按该 Agent 根目录管理），并刷新 Git 视图。
// 选择「跟随当前会话」（空值）时重置为 null，恢复随编辑器会话联动。
function onGitAgentChange(agentId) {
  gitAgentId.value = agentId ? agentId : null
  if (gitCustomDir.value) {
    gitCustomDir.value = null
    saveGitCustomDir()
  }
  if (workspaceSidebarView.value === 'git') refreshGitView()
}
// 切换目标节点：重新按新节点浏览目录
async function onOpenDirNodeChange(nodeId) {
  openDirNodeId.value = nodeId
  openDirPath.value = ''
  selectedDir.value = '~'
  dirSearchText.value = ''
  selectedDirIndex.value = -1
  await fetchDirectories('~')
}
// 在目录筛选列表中选中某项：同步到路径输入框（复用创建 Agent 的 selectDirectory）
function onOpenDirSelect(path) {
  selectDirectory(path)
  openDirPath.value = path
}
// 确认打开：以「手填路径」优先，其次「浏览选中目录」
async function confirmOpenDir() {
  const nodeId = String(openDirNodeId.value || 'master').trim() || 'master'
  const targetPath = String(openDirPath.value || selectedDir.value || '').trim()
  if (!targetPath) {
    showToast('请选择或输入目录路径', 'error')
    return
  }
  showOpenDirDialog.value = false
  // 复位场景，避免后续创建 Agent 的「选择目录」被误判为「打开目录」场景
  dirDialogContext.value = 'create-agent'
  resetDirectorySelectionState()
  if (openDirSource.value === 'plugin') {
    // 插件请求选择目录：以选中路径结束 Promise（不打开工作区）
    openDirSource.value = 'workspace'
    if (pluginPickDirResolver) {
      const resolve = pluginPickDirResolver
      pluginPickDirResolver = null
      resolve(targetPath)
    }
    return
  }
  if (openDirSource.value === 'git') {
    // Git 面板：把选中的目录设为 Git 管理目标，并刷新 Git 视图
    openDirSource.value = 'workspace'
    gitCustomDir.value = { nodeId, path: targetPath }
    saveGitCustomDir()
    if (workspaceSidebarView.value === 'git') refreshGitView()
    return
  }
  await openWorkspaceDir(nodeId, targetPath)
}

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


const workspacePanelStyle = computed(() => {
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
    top: `${workspacePanelRect.value.top}px`,
    left: `${workspacePanelRect.value.left}px`,
    width: `${workspacePanelRect.value.width}px`,
    height: `${workspacePanelRect.value.height}px`,
    zIndex: activeWindow.value === 'workspace' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
  }
})

const activeWorkspaceTab = computed(() => {
  return workspaceTabs.value.find(tab => tab.path === activeWorkspaceTabPath.value) || null
})

function clamp(value, min, max) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

function startWorkspaceSidebarResize(event) {
  if (windowWidth.value <= 768 || !showWorkspaceSidebar.value) return

  workspaceSidebarResizeState.value = {
    active: true,
    startX: event.clientX,
    startWidth: workspaceSidebarWidth.value,
  }

  document.addEventListener('mousemove', onWorkspaceSidebarResize)
  document.addEventListener('mouseup', stopWorkspaceSidebarResize)
  event.preventDefault()
  event.stopPropagation()
}

function onWorkspaceSidebarResize(event) {
  if (!workspaceSidebarResizeState.value.active) return

  const deltaX = event.clientX - workspaceSidebarResizeState.value.startX
  const nextWidth = workspaceSidebarResizeState.value.startWidth + deltaX
  workspaceSidebarWidth.value = normalizeWorkspaceSidebarWidth(nextWidth)
}

function stopWorkspaceSidebarResize() {
  if (!workspaceSidebarResizeState.value.active) {
    document.removeEventListener('mousemove', onWorkspaceSidebarResize)
    document.removeEventListener('mouseup', stopWorkspaceSidebarResize)
    return
  }

  workspaceSidebarResizeState.value = {
    active: false,
    startX: 0,
    startWidth: workspaceSidebarWidth.value,
  }

  document.removeEventListener('mousemove', onWorkspaceSidebarResize)
  document.removeEventListener('mouseup', stopWorkspaceSidebarResize)
  saveWorkspaceSidebarWidth()
}

// 设置焦点窗口
function focusWindow(windowType) {
  activeWindow.value = windowType
}

// 编辑器窗口最大化/还原
function toggleWorkspaceMaximize() {
  if (isWorkspaceMaximized.value) {
    // 还原
    if (workspacePanelRectBeforeMaximize.value) {
      workspacePanelRect.value = { ...workspacePanelRectBeforeMaximize.value }
    }
    isWorkspaceMaximized.value = false
  } else {
    // 最大化
    workspacePanelRectBeforeMaximize.value = { ...workspacePanelRect.value }
    workspacePanelRect.value = {
      top: 0,
      left: 0,
      width: window.innerWidth,
      height: window.innerHeight,
    }
    isWorkspaceMaximized.value = true
  }
  nextTick(() => {
    layoutMonacoEditor()
  })
}


function getWorkspacePanelBounds() {
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

function ensureWorkspacePanelInViewport() {
  const HEADER_HEIGHT = 32 // 标题栏高度
  const MIN_VISIBLE_WIDTH = 100 // 至少保留100px面板宽度可见
  const maxWidth = Math.max(window.innerWidth, EDITOR_PANEL_MIN_WIDTH)
  const maxHeight = Math.max(window.innerHeight, EDITOR_PANEL_MIN_HEIGHT)

  workspacePanelRect.value.width = clamp(workspacePanelRect.value.width, EDITOR_PANEL_MIN_WIDTH, maxWidth)
  workspacePanelRect.value.height = clamp(workspacePanelRect.value.height, EDITOR_PANEL_MIN_HEIGHT, maxHeight)

  // 标题栏不能移出窗口
  workspacePanelRect.value.left = clamp(
    workspacePanelRect.value.left,
    0, // 标题栏不能拖到窗口左侧之外
    window.innerWidth - MIN_VISIBLE_WIDTH // 保留至少100px面板宽度可见
  )
  workspacePanelRect.value.top = clamp(
    workspacePanelRect.value.top,
    0, // 标题栏不能拖到窗口顶部之外
    window.innerHeight - HEADER_HEIGHT // 保留标题栏高度可见
  )
}

function startWorkspacePanelMove(event) {
  if (windowWidth.value <= 768) return
  if (event.target.closest('.workspace-panel-actions')) return

  focusWindow('workspace')

  workspacePanelInteraction.value = {
    active: false,
    mode: 'move',
    direction: null,
    startX: event.clientX,
    startY: event.clientY,
    startTop: workspacePanelRect.value.top,
    startLeft: workspacePanelRect.value.left,
    startWidth: workspacePanelRect.value.width,
    startHeight: workspacePanelRect.value.height,
  }

  document.addEventListener('mousemove', onWorkspacePanelPointerMove)
  document.addEventListener('mouseup', stopWorkspacePanelInteraction)
}

function startWorkspacePanelResize(event, direction) {
  if (windowWidth.value <= 768) return

  workspacePanelInteraction.value = {
    active: true,
    mode: 'resize',
    direction,
    startX: event.clientX,
    startY: event.clientY,
    startTop: workspacePanelRect.value.top,
    startLeft: workspacePanelRect.value.left,
    startWidth: workspacePanelRect.value.width,
    startHeight: workspacePanelRect.value.height,
  }

  document.addEventListener('mousemove', onWorkspacePanelPointerMove)
  document.addEventListener('mouseup', stopWorkspacePanelInteraction)
  event.preventDefault()
  event.stopPropagation()
}

function onWorkspacePanelPointerMove(event) {
  const deltaX = event.clientX - workspacePanelInteraction.value.startX
  const deltaY = event.clientY - workspacePanelInteraction.value.startY

  if (workspacePanelInteraction.value.mode === 'move' && !workspacePanelInteraction.value.active) {
    const dragDistance = Math.hypot(deltaX, deltaY)
    if (dragDistance < PANEL_DRAG_ACTIVATION_DISTANCE) {
      return
    }

    workspacePanelInteraction.value = {
      ...workspacePanelInteraction.value,
      active: true,
    }
    event.preventDefault()
  }

  if (!workspacePanelInteraction.value.active) return

  if (workspacePanelInteraction.value.mode === 'move') {
    const bounds = getWorkspacePanelBounds()
    workspacePanelRect.value.left = clamp(workspacePanelInteraction.value.startLeft + deltaX, bounds.minLeft, bounds.maxLeft)
    workspacePanelRect.value.top = clamp(workspacePanelInteraction.value.startTop + deltaY, bounds.minTop, bounds.maxTop)
    return
  }

  const direction = workspacePanelInteraction.value.direction || ''
  const startLeft = workspacePanelInteraction.value.startLeft
  const startTop = workspacePanelInteraction.value.startTop
  const startWidth = workspacePanelInteraction.value.startWidth
  const startHeight = workspacePanelInteraction.value.startHeight

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

  workspacePanelRect.value.left = clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0))
  workspacePanelRect.value.top = clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0))
  workspacePanelRect.value.width = clamp(nextWidth, EDITOR_PANEL_MIN_WIDTH, Math.max(window.innerWidth - workspacePanelRect.value.left, EDITOR_PANEL_MIN_WIDTH))
  workspacePanelRect.value.height = clamp(nextHeight, EDITOR_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - workspacePanelRect.value.top, EDITOR_PANEL_MIN_HEIGHT))
}

function stopWorkspacePanelInteraction() {
  workspacePanelInteraction.value = {
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

  document.removeEventListener('mousemove', onWorkspacePanelPointerMove)
  document.removeEventListener('mouseup', stopWorkspacePanelInteraction)
  saveWorkspacePanelRect()
}

function getWorkspaceTabByPath(path) {
  return workspaceTabs.value.find(tab => tab.path === path) || null
}

function syncWorkspaceTabDirtyState(path, value) {
  const tab = getWorkspaceTabByPath(path)
  if (tab) {
    tab.isDirty = value
  }
}

function updateWorkspaceTabFileStat(tab, fileStat = {}) {
  if (!tab) return
  tab.mtimeNs = fileStat.mtime_ns ?? null
  tab.fileSize = fileStat.size ?? null
}

function markWorkspaceTabExternalModified(path, value) {
  const tab = getWorkspaceTabByPath(path)
  if (tab) {
    tab.externalModified = value
  }
}

// ===== 蓝色系 Monaco 主题（对应原 CodeMirror blueDark）=====
const EDITOR_FONT_FAMILY = "'Consolas', 'Microsoft YaHei', monospace"

monaco.editor.defineTheme('blueDark', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '5a7a9a' },
    { token: 'keyword', foreground: '7aa2f7' },
    { token: 'keyword.control', foreground: '7aa2f7' },
    { token: 'string', foreground: '9ece6a' },
    { token: 'string.escape', foreground: '56b6c2' },
    { token: 'number', foreground: 'e0af68' },
    { token: 'regexp', foreground: '56b6c2' },
    { token: 'operator', foreground: '56b6c2' },
    { token: 'delimiter', foreground: 'a8c8e8' },
    { token: 'type', foreground: 'e0af68' },
    { token: 'type.identifier', foreground: 'e0af68' },
    { token: 'namespace', foreground: 'e0af68' },
    { token: 'annotation', foreground: 'e0af68' },
    { token: 'modifier', foreground: 'e0af68' },
    { token: 'identifier', foreground: 'a8c8e8' },
    { token: 'variable', foreground: 'a8c8e8' },
    { token: 'variable.predefined', foreground: 'ff9e64' },
    { token: 'constant', foreground: 'ff9e64' },
    { token: 'tag', foreground: 'f7768e' },
    { token: 'attribute.name', foreground: 'f7768e' },
    { token: 'function', foreground: '82aaff' },
    { token: 'invalid', foreground: 'ffffff' },
    { token: 'strong', fontStyle: 'bold' },
    { token: 'emphasis', fontStyle: 'italic' },
    { token: 'strikethrough', fontStyle: 'strikethrough' },
  ],
  colors: {
    'editor.foreground': '#a8c8e8',
    'editor.background': '#0d1b2a',
    'editorCursor.foreground': '#528bff',
    'editor.lineHighlightBackground': '#1a2a3a55',
    'editor.selectionBackground': '#264f78',
    'editor.inactiveSelectionBackground': '#264f7855',
    'editor.selectionHighlightBackground': '#264f7855',
    'editor.findMatchBackground': '#72a1ff59',
    'editor.findMatchHighlightBackground': '#6199ff2f',
    'editorBracketMatch.background': '#264f78aa',
    'editorLineNumber.foreground': '#5a7a9a',
    'editorLineNumber.activeForeground': '#a8c8e8',
    'editorGutter.background': '#0d1b2a',
    'editorWidget.background': '#16263a',
    'editorWidget.border': '#1a2a3a',
    'editorSuggestWidget.background': '#16263a',
    'editorSuggestWidget.selectedBackground': '#1a2a3a',
    'editorHoverWidget.background': '#16263a',
    'editorHoverWidget.border': '#1a2a3a',
    'editorIndentGuide.background1': '#1a2a3a',
    'editorIndentGuide.activeBackground1': '#2a4a6a',
    'scrollbarSlider.background': '#1a2a3a88',
    'scrollbarSlider.hoverBackground': '#2a4a6aaa',
  },
})

// ===== 编辑器增强：VS Code 风格编辑能力 =====
// 说明：补全依赖 Monaco 内置的语言服务 worker（json/css/html/ts），
// 其余语言为词法级高亮；文件读写仍走网关远端接口。
const EDITOR_TAB_SIZE = 4

// ===== 自由分割：每个 file pane 一个独立 Monaco 实例 =====
// 设计要点（避免「多实例互相触发 layout 导致主线程卡死」）：
// 1) 实例创建/销毁只发生在 pane 容器集合真正变化时（ensureMonacoEditor 内做集合差分）；
// 2) 容器尺寸变化由 Monaco 自身的 automaticLayout(ResizeObserver) 处理，本文件不额外挂
//    ResizeObserver，也不在 resize 回调里对每个实例调 layout()，避免「layout → 尺寸变化 →
//    再 layout」的震荡；
// 3) 显式 layout() 一律经 scheduleWorkspaceLayout() 用 rAF 合并，同一帧内多次调用只执行一次。
const editorViews = new Map()  // paneId -> monaco editor instance
const workspaceViewPanes = new Map()  // paneId -> 该 pane 当前绑定的文件 path
// 自由分割：每个 diff pane 一个独立 Monaco DiffEditor 实例（paneId -> { editor, originalModel, modifiedModel, oldText, newText }）。
const diffEditorViews = new Map()
const diffContainerRefs = ref(new Map())  // paneId -> 容器元素
function setDiffContainerRef(paneId, el) {
  if (!paneId) return
  if (el) {
    if (diffContainerRefs.value.get(paneId) === el) return
    diffContainerRefs.value.set(paneId, el)
  } else {
    if (!diffContainerRefs.value.has(paneId)) return
    diffContainerRefs.value.delete(paneId)
  }
  triggerRef(diffContainerRefs)
  nextTick(() => {
    renderDiffForPane(paneId)
    scheduleDiffLayout()
  })
}
// 按 data-diff-pane-id 从文档解析「当前真实挂载」的容器（ref 元素可能是渲染中间态）
function resolveDiffContainer(paneId) {
  const live = document.querySelector(`.workspace-diff-monaco[data-diff-pane-id="${paneId}"]`)
  if (live && live.isConnected) return live
  const refEl = diffContainerRefs.value.get(paneId)
  return refEl && refEl.isConnected ? refEl : null
}
// 已分割时每个 pane 独立的标签列表（paneId -> path[]）。未分割时该 Map 为空，
// 标签栏仍由全局 workspaceTabs 驱动，保证未分割路径零回归。
// 目的：分割后两个 pane 的标签栏互不影响（关闭一个 pane 的标签不会连带关闭另一个）。
const workspacePaneTabs = new Map()  // paneId -> path[]
const workspacePaneTabsVersion = ref(0)  // 触发依赖 workspacePaneTabs 的模板/计算属性重算

function getPaneTabs(paneId) {
  if (!paneId) return []
  const paths = workspacePaneTabs.get(paneId)
  if (!paths || paths.length === 0) return []
  const all = workspaceTabs.value
  return paths.map(p => all.find(t => t.path === p)).filter(Boolean)
}

// 该 path 是否仍被某个 pane 的标签列表引用（用于判断关闭标签时能否真正释放模型）
function isPathReferencedByAnyPane(path) {
  for (const paths of workspacePaneTabs.values()) {
    if (paths.includes(path)) return true
  }
  return false
}

// 已分割时把 path 加入指定 pane 的标签列表（去重）
function addPaneTab(paneId, path) {
  if (!paneId || !path) return
  const paths = workspacePaneTabs.get(paneId) || []
  if (!paths.includes(path)) {
    paths.push(path)
    workspacePaneTabs.set(paneId, paths)
    workspacePaneTabsVersion.value += 1
  }
}

// 从指定 pane 的标签列表移除 path
function removePaneTab(paneId, path) {
  const paths = workspacePaneTabs.get(paneId)
  if (!paths) return
  const index = paths.indexOf(path)
  if (index === -1) return
  paths.splice(index, 1)
  workspacePaneTabsVersion.value += 1
}

// 当前激活 pane 的 Monaco 实例（激活 pane 非 file 时回退到任一实例）
function getActiveWorkspaceView() {
  const active = editorViews.get(activePaneId.value)
  if (active) return active
  for (const [, view] of editorViews) return view
  return null
}

function buildEditorOptions() {
  return {
    model: null,
    theme: 'blueDark',
    fontFamily: EDITOR_FONT_FAMILY,
    fontSize: 13,
    lineHeight: 20,
    tabSize: EDITOR_TAB_SIZE,
    insertSpaces: true,
    automaticLayout: true,
    minimap: { enabled: true },
    scrollBeyondLastLine: true,
    renderWhitespace: 'selection',
    smoothScrolling: true,
    cursorBlinking: 'smooth',
    mouseWheelZoom: true,
    bracketPairColorization: { enabled: true },
    guides: { bracketPairs: true, indentation: true },
    folding: true,
    showFoldingControls: 'mouseover',
    wordWrap: 'off',
    contextmenu: true,
    quickSuggestions: { other: true, comments: false, strings: true },
    suggestOnTriggerCharacters: true,
    tabCompletion: 'on',
    readOnly: !isWorkspaceEditable.value,
    readOnlyMessage: { value: '编辑器当前为只读，点击工具栏解锁后可编辑' },
  }
}

// 内容变更 → 回写该文件对应的 tab（模型上记录了 path，多 pane 打开同一文件时天然同步）
// ===== 光标历史（后退/前进，Ctrl+Alt+←/→）=====
// VS Code 的 navigateBack / navigateForward：记录光标「跳转」到的位置，可前后导航。
// Monaco standalone 无此内置功能，这里自行维护历史栈。
// 元素：{ path, line, column }；cursorHistoryIndex 为当前指针。
// 连续的光标移动（同文件、短时间）合并为一条记录，避免方向键逐字移动产生大量冗余；
// 后退/前进跳转期间置 cursorNavGuard，防止跳转本身被回写进历史。
const cursorHistory = []
let cursorHistoryIndex = -1
let lastCursorTime = 0
let cursorNavGuard = false
const CURSOR_MERGE_MS = 300 // 同文件连续光标移动在此窗口内合并为一条记录

// 记录一次光标位置。连续移动（同文件、短时间）合并更新当前记录，不新增。
function recordCursorLocation(path, line, column) {
  if (!path || !line) return
  if (cursorNavGuard) return // 后退/前进跳转中，不把跳转结果写回历史
  const now = Date.now()
  const current = cursorHistory[cursorHistoryIndex]
  // 与当前指针处完全相同 → 忽略
  if (current && current.path === path && current.line === line && current.column === column) return
  // 同文件且短时间内的连续移动 → 更新当前记录（光标随移动刷新）
  if (current && current.path === path && now - lastCursorTime < CURSOR_MERGE_MS) {
    cursorHistory[cursorHistoryIndex] = { path, line, column }
  } else {
    // 新增：截断指针之后的记录，追加新位置并前移指针
    cursorHistory.splice(cursorHistoryIndex + 1, cursorHistory.length - cursorHistoryIndex - 1)
    cursorHistory.push({ path, line, column })
    cursorHistoryIndex = cursorHistory.length - 1
  }
  lastCursorTime = now
}

// 后退到上一个光标位置（指针回退）
async function goToPreviousCursorLocation() {
  if (cursorHistoryIndex <= 0) return
  cursorHistoryIndex -= 1
  const loc = cursorHistory[cursorHistoryIndex]
  if (loc) {
    cursorNavGuard = true
    try {
      await revealInWorkspace(loc.path, loc.line, loc.column)
    } finally {
      cursorNavGuard = false
    }
  }
}

// 前进到下一个光标位置（指针前进）
async function goToNextCursorLocation() {
  if (cursorHistoryIndex >= cursorHistory.length - 1) return
  cursorHistoryIndex += 1
  const loc = cursorHistory[cursorHistoryIndex]
  if (loc) {
    cursorNavGuard = true
    try {
      await revealInWorkspace(loc.path, loc.line, loc.column)
    } finally {
      cursorNavGuard = false
    }
  }
}

function bindWorkspaceViewEvents(view) {
  // 重新聚焦编辑器时恢复原生快捷键控制（撤销 ESC「脱离」状态）：
  // 用户重新进入编辑器编辑，Ctrl+A 应恢复为编辑器全选。
  view.onDidFocusEditorText(() => {
    editorShortcutLocked.value = false
  })
  view.onDidChangeModelContent((e) => {
    const model = view.getModel()
    if (!model) return
    const path = model.__jarvisPath
    if (!path) return
    const tab = getWorkspaceTabByPath(path)
    if (!tab) return
    tab.content = model.getValue()
    tab.isDirty = tab.content !== tab.originalContent
  })
  // 记录光标位置（供 Ctrl+Alt+←/→ 后退/前进导航）：
  // 连续移动（同文件、短时间）合并为一条，跳转（跨文件/间隔）新增记录。
  view.onDidChangeCursorPosition((e) => {
    const model = view.getModel()
    if (!model) return
    const path = model.__jarvisPath
    if (!path) return
    const pos = e.position
    if (pos) recordCursorLocation(path, pos.lineNumber, pos.column)
  })
  // 跳转到定义：用纯 F12（Monaco 在编辑器聚焦时会拦截该键，浏览器不弹开发者工具）。
  // 不用 Monaco 内置 revealDefinition——它只能跳到已加载的 model，无法自动打开
  // 未打开的目标文件；这里拿到 LSP definition 结果后，若目标文件未打开则自行
  // openWorkspaceFile 打开再定位。
  view.addAction({
    id: 'jarvis.goToDefinition',
    label: 'Go to Definition',
    keybindings: [monaco.KeyCode.F12],
    contextMenuGroupId: 'navigation',
    contextMenuOrder: 1.5,
    run: (ed) => {
      jumpToDefinition(ed)
    },
  })
  // 后退/前进光标位置（Ctrl+Alt+←/→）。
  // 用 addAction 绑定：编辑器聚焦时优先于全局 Ctrl+Alt+方向键处理（切 pane/大厅）。
  view.addAction({
    id: 'jarvis.goToPreviousCursorLocation',
    label: 'Go to Previous Cursor Location',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.LeftArrow],
    run: () => {
      goToPreviousCursorLocation()
    },
  })
  view.addAction({
    id: 'jarvis.goToNextCursorLocation',
    label: 'Go to Next Cursor Location',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.RightArrow],
    run: () => {
      goToNextCursorLocation()
    },
  })
  // Ctrl+P 打开 Monaco 内置命令面板（editor.action.quickCommand，默认 F1）。
  // 全局 handler 在编辑器聚焦时让位给 Monaco，由这里的 addAction 接管 Ctrl+P。
  view.addAction({
    id: 'jarvis.openCommandPalette',
    label: 'Command Palette',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyP],
    run: (ed) => {
      ed.trigger('keyboard', 'editor.action.quickCommand', null)
    },
  })
}

// LSP file:// uri → 本地文件绝对路径（如 file:///home/a.py → /home/a.py）
function lspUriToPath(uri) {
  if (!uri) return ''
  const raw = String(uri)
  if (!raw.startsWith('file://')) return raw
  return decodeURIComponent(raw.slice('file://'.length))
}

// 从 LSP definition 结果中取第一个目标 {path, line, column}（支持 Location / LocationLink[]）
function pickFirstDefinitionTarget(result) {
  if (!result) return null
  const items = Array.isArray(result) ? result : [result]
  for (const it of items) {
    if (!it) continue
    const uri = it.targetUri || it.uri
    const range = it.targetRange || it.range
    if (!uri || !range) continue
    return {
      path: lspUriToPath(uri),
      line: (range.start?.line ?? 0) + 1,
      column: (range.start?.character ?? 0) + 1,
    }
  }
  return null
}

// Ctrl+F12 自定义跳转定义：拿到目标文件后，未打开则打开，再定位到目标行/列
async function jumpToDefinition(ed) {
  const model = ed && ed.getModel && ed.getModel()
  const position = ed && ed.getPosition && ed.getPosition()
  if (!model || !position) return
  const result = await getDefinition(model, position)
  const target = pickFirstDefinitionTarget(result)
  if (!target || !target.path) return
  await revealInWorkspace(target.path, target.line, target.column)
}

// 在工作区中打开（或激活）目标文件并定位到指定行列。
// 供 F12 跳转定义与 peek 双击跳转（registerEditorOpener）复用。
async function revealInWorkspace(path, line, column) {
  if (!path) return
  // 判断是否已作为标签打开（而非 editorModels 是否有 model——ensureModelForUri
  // 会预加载跨文件 model 但未建标签，若据此判断会误走 activateWorkspaceTab，
  // 导致不新建标签、只把当前缓冲区替换为目标文件内容）。
  // 有 tab 则激活，否则 openWorkspaceFile 新建标签并激活。
  if (!getWorkspaceTabByPath(path)) {
    await openWorkspaceFile(path)
  } else {
    activateWorkspaceTab(path)
  }
  await nextTick()
  const view = getActiveWorkspaceView()
  if (!view) return
  view.revealLineInCenter(line)
  view.setPosition({ lineNumber: line, column })
  view.focus()
}

// 注册 Monaco 资源 opener：当 Monaco 需要打开当前 model 之外的资源时（如 peek
// definition 窗口双击内容跳转、go-to-definition），回调这里。默认行为对未加载的
// model 什么都不做，故必须自行打开目标文件并定位，否则 peek 双击无法跳转。
// 返回 true 表示已处理，Monaco 不再走默认逻辑。
monaco.editor.registerEditorOpener({
  openCodeEditor: async (source, resource, selectionOrPosition) => {
    const path = lspUriToPath(resource?.toString?.() || '')
    if (!path) return false
    const line = selectionOrPosition?.startLineNumber ?? selectionOrPosition?.lineNumber ?? 1
    const column = selectionOrPosition?.startColumn ?? selectionOrPosition?.column ?? 1
    await revealInWorkspace(path, line, column)
    return true
  },
})
function applyEditorViewModel(paneId, view) {
  const path = workspaceViewPanes.get(paneId)
  if (!path) {
    if (view.getModel()) view.setModel(null)
    view.updateOptions({ readOnly: !isWorkspaceEditable.value })
    return
  }
  const modelData = editorModels.get(path)
  if (!modelData) {
    workspaceViewPanes.delete(paneId)
    if (view.getModel()) view.setModel(null)
    return
  }
  let model = modelData.model
  if (!model || model.isDisposed()) {
    model = monaco.editor.createModel(modelData.content, modelData.language, monaco.Uri.file(path))
    model.__jarvisPath = path
    modelData.model = model
  }
  if (view.getModel() !== model) view.setModel(model)
  view.updateOptions({ readOnly: !isWorkspaceEditable.value })
}

// 未分割时，Monaco 容器由 WorkspacePanel 内部渲染（editorContainerRef），沿用单实例路径。
// 为每个 file pane 的容器建立/复用实例；容器集合变化时才创建或销毁。
// 关键：ref 回调拿到的元素可能是「渲染中间态」元素（Vue 随后会替换掉它），把实例建在
// 这种脱离文档的元素上会导致编辑器 DOM 永久悬空（容器里看不到编辑器）。因此这里不直接
// 使用 ref 元素，而是按 data-pane-id 从文档中解析「当前真实挂载」的容器。
function resolveSplitWorkspaceContainer(paneId) {
  const live = document.querySelector(`.workspace-monaco-container[data-pane-id="${paneId}"]`)
  if (live && live.isConnected) return live
  const refEl = splitWorkspaceContainerRefs.value.get(paneId)
  return refEl && refEl.isConnected ? refEl : null
}

function ensureSplitMonacoEditors() {
  for (const paneId of [...splitWorkspaceContainerRefs.value.keys()]) {
    const container = resolveSplitWorkspaceContainer(paneId)
    // 容器尚未真正入文档时不要创建实例，等下一次调度（ref 回调 / rAF）补齐。
    if (!container) continue
    let view = editorViews.get(paneId)
    // 失效判定只看「宿主容器元素是否被替换」：Monaco 的编辑器 DOM 是异步挂载的，
    // getDomNode() 在无 model 时返回 null，创建后立刻 querySelector 也拿不到根节点，
    // 因此任何基于「实例 DOM 是否在容器里」的判断都会误判并导致反复 dispose/create。
    // 容器元素本身被 Vue 替换（pane 重建）时，才需要销毁旧实例、在新容器上重建。
    if (view && view.__jarvisContainer !== container) {
      view.dispose()
      editorViews.delete(paneId)
      view = null
    }
    if (!view) {
      view = monaco.editor.create(container, buildEditorOptions())
      view.__jarvisContainer = container
      bindWorkspaceViewEvents(view)
      editorViews.set(paneId, view)
    }
    applyEditorViewModel(paneId, view)
  }
  // 清理已消失 pane 的实例
  for (const [paneId, view] of [...editorViews]) {
    if (!splitWorkspaceContainerRefs.value.has(paneId)) {
      view.dispose()
      editorViews.delete(paneId)
      workspaceViewPanes.delete(paneId)
    }
  }
}

function ensureMonacoEditor() {
  ensureSplitMonacoEditors()
}




// 已分割时每个 pane 的标签列表由「打开文件 / 点击标签」时显式登记（addPaneTab），
// 新 pane 一律从空开始；不在这里用全局标签兜底补种，否则新 pane 会凭空出现
// 其他 pane 的标签（同一文件同时出现在两个 pane 顶部）。

// 显式 layout 合并到下一帧，避免同一帧内对多个实例反复 layout 造成尺寸震荡。
// 另外做有限次重试：ref 回调触发时容器可能尚未真正入文档（Vue 可能在插入前调用 ref），
// 此时建不了实例；等下一帧/下一个 tick 容器入文档后再补一次，避免「首次分割无实例」。
let workspaceLayoutScheduled = false
let workspaceLayoutRetries = 0
const EDITOR_LAYOUT_MAX_RETRIES = 8
function scheduleWorkspaceLayout() {
  if (workspaceLayoutScheduled) return
  workspaceLayoutScheduled = true
  requestAnimationFrame(() => {
    workspaceLayoutScheduled = false
    layoutMonacoEditor()
    if (workspaceLayoutRetries < EDITOR_LAYOUT_MAX_RETRIES) {
      const pending = [...splitWorkspaceContainerRefs.value.keys()].some((paneId) => {
        const container = resolveSplitWorkspaceContainer(paneId)
        if (!container) return false
        const view = editorViews.get(paneId)
        return !view || view.__jarvisContainer !== container
      })
      if (pending) {
        workspaceLayoutRetries += 1
        scheduleWorkspaceLayout()
        return
      }
    }
    workspaceLayoutRetries = 0
  })
}

function layoutMonacoEditor() {
  ensureSplitMonacoEditors()
  for (const [, view] of editorViews) {
    if (view.getContainerDomNode?.()?.isConnected) view.layout()
  }
}

// 自由分割：Monaco 视图绑定在具体 DOM 容器上，分割/激活/关闭 pane 时容器会被替换，
// 旧容器随 DOM 卸载后视图即失效。此处在容器变化后重建视图并恢复当前标签。
// 说明：模型（editorModels）与内容不受影响，仅重建视图层。
function remountMonacoEditor() {
  // 按容器集合差分补齐/复用实例（容器未变则复用，不会重建）
  ensureSplitMonacoEditors()
}

// 保存当前编辑器（激活 pane / 单实例）正在显示的文件的 view state（光标位置、滚动位置、选区、折叠）。
// Monaco 的 setModel 会重置光标与滚动，切换标签前必须先保存，否则切回来位置丢失。
function saveCurrentEditorViewState() {
  const currentPath = activeWorkspaceTabPath.value
  if (!currentPath) return
  const modelData = editorModels.get(currentPath)
  if (!modelData) return
  const view = editorViews.get(activePaneId.value)
  // 无 model 时 saveViewState 返回空状态，会覆盖已保存的 viewState（如 remountMonacoEditor 重建视图后）
  if (!view || !view.getModel()) return
  modelData.viewState = view.saveViewState()
}

// 恢复指定 pane 上目标文件的 view state（需在 setModel 之后调用）。
function restoreEditorViewState(view, path) {
  if (!view) return
  const modelData = editorModels.get(path)
  if (!modelData?.viewState) return
  view.restoreViewState(modelData.viewState)
}

function activateWorkspaceTab(path) {
  // 切换前先保存当前文件的 view state（光标+滚动），否则 setModel 重置后位置丢失
  saveCurrentEditorViewState()
  const session = activeWorkspaceSession.value
  if (session) session.activeTabPath = path
  const modelData = editorModels.get(path)
  if (!modelData) return
  let model = modelData.model
  if (!model || model.isDisposed()) {
    model = monaco.editor.createModel(modelData.content, modelData.language, monaco.Uri.file(path))
    model.__jarvisPath = path
    modelData.model = model
  }
  // 只把「激活 pane」绑定到该文件；其他 pane 保持各自内容（新 pane 为空）
  ensureSplitMonacoEditors()
  const activeView = editorViews.get(activePaneId.value)
  if (activeView) {
    // 该文件登记到激活 pane 的标签列表（点击标签/打开文件都走这里）
    addPaneTab(activePaneId.value, path)
    workspaceViewPanes.set(activePaneId.value, path)
    if (activeView.getModel() !== model) activeView.setModel(model)
    restoreEditorViewState(activeView, path)
    activeView.updateOptions({ readOnly: !isWorkspaceEditable.value })
    nextTick(() => {
      scheduleWorkspaceLayout()
      activeView.focus()
    })
  }
  // 模型就绪后尝试接入 LSP（失败静默降级，不影响编辑器）
  activateLspForModel(path, modelData)
}

// ---------------------------------------------------------------------------
// LSP 接入（薄层：所有逻辑在 src/lsp/ 模块内，此处只做时机编排）
// ---------------------------------------------------------------------------

// 语言清单只需拉一次，失败也不阻塞编辑器
let lspRegistryReady = false
async function ensureLspRegistry() {
  if (lspRegistryReady) return
  try {
    await loadLspServers({
      fetchWithAuth,
      getGatewayAddress,
      getHttpProtocol,
    })
    lspRegistryReady = true
  } catch {
    // registry 内部已降级处理，这里兜底
  }
}

// 记录 path -> { serverId, root }，供关闭标签时精确释放
const lspBindings = new Map()

/**
 * 为当前模型接入 LSP。
 *
 * 已知限制：仅支持 master 本地（文件读写走 /api/node/{id}/... 时，
 * 非 master 节点的文件系统与本地 LSP 进程不一致，故跳过）。
 */
async function activateLspForModel(path, modelData) {
  if (!path || !modelData || !modelData.model) return
  // 只读预览、非 master 节点：不接入
  if (getWorkspaceTargetNodeId() !== 'master') return

  await ensureLspRegistry()

  const language = modelData.model.getLanguageId?.() || modelData.language
  const spec = getServerByLanguage(language) || getServerByPath(path)
  if (!spec) return

  const workspaceRoot = resolveLspWorkspaceRoot(path)
  const client = await ensureClient({
    spec,
    workspaceRoot,
    model: modelData.model,
    deps: { fetchWithAuth, getGatewayAddress, getWebSocketProtocol, buildWebSocketProtocols, ensureModelForUri },
  })
  if (client) {
    lspBindings.set(path, { serverId: spec.id, root: workspaceRoot })
  }
}

/**
 * 确保 file:// uri 对应的 Monaco model 已存在（跨文件 peek definition 需要）。
 *
 * Monaco 内置 peek 通过 monaco.editor.getModel(uri) 取目标 model 渲染内容；
 * 目标文件从未打开过时 model 不存在 → peek 只显示文件名/行列号、内容空白。
 * 这里在 definition provider 返回前异步加载目标文件并创建 model（不激活标签、
 * 不创建 workspace tab），让 peek 能拿到内容。已加载则直接复用。
 *
 * @param {string} uri LSP file:// uri
 * @returns {Promise<void>}
 */
async function ensureModelForUri(uri) {
  if (!uri) return
  const raw = String(uri)
  const path = raw.startsWith('file://') ? decodeURIComponent(raw.slice('file://'.length)) : raw
  if (!path) return
  const existing = editorModels.get(path)
  if (existing && existing.model && !existing.model.isDisposed()) return
  // 只读预览、非 master 节点：无法读取远端文件内容，跳过（保持原有降级）
  if (getWorkspaceTargetNodeId() !== 'master') return
  const content = await fetchFileContent(path)
  const spec = getServerByPath(path)
  const language = spec?.monacoLanguage || 'plaintext'
  let model = existing?.model
  if (!model || model.isDisposed()) {
    model = monaco.editor.createModel(content, language, monaco.Uri.file(path))
    model.__jarvisPath = path
  } else {
    model.setValue(content)
  }
  editorModels.set(path, { model, content, language })
}

/** 由文件路径推导 workspace 根目录（取所在目录，后端会校验其存在性）。 */
function resolveLspWorkspaceRoot(path) {
  const normalized = String(path || '')
  const idx = normalized.lastIndexOf('/')
  return idx > 0 ? normalized.slice(0, idx) : ''
}

/**
 * 释放某个文件绑定的 LSP 连接。
 * 仅当同一 (serverId, root) 已无其他文件在用时才真正关闭连接，
 * 避免频繁开关标签导致反复重启语言服务器。
 */
function releaseLspBinding(path) {
  const binding = lspBindings.get(path)
  if (!binding) return
  lspBindings.delete(path)

  for (const other of lspBindings.values()) {
    if (other.serverId === binding.serverId && other.root === binding.root) {
      return // 仍有其他文件在用同一连接
    }
  }
  disposeClient(binding.serverId, binding.root)
}

function resolveAgentRelativePath(relativePath, agentId = null) {
  if (!relativePath) return ''
  const raw = String(relativePath)
  // 绝对路径直接返回，不做 working_dir 拼接（否则会把绝对路径当相对路径拼出重复前缀）
  if (raw.startsWith('/')) return raw
  // 优先用指定 Agent 的工作目录解析（命令面板/搜索场景应使用其对应的 Agent，
  // 而非 currentAgent——两者可能不一致，导致拼出相对路径触发 Monaco「path must be absolute」）。
  let workingDir = ''
  if (agentId) {
    const agent = agentList.value.find(a => a.agent_id === agentId)
    workingDir = agent?.working_dir || ''
  }
  if (!workingDir) workingDir = currentAgent.value?.working_dir || ''
  if (!workingDir) return raw
  return `${workingDir.replace(/\/$/, '')}/${raw.replace(/^\//, '')}`
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

async function fetchFileSearchResults(agentId, payload) {
  const { host, port } = getGatewayAddress()
  const agent = agentList.value.find(a => a.agent_id === agentId)
  if (!agent) {
    throw new Error(`找不到Agent: ${agentId}`)
  }
  if (!agent.node_id) {
    throw new Error(`Agent没有node_id: ${agentId}`)
  }
  const targetNodeId = String(agent.node_id).trim()
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `file-search/${agentId}`), {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      node_id: targetNodeId,
    })
  })
  const result = await response.json()
  if (!response.ok || !result.success || !result.data) {
    throw new Error(result.error?.message || '文件名搜索失败')
  }
  return result.data
}

const hasWorkspaceSidebarFileTree = computed(() => {
  const agentId = activeWorkspaceSessionId.value
  if (!agentId) return false
  return getVisibleFileTreeNodes(agentId).length > 0
})

async function ensureWorkspaceSidebarFileTree(agent = activeWorkspaceSession.value?.agent) {
  if (!agent?.agent_id || !agent.working_dir) return
  const treeNodes = fileTreeState.value.get(agent.agent_id) || []
  if (treeNodes.length === 0) {
    await initFileTree(agent.agent_id, agent.working_dir)
  }
}

function setWorkspaceSidebarView(view) {
  workspaceSidebarView.value = view
  showWorkspaceSidebar.value = true
  if (view === 'files') {
    nextTick(() => {
      ensureWorkspaceSidebarFileTree()
      layoutMonacoEditor()
    })
    return
  }
  if (view === 'git') {
    // 切到 Git 视图时自动刷新提交历史与分支（每次切换都拉取最新，避免停留在旧数据）
    nextTick(() => {
      layoutMonacoEditor()
      layoutGitDiffEditor()
      if (!gitLogLoading.value) {
        refreshGitView()
      }
    })
    return
  }
  if (view === 'manage') {
    // 切到能力清单视图：数据缓存，避免频繁请求；仅首次打开（四个数据源均为空）时加载，
    // 之后靠侧边栏内「刷新」按钮手动刷新。
    // 注意：不能用 topologyDaemonSessions/topologyExtensionSessions 是否为空来判断——
    // 这两个 ref 与网络拓扑图共享，可能已被拓扑图轮询填充，导致 installedScripts/
    // gatewayScripts 永远不加载（网关脚本库区块不显示）。
    if (
      !topologyDaemonSessions.value.length &&
      !topologyExtensionSessions.value.length &&
      !manageInstalledScripts.value.length &&
      !manageGatewayScripts.value.length
    ) {
      refreshManageCapabilities()
    }
    nextTick(() => {
      layoutMonacoEditor()
    })
    return
  }
  if (view === 'timers') {
    // 切到定时任务视图：任务会变化，拉取最新列表（只读展示）
    refreshManageTimers()
    nextTick(() => {
      layoutMonacoEditor()
    })
    return
  }
  if (view === 'plugins') {
    // 切到插件视图：插件列表可能变化，拉取最新（组件内部通过 watch 自行加载）
    nextTick(() => {
      layoutMonacoEditor()
    })
    return
  }
  nextTick(() => {
    layoutMonacoEditor()
  })
}

// 活动栏按钮点击：已打开该侧边栏视图时再次点击则收起，否则切换到该视图。
function toggleWorkspaceSidebarView(view) {
  if (showWorkspaceSidebar.value && workspaceSidebarView.value === view) {
    closeWorkspaceSidebar()
    return
  }
  setWorkspaceSidebarView(view)
}

// 活动栏按钮点击（聊天室/终端）：已打开该主视图时再次点击则回到文件视图。
// 已统一为 pane 树：host 由某个 pane 承载（未分割时唯一 leaf 即承载 pane）。
function toggleWorkspaceMainView(view) {
  const hostedByPane = !!findWorkspacePaneByView(view)
  if (workspaceMainView.value === view || hostedByPane) {
    setWorkspaceMainView('file')
    return
  }
  setWorkspaceMainView(view)
}

// 切换编辑器主区域视图（file / chat / terminal）
function setWorkspaceMainView(view) {
  // 已统一为 pane 树：pane 树本身承载 file/session 内容，主区域视图恒为 file，
  // 因此这里不改 workspaceMainView、也不收起分割（会话显示在各自的 pane 中）。
  // 「收起」语义（切回 file）必须在此提前处理，否则会被下面的 workspaceMainView === view 早退吞掉。
  if (view === 'file') {
    // 收起：把承载 chat / terminal 的 pane 清成中性空白（host 单例，至多一个）
    const hostPane = findWorkspacePaneByView('chat') || findWorkspacePaneByView('terminal')
    if (hostPane) setActivePaneViewForPane(hostPane, 'empty')
    // 未分割（唯一 leaf）时若主区域不是文件视图，原地切回文件并重排 Monaco
    if (workspacePaneCount.value === 1 && workspaceMainView.value !== 'file') {
      setMainViewOnLeaf('file')
      nextTick(() => {
        layoutMonacoEditor()
        layoutGitDiffEditor()
      })
    }
    return
  }
  if (view === 'session') {
    // session 由 pane 承载：交给 ensurePaneForView 定位承载 pane（未分割时唯一 leaf 原地承载）
    ensurePaneForView('session', workspaceSessionPanelId.value)
    return
  }
  // chat / terminal：空则原地、已有则复用、否则分割（不覆盖当前区域）
  ensurePaneForView(view)
  return
}

// 在工作区中显示 chat / terminal（host 单例）：确保工作区面板已打开，再交给主区域或激活 pane 承载。
// 面板分离能力移除后，chat/terminal 只能在工作区内部渲染，因此任何「打开终端/聊天室」的入口
// 都必须走这里，而不是去改已废弃的 showTerminalPanel / showChatPanel 标志。
function showWorkspaceHostView(view) {
  if (!showWorkspacePanel.value) {
    showWorkspacePanel.value = true
    if (windowWidth.value <= 768) pushOverlayState()
  }
  setWorkspaceMainView(view)
}

// 让主区域回到「文件视图」（打开文件时调用）。
// 主区域的 file/chat/terminal/session 四种内容是互斥的，打开文件类内容必须先切回文件视图，
// 否则会被 chat/terminal/session 内容挡住。
function showWorkspaceFileView() {
  if (workspaceMainView.value !== 'file') {
    setMainViewOnLeaf('file')
  }
  // 切回后容器尺寸可能变化，重排 Monaco（含 diff），确保内容正确渲染
  nextTick(() => {
    layoutMonacoEditor()
    layoutGitDiffEditor()
  })
}

function toggleWorkspaceSearchSidebar() {
  if (showWorkspaceSidebar.value && workspaceSidebarView.value === 'search') {
    closeWorkspaceSidebar()
    return
  }
  setWorkspaceSidebarView('search')
}

function closeWorkspaceSidebar() {
  showWorkspaceSidebar.value = false
  // 侧栏收起不影响主区域 diff，仅重排主编辑器
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
  fileSearchResults.value = []
  globalSearchTotalFiles.value = 0
  globalSearchTotalMatches.value = 0
  globalSearchExecuted.value = false
}

async function runGlobalSearch() {
  const searchAgentId = effectiveGlobalSearchAgentId.value
  if (!searchAgentId) {
    showToast('请先选择 Agent', 'error')
    return
  }

  const query = globalSearchQuery.value.trim()
  if (!query) {
    globalSearchError.value = '请输入搜索关键词'
    globalSearchExecuted.value = false
    globalSearchResults.value = []
    fileSearchResults.value = []
    setWorkspaceSidebarView('search')
    return
  }

  setWorkspaceSidebarView('search')
  globalSearchLoading.value = true
  globalSearchError.value = ''
  globalSearchExecuted.value = false

  try {
    if (globalSearchMode.value === 'filename') {
      const data = await fetchFileSearchResults(searchAgentId, {
        query,
        case_sensitive: globalSearchCaseSensitive.value,
        max_results: 200,
        file_glob: globalSearchFileGlob.value.trim(),
      })
      fileSearchResults.value = Array.isArray(data.results) ? data.results : []
      globalSearchTotalFiles.value = Number(data.total_files || 0)
      globalSearchTotalMatches.value = 0
      globalSearchExecuted.value = true
      return
    }
    const data = await fetchGlobalSearchResults(searchAgentId, {
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
    fileSearchResults.value = []
    globalSearchTotalFiles.value = 0
    globalSearchTotalMatches.value = 0
    globalSearchExecuted.value = true
    showToast(globalSearchError.value, 'error')
  } finally {
    globalSearchLoading.value = false
  }
}

function setGlobalSearchMode(mode) {
  if (globalSearchMode.value === mode) return
  globalSearchMode.value = mode
  globalSearchError.value = ''
  globalSearchExecuted.value = false
  globalSearchResults.value = []
  fileSearchResults.value = []
  globalSearchTotalFiles.value = 0
  globalSearchTotalMatches.value = 0
}

function openFileSearchResult(filePath) {
  openWorkspaceFile(resolveAgentRelativePath(filePath, effectiveGlobalSearchAgentId.value), effectiveGlobalSearchAgentId.value)
}

async function openGlobalSearchResult(filePath, lineNumber, matchStart = 0, matchEnd = matchStart) {
  const absolutePath = resolveAgentRelativePath(filePath, effectiveGlobalSearchAgentId.value)
  // 使用全局搜索侧边栏选中的 Agent
  await openWorkspaceFile(absolutePath, effectiveGlobalSearchAgentId.value)
  await nextTick()
  const modelData = editorModels.get(absolutePath)
  const view = getActiveWorkspaceView()
  if (!view || !modelData) {
    return
  }

  // Monaco: 通过 setPosition / setSelection + revealLineInCenter 定位
  const line = Number(lineNumber || 1)
  const col = Number(matchStart || 0) + 1
  const endCol = Math.max(col, Number(matchEnd || matchStart || 0) + 1)

  view.revealLineInCenter(line)
  view.setSelection(new monaco.Selection(line, col, line, endCol))
  view.setPosition({ lineNumber: line, column: col })
  view.focus()
}

async function fetchFileContent(path, agentId = null) {
  const { host, port } = getGatewayAddress()
  // 如果提供了agentId，使用对应的node_id；否则使用当前激活编辑器会话的node_id
  let targetNodeId
  if (agentId) {
    const agent = agentList.value.find(a => a.agent_id === agentId) || getVirtualWorkspaceAgent(agentId)
    if (!agent) {
      throw new Error(`找不到Agent: ${agentId}`)
    }
    if (!agent.node_id) {
      throw new Error(`Agent没有node_id: ${agentId}`)
    }
    targetNodeId = String(agent.node_id).trim()
  } else {
    targetNodeId = getWorkspaceTargetNodeId()
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
    const agent = agentList.value.find(a => a.agent_id === agentId) || getVirtualWorkspaceAgent(agentId)
    if (!agent) {
      throw new Error(`找不到Agent: ${agentId}`)
    }
    if (!agent.node_id) {
      throw new Error(`Agent没有node_id: ${agentId}`)
    }
    targetNodeId = String(agent.node_id).trim()
  } else {
    targetNodeId = getWorkspaceTargetNodeId()
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

async function refreshWorkspaceTabFromRemote(path, showAutoRefreshToast = false) {
  const tab = getWorkspaceTabByPath(path)
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
  updateWorkspaceTabFileStat(tab, fileStat)

  const modelData = editorModels.get(path)
  if (modelData && modelData.content !== content) {
    modelData.content = content
    // 模型是共享的：直接更新 model 内容，所有打开该文件的 pane 都会同步
    const model = modelData.model
    if (model && !model.isDisposed()) {
      model.setValue(content)
    }
  }

  if (showAutoRefreshToast) {
    showToast('检测到文件已更新，已自动刷新', 'info')
  }
}

async function checkActiveWorkspaceFileHeartbeat() {
  if (!showWorkspacePanel.value) return

  const tab = activeWorkspaceTab.value
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

    await refreshWorkspaceTabFromRemote(tab.path, true)
  } catch (error) {
    console.error('[EDITOR] File heartbeat check failed:', error)
  }
}

function stopWorkspaceFileHeartbeat() {
  if (workspaceFileHeartbeatTimer.value) {
    clearInterval(workspaceFileHeartbeatTimer.value)
    workspaceFileHeartbeatTimer.value = null
  }
}

function startWorkspaceFileHeartbeat() {
  stopWorkspaceFileHeartbeat()

  if (!showWorkspacePanel.value || !activeWorkspaceTab.value) {
    return
  }

  workspaceFileHeartbeatTimer.value = setInterval(() => {
    checkActiveWorkspaceFileHeartbeat()
  }, EDITOR_FILE_HEARTBEAT_INTERVAL)
}

async function openWorkspaceFile(path, agentId = null) {
  if (!path) return

  showWorkspacePanel.value = true
  // 智能定位打开位置（点击侧边文件）：
  //  1) 当前活动区域为空 → 在当前区域创建编辑器；
  //  2) 否则复用已打开的编辑器面板（不覆盖当前会话/聊天/终端）；
  //  3) 否则分割当前区域创建新编辑器。
  // 返回 paneId 表示已定位到某分割 pane；返回 null 表示走未分割的原地路径。
  const targetPaneId = ensureEditorPaneForFileOpen(agentId)
  // 打开文件属于「文件视图」：未分割且原地打开时，若主区域停在 chat/terminal/session，
  // 需先切回文件视图，否则文件（及 diff）会被这些内容挡住。
  // （已分割时由 ensureEditorPaneForFileOpen 负责定位到 file pane，无需再切。）
  if (!targetPaneId) {
    showWorkspaceFileView()
  }

  const existingTab = getWorkspaceTabByPath(path)
  if (existingTab) {
    // 已统一为 pane 树：把该文件登记到「激活 pane」的标签列表（同一文件可同时出现在多个 pane）
    addPaneTab(activePaneId.value, path)
    activateWorkspaceTab(path)
    return
  }

  const tab = reactive({
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
  })
  const session = activeWorkspaceSession.value
  if (!session) {
    // 编辑器面板可能通过 Ctrl+E / 命令面板打开（只设 showWorkspacePanel，未创建会话）。
    // 此时按传入的 agentId 或当前 Agent 补建会话，避免点击文件静默无反应。
    // 注意：虚拟目录会话（未创建 Agent 时打开的目录）不在 agentList 中，且刷新后
    // activeWorkspaceSession 为空（restoreVirtualWorkspaceDirs 只恢复会话不激活），
    // 因此必须优先按 agentId 命中已存在的虚拟会话并激活，否则点击文件会静默无反应。
    const virtualSession = agentId
      ? workspaceSessions.value.find(s => s.agent_id === agentId && s.agent?.virtual === true)
      : null
    if (virtualSession) {
      activeWorkspaceSessionId.value = agentId
    } else {
      const targetAgent = (agentId && agentList.value.find(a => a.agent_id === agentId))
        || getCurrentAgentOrNull()
      if (!targetAgent) return
      createWorkspaceForAgent(targetAgent)
      if (!activeWorkspaceSession.value) return
    }
  }
  const activeSession = activeWorkspaceSession.value
  activeSession.tabs.push(tab)
  activeSession.activeTabPath = path
  // 已统一为 pane 树：新文件登记到「激活 pane」的标签列表
  addPaneTab(activePaneId.value, path)

  try {
    const [content, fileStat] = await Promise.all([
      fetchFileContent(path, agentId),
      fetchFileStat(path, agentId),
    ])
    tab.content = content
    tab.originalContent = content
    tab.externalModified = false
    updateWorkspaceTabFileStat(tab, fileStat)
    tab.loading = false

    let modelData = editorModels.get(path)
    if (!modelData) {
      modelData = { model: null, content, language: getLanguageExtension(tab.language) }
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
    ensureMonacoEditor()
    activateWorkspaceTab(path)
  } catch (error) {
    tab.loading = false
    tab.error = error.message || '读取文件失败'
  }
}

// ===== 工作区 pane 树 / 自由分割 / 侧边栏（从 App.vue 拆出到 composables/useWorkspacePane.js）=====
const {
  // 常量
  EDITOR_PANEL_MIN_WIDTH, EDITOR_PANEL_MIN_HEIGHT, workspaceResizeDirections, PANEL_DRAG_ACTIVATION_DISTANCE,
  // workspace 面板状态
  isWorkspaceMaximized, workspacePanelRectBeforeMaximize, saveWorkspacePanelRect,
  workspacePanelRect, workspacePanelInteraction, workspacePanelRef,
  splitWorkspaceContainerRefs, setSplitWorkspaceContainerRef, editorContainerRef,
  // 会话/标签
  workspaceSessions, activeWorkspaceSessionId, workspaceTabs, activeWorkspaceTabPath,
  activeWorkspaceSession, virtualWorkspaceSessions, editorModels,
  workspaceFileHeartbeatTimer, isWorkspaceEditable, EDITOR_FILE_HEARTBEAT_INTERVAL,
  // 全局搜索
  globalSearchQuery, globalSearchFileGlob, globalSearchCaseSensitive, globalSearchWholeWord,
  globalSearchLoading, globalSearchError, globalSearchResults, globalSearchTotalFiles,
  globalSearchTotalMatches, globalSearchExecuted, globalSearchMode, fileSearchResults,
  // 侧边栏
  showWorkspaceSidebar, workspaceSidebarView, workspaceMainView,
  // pane 树核心
  workspacePaneTree, activePaneId, maximizedPaneId, workspacePaneCount, activePane,
  findWorkspacePaneById, activateWorkspacePane, toggleMaximizeWorkspacePane,
  moveActivePaneInDirection, splitWorkspacePane, closeWorkspacePane, collapseWorkspacePanes,
  findWorkspacePaneBySessionPanelId, findWorkspacePaneByView, ensureAgentEditorPane,
  ensureEditorPaneForFileOpen, setMainViewOnLeaf, ensurePaneForView, setActivePaneView,
  setActivePaneViewForPane, getWorkspacePaneTitle, getWorkspacePaneStatus, getPanePanel,
  isPaneActive, startWorkspacePaneResize, persistWorkspacePaneLayout,
  restoreWorkspacePaneLayout, restoreWorkspacePaneContents,
  // 插件扩展（usePlugins 返回透传）
  pluginExtensions, pluginAdminTabs, pluginSidebarViews, pluginToolPanels,
  pluginSidebarTitle, pluginToolPanelTitle, WORKSPACE_SIDEBAR_TITLES, workspaceSidebarTitle,
  loadPluginExtensionsForUi, resolvePluginExtensionComponent, isPluginSidebarView,
  isPluginToolView, pluginSidebarCompCache, activePluginSidebarComp, activePluginToolPanelComp,
} = useWorkspacePane({
  // 直传（定义在本调用点之前）
  fetchWithAuth,
  getGatewayAddress,
  getHttpProtocol,
  hasAuthToken,
  windowWidth,
  clamp,
  focusWindow,
  getWorkspaceTabByPath,
  activeWorkspaceTab,
  editorViews,
  workspaceViewPanes,
  diffEditorViews,
  workspacePaneTabs,
  workspacePaneTabsVersion,
  remountMonacoEditor,
  scheduleWorkspaceLayout,
  layoutMonacoEditor,
  activateWorkspaceTab,
  openWorkspaceFile,
  // getter 注入（来自 useGitView 解构，定义在本调用点之后，useWorkspacePane 内部以 xxx()() 二次求值）
  layoutGitDiffEditor: () => layoutGitDiffEditor,
  disposeDiffEditorForPane: () => disposeDiffEditorForPane,
  disposeAllDiffEditors: () => disposeAllDiffEditors,
  loadDiffForPane: () => loadDiffForPane,
  // getter 注入（定义在调用点之后，useWorkspacePane 内部以 xxx() 二次求值）
  panels: () => panels,
  activePanelId: () => activePanelId,
  closePanel: () => closePanel,
  getPanelAgent: () => getPanelAgent,
  workspaceSessionPanelId: () => workspaceSessionPanelId,
  agentList: () => agentList,
  gitAgentId: () => gitAgentId,
  switchAgent: () => switchAgent,
  activeTerminalId: () => activeTerminalId,
  terminalSessions: () => terminalSessions,
  restoreTerminalSessions: () => restoreTerminalSessions,
  focusFirstIn: () => focusFirstIn,
})

async function saveWorkspaceTab(path) {
  const tab = getWorkspaceTabByPath(path)
  if (!tab) return

  const modelData = editorModels.get(path)
  const content = modelData ? modelData.content : tab.content

  const { host, port } = getGatewayAddress()
  const targetNodeId = getWorkspaceTargetNodeId()
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
    updateWorkspaceTabFileStat(tab, fileStat)
  } catch (error) {
    console.error('[EDITOR] Failed to refresh file stat after save:', error)
  }

  showToast(`${getNodeDisplayName(targetNodeId)}节点的${path}已保存`, 'success')
}

async function saveActiveWorkspaceTab() {
  if (!activeWorkspaceTab.value) return
  await saveWorkspaceTab(activeWorkspaceTab.value.path)
}

// 保存指定 pane 当前绑定的文件（每个 pane 内的保存按钮调用）
async function savePaneWorkspaceFile(paneId) {
  const path = workspaceViewPanes.get(paneId)
  if (!path) return
  await saveWorkspaceTab(path)
}

function toggleWorkspaceEditable() {
  isWorkspaceEditable.value = !isWorkspaceEditable.value
  for (const [, view] of editorViews) {
    view.updateOptions({ readOnly: !isWorkspaceEditable.value })
  }
}

function hasDirtyWorkspaceTabs() {
  return workspaceTabs.value.some(tab => tab.isDirty)
}

function confirmCloseWorkspacePanel() {
  return new Promise((resolve) => {
    showConfirm(
      '存在未保存标签，确定关闭编辑器吗？',
      () => resolve(true),
      () => resolve(false),
      false
    )
  })
}

// 编辑器主区域正承载终端/聊天时，对应独立面板的显示状态是被内嵌取代的遗留值；
// 关闭编辑器前需复位，否则独立面板会「凭空」浮现（如编辑器内新建终端后关闭编辑器）。
// 同时复位主区域视图，避免下次打开编辑器直接进入终端/聊天视图。
function resetWorkspaceHostedPanelState() {
  if (workspaceHostsTerminal.value) showTerminalPanel.value = false
  if (workspaceHostsChat.value) showChatPanel.value = false
  setMainViewOnLeaf('file')
  // 关闭编辑器时一并收起自由分割，避免下次打开残留多 pane 布局
  if (workspacePaneCount.value > 1) collapseWorkspacePanes()
  // 内嵌会话 Panel 只在编辑器内部渲染：编辑器关闭后它们失去宿主，
  // 若继续留在 panels 中会既不可见、又让 hasNoPanel 恒为 false（宠物大厅不显示）。
  // 因此关闭编辑器时一并关闭所有会话 Panel。
  for (const panel of [...panels.value]) {
    closePanel(panel.id)
  }
  workspaceSessionPanelId.value = null
}

// 「关闭编辑器」只是隐藏：保留主区域视图、自由分割布局、会话 Panel 与 diff 数据，
// 使再次打开时恢复关闭前的状态。这里只做「避免独立终端/聊天面板凭空浮现」的必要清理
// （编辑器内嵌承载时，独立面板的显示状态是被取代的遗留值，关闭编辑器后需复位）。
// 注意：必须在 showWorkspacePanel 置 false 之前调用，否则 workspaceHosts* 已为 false，
// 独立面板不会被收起。
function hideWorkspaceHostedPanelState() {
  if (workspaceHostsTerminal.value) showTerminalPanel.value = false
  if (workspaceHostsChat.value) showChatPanel.value = false
}

async function closeWorkspacePanel() {
  if (hasDirtyWorkspaceTabs()) {
    const confirmed = await confirmCloseWorkspacePanel()
    if (!confirmed) return
  }

  hideWorkspaceHostedPanelState()
  showWorkspacePanel.value = false
}

// 为 Agent 创建/打开编辑器会话
function createWorkspaceForAgent(agent) {
  if (!socket.value) {
    console.warn('[workspace-session] No socket connection')
    return
  }

  const agentId = agent.agent_id
  const agentName = agent.name || agent.agent_type

  // 检查是否已存在该 Agent 的编辑器会话
  let session = workspaceSessions.value.find(s => s.agent_id === agentId)
  if (!session) {
    // 创建新的编辑器会话
    session = {
      agent_id: agentId,
      agent_name: agentName,
      agent: agent,
      tabs: [],
      activeTabPath: null,
      editorModels: new Map(),
      isEditable: false,
      showSidebar: true,
      sidebarView: 'files'
    }
    workspaceSessions.value.push(session)
  }

  // 切换到该会话
  activeWorkspaceSessionId.value = agentId
  showWorkspacePanel.value = true

}

// 虚拟目录会话的 agent_id 前缀：未创建 Agent 时直接打开某节点的目录
const VIRTUAL_WORKSPACE_PREFIX = '__node__:'

// 已打开目录记录的持久化 key：刷新后自动恢复，无需重新添加。
// 仅存 node_id + working_dir（agent_id 由二者推导），避免持久化整个会话对象。
const VIRTUAL_DIRS_STORAGE_KEY = 'jarvis_virtual_workspace_dirs'

// 从虚拟会话的 agent_id 还原出伪 agent 信息（含 node_id/working_dir），供文件树与文件读写复用
function getVirtualWorkspaceAgent(agentId) {
  const key = String(agentId || '')
  if (!key.startsWith(VIRTUAL_WORKSPACE_PREFIX)) return null
  const session = workspaceSessions.value.find(s => s.agent_id === key)
  return session?.agent || null
}

// 目录树/文件操作统一取 agent：优先真实 Agent，其次虚拟目录会话
function resolveFileTreeAgent(agentId) {
  return agentList.value.find(a => a.agent_id === agentId) || getVirtualWorkspaceAgent(agentId)
}

// 由文件的绝对路径反查其所属的目录树 Agent（真实 Agent 或虚拟目录会话）：
// 按 working_dir 前缀匹配，取最长前缀者（避免嵌套目录下命中父目录 Agent）；
// 前缀长度相同时优先活跃 Agent，避免命中同目录下已停止的旧 Agent。
// 返回 { agentId, agent } 或 null。
function resolveAgentForPath(path) {
  const raw = String(path || '')
  if (!raw) return null
  const candidates = []
  // 真实 Agent：附带其是否已停止（虚拟目录会话无「停止」概念，视为活跃）
  for (const agent of agentList.value) {
    if (agent?.agent_id && agent.working_dir) {
      candidates.push({ agent, stopped: isStoppedAgent(agent) })
    }
  }
  for (const session of virtualWorkspaceSessions.value) {
    if (session?.agent?.agent_id && session.agent.working_dir) {
      candidates.push({ agent: session.agent, stopped: false })
    }
  }
  let best = null
  let bestLen = -1
  let bestStopped = true
  for (const { agent, stopped } of candidates) {
    const dir = String(agent.working_dir).replace(/\/+$/, '')
    if (!dir) continue
    if (raw === dir || raw.startsWith(`${dir}/`)) {
      // 更长前缀优先；同长度时活跃 Agent 优先于已停止 Agent
      if (dir.length > bestLen || (dir.length === bestLen && bestStopped && !stopped)) {
        best = agent
        bestLen = dir.length
        bestStopped = stopped
      }
    }
  }
  return best ? { agentId: best.agent_id, agent: best } : null
}

// 读取持久化的「已打开目录」记录
function loadVirtualWorkspaceDirs() {
  try {
    const raw = localStorage.getItem(VIRTUAL_DIRS_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(item => item && item.node_id && item.working_dir)
      .map(item => ({ node_id: String(item.node_id), working_dir: String(item.working_dir) }))
  } catch (e) {
    return []
  }
}

// 把当前虚拟目录会话写回 localStorage（以实际会话为准，移除后自然消失）
function saveVirtualWorkspaceDirs() {
  try {
    const dirs = virtualWorkspaceSessions.value
      .map(s => ({
        node_id: String(s.agent?.node_id || '').trim(),
        working_dir: String(s.agent?.working_dir || '').trim(),
      }))
      .filter(item => item.node_id && item.working_dir)
    localStorage.setItem(VIRTUAL_DIRS_STORAGE_KEY, JSON.stringify(dirs))
  } catch (e) {
    // localStorage 不可用（隐私模式 / 配额满）时静默降级
  }
}

// 创建或复用某节点的虚拟目录会话，返回 { agentId, agent }
// 注意：agent_id 由「节点 + 目录」共同决定（同一节点可同时打开多个目录），
// 因此这里不能只按节点生成 id，否则同节点再次打开别的目录会复用并覆盖上一个会话。
function ensureVirtualWorkspaceSession(nodeId, dirPath) {
  const targetNodeId = String(nodeId || 'master').trim() || 'master'
  const targetDir = String(dirPath || '').trim()
  if (!targetDir) return null

  const agentId = `${VIRTUAL_WORKSPACE_PREFIX}${targetNodeId}:${targetDir}`
  // 节点名 + 目录名，便于在目录树中区分同一节点下的多个目录
  const dirLabel = targetDir.replace(/\/+$/, '').split('/').pop() || targetDir
  const virtualAgent = {
    agent_id: agentId,
    name: `${getNodeDisplayName(targetNodeId)} · ${dirLabel}`,
    node_id: targetNodeId,
    working_dir: targetDir,
    agent_type: 'virtual_dir',
    virtual: true
  }

  let session = workspaceSessions.value.find(s => s.agent_id === agentId)
  if (!session) {
    session = {
      agent_id: agentId,
      agent_name: virtualAgent.name,
      agent: virtualAgent,
      tabs: [],
      activeTabPath: null,
      editorModels: new Map(),
      isEditable: false,
      showSidebar: true,
      sidebarView: 'files'
    }
    workspaceSessions.value.push(session)
  } else {
    // 复用已有虚拟会话时刷新节点与目录
    session.agent = virtualAgent
    session.agent_name = virtualAgent.name
  }
  return { agentId, agent: virtualAgent }
}

// 打开「某节点的某目录」为编辑器工作区（不需要先创建 Agent）
async function openWorkspaceDir(nodeId, dirPath) {
  const created = ensureVirtualWorkspaceSession(nodeId, dirPath)
  if (!created) return
  const { agentId, agent: virtualAgent } = created

  activeWorkspaceSessionId.value = agentId
  showWorkspacePanel.value = true
  setActivePaneView('file')
  showWorkspaceFileView()
  workspaceSidebarView.value = 'files'

  // 初始化该目录的文件树
  await initFileTree(agentId, virtualAgent.working_dir)
  // 记录持久化，刷新后自动恢复
  saveVirtualWorkspaceDirs()
  showToast(`已打开目录：${virtualAgent.working_dir}`, 'success')
}

// 移除一个已打开的目录（关闭其虚拟会话并清理文件树状态），并同步持久化记录
function removeWorkspaceDir(agentId) {
  const index = workspaceSessions.value.findIndex(s => s.agent_id === agentId)
  if (index === -1) return
  const session = workspaceSessions.value[index]
  if (session.agent?.virtual !== true) return

  // 清理该会话的文件树 / 展开态 / 加载态
  fileTreeState.value.delete(agentId)
  fileTreeExpanded.value.delete(agentId)
  fileTreeLoading.value.delete(agentId)
  expandedAgents.value.delete(agentId)
  if (fileTreeSelectedAgentId.value === agentId) {
    fileTreeSelectedAgentId.value = null
    fileTreeSelectedPath.value = null
  }
  if (selectedAgentId.value === agentId) selectedAgentId.value = null

  // 释放编辑器模型
  session.editorModels?.clear()

  workspaceSessions.value.splice(index, 1)
  // 若移除的是当前激活会话，切到剩余的第一个会话；没有则清空激活态。
  // 注意：这里只移除一个目录条目，工作区面板本身要继续保留（面板是承载目录树的容器），
  // 不能像关闭编辑器会话那样把整个面板收起，否则用户会误以为「移除目录 = 关闭工作区」。
  if (activeWorkspaceSessionId.value === agentId) {
    activeWorkspaceSessionId.value = workspaceSessions.value.length > 0
      ? workspaceSessions.value[0].agent_id
      : null
    if (!activeWorkspaceSessionId.value) {
      // 无剩余会话时仅复位主区域视图/分割/内嵌会话面板，面板保持打开并显示占位提示
      resetWorkspaceHostedPanelState()
    }
  }
  triggerRef(expandedAgents)
  saveVirtualWorkspaceDirs()
  showToast('已移除目录', 'success')
}

// 刷新后恢复上次打开的目录记录（在连接成功、鉴权可用后调用）
async function restoreVirtualWorkspaceDirs() {
  const dirs = loadVirtualWorkspaceDirs()
  if (!dirs.length) return
  for (const dir of dirs) {
    const created = ensureVirtualWorkspaceSession(dir.node_id, dir.working_dir)
    if (!created) continue
    // 仅恢复会话与文件树，不抢占当前激活会话、不弹提示
    await initFileTree(created.agentId, created.agent.working_dir)
  }
}


// 关闭编辑器会话
async function closeWorkspaceSession(agentId) {
  const sessionIndex = workspaceSessions.value.findIndex(s => s.agent_id === agentId)
  if (sessionIndex === -1) return

  const session = workspaceSessions.value[sessionIndex]

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

  // 从数组中移除
  workspaceSessions.value.splice(sessionIndex, 1)

  // 如果关闭的是当前激活的会话，切换到另一个
  if (activeWorkspaceSessionId.value === agentId) {
    activeWorkspaceSessionId.value = workspaceSessions.value.length > 0 ? workspaceSessions.value[0].agent_id : null
    if (!activeWorkspaceSessionId.value) {
      // 与 closeWorkspacePanel 一致：编辑器承载终端/聊天时，关闭编辑器需一并收起其独立面板状态
      resetWorkspaceHostedPanelState()
      showWorkspacePanel.value = false
    }
  }

}

// 切换编辑器会话
function switchWorkspaceSession(agentId) {
  const session = workspaceSessions.value.find(s => s.agent_id === agentId)
  if (!session) return

  activeWorkspaceSessionId.value = agentId
  showWorkspacePanel.value = true
}

function confirmCloseDirtyWorkspaceTab(path) {
  return new Promise((resolve) => {
    showConfirm(
      '该标签存在未保存修改，确定关闭吗？',
      () => resolve(true),
      () => resolve(false),
      false
    )
  })
}

// skipDirtyConfirm：批量关闭（标签栏右键菜单）时调用方已统一确认过一次，
// 避免每个脏标签再逐个弹窗。
async function closeWorkspaceTab(path, paneId = null, skipDirtyConfirm = false) {
  const tab = getWorkspaceTabByPath(path)
  if (!tab) return

  if (tab.isDirty && !skipDirtyConfirm) {
    const confirmed = await confirmCloseDirtyWorkspaceTab(path)
    if (!confirmed) return
  }

  // 已统一为 pane 树：指定了 pane 时只从该 pane 的标签列表移除。
  // 若该文件仍被其他 pane 引用，则不销毁模型、也不从全局 tabs 移除，
  // 其他 pane 的编辑器保持原样（这正是「关闭一个 pane 的标签不影响另一个」的关键）。
  let closedFromPane = false
  if (paneId) {
    closedFromPane = true
    removePaneTab(paneId, path)
    const panePaths = workspacePaneTabs.get(paneId) || []
    if (workspaceViewPanes.get(paneId) === path) {
      const nextPath = panePaths[panePaths.length - 1] || null
      if (nextPath) {
        activateWorkspaceTab(nextPath)
      } else {
        workspaceViewPanes.delete(paneId)
        const view = editorViews.get(paneId)
        if (view) view.setModel(null)
      }
    }
    if (isPathReferencedByAnyPane(path)) return
    // 没有其他 pane 引用该文件：继续走下方全局清理（释放模型 / LSP / 全局 tab）
  }

  const session = activeWorkspaceSession.value
  if (!session) return
  const index = session.tabs.findIndex(item => item.path === path)
  if (index === -1) return

  const wasActive = session.activeTabPath === path
  session.tabs.splice(index, 1)

  const modelData = editorModels.get(path)
  if (modelData) {
    if (modelData.model && !modelData.model.isDisposed()) {
      modelData.model.dispose()
    }
    editorModels.delete(path)
  }

  // 释放该文件绑定的 LSP client（若该 server 无其他文件在用，则关闭连接）
  releaseLspBinding(path)

  if (wasActive) {
    const nextTab = session.tabs[index] || session.tabs[index - 1] || null
    // 从某个 pane 关闭标签时，该 pane 的「下一个标签 / 清空」已在上面处理完毕；
    // 这里若再激活全局下一个标签，会把别的 pane 的文件错误地绑到该 pane 上。
    if (closedFromPane) {
      // 该 pane 的视图已在上方处理；这里只把全局「激活文件」修正为仍存在的标签，
      // 避免它继续指向已删除的 path。
      session.activeTabPath = nextTab ? nextTab.path : null
    } else if (nextTab) {
      activateWorkspaceTab(nextTab.path)
    } else {
      session.activeTabPath = null
      // 不销毁编辑器实例，保留编辑器和容器 DOM，
      // 否则 v-if/v-else 切换会导致 editorContainerRef 消失，
      // 后续打开文件时无法重新创建编辑器。
      // 仅清空模型即可（所有 pane 的实例一并清空）。
      for (const [pid, view] of editorViews) {
        view.setModel(null)
        workspaceViewPanes.delete(pid)
      }
    }
  }
}

// ===== 编辑器标签栏右键菜单：关闭右侧所有 / 关闭所有 / 仅保留当前 =====
// paneId 为 null 表示未分割态（标签栏由全局 workspaceTabs 驱动，渲染在 WorkspacePanel.vue）；
// 否则为该 pane 的独立标签列表（getPaneTabs）。
const tabContextMenu = ref({ visible: false, x: 0, y: 0, paneId: null, path: '' })

function closeTabContextMenu() {
  if (tabContextMenu.value.visible) {
    tabContextMenu.value = { ...tabContextMenu.value, visible: false }
  }
}

function openTabContextMenu(paneId, path, event) {
  if (!path) return
  tabContextMenu.value = {
    visible: true,
    x: event?.clientX || 0,
    y: event?.clientY || 0,
    paneId: paneId || null,
    path,
  }
  // 点击空白处关闭（与目录树右键菜单同款：pointerdown 一次即解绑）
  document.addEventListener('pointerdown', closeTabContextMenu, { once: true })
}

// 当前右键菜单对应的标签 path 列表（按显示顺序）
function getTabContextPaths() {
  const menu = tabContextMenu.value
  if (menu.paneId) return getPaneTabs(menu.paneId).map(t => t.path)
  return workspaceTabs.value.map(t => t.path)
}

const tabContextActions = computed(() => {
  const paths = getTabContextPaths()
  const index = paths.indexOf(tabContextMenu.value.path)
  const hasRight = index >= 0 && index < paths.length - 1
  const hasOthers = paths.length > 1
  const canReveal = !!resolveAgentForPath(tabContextMenu.value.path)
  return [
    { id: 'reveal-in-tree', icon: '⌖', label: '在文件树中显示', enabled: canReveal },
    { id: 'close-right', icon: '⇥', label: '关闭右侧所有', enabled: hasRight },
    { id: 'close-all', icon: '✕', label: '关闭所有', enabled: hasOthers },
    { id: 'keep-current', icon: '◎', label: '仅保留当前', enabled: hasOthers },
  ]
})

async function runTabContextAction(act) {
  if (!act || act.enabled === false) return
  const menu = { ...tabContextMenu.value }
  const paneId = menu.paneId
  const paths = getTabContextPaths()
  const index = paths.indexOf(menu.path)
  if (index === -1) {
    closeTabContextMenu()
    return
  }

  let targets = []
  if (act.id === 'reveal-in-tree') {
    closeTabContextMenu()
    await revealTabInFileTree(menu.path)
    return
  }
  if (act.id === 'close-right') {
    targets = paths.slice(index + 1)
  } else if (act.id === 'close-all') {
    targets = paths.slice()
  } else if (act.id === 'keep-current') {
    targets = paths.filter(p => p !== menu.path)
  }
  closeTabContextMenu()
  if (!targets.length) return

  // 批量关闭：若其中含未保存标签，统一确认一次（避免逐个弹窗）
  const dirtyCount = targets.filter(p => getWorkspaceTabByPath(p)?.isDirty).length
  if (dirtyCount > 0) {
    const confirmed = await new Promise((resolve) => {
      showConfirm(
        `有 ${dirtyCount} 个标签存在未保存修改，确定关闭吗？`,
        () => resolve(true),
        () => resolve(false),
        false
      )
    })
    if (!confirmed) return
  }

  // 逐个关闭（closeWorkspaceTab 内部已处理模型/LSP/pane 绑定清理）；
  // 脏标签已在上方统一确认过，这里跳过逐个确认。
  for (const path of targets) {
    await closeWorkspaceTab(path, paneId, true)
  }
}

// 在左侧文件树中定位并高亮某个已打开文件（类似 VSCode 的 Reveal in Explorer）：
// 1) 反查文件所属 Agent/虚拟目录会话；2) 打开侧边栏并切到「文件」视图；
// 3) 展开 Agent 节点；4) 按路径逐级展开目录（必要时按需加载子节点）；
// 5) 选中并滚动到该文件节点。

// 通用 UI 图标（自绘 stroke 线性 SVG，currentColor 继承主题色）
const UI_ICONS = {
  folder: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 4.5v7a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H8.2L6.7 4.5H2.5a1 1 0 0 0-1 1z"/></svg>',
  monitor: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="2.5" width="12" height="8.5" rx="1.5"/><path d="M6 13.5h4M8 11v2.5"/></svg>',
  search: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3.5 3.5"/></svg>',
  save: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 2.5h9l1.5 1.5v9.5a1 1 0 0 1-1 1h-10a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1z"/><path d="M5 2.5v4h5v-4M5 13.5v-5h6v5"/></svg>',
  lock: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/></svg>',
  unlock: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 4.9-.8"/></svg>',
  receipt: '<svg viewBox="0 0 16 16" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.5h8v13l-1.5-1-1.5 1-1.5-1-1.5 1-1.5-1z"/><path d="M6 5.5h4M6 8h4M6 10.5h2.5"/></svg>',
  folderStack: '<svg viewBox="0 0 16 16" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 4.5v7a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H8.2L6.7 4.5H3.5a1 1 0 0 0-1 1z"/><path d="M5 13v.5a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V7.5"/></svg>',
  eye: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/></svg>',
  eyeOff: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><path d="M4 4 12 12M8 6.5a1.5 1.5 0 0 1 1.5 1.5"/></svg>',
}
// 细粒度扩展名 → 图标文件映射（图标源：material-icon-theme，位于 public/file-icons/）

// 取当前选中的文本，用于打开全局搜索时预填搜索框。
// 优先取 Monaco 编辑器选区（编辑器聚焦时），否则回退到页面 DOM 选区
// （如会话输出 / 聊天内容里选中的文字）。返回折叠空白后的单行文本，无选中返回空串。
function getSelectedTextForSearch() {
  let raw = ''
  const view = getActiveWorkspaceView()
  if (view && typeof view.getSelection === 'function') {
    const selection = view.getSelection()
    const model = view.getModel()
    if (selection && model && !selection.isEmpty()) {
      raw = model.getValueInRange(selection)
    }
  }
  if (!raw) {
    const domSelection = window.getSelection && window.getSelection()
    if (domSelection) raw = domSelection.toString()
  }
  // 搜索框是单行输入：把选区里的换行/连续空白折叠为单个空格，避免多行内容撑坏查询
  return raw.replace(/\s+/g, ' ').trim()
}

// 切到编辑器侧边栏的全局搜索并聚焦输入框（mode 为 'content' 内容搜索 / 'filename' 文件名搜索）。
// 若当前有选中文字，则预填到搜索框（选中内容优先于原有查询）。
function openWorkspaceGlobalSearch(mode = 'content') {
  if (!showWorkspacePanel.value) return
  setWorkspaceSidebarView('search')
  setGlobalSearchMode(mode)
  const selectedText = getSelectedTextForSearch()
  if (selectedText) globalSearchQuery.value = selectedText
  nextTick(() => {
    const input = document.querySelector('.workspace-global-search-input')
    if (input) input.focus()
  })
}

// ===== 编辑器侧边栏 Git 视图（只读：提交历史/详情/diff/分支） =====
const {
  // refs
  gitLog, gitLogLoading, gitLogError, gitLogHasMore, gitLogTotal,
  gitBranches, gitTags, gitCurrentBranch, gitSelectedCommit,
  gitRangeSelectMode, gitSelectedCommits, gitPatchLoading,
  gitCommitFiles, gitCommitDetailLoading, gitSelectedFile,
  gitDiffText, gitDiffLoading, gitDiffError, gitDiffTruncated,
  gitDiffSideBySide, gitDiffShowFull,
  pluginSidebarWorkingDir, pluginActiveAgentInfo,
  gitCommitContextMenu, gitCommitInfoModal,
  // 常量
  GIT_LOG_PAGE_SIZE,
  // 函数
  isNarrowGitDiffViewport, getGitTargetAgent, getGitTargetNodeId, getGitWorkingDir,
  callGitApi, fetchGitLog, fetchGitBranches, refreshGitView,
  toggleGitCommitDetail, enterGitRangeSelect, exitGitRangeSelect, toggleGitRangeSelect,
  downloadGitPatch, viewGitTargetDiff, onDiffTitleClick, onOpenDiffFileFromMessage,
  viewGitFileDiff, ensureGitDiffFullText, layoutGitDiffEditor,
  disposeDiffEditorForPane, disposeAllDiffEditors, ensureDiffEditorForPane,
  renderDiffForPane, loadDiffForPane, togglePaneDiffSideBySide, togglePaneDiffShowFull,
  navigatePaneDiff, closePaneDiff, scheduleDiffLayout,
  gitRefClass, gitFileStatus, formatGitRelativeTime, shortGitHash,
  closeGitCommitContextMenu, openGitCommitContextMenu, copyGitCommit, copyGitCommitId,
  formatGitCommitInfo, formatGitCommitTooltip, showGitCommitInfoModal,
} = useGitView({
  EDITOR_FONT_FAMILY,
  buildNodeHttpUrl,
  fetchWithAuth,
  getGatewayAddress,
  getLanguageExtension,
  getLanguageFromFilename,
  windowWidth,
  activeWorkspaceSessionId,
  ensurePaneForView,
  findWorkspacePaneById,
  gitCustomDir,
  persistWorkspacePaneLayout,
  resolveDiffContainer,
  scheduleWorkspaceLayout,
  showWorkspacePanel,
  workspacePaneTree,
  workspaceSidebarView,
  diffContainerRefs,
  diffEditorViews,
  openWorkspaceFile,
  activePane,
  getPanePanel,
  // getter 注入（定义在调用点之后，useGitView 内部以 xxx() 二次求值）
  effectiveGitAgentId: () => effectiveGitAgentId,
  agentList: () => agentList,
  showToast: () => showToast,
  viewDiff: () => viewDiff,
  copyTextToClipboard: () => copyTextToClipboard,
  getPanelAgent: () => getPanelAgent,
  getCurrentAgentOrNull: () => getCurrentAgentOrNull,
})

// 目录树右键菜单项

// 触发隐藏 file input，选择要上传到指定目录的本地文件

// 调用后端创建文件/目录接口（不覆盖已存在路径）

// ===== 目录树复制/剪切/粘贴 =====

// 列出目录下的直接子项（复用 directories 接口）

// ===== 目录树拖放（HTML5 DnD）：普通拖放=移动，按住 Ctrl/⌘=复制 =====
// 硬约束：只允许在同一个目录树内操作（同一 node_id），跨 Agent/跨节点一律拒绝。
// 拖放状态：{ agentId, nodeId, path, name, kind }，仅存活于一次拖拽过程。

// 由绝对路径找到对应的已加载目录树节点（找不到返回 null，表示刷新工作目录根）

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

const COMPLETION_USAGE_STORAGE_KEY = 'jarvis_completion_usage_stats'

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

// 打开缓存管理面板，记录目标 Agent（点击的 Panel 所属 Agent）
function openBufferPanel(panel) {
  bufferPanelAgentId.value = panel?.agentId ?? null
  showBufferPanel.value = true
}

const hasBufferedInput = computed(() => {
  const agentId = bufferPanelAgentId.value
  return agentId ? inputBuffers.value.has(agentId) : false
})

// 监听缓存面板打开，自动加载缓存内容
watch(showBufferPanel, (newVal) => {
  if (newVal && hasBufferedInput.value) {
    const agentId = bufferPanelAgentId.value
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

// 创建新 Panel
function createPanel() {
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
  // 若被关闭的 Panel 正被编辑器承载，需清理悬空引用，否则编辑器会指向一个已不存在的
  // Panel（会话视图空白）。已统一为 pane 树：找到承载它的 pane 清空为 empty；
  // 找不到（未分割且主区域是 session 的兜底）则回退到文件视图。
  if (workspaceSessionPanelId.value === panelId) {
    workspaceSessionPanelId.value = null
    const hostingPane = findWorkspacePaneBySessionPanelId(panelId)
    if (hostingPane) {
      hostingPane.view = 'empty'
      hostingPane.sessionPanelId = null
      persistWorkspacePaneLayout()
    } else if (workspaceMainView.value === 'session') {
      setMainViewOnLeaf('file')
    }
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

// 移动端返回键：关闭当前所有可见的内嵌 Panel（含终端/聊天/编辑器），回到宠物大厅。
// 移动端只允许一个内嵌 Panel，故直接关闭全部可见项即可。
function closeVisiblePanelsOnMobile() {
  if (showTerminalPanel.value) showTerminalPanel.value = false
  if (showChatPanel.value) showChatPanel.value = false
  if (showWorkspacePanel.value) closeWorkspacePanel()
  for (const panel of [...panels.value]) {
    closePanel(panel.id)
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

// 已分割时把 Agent 打开到「激活 pane」中（需求：新建 Panel 落在激活区域；
// 若该区域已有 Panel，则关闭旧的、新的覆盖）。返回 true 表示已处理。
// 说明：只操作激活 pane，绝不动其他 pane 承载的 Panel（否则会把别的区域的会话清掉）。
// 注意：激活 pane 已承载 Agent 会话时不再覆盖，而是开新面板（新 pane）保留当前会话，
// 避免命令面板/侧边栏切换 Agent 时把当前会话覆盖掉。
function openAgentInActivePane(agent) {
  const activePaneLeaf = activePane.value
  if (!activePaneLeaf) return false
  // 激活 pane 已承载的 Panel
  const hostedPanel = activePaneLeaf.view === 'session' && activePaneLeaf.sessionPanelId
    ? panels.value.find(p => p.id === activePaneLeaf.sessionPanelId)
    : null
  // 激活 pane 已承载 Agent 会话：不覆盖。承载的正是该 Agent 则无需操作（已显示）；
  // 否则开新面板（新 pane）承载，保留当前会话。
  if (hostedPanel) {
    if (hostedPanel.agentId === agent.agent_id) {
      activateWorkspacePane(activePaneLeaf.id)
      return true
    }
    openAgentInNewPane(agent)
    return true
  }
  // 激活 pane 是文件/空区域：新建 Panel 落在激活 pane（覆盖文件视图是合理的）
  const targetPanel = {
    id: `panel-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    agentId: agent.agent_id
  }
  panels.value.push(targetPanel)
  activePanelId.value = targetPanel.id
  workspaceSessionPanelId.value = targetPanel.id
  // 空则原地、已有承载该 Panel 的 pane 则复用、否则分割（不覆盖当前区域）
  ensurePaneForView('session', targetPanel.id)
  switchAgent(agent)
  nextTick(() => maybeStartTour('panel'))
  return true
}

// 已分割且激活 pane 已承载 Agent 会话时：开新面板（新 pane），保留当前会话。
// 新建 Panel 并让 ensurePaneForView 分割新 pane 承载它（不覆盖激活 pane 的会话）。
// 调用方需保证 agent 不在任何既有 Panel 中（openAgentInActivePane 的各调用点均已提前处理）。
function openAgentInNewPane(agent) {
  if (!agent) return
  const targetPanel = {
    id: `panel-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    agentId: agent.agent_id
  }
  panels.value.push(targetPanel)
  activePanelId.value = targetPanel.id
  workspaceSessionPanelId.value = targetPanel.id
  // 空则原地、已有承载该 Panel 的 pane 则复用、否则分割（不覆盖当前区域）
  ensurePaneForView('session', targetPanel.id)
  switchAgent(agent)
  nextTick(() => maybeStartTour('panel'))
}

// 在 Panel 中打开 Agent（替代 switchAgent）
function openAgentInPanel(agent, panelId = null) {
  // 所有内嵌 Panel 都只在编辑器内部渲染：从宠物大厅等入口打开 Agent 时，
  // 必须确保编辑器处于打开状态，否则 Panel 会失去宿主而不可见。
  showWorkspacePanel.value = true
  // 移动端不支持多 Panel，直接切换
  if (windowWidth.value <= 768) {
    // 从大厅进入 Panel 时推送一条历史状态，使移动端返回键能关闭 Panel 回到大厅
    // （已有可见 Panel 时不重复推送，避免返回键需要多按几次）
    if (hasNoPanel.value) {
      pushOverlayState()
    }
    // 确保至少有一个 Panel 存在
    if (panels.value.length === 0) {
      createPanel()
    }
    // 将 Agent 放入当前激活的 Panel
    const targetPanel = panels.value.find(p => p.id === activePanelId.value) || panels.value[0]
    if (targetPanel) {
      targetPanel.agentId = agent.agent_id
      // 内嵌 Panel 只在编辑器内部渲染：必须把该 Panel 交给编辑器主区域的会话视图承载，
      // 否则 Panel 失去宿主而不可见（移动端从大厅双击宠物即此路径）。
      workspaceSessionPanelId.value = targetPanel.id
      setWorkspaceMainView('session')
    }
    switchAgent(agent)
    return
  }
  // 已统一为 pane 树：把 Agent 路由到「激活 pane」中打开（未分割时 activePane 即唯一 leaf）。
  // 否则 Panel 会作为 panel-grid 的整格子项渲染到编辑器外面，用户感知为「Agent 的 panel 跑出编辑器」。
  const existingPanel = panels.value.find(p => p.agentId === agent.agent_id)
  if (existingPanel) {
    const hostingPane = findWorkspacePaneBySessionPanelId(existingPanel.id)
    if (hostingPane) {
      activateWorkspacePane(hostingPane.id)
    } else {
      // 空则原地、否则分割（不覆盖当前区域）
      ensurePaneForView('session', existingPanel.id)
    }
    activePanelId.value = existingPanel.id
    switchAgent(agent)
    workspaceSessionPanelId.value = existingPanel.id
    return
  }
  // 显式指定 panelId（如命令面板）：直接把它放到激活 pane。
  if (panelId) {
    const targetPanel = panels.value.find(p => p.id === panelId)
    if (targetPanel) {
      targetPanel.agentId = agent.agent_id
      activePanelId.value = targetPanel.id
      workspaceSessionPanelId.value = targetPanel.id
      // 空则原地、已有承载该 Panel 的 pane 则复用、否则分割（不覆盖当前区域）
      ensurePaneForView('session', targetPanel.id)
      switchAgent(agent)
      return
    }
  }
  // 需求：新建的 Panel 落在「激活 pane」里；若该 pane 已有 Panel，则关闭旧的、新的覆盖。
  openAgentInActivePane(agent)
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
  // 内嵌 Panel 只在编辑器内部渲染：必须确保编辑器打开、且 Panel 被编辑器承载，
  // 否则 Panel 失去宿主而不可见（编辑器停在文件视图或已分割时尤其明显）。
  showWorkspacePanel.value = true
  const existingPanel = panels.value.find(p => p.agentId === agent.agent_id)
  if (existingPanel) {
    // 已统一为 pane 树：把承载该 Panel 的 pane 设为激活；未承载则放进激活 pane。
    const hostingPane = findWorkspacePaneBySessionPanelId(existingPanel.id)
    if (hostingPane) {
      activateWorkspacePane(hostingPane.id)
    } else {
      // 空则原地、否则分割（不覆盖当前区域）
      ensurePaneForView('session', existingPanel.id)
    }
    activePanelId.value = existingPanel.id
    workspaceSessionPanelId.value = existingPanel.id
    switchAgent(agent)
    return
  }
  // 已统一为 pane 树：把 Agent 放进「激活 pane」（该 pane 已有 Panel 则就地覆盖）
  openAgentInActivePane(agent)
}

// 「在新的 Panel 中打开 Agent」：命令面板按 Tab 时使用
// - Agent 已在某个 Panel 中：激活它（避免重复打开同一 Agent）
// - 否则始终新建 Panel
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
// 音频提示 / 自动朗读 / 系统通知（拆自独立 composable）
const {
  autoReadSupported,
  notifyInputRequest,
  playChatNotificationSound,
  stopAutoRead,
  handleAutoRead,
  sendSystemNotification,
} = useAudioNotifications({
  sessionPanelRefs,
  allOutputs,
  panelInputTips,
  panels,
  isAutoReadEnabled,
})
// 历史输入管理（拆自独立 composable）
const {
  inputHistory,
  lobbyHistoryIndex,
  lobbyHistoryTemp,
  loadInputHistory,
  saveToHistory,
  navigateHistory,
  onLobbyHistoryNav,
} = useInputHistory({
  inputText,
  panelInputTexts,
})
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

// 编辑器主区域是否正在承载聊天室 / 终端（此时独立面板让位，避免同一状态被两个实例争抢）
// 已统一为 pane 树：某个 pane 的 view === 'chat'/'terminal'（host 单例，至多一个）即视为承载。
const workspaceHostsChat = computed(() =>
  showWorkspacePanel.value && !!findWorkspacePaneByView('chat')
)
const workspaceHostsTerminal = computed(() =>
  showWorkspacePanel.value && !!findWorkspacePaneByView('terminal')
)
// 编辑器主区域是否正在承载会话面板（此时网格中对应 panel 让位，避免同一 xterm host 被两实例争抢）
const workspaceHostsSession = computed(() => showWorkspacePanel.value && workspaceMainView.value === 'session')
// 编辑器主区域会话视图当前显示的 panel（由编辑器侧边栏 Agent 列表点击决定）
const workspaceSessionPanelId = ref(null)
// 编辑器当前占用的 panel：只要编辑器面板打开且已选定 panel，就让它从网格让位。
// 不随主区域视图（file/chat/terminal/session）变化而回到网格，否则点 chat/终端时
// 该 panel 会「凭空」出现在网格里，把布局挤乱（用户期望的是替换，而非并存）。
const workspaceHostedPanel = computed(() => {
  if (!showWorkspacePanel.value || !workspaceSessionPanelId.value) return null
  // 已统一为 pane 树：panel 由某个 pane 承载时才让它从网格让位；
  // 若没有任何 pane 承载它（例如承载它的 pane 被切成了 file/chat/terminal），
  // 则回到网格渲染，避免 panel「凭空消失」。
  const hostingPane = findWorkspacePaneBySessionPanelId(workspaceSessionPanelId.value)
  if (!hostingPane) return null
  return panels.value.find(p => p.id === workspaceSessionPanelId.value) || null
})
// 编辑器会话视图对应的 panel：优先取记录的面板，回退到当前激活/首个已绑定 Agent 的面板
const workspaceSessionPanel = computed(() => {
  if (!workspaceHostsSession.value) return null
  const byId = workspaceHostedPanel.value
  if (byId) return byId
  const active = panels.value.find(p => p.id === activePanelId.value && p.agentId)
  if (active) return active
  return panels.value.find(p => p.agentId) || null
})

// 「当前可见」的会话 Agent 集合：即此刻真正显示在界面上的 Agent 会话。
// 注意：不能用「panel 对象是否持有 agentId」来判断——面板被收起（视图切回 file）后
// panel.agentId 仍在，但会话已不可见。命令面板据此判断「选中它是否只是切回自身」：
// 会话不可见时选中它是有意义的（重新打开），故不能置灰。
const visibleSessionAgentIds = computed(() => {
  const ids = new Set()
  // 已统一为 pane 树：遍历 pane 树收集所有承载会话的 pane（未分割时唯一 leaf 也会被遍历到）。
  const walk = (node) => {
    if (!node) return
    if (node.type === 'leaf') {
      if (node.view === 'session' && node.sessionPanelId) {
        const panel = panels.value.find(p => p.id === node.sessionPanelId)
        if (panel && panel.agentId) ids.add(panel.agentId)
      }
      return
    }
    ;(node.children || []).forEach(walk)
  }
  walk(workspacePaneTree.value)
  return ids
})

// 网格内实际渲染的顶层子项数量（用于 panel-grid 的列/行布局）。
// 注意：会话/终端/聊天面板一律只在编辑器面板内部渲染（或作为浮动面板），
// 它们不是 panel-grid 的直接子项，因此绝不能计入网格布局，否则会出现
// 「网格被切成两列、但只有一个子项」→ 编辑器只占半宽、右侧空白的现象。
const embeddedPanelCount = computed(() => {
  // 网格唯一子项是编辑器面板（未打开时为空状态）
  return showWorkspacePanel.value ? 1 : 0
})

// 当前是否没有任何可见的内嵌 Panel（用于展示空状态欢迎背景）
const hasNoPanel = computed(() => embeddedPanelCount.value === 0)
// 是否已完成首次 Agent 列表拉取（无论成功失败）。
// 声明位置需早于下方 immediate watch（否则 watch 立即求值会命中 TDZ）。
const agentListLoaded = ref(false)

// 首次进入宠物大厅（无任何可见 Panel）时展示大厅场景引导
// 需等 Agent 列表首次拉取完成（agentListLoaded）后再触发：未登录时列表尚未拉取，
// 登录弹窗正遮住大厅，此时弹引导既看不到、又会被误标记为已看过。
watch([hasNoPanel, agentListLoaded], ([noPanel, loaded]) => {
  if (noPanel && loaded) maybeStartTour('lobby')
}, { immediate: true })

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
      // 缓冲已被消费：若缓存面板正显示该 Agent，关闭面板并重置编辑文本
      closeBufferPanelIfForAgent(agentId)
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
  // 注意：此处 @ 已真实写入输入框，故 completionHasAtSymbol 置 false，
  // 避免取消补全时 closeCompletionsWithoutSelect 再补插一个 @（导致出现两个 @）
  if (textBeforeCursor.endsWith('@')) {
    completionCursorPos.value = cursorPosition - 1
    completionHasAtSymbol.value = false
    openCompletionsFromPanel(panel)
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
  // 清空后若缓存面板正显示该 Agent，关闭面板并重置编辑文本
  closeBufferPanelIfForAgent(agentId)
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
            // 如果没有terminal_content（且无execution_chunks可回退），添加占位文本，避免显示空白区域
            if (!msg.terminal_content && !(msg.execution_chunks?.length > 0)) {
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
      // 历史记录是持久化的完整序列且为正序，故以它为主干；现有消息中历史没有的部分
      // （如刚收到、尚未落盘的推送）追加到末尾。这样 execution（Xterm）等无 seq 的消息
      // 也能落在正确位置，不会被排到列表末尾。
      const existingIds = new Set()
      for (const msg of processedMessages) {
        if (msg.execution_id) existingIds.add('exec_' + msg.execution_id)
        if (typeof msg.seq === 'number') existingIds.add('seq_' + msg.seq)
      }
      let merged = [...processedMessages]
      for (const msg of currentOutputs) {
        const execKey = msg.execution_id ? 'exec_' + msg.execution_id : null
        const seqKey = typeof msg.seq === 'number' ? 'seq_' + msg.seq : null
        if ((execKey && existingIds.has(execKey)) || (seqKey && existingIds.has(seqKey))) continue
        merged.push(msg)
        if (execKey) existingIds.add(execKey)
        if (seqKey) existingIds.add(seqKey)
      }
      // 兜底排序：若现有消息带有比历史更小的 seq（历史存储被截断等异常情况），
      // 仅对带 seq 的消息按 seq 归位；无 seq 的消息保持其在原序列中的相对位置。
      if (merged.some(msg => typeof msg.seq === 'number')) {
        let lastSeq = null
        merged = merged
          .map((msg, idx) => {
            if (typeof msg.seq === 'number') {
              lastSeq = msg.seq
              return { msg, idx, key: msg.seq, sub: 0 }
            }
            return { msg, idx, key: lastSeq === null ? -Infinity : lastSeq, sub: 1 }
          })
          .sort((a, b) => {
            if (a.key !== b.key) return a.key - b.key
            if (a.sub !== b.sub) return a.sub - b.sub
            return a.idx - b.idx
          })
          .map(item => item.msg)
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
// 全局搜索 / Git 侧边栏各自的 Agent 选择（互不影响，也不影响编辑器会话与文件树）。
// 未显式选择时（null）跟随全局当前 Agent；用户选择后保持自己的选择，不被 currentAgentId 覆盖。
const globalSearchAgentId = ref(null)
const gitAgentId = ref(null)
const effectiveGlobalSearchAgentId = computed(() => globalSearchAgentId.value || currentAgentId.value)
const effectiveGitAgentId = computed(() => gitAgentId.value || currentAgentId.value)

// Git 视图作用的目标 Agent 变化时，若当前停留在 Git 视图，则按新 Agent 的工作目录重新拉取。
// 监听 effectiveGitAgentId（而非仅 activeWorkspaceSessionId）：点击 session 面板切换 Agent
// 会更新 currentAgentId（进而改变 effectiveGitAgentId），但不会改变 activeWorkspaceSessionId，
// 否则 Git 面板的 commit 列表不会跟随新 Agent 刷新。
watch(effectiveGitAgentId, () => {
  if (!showWorkspacePanel.value || workspaceSidebarView.value !== 'git') return
  nextTick(() => {
    refreshGitView()
  })
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

watch([showWorkspacePanel, currentAgentId, workspaceSidebarView], ([isWorkspacePanelVisible, agentId, sidebarView]) => {
  if (!isWorkspacePanelVisible || !agentId || sidebarView !== 'files') {
    return
  }

  nextTick(() => {
    ensureWorkspaceSidebarFileTree()
  })
})

// 定时任务侧边栏：视图激活时定时刷新定时任务列表（只读展示，任务会变化）
let manageTimersTimer = null
watch([showWorkspaceSidebar, workspaceSidebarView], ([sidebarVisible, sidebarView]) => {
  const active = sidebarVisible && sidebarView === 'timers'
  if (manageTimersTimer) {
    clearInterval(manageTimersTimer)
    manageTimersTimer = null
  }
  if (active) {
    refreshManageTimers()
    manageTimersTimer = setInterval(refreshManageTimers, 5000)
  }
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


// 编辑器侧边栏 Agent 列表点击：把该 Agent 的会话显示到编辑器主区域（一次一个）
// 编辑器会话视图是单会话的：切换 Agent 时复用同一个 Panel 覆盖 agentId，
// 而不是每次新建 Panel（否则旧 Panel 会留在网格里，把编辑器挤成半屏）。
function onWorkspaceSidebarAgentClick(agent) {
  if (isBatchMode.value) {
    toggleSelectAgent(agent.agent_id)
    return
  }
  // 移动端不支持多 Panel，沿用既有逻辑（复用当前激活 Panel）
  if (windowWidth.value <= 768) {
    openAgentInPanel(agent)
    const mobilePanel = panels.value.find(p => p.agentId === agent.agent_id)
    if (mobilePanel) {
      workspaceSessionPanelId.value = mobilePanel.id
      setWorkspaceMainView('session')
    }
    // 移动端侧栏是覆盖主区域的底部抽屉（占 55% 高度），点选后自动收起，
    // 让用户立刻看到会话内容，体验更好。
    closeWorkspaceSidebar()
    return
  }
  // 该 Agent 已在某个 Panel 中：直接显示那个 Panel（不新建）
  const existingPanel = panels.value.find(p => p.agentId === agent.agent_id)
  if (existingPanel) {
    // 已统一为 pane 树：优先把「激活 pane」切到该 Panel；若该 Panel 已被别的 pane 承载，
    // 则聚焦到那个 pane（避免同一 panel 出现在两个 pane 中）。
    const hostingPane = findWorkspacePaneBySessionPanelId(existingPanel.id)
    if (hostingPane) {
      activateWorkspacePane(hostingPane.id)
    } else {
      // 空则原地、否则分割（不覆盖当前区域）
      ensurePaneForView('session', existingPanel.id)
    }
    activePanelId.value = existingPanel.id
    switchAgent(agent)
    workspaceSessionPanelId.value = existingPanel.id
    setWorkspaceMainView('session')
    return
  }
  // 已统一为 pane 树：把 Agent 打开到「激活 pane」中（若该区域已有 Panel 则覆盖），
  // 绝不复用其他 pane 承载的 Panel，否则会把那个区域的会话清掉。
  openAgentInActivePane(agent)
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
// ---- 流水线编排可视化 ----
// 选择某个流程（Tab 切换）
function selectPipeline(id) {
  activePipelineId.value = id
}
// 删除某条编排记录，并连带删除该流水线运行时创建的所有 Agent
async function removePipeline(id) {
  if (!id) return
  const pipeline = pipelineStore.getPipeline(id)
  // 收集该流水线创建的所有 Agent（pipeline_agents 事件回填到 stage.agentId）
  const agentIds = []
  if (pipeline && pipeline.stages) {
    for (const [, node] of pipeline.stages) {
      if (node && node.agentId) agentIds.push(node.agentId)
    }
  }
  // 有要删除的 Agent 时，先让用户确认再删
  if (agentIds.length) {
    showConfirm(
      `该流水线创建了 ${agentIds.length} 个 Agent，删除流水线将一并删除这些 Agent，确认删除？`,
      () => removePipelineWithAgents(id, agentIds),
      null,
      false
    )
    return
  }
  // 无关联 Agent：直接删除流水线记录
  pipelineStore.removePipeline(id)
  pipelineVersion.value++ // 刷新 pipelineList
  if (activePipelineId.value === id) activePipelineId.value = ''
}

// 用户确认后：删除流水线及其创建的 Agent
async function removePipelineWithAgents(id, agentIds) {
  // 删除流水线创建的 Agent（pipeline_runner 在 master 节点创建）
  if (agentIds.length) {
    const { host, port } = getGatewayAddress()
    const targetNodeId = 'master'
    let failed = 0
    for (const agentId of agentIds) {
      try {
        const resp = await fetchWithAuth(
          buildNodeHttpUrl(host, port, targetNodeId, `agents/${agentId}`),
          { method: 'DELETE' }
        )
        const result = await resp.json()
        if (!resp.ok || !result.success) {
          failed++
          console.warn('[PIPELINE] 删除流水线 Agent 失败', agentId, result.error?.message || '')
        }
      } catch (e) {
        failed++
        console.warn('[PIPELINE] 删除流水线 Agent 失败', agentId, e.message)
      }
    }
    if (failed) {
      showToast(`已删除流水线记录，但 ${failed}/${agentIds.length} 个 Agent 删除失败`, 'warning')
    } else {
      showToast(`已删除流水线记录及其 ${agentIds.length} 个 Agent`, 'success')
    }
  } else {
    showToast('已删除该流水线记录', 'success')
  }
  pipelineStore.removePipeline(id)
  pipelineVersion.value++ // 刷新 pipelineList
  if (activePipelineId.value === id) activePipelineId.value = ''
}
// 点击 DAG 节点：有 agent_id 时跳转到对应 Agent 面板，否则仅选中流程
function onOrchestrationJumpAgent(payload) {
  const agentId = payload && payload.agentId
  if (!agentId) return
  const target = agents.value.find(a => a.agent_id === agentId)
  if (target) {
    openAgentInPanel(target)
  } else {
    showToast('该阶段对应 Agent 已不存在', 'info')
  }
}
// 打开/关闭编排大图浮层
function openOrchestrationOverlay() {
  showOrchestrationOverlay.value = true
}
function closeOrchestrationOverlay() {
  showOrchestrationOverlay.value = false
}
// 收到后端 pipeline_event：归并进 store 并触发视图刷新
function onPipelineEvent(payload) {
  if (!payload) return
  pipelineStore.applyEvent(payload)
  pipelineStore.pruneFinished(20)
  pipelineVersion.value++
  if (!activePipelineId.value && payload.pipeline_id) {
    activePipelineId.value = payload.pipeline_id
  }
}

// 公网使用文档站点（MkDocs 发布到 GitHub Pages）
const DOCS_URL = 'https://skyfireitdiy.github.io/Jarvis/'
// 打开使用文档（新标签页，不阻塞当前界面）
function openDocs() {
  window.open(DOCS_URL, '_blank', 'noopener')
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

// 打开命令面板并预输入 f>，直接展示文件搜索
function openCommandPaletteFileSearch() {
  openCommandPalette('f>')
}

// 切换宠物显示/隐藏（命令面板触发，代理到 PetWidget 内部逻辑）
function togglePetVisibility() {
  petWidgetRef.value?.togglePet?.()
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
// 优先右键菜单锁定的 Agent；其次当前激活 Panel 内的 Agent；再次宠物大厅中选中的宠物对应的 Agent；最后回退到 currentAgentId
// 解析逻辑抽到 utils/currentAgentResolver.js（纯函数，可单测），此处只负责收集各状态快照。
const commandPaletteCurrentAgentId = computed(() => resolveCurrentAgentId({
  // 右键菜单（侧边栏 / Panel）锁定期间，菜单动作一律作用于被右键的那个 Agent（不改动面板与当前 Agent）。
  // 注意：只看 contextMenuAgentId，不能叠加 panelContextMenu.visible——
  // 菜单项被点击时菜单会先收起（visible=false），若依赖 visible 就会回退到「当前活动 Agent」，
  // 导致删除/重命名等操作作用到错误的 Agent。
  contextMenuAgentId: contextMenuAgentId.value,
  lobbyActiveAgentId: lobbyActiveAgentId.value,
  hasNoPanel: hasNoPanel.value,
  activePanelAgentId: getCurrentPanel()?.agentId || null,
  currentAgentId: currentAgentId.value,
}))
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
  if (!panel || !panel.agentId) {
    showToast('没有可操作的 Agent 面板', 'error')
    return
  }
  const next = !getPanelAutoScroll(panel)
  togglePanelAutoScroll(panel, next)
  showToast(next ? '自动滚动已开启' : '自动滚动已关闭', 'success')
}
// 切换当前 Agent 面板的自动朗读
function toggleCurrentAutoRead() {
  const panel = getCurrentPanel()
  if (!panel || !panel.agentId) {
    showToast('没有可操作的 Agent 面板', 'error')
    return
  }
  const next = !getPanelAutoRead(panel)
  if (next && !autoReadSupported) {
    showToast('当前浏览器不支持自动朗读', 'error')
    return
  }
  togglePanelAutoRead(panel, next)
  showToast(next ? '自动朗读已开启' : '自动朗读已关闭', 'success')
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
  if (key === 'terminal') return !!(showTerminalPanel.value && document.querySelector('.terminal-panel'))
  if (key === 'workspace') return !!(showWorkspacePanel.value && document.querySelector('.workspace-panel'))
  if (key === 'chat') return !!(showChatPanel.value && document.querySelector('.chat-panel'))
  if (key.startsWith('session:')) {
    const panelId = key.slice('session:'.length)
    return panels.value.some(p => p.id === panelId && p.agentId)
  }
  return false
}

// 命名面板（terminal/workspace/chat）的焦点 key：
// 优先依据真实 DOM 焦点；焦点不在任何可聚焦元素上时（如仅鼠标点击过面板空白处，
// activeElement 为 body），回退到最近一次交互的命名面板（activeWindow，由面板的
// mousedown 更新），并用 isFocusKeyAvailable 过滤掉已关闭的残留值。
function getNamedPanelFocusKey() {
  const focusedKey = getFocusedZoneKey()
  if (focusedKey === 'terminal' || focusedKey === 'workspace' || focusedKey === 'chat') {
    return focusedKey
  }
  if (activeWindow.value && isFocusKeyAvailable(activeWindow.value)) {
    return activeWindow.value
  }
  return null
}

// 当前焦点所处面板的 key（session:<id> / terminal / workspace / chat）
// 命令面板打开时会抢走焦点，此时优先用"打开前"记录的快照（且该面板须仍有效）；
// 否则依据真实 DOM 焦点，最后回退到当前激活 Panel
function getFocusedPanelKey() {
  if (showCommandPalette.value && isFocusKeyAvailable(commandPaletteFocusKey)) {
    return commandPaletteFocusKey
  }
  const focusedKey = getFocusedZoneKey()
  if (focusedKey) return focusedKey
  const namedKey = getNamedPanelFocusKey()
  if (namedKey) return namedKey
  if (isFocusKeyAvailable(commandPaletteFocusKey)) return commandPaletteFocusKey
  const panel = getCurrentPanel()
  if (panel && panel.agentId) return `session:${panel.id}`
  return null
}
// 编辑器面板的 Ctrl+W 语义（VS Code 同款）：关闭「当前激活 pane」的文件；
// 无文件可关时，分割态关闭该 pane、未分割态返回 false（由调用方关闭整个面板）。
// 返回是否已处理（关闭了文件或 pane）。
function handleWorkspaceCloseShortcut() {
  if (!showWorkspacePanel.value) return false
  // 已统一为 pane 树：activePane 就是当前激活区域（未分割时即唯一 leaf）。
  const pane = activePane.value
  // file pane 有文件 → 关闭该文件（只影响激活 pane，不影响其他 pane）
  if (pane && pane.view === 'file') {
    const path = workspaceViewPanes.get(activePaneId.value)
    if (path) {
      closeWorkspaceTab(path, activePaneId.value)
      return true
    }
  }
  // 无文件可关：关闭该 pane（仅剩一个 pane 时不允许关闭，回退到关闭整个面板）
  if (workspacePaneCount.value > 1) {
    closeWorkspacePane(activePaneId.value)
    return true
  }
  return false
}

// 关闭当前焦点所在的面板（会话/终端/编辑器/聊天）
function closeFocusedPanel() {
  const key = getFocusedPanelKey()
  if (!key) return
  if (key === 'terminal') {
    showTerminalPanel.value = false
  } else if (key === 'workspace') {
    // 编辑器面板：Ctrl+W 优先关闭当前文件（VS Code 语义）；无文件时关闭整个面板
    if (handleWorkspaceCloseShortcut()) return
    // 与 closeWorkspacePanel 一致：关闭只是隐藏，保留状态以便再次打开时恢复
    hideWorkspaceHostedPanelState()
    showWorkspacePanel.value = false
  } else if (key === 'chat') {
    showChatPanel.value = false
  } else if (key.startsWith('session:')) {
    closePanel(key.slice('session:'.length))
  }
}
// ===== 新手引导（拆自 composable useTour）=====
const {
  activeTourId,
  activeTourSteps,
  showOnboarding,
  maybeStartTour,
  finishTour,
  startOnboarding,
  resetOnboardingMarks,
  clearOnboardingTimer,
} = useTour({
  showToast: () => showToast,
  openWorkspaceAgentList: () => openWorkspaceAgentList,
})
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
  openQuickCreateAgent,
  refreshAgentList: fetchAgentList,
  restartGateway,
  restartAllNodes,
  confirmRestartAllNodes,
  // 管理类动作（需 admin 权限，registry 中通过 hasPermission 判定）
  hasPermission,
  confirmUpdateCodeToMain,
  openAdminPanel: () => { showAdminPanel.value = true; pushOverlayState() },
  openAdminRestartService: () => openAdminSystemAction('restart'),
  openAdminSyncConfig: () => openAdminSystemAction('sync-config'),
  openAdminNodeSecret: () => openAdminSystemAction('node-secret'),
  openAdminConfigFile: () => openAdminSystemAction('config-file'),
  openWorkspaceAgentList,
  // 打开工作区并切换到 Git 侧边栏视图（侧边活动栏「Git」按钮 / Ctrl+Alt+Shift+V）
  openWorkspaceGit: () => {
    if (!showWorkspacePanel.value) {
      showWorkspacePanel.value = true
      if (windowWidth.value <= 768) pushOverlayState()
    }
    setWorkspaceSidebarView('git')
  },
  // 打开工作区并切换到「插件管理」侧边栏视图（侧边活动栏「插件」按钮 / Space m p）
  openWorkspacePlugins: () => {
    if (!showWorkspacePanel.value) {
      showWorkspacePanel.value = true
      if (windowWidth.value <= 768) pushOverlayState()
    }
    setWorkspaceSidebarView('plugins')
  },
  toggleTerminalPanel,
  toggleChatPanel,
  // 打开编辑器侧边栏的「管理分组」弹窗（重命名 / 删除）
  manageGroups: () => { workspacePanelRef.value?.openManageGroups?.() },
  openTopology: openTopologyOverlay,
  openSettings: () => { showSettingsModal.value = true },
  openDocs: openDocs,
  togglePetVisibility,
  openAgentList: openAgentListPalette,
  openCommandPaletteFileSearch: openCommandPaletteFileSearch,
  // 重新打开新手引导（首次登录后自动展示过一次，可随时重看）
  startOnboarding: (tourId) => startOnboarding(tourId || 'welcome'),
  // 重置新手引导标记：下次进入对应场景会重新触发
  resetOnboarding: () => {
    resetOnboardingMarks()
    activeTourId.value = null
    showToast('新手引导已重置，进入对应界面时会重新提示', 'success')
  },
  // 打开宠物大厅的「安装浏览器插件」弹层
  openInstallExtension: () => { petLobbyRef.value?.openInstallExtensionDialog?.() },
  // 打开宠物大厅的「安装本地后台服务（daemon）」弹层
  openDaemonInstall: () => { petLobbyRef.value?.openDaemonDialog?.() },
  // 退出登录：断开所有连接并清除认证信息（复用设置面板的断开逻辑）
  logout: disconnectAll,
  // 当前 Agent 组
  viewCurrentDiff: () => { const a = getCurrentAgentOrNull(); if (a) viewDiff(a) },
  viewCurrentRules: () => { const a = getCurrentAgentOrNull(); if (a) viewRules(a) },
  viewCurrentTools: () => { const a = getCurrentAgentOrNull(); if (a) viewTools(a) },
  createTerminalForCurrent: () => { const a = getCurrentAgentOrNull(); if (a) createTerminalForAgent(a) },
  openWorkspaceForCurrent: () => { const a = getCurrentAgentOrNull(); if (a) createWorkspaceForAgent(a) },
  // 全局：打开/隐藏编辑器面板（与 Ctrl+E 分支行为一致，不依赖当前 Agent）
  toggleWorkspacePanel,
  // 全局：快速抵达编辑器侧边栏的「内容搜索」（与 Ctrl+Shift+F 分支行为一致，编辑器未打开时不响应）
  openWorkspaceGlobalSearch: () => openWorkspaceGlobalSearch('content'),
  // 全局：快速抵达编辑器侧边栏的「文件名搜索」（与 Ctrl+Shift+P 分支行为一致，编辑器未打开时不响应）
  openWorkspaceFileSearch: () => openWorkspaceGlobalSearch('filename'),
  // 全局：快速抵达编辑器侧边栏的目录树（与 Ctrl+Shift+E 分支行为一致，编辑器未打开时不响应）
  openWorkspaceFileTree: () => {
    if (!showWorkspacePanel.value) return
    setWorkspaceSidebarView('files')
    focusFileTreeContainer()
  },
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
  // 编辑器选中内容 → 当前 Agent（命令面板动作 editor-send-selection-to-agent）
  getEditorSelection,
  sendSelectionToAgent,
  // 隐藏/显示当前 Agent 在大厅中的输出气泡（持久化在 PetLobby 内）
  toggleCurrentAgentOutput: () => {
    const a = getCurrentAgentOrNull()
    const lobby = petLobbyRef.value
    if (a && lobby && typeof lobby.toggleAgentOutput === 'function') {
      lobby.toggleAgentOutput(a.agent_id)
    }
  },
  isCurrentAgentOutputHidden: () => {
    const a = getCurrentAgentOrNull()
    const lobby = petLobbyRef.value
    return !!(a && lobby && typeof lobby.isOutputHidden === 'function' && lobby.isOutputHidden(a.agent_id))
  },
  // 当前焦点面板：关闭（面板头部图标保留不变）
  closeFocusedPanel,
  // 命令面板「f> 搜索文件」：对当前 Agent 工作区按文件名做后端模糊搜索，结果只含文件
  fileSearchResults: commandPaletteFileResults.value,
  fileSearchLoading: commandPaletteFileSearching.value,
  fileSearchError: commandPaletteFileError.value,
  searchWorkspaceFiles,
  clearWorkspaceFileSearch,
  openFileResult: openCommandPaletteFileResult,
  // 全局：打开命令面板（与 Ctrl+P 分支行为一致）
  openCommandPalette: () => { showCommandPalette.value = true },
  // 全局：保存编辑器当前标签（与 Ctrl+S 分支行为一致）
  saveActiveWorkspaceTab: () => saveActiveWorkspaceTab(),
  // 全局：左右/上下分割编辑器工作区（与 Ctrl+\ / Ctrl+Shift+\ 分支行为一致）
  splitWorkspacePane: (paneId, direction) => splitWorkspacePane(paneId, direction),
  activePaneId: activePaneId.value,
  // 全局：发送缓冲输入（与 Ctrl+Alt+Enter 分支行为一致）
  sendBufferedInput: () => sendBufferedInput(),
  // 大厅：删除选中的 Agent（与 Delete 分支行为一致）
  lobbyActiveAgentId: lobbyActiveAgentId.value,
  deleteLobbyAgent: (agentId) => {
    const agent = agentList.value.find(a => a.agent_id === agentId)
    if (agent) deleteAgent(agent.agent_id)
  },
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
  // 当前「可见」的 Agent 会话（用于把激活的 Agent 排在列表上方，并判断是否置灰）
  openedAgentIds: visibleSessionAgentIds.value,
  // 节点组：作用于大厅中选中的节点（lobbyActiveNodeId）
  currentNodeId: lobbyActiveNodeId.value,
  createAgentOnNode: (nodeId) => onLobbyCreateAgentOnNode(nodeId),
  openTerminalOnNode: (nodeId) => createTerminalForNode(nodeId),
  updateNodeCode: (nodeId) => confirmUpdateNodeCode(nodeId),
  restartNodeService: (nodeId) => confirmRestartNodeService(nodeId),
  renameNode: (nodeId) => { petLobbyRef.value?.renameActiveNode?.(nodeId) },
  // 大厅方向选中（Ctrl+Alt+方向键）：仅在大厅有 Agent 时可用
  hasLobbyAgents: (agentList.value || []).some(a => a && a.status !== 'stopped'),
  selectLobbyAgentInDirection: (dir) => { petLobbyRef.value?.selectAgentInDirection?.(dir) },
  // 大厅节点方向选中（Ctrl+Shift+方向键）：仅在大厅有节点时可用
  hasLobbyNodes: (availableNodeOptions.value || []).length > 0,
  selectLobbyNodeInDirection: (dir) => { petLobbyRef.value?.selectNodeInDirection?.(dir) },
  // 大厅全部输出显隐（Ctrl+Alt+A）：仅在大厅有 Agent 时可用
  hasLobbyAgentsForOutput: (agentList.value || []).some(a => a && a.status !== 'stopped'),
  toggleAllLobbyOutputs: () => { petLobbyRef.value?.toggleAllOutputs?.() },
}))

// 命令面板动作清单（来自统一注册表，个别动作按当前状态动态调整文案/图标）
const appActions = computed(() => {
  const ctx = commandPaletteCtx.value
  return actionDefs.map(a => {
    const label = resolveActionLabel(a, ctx)
    const icon = resolveActionIcon(a, ctx)
    if (label === a.label && icon === a.icon) return a
    return { ...a, label, icon }
  })
})

// 动态菜单文案/图标：默认取注册表静态值，个别动作按当前状态调整
function resolveActionLabel(action, ctx) {
  if (action.id === 'current-toggle-output') {
    return ctx.isCurrentAgentOutputHidden && ctx.isCurrentAgentOutputHidden() ? '显示输出' : '隐藏输出'
  }
  return action.label
}
function resolveActionIcon(action, ctx) {
  if (action.id === 'current-toggle-output') {
    return ctx.isCurrentAgentOutputHidden && ctx.isCurrentAgentOutputHidden() ? UI_ICONS.eye : UI_ICONS.eyeOff
  }
  return action.icon
}
// 大厅中在 Agent 宠物上右键：把「当前 Agent」切到该宠物，菜单动作随之刷新
function onLobbyContextAgent(agentId) {
  if (agentId) lobbyActiveAgentId.value = agentId
}
// 大厅宠物右键菜单动作：复用命令面板「当前 Agent」组
const lobbyContextActions = computed(() => {
  const ctx = commandPaletteCtx.value
  return actionDefs
    .filter(a => a.group === '当前 Agent')
    .map(a => ({
      id: a.id,
      label: resolveActionLabel(a, ctx),
      icon: resolveActionIcon(a, ctx),
      enabled: typeof a.enabled === 'function' ? a.enabled(ctx) : true,
    }))
})

// 大厅宠物右键菜单点击：按命令面板同款逻辑执行
function onLobbyContextRun(action) {
  if (!action) return
  const def = actionDefs.find(a => a.id === action.id)
  if (def) onCommandRun(def)
}

// ===== Panel 右键菜单（与宠物右键同款动作） =====
// 菜单坐标使用视口坐标（position: fixed），name 用作标题
const panelContextMenu = ref({ visible: false, x: 0, y: 0, name: '' })
// 右键菜单锁定的 Agent：菜单打开期间，「当前 Agent」组动作作用于它，而非当前激活面板
const contextMenuAgentId = ref(null)

function closePanelContextMenu() {
  if (panelContextMenu.value.visible) panelContextMenu.value.visible = false
  contextMenuAgentId.value = null
}

// 在 Panel 内右键（未选中文字）：先激活该 Panel 使「当前 Agent」指向它，再就地弹出菜单
function onPanelContextMenu(panel, event) {
  if (!panel || !panel.agentId) return
  activatePanel(panel.id)
  contextMenuAgentId.value = panel.agentId
  const agent = agentList.value.find(a => a.agent_id === panel.agentId)
  const MENU_W = 320
  const rows = Math.max(1, Math.ceil(lobbyContextActions.value.length / 2))
  const MENU_H = Math.min(44 + rows * 33, window.innerHeight * 0.6)
  let x = event.clientX
  let y = event.clientY
  if (x + MENU_W > window.innerWidth) x = Math.max(window.innerWidth - MENU_W, 0)
  if (y + MENU_H > window.innerHeight) y = Math.max(window.innerHeight - MENU_H, 0)
  panelContextMenu.value = {
    visible: true,
    x,
    y,
    name: (agent && (agent.name || agent.agent_id)) || panel.agentId,
  }
}

// 点击菜单项：先收起菜单（避免确认框被菜单遮挡），再复用宠物右键的执行链路。
// 关键：菜单动作通过 commandPaletteCurrentAgentId 定位「被右键的 Agent」，而该 computed
// 依赖 contextMenuAgentId；closePanelContextMenu() 会把它清空，故这里先快照、
// 收起菜单后恢复，动作执行完再复位——保证删除/重命名等始终作用于被右键的 Agent。
function onPanelContextAction(action) {
  if (!action || action.enabled === false) return
  const targetAgentId = contextMenuAgentId.value
  closePanelContextMenu()
  contextMenuAgentId.value = targetAgentId
  try {
    onLobbyContextRun(action)
  } finally {
    contextMenuAgentId.value = null
  }
}

// 侧边栏 Agent 项右键：锁定该 Agent 为菜单作用对象，就地弹出操作菜单（不改变当前面板布局）
function onSidebarAgentContextMenu(agent, event) {
  if (!agent || !event) return
  contextMenuAgentId.value = agent.agent_id
  const MENU_W = 320
  const rows = Math.max(1, Math.ceil(lobbyContextActions.value.length / 2))
  const MENU_H = Math.min(44 + rows * 33, window.innerHeight * 0.6)
  let x = event.clientX
  let y = event.clientY
  if (x + MENU_W > window.innerWidth) x = Math.max(window.innerWidth - MENU_W, 0)
  if (y + MENU_H > window.innerHeight) y = Math.max(window.innerHeight - MENU_H, 0)
  panelContextMenu.value = {
    visible: true,
    x,
    y,
    name: agent.name || agent.agent_id,
  }
}

// 大厅节点右键菜单点击：创建 Agent / 打开终端 / 更新代码 / 重启服务（后续可在此扩展更多节点操作）
function onLobbyNodeContextRun({ action, nodeId }) {
  if (!action) return
  if (action.id === 'node-create-agent') {
    onLobbyCreateAgentOnNode(nodeId)
  } else if (action.id === 'node-open-terminal') {
    createTerminalForNode(nodeId)
  } else if (action.id === 'node-update-code') {
    confirmUpdateNodeCode(nodeId)
  } else if (action.id === 'node-restart-service') {
    confirmRestartNodeService(nodeId)
  }
}

// 大厅节点右键「更新代码」：二次确认后调用单节点代码更新接口
function confirmUpdateNodeCode(nodeId) {
  const normalizedNodeId = String(nodeId || '').trim()
  if (!normalizedNodeId) return
  showConfirm(
    `确定要更新节点 "${normalizedNodeId}" 的代码吗？\n\n此操作将：\n1. 切换该节点到 main 分支\n2. 拉取最新代码\n3. 可能需要重启该节点服务`,
    () => {
      updateNodeCode(normalizedNodeId)
    },
    () => {},
    false
  )
}

async function updateNodeCode(nodeId) {
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetchWithAuth(
      `${getHttpProtocol()}://${host}:${port}/api/nodes/${encodeURIComponent(nodeId)}/code-update`,
      { method: 'POST' }
    )
    const result = await response.json().catch(() => ({}))
    if (response.ok && result.success) {
      showToast(result.data?.message || `已向节点 "${nodeId}" 发送更新请求`, 'success')
    } else {
      showToast(`节点 "${nodeId}" 更新失败：${result.error?.message || `HTTP ${response.status}`}`, 'error')
    }
  } catch (error) {
    console.error(`[LOBBY] Failed to update code for node ${nodeId}:`, error)
    showToast(`节点 "${nodeId}" 更新失败：${error.message || '未知错误'}`, 'error')
  }
}

// 大厅节点右键「重启服务」：二次确认后调用单节点服务重启接口
function confirmRestartNodeService(nodeId) {
  const normalizedNodeId = String(nodeId || '').trim()
  if (!normalizedNodeId) return
  showConfirm(
    `确认重启节点 "${normalizedNodeId}" 的服务吗？这将短暂中断该节点的连接。`,
    () => {
      restartNodeService(normalizedNodeId)
    },
    () => {},
    false
  )
}

async function restartNodeService(nodeId) {
  try {
    const { host, port } = getGatewayAddress()
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, nodeId, 'service/restart'), {
      method: 'POST',
      body: JSON.stringify({
        node_id: nodeId,
        restart_frontend: restartFrontendService.value
      })
    })
    const data = await response.json().catch(() => ({}))
    if (response.ok) {
      if (data.success === false) {
        showToast(data.error?.message || `节点 "${nodeId}" 重启失败`, 'error')
      } else {
        showToast(data.data?.message || `已向节点 "${nodeId}" 发送重启请求`, 'success')
      }
    } else {
      showToast(`节点 "${nodeId}" 重启失败：HTTP ${response.status}`, 'error')
    }
  } catch (error) {
    console.error(`[LOBBY] Failed to restart node ${nodeId}:`, error)
    showToast(`节点 "${nodeId}" 重启失败：${error.message || '未知错误'}`, 'error')
  }
}

// 大厅节点重命名：写入节点名称映射（与设置界面同一份数据，留空则恢复为节点 ID）
function onLobbyRenameNode({ nodeId, name }) {
  const normalizedNodeId = String(nodeId || '').trim()
  if (!normalizedNodeId) return
  const next = { ...nodeDisplayNames.value }
  const trimmed = String(name || '').trim()
  if (trimmed) next[normalizedNodeId] = trimmed
  else delete next[normalizedNodeId]
  saveNodeDisplayNames(next)
}

// 执行命令面板中的动作
function onCommandRun(action, openMode) {
  // 需要弹层输入的动作（如节点重命名）先关闭面板让出焦点，避免弹层被面板遮挡/抢焦点
  if (!action?.closePaletteOnRun) showCommandPalette.value = false
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
// useAgents 通过此 setter 写入静默窗口截止时间（App.vue 保留变量所有权，composable 只赋值）
function setModalAutoFocusSuppressUntil(timestamp) {
  modalAutoFocusSuppressUntil = timestamp
}

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
    showQuickCreateAgentModal.value ||
    showRenameAgentModal.value ||
    inputPrompt.value.visible ||
    showSessionDialog.value ||
    showDirDialog.value ||
    showCommandPalette.value ||
    showToolsModal.value ||
    showEditAccessModal.value ||
    showTopologyOverlay.value ||
    showOrchestrateModal.value ||
    confirmDialog.value
  )
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
const newAgentType = ref('agent') // 新 Agent 类型（默认通用 Agent，避免误建 git 仓库）
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
const userPermissions = ref(null) // null=未加载, {allowed:[pattern],denied:[pattern]}=已加载

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
// 自动安装/更新浏览器扩展：默认关闭。开启后本机 daemon 会在网关扩展版本变化时
// 自动下载并覆盖本地扩展目录（不会重启浏览器）。状态只存浏览器 localStorage，
// 随登录态一并推送给 daemon（daemon 只保留内存态，不落盘）。
const AUTO_INSTALL_BROWSER_EXT_STORAGE_KEY = 'jarvis_auto_install_browser_ext'
function loadAutoInstallBrowserExt() {
  try {
    return localStorage.getItem(AUTO_INSTALL_BROWSER_EXT_STORAGE_KEY) === '1'
  } catch (error) {
    console.warn('[BROWSER_EXT] Failed to load auto install setting:', error)
    return false
  }
}
const autoInstallBrowserExt = ref(loadAutoInstallBrowserExt())
function saveAutoInstallBrowserExtSetting(nextValue = autoInstallBrowserExt.value) {
  autoInstallBrowserExt.value = !!nextValue
  try {
    localStorage.setItem(AUTO_INSTALL_BROWSER_EXT_STORAGE_KEY, autoInstallBrowserExt.value ? '1' : '0')
  } catch (error) {
    console.warn('[BROWSER_EXT] Failed to save auto install setting:', error)
  }
  // 开关变化后立即重新推送一次给本机 daemon（与终端名称一致的做法）
  syncTokenToDaemon(auth.value.token, window.__jarvisAuthBridge.getGateway())
}
// 工作目录展示：开启隐藏时返回占位符，否则返回原始目录
const WORKING_DIR_HIDDEN_PLACEHOLDER = '••••••'
function getWorkingDirDisplay(workingDir) {
  if (hideWorkingDir.value) return WORKING_DIR_HIDDEN_PLACEHOLDER
  return workingDir || ''
}
// 终端名称 / 节点（拆自 composable useTerminalName）。
// terminalName 需在 useDaemonSync/useAuthBridge 之前创建（二者读取 terminalName.value）；
// getDaemonUrl / syncTokenToDaemon 来自 useDaemonSync（在其后定义），故以 getter 形式传入，
// useTerminalName 内部调用时才求值，避免 TDZ。
const { terminalName, saveTerminalNameSetting, initTerminalNameFromDaemon, selectedTerminalNodeId } = useTerminalName({
  auth,
  getDaemonUrl: () => getDaemonUrl,
  syncTokenToDaemon: (token, gw) => syncTokenToDaemon(token, gw),
})
// 本机 daemon 登录态同步（拆自独立 composable）
const {
  daemonPort,
  localDaemonOnline,
  getDaemonUrl,
  saveDaemonPortSetting,
  startLocalDaemonProbe,
  stopLocalDaemonProbe,
  syncTokenToDaemon,
} = useDaemonSync({
  auth,
  terminalName,
  autoInstallBrowserExt,
  getGateway: () => window.__jarvisAuthBridge?.getGateway?.(),
})
// 浏览器扩展登录态桥接（拆自独立 composable）
const { installAuthBridge } = useAuthBridge({
  auth,
  terminalName,
  gatewayUrl,
  parseGatewayAddress,
  syncTokenToDaemon,
})
installAuthBridge()
const newAgentNodeId = ref('master')

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

// 创建 Agent 的默认节点：优先 master，其次第一个可用节点
function getDefaultCreateAgentNodeId() {
  const options = filteredNodeOptionsForCreateAgent.value
  if (options.some(node => node.node_id === 'master')) return 'master'
  return options[0]?.node_id || ''
}

// 生成 Agent 名称：Agent类型-创建时间（如：代码Agent-20261213-140013）
function generateAgentName(agentType) {
  const typeName = agentType === 'agent' ? '通用Agent' : '代码Agent'
  const now = new Date()
  const date = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
  const time = `${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`
  return `${username.value}-${typeName}-${date}-${time}`
}

// 复制 Agent 时跳过 watch 中的名称设置
const skipNameWatch = ref(false)

// 监听 Agent 类型变化，自动填充默认名称
watch(newAgentType, (newType) => {
  if (skipNameWatch.value) return
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

// 聊天室（状态 + 消息收发/面板交互），从 App.vue 拆出到 composables/useChat.js
// 依赖 socket/auth/username/windowWidth/activeWindow/showChatPanel/focusWindow/showToast/showConfirm/
// playChatNotificationSound/getGatewayAddress/workspaceHostsChat/setWorkspaceMainView/showWorkspaceHostView/
// clamp/PANEL_DRAG_ACTIVATION_DISTANCE/ACTIVE_Z_INDEX/BASE_Z_INDEX，须在其定义之后调用
const {
  chatPanelRect,
  chatPanelCollapsed,
  chatPanelInteraction,
  chatPanelStyle,
  chatRooms,
  chatMessages,
  chatClients,
  chatRoomMembers,
  myClientId,
  activeChatRoomId,
  activePrivateClientId,
  chatUnreadCount,
  chatName,
  myUserId,
  chatSidebarWidth,
  chatUnreadMap,
  chatJoinedRooms,
  startChatSidebarResize,
  startChatPanelMove,
  startChatPanelResize,
  toggleChatPanel,
  toggleChatPanelCollapse,
  sendChatMessageToServer,
  createChatRoom,
  joinChatRoom,
  leaveChatRoom,
  deleteChatRoom,
  renameChatRoom,
  clearChatMessages,
  sendChatMessage,
  selectPrivateClient,
  handleChatMessage,
  getOrCreateClientId,
  restoreChatRoomsFromServer,
} = useChat({
  socket,
  auth,
  username,
  windowWidth,
  activeWindow,
  showChatPanel,
  focusWindow,
  showToast,
  showConfirm,
  playChatNotificationSound,
  getGatewayAddress,
  workspaceHostsChat,
  setWorkspaceMainView,
  showWorkspaceHostView,
  clamp,
  PANEL_DRAG_ACTIVATION_DISTANCE,
  ACTIVE_Z_INDEX,
  BASE_Z_INDEX,
})
// 文件树（状态 + 节点交互/键盘导航/右键菜单/上传下载/文件CRUD/复制粘贴/拖拽/核心加载），
// 从 App.vue 拆出到 composables/useFileTree.js
// 依赖 agentList/getVirtualWorkspaceAgent/resolveFileTreeAgent/resolveAgentForPath/openWorkspaceFile/
// setWorkspaceSidebarView/removeWorkspaceDir/fetchFileContent/fetchWithAuth/buildNodeHttpUrl/
// getGatewayAddress/showToast/showConfirm/globalSearchFileGlob/ensureWorkspaceSidebarFileTree，
// 须在其定义之后调用
const {
  // 状态（供 App.vue 保留代码/template 访问）
  fileTreeState,
  fileTreeExpanded,
  fileTreeLoading,
  expandedAgents,
  selectedAgentId,
  fileTreeSelectedPath,
  fileTreeSelectedAgentId,
  fileTreeContextMenu,
  fileTreeUploadInput,
  inputPrompt,
  fileTreeDropTargetPath,
  // 节点交互
  getFileTypeIcon,
  handleFileTreeNodeClick,
  selectFileTreeNode,
  focusFileTreeContainer,
  revealTabInFileTree,
  toggleAgentExpanded,
  toggleStoppedNodeCollapse,
  isStoppedNodeCollapsed,
  // 键盘导航
  handleFileTreeKeydown,
  // 右键菜单
  copyTextToClipboard,
  openFileTreeContextMenu,
  cancelInputPrompt,
  confirmInputPrompt,
  fileTreeContextActions,
  runFileTreeContextAction,
  // 上传下载
  readFileAsDataUrl,
  onFileTreeUploadInputChange,
  // 拖拽
  handleFileTreeDragStart,
  handleFileTreeDragEnd,
  handleFileTreeDragOver,
  handleFileTreeDragLeave,
  handleFileTreeDrop,
  // 核心加载
  initFileTree,
  getVisibleFileTreeNodes,
} = useFileTree({
  agentList,
  getVirtualWorkspaceAgent,
  resolveFileTreeAgent,
  resolveAgentForPath,
  openWorkspaceFile,
  setWorkspaceSidebarView,
  removeWorkspaceDir,
  fetchFileContent,
  fetchWithAuth,
  buildNodeHttpUrl,
  getGatewayAddress,
  showToast,
  showConfirm,
  globalSearchFileGlob,
  ensureWorkspaceSidebarFileTree,
})

// 补全列表
const showCompletions = ref(false) // 是否显示补全列表
const completionCursorPos = ref(-1) // 记录打开补全列表时的光标位置
const completionHasAtSymbol = ref(false) // 打开补全时输入框中是否已存在待替换的 @ 符号
const completionAgentId = ref(null) // 记录打开补全列表时的 Panel agentId
const completionSource = ref('panel') // 补全来源：'panel' 或 'lobby'（宠物大厅）
const petLobbyRef = ref(null) // 宠物大厅组件引用（用于写回大厅输入框补全文本）
const lobbyActiveAgentId = ref(null) // 宠物大厅中当前选中的宠物对应的 agentId
const lobbyActiveNodeId = ref(null) // 宠物大厅中当前选中的节点 id（节点操作快捷键据此作用）
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
// 命令面板 f> 文件搜索：结果 / 加载 / 错误（由 CommandPalette 的输入变化驱动）
const commandPaletteFileResults = ref([])
const commandPaletteFileSearching = ref(false)
const commandPaletteFileError = ref('')
// 搜索请求序号：丢弃过期响应（快速输入时后发先至）
let commandPaletteFileSearchToken = 0

// f> 文件搜索：对「当前 Agent 的工作区」按文件名做后端模糊搜索（结果只含文件）
async function searchWorkspaceFiles(rawQuery) {
  const query = String(rawQuery || '').trim()
  const token = ++commandPaletteFileSearchToken
  if (!query) {
    commandPaletteFileResults.value = []
    commandPaletteFileError.value = ''
    commandPaletteFileSearching.value = false
    return
  }
  const agentId = commandPaletteCurrentAgentId.value
  if (!agentId) {
    commandPaletteFileResults.value = []
    commandPaletteFileError.value = '没有当前 Agent'
    commandPaletteFileSearching.value = false
    return
  }
  commandPaletteFileSearching.value = true
  commandPaletteFileError.value = ''
  try {
    const data = await fetchFileSearchResults(agentId, { query, max_results: 50 })
    if (token !== commandPaletteFileSearchToken) return
    const results = Array.isArray(data.results) ? data.results : []
    commandPaletteFileResults.value = results
      .filter(item => item && item.file_path)
      .map(item => ({ name: item.name || '', file_path: item.file_path }))
  } catch (error) {
    if (token !== commandPaletteFileSearchToken) return
    commandPaletteFileResults.value = []
    commandPaletteFileError.value = error.message || '文件名搜索失败'
  } finally {
    if (token === commandPaletteFileSearchToken) commandPaletteFileSearching.value = false
  }
}

// 离开 f> 模式 / 关闭面板时清理搜索结果
function clearWorkspaceFileSearch() {
  commandPaletteFileSearchToken += 1
  commandPaletteFileResults.value = []
  commandPaletteFileError.value = ''
  commandPaletteFileSearching.value = false
}

// f> 选中文件：关闭面板并在编辑器中打开（后端返回相对工作目录的路径，需转绝对路径）
function openCommandPaletteFileResult(item) {
  if (!item || !item.file_path) return
  const agentId = commandPaletteCurrentAgentId.value
  showCommandPalette.value = false
  openWorkspaceFile(resolveAgentRelativePath(item.file_path, agentId), agentId)
}
// ---- 流水线编排可视化 ----
// 开启 localStorage 持久化：刷新页面后仍能恢复历史编排（事件广播是纯内存、不落盘）
const pipelineStore = new PipelineStore(20, 'orchestration')
const pipelineVersion = ref(0) // 事件到达后自增，触发 computed 重算
const pipelineList = computed(() => {
  void pipelineVersion.value
  return pipelineStore.listPipelines()
})
const activePipelineId = ref('')
const showOrchestrationOverlay = ref(false)

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
  // 面板关闭：清理 f> 文件搜索结果，避免下次打开残留
  clearWorkspaceFileSearch()
  // 面板关闭动作可能同时打开了其它弹窗（如命令执行打开设置/拓扑），此时不抢焦点
  if (isAnyModalOpen()) return
  nextTick(() => {
    if (isAnyModalOpen()) return
    focusCurrentPanelInput()
  })
})

// 执行状态
const isExecuting = ref(false)


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

// 系统设置（通知开关/配置同步/代码更新/节点重启/管理面板定位），拆自独立 composable
// 依赖 showAdminPanel/adminPanelRef/availableNodeOptions/getGatewayAddress/getHttpProtocol/
// fetchWithAuth/buildNodeHttpUrl/showToast/showConfirm；pushOverlayState/isRestartingGateway/
// restartFrontendService 定义在调用点之后，用 getter 注入
const {
  notifyOnExit,
  notifyOnInput,
  syncConfigSourceNode,
  syncConfigTargetNodes,
  syncConfigSections,
  isSyncingConfig,
  isUpdatingCode,
  saveNotifySettings,
  handleSyncConfig,
  handleUpdateCodeToMain,
  openAdminSystemAction,
  confirmUpdateCodeToMain,
  confirmRestartAllNodes,
  restartAllNodes,
  syncConfig,
  updateCodeToMain,
} = useSettings({
  showAdminPanel,
  adminPanelRef,
  pushOverlayState: () => pushOverlayState,
  getGatewayAddress,
  getHttpProtocol,
  fetchWithAuth,
  buildNodeHttpUrl,
  showToast,
  showConfirm,
  availableNodeOptions,
  isRestartingGateway: () => isRestartingGateway,
  restartFrontendService: () => restartFrontendService,
})



// ========== Agent 管理方法（从 App.vue 拆出到 composables/useAgents.js）==========
const {
  // 域内 ref（App.vue 解构共享）
  dirDialogContext,
  showToolsModal,
  toolsContent,
  toolsLoading,
  showEditAccessModal,
  editingAccessAgent,
  editAccessRead,
  editAccessInteract,
  // 函数
  getStatusText,
  getStatusClass,
  isWaitingInput,
  fetchAgentStatus,
  syncOnlineAgentStatuses,
  getCreateAgentDirectoryNodeId,
  resetDirectorySelectionState,
  openDirDialog,
  fetchDirectories,
  selectDirectory,
  handleDirSearchKeydown,
  enterDirectory,
  goToParentDir,
  confirmDirectory,
  cancelDirDialog,
  openCreateAgentModal,
  onLobbyCreateAgentOnNode,
  fetchModelGroups,
  fetchUserAccessibleNodes,
  fetchUserPermissions,
  matchPermissionPattern,
  hasPermission,
  fetchNodeStatus,
  startNodeStatusRefresh,
  stopNodeStatusRefresh,
  fetchUserList,
  formatNodeOptionLabel,
  getDefaultTerminalNodeId,
  getAgentNodeLabel,
  getAgentNodeDisplayLabel,
  getAgentProxyNodeLabel,
  getCurrentAgentNodeId,
  getWorkspaceTargetNodeId,
  checkCodeAgentDirConflict,
  createAgentWithOptions,
  afterAgentCreated,
  createAgent,
  openQuickCreateAgent,
  openFullCreateAgentFromQuick,
  submitQuickCreateAgent,
  openCompletions,
  closeCompletionsWithoutSelect,
  handleCompletionKeydown,
  scrollToSelected,
  scrollToDirSelected,
  findVisiblePanelTextarea,
  insertAtPosition,
  insertCompletion,
  fetchAgentList,
  buildCopiedAgentPayload,
  copyAgent,
  batchCopyAgents,
  onLobbyAddAgentToGroup,
  onLobbyRemoveAgentFromGroup,
  addSelectedToGroup,
  createGroupWithAgents,
  renameAgentGroup,
  deleteAgentGroup,
  viewRules,
  exitNonInteractiveMode,
  viewTools,
  renameAgent,
  confirmRename,
  editAgentAccess,
  saveAgentAccess,
  deleteAgent,
  regenerateAgent,
  batchDeleteAgents,
  onLobbySelectAgent,
  getLobbyInputState,
  sendLobbyInput,
  getLobbyLatestOutput,
  onLobbyComplete,
  switchAgent,
  startAgentListRefresh,
  stopAgentListRefresh,
} = useAgents({
  agentList,
  currentAgentId,
  agentStatuses,
  isStoppedAgent,
  currentAgent,
  agentGroups,
  selectedAgents,
  isBatchMode,
  inputText,
  inputMode,
  inputRequests,
  inputTip,
  panelInputTexts,
  panelInputModes,
  panelInputTips,
  panelConfirmData,
  pendingInputAgentId,
  pendingConfirmAgentId,
  inputBuffers,
  allOutputs,
  outputs,
  outputList,
  panelOutputLists,
  panels,
  sessionPanelRefs,
  showToast,
  showConfirm,
  showSettingsModal,
  showWorkspacePanel,
  activeWorkspaceSession,
  hasNoPanel,
  isAutoFocusSuppressed,
  isAnyModalOpen,
  socket,
  sockets,
  auth,
  username,
  getHttpProtocol,
  buildNodeHttpUrl,
  getGatewayAddress,
  fetchWithAuth,
  escapeHtml,
  historyStorage,
  loadHistoryMessages,
  sendMessageToAgent,
  setupHistoryScrollListener,
  openAgentInPanel,
  closePanel,
  closeAgentInPanel,
  closeOpenDirDialog,
  confirmOpenDir,
  restoreWorkspacePaneContents,
  saveRecentWorkDir,
  loadRecentWorkDirs,
  filteredDirList,
  sortCompletionItems,
  recordCompletionSelection,
  switchGeneration,
  windowWidth,
  agentListLoaded,
  setModalAutoFocusSuppressUntil,
  MODAL_AUTOFOCUS_SUPPRESS_MS,
  hasMoreHistory,
  historyOffset,
  showCompletions,
  completionCursorPos,
  completionHasAtSymbol,
  completionAgentId,
  completionSource,
  petLobbyRef,
  completions,
  completionSearch,
  fileCompletions,
  completionSearchInput,
  completionsModalRef,
  selectedIndex,
  showCreateAgentModal,
  showQuickCreateAgentModal,
  quickCreateAgentLoading,
  quickCreateAgentError,
  showRenameAgentModal,
  renamingAgent,
  renameAgentName,
  showDirDialog,
  currentDirPath,
  dirList,
  selectedDir,
  dirSearchText,
  dirSearchInput,
  selectedDirIndex,
  dirDialogRef,
  saveAgentGroups,
  renameInput,
  openDirNodeId,
  openDirPath,
  openDirDialogRef,
  newAgentType,
  newAgentDir,
  newAgentName,
  modelGroups,
  newAgentModelGroup,
  newCodeAgentWorktree,
  newAgentQuickMode,
  newAgentRestoreSession,
  newAgentNoInteractionMode,
  newAgentTaskDescription,
  newAgentCreateError,
  newAgentProxyNode,
  newAgentAccessAclRead,
  newAgentAccessAclInteract,
  availableUserOptions,
  availableNodeOptions,
  userAccessibleNodes,
  userPermissions,
  getNodeDisplayName,
  newAgentNodeId,
  filteredNodeOptionsForCreateAgent,
  getDefaultCreateAgentNodeId,
  generateAgentName,
  skipNameWatch,
  rulesLoading,
  showRulesModal,
  rulesContent,
  rulesLoadedContent,
  selectedTerminalNodeId,
  chatName,
  saveToHistory,
  lobbyHistoryIndex,
  lobbyHistoryTemp,
  maybeStartTour,
  fileTreeState,
  fileTreeExpanded,
  fileTreeLoading,
  orchestrateAgents: () => orchestrateAgents,
  orchestrateActiveIndex: () => orchestrateActiveIndex,
  orchestrateNodeId: () => orchestrateNodeId,
  terminals: () => terminals,
  terminalHosts: () => terminalHosts,
  disposeExecutionTerminal: () => disposeExecutionTerminal,
  connectToAgent: () => connectToAgent,
  autoConnectToOnlineAgents: () => autoConnectToOnlineAgents,
  renderMessageHtml: () => renderMessageHtml,
  appendOutput: () => appendOutput,
  sendInputDirectly: () => sendInputDirectly,
  sendBufferedInput: () => sendBufferedInput,
  sendConfirmResult: () => sendConfirmResult,
  restoreWaitingConfirmUI: () => restoreWaitingConfirmUI,
  pushOverlayState: () => pushOverlayState,
})
// Diff 浮动窗口（状态 + 获取/渲染/文件导航），从 App.vue 拆出到 composables/useDiff.js
// 依赖 getGatewayAddress/getCurrentAgentNodeId/fetchWithAuth/buildNodeHttpUrl/windowWidth，须在其定义之后调用
const {
  showDiffModal,
  diffFiles,
  diffActiveIndex,
  diffLoading,
  diffError,
  diffMobileShowDetail,
  diffActiveHtml,
  selectDiffFile,
  viewDiff
} = useDiff({
  windowWidth,
  getGatewayAddress,
  getCurrentAgentNodeId,
  fetchWithAuth,
  buildNodeHttpUrl
})
// Session 恢复（状态 + 恢复/取消），从 App.vue 拆出到 composables/useSession.js
// 依赖 currentAgentId/getGatewayAddress/getCurrentAgentNodeId/fetchWithAuth/buildNodeHttpUrl/loadHistoryMessages，须在其定义之后调用
const {
  showSessionDialog,
  availableSessions,
  restoreSession,
  cancelSessionDialog
} = useSession({
  currentAgentId,
  getGatewayAddress,
  getCurrentAgentNodeId,
  fetchWithAuth,
  buildNodeHttpUrl,
  loadHistoryMessages
})
// 编排（状态 + 解析/创建/文件浏览），从 App.vue 拆出到 composables/useOrchestrate.js
const {
  showOrchestrateModal,
  orchestrateNodeId,
  orchestrateFilePath,
  orchestratePluginTemplates,
  orchestratePluginTemplatesLoading,
  orchestrateRecentFiles,
  ORCHESTRATE_RECENT_KEY,
  ORCHESTRATE_RECENT_MAX,
  orchestrateAgents,
  orchestrateHasFlow,
  orchestrateNodes,
  orchestrateActiveIndex,
  orchestrateLoading,
  orchestrateError,
  orchestrateCreating,
  orchestrateResults,
  orchestrateRunWorkingDir,
  orchestrateRunning,
  orchestrateFileEntries,
  orchestrateSelectedFile,
  orchestrateDialogRef,
  orchestrateShowBrowser,
  orchestrateCurrentDirPath,
  orchestrateLocalFileInput,
  orchestrateDirSearchText,
  orchestrateSelectedIndex,
  orchestrateFilteredDirs,
  orchestrateFilteredFiles,
  orchestrateNavItems,
  orchestrateHighlightedDir,
  orchestrateHighlightedFile,
  ORCHESTRATE_FILE_EXTENSIONS,
  buildOrchestrateAgentForm,
  openOrchestrateModal,
  closeOrchestrateModal,
  loadOrchestrateRecentFiles,
  saveOrchestrateRecentFile,
  removeOrchestrateRecentFile,
  selectOrchestrateRecentFile,
  loadOrchestratePluginTemplates,
  selectOrchestratePluginTemplate,
  parseOrchestrationFile,
  addOrchestrateAgent,
  removeOrchestrateAgent,
  createAllOrchestrateAgents,
  openOrchestrateDirDialog,
  runOrchestration,
  previewOrchestration,
  handleApproval,
  isOrchestrateFile,
  filterOrchestrateEntries,
  fetchOrchestrateEntries,
  toggleOrchestrateBrowser,
  orchestrateInitialBrowsePath,
  enterOrchestrateDir,
  goToOrchestrateParentDir,
  onOrchestrateSelectFile,
  onOrchestrateLocalSelect,
  onOrchestrateLocalFileChange,
  handleOrchestrateSearchKeydown,
  syncOrchestrateKeyboardSelection,
  scrollToOrchestrateSelected,
  onOrchestrateNodeChange,
} = useOrchestrate({
  agentList,
  availableNodeOptions,
  buildNodeHttpUrl,
  fetchWithAuth,
  filteredNodeOptionsForCreateAgent,
  getDefaultCreateAgentNodeId,
  getGatewayAddress,
  hasNoPanel,
  openAgentInPanel,
  pipelineStore,
  pipelineVersion,
  setWorkspaceSidebarView,
  showToast,
  showWorkspaceSidebar,
  readFileAsDataUrl,
  createAgentWithOptions,
  fetchAgentList,
  fetchNodeStatus,
  dirDialogContext,
  openDirDialog,
  startAgentListRefresh,
})
// 切换当前工作的 Agent

// 同步指定 Agent 的输入模式与提示到全局/面板状态
// 用于 input_request 到达时更新 UI（多行 textarea 与单行 input 的切换依据）
function syncAgentInputMode(targetAgentId, payload) {
  if (!targetAgentId) return
  inputTip.value = payload.tip || ''
  inputMode.value = payload.mode || 'multi'
  if (payload.preset) {
    inputText.value = payload.preset
  }
  // 同步到 Panel 隔离状态
  panelInputTips.value.set(targetAgentId, payload.tip || '')
  panelInputModes.value.set(targetAgentId, payload.mode || 'multi')
  panelInputPasswords.value.set(targetAgentId, payload.is_password || false)
  if (payload.preset) {
    panelInputTexts.value.set(targetAgentId, payload.preset)
  }
  pendingInputAgentId.value = targetAgentId
}

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
      // 缓冲区内容已消费，但输入模式仍需同步（否则多行输入框不会即时切为单行）
      if (isCurrentAgent(targetAgentId)) {
        syncAgentInputMode(targetAgentId, payload)
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
      syncAgentInputMode(targetAgentId, payload)
      // 聚焦输入框（弹窗或宠物环形菜单打开时不抢焦点）
      const targetPanel = panels.value.find(p => p.agentId === targetAgentId)
      const sp = targetPanel ? sessionPanelRefs.get(targetPanel.id) : null
      if (sp?.focusInput && !isAnyModalOpen()) sp.focusInput()

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
    if (sp?.focusInput && isCurrentAgent(targetAgentId) && !isAnyModalOpen()) sp.focusInput()
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
      // 去重：已存在的会话（如实时共享/恢复场景）只更新 access 级别，避免重复 push
      const existing = terminalSessions.value.find(t => t.terminal_id === terminalId)
      if (existing) {
        if (payload?.access) existing.access = payload.access
        return
      }
      terminalSessions.value.push({
        terminal_id: terminalId,
        node_id: nodeId,
        interpreter: payload?.interpreter || 'bash',
        working_dir: payload?.working_dir || '.',
        access: payload?.access || 'owner',
        terminal: null,
        hostEl: null,
        fitAddon: null,
        resizeObserver: null,  // ResizeObserver 实例
        history: [],  // 保存历史输出，用于面板隐藏后再显示时恢复
      })
      // 仅当本设备发起了终端创建时才自动切换，避免他端共享的终端打断本设备工作流
      if (terminalCreationTracker.shouldSwitch()) {
        activeTerminalId.value = terminalId
      }
      // 初始化终端
      nextTick(() => {
        const hostEl = independentTerminalHosts.value.get(terminalId)
        if (hostEl) {
          initIndependentTerminal(terminalId, hostEl)
        }
      })
      // 实时共享：接管会话，让后端记录本用户以便接收实时输出
      attachTerminalSession(terminalId)
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
  } else if (type === 'pipeline_event') {
    // 流水线编排进度事件：归并进 pipelineStore，驱动 DAG 视图实时刷新
    onPipelineEvent(payload)
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
  } else if (type === 'editor_open_file') {
    // Agent 请求在编辑器中打开文件并定位到指定行/列（结构化编辑器指令，非 eval_js 逃逸口）
    handleEditorOpenFile(payload)
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

// Agent → 编辑器指令：打开文件并定位到指定行/列
// payload: { agent_id, path, line?, column?, select_start?, select_end?, reveal? }
async function handleEditorOpenFile(payload) {
  const agentId = payload?.agent_id || currentAgentId.value
  const path = resolveAgentRelativePath(payload?.path, agentId)
  if (!path) return
  // 先定位/创建该 Agent 的编辑器面板：复用其已有的 file 面板，或分割当前面板
  // 在新 file 面板中打开——避免把当前会话/聊天/终端区域覆盖掉。
  ensureAgentEditorPane(agentId)
  await openWorkspaceFile(path, agentId)   // 复用现有入口（建会话/加载内容/激活标签）
  await nextTick()
  const modelData = editorModels.get(path)
  const view = getActiveWorkspaceView()
  if (!view || !modelData) return
  const line = Number(payload?.line || 1)
  const col = Number(payload?.column || 1)
  if (payload?.reveal !== false) view.revealLineInCenter(line)
  if (payload?.select_start != null && payload?.select_end != null) {
    const startCol = Number(payload.select_start) + 1
    const endCol = Math.max(startCol, Number(payload.select_end) + 1)
    view.setSelection(new monaco.Selection(line, startCol, line, endCol))
  }
  view.setPosition({ lineNumber: line, column: col })
  view.focus()
}

// 获取当前活跃编辑器中的选中内容（供命令面板动作 enabled 判断与 sendSelectionToAgent 使用）
// 返回 null 表示无选中/无编辑器；否则返回 { path, text, startLine, endLine }
function getEditorSelection() {
  const view = getActiveWorkspaceView()
  if (!view) return null
  const model = view.getModel()
  if (!model) return null
  const selection = view.getSelection()
  if (!selection || selection.isEmpty()) return null
  const path = model.__jarvisPath || ''
  const text = model.getValueInRange(selection)
  if (!text || !text.trim()) return null
  return { path, text, startLine: selection.startLineNumber, endLine: selection.endLineNumber }
}

// 把编辑器选中内容发给当前 Agent，让 Agent 分析/解释/修改
function sendSelectionToAgent() {
  const sel = getEditorSelection()
  if (!sel) {
    showToast('请先在编辑器中选中代码', 'info')
    return
  }
  const agentId = currentAgentId.value
  if (!agentId) {
    showToast('请先选中当前 Agent', 'error')
    return
  }
  const location = sel.path
    ? `（文件: ${sel.path} 行 ${sel.startLine}-${sel.endLine}）`
    : `（行 ${sel.startLine}-${sel.endLine}）`
  const message = {
    type: 'input_result',
    payload: {
      text: `请分析以下选中代码${location}：\n${sel.text}`,
      agent_id: agentId,
      display_name: chatName.value || username.value || '',
      input_mode: 'single',
    },
  }
  sendMessageToAgent(message, agentId)
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
  if (text.length > 10 * 1024 * 1024) text = text.slice(0, 10 * 1024 * 1024) + '...[truncated]'
  return text
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





// 缓冲被消费/清空时，若缓存管理面板正显示该 Agent 的缓冲，则关闭面板并重置编辑文本。
// 避免：① 面板残留旧内容（消费后再次打开显示旧内容）；② 消费后再次加内容时面板自动重弹
// （showBufferPanel 仍为 true，hasBufferedInput 由 false 变 true 触发 v-if 重新显示）。
function closeBufferPanelIfForAgent(agentId) {
  if (bufferPanelAgentId.value === agentId) {
    showBufferPanel.value = false
    bufferEditText.value = ''
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
  // 缓冲已被消费：若缓存面板正显示该 Agent，关闭面板并重置编辑文本
  closeBufferPanelIfForAgent(targetAgentId)
}

function clearBuffer() {
  const agentId = bufferPanelAgentId.value
  if (!agentId) {
    return
  }
  inputBuffers.value.delete(agentId)
  // 清空后若缓存面板正显示该 Agent，关闭面板并重置编辑文本
  closeBufferPanelIfForAgent(agentId)
  appendOutput({
    output_type: 'system',
    agent_name: 'system',
    text: '🗑️ 缓冲区已清空',
    lang: 'text',
  })
}

function loadBufferToInput() {
  const agentId = bufferPanelAgentId.value
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
  const agentId = bufferPanelAgentId.value
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
    // 乐观降级执行状态：避免后端 status_update 到达前，
    // 大厅/面板仍按 waiting_confirm 渲染出无消息的默认「请确认」
    const confirmStatus = agentStatuses.value.get(targetAgentId)?.execution_status
    if (confirmStatus === 'waiting_confirm') {
      agentStatuses.value.set(targetAgentId, {execution_status: 'running'})
    }
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

// 终端域（拆自 composable useTerminal）：xterm 实例管理、独立终端会话、
// 终端浮动面板、终端共享、execution chunks 重建。依赖注入与 App.vue 保持一致。
const {
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
  disposeExecutionTerminal,
  setTerminalRef,
  setTerminalHostRef,
  initIndependentTerminal,
  attachTerminalSession,
  restoreTerminalSessions,
  createTerminalForSelectedNode,
  createTerminalForNode,
  createTerminalForAgent,
  closeTerminal,
  saveTerminalPanelRect,
  terminalPanelInteraction,
  ensureTerminalPanelInViewport,
  startTerminalPanelMove,
  startTerminalPanelResize,
  switchTerminal,
  sendTerminalResize,
  showTerminalShareModal,
  terminalShareRead,
  terminalShareInteract,
  openTerminalShareDialog,
  saveTerminalShare,
  filteredUserOptionsForTerminalShare,
} = useTerminal({
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
})
let heartbeatTimer = null // 心跳定时器（App.vue 管理生命周期：onMounted 启动 / onUnmounted 清理）
// 网关连接（Gateway WebSocket 连接 + 多 Agent 连接 + 心跳检测），拆自独立 composable
// 依赖 socket/sockets（App.vue 顶层创建）/auth/username/myClientId/terminalSessions/allOutputs/
// currentAgentId/agentList/agentStatuses/showConnectModal/showSettingsModal/userAccessibleNodes/
// gitCustomDir/parseGatewayAddress/buildWebSocketUrl/buildWebSocketProtocols/buildAgentWebSocketUrl/
// getGatewayAddress/buildNodeHttpUrl/fetchWithAuth/loginWithPassword/hasAuthToken/
// startAgentListRefresh/startNodeStatusRefresh/restoreVirtualWorkspaceDirs/loadGitCustomDir/
// refreshUserInfo/fetchUserPermissions/fetchModelGroups/fetchNodeStatus/fetchUserAccessibleNodes/
// restoreTerminalSessions/getOrCreateClientId/sendChatMessageToServer/loadHistoryMessages/
// closeTerminal/handleMessage/getAgentLastSeq/showToast/showConfirm，
// 须在 useChat/useTerminal 之后调用（依赖其返回的 myClientId/terminalSessions 等）
const {
  gatewayUrl,
  lastPongTime,
  HEARTBEAT_INTERVAL,
  HEARTBEAT_TIMEOUT,
  connecting,
  agentConnecting,
  connectingAgents,
  connectErrorMessage,
  isRestartingGateway,
  restartNodeId,
  restartFrontendService,
  reconnecting,
  reconnectAttempts,
  reconnectTimer,
  reconnectInterval,
  userDisconnected,
  isAutoConnecting,
  connectionStatus,
  connectionLabel,
  connect,
  disconnect,
  reconnect,
  disconnectAll,
  handleRestartGateway,
  confirmRestartGateway,
  restartGateway,
  connectToAgent,
  autoConnectToOnlineAgents,
  checkHeartbeatTimeout,
  sendHeartbeat,
} = useGatewayConnection({
  socket,
  sockets,
  auth,
  username,
  myClientId,
  terminalSessions,
  allOutputs,
  currentAgentId,
  agentList,
  agentStatuses,
  showConnectModal,
  showSettingsModal,
  autoLoginEnabled,
  userAccessibleNodes,
  gitCustomDir,
  agentMap,
  parseGatewayAddress,
  buildWebSocketUrl,
  buildWebSocketProtocols,
  buildAgentWebSocketUrl,
  getGatewayAddress,
  buildNodeHttpUrl,
  fetchWithAuth,
  loginWithPassword,
  hasAuthToken,
  startAgentListRefresh,
  startNodeStatusRefresh,
  restoreVirtualWorkspaceDirs,
  loadGitCustomDir,
  refreshUserInfo,
  fetchUserPermissions,
  fetchModelGroups,
  fetchNodeStatus,
  fetchUserAccessibleNodes,
  restoreTerminalSessions,
  getOrCreateClientId,
  sendChatMessageToServer,
  loadHistoryMessages,
  closeTerminal,
  handleMessage,
  getAgentLastSeq,
  showToast,
  showConfirm,
})
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






// SessionPanel 浮动面板
const SESSION_PANEL_MIN_WIDTH = 400
const SESSION_PANEL_MIN_HEIGHT = 300
const SESSION_PANEL_STORAGE_KEY_PREFIX = 'jarvis_session_panel_rect_'
const sessionResizeDirections = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

function getDefaultSessionPanelRect(panelId) {
  return {
    top: 80,
    left: Math.max(window.innerWidth - 824, 16),
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




// 监听面板显示状态
watch(showWorkspacePanel, (visible) => {
  if (visible) {
    startWorkspaceFileHeartbeat()
    return
  }

  stopWorkspaceFileHeartbeat()
})

watch(activeWorkspaceTabPath, () => {
  startWorkspaceFileHeartbeat()
})

// 把注册表中的快捷键字符串（如 "Ctrl+Alt+Shift+D" / "F2"）解析为匹配条件

// 把注册表中的快捷键字符串（如 "Ctrl+Alt+Shift+D" / "F2"）解析为匹配条件

// 把注册表中的快捷键字符串（如 "Ctrl+Alt+Shift+D" / "F2"）解析为匹配条件
function parseShortcut(shortcut) {
  if (!shortcut || typeof shortcut !== 'string') return null
  const parts = shortcut.split('+').map(p => p.trim()).filter(Boolean)
  if (!parts.length) return null
  const cond = { ctrl: false, alt: false, shift: false, key: '' }
  for (const part of parts) {
    const lower = part.toLowerCase()
    if (lower === 'ctrl' || lower === 'cmd' || lower === 'meta') cond.ctrl = true
    else if (lower === 'alt' || lower === 'option') cond.alt = true
    else if (lower === 'shift') cond.shift = true
    else cond.key = part
  }
  return cond.key ? cond : null
}

// 判断键盘事件是否命中某个快捷键（基于 event.code，避免受输入法/键盘布局影响）
function matchShortcut(shortcut, event) {
  const cond = parseShortcut(shortcut)
  if (!cond) return false
  const ctrlPressed = event.ctrlKey || event.metaKey
  if (ctrlPressed !== cond.ctrl) return false
  if (event.altKey !== cond.alt) return false
  if (event.shiftKey !== cond.shift) return false
  const key = cond.key
  if (/^[a-z]$/i.test(key)) return event.code === 'Key' + key.toUpperCase()
  if (/^[0-9]$/.test(key)) return event.code === 'Digit' + key
  if (key === '`') return event.code === 'Backquote'
  if (key === ',') return event.code === 'Comma'
  if (key === '/') return event.code === 'Slash'
  if (key === '\\') return event.code === 'Backslash'
  if (key === 'Backspace') return event.code === 'Backspace'
  if (/^F[0-9]{1,2}$/i.test(key)) return event.code === key.toUpperCase()
  return event.key === key
}

// 判断事件目标是否是可编辑元素（输入框 / 文本域 / contentEditable）
// 用于全局快捷键避让：在可编辑元素中按键应保留原生行为
function isEditableElement(target) {
  if (!target || typeof target !== 'object') return false
  const tagName = String(target.tagName || '').toLowerCase()
  if (tagName === 'input' || tagName === 'textarea' || tagName === 'select') return true
  if (target.isContentEditable) return true
  return false
}

// 判断焦点是否在 Monaco 编辑器内部（含其隐藏输入框 textarea.ime-text-area）
// 用于全局快捷键避让：编辑器聚焦时，Monaco 自带键位（多光标 / 跳转括号 / 重命名符号）
// 应优先于全局快捷键生效，避免全局分支抢先 preventDefault 把编辑器原生行为吃掉
function isMonacoEditorFocused() {
  const el = document.activeElement
  if (!el || typeof el.closest !== 'function') return false
  return !!el.closest('.monaco-editor')
}

// 判断焦点是否在终端（xterm）内部。xterm 通过隐藏的 <textarea class="xterm-helper-textarea">
// 接收键盘输入，其 tagName 已是 textarea（isEditableElement 可覆盖）；这里再按 .xterm 容器
// 显式兜底，避免依赖 xterm 内部 DOM 结构变化，确保终端聚焦时空格序列不生效。
function isTerminalFocused() {
  const el = document.activeElement
  if (!el || typeof el.closest !== 'function') return false
  return !!el.closest('.xterm')
}

// 编辑器是否已「脱离」全局快捷键控制：在 Monaco 编辑器里按 ESC 后置 true，
// 使 Ctrl+A 不再被编辑器全选吃掉，而是触发命令面板（列出 Agent）。
// 重新点击/聚焦编辑器时自动恢复为 false（见 bindWorkspaceViewEvents 的 onDidFocusEditorText）。
const editorShortcutLocked = ref(false)

// ===== 空格 Leader 按键序列 =====
// 整体重设计：用「空格 + 领域键 + 动作键」的两级按键序列替代大量 Ctrl+Alt(+Shift)+字母 组合键。
// 语义键一律用无修饰键的单字母，绝对不被系统/浏览器拦截（用户环境 Ctrl+Alt+Shift 被系统软件拦截）。
// 流程：按空格进入序列 → 弹浮窗显示领域 → 按领域键(如 a) → 弹浮窗显示该领域动作 → 按动作键执行。
// ESC 中断；浮窗一直显示直到用户按键或 ESC 中断（不设超时自动退出）；
// 焦点在输入框/编辑器/终端时空格保留为正常输入。
// 序列状态：active 是否激活；path 为已输入的键序列（[]=待选领域，['a']=已选领域等待动作）
const spaceSeq = ref({ active: false, path: [] })

// 空格序列激活期间锁定焦点：防止焦点转移到可编辑元素（含多行输入框/编辑器/终端），
// 否则后续序列按键会被输入框捕获而不是推进序列。
function handleSpaceSeqFocusIn(e) {
  if (!spaceSeq.value.active) return
  const target = e.target
  if (isEditableElement(target) || isMonacoEditorFocused() || isTerminalFocused()) {
    // 阻止焦点落入可编辑元素：blur 回 body，让按键继续走全局 keydown 推进序列
    if (target && typeof target.blur === 'function') target.blur()
  }
}

function enterSpaceSeq() {
  spaceSeq.value = { active: true, path: [] }
  // 进入序列时若焦点在可编辑元素，立即移开，避免后续按键被输入框捕获
  const el = document.activeElement
  if (el && (isEditableElement(el) || isMonacoEditorFocused() || isTerminalFocused())) {
    el.blur()
  }
}
function exitSpaceSeq() {
  spaceSeq.value = { active: false, path: [] }
}
// 当前空格序列对应的命令分组（供浮窗渲染）：每一级都按「领域前缀」分组展示。一级（未选领域）
// 显示完整序列（如 ad=显示变更）；选定领域后（如 Space a）组内命令只显示动作键（如 d 显示变更），
// 不再重复领域前缀。只保留当前前缀对应的分组，让用户看到「当前前缀」下的全部可选项。
const spaceSeqOptions = computed(() => {
  const path = spaceSeq.value.path || []
  const prefix = path.join('')
  const showPrefix = path.length === 0
  return Object.entries(SPACE_COMMANDS)
    .filter(([gKey]) => path.length === 0 || gKey === prefix)
    .map(([gKey, g]) => ({
      key: gKey,
      label: g.label,
      active: path[0] === gKey,
      children: Object.entries(g.children || {}).map(([ck, leaf]) => ({
        key: showPrefix ? gKey + ck : ck,
        label: leaf.label,
        active: path.length === 2 && prefix === gKey + ck,
      })),
    }))
})

// 弹窗焦点陷阱：返回当前可见的弹窗容器（多个弹窗同时打开时取最顶层）
function getActiveOverlay() {
  const overlays = document.querySelectorAll('.modal-overlay, .palette-overlay')
  for (let i = overlays.length - 1; i >= 0; i--) {
    const el = overlays[i]
    // 仅取真正渲染且可见的（v-if 控制的弹窗关闭后不在 DOM 中；再排除 display:none）
    if (el.offsetParent !== null || el.getClientRects().length > 0) return el
  }
  return null
}

// 弹窗焦点恢复：记录弹窗打开前的焦点元素，弹窗关闭后恢复
let overlayReturnFocusEl = null
let overlayObserver = null

// 收集弹窗内可聚焦元素（Tab 循环目标）
function getFocusableElements(container) {
  const selector = [
    'button:not([disabled])',
    'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    'a[href]',
    '[tabindex]:not([tabindex="-1"])'
  ].join(', ')
  return Array.from(container.querySelectorAll(selector)).filter(
    (el) => el.offsetParent !== null || el.getClientRects().length > 0
  )
}

// 全局键盘事件处理
function handleGlobalKeydown(event) {
  const isModifierPressed = event.ctrlKey || event.metaKey

  // ===== 弹窗焦点陷阱：Tab/Shift+Tab 在弹窗内循环，不跳出到背后页面 =====
  if (event.key === 'Tab') {
    const overlay = getActiveOverlay()
    if (overlay) {
      // 记录弹窗打开前的焦点（供关闭后恢复）；若焦点已在弹窗内则不重复记录
      if (!overlayReturnFocusEl && !overlay.contains(document.activeElement)) {
        overlayReturnFocusEl = document.activeElement
      }
      const focusables = getFocusableElements(overlay)
      if (focusables.length) {
        const first = focusables[0]
        const last = focusables[focusables.length - 1]
        const active = document.activeElement
        if (event.shiftKey) {
          // Shift+Tab：从第一个（或弹窗外的焦点）回绕到最后一个
          if (active === first || !overlay.contains(active)) {
            event.preventDefault()
            last.focus()
          }
        } else {
          // Tab：从最后一个（或弹窗外的焦点）回绕到第一个
          if (active === last || !overlay.contains(active)) {
            event.preventDefault()
            first.focus()
          }
        }
      }
      return
    }
  }

  // ===== 空格 Leader 按键序列（优先于其他所有分支）=====
  if (spaceSeq.value.active) {
    // ESC 中断序列
    if (event.key === 'Escape') {
      event.preventDefault()
      exitSpaceSeq()
      return
    }
    // 空格再次按下：重置到第一级（重新选择领域）
    if (event.code === 'Space') {
      event.preventDefault()
      spaceSeq.value = { active: true, path: [] }
      return
    }
    // 无修饰键字母：推进序列
    if (!event.ctrlKey && !event.altKey && !event.metaKey && /^[a-z]$/i.test(event.key)) {
      const key = event.key.toLowerCase()
      const path = spaceSeq.value.path
      if (path.length === 0) {
        // 第一级：选择领域
        if (SPACE_COMMANDS[key]) {
          event.preventDefault()
          spaceSeq.value = { active: true, path: [key] }
        } else {
          exitSpaceSeq()
        }
      } else {
        // 第二级：选择动作
        const group = SPACE_COMMANDS[path[0]]
        const leaf = group?.children?.[key]
        if (leaf) {
          const action = actionDefs.find(a => a.id === leaf.actionId)
          exitSpaceSeq()
          event.preventDefault()
          if (action && typeof action.run === 'function') {
            onCommandRun(action)
          }
        } else {
          exitSpaceSeq()
        }
      }
      return
    }
    // 其他键（含修饰键组合）：退出序列并继续正常流程
    exitSpaceSeq()
  }

  // 进入空格序列：空格键（无修饰键、焦点不在输入框/编辑器/终端）
  if (event.code === 'Space' && !event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey) {
    if (isEditableElement(event.target) || isMonacoEditorFocused() || isTerminalFocused()) return
    event.preventDefault()
    enterSpaceSeq()
    return
  }

  // Ctrl/Cmd + P：编辑器聚焦时让位给 Monaco（其内置命令面板 editor.action.quickCommand 由
  // 我们额外绑定的 Ctrl+P addAction 触发）；否则打开 Jarvis 命令面板（登录界面不响应）
  // 排除 Shift：Ctrl+Shift+P 走下方「文件名搜索」分支（open-editor-file-search）
  if (isModifierPressed && !event.altKey && !event.shiftKey && event.code === 'KeyP') {
    if (showConnectModal.value) return
    // 编辑器聚焦时让位，让事件继续传播到 Monaco 触发其命令面板 addAction
    if (isMonacoEditorFocused()) return
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

  // Ctrl/Cmd + A 打开命令面板并直接展示 Agent 列表（预输入 a>）
  // 注意：Ctrl+A 是「全选」的通用快捷键，焦点在 Monaco 编辑器或输入框时须让位，
  // 否则会把编辑器/输入框的全选行为吃掉。
  // 例外：编辑器已按 ESC「脱离」快捷键控制（editorShortcutLocked）时不再让位，
  // 让 Ctrl+A 触发命令面板，而不是在编辑器里全选。
  // 普通输入框（textarea/input/contentEditable）无条件让位：即使 editorShortcutLocked
  // 为 true（曾按 ESC 脱离编辑器），进入输入框后 Ctrl+A 仍应恢复为原生全选。
  // 排除 Shift：Ctrl+Shift+A 不触发本分支（避免误拦截）
  if (isModifierPressed && !event.altKey && !event.shiftKey && event.code === 'KeyA') {
    if (showConnectModal.value) return
    if (isEditableElement(event.target) || (!editorShortcutLocked.value && isMonacoEditorFocused())) return
    event.preventDefault()
    commandPaletteFocusKey = getFocusedZoneKey()
    commandPaletteInitialQuery.value = 'a>'
    showCommandPalette.value = true
    return
  }

  // Ctrl/Cmd + F 打开命令面板并直接进入文件搜索（预输入 f>）
  // 注意：Ctrl+F 是「查找」的通用快捷键，焦点在 Monaco 编辑器或输入框时须让位，
  // 否则会把编辑器/输入框的原生查找行为吃掉。
  // 例外：编辑器已按 ESC「脱离」快捷键控制（editorShortcutLocked）时不再让位。
  // 普通输入框（textarea/input/contentEditable）无条件让位：即使 editorShortcutLocked
  // 为 true（曾按 ESC 脱离编辑器），进入输入框后 Ctrl+F 仍应恢复为原生查找。
  // 排除 Shift：Ctrl+Shift+F 走下方「内容搜索」分支（open-editor-global-search）
  if (isModifierPressed && !event.altKey && !event.shiftKey && event.code === 'KeyF') {
    if (showConnectModal.value) return
    if (isEditableElement(event.target) || (!editorShortcutLocked.value && isMonacoEditorFocused())) return
    event.preventDefault()
    commandPaletteFocusKey = getFocusedZoneKey()
    commandPaletteInitialQuery.value = 'f>'
    showCommandPalette.value = true
    return
  }

  // Ctrl/Cmd + Alt + Shift + 方向键：在大厅中按方向选中节点（相对当前选中节点的位置，
  // 无选中时从该方向的反向边缘开始，如 → 取最左侧的第一个节点）。
  // 与节点操作快捷键（Ctrl+Alt+Shift+字母）保持一致的「加 Shift 即作用于节点」约定。
  if (event.ctrlKey && event.altKey && event.shiftKey &&
      (event.key === 'ArrowLeft' || event.key === 'ArrowRight' || event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
    // 编辑器聚焦时让位给 Monaco 原生键位（Ctrl+Alt+↑/↓ 为插入光标，Shift 变体为选区变体）
    if (isMonacoEditorFocused()) return
    event.preventDefault()
    showCommandPalette.value = false
    const dirMap = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' }
    const lobby = petLobbyRef.value
    if (lobby && typeof lobby.selectNodeInDirection === 'function' && lobby.selectNodeInDirection(dirMap[event.key])) {
      return
    }
    return
  }

  // Ctrl/Cmd + Alt + 方向键：优先在大厅中按方向选中 Agent（相对当前选中宠物的位置，
  // 无选中时从该方向最靠边的一只开始）；大厅无宠物时回退为区域级焦点跳转
  // （Session Panel / 集成终端 / 编辑器）。使用 Ctrl+Alt 组合，避免与输入框/其它控件的方向键行为冲突
  if (event.ctrlKey && event.altKey && !event.shiftKey &&
      (event.key === 'ArrowLeft' || event.key === 'ArrowRight' || event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
    const dirMap = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' }
    const dir = dirMap[event.key]
    // 编辑器聚焦时让位给 Monaco 的 addAction（Ctrl+Alt+←/→ 为「上一次/下一次编辑位置」跳转，
    // Ctrl+Alt+↑/↓ 为「在上/下方插入光标」多光标编辑）。左右方向键在只读模式下同样让位，
    // 保证编辑位置跳转始终可用；上下方向键仅在可编辑模式让位（只读时多光标本就不生效，继续切 pane）。
    if (isMonacoEditorFocused()) {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') return
      if (isWorkspaceEditable.value) return
    }
    event.preventDefault()
    showCommandPalette.value = false
    const inWorkspace = getFocusedZoneKey() === 'workspace' || getNamedPanelFocusKey() === 'workspace'
    // 工作区：切换激活的分割区域（pane）
    if (inWorkspace && showWorkspacePanel.value) {
      if (moveActivePaneInDirection(dir)) return
      return
    }
    // 大厅：切换 Agent
    const lobby = petLobbyRef.value
    if (lobby && typeof lobby.selectAgentInDirection === 'function' && lobby.selectAgentInDirection(dir)) {
      return
    }
    moveFocusInDirection(dir)
    return
  }

  // Ctrl/Cmd + S 保存当前编辑器标签
  // 仅当焦点确实落在编辑器工作区（含 Monaco 编辑器 / 标签栏 / 侧边栏）时才保存；
  // 否则不拦截，避免在前端主界面误触发「文件已保存」提示。
  if (isModifierPressed && !event.altKey && event.key === 's') {
    if (getFocusedZoneKey() === 'workspace' &&
        showWorkspacePanel.value && activeWorkspaceTab.value && !activeWorkspaceTab.value.loading) {
      event.preventDefault()
      saveActiveWorkspaceTab()
    }
    return
  }

  // Ctrl/Cmd + Shift + F 快速抵达编辑器侧边栏的「内容搜索」（编辑器未打开时不响应）
  if (isModifierPressed && !event.altKey && event.shiftKey && event.code === 'KeyF') {
    if (!showWorkspacePanel.value) return
    // 输入框内保留默认行为（避免打断输入）；编辑器内例外——允许在编辑器里选中文字后直接搜索
    if (isEditableElement(event.target) && !isMonacoEditorFocused()) return
    event.preventDefault()
    openWorkspaceGlobalSearch('content')
    return
  }

  // Ctrl/Cmd + Shift + P 快速抵达编辑器侧边栏的「文件名搜索」（编辑器未打开时不响应）
  if (isModifierPressed && !event.altKey && event.shiftKey && event.code === 'KeyP') {
    if (!showWorkspacePanel.value) return
    // 输入框内保留默认行为（避免打断输入）；编辑器内例外——允许在编辑器里选中文字后直接搜索
    if (isEditableElement(event.target) && !isMonacoEditorFocused()) return
    event.preventDefault()
    openWorkspaceGlobalSearch('filename')
    return
  }

  // Ctrl/Cmd + Shift + E 快速抵达编辑器侧边栏的目录树（编辑器未打开时不响应）
  if (isModifierPressed && !event.altKey && event.shiftKey && event.code === 'KeyE') {
    if (!showWorkspacePanel.value) return
    // 输入框内保留默认行为（避免打断输入）
    if (isEditableElement(event.target)) return
    event.preventDefault()
    setWorkspaceSidebarView('files')
    focusFileTreeContainer()
    return
  }

  // Ctrl/Cmd + E 打开/隐藏编辑器面板
  if (isModifierPressed && !event.altKey && !event.shiftKey && event.code === 'KeyE') {
    event.preventDefault()
    if (showWorkspacePanel.value) {
      closeWorkspacePanel()
    } else {
      showWorkspacePanel.value = true
    }
    return
  }

  // Ctrl/Cmd + L 打开命令面板并直接展示 Agent 列表（预输入 a>）
  // 与 registry 的 open-agent-list（Ctrl+L）保持一致；浏览器默认聚焦地址栏需拦截
  if (isModifierPressed && !event.altKey && !event.shiftKey && event.code === 'KeyL') {
    if (showConnectModal.value) return
    // 输入框内保留默认行为（避免打断输入）
    if (isEditableElement(event.target)) return
    event.preventDefault()
    commandPaletteFocusKey = getFocusedZoneKey()
    commandPaletteInitialQuery.value = 'a>'
    showCommandPalette.value = true
    return
  }
  // Ctrl/Cmd + N 打开创建 Agent 弹窗（拦截浏览器新建窗口）
  if (isModifierPressed && !event.altKey && !event.shiftKey && event.code === 'KeyN') {
    // 登录界面不响应
    if (showConnectModal.value) return
    // 输入框内保留默认行为（避免打断输入）
    if (isEditableElement(event.target)) return
    event.preventDefault()
    openCreateAgentModal()
    return
  }

  // Ctrl + ` 打开/隐藏终端面板
  if (event.ctrlKey && !event.altKey && event.key === '`') {
    event.preventDefault()
    if (socket.value) {
      toggleTerminalPanel()
    }
  }



  // Ctrl + Alt + Enter 发送缓冲区内容（当缓冲区有内容时生效）
  if (event.ctrlKey && event.altKey && event.key === 'Enter') {
    if (hasBufferedInput.value) {
      event.preventDefault()
      sendBufferedInput()
    }
  }

  // F2 重命名：同一物理键在不同场景下复用，按 registry 的 shortcutScope 分派
  // - global 场景：重命名当前 Agent（优先级高于节点）
  // - node 场景：无当前 Agent 时，大厅中选中节点则重命名该节点
  // 已打开 Agent 重命名弹窗时不重复触发
  if (event.key === 'F2') {
    if (showRenameAgentModal.value) return
    // 编辑器聚焦时让位给 Monaco 的「重命名符号」（F2）
    if (isMonacoEditorFocused()) return
    const agent = getCurrentAgentOrNull()
    if (agent) {
      event.preventDefault()
      renameAgent(agent)
      return
    }
    const lobby = petLobbyRef.value
    if (lobby && typeof lobby.renameActiveNode === 'function' && lobby.renameActiveNode()) {
      event.preventDefault()
    }
    return
  }

  // Delete 删除宠物大厅中选中的 Agent（需二次确认）
  // 仅在宠物大厅有选中宠物、且焦点不在可编辑元素时生效，避免影响正常的删除字符操作
  if (event.key === 'Delete' && !isModifierPressed && !event.altKey && !event.shiftKey) {
    if (!isEditableElement(event.target) && lobbyActiveAgentId.value) {
      const agent = agentList.value.find(a => a.agent_id === lobbyActiveAgentId.value)
      if (agent) {
        event.preventDefault()
        deleteAgent(agent.agent_id)
        return
      }
    }
  }

  // Ctrl/Cmd + \ 左右分割当前激活 pane；Ctrl/Cmd + - 上下分割
  // 只要工作区打开（不再限定编辑器 file 视图）且非移动端即生效；未分割时先分割激活 pane。
  // 上下分割改用 Ctrl+-（替代原 Ctrl+Shift+\，避免与 Monaco「跳转到匹配括号」冲突；
  // 同时覆盖 Monaco 的 Ctrl+- 缩小字号，用户不需要缩放）。
  if (isModifierPressed && !event.altKey && !event.shiftKey && event.code === 'Backslash') {
    if (showWorkspacePanel.value && windowWidth.value > 768) {
      event.preventDefault()
      splitWorkspacePane(activePaneId.value, 'row')
      return
    }
  }
  // Ctrl/Cmd + - 上下分割（主键盘减号 Minus / 小键盘减号 NumpadSubtract）
  if (isModifierPressed && !event.altKey && !event.shiftKey &&
      (event.code === 'Minus' || event.code === 'NumpadSubtract')) {
    if (showWorkspacePanel.value && windowWidth.value > 768) {
      event.preventDefault()
      splitWorkspacePane(activePaneId.value, 'column')
      return
    }
  }

  // Ctrl/Cmd + W 关闭当前焦点所在的面板（需拦截浏览器原生关闭标签页行为）
  // 焦点在面板内（终端/编辑器/聊天/会话面板）时优先关闭该面板；
  // 焦点不在任何面板内（即处于宠物大厅）且有激活宠物时，改为「隐藏该 Agent 输出并取消选中」
  // 排除 Shift：Ctrl+Shift+W 不触发本分支（避免误拦截浏览器/其它行为）
  if (isModifierPressed && !event.altKey && !event.shiftKey && event.code === 'KeyW') {
    event.preventDefault()
    // 编辑器处于分割态且焦点在编辑器工作区内：Ctrl+W 优先关闭「激活 pane 的文件」
    // （VS Code 语义）；无文件则关闭该 pane。未分割态由 closeFocusedPanel 统一处理。
    if (workspacePaneCount.value > 1 && workspaceMainView.value === 'file' && windowWidth.value > 768) {
      const editorZone = getFocusedZoneKey()
      const namedKey = getNamedPanelFocusKey()
      if (editorZone === 'workspace' || namedKey === 'workspace') {
        if (handleWorkspaceCloseShortcut()) return
        closeFocusedPanel()
        return
      }
    }
    // 命名面板（terminal/workspace/chat）内：即使焦点未落在可聚焦元素上（仅鼠标点击过面板），
    // 也应关闭该面板，而不是被大厅逻辑拦截
    if (!getFocusedZoneKey() && !getNamedPanelFocusKey()) {
      const lobby = petLobbyRef.value
      if (lobby && typeof lobby.hideActiveOutputAndClose === 'function' && lobby.hideActiveOutputAndClose()) {
        return
      }
    }
    closeFocusedPanel()
    return
  }

  // ESC 键关闭所有对话框
  if (event.key === 'Escape') {
    // Panel 右键菜单打开时优先关闭它
    if (panelContextMenu.value.visible) {
      closePanelContextMenu()
      return
    }
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
    // 管理面板打开时优先关闭它
    if (showAdminPanel.value) {
      showAdminPanel.value = false
      return
    }
    // 关于弹窗打开时优先关闭它
    if (showAboutModal.value) {
      showAboutModal.value = false
      return
    }
    // 弹出面板（diff/rules/tools/缓存/重命名/权限管理）：Esc 关闭
    if (showDiffModal.value) {
      // 移动端详情态：Esc 先退回文件列表，再按一次才关闭弹窗
      if (diffMobileShowDetail.value) {
        diffMobileShowDetail.value = false
        return
      }
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
    } else if (showQuickCreateAgentModal.value) {
      showQuickCreateAgentModal.value = false
    } else if (showSessionDialog.value) {
      cancelSessionDialog()
    } else if (showDirDialog.value) {
      cancelDirDialog()
    } else if (showOpenDirDialog.value) {
      closeOpenDirDialog()
    }
    
    // ESC 键也关闭移动端菜单
    if (showMobileMenu.value) {
      showMobileMenu.value = false
    }
    
    // ESC 键也关闭终端面板（移动端）
    if (showTerminalPanel.value && windowWidth.value <= 768) {
      showTerminalPanel.value = false
    }

    // 最低优先级：退出宠物大厅中已选中的宠物（无选中时不做任何事）
    if (petLobbyRef.value && typeof petLobbyRef.value.closeActivePanel === 'function') {
      petLobbyRef.value.closeActivePanel()
    }

    // 有 pane 处于临时最大化时，Esc 还原回原布局
    if (maximizedPaneId.value) {
      maximizedPaneId.value = null
      nextTick(() => {
        remountMonacoEditor()
        layoutGitDiffEditor()
      })
      return
    }

    // 焦点在 Monaco 编辑器或可编辑输入框（无对话框/菜单需要关闭）时，按 ESC 移除焦点，
    // 让编辑器/输入框「脱离」快捷键控制：之后 Ctrl+A 不再被全选/输入框吃掉，
    // 而是触发命令面板（列出 Agent）。
    // - Monaco 编辑器：置 editorShortcutLocked 兜底（其隐藏 textarea blur 后 isMonacoEditorFocused
    //   可能仍为 true），重新聚焦编辑器时自动恢复（见 bindWorkspaceViewEvents 的 onDidFocusEditorText）。
    // - 普通输入框（textarea/input/contentEditable）：直接 blur，焦点移出后 event.target 即不再是输入框。
    const ae = document.activeElement
    if (isMonacoEditorFocused()) {
      editorShortcutLocked.value = true
      if (ae && typeof ae.blur === 'function') ae.blur()
    } else if (ae && isEditableElement(ae)) {
      if (typeof ae.blur === 'function') ae.blur()
    }
  }

  // 注册表快捷键统一分发：命中 registry 中带 shortcut 的动作则执行
  // 登录界面不响应；Ctrl+Alt 组合在输入框内也生效（不与输入框原生编辑冲突），
  // 仅登录界面与未启用动作被跳过
  if ((event.ctrlKey || event.metaKey) && event.altKey) {
    if (showConnectModal.value) return
    const matched = actionDefs.find(a => a.shortcut && matchShortcut(a.shortcut, event))
    if (matched) {
      const ctx = commandPaletteCtx.value
      const isEnabled = typeof matched.enabled === 'function' ? matched.enabled(ctx) : true
      if (isEnabled) {
        event.preventDefault()
        onCommandRun(matched)
      }
      return
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
  // tabindex="-1" 的控件（如区域分割/关闭、标题栏按钮）刻意不参与焦点导航，
  // 聚焦兜底时也应跳过，避免焦点落到这些"不抢焦点"的按钮上
  if (el.getAttribute && el.getAttribute('tabindex') === '-1') return false
  return true
}

// 在区域内查找首个可聚焦元素并聚焦；找不到则回退聚焦容器
function focusFirstIn(el, selector) {
  if (!el) return
  const defaultSel = 'textarea, input, [contenteditable="true"], button:not([disabled]):not([tabindex="-1"]), [tabindex]:not([tabindex="-1"])'
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
  if (showTerminalPanel.value) {
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
  if (showWorkspacePanel.value) {
    zones.push({
      key: 'workspace',
      kind: 'workspace',
      focus: () => {
        focusWindow('workspace')
        nextTick(() => {
          const view = getActiveWorkspaceView()
          if (view) {
            view.focus()
            return
          }
          // 无编辑器内容时，回退聚焦编辑器内首个可聚焦控件（如活动栏按钮），
          // 避免聚焦到不可交互的容器后被框架重置焦点
          focusFirstIn(document.querySelector('.workspace-panel'))
        })
      },
    })
  }
  if (showChatPanel.value) {
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
  const workspaceEl = document.querySelector('.workspace-panel')
  if (workspaceEl && workspaceEl.contains(el)) return 'workspace'
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
  if (activeWindow.value === 'terminal' && showTerminalPanel.value) {
    return 'terminal'
  }
  if (activeWindow.value === 'workspace' && showWorkspacePanel.value) {
    return 'workspace'
  }
  if (activeWindow.value === 'chat' && showChatPanel.value) {
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
  } else if (zone.kind === 'workspace') {
    el = document.querySelector('.workspace-panel')
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

// 移动端：打开浮层时推送历史状态
const pushOverlayState = () => {
  if (windowWidth.value <= 768) {
    window.history.pushState({ overlay: true }, '', '')
    historyStateCount++
  }
}

// 打开编辑器面板并切到「Agent 列表」视图（原全局 Agent 侧边栏的唯一入口）
const openWorkspaceAgentList = () => {
  if (!showWorkspacePanel.value) {
    showWorkspacePanel.value = true
    if (windowWidth.value <= 768) {
      pushOverlayState()
    }
  }
  setWorkspaceSidebarView('agents')
}

// 打开/关闭终端面板（移动端处理history）
const toggleTerminalPanel = () => {
  // 工作区正在显示终端时，语义为「收起」：切回文件视图
  if (workspaceHostsTerminal.value) {
    setWorkspaceMainView('file')
    return
  }
  showWorkspaceHostView('terminal')
}
// 打开/关闭编辑器面板（移动端处理history；不依赖当前 Agent，与 Ctrl+E 行为一致）
const toggleWorkspacePanel = () => {
  if (showWorkspacePanel.value) {
    closeWorkspacePanel()
    return
  }
  showWorkspacePanel.value = true
  if (windowWidth.value <= 768) {
    pushOverlayState()
  }
}

watch(showWorkspacePanel, async (visible) => {
  if (visible) {
    ensureWorkspacePanelInViewport()
    await nextTick()
    ensureMonacoEditor()
    if (activeWorkspaceTabPath.value) {
      activateWorkspaceTab(activeWorkspaceTabPath.value)
    }
    nextTick(() => layoutMonacoEditor())
  } else {
    stopWorkspacePanelInteraction()
  }
})

watch(activeWorkspaceTabPath, async (path) => {
  if (!path) return
  await nextTick()
  ensureMonacoEditor()
  activateWorkspaceTab(path)
})


watch(
  () => auth.value.token,
  (newToken) => {
    try {
      window.postMessage({ type: 'jarvis_token_changed', token: newToken || null }, '*')
    } catch (e) {
      console.warn('[AUTH] broadcast token change failed:', e)
    }
    // 通知插件订阅者 token 变化
    __jarvisEmit('token_changed', { token: newToken || null })
    // token 变化（含登出置空）时同步给本机 daemon
    syncTokenToDaemon(newToken, window.__jarvisAuthBridge.getGateway())
  }
)

// 用户信息变化时通知插件订阅者（登录/刷新/登出统一走这里）
watch(
  () => auth.value.userInfo,
  (newUserInfo) => {
    __jarvisEmit('user_changed', { userInfo: newUserInfo || null })
  }
)

// 当前 Agent 切换时通知插件订阅者（payload 与 __jarvisGetActiveAgentInfo 结构一致）
watch(
  () => currentAgentId.value,
  (newAgentId) => {
    const agent = agentList.value.find(a => a.agent_id === newAgentId) || null
    __jarvisEmit('agent_changed', agent
      ? { agentId: agent.agent_id, agentName: agent.name || agent.agent_id, workingDir: agent.working_dir || '' }
      : null)
  }
)

// 节点列表变化时通知插件订阅者
watch(
  () => availableNodeOptions.value,
  (nodes) => {
    __jarvisEmit('nodes_changed', { nodes: Array.isArray(nodes) ? [...nodes] : [] })
  }
)

onMounted(() => {
  // 阶段4：恢复上次的编辑器分割布局（非法数据自动回退默认单 leaf）
  restoreWorkspacePaneLayout()
  // 终端名称：用户从未配置过时，用本机 daemon 上报的计算机名作为默认值
  initTerminalNameFromDaemon()
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
    // 页面加载时已有 token（loadSavedToken 回填路径不会触发 watch），补推一次给本机 daemon，
    // 保证 daemon 与页面登录态一致；失败静默，不影响连接主流程。
    syncTokenToDaemon(auth.value.token, window.__jarvisAuthBridge.getGateway())
    // 加载插件声明的前端扩展点（admin_tabs / sidebar_views / tool_panels）
    loadPluginExtensionsForUi()
  }

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

  // 接入端会话轮询（浏览器扩展 / 后台服务）：迷你拓扑常驻显示，需在挂载后即开始拉取，
  // 否则要等用户打开一次拓扑大图才会出现接入端节点。
  if (hasAuthToken()) {
    startTopologyAccessPolling()
  }

  // 本机 daemon 是否在线探测：与登录态无关（daemon 无需鉴权即可应答 /api/status），
  // 用于隐藏大厅的「安装本地后台服务」引导入口。
  startLocalDaemonProbe()
  
  // 添加滚动事件监听，实现滚动到顶部时加载更多历史
  setupHistoryScrollListener(outputList.value)
  
  // 添加全局键盘事件监听（在捕获阶段处理 Ctrl+T 等快捷键）
  document.addEventListener('keydown', handleGlobalKeydown, { capture: true })

  // 空格序列激活期间锁定焦点，防止焦点落入输入框/编辑器/终端
  document.addEventListener('focusin', handleSpaceSeqFocusIn)

  // 点击菜单外任意处关闭 Panel 右键菜单（菜单自身已 stop 冒泡）
  document.addEventListener('pointerdown', closePanelContextMenu)
  
  // 监听窗口resize事件
  handleResize = () => {
    windowWidth.value = window.innerWidth
    updateViewportHeight()
    ensureWorkspacePanelInViewport()
    ensureTerminalPanelInViewport()
    saveWorkspacePanelRect()
    saveTerminalPanelRect()
    // 已分割时每个 Monaco 实例自带 automaticLayout(ResizeObserver)，会自行跟随容器尺寸，
    // 此处不再逐个 layout()（否则 resize → layout → 尺寸变化 → 再 layout 会形成震荡）。
    if (workspacePaneCount.value <= 1) {
      layoutMonacoEditor()
    }

    const activeSession = terminalSessions.value.find(session => session.terminal_id === activeTerminalId.value)
    if (activeSession && activeSession.fitAddon && activeSession.terminal) {
      activeSession.fitAddon.fit()
      sendTerminalResize(activeSession.terminal_id, activeSession.terminal.rows, activeSession.terminal.cols)
    }
  }
  window.addEventListener('resize', handleResize)

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
      } else if (showTerminalPanel.value && windowWidth.value <= 768) {
        showTerminalPanel.value = false
      } else if (showMobileMenu.value) {
        showMobileMenu.value = false
      } else if (windowWidth.value <= 768 && !hasNoPanel.value) {
        // 移动端：关闭当前可见的 Panel，回到宠物大厅
        closeVisiblePanelsOnMobile()
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

  // 弹窗焦点恢复：弹窗出现时记录打开前焦点，弹窗从 DOM 移除（任意关闭方式）时恢复焦点
  overlayObserver = new MutationObserver(() => {
    const overlay = document.querySelector('.modal-overlay, .palette-overlay')
    if (overlay) {
      // 弹窗出现：记录打开前焦点（若焦点不在弹窗内）
      const active = document.activeElement
      if (!overlayReturnFocusEl && active && !overlay.contains(active)) {
        overlayReturnFocusEl = active
      }
    } else if (overlayReturnFocusEl) {
      // 弹窗消失：恢复焦点到打开前元素
      const target = overlayReturnFocusEl
      overlayReturnFocusEl = null
      // 目标元素仍存在且可聚焦时才恢复，避免焦点落到已销毁元素
      if (target && document.body.contains(target) && typeof target.focus === 'function') {
        target.focus()
      }
    }
  })
  overlayObserver.observe(document.body, { childList: true, subtree: true })
})

onUnmounted(() => {

  // 清理新手引导延迟展示定时器
  clearOnboardingTimer()

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
  
  stopWorkspacePanelInteraction()
  stopWorkspaceFileHeartbeat()
  // 停止接入端会话轮询
  stopTopologyAccessPolling()
  // 停止本机 daemon 在线探测
  stopLocalDaemonProbe()
  window.visualViewport?.removeEventListener('resize', visualViewportResizeHandler)

  for (const [, view] of editorViews) {
    view.dispose()
  }
  editorViews.clear()
  workspaceViewPanes.clear()
  for (const modelData of editorModels.values()) {
    if (modelData.model && !modelData.model.isDisposed()) {
      modelData.model.dispose()
    }
  }
  editorModels.clear()
  // 释放全部 LSP 连接，避免 WS 泄漏
  disposeAllLspClients()
  lspBindings.clear()

  // 移除全局键盘事件监听
  document.removeEventListener('keydown', handleGlobalKeydown, { capture: true })

  // 移除空格序列焦点锁定监听
  document.removeEventListener('focusin', handleSpaceSeqFocusIn)

  // 移除 Panel 右键菜单的全局关闭监听
  document.removeEventListener('pointerdown', closePanelContextMenu)
  
  // 移除窗口resize监听
  window.removeEventListener('resize', handleResize)

  // 移除返回键监听
  window.removeEventListener('popstate', handlePopState)

  // 断开图表渲染 MutationObserver
  if (diagramObserver) {
    diagramObserver.disconnect()
    diagramObserver = null
  }

  // 断开弹窗焦点恢复 MutationObserver
  if (overlayObserver) {
    overlayObserver.disconnect()
    overlayObserver = null
  }
  overlayReturnFocusEl = null
})


</script>

<style>
/* 全局样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

/* Agent 等待输入状态的背景高亮 */
.workspace-agent-node.waiting-input {
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

/* 目录选择弹窗从「编排」弹窗内打开时，需盖在编排弹窗（z-index:3000）之上 */
.palette-overlay.dir-dialog-above-orchestrate {
  z-index: 3100;
}

/* PWA 全屏/独立模式：内容延伸到屏幕最顶部，去掉状态栏/挖孔安全边距（实现真正全屏）。
   注意：仅在 PWA 安装模式下生效；浏览器标签页模式仍保留安全边距，避免被浏览器顶栏遮挡。
   此块必须放在全局 <style>（非 scoped）中，否则 html/body/#app 会被加上 data-v 属性而无法命中。 */
@media (display-mode: fullscreen), (display-mode: standalone) {
  /* 移动端 PWA 全屏时 --app-height 取 visualViewport.height（不含系统状态栏），
     导致 .app 高度不足、顶部状态栏/挖孔区域露出 body 深色背景形成黑边。
     这里让 html/body/#app/.app 高度补上 safe-area-inset-top，使页面覆盖到屏幕最顶部。 */
  html, body, #app, .app {
    height: calc(var(--app-height, 100vh) + env(safe-area-inset-top, 0px));
  }
  .app {
    padding-top: 0;
    padding-left: 0;
    padding-right: 0;
  }
}

</style>

<style scoped src="./styles/app-layout.css"></style>
<style scoped src="./styles/app-split-pane.css"></style>
<style scoped src="./styles/app-editor-sidebar.css"></style>
<style scoped src="./styles/app-git-view.css"></style>
<style scoped src="./styles/app-agent-window.css"></style>
<style scoped src="./styles/app-session-panel.css"></style>
<style scoped src="./styles/app-panel-grid.css"></style>
<style scoped src="./styles/app-chat.css"></style>
<style scoped src="./styles/app-terminal-input.css"></style>
<style scoped src="./styles/app-buffer-buttons.css"></style>
<style scoped src="./styles/app-modals.css"></style>
<style scoped src="./styles/app-context-menus.css"></style>
<style scoped src="./styles/app-toast.css"></style>
<style scoped src="./styles/app-responsive.css"></style>
<style scoped src="./styles/app-toggle-switch.css"></style>
<style scoped src="./styles/app-diff-rules.css"></style>
<style scoped src="./styles/app-orchestrate.css"></style>
