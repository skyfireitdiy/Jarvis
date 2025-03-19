"""Functionality for downloading and building tree-sitter grammars."""

import os
import subprocess
import tempfile
import shutil
from typing import Dict, List, Optional
import logging
from pathlib import Path

from .language import LanguageType, get_language_config

# Setup logging
logger = logging.getLogger(__name__)

# Default grammar directory
DEFAULT_GRAMMAR_DIR = os.path.expanduser("~/.jarvis/treesitter")

# Tree-sitter grammar repositories
GRAMMAR_REPOS = {
    LanguageType.PYTHON: "https://github.com/tree-sitter/tree-sitter-python",
    LanguageType.C: "https://github.com/tree-sitter/tree-sitter-c",
    LanguageType.CPP: "https://github.com/tree-sitter/tree-sitter-cpp",
    LanguageType.GO: "https://github.com/tree-sitter/tree-sitter-go",
    LanguageType.RUST: "https://github.com/tree-sitter/tree-sitter-rust",
}

class GrammarBuilder:
    """Handles downloading and building tree-sitter grammar files."""
    
    def __init__(self, grammar_dir: str = DEFAULT_GRAMMAR_DIR):
        """Initialize the grammar builder.
        
        Args:
            grammar_dir: Directory to store built grammar files. 
                       Defaults to ~/.jarvis/treesitter
        """
        self.grammar_dir = grammar_dir
        os.makedirs(grammar_dir, exist_ok=True)
        
    def ensure_grammar(self, lang_type: LanguageType) -> str:
        """Ensure the grammar file for a language exists, downloading and building if necessary.
        
        Args:
            lang_type: The language type
            
        Returns:
            Path to the grammar file
        """
        config = get_language_config(lang_type)
        grammar_path = os.path.join(self.grammar_dir, config.grammar_file)
        
        # Check if grammar file already exists
        if os.path.exists(grammar_path):
            logger.info(f"Grammar file for {lang_type.value} already exists at {grammar_path}")
            return grammar_path
            
        # Download and build the grammar
        logger.info(f"Building grammar for {lang_type.value}")
        return self._build_grammar(lang_type)
    
    def ensure_all_grammars(self) -> Dict[LanguageType, str]:
        """Ensure grammar files for all supported languages exist.
        
        Returns:
            Dictionary mapping language types to grammar file paths
        """
        result = {}
        for lang_type in LanguageType:
            try:
                path = self.ensure_grammar(lang_type)
                result[lang_type] = path
            except Exception as e:
                logger.error(f"Failed to build grammar for {lang_type.value}: {str(e)}")
        
        return result
    
    def _build_grammar(self, lang_type: LanguageType) -> str:
        """Download and build the grammar for a language.
        
        Args:
            lang_type: The language type
            
        Returns:
            Path to the built grammar file
            
        Raises:
            RuntimeError: If grammar building fails
        """
        config = get_language_config(lang_type)
        repo_url = GRAMMAR_REPOS.get(lang_type)
        
        if not repo_url:
            raise ValueError(f"No repository URL defined for language {lang_type.value}")
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone the repository
            logger.info(f"Cloning {repo_url}")
            result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, temp_dir],
                check=False,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to clone repository {repo_url}: {result.stderr}")
            
            # Build the grammar
            grammar_path = os.path.join(self.grammar_dir, config.grammar_file)
            
            # Create build script
            build_script = self._create_build_script(temp_dir, lang_type.value, grammar_path)
            
            # Execute build script
            logger.info(f"Building grammar for {lang_type.value}")
            result = subprocess.run(
                ["python3", build_script],
                check=False,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to build grammar for {lang_type.value}: {result.stderr}")
            
            # Verify file exists
            if not os.path.exists(grammar_path):
                raise RuntimeError(f"Grammar file {grammar_path} was not created")
            
            logger.info(f"Successfully built grammar for {lang_type.value}: {grammar_path}")
            return grammar_path
    
    def _create_build_script(self, repo_dir: str, lang_name: str, output_path: str) -> str:
        """Create a Python script to build the grammar.
        
        Args:
            repo_dir: Path to the cloned repository
            lang_name: Language name
            output_path: Output path for the built grammar
            
        Returns:
            Path to the build script
        """
        script_path = os.path.join(repo_dir, "build_grammar.py")
        
        with open(script_path, "w") as f:
            f.write(f'''
import os
from tree_sitter import Language

# Ensure output directory exists
os.makedirs(os.path.dirname("{output_path}"), exist_ok=True)

# Build the language
Language.build_library(
    "{output_path}",
    [
        "{repo_dir}"
    ]
)

print(f"Built grammar: {output_path}")
''')
        
        return script_path


def setup_default_grammars() -> str:
    """Set up default grammars in ~/.jarvis/treesitter directory.
    
    Returns:
        Path to the grammar directory
    """
    grammar_dir = DEFAULT_GRAMMAR_DIR
    os.makedirs(grammar_dir, exist_ok=True)
    
    builder = GrammarBuilder(grammar_dir)
    builder.ensure_all_grammars()
    
    return grammar_dir 