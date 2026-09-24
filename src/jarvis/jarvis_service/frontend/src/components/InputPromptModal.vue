<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal input-prompt-modal">
      <h2>{{ title }}</h2>
      <div class="form-group">
        <label v-if="label">{{ label }}</label>
        <input
          :value="modelValue"
          @input="$emit('update:modelValue', $event.target.value)"
          type="text"
          class="form-control"
          :placeholder="placeholder"
          ref="promptInput"
          @keydown.enter="$emit('confirm')"
        />
        <div v-if="error" class="form-error">{{ error }}</div>
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
  title: { type: String, default: '请输入' },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  modelValue: { type: String, default: '' },
  error: { type: String, default: '' }
})

defineEmits(['update:modelValue', 'cancel', 'confirm'])

const promptInput = ref(null)

watch(() => props.visible, async (newVal) => {
  if (newVal) {
    await nextTick()
    promptInput.value?.focus()
    promptInput.value?.select()
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
  background: var(--color-overlay, rgba(4, 8, 15, 0.72));
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3000;
  padding: 20px;
}

/* 模态框基础样式 */
.modal-overlay .modal {
  background: var(--color-bg-secondary);
  border: none;
  border-radius: var(--tile-radius-sm);
  padding: 28px;
  width: 100%;
  max-width: 420px;
}

.input-prompt-modal h2 {
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

.input-prompt-modal .form-control {
  width: 100%;
  padding: 10px 12px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius-xs);
  color: var(--color-text-primary);
  font-size: 14px;
  box-sizing: border-box;
}

.input-prompt-modal .form-control:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-tertiary);
}

.form-error {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-error);
}

.input-prompt-modal .modal-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.input-prompt-modal .btn {
  flex: 1;
  padding: 10px;
  border-radius: var(--tile-radius-xs);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
}

.input-prompt-modal .btn.secondary {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.input-prompt-modal .btn.secondary:hover {
  background: var(--color-bg-tertiary);
}

.input-prompt-modal .btn.primary {
  background: var(--color-success);
  color: #060911;
}

.input-prompt-modal .btn.primary:hover {
  transform: translateY(-1px);
}
</style>
