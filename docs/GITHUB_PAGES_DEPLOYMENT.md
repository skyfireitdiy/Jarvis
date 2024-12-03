# GitHub Pages 部署指南

本文档说明如何使用 MkDocs 为 Jarvis 项目构建和部署 GitHub Pages。

## 📋 概述

本项目使用 [MkDocs](https://www.mkdocs.org/) + [Material Theme](https://squidfunk.github.io/mkdocs-material/) 构建文档网站，并通过 GitHub Actions 自动部署到 GitHub Pages。

## 🚀 本地预览

### 安装依赖

```bash
pip install -r requirements-docs.txt
```

或手动安装：

```bash
pip install mkdocs-material
pip install mkdocs-git-revision-date-localized-plugin
pip install pymdown-extensions
```

### 启动本地服务器

```bash
mkdocs serve
```

访问 <http://127.0.0.1:8000> 查看文档效果。

### 构建静态网站

```bash
mkdocs build
```

生成的静态文件将保存在 `site/` 目录中。

## 🔧 GitHub Pages 自动部署

### 配置说明

项目已配置 GitHub Actions 工作流 `.github/workflows/deploy-docs.yml`，当以下情况发生时会自动触发部署：

- 向 `main` 或 `master` 分支推送代码
- 向 `main` 或 `master` 分支提交 Pull Request

### 启用 GitHub Pages

首次使用需要手动启用 GitHub Pages：

1. 进入仓库的 **Settings** 页面
2. 在左侧菜单中选择 **Pages**
3. 在 **Build and deployment** 部分：
   - **Source**: 选择 `GitHub Actions`
4. 保存设置

### 部署流程

1. 推送代码到 `main` 分支
2. GitHub Actions 自动触发构建
3. 构建完成后自动部署到 GitHub Pages
4. 访问 `https://<username>.github.io/<repository>/` 查看部署结果

### 查看部署状态

- 在仓库的 **Actions** 标签页查看构建和部署状态
- 部署成功后会显示绿色的勾选标记
- 如果失败，点击失败的任务查看详细日志

## 📂 项目结构

```text
Jarvis/
├── docs/                      # 文档源文件
│   ├── jarvis_book/          # 主文档
│   ├── best_practices/       # 最佳实践
│   ├── compare/              # 对比分析
│   └── GITHUB_PAGES_DEPLOYMENT.md  # 本文档
├── .github/
│   └── workflows/
│       └── deploy-docs.yml   # GitHub Actions 工作流
├── mkdocs.yml                # MkDocs 配置文件
└── requirements-docs.txt     # 文档依赖
```

## 🎨 自定义配置

### 修改配置

编辑 `mkdocs.yml` 文件可以自定义：

- **主题配色**: 修改 `theme.palette` 部分
- **导航结构**: 修改 `nav` 部分
- **插件**: 在 `plugins` 部分添加或移除插件
- **Markdown 扩展**: 在 `markdown_extensions` 部分配置

### 更新仓库信息

在 `mkdocs.yml` 中修改以下配置为您的实际仓库信息：

```yaml
definition:
  github:
    repo_url: https://github.com/your-username/jarvis
    edit_uri: edit/main/docs/

extra:
  social:
    - icon: fontawesome/brands/github
      link: https://github.com/your-username/jarvis
```

## 🔍 功能特性

- ✅ 响应式设计，支持移动端
- ✅ 深色/浅色主题切换
- ✅ 智能搜索（支持中文）
- ✅ 代码高亮和复制按钮
- ✅ 自动目录生成
- ✅ Git 修订日期显示
- ✅ Tab 选项卡支持
- ✅ 任务列表支持
- ✅ 数学公式渲染
- ✅ Mermaid 图表支持

## 📚 相关资源

- [MkDocs 官方文档](https://www.mkdocs.org/)
- [Material Theme 文档](https://squidfunk.github.io/mkdocs-material/)
- [GitHub Pages 文档](https://docs.github.com/en/pages)
- [GitHub Actions 文档](https://docs.github.com/en/actions)

## 🐛 常见问题

### Q: 本地预览正常，但部署后样式错乱？

A: 清除浏览器缓存或使用隐私模式访问。

### Q: 搜索功能不工作？

A: 确保在 `mkdocs.yml` 中启用了搜索插件，并且网站已经完全部署。

### Q: 如何添加新页面？

A: 在 `docs/` 目录下添加 Markdown 文件，并在 `mkdocs.yml` 的 `nav` 部分添加导航链接。

### Q: 部署失败怎么办？

A: 在 GitHub Actions 页面查看详细日志，检查是否有语法错误或依赖问题。

## 📝 维护建议

1. **定期更新依赖**: 定期运行 `pip install -U mkdocs-material` 更新主题
2. **测试构建**: 推送前先在本地运行 `mkdocs build` 确保没有错误
3. **检查链接**: 定期检查文档中的链接是否有效
4. **备份配置**: 重要修改前备份 `mkdocs.yml` 配置文件

---

如有问题或建议，欢迎提交 Issue 或 Pull Request！
