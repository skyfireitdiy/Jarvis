// 编排 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 9），保持行为完全一致：
// - 状态：showOrchestrateModal / orchestrateNodeId / orchestrateFilePath / orchestrateAgents / ...（编排弹窗全部 ref）
// - 解析/创建：parseOrchestrationFile / createAllOrchestrateAgents / runOrchestration / previewOrchestration / handleApproval
// - 文件浏览：fetchOrchestrateEntries / toggleOrchestrateBrowser / 键盘导航 / 本地文件上传
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - agentList / hasNoPanel / openAgentInPanel / showToast / showWorkspaceSidebar / setWorkspaceSidebarView
// - getGatewayAddress / fetchWithAuth / buildNodeHttpUrl / availableNodeOptions / filteredNodeOptionsForCreateAgent / getDefaultCreateAgentNodeId
// - pipelineStore / pipelineVersion（App.vue 定义）
// - readFileAsDataUrl（useFileTree 返回）
// - useAgents 返回：createAgentWithOptions / fetchAgentList / fetchNodeStatus / dirDialogContext / openDirDialog / startAgentListRefresh
//
// 注意：orchestrateAgents / orchestrateActiveIndex / orchestrateNodeId 同时被 useAgents 的
// openDirDialog / confirmDirectory / getCreateAgentDirectoryNodeId 读取，故由本 composable 返回，
// useAgents 通过 getter 注入（useOrchestrate 在 useAgents 之后调用）。
import { ref, computed, watch, nextTick } from 'vue'

export function useOrchestrate({
  agentList,
  availableNodeOptions,
  buildNodeHttpUrl,
  fetchWithAuth,
  filteredNodeOptionsForCreateAgent,
  getDefaultCreateAgentNodeId,
  getGatewayAddress,
  hasNoPanel,
  openAgentInPanel,
  pipelineStore,
  pipelineVersion,
  setWorkspaceSidebarView,
  showToast,
  showWorkspaceSidebar,
  readFileAsDataUrl,
  // useAgents 返回（useOrchestrate 在 useAgents 之后调用，直接传引用）
  createAgentWithOptions,
  fetchAgentList,
  fetchNodeStatus,
  dirDialogContext,
  openDirDialog,
  startAgentListRefresh,
}) {
  const showOrchestrateModal = ref(false)          // 编排弹窗
  const orchestrateNodeId = ref('master')          // 编排文件所在节点（也是创建 Agent 的默认节点）
  const orchestrateFilePath = ref('')              // 编排文件绝对路径
  const orchestratePluginTemplates = ref([])        // 插件声明的编排模板列表 [{plugin,name,description,file}]
  const orchestratePluginTemplatesLoading = ref(false) // 插件编排模板加载中
  const orchestrateRecentFiles = ref([])            // 最近使用过的编排文件列表 [{path,nodeId}]（localStorage 持久化）
  const ORCHESTRATE_RECENT_KEY = 'jarvis_recent_orchestrations' // 最近编排文件 localStorage 键
  const ORCHESTRATE_RECENT_MAX = 20                // 最近编排文件最多保留条数
  const orchestrateAgents = ref([])                // 解析出的 Agent 表单列表（每项对应一个标签页）
  const orchestrateHasFlow = ref(false)            // 编排文件是否含 flow 字段（决定「运行流水线」还是「创建 Agent」）
  const orchestrateNodes = ref([])                 // 解析出的 DAG 节点（预览静态图用，不执行）
  const orchestrateActiveIndex = ref(0)            // 当前激活的标签页索引
  const orchestrateLoading = ref(false)            // 解析中
  const orchestrateError = ref('')                 // 解析错误
  const orchestrateCreating = ref(false)           // 批量创建中
  const orchestrateResults = ref([])               // 批量创建结果 [{ name, ok, error }]
  // 运行流水线（与 Agent 调用 pipeline_runner 同一路径，驱动 DAG 可视化）
  const orchestrateRunWorkingDir = ref('')         // 运行流水线的工作目录（产物 .jarvis/artifacts/ 在其中创建）
  const orchestrateRunning = ref(false)            // 运行流水线中（仅表示已提交，实际进度由事件驱动）
  // 编排文件浏览面板：目录 + 文件合并列表（复用 DirectoryDialog，fileSelectable 模式）
  const orchestrateFileEntries = ref([])           // 当前目录下的目录与文件项（{name,path,type}）
  const orchestrateSelectedFile = ref('')          // 面板中当前选中的文件路径
  const orchestrateDialogRef = ref(null)           // 内嵌 DirectoryDialog 引用
  const orchestrateShowBrowser = ref(false)        // 是否展开文件浏览面板
  const orchestrateCurrentDirPath = ref('')        // 浏览面板当前目录路径
  const orchestrateLocalFileInput = ref(null)       // 从本机选择编排文件的隐藏 file input
  const orchestrateDirSearchText = ref('')         // 浏览面板搜索文本
  const orchestrateSelectedIndex = ref(-1)         // 浏览面板键盘导航选中项索引（-1 未选中）
  // 编排文件允许的扩展名（仅展示这些文件供选择）：.yaml/.yml=组织编排，.flow=流程编排
  const ORCHESTRATE_FILE_EXTENSIONS = ['.yaml', '.yml', '.flow']

  // 把编排文件里的单个 agent 配置映射为可编辑表单对象（字段缺失时按后端默认值兜底）
  function buildOrchestrateAgentForm(raw = {}, fallbackNodeId = 'master') {
    const acl = raw.access_acl && typeof raw.access_acl === 'object' ? raw.access_acl : {}
    return {
      name: String(raw.name || ''),
      workingDir: String(raw.working_dir || '.'),
      llmGroup: String(raw.llm_group || 'default'),
      toolGroup: String(raw.tool_group || 'default'),
      task: String(raw.task || ''),
      additionalArgs: String(raw.additional_args || ''),
      quickMode: !!raw.quick_mode,
      restoreSession: !!raw.restore_session,
      noInteractionMode: !!raw.no_interaction_mode,
      nodeId: String(raw.node_id || fallbackNodeId || 'master'),
      proxyNode: String(raw.proxy_node || ''),
      accessAclRead: Array.isArray(acl.read) ? acl.read.map(String) : [],
      accessAclInteract: Array.isArray(acl.interact) ? acl.interact.map(String) : [],
    }
  }

  // 打开编排弹窗：加载节点选项并初始化默认节点
  async function openOrchestrateModal() {
    orchestrateError.value = ''
    orchestrateResults.value = []
    orchestrateAgents.value = []
    orchestrateHasFlow.value = false
    orchestrateNodes.value = []
    orchestrateActiveIndex.value = 0
    orchestrateFilePath.value = ''
    showOrchestrateModal.value = true
    if (!availableNodeOptions.value.length) {
      try { await fetchNodeStatus() } catch (error) { /* 失败时保持空列表，弹窗内会提示 */ }
    }
    const allowed = filteredNodeOptionsForCreateAgent.value
    orchestrateNodeId.value = allowed.some(n => n.node_id === orchestrateNodeId.value)
      ? orchestrateNodeId.value
      : (getDefaultCreateAgentNodeId() || 'master')
    // 拉取当前节点上插件声明的编排模板，供用户直接选择
    loadOrchestratePluginTemplates()
    // 加载最近使用过的编排文件历史
    loadOrchestrateRecentFiles()
  }

  function closeOrchestrateModal() {
    showOrchestrateModal.value = false
    orchestrateError.value = ''
    orchestrateResults.value = []
    orchestrateAgents.value = []
    orchestrateHasFlow.value = false
    orchestrateNodes.value = []
    orchestrateActiveIndex.value = 0
    orchestrateFilePath.value = ''
    orchestratePluginTemplates.value = []
    orchestratePluginTemplatesLoading.value = false
    // 复位文件浏览面板状态
    orchestrateShowBrowser.value = false
    orchestrateFileEntries.value = []
    orchestrateSelectedFile.value = ''
    orchestrateCurrentDirPath.value = ''
    orchestrateDirSearchText.value = ''
    orchestrateSelectedIndex.value = -1
    // 复位目录选择场景，避免污染创建 Agent 的「选择目录」
    dirDialogContext.value = 'create-agent'
  }

  // 最近使用编排文件管理（localStorage 持久化）
  // 元素格式：{ path: string, nodeId: string }，按节点区分
  function loadOrchestrateRecentFiles() {
    try {
      const stored = localStorage.getItem(ORCHESTRATE_RECENT_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        const isValid = Array.isArray(parsed) && parsed.every(item =>
          item && typeof item === 'object' && typeof item.path === 'string' && typeof item.nodeId === 'string'
        )
        orchestrateRecentFiles.value = isValid ? parsed : []
      } else {
        orchestrateRecentFiles.value = []
      }
    } catch (error) {
      console.error('[ORCHESTRATE] 加载最近编排文件失败:', error)
      orchestrateRecentFiles.value = []
    }
  }

  // 记录一次成功解析/使用的编排文件到最近历史
  function saveOrchestrateRecentFile(path, nodeId) {
    const normalizedPath = String(path || '').trim()
    if (!normalizedPath) return
    const normalizedNodeId = String(nodeId || '').trim() || 'master'
    // 去重：过滤掉已存在的同节点同路径
    const filtered = orchestrateRecentFiles.value.filter(item =>
      !(item.path === normalizedPath && item.nodeId === normalizedNodeId)
    )
    orchestrateRecentFiles.value = [{ path: normalizedPath, nodeId: normalizedNodeId }, ...filtered].slice(0, ORCHESTRATE_RECENT_MAX)
    try {
      localStorage.setItem(ORCHESTRATE_RECENT_KEY, JSON.stringify(orchestrateRecentFiles.value))
    } catch (error) {
      console.error('[ORCHESTRATE] 保存最近编排文件失败:', error)
    }
  }

  // 从最近历史中删除一条
  function removeOrchestrateRecentFile(path, nodeId) {
    const normalizedPath = String(path || '').trim()
    const normalizedNodeId = String(nodeId || '').trim() || 'master'
    orchestrateRecentFiles.value = orchestrateRecentFiles.value.filter(item =>
      !(item.path === normalizedPath && item.nodeId === normalizedNodeId)
    )
    try {
      localStorage.setItem(ORCHESTRATE_RECENT_KEY, JSON.stringify(orchestrateRecentFiles.value))
    } catch (error) {
      console.error('[ORCHESTRATE] 删除最近编排文件失败:', error)
    }
  }

  // 选择一条最近使用的编排文件：填入路径并立即解析
  function selectOrchestrateRecentFile(item) {
    if (!item || !item.path) return
    orchestrateFilePath.value = item.path
    parseOrchestrationFile()
  }

  // 拉取当前节点上插件声明的编排模板列表（供用户直接选择，无需手动输入路径）
  async function loadOrchestratePluginTemplates() {
    orchestratePluginTemplatesLoading.value = true
    orchestratePluginTemplates.value = []
    try {
      const { host, port } = getGatewayAddress()
      const nodeId = String(orchestrateNodeId.value || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, nodeId, 'plugins/orchestrations'))
      const result = await response.json().catch(() => ({}))
      if (!response.ok || !result.success || !result.data) {
        orchestratePluginTemplates.value = []
        return
      }
      const templates = Array.isArray(result.data.orchestrations) ? result.data.orchestrations : []
      orchestratePluginTemplates.value = templates.filter(t => t && t.file)
    } catch (error) {
      orchestratePluginTemplates.value = []
    } finally {
      orchestratePluginTemplatesLoading.value = false
    }
  }

  // 选择插件编排模板：填入路径并立即解析
  function selectOrchestratePluginTemplate(tpl) {
    if (!tpl || !tpl.file) return
    orchestrateFilePath.value = tpl.file
    parseOrchestrationFile()
  }

  // 解析编排文件：调后端接口读取 YAML 并取出 agents 列表
  async function parseOrchestrationFile() {
    const path = String(orchestrateFilePath.value || '').trim()
    if (!path) {
      orchestrateError.value = '请输入编排文件路径'
      return
    }
    orchestrateLoading.value = true
    orchestrateError.value = ''
    orchestrateResults.value = []
    try {
      const { host, port } = getGatewayAddress()
      const nodeId = String(orchestrateNodeId.value || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, nodeId, 'parse-orchestration'), {
        method: 'POST',
        body: JSON.stringify({ path, node_id: nodeId }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok || !result.success || !result.data) {
        orchestrateError.value = result.error?.message || '解析编排文件失败'
        return
      }
      const agents = Array.isArray(result.data.agents) ? result.data.agents : []
      if (!agents.length) {
        orchestrateError.value = '编排文件中没有 agents'
        return
      }
      orchestrateAgents.value = agents.map(raw => buildOrchestrateAgentForm(raw, nodeId))
      // 仅 .flow 流程编排走流水线；.yaml/.yml 为组织编排，一律按批量创建处理，忽略其 flow 字段
      const isFlowOrchestration = String(result.data.path || path).toLowerCase().endsWith('.flow')
      orchestrateHasFlow.value = isFlowOrchestration && !!result.data.has_flow
      orchestrateNodes.value = Array.isArray(result.data.nodes) ? result.data.nodes : []
      orchestrateFilePath.value = String(result.data.path || path)
      orchestrateActiveIndex.value = 0
      // 记录最近使用过的编排文件历史
      saveOrchestrateRecentFile(orchestrateFilePath.value, orchestrateNodeId.value)
    } catch (error) {
      orchestrateError.value = error.message || '解析编排文件失败'
    } finally {
      orchestrateLoading.value = false
    }
  }

  // 新增一个空白 Agent 标签页
  function addOrchestrateAgent() {
    orchestrateAgents.value.push(buildOrchestrateAgentForm({}, orchestrateNodeId.value))
    orchestrateActiveIndex.value = orchestrateAgents.value.length - 1
  }

  // 删除指定标签页的 Agent
  function removeOrchestrateAgent(index) {
    if (index < 0 || index >= orchestrateAgents.value.length) return
    orchestrateAgents.value.splice(index, 1)
    if (orchestrateActiveIndex.value >= orchestrateAgents.value.length) {
      orchestrateActiveIndex.value = Math.max(0, orchestrateAgents.value.length - 1)
    }
  }

  // 一键创建：逐个调用 createAgentWithOptions，汇总每个 Agent 的结果
  async function createAllOrchestrateAgents() {
    if (orchestrateCreating.value) return
    if (!orchestrateAgents.value.length) {
      orchestrateError.value = '没有可创建的 Agent'
      return
    }
    // 创建前统一校验：工作目录必填；非交互模式必须有任务描述
    for (let i = 0; i < orchestrateAgents.value.length; i++) {
      const form = orchestrateAgents.value[i]
      const label = form.name || form.workingDir || `Agent ${i + 1}`
      if (!String(form.workingDir || '').trim()) {
        orchestrateError.value = `「${label}」工作目录不能为空`
        orchestrateActiveIndex.value = i
        return
      }
      if (form.noInteractionMode && !String(form.task || '').trim()) {
        orchestrateError.value = `「${label}」启用了无交互模式，必须填写任务描述`
        orchestrateActiveIndex.value = i
        return
      }
    }
    orchestrateCreating.value = true
    orchestrateError.value = ''
    orchestrateResults.value = []
    const created = []
    try {
      for (const form of orchestrateAgents.value) {
        const result = await createAgentWithOptions({
          agentType: 'agent',
          workingDir: form.workingDir,
          name: form.name,
          llmGroup: form.llmGroup,
          quickMode: form.quickMode,
          restoreSession: form.restoreSession,
          noInteractionMode: form.noInteractionMode,
          // 任务描述与是否无交互模式无关：填写即传给 Agent（无交互模式仅额外要求任务必填）
          task: form.task,
          nodeId: form.nodeId,
          proxyNode: form.proxyNode,
          accessAclRead: form.accessAclRead,
          accessAclInteract: form.accessAclInteract,
          toolGroup: form.toolGroup,
          additionalArgs: form.additionalArgs,
        })
        orchestrateResults.value.push({
          name: form.name || form.workingDir || '未命名',
          ok: !!result.ok,
          error: result.ok ? '' : (result.error || '创建失败'),
        })
        if (result.ok) created.push(result.agent)
      }
      // 全部成功则关闭弹窗并收尾（加入列表、刷新、按场景打开 Panel）
      const allOk = orchestrateResults.value.every(r => r.ok)
      if (allOk && created.length) {
        showOrchestrateModal.value = false
        orchestrateAgents.value = []
        orchestrateResults.value = []
        for (const agent of created) {
          agentList.value.unshift(agent)
        }
        await fetchAgentList()
        startAgentListRefresh()
        if (!hasNoPanel.value && created[0]) {
          await openAgentInPanel(created[0])
        }
        showToast(`已创建 ${created.length} 个 Agent`, 'success')
      } else {
        const okCount = orchestrateResults.value.filter(r => r.ok).length
        if (okCount) {
          // 部分成功：刷新列表，保留失败项供用户修正后重试
          await fetchAgentList()
          startAgentListRefresh()
        }
        showToast(`创建完成：成功 ${okCount}/${orchestrateResults.value.length}`, okCount ? 'warning' : 'error')
      }
    } finally {
      orchestrateCreating.value = false
    }
  }

  // 为当前编排标签页选择工作目录：复用目录选择弹窗（orchestrate 场景）
  function openOrchestrateDirDialog() {
    if (!orchestrateAgents.value.length) return
    dirDialogContext.value = 'orchestrate'
    openDirDialog()
  }

  // 运行流水线：调用后端 /run-orchestration（与 Agent 调用 pipeline_runner 同一路径），
  // 运行进度经 pipeline_event 事件驱动 OrchestrationView 的 DAG 可视化。
  async function runOrchestration() {
    if (orchestrateRunning.value) return
    const orchestrationFile = String(orchestrateFilePath.value || '').trim()
    if (!orchestrationFile) {
      orchestrateError.value = '请先选择并解析编排文件'
      return
    }
    // 编排文件顶层 spec 字段由后端读取，作为各阶段 Agent 背景
    orchestrateRunning.value = true
    orchestrateError.value = ''
    try {
      const { host, port } = getGatewayAddress()
      const nodeId = String(orchestrateNodeId.value || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, nodeId, 'run-orchestration'), {
        method: 'POST',
        body: JSON.stringify({
          orchestration_file: orchestrationFile,
          working_dir: String(orchestrateRunWorkingDir.value || '').trim(),
          node_id: nodeId,
        }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok || !result.success) {
        orchestrateError.value = result.error?.message || '运行流水线失败'
        return
      }
      showToast('流水线已启动，可在「编排查看」中查看进度', 'success')
      // 关闭弹窗，让用户直接看到 DAG 可视化（事件到达后自动刷新）
      closeOrchestrateModal()
      showWorkspaceSidebar.value = true
      setWorkspaceSidebarView('orchestration')
    } catch (error) {
      orchestrateError.value = error.message || '运行流水线失败'
    } finally {
      orchestrateRunning.value = false
    }
  }

  // 预览：用解析出的 DAG 节点绘制静态图（不执行、不创建 Agent），直接加入 pipelineStore 并切到「编排查看」。
  function previewOrchestration() {
    const nodes = orchestrateNodes.value
    if (!nodes.length) {
      orchestrateError.value = '没有可预览的 DAG 节点，请先解析编排文件'
      return
    }
    const orchestrationFile = String(orchestrateFilePath.value || '').trim()
    const pid = `preview_${Date.now()}`
    pipelineStore.addPreview(pid, nodes, orchestrationFile)
    pipelineVersion.value++ // 触发 pipelineList computed 重算，让编排查看立即渲染新预览
    showToast('已生成编排预览（静态 DAG，未执行）', 'success')
    closeOrchestrateModal()
    showWorkspaceSidebar.value = true
    setWorkspaceSidebarView('orchestration')
  }
  // 门禁人工审批：记录决定（放行/拒绝/重试），放行/重试时以 approve=true 重跑流水线。
  // 由 OrchestrationView 审批浮层触发（参数 { pipelineId, note }）。
  async function handleApproval(action, { pipelineId, note = '' } = {}) {
    if (!pipelineId) return
    const pipeline = pipelineStore.getPipeline(pipelineId)
    if (!pipeline) {
      showToast('未找到该流水线记录', 'error')
      return
    }
    const { host, port } = getGatewayAddress()
    // 1) 先记录审批决定（POST /api/pipeline-approval，master 网关）
    try {
      const resp = await fetchWithAuth(buildNodeHttpUrl(host, port, 'master', 'pipeline-approval'), {
        method: 'POST',
        body: JSON.stringify({ pipeline_id: pipelineId, action, note }),
      })
      const result = await resp.json().catch(() => ({}))
      if (!resp.ok || !result.success) {
        showToast(result.error?.message || '记录审批决定失败', 'error')
        return
      }
    } catch (error) {
      showToast(error.message || '记录审批决定失败', 'error')
      return
    }
    const actionLabel = { approve: '放行', reject: '拒绝', retry: '重试' }[action] || action
    // 2) 放行/重试：以 approve=true 重跑流水线（门禁确认通过后继续后续阶段）
    if (action === 'approve' || action === 'retry') {
      const orchestrationFile = String(pipeline.orchestrationFile || '').trim()
      const workingDir = String(pipeline.workingDir || '').trim()
      if (!orchestrationFile) {
        showToast('流水线缺少编排文件，无法重跑', 'error')
        return
      }
      try {
        const resp = await fetchWithAuth(buildNodeHttpUrl(host, port, 'master', 'run-orchestration'), {
          method: 'POST',
          body: JSON.stringify({
            orchestration_file: orchestrationFile,
            working_dir: workingDir,
            node_id: 'master',
            approve: true,
          }),
        })
        const result = await resp.json().catch(() => ({}))
        if (!resp.ok || !result.success) {
          showToast(result.error?.message || '重跑流水线失败', 'error')
          return
        }
        showToast(`已${actionLabel}，流水线已重跑`, 'success')
      } catch (error) {
        showToast(error.message || '重跑流水线失败', 'error')
        return
      }
    } else {
      showToast(`已${actionLabel}`, 'success')
    }
  }
  // ===== 编排文件浏览面板（节点下拉 + 内嵌目录/文件浏览，参考「打开目录」）=====
  // 目录项（供 DirectoryDialog 的 filteredDirs 使用，支持搜索过滤）
  const orchestrateFilteredDirs = computed(() => {
    const dirs = orchestrateFileEntries.value.filter(item => item.type === 'directory')
    return filterOrchestrateEntries(dirs)
  })
  // 文件项（仅展示允许的扩展名，支持搜索过滤）
  const orchestrateFilteredFiles = computed(() => {
    const files = orchestrateFileEntries.value.filter(item => item.type === 'file' && isOrchestrateFile(item.name))
    return filterOrchestrateEntries(files)
  })
  // 键盘导航用的统一顺序列表：目录在前、文件在后（与面板渲染顺序一致）
  const orchestrateNavItems = computed(() => [
    ...orchestrateFilteredDirs.value.map(d => ({ type: 'directory', path: d.path })),
    ...orchestrateFilteredFiles.value.map(f => ({ type: 'file', path: f.path })),
  ])
  function isOrchestrateFile(name) {
    const lower = String(name || '').toLowerCase()
    return ORCHESTRATE_FILE_EXTENSIONS.some(ext => lower.endsWith(ext))
  }
  function filterOrchestrateEntries(items) {
    const keyword = String(orchestrateDirSearchText.value || '').toLowerCase().trim()
    if (!keyword) return items
    return items.filter(item =>
      String(item.name || '').toLowerCase().includes(keyword) ||
      String(item.path || '').toLowerCase().includes(keyword)
    )
  }
  // 拉取指定目录下的目录与文件（保留文件，与 fetchDirectories 的「仅目录」行为隔离）
  async function fetchOrchestrateEntries(path = '') {
    try {
      const { host, port } = getGatewayAddress()
      const params = new URLSearchParams({ path })
      const nodeId = String(orchestrateNodeId.value || 'master').trim() || 'master'
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, nodeId, `directories?${params.toString()}`))
      if (!response.ok) {
        const error = await response.json().catch(() => ({}))
        orchestrateError.value = error.error?.message || '获取目录列表失败'
        return
      }
      const result = await response.json()
      if (result.success && result.data) {
        orchestrateCurrentDirPath.value = result.data.current_path || ''
        orchestrateFileEntries.value = Array.isArray(result.data.items) ? result.data.items : []
      }
    } catch (error) {
      orchestrateError.value = error.message || '获取目录列表出错'
    }
  }
  // 展开/收起编排文件浏览面板
  async function toggleOrchestrateBrowser() {
    orchestrateShowBrowser.value = !orchestrateShowBrowser.value
    if (!orchestrateShowBrowser.value) return
    orchestrateDirSearchText.value = ''
    orchestrateSelectedFile.value = ''
    orchestrateSelectedIndex.value = -1
    await fetchOrchestrateEntries(orchestrateInitialBrowsePath())
  }
  // 计算浏览初始路径：已填路径为文件时取父目录，否则取自身；为空则从家目录开始
  function orchestrateInitialBrowsePath() {
    const filled = String(orchestrateFilePath.value || '').trim()
    if (!filled) return '~'
    if (isOrchestrateFile(filled)) {
      const idx = filled.replace(/\\/g, '/').lastIndexOf('/')
      return idx > 0 ? filled.slice(0, idx) : '~'
    }
    return filled
  }
  // 在面板中进入某目录
  async function enterOrchestrateDir(path) {
    orchestrateSelectedFile.value = ''
    orchestrateDirSearchText.value = ''
    orchestrateSelectedIndex.value = -1
    await fetchOrchestrateEntries(path)
  }
  // 返回上级目录
  async function goToOrchestrateParentDir() {
    const normalized = String(orchestrateCurrentDirPath.value || '').replace(/\\/g, '/')
    const parts = normalized.split('/').filter(p => p)
    if (!parts.length) return
    parts.pop()
    orchestrateSelectedIndex.value = -1
    await fetchOrchestrateEntries('/' + parts.join('/'))
  }
  // 选中文件：回填编排文件路径
  function onOrchestrateSelectFile(path) {
    orchestrateSelectedFile.value = path
    orchestrateFilePath.value = path
  }
  // 打开本机文件选择框
  function onOrchestrateLocalSelect() {
    const input = orchestrateLocalFileInput.value
    if (!input) return
    input.value = ''
    input.click()
  }
  // 本机选中编排文件：上传到所选节点后回填节点路径并解析
  async function onOrchestrateLocalFileChange(event) {
    const input = event?.target
    const file = input?.files?.[0]
    if (input) input.value = ''
    if (!file) return
    const nodeId = String(orchestrateNodeId.value || 'master').trim() || 'master'
    orchestrateError.value = ''
    try {
      // 上传目标目录：优先当前浏览目录（已打开浏览面板时）；否则拉取家目录绝对路径
      let baseDir = String(orchestrateCurrentDirPath.value || '').replace(/\/+$/, '')
      if (!baseDir) {
        await fetchOrchestrateEntries('~')
        baseDir = String(orchestrateCurrentDirPath.value || '').replace(/\/+$/, '')
      }
      if (!baseDir) {
        orchestrateError.value = '无法确定上传目录，请先打开「浏览」选择目标目录'
        return
      }
      const data = await readFileAsDataUrl(file)
      const { host, port } = getGatewayAddress()
      const targetPath = `${baseDir}/${file.name}`
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, nodeId, 'file-upload'), {
        method: 'POST',
        body: JSON.stringify({ path: targetPath, data, node_id: nodeId }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok || !result.success) {
        throw new Error(result.error?.message || '上传失败')
      }
      orchestrateFilePath.value = targetPath
      showToast(`已上传到 ${targetPath}`, 'success')
      parseOrchestrationFile()
    } catch (error) {
      orchestrateError.value = error.message || '上传本地编排文件失败'
    }
  }
  // 浏览面板搜索框键盘事件：Esc 收起面板；上下键在目录/文件列表中导航；回车进入目录或选中文件
  function handleOrchestrateSearchKeydown(event) {
    if (event.key === 'Escape') {
      orchestrateShowBrowser.value = false
      event.preventDefault()
      return
    }
    // 带 Ctrl/Alt/Meta 修饰键时不做列表导航
    if (event.ctrlKey || event.altKey || event.metaKey) return
    const items = orchestrateNavItems.value
    const maxIndex = items.length - 1

    if (event.key === 'ArrowDown') {
      if (orchestrateSelectedIndex.value < maxIndex) {
        orchestrateSelectedIndex.value++
      } else if (orchestrateSelectedIndex.value === -1 && maxIndex >= 0) {
        orchestrateSelectedIndex.value = 0
      }
      syncOrchestrateKeyboardSelection()
      scrollToOrchestrateSelected()
      event.preventDefault()
      return
    }
    if (event.key === 'ArrowUp') {
      if (orchestrateSelectedIndex.value > 0) {
        orchestrateSelectedIndex.value--
      } else if (orchestrateSelectedIndex.value === -1) {
        orchestrateSelectedIndex.value = maxIndex
      } else {
        orchestrateSelectedIndex.value = -1
      }
      syncOrchestrateKeyboardSelection()
      scrollToOrchestrateSelected()
      event.preventDefault()
      return
    }
    if (event.key === 'Enter') {
      const item = items[orchestrateSelectedIndex.value]
      if (item) {
        if (item.type === 'directory') {
          enterOrchestrateDir(item.path)
        } else {
          onOrchestrateSelectFile(item.path)
        }
        event.preventDefault()
      }
    }
  }
  // 键盘导航高亮同步：目录项高亮用 selectedDir，文件项高亮用 selectedFile
  const orchestrateHighlightedDir = computed(() => {
    const item = orchestrateNavItems.value[orchestrateSelectedIndex.value]
    return item && item.type === 'directory' ? item.path : ''
  })
  const orchestrateHighlightedFile = computed(() => {
    const item = orchestrateNavItems.value[orchestrateSelectedIndex.value]
    return item && item.type === 'file' ? item.path : ''
  })
  // 把当前键盘选中项同步到 DirectoryDialog 的高亮 props
  function syncOrchestrateKeyboardSelection() {
    const item = orchestrateNavItems.value[orchestrateSelectedIndex.value]
    if (item && item.type === 'file') {
      orchestrateSelectedFile.value = item.path
    }
  }
  // 滚动到键盘选中的列表项（DirectoryDialog 内 .dir-item.selected）
  function scrollToOrchestrateSelected() {
    nextTick(() => {
      const el = orchestrateDialogRef.value?.$el?.querySelector?.('.dir-item.selected')
      el?.scrollIntoView?.({ block: 'nearest' })
    })
  }
  // 搜索文本变化时重置键盘选中索引（过滤后列表已变，旧索引无意义）
  watch(orchestrateDirSearchText, () => {
    orchestrateSelectedIndex.value = -1
  })
  // 切换编排节点：重新拉取文件列表
  async function onOrchestrateNodeChange() {
    orchestrateFilePath.value = ''
    orchestrateSelectedFile.value = ''
    orchestrateSelectedIndex.value = -1
    // 节点切换后重新拉取该节点上的插件编排模板
    loadOrchestratePluginTemplates()
    if (orchestrateShowBrowser.value) {
      await fetchOrchestrateEntries('~')
    }
  }

  return {
    // ref
    showOrchestrateModal,
    orchestrateNodeId,
    orchestrateFilePath,
    orchestratePluginTemplates,
    orchestratePluginTemplatesLoading,
    orchestrateRecentFiles,
    orchestrateAgents,
    orchestrateHasFlow,
    orchestrateNodes,
    orchestrateActiveIndex,
    orchestrateLoading,
    orchestrateError,
    orchestrateCreating,
    orchestrateResults,
    orchestrateRunWorkingDir,
    orchestrateRunning,
    orchestrateFileEntries,
    orchestrateSelectedFile,
    orchestrateDialogRef,
    orchestrateShowBrowser,
    orchestrateCurrentDirPath,
    orchestrateLocalFileInput,
    orchestrateDirSearchText,
    orchestrateSelectedIndex,
    orchestrateFilteredDirs,
    orchestrateFilteredFiles,
    orchestrateNavItems,
    orchestrateHighlightedDir,
    orchestrateHighlightedFile,
    // 函数
    buildOrchestrateAgentForm,
    openOrchestrateModal,
    closeOrchestrateModal,
    loadOrchestrateRecentFiles,
    saveOrchestrateRecentFile,
    removeOrchestrateRecentFile,
    selectOrchestrateRecentFile,
    loadOrchestratePluginTemplates,
    selectOrchestratePluginTemplate,
    parseOrchestrationFile,
    addOrchestrateAgent,
    removeOrchestrateAgent,
    createAllOrchestrateAgents,
    openOrchestrateDirDialog,
    runOrchestration,
    previewOrchestration,
    handleApproval,
    isOrchestrateFile,
    filterOrchestrateEntries,
    fetchOrchestrateEntries,
    toggleOrchestrateBrowser,
    orchestrateInitialBrowsePath,
    enterOrchestrateDir,
    goToOrchestrateParentDir,
    onOrchestrateSelectFile,
    onOrchestrateLocalSelect,
    onOrchestrateLocalFileChange,
    handleOrchestrateSearchKeydown,
    syncOrchestrateKeyboardSelection,
    scrollToOrchestrateSelected,
    onOrchestrateNodeChange,
    // 常量
    ORCHESTRATE_RECENT_KEY,
    ORCHESTRATE_RECENT_MAX,
    ORCHESTRATE_FILE_EXTENSIONS,
  }
}
