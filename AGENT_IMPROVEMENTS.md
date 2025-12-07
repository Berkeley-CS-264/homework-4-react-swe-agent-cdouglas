# Agent Improvements Based on Test Analysis

## Analysis Summary

### Successful Instances (10 resolved)

1. **astropy__astropy-7166**: Metaclass property handling
   - **Pattern**: Properties require special handling - cannot assign `__doc__` directly
   - **Solution**: Create new property with inherited docstring: `property(fget, fset, fdel, doc=inherited_doc)`
   - **Key Insight**: Descriptors (properties, classmethods) need different handling than regular functions

2. **django__django-10973**: Environment variable preference
   - **Pattern**: Prefer environment variables over temporary files
   - **Solution**: Use `PGPASSWORD` env var instead of `.pgpass` file
   - **Key Insight**: Simpler, more reliable approach for passing credentials

3. **django__django-11179**: Variable scoping in loops
   - **Pattern**: Loop variables can be unreliable in exception handlers
   - **Solution**: Explicitly extract values from collections before use
   - **Key Insight**: Don't rely on loop variables that might be overwritten

4. **django__django-13810**: Exception state restoration
   - **Pattern**: Preserve state before try/except to restore on exception
   - **Solution**: Save `prev_handler` and restore it in exception handler
   - **Key Insight**: Always restore previous state when operations fail

5. **django__django-14053**: Duplicate prevention
   - **Pattern**: Track seen items to avoid yielding duplicates
   - **Solution**: Use a `set` to track already-yielded items
   - **Key Insight**: Generators may need deduplication logic

6. **django__django-16662**: Import organization
   - **Pattern**: Plain imports should come before from-imports
   - **Solution**: Group and sort imports: plain imports first, then from-imports
   - **Key Insight**: Code style requirements matter

7. **django__django-7530**: App config vs global models
   - **Pattern**: Use app-specific model access for router compatibility
   - **Solution**: `apps.get_app_config(app_label).get_models()` instead of `apps.get_models(app_label)`
   - **Key Insight**: Framework-specific APIs have subtle differences

8. **scikit-learn__scikit-learn-26323**: Collection completeness
   - **Pattern**: Check all sources, including hidden attributes
   - **Solution**: Include `remainder` estimator in transformer collection
   - **Key Insight**: Look for all places where items might be stored

9. **sympy__sympy-17655 & sympy__sympy-24213**: Reflected operations
   - **Pattern**: Implement `__rmul__` for scalar * Point operations
   - **Solution**: Delegate to main `__mul__` method
   - **Key Insight**: Handle both `obj * scalar` and `scalar * obj`

### Unresolved Instances (10 failed)

1. **django__django-12406**: Radio button selection logic
   - **Issue**: Edge case with empty choice selection for required fields
   - **Alternative Strategy**:
     - More carefully analyze the test case expectations
     - Check if the issue is about visual rendering vs. form validation
     - Consider that radio buttons have inherent "unselected" state

2. **django__django-13297**: TemplateView kwargs handling
   - **Issue**: Complex lazy object handling in template context
   - **Alternative Strategy**:
     - Understand the deprecation warning mechanism better
     - Test with actual template rendering, not just context creation
     - Consider that lazy objects might need special handling in Python code

3. **django__django-14011**: LiveServerThread daemon threads
   - **Issue**: Thread lifecycle and database connection management
   - **Alternative Strategy**:
     - Understand ThreadingMixIn behavior more deeply
     - Check if the issue is about thread joining vs. connection closing
     - Consider using thread synchronization primitives

4. **django__django-16631**: Documentation updates
   - **Issue**: Documentation-only changes may not be evaluated correctly
   - **Alternative Strategy**:
     - Verify that documentation changes are actually being tested
     - Check if there are code changes needed in addition to docs

5. **psf__requests-1921 & psf__requests-2931**: Session/request merging
   - **Issue**: Complex None value handling in header merging
   - **Alternative Strategy**:
     - Test with actual HTTP requests to see behavior
     - Understand the difference between "not set" and "explicitly None"
     - Check edge cases with various header combinations

6. **pytest-dev__pytest-7490**: Optional dependency handling
   - **Issue**: Using `importorskip` for optional dependencies
   - **Alternative Strategy**:
     - Verify that the importorskip pattern is correct
     - Check if tests need to be run with/without the optional dependency
     - Consider if the fix needs to handle both cases

7. **sphinx-doc__sphinx-7590**: C++ parser UDL handling
   - **Issue**: Complex parser state management for user-defined literals
   - **Alternative Strategy**:
     - Test with actual C++ code containing UDLs
     - Verify regex patterns match all UDL syntax variations
     - Check if parser state needs to be reset between matches

8. **sphinx-doc__sphinx-9230**: Regex token parsing
   - **Issue**: Complex bracket matching in regex patterns
   - **Alternative Strategy**:
     - Test with various bracket combinations
     - Verify the stack-based approach handles all edge cases
     - Check if escaped brackets need special handling

9. **sphinx-doc__sphinx-9658**: Type name extraction
   - **Issue**: Handling mocked/proxy objects with missing attributes
   - **Alternative Strategy**:
     - Test with actual mocked objects
     - Verify fallback logic handles all attribute combinations
     - Check if the repr-based fallback is correct

## System Prompt Improvements

The system prompt has been enhanced with:

1. **Problem-solving strategies** - Step-by-step approach to understanding issues
2. **Common fix patterns** - Based on successful solutions:
   - Metaclass/descriptor handling
   - Variable scoping
   - Exception handling
   - Reflected operations
   - Collection completeness
   - Import organization
   - Environment variables
3. **Testing strategy** - How to use tests effectively
4. **Edge case considerations** - Common pitfalls to avoid
5. **Troubleshooting guide** - What to do when stuck

## New Diagnostic Tools

Added to `SWEEnvironment`:

1. **`grep(pattern, file_pattern, case_sensitive)`**
   - Search for patterns in code
   - Useful for finding related code, error messages, similar patterns
   - Example: `grep("InheritDocstrings", "*.py")` to find all uses

2. **`find_files(name_pattern, file_type)`**
   - Find files by name pattern
   - Useful for locating test files, related modules
   - Example: `find_files("test_*.py")` to find all test files

3. **`run_test(test_path, test_name, verbose)`**
   - Run specific tests or test files
   - Useful for targeted testing and debugging
   - Example: `run_test("tests/test_misc.py", "test_inherit_docstrings")`

4. **`check_syntax(file_path)`**
   - Validate Python syntax before committing changes
   - Catches syntax errors early
   - Example: `check_syntax("astropy/utils/misc.py")`

## Recommendations for Future Improvements

1. **Better test understanding**: Add a tool to parse test files and extract test cases
2. **Code search**: Add semantic search to find similar code patterns
3. **Error analysis**: Add a tool to parse and analyze test failure output
4. **Incremental testing**: Run tests after each change, not just at the end
5. **Pattern matching**: Learn from successful patterns and suggest similar fixes
6. **Context awareness**: Better understanding of framework-specific patterns (Django, pytest, etc.)

## Usage

The improved agent now has:
- Enhanced system prompt with proven strategies
- Diagnostic tools for code exploration
- Better guidance on common fix patterns

Run the agent as before:
```bash
python run_agent.py --model gpt-4o-mini --max-steps 20 --output results
```

The agent will now:
1. Use the enhanced system prompt for better guidance
2. Have access to diagnostic tools for exploration
3. Follow proven patterns from successful fixes

