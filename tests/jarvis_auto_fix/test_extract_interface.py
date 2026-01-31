"""Tests for ExtractInterfaceRefactorer module."""

import ast
import tempfile
from pathlib import Path

from jarvis.jarvis_auto_fix.refactoring.extract_interface import (
    ExtractInterfaceRefactorer,
    InterfaceMethodAnalyzer,
)
from jarvis.jarvis_auto_fix.fix_history import FixHistory


class TestInterfaceMethodAnalyzer:
    """Tests for InterfaceMethodAnalyzer class."""

    def test_analyze_simple_class(self) -> None:
        """Test analyzing a simple class with public methods."""
        code = '''
class UserService:
    def get_user(self, user_id: int) -> dict:
        """Get user by ID."""
        return {}

    def create_user(self, name: str) -> dict:
        """Create a new user."""
        return {"name": name}
'''
        tree = ast.parse(code)
        class_node = tree.body[0]

        analyzer = InterfaceMethodAnalyzer()
        analyzer.analyze_class(class_node)

        assert len(analyzer.public_methods) == 2
        assert "get_user" in analyzer.public_methods
        assert "create_user" in analyzer.public_methods

    def test_filter_private_methods(self) -> None:
        """Test that private methods are filtered out."""
        code = """
class Service:
    def public_method(self) -> None:
        pass

    def _private_method(self) -> None:
        pass

    def __internal_method(self) -> None:
        pass
"""
        tree = ast.parse(code)
        class_node = tree.body[0]

        analyzer = InterfaceMethodAnalyzer()
        analyzer.analyze_class(class_node)

        assert "public_method" in analyzer.public_methods
        assert "_private_method" not in analyzer.public_methods
        assert "_private_method" in analyzer.private_methods
        assert "__internal_method" in analyzer.private_methods

    def test_include_init_method(self) -> None:
        """Test that __init__ is included in public methods."""
        code = """
class Database:
    def __init__(self, connection_string: str) -> None:
        self.connection = connection_string

    def connect(self) -> bool:
        return True
"""
        tree = ast.parse(code)
        class_node = tree.body[0]

        analyzer = InterfaceMethodAnalyzer()
        analyzer.analyze_class(class_node)

        assert "__init__" in analyzer.public_methods
        assert "connect" in analyzer.public_methods

    def test_get_method_signature(self) -> None:
        """Test extracting method signature."""
        code = """
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b

    def multiply(self, x: float, y: float) -> float:
        return x * y

    async def fetch_data(self, url: str) -> dict:
        return {}
"""
        tree = ast.parse(code)
        class_node = tree.body[0]

        analyzer = InterfaceMethodAnalyzer()
        analyzer.analyze_class(class_node)

        signature = analyzer.get_method_signature("add")
        assert "self, a: int, b: int" in signature
        assert "-> int" in signature

        signature = analyzer.get_method_signature("multiply")
        assert "self, x: float, y: float" in signature
        assert "-> float" in signature

    def test_get_method_signature_with_defaults_and_varargs(self) -> None:
        """Test extracting method signature with defaults and *args/**kwargs."""
        code = """
class Processor:
    def process(self, data: str, mode: str = 'default') -> None:
        pass

    def process_all(self, *args: str, **kwargs: int) -> None:
        pass
"""
        tree = ast.parse(code)
        class_node = tree.body[0]

        analyzer = InterfaceMethodAnalyzer()
        analyzer.analyze_class(class_node)

        signature = analyzer.get_method_signature("process")
        assert "self, data: str, mode: str" in signature
        assert "-> None" in signature

        signature = analyzer.get_method_signature("process_all")
        assert "*args: str" in signature
        assert "**kwargs: int" in signature

    def test_get_method_docstring(self) -> None:
        """Test extracting method docstring."""
        code = '''
class DocumentService:
    def save_document(self, doc_id: str) -> bool:
        """Save document to storage.
        
        Args:
            doc_id: Document identifier.
            
        Returns:
            True if successful.
        """
        return True
'''
        tree = ast.parse(code)
        class_node = tree.body[0]

        analyzer = InterfaceMethodAnalyzer()
        analyzer.analyze_class(class_node)

        docstring = analyzer.get_method_docstring("save_document")
        assert "Save document to storage" in docstring
        assert "doc_id: Document identifier" in docstring


class TestExtractInterfaceRefactorer:
    """Tests for ExtractInterfaceRefactorer class."""

    def test_extract_basic_interface(self) -> None:
        """Test extracting a basic ABC interface."""
        code = """
class UserRepository:
    def find_by_id(self, user_id: int) -> dict:
        return {"id": user_id}

    def find_all(self) -> list:
        return []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(file_path, "UserRepository")

            assert result.success is True
            assert "IUserRepository" in result.interface_code
            assert "from abc import ABC, abstractmethod" in result.interface_code
            assert "find_by_id" in result.interface_code
            assert "find_all" in result.interface_code
            assert "class UserRepository(IUserRepository)" in result.modified_class_code
        finally:
            Path(file_path).unlink()

    def test_extract_interface_with_custom_name(self) -> None:
        """Test extracting interface with custom name."""
        code = """
class EmailService:
    def send_email(self, to: str, subject: str) -> bool:
        return True
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(
                file_path, "EmailService", interface_name="IEmailSender"
            )

            assert result.success is True
            assert "IEmailSender" in result.interface_code
        finally:
            Path(file_path).unlink()

    def test_extract_protocol_interface(self) -> None:
        """Test extracting a Protocol interface."""
        code = """
class DataProcessorImpl:
    def process(self, data: dict) -> dict:
        return data

    def validate(self, data: dict) -> bool:
        return True
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(
                file_path, "DataProcessorImpl", base_type="Protocol"
            )

            assert result.success is True
            assert "from typing import Protocol" in result.interface_code
            assert "class DataProcessor(Protocol):" in result.interface_code
            assert "DataProcessorImpl(DataProcessor)" in result.modified_class_code
        finally:
            Path(file_path).unlink()

    def test_extract_specific_methods(self) -> None:
        """Test extracting only specific methods."""
        code = """
class UserService:
    def get_user(self, user_id: int) -> dict:
        return {}

    def create_user(self, name: str) -> dict:
        return {}

    def delete_user(self, user_id: int) -> bool:
        return True
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(
                file_path, "UserService", methods=["get_user", "create_user"]
            )

            assert result.success is True
            assert "get_user" in result.interface_code
            assert "create_user" in result.interface_code
            assert "delete_user" not in result.interface_code
        finally:
            Path(file_path).unlink()

    def test_suggest_interface_name_abc(self) -> None:
        """Test interface name suggestion for ABC."""
        refactorer = ExtractInterfaceRefactorer()

        # Standard class
        name = refactorer._suggest_interface_name("UserService", "ABC")
        assert name == "IUserService"

        # Class with Impl suffix
        name = refactorer._suggest_interface_name("UserServiceImpl", "ABC")
        assert name == "IUserService"

        # Class already with I prefix
        name = refactorer._suggest_interface_name("IUserService", "ABC")
        assert name == "IUserService"

    def test_suggest_interface_name_protocol(self) -> None:
        """Test interface name suggestion for Protocol."""
        refactorer = ExtractInterfaceRefactorer()

        # Class with Impl suffix
        name = refactorer._suggest_interface_name("DataProcessorImpl", "Protocol")
        assert name == "DataProcessor"

        # Standard class
        name = refactorer._suggest_interface_name("UserService", "Protocol")
        assert name == "UserServiceProtocol"

    def test_extract_interface_with_docstrings(self) -> None:
        """Test that method docstrings are preserved."""
        code = '''
class PaymentService:
    def process_payment(self, amount: float, currency: str) -> bool:
        """Process a payment.
        
        Args:
            amount: Payment amount.
            currency: Currency code.
            
        Returns:
            True if payment successful.
        """
        return True
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(file_path, "PaymentService")

            assert result.success is True
            assert "Process a payment" in result.interface_code
            assert "amount: Payment amount" in result.interface_code
        finally:
            Path(file_path).unlink()

    def test_extract_interface_with_type_annotations(self) -> None:
        """Test that type annotations are preserved."""
        code = """
from typing import List, Optional

class TaskManager:
    def get_tasks(self, user_id: int) -> List[dict]:
        return []

    def get_task(self, task_id: int) -> Optional[dict]:
        return None
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(file_path, "TaskManager")

            assert result.success is True
            assert "user_id: int" in result.interface_code
            assert "-> List[dict]" in result.interface_code
            assert "task_id: int" in result.interface_code
            assert "-> Optional[dict]" in result.interface_code
        finally:
            Path(file_path).unlink()

    def test_class_not_found(self) -> None:
        """Test error handling when class is not found."""
        code = "class Service: pass"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(file_path, "NonExistentClass")

            assert result.success is False
            assert "not found" in result.error_message
        finally:
            Path(file_path).unlink()

    def test_class_with_existing_bases(self) -> None:
        """Test extracting interface when class already has bases."""
        code = """
class BaseService:
    pass

class UserService(BaseService):
    def get_user(self, user_id: int) -> dict:
        return {}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(file_path, "UserService")

            assert result.success is True
            assert (
                "class UserService(BaseService, IUserService)"
                in result.modified_class_code
            )
        finally:
            Path(file_path).unlink()

    def test_analyze_interface_candidates(self) -> None:
        """Test analyzing file for interface extraction candidates."""
        code = """
class ServiceWithEnoughMethods:
    def method1(self) -> None:
        pass

    def method2(self) -> None:
        pass

class SmallService:
    def single_method(self) -> None:
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            candidates = refactorer.analyze_interface_candidates(file_path)

            # Should find ServiceWithEnoughMethods (has 2+ methods)
            assert len(candidates) >= 1
            service_candidate = [
                c for c in candidates if c.original_class == "ServiceWithEnoughMethods"
            ]
            assert len(service_candidate) == 1
        finally:
            Path(file_path).unlink()

    def test_fix_history_integration(self) -> None:
        """Test that extraction is recorded in FixHistory."""
        code = """
class Logger:
    def log(self, message: str) -> None:
        print(message)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        # Create a temporary history file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as hf:
            history_file_path = hf.name

        try:
            history = FixHistory(history_file=history_file_path)
            refactorer = ExtractInterfaceRefactorer(history=history)
            result = refactorer.extract_interface(file_path, "Logger")

            assert result.success is True
            # Verify fix was recorded
            records = history.get_all_fixes()
            assert len(records) == 1
            assert "ILogger" in records[0].fix_applied
            assert records[0].rollback_available is True
        finally:
            Path(file_path).unlink()
            Path(history_file_path).unlink(missing_ok=True)

    def test_async_methods(self) -> None:
        """Test extracting interface with async methods."""
        code = """
class AsyncDataService:
    async def fetch_data(self, url: str) -> dict:
        return {}

    async def save_data(self, data: dict) -> bool:
        return True
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(file_path, "AsyncDataService")

            assert result.success is True
            assert "fetch_data" in result.interface_code
            assert "save_data" in result.interface_code
            # async methods should not have async in interface
            assert "async def" not in result.interface_code
        finally:
            Path(file_path).unlink()

    def test_interface_info_returned(self) -> None:
        """Test that InterfaceInfo is correctly populated."""
        code = """
class CacheService:
    def get(self, key: str) -> str:
        return ""

    def set(self, key: str, value: str) -> None:
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            file_path = f.name

        try:
            refactorer = ExtractInterfaceRefactorer()
            result = refactorer.extract_interface(file_path, "CacheService")

            assert result.success is True
            assert result.interface_info is not None
            assert result.interface_info.interface_name == "ICacheService"
            assert result.interface_info.original_class == "CacheService"
            assert result.interface_info.base_type == "ABC"
            assert "get" in result.interface_info.methods
            assert "set" in result.interface_info.methods
        finally:
            Path(file_path).unlink()
