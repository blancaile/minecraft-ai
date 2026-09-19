param([Parameter(Mandatory=$true)][string]$RunDirectory, [object]$Manifest)
$ErrorActionPreference='Stop'
if (!$Manifest) {$Manifest=Get-Content -Raw -Encoding UTF8 (Join-Path $RunDirectory 'experiment.json') | ConvertFrom-Json}
if ($Manifest.status -ne 'PASSED' -or $Manifest.cleanup_errors.Count -or $Manifest.evidence_errors.Count) {throw 'Experiment/cleanup/evidence did not pass'}
function Assert-Trace($Condition,[string]$Message) {if (!$Condition){throw "Trace verification failed: $Message"}}
$spawnStep=@($Manifest.steps | Where-Object {$_.command -like 'jev spawn-near *'})
Assert-Trace ($spawnStep.Count -eq 1) 'Expected exactly one nearby spawn'
$spawn=(($spawnStep[0].receipt.output -join ' ') -replace '^JEV_OK Spawned JevBot ','') | ConvertFrom-Json
$summary=[ordered]@{result='PASS';experiment_id=$Manifest.id;world=$spawn.world;spawn=$spawn.spawn_position;checks=@()}
foreach($command in @('jev smoke','jev step TURN_LEFT')) {
    $step=@($Manifest.steps | Where-Object command -eq $command)
    Assert-Trace ($step.Count -eq 1) "Expected exactly one $command step"
    $message=$step[0].receipt.output -join ' '
    $pathMatch=[regex]::Match($message,'trace=\S*[/\\]([0-9a-f-]{36}\.jsonl)')
    $hashMatch=[regex]::Match($message,'sha256=([0-9a-f]{64})')
    Assert-Trace ($pathMatch.Success -and $hashMatch.Success) 'Receipt lacks trace/hash binding'
    $events=@(Get-Content -Encoding UTF8 (Join-Path $RunDirectory $pathMatch.Groups[1].Value) | ForEach-Object {$_ | ConvertFrom-Json})
    foreach($kind in @('run_started','input','result','terminal')) {Assert-Trace (@($events | Where-Object event -eq $kind).Count -eq 1) "Expected one $kind event"}
    Assert-Trace (@($events | Where-Object event -eq decision).Count -eq 0) 'Manual smoke must not invoke Jev'
    $meta=($events | Where-Object event -eq run_started).data
    $inputEvent=($events | Where-Object event -eq input).data
    $result=($events | Where-Object event -eq result).data
    $terminal=($events | Where-Object event -eq terminal).data
    Assert-Trace ($meta.artifact_sha256 -eq $hashMatch.Groups[1].Value) 'Trace JAR hash differs from receipt'
    Assert-Trace ($result.actual_ticks -eq $inputEvent.duration_ticks) 'Input duration mismatch'
    Assert-Trace ($terminal.final.health -gt 0) 'Bot not alive at completion'
    for($i=0;$i -lt 3;$i++) {
        Assert-Trace ([Math]::Abs($result.after.position[$i]-$inputEvent.before.position[$i]-$result.displacement[$i]) -lt 0.000001) 'Displacement differs from game positions'
    }
    if ($command -eq 'jev smoke') {
        Assert-Trace ($meta.policy -eq 'SMOKE_NO_MODEL' -and $terminal.status -eq 'SMOKE_PASSED' -and $result.action -eq 'FORWARD' -and $result.actual_ticks -eq 8) 'Wrong smoke execution'
        for($i=0;$i -lt 3;$i++) {Assert-Trace ([Math]::Abs($inputEvent.before.position[$i]-$spawn.spawn_position[$i]) -lt 0.05) 'Bot relocated before smoke'}
        $forward=$terminal.final.position[2]-$inputEvent.before.position[2]
        Assert-Trace ($forward -gt 0.05 -and $forward -lt 4) 'No bounded forward displacement'
        Assert-Trace ([Math]::Abs($terminal.final.position[0]-$spawn.spawn_position[0]) -lt 0.05 -and [Math]::Abs($terminal.final.position[1]-$spawn.spawn_position[1]) -lt 0.05) 'Unexpected lateral/vertical motion'
        Assert-Trace ([Math]::Abs($terminal.final.velocity[0])+[Math]::Abs($terminal.final.velocity[2]) -lt 0.001) 'Horizontal motion did not stop'
        $summary.forward_after_settling=$forward
    } else {
        Assert-Trace ($meta.policy -eq 'MANUAL_NO_MODEL' -and $terminal.status -eq 'MANUAL_COMPLETED' -and $result.action -eq 'TURN_LEFT') 'Wrong turn execution'
        Assert-Trace ([Math]::Abs($terminal.final.yaw-$inputEvent.before.yaw+15) -lt 0.001) 'Wrong yaw change'
    }
    $summary.checks+=@{action=$result.action;ticks=$result.actual_ticks;displacement=$result.displacement;final_velocity=$terminal.final.velocity;health=$terminal.final.health;trace=$pathMatch.Groups[1].Value;sha256=$meta.artifact_sha256}
}
$json=$summary | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path (Resolve-Path $RunDirectory).Path 'verification.json'),$json,[Text.UTF8Encoding]::new($false))
$json
