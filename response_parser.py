class ResponseParser:
    """
    Parses LLM responses to extract a single function call using a rigid textual format.

    The LLM must output exactly one function call at the end of its response.
    Do NOT use JSON or XML. Use rfind to locate the final markers.
    """

    BEGIN_CALL = "----BEGIN_FUNCTION_CALL----"
    END_CALL = "----END_FUNCTION_CALL----"
    ARG_SEP = "----ARG----"
    VALUE_SEP = "----VALUE----"

    # Students should include this exact template in the system prompt so the LLM follows it.
    response_format = f"""
your_thoughts_here
...
{BEGIN_CALL}
function_name
{ARG_SEP}
arg1_name
{VALUE_SEP}
arg1_value (can be multiline)
{ARG_SEP}
arg2_name
{VALUE_SEP}
arg2_value (can be multiline)
...
{END_CALL}

DO NOT CHANGE ANY TEST! AS THEY WILL BE USED FOR EVALUATION.
"""

    def parse(self, text: str) -> dict:
        """
        Parse the function call from `text` using string.rfind to avoid confusion with
        earlier delimiter-like content in the reasoning.

        Returns a dictionary: {"thought": str, "name": str, "arguments": dict}
        """
        # Find the last occurrence of BEGIN_CALL and END_CALL using rfind
        call_start = text.rfind(self.BEGIN_CALL)
        call_end = text.rfind(self.END_CALL)
        
        if call_start == -1 or call_end == -1 or call_end < call_start:
            raise ValueError("No valid function call found")
        
        # Extract thought (everything before BEGIN_CALL)
        thought = text[:call_start].strip()
        
        # Extract the function call block (between BEGIN_CALL and END_CALL)
        call_text = text[call_start + len(self.BEGIN_CALL):call_end].strip()
        
        # Split into lines for parsing
        lines = call_text.split('\n')
        
        # First line is the function name
        if not lines:
            raise ValueError("Function name not found")
        function_name = lines[0].strip()
        
        # Parse arguments
        arguments = {}
        i = 1
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for ARG_SEP marker
            if line == self.ARG_SEP:
                i += 1
                if i >= len(lines):
                    break
                # Next line is the argument name
                arg_name = lines[i].strip()
                i += 1
                
                # Look for VALUE_SEP marker
                if i < len(lines) and lines[i].strip() == self.VALUE_SEP:
                    i += 1
                    # Collect value (may be multiline until next ARG_SEP or end)
                    value_lines = []
                    while i < len(lines):
                        if lines[i].strip() == self.ARG_SEP:
                            break
                        value_lines.append(lines[i])
                        i += 1
                    arguments[arg_name] = '\n'.join(value_lines).strip()
                else:
                    # No value provided, set to empty string
                    arguments[arg_name] = ""
            else:
                i += 1
        
        return {"thought": thought, "name": function_name, "arguments": arguments}
