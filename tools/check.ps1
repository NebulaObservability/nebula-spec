$ErrorActionPreference = 'Stop'

python tools/spec_tool.py lint
if ($LASTEXITCODE -ne 0) { throw 'Specification lint failed.' }

python tools/spec_tool.py generate --check
if ($LASTEXITCODE -ne 0) { throw 'Generated artifact check failed.' }

python tools/spec_tool.py verify-artifacts
if ($LASTEXITCODE -ne 0) { throw 'Distributable artifact check failed.' }

python tools/spec_tool.py breaking --against compatibility/baselines/semantic-registry-0.2.0-draft.0.json
if ($LASTEXITCODE -ne 0) { throw 'Compatibility check failed.' }

npx --yes @bufbuild/buf@1.72.0 lint
if ($LASTEXITCODE -ne 0) { throw 'Protobuf lint failed.' }

npx --yes @bufbuild/buf@1.72.0 build
if ($LASTEXITCODE -ne 0) { throw 'Protobuf build failed.' }

npx --yes @bufbuild/buf@1.72.0 breaking --against compatibility/baselines/rutp-v1.binpb
if ($LASTEXITCODE -ne 0) { throw 'Protobuf compatibility check failed.' }

Write-Host 'All specification checks passed.'
