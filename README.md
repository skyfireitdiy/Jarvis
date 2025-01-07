<div align="center">

# 🤖 Jarvis AI Assistant

<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>

[![PyPI version](https://badge.fury.io/py/jarvis-ai.svg)](https://badge.fury.io/py/jarvis-ai)
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

🤖 **Multiple AI Models**
- Ollama integration (llama3.2, qwen2.5:14b)
- DuckDuckGo AI search capabilities

🛠️ **Rich Tool Integration**
- RAG (Retrieval-Augmented Generation)
- File operations & Shell commands
- Web search & content extraction
- Python code execution with dependency management

🔄 **Interactive Experience**
- Natural language understanding
- Context-aware responses
- User-friendly interface

## 🚀 Installation

```bash
pip install jarvis-ai-assistant
```

## 💡 Usage

```bash
# Quick Start
jarvis

# Using Specific Model
jarvis --platform ollama --model qwen2.5:14b

# Custom Ollama API
jarvis --platform ollama --model llama3.2 --api-base http://localhost:11434
```

## 🧰 Tools

| Tool | Description | Example |
|------|-------------|---------|
| 🔍 Search | Web search using DuckDuckGo | Search latest tech news |
| 📚 RAG | Document querying with embeddings | Query your documentation |
| 🐍 Python | Execute Python code | Run data analysis |
| 🖥️ Shell | Execute system commands | Manage files and processes |
| 📂 Files | Read/write operations | Handle configuration files |
| 🌐 Web | Extract webpage content | Gather information |
| 👤 User | Interactive input/confirmation | Get user preferences |


## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

Made with ❤️ by [Your Name]

</div>
