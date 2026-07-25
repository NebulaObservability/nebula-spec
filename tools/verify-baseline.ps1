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
    'specs/rum/rutp/v1/README.md',
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
    'compatibility/README.md',
    'compatibility/protocol-matrix.yaml',
    'compatibility/otel-schema-matrix.yaml',
    'fixtures/README.md',
    'fixtures/manifest.yaml',
    'generated/README.md',
    'releases/README.md',
    'tools/spec_tool.py',
    'tools/check.ps1',
    'tools/requirements.txt',
    '.github/CODEOWNERS',
    '.github/pull_request_template.md'
)

$missing = $requiredFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) }
if ($missing) {
    throw "Missing required files: $($missing -join ', ')"
}

$version = (Get-Content -Raw -LiteralPath 'VERSION').Trim()
if ($version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') {
    throw "VERSION is not a valid semantic version: $version"
}

Write-Host "Specification baseline is valid ($version)."
