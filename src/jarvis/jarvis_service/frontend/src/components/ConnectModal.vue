<template>
  <div class="modal-overlay connect-overlay" v-if="visible">
    <div class="modal connect-modal">
      <div class="brand-panel">
        <div class="brand-header">
          <img src="/icons/jarvis-logo.png" alt="Jarvis" class="brand-logo" />
          <div class="brand-title">
            <h1>JARVIS</h1>
            <p>让 AI 从「独自工作」走向「与众共事」</p>
          </div>
        </div>
        <div class="quadrants">
          <div class="quadrant">
            <div class="quadrant-name">单人单 Agent</div>
            <div class="quadrant-value">独当一面</div>
            <div class="quadrant-cap">符号级代码理解 · 影响分析 · 无人值守 · 交叉验证</div>
          </div>
          <div class="quadrant">
            <div class="quadrant-name">单人多 Agent</div>
            <div class="quadrant-value">一人驱动一个团队</div>
            <div class="quadrant-cap">编排网络 · Agent 间通信 · 多面板同屏操作</div>
          </div>
          <div class="quadrant">
            <div class="quadrant-name">多人单 Agent</div>
            <div class="quadrant-value">团队共享一个 AI</div>
            <div class="quadrant-cap">多用户认证 · ACL 权限 · 共享协作 · 聊天室</div>
          </div>
          <div class="quadrant">
            <div class="quadrant-name">多人多 Agent</div>
            <div class="quadrant-value">分布式协作网络</div>
            <div class="quadrant-cap">多节点多网关 · 跨节点通信 · 节点级运维</div>
          </div>
        </div>
      </div>
      <div class="form-panel">
        <h2>连接到 Jarvis</h2>
        <div v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </div>
        <div class="form-group">
          <label>用户名</label>
          <input :value="username" @input="$emit('update:username', $event.target.value)" type="text" placeholder="输入用户名" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input :value="password" @input="$emit('update:password', $event.target.value)" type="password" placeholder="必填" @keydown.enter="$emit('connect')" />
        </div>
        <div class="form-group">
          <label>网关地址</label>
          <input :value="gatewayUrl" @input="$emit('update:gatewayUrl', $event.target.value)" placeholder="127.0.0.1:8000 或 ws://example.com:8080/ws" />
        </div>
        <button class="primary-btn" @click="$emit('connect')" :disabled="connecting">
          {{ connecting ? '连接中...' : '连接' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  visible: Boolean,
  connecting: Boolean,
  errorMessage: String,
  gatewayUrl: String,
  password: String,
  username: String
})

defineEmits(['update:visible', 'update:gatewayUrl', 'update:password', 'update:username', 'connect'])
</script>

<style scoped>
.modal-overlay.connect-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: var(--app-height, 100dvh);
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  box-sizing: border-box;
  /* 向外扩出安全区，避免真机圆角/刘海处露出下层页面 */
  margin: calc(-1 * env(safe-area-inset-top, 0px)) calc(-1 * env(safe-area-inset-right, 0px))
          calc(-1 * env(safe-area-inset-bottom, 0px)) calc(-1 * env(safe-area-inset-left, 0px));
  padding: calc(20px + env(safe-area-inset-top, 0px)) calc(20px + env(safe-area-inset-right, 0px))
           calc(20px + env(safe-area-inset-bottom, 0px)) calc(20px + env(safe-area-inset-left, 0px));
}

.modal {
  background: var(--color-bg-secondary);
  border: none;
  border-radius: var(--tile-radius-sm);
  width: 100%;
  max-width: 820px;
  display: flex;
  overflow: hidden;
}

.brand-panel {
  flex: 1;
  padding: 36px 32px;
  background: var(--color-bg-primary);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 28px;
}

.brand-header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-logo {
  width: 44px;
  height: 44px;
  object-fit: contain;
  flex-shrink: 0;
}

.brand-title h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: 0.08em;
}

.brand-title p {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.quadrants {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.quadrant {
  padding-left: 12px;
  border-left: 2px solid var(--color-accent);
}

.quadrant-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.quadrant-value {
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-success);
}

.quadrant-cap {
  margin-top: 3px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.form-panel {
  width: 380px;
  flex-shrink: 0;
  padding: 36px 32px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.connect-modal h2 {
  margin: 0 0 24px 0;
  font-size: 21px;
  font-weight: 600;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
}

.error-message {
  background: var(--color-error-subtle);
  border: 1px solid var(--color-error);
  border-radius: var(--tile-radius);
  padding: 12px;
  margin-bottom: 16px;
  color: var(--color-error);
  font-size: 14px;
}

.form-group {
  margin-bottom: 16px;
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
  border: none;
  border-radius: var(--tile-radius);
  color: var(--color-text-primary);
  font-size: 14px;
}

.form-group input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: var(--tile-shadow);
}

.form-group input::placeholder {
  color: var(--color-text-secondary);
}

.primary-btn {
  width: 100%;
  padding: 10px 20px;
  background: var(--color-success);
  border: none;
  border-radius: var(--tile-radius);
  color: #060911;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 8px;
}

.primary-btn:hover:not(:disabled) {
  background: var(--color-success);
  transform: translateY(-1px);
}

.primary-btn:active:not(:disabled) {
  transform: translateY(0);
}

.primary-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .modal-overlay.connect-overlay {
    padding: 16px;
  }

  .modal {
    max-width: 480px;
    max-height: calc(var(--app-height, 100dvh) - 32px);
    overflow-y: auto;
    display: block;
  }

  .brand-panel {
    padding: 28px 24px;
    gap: 20px;
  }

  .quadrants {
    gap: 12px;
  }

  .quadrant-cap {
    display: none;
  }

  .form-panel {
    width: 100%;
    padding: 28px 24px;
  }
}
</style>