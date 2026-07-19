#!/usr/bin/env python3
"""Lint Nebula specifications, generate language registries, and detect breaks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SEMANTICS = ROOT / "specs" / "semantics"
SCHEMAS = ROOT / "schemas"


class SpecError(Exception):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise SpecError(f"{path.relative_to(ROOT)} must contain a YAML object")
    return value


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise SpecError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def validate(instance: Any, schema_path: Path, label: str) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{label}: {'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    ]


def duplicate_names(items: list[dict[str, Any]], label: str) -> list[str]:
    seen: set[str] = set()
    errors: list[str] = []
    for item in items:
        name = item.get("name")
        if name in seen:
            errors.append(f"duplicate {label}: {name}")
        seen.add(name)
    return errors


def registry() -> dict[str, Any]:
    attributes_doc = load_yaml(SEMANTICS / "attributes.yaml")
    events_doc = load_yaml(SEMANTICS / "events.yaml")
    metrics_doc = load_yaml(SEMANTICS / "metrics.yaml")
    spans_doc = load_yaml(SEMANTICS / "spans.yaml")
    enums_doc = load_yaml(SEMANTICS / "enums.yaml")
    return {
        "version": attributes_doc["registry_version"],
        "otel_schema_url": attributes_doc["otel_schema_url"],
        "attributes": attributes_doc["attributes"],
        "events": events_doc["events"],
        "metrics": metrics_doc["metrics"],
        "spans": spans_doc["spans"],
        "enums": enums_doc["enums"],
    }


def lint() -> None:
    data = registry()
    errors: list[str] = []

    attributes_doc = load_yaml(SEMANTICS / "attributes.yaml")
    privacy_policy = load_yaml(ROOT / "specs" / "privacy" / "default-policy.yaml")
    errors.extend(validate(attributes_doc, SCHEMAS / "semantic-attributes.schema.json", "attributes.yaml"))
    errors.extend(validate(privacy_policy, SCHEMAS / "privacy-policy.schema.json", "default-policy.yaml"))

    for key in ("attributes", "events", "metrics", "spans", "enums"):
        errors.extend(duplicate_names(data[key], key[:-1]))

    attributes = {item["name"]: item for item in data["attributes"]}
    enums = {item["name"]: item for item in data["enums"]}

    for item in data["attributes"]:
        name = item["name"]
        if item["source"] == "rutp" and not name.startswith("rum."):
            errors.append(f"RUTP extension attribute must use rum.*: {name}")
        if item["source"] == "otel" and name.startswith("rum."):
            errors.append(f"OTel attribute cannot use rum.*: {name}")
        if item["type"] == "enum" and item.get("enum") not in enums:
            errors.append(f"attribute {name} references unknown enum {item.get('enum')}")
        if item["type"] != "enum" and "enum" in item:
            errors.append(f"non-enum attribute {name} declares an enum")

    for enum in data["enums"]:
        values = enum.get("values", [])
        if not values:
            errors.append(f"enum has no values: {enum['name']}")
        if len(values) != len(set(values)):
            errors.append(f"enum has duplicate values: {enum['name']}")

    for collection in ("events", "spans"):
        for item in data[collection]:
            for attribute in item.get("attributes", []):
                if attribute["ref"] not in attributes:
                    errors.append(f"{collection[:-1]} {item['name']} references unknown attribute {attribute['ref']}")

    for metric in data["metrics"]:
        for attribute in metric.get("attributes", []):
            if attribute not in attributes:
                errors.append(f"metric {metric['name']} references unknown attribute {attribute}")

    apm = load_yaml(ROOT / "specs" / "apm" / "v1" / "manifest.yaml")
    for requirement in apm["resource"]["required"]:
        if requirement not in attributes:
            errors.append(f"APM required resource attribute is not registered: {requirement}")

    release = load_yaml(ROOT / "releases" / "2026.07.1-draft.yaml")
    errors.extend(validate(release, SCHEMAS / "release-manifest.schema.json", "release manifest"))

    fixture_manifest = load_yaml(ROOT / "fixtures" / "manifest.yaml")
    for fixture in fixture_manifest.get("fixtures", []):
        fixture_path = ROOT / fixture["path"]
        schema_path = ROOT / fixture["schema"]
        if not fixture_path.is_file():
            errors.append(f"fixture does not exist: {fixture['path']}")
            continue
        fixture_errors = validate(load_json(fixture_path), schema_path, fixture["path"])
        expected_valid = fixture.get("valid", True)
        if expected_valid:
            errors.extend(fixture_errors)
        elif not fixture_errors:
            errors.append(f"fixture was expected to be invalid: {fixture['path']}")

    for path in sorted((ROOT / "fixtures").rglob("*.json")):
        try:
            load_json(path)
        except (json.JSONDecodeError, SpecError) as error:
            errors.append(str(error))

    if errors:
        raise SpecError("Specification lint failed:\n- " + "\n- ".join(errors))
    print(
        "Specification lint passed: "
        f"{len(data['attributes'])} attributes, {len(data['events'])} events, "
        f"{len(data['metrics'])} metrics, {len(data['spans'])} spans, {len(data['enums'])} enums."
    )


def pascal_case(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[^A-Za-z0-9]+", value) if part)


def upper_snake(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()


def typescript_output(data: dict[str, Any]) -> str:
    lines = ["// Code generated by tools/spec_tool.py. DO NOT EDIT.", ""]
    for label, key in (("Attributes", "attributes"), ("Events", "events"), ("Metrics", "metrics"), ("Spans", "spans")):
        lines.append(f"export const {label} = {{")
        for item in sorted(data[key], key=lambda entry: entry["name"]):
            lines.append(f'  {pascal_case(item["name"])}: "{item["name"]}",')
        lines.extend(["} as const;", ""])
    for enum in sorted(data["enums"], key=lambda entry: entry["name"]):
        type_name = pascal_case(enum["name"])
        values = ", ".join(f'"{value}"' for value in enum["values"])
        lines.append(f"export const {type_name}Values = [{values}] as const;")
        lines.append(f"export type {type_name} = (typeof {type_name}Values)[number];")
        lines.append("")
    return "\n".join(lines)


def java_output(data: dict[str, Any]) -> str:
    lines = [
        "// Code generated by tools/spec_tool.py. DO NOT EDIT.",
        "package io.nebulaobservability.semantic;",
        "",
        "public final class NebulaSemanticRegistry {",
        "  private NebulaSemanticRegistry() {}",
    ]
    for label, key in (("Attributes", "attributes"), ("Events", "events"), ("Metrics", "metrics"), ("Spans", "spans")):
        lines.extend(["", f"  public static final class {label} {{", f"    private {label}() {{}}"])
        for item in sorted(data[key], key=lambda entry: entry["name"]):
            lines.append(f'    public static final String {upper_snake(item["name"])} = "{item["name"]}";')
        lines.append("  }")
    for enum in sorted(data["enums"], key=lambda entry: entry["name"]):
        type_name = pascal_case(enum["name"])
        lines.extend(["", f"  public enum {type_name} {{"])
        values = enum["values"]
        for index, value in enumerate(values):
            suffix = "," if index < len(values) - 1 else ";"
            lines.append(f'    {upper_snake(value)}("{value}"){suffix}')
        lines.extend(
            [
                "",
                "    private final String value;",
                f"    {type_name}(String value) {{ this.value = value; }}",
                "    public String value() { return value; }",
                "  }",
            ]
        )
    lines.extend(["}", ""])
    return "\n".join(lines)


def go_output(data: dict[str, Any]) -> str:
    lines = ["// Code generated by tools/spec_tool.py. DO NOT EDIT.", "package semantic", ""]
    for label, key, prefix in (
        ("Attributes", "attributes", "Attribute"),
        ("Events", "events", "Event"),
        ("Metrics", "metrics", "Metric"),
        ("Spans", "spans", "Span"),
    ):
        lines.append(f"// {label}")
        for item in sorted(data[key], key=lambda entry: entry["name"]):
            lines.append(f'const {prefix}{pascal_case(item["name"])} = "{item["name"]}"')
        lines.append("")
    for enum in sorted(data["enums"], key=lambda entry: entry["name"]):
        type_name = pascal_case(enum["name"])
        lines.extend([f"type {type_name} string", ""])
        for value in enum["values"]:
            lines.append(f'const {type_name}{pascal_case(value)} {type_name} = "{value}"')
        lines.append("")
    return "\n".join(lines)


def generated_files(data: dict[str, Any]) -> dict[Path, str]:
    return {
        ROOT / "generated" / "typescript" / "registry.ts": typescript_output(data),
        ROOT / "generated" / "java" / "io" / "nebulaobservability" / "semantic" / "NebulaSemanticRegistry.java": java_output(data),
        ROOT / "generated" / "go" / "semantic" / "registry.go": go_output(data),
    }


def generate(check: bool) -> None:
    failures: list[str] = []
    for path, content in generated_files(registry()).items():
        content = content.rstrip() + "\n"
        if check:
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != content:
                failures.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if failures:
        raise SpecError("Generated files are stale: " + ", ".join(failures))
    print("Generated files are current." if check else "Generated TypeScript, Java, and Go registries.")


def snapshot_data(data: dict[str, Any]) -> dict[str, Any]:
    def by_name(items: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
        return {item["name"]: {field: item.get(field) for field in fields} for item in sorted(items, key=lambda entry: entry["name"])}

    return {
        "registry_version": data["version"],
        "attributes": by_name(data["attributes"], ("type", "enum", "requirement", "privacy")),
        "events": by_name(data["events"], ("stability", "attributes")),
        "metrics": by_name(data["metrics"], ("instrument", "value_type", "unit", "attributes")),
        "spans": by_name(data["spans"], ("kind", "attributes")),
        "enums": by_name(data["enums"], ("values",)),
    }


def write_snapshot(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot_data(registry()), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote compatibility snapshot: {output.relative_to(ROOT)}")


def breaking(against: Path) -> None:
    baseline = load_json(against)
    current = snapshot_data(registry())
    errors: list[str] = []

    for collection in ("attributes", "events", "metrics", "spans", "enums"):
        old_items = baseline.get(collection, {})
        new_items = current.get(collection, {})
        for name in sorted(set(old_items) - set(new_items)):
            errors.append(f"removed {collection[:-1]}: {name}")

    for name, old in baseline.get("attributes", {}).items():
        new = current["attributes"].get(name)
        if not new:
            continue
        for field in ("type", "enum", "privacy"):
            if old.get(field) != new.get(field):
                errors.append(f"attribute {name} changed {field}: {old.get(field)} -> {new.get(field)}")
        if old.get("requirement") != "required" and new.get("requirement") == "required":
            errors.append(f"attribute {name} became required")

    for name, old in baseline.get("enums", {}).items():
        new = current["enums"].get(name)
        if not new:
            continue
        removed_values = set(old.get("values", [])) - set(new.get("values", []))
        if removed_values:
            errors.append(f"enum {name} removed values: {', '.join(sorted(removed_values))}")

    if errors:
        raise SpecError("Breaking changes detected:\n- " + "\n- ".join(errors))
    print(f"No breaking changes against {against.relative_to(ROOT)}.")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("lint")
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--check", action="store_true")
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--output", type=Path, required=True)
    breaking_parser = subparsers.add_parser("breaking")
    breaking_parser.add_argument("--against", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "lint":
            lint()
        elif args.command == "generate":
            generate(args.check)
        elif args.command == "snapshot":
            write_snapshot(args.output.resolve())
        elif args.command == "breaking":
            breaking(args.against.resolve())
    except SpecError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
