<template>
  <!-- 节点认证组件 -->
  <div class="node-secret-settings">
    <div class="form-group">
      <label>节点连接私钥</label>
      <div class="node-secret-section">
        <div class="secret-display">
          <code class="secret-code" v-if="nodeSecret" :title="nodeSecret">{{ maskedNodeSecret }}</code>
          <span class="secret-placeholder" v-else>点击"获取私钥"加载</span>
          <button class="copy-btn" @click="copyNodeSecret" :disabled="!nodeSecret" title="复制私钥">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
          </button>
        </div>
        <div class="secret-actions">
          <button class="ghost-btn" @click="fetchNodeSecret" :disabled="isLoadingSecret">
            {{ isLoadingSecret ? '加载中...' : '获取私钥' }}
          </button>
          <button class="ghost-btn" @click="toggleSecretMask" :disabled="!nodeSecret" title="显示/隐藏">
            {{ showSecret ? '隐藏' : '显示' }}
          </button>
        </div>
        <span class="form-help">此私钥用于子节点连接主网关时的身份认证，请妥善保管</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
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

// 私钥相关状态
const nodeSecret = ref('')
const isLoadingSecret = ref(false)
const showSecret = ref(false)

/**
 * 获取节点私钥
 */
async function fetchNodeSecret() {
  if (isLoadingSecret.value) return

  try {
    // 通过父组件传递的 getToken 函数获取 Token（优先内存，其次 localStorage）
    const token = props.getToken()
    if (!token) {
      throw new Error('请先登录')
    }
    // 构建完整的后端 API URL
    const apiProtocol = window.location.protocol === 'https:' ? 'https' : 'http'
    const apiUrl = `${apiProtocol}://${props.gatewayUrl}/api/node/secret`
    const response = await fetch(apiUrl, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    const result = await response.json()

    if (result.success && result.data?.node_secret) {
      nodeSecret.value = result.data.node_secret
    } else {
      console.error('获取私钥失败:', result.error?.message || '未知错误')
      alert(`获取私钥失败：${result.error?.message || '未知错误'}`)
    }
  } catch (error) {
    console.error('获取私钥异常:', error)
    alert(`获取私钥异常：${error.message}`)
  } finally {
    isLoadingSecret.value = false
  }
}

/**
 * 切换私钥显示/隐藏状态
 */
function toggleSecretMask() {
  showSecret.value = !showSecret.value
}

/**
 * 复制私钥到剪贴板
 */
async function copyNodeSecret() {
  if (!nodeSecret.value) {
    console.warn('复制失败：私钥内容为空')
    alert('私钥内容为空，请先获取私钥')
    return
  }

  try {
    await navigator.clipboard.writeText(nodeSecret.value)
    console.log('复制成功')
    props.showToast('已复制到剪贴板', 'success')
  } catch (error) {
    console.error('复制失败，尝试降级方案:', error)
    // 降级方案：使用 execCommand
    try {
      const textArea = document.createElement('textarea')
      textArea.value = nodeSecret.value
      textArea.style.position = 'fixed'
      textArea.style.opacity = '0'
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
      console.log('降级方案复制成功')
      props.showToast('已复制到剪贴板', 'success')
    } catch (fallbackErr) {
      console.error('降级方案也失败:', fallbackErr)
      alert('复制失败，请手动复制')
    }
  }
}

/**
 * 掩码显示的私钥（仅显示首尾部分）
 */
const maskedNodeSecret = computed(() => {
  if (!nodeSecret.value) return ''
  if (showSecret.value) return nodeSecret.value

  const secret = nodeSecret.value
  if (secret.length <= 16) {
    return '*'.repeat(secret.length)
  }
  return `${secret.slice(0, 8)}${'*'.repeat(secret.length - 16)}${secret.slice(-8)}`
})
</script>

<style scoped>
/* 节点认证组件样式 */
.node-secret-settings {
  margin-bottom: 16px;
}
</style>