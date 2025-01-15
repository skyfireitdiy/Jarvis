<div align="center">

# 🤖 Jarvis AI Assistant

<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*Your intelligent assistant for development and system interaction*

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

Create a `.jarvis_env` file in your home directory with your API keys:

### For Kimi:
```bash
KIMI_API_KEY=your_kimi_api_key_here
```

### For OpenAI:
```bash
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=your_api_base  # Optional, defaults to https://api.deepseek.com
OPENAI_MODEL_NAME=your_model_name  # Optional, defaults to deepseek-chat
```

## 🎯 Usage

### Basic Usage
```bash
jarvis
```

### With Specific Model
```bash
jarvis -p kimi  # Use Kimi platform
jarvis -p openai  # Use OpenAI platform
```

### Process Files
```bash
jarvis -f file1.py file2.py  # Process specific files
```

### Keep Chat History
```bash
jarvis --keep-history  # Don't delete chat session after completion
```

## 🛠️ Tools

### Built-in Tools

| Tool | Description |
|------|-------------|
| execute_shell | Execute system commands and capture output |
| file_operation | File operations (read/write/append/delete) |
| generate_tool | AI-powered tool generation and integration |
| methodology | Experience accumulation and methodology management |
| create_sub_agent | Create specialized sub-agents for specific tasks |

### Tool Locations
- Built-in tools: `src/jarvis/tools/`
- User tools: `~/.jarvis_tools/`

### Key Features

#### 1. Self-Extending Capabilities
- Tool generation through natural language description
- Automatic code generation and integration
- Dynamic capability expansion through sub-agents

#### 2. Methodology Learning
- Automatic experience accumulation from interactions
- Pattern recognition and methodology extraction
- Continuous refinement through usage

#### 3. Adaptive Problem Solving
- Context-aware sub-agent creation
- Dynamic tool composition
- Learning from execution feedback

## 🎯 Extending Jarvis

### Adding New Tools

Create a new Python file in `~/.jarvis_tools/` or `src/jarvis/tools/`:

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
                "error": str    # On failure
            }
        """
        try:
            # Implement tool logic here
            result = "Tool execution result"
            return {
                "success": True,
                "stdout": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
```

### Adding New Models

Create a new Python file in `~/.jarvis_models/`:

```python
from typing import Dict, List
from jarvis.models.base import BaseModel
from jarvis.utils import PrettyOutput, OutputType

class CustomModel(BaseModel):
    """Custom model implementation"""
    
    model_name = "custom"  # Model identifier
    
    def __init__(self):
        """Initialize model"""
        # Add your initialization code here
        self.messages = []
        self.system_message = ""
        
    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message
        
    def chat(self, message: str) -> str:
        """Execute chat with the model
        
        Args:
            message: User input message
            
        Returns:
            str: Model response
        """
        try:
            # Implement chat logic here
            PrettyOutput.print("发送请求...", OutputType.PROGRESS)
            
            # Add message to history
            self.messages.append({"role": "user", "content": message})
            
            # Get response from your model
            response = "Model response"
            
            # Add response to history
            self.messages.append({"role": "assistant", "content": response})
            
            return response
            
        except Exception as e:
            PrettyOutput.print(f"对话失败: {str(e)}", OutputType.ERROR)
            raise Exception(f"Chat failed: {str(e)}")
            
    def name(self) -> str:
        """Return model name"""
        return self.model_name
        
    def reset(self):
        """Reset model state"""
        self.messages = []
        if self.system_message:
            self.messages.append({"role": "system", "content": self.system_message})
            
    def delete_chat(self) -> bool:
        """Delete current chat session"""
        self.reset()
        return True
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
