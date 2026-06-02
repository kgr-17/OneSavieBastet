"""Try every plausible hash function against the high-confidence (hash, contest_name) pairs
from artifacts/hash_to_contest.json. Goal: find the function that reproduces ALL 12-char
hex hashes from a contest's metadata."""
import hashlib
import json
import sys
import itertools

MAPPING_FILE = "artifacts/hash_to_contest.json"
MIN_VOTE_SHARE = 0.7  # only use trusted mappings for cracking


def load_pairs():
    with open(MAPPING_FILE, encoding="utf-8") as f:
        m = json.load(f)
    pairs = []
    for repo_hash, info in m.items():
        if info["vote_share"] >= MIN_VOTE_SHARE:
            pairs.append((repo_hash.lower(), info["contest"]))
    return pairs


def candidate_inputs(contest):
    """Generate plausible input strings for the hash function."""
    yield contest
    yield contest.lower()
    yield contest.upper()
    yield f"code-423n4/{contest}"
    yield f"code-423n4/{contest}-findings"
    yield f"https://github.com/code-423n4/{contest}"
    yield f"https://github.com/code-423n4/{contest}-findings"
    yield f"https://github.com/code-423n4/{contest}.git"
    yield f"git@github.com:code-423n4/{contest}.git"
    yield f"https://code4rena.com/reports/{contest}"
    yield f"https://code4rena.com/contests/{contest}"
    yield f"{contest}\n"
    yield f"{contest}/"
    # Maybe the dataset uses just the contest part (without date prefix).
    parts = contest.split("-", 2)
    if len(parts) >= 3:
        yield parts[2]  # e.g. "meebits" from "2021-04-meebits"
        yield parts[2].lower()


HASH_FUNCS = {
    "md5":     lambda b: hashlib.md5(b).hexdigest(),
    "sha1":    lambda b: hashlib.sha1(b).hexdigest(),
    "sha224":  lambda b: hashlib.sha224(b).hexdigest(),
    "sha256":  lambda b: hashlib.sha256(b).hexdigest(),
    "sha384":  lambda b: hashlib.sha384(b).hexdigest(),
    "sha512":  lambda b: hashlib.sha512(b).hexdigest(),
    "blake2b": lambda b: hashlib.blake2b(b).hexdigest(),
    "blake2s": lambda b: hashlib.blake2s(b).hexdigest(),
    "sha3_256": lambda b: hashlib.sha3_256(b).hexdigest(),
}


def try_function(hash_name, slicer, transform_name, transform_fn, pairs):
    """For each pair, compute hash and check if it matches expected. Returns count of matches."""
    h = HASH_FUNCS[hash_name]
    matched = 0
    examples = []
    for repo_hash, contest in pairs:
        for inp in candidate_inputs(contest):
            inp_bytes = transform_fn(inp).encode("utf-8")
            digest = h(inp_bytes)
            candidate = slicer(digest)
            if candidate == repo_hash:
                matched += 1
                if len(examples) < 3:
                    examples.append((contest, inp, repo_hash))
                break
    return matched, examples


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pairs = load_pairs()
    print(f"Testing {len(pairs)} confident (hash, contest) pairs (vote_share>={MIN_VOTE_SHARE})\n")

    # Slicers: take first 12 hex chars, last 12, middle 12, etc.
    slicers = {
        "first12":  lambda d: d[:12],
        "last12":   lambda d: d[-12:],
        "mid12":    lambda d: d[len(d)//2 - 6 : len(d)//2 + 6],
        "skip4-16": lambda d: d[4:16],
    }
    # Optional input transforms.
    transforms = {
        "raw":   lambda s: s,
        "lower": lambda s: s.lower(),
        "upper": lambda s: s.upper(),
        "strip": lambda s: s.strip(),
    }

    best = (0, None)
    total = len(pairs)
    for hash_name in HASH_FUNCS:
        for slicer_name, slicer in slicers.items():
            for tname, tfn in transforms.items():
                matched, examples = try_function(hash_name, slicer, tname, tfn, pairs)
                if matched > best[0]:
                    best = (matched, (hash_name, slicer_name, tname, examples))
                if matched == total:
                    print(f"[FULL MATCH] {hash_name}({tname}(input))[{slicer_name}]")
                    for c, inp, h in examples:
                        print(f"    {c} | input='{inp}' | hash={h}")
                    return
                if matched >= 3:
                    print(f"  partial: {hash_name}({tname})[{slicer_name}] = {matched}/{total}")

    print(f"\nBest result: {best[0]}/{total} matched")
    if best[1]:
        hname, sname, tname, examples = best[1]
        print(f"  Best combo: {hname}({tname})[{sname}]")
        for c, inp, h in examples:
            print(f"    {c} | input='{inp}' | hash={h}")
    print("\nNo standard hash function matches all pairs. The hash may use:")
    print("  - A non-standard input (commit SHA, repo tree hash, etc.)")
    print("  - A random salt/nonce stored separately")
    print("  - A different encoding (utf-16, base64, etc.)")


if __name__ == "__main__":
    main()
