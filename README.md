<div align="center">

# 🤖 Jarvis AI Assistant

<img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-orange.svg)](https://ollama.ai/)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

*Your intelligent command-line assistant powered by Large Language Models*

[Features](#✨-features) • [Installation](#🚀-installation) • [Usage](#💡-usage) • [Examples](#📚-examples) • [Contributing](#🤝-contributing)

</div>

---

## ✨ Features

- 🧠 **Intelligent Task Analysis**: Understands complex tasks and breaks them down into actionable steps
- 🛠️ **Powerful Tools**: Execute shell commands, run Python code, and perform mathematical calculations
- 🔄 **Adaptive Learning**: Learns from failures and user suggestions to improve performance
- 🎨 **Beautiful Output**: Rich, colorful terminal output for better readability
- 🔒 **Safe Execution**: Built-in safety checks and timeouts for all operations
- 🌈 **Multiple LLM Support**: Works with Ollama, OpenAI, and custom LLM implementations
- 🔍 **Smart Error Handling**: Automatically reflects on failures and adjusts approach
- 🤝 **Interactive Assistance**: Asks for clarification when needed and learns from user feedback

## 🚀 Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/jarvis-ai.git
cd jarvis-ai
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Ollama (if using local LLMs):
```bash
# Linux/Mac
curl https://ollama.ai/install.sh | sh

# Windows
# Download from https://ollama.ai/download
```

## 💡 Usage

### Basic Usage

```bash
# Simple task execution
python main.py

# Verbose mode for detailed logs
python main.py -v
```

### Advanced Configuration

```bash
# Use specific LLM model
python main.py --model-name llama2
python main.py --model-name codellama
python main.py --model-name mistral

# Use OpenAI's models
python main.py --model openai --model-name gpt-4

# Custom parameters
python main.py --llm-params temperature=0.7 max_tokens=2000
```

### Environment Variables

Create a `.env` file in the project root:
```env
# Required for OpenAI
OPENAI_API_KEY=your_api_key_here

# Optional configurations
OLLAMA_HOST=http://localhost:11434
LOG_LEVEL=DEBUG
```

## 📚 Examples

### System Management
```bash
# Check system status
> Show me the current CPU and memory usage
🔍 Analyzing system resources...
📊 CPU: 45% utilized
💾 Memory: 6.2GB used of 16GB

# Process management
> Find and kill all Python processes using too much memory
🔍 Searching for memory-intensive Python processes...
⚡ Found 2 processes exceeding threshold
🎯 Terminating processes...
```

### Network Diagnostics
```bash
# Network connectivity
> Check if our database server is reachable
🌐 Testing connection to database server...
📡 Sending ping to db.example.com...
✅ Server is reachable (latency: 5ms)

# Port scanning
> Verify if port 3306 is open on the database server
🔍 Checking port status...
🚪 Port 3306 is open and accepting connections
```

### File Operations
```bash
# File search
> Find all log files modified in the last hour
📂 Searching for recent log files...
📄 Found 3 modified files:
  - /var/log/app.log
  - /var/log/error.log
  - /var/log/access.log

# Content analysis
> Show me the last 5 error messages from the logs
📖 Analyzing log files...
❌ Found recent errors:
  1. Connection timeout at 14:23
  2. Database query failed at 14:25
  ...
```

## 🛠️ Tool Details

### Shell Tool (`shell`)
- Execute system commands safely
- Built-in timeout protection
- Output capture and formatting
- Error handling and reporting

### Python Tool (`python`)
- Execute Python code snippets
- Safe execution environment
- Standard library access
- Exception handling
- Output capture

### Math Tool (`math`)
- Evaluate mathematical expressions
- Support for:
  - Basic arithmetic
  - Trigonometric functions
  - Logarithms
  - Constants (π, e)
  - Statistical operations

## 🔧 Configuration

### LLM Settings
```yaml
# config.yaml
llm:
  default_model: llama2
  temperature: 0.7
  max_tokens: 2000
  timeout: 30

tools:
  shell:
    timeout: 60
    max_output: 1000
  python:
    timeout: 30
    safe_mode: true
```

## 🤝 Contributing

We welcome contributions! Here's how you can help:

1. Fork the repository
2. Create your feature branch:
```bash
git checkout -b feature/AmazingFeature
```

3. Make your changes and commit:
```bash
git commit -m 'Add some AmazingFeature'
```

4. Push to your branch:
```bash
git push origin feature/AmazingFeature
```

5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guide
- Add tests for new features
- Update documentation
- Keep commits atomic and well-described

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Ollama](https://ollama.ai/) for the amazing local LLM runtime
- [OpenAI](https://openai.com/) for their powerful language models
- The open source community for various tools and libraries

---

<div align="center">

**Jarvis AI Assistant** - Making CLI tasks smarter and easier

[Report Bug](https://github.com/yourusername/jarvis-ai/issues) • [Request Feature](https://github.com/yourusername/jarvis-ai/issues)

</div>