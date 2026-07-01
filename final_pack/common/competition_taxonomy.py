from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


REFERENCE_PATH = Path(__file__).resolve().parent.parent / "references" / "competition_tag_definitions.md"
TAG_HEADER_PREFIX = "## "


@dataclass(frozen=True)
class TagDefinition:
    name: str
    description: str
    knowledge: str
    related_subtags: tuple[str, ...]


def _parse_subtags(raw_value: str) -> tuple[str, ...]:
    subtags = re.findall(r"`([^`]+)`", raw_value)
    if subtags:
        return tuple(subtags)
    fallback = []
    for part in raw_value.split(","):
        cleaned = part.strip().strip("`")
        if cleaned:
            fallback.append(cleaned)
    return tuple(fallback)


@lru_cache(maxsize=4)
def load_competition_taxonomy(reference_path: str | None = None) -> dict[str, TagDefinition]:
    path = Path(reference_path) if reference_path else REFERENCE_PATH
    text = path.read_text(encoding="utf-8")
    taxonomy: dict[str, TagDefinition] = {}
    current_name = None
    current_fields: dict[str, object] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(TAG_HEADER_PREFIX):
            header = line[len(TAG_HEADER_PREFIX):].strip()
            if header in {"Tag", "Subtags"}:
                continue
            if current_name:
                taxonomy[current_name] = TagDefinition(
                    name=current_name,
                    description=str(current_fields.get("description", "")).strip(),
                    knowledge=str(current_fields.get("knowledge", "")).strip(),
                    related_subtags=tuple(current_fields.get("related_subtags", ())),
                )
            current_name = header
            current_fields = {"description": "", "knowledge": "", "related_subtags": ()}
            continue
        if not current_name:
            continue
        if line.startswith("- Description:"):
            current_fields["description"] = line.split(":", 1)[1].strip()
        elif line.startswith("- Knowledge:"):
            current_fields["knowledge"] = line.split(":", 1)[1].strip()
        elif line.startswith("- Related subtags:"):
            current_fields["related_subtags"] = _parse_subtags(line.split(":", 1)[1].strip())

    if current_name:
        taxonomy[current_name] = TagDefinition(
            name=current_name,
            description=str(current_fields.get("description", "")).strip(),
            knowledge=str(current_fields.get("knowledge", "")).strip(),
            related_subtags=tuple(current_fields.get("related_subtags", ())),
        )

    return taxonomy


def build_subtag_to_tags(reference_path: str | None = None) -> dict[str, tuple[str, ...]]:
    taxonomy = load_competition_taxonomy(reference_path)
    mapping: dict[str, list[str]] = {}
    for tag_name, tag_definition in taxonomy.items():
        for subtag in tag_definition.related_subtags:
            mapping.setdefault(subtag, []).append(tag_name)
    return {subtag: tuple(sorted(tag_names)) for subtag, tag_names in mapping.items()}


def casefold_tag_lookup(reference_path: str | None = None) -> dict[str, str]:
    taxonomy = load_competition_taxonomy(reference_path)
    return {tag_name.casefold(): tag_name for tag_name in taxonomy}


def format_prompt_block(
    active_tags: list[str] | None = None,
    include_descriptions: bool = True,
    reference_path: str | None = None,
) -> str:
    taxonomy = load_competition_taxonomy(reference_path)
    tag_names = active_tags or sorted(taxonomy)
    lines = ["Use only the following competition tags and subtags:"]
    for tag_name in tag_names:
        if tag_name not in taxonomy:
            continue
        tag_definition = taxonomy[tag_name]
        subtags = ", ".join(tag_definition.related_subtags)
        if include_descriptions:
            lines.append(f"- {tag_name}: {tag_definition.description}")
        else:
            lines.append(f"- {tag_name}")
        lines.append(f"  Allowed subtags: {subtags}")
    return "\n".join(lines)
