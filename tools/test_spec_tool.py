import copy
import unittest

from tools.spec_tool import (
    ROOT,
    SCHEMAS,
    load_yaml,
    monotonic_sum_accumulation_errors,
    release_manifest_errors,
    validate,
)


class MonotonicSumAccumulationTest(unittest.TestCase):
    def test_large_integer_regression_is_exact(self) -> None:
        errors = monotonic_sum_accumulation_errors(
            {"asInt": "9007199254740993"},
            {"asInt": "9007199254740992"},
            "large-integer-series",
        )

        self.assertTrue(any("value regressed" in error for error in errors), errors)

    def test_large_integer_growth_is_valid(self) -> None:
        errors = monotonic_sum_accumulation_errors(
            {"asInt": "9007199254740992"},
            {"asInt": "9007199254740993"},
            "large-integer-series",
        )

        self.assertEqual([], errors)


class ReleaseManifestValidationTest(unittest.TestCase):
    schema = SCHEMAS / "release-manifest.schema.json"

    def errors(self, manifest: dict[str, object]) -> list[str]:
        return validate(manifest, self.schema, "release manifest") + release_manifest_errors(manifest)

    def test_historical_v1_manifests_remain_valid(self) -> None:
        historical = sorted((ROOT / "releases").glob("2026.07.*.yaml"))

        self.assertGreaterEqual(len(historical), 7)
        for path in historical:
            with self.subTest(path=path.name):
                manifest = load_yaml(path)
                self.assertNotIn("schema_version", manifest)
                self.assertEqual([], self.errors(manifest))

    def test_platform_v2_manifest_is_valid(self) -> None:
        manifest = load_yaml(ROOT / "releases" / "2026.08.1-mvp.yaml")

        self.assertEqual(2, manifest["schema_version"])
        self.assertEqual([], self.errors(manifest))

    def test_platform_manifest_mutations_fail_closed(self) -> None:
        original = load_yaml(ROOT / "releases" / "2026.08.1-mvp.yaml")
        mutations = {
            "missing component": lambda value: value["components"].pop("backend"),
            "source revision drift": lambda value: value["components"]["collector"]["source"].update(
                revision="not-a-git-sha"
            ),
            "image digest drift": lambda value: value["components"]["dashboard"]["artifact"].update(
                reference="docker.io/baicie2/nebula-dashboard:latest"
            ),
            "repository drift": lambda value: value["components"]["backend"]["source"].update(
                repository="Example/nebula-backend"
            ),
            "spec release drift": lambda value: value["components"]["rum_web"]["spec_dependency"].update(
                release="spec-v9.9.9", version="9.9.9"
            ),
            "transitive Spec mismatch": lambda value: value["components"]["backend"]["spec_dependency"].update(
                release="spec-v0.5.0-draft.0", version="0.5.0-draft.0"
            ),
            "vendored Spec mismatch": lambda value: value["components"]["dashboard"]["spec_dependency"].update(
                release="spec-v0.7.0-draft.0", version="0.7.0-draft.0"
            ),
            "absolute evidence": lambda value: value["components"]["collector"]["spec_dependency"].update(
                evidence=["/etc/passwd"]
            ),
            "parent evidence": lambda value: value["components"]["collector"]["spec_dependency"].update(
                evidence=["../../unrelated"]
            ),
            "direct dependency via": lambda value: value["components"]["collector"]["spec_dependency"].update(
                via="unexpected"
            ),
        }

        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(original)
                mutate(changed)
                self.assertTrue(self.errors(changed))

    def test_schema_rejects_unsafe_evidence_and_direct_via(self) -> None:
        original = load_yaml(ROOT / "releases" / "2026.08.1-mvp.yaml")
        mutations = (
            lambda value: value["components"]["collector"]["spec_dependency"].update(
                evidence=["/etc/passwd"]
            ),
            lambda value: value["components"]["collector"]["spec_dependency"].update(
                evidence=["../../unrelated"]
            ),
            lambda value: value["components"]["collector"]["spec_dependency"].update(
                via="unexpected"
            ),
        )

        for mutate in mutations:
            changed = copy.deepcopy(original)
            mutate(changed)
            self.assertTrue(validate(changed, self.schema, "release manifest"))


class ReleaseWorkflowSecurityTest(unittest.TestCase):
    def test_release_assets_have_signed_supply_chain_evidence(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-artifacts.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("id-token: write", workflow)
        self.assertIn(
            "anchore/sbom-action@aa0e114b2e19480f157109b9922bda359bd98b90",
            workflow,
        )
        self.assertIn(
            "sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6",
            workflow,
        )
        self.assertIn("nebula-spec-release.cdx.json", workflow)
        self.assertIn("https://slsa.dev/provenance/v1", workflow)
        self.assertIn("cosign sign-blob --yes --bundle", workflow)
        self.assertIn("cosign verify-blob", workflow)

    def test_release_is_reverified_without_source_checkout(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-artifacts.yml").read_text(
            encoding="utf-8"
        )
        verification = workflow.split("  verify-release:", maxsplit=1)

        self.assertEqual(2, len(verification), "release workflow lacks an independent verifier job")
        self.assertNotIn("actions/checkout@", verification[1])
        self.assertIn("gh release download", verification[1])
        self.assertIn("[.draft, .prerelease, .immutable, .tag_name]", verification[1])
        self.assertIn('test "$(resolve_tag_commit)" = "${GITHUB_SHA}"', verification[1])
        self.assertIn("sha256sum --check SHA256SUMS", verification[1])
        self.assertIn("cosign verify-blob", verification[1])


if __name__ == "__main__":
    unittest.main()
