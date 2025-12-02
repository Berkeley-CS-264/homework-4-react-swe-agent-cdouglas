"""
Tests for agent finish validation - ensuring agent cannot finish without edits and tests.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import os
import sys

# Mock dependencies before importing
sys.modules['minisweagent'] = MagicMock()
sys.modules['minisweagent.environments'] = MagicMock()
sys.modules['swebench'] = MagicMock()
sys.modules['utils'] = MagicMock()
sys.modules['openai'] = MagicMock()

mock_get_sb = MagicMock()
sys.modules['utils'].get_sb_environment = mock_get_sb

from agent import ReactAgent
from response_parser import ResponseParser
from llm import LLM


class MockLLM(LLM):
    """Mock LLM for testing."""

    def __init__(self):
        self.responses = []
        self.call_count = 0

    def generate(self, messages):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return "----BEGIN_FUNCTION_CALL----\nfinish\n----ARG----\nresult\n----VALUE----\nDone\n----END_FUNCTION_CALL----"

    def add_response(self, response):
        self.responses.append(response)


class MockEnvironment:
    """Mock environment for testing."""

    def execute(self, command):
        return ""


class TestAgentFinishValidation(unittest.TestCase):
    """Test that agent rejects finish when no edits or tests are made."""

    def setUp(self):
        """Set up test fixtures."""
        self.parser = ResponseParser()
        self.llm = MockLLM()
        self.agent = ReactAgent("test-agent", self.parser, self.llm)

        # Add mock functions that agents need
        def mock_replace_in_file(file_path, from_line, to_line, content):
            return f"Successfully replaced lines {from_line} to {to_line} in {file_path}"

        def mock_run_test(test_path=None, test_name=None, verbose=False):
            return "PASSED"

        def mock_grep(pattern, file_pattern="*", case_sensitive=True):
            return "No matches found"

        self.agent.add_functions([mock_replace_in_file, mock_run_test, mock_grep])

    def test_finish_rejected_when_no_edits(self):
        """Test that finish() is rejected when no edits have been made."""
        # Set up LLM to call finish immediately (without making edits)
        finish_call = (
            "I have completed the task.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "finish\n"
            "----ARG----\n"
            "result\n"
            "----VALUE----\n"
            "Fixed the issue\n"
            "----END_FUNCTION_CALL----"
        )
        self.llm.add_response(finish_call)

        # Add a second response that makes an edit (agent should continue after rejection)
        edit_response = (
            "I need to make changes first.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "replace_in_file\n"
            "----ARG----\n"
            "file_path\n"
            "----VALUE----\n"
            "test.py\n"
            "----ARG----\n"
            "from_line\n"
            "----VALUE----\n"
            "1\n"
            "----ARG----\n"
            "to_line\n"
            "----VALUE----\n"
            "1\n"
            "----ARG----\n"
            "content\n"
            "----VALUE----\n"
            "new code\n"
            "----END_FUNCTION_CALL----"
        )
        self.llm.add_response(edit_response)

        # Run agent with max_steps=2
        result = self.agent.run("Test task", max_steps=2)

        # Agent should not have finished (should continue loop after rejection)
        # Since we only have 2 steps and first finish is rejected, it should continue
        # The result should be "Max steps reached"
        self.assertIn("Max steps reached", result)

    def test_finish_rejected_when_no_tests_after_edit(self):
        """Test that finish() is rejected when tests haven't been run after edit."""
        # Set up LLM to: make edit, then try to finish (without running tests)
        edit_call = (
            "I'll make a change.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "replace_in_file\n"
            "----ARG----\n"
            "file_path\n"
            "----VALUE----\n"
            "test.py\n"
            "----ARG----\n"
            "from_line\n"
            "----VALUE----\n"
            "1\n"
            "----ARG----\n"
            "to_line\n"
            "----VALUE----\n"
            "1\n"
            "----ARG----\n"
            "content\n"
            "----VALUE----\n"
            "new code\n"
            "----END_FUNCTION_CALL----"
        )
        self.llm.add_response(edit_call)

        finish_call = (
            "Now I'll finish.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "finish\n"
            "----ARG----\n"
            "result\n"
            "----VALUE----\n"
            "Fixed the issue\n"
            "----END_FUNCTION_CALL----"
        )
        self.llm.add_response(finish_call)

        # Run agent with max_steps=2
        result = self.agent.run("Test task", max_steps=2)

        # Agent should not have finished (should continue loop after rejection)
        self.assertIn("Max steps reached", result)

    def test_finish_allowed_when_edit_and_test_done(self):
        """Test that finish() is allowed when edit and test are done."""
        # Create new LLM instance for this test to avoid state issues
        llm2 = MockLLM()
        agent2 = ReactAgent("test-agent-2", self.parser, llm2)

        # Add mock functions
        def mock_replace_in_file(file_path, from_line, to_line, content):
            return f"Successfully replaced lines {from_line} to {to_line} in {file_path}"

        test_outputs = ["FAILED", "PASSED"]

        def mock_run_test(test_path=None, test_name=None, verbose=False):
            return test_outputs.pop(0) if test_outputs else "PASSED"

        agent2.add_functions([mock_replace_in_file, mock_run_test])

        # Set up LLM to: reproduce failure, make edit, rerun tests, then finish
        reproduce_call = (
            "I'll reproduce the failure first.\n",
            "----BEGIN_FUNCTION_CALL----\n",
            "run_test\n",
            "----ARG----\n",
            "test_path\n",
            "----VALUE----\n",
            "test.py\n",
            "----END_FUNCTION_CALL----",
        )
        edit_call = (
            "I'll make a change.\n",
            "----BEGIN_FUNCTION_CALL----\n",
            "replace_in_file\n",
            "----ARG----\n",
            "file_path\n",
            "----VALUE----\n",
            "test.py\n",
            "----ARG----\n",
            "from_line\n",
            "----VALUE----\n",
            "1\n",
            "----ARG----\n",
            "to_line\n",
            "----VALUE----\n",
            "1\n",
            "----ARG----\n",
            "content\n",
            "----VALUE----\n",
            "new code\n",
            "----END_FUNCTION_CALL----",
        )
        test_call = (
            "Now I'll rerun tests.\n",
            "----BEGIN_FUNCTION_CALL----\n",
            "run_test\n",
            "----ARG----\n",
            "test_path\n",
            "----VALUE----\n",
            "test.py\n",
            "----END_FUNCTION_CALL----",
        )

        finish_call = (
            "Tests passed, I'll finish.\n",
            "----BEGIN_FUNCTION_CALL----\n",
            "finish\n",
            "----ARG----\n",
            "result\n",
            "----VALUE----\n",
            "Fixed the issue\n",
            "----END_FUNCTION_CALL----",
        )
        # Set LLM responses for this test
        llm2.responses = [reproduce_call, edit_call, test_call, finish_call]
        llm2.call_count = 0

        # Run agent (need enough steps for failure reproduction, edit, retest, and finish)
        result = agent2.run("Test task", max_steps=6)

        # Should finish successfully after passing test
        self.assertEqual(result, "Fixed the issue")

    def test_max_steps_reached_without_changes(self):
        """Test that when max_steps is reached without edits, agent returns appropriate message."""
        # Create agent
        agent3 = ReactAgent("test-agent-3", self.parser, self.llm)

        # Add mock functions
        def mock_grep(pattern, file_pattern="*", case_sensitive=True):
            return "No matches found"

        agent3.add_functions([mock_grep])

        # Set up LLM to never make edits (simulating max_steps scenario)
        non_edit_response = (
            "I need to understand the problem better.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "grep\n"
            "----ARG----\n"
            "pattern\n"
            "----VALUE----\n"
            "test\n"
            "----END_FUNCTION_CALL----"
        )
        # Add many responses so we hit max_steps
        for _ in range(5):
            self.llm.responses.append(non_edit_response)
        self.llm.call_count = 0

        # Run agent with max_steps=5
        result = agent3.run("Test task", max_steps=5)

        # Should return message indicating max_steps reached
        self.assertIn("Max steps reached", result)

    def test_max_steps_reached_with_changes(self):
        """Test that when max_steps is reached with edits and tests, agent finishes normally."""
        # Create agent
        agent4 = ReactAgent("test-agent-4", self.parser, self.llm)

        # Add mock functions
        def mock_replace_in_file(file_path, from_line, to_line, content):
            return f"Successfully replaced lines {from_line} to {to_line} in {file_path}"

        def mock_run_test(test_path=None, test_name=None, verbose=False):
            return "PASSED"

        def mock_grep(pattern, file_pattern="*", case_sensitive=True):
            return "No matches found"

        agent4.add_functions([mock_replace_in_file, mock_run_test, mock_grep])

        # Set up LLM to make edit and run test, then hit max_steps
        edit_call = (
            "I'll make a change.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "replace_in_file\n"
            "----ARG----\n"
            "file_path\n"
            "----VALUE----\n"
            "test.py\n"
            "----ARG----\n"
            "from_line\n"
            "----VALUE----\n"
            "1\n"
            "----ARG----\n"
            "to_line\n"
            "----VALUE----\n"
            "1\n"
            "----ARG----\n"
            "content\n"
            "----VALUE----\n"
            "new code\n"
            "----END_FUNCTION_CALL----"
        )
        test_call = (
            "Now I'll run tests.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "run_test\n"
            "----ARG----\n"
            "test_path\n"
            "----VALUE----\n"
            "test.py\n"
            "----END_FUNCTION_CALL----"
        )
        # Add edit, test, then more non-finish calls
        self.llm.responses = [edit_call, test_call]
        for _ in range(3):
            self.llm.responses.append((
                "Still working.\n"
                "----BEGIN_FUNCTION_CALL----\n"
                "grep\n"
                "----ARG----\n"
                "pattern\n"
                "----VALUE----\n"
                "test\n"
                "----END_FUNCTION_CALL----"
            ))
        self.llm.call_count = 0

        # Run agent with max_steps=5
        result = agent4.run("Test task", max_steps=5)

        # Should return message indicating max_steps reached
        self.assertIn("Max steps reached", result)


if __name__ == '__main__':
    unittest.main()

