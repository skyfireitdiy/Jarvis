<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal connect-modal">
      <h2>连接到 Jarvis</h2>
      <div v-if="errorMessage" class="error-message">
        {{ errorMessage }}
      </div>
      <div class="form-group">
        <label>密码</label>
        <input :value="password" @input="$emit('update:password', $event.target.value)" type="password" placeholder="可选" @keydown.enter="$emit('connect')" />
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
</template>

<script setup>
defineProps({
  visible: Boolean,
  connecting: Boolean,
  errorMessage: String,
  gatewayUrl: String,
  password: String
})

defineEmits(['update:visible', 'update:gatewayUrl', 'update:password', 'connect'])
</script>

<style scoped>
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

.modal {
  background: var(--color-bg-secondary);
  border: 0.5px solid var(--color-border);
  border-radius: 14px;
  padding: 28px;
  width: 100%;
  max-width: 420px;
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
  border-radius: 8px;
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
  border: 0.5px solid var(--color-border);
  border-radius: 9px;
  color: var(--color-text-primary);
  font-size: 14px;
}

.form-group input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-subtle);
}

.form-group input::placeholder {
  color: var(--color-text-secondary);
}

.primary-btn {
  width: 100%;
  padding: 10px 20px;
  background: var(--color-success);
  border: 0.5px solid var(--color-border);
  border-radius: 9px;
  color: var(--color-text-primary);
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
</style>