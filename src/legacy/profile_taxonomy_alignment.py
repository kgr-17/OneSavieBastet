from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from competition_taxonomy import (
    build_subtag_to_tags,
    casefold_tag_lookup,
    format_prompt_block,
    load_competition_taxonomy,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Profile train.csv against the saved competition taxonomy and export active priors."
    )
    parser.add_argument("--train-csv", default="train.csv")
    parser.add_argument("--taxonomy-md", default="")
    parser.add_argument("--output-dir", default="artifacts/taxonomy-profile")
    parser.add_argument("--min-pair-support", type=int, default=2)
    parser.add_argument("--min-pair-repos", type=int, default=2)
    return parser.parse_args()


def split_labels(raw_value: str) -> list[str]:
    return [part.strip() for part in str(raw_value).split(",") if part.strip()]


def normalize_description(text: str) -> str:
    return " ".join(str(text).replace("\r", " ").replace("\n", " ").split())


def choose_prototype(description_counts: Counter) -> str:
    if not description_counts:
        return ""
    ranked = sorted(
        description_counts.items(),
        key=lambda item: (-item[1], len(item[0]), item[0]),
    )
    return ranked[0][0]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    taxonomy = load_competition_taxonomy(args.taxonomy_md or None)
    subtag_to_tags = build_subtag_to_tags(args.taxonomy_md or None)
    casefold_lookup = casefold_tag_lookup(args.taxonomy_md or None)

    with open(args.train_csv, newline="", encoding="utf-8") as handle:
        train_rows = list(csv.DictReader(handle))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tag_counts = Counter()
    subtag_counts = Counter()
    severity_counts = Counter()
    tag_repo_sets = defaultdict(set)
    single_pair_stats = {}
    multi_label_sets = Counter()
    case_variant_tags = {}
    train_only_tags = Counter()

    for row in train_rows:
        repo_path = row["repo_path"]
        severity = row["severity"].strip()
        tags = split_labels(row["tag"])
        subtags = split_labels(row["subtag"])
        description = normalize_description(row["description"])

        severity_counts[severity] += 1
        if len(tags) > 1 or len(subtags) > 1:
            multi_label_sets[(tuple(sorted(tags)), tuple(sorted(subtags)))] += 1

        for tag in tags:
            tag_counts[tag] += 1
            tag_repo_sets[tag].add(repo_path)
            if tag not in taxonomy:
                canonical = casefold_lookup.get(tag.casefold())
                if canonical and canonical != tag:
                    case_variant_tags[tag] = canonical
                else:
                    train_only_tags[tag] += 1

        for subtag in subtags:
            subtag_counts[subtag] += 1

        if len(tags) == 1 and len(subtags) == 1:
            tag = tags[0]
            subtag = subtags[0]
            key = (tag, subtag, severity)
            if key not in single_pair_stats:
                single_pair_stats[key] = {
                    "tag": tag,
                    "subtag": subtag,
                    "severity": severity,
                    "count": 0,
                    "repos": set(),
                    "descriptions": Counter(),
                }
            single_pair_stats[key]["count"] += 1
            single_pair_stats[key]["repos"].add(repo_path)
            single_pair_stats[key]["descriptions"][description] += 1

    single_pair_rows = []
    active_core_rows = []
    for key, stats in single_pair_stats.items():
        tag = stats["tag"]
        canonical_tag = casefold_lookup.get(tag.casefold())
        exact_tag_match = tag in taxonomy
        case_variant_match = canonical_tag is not None and canonical_tag != tag
        allowed_subtags = ()
        if exact_tag_match:
            allowed_subtags = taxonomy[tag].related_subtags
        elif case_variant_match:
            allowed_subtags = taxonomy[canonical_tag].related_subtags
        subtag_allowed = stats["subtag"] in allowed_subtags if allowed_subtags else False
        row_payload = {
            "tag": tag,
            "subtag": stats["subtag"],
            "severity": stats["severity"],
            "count": stats["count"],
            "repo_count": len(stats["repos"]),
            "exact_taxonomy_tag": exact_tag_match,
            "case_variant_tag": case_variant_match,
            "canonical_tag": canonical_tag or "",
            "taxonomy_subtag_allowed": subtag_allowed,
            "prototype_description": choose_prototype(stats["descriptions"]),
        }
        single_pair_rows.append(row_payload)
        if (
            row_payload["count"] >= args.min_pair_support
            and row_payload["repo_count"] >= args.min_pair_repos
            and (row_payload["exact_taxonomy_tag"] or row_payload["case_variant_tag"])
        ):
            active_core_rows.append(row_payload)

    single_pair_rows.sort(
        key=lambda item: (-int(item["count"]), -int(item["repo_count"]), item["tag"], item["subtag"], item["severity"])
    )
    active_core_rows.sort(
        key=lambda item: (-int(item["count"]), -int(item["repo_count"]), item["tag"], item["subtag"], item["severity"])
    )

    active_tags = sorted({row["canonical_tag"] or row["tag"] for row in active_core_rows})
    exact_train_tags = sorted([tag for tag in tag_counts if tag in taxonomy])
    case_variant_rows = [
        {"train_tag": train_tag, "canonical_tag": canonical_tag, "count": tag_counts[train_tag]}
        for train_tag, canonical_tag in sorted(case_variant_tags.items())
    ]
    train_only_rows = [
        {"train_tag": train_tag, "count": count}
        for train_tag, count in sorted(train_only_tags.items(), key=lambda item: (-item[1], item[0]))
    ]

    summary = {
        "taxonomy_tag_count": len(taxonomy),
        "taxonomy_subtag_count": sum(len(item.related_subtags) for item in taxonomy.values()),
        "train_row_count": len(train_rows),
        "train_repo_count": len({row["repo_path"] for row in train_rows}),
        "train_distinct_tags": len(tag_counts),
        "train_distinct_subtags": len(subtag_counts),
        "single_label_row_count": sum(1 for row in train_rows if len(split_labels(row["tag"])) == 1 and len(split_labels(row["subtag"])) == 1),
        "multi_label_row_count": sum(1 for row in train_rows if len(split_labels(row["tag"])) > 1 or len(split_labels(row["subtag"])) > 1),
        "exact_taxonomy_train_tags": exact_train_tags,
        "case_variant_tags": case_variant_rows,
        "train_only_tags": train_only_rows,
        "active_core_tag_count": len(active_tags),
        "active_core_pair_count": len(active_core_rows),
        "severity_counts": dict(sorted(severity_counts.items())),
    }

    json_payload = {
        "summary": summary,
        "train_tag_counts": dict(sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))),
        "train_subtag_counts": dict(sorted(subtag_counts.items(), key=lambda item: (-item[1], item[0]))),
        "single_label_pairs": single_pair_rows,
        "active_core_pairs": active_core_rows,
        "top_multi_label_sets": [
            {
                "tags": list(tags),
                "subtags": list(subtags),
                "count": count,
            }
            for (tags, subtags), count in multi_label_sets.most_common(25)
        ],
        "subtag_to_tags": {key: list(value) for key, value in sorted(subtag_to_tags.items())},
    }

    (output_dir / "competition_taxonomy_profile.json").write_text(
        json.dumps(json_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "competition_taxonomy_prompt_block.txt").write_text(
        format_prompt_block(active_tags=active_tags, include_descriptions=True, reference_path=args.taxonomy_md or None),
        encoding="utf-8",
    )

    write_csv(
        output_dir / "active_core_pairs.csv",
        [
            "tag",
            "subtag",
            "severity",
            "count",
            "repo_count",
            "exact_taxonomy_tag",
            "case_variant_tag",
            "canonical_tag",
            "taxonomy_subtag_allowed",
            "prototype_description",
        ],
        active_core_rows,
    )

    summary_lines = [
        "Competition taxonomy profile",
        f"- Taxonomy tags: {summary['taxonomy_tag_count']}",
        f"- Taxonomy subtags: {summary['taxonomy_subtag_count']}",
        f"- Train rows: {summary['train_row_count']}",
        f"- Train repos: {summary['train_repo_count']}",
        f"- Distinct train tags: {summary['train_distinct_tags']}",
        f"- Distinct train subtags: {summary['train_distinct_subtags']}",
        f"- Single-label rows: {summary['single_label_row_count']}",
        f"- Multi-label rows: {summary['multi_label_row_count']}",
        f"- Active core tags: {summary['active_core_tag_count']}",
        f"- Active core pairs: {summary['active_core_pair_count']}",
        "",
        "Top train tags:",
    ]
    for tag, count in tag_counts.most_common(15):
        summary_lines.append(f"- {tag}: {count}")
    summary_lines.extend(["", "Case-variant tags:"])
    if case_variant_rows:
        for item in case_variant_rows:
            summary_lines.append(f"- {item['train_tag']} -> {item['canonical_tag']} ({item['count']})")
    else:
        summary_lines.append("- None")
    summary_lines.extend(["", "Train-only tags:"])
    if train_only_rows:
        for item in train_only_rows:
            summary_lines.append(f"- {item['train_tag']}: {item['count']}")
    else:
        summary_lines.append("- None")
    summary_lines.extend(["", "Top active core pairs:"])
    for item in active_core_rows[:20]:
        summary_lines.append(
            f"- {item['tag']} | {item['subtag']} | {item['severity']} "
            f"(count={item['count']}, repos={item['repo_count']})"
        )
    (output_dir / "competition_taxonomy_summary.txt").write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )

    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
