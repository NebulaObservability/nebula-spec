#!/usr/bin/env python3
"""Lint Nebula specifications, generate language registries, and detect breaks."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SEMANTICS = ROOT / "specs" / "semantics"
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "fixtures"
RUTP = ROOT / "specs" / "rum" / "rutp" / "v1"
RELEASES = ROOT / "releases"
CURRENT_RELEASE = RELEASES / "CURRENT"
RECEIVER_FIXTURES = FIXTURES / "receiver"
RECEIVER_FIXTURE_SCHEMA = SCHEMAS / "rutp-receiver-conformance.schema.json"
CONTROL_PLANE_FIXTURES = FIXTURES / "control-plane"
CONTROL_PLANE_REVISION_SCHEMA = SCHEMAS / "control-plane-config-revision.schema.json"
CONTROL_PLANE_DELIVERY_SCHEMA = SCHEMAS / "control-plane-config-delivery.schema.json"
APM_METRICS_CONTRACT = ROOT / "specs" / "apm" / "v1" / "metrics.yaml"
APM_METRICS_SCHEMA = SCHEMAS / "apm-metrics.schema.json"
APM_METRICS_FIXTURES = FIXTURES / "metrics"
APM_METRICS_FIXTURE = APM_METRICS_FIXTURES / "apm-metrics-mvp.json"
APM_METRICS_EXPLICIT_FIXTURE = APM_METRICS_FIXTURES / "apm-metrics-explicit-histogram.json"
APM_METRICS_NEGATIVE_FIXTURE = APM_METRICS_FIXTURES / "apm-metrics-negative-cases.json"
APM_METRICS_SEQUENCE_FIXTURE = APM_METRICS_FIXTURES / "apm-metrics-cumulative-sequence.json"
APM_METRICS_SEQUENCE_NEGATIVE_FIXTURE = (
    APM_METRICS_FIXTURES / "apm-metrics-cumulative-sequence-negative-cases.json"
)
OTLP_METRICS_SCHEMA = SCHEMAS / "otlp-metrics-export.schema.json"
APM_METRICS_SEQUENCE_SCHEMA = SCHEMAS / "apm-metrics-cumulative-sequence.schema.json"
APM_METRICS_BASELINE = ROOT / "compatibility" / "baselines" / "apm-metrics-1.1.0-draft.0.json"
APM_METRICS_BUNDLE = ROOT / "generated" / "apm-metrics-contract"
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

APM_METRICS_CONTRACT_VERSION = "1.1.0-draft.0"
APM_SEMANTIC_REGISTRY_VERSION = "1.1.0-draft.0"
APM_METRICS_OTEL_SCHEMA_URL = "https://opentelemetry.io/schemas/1.43.0"
APM_MVP_METRIC_NAMES = (
    "http.server.request.duration",
    "db.client.operation.duration",
    "jvm.memory.used",
    "jvm.memory.limit",
    "jvm.gc.duration",
    "jvm.thread.count",
    "jvm.cpu.time",
    "jvm.cpu.count",
    "jvm.cpu.recent_utilization",
    "process.cpu.time",
    "process.memory.usage",
    "process.uptime",
)
APM_HISTOGRAM_METRIC_NAMES = {
    "http.server.request.duration",
    "db.client.operation.duration",
    "jvm.gc.duration",
}
EXPECTED_APM_RESOURCE_ATTRIBUTES = [
    {"ref": "service.name", "type": "string", "requirement": "required", "non_empty": True},
    {"ref": "service.namespace", "type": "string", "requirement": "required", "non_empty": True},
    {"ref": "service.instance.id", "type": "string", "requirement": "required", "non_empty": True},
    {"ref": "service.version", "type": "string", "requirement": "required", "non_empty": True},
    {"ref": "deployment.environment.name", "type": "string", "requirement": "required", "non_empty": True},
    {"ref": "telemetry.sdk.name", "type": "string", "requirement": "required", "non_empty": True},
    {"ref": "telemetry.sdk.language", "type": "string", "requirement": "required", "non_empty": True},
    {"ref": "telemetry.sdk.version", "type": "string", "requirement": "required", "non_empty": True},
    {"ref": "process.pid", "type": "int", "requirement": "required", "minimum": 1},
    {"ref": "process.runtime.name", "type": "string", "requirement": "required", "non_empty": True},
    {"ref": "process.runtime.version", "type": "string", "requirement": "required", "non_empty": True},
]
PROHIBITED_METRIC_ATTRIBUTES = (
    "url.full",
    "url.path",
    "url.query",
    "db.query.text",
    "exception.message",
    "exception.stacktrace",
    "trace.id",
    "span.id",
    "trace_id",
    "span_id",
)
EXPECTED_APM_NEGATIVE_CASES = {
    "attribute-type",
    "base64-exemplar-id",
    "bad-bucket-total",
    "bad-exemplar-id",
    "delta-temporality",
    "empty-scope-version",
    "exemplar-filtered-attributes",
    "forbidden-db-query-text",
    "forbidden-exception-message",
    "forbidden-trace-id",
    "forbidden-url-full",
    "forbidden-url-query",
    "missing-required-point-attribute",
    "missing-resource",
    "missing-start-time",
    "non-official-schema-url",
    "non-finite-value",
    "non-monotonic-counter",
    "negative-duration-bucket",
    "nonempty-resource",
    "oversized-string",
    "oversized-scope-version",
    "short-exemplar-id",
    "too-many-attributes",
    "uppercase-exemplar-id",
    "future-schema-url",
    "wrong-metric-type",
    "wrong-unit",
}
EXPECTED_APM_SEQUENCE_CASES = {
    "cumulative-growth",
    "start-time-reset",
    "exponential-scale-transition",
    "agent-source-schema-compatibility",
    "scope-schema-url-transition",
}
EXPECTED_APM_SEQUENCE_NEGATIVE_CASES = {
    "same-start-bucket-regression",
    "same-start-count-regression",
    "same-start-monotonic-value-regression",
    "same-start-scale-transition-regression",
    "same-start-sum-regression",
    "start-time-regression",
}
EXPECTED_APM_METRICS_BASELINE_SHA256 = "925fc1ef3b831ebe8a116545d7fad91b72ab1f1705a3dc6cb9514efc3ffaa286"
OTLP_CUMULATIVE_TEMPORALITY = 2
OTLP_UINT64_MAX = 2**64 - 1


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
    validator = Draft202012Validator(schema, registry=schema_registry(), format_checker=FormatChecker())
    return [
        f"{label}: {'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    ]


def validation_error_paths(instance: Any, schema_path: Path) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, registry=schema_registry(), format_checker=FormatChecker())
    return sorted(
        {"/".join(str(part) for part in error.absolute_path) or "<root>" for error in validator.iter_errors(instance)}
    )


def schema_registry() -> Registry:
    registry = Registry()
    for path in SCHEMAS.glob("*.schema.json"):
        schema = load_json(path)
        identifier = schema.get("$id")
        if isinstance(identifier, str) and identifier:
            registry = registry.with_resource(identifier, Resource.from_contents(schema))
    return registry


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


def parse_rfc3339_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def control_plane_conformance_errors() -> list[str]:
    errors: list[str] = []
    if not CONTROL_PLANE_FIXTURES.is_dir():
        return ["fixtures/control-plane is missing"]

    fixture_manifest = load_yaml(FIXTURES / "manifest.yaml")
    entries = [
        entry
        for entry in fixture_manifest.get("fixtures", [])
        if entry.get("valid") is True
        and entry.get("schema")
        in {
            CONTROL_PLANE_REVISION_SCHEMA.relative_to(ROOT).as_posix(),
            CONTROL_PLANE_DELIVERY_SCHEMA.relative_to(ROOT).as_posix(),
        }
    ]
    if not entries:
        return ["fixtures/manifest.yaml is missing valid control-plane fixtures"]

    coverage = {"publish": False, "rollback": False, "delivery": False}
    revisions: dict[tuple[str, str, str], set[int]] = {}
    etags: dict[tuple[str, str, str], set[str]] = {}

    for entry in entries:
        fixture_path = ROOT / entry["path"]
        label = fixture_path.relative_to(ROOT).as_posix()
        try:
            fixture = load_json(fixture_path)
        except (OSError, json.JSONDecodeError, SpecError) as error:
            errors.append(f"{label}: {error}")
            continue

        schema_path = ROOT / entry["schema"]
        schema_errors = validate(fixture, schema_path, label)
        if schema_errors:
            errors.extend(schema_errors)
            continue

        document = fixture["document"]
        issued_at = parse_rfc3339_timestamp(document["issued_at"])
        expires_at = parse_rfc3339_timestamp(document["expires_at"])
        if issued_at is not None and expires_at is not None and expires_at <= issued_at:
            errors.append(f"{label}: document expires_at must be later than issued_at")
        if document["privacy"]["default_action"] != "drop":
            errors.append(f"{label}: control-plane document privacy.default_action must be drop")

        if schema_path == CONTROL_PLANE_DELIVERY_SCHEMA:
            coverage["delivery"] = True
            continue

        scope = fixture["scope"]
        key = (scope["tenant_id"], scope["project_id"], fixture["config_id"])
        known_revisions = revisions.setdefault(key, set())
        if fixture["revision"] in known_revisions:
            errors.append(f"{label}: duplicate revision for server scope and config_id")
        known_revisions.add(fixture["revision"])
        known_etags = etags.setdefault(key, set())
        if fixture["etag"] in known_etags:
            errors.append(f"{label}: duplicate ETag for server scope and config_id")
        known_etags.add(fixture["etag"])

        lifecycle = fixture["lifecycle"]
        operation = lifecycle["operation"]
        if operation == "publish":
            coverage["publish"] = True
        elif operation == "rollback":
            coverage["rollback"] = True
            if lifecycle["rollback_of_revision"] >= fixture["revision"]:
                errors.append(f"{label}: rollback_of_revision must be lower than the new revision")

    for name, covered in coverage.items():
        if not covered:
            errors.append(f"fixtures/control-plane is missing required coverage: {name}")
    return errors


def verify_control_plane_contract() -> None:
    errors = control_plane_conformance_errors()
    if errors:
        raise SpecError("Control Plane configuration conformance failed:\n- " + "\n- ".join(errors))
    print("Control Plane configuration revision and delivery conformance passed.")

def canonical_document_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apm_metrics_snapshot_data(contract: dict[str, Any] | None = None) -> dict[str, Any]:
    return copy.deepcopy(contract if contract is not None else load_yaml(APM_METRICS_CONTRACT))


def otlp_attribute_map(entries: Any, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(entries, list):
        errors.append(f"{label}: attributes must be an array")
        return {}
    value_types = {
        "stringValue": "string",
        "boolValue": "bool",
        "intValue": "int",
        "doubleValue": "double",
    }
    values: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str) or not isinstance(entry.get("value"), dict):
            errors.append(f"{label}: attribute {index} is malformed")
            continue
        key = entry["key"]
        if key in values:
            errors.append(f"{label}: duplicate attribute {key}")
            continue
        encoded = entry["value"]
        if len(encoded) != 1:
            errors.append(f"{label}: attribute {key} must contain exactly one AnyValue member")
            continue
        value_key, value = next(iter(encoded.items()))
        value_type = value_types.get(value_key)
        if value_type is None:
            errors.append(f"{label}: attribute {key} uses unsupported AnyValue member {value_key}")
            continue
        if value_type == "int":
            try:
                value = int(value)
            except (TypeError, ValueError):
                errors.append(f"{label}: attribute {key} has an invalid intValue")
                continue
        elif value_type == "double" and (
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        ):
            errors.append(f"{label}: attribute {key} has a non-finite doubleValue")
            continue
        values[key] = {"type": value_type, "value": value}
    return values


def uint64_value(value: Any, label: str, errors: list[str]) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors.append(f"{label}: value must be an unsigned integer string")
        return None
    if parsed < 0 or parsed > OTLP_UINT64_MAX:
        errors.append(f"{label}: value is outside the uint64 range")
        return None
    return parsed


def finite_number(value: Any, label: str, errors: list[str]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        errors.append(f"{label}: value must be a finite number")
        return None
    return float(value)


def decode_otlp_id(value: Any, expected_length: int, label: str, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{label}: identifier must be lowercase hexadecimal text")
        return
    expected_characters = expected_length * 2
    if re.fullmatch(f"[0-9a-f]{{{expected_characters}}}", value) is None:
        errors.append(f"{label}: identifier must contain exactly {expected_characters} lowercase hexadecimal characters")
        return
    decoded = bytes.fromhex(value)
    if not any(decoded):
        errors.append(f"{label}: identifier must not be all zeroes")


def metric_point_time_errors(point: dict[str, Any], label: str, cumulative: bool) -> list[str]:
    errors: list[str] = []
    timestamp = uint64_value(point.get("timeUnixNano"), f"{label}/timeUnixNano", errors)
    start_value = point.get("startTimeUnixNano")
    if cumulative and start_value is None:
        errors.append(f"{label}: cumulative point must declare startTimeUnixNano")
        return errors
    if start_value is not None:
        start = uint64_value(start_value, f"{label}/startTimeUnixNano", errors)
        if start is not None and timestamp is not None and start > timestamp:
            errors.append(f"{label}: startTimeUnixNano must not exceed timeUnixNano")
    return errors


def histogram_point_errors(point: dict[str, Any], signal_name: str, label: str) -> list[str]:
    errors: list[str] = []
    count = uint64_value(point.get("count"), f"{label}/count", errors)
    if count is None:
        return errors
    bucket_total = 0
    if signal_name == "exponentialHistogram":
        zero_count = uint64_value(point.get("zeroCount", "0"), f"{label}/zeroCount", errors)
        if zero_count is not None:
            bucket_total += zero_count
        for side in ("positive", "negative"):
            buckets = point.get(side)
            if buckets is None:
                continue
            if not isinstance(buckets, dict):
                errors.append(f"{label}: {side} buckets must be an object")
                continue
            side_total = 0
            for index, bucket_count in enumerate(buckets.get("bucketCounts", [])):
                parsed = uint64_value(bucket_count, f"{label}/{side}/bucketCounts/{index}", errors)
                if parsed is not None:
                    side_total += parsed
            bucket_total += side_total
            if side == "negative" and side_total != 0:
                errors.append(f"{label}: duration histogram must not contain negative bucket counts")
    else:
        bucket_counts: list[int] = []
        for index, bucket_count in enumerate(point.get("bucketCounts", [])):
            parsed = uint64_value(bucket_count, f"{label}/bucketCounts/{index}", errors)
            if parsed is not None:
                bucket_counts.append(parsed)
        bucket_total = sum(bucket_counts)
        raw_bounds = point.get("explicitBounds", [])
        bounds: list[float] = []
        for index, bound in enumerate(raw_bounds):
            parsed = finite_number(bound, f"{label}/explicitBounds/{index}", errors)
            if parsed is not None:
                bounds.append(parsed)
                if parsed < 0:
                    errors.append(f"{label}: duration histogram boundary must be non-negative")
        if len(bucket_counts) != len(raw_bounds) + 1:
            errors.append(f"{label}: explicit histogram must have one more bucket count than boundary")
        if any(left >= right for left, right in zip(bounds, bounds[1:])):
            errors.append(f"{label}: explicit histogram boundaries must be strictly increasing")
    if bucket_total != count:
        errors.append(f"{label}: histogram bucket counts total {bucket_total}, expected {count}")

    numeric: dict[str, float] = {}
    for field in ("sum", "min", "max"):
        if field in point:
            parsed = finite_number(point[field], f"{label}/{field}", errors)
            if parsed is not None:
                numeric[field] = parsed
                if parsed < 0:
                    errors.append(f"{label}: duration histogram {field} must be non-negative")
    if ("min" in numeric) != ("max" in numeric):
        errors.append(f"{label}: histogram min and max must be present together")
    if count == 0:
        if "min" in point or "max" in point:
            errors.append(f"{label}: empty histogram must not declare min or max")
        if numeric.get("sum", 0) != 0:
            errors.append(f"{label}: empty histogram sum must be zero when present")
    elif "min" in numeric and "max" in numeric:
        if numeric["min"] > numeric["max"]:
            errors.append(f"{label}: histogram min must not exceed max")
        if "sum" in numeric and (
            numeric["sum"] < numeric["min"] * count or numeric["sum"] > numeric["max"] * count
        ):
            errors.append(f"{label}: histogram sum is inconsistent with count, min, and max")
    return errors


def semantic_otlp_type(semantic_type: str) -> str:
    return "string" if semantic_type == "enum" else semantic_type


def source_otel_schema_url_errors(value: Any, contract: dict[str, Any], label: str) -> list[str]:
    if value is None or value == "":
        return []
    if not isinstance(value, str):
        return [f"{label}: source OTel schema URL must be text"]
    policy = contract["schema_url_policy"]["accepted_source"]
    prefix = policy["prefix"]
    if not value.startswith(prefix):
        return [f"{label}: source OTel schema URL must use the official {prefix} prefix"]
    version = value[len(prefix) :]
    try:
        parse_semver(version)
        if compare_semver(version, policy["maximum_version"]) > 0:
            return [f"{label}: source OTel schema version {version} exceeds {policy['maximum_version']}"]
    except SpecError as error:
        return [f"{label}: source OTel schema URL has an invalid semantic version: {error}"]
    return []


def attribute_value_errors(
    values: dict[str, dict[str, Any]],
    definitions: dict[str, dict[str, Any]],
    label: str,
) -> list[str]:
    errors: list[str] = []
    for name, encoded in values.items():
        definition = definitions.get(name)
        if definition is None:
            continue
        expected_type = semantic_otlp_type(str(definition["type"]))
        if encoded["type"] != expected_type:
            errors.append(f"{label}: attribute {name} must use {expected_type}Value")
            continue
        value = encoded["value"]
        if expected_type == "string" and definition.get("non_empty", True) and value == "":
            errors.append(f"{label}: attribute {name} must not be empty")
        minimum = definition.get("minimum")
        if minimum is not None and isinstance(value, (int, float)) and value < minimum:
            errors.append(f"{label}: attribute {name} is below minimum {minimum}")
    return errors


def point_attribute_policy_errors(
    entries: Any,
    values: dict[str, dict[str, Any]],
    policy: dict[str, Any],
    label: str,
) -> list[str]:
    errors: list[str] = []
    if isinstance(entries, list) and len(entries) > policy["max_attributes_per_point"]:
        errors.append(
            f"{label}: metric point has {len(entries)} attributes, "
            f"maximum is {policy['max_attributes_per_point']}"
        )
    maximum_bytes = policy["max_string_value_bytes"]
    for name, encoded in values.items():
        if encoded["type"] == "string" and len(encoded["value"].encode("utf-8")) > maximum_bytes:
            errors.append(f"{label}: attribute {name} exceeds {maximum_bytes} UTF-8 bytes")
    return errors


def apm_metrics_fixture_errors(
    contract: dict[str, Any],
    fixture: dict[str, Any],
    label: str,
    expected_metric_names: tuple[str, ...],
    expected_histogram_signal: str,
    enforce_red_counts: bool,
    require_target_schema: bool = False,
) -> list[str]:
    errors = validate(fixture, OTLP_METRICS_SCHEMA, label)
    if errors:
        return errors
    contract_by_name = {metric["name"]: metric for metric in contract["metrics"]}
    semantic_attributes = {item["name"]: item for item in registry()["attributes"]}
    resource_definitions = {item["ref"]: item for item in contract["resource"]["attributes"]}
    expected_resources = set(resource_definitions)
    global_forbidden = set(contract["attribute_policy"]["forbidden"])

    resource_metrics = fixture["resourceMetrics"]
    if len(resource_metrics) != 1:
        errors.append(f"{label}: fixture must contain exactly one ResourceMetrics")
    fixture_metrics: list[dict[str, Any]] = []
    scope_profiles: list[tuple[str, ...]] = []
    scope_names: list[str] = []
    for resource_index, resource_metric in enumerate(resource_metrics):
        resource_label = f"{label}/resourceMetrics/{resource_index}"
        resource_attributes = otlp_attribute_map(resource_metric["resource"]["attributes"], resource_label, errors)
        missing_resources = expected_resources - set(resource_attributes)
        unexpected_resources = set(resource_attributes) - expected_resources
        if missing_resources:
            errors.append(f"{resource_label}: missing required Resource attributes {sorted(missing_resources)}")
        if unexpected_resources:
            errors.append(f"{resource_label}: golden fixture has unexpected Resource attributes {sorted(unexpected_resources)}")
        errors.extend(attribute_value_errors(resource_attributes, resource_definitions, resource_label))
        resource_schema_url = resource_metric.get("schemaUrl")
        errors.extend(source_otel_schema_url_errors(resource_schema_url, contract, f"{resource_label}/schemaUrl"))
        if require_target_schema and resource_schema_url != contract["otel_schema_url"]:
            errors.append(f"{resource_label}: Golden Fixture schemaUrl must match the normalization target")
        scope_metrics = resource_metric["scopeMetrics"]
        for scope_index, scope_metric in enumerate(scope_metrics):
            scope_label = f"{resource_label}/scopeMetrics/{scope_index}"
            scope_schema_url = scope_metric.get("schemaUrl")
            errors.extend(source_otel_schema_url_errors(scope_schema_url, contract, f"{scope_label}/schemaUrl"))
            if require_target_schema and scope_schema_url != contract["otel_schema_url"]:
                errors.append(f"{scope_label}: Golden Fixture schemaUrl must match the normalization target")
            scope_name = scope_metric["scope"]["name"]
            scope_version = scope_metric["scope"].get("version")
            if not scope_name:
                errors.append(f"{scope_label}: instrumentation scope name must not be empty")
            if scope_version is not None:
                if not isinstance(scope_version, str) or not scope_version:
                    errors.append(f"{scope_label}: instrumentation scope version must not be empty when present")
                elif len(scope_version) > 128:
                    errors.append(f"{scope_label}: instrumentation scope version must not exceed 128 characters")
            if scope_name.startswith("io.nebulaobservability"):
                errors.append(f"{scope_label}: standard APM metrics must use producer instrumentation scopes")
            scope_names.append(scope_name)
            scope_profiles.append(tuple(metric["name"] for metric in scope_metric["metrics"]))
            fixture_metrics.extend(scope_metric["metrics"])
    expected_scope_profiles = (
        tuple(name for name in expected_metric_names if name == "http.server.request.duration"),
        tuple(name for name in expected_metric_names if name == "db.client.operation.duration"),
        tuple(
            name
            for name in expected_metric_names
            if name not in {"http.server.request.duration", "db.client.operation.duration"}
        ),
    )
    expected_scope_profiles = tuple(profile for profile in expected_scope_profiles if profile)
    if tuple(scope_profiles) != expected_scope_profiles:
        errors.append(
            f"{label}: fixture must split HTTP, DB, and runtime/process metrics across exact producer scopes; "
            f"expected={expected_scope_profiles}, got={tuple(scope_profiles)}"
        )
    if len(scope_names) != len(set(scope_names)):
        errors.append(f"{label}: producer instrumentation scope names must be distinct")

    fixture_names = [metric["name"] for metric in fixture_metrics]
    if len(fixture_names) != len(set(fixture_names)):
        errors.append(f"{label}: fixture contains duplicate metric names across scopes")
    if tuple(fixture_names) != expected_metric_names:
        errors.append(f"{label}: metric order/profile must be {list(expected_metric_names)}, got {fixture_names}")

    seen_series: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    http_success_count = 0
    http_error_count = 0
    for metric in fixture_metrics:
        name = metric["name"]
        definition = contract_by_name.get(name)
        if definition is None:
            continue
        metric_label = f"{label}/metric/{name}"
        if metric["unit"] != definition["unit"]:
            errors.append(f"{metric_label}: unit must be {definition['unit']}")
        instrument = definition["instrument"]
        if instrument == "histogram":
            signal_names = [candidate for candidate in ("exponentialHistogram", "histogram") if candidate in metric]
            if signal_names != [expected_histogram_signal]:
                errors.append(f"{metric_label}: expected {expected_histogram_signal}")
                continue
            signal_name = signal_names[0]
        elif instrument in ("counter", "updowncounter"):
            signal_name = "sum"
            if signal_name not in metric:
                errors.append(f"{metric_label}: expected OTLP Sum")
                continue
        else:
            signal_name = "gauge"
            if signal_name not in metric:
                errors.append(f"{metric_label}: expected OTLP Gauge")
                continue

        signal = metric[signal_name]
        cumulative = definition["temporality"] == "cumulative"
        if cumulative and signal.get("aggregationTemporality") != OTLP_CUMULATIVE_TEMPORALITY:
            errors.append(f"{metric_label}: aggregation temporality must be cumulative")
        if instrument in ("counter", "updowncounter") and signal.get("isMonotonic") != definition["monotonic"]:
            errors.append(f"{metric_label}: isMonotonic does not match the contract")
        attribute_definitions = {
            item["ref"]: {**semantic_attributes[item["ref"]], "non_empty": True}
            for item in definition["attributes"]
            if item["ref"] in semantic_attributes
        }
        required_attributes = {item["ref"] for item in definition["attributes"] if item["requirement"] == "required"}
        allowed_attributes = {item["ref"] for item in definition["attributes"]}
        metric_has_exemplar = False
        for point_index, point in enumerate(signal["dataPoints"]):
            point_label = f"{metric_label}/dataPoints/{point_index}"
            errors.extend(metric_point_time_errors(point, point_label, cumulative))
            raw_point_attributes = point.get("attributes", [])
            point_attributes = otlp_attribute_map(raw_point_attributes, point_label, errors)
            errors.extend(
                point_attribute_policy_errors(
                    raw_point_attributes,
                    point_attributes,
                    contract["attribute_policy"],
                    point_label,
                )
            )
            missing_attributes = required_attributes - set(point_attributes)
            unexpected_attributes = set(point_attributes) - allowed_attributes
            prohibited_attributes = set(point_attributes).intersection(global_forbidden)
            if missing_attributes:
                errors.append(f"{point_label}: missing required attributes {sorted(missing_attributes)}")
            if unexpected_attributes:
                errors.append(f"{point_label}: attributes are not declared by the allowlist: {sorted(unexpected_attributes)}")
            if prohibited_attributes:
                errors.append(f"{point_label}: prohibited metric attributes present: {sorted(prohibited_attributes)}")
            errors.extend(attribute_value_errors(point_attributes, attribute_definitions, point_label))
            identity = (
                name,
                tuple(sorted((key, json.dumps(value, sort_keys=True)) for key, value in point_attributes.items())),
            )
            if identity in seen_series:
                errors.append(f"{point_label}: duplicate metric timeseries")
            seen_series.add(identity)

            numeric_value: float | None = None
            if signal_name in ("histogram", "exponentialHistogram"):
                errors.extend(histogram_point_errors(point, signal_name, point_label))
            elif definition["value_type"] == "int":
                if "asInt" not in point:
                    errors.append(f"{point_label}: integer metric must use asInt")
                else:
                    try:
                        numeric_value = float(int(point["asInt"]))
                    except (TypeError, ValueError):
                        errors.append(f"{point_label}: asInt must be an integer string")
            else:
                if "asDouble" not in point:
                    errors.append(f"{point_label}: double metric must use asDouble")
                else:
                    numeric_value = finite_number(point["asDouble"], f"{point_label}/asDouble", errors)
            value_range = definition.get("value_range")
            if value_range and numeric_value is not None:
                if numeric_value < value_range["minimum"]:
                    errors.append(f"{point_label}: value is below the contract minimum")
                if "maximum" in value_range and numeric_value > value_range["maximum"]:
                    errors.append(f"{point_label}: value is above the contract maximum")

            exemplars = point.get("exemplars", [])
            if exemplars:
                metric_has_exemplar = True
            if definition["exemplars"]["policy"] == "none" and exemplars:
                errors.append(f"{point_label}: runtime metric must not synthesize exemplars")
            for exemplar_index, exemplar in enumerate(exemplars):
                exemplar_label = f"{point_label}/exemplars/{exemplar_index}"
                decode_otlp_id(
                    exemplar.get("traceId"),
                    definition["exemplars"].get("trace_id_bytes", 16),
                    f"{exemplar_label}/traceId",
                    errors,
                )
                decode_otlp_id(
                    exemplar.get("spanId"),
                    definition["exemplars"].get("span_id_bytes", 8),
                    f"{exemplar_label}/spanId",
                    errors,
                )
                exemplar_value = exemplar.get("asDouble", exemplar.get("asInt"))
                if "asInt" in exemplar:
                    try:
                        exemplar_value = int(exemplar_value)
                    except (TypeError, ValueError):
                        errors.append(f"{exemplar_label}: asInt must be an integer string")
                        exemplar_value = None
                if exemplar_value is not None:
                    parsed_exemplar = finite_number(exemplar_value, f"{exemplar_label}/value", errors)
                    if parsed_exemplar is not None and parsed_exemplar < 0:
                        errors.append(f"{exemplar_label}: duration exemplar must be non-negative")
                raw_filtered = exemplar.get("filteredAttributes", [])
                if raw_filtered:
                    errors.append(f"{exemplar_label}: exemplar filteredAttributes must be empty")
                filtered = otlp_attribute_map(raw_filtered, exemplar_label, errors)
                errors.extend(
                    point_attribute_policy_errors(
                        raw_filtered,
                        filtered,
                        contract["attribute_policy"],
                        exemplar_label,
                    )
                )
                filtered_forbidden = set(filtered).intersection(global_forbidden)
                if filtered_forbidden:
                    errors.append(f"{exemplar_label}: prohibited filtered attributes present: {sorted(filtered_forbidden)}")

            if enforce_red_counts and name == "http.server.request.duration":
                point_count = uint64_value(point.get("count"), f"{point_label}/count", errors)
                if point_count is not None:
                    if "error.type" in point_attributes:
                        http_error_count += point_count
                        if point_attributes["error.type"]["value"] != "500":
                            errors.append(f"{point_label}: error RED series must use error.type=500")
                        if point_attributes.get("http.response.status_code", {}).get("value") != 500:
                            errors.append(f"{point_label}: error RED series must use HTTP status 500")
                    else:
                        http_success_count += point_count
        if definition["exemplars"]["policy"] == "sampled_trace_context_if_available" and not metric_has_exemplar:
            errors.append(f"{metric_label}: sampled trace-context exemplar coverage is required")
    if enforce_red_counts and (http_success_count != 3 or http_error_count != 2):
        errors.append(
            f"{label}: HTTP RED fixture must contain success count 3 and error count 2, "
            f"got success={http_success_count}, error={http_error_count}"
        )
    return errors


def apply_json_patch(document: dict[str, Any], patches: Any, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(patches, list) or not patches:
        return [f"{label}: patch must be a non-empty array"]
    for patch_index, patch in enumerate(patches):
        patch_label = f"{label}/patch/{patch_index}"
        if not isinstance(patch, dict) or patch.get("op") not in {"add", "remove", "replace"}:
            errors.append(f"{patch_label}: unsupported patch operation")
            continue
        path = patch.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            errors.append(f"{patch_label}: path must be a JSON Pointer")
            continue
        tokens = [token.replace("~1", "/").replace("~0", "~") for token in path[1:].split("/")]
        try:
            parent: Any = document
            for token in tokens[:-1]:
                parent = parent[int(token)] if isinstance(parent, list) else parent[token]
            final = tokens[-1]
            operation = patch["op"]
            patch_value = math.nan if patch.get("value_kind") == "nan" else copy.deepcopy(patch.get("value"))
            if isinstance(parent, list):
                if operation == "add" and final == "-":
                    parent.append(patch_value)
                elif operation == "add":
                    parent.insert(int(final), patch_value)
                elif operation == "remove":
                    parent.pop(int(final))
                else:
                    parent[int(final)] = patch_value
            elif operation == "remove":
                del parent[final]
            else:
                parent[final] = patch_value
        except (IndexError, KeyError, TypeError, ValueError) as error:
            errors.append(f"{patch_label}: patch failed: {error}")
    return errors


def fixture_validation_profile(path: Path) -> tuple[tuple[str, ...], str, bool]:
    if path == APM_METRICS_FIXTURE:
        return APM_MVP_METRIC_NAMES, "exponentialHistogram", True
    if path == APM_METRICS_EXPLICIT_FIXTURE:
        histogram_names = tuple(name for name in APM_MVP_METRIC_NAMES if name in APM_HISTOGRAM_METRIC_NAMES)
        return histogram_names, "histogram", False
    raise SpecError(f"unsupported APM metrics fixture base: {path.relative_to(ROOT)}")


def apm_metrics_negative_conformance_errors(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        suite = load_json(APM_METRICS_NEGATIVE_FIXTURE)
    except (FileNotFoundError, json.JSONDecodeError, SpecError) as error:
        return [f"invalid APM metrics negative fixture suite: {error}"]
    if set(suite) != {"schema_version", "base_fixture", "cases"} or suite.get("schema_version") != 1:
        return ["fixtures/metrics/apm-metrics-negative-cases.json: invalid suite envelope"]
    base_name = suite.get("base_fixture")
    cases = suite.get("cases")
    if not isinstance(base_name, str) or not isinstance(cases, list):
        return ["fixtures/metrics/apm-metrics-negative-cases.json: base_fixture and cases are required"]

    seen_names: set[str] = set()
    for case_index, case in enumerate(cases):
        case_label = f"fixtures/metrics/apm-metrics-negative-cases.json/cases/{case_index}"
        if not isinstance(case, dict):
            errors.append(f"{case_label}: case must be an object")
            continue
        name = case.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{case_label}: case name is required")
            continue
        if name in seen_names:
            errors.append(f"{case_label}: duplicate case name {name}")
            continue
        seen_names.add(name)
        relative_base = case.get("base_fixture", base_name)
        if not isinstance(relative_base, str):
            errors.append(f"{case_label}: base_fixture must be a path")
            continue
        base_path = (ROOT / relative_base).resolve()
        if base_path not in {APM_METRICS_FIXTURE.resolve(), APM_METRICS_EXPLICIT_FIXTURE.resolve()}:
            errors.append(f"{case_label}: unsupported base fixture {relative_base}")
            continue
        try:
            base = load_json(base_path)
        except (FileNotFoundError, json.JSONDecodeError, SpecError) as error:
            errors.append(f"{case_label}: invalid base fixture: {error}")
            continue
        expected_names, histogram_signal, enforce_red = fixture_validation_profile(base_path)
        base_errors = apm_metrics_fixture_errors(
            contract, base, relative_base, expected_names, histogram_signal, enforce_red
        )
        mutated = copy.deepcopy(base)
        patch_errors = apply_json_patch(mutated, case.get("patch"), case_label)
        errors.extend(patch_errors)
        if patch_errors:
            continue
        mutated_errors = apm_metrics_fixture_errors(
            contract, mutated, relative_base, expected_names, histogram_signal, enforce_red
        )
        remaining = Counter(base_errors)
        added_errors: list[str] = []
        for error in mutated_errors:
            if remaining[error]:
                remaining[error] -= 1
            else:
                added_errors.append(error)
        if not added_errors:
            errors.append(f"{case_label}: mutation did not create a conformance failure")
            continue
        expected_errors = case.get("expected_errors")
        if (
            not isinstance(expected_errors, list)
            or not expected_errors
            or not all(isinstance(item, str) for item in expected_errors)
        ):
            errors.append(f"{case_label}: expected_errors must be a non-empty string array")
            continue
        for expected in expected_errors:
            if not any(expected in actual for actual in added_errors):
                errors.append(f"{case_label}: expected error containing {expected!r}, got {added_errors}")
    missing = EXPECTED_APM_NEGATIVE_CASES - seen_names
    unexpected = seen_names - EXPECTED_APM_NEGATIVE_CASES
    if missing or unexpected:
        errors.append(f"APM metrics negative cases differ: missing={sorted(missing)}, unexpected={sorted(unexpected)}")
    return errors


def metric_series_states(
    fixture: dict[str, Any],
    label: str,
) -> tuple[dict[tuple[str, ...], dict[str, Any]], list[str]]:
    errors: list[str] = []
    states: dict[tuple[str, ...], dict[str, Any]] = {}
    for resource_index, resource_metric in enumerate(fixture["resourceMetrics"]):
        resource_values = otlp_attribute_map(
            resource_metric["resource"]["attributes"],
            f"{label}/resourceMetrics/{resource_index}",
            errors,
        )
        resource_identity = json.dumps(resource_values, sort_keys=True, separators=(",", ":"))
        for scope_index, scope_metric in enumerate(resource_metric["scopeMetrics"]):
            scope = scope_metric["scope"]
            scope_identity = json.dumps(
                {
                    "name": scope["name"],
                    "version": scope.get("version"),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            for metric_index, metric in enumerate(scope_metric["metrics"]):
                signal_names = [
                    name for name in ("exponentialHistogram", "histogram", "sum", "gauge") if name in metric
                ]
                if len(signal_names) != 1:
                    errors.append(
                        f"{label}/resourceMetrics/{resource_index}/scopeMetrics/{scope_index}/metrics/{metric_index}: "
                        "metric must contain exactly one signal"
                    )
                    continue
                signal_name = signal_names[0]
                signal = metric[signal_name]
                for point_index, point in enumerate(signal["dataPoints"]):
                    point_label = (
                        f"{label}/resourceMetrics/{resource_index}/scopeMetrics/{scope_index}/"
                        f"metrics/{metric_index}/dataPoints/{point_index}"
                    )
                    point_values = otlp_attribute_map(point.get("attributes", []), point_label, errors)
                    point_identity = json.dumps(point_values, sort_keys=True, separators=(",", ":"))
                    key = (resource_identity, scope_identity, metric["name"], point_identity)
                    if key in states:
                        errors.append(f"{point_label}: duplicate cumulative series identity")
                        continue
                    states[key] = {
                        "metric_name": metric["name"],
                        "signal_name": signal_name,
                        "signal": signal,
                        "point": point,
                    }
    return states, errors


def exponential_bucket_map(
    point: dict[str, Any],
    side: str,
    target_scale: int,
    label: str,
    errors: list[str],
) -> dict[int, int]:
    source_scale = int(point["scale"])
    if source_scale < target_scale:
        errors.append(f"{label}: comparison scale must not exceed the source scale")
        return {}
    buckets = point.get(side)
    if not isinstance(buckets, dict):
        return {}
    divisor = 1 << (source_scale - target_scale)
    offset = int(buckets["offset"])
    result: dict[int, int] = {}
    for index, raw_count in enumerate(buckets["bucketCounts"]):
        count = uint64_value(raw_count, f"{label}/{side}/bucketCounts/{index}", errors)
        if count is None:
            continue
        projected_index = (offset + index) // divisor
        result[projected_index] = result.get(projected_index, 0) + count
    return result


def histogram_accumulation_errors(
    previous: dict[str, Any],
    current: dict[str, Any],
    signal_name: str,
    label: str,
) -> list[str]:
    errors: list[str] = []
    previous_count = uint64_value(previous.get("count"), f"{label}/previous/count", errors)
    current_count = uint64_value(current.get("count"), f"{label}/current/count", errors)
    if previous_count is not None and current_count is not None and current_count < previous_count:
        errors.append(f"{label}: cumulative histogram count regressed with an unchanged start time")

    if "sum" in previous:
        if "sum" not in current:
            errors.append(f"{label}: cumulative histogram sum disappeared with an unchanged start time")
        else:
            previous_sum = finite_number(previous["sum"], f"{label}/previous/sum", errors)
            current_sum = finite_number(current["sum"], f"{label}/current/sum", errors)
            if previous_sum is not None and current_sum is not None and current_sum < previous_sum:
                errors.append(f"{label}: cumulative histogram sum regressed with an unchanged start time")

    if signal_name == "exponentialHistogram":
        previous_zero = uint64_value(previous.get("zeroCount", "0"), f"{label}/previous/zeroCount", errors)
        current_zero = uint64_value(current.get("zeroCount", "0"), f"{label}/current/zeroCount", errors)
        if previous_zero is not None and current_zero is not None and current_zero < previous_zero:
            errors.append(f"{label}: cumulative histogram bucket regressed with an unchanged start time")
        common_scale = min(int(previous["scale"]), int(current["scale"]))
        for side in ("positive", "negative"):
            previous_buckets = exponential_bucket_map(previous, side, common_scale, f"{label}/previous", errors)
            current_buckets = exponential_bucket_map(current, side, common_scale, f"{label}/current", errors)
            for bucket_index, previous_value in previous_buckets.items():
                if current_buckets.get(bucket_index, 0) < previous_value:
                    errors.append(
                        f"{label}: cumulative histogram bucket regressed with an unchanged start time "
                        f"after projection to scale {common_scale}"
                    )
                    break
    else:
        if previous.get("explicitBounds") != current.get("explicitBounds"):
            errors.append(f"{label}: explicit histogram boundaries changed with an unchanged start time")
        previous_buckets = [
            uint64_value(value, f"{label}/previous/bucketCounts/{index}", errors)
            for index, value in enumerate(previous.get("bucketCounts", []))
        ]
        current_buckets = [
            uint64_value(value, f"{label}/current/bucketCounts/{index}", errors)
            for index, value in enumerate(current.get("bucketCounts", []))
        ]
        if len(previous_buckets) == len(current_buckets) and any(
            current_value is not None and previous_value is not None and current_value < previous_value
            for previous_value, current_value in zip(previous_buckets, current_buckets)
        ):
            errors.append(f"{label}: cumulative histogram bucket regressed with an unchanged start time")
    return errors


def monotonic_sum_accumulation_errors(
    previous: dict[str, Any],
    current: dict[str, Any],
    label: str,
) -> list[str]:
    errors: list[str] = []
    regressed = False
    if "asInt" in previous and "asInt" in current:
        try:
            regressed = int(current["asInt"]) < int(previous["asInt"])
        except (TypeError, ValueError):
            errors.append(f"{label}: cumulative monotonic sum integer values must be numeric")
    elif "asDouble" in previous and "asDouble" in current:
        previous_value = finite_number(previous["asDouble"], f"{label}/previous/asDouble", errors)
        current_value = finite_number(current["asDouble"], f"{label}/asDouble", errors)
        if previous_value is not None and current_value is not None:
            regressed = current_value < previous_value
    else:
        errors.append(f"{label}: cumulative monotonic sum numeric representation changed")
    if regressed:
        errors.append(f"{label}: cumulative monotonic sum value regressed with an unchanged start time")
    return errors


def cumulative_sequence_errors(exports: list[dict[str, Any]], label: str) -> list[str]:
    errors: list[str] = []
    previous_states: dict[tuple[str, ...], dict[str, Any]] | None = None
    for export_index, fixture in enumerate(exports):
        states, state_errors = metric_series_states(fixture, f"{label}/exports/{export_index}")
        errors.extend(state_errors)
        if previous_states is None:
            previous_states = states
            continue
        if set(states) != set(previous_states):
            errors.append(f"{label}/exports/{export_index}: cumulative series identities changed between exports")
            previous_states = states
            continue
        for key, current_state in states.items():
            previous_state = previous_states[key]
            metric_name = current_state["metric_name"]
            series_label = f"{label}/exports/{export_index}/metric/{metric_name}"
            if current_state["signal_name"] != previous_state["signal_name"]:
                errors.append(f"{series_label}: metric signal changed between cumulative exports")
                continue
            current_point = current_state["point"]
            previous_point = previous_state["point"]
            current_time = uint64_value(current_point.get("timeUnixNano"), f"{series_label}/timeUnixNano", errors)
            previous_time = uint64_value(
                previous_point.get("timeUnixNano"), f"{series_label}/previous/timeUnixNano", errors
            )
            if current_time is None or previous_time is None:
                continue
            if current_time < previous_time:
                errors.append(f"{series_label}: export time regressed")
                continue
            if current_time == previous_time:
                if current_point != previous_point:
                    errors.append(f"{series_label}: identical export timestamp is only valid for an idempotent point")
                continue

            signal_name = current_state["signal_name"]
            if signal_name == "gauge":
                continue
            current_start = uint64_value(
                current_point.get("startTimeUnixNano"), f"{series_label}/startTimeUnixNano", errors
            )
            previous_start = uint64_value(
                previous_point.get("startTimeUnixNano"), f"{series_label}/previous/startTimeUnixNano", errors
            )
            if current_start is None or previous_start is None:
                continue
            if current_start != previous_start:
                if current_start <= previous_start:
                    errors.append(f"{series_label}: cumulative reset start time must strictly advance")
                continue

            if signal_name in ("exponentialHistogram", "histogram"):
                errors.extend(
                    histogram_accumulation_errors(
                        previous_point,
                        current_point,
                        signal_name,
                        series_label,
                    )
                )
            elif signal_name == "sum" and current_state["signal"].get("isMonotonic") is True:
                errors.extend(monotonic_sum_accumulation_errors(previous_point, current_point, series_label))
        previous_states = states
    return errors


def materialize_sequence_exports(
    base: dict[str, Any],
    case: dict[str, Any],
    label: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    exports: list[dict[str, Any]] = []
    for export_index, export in enumerate(case["exports"]):
        materialized = copy.deepcopy(base)
        patches = export.get("patch")
        if patches is not None:
            errors.extend(apply_json_patch(materialized, patches, f"{label}/exports/{export_index}"))
        exports.append(materialized)
    return exports, errors


def apm_metrics_accumulation_conformance_errors(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    suites = (
        (APM_METRICS_SEQUENCE_FIXTURE, EXPECTED_APM_SEQUENCE_CASES, True),
        (APM_METRICS_SEQUENCE_NEGATIVE_FIXTURE, EXPECTED_APM_SEQUENCE_NEGATIVE_CASES, False),
    )
    for path, expected_names, expected_validity in suites:
        label = path.relative_to(ROOT).as_posix()
        try:
            suite = load_json(path)
        except (FileNotFoundError, json.JSONDecodeError, SpecError) as error:
            errors.append(f"invalid APM metrics accumulation fixture suite {label}: {error}")
            continue
        schema_errors = validate(suite, APM_METRICS_SEQUENCE_SCHEMA, label)
        if schema_errors:
            errors.extend(schema_errors)
            continue
        base_path = (ROOT / suite["base_fixture"]).resolve()
        if base_path != APM_METRICS_FIXTURE.resolve():
            errors.append(f"{label}: sequence suite must use the APM Metrics MVP fixture")
            continue
        base = load_json(base_path)
        seen_names: set[str] = set()
        for case_index, case in enumerate(suite["cases"]):
            case_label = f"{label}/cases/{case_index}/{case['name']}"
            if case["name"] in seen_names:
                errors.append(f"{case_label}: duplicate case name")
                continue
            seen_names.add(case["name"])
            if case["valid"] is not expected_validity:
                errors.append(f"{case_label}: case validity does not match its suite")
            exports, case_errors = materialize_sequence_exports(base, case, case_label)
            for export_index, export in enumerate(exports):
                case_errors.extend(
                    apm_metrics_fixture_errors(
                        contract,
                        export,
                        f"{case_label}/exports/{export_index}",
                        APM_MVP_METRIC_NAMES,
                        "exponentialHistogram",
                        False,
                    )
                )
            case_errors.extend(cumulative_sequence_errors(exports, case_label))
            if case["valid"]:
                if case_errors:
                    errors.extend(case_errors)
                continue
            if not case_errors:
                errors.append(f"{case_label}: invalid accumulation sequence did not fail")
                continue
            for expected_error in case["expected_errors"]:
                if not any(expected_error in actual for actual in case_errors):
                    errors.append(f"{case_label}: expected error containing {expected_error!r}, got {case_errors}")
        if seen_names != expected_names:
            errors.append(
                f"{label}: accumulation cases differ: "
                f"missing={sorted(expected_names - seen_names)}, unexpected={sorted(seen_names - expected_names)}"
            )
    return errors


def apm_metrics_conformance_errors(
    contract: dict[str, Any] | None = None,
    fixture: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    contract = contract if contract is not None else load_yaml(APM_METRICS_CONTRACT)
    contract_schema_errors = validate(contract, APM_METRICS_SCHEMA, "specs/apm/v1/metrics.yaml")
    errors.extend(contract_schema_errors)
    if contract_schema_errors:
        return errors
    if contract["contract_version"] != APM_METRICS_CONTRACT_VERSION:
        errors.append(f"APM metrics contract version must be {APM_METRICS_CONTRACT_VERSION}")
    if contract["otel_schema_url"] != APM_METRICS_OTEL_SCHEMA_URL:
        errors.append(f"APM metrics contract OTel schema must be {APM_METRICS_OTEL_SCHEMA_URL}")
    expected_schema_url_policy = {
        "normalization_target": APM_METRICS_OTEL_SCHEMA_URL,
        "accepted_source": {
            "empty": "allowed",
            "prefix": "https://opentelemetry.io/schemas/",
            "maximum_version": "1.43.0",
        },
    }
    if contract["schema_url_policy"] != expected_schema_url_policy:
        errors.append("APM metrics source OTel schema URL policy differs from the frozen target/maximum profile")
    expected_transport = {
        "temporality": "cumulative",
        "histogram": {
            "preferred": "exponential_histogram",
            "accepted": ["exponential_histogram", "explicit_histogram"],
        },
        "exemplars": {"preserve": True, "synthesize": False, "filtered_attributes": "forbidden"},
    }
    if contract["transport"] != expected_transport:
        errors.append("APM metrics transport profile differs from the frozen cumulative histogram profile")
    expected_accumulation = {
        "series_identity": [
            "resource_attributes",
            "instrumentation_scope",
            "metric_name",
            "point_attributes",
        ],
        "reset": {
            "trigger": "start_time_unix_nano_change",
            "start_time": "strictly_increasing",
        },
        "same_start": {
            "histogram_count": "non_decreasing",
            "histogram_sum": "non_decreasing",
            "histogram_buckets": "non_decreasing_at_common_scale",
            "monotonic_sum_value": "non_decreasing",
            "identical_timestamp": "idempotent_only",
        },
        "exponential_histogram": {
            "scale_change": "allowed",
            "comparison_scale": "minimum_of_previous_and_current",
        },
        "non_monotonic_sum_value": "unconstrained",
    }
    if contract["accumulation"] != expected_accumulation:
        errors.append("APM metrics accumulation profile differs from the frozen cumulative state rules")
    expected_red = {
        "metric": "http.server.request.duration",
        "throughput": "histogram_count",
        "errors": {"operation": "count_when_present", "attribute": "error.type"},
        "latency": "histogram_distribution",
        "trace_sampling": "independent",
        "vendor_counters": "forbidden",
    }
    if contract["red"] != expected_red:
        errors.append("APM RED derivation must use the HTTP duration histogram independently from trace sampling")
    if contract["resource"]["attributes"] != EXPECTED_APM_RESOURCE_ATTRIBUTES:
        errors.append("APM metrics Resource profile must contain the exact 11 typed required attributes")
    expected_policy = {
        "mode": "allowlist",
        "unknown_attributes": "reject",
        "max_attributes_per_point": 16,
        "max_string_value_bytes": 256,
        "forbidden": list(PROHIBITED_METRIC_ATTRIBUTES),
    }
    if contract["attribute_policy"] != expected_policy:
        errors.append("APM metrics attribute policy differs from the frozen reject/forbidden profile")
    contract_metrics = contract["metrics"]
    contract_names = tuple(metric["name"] for metric in contract_metrics)
    if contract_names != APM_MVP_METRIC_NAMES:
        errors.append(f"APM Metrics MVP order/profile differs: expected={list(APM_MVP_METRIC_NAMES)}, got={list(contract_names)}")

    try:
        baseline = load_json(APM_METRICS_BASELINE)
        if canonical_document_sha256(baseline) != EXPECTED_APM_METRICS_BASELINE_SHA256:
            errors.append("APM metrics compatibility baseline hash is not the reviewed immutable value")
        if apm_metrics_snapshot_data(contract) != baseline:
            errors.append("APM metrics contract differs from the frozen compatibility baseline")
    except (FileNotFoundError, json.JSONDecodeError, SpecError) as error:
        errors.append(f"invalid APM metrics compatibility baseline: {error}")

    semantic_registry = registry()
    if semantic_registry["version"] != APM_SEMANTIC_REGISTRY_VERSION:
        errors.append(f"semantic registry version must be {APM_SEMANTIC_REGISTRY_VERSION}")
    semantic_metrics = {metric["name"]: metric for metric in semantic_registry["metrics"]}
    semantic_attributes = {attribute["name"]: attribute for attribute in semantic_registry["attributes"]}
    for resource_attribute in contract["resource"]["attributes"]:
        semantic = semantic_attributes.get(resource_attribute["ref"])
        if semantic is None:
            errors.append(f"APM Resource attribute is not in the semantic registry: {resource_attribute['ref']}")
        elif semantic_otlp_type(semantic["type"]) != resource_attribute["type"]:
            errors.append(f"APM Resource attribute type disagrees with semantic registry: {resource_attribute['ref']}")
    for metric in contract_metrics:
        name = metric["name"]
        semantic = semantic_metrics.get(name)
        if semantic is None:
            errors.append(f"APM metric is not in the semantic registry: {name}")
            continue
        for field in ("instrument", "value_type", "unit", "stability"):
            if semantic.get(field) != metric.get(field):
                errors.append(f"APM metric {name} disagrees with semantic registry field {field}")
        allowed_refs = [attribute["ref"] for attribute in metric["attributes"]]
        if len(allowed_refs) != len(set(allowed_refs)):
            errors.append(f"APM metric {name} declares a duplicate attribute")
        if semantic.get("attributes") != allowed_refs:
            errors.append(f"APM metric {name} attributes must match semantic registry order")
        for ref in allowed_refs:
            if ref not in semantic_attributes:
                errors.append(f"APM metric {name} references unknown attribute {ref}")
        prohibited = set(PROHIBITED_METRIC_ATTRIBUTES).intersection(allowed_refs)
        if prohibited:
            errors.append(f"APM metric {name} allows prohibited high-cardinality attributes: {sorted(prohibited)}")

    apm_manifest = load_yaml(ROOT / "specs" / "apm" / "v1" / "manifest.yaml")
    if contract["contract_version"] != apm_manifest.get("metrics_contract_version"):
        errors.append("APM metrics contract version must match specs/apm/v1/manifest.yaml")
    if apm_manifest.get("semantic_rules", {}).get("metrics_independent_from_trace_sampling") is not True:
        errors.append("APM manifest must keep Metrics independent from Trace sampling")
    if (
        contract["otel_schema_url"] != semantic_registry["otel_schema_url"]
        or contract["otel_schema_url"] != apm_manifest["otel_schema_url"]
    ):
        errors.append("APM metrics contract must use the registered OTel schema URL")
    manifest_resources = apm_manifest.get("resource", {}).get("required", [])
    if manifest_resources != [item["ref"] for item in contract["resource"]["attributes"]]:
        errors.append("APM metrics Resource profile must match the APM manifest required Resource order")

    primary_fixture = fixture if fixture is not None else load_json(APM_METRICS_FIXTURE)
    errors.extend(
        apm_metrics_fixture_errors(
            contract,
            primary_fixture,
            "fixtures/metrics/apm-metrics-mvp.json",
            APM_MVP_METRIC_NAMES,
            "exponentialHistogram",
            True,
            True,
        )
    )
    histogram_names = tuple(name for name in APM_MVP_METRIC_NAMES if name in APM_HISTOGRAM_METRIC_NAMES)
    errors.extend(
        apm_metrics_fixture_errors(
            contract,
            load_json(APM_METRICS_EXPLICIT_FIXTURE),
            "fixtures/metrics/apm-metrics-explicit-histogram.json",
            histogram_names,
            "histogram",
            False,
            True,
        )
    )
    errors.extend(apm_metrics_negative_conformance_errors(contract))
    errors.extend(apm_metrics_accumulation_conformance_errors(contract))

    fixture_manifest = load_yaml(FIXTURES / "manifest.yaml")
    entries = {entry.get("path"): entry for entry in fixture_manifest.get("fixtures", []) if isinstance(entry, dict)}
    expected_entries = {
        "fixtures/metrics/apm-metrics-mvp.json": {
            "schema": "schemas/otlp-metrics-export.schema.json",
            "valid": True,
        },
        "fixtures/metrics/apm-metrics-explicit-histogram.json": {
            "schema": "schemas/otlp-metrics-export.schema.json",
            "valid": True,
        },
        "fixtures/metrics/apm-metrics-negative-cases.json": {
            "validator": "apm_metrics_negative_suite",
            "valid": True,
        },
        "fixtures/metrics/apm-metrics-cumulative-sequence.json": {
            "schema": "schemas/apm-metrics-cumulative-sequence.schema.json",
            "valid": True,
        },
        "fixtures/metrics/apm-metrics-cumulative-sequence-negative-cases.json": {
            "schema": "schemas/apm-metrics-cumulative-sequence.schema.json",
            "valid": True,
        },
    }
    for path, expected in expected_entries.items():
        entry = entries.get(path)
        if entry is None or any(entry.get(key) != value for key, value in expected.items()):
            errors.append(f"fixtures/manifest.yaml must register {path} with {expected}")
    return errors


def verify_apm_metrics_contract() -> None:
    errors = apm_metrics_conformance_errors()
    if errors:
        raise SpecError("APM Metrics conformance failed:\n- " + "\n- ".join(errors))
    print(
        "APM Metrics contract, OTLP fixtures, cumulative sequences, negative cases, "
        "and frozen profile conformance passed."
    )


def write_apm_metrics_snapshot(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(apm_metrics_snapshot_data(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote APM metrics compatibility snapshot: {output.relative_to(ROOT)}")


def breaking_apm_metrics(against: Path) -> None:
    baseline = load_json(against)
    current = apm_metrics_snapshot_data()
    if current != baseline:
        raise SpecError(f"APM Metrics contract differs from frozen baseline {against.relative_to(ROOT)}")
    print(f"No APM Metrics contract changes against {against.relative_to(ROOT)}.")


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

    apm_manifest = load_yaml(ROOT / "specs" / "apm" / "v1" / "manifest.yaml")
    matrix_apm_extension = protocol_matrix.get("protocols", {}).get("apm_extension", {})
    release_apm_extension = active_release.get("protocols", {}).get("apm_extension")
    if release_apm_extension != matrix_apm_extension.get("current"):
        errors.append("current release APM extension version must match compatibility/protocol-matrix.yaml")
    if release_apm_extension != apm_manifest.get("apm_extension_version"):
        errors.append("current release APM extension version must match specs/apm/v1/manifest.yaml")
    accepted_apm_extension_ranges = matrix_apm_extension.get("accepts", [])
    try:
        parse_semver(str(release_apm_extension))
        if not isinstance(accepted_apm_extension_ranges, list) or not accepted_apm_extension_ranges:
            errors.append("compatibility/protocol-matrix.yaml must declare accepted APM extension ranges")
        elif not any(
            semver_satisfies(str(release_apm_extension), str(expression))
            for expression in accepted_apm_extension_ranges
        ):
            errors.append("current release APM extension version must be included in its compatibility range")
    except SpecError as error:
        errors.append(str(error))

    matrix_apm_metrics = protocol_matrix.get("protocols", {}).get("apm_metrics", {})
    release_apm_metrics = active_release.get("protocols", {}).get("apm_metrics")
    if release_apm_metrics != matrix_apm_metrics.get("current"):
        errors.append("current release APM Metrics version must match compatibility/protocol-matrix.yaml")
    if release_apm_metrics != apm_manifest.get("metrics_contract_version"):
        errors.append("current release APM Metrics version must match specs/apm/v1/manifest.yaml")
    accepted_apm_metrics_ranges = matrix_apm_metrics.get("accepts", [])
    try:
        parse_semver(str(release_apm_metrics))
        if not isinstance(accepted_apm_metrics_ranges, list) or not accepted_apm_metrics_ranges:
            errors.append("compatibility/protocol-matrix.yaml must declare accepted APM Metrics ranges")
        elif not any(
            semver_satisfies(str(release_apm_metrics), str(expression))
            for expression in accepted_apm_metrics_ranges
        ):
            errors.append("current release APM Metrics version must be included in its compatibility range")
    except SpecError as error:
        errors.append(str(error))

    otel_matrix = load_yaml(ROOT / "compatibility" / "otel-schema-matrix.yaml")
    release_otel_schema = active_release.get("otel_schema")
    expected_otel_schema = str(apm_manifest.get("otel_schema_url", "")).rsplit("/", 1)[-1]
    if release_otel_schema != otel_matrix.get("current") or release_otel_schema != expected_otel_schema:
        errors.append("current release OTel Schema must match the APM manifest and OTel schema matrix")
    if matrix_apm_metrics.get("otel_schema") != release_otel_schema:
        errors.append("APM Metrics compatibility profile must pin the current release OTel Schema")

    matrix_control_plane = protocol_matrix.get("protocols", {}).get("control_plane_config", {})
    matrix_control_plane_version = matrix_control_plane.get("current")
    accepted_control_plane_ranges = matrix_control_plane.get("accepts", [])
    release_control_plane_version = active_release.get("protocols", {}).get("control_plane_config")
    if matrix_control_plane_version != release_control_plane_version:
        errors.append("current release Control Plane version must match compatibility/protocol-matrix.yaml")
    try:
        parse_semver(str(release_control_plane_version))
        if not isinstance(accepted_control_plane_ranges, list) or not accepted_control_plane_ranges:
            errors.append("compatibility/protocol-matrix.yaml must declare accepted Control Plane ranges")
        elif not any(
            semver_satisfies(str(release_control_plane_version), str(expression))
            for expression in accepted_control_plane_ranges
        ):
            errors.append("current release Control Plane version must be included in the compatibility acceptance range")
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

    for schema_path in (CONTROL_PLANE_REVISION_SCHEMA, CONTROL_PLANE_DELIVERY_SCHEMA):
        control_plane_schema = load_json(schema_path)
        contract_version = control_plane_schema.get("properties", {}).get("contract_version", {}).get("const")
        if contract_version != release_control_plane_version:
            errors.append(
                f"{schema_path.relative_to(ROOT).as_posix()} contract_version must equal the current release Control Plane version"
            )

    fixture_manifest = load_yaml(ROOT / "fixtures" / "manifest.yaml")
    for fixture in fixture_manifest.get("fixtures", []):
        fixture_path = ROOT / fixture["path"]
        if not fixture_path.is_file():
            errors.append(f"fixture does not exist: {fixture['path']}")
            continue
        fixture_data = load_json(fixture_path)
        custom_validator = fixture.get("validator")
        if custom_validator is not None:
            if custom_validator != "apm_metrics_negative_suite":
                errors.append(f"unknown fixture validator {custom_validator}: {fixture['path']}")
            if "schema" in fixture:
                errors.append(f"custom-validated fixture must not also declare schema: {fixture['path']}")
            continue
        if not isinstance(fixture.get("schema"), str):
            errors.append(f"fixture must declare schema or validator: {fixture['path']}")
            continue
        schema_path = ROOT / fixture["schema"]
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
    errors.extend(control_plane_conformance_errors())
    errors.extend(apm_metrics_conformance_errors())

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


def normalized_fixture_content(path: Path) -> str:
    return path.read_text(encoding="utf-8").rstrip() + "\n"


def rum_conformance_fixture_paths() -> list[Path]:
    return [path for path in sorted(FIXTURES.rglob("*.json")) if fixture_kind(path) != "metrics"]


def conformance_manifest_output() -> str:
    release = current_release()
    fixtures: list[dict[str, str]] = []
    for path in rum_conformance_fixture_paths():
        relative = path.relative_to(ROOT).as_posix()
        fixtures.append(
            {
                "path": relative,
                "kind": fixture_kind(path),
                "sha256": hashlib.sha256(normalized_fixture_content(path).encode("utf-8")).hexdigest(),
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
    for path in rum_conformance_fixture_paths():
        relative = path.relative_to(FIXTURES)
        output[ROOT / "generated" / "conformance" / "fixtures" / relative] = normalized_fixture_content(path)
    return output


def apm_metrics_package_json_output() -> str:
    return json.dumps(
        {
            "name": "@nebula-observability/apm-metrics-contract",
            "version": artifact_version(),
            "description": "Versioned Nebula APM Metrics OTLP contract and conformance fixtures.",
            "license": "Apache-2.0",
            "type": "module",
            "files": [
                "asset-manifest.json",
                "contract.json",
                "schemas",
                "fixtures",
                "compatibility",
                "README.md",
            ],
            "exports": {
                "./contract.json": "./contract.json",
                "./asset-manifest.json": "./asset-manifest.json",
                "./schemas/apm-metrics.schema.json": "./schemas/apm-metrics.schema.json",
                "./schemas/otlp-metrics-export.schema.json": "./schemas/otlp-metrics-export.schema.json",
                "./schemas/apm-metrics-cumulative-sequence.schema.json": "./schemas/apm-metrics-cumulative-sequence.schema.json",
                "./fixtures/apm-metrics-mvp.json": "./fixtures/apm-metrics-mvp.json",
                "./fixtures/apm-metrics-explicit-histogram.json": "./fixtures/apm-metrics-explicit-histogram.json",
                "./fixtures/apm-metrics-negative-cases.json": "./fixtures/apm-metrics-negative-cases.json",
                "./fixtures/apm-metrics-cumulative-sequence.json": "./fixtures/apm-metrics-cumulative-sequence.json",
                "./fixtures/apm-metrics-cumulative-sequence-negative-cases.json": "./fixtures/apm-metrics-cumulative-sequence-negative-cases.json",
                "./compatibility/apm-metrics.json": "./compatibility/apm-metrics.json",
            },
        },
        indent=2,
    ) + "\n"


def apm_metrics_package_readme_output() -> str:
    release = current_release()
    return f"""# @nebula-observability/apm-metrics-contract

Generated, immutable APM Metrics contract for Spec `{artifact_version()}` and
platform release `{release['release']}`. The bundle contains the exact 12-metric
OTLP profile, its schemas, ExponentialHistogram and explicit Histogram fixtures,
continuous cumulative export sequences, negative conformance cases, and the
frozen compatibility snapshot. OTLP exemplar trace/span IDs use lowercase hex;
filtered attributes are forbidden. Source Schema URLs may be empty or official
OpenTelemetry semver URLs up to the `1.43.0` normalization target.

Verify every file against `asset-manifest.json` before consuming it. Runtime
repositories must pin the matching release asset and must not copy or extend the
profile locally.
"""


def apm_metrics_bundle_payload_outputs() -> dict[Path, str]:
    return {
        APM_METRICS_BUNDLE / "package.json": apm_metrics_package_json_output(),
        APM_METRICS_BUNDLE / "README.md": apm_metrics_package_readme_output(),
        APM_METRICS_BUNDLE / "contract.json": json.dumps(
            load_yaml(APM_METRICS_CONTRACT), indent=2, sort_keys=True
        ) + "\n",
        APM_METRICS_BUNDLE / "schemas" / "apm-metrics.schema.json": normalized_fixture_content(
            APM_METRICS_SCHEMA
        ),
        APM_METRICS_BUNDLE / "schemas" / "otlp-metrics-export.schema.json": normalized_fixture_content(
            OTLP_METRICS_SCHEMA
        ),
        APM_METRICS_BUNDLE
        / "schemas"
        / "apm-metrics-cumulative-sequence.schema.json": normalized_fixture_content(APM_METRICS_SEQUENCE_SCHEMA),
        APM_METRICS_BUNDLE / "fixtures" / "apm-metrics-mvp.json": normalized_fixture_content(
            APM_METRICS_FIXTURE
        ),
        APM_METRICS_BUNDLE / "fixtures" / "apm-metrics-explicit-histogram.json": normalized_fixture_content(
            APM_METRICS_EXPLICIT_FIXTURE
        ),
        APM_METRICS_BUNDLE / "fixtures" / "apm-metrics-negative-cases.json": normalized_fixture_content(
            APM_METRICS_NEGATIVE_FIXTURE
        ),
        APM_METRICS_BUNDLE
        / "fixtures"
        / "apm-metrics-cumulative-sequence.json": normalized_fixture_content(APM_METRICS_SEQUENCE_FIXTURE),
        APM_METRICS_BUNDLE
        / "fixtures"
        / "apm-metrics-cumulative-sequence-negative-cases.json": normalized_fixture_content(
            APM_METRICS_SEQUENCE_NEGATIVE_FIXTURE
        ),
        APM_METRICS_BUNDLE / "compatibility" / "apm-metrics.json": normalized_fixture_content(
            APM_METRICS_BASELINE
        ),
    }


def apm_metrics_asset_manifest_output(payload: dict[Path, str]) -> str:
    release = current_release()
    files = [
        {
            "path": path.relative_to(APM_METRICS_BUNDLE).as_posix(),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
        for path, content in sorted(payload.items(), key=lambda item: item[0].as_posix())
    ]
    return json.dumps(
        {
            "format_version": 1,
            "spec_version": artifact_version(),
            "release": release["release"],
            "metrics_contract_version": release["protocols"]["apm_metrics"],
            "otel_schema": release["otel_schema"],
            "contract_sha256": canonical_document_sha256(load_yaml(APM_METRICS_CONTRACT)),
            "files": files,
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def apm_metrics_bundle_outputs() -> dict[Path, str]:
    payload = apm_metrics_bundle_payload_outputs()
    return {
        **payload,
        APM_METRICS_BUNDLE / "asset-manifest.json": apm_metrics_asset_manifest_output(payload),
    }


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
    output.update(apm_metrics_bundle_outputs())
    return output


def verify_artifacts() -> None:
    version = artifact_version()
    errors: list[str] = []

    for package_path, package_name in (
        (ROOT / "generated" / "typescript" / "package.json", "@nebula-observability/semantic-registry"),
        (TYPESCRIPT_RUTP / "package.json", "@nebula-observability/rutp-protobuf"),
        (ROOT / "generated" / "conformance" / "package.json", "@nebula-observability/rum-conformance"),
        (APM_METRICS_BUNDLE / "package.json", "@nebula-observability/apm-metrics-contract"),
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

    metrics_manifest_path = APM_METRICS_BUNDLE / "asset-manifest.json"
    try:
        metrics_manifest = load_json(metrics_manifest_path)
        release = current_release()
        expected_metadata = {
            "format_version": 1,
            "spec_version": version,
            "release": release["release"],
            "metrics_contract_version": release["protocols"]["apm_metrics"],
            "otel_schema": release["otel_schema"],
            "contract_sha256": EXPECTED_APM_METRICS_BASELINE_SHA256,
        }
        for field, expected in expected_metadata.items():
            if metrics_manifest.get(field) != expected:
                errors.append(f"APM Metrics bundle manifest {field} must be {expected}")
        payload_paths = {
            path.relative_to(APM_METRICS_BUNDLE).as_posix()
            for path in apm_metrics_bundle_payload_outputs()
        }
        manifest_files = metrics_manifest.get("files")
        if not isinstance(manifest_files, list):
            errors.append("APM Metrics bundle manifest files must be an array")
        else:
            declared_paths: set[str] = set()
            for entry in manifest_files:
                if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
                    errors.append("APM Metrics bundle manifest contains an invalid file entry")
                    continue
                relative = entry.get("path")
                if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
                    errors.append(f"APM Metrics bundle manifest contains an unsafe path: {relative}")
                    continue
                if relative in declared_paths:
                    errors.append(f"APM Metrics bundle manifest contains a duplicate path: {relative}")
                    continue
                declared_paths.add(relative)
                bundled = APM_METRICS_BUNDLE / Path(relative)
                if not bundled.is_file():
                    errors.append(f"APM Metrics bundle file is missing: {relative}")
                    continue
                actual_sha256 = hashlib.sha256(bundled.read_bytes()).hexdigest()
                if entry.get("sha256") != actual_sha256:
                    errors.append(f"APM Metrics bundle checksum mismatch: {relative}")
            if declared_paths != payload_paths:
                errors.append(
                    "APM Metrics bundle manifest file set differs: "
                    f"missing={sorted(payload_paths - declared_paths)}, "
                    f"unexpected={sorted(declared_paths - payload_paths)}"
                )
        bundled_contract = load_json(APM_METRICS_BUNDLE / "contract.json")
        if bundled_contract != load_yaml(APM_METRICS_CONTRACT):
            errors.append("APM Metrics bundled contract differs from specs/apm/v1/metrics.yaml")
    except (FileNotFoundError, json.JSONDecodeError, SpecError, KeyError, TypeError) as error:
        errors.append(f"invalid APM Metrics bundle: {error}")

    if errors:
        raise SpecError("Artifact verification failed:\n- " + "\n- ".join(errors))
    print("Generated TypeScript, Rust, Go, RUM conformance, and APM Metrics artifacts are valid.")


def generate(check: bool) -> None:
    expected = generated_files(registry())
    failures: list[str] = []
    conformance_fixtures = ROOT / "generated" / "conformance" / "fixtures"
    if not check and conformance_fixtures.exists():
        shutil.rmtree(conformance_fixtures)
    if not check and APM_METRICS_BUNDLE.exists():
        shutil.rmtree(APM_METRICS_BUNDLE)
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
        for managed_directory in (ROOT / "generated" / "conformance", APM_METRICS_BUNDLE):
            expected_managed = {path for path in expected if managed_directory in path.parents}
            if managed_directory.exists():
                for actual in managed_directory.rglob("*"):
                    if actual.is_file() and actual not in expected_managed:
                        failures.append(str(actual.relative_to(ROOT)))
    if failures:
        raise SpecError("Generated files are stale: " + ", ".join(failures))
    print(
        "Generated files are current."
        if check
        else "Generated language registries, RUM conformance, and APM Metrics bundles."
    )


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
    subparsers.add_parser("verify-control-plane-contract")
    subparsers.add_parser("verify-apm-metrics-contract")
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--check", action="store_true")
    subparsers.add_parser("verify-artifacts")
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--output", type=Path, required=True)
    apm_metrics_snapshot_parser = subparsers.add_parser("snapshot-apm-metrics")
    apm_metrics_snapshot_parser.add_argument("--output", type=Path, required=True)
    breaking_parser = subparsers.add_parser("breaking")
    breaking_parser.add_argument("--against", type=Path, required=True)
    apm_metrics_breaking_parser = subparsers.add_parser("breaking-apm-metrics")
    apm_metrics_breaking_parser.add_argument("--against", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "lint":
            lint()
        elif args.command == "verify-receiver-contract":
            verify_receiver_contract()
        elif args.command == "verify-control-plane-contract":
            verify_control_plane_contract()
        elif args.command == "verify-apm-metrics-contract":
            verify_apm_metrics_contract()
        elif args.command == "generate":
            generate(args.check)
        elif args.command == "verify-artifacts":
            verify_artifacts()
        elif args.command == "snapshot":
            write_snapshot(args.output.resolve())
        elif args.command == "snapshot-apm-metrics":
            write_apm_metrics_snapshot(args.output.resolve())
        elif args.command == "breaking":
            breaking(args.against.resolve())
        elif args.command == "breaking-apm-metrics":
            breaking_apm_metrics(args.against.resolve())
    except SpecError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
