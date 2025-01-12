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

🔄 **Interactive Experience**
- Natural language understanding
- Context-aware responses
- User-friendly interface
- Multi-line input support
- Colored output with progress indicators


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
