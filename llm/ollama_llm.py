import ollama
import logging
from typing import Dict, Any
from .base import BaseLLM

# Disable HTTP request logs from ollama package
logging.getLogger("httpx").setLevel(logging.WARNING)

class OllamaLLM(BaseLLM):
    """Ollama LLM implementation using ollama package"""
    
    def __init__(self, model_name: str = "llama3:latest", **kwargs):
        super().__init__(model_name=model_name, **kwargs)
        self.system_prompt = (
            "You are a highly precise and analytical AI assistant, specialized in task decomposition "
            "and systematic problem-solving. Your key characteristics are:\n\n"
            "1. PRECISION: You always provide exact, specific information\n"
            "2. COMPLETENESS: You include all necessary details in your responses\n"
            "3. STRUCTURE: You follow requested formats strictly\n"
            "4. FOCUS: You stay strictly on topic and avoid tangents\n"
            "5. VALIDATION: You verify all requirements before proceeding\n\n"
            "When analyzing tasks:\n"
            "- Break complex tasks into clear, actionable steps\n"
            "- Ensure each step has complete information\n"
            "- Verify prerequisites before suggesting actions\n"
            "- Maintain logical dependencies between steps\n"
            "- Provide specific, measurable outcomes\n\n"
            "Your responses must:\n"
            "- Be in valid YAML format when requested\n"
            "- Include all required information\n"
            "- Be self-contained and specific\n"
            "- Follow exact format requirements\n"
            "- Avoid assumptions or ambiguity"
        )
    
    def get_model_name(self) -> str:
        """Get the name of the current model"""
        return f"ollama-{self.model_name}"
    
    def get_completion(self, prompt: str, **kwargs) -> str:
        """Generate completion from Ollama using ollama package"""
        try:
            # Add instruction to wrap YAML in code blocks
            enhanced_prompt = (
                f"{prompt}\n\n"
                "IMPORTANT: Your response must be valid YAML wrapped in code blocks.\n"
                "Start with ```yaml and end with ```\n"
                "Example:\n"
                "```yaml\n"
                "key: value\n"
                "```"
            )
            
            # Generate response using ollama package with system prompt
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": enhanced_prompt}
                ],
                stream=False,  # We want the complete response at once
                **kwargs
            )
            
            # Return the response text
            return response.message.content
            
        except Exception as e:
            # Handle any errors that occur during generation
            raise RuntimeError(f"Failed to generate response: {str(e)}")

def create_llm(**kwargs) -> BaseLLM:
    """Create Ollama LLM instance"""
    return OllamaLLM(**kwargs)