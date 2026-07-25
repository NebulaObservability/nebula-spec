#!/usr/bin/env python3
"""Lint Nebula specifications, generate language registries, and detect breaks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SEMANTICS = ROOT / "specs" / "semantics"
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "fixtures"
RUTP = ROOT / "specs" / "rum" / "rutp" / "v1"
RELEASES = ROOT / "releases"
CURRENT_RELEASE = RELEASES / "CURRENT"
RECEIVER_FIXTURES = FIXTURES / "receiver"
RECEIVER_FIXTURE_SCHEMA = SCHEMAS / "rutp-receiver-conformance.schema.json"
GO_MODULE = ROOT / "generated" / "go"
GO_MODULE_PATH = "github.com/NebulaObservability/nebula-spec/generated/go"
GO_PROTOBUF_VERSION = "v1.36.6"
TYPESCRIPT_RUTP = ROOT / "generated" / "typescript-rutp"
TYPESCRIPT_PROTOBUF_VERSION = "2.10.0"
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:[.][0-9A-Za-z-]+)*))?"
    r"(?:[+]([0-9A-Za-z-]+(?:[.][0-9A-Za-z-]+)*))?$"
)


class SpecError(Exception):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise SpecError(f"{path.relative_to(ROOT)} must contain a YAML object")
    return value


def load_json(path: Path) -> dict[str, Any]:
    def object_with_unique_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise SpecError(f"{path.relative_to(ROOT)} contains duplicate JSON member: {key}")
            value[key] = item
        return value

    with path.open(encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=object_with_unique_members)
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


def validation_error_paths(instance: Any, schema_path: Path) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(
        {"/".join(str(part) for part in error.absolute_path) or "<root>" for error in validator.iter_errors(instance)}
    )


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


def artifact_version() -> str:
    value = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if SEMVER_PATTERN.fullmatch(value) is None:
        raise SpecError(f"VERSION is not a semantic version: {value}")
    return value


def parse_semver(value: str) -> tuple[int, int, int, tuple[str, ...] | None]:
    match = SEMVER_PATTERN.fullmatch(value)
    if match is None:
        raise SpecError(f"invalid semantic version: {value}")
    major, minor, patch, prerelease, _build = match.groups()
    return int(major), int(minor), int(patch), tuple(prerelease.split(".")) if prerelease else None


def compare_semver(left: str, right: str) -> int:
    left_major, left_minor, left_patch, left_pre = parse_semver(left)
    right_major, right_minor, right_patch, right_pre = parse_semver(right)
    left_core = (left_major, left_minor, left_patch)
    right_core = (right_major, right_minor, right_patch)
    if left_core != right_core:
        return -1 if left_core < right_core else 1
    if left_pre is None or right_pre is None:
        if left_pre is right_pre:
            return 0
        return 1 if left_pre is None else -1
    for left_item, right_item in zip(left_pre, right_pre):
        if left_item == right_item:
            continue
        left_numeric = left_item.isdigit()
        right_numeric = right_item.isdigit()
        if left_numeric and right_numeric:
            return -1 if int(left_item) < int(right_item) else 1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return -1 if left_item < right_item else 1
    if len(left_pre) == len(right_pre):
        return 0
    return -1 if len(left_pre) < len(right_pre) else 1


def semver_satisfies(version: str, expression: str) -> bool:
    tokens = expression.split()
    if not tokens:
        raise SpecError("semantic version range must not be empty")
    for token in tokens:
        match = re.fullmatch(r"(>=|<=|>|<|=)?(.+)", token)
        if match is None:
            raise SpecError(f"invalid semantic version comparator: {token}")
        operator, boundary = match.groups()
        comparison = compare_semver(version, boundary)
        if operator == ">=" and comparison < 0:
            return False
        if operator == "<=" and comparison > 0:
            return False
        if operator == ">" and comparison <= 0:
            return False
        if operator == "<" and comparison >= 0:
            return False
        if operator in (None, "=") and comparison != 0:
            return False
    return True


def current_release_path() -> Path:
    try:
        filename = CURRENT_RELEASE.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise SpecError(f"cannot read current release pointer: {error}") from error
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]*[.]yaml", filename):
        raise SpecError("releases/CURRENT must contain one release manifest filename")
    path = (RELEASES / filename).resolve()
    if path.parent != RELEASES.resolve() or not path.is_file():
        raise SpecError(f"current release manifest does not exist: {filename}")
    return path


def release_manifest_paths() -> list[Path]:
    paths = sorted(RELEASES.glob("*.yaml"))
    if not paths:
        raise SpecError("releases must contain at least one release manifest")
    current = current_release_path()
    if current not in paths:
        raise SpecError("releases/CURRENT must point to a YAML release manifest")
    return paths


def current_release() -> dict[str, Any]:
    return load_yaml(current_release_path())


def receiver_conformance_errors() -> list[str]:
    errors: list[str] = []
    if not RECEIVER_FIXTURES.is_dir():
        return ["fixtures/receiver is missing"]

    fixture_paths = sorted(RECEIVER_FIXTURES.glob("*.json"))
    if not fixture_paths:
        return ["fixtures/receiver must contain conformance cases"]

    coverage = {
        "accepted_binding": False,
        "missing_ingest_permission": False,
        "project_mismatch": False,
        "json_debug_unknown_members": False,
        "json_debug_explicit_opt_in": False,
        "json_debug_not_authorized": False,
    }
    for path in fixture_paths:
        label = path.relative_to(ROOT).as_posix()
        try:
            fixture = load_json(path)
        except (OSError, json.JSONDecodeError, SpecError) as error:
            errors.append(f"{label}: {error}")
            continue

        schema_errors = validate(fixture, RECEIVER_FIXTURE_SCHEMA, label)
        if schema_errors:
            errors.extend(schema_errors)
            continue

        request = fixture["request"]
        principal = request["authenticated_principal"]
        expected = fixture["expected"]
        permissions = set(principal["permissions"])
        content_type = request["content_type"]
        declared_project_id = request["declared_project_id"]
        bound_project_id = principal["project_id"]

        if "rum.ingest" not in permissions:
            expected_outcome = "rejected"
            expected_rejection = "ingest_not_authorized"
            coverage["missing_ingest_permission"] = True
        elif content_type == "application/json" and request.get("debug_opt_in") is not True:
            expected_outcome = "rejected"
            expected_rejection = "json_debug_opt_in_required"
            coverage["json_debug_explicit_opt_in"] = True
        elif content_type == "application/json" and "rum.ingest.debug" not in permissions:
            expected_outcome = "rejected"
            expected_rejection = "json_debug_not_authorized"
            coverage["json_debug_not_authorized"] = True
        elif declared_project_id != bound_project_id:
            expected_outcome = "rejected"
            expected_rejection = "project_binding_mismatch"
            coverage["project_mismatch"] = True
        else:
            expected_outcome = "accepted"
            expected_rejection = None
            if content_type == "application/x-protobuf":
                coverage["accepted_binding"] = True
            elif request.get("unknown_json_members"):
                coverage["json_debug_unknown_members"] = True

        if expected["outcome"] != expected_outcome:
            errors.append(f"{label}: expected outcome must be {expected_outcome}")
        if expected_rejection is None:
            if expected.get("resolved_tenant_id") != principal["tenant_id"]:
                errors.append(f"{label}: accepted request must use the principal tenant binding")
            if expected.get("resolved_project_id") != bound_project_id:
                errors.append(f"{label}: accepted request must use the principal project binding")
            if "rejection_code" in expected:
                errors.append(f"{label}: accepted request must not expose a rejection code")
        else:
            if expected.get("rejection_code") != expected_rejection:
                errors.append(f"{label}: expected rejection code must be {expected_rejection}")
            if "resolved_tenant_id" in expected or "resolved_project_id" in expected:
                errors.append(f"{label}: rejected request must not expose a resolved binding")

        expected_unknown_handling = "discarded" if content_type == "application/json" else "not_applicable"
        if expected["unknown_json_members"] != expected_unknown_handling:
            errors.append(f"{label}: unknown JSON member handling must be {expected_unknown_handling}")
        if content_type != "application/json" and "unknown_json_members" in request:
            errors.append(f"{label}: non-JSON request must not declare JSON members")
        if content_type != "application/json" and "debug_opt_in" in request:
            errors.append(f"{label}: non-JSON request must not declare JSON debug opt-in")

    for name, covered in coverage.items():
        if not covered:
            errors.append(f"fixtures/receiver is missing required coverage: {name}")
    return errors


def verify_receiver_contract() -> None:
    errors = receiver_conformance_errors()
    if errors:
        raise SpecError("RUTP Receiver conformance failed:\n- " + "\n- ".join(errors))
    print("RUTP Receiver authentication and JSON debug conformance passed.")


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

    for release_path in release_manifest_paths():
        release = load_yaml(release_path)
        errors.extend(
            validate(
                release,
                SCHEMAS / "release-manifest.schema.json",
                release_path.relative_to(ROOT).as_posix(),
            )
        )

    active_release = current_release()
    components = active_release.get("components")
    if not isinstance(components, dict) or components.get("spec") != artifact_version():
        errors.append("current release manifest components.spec must match VERSION")

    protocol_matrix = load_yaml(ROOT / "compatibility" / "protocol-matrix.yaml")
    matrix_rutp_config = protocol_matrix.get("protocols", {}).get("rutp", {})
    matrix_rutp = matrix_rutp_config.get("current")
    accepted_rutp_ranges = matrix_rutp_config.get("accepts", [])
    release_rutp = active_release.get("protocols", {}).get("rutp")
    if matrix_rutp != release_rutp:
        errors.append("current release manifest RUTP version must match compatibility/protocol-matrix.yaml")

    try:
        parse_semver(str(release_rutp))
        if not isinstance(accepted_rutp_ranges, list) or not accepted_rutp_ranges:
            errors.append("compatibility/protocol-matrix.yaml must declare accepted RUTP ranges")
        elif not any(semver_satisfies(str(release_rutp), str(expression)) for expression in accepted_rutp_ranges):
            errors.append("current release RUTP version must be included in the compatibility acceptance range")
    except SpecError as error:
        errors.append(str(error))

    versioned_schema_paths = (SCHEMAS / "rum-batch.schema.json", SCHEMAS / "rum-config.schema.json")
    for schema_path in versioned_schema_paths:
        schema = load_json(schema_path)
        version_schema = schema.get("properties", {}).get("protocol_version", {})
        if not Draft202012Validator(version_schema).is_valid(release_rutp):
            errors.append(
                f"{schema_path.relative_to(ROOT).as_posix()} must accept the current release RUTP version"
            )
    config_version = load_json(SCHEMAS / "rum-config.schema.json").get("properties", {}).get("protocol_version", {}).get("const")
    if config_version != release_rutp:
        errors.append("schemas/rum-config.schema.json protocol_version must equal the current release RUTP version")

    fixture_manifest = load_yaml(ROOT / "fixtures" / "manifest.yaml")
    for fixture in fixture_manifest.get("fixtures", []):
        fixture_path = ROOT / fixture["path"]
        schema_path = ROOT / fixture["schema"]
        if not fixture_path.is_file():
            errors.append(f"fixture does not exist: {fixture['path']}")
            continue
        fixture_data = load_json(fixture_path)
        fixture_errors = validate(fixture_data, schema_path, fixture["path"])
        expected_valid = fixture.get("valid", True)
        if expected_valid:
            errors.extend(fixture_errors)
        else:
            if not fixture_errors:
                errors.append(f"fixture was expected to be invalid: {fixture['path']}")
            expected_error_paths = fixture.get("expected_error_paths")
            if not isinstance(expected_error_paths, list) or not expected_error_paths:
                errors.append(f"invalid fixture must declare expected_error_paths: {fixture['path']}")
            else:
                actual_error_paths = validation_error_paths(fixture_data, schema_path)
                if sorted(expected_error_paths) != actual_error_paths:
                    errors.append(
                        f"{fixture['path']} validation errors must occur at {sorted(expected_error_paths)}, got {actual_error_paths}"
                    )

        protocol_expectation = fixture.get("protocol_expectation")
        if schema_path in versioned_schema_paths:
            fixture_rutp = fixture_data.get("protocol_version")
            if protocol_expectation == "current":
                if fixture_rutp != release_rutp:
                    errors.append(f"{fixture['path']} protocol_version must match the current release RUTP version")
            elif protocol_expectation == "compatible_future":
                try:
                    if fixture_rutp == release_rutp or not any(
                        semver_satisfies(str(fixture_rutp), str(expression)) for expression in accepted_rutp_ranges
                    ):
                        errors.append(f"{fixture['path']} must exercise a compatible future RUTP version")
                except SpecError as error:
                    errors.append(f"{fixture['path']}: {error}")
            elif protocol_expectation == "unsupported":
                try:
                    if any(semver_satisfies(str(fixture_rutp), str(expression)) for expression in accepted_rutp_ranges):
                        errors.append(f"{fixture['path']} must exercise an unsupported RUTP version")
                except SpecError as error:
                    errors.append(f"{fixture['path']}: {error}")
            else:
                errors.append(f"versioned fixture must declare protocol_expectation: {fixture['path']}")

    for path in sorted((ROOT / "fixtures").rglob("*.json")):
        try:
            load_json(path)
        except (json.JSONDecodeError, SpecError) as error:
            errors.append(str(error))

    errors.extend(receiver_conformance_errors())

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


def typescript_javascript_output(data: dict[str, Any]) -> str:
    lines = ["// Code generated by tools/spec_tool.py. DO NOT EDIT.", ""]
    for label, key in (("Attributes", "attributes"), ("Events", "events"), ("Metrics", "metrics"), ("Spans", "spans")):
        lines.append(f"export const {label} = Object.freeze({{")
        for item in sorted(data[key], key=lambda entry: entry["name"]):
            lines.append(f'  {pascal_case(item["name"])}: "{item["name"]}",')
        lines.extend(["});", ""])
    for enum in sorted(data["enums"], key=lambda entry: entry["name"]):
        type_name = pascal_case(enum["name"])
        values = ", ".join(f'"{value}"' for value in enum["values"])
        lines.append(f"export const {type_name}Values = Object.freeze([{values}]);")
        lines.append("")
    return "\n".join(lines)


def typescript_declaration_output(data: dict[str, Any]) -> str:
    lines = ["// Code generated by tools/spec_tool.py. DO NOT EDIT.", ""]
    for label, key in (("Attributes", "attributes"), ("Events", "events"), ("Metrics", "metrics"), ("Spans", "spans")):
        lines.append(f"export declare const {label}: {{")
        for item in sorted(data[key], key=lambda entry: entry["name"]):
            lines.append(f'  readonly {pascal_case(item["name"])}: "{item["name"]}";')
        lines.extend(["};", ""])
    for enum in sorted(data["enums"], key=lambda entry: entry["name"]):
        type_name = pascal_case(enum["name"])
        values = ", ".join(f'"{value}"' for value in enum["values"])
        lines.append(f"export declare const {type_name}Values: readonly [{values}];")
        lines.append(f"export type {type_name} = (typeof {type_name}Values)[number];")
        lines.append("")
    return "\n".join(lines)


def typescript_package_json_output() -> str:
    return json.dumps(
        {
            "name": "@nebula-observability/semantic-registry",
            "version": artifact_version(),
            "description": "Generated Nebula Observability semantic registry.",
            "license": "Apache-2.0",
            "type": "module",
            "sideEffects": False,
            "exports": {
                ".": {
                    "types": "./registry.d.ts",
                    "import": "./registry.js",
                    "default": "./registry.js",
                }
            },
            "files": ["registry.js", "registry.d.ts", "README.md"],
        },
        indent=2,
    ) + "\n"


def typescript_package_readme_output() -> str:
    return """# @nebula-observability/semantic-registry

Generated semantic names and enum values for Nebula Observability consumers.

This package is generated from `nebula-spec`. Do not edit its contents or copy
the registry into an implementation repository. Upgrade it through a versioned
`nebula-spec` release.
"""


def typescript_rutp_package_json_output() -> str:
    return json.dumps(
        {
            "name": "@nebula-observability/rutp-protobuf",
            "version": artifact_version(),
            "description": "Generated browser-compatible Nebula RUTP v1 Protobuf codec.",
            "license": "Apache-2.0",
            "type": "module",
            "sideEffects": False,
            "exports": {
                ".": {
                    "types": "./index.d.ts",
                    "import": "./index.js",
                    "default": "./index.js",
                }
            },
            "files": [
                "index.js",
                "index.d.ts",
                "version.js",
                "version.d.ts",
                "codec.js",
                "codec.d.ts",
                "rum",
                "README.md",
            ],
            "dependencies": {"@bufbuild/protobuf": TYPESCRIPT_PROTOBUF_VERSION},
            "engines": {"node": ">=18"},
        },
        indent=2,
    ) + "\n"


def typescript_rutp_index_output() -> str:
    modules = ("batch", "common", "config", "context", "record", "replay")
    lines = [
        "// Code generated by tools/spec_tool.py. DO NOT EDIT.",
        'export * from "./version.js";',
        'export * from "./codec.js";',
    ]
    lines.extend(f'export * from "./rum/rutp/v1/{module}_pb.js";' for module in modules)
    return "\n".join(lines) + "\n"


def typescript_rutp_version_output() -> str:
    return f'''// Code generated by tools/spec_tool.py. DO NOT EDIT.
export const SpecVersion = "{artifact_version()}";
export const ProtocolVersion = "{rutp_protocol_version()}";
'''


def typescript_rutp_version_declaration_output() -> str:
    return f'''// Code generated by tools/spec_tool.py. DO NOT EDIT.
export declare const SpecVersion: "{artifact_version()}";
export declare const ProtocolVersion: "{rutp_protocol_version()}";
'''


def typescript_rutp_codec_output() -> str:
    return """// Code generated by tools/spec_tool.py. DO NOT EDIT.
import { fromBinary, toBinary } from "@bufbuild/protobuf";
import { BatchAckSchema, RumBatchSchema } from "./rum/rutp/v1/batch_pb.js";

export function encodeRumBatch(batch) {
  return toBinary(RumBatchSchema, batch);
}

export function decodeRumBatch(bytes) {
  return fromBinary(RumBatchSchema, bytes);
}

export function encodeBatchAck(ack) {
  return toBinary(BatchAckSchema, ack);
}

export function decodeBatchAck(bytes) {
  return fromBinary(BatchAckSchema, bytes);
}
"""


def typescript_rutp_codec_declaration_output() -> str:
    return """// Code generated by tools/spec_tool.py. DO NOT EDIT.
import type { BatchAck, RumBatch } from "./rum/rutp/v1/batch_pb.js";

export declare function encodeRumBatch(batch: RumBatch): Uint8Array;
export declare function decodeRumBatch(bytes: Uint8Array): RumBatch;
export declare function encodeBatchAck(ack: BatchAck): Uint8Array;
export declare function decodeBatchAck(bytes: Uint8Array): BatchAck;
"""


def typescript_rutp_package_readme_output() -> str:
    return f"""# @nebula-observability/rutp-protobuf

Browser-compatible RUTP v1 Protobuf schemas and binary codec generated from
`nebula-spec` with `protoc-gen-es`. The package version is `{artifact_version()}`
and the RUTP wire version is `{rutp_protocol_version()}`.

Import `SpecVersion` and `ProtocolVersion` from the package root. Use
`ProtocolVersion` when constructing RUTP batches and signed configurations so
the wire value stays aligned with the released codec.

Use `create(RumBatchSchema, init)` from `@bufbuild/protobuf` to create a batch,
then call `encodeRumBatch` before sending it as `application/x-protobuf`.
Decode receiver acknowledgements with `decodeBatchAck`.

Do not copy generated message definitions into an SDK or service repository.
Pin and verify the matching immutable `nebula-spec` release asset instead.
"""


def rust_identifier(value: str) -> str:
    identifier = upper_snake(value)
    return f"r#{identifier.lower()}" if identifier.lower() in {"self", "super", "crate", "type", "match", "ref"} else identifier


def rust_output(data: dict[str, Any]) -> str:
    lines = [
        "// Code generated by tools/spec_tool.py. DO NOT EDIT.",
        "#![forbid(unsafe_code)]",
        "",
        f'pub const REGISTRY_VERSION: &str = "{artifact_version()}";',
        f'pub const OTEL_SCHEMA_URL: &str = "{data["otel_schema_url"]}";',
        "",
    ]
    for label, key in (("attributes", "attributes"), ("events", "events"), ("metrics", "metrics"), ("spans", "spans")):
        lines.append(f"pub mod {label} {{")
        for item in sorted(data[key], key=lambda entry: entry["name"]):
            lines.append(f'    pub const {rust_identifier(item["name"])}: &str = "{item["name"]}";')
        lines.extend(["}", ""])
    for enum in sorted(data["enums"], key=lambda entry: entry["name"]):
        type_name = pascal_case(enum["name"])
        lines.extend(
            [
                "#[derive(Clone, Copy, Debug, Eq, PartialEq)]",
                f"pub enum {type_name} {{",
            ]
        )
        for value in enum["values"]:
            lines.append(f"    {pascal_case(value)},")
        lines.extend(["}", "", f"impl {type_name} {{", "    pub const fn as_str(self) -> &'static str {"])
        lines.append("        match self {")
        for value in enum["values"]:
            lines.append(f'            Self::{pascal_case(value)} => "{value}",')
        lines.extend(["        }", "    }", "}", ""])
    return "\n".join(lines)


def rust_cargo_toml_output() -> str:
    return f"""# Code generated by tools/spec_tool.py. DO NOT EDIT.
[package]
name = "nebula-semantic-registry"
version = "{artifact_version()}"
edition = "2021"
rust-version = "1.85"
description = "Generated Nebula Observability semantic registry."
license = "Apache-2.0"
repository = "https://github.com/NebulaObservability/nebula-spec"
include = ["src/**", "README.md", "Cargo.toml", "Cargo.lock"]

[lib]
path = "src/lib.rs"
"""


def rust_cargo_lock_output() -> str:
    return f"""# Code generated by tools/spec_tool.py. DO NOT EDIT.
# This file is automatically @generated by Cargo.
version = 4

[[package]]
name = "nebula-semantic-registry"
version = "{artifact_version()}"
"""


def rust_package_readme_output() -> str:
    return """# nebula-semantic-registry

Generated Rust semantic names and enum values for Nebula Observability Native
SDKs. This crate is generated from `nebula-spec`; consumers must upgrade through
a versioned specification release instead of copying constants.
"""


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
    lines = [
        "// Code generated by tools/spec_tool.py. DO NOT EDIT.",
        "package semantic",
        "",
        f'const RegistryVersion = "{artifact_version()}"',
        f'const OTelSchemaURL = "{data["otel_schema_url"]}"',
        "",
    ]
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


def rutp_protocol_version() -> str:
    release = current_release()
    protocols = release.get("protocols")
    if not isinstance(protocols, dict) or not isinstance(protocols.get("rutp"), str):
        raise SpecError("release manifest must declare protocols.rutp")
    return protocols["rutp"]


def go_mod_output() -> str:
    return f"""// Code generated by tools/spec_tool.py. DO NOT EDIT.
module {GO_MODULE_PATH}

go 1.22

require google.golang.org/protobuf {GO_PROTOBUF_VERSION}
"""


def go_module_readme_output() -> str:
    version = artifact_version()
    return f"""# Nebula RUTP Go Module

Generated RUTP v1 Protobuf messages and Nebula semantic registry for Go
Collector and Backend consumers.

Module: `{GO_MODULE_PATH}`
Specification version: `{version}`
RUTP version: `{rutp_protocol_version()}`

Use the matching immutable Go module tag `generated/go/v{version}`:

```go
import (
    rutpv1 "{GO_MODULE_PATH}/rum/rutp/v1"
    "{GO_MODULE_PATH}/semantic"
)
```

`rum/rutp/v1/*.pb.go` is generated by the pinned `buf.gen.yaml` template.
`semantic/registry.go` and `rum/rutp/v1/version.go` are generated by
`tools/spec_tool.py`. Do not replace the Protobuf wire contract with the JSON
debug schemas or copy these sources into an implementation repository.
"""


def go_rutp_metadata_output() -> str:
    return f"""// Code generated by tools/spec_tool.py. DO NOT EDIT.
package rutpv1

const SpecVersion = "{artifact_version()}"
const ProtocolVersion = "{rutp_protocol_version()}"
"""


def fixture_kind(path: Path) -> str:
    relative = path.relative_to(FIXTURES)
    return relative.parts[0] if len(relative.parts) > 1 else "generic"


def conformance_manifest_output() -> str:
    release = current_release()
    fixtures: list[dict[str, str]] = []
    for path in sorted(FIXTURES.rglob("*.json")):
        relative = path.relative_to(ROOT).as_posix()
        fixtures.append(
            {
                "path": relative,
                "kind": fixture_kind(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return json.dumps(
        {
            "format_version": 1,
            "spec_version": artifact_version(),
            "release": release["release"],
            "protocols": release["protocols"],
            "fixtures": fixtures,
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def conformance_package_json_output() -> str:
    return json.dumps(
        {
            "name": "@nebula-observability/rum-conformance",
            "version": artifact_version(),
            "description": "Generated Nebula RUM conformance fixtures.",
            "license": "Apache-2.0",
            "type": "module",
            "files": ["fixture-manifest.json", "fixtures", "README.md"],
        },
        indent=2,
    ) + "\n"


def conformance_readme_output() -> str:
    return """# @nebula-observability/rum-conformance

Generated, versioned RUM conformance fixtures. Verify every fixture against
`fixture-manifest.json` before executing it. This package is produced by
`nebula-spec`; implementation repositories must not copy these inputs.
"""


def conformance_fixture_outputs() -> dict[Path, str]:
    output: dict[Path, str] = {
        ROOT / "generated" / "conformance" / "package.json": conformance_package_json_output(),
        ROOT / "generated" / "conformance" / "README.md": conformance_readme_output(),
        ROOT / "generated" / "conformance" / "fixture-manifest.json": conformance_manifest_output(),
    }
    for path in sorted(FIXTURES.rglob("*.json")):
        relative = path.relative_to(FIXTURES)
        output[ROOT / "generated" / "conformance" / "fixtures" / relative] = path.read_text(encoding="utf-8")
    return output


def generated_files(data: dict[str, Any]) -> dict[Path, str]:
    output = {
        ROOT / "generated" / "typescript" / "registry.ts": typescript_output(data),
        ROOT / "generated" / "typescript" / "registry.js": typescript_javascript_output(data),
        ROOT / "generated" / "typescript" / "registry.d.ts": typescript_declaration_output(data),
        ROOT / "generated" / "typescript" / "package.json": typescript_package_json_output(),
        ROOT / "generated" / "typescript" / "README.md": typescript_package_readme_output(),
        TYPESCRIPT_RUTP / "package.json": typescript_rutp_package_json_output(),
        TYPESCRIPT_RUTP / "README.md": typescript_rutp_package_readme_output(),
        TYPESCRIPT_RUTP / "index.js": typescript_rutp_index_output(),
        TYPESCRIPT_RUTP / "index.d.ts": typescript_rutp_index_output(),
        TYPESCRIPT_RUTP / "version.js": typescript_rutp_version_output(),
        TYPESCRIPT_RUTP / "version.d.ts": typescript_rutp_version_declaration_output(),
        TYPESCRIPT_RUTP / "codec.js": typescript_rutp_codec_output(),
        TYPESCRIPT_RUTP / "codec.d.ts": typescript_rutp_codec_declaration_output(),
        ROOT / "generated" / "java" / "io" / "nebulaobservability" / "semantic" / "NebulaSemanticRegistry.java": java_output(data),
        GO_MODULE / "go.mod": go_mod_output(),
        GO_MODULE / "README.md": go_module_readme_output(),
        GO_MODULE / "semantic" / "registry.go": go_output(data),
        GO_MODULE / "rum" / "rutp" / "v1" / "version.go": go_rutp_metadata_output(),
        ROOT / "generated" / "rust" / "nebula-semantic-registry" / "Cargo.toml": rust_cargo_toml_output(),
        ROOT / "generated" / "rust" / "nebula-semantic-registry" / "Cargo.lock": rust_cargo_lock_output(),
        ROOT / "generated" / "rust" / "nebula-semantic-registry" / "README.md": rust_package_readme_output(),
        ROOT / "generated" / "rust" / "nebula-semantic-registry" / "src" / "lib.rs": rust_output(data),
    }
    output.update(conformance_fixture_outputs())
    return output


def verify_artifacts() -> None:
    version = artifact_version()
    errors: list[str] = []

    for package_path, package_name in (
        (ROOT / "generated" / "typescript" / "package.json", "@nebula-observability/semantic-registry"),
        (TYPESCRIPT_RUTP / "package.json", "@nebula-observability/rutp-protobuf"),
        (ROOT / "generated" / "conformance" / "package.json", "@nebula-observability/rum-conformance"),
    ):
        try:
            package = load_json(package_path)
        except (FileNotFoundError, json.JSONDecodeError, SpecError) as error:
            errors.append(f"invalid generated package {package_path.relative_to(ROOT)}: {error}")
            continue
        if package.get("name") != package_name:
            errors.append(f"generated package has unexpected name: {package_path.relative_to(ROOT)}")
        if package.get("version") != version:
            errors.append(f"generated package version does not match VERSION: {package_path.relative_to(ROOT)}")

    typescript_rutp_package = load_json(TYPESCRIPT_RUTP / "package.json")
    if typescript_rutp_package.get("dependencies", {}).get("@bufbuild/protobuf") != TYPESCRIPT_PROTOBUF_VERSION:
        errors.append("generated TypeScript RUTP package has an unexpected protobuf runtime version")

    for metadata_path, declarations in (
        (
            TYPESCRIPT_RUTP / "version.js",
            (
                f'export const SpecVersion = "{version}";',
                f'export const ProtocolVersion = "{rutp_protocol_version()}";',
            ),
        ),
        (
            TYPESCRIPT_RUTP / "version.d.ts",
            (
                f'export declare const SpecVersion: "{version}";',
                f'export declare const ProtocolVersion: "{rutp_protocol_version()}";',
            ),
        ),
    ):
        try:
            metadata = metadata_path.read_text(encoding="utf-8")
            for declaration in declarations:
                if declaration not in metadata:
                    errors.append(
                        f"generated TypeScript RUTP metadata does not match the current release: {metadata_path.relative_to(ROOT)}"
                    )
                    break
        except OSError as error:
            errors.append(f"invalid generated TypeScript RUTP metadata: {error}")

    expected_typescript_proto_files = {
        TYPESCRIPT_RUTP / path.relative_to(ROOT / "specs").with_name(f"{path.stem}_pb.js")
        for path in RUTP.glob("*.proto")
    }
    actual_typescript_proto_files = set((TYPESCRIPT_RUTP / "rum" / "rutp" / "v1").glob("*_pb.js"))
    for path in sorted(expected_typescript_proto_files - actual_typescript_proto_files):
        errors.append(f"generated TypeScript RUTP protobuf file is missing: {path.relative_to(ROOT)}")
    for path in sorted(actual_typescript_proto_files - expected_typescript_proto_files):
        errors.append(f"unexpected generated TypeScript RUTP protobuf file: {path.relative_to(ROOT)}")
    for path in sorted(expected_typescript_proto_files & actual_typescript_proto_files):
        generated = path.read_text(encoding="utf-8")
        if "@generated by protoc-gen-es" not in generated or "@bufbuild/protobuf/codegenv2" not in generated:
            errors.append(f"invalid generated TypeScript RUTP protobuf file: {path.relative_to(ROOT)}")

    cargo_path = ROOT / "generated" / "rust" / "nebula-semantic-registry" / "Cargo.toml"
    if not cargo_path.is_file() or f'version = "{version}"' not in cargo_path.read_text(encoding="utf-8"):
        errors.append("generated Rust crate version does not match VERSION")

    go_mod_path = GO_MODULE / "go.mod"
    try:
        go_mod = go_mod_path.read_text(encoding="utf-8")
        if f"module {GO_MODULE_PATH}" not in go_mod:
            errors.append("generated Go module has an unexpected module path")
        if f"google.golang.org/protobuf {GO_PROTOBUF_VERSION}" not in go_mod:
            errors.append("generated Go module has an unexpected protobuf runtime version")
    except OSError as error:
        errors.append(f"invalid generated Go module: {error}")

    go_sum_path = GO_MODULE / "go.sum"
    try:
        go_sum = go_sum_path.read_text(encoding="utf-8")
        if f"google.golang.org/protobuf {GO_PROTOBUF_VERSION} " not in go_sum:
            errors.append("generated Go module checksum does not cover the protobuf runtime")
    except OSError as error:
        errors.append(f"missing generated Go module checksum: {error}")

    go_metadata_path = GO_MODULE / "rum" / "rutp" / "v1" / "version.go"
    try:
        go_metadata = go_metadata_path.read_text(encoding="utf-8")
        if f'const SpecVersion = "{version}"' not in go_metadata:
            errors.append("generated Go RUTP metadata version does not match VERSION")
        if f'const ProtocolVersion = "{rutp_protocol_version()}"' not in go_metadata:
            errors.append("generated Go RUTP metadata protocol version does not match the release manifest")
    except OSError as error:
        errors.append(f"invalid generated Go RUTP metadata: {error}")

    expected_go_proto_files = {
        GO_MODULE / path.relative_to(ROOT / "specs").with_suffix(".pb.go")
        for path in RUTP.glob("*.proto")
    }
    actual_go_proto_files = set((GO_MODULE / "rum" / "rutp" / "v1").glob("*.pb.go"))
    for path in sorted(expected_go_proto_files - actual_go_proto_files):
        errors.append(f"generated Go RUTP protobuf file is missing: {path.relative_to(ROOT)}")
    for path in sorted(actual_go_proto_files - expected_go_proto_files):
        errors.append(f"unexpected generated Go RUTP protobuf file: {path.relative_to(ROOT)}")
    for path in sorted(expected_go_proto_files & actual_go_proto_files):
        generated = path.read_text(encoding="utf-8")
        if "Code generated by protoc-gen-go" not in generated or "package rutpv1" not in generated:
            errors.append(f"invalid generated Go RUTP protobuf file: {path.relative_to(ROOT)}")

    manifest_path = ROOT / "generated" / "conformance" / "fixture-manifest.json"
    try:
        manifest = load_json(manifest_path)
        if manifest.get("spec_version") != version:
            errors.append("conformance bundle version does not match VERSION")
        if manifest.get("release") != current_release().get("release"):
            errors.append("conformance bundle release does not match the current release manifest")
        if manifest.get("protocols") != current_release().get("protocols"):
            errors.append("conformance bundle protocols do not match the current release manifest")
        for fixture in manifest.get("fixtures", []):
            relative = Path(fixture["path"])
            bundled = ROOT / "generated" / "conformance" / relative
            if not bundled.is_file():
                errors.append(f"bundle fixture is missing: {fixture['path']}")
                continue
            actual = hashlib.sha256(bundled.read_bytes()).hexdigest()
            if actual != fixture.get("sha256"):
                errors.append(f"bundle fixture checksum mismatch: {fixture['path']}")
    except (FileNotFoundError, json.JSONDecodeError, SpecError, KeyError, TypeError) as error:
        errors.append(f"invalid conformance bundle: {error}")

    if errors:
        raise SpecError("Artifact verification failed:\n- " + "\n- ".join(errors))
    print("Generated TypeScript, Rust, Go, and conformance artifacts are valid.")


def generate(check: bool) -> None:
    expected = generated_files(registry())
    failures: list[str] = []
    conformance_fixtures = ROOT / "generated" / "conformance" / "fixtures"
    if not check and conformance_fixtures.exists():
        shutil.rmtree(conformance_fixtures)
    for path, content in expected.items():
        content = content.rstrip() + "\n"
        if check:
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != content:
                failures.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if check:
        generated_conformance = ROOT / "generated" / "conformance"
        expected_conformance = {path for path in expected if generated_conformance in path.parents}
        if generated_conformance.exists():
            for actual in generated_conformance.rglob("*"):
                if actual.is_file() and actual not in expected_conformance:
                    failures.append(str(actual.relative_to(ROOT)))
    if failures:
        raise SpecError("Generated files are stale: " + ", ".join(failures))
    print("Generated files are current." if check else "Generated language registries and conformance bundle.")


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
    subparsers.add_parser("verify-receiver-contract")
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--check", action="store_true")
    subparsers.add_parser("verify-artifacts")
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--output", type=Path, required=True)
    breaking_parser = subparsers.add_parser("breaking")
    breaking_parser.add_argument("--against", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "lint":
            lint()
        elif args.command == "verify-receiver-contract":
            verify_receiver_contract()
        elif args.command == "generate":
            generate(args.check)
        elif args.command == "verify-artifacts":
            verify_artifacts()
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
