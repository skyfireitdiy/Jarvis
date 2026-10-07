# gh

GitHub 助手插件——自动处理当前仓库的 PR 和 Issue，复用 GitHub 官方 `gh` CLI 登录态。

> 由 Jarvis 内置插件，随源码分发，不可卸载/升级。

## 功能

- **PR 管理**：列出、查看、合并当前仓库的 Pull Request
- **Issue 管理**：列出、查看、评论、关闭当前仓库的 Issue
- **GitHub 认证**：复用 GitHub 官方 `gh` CLI 登录态（`gh auth login`），写操作（合并/评论/关闭）需认证
- **前端侧边栏**：编辑器活动栏 → GitHub 图标，直接浏览/操作 Issue 与 PR（列表/详情/评论/关闭/合并）

## 默认仓库

`skyfireitdiy/Jarvis`（GitHub 公开仓库）。各工具可通过 `repo` 参数覆盖，格式 `owner/repo`。

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

## 工具清单

| 工具             | 说明                          | 认证   |
| ---------------- | ----------------------------- | ------ |
| `gh_list_prs`    | 列出 PR（可按 state 过滤）    | 匿名   |
| `gh_get_pr`      | 查看单个 PR 详情              | 匿名   |
| `gh_merge_pr`    | 合并 PR（需认证）             | gh CLI |
| `gh_list_issues` | 列出 Issue（可按 state 过滤） | 匿名   |
| `gh_get_issue`   | 查看单个 Issue 详情           | 匿名   |
| `gh_comment`     | 对 PR/Issue 评论（需认证）    | gh CLI |
| `gh_close_issue` | 关闭 Issue（需认证）          | gh CLI |

## 插件结构

```text
gh/
├── config.yaml          # 插件配置（name/version + 扩展点声明）
├── README.md
├── rules/               # gh 插件使用规则
├── tools/               # 工具（class XxxTool, name==文件名 stem）
└── frontend/            # 前端侧边栏视图（编辑器活动栏 → GitHub）
```

## 相关代码

- GitHub REST API：`https://api.github.com`
- 认证：复用 GitHub 官方 `gh` CLI 登录态（`gh auth token`）
