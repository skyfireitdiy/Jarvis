import unittest
import sys
import os

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from jarvis.jarvis_codebase.main import CodeBase  # 使用实际的类名

class TestVectorSearch(unittest.TestCase):
    def setUp(self):
        self.instance = CodeBase(root_dir='.')  # 提供项目的根目录

    def test_vector_search(self):
        query_variants = ["example query"]
        top_k = 5
        results = self.instance._vector_search(query_variants, top_k)
        self.assertIsInstance(results, dict)
        self.assertTrue(len(results) <= top_k)

if __name__ == "__main__":
    unittest.main()