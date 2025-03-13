import importlib
import inspect
import os
import re
import sys
from typing import Dict, Type, Optional, List
from jarvis.jarvis_lsp.base import BaseLSP
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

REQUIRED_METHODS = [
    ('initialize', ['workspace_path']),
    ('find_references', ['file_path', 'position']),
    ('find_definition', ['file_path', 'position']),
    ('get_document_symbols', ['file_path']),
    ('get_diagnostics', ['file_path']),
    ('prepare_rename', ['file_path', 'position']),
    ('shutdown', [])
]

class LSPRegistry:
    """LSP server registry"""

    global_lsp_registry = None

    @staticmethod
    def get_lsp_dir() -> str:
        """Get LSP implementation directory."""
        user_lsp_dir = os.path.expanduser("~/.jarvis/lsp")
        if not os.path.exists(user_lsp_dir):
            try:
                os.makedirs(user_lsp_dir)
                with open(os.path.join(user_lsp_dir, "__init__.py"), "w") as f:
                    pass
            except Exception as e:
                PrettyOutput.print(f"创建 LSP 目录失败: {str(e)}", OutputType.ERROR)
                return ""
        return user_lsp_dir

    @staticmethod
    def check_lsp_implementation(lsp_class: Type[BaseLSP]) -> bool:
        """Check if the LSP class implements all necessary methods."""
        missing_methods = []
        
        for method_name, params in REQUIRED_METHODS:
            if not hasattr(lsp_class, method_name):
                missing_methods.append(method_name)
                continue
                
            method = getattr(lsp_class, method_name)
            if not callable(method):
                missing_methods.append(method_name)
                continue
                
            sig = inspect.signature(method)
            method_params = [p for p in sig.parameters if p != 'self']
            if len(method_params) != len(params):
                missing_methods.append(f"{method_name}(parameter mismatch)")
        
        if missing_methods:
            PrettyOutput.print(
                f"LSP {lsp_class.__name__} 缺少必要的方法: {', '.join(missing_methods)}", 
                OutputType.WARNING
            )
            return False
            
        return True

    @staticmethod
    def load_lsp_from_dir(directory: str) -> Dict[str, Type[BaseLSP]]:
        """Load LSP implementations from specified directory."""
        lsp_servers = {}
        
        if not os.path.exists(directory):
            PrettyOutput.print(f"LSP 目录不存在: {directory}", OutputType.WARNING)
            return lsp_servers
            
        package_name = None
        if directory == os.path.dirname(__file__):
            package_name = "jarvis.jarvis_lsp"
            
        if directory not in sys.path:
            sys.path.append(directory)
        
        for filename in os.listdir(directory):
            if filename.endswith('.py') and not filename.startswith('__'):
                module_name = filename[:-3]
                try:
                    if package_name:
                        module = importlib.import_module(f"{package_name}.{module_name}")
                    else:
                        module = importlib.import_module(module_name)
                    
                    for _, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) and 
                            issubclass(obj, BaseLSP) and 
                            obj != BaseLSP and
                            hasattr(obj, 'language')):
                            if not LSPRegistry.check_lsp_implementation(obj):
                                continue
                            if hasattr(obj, 'check'):
                                if not obj.check(): # type: ignore
                                    continue
                            lsp_servers[obj.language] = obj
                            break
                except Exception as e:
                    PrettyOutput.print(f"加载 LSP {module_name} 失败: {str(e)}", OutputType.ERROR)
        
        return lsp_servers

    @staticmethod
    def get_global_lsp_registry():
        """Get global LSP registry instance."""
        if LSPRegistry.global_lsp_registry is None:
            LSPRegistry.global_lsp_registry = LSPRegistry()
        return LSPRegistry.global_lsp_registry
    
    def __init__(self):
        """Initialize LSP registry."""
        self.lsp_servers: Dict[str, Type[BaseLSP]] = {}
        
        # Load from user LSP directory
        lsp_dir = LSPRegistry.get_lsp_dir()
        if lsp_dir and os.path.exists(lsp_dir):
            for language, lsp_class in LSPRegistry.load_lsp_from_dir(lsp_dir).items():
                self.register_lsp(language, lsp_class)
                
        # Load from built-in LSP directory
        lsp_dir = os.path.dirname(__file__)
        if lsp_dir and os.path.exists(lsp_dir):
            for language, lsp_class in LSPRegistry.load_lsp_from_dir(lsp_dir).items():
                self.register_lsp(language, lsp_class)

    def register_lsp(self, language: str, lsp_class: Type[BaseLSP]):
        """Register LSP implementation for a language."""
        self.lsp_servers[language] = lsp_class
            
    def create_lsp(self, language: str) -> Optional[BaseLSP]:
        """Create LSP instance for specified language."""
        if language not in self.lsp_servers:
            PrettyOutput.print(f"没有找到 LSP 支持的语言: {language}", OutputType.WARNING)
            return None
            
        try:
            lsp = self.lsp_servers[language]()
            return lsp
        except Exception as e:
            PrettyOutput.print(f"创建 LSP 失败: {str(e)}", OutputType.ERROR)
            return None

    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages."""
        return list(self.lsp_servers.keys())
    
    @staticmethod
    def get_text_at_position(file_path: str, line: int, start_character: int) -> str:
        """Get text at position."""
        with open(file_path, 'r') as file:
            lines = file.readlines()
            symbol = re.search(r'\b\w+\b', lines[line][start_character:])
            return symbol.group() if symbol else ""
        
    @staticmethod
    def get_line_at_position(file_path: str, line: int) -> str:
        """Get line at position."""
        with open(file_path, 'r') as file:
            lines = file.readlines()
            return lines[line]

def main():
    """CLI entry point for LSP testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description='LSP functionality testing')
    parser.add_argument('--language', type=str, required=True, help='Programming language')
    parser.add_argument('--file', type=str, required=True, help='File to analyze')
    parser.add_argument('--action', choices=['symbols', 'diagnostics', 'references', 'definition'],
                       required=True, help='Action to perform')
    parser.add_argument('--line', type=int, help='Line number (0-based) for references/definition')
    parser.add_argument('--character', type=int, help='Character position for references/definition')
    
    args = parser.parse_args()
    
    # Initialize LSP
    registry = LSPRegistry.get_global_lsp_registry()
    lsp = registry.create_lsp(args.language)
    
    if not lsp:
        PrettyOutput.print(f"没有 LSP 支持的语言: {args.language}", OutputType.WARNING)
        return 1
        
    if not lsp.initialize(os.path.abspath(os.getcwd())):
        PrettyOutput.print("LSP 初始化失败", OutputType.WARNING)
        return 1
    
    try:
        # Execute requested action
        if args.action == 'symbols':
            symbols = lsp.get_document_symbols(args.file)
            for symbol in symbols:
                print(f"Symbol {LSPRegistry.get_text_at_position(args.file, symbol['range']['start']['line'], symbol['range']['start']['character'])} at {symbol['range']['start']['line']}:{symbol['range']['start']['character']}: {symbol['uri']}")
                
        elif args.action == 'diagnostics':
            diagnostics = lsp.get_diagnostics(args.file)
            for diag in diagnostics:
                severity = ['Error', 'Warning', 'Info', 'Hint'][diag['severity'] - 1]
                PrettyOutput.print(f"{severity} 在 {diag['range']['start']['line']}:{diag['range']['start']['character']}: {diag['message']}", OutputType.INFO)
                
        elif args.action in ('references', 'definition'):
            if args.line is None or args.character is None:
                PrettyOutput.print("需要行和字符位置用于 references/definition", OutputType.WARNING)
                return 1
                
            if args.action == 'references':
                refs = lsp.find_references(args.file, (args.line, args.character))
                for ref in refs:
                    PrettyOutput.print(f"引用在 {ref['uri']} 在 {ref['range']['start']['line']}:{ref['range']['start']['character']}\n行: {LSPRegistry.get_line_at_position(ref['uri'], ref['range']['start']['line'])}", OutputType.INFO)
            else:
                defn = lsp.find_definition(args.file, (args.line, args.character))
                if defn:
                    PrettyOutput.print(f"定义在 {defn['uri']} 在 {defn['range']['start']['line']}:{defn['range']['start']['character']}\n行: {LSPRegistry.get_line_at_position(defn['uri'], defn['range']['start']['line'])}", OutputType.INFO)
                else:
                    PrettyOutput.print("没有找到定义", OutputType.WARNING)
                    
    except Exception as e:
        PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)
        return 1
    finally:
        lsp.shutdown()
    
    return 0

if __name__ == "__main__":
    exit(main())
