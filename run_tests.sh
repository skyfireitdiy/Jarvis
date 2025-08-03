#!/bin/bash
# 运行 jarvis_agent 模块的测试

echo "Running tests for jarvis_agent module..."
python -m pytest tests/jarvis_agent/ -v --tb=short
