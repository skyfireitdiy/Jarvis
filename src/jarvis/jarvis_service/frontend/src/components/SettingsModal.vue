<template>
  <!-- 设置弹窗 -->
  <div class="modal-overlay" v-if="visible">
    <div class="modal settings-modal">
      <div class="modal-header">
        <h2>设置</h2>
        <button class="close-btn" @click="close">×</button>
      </div>
      <div class="form-group">
        <div class="toggle-wrapper">
          <label class="toggle-switch">
            <input type="checkbox" v-model="localConnectionLockEnabled" @change="handleConnectionLockChange" class="toggle-input" />
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

      <!-- 连接管理 -->
      <div class="form-group">
        <label>连接管理</label>
        <div class="connection-management-section">
          <button class="danger-btn" @click="disconnectAll" :disabled="!socket">
            断开连接
          </button>
          <span class="form-help">断开所有WebSocket连接并刷新页面</span>
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
import { ref, watch } from 'vue'

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
  }
})

const emit = defineEmits([
  'update:visible',
  'update:connectionLockEnabled',
  'saveConnectionLockSetting',
  'confirmClearHistory',
  'confirmRestartGateway',
  'disconnectAll',
  'syncConfig'
])

// 本地状态
const localConnectionLockEnabled = ref(props.connectionLockEnabled)
const localRestartNodeId = ref('')
const localRestartFrontendService = ref(false)
const localSyncConfigSourceNode = ref('')

// 监听props变化
watch(() => props.connectionLockEnabled, (newVal) => {
  localConnectionLockEnabled.value = newVal
})

// 关闭弹窗
function close() {
  emit('update:visible', false)
}

// 处理连接锁定设置变更
function handleConnectionLockChange() {
  emit('update:connectionLockEnabled', localConnectionLockEnabled.value)
  emit('saveConnectionLockSetting')
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
</script>

<style scoped>
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
</style>
