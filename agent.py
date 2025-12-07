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
        initial_system_content = """You are an autonomous software engineer fixing bugs in a repository. Goal: resolve the issue and make the correct tests pass.

# Constraints
- No internet access. Use only the tools provided.
- Do NOT modify tests unless explicitly required.
- Make minimal, targeted changes. Prefer small fixes over refactors.
- Always end your reply with exactly ONE function call using the provided markers. Nothing may appear after ----END_FUNCTION_CALL----.

# Workflow (repeat until done)
1) Reproduce: First action should be get_repo_info(), then run the recommended failing test (use run_relevant_tests() first, or run_test() with specific test path).
2) Localize: Use analyze_test_failure() to understand errors. Use grep() to find relevant code patterns. Use show_code_structure() to understand file organization before reading.
3) Inspect: Read ONLY the specific functions/classes that need changes using show_file_snippet(). Do NOT read entire large files.
4) Edit: Apply a focused, surgical change with replace_in_file(). Replace ONLY the exact lines that need modification - typically 1-20 lines. NEVER replace entire functions or files unless absolutely necessary.
5) Re-test: Re-run the SAME failing test(s) immediately after every edit. Use analyze_test_failure() if tests still fail to understand what's wrong.
6) Verify: Use check_syntax() after Python edits. Use git_status() to see what files changed.

# Finish checklist (all must be true before calling finish())
- You have seen at least one failing test that matches the issue description.
- You made at least one successful code edit with replace_in_file().
- You re-ran tests after your last edit.
- Your latest test run shows all tests PASSED (no FAILED/ERROR in output).

# Critical Rules for Edits
- Use replace_in_file() for ALL code changes. Do NOT use run_bash_cmd() to edit files.
- BEFORE editing: Use show_file_snippet() or show_file() to see the EXACT current content and line numbers.
- AFTER editing: ALWAYS re-run tests to verify the change worked.
- Edit scope: Replace only what's necessary (typically 1-20 lines). Avoid replacing entire functions/classes/files.
- Line numbers: Use show_file() or show_file_snippet() to get accurate line numbers before calling replace_in_file().
- NEVER include function call markers (----BEGIN_FUNCTION_CALL----, ----END_FUNCTION_CALL----, ----ARG----, ----VALUE----) in the content parameter of replace_in_file().

# Efficient Tool Usage
- show_file(): Use for small files (<50 lines). Returns first 200 lines with line numbers.
- show_file_snippet(path, start_line, end_line): Use for specific sections of large files. More efficient than show_file().
- show_code_structure(): Use FIRST for large files to see structure, then use show_file_snippet() to read specific functions.
- grep(pattern, file_pattern): Use to search across files for specific patterns or function names.
- find_files(name_pattern): Use to locate files by name when you don't know the exact path.

# When Stuck
- Re-read the issue description for missed details.
- Use analyze_test_failure() to extract precise error messages and line numbers.
- Check if your edit actually changed what you intended - re-read the file with show_file_snippet() after editing.
- Check edge cases: None values, empty inputs, type mismatches, missing imports.
- Consider if the issue is in a different file than you think - use grep() to search broadly.
- If tests pass locally but the issue persists, ensure you're testing the right thing.
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
            "Repository Information": ["get_repo_info", "git_status"],
            "File Operations": ["show_file", "replace_in_file", "grep", "find_files", "show_code_structure", "show_file_snippet"],
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
                if not self.saw_failing_test:
                    self.add_message(
                        "user",
                        "You have not reproduced a failing test yet. Run the recommended failing test with run_relevant_tests() or run_test() before finishing."
                    )
                    continue
                if not self.made_edit:
                    self.add_message(
                        "user",
                        "You have not modified any files yet. Use replace_in_file() to change the code before calling finish()."
                    )
                    continue
                if not self.ran_tests_after_edit:
                    self.add_message(
                        "user",
                        "You have not run tests since your last code change. Re-run the failing test with run_relevant_tests() or run_test() before calling finish()."
                    )
                    continue
                if self.last_test_had_failure:
                    self.add_message(
                        "user",
                        "Your most recent test run still shows failures. Fix the issue and re-run tests before calling finish()."
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
                elif function_call["name"] in {"run_test", "run_relevant_tests"}:
                    has_failure = _has_test_failure(result)
                    self.last_test_had_failure = has_failure
                    if has_failure:
                        self.saw_failing_test = True
                    if self.made_edit:
                        self.ran_tests_after_edit = True
                elif function_call["name"] == "run_bash_cmd":
                    command = function_call["arguments"].get("command", "")
                    if _is_test_command(command):
                        has_failure = _has_test_failure(result)
                        self.last_test_had_failure = has_failure
                        if has_failure:
                            self.saw_failing_test = True
                        if self.made_edit:
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
