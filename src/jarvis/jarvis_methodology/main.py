"""
方法论导入导出命令行工具

功能：
- 导入方法论文件（合并策略）
- 导出当前方法论
- 列出所有方法论
"""

import os
import json
import click
from jarvis.jarvis_utils.methodology import (
    _get_methodology_directory,
    _load_all_methodologies,
    _save_embeddings_cache,
    _save_index_cache,
    _methodology_index_cache,
    _methodology_embeddings_cache
)

@click.group()
def cli():
    """方法论管理工具"""
    pass

@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
def import_methodology(input_file):
    """导入方法论文件（合并策略）"""
    try:
        # 加载现有方法论
        existing_methodologies = _load_all_methodologies()
        
        # 加载要导入的方法论
        with open(input_file, "r", encoding="utf-8") as f:
            import_data = json.load(f)
            
        # 合并方法论（新数据会覆盖旧数据）
        merged_data = {**existing_methodologies, **import_data}
        
        # 保存合并后的方法论
        methodology_dir = _get_methodology_directory()
        for problem_type, content in merged_data.items():
            safe_filename = hashlib.md5(problem_type.encode('utf-8')).hexdigest()
            file_path = os.path.join(methodology_dir, f"{safe_filename}.json")
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({
                    "problem_type": problem_type,
                    "content": content
                }, f, ensure_ascii=False, indent=2)
        
        # 清除缓存以强制重建索引
        global _methodology_index_cache, _methodology_embeddings_cache
        _methodology_index_cache = None
        _methodology_embeddings_cache = {}
        
        click.echo(f"成功导入 {len(import_data)} 个方法论（总计 {len(merged_data)} 个）")
    except Exception as e:
        click.echo(f"导入失败: {str(e)}", err=True)

@cli.command()
@click.argument("output_file", type=click.Path())
def export_methodology(output_file):
    """导出当前方法论到单个文件"""
    try:
        methodologies = _load_all_methodologies()
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(methodologies, f, ensure_ascii=False, indent=2)
        
        click.echo(f"成功导出 {len(methodologies)} 个方法论到 {output_file}")
    except Exception as e:
        click.echo(f"导出失败: {str(e)}", err=True)

@cli.command()
def list_methodologies():
    """列出所有方法论"""
    try:
        methodologies = _load_all_methodologies()
        
        if not methodologies:
            click.echo("没有找到方法论")
            return
            
        click.echo("可用方法论:")
        for i, (problem_type, _) in enumerate(methodologies.items(), 1):
            click.echo(f"{i}. {problem_type}")
    except Exception as e:
        click.echo(f"列出方法论失败: {str(e)}", err=True)

if __name__ == "__main__":
    cli()
