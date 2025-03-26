

from abc import ABC, abstractmethod
from typing import Any, Tuple



class OutputHandler(ABC):
    @abstractmethod
    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
        pass

    @abstractmethod
    def can_handle(self, response: str) -> bool:
        pass

    @abstractmethod
    def prompt(self) -> str:
        pass

    @abstractmethod
    def name(self) -> str:
        pass