#!/usr/bin/env python3
"""Example script demonstrating the use of the tree-sitter code database."""

import os
import sys
import logging
import argparse
from pathlib import Path
from typing import List, Optional, Set

from jarvis.jarvis_treesitter import (
    CodeDatabase, 
    SymbolType, 
    setup_default_grammars,
    DEFAULT_GRAMMAR_DIR
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def index_directory(db: CodeDatabase, directory: str, extensions: Optional[Set[str]] = None) -> int:
    """Index all supported files in a directory.
    
    Args:
        db: The code database
        directory: Directory to index
        extensions: Optional set of file extensions to index (e.g., {'.py', '.c'})
        
    Returns:
        Number of files indexed
    """
    count = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if extensions and not any(file.endswith(ext) for ext in extensions):
                continue
                
            file_path = os.path.join(root, file)
            try:
                db.index_file(file_path)
                count += 1
                logger.info(f"Indexed file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to index file {file_path}: {str(e)}")
    
    return count

def find_symbol(db: CodeDatabase, symbol_name: str) -> None:
    """Find and print all occurrences of a symbol.
    
    Args:
        db: The code database
        symbol_name: Symbol name to search for
    """
    symbols = db.find_symbol(symbol_name)
    
    if not symbols:
        print(f"No symbols found with name: {symbol_name}")
        return
        
    print(f"Found {len(symbols)} symbols with name: {symbol_name}")
    for i, symbol in enumerate(symbols):
        print(f"\n[{i+1}] {symbol.type.value}: {symbol.name}")
        print(f"    Location: {symbol.location.file_path}:{symbol.location.start_line}:{symbol.location.start_column}")
        
        # Find references for this symbol
        refs = db.find_references(symbol)
        print(f"    References: {len(refs)}")
        for j, ref in enumerate(refs[:5]):  # Show first 5 references
            print(f"      [{j+1}] {ref.location.file_path}:{ref.location.start_line}:{ref.location.start_column}")
        
        if len(refs) > 5:
            print(f"      ... and {len(refs) - 5} more")
            
        # Find callers if it's a function
        if symbol.type == SymbolType.FUNCTION:
            callers = db.find_callers(symbol)
            print(f"    Callers: {len(callers)}")
            for j, caller in enumerate(callers[:5]):  # Show first 5 callers
                print(f"      [{j+1}] {caller.location.file_path}:{caller.location.start_line}:{caller.location.start_column}")
            
            if len(callers) > 5:
                print(f"      ... and {len(callers) - 5} more")

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Tree-sitter code database example")
    parser.add_argument("--dir", "-d", type=str, default=".", help="Directory to index")
    parser.add_argument("--ext", "-e", type=str, nargs="*", help="File extensions to index (e.g., .py .c)")
    parser.add_argument("--symbol", "-s", type=str, help="Symbol name to search for")
    parser.add_argument("--grammar-dir", "-g", type=str, default=DEFAULT_GRAMMAR_DIR, 
                       help=f"Directory containing grammar files (default: {DEFAULT_GRAMMAR_DIR})")
    parser.add_argument("--no-download", action="store_true", help="Don't download missing grammars")
    args = parser.parse_args()
    
    # Create code database
    db = CodeDatabase(grammar_dir=args.grammar_dir, auto_download=not args.no_download)
    
    # Process extensions
    extensions = set(args.ext) if args.ext else None
    
    # Index directory
    count = index_directory(db, args.dir, extensions)
    print(f"Indexed {count} files in {args.dir}")
    
    # Search for symbol if specified
    if args.symbol:
        find_symbol(db, args.symbol)

if __name__ == "__main__":
    main() 