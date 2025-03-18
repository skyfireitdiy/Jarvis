"""Tree-sitter based code database implementation."""

import os
import logging
from typing import Dict, List, Optional, Set, Tuple
from tree_sitter import Language, Node, Parser, Tree
from .symbol import Symbol, SymbolType, SymbolLocation
from .language import LanguageType, detect_language, get_language_config
from .grammar_builder import GrammarBuilder, setup_default_grammars, DEFAULT_GRAMMAR_DIR

# Setup logging
logger = logging.getLogger(__name__)

class CodeDatabase:
    """A database for storing and querying code symbols using tree-sitter."""
    
    def __init__(self, grammar_dir: Optional[str] = None, auto_download: bool = True):
        """Initialize the code database.
        
        Args:
            grammar_dir: Directory containing tree-sitter grammar files.
                         If None, uses the default directory (~/.jarvis/treesitter).
            auto_download: Whether to automatically download missing grammar files.
        """
        self.parser = Parser()
        self.languages: Dict[LanguageType, Language] = {}
        self.file_languages: Dict[str, LanguageType] = {}
        
        # Use default grammar directory if not provided
        if grammar_dir is None:
            grammar_dir = DEFAULT_GRAMMAR_DIR
            if auto_download:
                grammar_dir = setup_default_grammars()
        
        # Create grammar builder
        self.grammar_builder = GrammarBuilder(grammar_dir)
        
        # Load all supported language grammars
        for lang_type in LanguageType:
            try:
                if auto_download:
                    # Ensure grammar exists (download if needed)
                    grammar_path = self.grammar_builder.ensure_grammar(lang_type)
                else:
                    # Just check if grammar file exists
                    config = get_language_config(lang_type)
                    grammar_path = os.path.join(grammar_dir, config.grammar_file)
                    if not os.path.exists(grammar_path):
                        logger.warning(f"Grammar file for {lang_type.value} not found: {grammar_path}")
                        continue
                
                # Load the language
                config = get_language_config(lang_type)
                self.languages[lang_type] = Language(grammar_path, config.name)
                logger.info(f"Loaded language grammar for {lang_type.value}")
            except Exception as e:
                logger.error(f"Failed to load grammar for {lang_type.value}: {str(e)}")
        
        # Symbol storage
        self.symbols: Dict[str, List[Symbol]] = {}
        self.file_trees: Dict[str, Tuple[Tree, LanguageType]] = {}
        
    def index_file(self, file_path: str) -> None:
        """Index a source code file.
        
        Args:
            file_path: Path to the source code file
        """
        # Detect language
        lang_type = detect_language(file_path)
        if not lang_type:
            raise ValueError(f"Could not detect language for file: {file_path}")
            
        # Check if language is supported
        if lang_type not in self.languages:
            if not hasattr(self, 'grammar_builder'):
                raise ValueError(f"Unsupported language for file: {file_path}")
            
            # Try to build the grammar on-demand
            try:
                grammar_path = self.grammar_builder.ensure_grammar(lang_type)
                config = get_language_config(lang_type)
                self.languages[lang_type] = Language(grammar_path, config.name)
                logger.info(f"Built and loaded language grammar for {lang_type.value}")
            except Exception as e:
                raise ValueError(f"Failed to build grammar for {lang_type.value}: {str(e)}")
        
        # Set language for parsing
        self.parser.set_language(self.languages[lang_type])
        self.file_languages[file_path] = lang_type
        
        # Parse file
        with open(file_path, 'rb') as f:
            source_code = f.read()
            
        tree = self.parser.parse(source_code)
        self.file_trees[file_path] = (tree, lang_type)
        
        # Extract symbols from the tree
        self._extract_symbols(tree, file_path, lang_type)
        
    def _extract_symbols(self, tree: Tree, file_path: str, lang_type: LanguageType) -> None:
        """Extract symbols from a tree-sitter tree.
        
        Args:
            tree: The tree-sitter tree
            file_path: Path to the source file
            lang_type: The language type
        """
        config = get_language_config(lang_type)
        
        def visit_node(node: Node):
            if not node:
                return
                
            # Extract symbols based on language-specific patterns
            for symbol_type, patterns in config.symbol_patterns.items():
                if node.type in patterns:
                    name_node = None
                    
                    # Get the name node based on language-specific rules
                    if lang_type == LanguageType.PYTHON:
                        name_node = node.child_by_field_name('name')
                    elif lang_type in (LanguageType.C, LanguageType.CPP):
                        if node.type == 'function_definition':
                            name_node = node.child_by_field_name('declarator')
                        elif node.type in ('struct_specifier', 'class_specifier'):
                            name_node = node.child_by_field_name('name')
                    elif lang_type == LanguageType.GO:
                        if node.type in ('function_declaration', 'method_declaration'):
                            name_node = node.child_by_field_name('name')
                    elif lang_type == LanguageType.RUST:
                        if node.type in ('function_item', 'struct_item', 'enum_item', 'trait_item'):
                            name_node = node.child_by_field_name('name')
                    
                    if name_node and name_node.type == 'identifier':
                        symbol = Symbol(
                            name=name_node.text.decode(),
                            type=SymbolType(symbol_type),
                            location=SymbolLocation(
                                file_path=file_path,
                                start_line=node.start_point[0] + 1,
                                start_column=node.start_point[1] + 1,
                                end_line=node.end_point[0] + 1,
                                end_column=node.end_point[1] + 1
                            )
                        )
                        self._add_symbol(symbol)
            
            # Recursively visit children
            for child in node.children:
                visit_node(child)
        
        visit_node(tree.root_node)
    
    def _add_symbol(self, symbol: Symbol) -> None:
        """Add a symbol to the database.
        
        Args:
            symbol: The symbol to add
        """
        if symbol.name not in self.symbols:
            self.symbols[symbol.name] = []
        self.symbols[symbol.name].append(symbol)
    
    def find_symbol(self, name: str) -> List[Symbol]:
        """Find all occurrences of a symbol by name.
        
        Args:
            name: The symbol name to search for
            
        Returns:
            List of matching symbols
        """
        return self.symbols.get(name, [])
    
    def find_references(self, symbol: Symbol) -> List[Symbol]:
        """Find all references to a symbol.
        
        Args:
            symbol: The symbol to find references for
            
        Returns:
            List of reference symbols
        """
        references = []
        for file_path, (tree, lang_type) in self.file_trees.items():
            def find_refs(node: Node):
                if not node:
                    return
                    
                if node.type == 'identifier' and node.text.decode() == symbol.name:
                    ref_symbol = Symbol(
                        name=node.text.decode(),
                        type=SymbolType.REFERENCE,
                        location=SymbolLocation(
                            file_path=file_path,
                            start_line=node.start_point[0] + 1,
                            start_column=node.start_point[1] + 1,
                            end_line=node.end_point[0] + 1,
                            end_column=node.end_point[1] + 1
                        )
                    )
                    references.append(ref_symbol)
                
                for child in node.children:
                    find_refs(child)
            
            find_refs(tree.root_node)
        
        return references
    
    def find_callers(self, function_symbol: Symbol) -> List[Symbol]:
        """Find all callers of a function.
        
        Args:
            function_symbol: The function symbol to find callers for
            
        Returns:
            List of caller symbols
        """
        callers = []
        for file_path, (tree, lang_type) in self.file_trees.items():
            def find_calls(node: Node):
                if not node:
                    return
                    
                # Language-specific call patterns
                call_patterns = {
                    LanguageType.PYTHON: ('call', 'function'),
                    LanguageType.C: ('call_expression', 'function'),
                    LanguageType.CPP: ('call_expression', 'function'),
                    LanguageType.GO: ('call_expression', 'function'),
                    LanguageType.RUST: ('call_expression', 'function'),
                }
                
                if node.type == call_patterns[lang_type][0]:
                    func_node = node.child_by_field_name(call_patterns[lang_type][1])
                    if func_node and func_node.type == 'identifier' and func_node.text.decode() == function_symbol.name:
                        caller_symbol = Symbol(
                            name=func_node.text.decode(),
                            type=SymbolType.FUNCTION_CALL,
                            location=SymbolLocation(
                                file_path=file_path,
                                start_line=node.start_point[0] + 1,
                                start_column=node.start_point[1] + 1,
                                end_line=node.end_point[0] + 1,
                                end_column=node.end_point[1] + 1
                            )
                        )
                        callers.append(caller_symbol)
                
                for child in node.children:
                    find_calls(child)
            
            find_calls(tree.root_node)
        
        return callers 