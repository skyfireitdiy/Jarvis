<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal create-agent-modal">
      <h2>重命名 Agent</h2>
      <div class="form-group">
        <label>Agent 名称（可选）</label>
        <input
          :value="name"
          @input="$emit('update:name', $event.target.value)"
          type="text"
          class="form-control"
          placeholder="留空则使用默认名称"
          ref="renameInput"
          @keydown.enter="$emit('confirm')"
        />
      </div>
      <div class="modal-actions">
        <button class="btn secondary" @click="$emit('cancel')">取消</button>
        <button class="btn primary" @click="$emit('confirm')">确认</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  visible: Boolean,
  name: { type: String, default: '' }
})

const emit = defineEmits(['update:name', 'cancel', 'confirm'])

const renameInput = ref(null)

watch(() => props.visible, async (newVal) => {
  if (newVal) {
    await nextTick()
    renameInput.value?.focus()
  }
})
</script>

<style scoped>

/* 模态框遮罩层 */
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

/* 模态框基础样式 */
.modal-overlay .modal {
  background: rgba(22, 27, 34, 0.95);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  padding: 28px;
}

.create-agent-modal h2 {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: #e6edf3;
}

/* 表单组样式 */
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

.create-agent-modal .form-control {
  width: 100%;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: #e6edf3;
  font-size: 14px;
}

.create-agent-modal .form-control:focus {
  outline: none;
  border-color: rgba(63, 185, 80, 0.6);
  background: rgba(255, 255, 255, 0.08);
}

.create-agent-modal .modal-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.create-agent-modal .btn {
  flex: 1;
  padding: 10px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
}

.create-agent-modal .btn.secondary {
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
}

.create-agent-modal .btn.secondary:hover {
  background: rgba(255, 255, 255, 0.15);
}

.create-agent-modal .btn.primary {
  background: #3fb950;
  color: white;
}

.create-agent-modal .btn.primary:hover {
  transform: translateY(-1px);
}

.create-agent-modal .btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none !important;
}
</style>