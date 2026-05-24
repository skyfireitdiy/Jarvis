#!/usr/bin/env python3
"""
多模态 API 实际调用测试

测试实际调用多模态 API
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


def test_multimodal_api_call():
    """测试多模态 API 实际调用"""
    print("=== 测试多模态 API 实际调用 ===")

    try:
        # 获取平台实例
        registry = PlatformRegistry.get_global_platform_registry()
        platform = registry.create_platform(platform_type="normal", silent=False)

        if platform is None:
            print("❌ 无法加载平台")
            return False

        print(f"✅ 成功加载平台: {platform.name()}")
        print(f"   支持多模态: {platform.supports_multimodal()}")

        if not platform.supports_multimodal():
            print("❌ 平台不支持多模态")
            return False

        # 创建多模态消息
        text_content: TextContent = {
            "type": "text",
            "text": "这张图片里有什么？请用中文回答。",
        }

        # 使用一个公开的测试图片 URL
        image_content: ImageURLContent = {
            "type": "image_url",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png",
            "detail": "low",
        }

        multimodal_message: list[ContentBlock] = [text_content, image_content]

        print(f"✅ 创建多模态消息: {len(multimodal_message)} 个内容块")
        print(f"   文本内容: {text_content['text']}")
        print(f"   图片 URL: {image_content['image_url']}")

        # 调用 chat 方法
        print("\n🚀 调用多模态 API...")
        response_chunks = []
        for chunk in platform.chat(multimodal_message):
            response_chunks.append(chunk)
            print(chunk, end="", flush=True)

        print("\n\n✅ API 调用成功")
        print(f"   响应长度: {len(''.join(response_chunks))} 字符")

        return True

    except Exception as e:
        print(f"\n❌ 多模态 API 调用失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("🚀 开始多模态 API 实际调用测试")
    print("=" * 50)

    result = test_multimodal_api_call()

    print("\n" + "=" * 50)
    if result:
        print("🎉 多模态 API 调用测试通过！")
        return 0
    else:
        print("❌ 多模态 API 调用测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
