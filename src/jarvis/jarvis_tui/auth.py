"""认证模块 - 与web版本loginWithPassword对齐"""

from dataclasses import dataclass
from typing import Optional
import httpx


@dataclass
class AuthToken:
    """认证Token"""

    token: str


class AuthManager:
    """认证管理器"""

    def __init__(self):
        self._token: Optional[str] = None
        self._gateway_url: Optional[str] = None

    def has_token(self) -> bool:
        """检查是否有有效Token"""
        return bool(self._token)

    def get_token(self) -> Optional[str]:
        """获取当前Token"""
        return self._token

    def clear_token(self) -> None:
        """清除Token"""
        self._token = None
        self._gateway_url = None

    async def login(self, gateway_url: str, password: str) -> str:
        """使用密码登录获取Token

        与web版本loginWithPassword对齐:
        - POST /api/auth/login
        - 请求体: {"password": "xxx"}
        - 响应: {"success": true, "data": {"token": "xxx"}}

        Args:
            gateway_url: 网关地址，格式为 host:port
            password: 登录密码

        Returns:
            str: 认证Token

        Raises:
            AuthenticationError: 认证失败
            ConnectionError: 连接失败
        """
        # 解析网关地址
        if ":" in gateway_url:
            host, port = gateway_url.rsplit(":", 1)
        else:
            host = gateway_url
            port = "8000"

        url = f"http://{host}:{port}/api/auth/login"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json={"password": password},
                    headers={"Content-Type": "application/json"},
                    timeout=10.0,
                )

                result = response.json()

                if (
                    not response.is_success
                    or not result.get("success")
                    or not result.get("data", {}).get("token")
                ):
                    error_msg = result.get("error", {}).get("message", "登录失败")
                    raise AuthenticationError(error_msg)

                token: str = result["data"]["token"]
                self._token = token

                # 登录成功后保存网关地址
                self._gateway_url = gateway_url

                # 登录成功后清除密码（安全最佳实践）
                return token

        except httpx.ConnectError as e:
            raise ConnectionError(f"连接失败: {e}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"连接超时: {e}") from e


class AuthenticationError(Exception):
    """认证错误"""

    pass


class ConnectionError(Exception):
    """连接错误"""

    pass
