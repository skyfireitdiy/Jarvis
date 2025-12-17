import json
import os
from dataclasses import dataclass
from typing import Dict
from typing import List
from typing import Optional


@dataclass
class Symbol:
    """表示代码中的单个符号。"""

    name: str
    kind: str  # 例如：'function'(函数)、'class'(类)、'variable'(变量)、'import'(导入)
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    # 根据需要添加更多字段，例如父作用域
    parent: Optional[str] = None
    # 定义位置（对于引用/调用，指向符号定义的位置）
    definition_location: Optional["Symbol"] = None  # 指向定义Symbol的引用
    is_definition: bool = False  # 如果此符号是定义则为True，如果是引用/调用则为False


class SymbolTable:
    """存储并提供对项目中符号的访问。"""

    def __init__(self, cache_dir: Optional[str] = None):
        # 按名称存储符号的字典，用于快速查找
        # 一个符号名可能出现在多个文件中，因此使用列表存储
        self.symbols_by_name: Dict[str, List[Symbol]] = {}
        # 按文件存储符号的字典
        self.symbols_by_file: Dict[str, List[Symbol]] = {}
        # 跟踪文件修改时间用于缓存失效
        self._file_mtimes: Dict[str, float] = {}
        # 持久化存储的缓存目录
        self.cache_dir = cache_dir or ".jarvis/symbol_cache"
        # 如果可用则加载缓存数据
        self._load_from_cache()

    def _get_cache_file(self) -> str:
        """获取缓存文件路径。"""
        return os.path.join(self.cache_dir, "symbol_table.json")

    def _load_from_cache(self) -> None:
        """从缓存文件加载符号表数据。"""
        cache_file = self._get_cache_file()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 将JSON数据转换回Symbol对象
                self.symbols_by_name = self._deserialize_symbols(
                    data.get("symbols_by_name", {})
                )
                self.symbols_by_file = self._deserialize_symbols(
                    data.get("symbols_by_file", {})
                )
                # 加载文件修改时间
                self._file_mtimes = data.get("file_mtimes", {})
            except Exception:
                # 如果缓存加载失败，则从空表开始
                pass

    def _save_to_cache(self) -> None:
        """将符号表数据保存到缓存文件。"""
        try:
            # 确保缓存目录存在
            os.makedirs(self.cache_dir, exist_ok=True)
            cache_file = self._get_cache_file()

            # 保存前更新文件修改时间
            self._update_file_mtimes()

            # 序列化符号以便JSON存储
            data = {
                "symbols_by_name": self._serialize_symbols(self.symbols_by_name),
                "symbols_by_file": self._serialize_symbols(self.symbols_by_file),
                "file_mtimes": self._file_mtimes,
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            # 如果缓存保存失败，则继续而不缓存
            pass

    def _serialize_symbols(
        self, symbol_dict: Dict[str, List[Symbol]]
    ) -> Dict[str, List[dict]]:
        """将Symbol对象转换为可序列化的字典。"""
        serialized = {}
        for key, symbols in symbol_dict.items():
            serialized[key] = [self._symbol_to_dict(symbol) for symbol in symbols]
        return serialized

    def _deserialize_symbols(
        self, symbol_dict: Dict[str, List[dict]]
    ) -> Dict[str, List[Symbol]]:
        """将序列化的字典转换回Symbol对象。"""
        deserialized = {}
        for key, symbol_data_list in symbol_dict.items():
            deserialized[key] = [
                self._dict_to_symbol(data) for data in symbol_data_list
            ]
        return deserialized

    def _symbol_to_dict(self, symbol: Symbol) -> dict:
        """将Symbol对象转换为字典。"""
        result = {
            "name": symbol.name,
            "kind": symbol.kind,
            "file_path": symbol.file_path,
            "line_start": symbol.line_start,
            "line_end": symbol.line_end,
            "signature": symbol.signature,
            "docstring": symbol.docstring,
            "parent": symbol.parent,
            "is_definition": getattr(symbol, "is_definition", False),
        }
        # 序列化定义位置（只保存基本信息，避免循环引用）
        if hasattr(symbol, "definition_location") and symbol.definition_location:
            result["definition_location"] = {
                "file_path": symbol.definition_location.file_path,
                "line_start": symbol.definition_location.line_start,
                "line_end": symbol.definition_location.line_end,
                "name": symbol.definition_location.name,
            }
        return result

    def _dict_to_symbol(self, data: dict) -> Symbol:
        """将字典转换回Symbol对象。"""
        symbol = Symbol(
            name=data["name"],
            kind=data["kind"],
            file_path=data["file_path"],
            line_start=data["line_start"],
            line_end=data["line_end"],
            signature=data.get("signature"),
            docstring=data.get("docstring"),
            parent=data.get("parent"),
            is_definition=data.get("is_definition", False),
        )
        # 恢复定义位置（创建临时 Symbol 对象）
        if "definition_location" in data and data["definition_location"]:
            def_loc = data["definition_location"]
            symbol.definition_location = Symbol(
                name=def_loc["name"],
                kind="",  # 未知类型
                file_path=def_loc["file_path"],
                line_start=def_loc["line_start"],
                line_end=def_loc["line_end"],
            )
        return symbol

    def add_symbol(self, symbol: Symbol, save_to_cache: bool = False) -> None:
        """向表中添加符号。

        参数:
            symbol: 要添加的符号
            save_to_cache: 如果为True，立即保存到缓存。默认为False以提高性能。
                          批量操作后使用save_cache()一次性保存所有符号。
        """
        if symbol.name not in self.symbols_by_name:
            self.symbols_by_name[symbol.name] = []
        self.symbols_by_name[symbol.name].append(symbol)

        if symbol.file_path not in self.symbols_by_file:
            self.symbols_by_file[symbol.file_path] = []
        self.symbols_by_file[symbol.file_path].append(symbol)

        # 仅在明确请求时保存到缓存（出于性能考虑）
        if save_to_cache:
            self._save_to_cache()

    def save_cache(self) -> None:
        """将整个符号表保存到缓存。批量操作后调用此方法。"""
        self._save_to_cache()

    def find_symbol(self, name: str, file_path: Optional[str] = None) -> List[Symbol]:
        """
        通过名称查找符号。
        如果提供了file_path，则搜索仅限于该文件。
        """
        if file_path:
            return [s for s in self.get_file_symbols(file_path) if s.name == name]
        return self.symbols_by_name.get(name, [])

    def get_file_symbols(self, file_path: str) -> List[Symbol]:
        """获取特定文件中的所有符号。"""
        return self.symbols_by_file.get(file_path, [])

    def clear_file_symbols(self, file_path: str) -> None:
        """移除与特定文件关联的所有符号。"""
        if file_path in self.symbols_by_file:
            symbols_to_remove = self.symbols_by_file.pop(file_path)
            for symbol in symbols_to_remove:
                if symbol.name in self.symbols_by_name:
                    self.symbols_by_name[symbol.name] = [
                        s
                        for s in self.symbols_by_name[symbol.name]
                        if s.file_path != file_path
                    ]
                    if not self.symbols_by_name[symbol.name]:
                        del self.symbols_by_name[symbol.name]

            # 移除文件修改时间跟踪
            if file_path in self._file_mtimes:
                del self._file_mtimes[file_path]

            # 清除后保存到缓存
            self._save_to_cache()

    def _update_file_mtimes(self) -> None:
        """更新所有跟踪文件的修改时间。"""
        for file_path in list(self.symbols_by_file.keys()):
            if os.path.exists(file_path):
                try:
                    self._file_mtimes[file_path] = os.path.getmtime(file_path)
                except Exception:
                    # 如果无法获取修改时间，则从跟踪中移除
                    self._file_mtimes.pop(file_path, None)

    def is_file_stale(self, file_path: str) -> bool:
        """检查文件自缓存后是否已被修改。

        参数:
            file_path: 要检查的文件路径

        返回:
            如果文件比缓存新则为True，否则为False
        """
        if file_path not in self.symbols_by_file:
            # 文件不在缓存中，视为已过期（需要加载）
            return True

        if file_path not in self._file_mtimes:
            # 没有记录修改时间，视为已过期
            return True

        if not os.path.exists(file_path):
            # 文件不存在，不算过期（将由clear_file_symbols处理）
            return False

        try:
            current_mtime = os.path.getmtime(file_path)
            cached_mtime = self._file_mtimes.get(file_path, 0)
            return current_mtime > cached_mtime
        except Exception:
            # 如果无法获取修改时间，则假定未过期
            return False


class SymbolExtractor:
    """从源代码文件中提取符号。"""

    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        """
        从代码中提取符号（函数、类、变量等）。
        此方法应由特定语言的子类实现。
        """
        raise NotImplementedError("Subclasses must implement this method.")
