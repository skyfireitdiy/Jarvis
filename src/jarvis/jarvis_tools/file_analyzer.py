from typing import Dict, Any
import os
import pathlib

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class FileAnalyzerTool:
    """
    单文件分析工具
    使用agent深入分析单个文件的结构、实现细节和代码质量
    """
    
    name = "file_analyzer"
    description = "深入分析单个文件的结构、实现细节和代码质量"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要分析的文件路径"
            },
            "root_dir": {
                "type": "string",
                "description": "项目根目录路径（可选）",
                "default": "."
            },
            "objective": {
                "type": "string",
                "description": "描述本次文件分析的目标和用途，例如'准备重构该文件'或'理解该文件在项目中的作用'",
                "default": ""
            }
        },
        "required": ["file_path"]
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单文件分析工具
        
        Args:
            args: 包含参数的字典
            
        Returns:
            包含执行结果的字典
        """
        # 存储原始目录
        original_dir = os.getcwd()
        
        try:
            # 解析参数
            file_path = args.get("file_path", "")
            root_dir = args.get("root_dir", ".")
            objective = args.get("objective", "")
            
            # 验证参数
            if not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须提供文件路径"
                }
            
            # 确保文件路径是相对于root_dir的，如果是绝对路径则转换为相对路径
            abs_file_path = os.path.abspath(file_path)
            abs_root_dir = os.path.abspath(root_dir)
            
            if abs_file_path.startswith(abs_root_dir):
                rel_file_path = os.path.relpath(abs_file_path, abs_root_dir)
            else:
                rel_file_path = file_path
            
            # 获取文件扩展名和文件名
            file_ext = pathlib.Path(file_path).suffix
            file_name = os.path.basename(file_path)
            
            # 创建agent的system prompt
            system_prompt = self._create_system_prompt(
                rel_file_path, file_name, file_ext, root_dir, objective
            )
            
            # 创建agent的summary prompt
            summary_prompt = self._create_summary_prompt(rel_file_path, file_name)
            
            # 切换到根目录
            os.chdir(root_dir)
            
            # 检查文件是否存在
            if not os.path.isfile(rel_file_path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"文件不存在: {rel_file_path}"
                }
            
            # 构建使用的工具
            from jarvis.jarvis_tools.registry import ToolRegistry
            tool_registry = ToolRegistry()
            tool_registry.use_tools([
                "execute_shell", 
                "read_code", 
                "find_symbol",
                "function_analyzer", 
                "find_caller"
            ])
            
            # 创建并运行agent
            analyzer_agent = Agent(
                system_prompt=system_prompt,
                name=f"FileAnalyzer-{file_name}",
                description=f"分析 {file_name} 文件的结构和实现",
                summary_prompt=summary_prompt,
                platform=PlatformRegistry().get_codegen_platform(),
                output_handler=[tool_registry],
                need_summary=True,
                is_sub_agent=True,
                use_methodology=False,
                record_methodology=False,
                execute_tool_confirm=False,
                auto_complete=True
            )
            
            # 运行agent并获取结果
            task_input = f"深入分析文件 {rel_file_path} 的结构、实现细节和代码质量"
            result = analyzer_agent.run(task_input)
            
            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }
                
        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"文件分析失败: {str(e)}"
            }
        finally:
            # 恢复原始目录
            os.chdir(original_dir)
    
    def _create_system_prompt(self, file_path: str, file_name: str, file_ext: str,
                             root_dir: str, objective: str) -> str:
        """
        创建Agent的system prompt
        
        Args:
            file_path: 文件相对路径
            file_name: 文件名
            file_ext: 文件扩展名
            root_dir: 项目根目录
            objective: 分析目标
            
        Returns:
            系统提示文本
        """
        # 根据文件扩展名确定语言
        language_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.c': 'C',
            '.cpp': 'C++',
            '.cs': 'C#',
            '.go': 'Go',
            '.rs': 'Rust',
            '.php': 'PHP',
            '.rb': 'Ruby',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.sh': 'Shell',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.json': 'JSON',
            '.xml': 'XML',
            '.yaml': 'YAML',
            '.md': 'Markdown'
        }
        
        language = language_map.get(file_ext, '未知')
        objective_text = f"\n\n## 分析目标\n{objective}" if objective else ""
        
        return f"""# 代码文件分析专家

## 任务描述
分析文件 `{file_path}` 的内容，专注于分析目标所需的信息，生成有针对性的文件分析报告。{objective_text}

## 文件信息
- 文件路径: `{file_path}`
- 编程语言: {language}
- 项目根目录: `{root_dir}`

## 分析策略
1. 首先理解分析目标，确定你需要查找的信息
2. 灵活采用适合目标的分析方法，不受预设分析框架的限制
3. 专注于与分析目标直接相关的内容，忽略无关部分
4. 根据目标需要自行判断分析的深度和广度

## 探索建议
- 首先读取整个文件内容以获取全局视图
- 识别与分析目标相关的关键部分
- 深入探索这些关键部分，提供有针对性的分析

## 执行指令
- 首先读取整个文件内容:
  ```
  read_code {{
    "files": [{{
      "path": "{file_path}",
      "start_line": 1,
      "end_line": -1
    }}]
  }}
  ```

- 分析文件统计信息:
  ```
  wc -l {file_path}
  ```

- 分析关键符号和函数:
  ```
  find_symbol {{
    "symbol": "关键符号名称",
    "root_dir": "."
  }}
  
  function_analyzer {{
    "function_name": "关键函数名称",
    "file_path": "{file_path}"
  }}
  ```

## 输出要求
- 直接回应分析目标的关键问题
- 提供与目标相关的深入洞察
- 分析内容应直接服务于分析目标
- 避免与目标无关的冗余信息
- 使用具体代码路径和示例支持分析结论
- 提供针对分析目标的具体建议和改进方向"""

    def _create_summary_prompt(self, file_path: str, file_name: str) -> str:
        """
        创建Agent的summary prompt
        
        Args:
            file_path: 文件路径
            file_name: 文件名
            
        Returns:
            总结提示文本
        """
        return f"""# 文件分析报告: `{file_name}`

## 报告要求
生成一份完全以分析目标为导向的文件分析报告。不要遵循固定的报告模板，而是完全根据分析目标来组织内容：

- 专注回答分析目标提出的问题
- 只包含与分析目标直接相关的发现和洞察
- 完全跳过与分析目标无关的内容，无需做全面分析
- 分析深度应与目标的具体需求匹配
- 使用具体的代码片段和实例支持你的观点
- 以清晰的Markdown格式呈现，简洁明了

在分析中保持灵活性，避免固定思维模式。你的任务不是提供全面的文件概览，而是直接解决分析目标中提出的具体问题。""" 