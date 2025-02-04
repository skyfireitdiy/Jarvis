from typing import Dict, Any
import os
from jarvis.utils import OutputType, PrettyOutput
from jarvis.jarvis_rag.main import RAGTool as RAGCore

class RAGTool:
    name = "rag"
    description = "基于文档目录进行问答，支持多种文档格式（txt、pdf、docx等）"
    parameters = {
        "type": "object",
        "properties": {
            "dir": {
                "type": "string",
                "description": "文档目录路径，支持相对路径和绝对路径"
            },
            "question": {
                "type": "string",
                "description": "要询问的问题"
            },
            "rebuild_index": {
                "type": "boolean",
                "description": "是否重建索引",
                "default": False
            }
        },
        "required": ["dir", "question"]
    }

    def __init__(self):
        """初始化 RAG 工具"""
        self.rag_instances = {}  # 缓存不同目录的 RAG 实例

    def _get_rag_instance(self, dir_path: str) -> RAGCore:
        """获取或创建 RAG 实例
        
        Args:
            dir_path: 文档目录的绝对路径
            
        Returns:
            RAGCore: RAG 实例
        """
        if dir_path not in self.rag_instances:
            self.rag_instances[dir_path] = RAGCore(dir_path)
        return self.rag_instances[dir_path]

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行文档问答
        
        Args:
            args: 包含参数的字典
                - dir: 文档目录路径
                - question: 要询问的问题
                - rebuild_index: 是否重建索引
                
        Returns:
            Dict[str, Any]: 执行结果
        """
        try:
            # 获取参数
            dir_path = os.path.expanduser(args["dir"])  # 展开 ~ 等路径
            dir_path = os.path.abspath(dir_path)  # 转换为绝对路径
            question = args["question"]
            rebuild_index = args.get("rebuild_index", False)
            
            # 检查目录是否存在
            if not os.path.exists(dir_path):
                return {
                    "success": False,
                    "error": f"目录不存在: {dir_path}"
                }
                
            # 检查是否是目录
            if not os.path.isdir(dir_path):
                return {
                    "success": False,
                    "error": f"路径不是目录: {dir_path}"
                }
                
            # 获取 RAG 实例
            rag = self._get_rag_instance(dir_path)
            
            # 如果需要重建索引或索引不存在
            if rebuild_index or not rag.is_index_built():
                PrettyOutput.print("正在构建文档索引...", OutputType.INFO)
                rag.build_index(dir_path)
            
            # 执行问答
            PrettyOutput.print(f"问题: {question}", OutputType.INFO)
            response = rag.ask(question)
            
            if response is None:
                return {
                    "success": False,
                    "error": "未能获取答案，可能是没有找到相关文档"
                }
                
            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }
            
        except Exception as e:
            PrettyOutput.print(f"文档问答失败: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "error": f"执行失败: {str(e)}"
            }

def main():
    """命令行直接运行工具"""
    import argparse
    
    parser = argparse.ArgumentParser(description='文档问答工具')
    parser.add_argument('--dir', required=True, help='文档目录路径')
    parser.add_argument('--question', required=True, help='要询问的问题')
    parser.add_argument('--rebuild', action='store_true', help='重建索引')
    args = parser.parse_args()
    
    tool = RAGTool()
    result = tool.execute({
        "dir": args.dir,
        "question": args.question,
        "rebuild_index": args.rebuild
    })
    
    if result["success"]:
        PrettyOutput.print("\n回答:", OutputType.INFO)
        PrettyOutput.print(result["stdout"], OutputType.INFO)
    else:
        PrettyOutput.print(result["error"], OutputType.ERROR)

if __name__ == "__main__":
    main() 