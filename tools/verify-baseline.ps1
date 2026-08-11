$ErrorActionPreference = 'Stop'

$requiredFiles = @(
    'README.md',
    'VERSION',
    'VERSIONING.md',
    'CONTRIBUTING.md',
    'buf.yaml',
    'buf.gen.yaml',
    'specs/README.md',
    'specs/apm/v1/README.md',
    'specs/apm/v1/manifest.yaml',
    'specs/apm/v1/go-agent.yaml',
    'specs/control-plane/v1/README.md',
    'specs/rum/rutp/v1/README.md',
    'specs/rum/rutp/v1/receiver.md',
    'specs/rum/rutp/v1/batch.proto',
    'specs/rum/rutp/v1/common.proto',
    'specs/rum/rutp/v1/config.proto',
    'specs/rum/rutp/v1/context.proto',
    'specs/rum/rutp/v1/record.proto',
    'specs/rum/rutp/v1/replay.proto',
    'specs/semantics/README.md',
    'specs/semantics/attributes.yaml',
    'specs/semantics/events.yaml',
    'specs/semantics/metrics.yaml',
    'specs/semantics/spans.yaml',
    'specs/semantics/enums.yaml',
    'specs/privacy/README.md',
    'specs/privacy/classification.yaml',
    'specs/privacy/default-policy.yaml',
    'specs/otlp/README.md',
    'specs/otlp/mappings.yaml',
    'schemas/README.md',
    'schemas/rutp-receiver-conformance.schema.json',
    'schemas/control-plane-config-revision.schema.json',
    'schemas/control-plane-config-delivery.schema.json',
    'schemas/apm-go-agent.schema.json',
    'schemas/apm-agent-config.schema.json',
    'schemas/apm-agent-diagnostics.schema.json',
    'compatibility/README.md',
    'compatibility/protocol-matrix.yaml',
    'compatibility/otel-schema-matrix.yaml',
    'fixtures/README.md',
    'fixtures/manifest.yaml',
    'fixtures/receiver/accepted-binding.json',
    'fixtures/receiver/rejected-missing-ingest-permission.json',
    'fixtures/receiver/rejected-project-mismatch.json',
    'fixtures/control-plane/active-rum-config-revision.json',
    'fixtures/control-plane/rollback-rum-config-revision.json',
    'fixtures/control-plane/delivery-active-rum-config.json',
    'fixtures/control-plane/invalid-privacy-escalation.json',
    'fixtures/control-plane/invalid-client-scope-in-delivery.json',
    'fixtures/agent/apm-agent-config.json',
    'fixtures/agent/apm-agent-disabled-config.json',
    'fixtures/agent/apm-agent-diagnostics.json',
    'fixtures/metrics/apm-metrics-go-agent.json',
    'fixtures/metrics/apm-metrics-go-agent-negative-cases.json',
    'fixtures/metrics/apm-metrics-standard-go-distro.json',
    'fixtures/receiver/json-debug-unknown-members.json',
    'fixtures/receiver/rejected-json-debug-missing-opt-in.json',
    'fixtures/receiver/rejected-json-debug-not-authorized.json',
    'generated/README.md',
    'releases/README.md',
    'releases/CURRENT',
    'releases/2026.07.2-draft.yaml',
    'releases/2026.07.3-draft.yaml',
    'releases/2026.07.5-draft.yaml',
    'releases/2026.07.7-draft.yaml',
    'releases/2026.08.1-mvp.yaml',
    'tools/spec_tool.py',
    'tools/release_sbom.py',
    'tools/test_release_sbom.py',
    'tools/verify-action-pins.rb',
    'tools/check.ps1',
    'tools/requirements.txt',
    '.github/CODEOWNERS',
    '.github/pull_request_template.md'
)

$missing = $requiredFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) }
if ($missing) {
    throw "Missing required files: $($missing -join ', ')"
}

$mutableActionRefs = @()
Get-ChildItem -LiteralPath '.github/workflows' -File | Where-Object {
    $_.Extension -in @('.yml', '.yaml')
} | ForEach-Object {
    $workflow = $_
    $lineNumber = 0
    Get-Content -LiteralPath $workflow.FullName | ForEach-Object {
        $lineNumber++
        if ($_ -match '^\s*(?:-\s*)?uses:\s*(?<action>[^@\s]+)@(?<reference>[^\s#]+)' -and
            -not $Matches.action.StartsWith('./') -and
            $Matches.reference -notmatch '^[0-9a-f]{40}$') {
            $mutableActionRefs += "$($workflow.FullName):${lineNumber}: $($Matches.action)@$($Matches.reference)"
        }
    }
}
if ($mutableActionRefs) {
    throw "Workflow actions must use reviewed 40-character commit SHAs:`n$($mutableActionRefs -join "`n")"
}

$ruby = Get-Command ruby -ErrorAction SilentlyContinue
if (-not $ruby) {
    throw 'Ruby is required for AST workflow action pin verification.'
}
& ruby ./tools/verify-action-pins.rb
if ($LASTEXITCODE -ne 0) {
    throw 'AST workflow action pin verification failed.'
}

$version = (Get-Content -Raw -LiteralPath 'VERSION').Trim()
if ($version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') {
    throw "VERSION is not a valid semantic version: $version"
}

Write-Host "Specification baseline is valid ($version)."
