from utils import get_sb_environment
import subprocess
import swebench

class LimitsExceeded(Exception):
    """Raised when the agent has reached its step limit."""


class SWEEnvironment:
    """
    Minimal interface to the SWEBench execution environment.

    Students may use their own wrapper. The environment must expose:
    - execute(command: str) -> str: Run a shell command and return stdout, or raise ValueError on failure
    """

    def __init__(self, instance: dict):
        self.env = get_sb_environment(instance)
        self.instance = instance  # Store instance for test execution
     
    # -------------------- REQUIRED TOOLS --------------------
    def run_bash_cmd(self, command: str) -> str:
        """
        Run the command in a bash shell and return the output or throw a ValueError
        if the process returns non-zero exit code.

        Args;
            command (str): the shell command to run

        Returns:
            The output of running the shell command
        """
        try:
            output = self.env.execute(command)
            
            # Handle case where execute returns a dict instead of string
            if isinstance(output, dict):
                output = output.get("output", "") or output.get("stdout", "")
                
        except subprocess.TimeoutExpired as e:
            output = e.output.decode("utf-8", errors="replace") if e.output else ""
            raise ValueError(output)
        except TimeoutError:
            raise ValueError("TimeoutError")
        return output
    
    def generate_patch(self, result: str) -> str:
        """
        Generate a patch from staged changes. Returns valid git diff or empty string.

        Args:
            result (str): The agent's result message (for logging, not included in patch)

        Returns:
            str: Valid git diff format patch, or empty string if no changes detected
        """
        try:
            # Ensure all changes are staged
            add_result = self.env.execute("git add -A")
            if isinstance(add_result, dict):
                add_result = add_result.get("output", "") or add_result.get("stdout", "")
            
            # Get the diff
            patch_output = self.env.execute("git diff --cached")
            if isinstance(patch_output, dict):
                patch_output = patch_output.get("output", "") or patch_output.get("stdout", "")
            
            # Validate it's a proper git diff
            if patch_output and patch_output.strip().startswith("diff --git"):
                return patch_output.strip()

            # If no valid patch, check git status to understand why (for debugging)
            # But don't include this in the return value - just return empty string
            status = self.env.execute("git status --short")
            if isinstance(status, dict):
                status = status.get("output", "") or status.get("stdout", "")

            # Return empty string (valid empty patch) instead of text description
            return ""
        except Exception as e:
            # Log error but return empty patch (not error text)
            # Empty string is a valid patch format that evaluation harness accepts
            return ""

    # -------------------- OPTIONAL TOOLS --------------------
    def show_file(self, file_path: str) -> str:
        """
        Show the content of the file.

        Args:
            file_path (str): Path to the file to read (tolerates leading/trailing whitespace, relative paths)

        Returns:
            The contents of the file
        """
        try:
            # Normalize file path: strip whitespace, handle relative paths
            file_path = file_path.strip()
            if not file_path:
                raise ValueError("File path cannot be empty")

            # Remove leading ./ if present (common agent mistake)
            if file_path.startswith('./'):
                file_path = file_path[2:]

            output = self.env.execute(f"cat '{file_path}'")

            # Handle case where execute returns a dict instead of string
            if isinstance(output, dict):
                output = output.get("output", "") or output.get("stdout", "")

            return output
        except subprocess.TimeoutExpired as e:
            output = e.output.decode("utf-8", errors="replace") if e.output else ""
            raise ValueError(f"Timeout reading file {file_path}: {output}")
        except TimeoutError:
            raise ValueError(f"Timeout reading file {file_path}")
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error message
            if "No such file" in error_msg or "cannot find" in error_msg.lower():
                return f"Error: File '{file_path}' not found. Use find_files() or grep() to locate the correct path."
            raise ValueError(f"Error reading file {file_path}: {error_msg}")

    def replace_in_file(self, file_path: str, from_line: int, to_line: int, content: str) -> str:
        """
        Replace lines in a file from from_line to to_line (inclusive, 1-indexed) with the given content.

        Args:
            file_path (str): Path to the file to modify (tolerates leading/trailing whitespace, relative paths)
            from_line (int): Starting line number (1-indexed, inclusive). Auto-corrects if to_line < from_line.
            to_line (int): Ending line number (1-indexed, inclusive). Auto-corrects if < from_line.
            content (str): New content to replace the lines with (can be multiline)

        Returns:
            Confirmation message with the number of lines replaced
        """
        import tempfile
        import os

        try:
            # Normalize file path
            file_path = file_path.strip()
            if not file_path:
                raise ValueError("File path cannot be empty")
            if file_path.startswith('./'):
                file_path = file_path[2:]

            # Normalize and validate line numbers (make tolerant)
            try:
                from_line = int(from_line)
                to_line = int(to_line)
            except (ValueError, TypeError):
                raise ValueError(f"Line numbers must be integers. Got from_line={from_line}, to_line={to_line}")

            # Auto-correct if to_line < from_line (common mistake)
            if to_line < from_line:
                from_line, to_line = to_line, from_line

            # Ensure line numbers are positive
            if from_line < 1:
                from_line = 1
            if to_line < 1:
                to_line = 1
            # Use Python to safely replace lines in the file
            # We'll use base64 encoding to safely pass the content through the command line
            import base64

            # Encode content to base64 to avoid shell escaping issues
            content_b64 = base64.b64encode(content.encode('utf-8')).decode('ascii')

            python_script = f"""
import sys
import base64
from pathlib import Path

file_path = Path('{file_path}')
content_b64 = '{content_b64}'

if not file_path.exists():
    print(f"Error: File {{file_path}} does not exist", file=sys.stderr)
    sys.exit(1)

# Decode the content
try:
    new_content = base64.b64decode(content_b64.encode('ascii')).decode('utf-8')
except Exception as e:
    print(f"Error decoding content: {{e}}", file=sys.stderr)
    sys.exit(1)

# Read the file
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
except Exception as e:
    print(f"Error reading file: {{e}}", file=sys.stderr)
    sys.exit(1)

# Validate line numbers (already normalized by outer function)
from_line = {from_line}
to_line = {to_line}

# More tolerant validation - allow appending at end of file
if from_line > len(lines) + 1:
    # Allow appending at end
    from_line = len(lines) + 1
    to_line = len(lines)
    print(f"Warning: Line numbers adjusted. File has {{len(lines)}} lines. Appending at end.", file=sys.stderr)

if to_line < from_line:
    # Auto-correct
    from_line, to_line = to_line, from_line

# Prepare new content (split into lines)
new_lines = new_content.splitlines(keepends=True)
if not new_lines:
    new_lines = ['']
# Ensure last line has newline if original file had newlines
if lines and lines[-1].endswith('\\n') and new_lines and not new_lines[-1].endswith('\\n'):
    new_lines[-1] = new_lines[-1] + '\\n'
elif not new_lines[-1].endswith('\\n'):
    new_lines[-1] = new_lines[-1] + '\\n'

# Replace lines (convert to 0-indexed)
start_idx = from_line - 1
end_idx = to_line  # exclusive end

# Build new file content
new_file_lines = lines[:start_idx] + new_lines + lines[end_idx:]

# Write back to file
try:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_file_lines)
    num_replaced = to_line - from_line + 1
    print(f"Successfully replaced lines {{from_line}} to {{to_line}} ({{num_replaced}} lines) in {{file_path}}")
except Exception as e:
    print(f"Error writing file: {{e}}", file=sys.stderr)
    sys.exit(1)
"""
            # Write script to container filesystem (not host /tmp)
            # CRITICAL FIX: Temp files created on host don't exist in Docker container
            # Write directly to container filesystem at /testbed using heredoc
            script_path = "/testbed/.agent_replace_script.py"

            # Use base64 encoding to safely pass script content through shell
            # Then decode and write it in the container using Python
            script_b64 = base64.b64encode(python_script.encode('utf-8')).decode('ascii')

            # Write script to container using Python one-liner
            # This avoids shell escaping issues with the script content
            write_cmd = f"python3 -c \"import base64; open('{script_path}', 'w').write(base64.b64decode('{script_b64}').decode('utf-8'))\""
            write_result = self.env.execute(write_cmd)

            # Check if write succeeded (ignore output, just check for exceptions)
            if isinstance(write_result, dict):
                write_result = write_result.get("output", "") or write_result.get("stdout", "")
                # Check for error indicators
                if write_result and ("Error" in write_result or "error" in write_result.lower() or "Traceback" in write_result):
                    raise ValueError(f"Failed to write script to container: {write_result}")

            try:
                output = self.env.execute(f"python3 {script_path}")
            finally:
                # Clean up script file in container
                try:
                    self.env.execute(f"rm -f {script_path}")
                except:
                    pass

            # Handle case where execute returns a dict instead of string
            if isinstance(output, dict):
                output = output.get("output", "") or output.get("stdout", "")

            return output
        except subprocess.TimeoutExpired as e:
            output = e.output.decode("utf-8", errors="replace") if e.output else ""
            raise ValueError(f"Timeout replacing lines in {file_path}: {output}")
        except TimeoutError:
            raise ValueError(f"Timeout replacing lines in {file_path}")
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error message for temp file issues
            if "No such file" in error_msg and ("/tmp/" in error_msg or "can't open file" in error_msg):
                return (f"Error: Temporary script file not found in container. "
                       f"This indicates a system error with file operations. "
                       f"Please try the replace_in_file() call again. "
                       f"If the problem persists, you may need to use run_bash_cmd() "
                       f"to manually edit the file. Original error: {error_msg}")
            raise ValueError(f"Error replacing lines in {file_path}: {error_msg}")

    def grep(self, pattern: str, file_pattern: str = "*", case_sensitive: bool = True) -> str:
        """
        Search for a pattern in files using grep.

        Args:
            pattern (str): The pattern to search for (regex)
            file_pattern (str): File pattern to search in (e.g., "*.py", "test_*.py")
            case_sensitive (bool): Whether search is case-sensitive

        Returns:
            Matching lines with file names and line numbers
        """
        try:
            flags = "-E" if case_sensitive else "-iE"  # -E for extended regex
            cmd = f"grep -rn {flags} '{pattern}' --include='{file_pattern}' . 2>/dev/null || true"
            output = self.env.execute(cmd)

            if isinstance(output, dict):
                output = output.get("output", "") or output.get("stdout", "")

            return output if output else "No matches found"
        except Exception as e:
            raise ValueError(f"Error searching for pattern: {str(e)}")

    def find_files(self, name_pattern: str = "*", file_type: str = "f") -> str:
        """
        Find files matching a pattern.

        Args:
            name_pattern (str): Filename pattern (e.g., "test_*.py", "*misc.py")
            file_type (str): "f" for files, "d" for directories

        Returns:
            List of matching file paths
        """
        try:
            # Use find with proper escaping
            cmd = f"find . -type {file_type} -name '{name_pattern}' 2>/dev/null | head -50"
            output = self.env.execute(cmd)

            if isinstance(output, dict):
                output = output.get("output", "") or output.get("stdout", "")

            return output if output else "No files found"
        except Exception as e:
            raise ValueError(f"Error finding files: {str(e)}")

    def run_test(self, test_path: str = None, test_name: str = None, verbose: bool = False) -> str:
        """
        Run tests using pytest.

        Args:
            test_path (str): Path to test file or directory (e.g., "tests/test_misc.py").
                            Tolerates leading/trailing whitespace, relative paths, with/without .py extension.
            test_name (str): Specific test function name (e.g., "test_inherit_docstrings")
            verbose (bool): Whether to show verbose output (accepts bool, int, or string "true"/"false")

        Returns:
            Test output
        """
        try:
            # Normalize verbose flag (tolerant of string inputs)
            if isinstance(verbose, str):
                verbose = verbose.lower() in ('true', '1', 'yes', 'on')
            verbose = bool(verbose)

            cmd_parts = ["pytest", "-q"]
            if verbose:
                cmd_parts.append("-v")

            if test_path:
                # Normalize test path
                test_path = test_path.strip()
                if test_path.startswith('./'):
                    test_path = test_path[2:]
                # Remove .py extension if present (pytest handles both)
                if test_path.endswith('.py'):
                    test_path = test_path[:-3]
                cmd_parts.append(test_path)
            elif test_name:
                # Normalize test name
                test_name = test_name.strip()
                # Remove "test_" prefix if agent adds it redundantly
                if test_name.startswith('test_') and 'test_' in test_name[5:]:
                    test_name = test_name[5:]
                # Search for the test function
                cmd_parts.append("-k")
                cmd_parts.append(test_name)
            else:
                cmd_parts.append(".")

            cmd = " ".join(cmd_parts)
            output = self.env.execute(cmd)

            if isinstance(output, dict):
                output = output.get("output", "") or output.get("stdout", "")

            return output
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error message
            if "not found" in error_msg.lower() or "no such file" in error_msg.lower():
                return f"Error: Test path not found. Use find_test_file() to locate test files.\nOriginal error: {error_msg}"
            raise ValueError(f"Error running tests: {error_msg}")

    def check_syntax(self, file_path: str) -> str:
        """
        Check Python syntax of a file.

        Args:
            file_path (str): Path to Python file to check (tolerates leading/trailing whitespace, relative paths)

        Returns:
            Syntax check result ("Syntax OK" if valid, error message if invalid)
        """
        try:
            # Normalize file path
            file_path = file_path.strip()
            if not file_path:
                raise ValueError("File path cannot be empty")
            if file_path.startswith('./'):
                file_path = file_path[2:]

            cmd = f"python3 -m py_compile '{file_path}' 2>&1"
            output = self.env.execute(cmd)

            if isinstance(output, dict):
                output = output.get("output", "") or output.get("stdout", "")

            # If compilation succeeds, output is usually empty
            if not output or "SyntaxError" not in output:
                return "Syntax OK"
            return output
        except Exception as e:
            # If command fails, there's a syntax error
            error_msg = str(e)
            if "SyntaxError" in error_msg or "syntax" in error_msg.lower():
                return error_msg
            if "No such file" in error_msg or "cannot find" in error_msg.lower():
                return f"Error: File '{file_path}' not found. Cannot check syntax."
            raise ValueError(f"Error checking syntax: {error_msg}")

    def analyze_test_failure(self, test_output: str) -> str:
        """
        Analyze test failure output to extract key information.

        Args:
            test_output (str): The output from a failed test run

        Returns:
            Analysis of the failure including error type, message, and location
        """
        try:
            # Extract key failure information
            lines = test_output.split('\n')
            analysis = []

            # Look for common failure patterns
            error_type = None
            error_message = None
            file_location = None
            traceback_lines = []

            in_traceback = False
            for i, line in enumerate(lines):
                if "FAILED" in line or "ERROR" in line:
                    analysis.append(f"Test Status: {line.strip()}")
                elif "AssertionError" in line or "ValueError" in line or "TypeError" in line or "AttributeError" in line:
                    error_type = line.strip()
                    analysis.append(f"Error Type: {error_type}")
                elif "def test_" in line and file_location is None:
                    # Try to find test function
                    analysis.append(f"Test Function: {line.strip()}")
                elif ".py:" in line and ("test_" in line or "FAILED" in line):
                    file_location = line.strip()
                    analysis.append(f"File Location: {file_location}")
                elif "assert" in line.lower() and "failed" in line.lower():
                    analysis.append(f"Assertion: {line.strip()}")
                elif line.strip().startswith("E ") and len(line.strip()) > 2:
                    # Error message line
                    error_message = line.strip()[2:]
                    analysis.append(f"Error Message: {error_message}")

            if not analysis:
                # Fallback: return key sections
                key_sections = []
                for line in lines[-20:]:  # Last 20 lines often have the error
                    if any(keyword in line for keyword in ["FAILED", "ERROR", "AssertionError", "ValueError", "TypeError", "AttributeError", "assert"]):
                        key_sections.append(line.strip())
                if key_sections:
                    return "Key failure information:\n" + "\n".join(key_sections)
                return "Could not extract failure details. Full output:\n" + test_output[-500:]  # Last 500 chars

            return "\n".join(analysis) if analysis else "No failure information extracted"
        except Exception as e:
            return f"Error analyzing test failure: {str(e)}\n\nRaw output:\n{test_output[-500:]}"

    def find_test_file(self, issue_description: str = None) -> str:
        """
        Find test files related to the issue.

        Args:
            issue_description (str): Optional description to help find relevant tests

        Returns:
            List of test files that might be relevant
        """
        try:
            # Find all test files
            cmd = "find . -name 'test_*.py' -o -name '*_test.py' 2>/dev/null | head -20"
            output = self.env.execute(cmd)

            if isinstance(output, dict):
                output = output.get("output", "") or output.get("stdout", "")

            if not output:
                return "No test files found"

            # If we have issue description, try to match
            if issue_description:
                # Simple keyword matching
                keywords = []
                for word in issue_description.lower().split():
                    if len(word) > 4:  # Skip short words
                        keywords.append(word)

                matching_files = []
                for line in output.split('\n'):
                    if line.strip():
                        # Check if any keyword appears in the path
                        line_lower = line.lower()
                        if any(kw in line_lower for kw in keywords[:3]):  # Check first 3 keywords
                            matching_files.append(line.strip())

                if matching_files:
                    return "Potentially relevant test files:\n" + "\n".join(matching_files[:10])

            return "Test files found:\n" + output
        except Exception as e:
            raise ValueError(f"Error finding test files: {str(e)}")

    def show_diff(self, file_path: str = None) -> str:
        """
        Show the git diff for a file to see what has changed.

        Args:
            file_path (str, optional): Path to the file. If None or empty, shows diff for all changed files.
                                      Tolerates leading/trailing whitespace, relative paths.

        Returns:
            Git diff output showing changes
        """
        try:
            if file_path:
                # Normalize file path
                file_path = file_path.strip()
                if file_path.startswith('./'):
                    file_path = file_path[2:]
                cmd = f"git diff '{file_path}' 2>&1"
            else:
                # Show diff for all changed files
                cmd = "git diff 2>&1"

            output = self.env.execute(cmd)

            if isinstance(output, dict):
                output = output.get("output", "") or output.get("stdout", "")

            if not output or "fatal" in output.lower():
                if file_path:
                    return f"No changes detected for '{file_path}' (file may not be tracked or no changes made)"
                return "No changes detected (no files have been modified)"

            return output
        except Exception as e:
            raise ValueError(f"Error showing diff: {str(e)}")

    def verify_changes(self) -> str:
        """
        Verify that file changes exist and are staged.

        Returns:
            Git status output showing modified files, or "No changes detected"
        """
        try:
            status = self.env.execute("git status --short")
            if isinstance(status, dict):
                status = status.get("output", "") or status.get("stdout", "")
            return status if status else "No changes detected"
        except Exception as e:
            return f"Error checking status: {e}"

    def get_git_status(self) -> str:
        """
        Get detailed git status to help debug why changes aren't detected.

        Returns:
            Full git status output
        """
        try:
            status = self.env.execute("git status")
            if isinstance(status, dict):
                status = status.get("output", "") or status.get("stdout", "")
            return status if status else "No git status available"
        except Exception as e:
            return f"Error getting git status: {e}"

    def get_repo_info(self) -> str:
        """Get repository name and root directory information.

        Returns:
            String containing repository name and root directory path
        """
        try:
            repo = self.instance.get("repo", "unknown")
            # Extract repo name from instance_id (format: repo__repo-issue)
            instance_id = self.instance.get("instance_id", "")
            if "__" in instance_id:
                repo_name = instance_id.split("__")[0]
            else:
                repo_name = repo

            # Get root directory (usually /testbed in Docker containers)
            root_dir = self.env.execute("pwd")
            if isinstance(root_dir, dict):
                root_dir = root_dir.get("output", "") or root_dir.get("stdout", "")
            root_dir = root_dir.strip() if root_dir else "/testbed"

            return f"Repository: {repo_name}\nRoot directory: {root_dir}"
        except Exception as e:
            return f"Repository: {self.instance.get('repo', 'unknown')}\nRoot directory: /testbed\n(Error getting details: {e})"

    def stage_changes(self) -> str:
        """
        Explicitly stage all file changes and verify they're detected.

        This tool ensures that all modifications are staged for git and can be
        included in the generated patch. Use this if verify_changes() shows
        changes but they're not being detected.

        Returns:
            Confirmation of staged changes or warning if no changes exist
        """
        try:
            # Stage all changes
            add_result = self.env.execute("git add -A")
            if isinstance(add_result, dict):
                add_result = add_result.get("output", "") or add_result.get("stdout", "")

            # Verify changes are staged
            status = self.env.execute("git status --short")
            if isinstance(status, dict):
                status = status.get("output", "") or status.get("stdout", "")

            if status and status.strip():
                return f"Changes staged successfully:\n{status}"
            else:
                return "WARNING: No changes to stage. Use replace_in_file() to make code changes before staging."
        except Exception as e:
            return f"Error staging changes: {e}"

    def can_finish(self) -> str:
        """
        Check if agent is ready to finish (has made changes and can generate patch).

        This tool validates that:
        1. File changes exist
        2. Changes are staged
        3. A valid patch can be generated

        Call this before finish() to ensure you're ready to complete the task.

        Returns:
            Status message indicating if agent can finish or what's missing
        """
        try:
            # Check for changes
            status = self.env.execute("git status --short")
            if isinstance(status, dict):
                status = status.get("output", "") or status.get("stdout", "")

            if not status or not status.strip():
                return ("CANNOT FINISH: No changes detected.\n\n"
                       "You must use replace_in_file() to make actual code changes before calling finish().\n"
                       "Text descriptions in finish() do NOT create patches - only file edits do.")

            # Stage changes
            self.env.execute("git add -A")

            # Check if patch can be generated
            patch = self.env.execute("git diff --cached")
            if isinstance(patch, dict):
                patch = patch.get("output", "") or patch.get("stdout", "")

            if patch and patch.strip().startswith("diff --git"):
                return (f"READY TO FINISH: Changes detected and patch can be generated.\n\n"
                       f"Modified files:\n{status}\n\n"
                       "You can now call finish() to complete the task.")
            else:
                return ("CANNOT FINISH: Changes exist but patch cannot be generated.\n\n"
                       "This may indicate the changes weren't properly saved or staged.\n"
                       "Try calling stage_changes() and verify_changes() to diagnose the issue.")
        except Exception as e:
            return f"Error checking finish readiness: {e}"

    def show_code_structure(self, file_path: str) -> str:
        """
        Show the structure of a Python file (classes, functions, imports).

        This helps understand code organization without reading the entire file.
        Useful for large files or when you need to understand the file's structure.

        Args:
            file_path (str): Path to Python file (tolerates whitespace, relative paths)

        Returns:
            Summary of classes, functions, and key imports in the file
        """
        try:
            # Normalize file path
            file_path = file_path.strip()
            if not file_path:
                raise ValueError("File path cannot be empty")
            if file_path.startswith('./'):
                file_path = file_path[2:]

            # Read the file
            content = self.show_file(file_path)
            if not content:
                return f"File {file_path} is empty or could not be read"

            lines = content.split('\n')
            structure = []
            structure.append(f"File: {file_path}\n")

            # Extract imports
            imports = []
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('import ') or stripped.startswith('from '):
                    imports.append(f"  Line {i}: {stripped}")

            if imports:
                structure.append("Imports:")
                structure.extend(imports[:20])  # Limit to first 20 imports
                if len(imports) > 20:
                    structure.append(f"  ... and {len(imports) - 20} more imports")
                structure.append("")

            # Extract classes and functions
            classes = []
            functions = []
            in_class = False
            indent_level = 0

            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue

                # Check indentation level (simple heuristic)
                line_indent = len(line) - len(line.lstrip())

                # Check for class definition
                if stripped.startswith('class '):
                    class_name = stripped.split('(')[0].replace('class ', '').strip()
                    classes.append(f"  Line {i}: class {class_name}")
                    in_class = True
                    indent_level = line_indent
                # Check for function definition
                elif stripped.startswith('def '):
                    func_name = stripped.split('(')[0].replace('def ', '').strip()
                    # If indentation is same or less than class, it's a module-level function
                    if not in_class or line_indent <= indent_level:
                        functions.append(f"  Line {i}: def {func_name}")
                        if line_indent <= indent_level:
                            in_class = False  # Reset if we're back at module level

            if classes:
                structure.append("Classes:")
                structure.extend(classes[:30])  # Limit to first 30 classes
                if len(classes) > 30:
                    structure.append(f"  ... and {len(classes) - 30} more classes")
                structure.append("")

            if functions:
                structure.append("Functions:")
                structure.extend(functions[:30])  # Limit to first 30 functions
                if len(functions) > 30:
                    structure.append(f"  ... and {len(functions) - 30} more functions")

            return "\n".join(structure) if structure else f"Could not extract structure from {file_path}"
        except Exception as e:
            return f"Error analyzing code structure: {str(e)}"

class DumbEnvironment:
    """
    Dumb environment that just executes the command
    """

    def execute(self, command: str) -> str:
        """
        Run the command in bash and return the output

        Args;
            command (str): the shell command to run

        Returns:
            The output of running the shell command
        """
        result = subprocess.run(command, capture_output=True, shell=True, check=False)
        output = f"--STDOUT--\n{result.stdout.decode()}\n--STDERR--\n{result.stderr.decode()}"
        if result.returncode:
            raise ValueError(output)
        return output
    
    def run_bash_cmd(self, command: str) -> str:
        """
        Run the command in a bash shell and return the output or throw a ValueError
        if the process returns non-zero exit code.

        Args;
            command (str): the shell command to run

        Returns:
            The output of running the shell command
        """
        return self.execute(command)
