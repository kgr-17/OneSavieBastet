"""
Claude-powered vulnerability analyzer for the Bastet competition.

Focused on the three zero-recall categories identified by the team agent:
  - Reentrancy     (P=0.0, R=0.0)
  - Liquidation    (P=0.0, R=0.0)
  - Oracle         (P=0.0, R=0.0)

These require cross-file reasoning and semantic understanding that rule-based
detectors miss. Claude analyzes the full repo context.

Usage (standalone):
    python src/claude_analyzer.py --repo-dir /path/to/repo --repo-id abc123

Usage (as module):
    from src.claude_analyzer import analyze_repo
    findings = analyze_repo(repo_dir="/path/to/repo", repo_id="abc123")
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CLAUDE_MODEL = "claude-opus-4-6"
MAX_FILE_BYTES = 60_000          # per-file cap before truncation
MAX_TOTAL_BYTES = 180_000        # total context cap for all files combined
SCAN_EXTENSIONS = {".sol", ".vy"}

# The three categories the team agent currently misses entirely
TARGET_CATEGORIES = ["Reentrancy", "Liquidation", "Oracle"]

# Known subtags from training data for these categories
SUBTAG_HINTS = {
    # Subtags aligned with TRAINING DATA vocabulary (not TAG_DEFINITIONS)
    # The competition scorer matches against training ground-truth subtags.
    "Reentrancy": [
        "Violating CEI / Missing nonReentrant",   # 9 instances in training
        "Cross-Function Reentrancy",               # 2 instances
        "ERC777 Callback",
    ],
    "Liquidation": [
        "No Incentive to Liquidate",              # 4 instances in training
        "Incorrect Parameter",                    # 2 instances
        "Unfair Liquidation",                     # 2 instances
        "Bypass Mechanism",
        "Bad Debt",
        "Does not match with Doc",
    ],
    "Oracle": [
        "Hardcoded Parameter",                    # 1 instance in training
        "Incorrect Formula",                      # 2 instances
        "Stale Value",                            # 2 instances
        "Price Manipulation / Arbitrage opportunity",
        "Invalid Validation",
        "Incorrect Parameter",
    ],
}

SYSTEM_PROMPT = """You are an expert smart contract security auditor specializing in DeFi protocol vulnerabilities.

Your task: analyze Solidity smart contract code and identify REAL, EXPLOITABLE vulnerabilities.
Focus only on high-confidence findings — false positives hurt the competition score.

You must respond with a JSON array. Each element is one finding:
{
  "tag": "<vulnerability category>",
  "subtag": "<specific type>",
  "severity": "High" or "Medium",
  "description": "<precise, technical description of the root cause and exploit path>"
}

Rules:
- Only include findings you are highly confident about (>80% confidence).
- Descriptions must explain the EXACT root cause and HOW it could be exploited.
- Avoid generic statements like "this may be vulnerable". Be specific about which function, state, or condition.
- A repo with no real vulnerabilities in a given category should return an empty array.
- Do NOT hallucinate vulnerabilities that are not clearly supported by the code.
"""


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_repo_files(repo_dir: str) -> dict[str, str]:
    """Load all Solidity/Vyper files from a repo directory."""
    repo_path = Path(repo_dir)
    files: dict[str, str] = {}

    for ext in SCAN_EXTENSIONS:
        for fpath in sorted(repo_path.rglob(f"*{ext}")):
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                rel = str(fpath.relative_to(repo_path))
                files[rel] = content
            except Exception:
                continue

    return files


def build_context(files: dict[str, str]) -> str:
    """Pack file contents into a context string, respecting byte limits."""
    parts: list[str] = []
    total = 0

    for rel_path, content in files.items():
        if total >= MAX_TOTAL_BYTES:
            parts.append(f"\n[... remaining files omitted due to size limit ...]")
            break

        if len(content) > MAX_FILE_BYTES:
            content = content[:MAX_FILE_BYTES] + f"\n[... {rel_path} truncated ...]"

        chunk = f"\n\n=== FILE: {rel_path} ===\n{content}"
        total += len(chunk)
        parts.append(chunk)

    return "".join(parts)


# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------

def call_claude(context: str, category: str) -> list[dict]:
    """Ask Claude to find vulnerabilities in one specific category."""
    client = anthropic.Anthropic()

    subtag_hint = ", ".join(SUBTAG_HINTS.get(category, []))
    user_message = f"""Analyze the following smart contract repository for **{category}** vulnerabilities only.

Known subtag examples for this category: {subtag_hint}

Look carefully for:
{"- Reentrancy: functions that make external calls before updating state (CEI violation), missing nonReentrant guards, cross-function reentrancy via shared state, read-only reentrancy in view functions used for pricing." if category == "Reentrancy" else ""}
{"- Liquidation: incorrect health-factor formulas, wrong collateral/debt accounting, missing or bypassable liquidation checks, incentive misalignment that blocks liquidations, precision errors in threshold calculations." if category == "Liquidation" else ""}
{"- Oracle: reliance on spot price from a single DEX (manipulable), missing staleness checks on Chainlink feeds, missing bounds validation on returned price, TWAP windows too short to prevent manipulation, price used before validation." if category == "Oracle" else ""}

Return a JSON array of findings. Empty array [] if none found.

{context}"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        thinking={"type": "enabled", "budget_tokens": 3000},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract text response
    text = ""
    for block in response.content:
        if block.type == "text":
            text = block.text
            break

    # Parse JSON from response
    return _parse_json_findings(text, category)


def _parse_json_findings(text: str, category: str) -> list[dict]:
    """Extract JSON array from Claude's response."""
    # Try to find a JSON array in the response
    text = text.strip()

    # Look for ```json ... ``` block
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Find first [ to last ]
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
        else:
            return []

    try:
        findings = json.loads(text)
        if not isinstance(findings, list):
            return []

        # Validate and normalize each finding
        valid = []
        for f in findings:
            if not isinstance(f, dict):
                continue
            tag = f.get("tag", category)
            subtag = f.get("subtag", "")
            severity = f.get("severity", "Medium")
            description = f.get("description", "")

            if not subtag or not description:
                continue
            if severity not in ("High", "Medium"):
                severity = "Medium"

            valid.append({
                "tag": tag,
                "subtag": subtag,
                "severity": severity,
                "description": description.strip(),
            })

        return valid

    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze_repo(
    repo_dir: str,
    repo_id: str,
    categories: Optional[list[str]] = None,
    verbose: bool = False,
) -> list[dict]:
    """
    Analyze a repository for target vulnerability categories using Claude.

    Returns a list of findings dicts, each with:
      repo_path, tag, subtag, severity, description
    """
    if categories is None:
        categories = TARGET_CATEGORIES

    files = load_repo_files(repo_dir)
    if not files:
        if verbose:
            print(f"[claude_analyzer] No source files found in {repo_dir}", file=sys.stderr)
        return []

    context = build_context(files)
    if verbose:
        print(
            f"[claude_analyzer] {repo_id}: {len(files)} files, "
            f"{len(context):,} bytes of context",
            file=sys.stderr,
        )

    all_findings: list[dict] = []

    for category in categories:
        if verbose:
            print(f"[claude_analyzer]   Scanning for {category}...", file=sys.stderr)
        try:
            raw = call_claude(context, category)
            for finding in raw:
                all_findings.append(
                    {
                        "repo_path": repo_id,
                        "tag": finding["tag"],
                        "subtag": finding["subtag"],
                        "severity": finding["severity"],
                        "description": finding["description"],
                    }
                )
            if verbose:
                print(
                    f"[claude_analyzer]   {category}: {len(raw)} finding(s)",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(
                f"[claude_analyzer] ERROR on {repo_id}/{category}: {exc}",
                file=sys.stderr,
            )

    return all_findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyze a smart contract repo with Claude for Reentrancy/Liquidation/Oracle bugs."
    )
    parser.add_argument("--repo-dir", required=True, help="Path to the repo directory")
    parser.add_argument("--repo-id", required=True, help="Repository identifier (used as repo_path in output)")
    parser.add_argument(
        "--categories",
        nargs="+",
        default=TARGET_CATEGORIES,
        help=f"Categories to scan (default: {TARGET_CATEGORIES})",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--output", default="-", help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    findings = analyze_repo(
        repo_dir=args.repo_dir,
        repo_id=args.repo_id,
        categories=args.categories,
        verbose=args.verbose,
    )

    result = json.dumps(findings, indent=2)

    if args.output == "-":
        print(result)
    else:
        Path(args.output).write_text(result)
        if args.verbose:
            print(f"[claude_analyzer] Written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
