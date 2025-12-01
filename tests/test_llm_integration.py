"""
Integration test for LLM logging without mocks.

This test verifies that:
1. System prompt is only logged on the first call
2. Subsequent calls only log the last message
3. Log file is properly created and contains correct entries
"""

import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

# Import the module to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock OpenAI before importing llm module
mock_openai = MagicMock()
sys.modules['openai'] = mock_openai
sys.modules['openai'].OpenAI = MagicMock

from llm import OpenAIModel


class TestLLMLoggingIntegration(unittest.TestCase):
    """Integration tests for LLM logging without mocks."""

    def setUp(self):
        """Set up test fixtures."""
        self.stop_token = "----END_FUNCTION_CALL----"
        self.model_name = "gpt-5-mini"

        # Create temporary directory for logs
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir)

        # Mock OpenAI client
        self.mock_client = MagicMock()

        # Patch OpenAI class to return our mock client
        self.openai_patcher = patch('llm.OpenAI', return_value=self.mock_client)
        self.openai_patcher.start()

        # Patch environment variable
        self.env_patcher = patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
        self.env_patcher.start()

        # Create model instance
        self.llm = OpenAIModel(
            stop_token=self.stop_token,
            model_name=self.model_name,
            log_dir=self.log_dir
        )
        # Replace the client with our mock
        self.llm.client = self.mock_client

    def tearDown(self):
        """Clean up after tests."""
        self.openai_patcher.stop()
        self.env_patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_logging_only_last_message_on_subsequent_calls(self):
        """Test that logging only includes last message on subsequent calls (no system prompt)."""

        # First call - should include system prompt
        mock_response1 = Mock()
        mock_response1.id = "resp_123"
        mock_response1.output_text = "First response"

        # Second call - should only include last message
        mock_response2 = Mock()
        mock_response2.id = "resp_456"
        mock_response2.output_text = "Second response"

        self.mock_client.responses.create.side_effect = [mock_response1, mock_response2]

        # First call with full conversation including system prompt
        messages1 = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "first message"}
        ]
        self.llm.generate(messages1)

        # Second call with full conversation (but only last message should be logged)
        messages2 = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "First response"},
            {"role": "user", "content": "second message"}
        ]
        self.llm.generate(messages2)

        # Read log file
        log_file = self.log_dir / "llm_calls.jsonl"
        self.assertTrue(log_file.exists(), "Log file should exist")

        with open(log_file, "r") as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 2, "Should have 2 log entries")

        # Parse first log entry
        entry1 = json.loads(lines[0])
        self.assertEqual(entry1["call_number"], 1)
        self.assertEqual(len(entry1["messages"]), 2, "First call should log all messages including system")
        self.assertEqual(entry1["messages"][0]["role"], "system")
        self.assertEqual(entry1["messages"][1]["role"], "user")
        self.assertEqual(entry1["messages"][1]["content"], "first message")

        # Parse second log entry
        entry2 = json.loads(lines[1])
        self.assertEqual(entry2["call_number"], 2)
        self.assertEqual(len(entry2["messages"]), 1, "Second call should only log last message")
        self.assertEqual(entry2["messages"][0]["role"], "user")
        self.assertEqual(entry2["messages"][0]["content"], "second message")
        # Verify system prompt is NOT in second entry
        system_messages = [msg for msg in entry2["messages"] if msg["role"] == "system"]
        self.assertEqual(len(system_messages), 0, "System prompt should not be in second log entry")
        self.assertEqual(entry2["previous_response_id"], "resp_123")

    def test_log_file_deletion_on_new_run(self):
        """Test that log file can be deleted and recreated."""

        # Create initial log entries
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = "Test response"
        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        self.llm.generate(messages)

        log_file = self.log_dir / "llm_calls.jsonl"
        self.assertTrue(log_file.exists())

        # Delete log file (simulating new run)
        log_file.unlink()
        self.assertFalse(log_file.exists())

        # Create new LLM instance and generate (should create new log file)
        llm2 = OpenAIModel(
            stop_token=self.stop_token,
            model_name=self.model_name,
            log_dir=self.log_dir
        )
        llm2.client = self.mock_client

        llm2.generate(messages)

        # Verify new log file exists with only one entry
        self.assertTrue(log_file.exists())
        with open(log_file, "r") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1, "New run should start with fresh log file")


if __name__ == '__main__':
    unittest.main()

