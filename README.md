<div align="center">

# 🤖 Jarvis AI Assistant

<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*Your intelligent assistant for development and system interaction*

English | [简体中文](README_zh.md)

[Features](#features) •
[Usage](#usage) •
[Configuration](#configuration) •
[Extending Jarvis](#-extending-jarvis) •
[Contributing](#-contributing) •
[License](#-license)

</div>

---

## ✨ Features

### 🧠 Intelligent Agent
- Self-improving through experience accumulation
- Automatic methodology generation from successful problem-solving
- Iterative learning from each interaction
- Context-aware problem solving

### 🛠️ Extensible Architecture
- Dynamic tool loading and integration
- Custom model support with simple interface
- AI-powered tool generation
- Hot-reload support for tools and models

### 💡 Smart Features
- Automated methodology management
- Problem-specific solution patterns
- Continuous capability enhancement
- Learning from past interactions

### 🎨 User Experience
- Beautiful console output
- Interactive mode
- Multi-line input support
- Progress indicators
- Colored output

## 🚀 Installation

```bash
pip install jarvis-ai-assistant
```

## 🔧 Configuration

Jarvis supports configuration through environment variables that can be set in the `~/.jarvis/env` file:

| Environment Variable | Description | Default Value | Required |
|---------|------|--------|------|
| JARVIS_PLATFORM | AI platform to use, supports kimi/openai/ai8 etc | kimi | Yes |
| JARVIS_MODEL | Model name to use | - | No |
| JARVIS_CODEGEN_PLATFORM | AI platform for code generation | Same as JARVIS_PLATFORM | No |
| JARVIS_CODEGEN_MODEL | Model name for code generation | Same as JARVIS_MODEL | No |
| JARVIS_CHEAP_PLATFORM | AI platform for cheap operations | Same as JARVIS_PLATFORM | No |
| JARVIS_CHEAP_MODEL | Model name for cheap operations | Same as JARVIS_MODEL | No |
| JARVIS_THINKING_PLATFORM | AI platform for thinking | Same as JARVIS_PLATFORM | No |
| JARVIS_THINKING_MODEL | Model name for thinking | Same as JARVIS_MODEL | No |
| JARVIS_THREAD_COUNT | Number of threads for parallel processing | 10 | No |
| OPENAI_API_KEY | API key for OpenAI platform | - | Required for OpenAI |
| OPENAI_API_BASE | Base URL for OpenAI API | https://api.deepseek.com | No |
| OPENAI_MODEL_NAME | Model name for OpenAI | deepseek-chat | No |
| AI8_API_KEY | API key for AI8 platform | - | Required for AI8 |
| KIMI_API_KEY | API key for Kimi platform | - | Required for Kimi |
| OYI_API_KEY | API key for OYI platform | - | Required for OYI |
| OLLAMA_API_BASE | Base URL for Ollama API | http://localhost:11434 | No |


## 🎯 Usage

### Code Modification
```bash
# Using main agent
jarvis

# Using code agent directly
jarvis-code-agent
```

### Codebase Query
```bash
# Ask questions about the codebase
jarvis-codebase ask "your question"
```

### Document Analysis (RAG)
```bash
# Build document index
jarvis-rag --dir /path/to/documents --build

# Ask questions about documents
jarvis-rag --query "your question"
```

### Smart Shell
```bash
# Using full name
jarvis-smart-shell "describe what you want to do"

# Using shorthand
jss "describe what you want to do"
```

### Development Tools
```bash
# Manage git commits
jarvis-git-commit

# Generate and manage ctags
jarvis-ctags

# Manage AI platforms
jarvis-platform
```

Each command supports `--help` flag for detailed usage information:
```bash
jarvis --help
jarvis-code-agent --help
jarvis-codebase --help
jarvis-rag --help
jarvis-smart-shell --help
jarvis-platform --help
jarvis-git-commit --help
jarvis-ctags --help
```

## 🛠️ Tools

### Built-in Tools

| Tool | Description |
|------|-------------|
| read_code | Read code files with line numbers and range support |
| execute_shell | Execute system commands and capture output |
| search | Web search for development related queries |
| ask_user | Interactive user input collection |
| ask_codebase | Intelligent codebase querying and analysis |
| code_review | Automated code review with multi-dimensional analysis |
| file_operation | Basic file operations (read/exists) |
| git_commiter | Automated git commit handling |

### Tool Locations
- Built-in tools: `src/jarvis/tools/`
- User tools: `~/.jarvis/tools/`

### Key Features

#### 1. Code Intelligence
- Smart file selection and analysis based on requirements
- Semantic codebase search and querying
- Efficient handling of large files with context-aware reading
- Precise patch-based code modifications
- Automated git commit management

#### 2. Multi-Model Architecture
- Support for multiple AI platforms (Kimi/OpenAI/AI8/OYI/Ollama)
- Platform-specific optimizations for different tasks
- Specialized models for code generation, thinking, and general tasks
- Streaming response support for better interaction
- Automatic model fallback and retry mechanisms

#### 3. RAG Capabilities
- Document indexing and semantic search
- Smart context management for large documents
- Automatic file change detection
- Efficient caching mechanisms
- Multi-format document support

#### 4. Development Tools
- Interactive shell command generation
- Code review with multi-dimensional analysis
- Codebase-aware problem solving
- File operations with safety checks
- Progress tracking and error handling

#### 5. User Experience
- Beautiful console output with color support
- Interactive multi-line input
- Progress indicators for long operations
- Clear error messages and handling
- Context-aware response formatting

## 🎯 Extending Jarvis

### Adding New Tools

Create a new Python file in `~/.jarvis/tools/` or `src/jarvis/tools/`:

```python
from typing import Dict, Any
from jarvis.utils import OutputType, PrettyOutput

class CustomTool:
    name = "tool_name"              # Tool name for invocation
    description = "Tool description" # Tool purpose
    parameters = {                  # JSON Schema for parameters
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Parameter description"
            }
        },
        "required": ["param1"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool functionality
        
        Args:
            args: Parameters passed to the tool
            
        Returns:
            Dict with execution results:
            {
                "success": bool,
                "stdout": str,  # On success
                "stderr": str,  # Optional error details
            }
        """
        try:
            # Implement tool logic here
            result = "Tool execution result"
            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }
```

### Adding New Models

Create a new Python file in `~/.jarvis/models/`:

```python
from typing import Dict, List
from jarvis.models.base import BasePlatform
from jarvis.utils import PrettyOutput, OutputType

class CustomPlatform(BasePlatform):
    """Custom model implementation"""
    
    platform_name = "custom"  # Platform identifier
    
    def __init__(self):
        """Initialize model"""
        # add initialization code
        super().__init__()
        self.messages = []
        self.system_message = ""

    def set_model_name(self, model_name: str):
        """Set model name"""
        self.model_name = model_name

    def chat(self, message: str) -> str:
        """Chat with model
        
        Args:
            message: user input message
            
        Returns:
            str: model response
        """
        try:
            # implement chat logic
            PrettyOutput.print("Sending request...", OutputType.PROGRESS)
            
            # add message to history
            self.messages.append({"role": "user", "content": message})
            
            # get response from model
            response = "model response"
            
            # add response to history
            self.messages.append({"role": "assistant", "content": response})
            
            return response
            
        except Exception as e:
            PrettyOutput.print(f"Chat failed: {str(e)}", OutputType.ERROR)
            raise Exception(f"Chat failed: {str(e)}")
    
    def upload_files(self, file_list: List[str]) -> List[Dict]:
        """Upload files"""
        # implement file upload logic
        return []    
        
    def reset(self):
        """Reset model state"""
        self.messages = []
        if self.system_message:
            self.messages.append({"role": "system", "content": self.system_message})
            
    def name(self) -> str:
        """Return model name"""
        return self.model_name
            
    def delete_chat(self) -> bool:
        """Delete current chat session"""
        self.reset()
        return True  

    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message

    def set_suppress_output(self, suppress: bool):
        """Set whether to suppress output"""
        self.suppress_output = suppress
```

### Development Guidelines

1. **Tool Development**
   - Use descriptive names and documentation
   - Define clear parameter schemas
   - Handle errors gracefully
   - Return standardized results
   - Keep tools focused and simple

2. **Model Development**
   - Implement all required methods
   - Handle streaming responses
   - Manage chat history properly
   - Use proper error handling
   - Follow existing model patterns

3. **Best Practices**
   - Use PrettyOutput for console output
   - Document your code
   - Add type hints
   - Test thoroughly
   - Handle edge cases

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

Made with ❤️ by the Jarvis Team

</div>
