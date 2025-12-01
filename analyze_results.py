#!/usr/bin/env python3
"""
Analyze SWE-Bench results and generate summary table with recommendations.

This script:
1. Reads all trajectory files from results/ directory
2. Extracts step counts from trajectory context (counting assistant messages)
3. Determines status from evaluation JSON
4. Uses OpenAI API (reasoning model) to generate summaries with recommendations
5. Outputs a markdown table
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from openai import OpenAI


def count_steps_from_trajectory(traj_file: Path) -> int:
    """
    Count steps (LLM calls) from trajectory file by counting assistant messages in context.

    Args:
        traj_file: Path to trajectory JSON file

    Returns:
        Number of steps (assistant messages = LLM calls)
    """
    try:
        with open(traj_file) as f:
            traj = json.load(f)

        context = traj.get("context", "")
        if not context:
            return 0

        # Count assistant messages in context
        # Pattern: |MESSAGE(role="assistant", id=...)
        assistant_pattern = r'\|MESSAGE\(role="assistant"'
        matches = re.findall(assistant_pattern, context)
        return len(matches)
    except Exception as e:
        print(f"Warning: Could not count steps from {traj_file}: {e}")
        return 0


def get_status_from_evaluation(eval_file: Path, instance_id: str) -> str:
    """
    Determine status of an instance from evaluation JSON.

    Args:
        eval_file: Path to evaluation JSON file
        instance_id: Instance identifier

    Returns:
        Status: "resolved", "unresolved", "empty_patch", or "error"
    """
    try:
        with open(eval_file) as f:
            eval_data = json.load(f)

        if instance_id in eval_data.get("resolved_ids", []):
            return "resolved"
        elif instance_id in eval_data.get("unresolved_ids", []):
            return "unresolved"
        elif instance_id in eval_data.get("empty_patch_ids", []):
            return "empty_patch"
        elif instance_id in eval_data.get("error_ids", []):
            return "error"
        else:
            return "unknown"
    except Exception as e:
        print(f"Warning: Could not determine status for {instance_id}: {e}")
        return "unknown"


def extract_problem_statement(traj_file: Path) -> str:
    """
    Extract problem statement from trajectory file.

    Args:
        traj_file: Path to trajectory JSON file

    Returns:
        Problem statement text
    """
    try:
        with open(traj_file) as f:
            traj = json.load(f)

        context = traj.get("context", "")
        if not context:
            return ""

        # Extract first user message (problem statement)
        # Pattern: |MESSAGE(role="user", id=1)|\n...content...
        user_pattern = r'\|MESSAGE\(role="user", id=1\)\|\n(.*?)(?=\n----------------------------|\Z)'
        match = re.search(user_pattern, context, re.DOTALL)
        if match:
            return match.group(1).strip()

        return ""
    except Exception as e:
        print(f"Warning: Could not extract problem from {traj_file}: {e}")
        return ""


def extract_patch(traj_file: Path, preds_file: Path, instance_id: str) -> str:
    """
    Extract patch from trajectory or predictions file.

    Args:
        traj_file: Path to trajectory JSON file
        preds_file: Path to predictions JSON file
        instance_id: Instance identifier

    Returns:
        Patch content (or empty string)
    """
    # Try trajectory first
    try:
        with open(traj_file) as f:
            traj = json.load(f)
        submission = traj.get("info", {}).get("submission", "")
        if submission:
            return submission
    except Exception:
        pass

    # Fallback to predictions file
    try:
        with open(preds_file) as f:
            preds = json.load(f)
        instance_data = preds.get(instance_id, {})
        patch = instance_data.get("model_patch", "")
        if patch:
            return patch
    except Exception:
        pass

    return ""


def read_agent_code_files() -> Dict[str, str]:
    """
    Read agent code files for context.

    Returns:
        Dictionary mapping filename to content
    """
    files_to_read = ["agent.py", "run_agent.py", "envs.py", "llm.py"]
    code_context = {}

    for filename in files_to_read:
        filepath = Path(filename)
        if filepath.exists():
            try:
                with open(filepath) as f:
                    code_context[filename] = f.read()
            except Exception as e:
                print(f"Warning: Could not read {filename}: {e}")
                code_context[filename] = f"[Error reading {filename}]"
        else:
            code_context[filename] = f"[File {filename} not found]"

    return code_context


def generate_summary_with_recommendations(
    instance_id: str,
    problem: str,
    status: str,
    steps: int,
    patch: str,
    agent_code: Dict[str, str],
    model_name: str = "gpt-5.1"
) -> str:
    """
    Use OpenAI API to generate summary with recommendations.

    Args:
        instance_id: Instance identifier
        problem: Problem statement
        status: Instance status (resolved/unresolved/empty_patch/error)
        steps: Number of steps taken
        patch: Generated patch (may be empty)
        agent_code: Dictionary of agent code files
        model_name: OpenAI model to use (default: gpt-5.1)

    Returns:
        Formatted summary with recommendations
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Error: OPENAI_API_KEY not set"

    client = OpenAI(api_key=api_key)

    # Format agent code context
    agent_code_text = "\n\n".join([
        f"=== {filename} ===\n{content}"
        for filename, content in agent_code.items()
    ])

    # Truncate patch if too long
    patch_preview = patch[:2000] if len(patch) > 2000 else patch
    if len(patch) > 2000:
        patch_preview += "\n... [truncated]"

    # Truncate problem if too long
    problem_preview = problem[:1500] if len(problem) > 1500 else problem
    if len(problem) > 1500:
        problem_preview += "\n... [truncated]"

    prompt = f"""You are analyzing SWE-Bench agent results to provide recommendations for improving the agent.

Agent Code Context:
{agent_code_text}

Instance Analysis:
- Instance ID: {instance_id}
- Problem: {problem_preview}
- Status: {status}
- Steps taken: {steps}
- Patch generated: {patch_preview if patch else "[Empty patch]"}

Provide:
1. A 2-3 sentence summary of what happened (success or failure)
2. Specific recommendations for improving the agent code (agent.py, run_agent.py, envs.py, or llm.py) to increase accuracy on similar instances
3. Identify patterns or root causes that led to this outcome

Format your response as:
Summary: [what happened]
Recommendations: [actionable improvements to agent code]
Root Cause: [why this happened]"""

    # Retry logic for API calls
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Try using Responses API for reasoning models (gpt-5.1)
            # If that fails, fall back to chat completions
            try:
                response = client.responses.create(
                    model=model_name,
                    input=[
                        {"role": "system", "content": "You are an expert at analyzing software engineering agents and providing actionable recommendations."},
                        {"role": "user", "content": prompt}
                    ],
                    max_output_tokens=2000
                )
                # Extract text from Responses API format
                text = getattr(response, "output_text", None)
                if isinstance(text, str) and text:
                    summary = text.strip()
                else:
                    # Fallback extraction
                    output_items = getattr(response, "output", [])
                    text_parts = []
                    for item in output_items:
                        if isinstance(item, dict):
                            content = item.get("content", [])
                        else:
                            content = getattr(item, "content", [])
                        for content_item in content:
                            if isinstance(content_item, dict):
                                text_val = content_item.get("text")
                            elif hasattr(content_item, "text"):
                                text_val = content_item.text
                            else:
                                continue
                            if text_val:
                                text_parts.append(text_val)
                    summary = "\n\n".join(text_parts).strip() if text_parts else "No response generated"
            except Exception as e1:
                # Fallback to chat completions API
                try:
                    response = client.chat.completions.create(
                        model=model_name if model_name != "gpt-5.1" else "gpt-4o",  # Fallback model
                        messages=[
                            {"role": "system", "content": "You are an expert at analyzing software engineering agents and providing actionable recommendations."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=2000,
                        temperature=0.7
                    )
                    summary = response.choices[0].message.content.strip()
                except Exception as e2:
                    # If both fail, raise the first exception
                    raise e1 from e2

            return summary
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                print(f"  Retry {attempt + 1}/{max_retries} after {wait_time}s...")
                time.sleep(wait_time)
            else:
                return f"Error generating summary after {max_retries} attempts: {type(e).__name__}: {str(e)}"


def main():
    """Main function to analyze results and generate markdown table."""
    results_dir = Path("results")
    eval_file = Path("gpt-5-mini.my_evaluation_run.json")
    preds_file = results_dir / "preds.json"

    if not results_dir.exists():
        print(f"Error: Results directory {results_dir} not found")
        return

    if not eval_file.exists():
        print(f"Error: Evaluation file {eval_file} not found")
        return

    # Read agent code for context
    print("Reading agent code files...")
    agent_code = read_agent_code_files()

    # Find all trajectory files
    print("Finding trajectory files...")
    traj_files = list(results_dir.glob("**/*.traj.json"))
    print(f"Found {len(traj_files)} trajectory files")

    # Process each instance
    instances_data = []
    for i, traj_file in enumerate(sorted(traj_files), 1):
        instance_id = traj_file.stem.replace(".traj", "")
        instance_dir = traj_file.parent

        print(f"\n[{i}/{len(traj_files)}] Processing {instance_id}...")

        try:
            # Extract data
            steps = count_steps_from_trajectory(traj_file)
            status = get_status_from_evaluation(eval_file, instance_id)
            problem = extract_problem_statement(traj_file)
            patch = extract_patch(traj_file, preds_file, instance_id)

            # Generate summary with recommendations
            print(f"  Generating summary for {instance_id}...")
            summary = generate_summary_with_recommendations(
                instance_id=instance_id,
                problem=problem,
                status=status,
                steps=steps,
                patch=patch,
                agent_code=agent_code
            )

            instances_data.append({
                "instance_id": instance_id,
                "steps": steps,
                "status": status,
                "summary": summary
            })
        except Exception as e:
            print(f"  Error processing {instance_id}: {e}")
            instances_data.append({
                "instance_id": instance_id,
                "steps": 0,
                "status": "error",
                "summary": f"Error processing instance: {type(e).__name__}: {str(e)}"
            })

    # Generate markdown output
    output_file = Path("results_analysis.md")
    print(f"\nWriting results to {output_file}...")

    with open(output_file, "w") as f:
        # Header
        f.write("# SWE-Bench Results Analysis\n\n")
        f.write(f"Generated analysis of {len(instances_data)} instances.\n\n")

        # Statistics
        status_counts = defaultdict(int)
        for inst in instances_data:
            status_counts[inst["status"]] += 1

        f.write("## Summary Statistics\n\n")
        f.write(f"- Total instances: {len(instances_data)}\n")
        for status, count in sorted(status_counts.items()):
            f.write(f"- {status}: {count}\n")
        f.write("\n")

        # Parse summaries and recommendations for all instances
        for inst in instances_data:
            summary_lines = inst["summary"].split("\n")
            summary_parts = []
            recommendations_parts = []
            root_cause_parts = []

            in_summary = False
            in_recommendations = False
            in_root_cause = False

            for line in summary_lines:
                line_stripped = line.strip()
                if line_stripped.startswith("Summary:"):
                    in_summary = True
                    in_recommendations = False
                    in_root_cause = False
                    summary_parts.append(line_stripped.replace("Summary:", "").strip())
                elif line_stripped.startswith("Recommendations:"):
                    in_summary = False
                    in_recommendations = True
                    in_root_cause = False
                    recommendations_parts.append(line_stripped.replace("Recommendations:", "").strip())
                elif line_stripped.startswith("Root Cause:"):
                    in_summary = False
                    in_recommendations = False
                    in_root_cause = True
                    root_cause_parts.append(line_stripped.replace("Root Cause:", "").strip())
                elif in_summary:
                    if line_stripped:
                        summary_parts.append(line_stripped)
                    elif summary_parts and summary_parts[-1]:  # Preserve paragraph breaks
                        summary_parts.append("")
                elif in_recommendations:
                    if line_stripped:
                        recommendations_parts.append(line_stripped)
                    elif recommendations_parts and recommendations_parts[-1]:  # Preserve paragraph breaks
                        recommendations_parts.append("")
                elif in_root_cause:
                    if line_stripped:
                        root_cause_parts.append(line_stripped)
                    elif root_cause_parts and root_cause_parts[-1]:  # Preserve paragraph breaks
                        root_cause_parts.append("")

            # Join parts, preserving line breaks
            summary_text = "\n".join(summary_parts).strip()
            recommendations_text = "\n".join(recommendations_parts).strip()
            root_cause_text = "\n".join(root_cause_parts).strip()

            # Fallback if parsing failed
            if not summary_text:
                summary_text = inst["summary"]
            if not recommendations_text:
                recommendations_text = "No specific recommendations provided."

            # Add root cause to summary if present
            if root_cause_text:
                summary_text += "\n\n**Root Cause:** " + root_cause_text

            # Store parsed text
            inst["parsed_summary"] = summary_text
            inst["parsed_recommendations"] = recommendations_text

        # Table with links
        f.write("## Detailed Results\n\n")
        f.write("| Instance ID | Steps | Status | Summary | Recommendations |\n")
        f.write("|------------|-------|--------|---------|-----------------|\n")

        for inst in instances_data:
            instance_id = inst['instance_id']
            # Create anchor-friendly IDs (replace special chars with hyphens)
            anchor_id = instance_id.replace("__", "-").replace("_", "-")
            summary_link = f"[View Summary](#summary-{anchor_id})"
            recommendations_link = f"[View Recommendations](#recommendations-{anchor_id})"

            f.write(f"| {instance_id} | {inst['steps']} | {inst['status']} | {summary_link} | {recommendations_link} |\n")

        # Summary section
        f.write("\n## Summary\n\n")
        for inst in instances_data:
            instance_id = inst['instance_id']
            anchor_id = instance_id.replace("__", "-").replace("_", "-")
            f.write(f"### <a id=\"summary-{anchor_id}\"></a>**{instance_id}**\n\n")
            f.write(f"{inst['parsed_summary']}\n\n")

        # Recommendations section
        f.write("\n## Recommendations\n\n")
        for inst in instances_data:
            instance_id = inst['instance_id']
            anchor_id = instance_id.replace("__", "-").replace("_", "-")
            f.write(f"### <a id=\"recommendations-{anchor_id}\"></a>**{instance_id}**\n\n")
            f.write(f"{inst['parsed_recommendations']}\n\n")

        # Aggregated recommendations section
        f.write("\n## Aggregated Recommendations\n\n")
        f.write("Based on analysis of all instances, here are key recommendations:\n\n")
        # TODO: Could use LLM to aggregate recommendations across all instances
        f.write("(See individual instance recommendations above for specific recommendations)\n")

    print(f"\nAnalysis complete! Results written to {output_file}")


if __name__ == "__main__":
    main()

