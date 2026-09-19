param(
    [Parameter(Mandatory=$true)][string]$Scenario,
    [switch]$Deploy,
    [switch]$Reload,
    [switch]$Execute
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$remote=Join-Path $PSScriptRoot 'remote.ps1'
$spec=Get-Content -Raw -Encoding UTF8 -LiteralPath $Scenario | ConvertFrom-Json
if (!$spec.steps -or $spec.steps.Count -gt 30) {throw 'Scenario requires 1..30 steps'}
foreach($step in $spec.steps) {
    if ($step.command -notmatch '^jev (spawn|goal|observe|smoke|step|status|stop|start)( |$)' -or !$step.expect) {throw 'Each step requires a Jev command and an expected result regex'}
    [regex]::new([string]$step.expect) | Out-Null
}
if (!$Execute) {
    [pscustomobject]@{deploy=$Deploy.IsPresent;reload=$Reload.IsPresent;steps=$spec.steps;mode='PLAN';cleanup='stop and despawn owned bot; collect logs/traces'} | ConvertTo-Json -Depth 8
    return
}
$runId=[guid]::NewGuid().ToString()
$directory=Join-Path $repo ".runtime-harness/remote-$runId"
[IO.Directory]::CreateDirectory($directory) | Out-Null
$manifest=[ordered]@{id=$runId;status='RUNNING';steps=@();cleanup_errors=@();evidence_errors=@()}
$ownsBot=$false
$failure=$null
try {
    # Check ownership BEFORE reload can remove somebody else's currently running bot.
    if ($Deploy -or $Reload) {
        $preflight=(& $remote -Action Preflight -RunId $runId | Out-String) | ConvertFrom-Json
        if ($preflight.jev_artifacts -contains 'jev-control-paper.jar') {
            $before=(& $remote -Action Command -Command 'jev status' -RunId $runId | Out-String) | ConvertFrom-Json
            if (($before.output -join ' ') -notmatch 'bot=none') {throw 'Existing bot present; refusing deployment/reload'}
        }
    }
    if ($Deploy) {& $remote -Action Deploy -RunId $runId | Out-Null}
    if ($Reload) {& $remote -Action Reload -RunId $runId | Out-Null}
    $initial=(& $remote -Action Command -Command 'jev status' -RunId $runId | Out-String) | ConvertFrom-Json
    if (($initial.output -join ' ') -notmatch 'bot=none') {throw 'An existing managed bot is present; refusing to take it over'}
    foreach($step in $spec.steps) {
        if ($step.command -match '^jev spawn( |$)') {$ownsBot=$true}
        $response=(& $remote -Action Command -Command $step.command -RunId $runId | Out-String) | ConvertFrom-Json
        $deadline=[DateTime]::UtcNow.AddSeconds(30)
        $text=$response.output -join ' '
        while ($text -notmatch $step.expect -and [DateTime]::UtcNow -lt $deadline) {
            if ($text -match 'state=(ERROR|DEAD_OR_DISCONNECTED)') {throw $text}
            Start-Sleep -Milliseconds 500
            $response=(& $remote -Action Command -Command 'jev status' -RunId $runId | Out-String) | ConvertFrom-Json
            $text=$response.output -join ' '
        }
        if ($text -notmatch $step.expect) {throw "Expected result missing for: $($step.command)"}
        $manifest.steps+=@{command=$step.command;expect=$step.expect;receipt=$response}
    }
    $manifest.status='PASSED'
} catch {
    $failure=$_
    $manifest.status='FAILED'
    $manifest.failure=$_.Exception.Message
} finally {
    if ($ownsBot) {
        foreach($command in @('jev stop','jev despawn')) {
            try {& $remote -Action Command -Command $command -RunId $runId | Out-Null}
            catch {$manifest.cleanup_errors+=@($_.Exception.Message);$manifest.status='FAILED'}
        }
    }
    foreach($action in @('Log','Traces')) {
        try {& $remote -Action $action -RunId $runId | Out-Null}
        catch {$manifest.evidence_errors+=@($_.Exception.Message);$manifest.status='FAILED'}
    }
    $json=$manifest | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText((Join-Path $directory 'experiment.json'),$json,[Text.UTF8Encoding]::new($false))
    $json
}
if ($failure) {throw $failure}
if ($manifest.status -ne 'PASSED') {throw 'Cleanup or evidence collection failed; inspect experiment.json'}
