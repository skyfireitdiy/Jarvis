<template>
  <aside
    v-show="visible"
    class="editor-panel"
    :class="{ 'editor-panel-dragging': interaction.active }"
    :style="panelStyle"
    @mousedown="$emit('focus', 'editor')"
  >
    <div
      class="editor-panel-header"
      @mousedown="$emit('startMove', $event)"
      @dblclick.stop="$emit('toggleMaximize')"
    >
      <div class="editor-panel-title-group">
        <h3>编辑器</h3>
        <span v-if="activeTab" class="editor-panel-subtitle">{{ activeTab.path }}</span>
      </div>
      <div class="editor-panel-actions">
        <button class="icon-btn" @click.stop="$emit('save')" :disabled="!activeTab || activeTab.loading" title="保存文件">💾</button>
        <button class="icon-btn maximize-btn" @click="$emit('toggleMaximize')" :title="isMaximized ? '还原' : '最大化'">
          {{ isMaximized ? '🗗' : '🗖' }}
        </button>
        <button class="icon-btn" @click="$emit('close')" title="关闭编辑器">✕</button>
      </div>
    </div>
    <div class="editor-tabs" v-if="tabs.length > 0">
      <div
        v-for="tab in tabs"
        :key="tab.path"
        class="editor-tab"
        :class="{ active: activeTabPath === tab.path }"
        @click="$emit('activateTab', tab.path)"
      >
        <span class="editor-tab-name">{{ tab.name }}</span>
        <span v-if="tab.isDirty" class="editor-tab-dirty">●</span>
        <button class="editor-tab-close" @click.stop="$emit('closeTab', tab.path)">✕</button>
      </div>
    </div>
    <div class="editor-panel-toolbar">
      <span class="editor-toolbar-status" v-if="activeTab?.loading">加载中...</span>
      <span class="editor-toolbar-status error" v-else-if="activeTab?.error">{{ activeTab.error }}</span>
      <span class="editor-toolbar-status" v-else-if="activeTab">{{ activeTab.isDirty ? '未保存修改' : '已保存' }}</span>
      <span class="editor-toolbar-status" v-else>点击文件树中的文件打开编辑器</span>
      <div class="editor-toolbar-spacer"></div>
      <button
        v-if="tabs.length > 0"
        class="editor-edit-toggle"
        :class="{ 'editable': isEditable }"
        @click="$emit('toggleEditable')"
        :title="isEditable ? '切换到只读模式' : '切换到编辑模式'"
      >
        <span class="editor-edit-toggle-icon">{{ isEditable ? '🔓' : '🔒' }}</span>
        <span class="editor-edit-toggle-text">{{ isEditable ? '可编辑' : '只读' }}</span>
      </button>
    </div>
    <div class="editor-workspace">
      <div class="editor-activity-bar">
        <button
          class="editor-activity-button"
          :class="{ active: showSidebar && sidebarView === 'files' }"
          @click="$emit('setSidebarView', 'files')"
          title="目录树"
        >📁</button>
        <button
          class="editor-activity-button"
          :class="{ active: showSidebar && sidebarView === 'search' }"
          @click="$emit('setSidebarView', 'search')"
          title="全局搜索"
        >🔎</button>
      </div>
      <aside v-if="showSidebar" class="editor-sidebar">
        <div class="editor-sidebar-header">
          <span class="editor-sidebar-title">{{ sidebarView === 'search' ? '全局搜索' : '目录树' }}</span>
          <button class="icon-btn-small" @click="$emit('closeSidebar')" title="关闭侧边栏">✕</button>
        </div>
        <div v-if="sidebarView === 'files'" class="editor-sidebar-content">
          <div v-if="currentAgent" class="editor-file-tree-panel">
            <div class="editor-file-tree-root" @click.stop="$emit('ensureFileTree', currentAgent)">
              {{ currentAgent.working_dir }}
            </div>
            <div v-if="!hasFileTree" class="editor-file-tree-empty">
              当前工作目录下暂无可显示内容
            </div>
            <div v-else class="editor-file-tree-list">
              <div
                v-for="visibleNode in getVisibleNodes(currentAgent.agent_id)"
                :key="visibleNode.node.path"
                class="tree-node editor-tree-node"
              >
                <div
                  class="tree-node-content"
                  :style="{ paddingLeft: `${8 + visibleNode.depth * 20}px` }"
                  @click.stop="$emit('fileNodeClick', currentAgent.agent_id, visibleNode.node)"
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
              :value="searchQuery"
              @input="$emit('update:searchQuery', $event.target.value)"
              class="editor-global-search-input"
              type="text"
              placeholder="全局搜索文件内容..."
              :disabled="searchLoading || !currentAgentId"
              @keydown.enter.prevent="$emit('runSearch')"
            >
            <input
              :value="searchFileGlob"
              @input="$emit('update:searchFileGlob', $event.target.value)"
              class="editor-global-search-input editor-global-search-glob-input"
              type="text"
              placeholder="文件过滤，如 *.py,!tests/**"
              :disabled="searchLoading || !currentAgentId"
              @keydown.enter.prevent="$emit('runSearch')"
            >
            <div class="editor-global-search-toolbar">
              <label class="editor-global-search-toggle">
                <input :value="searchCaseSensitive" @change="$emit('update:searchCaseSensitive', $event.target.checked)" type="checkbox">
                <span>区分大小写</span>
              </label>
              <label class="editor-global-search-toggle">
                <input :value="searchWholeWord" @change="$emit('update:searchWholeWord', $event.target.checked)" type="checkbox">
                <span>全词匹配</span>
              </label>
              <div class="editor-global-search-actions">
                <button class="icon-btn editor-global-search-btn" @click="$emit('runSearch')" :disabled="searchLoading || !currentAgentId || !searchQuery?.trim()" title="全局搜索">🔍</button>
                <button class="icon-btn editor-global-search-btn" @click="$emit('clearSearch')" :disabled="searchLoading" title="清空搜索">✕</button>
              </div>
            </div>
          </div>
          <div class="editor-global-search-results">
            <div class="editor-global-search-summary">
              <span v-if="searchLoading">搜索中...</span>
              <span v-else-if="searchError" class="error">{{ searchError }}</span>
              <span v-else-if="searchExecuted">找到 {{ searchTotalMatches }} 处匹配，分布在 {{ searchTotalFiles }} 个文件</span>
              <span v-else>输入关键词并回车，可在当前 Agent 工作目录中全局搜索</span>
            </div>
            <div v-if="!searchLoading && searchExecuted && searchResults.length === 0 && !searchError" class="editor-global-search-empty">
              未找到匹配结果
            </div>
            <div v-for="result in searchResults" :key="result.file_path" class="editor-global-search-file-group">
              <div class="editor-global-search-file-path" @click="$emit('openFile', resolvePath(result.file_path))">
                {{ result.file_path }}
                <span class="editor-global-search-file-count">({{ result.matches.length }})</span>
              </div>
              <button
                v-for="match in result.matches"
                :key="`${result.file_path}:${match.line_number}:${match.match_start}`"
                class="editor-global-search-match"
                @click="$emit('openSearchResult', result.file_path, match.line_number, match.match_start, match.match_end)"
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
        <div v-if="tabs.length === 0" class="editor-placeholder">
          <div class="editor-placeholder-icon">📝</div>
          <div class="editor-placeholder-title">点击文件树中的文件打开代码编辑器</div>
          <div class="editor-placeholder-text">支持 Monaco 语法高亮、代码折叠、多标签切换与保存。</div>
        </div>
        <div v-else ref="containerRef" class="editor-monaco-container"></div>
      </div>
    </div>
    <div
      v-for="direction in resizeDirections"
      :key="direction"
      :class="['editor-resize-handle', `editor-resize-${direction}`]"
      @mousedown="$emit('startResize', $event, direction)"
    ></div>
  </aside>
</template>

<script setup>
import { defineProps, defineEmits, ref } from 'vue'

const props = defineProps({
  visible: Boolean,
  interaction: Object,
  panelStyle: Object,
  activeTab: Object,
  activeTabPath: String,
  tabs: Array,
  isMaximized: Boolean,
  isEditable: Boolean,
  showSidebar: Boolean,
  sidebarView: String,
  currentAgent: Object,
  currentAgentId: String,
  hasFileTree: Boolean,
  getVisibleNodes: Function,
  resolvePath: Function,
  searchQuery: String,
  searchFileGlob: String,
  searchCaseSensitive: Boolean,
  searchWholeWord: Boolean,
  searchLoading: Boolean,
  searchError: String,
  searchExecuted: Boolean,
  searchTotalMatches: Number,
  searchTotalFiles: Number,
  searchResults: Array,
  resizeDirections: Array
})

const emit = defineEmits([
  'focus',
  'startMove',
  'toggleMaximize',
  'save',
  'close',
  'activateTab',
  'closeTab',
  'toggleEditable',
  'setSidebarView',
  'closeSidebar',
  'ensureFileTree',
  'fileNodeClick',
  'update:searchQuery',
  'update:searchFileGlob',
  'update:searchCaseSensitive',
  'update:searchWholeWord',
  'runSearch',
  'clearSearch',
  'openFile',
  'openSearchResult',
  'startResize'
])

const containerRef = ref(null)

defineExpose({ containerRef })
</script>

<style scoped>
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

.icon-btn-small:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(13, 17, 23, 0.9);
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
  gap: 8px;
  min-height: 30px;
  padding: 0 10px;
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
