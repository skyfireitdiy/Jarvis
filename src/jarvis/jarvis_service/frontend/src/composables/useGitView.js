// 编辑器侧边栏 Git 视图 + diff pane 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（原 Git 视图 / diff pane 多实例管理域，6503-7202 行），
// 保持行为完全一致：
// - Git 视图状态：gitLog / gitLogLoading / gitLogError / gitLogHasMore / gitLogTotal /
//   gitBranches / gitTags / gitCurrentBranch / gitSelectedCommit / gitRangeSelectMode /
//   gitSelectedCommits / gitPatchLoading / gitCommitFiles / gitCommitDetailLoading /
//   gitSelectedFile / gitDiffText / gitDiffLoading / gitDiffError / gitDiffTruncated /
//   gitDiffSideBySide / gitDiffShowFull / pluginSidebarWorkingDir / pluginActiveAgentInfo /
//   gitCommitContextMenu / gitCommitInfoModal / GIT_LOG_PAGE_SIZE
// - 目标 Agent 解析：isNarrowGitDiffViewport / getGitTargetAgent / getGitTargetNodeId / getGitWorkingDir
// - 后端调用：callGitApi / fetchGitLog / fetchGitBranches / refreshGitView / toggleGitCommitDetail
// - 范围选择：enterGitRangeSelect / exitGitRangeSelect / toggleGitRangeSelect / downloadGitPatch
// - diff 打开：viewGitTargetDiff / onDiffTitleClick / onOpenDiffFileFromMessage / viewGitFileDiff
// - diff 全文：gitDiffFullTextCache / ensureGitDiffFullText / gitDiffOldText / gitDiffNewText
// - diff pane 多实例：layoutGitDiffEditor / disposeDiffEditorForPane / disposeAllDiffEditors /
//   ensureDiffEditorForPane / renderDiffForPane / loadDiffForPane / togglePaneDiffSideBySide /
//   togglePaneDiffShowFull / navigatePaneDiff / closePaneDiff / scheduleDiffLayout
// - 展示工具：gitRefClass / gitFileStatus / formatGitRelativeTime / shortGitHash
// - 提交右键菜单：closeGitCommitContextMenu / openGitCommitContextMenu / copyGitCommit /
//   copyGitCommitId / formatGitCommitInfo / formatGitCommitTooltip / showGitCommitInfoModal
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - 直传（定义在本 composable 调用点之前）：EDITOR_FONT_FAMILY / buildNodeHttpUrl /
//   fetchWithAuth / getGatewayAddress / getLanguageExtension / getLanguageFromFilename /
//   windowWidth / activeWorkspaceSessionId / ensurePaneForView / findWorkspacePaneById /
//   gitCustomDir / persistWorkspacePaneLayout / resolveDiffContainer / scheduleWorkspaceLayout /
//   showWorkspacePanel / workspacePaneTree / workspaceSidebarView / diffContainerRefs /
//   diffEditorViews / openWorkspaceFile / activePane / getPanePanel
// - getter 注入（定义在调用点之后，内部通过 () => xxx 求值）：effectiveGitAgentId /
//   agentList / showToast / viewDiff / copyTextToClipboard / getPanelAgent / getCurrentAgentOrNull
import { computed, nextTick, ref, triggerRef, watch } from 'vue'
import * as monaco from 'monaco-editor/esm/vs/editor/editor.main.js'
import { parseUnifiedDiff, extractDiffContext } from '../gitDiffParser.js'

export function useGitView({
  EDITOR_FONT_FAMILY,
  buildNodeHttpUrl,
  fetchWithAuth,
  getGatewayAddress,
  getLanguageExtension,
  getLanguageFromFilename,
  windowWidth,
  activeWorkspaceSessionId,
  ensurePaneForView,
  findWorkspacePaneById,
  gitCustomDir,
  persistWorkspacePaneLayout,
  resolveDiffContainer,
  scheduleWorkspaceLayout,
  showWorkspacePanel,
  workspacePaneTree,
  workspaceSidebarView,
  diffContainerRefs,
  diffEditorViews,
  openWorkspaceFile,
  activePane,
  getPanePanel,
  effectiveGitAgentId,
  agentList,
  showToast,
  viewDiff,
  copyTextToClipboard,
  getPanelAgent,
  getCurrentAgentOrNull,
}) {

// ===== 编辑器侧边栏 Git 视图（只读：提交历史/详情/diff/分支） =====
const gitLog = ref([])                 // 提交列表
const gitLogLoading = ref(false)
const gitLogError = ref('')
const gitLogHasMore = ref(false)
const gitLogTotal = ref(null)          // 仓库实际提交总数（后端 rev-list --count，首页返回）
const gitBranches = ref([])            // 分支列表
const gitTags = ref([])                // tag 列表
const gitCurrentBranch = ref('')       // 当前分支
const gitSelectedCommit = ref(null)    // 展开详情的提交 hash
const gitRangeSelectMode = ref(false)  // 是否处于范围选择模式
const gitSelectedCommits = ref(new Set()) // 范围选择模式下选中的提交 hash 集合
const gitPatchLoading = ref(false)     // 下载补丁进行中
const gitCommitFiles = ref([])         // 该提交的文件变更列表
const gitCommitDetailLoading = ref(false)
const gitSelectedFile = ref(null)      // 当前查看 diff 的文件路径
const gitDiffText = ref('')
const gitDiffLoading = ref(false)
const gitDiffError = ref('')
const gitDiffTruncated = ref(false)
// Monaco DiffEditor：并排/内联切换（桌面默认并排；移动端屏幕窄，默认内联）
const gitDiffSideBySide = ref(window.innerWidth > 768)
// diff 显示范围：false=只显示变更上下文区域（默认），true=显示文件全文
const gitDiffShowFull = ref(false)

// 当前是否处于窄屏（移动端）：diff 强制内联，避免并排两栏在窄屏上被裁掉
function isNarrowGitDiffViewport() {
  return windowWidth.value <= 768
}
const GIT_LOG_PAGE_SIZE = 100

// Git 视图作用的目标 Agent：优先 Git 侧边栏自己选中的 Agent（gitAgentId），
// 未显式选择时回退到全局当前 Agent。与编辑器会话、全局搜索互不影响。
function getGitTargetAgent() {
  const agentId = effectiveGitAgentId().value
  return agentList().value.find(a => a.agent_id === agentId) || null
}

// 取 Git 目标 Agent 的 node_id（自定义 Git 目录优先，其次目标 Agent 的 node_id）
function getGitTargetNodeId() {
  if (gitCustomDir.value?.nodeId) return String(gitCustomDir.value.nodeId).trim()
  return String(getGitTargetAgent()?.node_id || '').trim()
}

// 取 Git 工作目录（自定义 Git 目录优先，其次目标 Agent 的 working_dir）
function getGitWorkingDir() {
  if (gitCustomDir.value?.path) return String(gitCustomDir.value.path).trim()
  return String(getGitTargetAgent()?.working_dir || '').trim()
}

// 插件侧边栏（如 gh）跟随 Git 面板目标工作目录，用于解析当前仓库
const pluginSidebarWorkingDir = computed(() => getGitWorkingDir())
// 插件侧边栏注入的当前活跃 Agent 信息（与 __jarvisGetActiveAgentInfo 同源：Git 目标 Agent 优先）
const pluginActiveAgentInfo = computed(() => {
  const agentId = effectiveGitAgentId().value
  const agent = agentId ? (agentList().value.find(a => a.agent_id === agentId) || null) : null
  return agent
    ? {
        agentId: agent.agent_id,
        agentName: agent.name || agent.agent_id,
        workingDir: agent.working_dir || '',
      }
    : null
})

// 调用后端 Git 只读接口
async function callGitApi(apiPath, payload) {
  const { host, port } = getGatewayAddress()
  const targetNodeId = getGitTargetNodeId() || 'master'
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, apiPath), {
    method: 'POST',
    body: JSON.stringify({ ...payload, node_id: targetNodeId }),
  })
  const result = await response.json()
  if (!response.ok || !result.success || !result.data) {
    throw new Error(result.error?.message || 'Git 请求失败')
  }
  return result.data
}

// 拉取提交历史
async function fetchGitLog(append = false) {
  const workingDir = getGitWorkingDir()
  if (!workingDir) {
    gitLogError.value = '当前 Agent 没有工作目录'
    gitLog.value = []
    gitLogTotal.value = null
    return
  }
  gitLogLoading.value = true
  gitLogError.value = ''
  try {
    const skip = append ? gitLog.value.length : 0
    const data = await callGitApi('git/log', {
      path: workingDir,
      limit: GIT_LOG_PAGE_SIZE,
      skip,
    })
    const commits = Array.isArray(data.commits) ? data.commits : []
    gitLog.value = append ? [...gitLog.value, ...commits] : commits
    gitLogHasMore.value = Boolean(data.has_more)
    if (typeof data.total === 'number') {
      gitLogTotal.value = data.total
    }
  } catch (error) {
    gitLogError.value = error.message || '获取提交历史失败'
    if (!append) {
      gitLog.value = []
      gitLogTotal.value = null
    }
  } finally {
    gitLogLoading.value = false
  }
}

// 拉取分支/tag 列表
async function fetchGitBranches() {
  const workingDir = getGitWorkingDir()
  if (!workingDir) return
  try {
    const data = await callGitApi('git/branches', { path: workingDir })
    gitBranches.value = Array.isArray(data.branches) ? data.branches : []
    gitTags.value = Array.isArray(data.tags) ? data.tags : []
    gitCurrentBranch.value = data.current || ''
  } catch (error) {
    // 分支信息失败不阻塞提交历史展示
    gitBranches.value = []
    gitTags.value = []
    gitCurrentBranch.value = ''
  }
}

// 编辑器面板切换 Agent 时，若当前停留在 Git 视图，则按新 Agent 的工作目录重新拉取
watch(activeWorkspaceSessionId, () => {
  if (!showWorkspacePanel.value || workspaceSidebarView.value !== 'git') return
  nextTick(() => {
    refreshGitView()
  })
})

// 刷新 Git 视图（历史 + 分支）
async function refreshGitView() {
  gitSelectedCommit.value = null
  gitCommitFiles.value = []
  gitSelectedFile.value = null
  gitDiffText.value = ''
  gitDiffError.value = ''
  await Promise.all([fetchGitLog(false), fetchGitBranches()])
}

// 展开某提交的详情（文件变更列表）
async function toggleGitCommitDetail(commit) {
  if (gitSelectedCommit.value === commit.hash) {
    gitSelectedCommit.value = null
    gitCommitFiles.value = []
    gitSelectedFile.value = null
    gitDiffText.value = ''
    return
  }
  gitSelectedCommit.value = commit.hash
  gitCommitFiles.value = []
  gitSelectedFile.value = null
  gitDiffText.value = ''
  gitDiffError.value = ''
  const workingDir = getGitWorkingDir()
  if (!workingDir) return
  gitCommitDetailLoading.value = true
  try {
    const data = await callGitApi('git/commit-detail', { path: workingDir, hash: commit.hash })
    gitCommitFiles.value = Array.isArray(data.files) ? data.files : []
  } catch (error) {
    gitDiffError.value = error.message || '获取提交详情失败'
  } finally {
    gitCommitDetailLoading.value = false
  }
}

// 进入范围选择模式：清空已选，退出详情展开
function enterGitRangeSelect() {
  gitRangeSelectMode.value = true
  gitSelectedCommits.value = new Set()
  gitSelectedCommit.value = null
  gitCommitFiles.value = []
  gitSelectedFile.value = null
  gitDiffText.value = ''
}

// 退出范围选择模式
function exitGitRangeSelect() {
  gitRangeSelectMode.value = false
  gitSelectedCommits.value = new Set()
}

// 范围选择模式下切换某提交的选中状态
function toggleGitRangeSelect(commit) {
  const set = gitSelectedCommits.value
  if (set.has(commit.hash)) {
    set.delete(commit.hash)
  } else {
    set.add(commit.hash)
  }
  // 触发响应式更新
  gitSelectedCommits.value = new Set(set)
}

// 下载补丁：1 个 commit 为 .patch，多个为 .tar.gz
async function downloadGitPatch() {
  const workingDir = getGitWorkingDir()
  if (!workingDir) return
  const commits = Array.from(gitSelectedCommits.value)
  if (!commits.length) {
    showToast()('请先选择至少一个提交', 'error')
    return
  }
  gitPatchLoading.value = true
  try {
    const data = await callGitApi('git/patch', { path: workingDir, commits })
    if (!data || !data.format || !data.filename) {
      throw new Error('补丁数据无效')
    }
    let blob
    if (data.format === 'tar.gz') {
      // base64 → 二进制
      const binary = atob(data.content_base64)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
      blob = new Blob([bytes], { type: 'application/gzip' })
    } else {
      blob = new Blob([data.content], { type: 'text/plain;charset=utf-8' })
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = data.filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    showToast()(`已下载 ${data.filename}`, 'success')
  } catch (error) {
    showToast()(error.message || '下载补丁失败', 'error')
  } finally {
    gitPatchLoading.value = false
  }
}

// 在 Git 侧边栏查看当前 Git 目标 Agent 的变更（打开 diff 浮动窗口）
function viewGitTargetDiff() {
  const agent = getGitTargetAgent()
  if (!agent) {
    showToast()('请先选择 Git 目标 Agent', 'error')
    return
  }
  viewDiff()(agent)
}

// diff 标题栏文件名：点击时在编辑器面板打开该文件。
// diff 的 filePath 是相对 Git 工作目录的路径，需拼成绝对路径后再交给编辑器。
async function onDiffTitleClick(event, pane) {
  const filePath = pane?.diff?.filePath
  if (!filePath) return
  const workingDir = getGitWorkingDir()
  if (!workingDir) return
  const absPath = filePath.startsWith('/')
    ? filePath
    : `${workingDir.replace(/\/$/, '')}/${filePath.replace(/^\//, '')}`
  event.preventDefault()
  event.stopPropagation()
  await openWorkspaceFile(absPath, effectiveGitAgentId().value)
}

// 对话消息中嵌入的 diff 文件路径点击打开：
// diff 的 file_path 通常是相对路径，按承载该会话的 Agent 的 working_dir 拼成绝对路径，
// 再交给编辑器打开。找不到 Agent 工作目录时，回退到 Git 目标工作目录。
async function onOpenDiffFileFromMessage(filePath) {
  if (!filePath) return
  // 定位承载该会话的 panel：优先当前激活 pane 的 session panel
  const pane = activePane.value
  const panel = pane && pane.view === 'session' ? getPanePanel(pane) : null
  const agent = getPanelAgent()(panel) || getCurrentAgentOrNull()()
  const workingDir = String(agent?.working_dir || '').trim() || getGitWorkingDir()
  const absPath = filePath.startsWith('/')
    ? filePath
    : (workingDir ? `${workingDir.replace(/\/$/, '')}/${filePath.replace(/^\//, '')}` : filePath)
  await openWorkspaceFile(absPath, agent?.agent_id || effectiveGitAgentId().value)
}

// 查看某文件在某提交中的 diff
// 默认只显示变更上下文区域，因此先只请求 diff 文本（快），全文按需懒加载。
async function viewGitFileDiff(commitHash, filePath) {
  const workingDir = getGitWorkingDir()
  if (!workingDir) return
  gitSelectedFile.value = filePath
  gitDiffText.value = ''
  gitDiffError.value = ''
  gitDiffTruncated.value = false
  gitDiffLoading.value = true
  // 清掉上一份文件的全文缓存变量，避免在「仅上下文」模式下误用旧全文
  gitDiffOldText = ''
  gitDiffNewText = ''
  // diff 作为「面板视图」打开（与 file/session/chat/terminal 同等策略，不区分分割与否）：
  // 已存在 diff pane 则复用、当前区域空则原地创建、否则分割面积最大的 pane，
  // 避免覆盖当前区域内容。每个 pane 一个独立 DiffEditor 实例，互不干扰。
  const paneId = ensurePaneForView('diff')
  const pane = paneId ? findWorkspacePaneById(workspacePaneTree.value, paneId) : null
  if (pane) {
    // 从 diff 切到 diff（换文件）时先释放旧实例，避免复用旧 model
    disposeDiffEditorForPane(pane.id)
    pane.view = 'diff'
    pane.sessionPanelId = null
    persistWorkspacePaneLayout()
    gitDiffLoading.value = false
    await loadDiffForPane(pane.id, commitHash, filePath)
    return
  }
  // 未分割且原地创建（ensurePaneForView 返回 null）：唯一 leaf 就是主区域，
  // diff 已承载到该 leaf，统一走 pane 路径。
  const root = workspacePaneTree.value
  if (root && root.type === 'leaf') {
    disposeDiffEditorForPane(root.id)
    root.view = 'diff'
    root.sessionPanelId = null
    persistWorkspacePaneLayout()
    gitDiffLoading.value = false
    await loadDiffForPane(root.id, commitHash, filePath)
    return
  }
}

// 懒加载某文件在某提交中的两侧全文（父版本 / 当前版本），带缓存
const gitDiffFullTextCache = new Map() // key: `${commitHash}|${filePath}` -> { oldText, newText, truncated }
async function ensureGitDiffFullText(commitHash, filePath) {
  const key = `${commitHash}|${filePath}`
  const cached = gitDiffFullTextCache.get(key)
  if (cached) {
    gitDiffOldText = cached.oldText
    gitDiffNewText = cached.newText
    return cached
  }
  const workingDir = getGitWorkingDir()
  if (!workingDir) return null
  const [newData, oldData] = await Promise.all([
    callGitApi('git/file-content', { path: workingDir, ref: commitHash, file: filePath }),
    // 父版本：新增文件时父版本不存在，后端返回 NOT_FOUND，按空文件处理
    callGitApi('git/file-content', { path: workingDir, ref: `${commitHash}^`, file: filePath })
      .catch(() => ({ content: '', truncated: false })),
  ])
  const entry = {
    oldText: oldData.content || '',
    newText: newData.content || '',
    truncated: Boolean(newData.truncated || oldData.truncated),
  }
  gitDiffFullTextCache.set(key, entry)
  gitDiffOldText = entry.oldText
  gitDiffNewText = entry.newText
  return entry
}

// 两侧全文（由 git/file-content 提供）
let gitDiffOldText = ''
let gitDiffNewText = ''

// 侧栏尺寸/视图变化时重排（复用主编辑器的 layout 时机）
function layoutGitDiffEditor() {
  for (const [, entry] of diffEditorViews) {
    if (entry.editor && entry.editor.getContainerDomNode?.()?.isConnected) entry.editor.layout()
  }
}

// ===== 自由分割：diff pane 的多实例管理 =====
// 每个 diff pane 一个独立 Monaco DiffEditor；diff 数据挂在 leaf.diff 上（commitHash/filePath/loading/error/truncated/sideBySide/showFull）。

// 释放某个 diff pane 的实例与 model
function disposeDiffEditorForPane(paneId) {
  const entry = diffEditorViews.get(paneId)
  if (!entry) return
  if (entry.originalModel && !entry.originalModel.isDisposed()) entry.originalModel.dispose()
  if (entry.modifiedModel && !entry.modifiedModel.isDisposed()) entry.modifiedModel.dispose()
  if (entry.editor) entry.editor.dispose()
  diffEditorViews.delete(paneId)
}

// 释放所有 diff pane 实例（收起分割 / 关闭编辑器时调用）
function disposeAllDiffEditors() {
  for (const paneId of [...diffEditorViews.keys()]) disposeDiffEditorForPane(paneId)
  diffContainerRefs.value.clear()
  triggerRef(diffContainerRefs)
}

// 确保某个 diff pane 的编辑器实例存在（容器被替换时销毁重建）
function ensureDiffEditorForPane(paneId) {
  const container = resolveDiffContainer(paneId)
  if (!container) return null
  let entry = diffEditorViews.get(paneId)
  if (entry && entry.editor && entry.editor.getContainerDomNode() !== container) {
    disposeDiffEditorForPane(paneId)
    entry = null
  }
  if (entry) return entry
  const editor = monaco.editor.createDiffEditor(container, {
    theme: 'blueDark',
    fontFamily: EDITOR_FONT_FAMILY,
    fontSize: 12,
    lineHeight: 18,
    readOnly: true,
    originalEditable: false,
    automaticLayout: true,
    renderSideBySide: gitDiffSideBySide.value && !isNarrowGitDiffViewport(),
    useInlineViewWhenSpaceIsLimited: isNarrowGitDiffViewport(),
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    renderOverviewRuler: false,
    renderWhitespace: 'selection',
    smoothScrolling: true,
    folding: false,
    lineNumbersMinChars: 3,
    wordWrap: isNarrowGitDiffViewport() ? 'on' : 'off',
  })
  entry = { editor, originalModel: null, modifiedModel: null, oldText: '', newText: '' }
  diffEditorViews.set(paneId, entry)
  return entry
}

// 用该 pane 的 diff 数据渲染 Monaco（容器未就绪时轮询等待）
async function renderDiffForPane(paneId) {
  const pane = findWorkspacePaneById(workspacePaneTree.value, paneId)
  if (!pane || pane.view !== 'diff' || !pane.diff) return
  let container = resolveDiffContainer(paneId)
  for (let i = 0; !container && i < 10; i++) {
    await new Promise(resolve => setTimeout(resolve, 50))
    container = resolveDiffContainer(paneId)
  }
  if (!container) return
  // 等待期间 pane 可能已切走/关闭
  const current = findWorkspacePaneById(workspacePaneTree.value, paneId)
  if (!current || current.view !== 'diff' || !current.diff) return
  const diff = current.diff
  try {
    const entry = ensureDiffEditorForPane(paneId)
    if (!entry) return
    const language = getLanguageExtension(getLanguageFromFilename(diff.filePath))
    let oldText = entry.oldText
    let newText = entry.newText
    if (!oldText && !newText) {
      const parsed = parseUnifiedDiff(diff.diffText || '', { absoluteLineNumbers: true })
      oldText = parsed.oldText
      newText = parsed.newText
    }
    // 默认只显示变更上下文区域
    if (!diff.showFull && diff.diffText) {
      const context = extractDiffContext(diff.diffText)
      if (context.oldText || context.newText) {
        oldText = context.oldText
        newText = context.newText
      }
    }
    if (entry.originalModel && !entry.originalModel.isDisposed()) entry.originalModel.dispose()
    if (entry.modifiedModel && !entry.modifiedModel.isDisposed()) entry.modifiedModel.dispose()
    entry.originalModel = monaco.editor.createModel(oldText, language)
    entry.modifiedModel = monaco.editor.createModel(newText, language)
    entry.editor.setModel({ original: entry.originalModel, modified: entry.modifiedModel })
    entry.editor.updateOptions({ renderSideBySide: diff.sideBySide && !isNarrowGitDiffViewport() })
    entry.editor.layout()
  } catch (error) {
    console.warn('[GIT] render pane diff with monaco failed:', error)
    diff.error = `diff 渲染失败：${error?.message || error}`
  }
}

// 为某个 pane 加载并渲染 diff（写 leaf.diff 后调用）
async function loadDiffForPane(paneId, commitHash, filePath) {
  const pane = findWorkspacePaneById(workspacePaneTree.value, paneId)
  if (!pane || pane.view !== 'diff') return
  const workingDir = getGitWorkingDir()
  if (!workingDir) return
  pane.diff = {
    commitHash,
    filePath,
    diffText: '',
    loading: true,
    error: '',
    truncated: false,
    sideBySide: gitDiffSideBySide.value,
    showFull: gitDiffShowFull.value,
  }
  try {
    const diffData = await callGitApi('git/diff', { path: workingDir, hash: commitHash, file: filePath })
    // 等待期间 pane 可能已切走/关闭
    const current = findWorkspacePaneById(workspacePaneTree.value, paneId)
    if (!current || current.view !== 'diff' || !current.diff) return
    current.diff.diffText = diffData.diff || ''
    current.diff.truncated = Boolean(diffData.truncated)
    if (current.diff.showFull) {
      const entry = await ensureGitDiffFullText(commitHash, filePath)
      if (entry) current.diff.truncated = Boolean(current.diff.truncated || entry.truncated)
      const e = diffEditorViews.get(paneId)
      if (e) { e.oldText = gitDiffOldText; e.newText = gitDiffNewText }
    }
    current.diff.loading = false
    await nextTick()
    await renderDiffForPane(paneId)
  } catch (error) {
    const current = findWorkspacePaneById(workspacePaneTree.value, paneId)
    if (current && current.diff) {
      current.diff.loading = false
      current.diff.error = error.message || '获取 diff 失败'
    }
  }
}

// diff pane 内切换「并排 / 内联」
function togglePaneDiffSideBySide(paneId) {
  const pane = findWorkspacePaneById(workspacePaneTree.value, paneId)
  if (!pane || !pane.diff) return
  pane.diff.sideBySide = !pane.diff.sideBySide
  const entry = diffEditorViews.get(paneId)
  if (entry) entry.editor.updateOptions({ renderSideBySide: pane.diff.sideBySide && !isNarrowGitDiffViewport() })
}

// diff pane 内切换「全文 / 仅上下文」
async function togglePaneDiffShowFull(paneId) {
  const pane = findWorkspacePaneById(workspacePaneTree.value, paneId)
  if (!pane || !pane.diff) return
  pane.diff.showFull = !pane.diff.showFull
  const entry = diffEditorViews.get(paneId)
  if (pane.diff.showFull) {
    const { commitHash, filePath } = pane.diff
    const key = `${commitHash}|${filePath}`
    if (!gitDiffFullTextCache.has(key)) {
      pane.diff.loading = true
      try {
        const full = await ensureGitDiffFullText(commitHash, filePath)
        if (full) pane.diff.truncated = Boolean(pane.diff.truncated || full.truncated)
      } catch (error) {
        pane.diff.error = error.message || '获取文件全文失败'
        pane.diff.loading = false
        return
      } finally {
        pane.diff.loading = false
      }
    } else {
      await ensureGitDiffFullText(commitHash, filePath)
    }
    if (entry) { entry.oldText = gitDiffOldText; entry.newText = gitDiffNewText }
    await nextTick()
  } else if (entry) {
    // 切回「仅上下文」：清掉全文缓存变量，避免误用旧全文
    entry.oldText = ''
    entry.newText = ''
  }
  await renderDiffForPane(paneId)
}

// diff pane 内跳转上一个 / 下一个差异
function navigatePaneDiff(paneId, direction) {
  const entry = diffEditorViews.get(paneId)
  if (!entry || !entry.editor) return
  const target = direction === 'prev' ? 'previous' : 'next'
  if (typeof entry.editor.goToDiff === 'function') entry.editor.goToDiff(target)
}

// 关闭某个 diff pane 的 diff（回到空 pane）
function closePaneDiff(paneId) {
  const pane = findWorkspacePaneById(workspacePaneTree.value, paneId)
  if (!pane) return
  disposeDiffEditorForPane(paneId)
  pane.diff = null
  pane.view = 'empty'
  persistWorkspacePaneLayout()
  nextTick(() => scheduleWorkspaceLayout())
}

// 显式 layout 合并到下一帧，避免同一帧内对多个 diff 实例反复 layout 造成尺寸震荡
let diffLayoutScheduled = false
function scheduleDiffLayout() {
  if (diffLayoutScheduled) return
  diffLayoutScheduled = true
  requestAnimationFrame(() => {
    diffLayoutScheduled = false
    for (const [, entry] of diffEditorViews) {
      if (entry.editor && entry.editor.getContainerDomNode?.()?.isConnected) entry.editor.layout()
    }
  })
}

// 提交信息中的 refs 标签：区分 HEAD/分支/tag 样式
function gitRefClass(refName) {
  if (refName.startsWith('HEAD')) return 'git-ref-head'
  if (refName.startsWith('tag:')) return 'git-ref-tag'
  return 'git-ref-branch'
}

// 由增删行数推断文件变更状态（后端只返回增删统计，无 status）
function gitFileStatus(file) {
  const additions = Number(file?.additions) || 0
  const deletions = Number(file?.deletions) || 0
  if (additions > 0 && deletions === 0) return 'A'
  if (deletions > 0 && additions === 0) return 'D'
  return 'M'
}

// 提交相对时间（如 3 分钟前）
function formatGitRelativeTime(isoDate) {
  const time = Date.parse(isoDate)
  if (!time) return ''
  const diffSeconds = Math.floor((Date.now() - time) / 1000)
  if (diffSeconds < 60) return '刚刚'
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} 分钟前`
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)} 小时前`
  if (diffSeconds < 2592000) return `${Math.floor(diffSeconds / 86400)} 天前`
  if (diffSeconds < 31536000) return `${Math.floor(diffSeconds / 2592000)} 个月前`
  return `${Math.floor(diffSeconds / 31536000)} 年前`
}

// 短 hash（前 7 位）
function shortGitHash(hash) {
  return String(hash || '').slice(0, 7)
}


// ===== 编辑器目录树右键菜单 =====

// ===== Git 提交右键菜单 =====
const gitCommitContextMenu = ref({ visible: false, x: 0, y: 0, commit: null })

function closeGitCommitContextMenu() {
  if (gitCommitContextMenu.value.visible) {
    gitCommitContextMenu.value = { ...gitCommitContextMenu.value, visible: false }
  }
}

// 在 Git 提交项上右键：就地弹出菜单（视口坐标 + 边界收敛）
function openGitCommitContextMenu(commit, event) {
  if (!commit || !event) return
  const MENU_W = 220
  const MENU_H = 120
  let x = event.clientX
  let y = event.clientY
  if (x + MENU_W > window.innerWidth) x = Math.max(window.innerWidth - MENU_W, 0)
  if (y + MENU_H > window.innerHeight) y = Math.max(window.innerHeight - MENU_H, 0)
  gitCommitContextMenu.value = { visible: true, x, y, commit }
  // 点击菜单外部时关闭（一次性监听）
  nextTick(() => {
    document.addEventListener('pointerdown', closeGitCommitContextMenu, { once: true })
  })
}

// 复制完整 commit 信息到剪贴板
async function copyGitCommit(commit) {
  if (!commit) return
  closeGitCommitContextMenu()
  try {
    await copyTextToClipboard()(formatGitCommitInfo(commit))
    showToast()('已复制 commit 信息')
  } catch (e) {
    showToast()('复制失败', 'error')
  }
}

// 复制 commit ID（完整 hash）到剪贴板
async function copyGitCommitId(commit) {
  if (!commit) return
  closeGitCommitContextMenu()
  try {
    await copyTextToClipboard()(commit.hash)
    showToast()('已复制 commit ID')
  } catch (e) {
    showToast()('复制失败', 'error')
  }
}

// 组装完整 commit 信息（hash + subject + body + author + email + date + refs）
function formatGitCommitInfo(commit) {
  const lines = []
  lines.push(`commit ${commit.hash}`)
  if (commit.refs && commit.refs.length) lines.push(`refs: ${commit.refs.join(', ')}`)
  lines.push(`Author: ${commit.author} <${commit.email}>`)
  lines.push(`Date:   ${commit.date}`)
  lines.push('')
  lines.push(commit.subject)
  if (commit.body) {
    lines.push('')
    lines.push(commit.body)
  }
  return lines.join('\n')
}

// 悬停/长按提示：完整 commit 信息（单行 subject 之外补全 body 与元信息）
function formatGitCommitTooltip(commit) {
  if (!commit) return ''
  return formatGitCommitInfo(commit)
}

// 移动端「详情」弹窗：当前展示的 commit（null 表示关闭）
const gitCommitInfoModal = ref(null)

function showGitCommitInfoModal(commit) {
  if (!commit) return
  gitCommitInfoModal.value = commit
}


  return {
    // refs
    gitLog,
    gitLogLoading,
    gitLogError,
    gitLogHasMore,
    gitLogTotal,
    gitBranches,
    gitTags,
    gitCurrentBranch,
    gitSelectedCommit,
    gitRangeSelectMode,
    gitSelectedCommits,
    gitPatchLoading,
    gitCommitFiles,
    gitCommitDetailLoading,
    gitSelectedFile,
    gitDiffText,
    gitDiffLoading,
    gitDiffError,
    gitDiffTruncated,
    gitDiffSideBySide,
    gitDiffShowFull,
    pluginSidebarWorkingDir,
    pluginActiveAgentInfo,
    gitCommitContextMenu,
    gitCommitInfoModal,
    // 常量
    GIT_LOG_PAGE_SIZE,
    // 函数
    isNarrowGitDiffViewport,
    getGitTargetAgent,
    getGitTargetNodeId,
    getGitWorkingDir,
    callGitApi,
    fetchGitLog,
    fetchGitBranches,
    refreshGitView,
    toggleGitCommitDetail,
    enterGitRangeSelect,
    exitGitRangeSelect,
    toggleGitRangeSelect,
    downloadGitPatch,
    viewGitTargetDiff,
    onDiffTitleClick,
    onOpenDiffFileFromMessage,
    viewGitFileDiff,
    ensureGitDiffFullText,
    layoutGitDiffEditor,
    disposeDiffEditorForPane,
    disposeAllDiffEditors,
    ensureDiffEditorForPane,
    renderDiffForPane,
    loadDiffForPane,
    togglePaneDiffSideBySide,
    togglePaneDiffShowFull,
    navigatePaneDiff,
    closePaneDiff,
    scheduleDiffLayout,
    gitRefClass,
    gitFileStatus,
    formatGitRelativeTime,
    shortGitHash,
    closeGitCommitContextMenu,
    openGitCommitContextMenu,
    copyGitCommit,
    copyGitCommitId,
    formatGitCommitInfo,
    formatGitCommitTooltip,
    showGitCommitInfoModal,
  }
}
