# baseline_v6: Improved description templates (audit-report style)
# vs baseline_v4:
#   1. make_description() rewritten with keyword-rich, audit-specific templates per (tag, subtag)
#   2. pick_representative_description() now prefers make_description() over training descriptions
#      (training descriptions are repo-specific noise; our templates are semantically central)
#   3. Default max_per_repo = 10, min_per_repo = 5 (same as v4)
import argparse
import csv
import hashlib
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path


EMPTY_TOKEN = "empty"
DEFAULT_TARGET_ROWS = 400
DEFAULT_MAX_FINDINGS_PER_REPO = 10
DEFAULT_PRIOR_POOL_SIZE = 40
DEFAULT_TAG_DIVERSITY_BONUS = 0.02
DEFAULT_REPEAT_TAG_PENALTY = 0.01
DEFAULT_MIN_FINDINGS_PER_REPO = 5
DEFAULT_HIGH_SEVERITY_POOL_SIZE = 0
DEFAULT_HIGH_SEVERITY_POOL_BONUS = 0.0
DEFAULT_INTRINSIC_HIGH_SEVERITY_BONUS = 0.0
DEFAULT_SCAN_EXTENSIONS = {".sol", ".vy", ".ts", ".js"}
DEFAULT_TOP_K_SIMILAR = 3
DEFAULT_SIMILARITY_THRESHOLD = 0.08
DEFAULT_BYTE_LIMIT = 300000


FINGERPRINT_KEYWORDS = [
    "transfer",
    "transferfrom",
    "approve",
    "allowance",
    "mint",
    "burn",
    "swap",
    "deposit",
    "withdraw",
    "liquidat",
    "oracle",
    "proxy",
    "delegatecall",
    "selfdestruct",
    "onlyowner",
    "require",
    "revert",
    "balanceof",
    "totalsupply",
    "stake",
    "reward",
    "flash",
    "loan",
    "borrow",
    "collateral",
    "repay",
    "governance",
    "vote",
    "proposal",
    "timelock",
    "permit",
    "signature",
    "ecrecover",
    "nonce",
    "erc20",
    "erc721",
    "erc1155",
    "upgradeable",
    "initializ",
    "ownable",
    "pausable",
    "reentrancy",
    "safetransfer",
    "unchecked",
    "assembly",
]


OBSERVED_RULES = [
    {
        "name": "reentrancy_value_call",
        "tag": "Reentrancy",
        "subtag": "Violating CEI / Missing nonReentrant",
        "severity": "High",
        "patterns": [r"\.call\s*\{[^}]*value\s*:"],
        "must_not": [r"nonReentrant", r"ReentrancyGuard"],
    },
    {
        "name": "reentrancy_callback",
        "tag": "Reentrancy",
        "subtag": "Violating CEI / Missing nonReentrant",
        "severity": "Medium",
        "patterns": [r"onERC721Received", r"onERC1155Received", r"tokensReceived"],
        "must_not": [r"nonReentrant", r"ReentrancyGuard"],
    },
    {
        "name": "invalid_validation_address",
        "tag": "Input Validation",
        "subtag": "Invalid Validation",
        "severity": "Medium",
        "patterns": [r"function\s+\w+\s*\([^)]*address\s+\w+"],
        "must_not": [r"address\s*\(\s*0\s*\)", r"!=\s*address\s*\(\s*0\s*\)"],
    },
    {
        "name": "invalid_validation_signature",
        "tag": "Input Validation",
        "subtag": "Invalid Validation",
        "severity": "High",
        "patterns": [r"ecrecover\s*\("],
        "must_not": [r"!=\s*address\s*\(\s*0\s*\)", r"\bs\s*<=", r"\bv\s*=="],
    },
    {
        "name": "dos_out_of_gas",
        "tag": "DoS",
        "subtag": "Out of Gas",
        "severity": "Medium",
        "patterns": [r"for\s*\([^)]*;\s*[^;]*<\s*\w+\.length\s*;", r"while\s*\("],
        "must_not": [],
    },
    {
        "name": "dos_receive",
        "tag": "DoS",
        "subtag": "payable / receive()",
        "severity": "Medium",
        "patterns": [r"\breceive\s*\(\s*\)\s*external\s*payable", r"\bfallback\s*\(\s*\)\s*external\s*payable"],
        "must_not": [],
    },
    {
        "name": "access_control_centralized",
        "tag": "Access Control",
        "subtag": "Centralization Risk",
        "severity": "Medium",
        "patterns": [r"function\s+(?:set|update|change|pause|unpause|mint|burn|withdraw)\w*\s*\([^)]*\)\s*(?:public|external)"],
        "must_not": [r"onlyOwner", r"onlyAdmin", r"onlyRole", r"AccessControl", r"Ownable"],
    },
    {
        "name": "erc20_missing_return_check",
        "tag": "ERC20",
        "subtag": "Missing Return Check",
        "severity": "Medium",
        "patterns": [r"\.(?:transfer|transferFrom)\s*\("],
        "must_not": [r"safeTransfer", r"safeTransferFrom", r"require\s*\([^)]*\.(?:transfer|transferFrom)"],
    },
    {
        "name": "erc20_safe_approve",
        "tag": "ERC20",
        "subtag": "safeApprove",
        "severity": "Medium",
        "patterns": [r"\.approve\s*\("],
        "must_not": [r"safeApprove", r"forceApprove", r"\.approve\s*\([^)]*,\s*0\s*\)"],
    },
    {
        "name": "arithmetic_precision_loss",
        "tag": "Arithmetic",
        "subtag": "Precision Loss",
        "severity": "Medium",
        "patterns": [r"\/\s*\w+\s*\*", r"\b\d+\s*/\s*\w+\s*\*"],
        "must_not": [],
    },
    {
        "name": "oracle_price_manipulation",
        "tag": "Oracle",
        "subtag": "Price Manipulation / Arbitrage opportunity",
        "severity": "High",
        "patterns": [r"getReserves\s*\(", r"slot0\s*\(", r"balanceOf\s*\([^)]*\)\s*[*/]"],
        "must_not": [],
    },
    {
        "name": "mev_front_run",
        "tag": "MEV",
        "subtag": "Front Run",
        "severity": "Medium",
        "patterns": [r"swap\w*\([^)]*,\s*0\s*[,)]]", r"deadline\s*=\s*block\.timestamp", r"block\.timestamp\s*\+\s*\d+"],
        "must_not": [],
    },
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a stronger Bastet baseline inspired by rule + similarity ideas."
    )
    parser.add_argument("--train-csv", default="train.csv")
    parser.add_argument("--test-csv", default="test.csv")
    parser.add_argument("--sample-submission", default="submission_example.csv")
    parser.add_argument("--output", default="outputs/submission_v6.csv")
    parser.add_argument("--train-repo-root", default="", help="Optional directory containing extracted train repos.")
    parser.add_argument("--test-repo-root", default="", help="Optional directory containing extracted test repos.")
    parser.add_argument(
        "--mode",
        choices=["prior", "similarity", "hybrid"],
        default="hybrid",
        help="Prior works from CSVs only. Similarity/Hybrid use repo folders when provided.",
    )
    parser.add_argument("--target-rows", type=int, default=DEFAULT_TARGET_ROWS)
    parser.add_argument("--max-findings-per-repo", type=int, default=DEFAULT_MAX_FINDINGS_PER_REPO)
    parser.add_argument("--prior-pool-size", type=int, default=DEFAULT_PRIOR_POOL_SIZE)
    parser.add_argument("--tag-diversity-bonus", type=float, default=DEFAULT_TAG_DIVERSITY_BONUS)
    parser.add_argument("--repeat-tag-penalty", type=float, default=DEFAULT_REPEAT_TAG_PENALTY)
    parser.add_argument("--min-findings-per-repo", type=int, default=DEFAULT_MIN_FINDINGS_PER_REPO)
    parser.add_argument("--high-severity-pool-size", type=int, default=DEFAULT_HIGH_SEVERITY_POOL_SIZE)
    parser.add_argument("--high-severity-pool-bonus", type=float, default=DEFAULT_HIGH_SEVERITY_POOL_BONUS)
    parser.add_argument("--intrinsic-high-severity-bonus", type=float, default=DEFAULT_INTRINSIC_HIGH_SEVERITY_BONUS)
    parser.add_argument("--top-k-similar", type=int, default=DEFAULT_TOP_K_SIMILAR)
    parser.add_argument("--similarity-threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD)
    parser.add_argument("--pad-token", default=EMPTY_TOKEN)
    return parser.parse_args()


def load_csv_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path, rows, fieldnames):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def stable_hash(value):
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def split_labels(raw_value):
    return [part.strip() for part in str(raw_value).split(",") if part.strip()]


def normalize_description(text):
    return " ".join(str(text).replace("\r", " ").replace("\n", " ").split())


def make_description(tag, subtag):
    """v6: Keyword-rich, audit-report-style descriptions per (tag, subtag).
    These are semantically close to real audit descriptions and score better on BGE 0.7 threshold
    than repo-specific training descriptions copied to the wrong test repo.
    """
    key = (tag, subtag)

    # ── Reentrancy ──
    if key == ("Reentrancy", "Violating CEI / Missing nonReentrant"):
        return (
            "External call is executed before state variables are updated, violating the Checks-Effects-Interactions "
            "pattern. Without a nonReentrant guard, an attacker can reenter the function through a fallback or "
            "receive callback before the balance or accounting update completes, allowing the same funds to be "
            "withdrawn or processed multiple times. This results in fund drainage or corrupted protocol state."
        )
    if key == ("Reentrancy", "Cross-Function Reentrancy"):
        return (
            "A cross-function reentrancy vulnerability exists where an external call in one function allows an "
            "attacker to invoke a related function before state updates are finalized. Because both functions "
            "share state variables that are not yet updated, the attacker can exploit the inconsistency to "
            "bypass intended limits, double-spend, or extract excess value."
        )

    # ── Input Validation ──
    if key == ("Input Validation", "Invalid Validation"):
        return (
            "A critical function parameter or return value is not properly validated before use. The missing or "
            "incorrect validation allows an attacker to supply boundary values, zero addresses, or malformed "
            "inputs that bypass intended access checks or trigger unexpected execution paths. This can result "
            "in unauthorized state changes, asset theft, or invariant violations."
        )
    if key == ("Input Validation", "Bypass Mechanism"):
        return (
            "A validation check can be bypassed through a specific input pattern or call sequence. The incomplete "
            "guard allows an attacker to skip intended restrictions, pass invalid data as legitimate, or exploit "
            "a path that was assumed to be unreachable. This enables unauthorized operations or access."
        )
    if key == ("Input Validation", "Incorrect Parameter"):
        return (
            "A function uses an incorrect or unvalidated parameter in a critical computation or access check. "
            "When the parameter contains an unexpected value, the resulting calculation or comparison is wrong, "
            "allowing an attacker to influence outcomes, bypass limits, or trigger unintended behavior."
        )
    if key == ("Input Validation", "Hardcoded Parameter"):
        return (
            "A critical threshold, address, or configuration value is hardcoded rather than set through a "
            "governance-controlled parameter. The fixed value may become incorrect as protocol conditions change, "
            "and cannot be updated without a contract upgrade, creating a systemic risk that increases over time."
        )
    if key == ("Input Validation", "Missing Return Check"):
        return (
            "The return value of an external call or token operation is not verified. For non-standard tokens or "
            "contracts that return false instead of reverting on failure, this causes the caller to continue as "
            "if the operation succeeded when it did not, leading to accounting errors or lost funds."
        )

    # ── Accounting Error ──
    if key == ("Accounting Error", "State Update Inconsistency"):
        return (
            "State variables tracking balances, shares, debt, or rewards are updated in an inconsistent order "
            "or with stale values. When a sequence of operations updates one variable without correspondingly "
            "updating a related variable, the protocol's internal accounting diverges from actual token balances, "
            "enabling value extraction or creating insolvency conditions."
        )
    if key == ("Accounting Error", "Incorrect Formula"):
        return (
            "A mathematical formula used to compute balances, shares, fees, or rewards contains an error. The "
            "incorrect calculation produces results that diverge from the intended protocol invariant, allowing "
            "users to receive more or less value than expected and enabling systematic extraction over time."
        )
    if key == ("Accounting Error", "Incorrect Parameter"):
        return (
            "An accounting function uses a wrong input value, such as a stale balance, an unupdated accumulator, "
            "or a parameter from the wrong context. The resulting computation is incorrect and causes the protocol "
            "to misallocate value, underpay or overpay users, or violate economic invariants."
        )
    if key == ("Accounting Error", "Precision Loss"):
        return (
            "Integer division or token-unit conversion discards fractional precision that should be tracked. "
            "The accumulated rounding error across many operations allows value to disappear from the system or "
            "be captured by users who perform repeated small interactions to extract the accumulated discrepancy."
        )

    # ── Access Control ──
    if key == ("Access Control", "Centralization Risk"):
        return (
            "A privileged function can be called by a single admin key without time-lock, multi-sig, or "
            "governance approval. A compromised or malicious owner can change critical parameters, pause "
            "operations indefinitely, drain funds, or alter protocol mechanics in ways that harm users with "
            "no on-chain recourse or warning period."
        )
    if key == ("Access Control", "Bypass Mechanism"):
        return (
            "An access control check can be bypassed through a specific call pattern, inherited function, or "
            "proxy mechanism. An unauthorized caller can invoke a protected function by exploiting the gap "
            "in the access control logic, leading to privilege escalation or unauthorized state changes."
        )
    if key == ("Access Control", "State Update Inconsistency"):
        return (
            "Role or permission state is not updated atomically or is left in an intermediate state after "
            "access control operations. This creates a window where unauthorized access is possible or where "
            "previously revoked roles remain effective, enabling privilege escalation or bypassing intended controls."
        )
    if key == ("Access Control", "Role Takeover"):
        return (
            "A role transfer or ownership change function does not properly validate the new recipient or "
            "does not require confirmation from the new owner. An attacker can trigger the transfer to an "
            "unintended address or exploit a two-step transfer that lacks proper verification, taking control "
            "of administrative functions."
        )

    # ── Arithmetic ──
    if key == ("Arithmetic", "Precision Loss"):
        return (
            "Integer arithmetic performs division before multiplication or uses mismatched decimal precisions, "
            "causing significant rounding loss. Over multiple operations the accumulated truncation allows "
            "value to be silently dropped from accounting or extracted by users who exploit the rounding direction."
        )
    if key == ("Arithmetic", "Token Decimal"):
        return (
            "Token decimal handling does not correctly normalize values when interacting with tokens of "
            "non-standard decimal counts. When an 18-decimal assumption is applied to a 6-decimal token "
            "or vice versa, calculations of prices, shares, or collateral are off by many orders of magnitude, "
            "enabling massive over- or under-valuation."
        )
    if key == ("Arithmetic", "Unsafe Downcast"):
        return (
            "A value is cast from a larger integer type to a smaller one without checking for overflow. "
            "When the actual value exceeds the target type range, the cast silently truncates the high bits, "
            "producing a completely wrong result that corrupts balances, timestamps, or array indices."
        )
    if key == ("Arithmetic", "Rounding Error"):
        return (
            "Rounding direction is not enforced consistently: operations that should round in favor of the "
            "protocol instead round in favor of the user. Repeated interactions exploit the systematic rounding "
            "bias to extract value that accumulates into a significant loss for the protocol."
        )

    # ── Logic Error ──
    if key == ("Logic Error", "Bad Condition"):
        return (
            "A conditional check uses the wrong comparison operator, wrong variable, or inverted logic. "
            "The incorrect condition causes the contract to take the wrong branch in a security-critical "
            "decision, allowing operations that should be blocked to proceed or blocking legitimate operations "
            "that should be allowed."
        )
    if key == ("Logic Error", "Implementation Error"):
        return (
            "The implementation of a key protocol function deviates from the intended specification. The "
            "divergence between the intended logic and the actual code creates an exploitable gap where an "
            "attacker can trigger incorrect state transitions, bypass invariants, or cause the protocol to "
            "behave in an unintended way under specific conditions."
        )
    if key == ("Logic Error", "State Update Inconsistency"):
        return (
            "State is updated in an order or manner that leaves the contract in an inconsistent intermediate "
            "state. When a sequence of operations is interrupted or when multiple state variables must be "
            "updated together, the resulting inconsistency can be exploited to read stale values or trigger "
            "incorrect behavior in dependent functions."
        )
    if key == ("Logic Error", "Incorrect Parameter"):
        return (
            "A function is called with a wrong argument, or reads from the wrong storage slot or struct "
            "field. The incorrect parameter propagates through the computation and produces a wrong result "
            "that corrupts state, misallocates value, or bypasses a security check."
        )

    # ── DoS ──
    if key == ("DoS", "Bad Condition"):
        return (
            "A reachable require or revert condition can be triggered by an attacker or by normal market "
            "conditions, causing core protocol functions to become permanently or indefinitely blocked. "
            "The denial-of-service prevents users from withdrawing funds, executing transactions, or "
            "otherwise interacting with the protocol."
        )
    if key == ("DoS", "Out of Gas"):
        return (
            "An unbounded loop or operation that iterates over a user-controlled or growing array can "
            "exceed the block gas limit. As the array size grows, the transaction cost increases until "
            "the operation becomes impossible to execute, permanently blocking the affected functionality."
        )
    if key == ("DoS", "payable / receive()"):
        return (
            "A payable fallback or receive function accepts ETH without restriction, or contract logic "
            "assumes a push payment will always succeed. An attacker can force-send ETH or cause a "
            "payment to fail, disrupting state-dependent logic that assumes successful transfers."
        )
    if key == ("DoS", "Missing Functionality"):
        return (
            "A function critical for protocol operation is missing, unreachable, or permanently disabled. "
            "Users cannot perform a required action such as withdrawing funds, claiming rewards, or "
            "updating configuration, creating a permanent lock or loss of user assets."
        )

    # ── ERC20 ──
    if key == ("ERC20", "Missing Return Check"):
        return (
            "The return value of an ERC20 transfer or transferFrom call is not verified. Non-standard tokens "
            "that return false on failure rather than reverting will silently fail, but the calling contract "
            "continues execution as if the transfer succeeded, causing accounting to diverge from actual balances."
        )
    if key == ("ERC20", "Fee On Transfer Token"):
        return (
            "Token integration logic does not account for fee-on-transfer tokens that deliver less to the "
            "recipient than the amount specified in the transfer call. The protocol records the full transfer "
            "amount but receives fewer tokens, causing accounting to overstate balances and enabling "
            "extraction of the discrepancy."
        )
    if key == ("ERC20", "safeApprove"):
        return (
            "A direct ERC20 approve call is used instead of the safeApprove or increaseAllowance pattern. "
            "Setting a non-zero allowance when the current allowance is also non-zero is vulnerable to an "
            "approval race condition where an attacker front-runs the second approval to spend tokens under "
            "both the old and new allowance."
        )
    if key == ("ERC20", "Rebase Token"):
        return (
            "The protocol does not handle rebasing or elastic supply tokens correctly. When a token's balance "
            "changes automatically due to rebasing, the protocol's recorded balance diverges from the actual "
            "balance, enabling users to extract the difference or causing protocol insolvency."
        )

    # ── Oracle ──
    if key == ("Oracle", "Stale Value"):
        return (
            "Oracle price data is consumed without checking its freshness. If the oracle has not updated "
            "recently due to a sequencer outage, low volatility threshold, or attack, stale prices cause "
            "the protocol to compute incorrect collateral values, enabling undercollateralized borrowing, "
            "unjust liquidations, or price arbitrage at stale rates."
        )
    if key == ("Oracle", "Price Manipulation / Arbitrage opportunity"):
        return (
            "The protocol uses a manipulable spot price, AMM reserve ratio, or TWAP with an insufficient "
            "observation window as a price oracle. An attacker can use a flash loan to temporarily distort "
            "the price reference, execute a profitable action at the manipulated price, then restore the "
            "price within the same transaction, extracting value without lasting capital commitment."
        )
    if key == ("Oracle", "Hardcoded Parameter"):
        return (
            "A price feed address, heartbeat threshold, or staleness tolerance is hardcoded and cannot be "
            "updated without a contract upgrade. As market conditions change or the oracle infrastructure "
            "evolves, the hardcoded value becomes incorrect, causing the protocol to consume invalid price "
            "data without any recourse."
        )

    # ── Governance ──
    if key == ("Governance", "Bad Condition"):
        return (
            "A governance proposal validation condition is incorrect, allowing invalid proposals to pass "
            "or preventing valid proposals from executing. An attacker can craft a proposal that bypasses "
            "intended safety checks, or legitimate governance actions may be permanently blocked by an "
            "over-restrictive condition."
        )
    if key == ("Governance", "Incorrect Parameter"):
        return (
            "A governance function applies a parameter update without sufficient bounds checking or uses "
            "the wrong parameter in the update logic. This allows the protocol to be misconfigured through "
            "governance, setting critical values outside safe operating ranges or updating the wrong "
            "configuration variable."
        )

    # ── Liquidation ──
    if key == ("Liquidation", "No Incentive to Liquidate"):
        return (
            "The liquidation incentive is too small or can become negative, making liquidation unprofitable "
            "for external liquidators. Undercollateralized positions are not liquidated in a timely manner "
            "because no external party has a financial reason to do so, causing bad debt to accumulate and "
            "threatening protocol solvency."
        )
    if key == ("Liquidation", "Incorrect Parameter"):
        return (
            "The liquidation function uses a wrong parameter when computing collateral ratios, liquidation "
            "bonuses, or debt repayment amounts. The incorrect calculation produces wrong liquidation "
            "thresholds, over- or under-seizes collateral, or leaves positions in an incorrect state "
            "after liquidation."
        )

    # ── Slippage ──
    if key == ("Slippage", "Missing minOut / maxAmount"):
        return (
            "A swap or liquidity operation does not enforce a minimum output amount or maximum slippage "
            "parameter. Without slippage protection, a sandwich attacker or MEV bot can manipulate the "
            "pool price before and after the transaction to extract value, causing the user to receive "
            "significantly less than the fair market rate."
        )
    if key == ("Slippage", "Invalid Slippage Control / Missing slippage check"):
        return (
            "The slippage protection mechanism is implemented incorrectly or checks the wrong value. "
            "Despite having a minOut parameter, the validation is bypassed or applied after the critical "
            "price-sensitive operation, leaving transactions vulnerable to sandwich attacks and front-running."
        )

    # ── Cross-Chain ──
    if key == ("Cross-Chain", "No Recovery Mechanism"):
        return (
            "Tokens or messages that fail during cross-chain transmission have no recovery path. If a "
            "bridge message fails on the destination chain, the originating chain has already locked or "
            "burned tokens with no mechanism to return them, causing permanent loss of user funds."
        )

    # ── Signature ──
    if key == ("Signature", "Invalid Validation"):
        return (
            "Signature validation does not check all required fields, such as the recovered address being "
            "non-zero, the message domain separator being correct, or the nonce being consumed. An attacker "
            "can craft or reuse a signature that passes the incomplete check to authorize unauthorized "
            "operations or replay a previously used authorization."
        )

    # ── Flash Loan ──
    if key == ("Flash Loan", "Price Manipulation / Arbitrage opportunity"):
        return (
            "Protocol logic that depends on token balances, reserve ratios, or spot prices is vulnerable to "
            "flash loan price manipulation. An attacker borrows a large amount in a single transaction, "
            "manipulates the price reference to a favorable level, performs an arbitrage or extractive "
            "action, then repays the loan, all within one atomic transaction."
        )

    # ── Fallback by tag ──
    combined = f"{tag.lower()} {subtag.lower()}"

    if "reentrancy" in combined or "cei" in combined:
        return (
            "An external call is made before state variables are updated, enabling reentrancy. An attacker "
            "can reenter the function through a fallback or token callback before accounting changes are "
            "finalized, withdrawing funds or executing operations multiple times beyond intended limits."
        )
    if "input validation" in combined or "invalid validation" in combined or "incorrect parameter" in combined:
        return (
            "A critical parameter, return value, or address is not properly validated before use in a "
            "security-sensitive operation. Missing or incorrect validation allows an attacker to supply "
            "out-of-range, zero, or specially crafted inputs that bypass access controls or corrupt state."
        )
    if "accounting error" in combined or "state update" in combined or "incorrect formula" in combined:
        return (
            "State variables tracking value, shares, or positions are updated incorrectly or inconsistently. "
            "The accounting error causes the protocol to compute wrong balances, enabling value extraction "
            "or creating conditions where the protocol's liabilities exceed its assets."
        )
    if "dos" in combined or "out of gas" in combined or "bad condition" in combined:
        return (
            "A reachable failure condition or unbounded operation can permanently block core protocol "
            "functions. Under specific inputs or accumulated state, legitimate user transactions revert "
            "or become too expensive to execute, creating a denial-of-service."
        )
    if "access control" in combined or "centralization" in combined:
        return (
            "Sensitive protocol functions lack sufficient access restrictions or rely on a single privileged "
            "key. A compromised or malicious admin can exploit this to change parameters, drain funds, "
            "or halt the protocol without meaningful on-chain checks or time-delays."
        )
    if "arithmetic" in combined or "precision" in combined or "rounding" in combined or "decimal" in combined:
        return (
            "Arithmetic operations do not preserve the required precision or handle token decimal differences "
            "correctly. Accumulated rounding errors or unit mismatches create exploitable discrepancies that "
            "allow value extraction or cause protocol invariants to drift over time."
        )
    if "erc20" in combined or "missing return" in combined or "fee on transfer" in combined:
        return (
            "ERC20 token integration does not account for non-standard behavior such as missing return values, "
            "fee-on-transfer, or rebasing. The protocol's accounting assumes standard behavior and diverges "
            "from actual token balances, creating exploitable gaps."
        )
    if "oracle" in combined or "price manipulation" in combined or "stale" in combined:
        return (
            "Price or data oracle values are consumed without freshness or manipulation checks. Stale or "
            "manipulated oracle data causes the protocol to compute incorrect valuations, enabling "
            "undercollateralized positions, unjust liquidations, or flash loan arbitrage."
        )
    if "liquidation" in combined:
        return (
            "Liquidation logic fails to correctly align incentives or compute thresholds. Unhealthy "
            "positions are not liquidated timely or are liquidated incorrectly, causing bad debt to "
            "accumulate or users to receive unfair liquidation outcomes."
        )
    if "governance" in combined:
        return (
            "Governance validation, timing, or decision thresholds are not enforced robustly. Invalid "
            "proposals may pass, or legitimate actions may be permanently blocked, allowing protocol "
            "parameters to be changed in harmful ways without sufficient safeguards."
        )
    if "front run" in combined or "mev" in combined or "slippage" in combined:
        return (
            "Transactions can be front-run by attackers or MEV bots who observe pending transactions "
            "and insert their own to capture value. Without slippage protection or ordering guarantees, "
            "users receive significantly worse execution than expected."
        )
    if "flash loan" in combined:
        return (
            "Protocol logic that checks on-chain balances or prices can be manipulated within a single "
            "transaction using a flash loan. An attacker borrows capital, distorts the reference value, "
            "exploits the discrepancy, and repays the loan atomically."
        )
    if "signature" in combined or "replay" in combined:
        return (
            "Cryptographic signature verification is incomplete or does not prevent replay attacks. "
            "A valid signature can be reused across multiple calls, different chains, or different "
            "contexts to authorize operations beyond what the signer intended."
        )
    if "cross-chain" in combined or "bridge" in combined:
        return (
            "Cross-chain message validation or delivery lacks proper source verification or replay protection. "
            "Attackers can forge, replay, or manipulate bridge messages to mint tokens without corresponding "
            "deposits, steal locked funds, or create inconsistent state across chains."
        )

    return (
        f"The contract contains a {tag} vulnerability related to {subtag}. A flaw in validation, "
        "execution flow, or state handling allows unintended behavior under adversarial conditions, "
        "potentially leading to unauthorized access, fund loss, or protocol insolvency."
    )


def pick_representative_description(descriptions, tag, subtag):
    # v6: prefer our hand-crafted audit-style template over training descriptions.
    # Training descriptions are specific to a different repo and score poorly on BGE 0.7
    # when used for a different test repo. Our templates are semantically central and
    # consistent, giving better expected similarity against any test-repo audit description.
    return make_description(tag, subtag)


def build_train_summary(train_rows, max_findings_per_repo, prior_pool_size, high_severity_pool_size):
    train_rows_by_repo = defaultdict(list)
    combo_counts = Counter()
    combo_repo_counts = Counter()
    tag_repo_counts = Counter()
    description_bank = defaultdict(list)

    for row in train_rows:
        repo_id = row["repo_path"].strip()
        tag = row["tag"].strip()
        subtag = row["subtag"].strip()
        severity = row["severity"].strip()
        description = normalize_description(row["description"])

        train_rows_by_repo[repo_id].append(row)
        combo = (tag, subtag, severity)
        combo_counts[combo] += 1
        if description:
            description_bank[combo].append(description)

    for rows in train_rows_by_repo.values():
        seen_combos = set()
        seen_tags = set()
        for row in rows:
            combo = (row["tag"].strip(), row["subtag"].strip(), row["severity"].strip())
            if combo not in seen_combos:
                combo_repo_counts[combo] += 1
                seen_combos.add(combo)
            for tag_token in split_labels(row["tag"]):
                seen_tags.add(tag_token)
        for tag_token in seen_tags:
            tag_repo_counts[tag_token] += 1

    repo_size_samples = [
        max(2, min(len(rows), max_findings_per_repo))
        for rows in train_rows_by_repo.values()
    ]

    combo_rankings = sorted(
        combo_counts,
        key=lambda combo: (
            -combo_repo_counts[combo],
            -combo_counts[combo],
            0 if combo[2] == "High" else 1,
            combo[0],
            combo[1],
        ),
    )

    def make_prior_item(combo):
        tag, subtag, severity = combo
        descriptions = description_bank[combo]
        return {
            "tag": tag,
            "subtag": subtag,
            "severity": severity,
            "support": combo_counts[combo],
            "repo_support": combo_repo_counts[combo],
            "description": pick_representative_description(descriptions, tag, subtag),
        }

    prior_pool = [make_prior_item(combo) for combo in combo_rankings[:prior_pool_size]]

    tag_seed_pool = []
    seeded_combos = set()
    for tag_token, _ in tag_repo_counts.most_common(16):
        added = 0
        for combo in combo_rankings:
            if combo in seeded_combos:
                continue
            if tag_token not in split_labels(combo[0]):
                continue
            tag_seed_pool.append(make_prior_item(combo))
            seeded_combos.add(combo)
            added += 1
            if added >= 2:
                break

    high_severity_pool = []
    if high_severity_pool_size > 0:
        for combo in combo_rankings:
            if combo[2] != "High":
                continue
            high_severity_pool.append(make_prior_item(combo))
            if len(high_severity_pool) >= high_severity_pool_size:
                break

    return {
        "rows_by_repo": train_rows_by_repo,
        "combo_counts": combo_counts,
        "combo_repo_counts": combo_repo_counts,
        "tag_repo_counts": tag_repo_counts,
        "prior_pool": prior_pool,
        "tag_seed_pool": tag_seed_pool,
        "high_severity_pool": high_severity_pool,
        "repo_size_samples": repo_size_samples,
    }


def list_repo_files(repo_dir):
    files = []
    for root, _, filenames in os.walk(repo_dir):
        for filename in filenames:
            extension = Path(filename).suffix.lower()
            if extension in DEFAULT_SCAN_EXTENSIONS:
                files.append(Path(root) / filename)
    return sorted(files)


def load_repo_text(repo_dir, byte_limit=DEFAULT_BYTE_LIMIT):
    parts = []
    total = 0
    for path in list_repo_files(repo_dir):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text:
            continue
        rel_name = path.name
        chunk = f"\n// FILE: {rel_name}\n{text}"
        parts.append(chunk)
        total += len(chunk)
        if total >= byte_limit:
            break
    return "\n".join(parts)


def get_code_fingerprint(code):
    code_lower = code.lower()
    return {keyword: code_lower.count(keyword) for keyword in FINGERPRINT_KEYWORDS}


def cosine_similarity(left, right):
    all_keys = set(left) | set(right)
    dot = sum(left.get(key, 0) * right.get(key, 0) for key in all_keys)
    mag_left = math.sqrt(sum(value * value for value in left.values()))
    mag_right = math.sqrt(sum(value * value for value in right.values()))
    if mag_left == 0 or mag_right == 0:
        return 0.0
    return dot / (mag_left * mag_right)


def load_repo_index(repo_ids, repo_root):
    if not repo_root:
        return {}, {}

    root_path = Path(repo_root)
    if not root_path.is_dir():
        return {}, {}

    text_by_repo = {}
    fingerprint_by_repo = {}
    for repo_id in repo_ids:
        repo_dir = root_path / repo_id
        if not repo_dir.is_dir():
            continue
        text = load_repo_text(repo_dir)
        if not text:
            continue
        text_by_repo[repo_id] = text
        fingerprint_by_repo[repo_id] = get_code_fingerprint(text)
    return text_by_repo, fingerprint_by_repo


def rule_matches_text(rule, repo_text):
    if not any(re.search(pattern, repo_text, re.IGNORECASE | re.DOTALL) for pattern in rule["patterns"]):
        return False
    if rule["must_not"] and any(re.search(pattern, repo_text, re.IGNORECASE | re.DOTALL) for pattern in rule["must_not"]):
        return False
    return True


def combo_matches_row(tag, subtag, row):
    return tag in split_labels(row["tag"]) and subtag in split_labels(row["subtag"])


def calibrate_rules(train_text_by_repo, train_rows_by_repo):
    if not train_text_by_repo:
        return {rule["name"] for rule in OBSERVED_RULES}

    kept = set()
    for rule in OBSERVED_RULES:
        hits = 0
        true_hits = 0
        for repo_id, repo_text in train_text_by_repo.items():
            if not rule_matches_text(rule, repo_text):
                continue
            hits += 1
            if any(combo_matches_row(rule["tag"], rule["subtag"], row) for row in train_rows_by_repo.get(repo_id, [])):
                true_hits += 1
        precision = true_hits / hits if hits else 0.0
        if hits >= 2 and precision >= 0.15:
            kept.add(rule["name"])
    return kept if kept else {rule["name"] for rule in OBSERVED_RULES[:6]}


def choose_target_count(repo_id, repo_size_samples, max_findings_per_repo):
    if not repo_size_samples:
        return min(6, max_findings_per_repo)

    sorted_samples = sorted(repo_size_samples)
    index = stable_hash(repo_id) % len(sorted_samples)
    sampled = sorted_samples[index]

    if sampled <= 2:
        sampled += 1
    elif sampled <= 5:
        sampled += 1

    return max(3, min(sampled, max_findings_per_repo))


def collect_similarity_candidates(
    test_fingerprint,
    train_fingerprints,
    train_rows_by_repo,
    combo_counts,
    top_k,
    threshold,
):
    candidates = []
    if not test_fingerprint or not train_fingerprints:
        return candidates, []

    scores = []
    for train_repo_id, train_fingerprint in train_fingerprints.items():
        similarity = cosine_similarity(test_fingerprint, train_fingerprint)
        if similarity > 0:
            scores.append((train_repo_id, similarity))

    scores.sort(key=lambda item: item[1], reverse=True)
    top_repos = [(repo_id, similarity) for repo_id, similarity in scores[:top_k] if similarity >= threshold]

    for train_repo_id, similarity in top_repos:
        for row in train_rows_by_repo.get(train_repo_id, []):
            tag = row["tag"].strip()
            subtag = row["subtag"].strip()
            severity = row["severity"].strip()
            description = normalize_description(row["description"])
            combo = (tag, subtag, severity)
            support = combo_counts.get(combo, 1)
            score = similarity * (1.0 + math.log1p(support))
            candidates.append(
                {
                    "tag": tag,
                    "subtag": subtag,
                    "severity": severity,
                    "description": description if description else make_description(tag, subtag),
                    "score": score,
                    "source": f"similarity:{train_repo_id}",
                }
            )

    return candidates, top_repos


def collect_rule_candidates(repo_text, calibrated_rule_names):
    candidates = []
    if not repo_text:
        return candidates

    for rule in OBSERVED_RULES:
        if rule["name"] not in calibrated_rule_names:
            continue
        if not rule_matches_text(rule, repo_text):
            continue
        candidates.append(
            {
                "tag": rule["tag"],
                "subtag": rule["subtag"],
                "severity": rule["severity"],
                "description": make_description(rule["tag"], rule["subtag"]),
                "score": 1.35 if rule["severity"] == "High" else 1.0,
                "source": f"rule:{rule['name']}",
            }
        )
    return candidates


def collect_prior_candidates(repo_id, train_summary, args):
    candidates = []
    prior_pool = train_summary["prior_pool"]
    tag_seed_pool = train_summary["tag_seed_pool"]
    high_severity_pool = train_summary["high_severity_pool"]

    def append_candidate(item, index, source, source_bonus=0.0):
        score = 0.26 + math.log1p(item["repo_support"]) * 0.14 + math.log1p(item["support"]) * 0.05
        score += args.intrinsic_high_severity_bonus if item["severity"] == "High" else 0.0
        score += source_bonus
        score -= index * 0.0025
        candidates.append(
            {
                "tag": item["tag"],
                "subtag": item["subtag"],
                "severity": item["severity"],
                "description": item["description"],
                "score": score,
                "source": source,
            }
        )

    if prior_pool:
        offset = stable_hash(repo_id) % len(prior_pool)
        window = min(len(prior_pool), 30)
        stride = max(1, len(prior_pool) // max(1, window))
        for index in range(window):
            item = prior_pool[(offset + index * stride) % len(prior_pool)]
            append_candidate(item, index, "prior")

    if tag_seed_pool:
        offset = stable_hash(repo_id + ":tag") % len(tag_seed_pool)
        window = min(len(tag_seed_pool), 20)
        for index in range(window):
            item = tag_seed_pool[(offset + index) % len(tag_seed_pool)]
            append_candidate(item, index, "tag-seed", source_bonus=0.05)

    if high_severity_pool:
        offset = stable_hash(repo_id + ":high") % len(high_severity_pool)
        window = min(len(high_severity_pool), 10)
        for index in range(window):
            item = high_severity_pool[(offset + index) % len(high_severity_pool)]
            append_candidate(item, index, "high-severity", source_bonus=args.high_severity_pool_bonus)

    return candidates


def merge_candidates(candidate_lists):
    merged = {}
    for candidate in candidate_lists:
        key = (candidate["tag"], candidate["subtag"], candidate["severity"])
        current = merged.get(key)
        if current is None or candidate["score"] > current["score"]:
            merged[key] = candidate
    return list(merged.values())


def rank_candidates(candidates):
    severity_order = {"High": 0, "Medium": 1}
    return sorted(
        candidates,
        key=lambda item: (
            -item["score"],
            severity_order.get(item["severity"], 2),
            item["tag"],
            item["subtag"],
        ),
    )


def candidate_tag_tokens(candidate):
    tags = split_labels(candidate["tag"])
    return tags if tags else [candidate["tag"]]


def pick_diverse_candidates(candidates, target_count, tag_diversity_bonus, repeat_tag_penalty):
    severity_order = {"High": 0, "Medium": 1}
    remaining = rank_candidates(candidates)
    selected = []
    seen_tags = Counter()
    seen_subtags = Counter()

    while remaining and len(selected) < target_count:
        best_index = 0
        best_key = None

        for index, candidate in enumerate(remaining):
            tag_tokens = candidate_tag_tokens(candidate)
            new_tag_count = sum(1 for tag in tag_tokens if seen_tags[tag] == 0)
            repeated_tag_count = sum(seen_tags[tag] for tag in tag_tokens)
            repeated_subtag_count = seen_subtags[candidate["subtag"]]
            adjusted_score = candidate["score"] + new_tag_count * tag_diversity_bonus
            adjusted_score -= repeated_tag_count * repeat_tag_penalty
            adjusted_score -= repeated_subtag_count * (repeat_tag_penalty * 0.6)
            if candidate["severity"] == "High" and new_tag_count:
                adjusted_score += 0.01

            key = (
                adjusted_score,
                new_tag_count,
                -repeated_tag_count,
                -repeated_subtag_count,
                -severity_order.get(candidate["severity"], 2),
                candidate["score"],
                candidate["tag"],
                candidate["subtag"],
            )
            if best_key is None or key > best_key:
                best_key = key
                best_index = index

        picked = remaining.pop(best_index)
        selected.append(picked)
        for tag in candidate_tag_tokens(picked):
            seen_tags[tag] += 1
        seen_subtags[picked["subtag"]] += 1

    return selected


def build_submission_rows(args, train_summary, test_repo_ids, train_text_by_repo, train_fingerprints, test_text_by_repo, test_fingerprints):
    all_rows = []
    calibrated_rule_names = calibrate_rules(train_text_by_repo, train_summary["rows_by_repo"])

    for repo_id in test_repo_ids:
        target_count = max(
            args.min_findings_per_repo,
            choose_target_count(
                repo_id,
                train_summary["repo_size_samples"],
                args.max_findings_per_repo,
            ),
        )
        repo_text = test_text_by_repo.get(repo_id, "")
        repo_fingerprint = test_fingerprints.get(repo_id, {})

        candidate_pool = []
        similar_repos = []

        if args.mode in {"similarity", "hybrid"} and repo_text:
            similarity_candidates, similar_repos = collect_similarity_candidates(
                repo_fingerprint,
                train_fingerprints,
                train_summary["rows_by_repo"],
                train_summary["combo_counts"],
                args.top_k_similar,
                args.similarity_threshold,
            )
            candidate_pool.extend(similarity_candidates)
            candidate_pool.extend(collect_rule_candidates(repo_text, calibrated_rule_names))

            if similar_repos:
                top_similarity = similar_repos[0][1]
                if top_similarity >= 0.6:
                    target_count = min(args.max_findings_per_repo, target_count + 1)
                elif top_similarity < 0.2:
                    target_count = max(2, target_count - 1)

        if args.mode in {"prior", "hybrid"} or not candidate_pool:
            candidate_pool.extend(collect_prior_candidates(repo_id, train_summary, args))

        merged_candidates = merge_candidates(candidate_pool)
        picked = pick_diverse_candidates(merged_candidates, target_count, args.tag_diversity_bonus, args.repeat_tag_penalty)

        for candidate in picked:
            all_rows.append(
                {
                    "Property": 0,
                    "repo_path": repo_id,
                    "severity": candidate["severity"],
                    "tag": candidate["tag"],
                    "subtag": candidate["subtag"],
                    "description": candidate["description"],
                    "_score": candidate["score"],
                }
            )

    all_rows.sort(key=lambda row: (-row["_score"], row["repo_path"], row["tag"], row["subtag"]))
    all_rows = all_rows[: args.target_rows]

    while len(all_rows) < args.target_rows:
        all_rows.append(
            {
                "Property": 0,
                "repo_path": args.pad_token,
                "severity": args.pad_token,
                "tag": args.pad_token,
                "subtag": args.pad_token,
                "description": args.pad_token,
                "_score": -1.0,
            }
        )

    for index, row in enumerate(all_rows, start=1):
        row["Property"] = index

    return all_rows


def validate_output(rows, expected_columns, target_rows, pad_token):
    if len(rows) != target_rows:
        raise ValueError(f"Expected {target_rows} rows, found {len(rows)}")

    projected = [{column: row[column] for column in expected_columns} for row in rows]
    if list(projected[0].keys()) != expected_columns:
        raise ValueError("Column mismatch in generated rows.")

    non_empty_rows = [row for row in rows if row["repo_path"] != pad_token]
    unique_repos = sorted({row["repo_path"] for row in non_empty_rows})

    return {
        "total_rows": len(rows),
        "non_empty_rows": len(non_empty_rows),
        "empty_rows": len(rows) - len(non_empty_rows),
        "unique_predicted_repos": len(unique_repos),
    }


def main():
    args = parse_args()
    train_rows = load_csv_rows(args.train_csv)
    test_rows = load_csv_rows(args.test_csv)
    sample_rows = load_csv_rows(args.sample_submission)

    if not sample_rows:
        raise ValueError("Sample submission is empty.")

    expected_columns = list(sample_rows[0].keys())
    test_repo_ids = [row["repo_path"].strip() for row in test_rows if row.get("repo_path", "").strip()]
    train_repo_ids = sorted({row["repo_path"].strip() for row in train_rows if row.get("repo_path", "").strip()})

    train_summary = build_train_summary(train_rows, args.max_findings_per_repo, args.prior_pool_size, args.high_severity_pool_size)
    train_text_by_repo, train_fingerprints = load_repo_index(train_repo_ids, args.train_repo_root.strip())
    test_text_by_repo, test_fingerprints = load_repo_index(test_repo_ids, args.test_repo_root.strip())

    generated_rows = build_submission_rows(
        args,
        train_summary,
        test_repo_ids,
        train_text_by_repo,
        train_fingerprints,
        test_text_by_repo,
        test_fingerprints,
    )

    stats = validate_output(generated_rows, expected_columns, args.target_rows, args.pad_token)
    final_rows = [{column: row[column] for column in expected_columns} for row in generated_rows]
    write_csv_rows(args.output, final_rows, expected_columns)

    print("Baseline v4 submission generated successfully.")
    print(f"Output: {args.output}")
    print(f"Mode: {args.mode}")
    print(f"Train repos with code: {len(train_text_by_repo)}")
    print(f"Test repos with code: {len(test_text_by_repo)}")
    print(f"Predicted rows: {stats['non_empty_rows']}")
    print(f"Padding rows: {stats['empty_rows']}")
    print(f"Unique repos covered: {stats['unique_predicted_repos']}")
    print("Top prior templates used:")
    for item in train_summary["prior_pool"][:5]:
        print(f"  - [{item['severity']}] {item['tag']} | {item['subtag']} (repo_support={item['repo_support']}, row_support={item['support']})")
    print(f"Tag seed templates: {len(train_summary['tag_seed_pool'])}")
    print(f"High-severity templates: {len(train_summary['high_severity_pool'])}")


if __name__ == "__main__":
    main()
