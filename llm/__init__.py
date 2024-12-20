from .base import BaseLLM
from .discovery import LLMDiscovery, LLMRegistry

# Create a global registry instance
registry = LLMRegistry()

# Export the registry's create_llm function as the main factory
create_llm = registry.create_llm

__all__ = [
    'BaseLLM',
    'create_llm',
    'LLMDiscovery',
    'LLMRegistry'
] 