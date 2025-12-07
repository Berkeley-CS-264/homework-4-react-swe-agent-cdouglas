# SWE-Agent Implementation Documentation

## Table of Contents
1. [Overview](#overview)
2. [Missing Functionality in Base Harness](#missing-functionality-in-base-harness)
3. [Fixes Required for Basic ReAct Loop](#fixes-required-for-basic-react-loop)
4. [Execution Flow](#execution-flow)
5. [Extending the Agent for Better Performance](#extending-the-agent-for-better-performance)

## Overview

This document explains the implementation of a ReAct (Reasoning and Acting) agent for solving SWE-bench tasks. The agent is based on the [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) architecture, which is a minimal implementation that achieves >74% accuracy on SWE-bench Verified.

### SWE-bench Context

SWE-bench is a benchmark for evaluating AI agents on real-world software engineering tasks. Each task consists of:
- A GitHub issue description (the problem statement)
- A codebase snapshot at a specific commit
- A test suite that validates the fix
- A Docker container environment for isolated execution

The agent must:
1. Understand the problem from the issue description
2. Navigate and understand the codebase
3. Generate a code patch that fixes the issue
4. Ensure the patch passes all existing tests

## Missing Functionality in Base Harness

The starter code provided several scaffolded methods marked with `TODO(student)`. The following critical functionality was missing:

### 1. Message Format Conversion (`agent.py`)

**Problem**: The `get_context()` method returned a formatted string, but the LLM's `generate()` method expects OpenAI's chat format: a list of message dictionaries with `"role"` and `"content"` keys.

**Error Encountered**:
```
OpenAI API call failed: BadRequestError: Error code: 400 -
{'error': {'message': "Invalid type for 'messages': expected an array of objects,
but got a string instead.", 'type': 'invalid_request_error', 'param': 'messages',
'code': 'invalid_type'}}
```

**Solution**: Added `get_messages_for_llm()` method that converts the internal message list format to OpenAI's chat API format.

### 2. System Message Tool Descriptions (`agent.py`)

**Problem**: The `add_functions()` method registered tools in `function_map` but didn't update the system message to include tool descriptions. The LLM needs to know what tools are available and how to use them.

**Solution**: Modified `add_functions()` to:
- Build tool descriptions from function signatures and docstrings
- Update the system message content with available tools and response format
- Ensure the system message is properly formatted for the LLM

### 3. ReAct Loop Message Flow (`agent.py`)

**Problem**: The initial `run()` method had several issues:
- Called `get_context()` (returns string) instead of `get_messages_for_llm()` (returns list)
- Didn't properly track the conversation flow (LLM response → tool execution → observation)
- Incorrect finish detection logic
- Didn't handle parsing errors gracefully

**Solution**: Completely rewrote the ReAct loop to:
- Use `get_messages_for_llm()` for LLM calls
- Add LLM responses as assistant messages
- Add tool results as user/observation messages
- Properly detect when `finish` is called
- Handle errors gracefully and continue the loop

### 4. Function Call Argument Parsing (`response_parser.py`)

**Problem**: The `parse()` method only extracted the function name but didn't parse arguments. The textual format uses `ARG_SEP` and `VALUE_SEP` markers, and arguments can be multiline.

**Solution**: Implemented full argument parsing that:
- Uses `rfind()` to locate the last function call block
- Extracts the "thought" portion (reasoning before the function call)
- Parses function name from the first line after `BEGIN_CALL`
- Iterates through `ARG_SEP` markers to extract argument names
- Extracts argument values (which can be multiline) between `VALUE_SEP` and the next `ARG_SEP`

## Fixes Required for Basic ReAct Loop

### Critical Fixes (Required for Basic Functionality)

1. **Message Format Conversion**
   ```python
   def get_messages_for_llm(self) -> List[Dict[str, str]]:
       """Convert to OpenAI chat format."""
       messages = []
       for idx, msg in enumerate(self.id_to_message):
           if msg["role"] == "system":
               # Include formatted system message with tools
               formatted_content = self.message_id_to_context(idx)
               content = '\n'.join(formatted_content.split('\n')[2:])
               messages.append({"role": "system", "content": content})
           else:
               messages.append({"role": msg["role"], "content": msg["content"]})
       return messages
   ```

2. **System Message Update**
   ```python
   def add_functions(self, tools: List[Callable]):
       self.function_map.update({tool.__name__: tool for tool in tools})
       # Build and update system message with tool descriptions
       tool_descriptions = [...]
       system_content = f"You are a Smart ReAct agent.\n\n--- AVAILABLE TOOLS ---\n{tool_text}..."
       self.set_message_content(self.system_message_id, system_content)
   ```

3. **ReAct Loop Structure**
   ```python
   def run(self, task: str, max_steps: int) -> str:
       self.set_message_content(self.user_message_id, task)
       for step in range(max_steps):
           messages = self.get_messages_for_llm()  # Not get_context()!
           response = self.llm.generate(messages)
           self.add_message("assistant", response)
           function_call = self.parser.parse(response)
           if function_call["name"] == "finish":
               return self.function_map["finish"](**function_call["arguments"])
           result = self.function_map[function_call["name"]](**function_call["arguments"])
           self.add_message("user", f"Observation: {result}")
   ```

4. **Argument Parsing**
   ```python
   def parse(self, text: str) -> dict:
       # Use rfind to find last function call
       # Extract thought, function name, and arguments
       # Handle multiline argument values
   ```

### What Was NOT a Placeholder

- **"sleep 2h" in Docker**: This is NOT a placeholder. It's how mini-swe-agent keeps Docker containers alive for command execution. The container runs `sleep 2h` in the background, and commands are executed via `docker exec`.
- **Docker Environment Setup**: The environment initialization in `utils.py` is correct and working.
- **LLM Implementation**: The `OpenAIModel` class in `llm.py` was already correctly implemented.

## Execution Flow

### High-Level Flow

```
1. run_agent.py loads SWE-bench dataset
   ↓
2. For each instance:
   a. Create Docker container (sleep 2h keeps it alive)
   b. Initialize SWEEnvironment (wraps mini-swe-agent Docker env)
   c. Create ReactAgent with LLM and parser
   d. Add tools (run_bash_cmd, finish)
   ↓
3. Agent.run(task, max_steps):
   a. Set user message with task
   b. ReAct Loop (up to max_steps):
      i. Build messages for LLM (OpenAI format)
      ii. Query LLM → get response with function call
      iii. Parse function call
      iv. If finish: return result
      v. Execute tool (e.g., run_bash_cmd)
      vi. Add observation to history
   ↓
4. Generate patch:
   a. Run "git add -A && git diff --cached" in container
   b. Save patch to preds.json
   ↓
5. SWE-bench evaluation harness tests patch
```

### ReAct Loop Details

The ReAct (Reasoning and Acting) loop alternates between:

1. **Reasoning**: LLM generates thoughts and decides on an action
2. **Acting**: Execute the chosen tool/function
3. **Observing**: Add the tool result to conversation history
4. **Repeat**: Until `finish` is called or max steps reached

Message flow in the loop:
```
[System] You are a Smart ReAct agent. Available tools: ...
[User] Task: Fix issue #1234
[Assistant] I need to understand the codebase... ----BEGIN_FUNCTION_CALL---- run_bash_cmd...
[User] Observation: [command output]
[Assistant] Now I'll check the test file... ----BEGIN_FUNCTION_CALL---- run_bash_cmd...
[User] Observation: [test output]
[Assistant] I'll fix the bug... ----BEGIN_FUNCTION_CALL---- finish...
```

## Extending the Agent for Better Performance

### 1. Add Custom Tools (`envs.py`)

The scaffold provides optional tool stubs:

```python
def show_file(self, file_path: str) -> str:
    """Show the content of a file."""
    return self.run_bash_cmd(f"cat {file_path}")

def replace_in_file(self, file_path: str, from_line: int, to_line: int, content: str) -> str:
    """Replace lines in a file."""
    # Implementation using sed or Python
    ...
```

**Why**: These tools provide structured file operations, making it easier for the LLM to reason about code changes. Instead of complex bash commands, the agent can use semantic operations.

**How to add**:
1. Implement the method in `SWEEnvironment`
2. Add it to the agent: `agent.add_functions([env.show_file, env.replace_in_file])`

### 2. Improve System Prompt

The system prompt can be enhanced with:
- **Context about SWE-bench**: Explain that tests must not be modified
- **Code navigation strategies**: Suggest exploring the codebase systematically
- **Error handling guidance**: How to interpret and recover from errors
- **Patch generation hints**: Remind about git workflow

**Location**: Modify the system message in `add_functions()` or `__init__()`.

### 3. Add Error Recovery

Current implementation adds errors as observations, but you could:
- **Retry logic**: Automatically retry failed commands with variations
- **Error classification**: Parse error messages and provide structured feedback
- **Rollback**: Undo changes if tests fail

**Example**:
```python
try:
    result = self.function_map[function_call["name"]](**function_call["arguments"])
except ValueError as e:
    # Parse error and provide helpful context
    error_msg = f"Command failed: {str(e)}\nSuggestion: Check file paths and permissions."
    self.add_message("user", f"Observation: {error_msg}")
```

### 4. Implement Code Search Tools

Add tools to help the agent navigate large codebases:

```python
def search_code(self, pattern: str, file_pattern: str = "*.py") -> str:
    """Search for code patterns using grep."""
    return self.run_bash_cmd(f"grep -r '{pattern}' --include='{file_pattern}' .")

def find_test_files(self, test_name: str = None) -> str:
    """Find test files related to the issue."""
    # Implementation
    ...
```

### 5. Add Context Window Management

For long conversations, implement:
- **Message summarization**: Summarize old messages to save tokens
- **Selective context**: Only include relevant messages
- **File content caching**: Cache file contents to avoid re-reading

### 6. Improve Response Parser

The parser could be enhanced with:
- **Better error messages**: More descriptive errors when parsing fails
- **Validation**: Check that required arguments are present
- **Type conversion**: Convert string arguments to appropriate types

### 7. Add Planning Phase

Before starting execution, have the agent:
1. Read the problem statement carefully
2. Explore the codebase structure
3. Identify relevant files
4. Create a plan

This can be implemented as a separate phase or integrated into the system prompt.

### 8. Implement Multi-Step Reasoning

For complex tasks, allow the agent to:
- Break down the problem into sub-tasks
- Track progress on each sub-task
- Re-evaluate strategy if stuck

### 9. Add Evaluation Feedback Loop

After generating a patch:
- Run tests locally (if possible)
- Parse test results
- If tests fail, provide feedback and retry

### 10. Optimize for SWE-bench Specifics

SWE-bench specific improvements:
- **Test awareness**: Parse test files to understand expected behavior
- **Issue analysis**: Extract key information from issue descriptions
- **Code pattern matching**: Learn common fix patterns from training data

## Testing Your Implementation

### Basic Test

```python
from agent import ReactAgent
from llm import OpenAIModel
from response_parser import ResponseParser
from envs import DumbEnvironment

llm = OpenAIModel("----END_FUNCTION_CALL----", "gpt-4o-mini")
parser = ResponseParser()
env = DumbEnvironment()

agent = ReactAgent("test-agent", parser, llm)
agent.add_functions([env.run_bash_cmd])
result = agent.run("List all files in the current directory", max_steps=5)
print(result)
```

### SWE-bench Test

```bash
python run_agent.py --model gpt-4o-mini --max-steps 10 --output results
```

This will process instances and save results. Check `results/preds.json` for generated patches.

## Common Pitfalls

1. **Type Mismatch**: Always use `get_messages_for_llm()` for LLM calls, not `get_context()`
2. **Finish Detection**: Check function name before executing, not after
3. **Message Flow**: LLM response → assistant message, tool result → user message
4. **Error Handling**: Don't let parsing errors crash the loop
5. **System Message**: Must be updated when tools are added

## References

- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent): Reference implementation
- [SWE-bench](https://www.swebench.com/): Benchmark details
- [ReAct Paper](https://arxiv.org/abs/2210.03629): Original ReAct methodology

