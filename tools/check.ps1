$ErrorActionPreference = 'Stop'

python tools/spec_tool.py lint
if ($LASTEXITCODE -ne 0) { throw 'Specification lint failed.' }

python tools/spec_tool.py verify-receiver-contract
if ($LASTEXITCODE -ne 0) { throw 'RUTP Receiver conformance check failed.' }

python tools/spec_tool.py verify-control-plane-contract
if ($LASTEXITCODE -ne 0) { throw 'Control Plane configuration conformance check failed.' }

python tools/spec_tool.py verify-apm-metrics-contract
if ($LASTEXITCODE -ne 0) { throw 'APM Metrics conformance check failed.' }

$protobufGeneratedBefore = (git status --porcelain -- generated/go generated/typescript-rutp) -join "`n"
npx --yes @bufbuild/buf@1.72.0 generate --template buf.gen.yaml
if ($LASTEXITCODE -ne 0) { throw 'RUTP Protobuf generation failed.' }
$protobufGeneratedAfter = (git status --porcelain -- generated/go generated/typescript-rutp) -join "`n"
if ($protobufGeneratedBefore -ne $protobufGeneratedAfter) {
    throw 'Generated Go or TypeScript RUTP Protobuf sources are stale. Run: npx --yes @bufbuild/buf@1.72.0 generate --template buf.gen.yaml'
}

python tools/spec_tool.py generate --check
if ($LASTEXITCODE -ne 0) { throw 'Generated artifact check failed.' }

python tools/spec_tool.py verify-artifacts
if ($LASTEXITCODE -ne 0) { throw 'Distributable artifact check failed.' }

python tools/spec_tool.py breaking --against compatibility/baselines/semantic-registry-0.5.0-draft.0.json
if ($LASTEXITCODE -ne 0) { throw 'Compatibility check failed.' }

python tools/spec_tool.py breaking-apm-metrics --against compatibility/baselines/apm-metrics-1.1.0-draft.0.json
if ($LASTEXITCODE -ne 0) { throw 'APM Metrics compatibility check failed.' }

npx --yes @bufbuild/buf@1.72.0 lint
if ($LASTEXITCODE -ne 0) { throw 'Protobuf lint failed.' }

npx --yes @bufbuild/buf@1.72.0 build
if ($LASTEXITCODE -ne 0) { throw 'Protobuf build failed.' }

npx --yes @bufbuild/buf@1.72.0 breaking --against compatibility/baselines/rutp-v1.binpb
if ($LASTEXITCODE -ne 0) { throw 'Protobuf compatibility check failed.' }

Write-Host 'All specification checks passed.'
