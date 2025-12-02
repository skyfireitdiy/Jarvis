# -*- coding: utf-8 -*-
"""jarvis_utils.http 模块单元测试"""

from unittest.mock import patch, MagicMock
import requests

from jarvis.jarvis_utils.http import (
    get_requests_session,
    post,
    get,
    put,
    delete,
    stream_post,
)


class TestGetRequestsSession:
    """测试 get_requests_session 函数"""

    def test_returns_session(self):
        """测试返回 Session 对象"""
        session = get_requests_session()
        assert isinstance(session, requests.Session)

    def test_session_has_user_agent(self):
        """测试 Session 包含 User-Agent"""
        session = get_requests_session()
        assert "User-Agent" in session.headers
        assert "Mozilla" in session.headers["User-Agent"]


class TestPost:
    """测试 post 函数"""

    @patch("jarvis.jarvis_utils.http.get_requests_session")
    def test_post_request(self, mock_get_session):
        """测试 POST 请求"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session.post.return_value = mock_response
        mock_get_session.return_value = mock_session

        result = post("http://example.com", json={"key": "value"})

        mock_session.post.assert_called_once()
        assert result == mock_response

    @patch("jarvis.jarvis_utils.http.get_requests_session")
    def test_post_with_data(self, mock_get_session):
        """测试带 data 的 POST 请求"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session.post.return_value = mock_response
        mock_get_session.return_value = mock_session

        post("http://example.com", data="test data")

        call_kwargs = mock_session.post.call_args[1]
        assert call_kwargs.get("data") == "test data"
        assert call_kwargs.get("timeout") is None


class TestGet:
    """测试 get 函数"""

    @patch("jarvis.jarvis_utils.http.get_requests_session")
    def test_get_request(self, mock_get_session):
        """测试 GET 请求"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session.get.return_value = mock_response
        mock_get_session.return_value = mock_session

        result = get("http://example.com")

        mock_session.get.assert_called_once_with(url="http://example.com", timeout=None)
        assert result == mock_response


class TestPut:
    """测试 put 函数"""

    @patch("jarvis.jarvis_utils.http.get_requests_session")
    def test_put_request(self, mock_get_session):
        """测试 PUT 请求"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session.put.return_value = mock_response
        mock_get_session.return_value = mock_session

        put("http://example.com", data="test data")

        call_kwargs = mock_session.put.call_args[1]
        assert call_kwargs.get("data") == "test data"
        assert call_kwargs.get("timeout") is None


class TestDelete:
    """测试 delete 函数"""

    @patch("jarvis.jarvis_utils.http.get_requests_session")
    def test_delete_request(self, mock_get_session):
        """测试 DELETE 请求"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session.delete.return_value = mock_response
        mock_get_session.return_value = mock_session

        result = delete("http://example.com")

        mock_session.delete.assert_called_once_with(
            url="http://example.com", timeout=None
        )
        assert result == mock_response


class TestStreamPost:
    """测试 stream_post 函数"""

    @patch("jarvis.jarvis_utils.http.get_requests_session")
    def test_stream_post(self, mock_get_session):
        """测试流式 POST 请求"""
        # 创建 mock session 和 response
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        # iter_lines 返回一个迭代器，chunk_size=1
        mock_response.iter_lines.return_value = iter([b"line1\n", b"line2\n"])

        # post 返回的 context manager
        mock_post_context = MagicMock()
        mock_post_context.__enter__ = MagicMock(return_value=mock_response)
        mock_post_context.__exit__ = MagicMock(return_value=None)
        mock_session.post.return_value = mock_post_context

        # session 作为 context manager
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_get_session.return_value = mock_session

        result = list(stream_post("http://example.com", json={"key": "value"}))

        # 验证调用了 post 并设置了 stream=True
        assert mock_session.post.called
        call_kwargs = mock_session.post.call_args[1]
        assert call_kwargs.get("stream") is True
        # 验证结果
        assert len(result) == 2
        assert result[0] == "line1\n"
        assert result[1] == "line2\n"
