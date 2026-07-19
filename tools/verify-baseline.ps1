$ErrorActionPreference = 'Stop'

$requiredFiles = @(
    'README.md',
    'VERSION',
    'VERSIONING.md',
    'CONTRIBUTING.md',
    'specs/README.md',
    'specs/apm/v1/README.md',
    'specs/rum/rutp/v1/README.md',
    'specs/semantics/README.md',
    'specs/privacy/README.md',
    'specs/otlp/README.md',
    'schemas/README.md',
    'compatibility/README.md',
    'fixtures/README.md',
    'generated/README.md',
    'releases/README.md',
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
