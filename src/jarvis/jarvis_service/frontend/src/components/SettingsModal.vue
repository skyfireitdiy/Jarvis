<template>
  <!-- 设置弹窗 -->
  <div class="modal-overlay" v-if="visible">
    <div class="modal settings-modal">
      <div class="modal-header">
        <h2>设置</h2>
        <button class="close-btn" @click="close">×</button>
      </div>
      <!-- 连接设置组件 -->
      <ConnectionSettings
        :connection-lock-enabled="connectionLockEnabled"
        :auto-login-enabled="autoLoginEnabled"
        @update:connection-lock-enabled="val => emit('update:connectionLockEnabled', val)"
        @save-connection-lock-setting="emit('saveConnectionLockSetting')"
        @update:auto-login-enabled="val => emit('update:autoLoginEnabled', val)"
        @save-auto-login-setting="emit('saveAutoLoginSetting')"
      />

      <!-- 历史消息管理组件 -->
      <HistorySettings
        :history-storage="historyStorage"
        @confirm-clear-history="emit('confirmClearHistory')"
      />
      <div class="form-group" v-if="availableNodeOptions.length > 0">
        <label>重启节点服务</label>
        <select v-model="localRestartNodeId" class="node-select">
          <option value="">本节点 (master)</option>
          <option v-for="node in availableNodeOptions" :key="node.node_id" :value="node.node_id">
            {{ formatNodeOptionLabel(node) }}
          </option>
        </select>
        <span class="form-help">选择要重启服务的节点，默认为本节点</span>
      </div>

      <div class="form-group" v-if="!localRestartNodeId || localRestartNodeId === 'master'">
        <label class="checkbox-label">
          <input type="checkbox" v-model="localRestartFrontendService" />
          <span>同时重启前端服务</span>
        </label>
        <span class="form-help">前端服务重启时间较长，通常只需重启后端</span>
      </div>
      <div class="form-group">
        <button class="ghost-btn" @click="confirmRestartGateway" :disabled="isRestartingGateway">
          {{ isRestartingGateway ? '请稍候...' : (localRestartNodeId ? `重启节点 ${localRestartNodeId} 服务` : '重启本节点服务') }}
        </button>
      </div>

      <!-- 代码更新 -->
      <div class="form-group">
        <label>代码更新</label>
        <span class="form-help">将所有节点的 Jarvis 代码切换到 main 分支并拉取最新代码</span>
        <button class="ghost-btn" @click="updateCodeToMain" :disabled="isUpdatingCode">
          {{ isUpdatingCode ? '更新中...' : '更新代码到 main 分支' }}
        </button>
      </div>

      <!-- 节点认证组件 -->
      <NodeSecretSettings
        :get-token="getToken"
        :gateway-url="gatewayUrl"
        :show-toast="showToast"
      />

      <!-- 连接管理 -->
      <div class="form-group">
        <label>连接管理</label>
        <div class="connection-management-section">
          <button class="danger-btn" @click="disconnectAll" :disabled="!socket">
            断开连接
          </button>
          <span class="form-help">断开所有 WebSocket 连接并刷新页面</span>
        </div>
      </div>

      <!-- 配置同步 -->
      <div class="form-group" v-if="availableNodeOptions.length > 0">
        <label>配置同步</label>
        <div class="config-sync-section">
          <div class="config-sync-row">
            <span class="config-sync-label">源节点:</span>
            <select v-model="localSyncConfigSourceNode" class="node-select">
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
        <button class="ghost-btn" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import ConnectionSettings from './settings/ConnectionSettings.vue'
import NodeSecretSettings from './settings/NodeSecretSettings.vue'
import HistorySettings from './settings/HistorySettings.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  connectionLockEnabled: {
    type: Boolean,
    default: false
  },
  historyStorage: {
    type: Object,
    required: true
  },
  availableNodeOptions: {
    type: Array,
    default: () => []
  },
  socket: {
    type: Object,
    default: null
  },
  isRestartingGateway: {
    type: Boolean,
    default: false
  },
  isSyncingConfig: {
    type: Boolean,
    default: false
  },
  isUpdatingCode: {
    type: Boolean,
    default: false
  },
  autoLoginEnabled: {
    type: Boolean,
    default: false
  },
  getToken: {
    type: Function,
    required: true
  },
  gatewayUrl: {
    type: String,
    default: '127.0.0.1:8000'
  },
  showToast: {
    type: Function,
    default: () => {}
  }
})

const emit = defineEmits([
  'update:visible',
  'update:connectionLockEnabled',
  'saveConnectionLockSetting',
  'confirmClearHistory',
  'confirmRestartGateway',
  'disconnectAll',
  'syncConfig',
  'update:autoLoginEnabled',
  'saveAutoLoginSetting',
  'updateCodeToMain',
  'confirmUpdateCodeToMain'
])

// 本地状态
const localRestartNodeId = ref('')
const localRestartFrontendService = ref(false)
const localSyncConfigSourceNode = ref('')

// 关闭弹窗
function close() {
  emit('update:visible', false)
}

// 格式化节点选项标签
function formatNodeOptionLabel(node) {
  const nodeId = String(node?.node_id || '').trim()
  const status = String(node?.status || node?.runtime_status || '').trim()
  return status ? `${nodeId} (${status})` : nodeId
}

// 确认清除历史
function confirmClearHistory() {
  emit('confirmClearHistory')
}

// 确认重启网关
function confirmRestartGateway() {
  emit('confirmRestartGateway', {
    nodeId: localRestartNodeId.value,
    restartFrontend: localRestartFrontendService.value
  })
}

// 断开所有连接
function disconnectAll() {
  emit('disconnectAll')
}

// 同步配置
function syncConfig() {
  emit('syncConfig', {
    sourceNodeId: localSyncConfigSourceNode.value
  })
}

// 更新代码到 main 分支
function updateCodeToMain() {
  emit('confirmUpdateCodeToMain')
}


</script>

<style scoped>

/* 模态框遮罩层 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

/* 模态框基础样式 */
.modal-overlay .modal {
  background: var(--color-bg-secondary);
  border: 0.5px solid var(--color-border);
  border-radius: 14px;
  padding: 28px;
}

/* ========== Form Group 样式（从 App.vue 全局样式迁移） ========== */
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
  color: var(--color-text-secondary);
  letter-spacing: 0.01em;
}

.form-group input {
  width: 100%;
  padding: 11px 14px;
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border);
  border-radius: 9px;
  color: var(--color-text-primary);
  font-size: 14px;
}

.form-group input:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-primary);
}

.form-group select {
  width: 100%;
  padding: 11px 14px;
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border);
  border-radius: 9px;
  color: var(--color-text-primary);
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
  background-color: var(--color-bg-primary);
}

.form-group select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  padding: 8px;
}

/* ========== Toggle Switch 样式（从 App.vue 全局样式迁移） ========== */
.toggle-wrapper {
  display: flex !important;
  align-items: center !important;
  justify-content: flex-start;
  gap: 16px;
  padding: 16px 20px;
  background: var(--color-bg-secondary);
  backdrop-filter: blur(40px) saturate(150%);
  -webkit-backdrop-filter: blur(40px) saturate(150%);
  border: 1px solid var(--color-border);
  outline: 1px solid var(--color-border);
  outline-offset: -1px;
  border-radius: 16px;
  box-shadow: 0 4px 12px var(--color-shadow), inset 0 1px 0 var(--color-border);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toggle-wrapper:hover {
  backdrop-filter: blur(60px) saturate(180%);
  -webkit-backdrop-filter: blur(60px) saturate(180%);
  border-color: var(--color-accent);
  outline-color: var(--color-accent-subtle);
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
  background-color: var(--color-bg-secondary);
  backdrop-filter: blur(40px) saturate(150%);
  -webkit-backdrop-filter: blur(40px) saturate(150%);
  border: 1px solid var(--color-border);
  box-shadow: 0 4px 12px var(--color-shadow), inset 0 1px 0 var(--color-border);
  border-radius: 15px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  /* 外描边效果 */
  outline: 1px solid var(--color-border);
  outline-offset: -1px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 24px;
  width: 24px;
  left: 3px;
  bottom: 3px;
  background-color: var(--color-text-secondary);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 50%;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px var(--color-shadow);
  border: 1px solid var(--color-border);
}

.toggle-input:checked + .toggle-slider {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-secondary) 100%);
  border-color: var(--color-accent);
  box-shadow: 0 4px 16px var(--color-accent-subtle), inset 0 1px 0 var(--color-border);
  outline-color: var(--color-accent-subtle);
}

.toggle-input:checked + .toggle-slider:before {
  transform: translateX(22px);
  background-color: var(--color-text-primary);
  box-shadow: 0 2px 8px var(--color-shadow);
  border-color: var(--color-accent-subtle);
}

/* Hover 状态 */
.toggle-switch:hover .toggle-slider {
  backdrop-filter: blur(60px) saturate(180%);
  -webkit-backdrop-filter: blur(60px) saturate(180%);
}

.toggle-switch:hover .toggle-slider:before {
  background-color: var(--color-text-primary);
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
  color: var(--color-text-primary);
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
  color: var(--color-text-secondary);
  line-height: 1.4;
}

/* ========== SettingsModal 特有样式 ========== */
.settings-modal {
  max-width: 640px;
  max-height: 80vh;
  overflow-y: auto;
}

.settings-modal h2 {
  margin: 0 0 24px 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.03em;
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
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
}

.close-btn {
  background: var(--color-bg-tertiary);
  border: 0.5px solid var(--color-border);
  border-radius: 8px;
  font-size: 22px;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background: var(--color-error-subtle);
  color: var(--color-error);
  transform: rotate(90deg);
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 24px;
}

.danger-btn {
  padding: 10px 20px;
  background: var(--color-error);
  border: 0.5px solid var(--color-border);
  border-radius: 9px;
  color: var(--color-text-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
}

.danger-btn:hover:not(:disabled) {
  background: var(--color-error);
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
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border);
  border-radius: 10px;
}

.history-stat {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.history-stat-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.history-stat-value {
  font-size: 14px;
  color: var(--color-text-primary);
  font-weight: 600;
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
}

.ghost-btn {
  padding: 10px 20px;
  background: var(--color-bg-tertiary);
  border: 0.5px solid var(--color-border);
  border-radius: 9px;
  color: var(--color-text-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.ghost-btn:hover {
  background: var(--color-bg-tertiary);
  border-color: var(--color-border);
  transform: translateY(-1px);
}

.config-sync-section {
  margin-top: 16px;
  padding: 16px;
  background: var(--color-bg-secondary);
  border-radius: 12px;
  border: 1px solid var(--color-border);
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
  color: var(--color-text-primary);
}

.config-sync-section .node-select {
  width: 100%;
  padding: 8px 12px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.config-sync-section .node-select:hover {
  border-color: var(--color-border);
}

.config-sync-section .node-select:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-subtle);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-bg-secondary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  color: var(--color-text-primary);
}

.checkbox-label:hover {
  background: var(--color-bg-secondary);
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--color-accent);
}

/* ========== 私钥显示区域样式 ========== */
.node-secret-section {
  margin-top: 12px;
  padding: 16px;
  background: var(--color-bg-secondary);
  border-radius: 12px;
  border: 1px solid var(--color-border);
}

.secret-display {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--color-bg-primary);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.secret-code {
  flex: 1;
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
  font-size: 13px;
  color: var(--color-text-primary);
  word-break: break-all;
  min-width: 0;
}

.secret-placeholder {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-secondary);
  font-style: italic;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
  background: var(--color-bg-tertiary);
  border: 0.5px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.copy-btn:hover:not(:disabled) {
  background: var(--color-bg-secondary);
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.copy-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.secret-actions {
  display: flex;
  gap: 8px;
}

.secret-actions .ghost-btn {
  flex: 1;
  padding: 8px 16px;
  font-size: 13px;
}
</style>
