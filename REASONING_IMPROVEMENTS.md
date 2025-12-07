# Agent Reasoning and Diagnostic Improvements

## Problem Analysis

The agent's performance remained at 10/20 resolved instances despite previous improvements. Analysis of successful vs. unsuccessful attempts reveals:

### Key Issues Identified

1. **Lack of Testing Before Finishing**: Agent makes changes but doesn't verify they work
2. **Insufficient Reasoning**: Agent doesn't explain its thought process, making failures hard to diagnose
3. **Poor Failure Analysis**: When tests fail, agent doesn't analyze why
4. **Incomplete Problem Understanding**: Agent sometimes fixes symptoms rather than root causes

### Examples from Failed Cases

- **django-12406**: Agent made changes but didn't test them properly
- **django-13297**: Agent attempted fix but didn't verify it addressed the actual issue
- **sphinx-7590**: Agent made changes but they didn't pass evaluation
- **django-16631**: Documentation-only changes may not be evaluated correctly

## Improvements Made

### 1. Enhanced System Prompt with Reasoning Requirements

**New Mandatory Requirements:**
- Agent MUST report reasoning at each step
- Before making changes: Explain problem, approach, assumptions, edge cases
- After making changes: Explain what changed, why, what could go wrong
- Before calling finish: MUST run tests and document reasoning in result

**Reasoning Format:**
```
REASONING:
- Problem: [What is the issue?]
- Root cause: [Why does it happen?]
- Solution: [What I'm changing and why]
- Assumptions: [What I'm assuming]
- Edge cases: [What edge cases I considered]
- Test status: [Did tests pass? If not, why?]
```

### 2. New Diagnostic Tools

#### `analyze_test_failure(test_output: str) -> str`
- Extracts key failure information from test output
- Identifies error types, messages, and locations
- Helps agent understand why tests fail

**Usage:**
```python
# After running tests that fail
failure_analysis = env.analyze_test_failure(test_output)
# Use this to understand what went wrong
```

#### `find_test_file(issue_description: str = None) -> str`
- Finds test files related to the issue
- Can match keywords from issue description
- Helps agent locate relevant tests

**Usage:**
```python
# Find tests related to the issue
test_files = env.find_test_file("radio button selection")
```

#### `show_diff(file_path: str) -> str`
- Shows git diff for a file
- Helps agent see what has changed
- Useful for verifying edits

**Usage:**
```python
# See what changed in a file
diff = env.show_diff("django/forms/widgets.py")
```

### 3. Enhanced Testing Strategy in Prompt

**Mandatory Steps:**
1. Run specific failing tests first to understand the issue
2. After making changes, run the same tests to verify the fix
3. Run related tests to ensure no regressions
4. If tests fail, analyze the failure output carefully
5. **DO NOT call finish until tests pass**

### 4. Common Failure Modes Section

Added explicit guidance on common mistakes:
- Making changes without testing
- Fixing symptoms instead of root cause
- Missing edge cases
- Incomplete fixes
- Not reading tests carefully

### 5. Improved Problem Understanding Section

Emphasized:
- Reading issue description CAREFULLY
- Finding and reading test files COMPLETELY
- Understanding expected behavior from tests
- Tracing through codebase to understand data flow

## Expected Behavior Changes

### Before Calling Finish, Agent Should:

1. **Run Tests**: Use `run_test()` to verify the fix works
2. **Analyze Failures**: If tests fail, use `analyze_test_failure()` to understand why
3. **Document Reasoning**: Include in the finish result:
   - What problem was identified
   - Why the solution works
   - Test results
   - Any concerns or edge cases

### Example Workflow:

```
1. Read issue description
2. Find and read test file
3. Understand expected behavior
4. Locate relevant code
5. Make fix
6. Run tests
7. If tests fail:
   - Analyze failure
   - Understand what went wrong
   - Try different approach
8. If tests pass:
   - Document reasoning
   - Call finish with reasoning included
```

## Diagnostic Information Requested

The system prompt now explicitly requests:

1. **Problem Analysis**: What is the issue? Why does it happen?
2. **Solution Approach**: What are you changing and why?
3. **Assumptions**: What are you assuming?
4. **Edge Cases**: What edge cases did you consider?
5. **Test Results**: Did tests pass? If not, why?
6. **Concerns**: What could still go wrong?

This information will help diagnose issues in future iterations.

## Usage

The agent now has:
- Enhanced system prompt requiring reasoning reports
- New diagnostic tools for test failure analysis
- Mandatory testing requirements
- Better guidance on common failure modes

Run the agent as before:
```bash
python run_agent.py --model gpt-4o-mini --max-steps 20 --output results
```

The agent will now:
1. Report reasoning at each step
2. Test changes before finishing
3. Analyze test failures when they occur
4. Include detailed reasoning in finish results

## Next Steps for Analysis

When reviewing agent runs, look for:

1. **Reasoning Quality**: Does the agent explain its thinking?
2. **Test Execution**: Did the agent run tests before finishing?
3. **Failure Analysis**: If tests failed, did the agent analyze why?
4. **Problem Understanding**: Did the agent correctly identify the root cause?
5. **Solution Completeness**: Does the fix handle all cases?

Use this information to further refine the system prompt and tools.

