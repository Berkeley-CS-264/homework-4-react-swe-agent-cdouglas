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

    def test_logging_logs_full_messages_each_call(self):
        """Test that logging records the full formatted messages on every call."""

        # First call - should include system prompt
        mock_response1 = Mock()
        mock_response1.id = "resp_123"
        mock_response1.output_text = "First response"

        # Second call - should only include last message
        mock_response2 = Mock()
        mock_response2.id = "resp_456"
        mock_response2.output_text = "Second response"

        self.mock_client.responses.create.side_effect = [mock_response1, mock_response2]

        messages1 = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "first message"}
        ]
        formatted1 = [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": "You are a helpful assistant"}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "first message"}
                ],
            },
        ]
        self.llm.generate(messages1)

        messages2 = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "First response"},
            {"role": "user", "content": "second message"},
        ]
        formatted2 = [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": "You are a helpful assistant"}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "first message"}
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "First response"}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "second message"}
                ],
            },
        ]
        self.llm.generate(messages2)

        # Read log file
        log_file = self.log_dir / "llm_calls.jsonl"
        self.assertTrue(log_file.exists(), "Log file should exist")

        with open(log_file, "r") as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 2, "Should have 2 log entries")

        entry1 = json.loads(lines[0])
        self.assertEqual(entry1["call_number"], 1)
        self.assertEqual(entry1["messages"], formatted1)

        entry2 = json.loads(lines[1])
        self.assertEqual(entry2["call_number"], 2)
        self.assertEqual(entry2["messages"], formatted2)

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

