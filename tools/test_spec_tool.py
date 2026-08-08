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
                release="spec-v0.7.0-draft.0"
            ),
        }

        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(original)
                mutate(changed)
                self.assertTrue(self.errors(changed))


if __name__ == "__main__":
    unittest.main()
