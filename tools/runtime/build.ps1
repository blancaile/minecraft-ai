param([switch]$Clean, [switch]$Smoke)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $repo
try {
    $diagnostics = @(Get-ChildItem src/main -Recurse -File | Select-String -SimpleMatch -Pattern 'RUNTIME-DIAG','HARNESS-DIAG')
    if ($diagnostics.Count) { throw 'Remove temporary diagnostic statements before producing the deployment JAR.' }
    $tasks = @('build', '--console=plain')
    if ($Clean) { $tasks = @('clean') + $tasks }
    & ./gradlew.bat @tasks
    if ($LASTEXITCODE -ne 0) { throw 'Gradle build failed' }
    $artifact = (Resolve-Path build/libs/jev-control-paper-0.2.0.jar).Path
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($artifact)
    try {
        if (!$zip.GetEntry('plugin.yml') -or $zip.GetEntry('fabric.mod.json')) { throw 'Not a Paper plugin JAR' }
        if (@($zip.Entries | Where-Object {$_.FullName -match '^(net/minecraft|org/bukkit|carpet|net/fabricmc)/'}).Count) {
            throw 'Server or MOD classes must not be bundled'
        }
    } finally { $zip.Dispose() }
    & (Join-Path $PSScriptRoot 'test-remote.ps1') -Artifact $artifact
    python -m unittest discover -s tools/runtime -p test_paper_acceptance.py
    if ($LASTEXITCODE -ne 0) { throw 'Acceptance evidence verifier tests failed' }
    if ($Smoke) {
        python tools/ci/server_smoke.py $artifact
        if ($LASTEXITCODE -ne 0) { throw 'Paper runtime smoke failed' }
    }
    [pscustomobject]@{artifact=$artifact;sha256=(Get-FileHash $artifact -Algorithm SHA256).Hash;bytes=(Get-Item $artifact).Length}
} finally { Pop-Location }
