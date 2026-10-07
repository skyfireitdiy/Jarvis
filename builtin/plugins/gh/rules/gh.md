---
name: gh_rule
description: 当需要自动处理 GitHub 仓库的 PR 或 Issue 时触发。每当用户提及"处理 PR"、"处理 issue"、"合并 PR"、"查看 PR"、"关闭 issue"、"评论 issue"、"gh 插件"、"GitHub 助手"时触发。
---

# gh 插件使用规则

此规则定义了 gh 插件（GitHub 助手）的使用方式，指导 Agent 正确调用各工具处理当前仓库的 PR 和 Issue。

## 能力清单

gh 插件提供以下能力：

| 能力       | 工具             | 说明                       |
| ---------- | ---------------- | -------------------------- |
| 列出 PR    | `gh_list_prs`    | 按 state 列出 Pull Request |
| 查看 PR    | `gh_get_pr`      | 查看单个 PR 详情           |
| 合并 PR    | `gh_merge_pr`    | 合并 PR（需认证）          |
| 列出 Issue | `gh_list_issues` | 按 state 列出 Issue        |
| 查看 Issue | `gh_get_issue`   | 查看单个 Issue 详情        |
| 评论       | `gh_comment`     | 对 PR/Issue 评论（需认证） |
| 关闭 Issue | `gh_close_issue` | 关闭 Issue（需认证）       |

## 默认仓库

gh 插件默认处理**当前工作目录对应的 GitHub 仓库**（读取 git remote origin 自动解析），不固定某个仓库。各工具支持 `repo` 参数显式覆盖（格式 `owner/repo`）；若当前目录不是 git 仓库或缺少 origin remote，工具会提示"未指定仓库"，此时请显式传入 `repo` 参数。

## 前端侧边栏

gh 插件还提供前端侧边栏视图（编辑器活动栏 → GitHub 图标）：可直接浏览/操作当前仓库的 Issue 与 PR（列表、详情、评论、关闭 issue、合并 PR）。前端写操作复用 GitHub 官方 `gh` CLI 的登录态（`gh auth login`），无需在前端输入 token。若用户想通过界面操作而非让 Agent 调用工具，可引导其使用前端侧边栏。

## 认证流程

1. **读操作**（列出/查看 PR、issue）：公开仓库匿名可访问，无需认证，直接调用。
2. **写操作**（合并 PR、评论、关闭 issue）：**必须先认证**。若工具返回"未登录"提示，引导用户在终端执行：

   ```bash
   gh auth login
   ```

   插件通过 `gh auth token` 读取登录态，后续写操作自动复用。

3. 可用 `gh auth status` 查看是否已登录。

## 使用规范

- **合并 PR 前**：先用 `gh_get_pr` 查看 PR 状态（是否可合并、是否有冲突），确认后再 `gh_merge_pr`。
- **合并方法**：默认 `merge`，可用 `gh_merge_pr` 的 `merge_method` 参数指定 `squash`/`rebase`/`merge`。
- **评论/关闭前**：确认目标 PR/Issue 编号正确。
- **写操作失败**：若返回 401/403，提示用户重新登录（token 可能失效）。

## 安全提示

- token 是敏感凭据，**不要**在评论、日志或输出中泄露完整 token。
- 合并/关闭等不可逆操作，执行前向用户确认。
