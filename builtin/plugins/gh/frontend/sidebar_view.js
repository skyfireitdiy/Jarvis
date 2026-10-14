// gh 插件前端侧边栏视图。
// 约定：纯浏览器 ES module，用 window.Vue 渲染，导出 default 组件，不 import 'vue'。
// 功能：浏览/操作当前仓库的 Issue 与 Pull Request。
// 认证：读操作匿名可用；写操作（评论/关闭/合并）需 GitHub token。
//       token 复用 GitHub 官方 gh CLI 登录态（gh auth login），由服务端 gh 插件
//       私有功能读取，前端通过插件功能代理端点调用，不直接访问 api.github.com，
//       也不在浏览器保存 GitHub token。

const PLUGIN = "gh";
// 当前解析出的仓库（owner/repo），由 resolveRepo 根据 workingDir 动态确定。
// 初始为空：不硬编码默认仓库，避免插件发布后其他用户看到固定仓库。
let currentRepo = "";
// 手动切换的仓库（owner/repo）。为空表示跟随 workingDir 自动解析；
// 非空表示用户显式指定了其他仓库，此时不再被 resolveRepo 覆盖。
let manualRepo = "";
// 记住手动指定的仓库，刷新页面后仍生效（key 按插件固定）。
const MANUAL_REPO_KEY = "jarvis_gh_manual_repo";
// 最近手动指定过的仓库历史（JSON 数组，最多 10 条，最近使用在前），用于快速选择切换。
const REPO_HISTORY_KEY = "jarvis_gh_repo_history";
const REPO_HISTORY_MAX = 10;
// 当前平台：'auto' 跟随仓库 remote 自动识别；'github'/'gitee' 为显式指定。
// 手动指定仓库时（无法从 workingDir 识别）建议显式选择平台。
let currentPlatform = "auto";
// 记住平台选择，刷新页面后仍生效。
const PLATFORM_KEY = "jarvis_gh_platform";

// 复刻 App.vue 的 gateway 地址解析（侧边栏组件无 props 注入，需自行解析）
function parseGatewayAddress(address) {
  address = (address || "").trim();
  if (!address) return null;
  if (address.includes("://")) {
    try {
      const url = new URL(address);
      return {
        protocol: url.protocol.replace(":", ""),
        host: url.hostname,
        port:
          url.port ||
          (url.protocol === "https:" || url.protocol === "wss:" ? "443" : "80"),
        path: url.pathname,
      };
    } catch {
      return null;
    }
  }
  if (address.includes(":")) {
    const parts = address.split(":");
    if (parts.length === 2) {
      return { protocol: null, host: parts[0], port: parts[1], path: "" };
    }
  }
  return { protocol: null, host: address, port: "8000", path: "" };
}

// 获取当前页面的 HTTP 协议（与 App.vue getHttpProtocol 一致）
function getHttpProtocol() {
  return window.location.protocol === "https:" ? "https" : "http";
}

function gatewayBase() {
  const parsed = parseGatewayAddress(
    localStorage.getItem("jarvis_gateway_url") || "",
  );
  const host = (parsed && parsed.host) || "127.0.0.1";
  const port = (parsed && parsed.port) || "8000";
  // 协议：显式指定（https）则用之；否则用当前页面协议（与 App.vue 一致），
  // 避免 HTTPS 页面请求 http 地址导致混合内容被浏览器阻止。
  const protocol =
    parsed && parsed.protocol === "https" ? "https" : getHttpProtocol();
  return `${protocol}://${host}:${port}`;
}

// 通过 gateway 插件功能代理端点调用插件私有功能
// nodeId 指定目标节点（默认 master）：gh 功能（gh CLI / git / 仓库解析）在所选节点本地执行
// platform 指定平台（auto/github/gitee，默认 auto 由后端按仓库 remote 识别）
async function callFunction(functionName, args, nodeId, platform) {
  // 统一走 App.vue 暴露的带认证请求函数 window.__jarvisFetch（自动携带 jarvis
  // 认证信息，token 不暴露给插件）；若宿主未注入则回退到普通 fetch。
  const authedFetch =
    (typeof window !== "undefined" && window.__jarvisFetch) || fetch;
  // 除 resolve_repo 外，其余函数都需指定 repo；未解析到仓库时传空，
  // 由后端返回明确错误提示。
  const noRepoFns = ["resolve_repo", "auth_status", "auth_login"];
  const callArgs = args || {};
  if (!noRepoFns.includes(functionName) && !callArgs.repo) {
    callArgs.repo = currentRepo;
  }
  // 平台透传：显式指定时传给后端；auto 时不传（后端按仓库 remote 自动识别）
  if (platform && String(platform).trim() && String(platform).trim() !== "auto") {
    callArgs.platform = String(platform).trim();
  }
  const targetNodeId = String(nodeId || "master").trim() || "master";
  const resp = await authedFetch(
    `${gatewayBase()}/api/plugins/${encodeURIComponent(targetNodeId)}/function-call`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plugin: PLUGIN,
        function: functionName,
        arguments: callArgs,
      }),
    },
  );
  let result;
  try {
    result = await resp.json();
  } catch (e) {
    throw new Error("网关响应异常", { cause: e });
  }
  if (!result.success) {
    const err = result.error || {};
    throw new Error(err.message || err.code || "调用失败");
  }
  const payload = result.result || {};
  if (payload.success === false) {
    throw new Error(payload.error || "操作失败");
  }
  return payload;
}

export default {
  name: "GhSidebarView",
  props: {
    workingDir: { type: String, default: "" },
  },
  data() {
    return {
      repo: currentRepo,
      repoInput: "",
      repoEditing: false,
      // 节点列表与当前节点（master 恒在列）；gh 功能在所选节点本地执行
      nodes: [],
      nodeId: "master",
      // 当前平台：auto 跟随仓库 remote 自动识别；github/gitee 显式指定
      platform: currentPlatform,
      // 是否处于「手动指定的自定义仓库」：为真表示当前展示的仓库不是当前
      // Agent 工作目录对应的仓库，此时不应把 issue/PR 交给当前 Agent 处理
      // （Agent 的工作目录属于另一个仓库，gh 命令会在错误仓库上执行）。
      isManualRepo: false,
      // 最近手动指定过的仓库历史（最多 10 条，最近使用在前），用于快速选择切换。
      repoHistory: [],
      // 当前目标 Agent 名称（宿主 __jarvisGetActiveAgentInfo 提供；无则空）。
      // 用于 header 与右键菜单标注「在当前 Agent 中处理」的实际接收者。
      agentName: "",
      tab: "issues",
      loading: false,
      loadingMore: false,
      error: "",
      items: [],
      // 分页状态：page 为当前已加载到的页码，hasMore 表示是否还有下一页，
      // total 为后端推断的总条数（用于「已加载 N / 共 M 条」提示）。
      page: 1,
      hasMore: false,
      total: 0,
      selected: null,
      comments: [],
      // 操作
      commentText: "",
      busy: false,
      message: "",
      // 列表项右键菜单
      menuVisible: false,
      menuStyle: {},
      menuItem: null,
      // 帮助弹层：展示插件使用条件（非开箱即用，需配置 CLI 与登录）
      helpVisible: false,
      // 认证表单状态（帮助弹层内）：authStatus 为 null 表示尚未查询；
      // authenticated 为 true 时显示「已登录 xxx」，否则显示认证表单。
      authStatus: null,
      authLoading: false,
      authBusy: false,
      authToken: "",
      // 认证表单的平台（默认跟随当前平台；auto 时用 github）
      authPlatform: currentPlatform === "gitee" ? "gitee" : "github",
      // 认证表单的节点（默认跟随当前节点）
      authNodeId: "master",
    };
  },
  mounted() {
    this.initNodes();
    this.restoreManualRepo();
    this.restorePlatform();
    this.refreshAgentName();
    this.resolveRepo().then(() => this.refresh());
    // 订阅宿主 agent_changed 事件：切换 Agent 时即使 workingDir 不变（同目录切换），
    // 顶部「当前 Agent」也能同步更新（watch workingDir 只在值变化时触发）。
    const on = typeof window !== "undefined" && window.__jarvisOn;
    if (typeof on === "function") {
      this._offAgentChanged = on("agent_changed", () => {
        this.refreshAgentName();
      });
    }
    // 点击别处 / 按 Esc 关闭右键菜单
    this._onDocClick = () => this.closeItemMenu();
    this._onDocKeydown = (e) => {
      if (e.key === "Escape") this.closeItemMenu();
    };
    document.addEventListener("click", this._onDocClick);
    document.addEventListener("keydown", this._onDocKeydown);
  },
  beforeUnmount() {
    if (typeof this._offAgentChanged === "function") this._offAgentChanged();
    document.removeEventListener("click", this._onDocClick);
    document.removeEventListener("keydown", this._onDocKeydown);
  },
  watch: {
    workingDir() {
      // agent 切换仓库时重新解析并刷新；目标 Agent 可能随之变化，同步刷新名称
      this.refreshAgentName();
      this.resolveRepo().then(() => this.refresh());
    },
  },
  methods: {
    // ---- 节点管理 ----
    // 加载节点列表（__jarvisGetNodes，master 恒在列），并恢复上次选中的节点
    initNodes() {
      const getNodes =
        typeof window !== "undefined" && window.__jarvisGetNodes;
      if (typeof getNodes !== "function") {
        this.nodes = [{ node_id: "master", status: "running" }];
        return;
      }
      try {
        const list = getNodes() || [];
        const nodes = Array.isArray(list)
          ? list.filter((n) => n && String(n.node_id || "").trim())
          : [];
        // 确保 master 恒在列
        if (!nodes.some((n) => n.node_id === "master")) {
          nodes.unshift({ node_id: "master", status: "running" });
        }
        this.nodes = nodes;
      } catch {
        this.nodes = [{ node_id: "master", status: "running" }];
        return;
      }
      // 恢复上次选中的节点（若仍存在）
      let savedNode = "master";
      try {
        savedNode = (localStorage.getItem("jarvis_gh_node") || "master").trim() || "master";
      } catch {
        /* 忽略 */
      }
      if (this.nodes.some((n) => n.node_id === savedNode)) {
        this.nodeId = savedNode;
      } else {
        this.nodeId = this.nodes[0]?.node_id || "master";
      }
    },
    // 切换节点：保存选择并重新解析仓库、刷新列表
    onNodeChange(nodeId) {
      this.nodeId = String(nodeId || "master").trim() || "master";
      try {
        localStorage.setItem("jarvis_gh_node", this.nodeId);
      } catch {
        /* 忽略 */
      }
      this.resolveRepo().then(() => this.refresh());
    },
    // 节点展示名：优先宿主自定义名，否则回退 node_id
    nodeLabel(node) {
      if (!node) return "master";
      return (node.display_name || node.name || node.node_id || "master");
    },
    // 按节点 ID 取展示名（模板用，避免模板内写复杂表达式）
    nodeLabelById(nodeId) {
      const target = String(nodeId || "master").trim() || "master";
      const found = this.nodes.find((n) => n && n.node_id === target);
      return this.nodeLabel(found || { node_id: target });
    },
    // 从宿主获取当前目标 Agent 名称（与「在当前 Agent 中处理」的实际接收者一致）。
    // 宿主未提供接口时静默置空（不阻塞插件其余功能）。
    refreshAgentName() {
      const getInfo =
        typeof window !== "undefined" && window.__jarvisGetActiveAgentInfo;
      if (typeof getInfo !== "function") {
        this.agentName = "";
        return;
      }
      try {
        const info = getInfo() || {};
        this.agentName = (info && info.agentName) || "";
      } catch {
        this.agentName = "";
      }
    },
    async resolveRepo() {
      // 手动指定的仓库优先：不再被 workingDir 自动解析覆盖。
      if (manualRepo) {
        currentRepo = manualRepo;
        this.repo = currentRepo;
        this.repoInput = currentRepo;
        this.isManualRepo = true;
        return;
      }
      try {
        const payload = await callFunction("resolve_repo", {
          working_dir: this.workingDir || "",
          platform: this.platform,
        }, this.nodeId);
        currentRepo = (payload && payload.repo) || "";
        this.repo = currentRepo;
        this.repoInput = currentRepo;
        // 后端返回识别出的平台；显式指定（github/gitee）时以后端为准
        if (payload && payload.platform) {
          currentPlatform = payload.platform;
          this.platform = payload.platform;
        }
      } catch {
        // 解析失败：清空仓库（不硬编码默认仓库）
        currentRepo = "";
        this.repo = "";
        this.repoInput = "";
      }
      this.isManualRepo = false;
    },
    // 从 localStorage 恢复上次手动指定的仓库（刷新页面后仍生效）。
    restoreManualRepo() {
      try {
        const saved = (localStorage.getItem(MANUAL_REPO_KEY) || "").trim();
        if (saved) manualRepo = saved;
      } catch {
        /* localStorage 不可用时忽略 */
      }
    },
    // 从 localStorage 恢复上次选择的平台（刷新页面后仍生效）。
    restorePlatform() {
      try {
        const saved = (localStorage.getItem(PLATFORM_KEY) || "auto").trim();
        if (["auto", "github", "gitee"].includes(saved)) {
          currentPlatform = saved;
          this.platform = saved;
        }
      } catch {
        /* localStorage 不可用时忽略 */
      }
    },
    // 切换平台：保存选择并刷新列表。
    onPlatformChange(platform) {
      currentPlatform = String(platform || "auto").trim() || "auto";
      this.platform = currentPlatform;
      try {
        localStorage.setItem(PLATFORM_KEY, currentPlatform);
      } catch {
        /* 忽略 */
      }
      // 跟随目录时重新解析平台；手动仓库时直接刷新
      if (!manualRepo) {
        this.resolveRepo().then(() => this.refresh());
      } else {
        this.refresh();
      }
    },
    // 读取最近手动指定过的仓库历史（最多 REPO_HISTORY_MAX 条，最近使用在前）。
    // 存储损坏/不可用时返回空数组，不影响主流程。
    getRepoHistory() {
      try {
        const raw = localStorage.getItem(REPO_HISTORY_KEY);
        if (!raw) return [];
        const list = JSON.parse(raw);
        if (!Array.isArray(list)) return [];
        return list
          .filter((r) => typeof r === "string")
          .map((r) => r.trim())
          .filter(Boolean)
          .slice(0, REPO_HISTORY_MAX);
      } catch {
        return [];
      }
    },
    // 把仓库写入历史：去重（已存在则移到最前）、按最近使用排序、截断到上限。
    saveRepoHistory(repo) {
      try {
        const list = this.getRepoHistory().filter((r) => r !== repo);
        list.unshift(repo);
        localStorage.setItem(
          REPO_HISTORY_KEY,
          JSON.stringify(list.slice(0, REPO_HISTORY_MAX)),
        );
      } catch {
        /* 忽略存储失败 */
      }
    },
    // 规范化用户输入的仓库：去空白、去 .git 后缀，校验 owner/repo 两段格式。
    // 返回规范化后的 owner/repo；非法时返回空字符串。
    normalizeRepoInput(raw) {
      let value = String(raw || "").trim();
      if (value.endsWith(".git")) value = value.slice(0, -4);
      // 允许粘贴完整 URL / ssh 地址，提取 owner/repo
      if (value.includes("://")) {
        // https://github.com/owner/repo 或 ssh://git@github.com/owner/repo
        value = value.replace(/^[a-z]+:\/\//i, "");
        value = value.replace(/^[^@/]*@/, "");
        value = value.replace(/^[^/]+\//, "");
      } else if (value.includes("@")) {
        // scp 风格 git@github.com:owner/repo
        value = value.replace(/^[^@/]*@/, "");
        value = value.replace(/^[^:/]+\//, "");
        const colon = value.indexOf(":");
        if (colon !== -1) value = value.slice(colon + 1);
      }
      value = value.replace(/^\/+|\/+$/g, "");
      const parts = value.split("/").filter((p) => p);
      if (parts.length !== 2) return "";
      if (!/^[\w.-]+$/.test(parts[0]) || !/^[\w.-]+$/.test(parts[1])) return "";
      return `${parts[0]}/${parts[1]}`;
    },
    // 切换到用户输入的仓库。
    setRepo() {
      const normalized = this.normalizeRepoInput(this.repoInput);
      if (!normalized) {
        this.error = "仓库格式不正确，请填写 owner/repo（如 octocat/Hello-World）";
        return;
      }
      this.error = "";
      manualRepo = normalized;
      try {
        localStorage.setItem(MANUAL_REPO_KEY, normalized);
      } catch {
        /* 忽略存储失败 */
      }
      this.saveRepoHistory(normalized);
      currentRepo = normalized;
      this.repo = normalized;
      this.repoInput = normalized;
      this.isManualRepo = true;
      this.repoEditing = false;
      this.refresh();
    },
    // 从历史中快速选择仓库并切换（与 setRepo 等效，无需重新输入）。
    selectRepoHistory(repo) {
      this.repoInput = repo;
      this.setRepo();
    },
    // 恢复为「跟随当前工作目录」自动解析的仓库。
    useCurrentDirRepo() {
      manualRepo = "";
      try {
        localStorage.removeItem(MANUAL_REPO_KEY);
      } catch {
        /* 忽略 */
      }
      this.repoEditing = false;
      this.resolveRepo().then(() => this.refresh());
    },
    toggleRepoEdit() {
      this.repoEditing = !this.repoEditing;
      if (this.repoEditing) {
        this.repoInput = this.repo || "";
        this.error = "";
        this.repoHistory = this.getRepoHistory();
      }
    },
    fmtDate(s) {
      if (!s) return "";
      try {
        return new Date(s).toLocaleString();
      } catch {
        return s;
      }
    },
    // 把后端返回的原始条目规范化为列表项。
    mapItem(it) {
      return {
        number: it.number,
        title: it.title,
        state: it.state,
        user: it.user,
        created_at: it.created_at,
        updated_at: it.updated_at,
        body: it.body || "",
        html_url: it.html_url,
        comments: it.comments,
      };
    },
    async refresh() {
      this.loading = true;
      this.error = "";
      this.message = "";
      // 切换/刷新瞬间先清空列表，避免请求失败时残留上一个仓库的数据
      this.items = [];
      this.page = 1;
      this.hasMore = false;
      this.total = 0;
      this.selected = null;
      this.comments = [];
      try {
        const fn = this.tab === "issues" ? "list_issues" : "list_prs";
        const payload = await callFunction(fn, { state: "open", page: 1 }, this.nodeId, this.platform);
        this.items = (payload.data || []).map((it) => this.mapItem(it));
        this.page = payload.page || 1;
        this.hasMore = !!payload.has_more;
        this.total = payload.total || this.items.length;
        this.selected = null;
        this.comments = [];
      } catch (e) {
        this.error = String((e && e.message) || e);
      } finally {
        this.loading = false;
      }
    },
    // 加载下一页并追加到列表（分页展示，避免一次性拉取过多）。
    async loadMore() {
      if (this.loadingMore || !this.hasMore) return;
      this.loadingMore = true;
      this.error = "";
      try {
        const fn = this.tab === "issues" ? "list_issues" : "list_prs";
        const nextPage = this.page + 1;
        const payload = await callFunction(fn, {
          state: "open",
          page: nextPage,
        }, this.nodeId, this.platform);
        const more = (payload.data || []).map((it) => this.mapItem(it));
        // 去重：避免分页边界重复（如翻页期间数据变动）
        const seen = new Set(this.items.map((it) => it.number));
        for (const it of more) {
          if (!seen.has(it.number)) {
            this.items.push(it);
            seen.add(it.number);
          }
        }
        this.page = payload.page || nextPage;
        this.hasMore = !!payload.has_more;
        this.total = payload.total || this.items.length;
      } catch (e) {
        this.error = String((e && e.message) || e);
      } finally {
        this.loadingMore = false;
      }
    },
    async openItem(item) {
      this.selected = item;
      this.commentText = "";
      this.message = "";
      try {
        const fn = this.tab === "issues" ? "get_issue" : "get_pr";
        const detail = await callFunction(fn, { number: item.number }, this.nodeId, this.platform);
        this.selected.body = ((detail.data && detail.data.body) || "").trim();
        const comments = await callFunction("list_comments", {
          number: item.number,
        }, this.nodeId, this.platform);
        this.comments = Array.isArray(comments.data) ? comments.data : [];
      } catch (e) {
        this.error = String((e && e.message) || e);
      }
    },
    back() {
      this.selected = null;
      this.comments = [];
    },
    // ---- 列表项右键菜单 ----
    openItemMenu(item, event) {
      this.menuItem = item;
      const menuWidth = 140;
      const menuHeight = 40;
      let left = event.clientX;
      let top = event.clientY;
      // 不超出视口右下缘
      if (left + menuWidth > window.innerWidth - 8) {
        left = window.innerWidth - menuWidth - 8;
      }
      if (left < 8) left = 8;
      if (top + menuHeight > window.innerHeight - 8) {
        top = window.innerHeight - menuHeight - 8;
      }
      if (top < 8) top = 8;
      this.menuStyle = { left: left + "px", top: top + "px" };
      this.menuVisible = true;
    },
    closeItemMenu() {
      this.menuVisible = false;
      this.menuItem = null;
    },
    // 生成处理该 issue/PR 的提示词。
    // isFork=true 时用于「Fork 并创建 CodeAgent 处理」：目标是修改代码后向上游原仓库提 PR。
    buildItemPrompt(item, isFork = false) {
      const isIssue = this.tab === "issues";
      const repo = currentRepo || "(当前仓库)";
      const number = item.number;
      const title = item.title || "";
      // 平台对应的 CLI 命令与平台名（Gitee 用 gitee CLI，GitHub 用 gh CLI）
      const isGitee = this.platform === "gitee";
      const cli = isGitee ? "gitee" : "gh";
      const platformName = isGitee ? "Gitee" : "GitHub";
      if (isFork) {
        // 自定义仓库（fork 的他人仓库）：非本仓库，目标是改代码后向上游提 PR
        const head = `请处理 ${platformName} ${isIssue ? "Issue" : "Pull Request"} #${number}：${title}`;
        const upstream = [
          `目标仓库 ${repo} 不是我们的仓库，而是其他开源项目的仓库。`,
          "本地目录是 fork 的 clone（origin 指向你的 fork，upstream 已配置指向原仓库）。",
          "目标是：修改代码修复问题，然后向上游原仓库提交 Pull Request。",
        ].join("\n");
        const flow = [
          "开源贡献流程：",
          "1. 从上游主干切出特性分支：`git fetch upstream && git checkout -b fix/issue-<编号> upstream/<上游主干>`。",
          "2. 在分支上完成改动，遵循相关开发规则（含测试）。",
          "3. 用 `commit` 工具生成正式提交。",
          `4. 推送分支到 fork：\`git push origin <分支名>\`。`,
          `5. 向上游提 PR：\`${cli} pr create --repo ${repo} --head <你的fork>:<分支名> --base <上游主干> --title <标题>\`，并在描述中用 \`Closes #${number}\` 关联该 Issue。`,
          "6. 写操作（评论/关闭/合并）前先与我确认，再执行。",
        ].join("\n");
        return [head, "", upstream, "", flow].join("\n");
      }
      return isIssue
        ? [
            `请处理当前仓库 ${repo} 的 ${platformName} Issue #${number}：${title}`,
            "",
            "遵循 gh_rule 处理该 Issue：",
            `1. 用 \`${cli} issue view ${number}\` 查看该 Issue 详情（标题、作者、body、labels、状态），先复述内容确认理解正确。`,
            "2. 阅读 body 与现有评论，判断问题类型并形成处理方案。",
            "3. 如需写码实现，遵循 gh_rule 与相关开发规则完成修改。",
            "4. 写操作（评论/关闭）前先与我确认，再执行。",
          ].join("\n")
        : [
            `请处理当前仓库 ${repo} 的 ${platformName} Pull Request #${number}：${title}`,
            "",
            "遵循 gh_rule 处理该 PR：",
            `1. 用 \`${cli} pr view ${number}\` 与 \`${cli} pr diff ${number}\` 查看详情与改动。`,
            "2. 评估是否可合并或需修改；如需修改，遵循 gh_rule 与相关开发规则补齐实现/测试。",
            "3. 合并前先与我确认（含合并方式），再执行。",
          ].join("\n");
    },
    // 在当前活跃 Agent 中处理该 issue/PR
    async handleItem(item) {
      this.closeItemMenu();
      if (!item) return;
      // 防御性校验：自定义仓库与当前 Agent 工作目录不一致，交给当前 Agent
      // 会在错误仓库上执行 gh 命令，故直接拒绝（UI 已隐藏该入口）。
      if (this.isManualRepo) {
        this.message = "当前为自定义仓库，与 Agent 工作目录不一致，请改用「创建新 Agent 处理」";
        return;
      }
      const isIssue = this.tab === "issues";
      const kind = isIssue ? "Issue" : "Pull Request";
      const number = item.number;
      const send =
        typeof window !== "undefined" && window.__jarvisSendToActiveAgent;
      if (typeof send !== "function") {
        this.message = "宿主未提供发送通道，无法处理";
        return;
      }
      const res = send(this.buildItemPrompt(item));
      if (res && res.success) {
        this.message = `已把 ${kind} #${number} 的处理提示词发送给当前 Agent`;
      } else {
        this.message = "失败: " + ((res && res.error) || "发送失败");
      }
    },
    // 创建新普通 Agent 处理该 issue/PR
    async handleItemNewAgent(item) {
      this.closeItemMenu();
      if (!item) return;
      const isIssue = this.tab === "issues";
      const kind = isIssue ? "Issue" : "Pull Request";
      const number = item.number;
      // 优先使用「打开创建 Agent 弹窗（带预填）」通道，让用户确认/编辑后再创建；
      // 宿主未提供新通道时回退到直接创建通道（向后兼容）。
      const openModal =
        typeof window !== "undefined" && window.__jarvisOpenCreateAgentModal;
      const create =
        typeof window !== "undefined" && window.__jarvisCreateAgentForTask;
      if (typeof openModal !== "function" && typeof create !== "function") {
        this.message = "宿主未提供创建通道，无法创建 Agent";
        return;
      }
      const workingDir = (this.workingDir || "").trim();
      if (!workingDir) {
        this.message = "失败: 未解析到工作目录";
        return;
      }
      this.busy = true;
      this.message = `正在创建新 Agent 处理 ${kind} #${number}…`;
      try {
        const prefill = {
          workingDir: workingDir,
          task: this.buildItemPrompt(item),
          name: `${kind} #${number}`,
          nodeId: this.nodeId,
        };
        if (typeof openModal === "function") {
          const res = await openModal(prefill);
          if (res && res.confirmed) {
            this.message = `已创建新 Agent 处理 ${kind} #${number}`;
          } else {
            this.message = "已取消";
          }
        } else {
          const res = await create(prefill);
          if (res && res.success) {
            this.message = `已创建新 Agent 处理 ${kind} #${number}`;
          } else {
            this.message = "失败: " + ((res && res.error) || "创建失败");
          }
        }
      } catch (e) {
        this.message = "失败: " + String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // 创建独立 git worktree 的 CodeAgent 处理该 issue/PR，支持多个 Issue/PR 并行互不干扰。
    // worktree 仅在 code_agent 类型下生效，故此处固定以 code_agent + worktree=true 创建。
    async handleItemWorktreeAgent(item) {
      this.closeItemMenu();
      if (!item) return;
      const isIssue = this.tab === "issues";
      const kind = isIssue ? "Issue" : "Pull Request";
      const number = item.number;
      // 优先使用「打开创建 Agent 弹窗（带预填）」通道，让用户确认/编辑后再创建；
      // 宿主未提供新通道时回退到直接创建通道（向后兼容）。
      const openModal =
        typeof window !== "undefined" && window.__jarvisOpenCreateAgentModal;
      const create =
        typeof window !== "undefined" && window.__jarvisCreateAgentForTask;
      if (typeof openModal !== "function" && typeof create !== "function") {
        this.message = "宿主未提供创建通道，无法创建 Agent";
        return;
      }
      const workingDir = (this.workingDir || "").trim();
      if (!workingDir) {
        this.message = "失败: 未解析到工作目录";
        return;
      }
      this.busy = true;
      this.message = `正在创建 Worktree Agent 处理 ${kind} #${number}…`;
      try {
        const prefill = {
          workingDir: workingDir,
          task: this.buildItemPrompt(item),
          name: `${kind} #${number}`,
          nodeId: this.nodeId,
          agentType: "code_agent",
          worktree: true,
        };
        if (typeof openModal === "function") {
          const res = await openModal(prefill);
          if (res && res.confirmed) {
            this.message = `已创建 Worktree Agent 处理 ${kind} #${number}`;
          } else {
            this.message = "已取消";
          }
        } else {
          const res = await create(prefill);
          if (res && res.success) {
            this.message = `已创建 Worktree Agent 处理 ${kind} #${number}`;
          } else {
            this.message = "失败: " + ((res && res.error) || "创建失败");
          }
        }
      } catch (e) {
        this.message = "失败: " + String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // 自定义仓库 Issue：Fork 原仓库并 clone 到所选目录，再在该目录创建 CodeAgent 处理。
    // 流程：选目录（含节点）→ 在所选节点 fork（已存在复用）→ clone → 创建 CodeAgent。
    async handleItemForkCloneAgent(item) {
      this.closeItemMenu();
      if (!item) return;
      const repo = currentRepo;
      if (!repo) {
        this.message = "失败: 未解析到仓库";
        return;
      }
      const number = item.number;
      const pick =
        typeof window !== "undefined" && window.__jarvisPickDirectoryWithNode;
      // 优先使用「打开创建 Agent 弹窗（带预填）」通道；宿主未提供时回退到直接创建通道。
      const openModal =
        typeof window !== "undefined" && window.__jarvisOpenCreateAgentModal;
      const create =
        typeof window !== "undefined" && window.__jarvisCreateAgentForTask;
      if (typeof pick !== "function") {
        this.message = "宿主未提供目录选择通道，无法选择目录";
        return;
      }
      if (typeof openModal !== "function" && typeof create !== "function") {
        this.message = "宿主未提供创建通道，无法创建 Agent";
        return;
      }
      this.busy = true;
      try {
        this.message = "请选择 Fork 后 clone 的目标目录…";
        const picked = await pick();
        if (!picked || !picked.path) {
          this.message = "已取消";
          return;
        }
        const targetDir = picked.path;
        // fork/clone 在所选目录所在节点执行
        const targetNode = String(picked.nodeId || "master").trim() || "master";
        this.message = `正在 Fork 并 Clone ${repo}…`;
        const prepared = await callFunction("prepare_issue_repo", {
          repo: repo,
          target_dir: targetDir,
        }, targetNode, this.platform);
        const localDir = (prepared && prepared.local_dir) || "";
        if (!localDir) {
          this.message = "失败: 未获取到本地目录";
          return;
        }
        this.message = `正在创建 CodeAgent（${localDir}）…`;
        const prefill = {
          agentType: "code_agent",
          workingDir: localDir,
          task: this.buildItemPrompt(item, true),
          name: `Issue #${number}`,
          nodeId: targetNode,
        };
        if (typeof openModal === "function") {
          const res = await openModal(prefill);
          if (res && res.confirmed) {
            this.message = `已创建 CodeAgent 处理 Issue #${number}（${localDir}）`;
          } else {
            this.message = "已取消";
          }
        } else {
          const res = await create(prefill);
          if (res && res.success) {
            this.message = `已创建 CodeAgent 处理 Issue #${number}（${localDir}）`;
          } else {
            this.message = "失败: " + ((res && res.error) || "创建失败");
          }
        }
      } catch (e) {
        this.message = "失败: " + String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // ---- 写操作 ----
    async postComment() {
      const body = (this.commentText || "").trim();
      if (!body) return;
      this.busy = true;
      this.message = "";
      try {
        await callFunction("comment", {
          number: this.selected.number,
          body: body,
        }, this.nodeId, this.platform);
        this.commentText = "";
        this.message = "评论已发布";
        await this.openItem(this.selected);
      } catch (e) {
        this.message = "失败: " + String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    async closeIssue() {
      if (!confirm("确定关闭 issue #" + this.selected.number + " 吗？")) return;
      this.busy = true;
      this.message = "";
      try {
        await callFunction("close_issue", { number: this.selected.number }, this.nodeId, this.platform);
        this.message = "issue 已关闭";
        await this.refresh();
      } catch (e) {
        this.message = "失败: " + String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    async mergePr() {
      if (!confirm("确定合并 PR #" + this.selected.number + " 吗？")) return;
      this.busy = true;
      this.message = "";
      try {
        await callFunction("merge_pr", {
          number: this.selected.number,
          merge_method: "merge",
        }, this.nodeId, this.platform);
        this.message = "PR 已合并";
        await this.refresh();
      } catch (e) {
        this.message = "失败: " + String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    tabBtnStyle(t) {
      const active = this.tab === t;
      return {
        padding: "4px 10px",
        background: active ? "#1f6feb" : "#333",
        color: active ? "#fff" : "#ddd",
        border: "none",
        borderRadius: "4px",
        cursor: "pointer",
      };
    },
    openExternal(url) {
      if (url) window.open(url, "_blank");
    },
    // 打开/关闭帮助弹层
    toggleHelp() {
      this.helpVisible = !this.helpVisible;
      if (this.helpVisible) {
        // 打开时同步认证表单的节点，并查询 github+gitee 双平台认证状态
        this.authNodeId = this.nodeId;
        this.refreshAuthStatus();
      }
    },
    // 认证表单切换节点：重新查询该节点 github+gitee 双平台的认证状态
    onAuthNodeChange() {
      this.authStatus = null;
      this.authToken = "";
      this.refreshAuthStatus();
    },
    // 认证表单切换平台：双平台状态已同时显示，无需重查，仅清空 token
    onAuthPlatformChange() {
      this.authToken = "";
    },
    // 查询所选节点上 github+gitee 双平台的认证状态
    // （仅用于展示「已登录/未认证」，不泄露 token）
    async refreshAuthStatus() {
      this.authLoading = true;
      this.authStatus = null;
      try {
        const [github, gitee] = await Promise.all([
          callFunction("auth_status", { platform: "github" }, this.authNodeId),
          callFunction("auth_status", { platform: "gitee" }, this.authNodeId),
        ]);
        this.authStatus = { github: github || {}, gitee: gitee || {} };
      } catch (e) {
        this.authStatus = { error: String((e && e.message) || e) };
      } finally {
        this.authLoading = false;
      }
    },
    // 提交认证：把 token 交给后端写入 CLI 凭据（仅未认证时执行）。
    // 成功后清空 token 并刷新状态；失败提示原因（token 不回显、不落日志）。
    async doAuth() {
      const token = (this.authToken || "").trim();
      if (!token) {
        this.message = "请填写 token";
        return;
      }
      this.authBusy = true;
      this.message = "";
      try {
        await callFunction(
          "auth_login",
          { platform: this.authPlatform, token: token },
          this.authNodeId,
        );
        this.authToken = "";
        this.message = `已在节点 ${this.nodeLabelById(this.authNodeId)} 完成 ${this.authPlatform === "gitee" ? "Gitee" : "GitHub"} 认证`;
        await this.refreshAuthStatus();
      } catch (e) {
        this.message = "认证失败: " + String((e && e.message) || e);
      } finally {
        this.authBusy = false;
      }
    },
  },
  template: `
  <div style="padding:12px;font-size:13px;color:#ddd;overflow:auto;height:100%;box-sizing:border-box;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
      <strong style="font-size:14px;">{{ platform === 'gitee' ? 'Gitee' : 'GitHub' }}</strong>
      <div style="display:flex;align-items:center;gap:6px;">
        <span style="font-size:11px;color:#888;" :title="repo || ''">{{ repo || '未检测到仓库' }}</span>
        <button @click="toggleHelp" title="使用帮助"
          style="padding:2px 6px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:11px;">帮助</button>
        <button @click="toggleRepoEdit" title="切换到其他仓库"
          style="padding:2px 6px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:11px;">切换</button>
      </div>
    </div>
    <!-- 目标节点：gh 功能（gh CLI / git / 仓库解析）在所选节点本地执行；切换后自动刷新 -->
    <div v-if="nodes.length > 0" style="display:flex;align-items:center;gap:6px;margin-bottom:10px;">
      <span style="font-size:11px;color:#888;">节点</span>
      <select v-model="nodeId" @change="onNodeChange(nodeId)"
        style="flex:1;min-width:0;padding:4px 6px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <option v-for="n in nodes" :key="n.node_id" :value="n.node_id">{{ nodeLabel(n) }}</option>
      </select>
    </div>
    <!-- 平台：auto 跟随仓库 remote 自动识别；github/gitee 显式指定。切换后自动刷新 -->
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px;">
      <span style="font-size:11px;color:#888;">平台</span>
      <select v-model="platform" @change="onPlatformChange(platform)"
        style="flex:1;min-width:0;padding:4px 6px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <option value="auto">自动识别</option>
        <option value="github">GitHub</option>
        <option value="gitee">Gitee</option>
      </select>
    </div>
    <!-- 当前目标 Agent：与「在当前 Agent 中处理」的实际接收者一致；无 Agent 时提示 -->
    <div style="font-size:11px;color:#58a6ff;margin-bottom:10px;">
      当前 Agent: <span :title="agentName || ''">{{ agentName || '未选择 Agent' }}</span>
    </div>

    <!-- 仓库切换：手动输入 owner/repo 查看其他仓库；也可恢复为跟随当前工作目录 -->
    <div v-if="repoEditing" style="margin-bottom:10px;padding:8px;background:#252526;border-radius:6px;">
      <div style="font-size:11px;color:#888;margin-bottom:4px;">仓库（owner/repo，可粘贴 GitHub 地址）</div>
      <div style="display:flex;gap:6px;">
        <input v-model="repoInput" type="text" placeholder="如 octocat/Hello-World"
          @keydown.enter.prevent="setRepo"
          style="flex:1;min-width:0;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <button @click="setRepo" style="padding:5px 10px;background:#1f6feb;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;">确定</button>
      </div>
      <div style="display:flex;gap:6px;margin-top:6px;">
        <button @click="useCurrentDirRepo" style="padding:4px 8px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:11px;">跟随当前目录</button>
        <button @click="repoEditing = false" style="padding:4px 8px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:11px;">取消</button>
      </div>
      <!-- 最近使用过的仓库：点击快速切换，无需重新输入 -->
      <div v-if="repoHistory.length" style="margin-top:8px;">
        <div style="font-size:11px;color:#888;margin-bottom:4px;">最近使用</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px;">
          <button v-for="r in repoHistory" :key="r" @click="selectRepoHistory(r)"
            :title="r"
            style="padding:3px 8px;background:#1e1e1e;color:#58a6ff;border:1px solid #333;border-radius:4px;cursor:pointer;font-size:11px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ r }}</button>
        </div>
      </div>
    </div>

    <!-- 消息 -->
    <div v-if="message" style="margin-bottom:8px;padding:6px;background:#1f6feb33;border-radius:4px;font-size:12px;">{{ message }}</div>
    <div v-if="error" style="margin-bottom:8px;padding:6px;background:#f8514933;border-radius:4px;font-size:12px;color:#f85149;">{{ error }}</div>

    <!-- 列表视图 -->
    <div v-if="!selected">
      <div style="display:flex;gap:6px;margin-bottom:10px;">
        <button @click="tab='issues';refresh()" :style="tabBtnStyle('issues')">Issues</button>
        <button @click="tab='pulls';refresh()" :style="tabBtnStyle('pulls')">PRs</button>
        <button @click="refresh()" style="margin-left:auto;padding:4px 8px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;">🔄</button>
      </div>
      <div v-if="loading" style="color:#888;padding:20px;text-align:center;">加载中…</div>
      <div v-else-if="items.length === 0" style="color:#888;padding:20px;text-align:center;">暂无 {{ tab === 'issues' ? 'issue' : 'PR' }}</div>
      <div v-for="it in items" :key="it.number" @click="openItem(it)" @contextmenu.prevent="openItemMenu(it, $event)"
        style="padding:8px;margin-bottom:6px;background:#252526;border-radius:6px;cursor:pointer;border-left:3px solid #58a6ff;">
        <div style="display:flex;justify-content:space-between;">
          <span style="color:#888;">#{{ it.number }}</span>
          <span :style="{color: it.state === 'open' ? '#3fb950' : '#f85149', fontSize:'11px'}">{{ it.state }}</span>
        </div>
        <div style="margin-top:2px;font-weight:600;">{{ it.title }}</div>
        <div style="font-size:11px;color:#888;margin-top:2px;">@{{ it.user }} · {{ fmtDate(it.created_at) }}</div>
      </div>
      <!-- 分页：显示已加载/总数，并提供「加载更多」按钮 -->
      <div v-if="items.length > 0" style="text-align:center;margin-top:10px;">
        <div style="font-size:11px;color:#888;margin-bottom:6px;">
          已加载 {{ items.length }} 条<span v-if="total > items.length">（共约 {{ total }} 条）</span>
        </div>
        <button v-if="hasMore" @click="loadMore" :disabled="loadingMore"
          style="padding:5px 14px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:12px;">
          {{ loadingMore ? '加载中…' : '加载更多' }}
        </button>
      </div>
    </div>

    <!-- 详情视图 -->
    <div v-else>
      <button @click="back()" style="margin-bottom:8px;padding:4px 10px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;">← 返回</button>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <h3 style="margin:0;font-size:14px;">#{{ selected.number }} {{ selected.title }}</h3>
        <a v-if="selected.html_url" href="javascript:void(0)" @click="openExternal(selected.html_url)" style="font-size:11px;color:#58a6ff;">打开 ↗</a>
      </div>
      <div style="font-size:11px;color:#888;margin:4px 0;">@{{ selected.user }} · {{ fmtDate(selected.created_at) }}</div>
      <div style="white-space:pre-wrap;background:#1e1e1e;padding:8px;border-radius:6px;margin:8px 0;max-height:200px;overflow:auto;font-size:12px;">{{ selected.body || '(无描述)' }}</div>

      <!-- 操作按钮 -->
      <div style="display:flex;gap:6px;margin-bottom:10px;">
        <button v-if="tab==='issues' && selected.state==='open'" @click="closeIssue" :disabled="busy"
          style="padding:5px 10px;background:#f8514933;color:#f85149;border:1px solid #f85149;border-radius:4px;cursor:pointer;">关闭 issue</button>
        <button v-if="tab==='pulls' && selected.state==='open'" @click="mergePr" :disabled="busy"
          style="padding:5px 10px;background:#238636;color:#fff;border:none;border-radius:4px;cursor:pointer;">合并 PR</button>
      </div>

      <!-- 评论 -->
      <div style="font-size:12px;font-weight:600;margin-bottom:6px;">评论 ({{ comments.length }})</div>
      <div v-for="c in comments" :key="c.created_at" style="background:#1e1e1e;padding:6px;border-radius:6px;margin-bottom:6px;">
        <div style="font-size:11px;color:#888;">@{{ c.user }} · {{ fmtDate(c.created_at) }}</div>
        <div style="white-space:pre-wrap;font-size:12px;margin-top:2px;">{{ c.body }}</div>
      </div>
      <div v-if="comments.length === 0" style="font-size:11px;color:#888;">暂无评论</div>

      <textarea v-model="commentText" rows="3" placeholder="写评论…"
        style="width:100%;box-sizing:border-box;margin-top:8px;padding:6px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;"></textarea>
      <button @click="postComment" :disabled="busy || !commentText.trim()"
        style="margin-top:6px;padding:6px 12px;background:#1f6feb;color:#fff;border:none;border-radius:4px;cursor:pointer;">发布评论</button>
    </div>

    <!-- 列表项右键菜单 -->
    <div v-if="menuVisible" :style="menuStyle"
      style="position:fixed;z-index:9999;background:#2d2d30;border:1px solid #454545;border-radius:6px;box-shadow:0 4px 12px #0008;padding:4px;min-width:120px;">
      <div v-if="!isManualRepo" @click="handleItem(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#ddd;cursor:pointer;border-radius:4px;white-space:nowrap;">在当前 Agent 中处理{{ agentName ? '（' + agentName + '）' : '' }}</div>
      <div v-if="!isManualRepo" @click="handleItemNewAgent(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#ddd;cursor:pointer;border-radius:4px;white-space:nowrap;">创建新 Agent 处理</div>
      <div v-if="!isManualRepo" @click="handleItemWorktreeAgent(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#ddd;cursor:pointer;border-radius:4px;white-space:nowrap;">开启 Worktree 处理</div>
      <div v-if="isManualRepo" @click="handleItemForkCloneAgent(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#ddd;cursor:pointer;border-radius:4px;white-space:nowrap;">Fork 并创建 CodeAgent 处理</div>
    </div>

    <!-- 帮助弹层：插件使用条件（非开箱即用，需配置 CLI 与登录） -->
    <div v-if="helpVisible" @click.self="helpVisible = false"
      style="position:fixed;inset:0;z-index:10000;background:#000a;display:flex;align-items:center;justify-content:center;">
      <div style="background:#1e1e1e;border:1px solid #454545;border-radius:8px;max-width:560px;width:92%;max-height:80vh;overflow:auto;padding:16px;box-sizing:border-box;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
          <strong style="font-size:14px;">gh 插件使用说明</strong>
          <button @click="helpVisible = false" title="关闭"
            style="padding:2px 8px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:12px;">✕</button>
        </div>
        <div style="font-size:12px;line-height:1.7;color:#ddd;white-space:pre-wrap;">
本插件不是开箱即用，使用前需在目标节点完成以下配置：

【1. 安装命令行工具】
· GitHub：安装官方 gh CLI（https://cli.github.com）
· Gitee：安装 gitee CLI（https://github.com/oschina/gitee-cli）
· git（fork/clone 仓库时需要）

【2. 登录认证】
· 读操作（列出/查看）公开仓库无需登录
· 写操作（评论/关闭/合并）需对应平台已登录
· 认证在所选节点本地执行，不跨节点共享

<!-- 认证表单：选择节点+平台+token；顶部同时展示 github+gitee 双平台认证状态 -->
<div style="margin:10px 0;padding:10px;background:#252526;border-radius:6px;">
  <div style="font-size:12px;font-weight:600;margin-bottom:8px;">🔐 认证</div>
  <div v-if="authLoading" style="font-size:12px;color:#888;">查询认证状态…</div>
  <template v-else-if="authStatus && !authStatus.error">
    <div style="font-size:12px;margin-bottom:6px;">
      <span style="display:inline-block;width:60px;color:#888;">GitHub</span>
      <span v-if="authStatus.github && authStatus.github.authenticated" style="color:#3fb950;">
        ✓ 已登录（{{ authStatus.github.login || '已认证' }}）
      </span>
      <span v-else style="color:#f85149;">
        ✗ 未认证<template v-if="authStatus.github && authStatus.github.installed === false">（gh 未安装）</template>
      </span>
    </div>
    <div style="font-size:12px;margin-bottom:6px;">
      <span style="display:inline-block;width:60px;color:#888;">Gitee</span>
      <span v-if="authStatus.gitee && authStatus.gitee.authenticated" style="color:#3fb950;">
        ✓ 已登录（{{ authStatus.gitee.login || '已认证' }}）
      </span>
      <span v-else style="color:#f85149;">
        ✗ 未认证<template v-if="authStatus.gitee && authStatus.gitee.installed === false">（gitee 未安装）</template>
      </span>
    </div>
  </template>
  <template v-else>
    <div v-if="authStatus && authStatus.error" style="font-size:11px;color:#f85149;margin-bottom:6px;">{{ authStatus.error }}</div>
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
      <span style="font-size:11px;color:#888;width:28px;">节点</span>
      <select v-model="authNodeId" @change="onAuthNodeChange"
        style="flex:1;min-width:0;padding:4px 6px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <option v-for="n in nodes" :key="n.node_id" :value="n.node_id">{{ nodeLabel(n) }}</option>
      </select>
    </div>
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
      <span style="font-size:11px;color:#888;width:28px;">平台</span>
      <select v-model="authPlatform" @change="onAuthPlatformChange"
        style="flex:1;min-width:0;padding:4px 6px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <option value="github">GitHub</option>
        <option value="gitee">Gitee</option>
      </select>
    </div>
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
      <span style="font-size:11px;color:#888;width:28px;">Token</span>
      <input v-model="authToken" type="password" placeholder="粘贴 Personal Access Token"
        @keydown.enter.prevent="doAuth"
        style="flex:1;min-width:0;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
    </div>
    <button @click="doAuth" :disabled="authBusy || !authToken.trim()"
      style="padding:6px 14px;background:#1f6feb;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;">
      {{ authBusy ? '认证中…' : '认证' }}
    </button>
    <div style="font-size:11px;color:#888;margin-top:6px;">token 仅发送到所选节点本地写入 CLI 凭据，不会保存到浏览器。</div>
  </template>
</div>

【3. 选择平台】
· 平台默认「自动识别」：按当前仓库 remote 自动判断
  （gitee.com → Gitee，其余 → GitHub）
· 手动指定仓库时建议显式选择平台（GitHub / Gitee）

【4. 选择节点】
· gh/gitee 命令在所选节点本地执行，需该节点已安装 CLI 并登录
· 子节点需单独安装与登录，认证不跨节点共享

【5. 使用说明】
· 列表/查看为读操作，可直接使用
· 评论/关闭/合并为写操作，执行前会与用户确认
· 写操作失败提示未登录时，请先在对应节点终端登录
        </div>
      </div>
    </div>
  </div>
  `,
};
