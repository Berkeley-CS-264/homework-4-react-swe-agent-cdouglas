"""
Unit tests for LLM implementation.

Tests cover:
- Stop token presence in responses
- Previous response ID chaining across multiple calls
- Text extraction from Responses API format
- Error handling
- Logging functionality
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import json
from pathlib import Path

# Import the module to test
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock OpenAI before importing llm module
mock_openai = MagicMock()
sys.modules['openai'] = mock_openai
sys.modules['openai'].OpenAI = MagicMock

from llm import OpenAIModel


class TestOpenAIModel(unittest.TestCase):
    """Test suite for OpenAIModel class."""

    def setUp(self):
        """Set up test fixtures."""
        self.stop_token = "----END_FUNCTION_CALL----"
        self.model_name = "gpt-5-mini"

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
            model_name=self.model_name
        )
        # Replace the client with our mock
        self.llm.client = self.mock_client

    def tearDown(self):
        """Clean up after tests."""
        self.openai_patcher.stop()
        self.env_patcher.stop()

    def test_stop_token_present_in_response(self):
        """Test that stop token is always present in the response."""
        # Mock response with output_text
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = "This is a test response"
        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        result = self.llm.generate(messages)

        # Verify stop token is present
        self.assertIn(self.stop_token, result)
        self.assertTrue(result.endswith(self.stop_token))

        # Verify the text before stop token is correct
        text_before_stop = result.replace(f"\n{self.stop_token}", "")
        self.assertIn("This is a test response", text_before_stop)

    def test_stop_token_with_existing_stop_token(self):
        """Test that stop token handling works when response already contains stop token."""
        # Mock response that already contains stop token
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = f"Response text {self.stop_token} extra text"
        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        result = self.llm.generate(messages)

        # Should only have one stop token at the end
        self.assertTrue(result.endswith(f"\n{self.stop_token}"))
        # Should not have the extra text after the stop token
        self.assertNotIn("extra text", result)
        # Should have the text before the stop token
        self.assertIn("Response text", result)

    def test_previous_response_id_initial_call(self):
        """Test that previous_response_id is None on first call."""
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = "First response"
        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "first"}]
        self.llm.generate(messages)

        # Verify previous_response_id was None on first call
        call_args = self.mock_client.responses.create.call_args
        self.assertIsNone(call_args.kwargs.get("previous_response_id"))

        # Verify it was set after the call
        self.assertEqual(self.llm.prev_response_id, "resp_123")

    def test_previous_response_id_chaining(self):
        """Test that previous_response_id is correctly chained across multiple calls."""
        # First call
        mock_response1 = Mock()
        mock_response1.id = "resp_123"
        mock_response1.output_text = "First response"

        # Second call
        mock_response2 = Mock()
        mock_response2.id = "resp_456"
        mock_response2.output_text = "Second response"

        # Set up side effect to return different responses
        self.mock_client.responses.create.side_effect = [mock_response1, mock_response2]

        messages1 = [{"role": "user", "content": "first"}]
        result1 = self.llm.generate(messages1)

        # Verify first call had None as previous_response_id
        first_call = self.mock_client.responses.create.call_args_list[0]
        self.assertIsNone(first_call.kwargs.get("previous_response_id"))
        self.assertEqual(self.llm.prev_response_id, "resp_123")

        # Second call
        messages2 = [{"role": "user", "content": "second"}]
        result2 = self.llm.generate(messages2)

        # Verify second call used the first response's ID
        second_call = self.mock_client.responses.create.call_args_list[1]
        self.assertEqual(second_call.kwargs.get("previous_response_id"), "resp_123")
        self.assertEqual(self.llm.prev_response_id, "resp_456")

        # Verify both responses have stop tokens
        self.assertIn(self.stop_token, result1)
        self.assertIn(self.stop_token, result2)

    def test_previous_response_id_multiple_calls(self):
        """Test previous_response_id chaining across three or more calls."""
        responses = []
        for i in range(3):
            mock_response = Mock()
            mock_response.id = f"resp_{i+1}"
            mock_response.output_text = f"Response {i+1}"
            responses.append(mock_response)

        self.mock_client.responses.create.side_effect = responses

        # Make three calls
        for i in range(3):
            messages = [{"role": "user", "content": f"message {i+1}"}]
            self.llm.generate(messages)

        # Verify chaining
        calls = self.mock_client.responses.create.call_args_list
        self.assertIsNone(calls[0].kwargs.get("previous_response_id"))
        self.assertEqual(calls[1].kwargs.get("previous_response_id"), "resp_1")
        self.assertEqual(calls[2].kwargs.get("previous_response_id"), "resp_2")

        # Verify final previous_response_id
        self.assertEqual(self.llm.prev_response_id, "resp_3")

    def test_text_extraction_from_output_text(self):
        """Test text extraction when output_text is available."""
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = "Direct output text"
        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        result = self.llm.generate(messages)

        self.assertIn("Direct output text", result)
        self.assertIn(self.stop_token, result)

    def test_text_extraction_from_output_structure(self):
        """Test text extraction from nested output structure when output_text is None."""
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = None  # Not available

        # Create nested structure with Mock objects
        mock_content = Mock()
        mock_content.text = "Extracted from structure"
        mock_output_message = Mock()
        mock_output_message.content = [mock_content]
        mock_response.output = [mock_output_message]

        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        result = self.llm.generate(messages)

        self.assertIn("Extracted from structure", result)
        self.assertIn(self.stop_token, result)

    def test_text_extraction_from_dict_structure(self):
        """Test text extraction when output structure uses dict format."""
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = None

        # Use dict format
        mock_response.output = [{
            "content": [{"text": "Text from dict"}]
        }]

        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        result = self.llm.generate(messages)

        self.assertIn("Text from dict", result)
        self.assertIn(self.stop_token, result)

    def test_text_extraction_multiple_content_items(self):
        """Test text extraction when there are multiple content items."""
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = None

        mock_response.output = [{
            "content": [
                {"text": "First part"},
                {"text": "Second part"}
            ]
        }]

        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        result = self.llm.generate(messages)

        # Should join multiple parts with \n\n
        self.assertIn("First part", result)
        self.assertIn("Second part", result)
        self.assertIn(self.stop_token, result)

    def test_empty_response_error(self):
        """Test that empty response raises appropriate error."""
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = ""
        mock_response.output = []

        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]

        with self.assertRaises(RuntimeError) as cm:
            self.llm.generate(messages)

        self.assertIn("Empty response", str(cm.exception))

    def test_api_call_error_handling(self):
        """Test that API errors are properly handled and re-raised."""
        self.mock_client.responses.create.side_effect = Exception("API Error")

        messages = [{"role": "user", "content": "test"}]

        with self.assertRaises(RuntimeError) as cm:
            self.llm.generate(messages)

        self.assertIn("OpenAI API call failed", str(cm.exception))
        self.assertIn("API Error", str(cm.exception))

    def test_logging_on_success(self):
        """Test that successful calls are logged when log_dir is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            llm = OpenAIModel(
                stop_token=self.stop_token,
                model_name=self.model_name,
                log_dir=log_dir
            )
            llm.client = self.mock_client

            mock_response = Mock()
            mock_response.id = "resp_123"
            mock_response.output_text = "Test response"
            self.mock_client.responses.create.return_value = mock_response

            messages = [{"role": "user", "content": "test"}]
            llm.generate(messages)

            # Check log file was created
            log_file = log_dir / "llm_calls.jsonl"
            self.assertTrue(log_file.exists())

            # Check log content
            with open(log_file, "r") as f:
                log_entry = json.loads(f.readline())

            self.assertEqual(log_entry["call_number"], 1)
            self.assertEqual(log_entry["model"], self.model_name)
            self.assertTrue(log_entry["success"])
            self.assertEqual(log_entry["messages"], messages)
            self.assertIn(self.stop_token, log_entry["response"])

    def test_logging_on_failure(self):
        """Test that failed calls are logged when log_dir is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            llm = OpenAIModel(
                stop_token=self.stop_token,
                model_name=self.model_name,
                log_dir=log_dir
            )
            llm.client = self.mock_client

            self.mock_client.responses.create.side_effect = Exception("API Error")

            messages = [{"role": "user", "content": "test"}]

            with self.assertRaises(RuntimeError):
                llm.generate(messages)

            # Check log file was created
            log_file = log_dir / "llm_calls.jsonl"
            self.assertTrue(log_file.exists())

            # Check log content
            with open(log_file, "r") as f:
                log_entry = json.loads(f.readline())

            self.assertFalse(log_entry["success"])
            self.assertIn("error", log_entry)
            self.assertEqual(log_entry["error"], "API Error")

    def test_logging_multiple_calls(self):
        """Test that multiple calls are logged with correct call numbers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            llm = OpenAIModel(
                stop_token=self.stop_token,
                model_name=self.model_name,
                log_dir=log_dir
            )
            llm.client = self.mock_client

            mock_response = Mock()
            mock_response.id = "resp_123"
            mock_response.output_text = "Test response"
            self.mock_client.responses.create.return_value = mock_response

            messages = [{"role": "user", "content": "test"}]

            # Make three calls
            for _ in range(3):
                llm.generate(messages)

            # Check log file
            log_file = log_dir / "llm_calls.jsonl"
            self.assertTrue(log_file.exists())

            # Check all entries
            with open(log_file, "r") as f:
                lines = f.readlines()

            self.assertEqual(len(lines), 3)
            for i, line in enumerate(lines, 1):
                log_entry = json.loads(line)
                self.assertEqual(log_entry["call_number"], i)

    def test_no_logging_when_log_dir_not_set(self):
        """Test that no logging occurs when log_dir is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            mock_response = Mock()
            mock_response.id = "resp_123"
            mock_response.output_text = "Test response"
            self.mock_client.responses.create.return_value = mock_response

            messages = [{"role": "user", "content": "test"}]
            self.llm.generate(messages)

            # Check no log file was created
            log_file = log_dir / "llm_calls.jsonl"
            self.assertFalse(log_file.exists())

    def test_api_call_parameters(self):
        """Test that API is called with correct parameters."""
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = "Test response"
        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test message"}]
        self.llm.generate(messages)

        # Verify API was called with correct parameters
        self.mock_client.responses.create.assert_called_once_with(
            model=self.model_name,
            input=messages,
            previous_response_id=None,
            max_completion_tokens=4096
        )

    def test_api_call_with_previous_response_id(self):
        """Test that API is called with previous_response_id on subsequent calls."""
        # First call
        mock_response1 = Mock()
        mock_response1.id = "resp_123"
        mock_response1.output_text = "First"

        # Second call
        mock_response2 = Mock()
        mock_response2.id = "resp_456"
        mock_response2.output_text = "Second"

        self.mock_client.responses.create.side_effect = [mock_response1, mock_response2]

        messages = [{"role": "user", "content": "test"}]
        self.llm.generate(messages)
        self.llm.generate(messages)

        # Verify second call used previous_response_id
        calls = self.mock_client.responses.create.call_args_list
        self.assertEqual(calls[1].kwargs["previous_response_id"], "resp_123")

    def test_stop_token_handling_with_whitespace(self):
        """Test stop token handling with various whitespace scenarios."""
        mock_response = Mock()
        mock_response.id = "resp_123"
        mock_response.output_text = "Response with   whitespace   "
        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        result = self.llm.generate(messages)

        # Should still have stop token
        self.assertIn(self.stop_token, result)
        # Whitespace should be stripped before stop token
        self.assertTrue(result.endswith(f"\n{self.stop_token}"))

    def test_response_id_none_handling(self):
        """Test handling when response ID is None."""
        mock_response = Mock()
        mock_response.id = None
        mock_response.output_text = "Response without ID"
        self.mock_client.responses.create.return_value = mock_response

        messages = [{"role": "user", "content": "test"}]
        result = self.llm.generate(messages)

        # Should still work
        self.assertIn("Response without ID", result)
        self.assertIn(self.stop_token, result)
        # previous_response_id should be None
        self.assertIsNone(self.llm.prev_response_id)

        # Next call should still work with None
        mock_response2 = Mock()
        mock_response2.id = "resp_456"
        mock_response2.output_text = "Second response"
        self.mock_client.responses.create.return_value = mock_response2

        result2 = self.llm.generate(messages)
        # Should have called with None as previous_response_id
        calls = self.mock_client.responses.create.call_args_list
        self.assertIsNone(calls[-1].kwargs.get("previous_response_id"))


if __name__ == '__main__':
    unittest.main()

