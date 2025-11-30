"""
Starter scaffold for the CS 294-264 HW1 ReAct agent.

Students must implement a minimal ReAct agent that:
- Maintains a message history list (role, content, timestamp, unique_id)
- Uses a textual function-call format (see ResponseParser) with rfind-based parsing
- Alternates Reasoning and Acting until calling the tool `finish`
- Supports tools: `run_bash_cmd`, `finish`

This file intentionally omits core implementations and replaces them with
clear specifications and TODOs.
"""

from typing import List, Callable, Dict, Any
import time

from response_parser import ResponseParser
from llm import LLM, OpenAIModel
import inspect

class ReactAgent:
    """
    Minimal ReAct agent that:
    - Maintains a message history list with unique ids
    - Builds the LLM context from the message list
    - Registers callable tools with auto-generated docstrings in the system prompt
    - Runs a Reason-Act loop until `finish` is called or MAX_STEPS is reached
    """

    def __init__(self, name: str, parser: ResponseParser, llm: LLM):
        self.name: str = name
        self.parser = parser
        self.llm = llm

        # Message list storage
        self.id_to_message: List[Dict[str, Any]] = []
        self.root_message_id: int = -1
        self.current_message_id: int = -1

        # Registered tools
        self.function_map: Dict[str, Callable] = {}

        # Track agent actions for finish validation
        self.made_edit: bool = False
        self.ran_tests_after_edit: bool = False

        # Set up the initial structure of the history
        # Create required root nodes and a user node (task)
        initial_system_content = """You are an autonomous software engineer fixing bugs in a repository. Your goal: resolve the issue and make tests pass.

# Constraints
- No internet access. Use only the tools provided.
- Do NOT modify tests unless the issue explicitly requires it.
- Make minimal, targeted changes. Prefer small fixes over refactors.

# Workflow
1. First action: Call get_repo_info(), then find_test_file() or grep() to locate relevant code.
2. Locate the bug: Use grep(), find_files(), show_file(), or show_code_structure() to find relevant files.
3. Reproduce: Run a failing test with run_test() or run_bash_cmd("pytest ..."). Use analyze_test_failure() to understand errors.
4. Fix: Use replace_in_file() to make targeted changes. NEVER include function call markers (----BEGIN_FUNCTION_CALL----, ----END_FUNCTION_CALL----, etc.) in file content.
5. Verify: Re-run tests after EVERY edit. If tests fail, analyze and iterate.
6. Finish: Call finish() only when tests pass and you've run tests since your last edit.

# Critical Rules
- Use replace_in_file() for ALL code changes. Do NOT use run_bash_cmd() to edit files.
- Run tests BEFORE your first edit and AFTER every edit.
- For large files, use show_file_snippet(path, start_line, end_line) instead of show_file().
- Keep Thoughts concise (1-3 sentences). Call exactly ONE tool per Action.
- NEVER include function call markers (----BEGIN_FUNCTION_CALL----, ----END_FUNCTION_CALL----, ----ARG----, ----VALUE----) in replace_in_file() content.
- Do NOT call finish() if tests are failing or you haven't run tests since your last edit.

# When Stuck
- Re-read the issue description for missed details.
- Use analyze_test_failure() to extract error types and locations.
- Use show_code_structure() for large files before reading details.
- Check edge cases: None values, empty inputs, type mismatches.
- Call check_syntax() after significant Python file changes.

"""

        self.system_message_id = self.add_message("system", initial_system_content)
        self.user_message_id = self.add_message("user", "")
        # NOTE: mandatory finish function that terminates the agent
        self.add_functions([self.finish])

    # -------------------- MESSAGE LIST --------------------
    def add_message(self, role: str, content: str) -> int:
        """
        Create a new message and add it to the list.

        The message must include fields: role, content, timestamp, unique_id.
        """
        self.id_to_message.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "unique_id": len(self.id_to_message),
        })
        return len(self.id_to_message) - 1

    def set_message_content(self, message_id: int, content: str) -> None:
        """
        Update message content by id.
        """
        self.id_to_message[message_id]["content"] = content

    def get_context(self) -> str:
        """
        Build the full LLM context from the message list.
        
        This is used for debugging/logging. For actual LLM calls, use get_messages_for_llm().
        """
        return "\n".join([self.message_id_to_context(i) for i in range(len(self.id_to_message))])
    
    def get_messages_for_llm(self) -> List[Dict[str, str]]:
        """
        Convert message list to OpenAI chat format (list of dicts with role and content).
        
        This is the format required by the LLM.generate() method.
        """
        messages = []
        for idx, msg in enumerate(self.id_to_message):
            # For system messages, include the formatted context with tool descriptions
            if msg["role"] == "system":
                # Use message_id_to_context to get the full formatted system message
                formatted_content = self.message_id_to_context(idx)
                # Extract just the content part (after the header)
                content_lines = formatted_content.split('\n')
                # Skip the header line and get the content
                content = '\n'.join(content_lines[2:]) if len(content_lines) > 2 else msg["content"]
                messages.append({"role": "system", "content": content})
            else:
                # For user and assistant messages, just use the content
                messages.append({"role": msg["role"], "content": msg["content"]})
        return messages

    # -------------------- REQUIRED TOOLS --------------------
    def add_functions(self, tools: List[Callable]):
        """
        Add callable tools to the agent's function map.

        The system prompt must include tool descriptions that cover:
        - The signature of each tool
        - The docstring of each tool
        """
        # Register tools in function map
        self.function_map.update({tool.__name__: tool for tool in tools})
        
        # Organize tools by category
        tool_categories = {
            "Repository Information": ["get_repo_info"],
            "File Operations": ["show_file", "replace_in_file", "grep", "find_files", "show_code_structure", "show_file_snippet"],
            "Testing & Analysis": ["run_test", "analyze_test_failure", "find_test_file", "check_syntax"],
            "General": ["run_bash_cmd", "finish"],
        }

        # Build organized tool descriptions
        categorized_tools = {cat: [] for cat in tool_categories.keys()}
        uncategorized = []

        for tool in self.function_map.values():
            signature = inspect.signature(tool)
            docstring = inspect.getdoc(tool) or ""
            tool_description = f"Function: {tool.__name__}{signature}\n{docstring}\n"

            # Find which category this tool belongs to
            categorized = False
            for category, tool_names in tool_categories.items():
                if tool.__name__ in tool_names:
                    categorized_tools[category].append(tool_description)
                    categorized = True
                    break

            if not categorized:
                uncategorized.append(tool_description)

        # Build tool text with categories
        tool_sections = []
        for category, descriptions in categorized_tools.items():
            if descriptions:
                tool_sections.append(f"### {category}\n" + "\n".join(descriptions))

        if uncategorized:
            tool_sections.append("### Other Tools\n" + "\n".join(uncategorized))

        tool_text = "\n".join(tool_sections)
        
        # Get current system content and append tool descriptions
        current_content = self.id_to_message[self.system_message_id]["content"]
        system_content = (
            f"{current_content}\n\n"
            f"## Available Tools\n\n{tool_text}\n\n"
            f"## Response Format\n\n{self.parser.response_format}\n\n"
            "DO NOT CHANGE ANY TEST! AS THEY WILL BE USED FOR EVALUATION."
        )
        self.set_message_content(self.system_message_id, system_content)
    
    def finish(self, result: str):
        """The agent must call this function with the final result when it has solved the given task. The function calls "git add -A and git diff --cached" to generate a patch and returns the patch as submission.

        Args: 
            result (str); the result generated by the agent

        Returns:
            The result passed as an argument.  The result is then returned by the agent's run method.
        """
        return result 

    # -------------------- MAIN LOOP --------------------
    def run(self, task: str, max_steps: int) -> str:
        """
        Run the agent's main ReAct loop:
        - Set the user prompt
        - Loop up to max_steps (<= 100):
            - Build messages for LLM (OpenAI chat format)
            - Query the LLM
            - Add LLM response as assistant message
            - Parse a single function call at the end (see ResponseParser)
            - If `finish` is called, return the final result
            - Execute the tool
            - Append tool result as observation (user message)
        """
        # Set the user task message
        self.set_message_content(self.user_message_id, task)
        
        # Main ReAct loop
        for step in range(max_steps):
            # Build messages for LLM (must be list of dicts, not string)
            messages = self.get_messages_for_llm()
            
            # Query LLM
            response = self.llm.generate(messages)
            
            # Add LLM response as assistant message
            self.add_message("assistant", response)
            
            # Parse function call from response
            try:
                function_call = self.parser.parse(response)
            except Exception as e:
                # If parsing fails, add error as observation with helpful context
                error_msg = (
                    f"Error parsing function call: {str(e)}\n"
                    f"Make sure your response includes exactly one function call with the format:\n"
                    f"{self.parser.BEGIN_CALL}\n"
                    f"function_name\n"
                    f"{self.parser.ARG_SEP}\n"
                    f"arg_name\n"
                    f"{self.parser.VALUE_SEP}\n"
                    f"arg_value\n"
                    f"{self.parser.END_CALL}\n"
                    f"Your response should not include function call markers in file content."
                )
                self.add_message("user", error_msg)
                continue

            # Check if finish was called
            if function_call["name"] == "finish":
                # Enforce simple guards
                if not self.made_edit:
                    self.add_message(
                        "user",
                        "You have not modified any files yet. Use replace_in_file() to change the code before calling finish()."
                    )
                    continue
                if not self.ran_tests_after_edit:
                    self.add_message(
                        "user",
                        "You have not run tests since your last code change. Run tests with run_test() or run_bash_cmd('pytest ...') before calling finish()."
                    )
                    continue
                result = self.function_map["finish"](**function_call["arguments"])
                return result

            # Execute the tool
            try:
                if function_call["name"] not in self.function_map:
                    available_tools = ", ".join(sorted(self.function_map.keys()))
                    raise ValueError(
                        f"Unknown function: {function_call['name']}. "
                        f"Available functions: {available_tools}"
                    )
                
                result = self.function_map[function_call["name"]](**function_call["arguments"])

                # Update flags
                if function_call["name"] == "replace_in_file":
                    self.made_edit = True
                    self.ran_tests_after_edit = False
                elif function_call["name"] == "run_test":
                    if self.made_edit:
                        self.ran_tests_after_edit = True
                elif function_call["name"] == "run_bash_cmd":
                    command = function_call["arguments"].get("command", "").lower()
                    # Detect various test execution patterns
                    is_test_command = (
                        "pytest" in command or
                        "python -m pytest" in command or
                        "python -m unittest" in command or
                        "make test" in command or
                        ("test" in command and any(keyword in command for keyword in ["test_", "tests/", "/test"]))
                    )
                    if is_test_command and self.made_edit:
                        self.ran_tests_after_edit = True

                # Add tool result as observation (user message)
                self.add_message("user", f"Observation: {result}")
            except ValueError as e:
                # ValueError usually indicates a user error (bad arguments, validation failure)
                # Provide helpful context and suggestions
                error_msg = f"Error executing {function_call['name']}: {str(e)}"
                if "function call marker" in str(e).lower():
                    error_msg += "\nTip: When using replace_in_file(), only include the actual code content. Do not include function call markers (----BEGIN_FUNCTION_CALL----, etc.) in the content parameter."
                elif "not found" in str(e).lower() or "does not exist" in str(e).lower():
                    error_msg += "\nTip: Use find_files() or grep() to locate the correct file path."
                self.add_message("user", error_msg)
            except Exception as e:
                # Other exceptions (system errors, etc.)
                error_msg = (
                    f"Error executing {function_call['name']}: {type(e).__name__}: {str(e)}\n"
                    f"Arguments used: {function_call.get('arguments', {})}"
                )
                self.add_message("user", error_msg)
        
        # Max steps reached
        return self.finish("Max steps reached")

    def message_id_to_context(self, message_id: int) -> str:
        """
        Helper function to convert a message id to a context string.
        """
        message = self.id_to_message[message_id]
        header = f'----------------------------\n|MESSAGE(role="{message["role"]}", id={message["unique_id"]})|\n'
        content = message["content"]
        if message["role"] == "system":
            tool_descriptions = []
            for tool in self.function_map.values():
                signature = inspect.signature(tool)
                docstring = inspect.getdoc(tool)
                tool_description = f"Function: {tool.__name__}{signature}\n{docstring}\n"
                tool_descriptions.append(tool_description)

            tool_descriptions = "\n".join(tool_descriptions)
            return (
                f"{header}{content}\n"
                f"--- AVAILABLE TOOLS ---\n{tool_descriptions}\n\n"
                f"--- RESPONSE FORMAT ---\n{self.parser.response_format}\n"
            )
        else:
            return f"{header}{content}\n"

def main():
    from envs import DumbEnvironment
    llm = OpenAIModel("----END_FUNCTION_CALL----", "gpt-4o-mini")
    parser = ResponseParser()

    env = DumbEnvironment()
    dumb_agent = ReactAgent("dumb-agent", parser, llm)
    dumb_agent.add_functions([env.run_bash_cmd])
    result = dumb_agent.run("Show the contents of all files in the current directory.", max_steps=10)
    print(result)

if __name__ == "__main__":
    # Optional: students can add their own quick manual test here.
    main()
