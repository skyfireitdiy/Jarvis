|
| Python                | python-lsp-server          | `pip install "python-lsp-server[all]"`                 | `python`                   |
| Rust                  | rust-analyzer              | `rustup component add rust-analyzer`                   | `rust`                     |
| JavaScript/TypeScript | typescript-language-server | `npm install -g typescript typescript-language-server` | `javascript`, `typescript` |
| Go                    | gopls                      | `go install golang.org/x/tools/gopls@latest`           | `go`                       |
| C/C++                 | clangd                     | `apt install clangd` 或 `brew install clangd`          | `c`, `cpp`                 |
| Java                  | jdt.ls                     | 下载 Eclipse 插件或使用 VSCode 扩展                    | `java`                     |
| PHP                   | intelephense               | `npm install -g intelephense`                          | `php`                      |
| Lua                   | lua-language-server        | 下载二进制或从源码编译                                 | `lua`                      |

**安装失败排查**：

1. **检查系统环境**

   ```bash
   # 检查 PATH
   echo $PATH

   # 检查包管理器
   pip --version
   npm --version
   go version
   rustc --version
   ```

2. **检查权限**
   - 如果需要 sudo，使用 `sudo pip install` 或 `sudo npm install -g`
   - 或使用用户目录安装：`pip install --user`、`npm config set prefix ~/.local`

3. **查看错误日志**
   - 大多数 LSP server 在启动时会输出详细日志
   - 可以在终端直接运行 `<lsp-server-command>` 查看错误

4. **查找替代方案**
   - 如果一个 LSP server 不工作，可以尝试其他实现
   - 例如：Python 有 pyls、pylsp、pyright 等多种选择

**使用方法**：

```bash
jlsp document_symbols src/main.rs --language rust
jlsp def-name src/main.rs MyStruct --language rust
```

**注意**：`--language` 参数是必填项，所有命令都必须指定。

## 总结

**核心原则**：

1. 优先使用基于符号名的命令，避免精确列号
2. 先了解文件结构，再进行符号查询
3. 结合诊断和修复建议，提升代码质量
4. 利用守护进程复用，优化性能

**适用场景**：

- 代码理解和分析
- 符号导航和定位
- 代码质量检查
- 代码修复和重构

**不适用场景**：

- 简单的文本搜索（应使用 rg、grep）
- 非代码文件的查询
- 不支持 LSP 的编程语言
