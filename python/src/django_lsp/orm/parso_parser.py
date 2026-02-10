"""
Parso-based ORM parser for Django LSP.

This module provides Python code parsing using Parso for detecting
Django ORM operations and extracting context for completions/hover.

Parso is a pure Python parser that handles incomplete code gracefully,
making it ideal for IDE/LSP use cases.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

import parso as _parso

_PARSER_AVAILABLE = True


# Common ORM operations that take field arguments
ORM_FIELD_OPERATIONS = frozenset(
    {
        "filter",
        "exclude",
        "get",
        "get_or_create",
        "update_or_create",
        "create",
        "update",
        "values",
        "values_list",
        "order_by",
        "only",
        "defer",
        "select_related",
        "prefetch_related",
        "annotate",
        "aggregate",
    }
)

# Common manager names
MANAGER_NAMES = frozenset({"objects", "all_objects", "_default_manager"})


class ParsoParser:
    """
    Parso-based parser for Django ORM pattern detection.

    This parser detects Django ORM operations (filter, exclude, get, etc.)
    and provides context for completions and hover documentation.
    """

    def __init__(self) -> None:
        """Initialize the Parso parser."""
        if not _PARSER_AVAILABLE:
            logger.warning("Parso parser unavailable - install parso")

    @property
    def is_available(self) -> bool:
        """Check if the parser is available and functional."""
        return _PARSER_AVAILABLE

    def parse(self, source: str) -> Optional[Any]:
        """Parse source code and return the module node."""
        if not _PARSER_AVAILABLE:
            return None

        try:
            return _parso.parse(source)
        except Exception as e:
            logger.error("Error parsing source: %s", e)
            return None

    def get_completion_context(
        self, source: str, cursor_line: int, cursor_col: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get completion context at the given position.

        Args:
            source: Python source code
            cursor_line: 1-based line number
            cursor_col: 0-based column number

        Returns:
            Dictionary with ORM context or None
        """
        try:
            orm_operations = self.extract_orm_operations_with_ranges(source)

            for orm_op in orm_operations:
                start_line = orm_op.get("range_start_line", 0)
                start_col = orm_op.get("range_start_character", 0)
                end_line = orm_op.get("range_end_line", 0)
                end_col = orm_op.get("range_end_character", 0)

                # Convert to 0-based for comparison
                check_line = cursor_line - 1

                # Check if cursor is within this ORM call's argument range
                if start_line <= check_line <= end_line:
                    if check_line == start_line and cursor_col < start_col:
                        continue
                    if check_line == end_line and cursor_col > end_col:
                        continue

                    return {
                        "model_name": orm_op["model_name"],
                        "manager_name": orm_op["manager_name"],
                        "operation_name": orm_op["operation_name"],
                        "is_self": orm_op.get("is_self", False),
                        "context_type": "orm_call",
                        "cursor_line": cursor_line,
                        "cursor_col": cursor_col,
                    }

            return None

        except Exception as e:
            logger.error("Error in get_completion_context: %s", e)
            return None

    def extract_current_argument(
        self, source: str, cursor_line: int, cursor_col: int
    ) -> str:
        """
        Extract the text of the argument at the cursor position.

        Args:
            source: Source code
            cursor_line: 1-based line number
            cursor_col: 0-based column number

        Returns:
            The text of the current argument, or empty string
        """
        try:
            # Get the line content up to cursor
            lines = source.split("\n")
            if cursor_line < 1 or cursor_line > len(lines):
                return ""

            line = lines[cursor_line - 1]
            prefix = line[:cursor_col]

            # Look for the start of the current argument
            # Find the last comma or opening paren
            arg_start = max(prefix.rfind(","), prefix.rfind("("))
            if arg_start == -1:
                return ""

            current_arg = prefix[arg_start + 1 :].strip()
            return current_arg

        except Exception as e:
            logger.error("Error extracting current argument: %s", e)
            return ""

    def extract_field_name_at_position(
        self, source: str, cursor_line: int, cursor_col: int
    ) -> str:
        """
        Extract field name part when cursor is after a field path ending with __.

        Args:
            source: Source code
            cursor_line: 1-based line number
            cursor_col: 0-based column number

        Returns:
            Field name ending with __, or empty string
        """
        try:
            current_arg = self.extract_current_argument(source, cursor_line, cursor_col)

            if "__" in current_arg:
                # Find the base field name (everything before the last __)
                last_underscore = current_arg.rfind("__")
                return current_arg[: last_underscore + 2]

            return ""

        except Exception as e:
            logger.error("Error extracting field name at position: %s", e)
            return ""

    def extract_orm_operations_with_ranges(self, source: str) -> List[Dict[str, Any]]:
        """
        Extract all ORM operations from source with position ranges.

        Args:
            source: Python source code

        Returns:
            List of ORM operations with position ranges
        """
        if not _PARSER_AVAILABLE:
            return []

        try:
            module = self.parse(source)
            if not module:
                return []

            orm_operations: List[Dict[str, Any]] = []
            self._find_orm_calls(module, orm_operations)
            return orm_operations

        except Exception as e:
            logger.error("Error extracting ORM operations: %s", e)
            return []

    def _find_orm_calls(self, node: Any, results: List[Dict[str, Any]]) -> None:
        """Recursively find ORM call patterns in the AST."""
        try:
            # Check if this is an atom_expr or power node (call chain)
            # Pattern: Model.objects.filter(...)
            if hasattr(node, "type") and node.type in (
                "atom_expr",
                "power",
                "error_node",
            ):
                orm_info = self._extract_orm_call_info(node)
                if orm_info:
                    results.append(orm_info)

            # Recurse into children
            if hasattr(node, "children") and node.children:
                for child in node.children:
                    self._find_orm_calls(child, results)

        except Exception as e:
            logger.debug("Error in _find_orm_calls: %s", e)

    def _extract_orm_call_info(self, node: Any) -> Optional[Dict[str, Any]]:
        """Extract ORM call information from an expression node."""
        try:
            # Get the string representation of the node
            code = node.get_code().strip()

            # Pattern: Model.manager.operation(args)
            # Use regex to match ORM patterns
            pattern = r"(\w+)\.(\w+)\.(\w+)\s*\("
            match = re.match(pattern, code)

            if not match:
                return None

            model_name = match.group(1)
            manager_name = match.group(2)
            operation_name = match.group(3)

            # Validate this looks like an ORM call
            if (
                manager_name not in MANAGER_NAMES
                and operation_name not in ORM_FIELD_OPERATIONS
            ):
                # If neither manager nor operation matches known patterns, skip
                if not self._looks_like_model(model_name):
                    return None

            # Find the trailer with the arguments
            args_range = self._find_argument_range(node, operation_name)

            return {
                "model_name": model_name,
                "manager_name": manager_name,
                "operation_name": operation_name,
                "is_self": model_name == "self",
                "context_type": "orm_call",
                **args_range,
            }

        except Exception as e:
            logger.debug("Error extracting ORM call info: %s", e)
            return None

    def _find_argument_range(self, node: Any, operation_name: str) -> Dict[str, int]:
        """Find the position range of the arguments for the given operation."""
        default_range = {
            "range_start_line": 0,
            "range_start_character": 0,
            "range_end_line": 0,
            "range_end_character": 0,
        }

        try:
            # Walk through trailers to find the argument list
            if hasattr(node, "children"):
                for i, child in enumerate(node.children):
                    if hasattr(child, "type") and child.type == "trailer":
                        # Check if this trailer is a call with our operation
                        child_code = child.get_code().strip()
                        if child_code.startswith("("):
                            # This is an argument list trailer
                            start_pos = child.start_pos
                            end_pos = child.end_pos

                            return {
                                "range_start_line": start_pos[0] - 1,  # 0-based
                                "range_start_character": start_pos[1],
                                "range_end_line": end_pos[0] - 1,
                                "range_end_character": end_pos[1],
                            }

            # Fallback: use the whole node range
            if hasattr(node, "start_pos") and hasattr(node, "end_pos"):
                return {
                    "range_start_line": node.start_pos[0] - 1,
                    "range_start_character": node.start_pos[1],
                    "range_end_line": node.end_pos[0] - 1,
                    "range_end_character": node.end_pos[1],
                }

        except Exception as e:
            logger.debug("Error finding argument range: %s", e)

        return default_range

    def _looks_like_model(self, name: str) -> bool:
        """Check if a name looks like a Django model (PascalCase)."""
        if not name:
            return False
        # Models are typically PascalCase
        return name[0].isupper() and not name.isupper()

    def analyze_imports(self, source: str) -> Dict[str, str]:
        """
        Analyze Python source to detect available Django models.

        Args:
            source: Python source code

        Returns:
            Dictionary mapping model names to import paths
        """
        if not _PARSER_AVAILABLE:
            return {}

        try:
            module = self.parse(source)
            if not module:
                return {}

            imports: Dict[str, str] = {}
            self._collect_imports(module, imports)
            self._collect_class_definitions(module, imports)
            return imports

        except Exception as e:
            logger.error("Error analyzing imports: %s", e)
            return {}

    def _collect_imports(self, node: Any, imports: Dict[str, str]) -> None:
        """Collect import statements from the AST."""
        try:
            if hasattr(node, "type"):
                # from x import y
                if node.type == "import_from":
                    module_name = ""
                    imported_names: List[str] = []

                    for child in node.children:
                        if hasattr(child, "type"):
                            if child.type == "dotted_name":
                                module_name = child.get_code().strip()
                            elif child.type == "import_as_names":
                                for name_child in child.children:
                                    if (
                                        hasattr(name_child, "type")
                                        and name_child.type == "name"
                                    ):
                                        imported_names.append(name_child.value)
                            elif child.type == "name":
                                imported_names.append(child.value)

                    for name in imported_names:
                        if module_name:
                            imports[name] = f"{module_name}.{name}"
                        else:
                            imports[name] = name

                # import x
                elif node.type == "import_name":
                    for child in node.children:
                        if hasattr(child, "type") and child.type == "dotted_as_names":
                            for name_child in child.children:
                                if (
                                    hasattr(name_child, "type")
                                    and name_child.type == "dotted_name"
                                ):
                                    module = name_child.get_code().strip()
                                    imports[module.split(".")[-1]] = module

            # Recurse
            if hasattr(node, "children") and node.children:
                for child in node.children:
                    self._collect_imports(child, imports)

        except Exception as e:
            logger.debug("Error collecting imports: %s", e)

    def _collect_class_definitions(self, node: Any, result: Any) -> None:
        """Collect class definitions from the AST."""
        try:
            if hasattr(node, "type") and node.type == "classdef":
                # Get the class name
                if hasattr(node, "name") and node.name:
                    class_name = node.name.value
                    if isinstance(result, dict):
                        result[class_name] = class_name
                    elif isinstance(result, set):
                        result.add(class_name)

            # Recurse
            if hasattr(node, "children") and node.children:
                for child in node.children:
                    self._collect_class_definitions(child, result)

        except Exception as e:
            logger.debug("Error collecting class definitions: %s", e)

    def get_defined_classes(self, source: str) -> Set[str]:
        """Return names of classes defined in the source."""
        result: Set[str] = set()

        if not _PARSER_AVAILABLE:
            return result

        try:
            module = self.parse(source)
            if module:
                self._collect_class_definitions(module, result)
        except Exception as e:
            logger.debug("Error getting defined classes: %s", e)

        return result

    def resolve_self_to_class_name(
        self, document_source: str, line_number: int
    ) -> Optional[str]:
        """
        Resolve 'self' to the enclosing class name.

        Args:
            document_source: Document source code
            line_number: Line number (0-based)

        Returns:
            Enclosing class name or None
        """
        if not _PARSER_AVAILABLE:
            return None

        try:
            module = self.parse(document_source)
            if not module:
                return None

            # Find the node at the given line
            target_line = line_number + 1  # parso uses 1-based lines

            return self._find_enclosing_class_at_line(module, target_line)

        except Exception as e:
            logger.debug("Error resolving self: %s", e)
            return None

    def _find_enclosing_class_at_line(
        self, node: Any, target_line: int
    ) -> Optional[str]:
        """Find the enclosing class for a given line."""
        try:
            # Check if this is a class definition containing the target line
            if hasattr(node, "type") and node.type == "classdef":
                start_line = node.start_pos[0]
                end_line = node.end_pos[0]

                if start_line <= target_line <= end_line:
                    # This class contains the target line
                    # Check if any nested class also contains it
                    if hasattr(node, "children") and node.children:
                        for child in node.children:
                            nested_class = self._find_enclosing_class_at_line(
                                child, target_line
                            )
                            if nested_class and nested_class not in ("Meta", "Options"):
                                return nested_class

                    # Return this class name
                    if hasattr(node, "name") and node.name:
                        class_name = node.name.value
                        if class_name not in ("Meta", "Options"):
                            return class_name

            # Recurse into children
            if hasattr(node, "children") and node.children:
                for child in node.children:
                    result = self._find_enclosing_class_at_line(child, target_line)
                    if result:
                        return result

        except Exception as e:
            logger.debug("Error finding enclosing class: %s", e)

        return None

    def resolve_model_name_if_self(
        self, model_name: str, document_source: str, line_number: int
    ) -> str:
        """
        Resolve model name to class name if it's 'self'.

        Args:
            model_name: Model name to resolve
            document_source: Document source code
            line_number: Line number (0-based)

        Returns:
            Resolved model name
        """
        if model_name == "self":
            resolved = self.resolve_self_to_class_name(document_source, line_number)
            return resolved if resolved else model_name
        return model_name


# Module-level singleton for reuse
_parser_instance: Optional[ParsoParser] = None


def get_parser() -> ParsoParser:
    """Get the shared parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = ParsoParser()
    return _parser_instance
