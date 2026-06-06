# Android 签名密钥信息

## 密钥库信息

- **密钥库文件**: `android/app/jarvis-release-key.jks`
- **密钥别名**: `jarvis-key`
- **密钥算法**: RSA 2048
- **有效期**: 10000 天
- **组织信息**: CN=Jarvis Team, OU=Development, O=Jarvis, L=Beijing, ST=Beijing, C=CN

## ⚠️ 安全注意事项

**绝对禁止：**
- ❌ 不要将 keystore 文件（.jks, .keystore）提交到 Git
- ❌ 不要将密码写入代码或配置文件
- ❌ 不要在公开场合分享密码

**密码管理：**
- keystore 文件已添加到 `.gitignore`
- 密码仅通过环境变量或 GitHub Secrets 传递
- 本地构建使用环境变量，CI/CD 使用 GitHub Secrets

## GitHub Actions 配置

### 需要配置的 GitHub Secrets

在 GitHub 仓库的 Settings → Secrets and variables → Actions 中添加以下 secrets：

| Secret 名称 | 说明 | 示例值 |
|------------|------|--------|
| `ANDROID_KEYSTORE_FILE` | keystore 文件的 base64 编码 | (base64 字符串) |
| `KEYSTORE_KEY_ALIAS` | 密钥别名 | `jarvis-key` |
| `KEYSTORE_KEY_PASSWORD` | 密钥密码 | (你的密码) |
| `KEYSTORE_STORE_PASSWORD` | 密钥库密码 | (你的密码) |
| `DEVELOPER_PACKAGE_NAME` | Android 包名 | `app.jarvis.mobile` |

### 生成 ANDROID_KEYSTORE_FILE

将 keystore 文件编码为 base64：

```bash
base64 -i android/app/jarvis-release-key.jks | pbcopy  # macOS
base64 -w 0 android/app/jarvis-release-key.jks  # Linux
```

将输出的 base64 字符串复制到 GitHub Secret `ANDROID_KEYSTORE_FILE` 中。

## 本地构建配置

### 方式 1：使用环境变量（推荐）

在终端中设置环境变量后构建：

```bash
export KEYSTORE_FILE=android/app/jarvis-release-key.jks
export KEYSTORE_KEY_ALIAS=jarvis-key
export KEYSTORE_KEY_PASSWORD=你的密码
export KEYSTORE_STORE_PASSWORD=你的密码

npx cap build android
```

### 方式 2：创建本地配置文件（不推荐）

创建 `android/keystore.properties`（已添加到 .gitignore）：

```properties
storeFile=./app/jarvis-release-key.jks
storePassword=你的密码
keyAlias=jarvis-key
keyPassword=你的密码
```

**注意**：此文件包含敏感信息，确保已添加到 `.gitignore`。

## 签名配置说明

`android/app/build.gradle` 已配置签名配置：

```gradle
signingConfigs {
    release {
        // 从环境变量读取配置
        storeFile file(System.getenv("KEYSTORE_FILE") ?: "./jarvis-release-key.jks")
        storePassword System.getenv("KEYSTORE_STORE_PASSWORD")
        keyAlias System.getenv("KEYSTORE_KEY_ALIAS")
        keyPassword System.getenv("KEYSTORE_KEY_PASSWORD")
    }
}

buildTypes {
    release {
        signingConfig signingConfigs.release
        minifyEnabled false
        proguardFiles getDefaultProguardFile('proguard-android.txt'), 'proguard-rules.pro'
    }
}
```

## 密码信息（本地保存，不要提交）

**默认密码**（仅供初始设置参考）：
- Store Password: `JarvisRelease2024!`
- Key Password: `JarvisRelease2024!`

**重要提示**：
- 这些是生成 keystore 时使用的默认密码
- 在生产环境中，请修改为更安全的密码
- 不要将此文档提交到公开仓库
- 建议将密码保存在密码管理器中

## 验证签名

构建完成后，验证 APK 签名：

```bash
# 查看签名信息
jarsigner -verify -verbose -certs android/app/build/outputs/apk/release/app-release.apk

# 查看证书指纹
keytool -list -v -keystore android/app/jarvis-release-key.jks -alias jarvis-key
```

## 重新生成密钥（如需）

如果需要重新生成签名密钥：

```bash
keytool -genkey -v \
  -keystore android/app/jarvis-release-key.jks \
  -alias jarvis-key \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000
```

按提示输入密码和组织信息。

## 常见问题

### Q: 构建时提示找不到 keystore 文件？
A: 确保环境变量 `KEYSTORE_FILE` 设置正确，或使用绝对路径。

### Q: 签名失败？
A: 检查密码是否正确，使用 `keytool -list -v -keystore xxx.jks` 验证 keystore 文件。

### Q: GitHub Actions 构建失败？
A: 确认所有 Secrets 已正确配置，特别是 `ANDROID_KEYSTORE_FILE` 的 base64 编码。
