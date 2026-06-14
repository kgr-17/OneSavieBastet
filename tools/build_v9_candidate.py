import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


TEAMMATE_CSV = "teamate_hightst_submission.csv"
TRAIN_CSV = "train.csv"
DATASET_0831_CSV = "data/dataset_0831.csv"
OUTPUT_CSV = "outputs/submission_v9_candidate.csv"
REPORT_JSON = "artifacts/v9-candidate/build_report.json"
TARGET_ROWS = 400
DEDUPE_SIM = 0.30
CLASSIFY_MIN_SIM = 0.15
MAX_DESCRIPTION_CHARS = 280

TARGETS = [
    {
        "repo_path": "e0d2d83ea351",
        "audit": "2023-01-popcorn",
        "platform": "c4",
        "budget": 5,
        "report": "artifacts/c4_reports/2023-01-popcorn.md",
    },
    {
        "repo_path": "e7921851ec01",
        "audit": "2023-06-dodo",
        "platform": "sherlock",
        "budget": 5,
        "report": "artifacts/sherlock_reports/2023-06-dodo.md",
    },
    {
        "repo_path": "54405135ebf3",
        "audit": "2022-08-frax",
        "platform": "c4",
        "budget": 3,
        "report": "artifacts/c4_reports/2022-08-frax.md",
    },
    {
        "repo_path": "198fa93fabdd",
        "audit": "2022-06-nibbl",
        "platform": "c4",
        "budget": 2,
        "report": "artifacts/c4_reports/2022-06-nibbl.md",
    },
]

C4_FINDING_RE = re.compile(
    r"^##\s+\[\[([HM])-(\d+)\]\s+(.+?)\]\([^)]+\)\s*$"
    r"|^##\s+\[?\[?([HM])-(\d+)\]\s+(.+?)\]?\s*$",
    re.MULTILINE,
)
SHERLOCK_FINDING_RE = re.compile(r"^#\s+Issue\s+([HM])-(\d+)\s*:?\s*(.+?)$", re.MULTILINE)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
TOKEN_RE = re.compile(r"[a-z0-9_]+")


def parse_args():
    parser = argparse.ArgumentParser(description="Build v9 candidate from cached audit report rows only.")
    parser.add_argument("--teammate", default=TEAMMATE_CSV)
    parser.add_argument("--train-csv", default=TRAIN_CSV)
    parser.add_argument("--dataset-0831", default=DATASET_0831_CSV)
    parser.add_argument("--output", default=OUTPUT_CSV)
    parser.add_argument("--report", default=REPORT_JSON)
    parser.add_argument("--target-rows", type=int, default=TARGET_ROWS)
    return parser.parse_args()


def load_csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path, rows, fieldnames):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_space(value):
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


def ascii_clean(value):
    value = str(value).replace("\u00a0", " ")
    value = value.replace("\u2018", "'").replace("\u2019", "'")
    value = value.replace("\u201c", '"').replace("\u201d", '"')
    value = value.replace("\u2013", "-").replace("\u2014", "-")
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def clean_markdown_text(value):
    text = ascii_clean(value)
    text = text.replace("\\_", "_").replace("\\", " ")
    text = re.sub(r"[<>]\s*[<>]\s*[<>]", " ", text)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = URL_RE.sub(" ", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"^\s*[*_]*Submitted by.*$", " ", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^\s*Source:.*$", " ", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^\s*#{1,6}\s+.*$", " ", text, flags=re.MULTILINE)
    text = text.replace("<", " ").replace(">", " ")
    text = text.replace("*", " ").replace("_", " ")
    return normalize_space(text)


def trim_sentence_boundary(text, max_chars=MAX_DESCRIPTION_CHARS):
    text = normalize_space(text)
    if len(text) <= max_chars:
        return text

    sentences = SENTENCE_RE.split(text)
    chosen = []
    for sentence in sentences:
        candidate = normalize_space(" ".join(chosen + [sentence]))
        if len(candidate) <= max_chars:
            chosen.append(sentence)
        else:
            break
    if chosen:
        return normalize_space(" ".join(chosen))

    words = text[:max_chars].split()
    return " ".join(words[:-1]) if len(words) > 1 else text[:max_chars]


def parse_findings_from_cached(path, platform):
    report_path = Path(path)
    if not report_path.exists():
        return []
    text = report_path.read_text(encoding="utf-8", errors="replace")
    pattern = C4_FINDING_RE if platform == "c4" else SHERLOCK_FINDING_RE
    matches = list(pattern.finditer(text))
    findings = []
    for index, match in enumerate(matches):
        severity_marker = match.group(1) or match.group(4)
        issue_number = match.group(2) or match.group(5)
        raw_title = match.group(3) or match.group(6)
        severity = "High" if severity_marker == "H" else "Medium"
        issue_id = f"{severity_marker}-{issue_number}"
        title = clean_markdown_text(raw_title.strip().rstrip("]"))
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : body_end].strip()
        body = re.sub(r"^##\s+Found by[\s\S]*?(?=^##|\Z)", " ", body, flags=re.MULTILINE)
        cleaned_body = clean_markdown_text(body)
        findings.append(
            {
                "severity": severity,
                "issue_id": issue_id,
                "title": title,
                "body": cleaned_body,
                "source_report": str(report_path),
            }
        )
    return findings


def build_description(title, body):
    title = clean_markdown_text(title).rstrip(".")
    body = clean_markdown_text(body)
    body_sentences = SENTENCE_RE.split(body) if body else []
    while body_sentences and is_near_duplicate_sentence(title, body_sentences[0]):
        body_sentences.pop(0)
    body = normalize_space(" ".join(body_sentences))
    combined = f"{title}. {body}" if body else f"{title}."
    description = trim_sentence_boundary(combined)
    description = clean_markdown_text(description)
    return trim_sentence_boundary(description)


def is_near_duplicate_sentence(left, right):
    left_tokens = set(TOKEN_RE.findall(left.lower()))
    right_tokens = set(TOKEN_RE.findall(right.lower()))
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return overlap >= 0.65


def has_bad_description(description, max_chars=MAX_DESCRIPTION_CHARS):
    return (
        not description
        or len(description) > max_chars
        or "`" in description
        or bool(URL_RE.search(description))
    )


def build_label_rows(train_csv, dataset_0831):
    label_rows = []
    for row in load_csv_rows(train_csv):
        description = normalize_space(row.get("description", ""))
        if description and row.get("tag") and row.get("subtag"):
            label_rows.append(
                {
                    "source": "train.csv",
                    "severity": row.get("severity", ""),
                    "tag": row.get("tag", ""),
                    "subtag": row.get("subtag", ""),
                    "description": description,
                }
            )

    dataset_done_descriptions = set()
    for row in load_csv_rows(dataset_0831):
        description = normalize_space(row.get("description", ""))
        status = row.get("status", "").strip().lower()
        if status == "done" and description:
            dataset_done_descriptions.add(description)
            if row.get("tag") and row.get("subtag"):
                label_rows.append(
                    {
                        "source": "dataset_0831.csv",
                        "severity": row.get("severity", ""),
                        "tag": row.get("tag", ""),
                        "subtag": row.get("subtag", ""),
                        "description": description,
                    }
                )

    return label_rows, dataset_done_descriptions


def fit_label_vectorizer(label_rows):
    texts = [row["description"] for row in label_rows]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
    matrix = vectorizer.fit_transform(texts)
    return vectorizer, matrix


def best_label_match(text, label_rows, vectorizer, label_matrix):
    vector = vectorizer.transform([text])
    sims = cosine_similarity(vector, label_matrix)[0]
    best_index = int(sims.argmax())
    best_similarity = float(sims[best_index])
    return label_rows[best_index], best_similarity


def max_similarity_to_texts(text, existing_texts):
    existing_texts = [item for item in existing_texts if item]
    if not existing_texts:
        return 0.0
    corpus = [text] + existing_texts
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
    matrix = vectorizer.fit_transform(corpus)
    sims = cosine_similarity(matrix[0:1], matrix[1:])[0]
    return float(sims.max()) if len(sims) else 0.0


def row_description(row):
    return normalize_space(row.get("description", ""))


def add_property_numbers(rows):
    output = []
    for index, row in enumerate(rows, start=1):
        new_row = dict(row)
        new_row["Property"] = str(index)
        output.append(new_row)
    return output


def main():
    args = parse_args()
    teammate_rows = load_csv_rows(args.teammate)
    fieldnames = list(teammate_rows[0].keys())
    non_empty_rows = [row for row in teammate_rows if row.get("repo_path") != "empty"]
    teammate_counts = Counter(row["repo_path"] for row in non_empty_rows)
    teammate_sha = hashlib.sha256(Path(args.teammate).read_bytes()).hexdigest()

    label_rows, dataset_done_descriptions = build_label_rows(args.train_csv, args.dataset_0831)
    dataset_done_normalized = {normalize_space(item) for item in dataset_done_descriptions}
    label_vectorizer, label_matrix = fit_label_vectorizer(label_rows)

    added_rows = []
    skipped = []

    for target in TARGETS:
        existing_descriptions = [
            row_description(row)
            for row in non_empty_rows
            if row.get("repo_path") == target["repo_path"]
        ]
        selected_for_repo = 0
        for finding in parse_findings_from_cached(target["report"], target["platform"]):
            if selected_for_repo >= target["budget"]:
                break
            source_text = normalize_space(f"{finding['title']} {finding['body']}")
            duplicate_similarity = max_similarity_to_texts(source_text, existing_descriptions)
            if duplicate_similarity >= DEDUPE_SIM:
                skipped.append(
                    {
                        "repo_path": target["repo_path"],
                        "issue_id": finding["issue_id"],
                        "title": finding["title"],
                        "reason": "duplicate_against_teammate_repo",
                        "duplicate_similarity": duplicate_similarity,
                    }
                )
                continue

            label_match, label_similarity = best_label_match(
                source_text,
                label_rows,
                label_vectorizer,
                label_matrix,
            )
            if label_similarity < CLASSIFY_MIN_SIM:
                skipped.append(
                    {
                        "repo_path": target["repo_path"],
                        "issue_id": finding["issue_id"],
                        "title": finding["title"],
                        "reason": "classification_similarity_below_threshold",
                        "label_similarity": label_similarity,
                    }
                )
                continue

            description = build_description(finding["title"], finding["body"])
            if has_bad_description(description):
                skipped.append(
                    {
                        "repo_path": target["repo_path"],
                        "issue_id": finding["issue_id"],
                        "title": finding["title"],
                        "reason": "description_hygiene_failed",
                        "description": description,
                    }
                )
                continue

            row = {
                "Property": "",
                "repo_path": target["repo_path"],
                "severity": finding["severity"],
                "tag": label_match["tag"],
                "subtag": label_match["subtag"],
                "description": description,
            }
            added_rows.append(row)
            selected_for_repo += 1
            existing_descriptions.append(description)
            skipped.append(
                {
                    "repo_path": target["repo_path"],
                    "issue_id": finding["issue_id"],
                    "title": finding["title"],
                    "reason": "selected",
                    "label_similarity": label_similarity,
                    "duplicate_similarity": duplicate_similarity,
                    "tag": label_match["tag"],
                    "subtag": label_match["subtag"],
                    "label_source": label_match["source"],
                    "label_description": label_match["description"],
                }
            )

    scored_drop_candidates = []
    for row in non_empty_rows:
        description = row_description(row)
        if teammate_counts[row["repo_path"]] <= 5:
            continue
        if normalize_space(description) in dataset_done_normalized:
            continue
        label_match, label_similarity = best_label_match(
            description,
            label_rows,
            label_vectorizer,
            label_matrix,
        )
        scored_drop_candidates.append(
            {
                "row": row,
                "property": row.get("Property", ""),
                "repo_path": row.get("repo_path", ""),
                "severity": row.get("severity", ""),
                "tag": row.get("tag", ""),
                "subtag": row.get("subtag", ""),
                "description": description,
                "description_len": len(description),
                "label_similarity": label_similarity,
                "nearest_label_source": label_match["source"],
                "nearest_label_tag": label_match["tag"],
                "nearest_label_subtag": label_match["subtag"],
            }
        )

    scored_drop_candidates.sort(
        key=lambda item: (
            item["description_len"],
            item["label_similarity"],
            int(item["property"]) if str(item["property"]).isdigit() else 999999,
        )
    )
    dropped = scored_drop_candidates[: len(added_rows)]
    dropped_keys = {
        (
            item["row"].get("Property", ""),
            item["row"].get("repo_path", ""),
            item["row"].get("description", ""),
        )
        for item in dropped
    }

    remaining_rows = [
        row
        for row in non_empty_rows
        if (row.get("Property", ""), row.get("repo_path", ""), row.get("description", "")) not in dropped_keys
    ]
    final_rows = add_property_numbers(remaining_rows + added_rows)
    if len(final_rows) != args.target_rows:
        raise ValueError(f"Expected {args.target_rows} final rows, got {len(final_rows)}")

    write_csv_rows(args.output, final_rows, fieldnames)

    output_path = Path(args.output)
    final_sha = hashlib.sha256(output_path.read_bytes()).hexdigest()
    report = {
        "teammate_csv": str(Path(args.teammate).resolve()),
        "teammate_sha256": teammate_sha,
        "output_csv": str(output_path.resolve()),
        "output_sha256": final_sha,
        "target_rows": args.target_rows,
        "label_row_count": len(label_rows),
        "dataset_done_description_count": len(dataset_done_descriptions),
        "dedupe_similarity_threshold": DEDUPE_SIM,
        "classification_similarity_threshold": CLASSIFY_MIN_SIM,
        "max_new_description_chars": MAX_DESCRIPTION_CHARS,
        "added_count": len(added_rows),
        "dropped_count": len(dropped),
        "added_by_repo": dict(Counter(row["repo_path"] for row in added_rows)),
        "added_rows": added_rows,
        "dropped_rows": [
            {key: value for key, value in item.items() if key != "row"}
            for item in dropped
        ],
        "candidate_events": skipped,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(
        f"built_v9_candidate output={args.output} added={len(added_rows)} "
        f"dropped={len(dropped)} sha256={final_sha} report={args.report}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"build_v9_candidate failed: {exc}", file=sys.stderr)
        raise
