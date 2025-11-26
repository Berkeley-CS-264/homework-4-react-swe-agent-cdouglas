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
        Generate a patch from the result (for SWE-Bench)
        """
        try:
            patch_output = self.env.execute("git add -A && git diff --cached")
            
            # Handle case where execute returns a dict instead of string
            if isinstance(patch_output, dict):
                patch_output = patch_output.get("output", "") or patch_output.get("stdout", "")
            
            if patch_output and patch_output.strip():
                return patch_output
            else:
                return f"{result}\n\nNo changes detected to generate a patch."
        except Exception as e:
            return f"{result}\n\nError running git commands: {e}"

    # -------------------- OPTIONAL TOOLS --------------------
    def show_file(self, file_path: str) -> str:
        """
        Show the content of the file.

        Args:
            file_path (str): Path to the file to read

        Returns:
            The contents of the file
        """
        try:
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
            raise ValueError(f"Error reading file {file_path}: {str(e)}")

    def replace_in_file(self, file_path: str, from_line: int, to_line: int, content: str) -> str:
        """
        Replace lines in a file from from_line to to_line (inclusive, 1-indexed) with the given content.

        Args:
            file_path (str): Path to the file to modify
            from_line (int): Starting line number (1-indexed, inclusive)
            to_line (int): Ending line number (1-indexed, inclusive)
            content (str): New content to replace the lines with (can be multiline)

        Returns:
            Confirmation message with the number of lines replaced
        """
        try:
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

# Validate line numbers
from_line = {from_line}
to_line = {to_line}

if from_line < 1 or to_line < 1:
    print("Error: Line numbers must be >= 1", file=sys.stderr)
    sys.exit(1)
if from_line > len(lines) + 1:
    print(f"Error: from_line ({{from_line}}) exceeds file length ({{len(lines)}})", file=sys.stderr)
    sys.exit(1)
if to_line < from_line:
    print("Error: to_line must be >= from_line", file=sys.stderr)
    sys.exit(1)

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
            output = self.env.execute(f"python3 -c {repr(python_script)}")

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
            raise ValueError(f"Error replacing lines in {file_path}: {str(e)}")

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
