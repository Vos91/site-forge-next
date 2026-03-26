#!/usr/bin/env python3
"""
SiteForge — Autonomous website builder using Claude Agent SDK.

Three-agent architecture inspired by Anthropic's harness design blog:
  Planner → Generator → Evaluator → (feedback loop) → Website

Usage:
  python forge.py "A portfolio site for an architecture photographer"
  python forge.py "Dutch cheese shop webshop" --max-iterations 3
  python forge.py "SaaS landing page for a project management tool" --skip-eval
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions


# ─── Configuration ──────────────────────────────────────────────────────────

PROMPTS_DIR = Path(__file__).parent / "prompts"

ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
]

# Playwright MCP server config (official Microsoft one)
PLAYWRIGHT_MCP = {
    "type": "stdio",
    "command": "npx",
    "args": ["@anthropic-ai/playwright-mcp@latest"],
}


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


# ─── Agent runners ──────────────────────────────────────────────────────────

async def run_agent(
    prompt: str,
    system_prompt: str,
    cwd: str,
    model: str,
    tools: list[str] | None = None,
    mcp_servers: dict | None = None,
    verbose: bool = False,
    live: bool = False,
    label: str = "Agent",
) -> str:
    """Run a single agent session and return the final text output."""
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        permission_mode="acceptEdits",
        cwd=cwd,
        model=model,
        allowed_tools=tools or ALLOWED_TOOLS,
    )

    if mcp_servers:
        options.mcp_servers = mcp_servers

    result_text = ""
    start = time.time()
    last_tool = ""

    print(f"\n{'='*60}")
    print(f"🤖 {label} started")
    print(f"{'='*60}")

    async for message in query(prompt=prompt, options=options):
        # Collect text from assistant messages
        if hasattr(message, "content"):
            for block in message.content if isinstance(message.content, list) else []:
                if hasattr(block, "text"):
                    result_text += block.text + "\n"
                    if live:
                        # Show full thinking/text output
                        for line in block.text.split("\n"):
                            print(f"  💭 {line}")
                    elif verbose:
                        print(f"  [{label}] {block.text[:200]}")

        # Show tool usage
        if hasattr(message, "content") and isinstance(message.content, list):
            for block in message.content:
                if hasattr(block, "name"):
                    tool_name = block.name
                    last_tool = tool_name
                    if live:
                        # Show tool with input details
                        tool_input = ""
                        if hasattr(block, "input") and isinstance(block.input, dict):
                            if "file_path" in block.input:
                                tool_input = f" → {block.input['file_path']}"
                            elif "path" in block.input:
                                tool_input = f" → {block.input['path']}"
                            elif "command" in block.input:
                                cmd = block.input["command"][:80]
                                tool_input = f" → {cmd}"
                        elapsed_now = time.time() - start
                        print(f"  🔧 [{elapsed_now:.0f}s] {tool_name}{tool_input}")
                    elif verbose:
                        print(f"  [{label}] 🔧 {tool_name}")

                # Show tool results in live mode
                if live and hasattr(block, "content") and isinstance(block.content, list):
                    for sub in block.content:
                        if hasattr(sub, "text") and sub.text:
                            # Show first few lines of tool output
                            lines = sub.text.strip().split("\n")
                            for line in lines[:5]:
                                print(f"      {line[:120]}")
                            if len(lines) > 5:
                                print(f"      ... ({len(lines) - 5} more lines)")

        # Show result
        if hasattr(message, "result"):
            elapsed = time.time() - start
            print(f"  ✅ {label} done ({elapsed:.0f}s)")

    return result_text


async def run_planner(user_prompt: str, project_dir: str, model: str, verbose: bool, live: bool = False) -> None:
    """Run the planner agent to create a product spec."""
    system_prompt = load_prompt("planner")
    prompt = f"""Create a detailed product spec for the following website:

"{user_prompt}"

Write the spec to `spec.md` in the current directory. Be ambitious about scope — go beyond what was literally asked for. Include 8-16 features with specific, testable acceptance criteria.

Also initialize progress.json with all features set to "todo"."""

    await run_agent(
        prompt=prompt,
        system_prompt=system_prompt,
        cwd=project_dir,
        model=model,
        verbose=verbose,
        live=live,
        label="Planner",
    )


async def run_generator(project_dir: str, model: str, verbose: bool, live: bool = False, feedback: str | None = None) -> None:
    """Run the generator agent to build the website."""
    system_prompt = load_prompt("generator")

    if feedback:
        prompt = f"""Read the evaluator's feedback in `evaluation.md` and the product spec in `spec.md`.

The evaluator found issues that need fixing. Here's a summary:

{feedback}

Fix the issues, improve the design based on feedback, and update progress.json.
Remember: if scores are below 5 on any criterion, consider a significant design pivot.
Commit your changes with descriptive messages."""
    else:
        prompt = """Read the product spec in `spec.md` and the progress in `progress.json`.

Set up the project (if not already set up) and implement features one at a time.

For each feature:
1. Implement it
2. Start the dev server and verify it works
3. Git commit with a descriptive message
4. Update progress.json

Build ALL features listed in the spec. Follow the design direction closely.
Make the site look professional and distinctive — NOT generic AI slop."""

    await run_agent(
        prompt=prompt,
        system_prompt=system_prompt,
        cwd=project_dir,
        model=model,
        verbose=verbose,
        live=live,
        label="Generator",
    )


async def run_evaluator(project_dir: str, model: str, verbose: bool, live: bool = False) -> dict:
    """Run the evaluator agent. Returns scores and pass/fail."""
    system_prompt = load_prompt("evaluator")

    prompt = """Read `spec.md` and `progress.json` to understand what was supposed to be built.

The site should be running on http://localhost:3000 (or check progress.json for the port).

Use Playwright to:
1. Open the site
2. Navigate through every page
3. Test all interactive features
4. Check desktop (1280px) and mobile (375px) viewports
5. Take screenshots of key pages

Score the site on the 4 criteria and write your full evaluation to `evaluation.md`.

Be critical and honest. Call out AI-slop patterns if you see them."""

    # Evaluator gets Playwright MCP for browser testing
    await run_agent(
        prompt=prompt,
        live=live,
        system_prompt=system_prompt,
        cwd=project_dir,
        model=model,
        tools=ALLOWED_TOOLS + ["mcp__playwright__*"],
        mcp_servers={"playwright": PLAYWRIGHT_MCP},
        verbose=verbose,
        label="Evaluator",
    )

    # Parse the evaluation results
    eval_path = Path(project_dir) / "evaluation.md"
    if eval_path.exists():
        eval_content = eval_path.read_text(encoding="utf-8")
        # Try to extract the overall score
        score = _extract_score(eval_content)
        return {"score": score, "content": eval_content, "passed": score >= 8.5}
    else:
        print("  ⚠️  Evaluator didn't write evaluation.md")
        return {"score": 0, "content": "", "passed": False}


def _extract_score(eval_content: str) -> float:
    """Try to extract the overall score from evaluation.md."""
    import re
    # Look for "Overall Score: X/10" pattern
    match = re.search(r"Overall Score:\s*(\d+(?:\.\d+)?)\s*/\s*10", eval_content)
    if match:
        return float(match.group(1))
    # Fallback: look for weighted score
    match = re.search(r"Weighted.*?(\d+(?:\.\d+)?)\s*/\s*10", eval_content)
    if match:
        return float(match.group(1))
    return 0.0


# ─── Main orchestrator ──────────────────────────────────────────────────────

async def forge(
    user_prompt: str,
    output_dir: str = "./output",
    max_iterations: int = 5,
    model: str = "claude-sonnet-4-5",
    skip_eval: bool = False,
    planner_only: bool = False,
    verbose: bool = False,
    live: bool = False,
) -> None:
    """Main orchestration loop: Planner → Generator → Evaluator → repeat."""

    # Setup project directory
    project_dir = os.path.abspath(output_dir)
    os.makedirs(project_dir, exist_ok=True)

    # Init git in project dir if not already
    if not os.path.exists(os.path.join(project_dir, ".git")):
        os.system(f"cd {project_dir} && git init && git checkout -b main 2>/dev/null")

    mode = "Planner only" if planner_only else ("Skip eval" if skip_eval else "Full harness")

    print(f"""
╔══════════════════════════════════════════════════════╗
║  🏗️  SiteForge — Autonomous Website Builder          ║
╠══════════════════════════════════════════════════════╣
║  Prompt: {user_prompt[:43]:<43} ║
║  Model:  {model:<43} ║
║  Output: {output_dir:<43} ║
║  Mode:   {mode:<43} ║
╚══════════════════════════════════════════════════════╝
""")

    total_start = time.time()

    # ── Phase 1: Planning ────────────────────────────────────────────────
    print("\n📋 Phase 1: Planning")
    print("─" * 40)
    await run_planner(user_prompt, project_dir, model, verbose, live=live)

    spec_path = Path(project_dir) / "spec.md"
    if not spec_path.exists():
        print("❌ Planner failed to create spec.md. Aborting.")
        return

    print(f"  📄 Spec created: {spec_path}")

    if planner_only:
        elapsed = time.time() - total_start
        print(f"\n{'='*60}")
        print(f"✅ Spec generated (planner-only mode)")
        print(f"⏱️  Total time: {elapsed:.0f}s")
        print(f"📄 Spec: {spec_path}")
        print(f"\nBekijk de spec, en run dan zonder --planner-only om te bouwen:")
        print(f"  python forge.py \"{user_prompt}\" --output-dir {output_dir} --skip-eval")
        print(f"{'='*60}")
        return

    # ── Phase 2: Building ────────────────────────────────────────────────
    print("\n🔨 Phase 2: Building")
    print("─" * 40)
    await run_generator(project_dir, model, verbose, live=live)

    if skip_eval:
        elapsed = time.time() - total_start
        print(f"""
╔══════════════════════════════════════════════════════╗
║  🏗️  SiteForge — Complete                            ║
╠══════════════════════════════════════════════════════╣
║  ⏱️  Total time: {elapsed/60:>5.1f} minutes{' '*28}║
║  📁 Output: {project_dir:<40} ║
║  Mode: Skip eval (Planner + Generator)               ║
╚══════════════════════════════════════════════════════╝

To view the site:
  cd {project_dir}
  npm install && npm run dev
""")
        return

    # ── Phase 3: Evaluate → Improve loop ─────────────────────────────────
    result = {"score": 0, "content": "", "passed": False}

    for iteration in range(1, max_iterations + 1):
        print(f"\n🔍 Phase 3: Evaluation (iteration {iteration}/{max_iterations})")
        print("─" * 40)

        result = await run_evaluator(project_dir, model, verbose, live=live)

        print(f"  📊 Score: {result['score']}/10")

        if result["passed"]:
            print(f"  ✅ PASSED — site meets quality threshold")
            break
        else:
            print(f"  ❌ FAILED — sending feedback to generator")

            if iteration < max_iterations:
                # Pass the full evaluation — don't truncate important feedback
                feedback_summary = result["content"][:8000]
                print(f"\n🔧 Phase 2b: Improving (iteration {iteration})")
                print("─" * 40)
                await run_generator(project_dir, model, verbose, live=live, feedback=feedback_summary)
            else:
                print(f"  ⚠️  Max iterations reached. Final score: {result['score']}/10")

    elapsed = time.time() - total_start

    print(f"""
╔══════════════════════════════════════════════════════╗
║  🏗️  SiteForge — Complete                            ║
╠══════════════════════════════════════════════════════╣
║  ⏱️  Total time: {elapsed/60:>5.1f} minutes{' '*28}║
║  📁 Output: {project_dir:<40} ║
║  📊 Final score: {result['score']}/10{' '*32}║
╚══════════════════════════════════════════════════════╝

To view the site:
  cd {project_dir}
  npm install && npm run dev
""")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SiteForge — Autonomous website builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python forge.py "Portfolio site for a photographer" --skip-eval
  python forge.py "Dutch cheese shop" --planner-only
  python forge.py "SaaS landing page" --max-iterations 3
        """,
    )
    parser.add_argument("prompt", help="Description of the website to build")
    parser.add_argument("--output-dir", default="./output", help="Output directory (default: ./output)")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max evaluator iterations (default: 5)")
    parser.add_argument("--model", default="claude-sonnet-4-5", help="Claude model (default: claude-sonnet-4-5)")
    parser.add_argument("--skip-eval", action="store_true", help="Skip evaluator (faster, less tokens)")
    parser.add_argument("--planner-only", action="store_true", help="Only generate the spec, don't build")
    parser.add_argument("--verbose", action="store_true", help="Show all agent output")
    parser.add_argument("--live", action="store_true", help="Live stream: show all tool calls, file paths, and agent thinking in real-time")

    args = parser.parse_args()

    asyncio.run(forge(
        user_prompt=args.prompt,
        output_dir=args.output_dir,
        max_iterations=args.max_iterations,
        model=args.model,
        skip_eval=args.skip_eval,
        planner_only=args.planner_only,
        verbose=args.verbose,
        live=args.live,
    ))


if __name__ == "__main__":
    main()
