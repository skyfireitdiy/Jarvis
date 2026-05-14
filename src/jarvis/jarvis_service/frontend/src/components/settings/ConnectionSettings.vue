<template>
  <!-- 连接设置组件 -->
  <div class="connection-settings">
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
    <div class="form-group">
      <div class="toggle-wrapper">
        <label class="toggle-switch">
          <input type="checkbox" v-model="localAutoLoginEnabled" @change="handleAutoLoginChange" class="toggle-input" />
          <span class="toggle-slider"></span>
        </label>
        <div class="toggle-info">
          <span class="toggle-label-text">免登录（记住Token）</span>
          <span class="form-help">启用后，登录成功时将Token保存在浏览器本地，下次打开时自动尝试连接。</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  connectionLockEnabled: {
    type: Boolean,
    default: false
  },
  autoLoginEnabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'update:connectionLockEnabled',
  'saveConnectionLockSetting',
  'update:autoLoginEnabled',
  'saveAutoLoginSetting'
])

// 本地状态
const localConnectionLockEnabled = ref(props.connectionLockEnabled)
const localAutoLoginEnabled = ref(props.autoLoginEnabled)

// 监听props变化
watch(() => props.connectionLockEnabled, (newVal) => {
  localConnectionLockEnabled.value = newVal
})

watch(() => props.autoLoginEnabled, (newVal) => {
  localAutoLoginEnabled.value = newVal
})

// 处理连接锁定设置变更
function handleConnectionLockChange() {
  emit('update:connectionLockEnabled', localConnectionLockEnabled.value)
  emit('saveConnectionLockSetting')
}

// 处理免登录设置变更
function handleAutoLoginChange() {
  emit('update:autoLoginEnabled', localAutoLoginEnabled.value)
  emit('saveAutoLoginSetting')
}
</script>

<style scoped>
/* 连接设置组件样式 */
.connection-settings {
  margin-bottom: 16px;
}
</style>