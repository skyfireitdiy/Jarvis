# -*- coding: utf-8 -*-
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class CtagsTool:
    name = "ctags"
    description = "符号定义查找工具，用于查找某个符号的定义位置，仅在CodeAgent模式下可用"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "要查找的符号名称（函数名、类名、变量名等）"
            }
        },
        "required": ["symbol"]
    }
    
    @classmethod
    def check(cls) -> bool:
        """检查工具是否可用，仅在CodeAgent模式下启用，且需要安装ctags工具"""
        # 检查是否在CodeAgent模式下
        if os.environ.get("JARVIS_CODE_AGENT", "") != "1":
            return False
        
        # 检查ctags工具是否安装
        try:
            result = subprocess.run(
                ["ctags", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _get_git_root(self) -> Optional[Path]:
        """获取 git 根目录"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                git_root = result.stdout.strip()
                if git_root:
                    return Path(git_root)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None
    
    def _get_tags_file_path(self) -> Optional[Path]:
        """获取 tags 文件路径，位于 git 根目录下的 .jarvis/ctags/tags"""
        git_root = self._get_git_root()
        if not git_root:
            return None
        tags_dir = git_root / ".jarvis" / "ctags"
        return tags_dir / "tags"
    
    def _ensure_tags_index(self) -> bool:
        """确保 ctags 索引存在且是最新的"""
        try:
            tags_file = self._get_tags_file_path()
            if not tags_file:
                PrettyOutput.print("❌ 未找到 git 仓库根目录，无法生成 ctags 索引", OutputType.ERROR)
                return False
            
            # 确保 .jarvis/ctags 目录存在
            tags_dir = tags_file.parent
            tags_dir.mkdir(parents=True, exist_ok=True)
            
            tags_exists = tags_file.exists()
            
            # 检查是否需要更新索引
            # 如果索引不存在，或者索引文件比源代码文件旧，则需要更新
            need_update = False
            
            if not tags_exists:
                PrettyOutput.print("📝 ctags 索引文件不存在，开始生成...", OutputType.INFO)
                need_update = True
            else:
                # 检查是否有源代码文件比索引文件新
                tags_mtime = tags_file.stat().st_mtime
                git_root = self._get_git_root()
                if not git_root:
                    return False
                
                # 检查所有常见的源代码文件扩展名
                source_extensions = [
                    "*.py", "*.js", "*.ts", "*.jsx", "*.tsx",  # Python, JavaScript, TypeScript
                    "*.java", "*.kt", "*.scala",  # JVM 语言
                    "*.c", "*.cpp", "*.cc", "*.cxx", "*.h", "*.hpp",  # C/C++
                    "*.rs",  # Rust
                    "*.go",  # Go
                    "*.rb",  # Ruby
                    "*.php",  # PHP
                    "*.swift",  # Swift
                    "*.m", "*.mm",  # Objective-C
                    "*.sh", "*.bash",  # Shell
                    "*.lua",  # Lua
                    "*.r", "*.R",  # R
                    "*.pl", "*.pm",  # Perl
                    "*.sql",  # SQL
                ]
                source_files = []
                for ext in source_extensions:
                    source_files.extend(git_root.rglob(ext))
                
                # 检查最近修改的源代码文件
                if source_files:
                    latest_source_mtime = max(f.stat().st_mtime for f in source_files if f.exists())
                    if latest_source_mtime > tags_mtime:
                        PrettyOutput.print("🔄 检测到源代码文件更新，需要更新 ctags 索引...", OutputType.INFO)
                        need_update = True
                    else:
                        PrettyOutput.print("✅ ctags 索引文件已存在且是最新的", OutputType.SUCCESS)
                else:
                    # 如果没有源代码文件，但索引存在，不需要更新
                    PrettyOutput.print("✅ ctags 索引文件已存在", OutputType.SUCCESS)
            
            if need_update:
                # 生成/更新索引
                PrettyOutput.print("🔨 正在生成/更新 ctags 索引...", OutputType.INFO)
                
                git_root = self._get_git_root()
                if not git_root:
                    return False
                
                # 构建 ctags 命令
                # 使用 -R 递归扫描，支持所有语言，排除常见的不需要索引的文件和目录
                # 使用 -f 指定输出文件路径
                cmd = [
                    "ctags",
                    "-R",
                    "--sort=yes",
                    f"-f{tags_file}",
                    "--exclude=*.pyc",
                    "--exclude=__pycache__",
                    "--exclude=node_modules",
                    "--exclude=.git",
                    "--exclude=.svn",
                    "--exclude=.hg",
                    "--exclude=.jarvis",
                    "--exclude=*.o",
                    "--exclude=*.so",
                    "--exclude=*.dylib",
                    "--exclude=*.dll",
                    "--exclude=*.exe",
                    "--exclude=*.class",
                    "--exclude=*.jar",
                    "--exclude=*.war",
                    "--exclude=target",
                    "--exclude=build",
                    "--exclude=dist",
                    str(git_root)
                ]
                
                PrettyOutput.print(f"⚙️  执行命令: {' '.join(cmd)}", OutputType.INFO)
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
                
                if result.returncode != 0:
                    PrettyOutput.print(f"❌ 生成 ctags 索引失败: {result.stderr}", OutputType.ERROR)
                    return False
                
                if tags_file.exists():
                    file_size = tags_file.stat().st_size
                    PrettyOutput.print(f"✅ ctags 索引生成成功（文件大小: {file_size} 字节）", OutputType.SUCCESS)
                else:
                    PrettyOutput.print("⚠️  ctags 索引文件未生成，但命令执行成功", OutputType.WARNING)
                    return False
            
            return True
            
        except FileNotFoundError:
            PrettyOutput.print("❌ ctags 命令未找到，请先安装 ctags 工具", OutputType.ERROR)
            return False
        except Exception as e:
            PrettyOutput.print(f"❌ 生成 ctags 索引时出错: {str(e)}", OutputType.ERROR)
            return False
    
    def _find_symbol_with_ctags(self, symbol: str, file_pattern: Optional[str] = None) -> Dict[str, Any]:
        """使用ctags查找符号定义位置"""
        try:
            tags_file = self._get_tags_file_path()
            if not tags_file or not tags_file.exists():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "ctags 索引文件不存在"
                }
            
            git_root = self._get_git_root()
            if not git_root:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "未找到 git 仓库根目录"
                }
            
            PrettyOutput.print(f"🔍 使用 ctags 查找符号 '{symbol}'...", OutputType.INFO)
            
            # 构建ctags命令
            # 使用 -x 生成交叉引用列表，支持所有语言
            # ctags -x 会在当前目录查找 tags 文件，所以需要在 tags 文件所在目录执行
            cmd = ["ctags", "-x", "--sort=no", symbol]
            
            # 如果指定了文件模式，添加过滤选项
            if file_pattern:
                # ctags -x 不支持直接的文件模式过滤，但可以通过 grep 过滤输出
                # 或者使用 -L 选项配合文件列表，但这里简化处理，在输出后过滤
                pass  # 文件模式过滤在解析输出时处理
            
            PrettyOutput.print(f"⚙️  执行命令: {' '.join(cmd)}", OutputType.INFO)
            
            # 在 tags 文件所在目录执行命令，这样 ctags 会自动找到 tags 文件
            result = subprocess.run(
                cmd,
                cwd=str(tags_file.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            
            if result.returncode != 0:
                PrettyOutput.print(f"❌ ctags 执行失败: {result.stderr}", OutputType.ERROR)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"ctags执行失败: {result.stderr}"
                }
            
            if not result.stdout.strip():
                PrettyOutput.print(f"⚠️  未找到符号 '{symbol}' 的定义", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到符号 '{symbol}' 的定义"
                }
            
            # 解析ctags输出
            lines = result.stdout.strip().split('\n')
            locations = []
            
            PrettyOutput.print(f"📊 解析 ctags 输出，共 {len(lines)} 行结果", OutputType.INFO)
            
            # 如果指定了文件模式，需要导入 fnmatch 进行模式匹配
            if file_pattern:
                import fnmatch
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    symbol_name = parts[0]
                    symbol_type = parts[1]
                    file_path = parts[2]
                    line_number = parts[3] if len(parts) > 3 else "未知"
                    
                    # 如果指定了文件模式，进行过滤
                    if file_pattern:
                        if not fnmatch.fnmatch(file_path, file_pattern):
                            continue
                    
                    locations.append({
                        "symbol": symbol_name,
                        "type": symbol_type,
                        "file": file_path,
                        "line": line_number
                    })
            
            PrettyOutput.print(f"✅ 找到 {len(locations)} 个定义位置", OutputType.SUCCESS)
            
            # 格式化输出
            output_lines = [f"🔍 符号 '{symbol}' 的定义位置:"]
            output_lines.append("─" * 60)
            
            for loc in locations:
                output_lines.append(f"📄 文件: {loc['file']}")
                output_lines.append(f"📍 行号: {loc['line']}")
                output_lines.append(f"🔧 类型: {loc['type']}")
                output_lines.append("─" * 60)
            
            return {
                "success": True,
                "stdout": "\n".join(output_lines),
                "stderr": ""
            }
            
        except FileNotFoundError:
            return {
                "success": False,
                "stdout": "",
                "stderr": "ctags命令未找到，请先安装ctags工具"
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"ctags执行出错: {str(e)}"
            }
    
    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行符号查找操作"""
        try:
            # 检查是否在CodeAgent模式下
            if not self.check():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "ctags工具仅在CodeAgent模式下可用"
                }
            
            symbol = args.get("symbol", "").strip()
            
            if not symbol:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须提供要查找的符号名称"
                }
            
            PrettyOutput.print(f"🚀 开始查找符号: {symbol}", OutputType.INFO)
            
            # 确保 ctags 索引存在且是最新的
            if not self._ensure_tags_index():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "ctags 索引生成失败，无法查找符号"
                }
            
            # 使用ctags查找
            result = self._find_symbol_with_ctags(symbol)
            
            if result["success"]:
                PrettyOutput.print("✨ 符号查找完成", OutputType.SUCCESS)
            else:
                PrettyOutput.print("❌ 符号查找失败", OutputType.ERROR)
            
            return result
            
        except Exception as e:
            PrettyOutput.print(f"ctags工具执行失败: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"ctags工具执行失败: {str(e)}"
            }
