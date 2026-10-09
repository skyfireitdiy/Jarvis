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
    } catch (e) {
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
async function callFunction(functionName, args) {
  // 统一走 App.vue 暴露的带认证请求函数 window.__jarvisFetch（自动携带 jarvis
  // 认证信息，token 不暴露给插件）；若宿主未注入则回退到普通 fetch。
  const authedFetch =
    (typeof window !== "undefined" && window.__jarvisFetch) || fetch;
  // 除 resolve_repo 外，其余函数都需指定 repo；未解析到仓库时传空，
  // 由后端返回明确错误提示。
  const noRepoFns = ["resolve_repo"];
  const callArgs = args || {};
  if (!noRepoFns.includes(functionName) && !callArgs.repo) {
    callArgs.repo = currentRepo;
  }
  const resp = await authedFetch(
    `${gatewayBase()}/api/plugins/master/function-call`,
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
    throw new Error("网关响应异常");
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
      tab: "issues",
      loading: false,
      error: "",
      items: [],
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
    };
  },
  mounted() {
    this.resolveRepo().then(() => this.refresh());
    // 点击别处 / 按 Esc 关闭右键菜单
    this._onDocClick = () => this.closeItemMenu();
    this._onDocKeydown = (e) => {
      if (e.key === "Escape") this.closeItemMenu();
    };
    document.addEventListener("click", this._onDocClick);
    document.addEventListener("keydown", this._onDocKeydown);
  },
  beforeUnmount() {
    document.removeEventListener("click", this._onDocClick);
    document.removeEventListener("keydown", this._onDocKeydown);
  },
  watch: {
    workingDir() {
      // agent 切换仓库时重新解析并刷新
      this.resolveRepo().then(() => this.refresh());
    },
  },
  methods: {
    async resolveRepo() {
      try {
        const payload = await callFunction("resolve_repo", {
          working_dir: this.workingDir || "",
        });
        currentRepo = (payload && payload.repo) || "";
        this.repo = currentRepo;
      } catch (e) {
        // 解析失败：清空仓库（不硬编码默认仓库）
        currentRepo = "";
        this.repo = "";
      }
    },
    fmtDate(s) {
      if (!s) return "";
      try {
        return new Date(s).toLocaleString();
      } catch (e) {
        return s;
      }
    },
    async refresh() {
      this.loading = true;
      this.error = "";
      this.message = "";
      // 切换/刷新瞬间先清空列表，避免请求失败时残留上一个仓库的数据
      this.items = [];
      this.selected = null;
      this.comments = [];
      try {
        const fn = this.tab === "issues" ? "list_issues" : "list_prs";
        const payload = await callFunction(fn, { state: "open" });
        this.items = (payload.data || []).map((it) => ({
          number: it.number,
          title: it.title,
          state: it.state,
          user: it.user,
          created_at: it.created_at,
          updated_at: it.updated_at,
          body: it.body || "",
          html_url: it.html_url,
          comments: it.comments,
        }));
        this.selected = null;
        this.comments = [];
      } catch (e) {
        this.error = String((e && e.message) || e);
      } finally {
        this.loading = false;
      }
    },
    async openItem(item) {
      this.selected = item;
      this.commentText = "";
      this.message = "";
      try {
        const fn = this.tab === "issues" ? "get_issue" : "get_pr";
        const detail = await callFunction(fn, { number: item.number });
        this.selected.body = ((detail.data && detail.data.body) || "").trim();
        const comments = await callFunction("list_comments", {
          number: item.number,
        });
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
    // 生成处理该 issue/PR 的提示词
    buildItemPrompt(item) {
      const isIssue = this.tab === "issues";
      const repo = currentRepo || "(当前仓库)";
      const number = item.number;
      const title = item.title || "";
      return isIssue
        ? [
            `请处理当前仓库 ${repo} 的 GitHub Issue #${number}：${title}`,
            "",
            "遵循 gh_rule 处理该 Issue：",
            `1. 用 \`gh issue view ${number}\` 查看该 Issue 详情（标题、作者、body、labels、状态），先复述内容确认理解正确。`,
            "2. 阅读 body 与现有评论，判断问题类型并形成处理方案。",
            "3. 如需写码实现，遵循 gh_rule 与相关开发规则完成修改。",
            "4. 写操作（评论/关闭）前先与我确认，再执行。",
          ].join("\n")
        : [
            `请处理当前仓库 ${repo} 的 GitHub Pull Request #${number}：${title}`,
            "",
            "遵循 gh_rule 处理该 PR：",
            `1. 用 \`gh pr view ${number}\` 与 \`gh pr diff ${number}\` 查看详情与改动。`,
            "2. 评估是否可合并或需修改；如需修改，遵循 gh_rule 与相关开发规则补齐实现/测试。",
            "3. 合并前先与我确认（含合并方式），再执行。",
          ].join("\n");
    },
    // 在当前活跃 Agent 中处理该 issue/PR
    async handleItem(item) {
      this.closeItemMenu();
      if (!item) return;
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
      const create =
        typeof window !== "undefined" && window.__jarvisCreateAgentForTask;
      if (typeof create !== "function") {
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
        const res = await create({
          workingDir: workingDir,
          task: this.buildItemPrompt(item),
          name: `${kind} #${number}`,
        });
        if (res && res.success) {
          this.message = `已创建新 Agent 处理 ${kind} #${number}`;
        } else {
          this.message = "失败: " + ((res && res.error) || "创建失败");
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
        });
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
        await callFunction("close_issue", { number: this.selected.number });
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
        });
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
  },
  template: `
  <div style="padding:12px;font-size:13px;color:#ddd;overflow:auto;height:100%;box-sizing:border-box;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
      <strong style="font-size:14px;">GitHub</strong>
      <span style="font-size:11px;color:#888;">{{ repo || '未检测到仓库' }}</span>
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
      <div @click="handleItem(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#ddd;cursor:pointer;border-radius:4px;white-space:nowrap;">在当前 Agent 中处理</div>
      <div @click="handleItemNewAgent(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#ddd;cursor:pointer;border-radius:4px;white-space:nowrap;">创建新 Agent 处理</div>
    </div>
  </div>
  `,
};
