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
        initial_system_content = """You are an autonomous software engineer working in a local checkout of a repository.
Your task is to modify the code so that the issue below is resolved and all relevant tests pass.

# Environment & Constraints
- You work in a local Python environment with the repo at the root directory.
- You have NO internet access.
- You may only interact with the repo using the tools listed below.
- Do NOT modify existing tests or test data unless the issue explicitly requires it.
- Prefer minimal, targeted changes over broad refactors.
- Use get_repo_info() to learn the repository name and root directory.

# High-level workflow (follow this order)
1. Carefully read the issue description in the user message.
2. Use grep() and find_files() to locate relevant files, functions, and tests.
3. Use show_file() and show_code_structure() to inspect small, relevant parts of the code.
4. Identify an existing test (or small group of tests) that reproduces the bug and run it using run_test() or run_bash_cmd("pytest ...").
5. When tests fail, call analyze_test_failure(test_output=...) on the pytest output to extract the key error type, message, and file/line location.
6. Based on the failing test and code, write a short plan in your Thought:
   - suspected root cause
   - the specific file(s) and function(s) you will change
   - which tests you will run after the change
7. Apply a small, focused code change using replace_in_file(). Edit only the lines that are actually necessary.
8. Re-run the same test(s) using run_test() or run_bash_cmd() to confirm the bug is fixed and no new failures appear.
9. If tests still fail, inspect the test output, call analyze_test_failure() again if needed, refine your plan, and repeat steps 3–8.
10. When you are confident the bug is fixed and tests pass, call finish() with a short explanation of:
   - what you changed,
   - why it fixes the issue,
   - which tests you ran.

# First step
On your very first Action, you MUST:
1. Call get_repo_info() to see the repo name and root directory.
2. Then call either:
   - find_test_file() to list likely test files, or
   - grep() to search for a key symbol or phrase from the issue.
Do NOT run broad commands like "pytest" or "ls -R" as your first action.

# When choosing tests:
- Prefer narrow tests over the whole suite:
  - If you know the test file, use run_test(test_path="path/to/test_file.py").
  - If you only know a keyword, use run_test(test_name="keyword") to run a subset with -k.
- Avoid running the entire test suite repeatedly. Only do that near the end, if needed.
- Make sure at least one failing test clearly matches the issue description (same feature, function, or error message).

# When Stuck
- Re-read the issue description carefully; you may have missed a key detail.
- Use find_test_file() to locate likely relevant tests.
- Re-read the relevant test file(s) with show_file() and understand exactly what is being asserted.
- Use show_code_structure() to understand large or complex files before reading them in detail.
- Use grep() to search for similar logic or patterns in other parts of the codebase.
- Use analyze_test_failure() on pytest output to extract the key error and stack trace location.
- Add temporary debug prints using replace_in_file() if needed to understand the control flow.
- Consider edge cases: empty inputs, None values, type mismatches, boundary conditions, etc.
- Remember that some fixes require changes in more than one place (e.g., both implementation and helper utilities).
- If you significantly change a Python file, call check_syntax(file_path) on it before running tests.

# Critical Rules
- Always make real code changes using replace_in_file(); your explanation in finish() does NOT modify files.
- Do NOT modify files using run_bash_cmd(). Use replace_in_file() for all code changes so they are captured in the final patch.
- Before your FIRST call to replace_in_file(), identify and run at least one failing test using run_test() or run_bash_cmd("pytest ...").
- AFTER every successful call to replace_in_file(), run at least one test again.
- Do NOT call finish() if:
  - you have not clearly reproduced the bug with a failing test,
  - the last tests you ran are still failing, or
  - you have not run any tests since your last code change.
- Do NOT modify existing tests or test data unless the issue explicitly requires it.
- Prefer the smallest change that makes the tests pass and matches the issue description.
- Keep your Thought concise (1–3 short sentences) and then call exactly ONE tool in each Action.
- For large files, prefer show_file_snippet(path, start_line, end_line) to view just the relevant part, then use those line numbers with replace_in_file().

# Example pattern (do NOT hard-code these paths; they are just an example):

Thought: I should find where MyClass is defined.
Action: grep(pattern="MyClass", file_pattern="*.py")

Thought: I found MyClass in src/foo.py. I will view the relevant lines.
Action: show_file(file_path="src/foo.py")

Thought: I see the bug in method do_thing at lines 40–55. I will edit those lines.
Action: replace_in_file(
    file_path="src/foo.py",
    from_line=40,
    to_line=55,
    content=\"\"\"
    def do_thing(x, y):
        # new implementation here
        ...
    \"\"\"
)

Thought: Now I will run the failing test to confirm the fix.
Action: run_test(test_path="tests/test_foo.py", verbose=True)

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
            "File Operations": ["show_file", "replace_in_file", "grep", "find_files", "show_code_structure"],
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
                # If parsing fails, add error as observation and continue
                self.add_message("user", f"Error parsing function call: {str(e)}")
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
                    raise ValueError(f"Unknown function: {function_call['name']}")
                
                result = self.function_map[function_call["name"]](**function_call["arguments"])

                # Update flags
                if function_call["name"] == "replace_in_file":
                    self.made_edit = True
                    self.ran_tests_after_edit = False
                elif function_call["name"] in ("run_test",) or (
                    function_call["name"] == "run_bash_cmd"
                    and "pytest" in function_call["arguments"].get("command", "")
                ):
                    if self.made_edit:
                        self.ran_tests_after_edit = True

                # Add tool result as observation (user message)
                self.add_message("user", f"Observation: {result}")
            except Exception as e:
                # Add error as observation
                self.add_message("user", f"Error executing {function_call['name']}: {str(e)}")
        
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
