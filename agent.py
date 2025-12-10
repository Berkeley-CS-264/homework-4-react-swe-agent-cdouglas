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
        self.saw_failing_test: bool = False
        self.last_test_had_failure: bool = False

        # Set up the initial structure of the history
        # Create required root nodes and a user node (task)
        initial_system_content = """You are fixing bugs in a repository. Make tests pass with minimal changes.

# Workflow
1. Reproduce: get_repo_info(), then run_relevant_tests()
2. Fix: Use grep() to find code, show_file_snippet() to read it, replace_in_file() to edit
3. Verify: Re-run tests after EVERY edit
4. Finish: Call finish() only when tests pass

# Rules
- Use replace_in_file() for edits (never run_bash_cmd)
- Read file before editing to get exact content
- Edit only 1-20 lines at a time
- Always re-run tests after editing
- Don't modify test files

# Tool Tips
- grep(): Use specific patterns like "def function_name" or "class ClassName"
- show_file_snippet(): Always use for large files, specify line range
- replace_in_file(): Copy exact text with whitespace. Read file first.
- find_files(): Search by filename pattern when path unknown

# Before finish():
- Made at least one edit
- Re-ran tests after last edit
- Latest test run shows PASSED
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
            "Repository Information": ["get_repo_info", "git_status", "show_current_diff"],
            "File Operations": ["show_file", "replace_in_file", "preview_replace", "grep", "find_files", "show_code_structure", "show_file_snippet"],
            "Testing & Analysis": ["run_test", "run_relevant_tests", "analyze_test_failure", "find_test_file", "check_syntax"],
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

        def _is_test_command(command: str) -> bool:
            if not command:
                return False
            command_lower = command.lower()
            return (
                "pytest" in command_lower
                or "python -m pytest" in command_lower
                or "python -m unittest" in command_lower
                or "unittest" in command_lower
                or "make test" in command_lower
                or (
                    "test" in command_lower
                    and any(keyword in command_lower for keyword in ["test_", "tests/", "/test"])
                )
            )

        def _has_test_failure(output: str) -> bool:
            if not isinstance(output, str):
                return False
            upper = output.upper()
            return any(token in upper for token in ["FAILED", "ERROR", "TRACEBACK", "EXCEPTION", "FAILURES"])
        
        # Main ReAct loop
        for step in range(max_steps):
            # Build messages for LLM (must be list of dicts, not string)
            messages = self.get_messages_for_llm()

            # Query LLM with exception handling
            try:
                response = self.llm.generate(messages)
            except Exception as e:
                # If LLM call fails, add error message and allow agent to continue
                # This prevents the entire agent from crashing on API failures
                error_msg = (
                    f"Error calling LLM: {type(e).__name__}: {str(e)}\n"
                    f"The API call failed. Please try again with your next action."
                )
                self.add_message("user", error_msg)
                # Continue to next iteration - agent can try again
                continue
            
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
                        "You have not run tests since your last code change. Re-run tests with run_relevant_tests() or run_test() before calling finish()."
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
                    lowered = result.lower() if isinstance(result, str) else ""
                    success = (
                        isinstance(result, str)
                        and "successfully replaced" in lowered
                        and "error" not in lowered
                        and "timeout" not in lowered
                    )
                    if success:
                        self.made_edit = True
                        self.ran_tests_after_edit = False

                        # Iteration 6: Automatic syntax checking for Python files
                        file_path = function_call["arguments"].get("file_path", "")
                        if file_path and file_path.strip().endswith('.py'):
                            # Automatically check syntax after editing Python files
                            if "check_syntax" in self.function_map:
                                try:
                                    syntax_result = self.function_map["check_syntax"](file_path=file_path)
                                    if syntax_result and "Syntax OK" not in syntax_result:
                                        # Syntax error detected - add warning to result
                                        result = result + (
                                            f"\n\n⚠ SYNTAX ERROR DETECTED in {file_path}:\n"
                                            f"{syntax_result}\n"
                                            f"You must fix this syntax error before proceeding. "
                                            f"Use show_file_snippet() to view the problematic section and replace_in_file() to fix it."
                                        )
                                except Exception as e:
                                    # Don't fail if syntax check fails - just log it
                                    pass

                        # Iteration 6: Post-edit verification prompt
                        if "⚠ SYNTAX ERROR" not in result:
                            result = result + (
                                f"\n\nEdit complete. "
                                f"Verify changes with show_file_snippet('{file_path}') before running tests."
                            )
                elif function_call["name"] in {"run_test", "run_relevant_tests"}:
                    has_failure = _has_test_failure(result)
                    self.last_test_had_failure = has_failure
                    if has_failure:
                        self.saw_failing_test = True
                    if self.made_edit:
                        self.ran_tests_after_edit = True

                    # Early success detection
                    if not has_failure and self.made_edit and self.ran_tests_after_edit:
                        result = result + "\n\n✓ Tests passing! You can call finish() now."

                elif function_call["name"] == "run_bash_cmd":
                    command = function_call["arguments"].get("command", "")
                    if _is_test_command(command):
                        has_failure = _has_test_failure(result)
                        self.last_test_had_failure = has_failure
                        if has_failure:
                            self.saw_failing_test = True
                        if self.made_edit:
                            self.ran_tests_after_edit = True

                        # Early success detection
                        if not has_failure and self.made_edit and self.ran_tests_after_edit:
                            result = result + "\n\n✓ Tests passing! You can call finish() now."

                # Add tool result as observation (user message)
                self.add_message("user", f"Observation: {result}")
            except ValueError as e:
                # ValueError usually indicates a user error (bad arguments, validation failure)
                # Provide helpful context and recovery suggestions
                error_msg = f"Error: {str(e)}"
                error_lower = str(e).lower()

                # Add specific recovery suggestions
                if "function call marker" in error_lower:
                    error_msg += "\nFix: Don't include markers in content. Only include actual code."
                elif "not found" in error_lower or "does not exist" in error_lower:
                    error_msg += "\nFix: Use find_files('pattern') or grep('pattern', '*.py') to locate the file."
                elif "no such file" in error_lower:
                    error_msg += "\nFix: Check file path. Use find_files() to search for it."
                elif "old_text" in error_lower or "not match" in error_lower:
                    error_msg += "\nFix: Read the file first with show_file_snippet() to see exact content."
                elif "parse" in error_lower or "format" in error_lower:
                    error_msg += "\nFix: Check your function call format. End with ----END_FUNCTION_CALL----"

                self.add_message("user", error_msg)
            except Exception as e:
                # Other exceptions (system errors, etc.)
                error_type = type(e).__name__
                error_msg = f"Error ({error_type}): {str(e)}"

                # Add recovery hint based on error type
                if "timeout" in str(e).lower():
                    error_msg += "\nThe command took too long. Try a simpler approach."
                elif "permission" in str(e).lower():
                    error_msg += "\nPermission denied. Check if the file/command is accessible."

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
