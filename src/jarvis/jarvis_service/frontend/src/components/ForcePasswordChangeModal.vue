<template>
  <!-- 强制改密弹窗：初始 admin 为无密码状态，首次登录后必须设置密码才能使用 -->
  <div v-if="visible" class="force-pwd-overlay modal-overlay">
    <div class="force-pwd-modal">
      <div class="force-pwd-header">
        <h2>设置管理员密码</h2>
      </div>
      <div class="force-pwd-body">
        <p class="force-pwd-warning">
          首次登录必须为管理员账号设置密码。在设置密码前，除修改密码外的所有操作都会被拒绝。
        </p>
        <div v-if="displayError" class="force-pwd-error">{{ displayError }}</div>
        <div class="force-pwd-field">
          <label>新密码</label>
          <input
            ref="newPasswordInput"
            v-model="newPassword"
            type="password"
            placeholder="请输入新密码"
            @keydown.enter="submit"
          />
        </div>
        <div class="force-pwd-field">
          <label>确认密码</label>
          <input
            v-model="confirmPassword"
            type="password"
            placeholder="请再次输入新密码"
            @keydown.enter="submit"
          />
        </div>
      </div>
      <div class="force-pwd-actions">
        <button class="btn primary force-pwd-submit" :disabled="loading" @click="submit">
          {{ loading ? '提交中...' : '设置密码' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  errorMessage: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['submit'])

const newPassword = ref('')
const confirmPassword = ref('')
const localError = ref('')
const newPasswordInput = ref(null)

// 本地校验错误优先于父组件传入的错误（如接口返回的错误）
const displayError = computed(() => localError.value || props.errorMessage)

watch(
  () => props.visible,
  (val) => {
    if (val) {
      newPassword.value = ''
      confirmPassword.value = ''
      localError.value = ''
      nextTick(() => newPasswordInput.value?.focus())
    }
  }
)

function submit() {
  localError.value = ''
  const pwd = String(newPassword.value || '')
  if (!pwd) {
    localError.value = '新密码不能为空'
    return
  }
  if (pwd !== String(confirmPassword.value || '')) {
    localError.value = '两次输入的新密码不一致'
    return
  }
  emit('submit', { new_password: pwd })
}
</script>

<style scoped>
.force-pwd-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  /* 高于 ConnectModal(9999)，低于用户协议(10001) */
  z-index: 10000;
}

.force-pwd-modal {
  width: min(460px, 92vw);
  display: flex;
  flex-direction: column;
  background: var(--bg-color, #1e1e2e);
  color: var(--text-color, #e6e6e6);
  border: 1px solid var(--border-color, #3a3a4a);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.force-pwd-header {
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-color, #3a3a4a);
}

.force-pwd-header h2 {
  margin: 0;
  font-size: 18px;
}

.force-pwd-body {
  padding: 18px 24px;
  font-size: 13px;
  line-height: 1.7;
}

.force-pwd-warning {
  padding: 12px 14px;
  margin: 0 0 16px;
  background: rgba(255, 193, 7, 0.12);
  border-left: 4px solid #ffc107;
  border-radius: 6px;
}

.force-pwd-error {
  padding: 10px 12px;
  margin-bottom: 14px;
  background: rgba(244, 67, 54, 0.12);
  border-left: 4px solid #f44336;
  border-radius: 6px;
  color: #ff8a80;
}

.force-pwd-field {
  margin-bottom: 14px;
}

.force-pwd-field label {
  display: block;
  margin-bottom: 6px;
  color: var(--text-muted, #9a9aa8);
}

.force-pwd-field input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  background: var(--input-bg, #2a2a3a);
  color: var(--text-color, #e6e6e6);
  border: 1px solid var(--border-color, #3a3a4a);
  border-radius: 6px;
}

.force-pwd-actions {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color, #3a3a4a);
  display: flex;
  justify-content: flex-end;
}

.force-pwd-submit {
  min-width: 120px;
}
</style>
