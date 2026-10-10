// Diff 浮动窗口 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（原 2942-2954 状态 + 14765-14822 函数），保持行为完全一致：
// - showDiffModal：显示 diff 浮动窗口
// - diffFiles：结构化 diff 文件列表（每个元素含 file_path/additions/deletions/rows）
// - diffActiveIndex：当前选中的文件索引
// - diffLoading：加载状态
// - diffError：加载失败时的错误信息
// - diffMobileShowDetail：移动端两级导航（false=文件列表，true=选中文件的 diff 详情）
// - diffActiveHtml：当前选中文件的渲染结果（复用 renderSideBySideDiff）
// - selectDiffFile(index)：选中某个文件（桌面端仅切换右侧内容，移动端进入全屏详情）
// - viewDiff(agent)：查看 Agent 的 Diff（从后端拉取结构化 diff 数据）
//
// 依赖注入：
// - windowWidth：ref(number)（窗口宽度，移动端窄屏判断）
// - getGatewayAddress：函数（返回 { host, port }，调用方注入）
// - getCurrentAgentNodeId：函数（返回当前 Agent 的节点 ID 字符串）
// - fetchWithAuth：函数（带鉴权的 fetch 封装）
// - buildNodeHttpUrl：函数（构建节点 HTTP URL）
import { computed, ref } from 'vue'
import { renderSideBySideDiff } from '../diffRenderer.js'

export function useDiff({ windowWidth, getGatewayAddress, getCurrentAgentNodeId, fetchWithAuth, buildNodeHttpUrl }) {
  const showDiffModal = ref(false)      // 显示diff浮动窗口
  const diffFiles = ref([])             // 结构化 diff 文件列表（每个元素含 file_path/additions/deletions/rows）
  const diffActiveIndex = ref(0)        // 当前选中的文件索引
  const diffLoading = ref(false)        // 加载状态
  const diffError = ref('')             // 加载失败时的错误信息
  // 移动端两级导航：false=文件列表，true=选中文件的 diff 详情
  const diffMobileShowDetail = ref(false)
  // 当前选中文件的渲染结果（复用 renderSideBySideDiff）
  const diffActiveHtml = computed(() => {
    const file = diffFiles.value[diffActiveIndex.value]
    if (!file) return ''
    return renderSideBySideDiff(file)
  })

  // 选中某个文件：桌面端仅切换右侧内容，移动端进入全屏详情
  function selectDiffFile(index) {
    diffActiveIndex.value = index
    // 移动端（窄屏）点击文件后全屏展示该文件 diff，由顶部返回按钮回到列表
    if (windowWidth.value <= 768) {
      diffMobileShowDetail.value = true
    }
  }

  // 查看 Agent 的 Diff
  async function viewDiff(agent) {
    if (!agent || !agent.agent_id) {
      console.warn('[DIFF] Invalid agent:', agent)
      return
    }
    diffLoading.value = true
    showDiffModal.value = true
    diffFiles.value = []
    diffActiveIndex.value = 0
    diffError.value = ''
    diffMobileShowDetail.value = false
    try {
      const { host, port } = getGatewayAddress()
      const targetNodeId = String(agent?.node_id || '').trim() || String(getCurrentAgentNodeId() || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `agent/${agent.agent_id}/diff`))
      if (!response.ok) {
        console.warn(`[DIFF] Failed to fetch diff for agent ${agent.agent_id}:`, response.status)
        diffError.value = '获取 diff 失败'
        return
      }
      const result = await response.json()
      // 使用后端返回的结构化数据，添加数据验证
      if (result.files && Array.isArray(result.files) && result.files.length > 0) {
        // 验证并过滤有效的文件数据
        const validFiles = result.files.filter(file => {
          // 验证文件对象包含必要字段
          if (!file || typeof file !== 'object') return false
          if (!file.rows || !Array.isArray(file.rows)) return false
          // 验证 rows 中的每个元素
          return file.rows.every(row => {
            return row && typeof row === 'object' &&
                   ['equal', 'insert', 'delete', 'replace'].includes(row.type)
          })
        })
        diffFiles.value = validFiles
      }
    } catch (error) {
      console.error('[DIFF] Error fetching diff:', error)
      diffError.value = '获取 diff 失败: ' + (error.message || '')
    } finally {
      diffLoading.value = false
    }
  }

  return {
    showDiffModal,
    diffFiles,
    diffActiveIndex,
    diffLoading,
    diffError,
    diffMobileShowDetail,
    diffActiveHtml,
    selectDiffFile,
    viewDiff
  }
}
