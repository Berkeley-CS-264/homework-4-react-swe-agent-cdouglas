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
    Example LLM implementation using OpenAI's Responses API.

    TODO(student): Implement this class to call your chosen backend (e.g., OpenAI GPT-5 mini)
    and return the model's text output. You should ensure the model produces the response
    format required by ResponseParser and include the stop token in the output string.
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
        Call the OpenAI API with the given messages and return the response text.
        
        Args:
            messages: List of message dictionaries with "role" and "content" keys
            
        Returns:
            The text response from the model including the stop token
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.3,
                max_completion_tokens=4096,
            )
            
            text = response.choices[0].message.content

            # split from the first stop token (including the stop token)
            text = text.split(self.stop_token)[0].strip() + "\n" + self.stop_token
            
            # Log the LLM call if log_dir is set
            if self.log_dir:
                self._log_call(messages, text, success=True)
            
            return text
            
        except Exception as e:
            # Log the failed call if log_dir is set
            if self.log_dir:
                self._log_call(messages, None, success=False, error=str(e))
            
            # Re-raise the exception with more context
            raise RuntimeError(f"OpenAI API call failed: {type(e).__name__}: {str(e)}") from e
    
    def _log_call(self, messages: list, response: str = None, success: bool = True, error: str = None) -> None:
        """
        Log an LLM generation call to a file in the log directory.
        
        Args:
            messages: The input messages
            response: The generated response (None if call failed)
            success: Whether the API call was successful
            error: Error message if the call failed
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
            "response": response
        }
        
        # Add error information if the call failed
        if not success and error:
            log_entry["error"] = error
        
        # Write to log file (append mode)
        log_file = self.log_dir / "llm_calls.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")