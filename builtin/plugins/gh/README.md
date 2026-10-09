# gh

GitHub 助手插件——自动处理当前仓库的 PR 和 Issue，复用 GitHub 官方 `gh` CLI 登录态。

> 由 Jarvis 内置插件，随源码分发，不可卸载/升级。

## 功能

- **PR 管理**：列出、查看、合并当前仓库的 Pull Request
- **Issue 管理**：列出、查看、评论、关闭当前仓库的 Issue
- **GitHub 认证**：复用 GitHub 官方 `gh` CLI 登录态（`gh auth login`），写操作（合并/评论/关闭）需认证
- **前端侧边栏**：编辑器活动栏 → GitHub 图标，直接浏览/操作 Issue 与 PR（列表/详情/评论/关闭/合并）

## 默认仓库

gh 插件默认处理**当前工作目录对应的 GitHub 仓库**（读取 git remote origin 自动解析）。若需操作其他仓库，可执行 `gh repo set-default owner/repo`，或命令加 `--repo owner/repo` 参数显式指定。

- **侧边栏切换仓库**：侧边栏顶部「切换」按钮可手动输入 `owner/repo`（支持粘贴 GitHub 地址），查看其他仓库的 Issue/PR；点「跟随当前目录」恢复为自动解析。手动指定的仓库会记入本地存储，刷新后仍生效。

## 认证方式

插件复用 GitHub 官方 `gh` CLI 的登录态（`gh auth login`），通过 `gh auth token` 读取 token，不自行存储 token。

- **读操作**（列出/查看 PR、issue）：公开仓库匿名可访问，无需认证。
- **写操作**（合并 PR、评论、关闭 issue）：需要认证。请先在终端用 GitHub 官方 CLI 登录：

```bash
# 登录（GitHub 官方 CLI）
gh auth login

# 查看登录状态
gh auth status
```

## 常用命令

Agent 通过 `execute_script` 直接调用 GitHub 官方 `gh` CLI 完成 GitHub 操作，无需额外工具：

| 命令                                 | 说明                          | 认证   |
| ------------------------------------ | ----------------------------- | ------ |
| `gh pr list`                         | 列出 PR（可按 state 过滤）    | 匿名   |
| `gh pr view <number>`                | 查看单个 PR 详情              | 匿名   |
| `gh pr merge <number>`               | 合并 PR（需认证）             | gh CLI |
| `gh issue list`                      | 列出 Issue（可按 state 过滤） | 匿名   |
| `gh issue view <number>`             | 查看单个 Issue 详情           | 匿名   |
| `gh issue comment` / `gh pr comment` | 对 PR/Issue 评论（需认证）    | gh CLI |
| `gh issue close <number>`            | 关闭 Issue（需认证）          | gh CLI |

## 插件结构

```text
gh/
├── config.yaml          # 插件配置（name/version + 扩展点声明）
├── README.md
├── rules/               # gh 插件使用规则
├── plugin/              # 插件私有功能（api.py + gh_common.py，供前端侧边栏调用）
└── frontend/            # 前端侧边栏视图（编辑器活动栏 → GitHub）
```

## 相关代码

- 前端侧边栏：通过 `plugin/api.py` 调用 GitHub REST API（`https://api.github.com`）
- 认证：复用 GitHub 官方 `gh` CLI 登录态（`gh auth token`）
