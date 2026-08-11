import copy
import re
import subprocess
import unittest

import yaml

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
    verifier = ROOT / "tools" / "verify-action-pins.rb"

    def run_action_verifier(self, source: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["ruby", str(self.verifier), "-"],
            input=source,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_ast_action_pin_verifier_rejects_structural_bypasses(self) -> None:
        valid = self.run_action_verifier(
            """
name: valid
on: pull_request
jobs:
  check:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
"""
        )
        self.assertEqual(0, valid.returncode, valid.stderr)

        mutations = {
            "flow mapping": """
name: invalid
on: pull_request
jobs:
  check:
    runs-on: ubuntu-24.04
    steps:
      - {"uses": "evil/example@v1"}
""",
            "duplicate key": """
name: invalid
on: pull_request
jobs:
  check:
    runs-on: ubuntu-24.04
    runs-on: ubuntu-latest
""",
            "alias": """
name: invalid
on: pull_request
defaults: &shared
  run:
    shell: bash
jobs:
  check:
    defaults: *shared
    runs-on: ubuntu-24.04
""",
        }
        for name, source in mutations.items():
            with self.subTest(name=name):
                result = self.run_action_verifier(source)
                self.assertNotEqual(0, result.returncode)

    def test_all_workflows_pass_ast_action_pin_verifier(self) -> None:
        result = subprocess.run(
            ["ruby", str(self.verifier)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_release_commits_require_exactly_one_merged_main_pr(self) -> None:
        head_check = 'gh pr checks "${merged_pr_number}" --repo "${GITHUB_REPOSITORY}"'
        permission_controls = ("checks", "pull-requests", "statuses")
        run_controls = (
            'repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/pulls?per_page=100',
            '.state == "closed"',
            ".merged_at != null",
            ".merge_commit_sha == env.GITHUB_SHA",
            '.base.ref == "main"',
            ".base.repo.full_name == env.GITHUB_REPOSITORY",
            "select(length == 1)",
            '[[ "${merged_pr_number}" =~ ^[1-9][0-9]*$ ]]',
            head_check,
        )
        required = (
            "checks: read",
            "pull-requests: read",
            "statuses: read",
            *run_controls,
        )
        provenance_targets = {
            "release-artifacts.yml": ("release", "Verify tag matches VERSION"),
            "go-module.yml": ("validate", "Verify module tag matches VERSION"),
        }

        def errors(workflow: str, name: str) -> list[str]:
            failures: list[str] = []
            try:
                document = yaml.safe_load(workflow)
            except yaml.YAMLError:
                return ["valid workflow YAML"]

            job_name, step_name = provenance_targets[name]
            permissions = document.get("permissions") if isinstance(document, dict) else None
            for control in permission_controls:
                if not isinstance(permissions, dict) or permissions.get(control) != "read":
                    failures.append(f"{control}: read")
            jobs = document.get("jobs", {}) if isinstance(document, dict) else {}
            job = jobs.get(job_name, {}) if isinstance(jobs, dict) else {}
            steps = job.get("steps", []) if isinstance(job, dict) else []
            target_steps = [
                step
                for step in steps
                if isinstance(step, dict) and step.get("name") == step_name
            ]
            if len(target_steps) != 1:
                failures.append(f"unique provenance step: {step_name}")
                return failures

            step = target_steps[0]
            environment = step.get("env")
            if not isinstance(environment, dict) or environment.get("GH_TOKEN") != "${{ github.token }}":
                failures.append("GH_TOKEN: ${{ github.token }}")
            run = step.get("run")
            commands = (
                "\n".join(
                    line.strip()
                    for line in run.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                )
                if isinstance(run, str)
                else ""
            )
            failures.extend(control for control in run_controls if control not in commands)
            executable_head_check = re.compile(rf"(?m)^{re.escape(head_check)}$")
            if executable_head_check.search(commands) is None:
                failures.append(head_check)
            return failures

        for name in ("release-artifacts.yml", "go-module.yml"):
            workflow = (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf-8"
            )
            self.assertEqual([], errors(workflow, name), name)
            for fragment in required:
                with self.subTest(workflow=name, mutation=fragment):
                    mutated = workflow.replace(fragment, "removed", 1)
                    self.assertNotEqual(workflow, mutated)
                    self.assertTrue(errors(mutated, name))
            commented = workflow.replace(
                f"          {head_check}", f"          # {head_check}", 1
            )
            self.assertNotEqual(workflow, commented)
            self.assertTrue(errors(commented, name), name)
            commented_jq = workflow.replace(
                "            --jq ", "            # --jq ", 1
            )
            self.assertNotEqual(workflow, commented_jq)
            self.assertTrue(errors(commented_jq, name), name)

    def test_workflows_use_reviewed_action_tags_and_exact_toolchains(self) -> None:
        reviewed_actions = {
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262": "v4.4.0",
            "actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e": "v7.0.0",
            "actions/setup-java@c5195efecf7bdfc987ee8bae7a71cb8b11521c00": "v4.7.1",
            "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020": "v4.4.0",
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065": "v5.6.0",
            "anchore/sbom-action@aa0e114b2e19480f157109b9922bda359bd98b90": "v0.20.8",
            "bufbuild/buf-setup-action@a47c93e0b1648d5651a065437926377d060baa99": "v1.50.0",
            "sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6": "v4.1.2",
        }
        action_pattern = re.compile(
            r"(?m)^\s*(?:-\s*)?uses\s*:\s*(?P<ref>[^\s#]+)"
            r"(?:\s+#\s+(?P<tag>\S+))?\s*$"
        )
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
        }
        expected_toolchains = {
            "go-module.yml": {"python": ["3.13.14"], "go": ["1.25.12"]},
            "release-artifacts.yml": {
                "python": ["3.13.14"],
                "node": ["22.23.1"],
                "go": ["1.25.12"],
            },
            "repository-baseline.yml": {},
            "specification.yml": {
                "python": ["3.13.14"],
                "java": ["21.0.12+8.0.LTS"],
                "node": ["22.23.1"],
                "go": ["1.25.12"],
            },
        }

        def security_errors(sources: dict[str, str]) -> tuple[list[str], set[str]]:
            errors: list[str] = []
            found: set[str] = set()
            all_runs: list[str] = []
            for name, workflow in sources.items():
                try:
                    document = yaml.safe_load(workflow)
                except yaml.YAMLError:
                    errors.append(f"{name}: valid YAML")
                    continue
                jobs = document.get("jobs") if isinstance(document, dict) else None
                if not isinstance(jobs, dict) or not jobs:
                    errors.append(f"{name}: jobs mapping")
                    continue

                structured_actions: list[str] = []
                toolchains: dict[str, list[str]] = {}
                for job_name, job in jobs.items():
                    if not isinstance(job, dict) or job.get("runs-on") != "ubuntu-24.04":
                        errors.append(f"{name}: {job_name} runner")
                        continue
                    steps = job.get("steps")
                    if not isinstance(steps, list):
                        errors.append(f"{name}: {job_name} steps")
                        continue
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        run = step.get("run")
                        if isinstance(run, str):
                            all_runs.append(run)
                        reference = step.get("uses")
                        if not isinstance(reference, str):
                            continue
                        structured_actions.append(reference)
                        if reference.startswith("./"):
                            continue
                        found.add(reference)
                        if reference not in reviewed_actions:
                            errors.append(f"{name}: unreviewed action {reference}")
                        action = reference.partition("@")[0]
                        language = {
                            "actions/setup-python": "python",
                            "actions/setup-node": "node",
                            "actions/setup-go": "go",
                            "actions/setup-java": "java",
                        }.get(action)
                        if language is not None:
                            inputs = step.get("with")
                            version = (
                                inputs.get(f"{language}-version")
                                if isinstance(inputs, dict)
                                else None
                            )
                            toolchains.setdefault(language, []).append(version)

                text_matches = list(action_pattern.finditer(workflow))
                if [match.group("ref") for match in text_matches] != structured_actions:
                    errors.append(f"{name}: action syntax and tag-comment binding")
                for match in text_matches:
                    reference = match.group("ref")
                    if reference.startswith("./"):
                        continue
                    if match.group("tag") != reviewed_actions.get(reference):
                        errors.append(f"{name}: action tag comment drifted {reference}")
                if toolchains != expected_toolchains[name]:
                    errors.append(f"{name}: exact toolchains {toolchains}")

            all_run_text = "\n".join(all_runs)
            if "dtolnay/rust-toolchain@" in all_run_text:
                errors.append("mutable Rust action")
            if all_run_text.count(
                "rustup toolchain install 1.85.0 --profile minimal --no-self-update"
            ) != 2:
                errors.append("exact Rust installation commands")
            if all_run_text.count("cargo +1.85.0") != 3:
                errors.append("exact Rust cargo commands")
            return errors, found

        errors, found = security_errors(workflows)
        self.assertEqual([], errors)
        self.assertEqual(set(reviewed_actions), found)

        specification = workflows["specification.yml"]
        checkout_line = (
            "      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 "
            "# v4.4.0"
        )
        mutations = {
            "spaced mutable action": specification.replace(
                checkout_line,
                f"      # {checkout_line.strip()}\n"
                "      - uses : actions/checkout@v4",
                1,
            ),
            "spaced runner alias": specification.replace(
                "    runs-on: ubuntu-24.04",
                "    # runs-on: ubuntu-24.04\n    runs-on : ubuntu-latest",
                1,
            ),
            "spaced Python range": specification.replace(
                '          python-version: "3.13.14"',
                '          # python-version: "3.13.14"\n'
                '          python-version : "3.13"',
                1,
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(specification, mutated)
                changed = dict(workflows)
                changed["specification.yml"] = mutated
                mutation_errors, _ = security_errors(changed)
                self.assertTrue(mutation_errors)

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
