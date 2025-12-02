from abc import ABC, abstractmethod
from openai import OpenAI
import os
import json
from pathlib import Path
from datetime import datetime


class LLM(ABC):
    """Abstract base class for Large Language Models."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """
        Generate a response from the LLM given a prompt.
        Must include any required stop-token logic at the caller level.
        """
        raise NotImplementedError


class OpenAIModel(LLM):
    """
    LLM implementation using OpenAI's Responses API.

    This implementation uses the Responses API which is designed for GPT-5 models
    and supports extended reasoning capabilities. The Responses API does not support
    temperature parameters.
    """

    def __init__(self, stop_token: str, model_name: str = "gpt-5-mini", log_dir: Path = None):
        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.client = OpenAI(api_key=api_key)
        self.stop_token = stop_token
        self.model_name = model_name
        self.log_dir = log_dir
        self.call_count = 0

    def generate(self, messages: list) -> str:
        """
        Call the OpenAI Responses API with the given messages and return the response text.
        
        Args:
            messages: List of message dictionaries with "role" and "content" keys

        Returns:
            The text response from the model including the stop token
        """
        formatted_messages = [
            {
                "role": m["role"],
                "content": [
                    {"type": "output_text", "text": m["content"]}
                ],
            }
            for m in messages
        ]

        try:
            # Use Responses API for GPT-5 models (does not support temperature)
            response = self.client.responses.create(
                model=self.model_name,
                input=formatted_messages,
                max_output_tokens=4096,
            )

            # Extract text from Responses API format using the same logic as mini-swe-agent
            # Try output_text first (most common case)
            text = getattr(response, "output_text", None)
            if isinstance(text, str) and text:
                pass  # Use output_text
            else:
                # Fallback: extract from output structure
                try:
                    output_items = getattr(response, "output", [])
                    text_parts = []
                    for item in output_items:
                        if isinstance(item, dict):
                            content = item.get("content", [])
                        else:
                            # Handle ResponseOutputMessage objects
                            content = getattr(item, "content", [])

                        for content_item in content:
                            if isinstance(content_item, dict):
                                text_val = content_item.get("text")
                            elif hasattr(content_item, "text"):
                                text_val = content_item.text
                            else:
                                continue

                            if text_val:
                                text_parts.append(text_val)

                    text = "\n\n".join(text_parts) if text_parts else ""
                except (AttributeError, IndexError, TypeError) as e:
                    raise RuntimeError(f"Could not extract text from Responses API response: {e}")

            if not text:
                raise RuntimeError("Empty response from OpenAI Responses API")

            # split from the first stop token (including the stop token)
            text = text.split(self.stop_token)[0].strip() + "\n" + self.stop_token
            
            # Log the LLM call if log_dir is set
            # Log formatted_messages (what was actually sent) not messages (what agent passed in)
            if self.log_dir:
                response_id = getattr(response, "id", None)
                self._log_call(formatted_messages, text, success=True, response_id=response_id)
            
            return text
            
        except Exception as e:
            # Log the failed call if log_dir is set
            # Log formatted_messages (what was actually sent) not messages (what agent passed in)
            # No response_id available on failure
            if self.log_dir:
                self._log_call(formatted_messages, None, success=False, error=str(e), response_id=None)
            
            # Re-raise the exception with more context
            raise RuntimeError(f"OpenAI API call failed: {type(e).__name__}: {str(e)}") from e
    
    def _log_call(self, messages: list, response: str = None, success: bool = True, error: str = None, response_id: str = None) -> None:
        """
        Log an LLM generation call to a file in the log directory.
        
        Args:
            messages: The input messages that were actually sent to the API
            response: The generated response (None if call failed)
            success: Whether the API call was successful
            error: Error message if the call failed
            response_id: The response ID returned by the API
        """
        if not self.log_dir:
            return
        
        # Create log directory if it doesn't exist
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Increment call count
        self.call_count += 1
        
        # Create log entry
        log_entry = {
            "call_number": self.call_count,
            "timestamp": datetime.now().isoformat(),
            "model": self.model_name,
            "success": success,
            "messages": messages,
            "response": response,
            "response_id": response_id
        }
        
        # Add error information if the call failed
        if not success and error:
            log_entry["error"] = error
        
        # Write to log file (append mode)
        log_file = self.log_dir / "llm_calls.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
