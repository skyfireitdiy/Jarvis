# -*- coding: utf-8 -*-
"""jarvis_config 模块测试 fixtures"""

import json
import pytest

from jarvis.jarvis_config.schema_parser import SchemaParser


@pytest.fixture(scope="function")
def sample_schema_file(tmp_path):
    """创建测试用的 JSON Schema 文件

    包含多种字段类型和约束条件
    """
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "测试配置",
        "description": "用于测试的配置 Schema",
        "type": "object",
        "required": ["name", "count"],
        "properties": {
            "name": {
                "type": "string",
                "description": "名称字段",
                "minLength": 1,
                "maxLength": 100,
                "default": "test",
            },
            "count": {
                "type": "integer",
                "description": "计数字段",
                "minimum": 0,
                "maximum": 100,
                "default": 1,
            },
            "rate": {
                "type": "number",
                "description": "速率字段",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
            },
            "enabled": {"type": "boolean", "description": "是否启用", "default": True},
            "status": {
                "type": "string",
                "enum": ["active", "inactive", "pending"],
                "description": "状态枚举",
                "default": "pending",
            },
            "tags": {
                "type": "array",
                "description": "标签数组",
                "items": {"type": "string"},
                "minItems": 0,
                "maxItems": 10,
                "default": [],
            },
            "metadata": {
                "type": "object",
                "description": "元数据对象",
                "properties": {
                    "key1": {"type": "string", "default": "value1"},
                    "key2": {"type": "integer", "default": 42},
                },
                "default": {},
            },
        },
    }

    schema_path = tmp_path / "test_schema.json"
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    return schema_path


@pytest.fixture(scope="function")
def parser_with_schema(sample_schema_file):
    """使用测试 Schema 初始化的 SchemaParser 实例"""
    return SchemaParser(sample_schema_file)


@pytest.fixture(scope="function")
def valid_config_data():
    """有效的配置数据用于测试"""
    return {
        "name": "test-config",
        "count": 10,
        "rate": 0.75,
        "enabled": True,
        "status": "active",
        "tags": ["tag1", "tag2"],
        "metadata": {"key1": "custom-value", "key2": 100},
    }


@pytest.fixture(scope="function")
def invalid_config_data():
    """无效的配置数据用于测试验证逻辑"""
    return {
        "name": "",  # 违反 minLength: 1
        "count": -1,  # 违反 minimum: 0
        "rate": 2.0,  # 违反 maximum: 1.0
        "status": "invalid",  # 不在 enum 中
        "enabled": "not-a-boolean",  # 类型错误
    }
