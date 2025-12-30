# -*- coding: utf-8 -*-
"""Web API 集成测试"""

import json

import yaml
from fastapi.testclient import TestClient

from jarvis.jarvis_config.web_app import create_app


class TestWebApp:
    """测试 FastAPI 应用"""

    def test_create_app(self, sample_schema_file, tmp_path):
        """测试应用创建"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        assert app is not None
        assert app.title == "Jarvis 配置工具"

    def test_get_schema_endpoint(self, sample_schema_file, tmp_path):
        """测试 GET /api/schema 接口"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        response = client.get("/api/schema")
        assert response.status_code == 200

        data = response.json()
        assert "title" in data
        assert "description" in data
        assert "properties" in data
        assert "required" in data
        assert data["title"] == "测试配置"

    def test_get_schema_endpoint_with_meta(self, sample_schema_file, tmp_path):
        """测试 /api/schema 返回的属性包含 _meta 信息"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        response = client.get("/api/schema")
        assert response.status_code == 200

        data = response.json()
        properties = data["properties"]

        # 检查 name 属性的 _meta 信息
        assert "_meta" in properties["name"]
        assert properties["name"]["_meta"]["description"] == "名称字段"
        assert properties["name"]["_meta"]["default"] == "test"
        assert properties["name"]["_meta"]["required"] is True

        # 检查 count 属性的 _meta 信息
        assert "_meta" in properties["count"]
        assert properties["count"]["_meta"]["required"] is True

        # 检查 enabled 属性的 _meta 信息（非必填）
        assert "_meta" in properties["enabled"]
        assert properties["enabled"]["_meta"]["required"] is False

    def test_post_save_endpoint_success(self, sample_schema_file, tmp_path):
        """测试 POST /api/save 接口 - 成功保存"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        config_data = {
            "name": "test-config",
            "count": 10,
            "rate": 0.75,
            "enabled": True,
            "status": "active",
        }

        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200

        result = response.json()
        assert result["success"] is True
        assert "message" in result
        assert "path" in result

        # 检查文件是否被保存
        assert output_file.exists()
        with open(output_file, "r", encoding="utf-8") as f:
            saved_config = json.load(f)
        assert saved_config == config_data

    def test_post_save_endpoint_validation_error(self, sample_schema_file, tmp_path):
        """测试 POST /api/save 接口 - 验证失败"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        # 提供无效的配置数据
        config_data = {
            "name": "",  # 违反 minLength: 1
            "count": -1,  # 违反 minimum: 0
        }

        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200

        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert len(result["errors"]) > 0

    def test_post_save_endpoint_enum_validation(self, sample_schema_file, tmp_path):
        """测试 POST /api/save 接口 - 枚举值验证"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        config_data = {
            "name": "test",
            "count": 10,
            "status": "invalid_status",  # 不在枚举中
        }

        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200

        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert any("not in enum" in str(err).lower() for err in result["errors"])

    def test_post_save_endpoint_type_error(self, sample_schema_file, tmp_path):
        """测试 POST /api/save 接口 - 类型错误"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        config_data = {
            "name": "test",
            "count": 10,
            "enabled": "not-a-boolean",  # 类型错误
        }

        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200

        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert any("Expected type boolean" in str(err) for err in result["errors"])

    def test_post_save_endpoint_missing_required(self, sample_schema_file, tmp_path):
        """测试 POST /api/save 接口 - 缺少必填字段"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        config_data = {
            "count": 10  # 缺少必填字段 'name'
        }

        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200

        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert any("Required field" in str(err) for err in result["errors"])

    def test_get_health_endpoint(self, sample_schema_file, tmp_path):
        """测试 GET /api/health 健康检查接口"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        response = client.get("/api/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"

    def test_get_root_endpoint(self, sample_schema_file, tmp_path):
        """测试 GET / 接口返回 HTML"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "<!DOCTYPE html>" in response.text

    def test_save_creates_output_directory(self, sample_schema_file, tmp_path):
        """测试保存配置时自动创建输出目录"""
        output_dir = tmp_path / "subdir" / "nested"
        output_file = output_dir / "config.json"

        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        config_data = {"name": "test", "count": 5}

        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 检查目录和文件是否被创建
        assert output_dir.exists()
        assert output_file.exists()

    def test_nested_object_validation(self, sample_schema_file, tmp_path):
        """测试嵌套对象的验证和保存"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        # 有效的嵌套对象
        config_data = {
            "name": "test",
            "count": 10,
            "metadata": {"key1": "value1", "key2": 42},
        }

        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 无效的嵌套对象（类型错误）
        config_data_invalid = {
            "name": "test",
            "count": 10,
            "metadata": {"key1": "value1", "key2": "not-an-integer"},
        }

        response = client.post("/api/save", json={"config": config_data_invalid})
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_array_validation(self, sample_schema_file, tmp_path):
        """测试数组的验证和保存"""
        output_file = tmp_path / "config.json"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        # 有效的数组
        config_data = {"name": "test", "count": 10, "tags": ["tag1", "tag2", "tag3"]}

        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 无效的数组（超过最大项数）
        config_data_invalid = {
            "name": "test",
            "count": 10,
            "tags": [f"tag{i}" for i in range(11)],
        }

        response = client.post("/api/save", json={"config": config_data_invalid})
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_yaml_save_and_load(self, sample_schema_file, tmp_path):
        """测试 YAML 格式保存和加载"""
        output_file = tmp_path / "config.yaml"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        # 保存配置为 YAML
        config_data = {
            "name": "test",
            "count": 42,
            "enabled": True,
            "tags": ["tag1", "tag2"],
        }
        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 验证文件存在且是有效的 YAML
        assert output_file.exists()
        with open(output_file, "r", encoding="utf-8") as f:
            loaded_config = yaml.safe_load(f)
        assert loaded_config == config_data

        # 重新创建应用，验证能正确加载 YAML 配置
        app2 = create_app(sample_schema_file, output_file)
        client2 = TestClient(app2)
        response2 = client2.get("/api/schema")
        assert response2.status_code == 200
        schema_data = response2.json()
        # 验证默认值已被 YAML 配置覆盖
        assert schema_data["properties"]["name"]["_meta"]["default"] == "test"
        assert schema_data["properties"]["count"]["_meta"]["default"] == 42

    def test_yml_extension(self, sample_schema_file, tmp_path):
        """测试 .yml 扩展名支持"""
        output_file = tmp_path / "config.yml"
        app = create_app(sample_schema_file, output_file)
        client = TestClient(app)

        config_data = {"name": "test", "count": 10}
        response = client.post("/api/save", json={"config": config_data})
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 验证文件是有效的 YAML
        with open(output_file, "r", encoding="utf-8") as f:
            loaded_config = yaml.safe_load(f)
        assert loaded_config == config_data
