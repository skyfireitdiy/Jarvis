# Jarvis 离线安装指南

## 概述

Jarvis离线安装包允许您在没有网络连接的环境中快速部署Jarvis AI助手。离线包包含所有必要的依赖，包括Python环境、虚拟环境、内置工具和前端构建产物。

## 适用场景

- **网络受限环境**：无法访问PyPI或GitHub的环境
- **快速部署**：需要在多台机器上快速部署
- **稳定版本分发**：确保所有机器使用相同的依赖版本
- **离线演示**：在没有网络的场所演示Jarvis功能

## 系统要求

### 支持的架构

- **x86_64** (AMD64/Intel64)
- **aarch64** (ARM64)

### 最低要求

- **操作系统**：Linux (推荐Ubuntu 20.04+或CentOS 7+)
- **磁盘空间**：至少2GB可用空间
- **内存**：至少1GB RAM
- **可选**：Git (用于版本管理和更新)

## 创建离线安装包

### 步骤1：准备环境

确保您已经成功安装Jarvis，并且虚拟环境正常工作：

```bash
# 检查Jarvis是否正常工作
jarvis --version

# 检查虚拟环境
ls -la .venv/
```

### 步骤2：运行打包脚本

```bash
# 进入Jarvis项目目录
cd ~/Jarvis

# 运行打包脚本
./scripts/create_offline_package.sh

# 或指定输出目录
./scripts/create_offline_package.sh /path/to/output
```

### 步骤3：查看打包结果

打包完成后，会在输出目录生成以下文件：

```bash
# 查看离线包
ls -lh offline_package/

# 输出示例：
# jarvis-offline-20250115-143022.tar.gz  (约1-2GB)
```

### 打包内容说明

离线包包含以下内容：

| 目录/文件      | 说明                   | 大约大小 |
| -------------- | ---------------------- | -------- |
| source/        | Jarvis源码             | ~50MB    |
| venv/          | Python虚拟环境         | ~900MB   |
| python/        | Python 3.12独立环境    | ~50MB    |
| deps/          | 内置工具(uv, rg, fd等) | ~160MB   |
| frontend/dist/ | 前端构建产物           | ~10MB    |
| install.sh     | 安装脚本               | ~10KB    |
| README.md      | 使用说明               | ~5KB     |

## 使用离线安装包

### 步骤1：传输离线包

将离线包传输到目标机器：

```bash
# 使用scp传输
scp jarvis-offline-*.tar.gz user@target-machine:/home/user/

# 或使用USB存储设备
cp jarvis-offline-*.tar.gz /media/usb/
```

### 步骤2：解压离线包

在目标机器上解压：

```bash
# 解压离线包
tar -xzf jarvis-offline-*.tar.gz

# 进入解压目录
cd jarvis-offline
```

### 步骤3：运行安装脚本

```bash
# 默认安装到 ~/Jarvis
./install.sh

# 或指定安装目录
./install.sh /opt/jarvis
```

### 步骤4：激活环境

安装完成后，激活环境：

```bash
# Bash用户
source ~/.bashrc

# Zsh用户
source ~/.zshrc

# Fish用户
source ~/.config/fish/config.fish

# 或直接激活虚拟环境
source ~/Jarvis/.venv/bin/activate
```

### 步骤5：验证安装

```bash
# 检查Jarvis版本
jarvis --version

# 启动Jarvis
jarvis
```

## 安装过程详解

### 安装脚本执行流程

1. **源码安装**：将Jarvis源码复制到目标目录
2. **虚拟环境配置**：复制虚拟环境并修复路径引用
3. **Python环境配置**：配置Python 3.12环境
4. **内置依赖安装**：安装内置工具(uv, rg, fd等)
5. **前端构建产物**：安装前端构建结果
6. **系统安装**：将Jarvis安装到系统PATH
7. **Shell配置**：更新Shell配置文件
8. **安装验证**：验证安装结果

### 路径修复机制

离线包中的虚拟环境包含原始打包机器的路径引用。安装脚本会自动修复以下内容：

- **bin目录脚本**：更新Python解释器路径
- **pyvenv.cfg**：更新home目录配置
- **shebang行**：修复脚本执行路径

## 常见问题

### Q1: 离线包体积太大怎么办？

**解决方案**：

1. **排除node_modules**：打包脚本已自动排除node_modules，安装时会重新构建
2. **清理缓存**：打包前清理虚拟环境缓存
   ```bash
   find .venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
   find .venv -type f -name "*.pyc" -delete 2>/dev/null || true
   ```
3. **压缩优化**：使用更高压缩率
   ```bash
   tar -cvf jarvis-offline.tar jarvis-offline/
   gzip -9 jarvis-offline.tar
   ```

### Q2: 安装后jarvis命令不可用？

**解决方案**：

1. **检查PATH配置**：

   ```bash
   echo $PATH
   # 应包含 ~/Jarvis/.venv/bin
   ```

2. **手动激活环境**：

   ```bash
   source ~/Jarvis/.venv/bin/activate
   ```

3. **重新安装**：
   ```bash
   cd ~/Jarvis
   pip install -e .
   ```

### Q3: 架构不匹配怎么办？

**解决方案**：

离线包为特定架构打包，必须确保架构匹配：

```bash
# 检查当前架构
uname -m

# 检查离线包架构（查看README.md）
cat jarvis-offline/README.md
```

如果架构不匹配，需要重新打包或使用在线安装方式。

### Q4: Python版本冲突？

**解决方案**：

Jarvis严格要求Python 3.12。离线包已包含Python 3.12环境，但如果系统有其他Python版本，可能产生冲突：

```bash
# 检查系统Python版本
python --version
python3 --version

# 使用虚拟环境中的Python
~/Jarvis/.venv/bin/python --version
```

### Q5: 前端无法访问？

**解决方案**：

如果前端构建产物缺失，需要重新构建：

```bash
cd ~/Jarvis/src/jarvis/jarvis_service/frontend
npm install
npm run build
```

## 高级用法

### 自定义打包内容

修改打包脚本以包含/排除特定内容：

```bash
# 编辑打包脚本
vim scripts/create_offline_package.sh

# 自定义EXCLUDE_PATTERNS
EXCLUDE_PATTERNS="
--exclude=.git
--exclude=node_modules
--exclude=tests  # 排除测试文件
--exclude=docs   # 排除文档
"
```

### 多架构打包

为不同架构创建离线包：

```bash
# 在x86_64机器上打包
./scripts/create_offline_package.sh output_x86_64

# 在aarch64机器上打包
./scripts/create_offline_package.sh output_aarch64
```

### 版本管理

为特定版本创建离线包：

```bash
# 切换到特定版本
git checkout v3.1.20

# 创建离线包
./scripts/create_offline_package.sh output_v3.1.20
```

## 更新和维护

### 更新离线包

当Jarvis更新后，重新创建离线包：

```bash
# 更新源码
git pull origin main

# 更新依赖
pip install -e .

# 重新打包
./scripts/create_offline_package.sh
```

### 离线环境更新

在离线环境中更新Jarvis：

1. **创建新版本离线包**（在有网络的机器上）
2. **传输到离线环境**
3. **备份旧版本**：
   ```bash
   mv ~/Jarvis ~/Jarvis.backup
   ```
4. **安装新版本**：
   ```bash
   ./install.sh ~/Jarvis
   ```

## 安全注意事项

### 离线包安全

- **传输安全**：使用加密传输方式（如scp over SSH）
- **存储安全**：妥善保管离线包，避免未授权访问
- **版本验证**：验证离线包的完整性和来源

### 安装后安全

- **API密钥**：配置API密钥时注意安全存储
- **配置文件**：保护配置文件中的敏感信息
- **日志文件**：定期清理日志文件中的敏感信息

## 技术支持

### 获取帮助

- **GitHub Issues**: https://github.com/skyfireitdiy/Jarvis/issues
- **文档**: https://github.com/skyfireitdiy/Jarvis/docs
- **社区**: 加入Jarvis社区获取支持

### 反馈问题

遇到问题时，请提供以下信息：

1. 系统架构和版本
2. 离线包创建时间和架构
3. 安装日志输出
4. 错误信息和截图

## 附录

### 打包脚本参数

```bash
./scripts/create_offline_package.sh [输出目录]
```

| 参数     | 说明           | 默认值            |
| -------- | -------------- | ----------------- |
| 输出目录 | 离线包输出路径 | ./offline_package |

### 安装脚本参数

```bash
./install.sh [安装目录]
```

| 参数     | 说明           | 默认值   |
| -------- | -------------- | -------- |
| 安装目录 | Jarvis安装路径 | ~/Jarvis |

### 离线包文件结构

```
jarvis-offline/
├── source/              # Jarvis源码
│   ├── src/
│   ├── builtin/
│   ├── pyproject.toml
│   └── ...
├── venv/                # Python虚拟环境
│   ├── bin/             # 可执行文件
│   ├── lib/             # Python库
│   └── pyvenv.cfg       # 虚拟环境配置
├── python/              # Python独立环境
│   └── cpython-3.12.x-linux-x86_64-gnu/  # uv创建的cpython子目录
│       ├── bin/         # Python可执行文件
│       │   └── python3.12
│       └── lib/         # Python标准库
├── deps/                # 内置工具（仅当前架构）
│   └── x86_64_linux/    # 或 aarch64_linux，取决于打包机器架构
│       ├── bin/         # uv, rg, fd等
│       └── lib/         # 依赖库
├── frontend/            # 前端构建产物
│   └── dist/            # 构建结果
├── install.sh           # 安装脚本
└── README.md            # 使用说明
```

---

**最后更新**: 2025-01-15
**版本**: 1.0
**作者**: Jarvis Team
