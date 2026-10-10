// 系统设置 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 8），保持行为完全一致：
// - 状态：notifyOnExit / notifyOnInput / syncConfigSourceNode / syncConfigTargetNodes /
//   syncConfigSections / isSyncingConfig / isUpdatingCode
// - 通知开关：saveNotifySettings
// - 配置同步：handleSyncConfig / syncConfig
// - 代码更新：handleUpdateCodeToMain / confirmUpdateCodeToMain / updateCodeToMain
// - 节点重启：confirmRestartAllNodes / restartAllNodes
// - 管理面板定位：openAdminSystemAction
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - notifyOnExit / notifyOnInput 等 ref 由本 composable 创建并返回，App.vue 解构后共享
//   （notifyOnExit / notifyOnInput 被 App.vue 的 handleMessage 通知逻辑读取）。
// - getGatewayAddress / getHttpProtocol / fetchWithAuth / buildNodeHttpUrl / showToast /
//   showConfirm / availableNodeOptions / showAdminPanel / adminPanelRef：定义在本 composable
//   调用点之前，直接传引用/ref。
// - pushOverlayState / isRestartingGateway / restartFrontendService：定义在调用点之后
//   （isRestartingGateway / restartFrontendService 来自 useGatewayConnection），用 getter
//   注入，内部通过 () => xxx 求值。
import { nextTick, ref } from 'vue'
export function useSettings({
  showAdminPanel,
  adminPanelRef,
  pushOverlayState,
  getGatewayAddress,
  getHttpProtocol,
  fetchWithAuth,
  buildNodeHttpUrl,
  showToast,
  showConfirm,
  availableNodeOptions,
  isRestartingGateway,
  restartFrontendService,
}) {
  // 通知开关仅控制系统通知弹窗，不影响提示音（提示音由自动朗读等逻辑独立触发）
  const notifyOnExit = ref(localStorage.getItem('jarvis_notify_on_exit') === 'true')  // Agent 退出通知开关（默认关闭）
  const notifyOnInput = ref(localStorage.getItem('jarvis_notify_on_input') === 'true')  // 需要输入通知开关（默认关闭）
  // 配置同步相关状态
  const syncConfigSourceNode = ref('') // 配置同步的源节点ID
  const syncConfigTargetNodes = ref([]) // 配置同步的目标节点ID数组
  const syncConfigSections = ref(['llms', 'llm_groups']) // 要同步的配置类型数组（llms, llm_groups）
  const isSyncingConfig = ref(false) // 是否正在同步配置
  const isUpdatingCode = ref(false) // 是否正在更新代码

  // 保存通知开关设置（仅控制弹窗，不影响提示音）
  function saveNotifySettings() {
    localStorage.setItem('jarvis_notify_on_exit', notifyOnExit.value)
    localStorage.setItem('jarvis_notify_on_input', notifyOnInput.value)
  }

  // 处理 SettingsModal 组件的同步配置事件
  function handleSyncConfig({ sourceNodeId }) {
    syncConfigSourceNode.value = sourceNodeId || ''

    // 显示确认框
    showConfirm(
      '确定要同步配置到其他节点吗？此操作将覆盖目标节点的配置。',
      () => {
        syncConfig()
      },
      () => {},
      false
    )
  }

  // 处理 SettingsModal 组件的更新代码事件
  function handleUpdateCodeToMain() {
    updateCodeToMain()
  }

  // 打开管理面板并定位到系统配置，触发指定操作（供命令面板调用）
  function openAdminSystemAction(kind) {
    showAdminPanel.value = true
    pushOverlayState()()
    nextTick(() => {
      adminPanelRef.value?.openSystemAction?.(kind)
    })
  }

  // 确认更新代码到 main 分支
  function confirmUpdateCodeToMain() {
    showConfirm(
      '确定要更新所有节点的代码到 main 分支吗？\n\n此操作将：\n1. 切换所有节点到 main 分支\n2. 拉取最新代码\n3. 可能需要重启服务',
      () => {
        updateCodeToMain()
      },
      () => {},
      false
    )
  }

  // 确认重启所有节点（依次重启子节点，最后 master）
  async function confirmRestartAllNodes() {
    showConfirm(
      '确认要一键重启所有节点吗？\n\n操作顺序：\n1. 依次重启所有子节点\n2. 最后重启 master 节点\n\n这将短暂中断所有节点的连接，包括正在运行的 Agent。',
      () => {
        restartAllNodes()
      },
      () => {},
      false
    )
  }

  async function restartAllNodes() {
    try {
      isRestartingGateway().value = true
      const { host, port } = getGatewayAddress()

      // 获取所有节点列表（排除 master）
      const childNodes = (availableNodeOptions.value || []).filter(node => node.node_id !== 'master')
      const allNodes = [...childNodes, { node_id: 'master', label: 'Master' }]

      for (const node of allNodes) {
        const nodeId = node.node_id
        const normalizedNodeId = nodeId || 'master'

        try {
          // 发送重启请求
          const response = await fetchWithAuth(buildNodeHttpUrl(host, port, normalizedNodeId, 'service/restart'), {
            method: 'POST',
            body: JSON.stringify({
              node_id: normalizedNodeId,
              restart_frontend: restartFrontendService().value
            })
          })

          if (response.ok) {
            const data = await response.json().catch(() => ({}))
            if (data.success === false) {
              showToast(`节点 "${normalizedNodeId}" 重启失败：${data.error?.message || '未知错误'}`, 'error')
            } else {
              showToast(`已向节点 "${normalizedNodeId}" 发送重启请求`, 'success')
            }
          } else {
            showToast(`节点 "${normalizedNodeId}" 重启失败：HTTP ${response.status}`, 'error')
          }
        } catch (error) {
          console.error(`[SETTINGS] Failed to restart node ${normalizedNodeId}:`, error)
          showToast(`节点 "${normalizedNodeId}" 重启失败：${error.message || '未知错误'}`, 'error')
        }

        // 每个节点之间间隔 1 秒，避免请求过于密集
        if (node.node_id !== 'master') {
          await new Promise(resolve => setTimeout(resolve, 1000))
        }
      }

      showToast('所有节点重启命令已发送完成', 'success')
    } catch (error) {
      console.error('[SETTINGS] Failed to restart all nodes:', error)
      showToast(error.message || '重启所有节点失败', 'error')
    } finally {
      setTimeout(() => {
        isRestartingGateway().value = false
      }, 3000)
    }
  }
  async function syncConfig() {
    if (isSyncingConfig.value) {
      return
    }

    try {
      isSyncingConfig.value = true
      const { host, port } = getGatewayAddress()
      const sourceNodeId = syncConfigSourceNode.value || 'master'

      // 自动选择除源节点外的所有节点作为目标
      const targetNodeIds = availableNodeOptions.value
        .map(node => node.node_id)
        .filter(id => id !== sourceNodeId)

      // 如果源节点不是 master，将 master 加入目标节点列表
      if (sourceNodeId !== 'master' && !targetNodeIds.includes('master')) {
        targetNodeIds.unshift('master')
      }

      if (targetNodeIds.length === 0) {
        showToast('没有其他节点可以同步', 'warning')
        return
      }

      // 1. 从源节点获取配置
      const getResponse = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/nodes/${sourceNodeId}/config`, {
        method: 'GET'
      })
      const getResult = await getResponse.json()

      if (!getResponse.ok || !getResult.success) {
        throw new Error(getResult.error?.message || '获取源节点配置失败')
      }

      const sourceConfig = getResult.data?.config || {}

      // 提取要同步的配置
      const configData = {}
      for (const section of syncConfigSections.value) {
        if (sourceConfig[section]) {
          configData[section] = sourceConfig[section]
        }
      }

      if (Object.keys(configData).length === 0) {
        showToast('没有可同步的配置数据', 'warning')
        return
      }

      // 2. 对每个目标节点设置配置
      let successCount = 0
      const totalCount = targetNodeIds.length
      const results = []

      for (const targetNodeId of targetNodeIds) {
        try {
          const setResponse = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/nodes/${targetNodeId}/config`, {
            method: 'POST',
            body: JSON.stringify({
              config_sections: syncConfigSections.value,
              config_data: configData
            })
          })
          const setResult = await setResponse.json()

          if (setResponse.ok && setResult.success) {
            successCount++
            results.push({
              node_id: targetNodeId,
              success: true,
              data: setResult.data
            })
          } else {
            results.push({
              node_id: targetNodeId,
              success: false,
              error: setResult.error || { message: '设置配置失败' }
            })
          }
        } catch (error) {
          console.error(`[SETTINGS] Failed to set config for node ${targetNodeId}:`, error)
          results.push({
            node_id: targetNodeId,
            success: false,
            error: { message: error.message || '设置配置失败' }
          })
        }
      }

      // 3. 显示结果
      if (successCount === totalCount) {
        showToast(`配置同步成功，已同步到 ${successCount} 个节点`, 'success')
      } else {
        showToast(`配置同步部分成功，成功 ${successCount}/${totalCount} 个节点`, 'warning')
      }

      // 记录详细结果
    } catch (error) {
      console.error('[SETTINGS] Failed to sync config:', error)
      showToast(error.message || '配置同步失败', 'error')
    } finally {
      isSyncingConfig.value = false
    }
  }

  async function updateCodeToMain() {
    if (isUpdatingCode.value) {
      return
    }

    // 调试日志

    try {
      isUpdatingCode.value = true
      const { host, port } = getGatewayAddress()

      // 获取所有在线节点
      const nodeOptions = availableNodeOptions.value || []
      if (nodeOptions.length === 0) {
        showToast('没有在线节点可更新', 'warning')
        return
      }

      // 对每个节点执行更新
      let successCount = 0
      const totalCount = nodeOptions.length
      const results = []

      for (const node of nodeOptions) {
        const nodeId = node.node_id
        try {
          const response = await fetchWithAuth(`${getHttpProtocol()}://${host}:${port}/api/nodes/${nodeId}/code-update`, {
            method: 'POST'
          })
          const result = await response.json()

          if (response.ok && result.success) {
            successCount++
            results.push({
              node_id: nodeId,
              success: true,
              message: result.data?.message || '更新成功'
            })
            showToast(`已向节点 "${nodeId}" 发送更新请求`, 'success')
          } else {
            results.push({
              node_id: nodeId,
              success: false,
              message: result.error?.message || '更新失败'
            })
            showToast(`节点 "${nodeId}" 更新失败：${result.error?.message || '未知错误'}`, 'error')
          }
        } catch (error) {
          console.error(`[SETTINGS] Failed to update code for node ${nodeId}:`, error)
          results.push({
            node_id: nodeId,
            success: false,
            message: error.message || '更新失败'
          })
          showToast(`节点 "${nodeId}" 更新失败：${error.message || '未知错误'}`, 'error')
        }
      }

      // 显示结果

      if (successCount === totalCount) {
        showToast(`代码更新成功，已更新 ${successCount}/${totalCount} 个节点`, 'success')
      } else if (successCount > 0) {
        showToast(`代码更新部分成功，成功 ${successCount}/${totalCount} 个节点`, 'warning')
      } else {
        showToast('代码更新失败，没有节点更新成功', 'error')
      }
    } catch (error) {
      console.error('[SETTINGS] Failed to update code:', error)
      showToast(error.message || '代码更新失败', 'error')
    } finally {
      isUpdatingCode.value = false
    }
  }

  return {
    notifyOnExit,
    notifyOnInput,
    syncConfigSourceNode,
    syncConfigTargetNodes,
    syncConfigSections,
    isSyncingConfig,
    isUpdatingCode,
    saveNotifySettings,
    handleSyncConfig,
    handleUpdateCodeToMain,
    openAdminSystemAction,
    confirmUpdateCodeToMain,
    confirmRestartAllNodes,
    restartAllNodes,
    syncConfig,
    updateCodeToMain,
  }
}
