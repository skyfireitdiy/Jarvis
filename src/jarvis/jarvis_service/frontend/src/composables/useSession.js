// 会话（Session）恢复 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（原 4202-4203 状态 + 12735-12769 函数），保持行为完全一致：
// - showSessionDialog：会话恢复对话框是否可见
// - availableSessions：可恢复的 session 列表
// - restoreSession(sessionFile)：调用后端恢复指定 session 文件
// - cancelSessionDialog()：取消会话恢复（不恢复，仅加载历史消息）
//
// 依赖注入：
// - currentAgentId：ref(string|null)（当前连接的 Agent ID）
// - getGatewayAddress：函数（返回 { host, port }，调用方注入）
// - getCurrentAgentNodeId：函数（返回当前 Agent 的节点 ID 字符串）
// - fetchWithAuth：函数（带鉴权的 fetch 封装）
// - buildNodeHttpUrl：函数（构建节点 HTTP URL）
// - loadHistoryMessages：函数（加载历史消息，prepend/agentId 可选参数）
import { ref } from 'vue'

export function useSession({ currentAgentId, getGatewayAddress, getCurrentAgentNodeId, fetchWithAuth, buildNodeHttpUrl, loadHistoryMessages }) {
  const showSessionDialog = ref(false)   // Session 选择对话框
  const availableSessions = ref([])      // 可恢复的 session 列表

  // 恢复指定 session 文件：调用后端 agents/{id}/sessions 接口
  async function restoreSession(sessionFile) {
    if (!sessionFile || !currentAgentId.value) {
      console.error('[SESSION] Invalid parameters:', { sessionFile, agentId: currentAgentId.value })
      return
    }

    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agents/${currentAgentId.value}/sessions`), {
        method: 'POST',
        body: JSON.stringify({ session_file: sessionFile, node_id: targetNodeId })
      })

      const result = await response.json()
      if (result.success) {
        showSessionDialog.value = false
        // 加载历史消息
        loadHistoryMessages(false)
      } else {
        console.error('[SESSION] Failed to restore session:', result.error)
        alert(`恢复会话失败: ${result.error}`)
      }
    } catch (error) {
      console.error('[SESSION] Error restoring session:', error)
      alert(`恢复会话失败: ${error.message}`)
    }
  }

  // 取消会话恢复（用户不恢复 session）
  function cancelSessionDialog() {
    showSessionDialog.value = false
    // 加载历史消息（用户不恢复 session）
    loadHistoryMessages(false)
  }

  return {
    showSessionDialog,
    availableSessions,
    restoreSession,
    cancelSessionDialog
  }
}
