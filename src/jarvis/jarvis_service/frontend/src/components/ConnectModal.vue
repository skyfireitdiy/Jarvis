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