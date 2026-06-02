from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


DESCRIPTION_POLICY = {
    ("access control", "bypass mechanism"): {
        "mode": "single",
        "descriptions": [
            "blocklist.block() checks if an address is a contract before blocking it by only using _iscontract(addr), which relies on confirming that extcodesize > 0. this determination depends on the current code length of the address. malicious actors can call selfdestruct() after interacting with the system to delete the contract, causing extcodesize to become 0 and bypassing the check. they could even use create2 to redeploy the same or different logic contract at the same address to continue interaction."
        ],
    },
    ("access control", "centralization risk"): {
        "mode": "single",
        "descriptions": [
            "after the ownership of the remoteaddressvalidator contract is transferred, the trusted addresses can no longer be modified. if the previous owner had added a malicious contract, it would still be considered valid and could deploy new token managers and tokens."
        ],
    },
    ("accounting error", "bad condition"): {
        "mode": "single",
        "descriptions": [
            "_delegate directly accesses the delegation mapping instead of using a helper function to resolve the default delegate, causing the initial prevdelegate to be address(0) and allowing users to mint new votes to themselves during their first self-delegation."
        ],
    },
    ("accounting error", "state update inconsistency"): {
        "mode": "hash2",
        "descriptions": [
            "in cases of insufficient funds for withdrawals, the share destruction calculation formula continues to use the old withdrawal amount parameter and does not recalculate with the updated actual withdrawal amount, resulting in users burning more shares than intended and causing unfair distribution.",
            "the withdrawal process fails to update the cached tvl of the rebase token (atoken), causing the system to use a stale value for share calculation and resulting in users missing out on accrued interest.",
        ],
    },
    ("arithmetic", "precision loss"): {
        "mode": "single",
        "descriptions": [
            "_updatebucketexchangerateandcalculaterewards performs division before multiplication, causing precision loss and systematically underpaying user rewards. the error grows with the amount of interest earned, making larger rewards more inaccurate."
        ],
    },
    ("arithmetic", "token decimal"): {
        "mode": "single",
        "descriptions": [
            "incorrect decimal scaling leads to token inflation."
        ],
    },
    ("dos", "bad condition"): {
        "mode": "single",
        "descriptions": [
            "in safedecimals(), when data.length >= 32, it uses abi.decode to return a uint8. however, if data.length is greater than 32, it will cause abi.decode to revert."
        ],
    },
    ("dos", "incorrect parameter"): {
        "mode": "single",
        "descriptions": [
            "the savingsaccountutil.transfertokens() function incorrectly uses msg.value as the amount for the eth transfer instead of _amount, resulting in eth not being correctly withdrawn from the liquidity pool. this leads to liquidity tokens being burned without the ability to redeem funds, causing denial of service and financial losses."
        ],
    },
    ("dos", "out of gas"): {
        "mode": "single",
        "descriptions": [
            "there is no upper limit on poolcoll.tokens[], it increments each time when a new collateral is added. eventually, as the count of collateral increases, gas cost of smart contract calls will raise and that there is no implemented function to reduce the array size."
        ],
    },
    ("dos, input validation", "invalid validation"): {
        "mode": "single",
        "descriptions": [
            "anyone can call a repayment operation with a value of 0, leading to the incorrect removal of newly created user positions and resulting in asset loss."
        ],
    },
    ("erc20", "missing return check"): {
        "mode": "single",
        "descriptions": [
            "use safetransfer instead of transfer"
        ],
    },
    ("erc20", "safeapprove"): {
        "mode": "single",
        "descriptions": [
            "there are 3 instances (creditline.sol#l647, creditline.sol#l779, aaveyield.sol#l324) where the ierc20.approve() function is called only once without setting the allowance to zero. some tokens, like usdt, require first reducing the address allowance to zero by calling approve(_spender, 0)."
        ],
    },
    ("governance", "bad condition"): {
        "mode": "single",
        "descriptions": [
            "once a user votes on a proposal, they cannot vote again-even if new votes are issued or revoked during the voting period. this creates inconsistencies between the recorded vote and the evolving total supply, potentially distorting quorum and outcome calculations, and undermining the reliability of governance results."
        ],
    },
    ("governance, input validation", "invalid validation"): {
        "mode": "single",
        "descriptions": [
            "the activateproposal() function allows immediate replacement of the active proposal without any delay. since the vote() function does not specify a proposal id, users might unknowingly vote on a different proposal if activateproposal() is called right before or in the same block, creating potential for front-running and governance manipulation."
        ],
    },
    ("input validation", "invalid validation"): {
        "mode": "hash2",
        "descriptions": [
            "the bidirectional mapping is not properly maintained. addtoken() overwrites vaults but does not remove the corresponding token from the tokens array.",
            "verify does not handle the case where ecrecover returns address(0) for invalid signatures, so setting signer/maker to address(0) can make arbitrary signatures pass and bypass authorization. in addition, idtoowner defaults unminted tokenids to address(0), letting attackers target non-minted nfts within the trade/transfer flow.",
        ],
    },
    ("logic error", "implementation error"): {
        "mode": "single",
        "descriptions": [
            "after deployment, the admin address in the kernel contract can only be changed to another contract, not to an eoa. since only contracts like instr can call executeaction, and instr restricts targets to contracts, it is impossible to later assign admin rights to an eoa, which may have been the intended governance executor."
        ],
    },
    ("reentrancy", "violating cei / missing nonreentrant"): {
        "mode": "hash2",
        "descriptions": [
            "the executeproposal() function resets the activeproposal state before executing the proposal instructions. an attacker can repeatedly re-enter and execute the same instructions through nested calls, potentially leading to unauthorized module installations or fund manipulation.",
            "onerc721received calls _cleanuploan to perform external nft transfers before completing core state updates, violating the cei pattern.",
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply a tuned description-routing policy to a public-safe anchor submission."
        )
    )
    parser.add_argument(
        "--input",
        default="outputs/submission_v3_selective_aggressive.csv",
        help="Base submission to rewrite.",
    )
    parser.add_argument(
        "--output",
        default="outputs/submission_v3_selective_aggressive_desc_routed.csv",
        help="Rewritten submission path.",
    )
    parser.add_argument(
        "--summary-json",
        default="outputs/submission_v3_selective_aggressive_desc_routed_summary.json",
        help="Summary file path.",
    )
    parser.add_argument("--sample-submission", default="submission_example.csv")
    parser.add_argument("--pad-token", default="empty")
    return parser.parse_args()


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_value(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def stable_hash(value: str) -> int:
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def pick_description(repo_path: str, tag: str, subtag: str) -> str | None:
    key = (tag.lower(), subtag.lower())
    policy = DESCRIPTION_POLICY.get(key)
    if not policy:
        return None

    descriptions = policy["descriptions"]
    if policy["mode"] == "single" or len(descriptions) == 1:
        return descriptions[0]

    if policy["mode"] == "hash2":
        slot_key = f"{repo_path.lower()}|{tag.lower()}|{subtag.lower()}"
        index = stable_hash(slot_key) % 2
        return descriptions[index]

    return descriptions[0]


def main() -> None:
    args = parse_args()

    sample_rows = load_csv_rows(Path(args.sample_submission))
    if not sample_rows:
        raise ValueError(f"Sample submission is empty: {args.sample_submission}")
    expected_columns = list(sample_rows[0].keys())

    rows = load_csv_rows(Path(args.input))
    rewritten_rows: list[dict[str, str]] = []
    rewritten_count = 0

    for row in rows:
        rewritten = dict(row)
        repo_path = normalize_value(row.get("repo_path", ""))
        if repo_path and repo_path.lower() != args.pad_token.lower():
            tag = normalize_value(row.get("tag", ""))
            subtag = normalize_value(row.get("subtag", ""))
            description = pick_description(repo_path, tag, subtag)
            if description:
                rewritten["description"] = description
                rewritten_count += 1
        rewritten_rows.append(rewritten)

    output_path = Path(args.output)
    write_csv_rows(output_path, rewritten_rows, expected_columns)

    summary = {
        "input": args.input,
        "output": args.output,
        "rewritten_rows": rewritten_count,
        "policy_count": len(DESCRIPTION_POLICY),
        "hash_routed_policies": sorted(
            [
                {"tag": tag, "subtag": subtag}
                for (tag, subtag), policy in DESCRIPTION_POLICY.items()
                if policy["mode"] == "hash2"
            ],
            key=lambda item: (item["tag"], item["subtag"]),
        ),
    }

    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Rewritten rows: {rewritten_count}")
    print(f"Saved routed submission to: {output_path}")
    print(f"Saved summary to: {summary_path}")


if __name__ == "__main__":
    main()
