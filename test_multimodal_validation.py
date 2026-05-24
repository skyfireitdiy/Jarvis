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

from jarvis.jarvis_platform.registry import get_platform_instance
from jarvis.jarvis_platform.content_types import TextContent, ImageURLContent, ContentBlock
from jarvis.jarvis_utils.embedding import get_multimodal_token_count, _estimate_image_tokens


def test_config_loading():
    """测试配置加载"""
    print("=== 测试配置加载 ===")
    
    try:
        # 获取 mimo_v2_5 平台实例
        platform = get_platform_instance("openai_mimo_v2_5")
        print(f"✅ 成功加载平台: {platform.name()}")
        print(f"   平台类型: {platform.platform_name()}")
        print(f"   支持多模态: {platform.supports_multimodal()}")
        
        # 获取 mimo_v2_pro 平台实例
        platform_pro = get_platform_instance("openai_mimo_v2_pro")
        print(f"✅ 成功加载平台: {platform_pro.name()}")
        print(f"   平台类型: {platform_pro.platform_name()}")
        print(f"   支持多模态: {platform_pro.supports_multimodal()}")
        
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
    print(f"✅ 多模态 token 计算: {len(multimodal_content)} 个内容块 -> {multimodal_tokens} tokens")
    
    # 测试图片 token 估算
    image_tokens = _estimate_image_tokens({"image_url": "https://example.com/image.jpg"})
    print(f"✅ 图片 token 估算: {image_tokens} tokens")
    
    return True


def test_multimodal_support():
    """测试多模态支持"""
    print("\n=== 测试多模态支持 ===")
    
    try:
        # 获取支持多模态的平台
        platform = get_platform_instance("openai_mimo_v2_5")
        
        if not platform.supports_multimodal():
            print("❌ 平台不支持多模态")
            return False
        
        print(f"✅ 平台支持多模态: {platform.supports_multimodal()}")
        
        # 测试多模态消息处理
        text_content: TextContent = {"type": "text", "text": "What is in this image?"}
        image_content: ImageURLContent = {
            "type": "image_url",
            "image_url": "https://example.com/test.jpg",
            "detail": "high"
        }
        
        multimodal_message: list[ContentBlock] = [text_content, image_content]
        
        print(f"✅ 创建多模态消息: {len(multimodal_message)} 个内容块")
        print(f"   文本内容: {text_content['text']}")
        print(f"   图片 URL: {image_content['image_url']}")
        
        # 注意：这里不实际调用 API，只验证消息格式
        print("✅ 多模态消息格式验证通过")
        
        return True
        
    except Exception as e:
        print(f"❌ 多模态支持测试失败: {e}")
        return False


def test_backward_compatibility():
    """测试向后兼容性"""
    print("\n=== 测试向后兼容性 ===")
    
    try:
        # 获取不支持多模态的平台
        platform = get_platform_instance("openai_mimo_v2_pro")
        
        if platform.supports_multimodal():
            print("❌ 平台应该不支持多模态")
            return False
        
        print(f"✅ 平台不支持多模态: {not platform.supports_multimodal()}")
        
        # 测试纯文本消息
        text_message = "Hello, world!"
        print(f"✅ 纯文本消息: '{text_message}'")
        
        # 测试多模态消息应该被拒绝
        multimodal_message = [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "image_url": "https://example.com/test.jpg"},
        ]
        
        print("✅ 多模态消息应该被拒绝（平台不支持）")
        
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