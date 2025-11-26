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

        # Set up the initial structure of the history
        # Create required root nodes and a user node (task)
        initial_system_content = """You are an autonomous software engineer working in a local checkout of a repository.
Your task is to modify the code so that the issue below is resolved and all relevant tests pass.

## Environment & Constraints
- You work in a local Python environment with the repo at the root directory
- You have NO internet access
- You may only interact with the repo using the tools listed below
- Do NOT modify tests or test data unless explicitly instructed
- Prefer minimal, targeted changes over broad refactors
- Use `get_repo_info()` to learn the repository name and root directory

## Recommended Workflow

1. **Understand the Problem**
   - Read the issue description carefully
   - Find and read the relevant test file using `find_test_file()` or `grep()`
   - Identify what should happen vs. what actually happens
   - Use `get_repo_info()` to understand the repository context

2. **Locate Relevant Code**
   - Use `grep()` and `find_files()` to find relevant files
   - Use `show_file()` to read code sections
   - Trace through the codebase to understand the flow

3. **Make Changes**
   - Use `replace_in_file(file_path, from_line, to_line, content)` to modify code
   - Line numbers are 1-indexed and inclusive (both from_line and to_line are included)
   - Make minimal, targeted changes
   - Preserve existing code style and patterns

4. **Verify Changes**
   - Use `show_diff(file_path)` to see what changed in each modified file
   - Use `verify_changes()` to confirm files are modified
   - Use `check_syntax(file_path)` to validate Python syntax
   - Run tests with `run_test()` to verify the fix

5. **Testing Requirements (CRITICAL)**
   - **You MUST run the specific test mentioned in the issue before finishing**
     - Use `find_test_file(issue_description)` to locate the test
     - Run it with `run_test(test_path, test_name)` to verify your fix works
   - **Run related tests to check for regressions**
     - Look for other tests in the same file/module using `grep()` or `find_files()`
     - Run tests for related functionality
   - **Handle edge cases mentioned in the issue**
     - Read the issue description carefully for all scenarios
     - Ensure your fix addresses all cases mentioned
     - Test edge cases explicitly if possible
   - **Verify the fix is complete**
     - If the issue mentions multiple cases, test all of them
     - If the issue mentions specific error conditions, verify they're handled
     - Only call `finish()` after tests pass

6. **Complete the Task**
   - Only call `finish()` after verifying changes exist AND tests pass
   - The `finish()` result parameter is for logging only
   - Actual patch is generated automatically from file edits via git

## Critical Rules

- **You MUST use `replace_in_file()` to make actual code changes**
- **You MUST verify changes exist before calling `finish()`**
- **You MUST run tests before finishing to ensure your fix works**
- **Text descriptions in `finish()` do NOT create patches - only file edits do**
- **If `verify_changes()` shows no changes, you haven't fixed the issue**
- **If tests fail, debug and fix before finishing**

## Common Fix Patterns

**Metaclasses and Descriptors:**
- Properties: Cannot assign __doc__ directly. Create new property: `property(fget, fset, fdel, doc=inherited_doc)`
- Classmethod/staticmethod: Access underlying function via `__func__` attribute
- Use `base.__dict__.get(key)` to avoid descriptor binding side-effects

**Variable Scoping:**
- Preserve state before try/except blocks if you need to restore on exception
- Use explicit variable assignments rather than relying on loop variables

**Exception Handling:**
- Always restore previous state in finally blocks or exception handlers

**Import Organization:**
- Plain `import` statements should come before `from ... import` statements
- Sort within each group alphabetically

**Environment Variables:**
- Prefer environment variables over temporary files when possible
- Use `os.environ.copy()` and modify the copy for subprocess calls

**Dimension/Unit Equivalence:**
- Use dimension system's `equivalent_dims()` method instead of structural equality
- Example: `acceleration * time` is equivalent to `velocity` but not structurally equal

## When Stuck
- Re-read the issue description - you might have missed a detail
- Re-read the test file - understand what it's actually testing
- Check if similar issues exist in the codebase (grep for related code)
- Use `analyze_test_failure()` to understand test failures better"""

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
            "File Operations": ["show_file", "replace_in_file", "grep", "find_files"],
            "Testing & Analysis": ["run_test", "analyze_test_failure", "find_test_file", "check_syntax"],
            "Git & Verification": ["show_diff", "verify_changes", "get_git_status"],
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
                result = self.function_map["finish"](**function_call["arguments"])
                return result
            
            # Execute the tool
            try:
                if function_call["name"] not in self.function_map:
                    raise ValueError(f"Unknown function: {function_call['name']}")
                
                result = self.function_map[function_call["name"]](**function_call["arguments"])
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
