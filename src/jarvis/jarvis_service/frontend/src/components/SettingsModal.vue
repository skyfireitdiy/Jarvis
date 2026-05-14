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
      <!-- 节点重启服务组件 -->
      <NodeRestartSettings
        :available-node-options="availableNodeOptions"
        :is-restarting-gateway="isRestartingGateway"
        @confirm-restart-gateway="confirmRestartGateway"
      />

      <!-- 代码更新组件 -->
      <CodeUpdateSettings
        :is-updating-code="isUpdatingCode"
        @confirm-update-code-to-main="emit('confirmUpdateCodeToMain')"
      />

      <!-- 节点认证组件 -->
      <NodeSecretSettings
        :get-token="getToken"
        :gateway-url="gatewayUrl"
        :show-toast="showToast"
      />

      <!-- 连接管理组件 -->
      <ConnectionManagementSettings
        :socket="socket"
        @disconnect-all="emit('disconnectAll')"
      />

      <!-- 配置同步组件 -->
      <ConfigSyncSettings
        :available-node-options="availableNodeOptions"
        :is-syncing-config="isSyncingConfig"
        @sync-config="syncConfig"
      />
      <div class="modal-actions">
        <button class="ghost-btn" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import '../styles/settings-modal.css'
import ConnectionSettings from './settings/ConnectionSettings.vue'
import NodeSecretSettings from './settings/NodeSecretSettings.vue'
import HistorySettings from './settings/HistorySettings.vue'
import NodeRestartSettings from './settings/NodeRestartSettings.vue'
import CodeUpdateSettings from './settings/CodeUpdateSettings.vue'
import ConnectionManagementSettings from './settings/ConnectionManagementSettings.vue'
import ConfigSyncSettings from './settings/ConfigSyncSettings.vue'

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

// 本地状态（已移至子组件）

// 关闭弹窗
function close() {
  emit('update:visible', false)
}

// 格式化节点选项标签（已移至子组件）

// 确认清除历史
function confirmClearHistory() {
  emit('confirmClearHistory')
}

// 确认重启网关（已移至子组件）
// 断开所有连接（已移至子组件）
// 同步配置（已移至子组件）
// 更新代码到 main 分支（已移至子组件）


</script>

