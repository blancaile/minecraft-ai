param(
    [Parameter(Mandatory=$true)][string]$KeyFile,
    [string]$Player = 'Philia_Gray',
    [switch]$Execute
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$remote=Join-Path $PSScriptRoot 'remote.ps1'
$budget=@{maxDecisions=20;maxRunSeconds=120;timeoutSeconds=10;maxObservationAgeTicks=200}
if (!$Execute) {
    @{mode='PLAN';player=$Player;goal_offset=@(0,0,3);budget=$budget;model='jev-1.13.0';cleanup='stop/despawn; restore original config; collect evidence'} | ConvertTo-Json -Depth 5
    return
}
if ($Player -notmatch '^[A-Za-z0-9_]{1,16}$') {throw 'Invalid player name'}
$runId='live-'+[guid]::NewGuid().ToString()
$directory=Join-Path $repo ".runtime-harness/remote-$runId"
[IO.Directory]::CreateDirectory($directory) | Out-Null
$manifest=[ordered]@{id=$runId;status='RUNNING';player=$Player;goal_offset=@(0,0,3);budget=$budget;model='jev-1.13.0';cleanup_errors=@();receipts=@()}
$session=$null; $original=$null; $configured=$false; $ownsBot=$false; $failure=$null
function Invoke-Jev([string]$Value) {
    $receipt=(& $remote -Action Command -Command $Value -RunId $runId | Out-String) | ConvertFrom-Json
    $manifest.receipts+=@{command=$Value;receipt=$receipt}
    return $receipt
}
function Write-Config([string]$Value) {
    # SFTP WriteAllText does not reliably truncate a longer existing file.
    $stream=$client.Create($configPath)
    try {
        $bytes=[Text.UTF8Encoding]::new($false).GetBytes($Value)
        $stream.Write($bytes,0,$bytes.Length)
    } finally {$stream.Dispose()}
}
try {
    $initial=Invoke-Jev 'jev status'
    if (($initial.output -join ' ') -notmatch 'bot=none') {throw 'Existing bot present; refusing takeover'}
    Invoke-Jev "jev site $Player" | Out-Null
    # Reuse exactly the README's loader; capture stdout privately, never print the key.
    $loader='import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from jev_client import load_jev_api_key; print(load_jev_api_key(Path(sys.argv[2])))'
    $key=& python -c $loader (Join-Path $repo 'tools/probes') $KeyFile
    if ($LASTEXITCODE -ne 0 -or !$key -or $key -is [array] -or $key -match '[\r\n]') {throw 'Cannot load Jev credential'}
    Import-Module Posh-SSH
    $port=if($env:MINECRAFT_SFTP_PORT){[int]$env:MINECRAFT_SFTP_PORT}else{22}
    $credential=[pscredential]::new($env:MINECRAFT_SFTP_USER,(ConvertTo-SecureString $env:MINECRAFT_SFTP_PASSWORD -AsPlainText -Force))
    $session=New-SFTPSession -ComputerName $env:MINECRAFT_SFTP_HOST -Port $port -Credential $credential -ErrorOnUntrusted
    $client=$session.Session
    $client.OperationTimeout=[TimeSpan]::FromSeconds(15)
    $serverRoot=if($env:MINECRAFT_SERVER_ROOT){$env:MINECRAFT_SERVER_ROOT.TrimEnd('/')}else{'/test_server'}
    if ($serverRoot -notmatch '^/[A-Za-z0-9_/-]+$' -or $serverRoot -match '\.\.' -or !$serverRoot.Trim('/')) {throw 'Invalid server root'}
    $configPath="$serverRoot/plugins/JevControl/jev-control.json"
    $original=$client.ReadAllText($configPath)
    $config=$original | ConvertFrom-Json
    $config.apiKey=$key
    $config.model='jev-1.13.0'
    foreach($field in $budget.Keys) {$config.$field=$budget[$field]}
    $configured=$true # Also restore if writing is interrupted.
    Write-Config ($config | ConvertTo-Json)
    $check=$client.ReadAllText($configPath) | ConvertFrom-Json
    if ($check.apiKey -cne $key) {throw 'Credential provisioning verification failed'}
    $key=$null; $check=$null; $config=$null
    $ownsBot=$true # A timeout has unknown outcome: always attempt scoped cleanup.
    $spawn=Invoke-Jev "jev spawn-near $Player"
    $site=($spawn.output[0] -replace '^JEV_OK Spawned JevBot ','') | ConvertFrom-Json
    $position=$site.spawn_position
    $goal=[string]::Format([Globalization.CultureInfo]::InvariantCulture,'jev goal {0} {1} {2} {3}',$position[0],$position[1],($position[2]+3),$site.world)
    $manifest.site=$site
    Invoke-Jev $goal | Out-Null
    Invoke-Jev 'jev observe' | Out-Null
    Invoke-Jev 'jev start' | Out-Null
    $deadline=[DateTime]::UtcNow.AddSeconds($budget.maxRunSeconds+15)
    do {
        Start-Sleep -Seconds 2
        $status=Invoke-Jev 'jev status'
        $state=$status.output -join ' '
        Write-Host ($state -replace ' trace=.*$','')
        if ($state -match 'state=(ERROR|DEAD_OR_DISCONNECTED|CANCELLED)') {throw $state}
    } until ($state -match 'state=(GOAL_REACHED|BUDGET_EXCEEDED)' -or [DateTime]::UtcNow -ge $deadline)
    $manifest.terminal=$state
    if ($state -notmatch 'state=GOAL_REACHED') {throw 'Simple live probe did not reach its goal within the declared budget'}
    Invoke-Jev 'jev observe' | Out-Null
    $manifest.status='GOAL_REACHED_PENDING_TRACE_VERIFICATION'
} catch {
    $failure=$_
    $manifest.status='FAILED'
    $manifest.failure=$_.Exception.Message
} finally {
    if ($ownsBot) {
        foreach($command in @('jev stop','jev despawn')) {
            try {Invoke-Jev $command | Out-Null} catch {$manifest.cleanup_errors+=@($_.Exception.Message)}
        }
    }
    if ($configured) {
        try {
            Write-Config $original
            if ($client.ReadAllText($configPath) -cne $original) {throw 'Restored config verification failed'}
            $manifest.config_restored=$true
        } catch {$manifest.cleanup_errors+=@('Config restoration failed; operator attention required')}
    }
    $key=$null; $original=$null; $config=$null; $check=$null
    if ($session) {Remove-SFTPSession -SessionId $session.SessionId | Out-Null}
    foreach($action in @('Log','Traces')) {
        try {& $remote -Action $action -RunId $runId | Out-Null} catch {$manifest.cleanup_errors+=@($_.Exception.Message)}
    }
    if ($manifest.cleanup_errors.Count) {$manifest.status='FAILED'}
    [IO.File]::WriteAllText((Join-Path $directory 'live-experiment.json'),($manifest | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    Write-Host "EVIDENCE_DIRECTORY=$directory STATUS=$($manifest.status)"
}
if ($failure) {throw $failure}
if ($manifest.status -eq 'FAILED') {throw 'Live experiment cleanup failed'}
python (Join-Path $PSScriptRoot 'paper_acceptance.py') --verify-shared $directory
if ($LASTEXITCODE -ne 0) {throw 'Live trace verification failed; preserve evidence and inspect it'}
