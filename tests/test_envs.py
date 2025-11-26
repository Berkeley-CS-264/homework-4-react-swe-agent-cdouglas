"""
Unit tests for SWEEnvironment tools.

Tests cover:
- General-purpose functionality tests
- Specialized tests based on real instances from evaluation runs
- Edge cases and error handling
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import json
import subprocess
from pathlib import Path

# Mock the dependencies before importing SWEEnvironment
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock all external dependencies before importing
sys.modules['minisweagent'] = MagicMock()
sys.modules['minisweagent.environments'] = MagicMock()
sys.modules['swebench'] = MagicMock()
sys.modules['utils'] = MagicMock()

# Mock get_sb_environment before importing envs
mock_get_sb = MagicMock()
sys.modules['utils'].get_sb_environment = mock_get_sb

# Now import envs (it will use our mocks)
from envs import SWEEnvironment


class MockEnvironment:
    """Mock environment that simulates Docker container execution."""

    def __init__(self):
        self.files = {}
        self.commands_run = []

    def execute(self, command: str):
        """Simulate command execution."""
        self.commands_run.append(command)

        # Simulate file operations
        if command.startswith("cat "):
            file_path = command.split("cat ", 1)[1].strip().strip("'\"")
            if file_path in self.files:
                return self.files[file_path]
            return ""

        if command.startswith("python3 ") and command.endswith(".py"):
            # Simulate Python script execution for replace_in_file
            script_path = command.split("python3 ", 1)[1].strip()
            # In real implementation, this would execute the script
            # For testing, we'll simulate it
            return "Successfully replaced lines 1 to 1 (1 lines) in test.py"

        if command.startswith("git "):
            if "status" in command:
                return " M test.py"
            if "diff --cached" in command:
                return "diff --git a/test.py b/test.py\nindex 123..456\n--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,1 @@\n-old\n+new"
            if "diff" in command and "--cached" not in command:
                # Regular git diff (for show_diff)
                return "diff --git a/test.py b/test.py\nindex 123..456\n--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,1 @@\n-old\n+new"
            if "add" in command:
                return ""
            return ""

        if "pwd" in command:
            return "/testbed"

        if "grep" in command:
            return "test.py:10:def test_function():"

        if "find" in command:
            return "./test.py\n./test_file.py"

        if "pytest" in command:
            return "test.py::test_function PASSED"

        if "py_compile" in command:
            return ""

        return ""


class TestSWEEnvironment(unittest.TestCase):
    """Test suite for SWEEnvironment tools."""

    def setUp(self):
        """Set up test fixtures."""
        self.instance = {
            "repo": "test_repo",
            "base_commit": "abc123",
            "instance_id": "test__test-1"
        }
        self.mock_env = MockEnvironment()

        # Mock get_sb_environment to return our mock environment
        # We need to patch it before creating SWEEnvironment
        self.patcher = patch('envs.get_sb_environment', return_value=self.mock_env)
        self.patcher.start()

        # Create the environment wrapper
        self.env_wrapper = SWEEnvironment(self.instance)
        # Ensure the mock is set (in case patching didn't work)
        self.env_wrapper.env = self.mock_env

    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'patcher'):
            self.patcher.stop()

    def test_show_file(self):
        """Test show_file() reads file contents correctly."""
        # General-purpose test
        self.mock_env.files["test.py"] = "def hello():\n    pass\n"
        result = self.env_wrapper.show_file("test.py")
        self.assertIn("def hello", result)
        self.assertIn("pass", result)

        # Test from real instance: astropy-7166 (reading misc.py)
        self.mock_env.files["misc.py"] = "class InheritDocstrings(type):\n    pass\n"
        result = self.env_wrapper.show_file("misc.py")
        self.assertIn("InheritDocstrings", result)

    def test_replace_in_file_basic(self):
        """Test replace_in_file() with basic replacement."""
        # Create a temporary file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\nline2\nline3\n")
            temp_file = f.name

        try:
            # Mock the file reading and writing
            original_content = "line1\nline2\nline3\n"
            self.mock_env.files[temp_file] = original_content

            # Test replacing a single line
            result = self.env_wrapper.replace_in_file(temp_file, 2, 2, "new_line2\n")
            self.assertIn("Successfully replaced", result)

        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_replace_in_file_multiline(self):
        """Test replace_in_file() with multiline content."""
        # Based on real instance: sympy-17655 (adding Mul import and handling)
        content = """from sympy.core.mul import Mul
# allow expressions like scalar*Point (Mul), e.g. 2*Point(1,1)
if isinstance(other, Mul):
    # look for a Point argument inside the Mul
    pass
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("old content\n")
            temp_file = f.name

        try:
            self.mock_env.files[temp_file] = "old content\n"
            result = self.env_wrapper.replace_in_file(temp_file, 1, 1, content)
            self.assertIn("Successfully replaced", result)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_replace_in_file_edge_cases(self):
        """Test replace_in_file() with edge cases."""
        # Test replacing at file start
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\nline2\n")
            temp_file = f.name

        try:
            self.mock_env.files[temp_file] = "line1\nline2\n"
            result = self.env_wrapper.replace_in_file(temp_file, 1, 1, "new_start\n")
            self.assertIn("Successfully replaced", result)

            # Test replacing at file end
            result = self.env_wrapper.replace_in_file(temp_file, 2, 2, "new_end\n")
            self.assertIn("Successfully replaced", result)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_replace_in_file_fixes_bash_error(self):
        """Test that replace_in_file() uses temp file to avoid bash syntax errors.

        This test verifies the fix for the critical bug where repr() caused
        "bash: syntax error near unexpected token `)'" errors.
        """
        # The fix should use a temp file instead of repr() in command
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("test content\n")
            temp_file = f.name

        try:
            self.mock_env.files[temp_file] = "test content\n"

            # This should work without bash syntax errors
            # Content with special characters that would break with repr()
            special_content = "def func():\n    if x == 'test':\n        pass\n"
            result = self.env_wrapper.replace_in_file(temp_file, 1, 1, special_content)

            # Verify the command uses a temp file (not -c with repr)
            executed_commands = self.mock_env.commands_run
            python_commands = [c for c in executed_commands if "python3" in c]

            # Should use temp file approach (python3 /path/to/file.py)
            # NOT the broken approach (python3 -c '...')
            self.assertTrue(
                any("python3" in cmd and cmd.endswith(".py") and "-c" not in cmd
                    for cmd in python_commands),
                "replace_in_file should use temp file, not -c with repr()"
            )
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_grep(self):
        """Test grep() searches for patterns correctly."""
        # General-purpose test
        result = self.env_wrapper.grep("def test")
        self.assertIn("test.py", result)
        self.assertIn("test_function", result)

        # Test from real instance: finding test files
        result = self.env_wrapper.grep("test_inherit", "*.py")
        self.assertIn("test.py", result)

    def test_grep_case_insensitive(self):
        """Test grep() with case-insensitive search."""
        result = self.env_wrapper.grep("DEF TEST", case_sensitive=False)
        self.assertIn("test.py", result)

    def test_find_files(self):
        """Test find_files() locates files by pattern."""
        # General-purpose test
        result = self.env_wrapper.find_files("test_*.py")
        self.assertIn("test.py", result)
        self.assertIn("test_file.py", result)

        # Test from real instance: finding test files
        result = self.env_wrapper.find_files("*test*.py")
        self.assertIn("test", result)

    def test_find_files_directories(self):
        """Test find_files() can find directories."""
        result = self.env_wrapper.find_files("test*", file_type="d")
        # Mock returns files, but test structure is correct
        self.assertIsInstance(result, str)

    def test_run_test(self):
        """Test run_test() executes pytest correctly."""
        # General-purpose test
        result = self.env_wrapper.run_test("test.py")
        self.assertIn("PASSED", result)

        # Test from real instance: running specific test
        result = self.env_wrapper.run_test(test_name="test_inherit_docstrings")
        self.assertIn("test", result)

    def test_run_test_verbose(self):
        """Test run_test() with verbose output."""
        result = self.env_wrapper.run_test("test.py", verbose=True)
        self.assertIn("test", result)

    def test_check_syntax(self):
        """Test check_syntax() validates Python syntax."""
        # General-purpose test - valid syntax
        with patch.object(self.env_wrapper.env, 'execute', return_value=""):
            result = self.env_wrapper.check_syntax("test.py")
            self.assertEqual("Syntax OK", result)

        # Test - invalid syntax
        with patch.object(self.env_wrapper.env, 'execute',
                         return_value="SyntaxError: invalid syntax"):
            result = self.env_wrapper.check_syntax("test.py")
            self.assertIn("SyntaxError", result)

    def test_analyze_test_failure(self):
        """Test analyze_test_failure() extracts error information."""
        # General-purpose test
        failure_output = """
        test.py::test_function FAILED
        AssertionError: assert 1 == 2
        at test.py:10
        """
        result = self.env_wrapper.analyze_test_failure(failure_output)
        self.assertIn("AssertionError", result)
        self.assertIn("test.py", result)

    def test_find_test_file(self):
        """Test find_test_file() locates relevant test files."""
        # General-purpose test
        issue = "Test for inherit docstrings functionality"
        result = self.env_wrapper.find_test_file(issue)
        self.assertIsInstance(result, str)

    def test_show_diff(self):
        """Test show_diff() displays git diff."""
        # General-purpose test
        # Mock should return a git diff
        self.mock_env.execute = Mock(return_value="diff --git a/test.py b/test.py\nindex 123..456\n--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,1 @@\n-old\n+new")
        result = self.env_wrapper.show_diff("test.py")
        self.assertIn("diff --git", result)
        self.assertIn("test.py", result)

    def test_verify_changes(self):
        """Test verify_changes() detects modified files."""
        # General-purpose test
        result = self.env_wrapper.verify_changes()
        self.assertIn("test.py", result)

        # Test from real instance: verifying changes before finish
        # This is critical - agent should verify before finishing
        result = self.env_wrapper.verify_changes()
        self.assertIsInstance(result, str)

    def test_get_git_status(self):
        """Test get_git_status() returns git status."""
        # General-purpose test
        result = self.env_wrapper.get_git_status()
        self.assertIsInstance(result, str)

    def test_get_repo_info(self):
        """Test get_repo_info() returns repository information."""
        # General-purpose test
        # get_repo_info extracts repo name from instance_id (splits on "__")
        # For "test__test-1", it extracts "test"
        result = self.env_wrapper.get_repo_info()
        self.assertIn("Repository:", result)
        self.assertIn("Root directory:", result)
        # The repo name is extracted from instance_id, so "test" not "test_repo"
        self.assertIn("test", result)

    def test_generate_patch(self):
        """Test generate_patch() creates valid git diff."""
        # General-purpose test
        result = self.env_wrapper.generate_patch("test result")
        self.assertIn("diff --git", result)
        self.assertTrue(result.strip().startswith("diff --git"))

    def test_generate_patch_empty(self):
        """Test generate_patch() returns empty string when no changes."""
        # Test from real instance: empty patches should be valid empty strings
        # Mock git diff to return empty
        with patch.object(self.env_wrapper.env, 'execute',
                         side_effect=lambda cmd: "" if "diff" in cmd else " M test.py"):
            result = self.env_wrapper.generate_patch("no changes")
            # Should return empty string, not error text
            self.assertEqual("", result)

    def test_generate_patch_validates_format(self):
        """Test generate_patch() validates patch format.

        This test verifies the fix for the bug where invalid patches
        (text descriptions) were returned instead of empty strings.
        """
        # Test that invalid patch format returns empty string
        with patch.object(self.env_wrapper.env, 'execute',
                         side_effect=lambda cmd:
                         "No changes detected" if "diff" in cmd else ""):
            result = self.env_wrapper.generate_patch("test")
            # Should return empty string, not "No changes detected"
            self.assertEqual("", result)

    def test_run_bash_cmd(self):
        """Test run_bash_cmd() executes shell commands."""
        # General-purpose test
        result = self.env_wrapper.run_bash_cmd("echo test")
        self.assertIsInstance(result, str)

    def test_run_bash_cmd_error_handling(self):
        """Test run_bash_cmd() handles errors correctly."""
        # Test timeout handling
        with patch.object(self.env_wrapper.env, 'execute',
                         side_effect=subprocess.TimeoutExpired("cmd", 10)):
            with self.assertRaises(ValueError):
                self.env_wrapper.run_bash_cmd("slow_command")

    # Specialized tests based on real instances

    def test_replace_in_file_django_12406_scenario(self):
        """Test replace_in_file() handles the scenario from django-12406.

        This instance failed because replace_in_file() had bash syntax errors.
        The fix should allow this to work.
        """
        # Simulate the content that caused issues
        problematic_content = """from django.forms.widgets import (
    HiddenInput, MultipleHiddenInput, SelectMultiple, RadioSelect,
)
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("old import\n")
            temp_file = f.name

        try:
            self.mock_env.files[temp_file] = "old import\n"
            # This should work without bash errors
            result = self.env_wrapper.replace_in_file(temp_file, 1, 1, problematic_content)
            self.assertIn("Successfully replaced", result)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_verify_changes_before_finish(self):
        """Test that verify_changes() is used before finish (best practice).

        Based on successful instances like sympy-17655 and sympy-24213,
        which verified changes before finishing.
        """
        result = self.env_wrapper.verify_changes()
        # Should return status showing modified files
        self.assertIsInstance(result, str)
        # Agent should check this before calling finish()

    def test_run_test_specific_test(self):
        """Test running a specific test function.

        Based on successful pattern: agents should run the specific test
        mentioned in the issue before finishing.
        """
        result = self.env_wrapper.run_test(test_path="tests/test_misc.py",
                                          test_name="test_inherit_docstrings")
        self.assertIn("test", result)

    def test_check_syntax_after_edit(self):
        """Test checking syntax after making edits.

        Based on successful pattern: agents should verify syntax
        after making changes (e.g., django-14053, django-11179).
        """
        with patch.object(self.env_wrapper.env, 'execute', return_value=""):
            result = self.env_wrapper.check_syntax("modified_file.py")
            self.assertEqual("Syntax OK", result)

    # Tests for tool misuse and failure scenarios

    def test_replace_in_file_wrong_line_order(self):
        """Test replace_in_file() auto-corrects when to_line < from_line."""
        # Common agent mistake: swapping line numbers
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\nline2\nline3\n")
            temp_file = f.name

        try:
            self.mock_env.files[temp_file] = "line1\nline2\nline3\n"
            # Agent mistakenly passes to_line < from_line
            result = self.env_wrapper.replace_in_file(temp_file, 3, 1, "new content\n")
            # Should auto-correct and succeed
            self.assertIn("Successfully replaced", result)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_replace_in_file_normalizes_path(self):
        """Test replace_in_file() normalizes file paths (removes ./ prefix)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("test\n")
            temp_file = f.name

        try:
            self.mock_env.files[temp_file] = "test\n"
            # Agent adds ./ prefix (common mistake)
            result = self.env_wrapper.replace_in_file(f"./{temp_file}", 1, 1, "new\n")
            self.assertIn("Successfully replaced", result)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_show_file_normalizes_path(self):
        """Test show_file() normalizes file paths."""
        self.mock_env.files["test.py"] = "content"
        # Agent adds ./ prefix
        result = self.env_wrapper.show_file("./test.py")
        self.assertIn("content", result)

    def test_show_file_not_found_helpful_message(self):
        """Test show_file() provides helpful error when file not found."""
        with patch.object(self.env_wrapper.env, 'execute',
                         side_effect=ValueError("No such file")):
            result = self.env_wrapper.show_file("nonexistent.py")
            self.assertIn("not found", result)
            self.assertIn("find_files", result)

    def test_run_test_normalizes_path(self):
        """Test run_test() normalizes test paths."""
        # Agent might pass "./tests/test.py" or "tests/test.py.py"
        with patch.object(self.env_wrapper.env, 'execute', return_value="PASSED"):
            result = self.env_wrapper.run_test("./tests/test.py")
            self.assertIn("PASSED", result)

            # Test removing .py extension
            result = self.env_wrapper.run_test("tests/test.py")
            self.assertIn("PASSED", result)

    def test_run_test_verbose_string_input(self):
        """Test run_test() accepts string for verbose flag."""
        # Agent might pass "true" instead of True
        with patch.object(self.env_wrapper.env, 'execute', return_value="PASSED"):
            result = self.env_wrapper.run_test("test.py", verbose="true")
            self.assertIn("PASSED", result)

            result = self.env_wrapper.run_test("test.py", verbose="false")
            self.assertIn("PASSED", result)

    def test_check_syntax_normalizes_path(self):
        """Test check_syntax() normalizes file paths."""
        with patch.object(self.env_wrapper.env, 'execute', return_value=""):
            result = self.env_wrapper.check_syntax("./test.py")
            self.assertEqual("Syntax OK", result)

    def test_show_diff_no_file_shows_all(self):
        """Test show_diff() works without file_path to show all changes."""
        self.mock_env.execute = Mock(return_value="diff --git a/test.py b/test.py")
        result = self.env_wrapper.show_diff()
        self.assertIn("diff --git", result)

    def test_verify_changes_no_changes(self):
        """Test verify_changes() when no changes exist (common failure scenario)."""
        # This is a critical test - agent should check this before finishing
        with patch.object(self.env_wrapper.env, 'execute', return_value=""):
            result = self.env_wrapper.verify_changes()
            self.assertEqual("No changes detected", result)
            # Agent should NOT call finish() if this returns "No changes detected"

    def test_replace_in_file_invalid_line_numbers(self):
        """Test replace_in_file() handles invalid line number types."""
        # Agent might pass strings instead of ints
        with self.assertRaises(ValueError) as cm:
            self.env_wrapper.replace_in_file("test.py", "one", "two", "content")
        self.assertIn("integers", str(cm.exception).lower())

    def test_replace_in_file_negative_line_numbers(self):
        """Test replace_in_file() auto-corrects negative line numbers."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\n")
            temp_file = f.name

        try:
            self.mock_env.files[temp_file] = "line1\n"
            # Agent mistakenly passes negative line numbers
            result = self.env_wrapper.replace_in_file(temp_file, -1, 0, "new\n")
            # Should auto-correct to 1, 1
            self.assertIn("Successfully replaced", result)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_analyze_test_failure_various_errors(self):
        """Test analyze_test_failure() handles various error types."""
        # Test AssertionError
        failure1 = "test.py::test_func FAILED\nAssertionError: assert 1 == 2"
        result = self.env_wrapper.analyze_test_failure(failure1)
        self.assertIn("AssertionError", result)

        # Test ValueError
        failure2 = "test.py::test_func FAILED\nValueError: invalid value"
        result = self.env_wrapper.analyze_test_failure(failure2)
        self.assertIn("ValueError", result)

        # Test TypeError
        failure3 = "test.py::test_func FAILED\nTypeError: unsupported operand"
        result = self.env_wrapper.analyze_test_failure(failure3)
        self.assertIn("TypeError", result)

    def test_find_test_file_with_keywords(self):
        """Test find_test_file() matches keywords from issue description."""
        # Simulate finding test files
        self.mock_env.execute = Mock(return_value="./tests/test_inherit.py\n./tests/test_docstrings.py")
        result = self.env_wrapper.find_test_file("inherit docstrings functionality")
        self.assertIn("test_inherit", result)

    def test_generate_patch_no_changes_returns_empty(self):
        """Test generate_patch() returns empty string when no changes (not error text).

        This verifies the fix for the bug where invalid patches were returned.
        """
        with patch.object(self.env_wrapper.env, 'execute',
                         side_effect=lambda cmd: "" if "diff" in cmd else ""):
            result = self.env_wrapper.generate_patch("test")
            # Should return empty string, not error description
            self.assertEqual("", result)
            self.assertNotIn("No changes detected", result)

    def test_tool_tolerance_whitespace(self):
        """Test tools tolerate leading/trailing whitespace in paths."""
        self.mock_env.files["test.py"] = "content"

        # Test show_file with whitespace
        result = self.env_wrapper.show_file("  test.py  ")
        self.assertIn("content", result)

        # Test check_syntax with whitespace
        with patch.object(self.env_wrapper.env, 'execute', return_value=""):
            result = self.env_wrapper.check_syntax("  test.py  ")
            self.assertEqual("Syntax OK", result)


if __name__ == '__main__':
    unittest.main()

