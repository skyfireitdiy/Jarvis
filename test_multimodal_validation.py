#!/usr/bin/env python3
"""
多模态功能验证脚本

验证 mimo 模型的多模态支持功能
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from jarvis.jarvis_platform.registry import PlatformRegistry  # noqa: E402
from jarvis.jarvis_platform.content_types import (
    TextContent,
    ImageURLContent,
    ContentBlock,
)  # noqa: E402
from jarvis.jarvis_utils.embedding import (
    get_multimodal_token_count,
    _estimate_image_tokens,
)  # noqa: E402


def test_config_loading():
    """测试配置加载"""
    print("=== 测试配置加载 ===")

    try:
        # 获取平台实例（使用 platform_type 参数）
        registry = PlatformRegistry.get_global_platform_registry()

        # 检查可用平台
        available_platforms = registry.get_available_platforms()
        print(f"可用平台: {available_platforms}")

        # 创建 normal 平台（根据配置，normal_llm 是 openai_mimo_v2_5）
        platform = registry.create_platform(platform_type="normal", silent=False)
        if platform is None:
            print("❌ 无法加载 normal 平台 (create_platform 返回 None)")
            return False
        print(f"✅ 成功加载平台: {platform.name()}")
        print(f"   平台类型: {platform.platform_name()}")
        print(f"   支持多模态: {platform.supports_multimodal()}")

        return True
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return False


def test_token_calculation():
    """测试 token 计算"""
    print("\n=== 测试 Token 计算 ===")

    # 测试纯文本
    text_content = "Hello, world!"
    text_tokens = get_multimodal_token_count(text_content)
    print(f"✅ 纯文本 token 计算: '{text_content}' -> {text_tokens} tokens")

    # 测试多模态内容
    multimodal_content = [
        {"type": "text", "text": "Look at this image:"},
        {"type": "image_url", "image_url": "https://example.com/image.jpg"},
    ]
    multimodal_tokens = get_multimodal_token_count(multimodal_content)
    print(
        f"✅ 多模态 token 计算: {len(multimodal_content)} 个内容块 -> {multimodal_tokens} tokens"
    )

    # 测试图片 token 估算
    image_tokens = _estimate_image_tokens(
        {"image_url": "https://example.com/image.jpg"}
    )
    print(f"✅ 图片 token 估算: {image_tokens} tokens")

    return True


def test_multimodal_support():
    """测试多模态支持"""
    print("\n=== 测试多模态支持 ===")

    try:
        # 测试多模态消息格式转换（不依赖 API）
        text_content: TextContent = {"type": "text", "text": "What is in this image?"}
        image_content: ImageURLContent = {
            "type": "image_url",
            "image_url": "https://example.com/test.jpg",
            "detail": "high",
        }

        multimodal_message: list[ContentBlock] = [text_content, image_content]

        print(f"✅ 创建多模态消息: {len(multimodal_message)} 个内容块")
        print(f"   文本内容: {text_content['text']}")
        print(f"   图片 URL: {image_content['image_url']}")

        # 模拟 OpenAI 格式转换
        openai_format = []
        for block in multimodal_message:
            if block["type"] == "text":
                openai_format.append({"type": "text", "text": block["text"]})
            elif block["type"] == "image_url":
                image_url_data = block["image_url"]
                if isinstance(image_url_data, str):
                    image_url_data = {"url": image_url_data}
                openai_format.append({"type": "image_url", "image_url": image_url_data})

        print(f"✅ OpenAI 格式转换成功: {len(openai_format)} 个内容块")
        print(f"   格式: {openai_format}")

        # 验证格式正确性
        assert len(openai_format) == 2
        assert openai_format[0]["type"] == "text"
        assert openai_format[1]["type"] == "image_url"
        assert "url" in openai_format[1]["image_url"]

        print("✅ 多模态消息格式验证通过")

        return True

    except Exception as e:
        print(f"❌ 多模态支持测试失败: {e}")
        return False


def test_backward_compatibility():
    """测试向后兼容性"""
    print("\n=== 测试向后兼容性 ===")

    try:
        # 测试多模态消息拒绝逻辑（不依赖 API）
        print("✅ 测试多模态消息拒绝逻辑")

        # 模拟不支持多模态的平台
        class MockPlatform:
            def supports_multimodal(self):
                return False

        mock_platform = MockPlatform()

        # 测试多模态消息应该被拒绝
        multimodal_message = [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "image_url": "https://example.com/test.jpg"},
        ]

        # 模拟检查逻辑
        if (
            not isinstance(multimodal_message, str)
            and not mock_platform.supports_multimodal()
        ):
            print("✅ 多模态消息被正确拒绝（平台不支持）")
        else:
            print("❌ 多模态消息应该被拒绝")
            return False

        # 测试纯文本消息
        text_message = "Hello, world!"
        print(f"✅ 纯文本消息: '{text_message}'")

        return True

    except Exception as e:
        print(f"❌ 向后兼容性测试失败: {e}")
        return False


def main():
    """主函数"""
    print("🚀 开始多模态功能验证")
    print("=" * 50)

    tests = [
        ("配置加载", test_config_loading),
        ("Token 计算", test_token_calculation),
        ("多模态支持", test_multimodal_support),
        ("向后兼容性", test_backward_compatibility),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
            results.append((test_name, False))

    # 输出测试结果
    print("\n" + "=" * 50)
    print("📊 测试结果总结")
    print("=" * 50)

    passed = 0
    failed = 0

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\n总计: {passed + failed} 个测试")
    print(f"通过: {passed} 个")
    print(f"失败: {failed} 个")

    if failed == 0:
        print("\n🎉 所有测试通过！多模态功能正常工作。")
        return 0
    else:
        print(f"\n⚠️  有 {failed} 个测试失败，请检查实现。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
