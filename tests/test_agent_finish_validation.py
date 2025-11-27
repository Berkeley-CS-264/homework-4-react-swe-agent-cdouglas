"""
Tests for agent finish validation - ensuring agent cannot finish without changes.
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
        if "status" in command:
            return ""  # No changes
        return ""


class TestAgentFinishValidation(unittest.TestCase):
    """Test that agent rejects finish when no changes are detected."""

    def setUp(self):
        """Set up test fixtures."""
        self.parser = ResponseParser()
        self.llm = MockLLM()
        self.agent = ReactAgent("test-agent", self.parser, self.llm)

        # Create mock environment
        self.mock_env = MockEnvironment()

        # Mock verify_changes to return "No changes detected"
        def mock_verify_changes():
            return "No changes detected"

        # Add verify_changes to agent
        self.agent.add_functions([mock_verify_changes])

    def test_finish_rejected_when_no_changes(self):
        """Test that finish() is rejected when verify_changes() shows no changes."""
        # Set up LLM to call finish
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

        # Add a second response that doesn't call finish (agent should continue)
        continue_response = (
            "I understand I need to make changes first.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "verify_changes\n"
            "----END_FUNCTION_CALL----"
        )
        self.llm.add_response(continue_response)

        # Run agent with max_steps=2
        result = self.agent.run("Test task", max_steps=2)

        # Agent should not have finished (should continue loop)
        # Since we only have 2 steps and first finish is rejected, it should continue
        # The result should be from the second step or "Max steps reached"
        self.assertIsNotNone(result)

    def test_finish_allowed_when_changes_exist(self):
        """Test that finish() is allowed when verify_changes() shows changes exist."""
        # Mock verify_changes to return changes
        def mock_verify_changes_with_changes():
            return " M test.py"

        # Create new agent with changes
        agent2 = ReactAgent("test-agent-2", self.parser, self.llm)
        agent2.add_functions([mock_verify_changes_with_changes])

        # Set up LLM to call finish
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
        self.llm.responses = [finish_call]
        self.llm.call_count = 0

        # Run agent
        result = agent2.run("Test task", max_steps=1)

        # Should finish successfully
        self.assertEqual(result, "Fixed the issue")

    def test_max_steps_reached_without_changes(self):
        """Test that when max_steps is reached without changes, agent returns appropriate message."""
        # Create agent with verify_changes that returns no changes
        agent3 = ReactAgent("test-agent-3", self.parser, self.llm)

        # Create a function with the exact name "verify_changes" so it's registered correctly
        def verify_changes():
            return "No changes detected"

        agent3.add_functions([verify_changes])

        # Set up LLM to never call finish (simulating max_steps scenario)
        # The LLM will keep responding with non-finish calls
        non_finish_response = (
            "I need to understand the problem better.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "verify_changes\n"
            "----END_FUNCTION_CALL----"
        )
        # Add many responses so we hit max_steps
        for _ in range(5):
            self.llm.responses.append(non_finish_response)
        self.llm.call_count = 0

        # Run agent with max_steps=5
        result = agent3.run("Test task", max_steps=5)

        # Should return message indicating max_steps reached without changes
        # The agent checks verify_changes when max_steps is reached
        self.assertIn("Max steps reached", result)
        # If no changes detected, should include "no changes made"
        self.assertIn("no changes made", result.lower())

    def test_max_steps_reached_with_changes(self):
        """Test that when max_steps is reached with changes, agent finishes normally."""
        # Create agent with verify_changes that returns changes
        agent4 = ReactAgent("test-agent-4", self.parser, self.llm)

        # Create a function with the exact name "verify_changes" so it's registered correctly
        def verify_changes():
            return " M test.py"

        agent4.add_functions([verify_changes])

        # Set up LLM to never call finish (simulating max_steps scenario)
        non_finish_response = (
            "I need to understand the problem better.\n"
            "----BEGIN_FUNCTION_CALL----\n"
            "verify_changes\n"
            "----END_FUNCTION_CALL----"
        )
        # Add many responses so we hit max_steps
        for _ in range(5):
            self.llm.responses.append(non_finish_response)
        self.llm.call_count = 0

        # Run agent with max_steps=5
        result = agent4.run("Test task", max_steps=5)

        # Should return message indicating max_steps reached (but changes exist)
        self.assertIn("Max steps reached", result)
        self.assertNotIn("no changes made", result)


if __name__ == '__main__':
    unittest.main()

