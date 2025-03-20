# 🔮 Jarvis Smart Shell - 智能命令行助手

<div align="center">
  <img src="../images/smart-shell.png" alt="Smart Shell" width="250" style="margin-bottom: 20px"/>
  
  *终端操作的魔法体验*
  
  ![Version](https://img.shields.io/badge/version-0.1.x-blue)
  ![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS-lightgrey)
</div>

## 🌈 魔法简介
Jarvis Smart Shell (JSS) 是一个革命性的命令行助手，让您用自然语言描述需求，智能转化为精确的 Shell 命令。不再需要记忆复杂的命令语法和参数，只需告诉 JSS 您想做什么，它就能为您生成最佳命令并执行。

## ✨ 闪耀特性
- **自然语言理解** - 使用日常语言描述您的需求
- **智能命令生成** - 精确转换为最优 Shell 命令
- **命令编辑** - 生成后可以进一步微调命令
- **命令历史** - 智能记忆您常用的操作模式
- **跨平台支持** - 适配不同的 Shell 类型和操作系统
- **上下文感知** - 理解当前工作目录与环境

## 💫 使用方法
```bash
# 主命令
jarvis-smart-shell

# 简写命令
jss
```

### 💎 交互流程
1. **启动助手** - 运行 `jss` 启动交互式环境
2. **描述需求** - 用自然语言输入您的操作需求
3. **命令生成** - 系统生成对应的 Shell 命令
4. **确认执行** - 您可以直接执行或编辑后再执行
5. **查看结果** - 命令执行结果直接显示

## 🚀 使用场景
- **文件操作** - "找出所有大于100MB的视频文件并移动到新目录"
- **系统管理** - "显示当前系统资源使用情况，按CPU使用率排序"
- **网络诊断** - "检查与服务器的连接状态并显示网络延迟"
- **开发辅助** - "找出所有包含TODO注释的Python文件"
- **数据处理** - "合并所有CSV文件并提取第3和第5列数据"
- **批量操作** - "压缩所有图片并调整分辨率为1080p"

## 🎯 常用示例
| 自然语言请求 | 生成的命令 |
|------------|-----------|
| 查找最近3天修改的所有JS文件 | `find . -name "*.js" -mtime -3 -type f` |
| 显示当前目录下最大的5个文件 | `du -ah . \| sort -hr \| head -n 5` |
| 统计代码仓库中每种语言的行数 | `find . -type f -name "*.py" \| xargs wc -l \| sort -nr` |
| 后台运行服务并记录日志 | `nohup python server.py > server.log 2>&1 &` |
| 监控系统CPU和内存使用情况 | `watch -n 1 "ps aux \| sort -rk 3 \| head -10"` |

## 🔍 高级用法
- **定制化提示** - 通过环境变量个性化您的交互体验
  ```bash
  export JSS_STYLE=detailed  # 生成带有解释的详细命令
  ```
- **错误检测** - 自动检测并修复常见的命令错误
- **命令序列** - 支持描述多步骤操作流程
- **别名集成** - 与您的自定义Shell别名完美融合

## 💡 专家小贴士
- 使用清晰具体的描述获得最精确的命令
- 提及文件类型、数量限制等具体细节
- 复杂操作可分解为多个简单步骤
- 结合管道操作可实现强大的数据处理流
- 善用命令编辑功能进行个性化调整

---

<div align="center">
  <p><i>Jarvis Smart Shell - 您的终端操作，一句话的距离</i></p>
</div> 