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
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal {
  background: rgba(22, 27, 34, 0.95);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
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

.error-message {
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid rgba(248, 81, 73, 0.3);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
  color: #f85149;
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
  color: #8b949e;
  letter-spacing: 0.01em;
}

.form-group input {
  width: 100%;
  padding: 11px 14px;
  background: rgba(13, 17, 23, 0.8);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
}

.form-group input:focus {
  outline: none;
  border-color: rgba(56, 139, 253, 0.5);
  box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.1);
}

.form-group input::placeholder {
  color: #484f58;
}

.primary-btn {
  width: 100%;
  padding: 10px 20px;
  background: #238636;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 9px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 8px;
}

.primary-btn:hover:not(:disabled) {
  background: #2ea043;
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