"""文件管理模块 - 文件查看和编辑"""

import logging
from typing import List, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """文件信息"""

    name: str  # 文件名
    path: str  # 完整路径
    is_directory: bool  # 是否为目录
    size: int = 0  # 文件大小
    modified_at: Optional[datetime] = None  # 修改时间


@dataclass
class SearchResult:
    """搜索结果"""

    file_path: str  # 文件路径
    line_number: int  # 行号
    line_content: str  # 行内容
    match_start: int  # 匹配开始位置
    match_end: int  # 匹配结束位置


class FileManager:
    """文件管理器"""

    def __init__(self):
        self._file_cache: Dict[str, str] = {}  # path -> content
        self._cache_max_size = 100

    async def list_files(self, agent_id: str, path: str = "/") -> List[FileInfo]:
        """列出目录文件

        Args:
            agent_id: Agent ID
            path: 目录路径

        Returns:
            List[FileInfo]: 文件信息列表
        """
        # 本地模式：直接读取本地文件系统
        try:
            target_path = Path(path)
            if not target_path.exists():
                logger.warning(f"Path not found: {path}")
                return []

            if not target_path.is_dir():
                logger.warning(f"Path is not a directory: {path}")
                return []

            files = []
            for item in sorted(target_path.iterdir()):
                try:
                    stat = item.stat()
                    files.append(
                        FileInfo(
                            name=item.name,
                            path=str(item),
                            is_directory=item.is_dir(),
                            size=stat.st_size if item.is_file() else 0,
                            modified_at=datetime.fromtimestamp(stat.st_mtime),
                        )
                    )
                except (PermissionError, OSError) as e:
                    logger.warning(f"Cannot access {item}: {e}")
                    continue

            return files
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []

    async def read_file(self, agent_id: str, path: str) -> Optional[str]:
        """读取文件内容

        Args:
            agent_id: Agent ID
            path: 文件路径

        Returns:
            Optional[str]: 文件内容，失败返回None
        """
        # 检查缓存
        if path in self._file_cache:
            return self._file_cache[path]

        try:
            target_path = Path(path)
            if not target_path.exists():
                logger.warning(f"File not found: {path}")
                return None

            if not target_path.is_file():
                logger.warning(f"Path is not a file: {path}")
                return None

            # 检查文件大小（限制1MB）
            if target_path.stat().st_size > 1024 * 1024:
                logger.warning(f"File too large: {path}")
                return None

            # 自动检测编码
            content = self._read_with_encoding(target_path)

            # 更新缓存
            self._update_cache(path, content)

            return content
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return None

    def _read_with_encoding(self, path: Path) -> str:
        """自动检测编码并读取文件"""
        encodings = ["utf-8", "gbk", "gb2312", "latin-1"]

        for encoding in encodings:
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue

        # 如果所有编码都失败，使用latin-1（不会失败）
        return path.read_text(encoding="latin-1")

    async def write_file(self, agent_id: str, path: str, content: str) -> bool:
        """写入文件内容

        Args:
            agent_id: Agent ID
            path: 文件路径
            content: 文件内容

        Returns:
            bool: 写入是否成功
        """
        try:
            target_path = Path(path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")

            # 更新缓存
            self._update_cache(path, content)

            logger.info(f"File written: {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write file: {e}")
            return False

    async def search_files(
        self, agent_id: str, query: str, path: str = "/", glob: str = "*"
    ) -> List[SearchResult]:
        """全局搜索

        Args:
            agent_id: Agent ID
            query: 搜索关键词
            path: 搜索路径
            glob: 文件过滤

        Returns:
            List[SearchResult]: 搜索结果列表
        """
        results: List[SearchResult] = []

        try:
            target_path = Path(path)
            if not target_path.exists():
                return results

            # 遍历文件
            for file_path in target_path.rglob(glob):
                if not file_path.is_file():
                    continue

                # 跳过二进制文件和大文件
                try:
                    if file_path.stat().st_size > 1024 * 1024:
                        continue

                    content = self._read_with_encoding(file_path)
                    lines = content.split("\n")

                    for line_num, line in enumerate(lines, 1):
                        if query in line:
                            match_start = line.find(query)
                            results.append(
                                SearchResult(
                                    file_path=str(file_path),
                                    line_number=line_num,
                                    line_content=line.strip()[:200],  # 限制长度
                                    match_start=match_start,
                                    match_end=match_start + len(query),
                                )
                            )
                except (UnicodeDecodeError, PermissionError, OSError):
                    continue

            return results[:100]  # 限制结果数量
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _update_cache(self, path: str, content: str) -> None:
        """更新文件缓存"""
        if len(self._file_cache) >= self._cache_max_size:
            # 删除最旧的缓存
            oldest = next(iter(self._file_cache))
            del self._file_cache[oldest]

        self._file_cache[path] = content

    def clear_cache(self) -> None:
        """清空缓存"""
        self._file_cache.clear()

    def get_cached_files(self) -> List[str]:
        """获取缓存的文件列表"""
        return list(self._file_cache.keys())
