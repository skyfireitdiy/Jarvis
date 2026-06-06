# GitHub Secrets 配置指南

本文档说明如何配置 GitHub Secrets 以支持自动构建 Android APK。

## 必需的 Secrets

在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中添加以下 secrets：

### 1. ANDROID_KEYSTORE_FILE

**说明**：Android 签名密钥库文件的 base64 编码

**生成方法**：

```bash
# Linux/macOS
base64 -w 0 src/jarvis/jarvis_service/frontend/android/app/jarvis-release-key.jks

# macOS (复制到剪贴板)
base64 -i src/jarvis/jarvis_service/frontend/android/app/jarvis-release-key.jks | pbcopy
```

将输出的 base64 字符串（一整行，无换行符）复制到 GitHub Secret 中。

### 2. KEYSTORE_KEY_ALIAS

**说明**：密钥别名

**值**：`jarvis-key`

### 3. KEYSTORE_KEY_PASSWORD

**说明**：密钥密码

**默认值**：`JarvisRelease2024!`

⚠️ **重要**：如果您修改了密钥密码，请填入实际密码。

### 4. KEYSTORE_STORE_PASSWORD

**说明**：密钥库密码

**默认值**：`JarvisRelease2024!`

⚠️ **重要**：如果您修改了密钥库密码，请填入实际密码。

## 配置步骤

1. 进入 GitHub 仓库页面
2. 点击 **Settings**（设置）
3. 左侧菜单选择 **Secrets and variables → Actions**
4. 点击 **New repository secret**
5. 依次添加上述 4 个 secrets

## 验证配置

配置完成后，可以通过以下方式验证：

### 方式 1：手动触发工作流

1. 进入 **Actions** 标签页
2. 选择 **Build Android APK** 工作流
3. 点击 **Run workflow**
4. 输入版本号（可选，如 `v1.0.0`）或使用默认值 `manual`
5. 点击 **Run workflow** 开始构建

### 方式 2：推送标签触发

```bash
# 创建并推送标签
git tag v1.0.0
git push origin v1.0.0
```

工作流会自动触发，构建完成后会创建 GitHub Release 并上传 APK。

## 构建产物

构建成功后，APK 文件会：

1. **上传到 GitHub Actions Artifacts**
   - 保留 30 天
   - 文件名格式：`jarvis-{version}-{short_sha}.apk`
   - 在工作流运行详情页可下载

2. **创建 GitHub Release**（仅标签触发）
   - 自动生成 Release Notes
   - APK 作为 Release 附件
   - 可在 **Releases** 页面查看和下载

## 常见问题

### Q: 构建失败提示 "Keystore file not found"？

A: 检查 `ANDROID_KEYSTORE_FILE` 是否正确配置：

- 确保 base64 编码正确（无换行符）
- 使用 `base64 -w 0` 参数（Linux）或 `base64 -i`（macOS）

### Q: 构建失败提示 "Failed to sign APK"？

A: 检查密码是否正确：

- 确认 `KEYSTORE_KEY_PASSWORD` 和 `KEYSTORE_STORE_PASSWORD` 与 keystore 文件匹配
- 可以在本地使用以下命令验证密码：

  ```bash
  keytool -list -v -keystore src/jarvis/jarvis_service/frontend/android/app/jarvis-release-key.jks
  ```

### Q: 如何修改密码？

A: 修改 GitHub Secrets 中的密码值即可，无需修改工作流文件。

### Q: 构建需要多长时间？

A: 通常 5-10 分钟，具体取决于 GitHub Actions 队列和网络状况。

### Q: 如何下载构建的 APK？

**方式 1（Artifacts）：**

1. 进入 **Actions** → 选择构建运行记录
2. 在 **Artifacts** 部分下载 APK

**方式 2（Releases）：**

1. 进入 **Releases** 页面
2. 找到对应版本的 Release
3. 在 **Assets** 部分下载 APK

## 安全建议

1. **定期更换密码**：建议每 6-12 个月更换一次密钥库密码
2. **限制访问权限**：只授予必要的人员仓库 Settings 访问权限
3. **备份 keystore**：在安全的地方备份 `jarvis-release-key.jks` 文件
4. **监控构建日志**：定期检查 Actions 构建日志，确保无异常

## 更多信息

- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [Capacitor Android 构建指南](https://capacitorjs.com/docs/android)
- [Android 签名文档](https://developer.android.com/studio/publish/app-signing)
