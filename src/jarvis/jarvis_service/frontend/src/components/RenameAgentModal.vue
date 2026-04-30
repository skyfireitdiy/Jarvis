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

.create-agent-modal h2 {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: var(--color-text-primary);
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
  color: var(--color-text-secondary);
  letter-spacing: 0.01em;
}

.create-agent-modal .form-control {
  width: 100%;
  padding: 10px 12px;
  background: var(--color-bg-tertiary);
  border: 0.5px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-primary);
  font-size: 14px;
}

.create-agent-modal .form-control:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-tertiary);
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
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.create-agent-modal .btn.secondary:hover {
  background: var(--color-bg-tertiary);
}

.create-agent-modal .btn.primary {
  background: var(--color-success);
  color: var(--color-text-primary);
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