# -*- coding: utf-8 -*-
from typing import Any, Protocol, Tuple


class OutputHandlerProtocol(Protocol):
    """
    Defines the interface for an output handler, which is responsible for
    processing the model's response, typically to execute a tool.
    """

    def name(self) -> str:
        """Returns the name of the handler."""
        ...

    def can_handle(self, response: str) -> bool:
        """Determines if this handler can process the given response."""
        ...

    def prompt(self) -> str:
        """Returns the prompt snippet that describes the handler's functionality."""
        ...

    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
        """
        Handles the response, executing the associated logic.

        Returns:
            A tuple containing a boolean (whether to return) and the result.
        """
        ...
