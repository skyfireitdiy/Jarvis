// 用户协议 组合式函数。
//
// 需求（Administrator）：首次打开前端页面时弹出用户协议，用户不同意则不能使用软件。
// 从 App.vue 的 <script setup> 中拆出，保持 App.vue 不臃肿：
// - 常量：AGREEMENT_STORAGE_KEY（带版本号，协议内容更新时递增版本号即可强制老用户重新确认）
// - 状态：showAgreement / agreed
// - 读写：hasAccepted() / agree()
//
// localStorage 读写均 try/catch 静默降级（隐私模式 / 配额满）：
// - 读不到视为未同意 → 每次打开都弹协议（严格模式，宁可不放行也不绕过）
// - 写入失败静默忽略 → 本次会话内 agreed=true 仍可正常使用
import { ref } from 'vue'

export const AGREEMENT_STORAGE_KEY = 'jarvis_user_agreement_v1'

export function useUserAgreement() {
  // 是否展示协议弹窗（首次打开且未同意时为 true）
  const showAgreement = ref(false)
  // 本次会话是否已同意（内存态；localStorage 持久化见 agree）
  const agreed = ref(false)

  // 是否已接受过协议（读取持久化标记；localStorage 不可用时视为未同意）
  function hasAccepted() {
    try {
      return localStorage.getItem(AGREEMENT_STORAGE_KEY) === '1'
    } catch {
      return false
    }
  }

  // 用户同意：写入持久化标记并更新内存态
  function agree() {
    agreed.value = true
    showAgreement.value = false
    try {
      localStorage.setItem(AGREEMENT_STORAGE_KEY, '1')
    } catch {
      // localStorage 不可用时静默降级：本次会话内 agreed=true 已放行
    }
  }

  return { showAgreement, agreed, hasAccepted, agree }
}
