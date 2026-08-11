#!/usr/bin/env python3
"""Build and verify the deterministic CycloneDX graph for a Spec release."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import urllib.parse
import uuid
from typing import Any


SBOM_NAME = "nebula-spec-release.cdx.json"
ROOT_NAME = "nebula-spec-release"
VERIFIER_NAME = "verify-nebula-spec-release.py"
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def expected_payload_names(version: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            (
                f"apm-agent-contract-{version}.zip",
                f"apm-metrics-contract-{version}.zip",
                f"nebula-observability-apm-agent-contract-{version}.tgz",
                f"nebula-observability-apm-metrics-contract-{version}.tgz",
                f"nebula-observability-rum-conformance-{version}.tgz",
                f"nebula-observability-rutp-protobuf-{version}.tgz",
                f"nebula-observability-semantic-registry-{version}.tgz",
                f"nebula-rutp-go-module-{version}.zip",
                f"nebula-semantic-registry-{version}.crate",
                f"platform-release-manifest-{version}.yaml",
                f"rum-conformance-fixtures-{version}.zip",
                VERIFIER_NAME,
            )
        )
    )


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def root_purl(version: str) -> str:
    return f"pkg:github/NebulaObservability/nebula-spec@{version}"


def payload_purl(name: str, version: str) -> str:
    encoded_name = urllib.parse.quote(name, safe=".-_")
    encoded_version = urllib.parse.quote(version, safe=".-_")
    return f"pkg:generic/nebula-spec-release/{encoded_name}@{encoded_version}"


def require_version(version: str) -> None:
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(f"invalid Spec release version: {version}")


def build_document(artifacts: pathlib.Path, version: str) -> dict[str, Any]:
    require_version(version)
    expected = expected_payload_names(version)
    actual = tuple(
        sorted(
            path.name
            for path in artifacts.iterdir()
            if path.is_file() and path.name != SBOM_NAME
        )
    )
    if actual != expected:
        raise ValueError(
            "release payload differs from the reviewed SBOM inventory: "
            f"expected {list(expected)}, got {list(actual)}"
        )

    components: list[dict[str, Any]] = []
    for name in expected:
        purl = payload_purl(name, version)
        components.append(
            {
                "type": "file",
                "bom-ref": purl,
                "name": name,
                "version": version,
                "purl": purl,
                "hashes": [{"alg": "SHA-256", "content": sha256(artifacts / name)}],
            }
        )

    root_ref = root_purl(version)
    component_refs = [component["bom-ref"] for component in components]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, root_ref)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": ROOT_NAME,
                "version": version,
                "purl": root_ref,
            }
        },
        "components": components,
        "dependencies": [
            {"ref": root_ref, "dependsOn": component_refs},
            *({"ref": reference, "dependsOn": []} for reference in component_refs),
        ],
    }


def verify_document(
    document: Any, artifacts: pathlib.Path, version: str
) -> None:
    require_version(version)
    if not isinstance(document, dict):
        raise ValueError("release SBOM root must be an object")
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != "1.6":
        raise ValueError("release SBOM must use CycloneDX 1.6")

    expected_root = {
        "type": "application",
        "bom-ref": root_purl(version),
        "name": ROOT_NAME,
        "version": version,
        "purl": root_purl(version),
    }
    metadata = document.get("metadata")
    root = metadata.get("component") if isinstance(metadata, dict) else None
    if root != expected_root:
        raise ValueError("release SBOM root component identity/version/PURL drifted")

    components = document.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("release SBOM components must be non-empty")
    expected_names = expected_payload_names(version)
    actual_names = tuple(sorted(component.get("name", "") for component in components if isinstance(component, dict)))
    if actual_names != expected_names or len(components) != len(expected_names):
        raise ValueError("release SBOM component inventory drifted")

    component_refs: list[str] = []
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("release SBOM component must be an object")
        name = component["name"]
        expected_purl = payload_purl(name, version)
        expected_hash = sha256(artifacts / name)
        if (
            component.get("type") != "file"
            or component.get("version") != version
            or component.get("purl") != expected_purl
            or component.get("bom-ref") != expected_purl
            or component.get("hashes")
            != [{"alg": "SHA-256", "content": expected_hash}]
        ):
            raise ValueError(f"release SBOM component identity/hash drifted: {name}")
        component_refs.append(expected_purl)

    if len(set(component_refs)) != len(component_refs):
        raise ValueError("release SBOM component references must be unique")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError("release SBOM dependency graph must be non-empty")
    by_ref: dict[str, Any] = {}
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(dependency.get("ref"), str):
            raise ValueError("release SBOM dependency entry is invalid")
        if dependency["ref"] in by_ref:
            raise ValueError("release SBOM dependency references must be unique")
        by_ref[dependency["ref"]] = dependency.get("dependsOn")
    root_ref = root_purl(version)
    if set(by_ref) != {root_ref, *component_refs}:
        raise ValueError("release SBOM dependency graph does not cover every component")
    if by_ref[root_ref] != component_refs or not by_ref[root_ref]:
        raise ValueError("release SBOM root must depend on the complete payload")
    if any(by_ref[reference] != [] for reference in component_refs):
        raise ValueError("release SBOM payload dependency leaves drifted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--artifacts", type=pathlib.Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.command == "build":
        document = build_document(arguments.artifacts, arguments.version)
        arguments.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    else:
        document = json.loads(arguments.output.read_text(encoding="utf-8"))
        verify_document(document, arguments.artifacts, arguments.version)
    print(f"Spec release SBOM {arguments.command} succeeded for {arguments.version}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Spec release SBOM verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
