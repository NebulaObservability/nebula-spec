from __future__ import annotations

import copy
import pathlib
import tempfile
import unittest

from tools import release_sbom


class ReleaseSbomTests(unittest.TestCase):
    VERSION = "0.8.0-draft.0"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.artifacts = pathlib.Path(self.temporary.name)
        for name in release_sbom.expected_payload_names(self.VERSION):
            (self.artifacts / name).write_bytes(f"payload:{name}\n".encode())
        self.document = release_sbom.build_document(self.artifacts, self.VERSION)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_builds_and_verifies_complete_release_graph(self) -> None:
        release_sbom.verify_document(self.document, self.artifacts, self.VERSION)
        root_ref = release_sbom.root_purl(self.VERSION)
        root_dependency = next(
            value for value in self.document["dependencies"] if value["ref"] == root_ref
        )
        self.assertEqual(len(self.document["components"]), len(root_dependency["dependsOn"]))

    def test_rejects_empty_components_or_relationships(self) -> None:
        for field in ("components", "dependencies"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.document)
                mutated[field] = []
                with self.assertRaises(ValueError):
                    release_sbom.verify_document(mutated, self.artifacts, self.VERSION)

    def test_rejects_root_identity_version_or_purl_drift(self) -> None:
        for field, value in (
            ("name", "other-release"),
            ("version", "9.9.9"),
            ("purl", "pkg:github/evil/repository@9.9.9"),
        ):
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.document)
                mutated["metadata"]["component"][field] = value
                with self.assertRaisesRegex(ValueError, "identity/version/PURL"):
                    release_sbom.verify_document(mutated, self.artifacts, self.VERSION)

    def test_rejects_incomplete_relationship_graph(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["dependencies"][0]["dependsOn"] = []
        with self.assertRaisesRegex(ValueError, "complete payload"):
            release_sbom.verify_document(mutated, self.artifacts, self.VERSION)

    def test_rejects_tampered_payload(self) -> None:
        target = self.artifacts / release_sbom.expected_payload_names(self.VERSION)[0]
        target.write_bytes(b"tampered\n")
        with self.assertRaisesRegex(ValueError, "identity/hash drifted"):
            release_sbom.verify_document(self.document, self.artifacts, self.VERSION)


if __name__ == "__main__":
    unittest.main()
