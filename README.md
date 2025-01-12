<div align="center">

# 🤖 Jarvis AI Assistant

<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>

[![PyPI version](https://badge.fury.io/py/jarvis-ai-assistant.svg)](https://badge.fury.io/py/jarvis-ai-assistant)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

*Your intelligent assistant for development and system interaction*

[Installation](#installation) •
[Features](#features) •
[Usage](#usage) •
[Tools](#tools) •
[Documentation](https://jarvis-ai.readthedocs.io/)

</div>

---

## 🌟 Features

🤖 **AI Integration**
- Kimi AI integration with streaming responses
- Context-aware conversations
- File understanding capabilities

🛠️ **Rich Tool Integration**
- Shell command execution
- File operations (read/write/append)
- Task automation
- Predefined task support
- Dynamic tool system with auto-loading
- AI-powered tool generation
- Custom tool development

🔄 **Interactive Experience**
- Natural language understanding
- Context-aware responses
- User-friendly interface
- Multi-line input support
- Colored output with progress indicators

## 🛠️ Custom Tools

### Tool Locations
- Built-in tools: `src/jarvis/tools/`
- User tools: `~/.jarvis_tools/` (automatically created)

### Creating Tools

#### 1. Using AI Generator (Recommended)
```yaml
<START_TOOL_CALL>
name: generate_tool
arguments:
    tool_name: calculator
    class_name: CalculatorTool
    description: Basic math calculations
    parameters:
        type: object
        properties:
            operation:
                type: string
                enum: ["add", "subtract", "multiply", "divide"]
            numbers:
                type: array
                items:
                    type: number
        required: ["operation", "numbers"]
<END_TOOL_CALL>
```

#### 2. Manual Creation
Create a new Python file in `~/.jarvis_tools/`:

```python
from typing import Dict, Any, Protocol, Optional
from enum import Enum

class OutputType(Enum):
    INFO = "info"
    ERROR = "error"

class OutputHandler(Protocol):
    def print(self, text: str, output_type: OutputType) -> None: ...

class ModelHandler(Protocol):
    def chat(self, message: str) -> str: ...

class CustomTool:
    name = "tool_name"              # Tool name for invocation
    description = "Tool description" # Tool purpose
    parameters = {                  # JSON Schema for parameters
        "type": "object",
        "properties": {
            "param1": {"type": "string"}
        },
        "required": ["param1"]
    }

    def __init__(self, **kwargs):
        """Initialize tool with optional dependencies
        
        Args:
            model: AI model for advanced features
            output_handler: For consistent output formatting
            register: Access to tool registry
        """
        self.model = kwargs.get('model')
        self.output = kwargs.get('output_handler')
        self.register = kwargs.get('register')
        
    def _print(self, text: str, output_type: OutputType = OutputType.INFO):
        """Print formatted output"""
        if self.output:
            self.output.print(text, output_type)

    def execute(self, args: Dict) -> Dict[str, Any]:
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
                "stdout": result,
                "stderr": ""
            }
        except Exception as e:
            self._print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": str(e)
            }
```

### Development Guidelines

1. **Tool Structure**
   - Clear name and description
   - Well-defined parameters schema
   - Proper error handling
   - Consistent output format

2. **Best Practices**
   - Use `_print` for output
   - Handle all required parameters
   - Document functionality
   - Return standardized results
   - Keep tools focused and simple

3. **Testing**
   - Verify parameter validation
   - Test error handling
   - Check output format
   - Ensure proper cleanup

4. **Integration**
   - Tools are auto-loaded on startup
   - No manual registration needed
   - Hot-reload supported
   - Dependencies injected automatically

## ⚙️ Environment Setup

Before using Jarvis, you need to set up your environment:

1. **API Key Configuration**

Create a `.jarvis_env` file in your home directory (`~/.jarvis_env`):

```bash
KIMI_API_KEY=your_kimi_api_key_here
```

To get your Kimi API key:
1. Visit [Kimi AI Platform](https://kimi.moonshot.cn) in your browser
2. Login to your account
3. Open browser Developer Tools (F12 or right-click -> Inspect)
4. Go to Network tab
5. Make any request (e.g., send a message)
6. Find a request to the Kimi API
7. Look for the `Authorization` header in the request headers
8. Copy the token value (remove the "Bearer " prefix)
9. Use this token as your `KIMI_API_KEY` in the `.jarvis_env` file

2. **Task Configuration (Optional)**

Create a `.jarvis` file in your working directory to define predefined tasks:

```yaml
# .jarvis
analyze_code: Analyze the code structure and quality in the current directory
fix_bugs: Help me find and fix potential bugs in the code
optimize: Suggest optimizations for the code
document: Generate documentation for the code
```

## 🚀 Installation

```bash
pip install jarvis-ai-assistant
```

## 💡 Usage

1. **Basic Usage**
```bash
# Start Jarvis
jarvis

# Process specific files
jarvis -f file1.txt file2.py
```

2. **Using Predefined Tasks**

If you have a `.jarvis` file in your working directory:
```bash
# Jarvis will show available tasks on startup
# Select a task number or start a new conversation
```

3. **Interactive Features**
- Multi-line input support (press Enter twice to submit)
- File understanding and analysis
- Context-aware conversations
- Tool integration for system operations

4. **Environment Variables**
- `KIMI_API_KEY`: Your Kimi AI API key (required)
- Location: `~/.jarvis_env`
- Format: `KEY=value` (one per line)

5. **Task Configuration**
- File: `.jarvis` in working directory
- Format: `task_name: task_description`
- Purpose: Define commonly used tasks for quick access
- Example tasks:
  - Code analysis
  - Bug finding
  - Documentation generation
  - Performance optimization

## 🧰 Tools

| Tool | Description | Example |
|------|-------------|---------|
| 🖥️ Shell | Execute system commands | Manage files and processes |
| 📂 Files | Read/write operations | Handle configuration files |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚙️ Environment Setup

Create a `.jarvis_env` file in your home directory with:

```bash
KIMI_API_KEY=your_kimi_api_key_here
```

---

<div align="center">

Made with ❤️ by [Your Name]

</div>
