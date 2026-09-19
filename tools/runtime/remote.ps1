param(
    [Parameter(Mandatory=$true)][ValidateSet('Preflight','Deploy','Command','Reload','Log','Traces')][string]$Action,
    [string]$Artifact = 'build/libs/jev-control-paper-0.2.0.jar',
    [string]$Command,
    [ValidateSet('Jev','LastOrder')][string]$Transport = 'Jev',
    [ValidateRange(1,50)][int]$TimeoutSeconds = 30,
    [string]$RunId = ([guid]::NewGuid().ToString()),
    [switch]$Plan
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
# Literal KEY=value reader: never evaluate shell code from configuration.
$envFile = Join-Path $repo 'deploy.local.env'
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        if ($line -match '^\s*(#|$)') { continue }
        if ($line -notmatch '^([A-Z_]+)=(.*)$') { throw 'Invalid deploy.local.env entry' }
        $key=$Matches[1]; $value=$Matches[2].Trim()
        if (![Environment]::GetEnvironmentVariable($key)) { [Environment]::SetEnvironmentVariable($key,$value) }
    }
}
$remoteRoot = $env:MINECRAFT_SERVER_ROOT
if (!$remoteRoot) { $remoteRoot = '/test_server' }
if ($remoteRoot -notmatch '^/[A-Za-z0-9_/-]+$' -or $remoteRoot -match '\.\.' -or $remoteRoot.Trim('/') -eq '') { throw 'Invalid remote server root' }
$remoteRoot = $remoteRoot.TrimEnd('/')
$plugins = "$remoteRoot/plugins"
$data = "$plugins/JevControl"
$target = "$plugins/jev-control-paper.jar"
$safeId = $RunId -replace '[^a-zA-Z0-9_-]','_'
$output = Join-Path $repo ".runtime-harness/remote-$safeId"
if ($Action -eq 'Reload') { $Transport='LastOrder'; $Command='bukkit:reload confirm' }
if ($Action -in @('Command','Reload') -and (!$Command -or $Command.Contains("`n") -or $Command.Contains("`r") -or $Command.Length -gt 256)) { throw 'Expected one bounded console command' }
if ($Action -eq 'Deploy') {
    if (![IO.Path]::IsPathRooted($Artifact)) { $Artifact=Join-Path $repo $Artifact }
    $Artifact=(Resolve-Path -LiteralPath $Artifact).Path
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $jar=[IO.Compression.ZipFile]::OpenRead($Artifact)
    try {
        $entry=$jar.GetEntry('plugin.yml')
        if (!$entry -or $jar.GetEntry('fabric.mod.json')) { throw 'Only a Paper plugin can be deployed here' }
        $reader=[IO.StreamReader]::new($entry.Open())
        try { if ($reader.ReadToEnd() -notmatch '(?m)^name: JevControl\s*$') { throw 'Artifact is not JevControl' } } finally {$reader.Dispose()}
    } finally {$jar.Dispose()}
}
if ($Plan) {
    [pscustomobject]@{action=$Action;artifact=$Artifact;target=$target;transport=$Transport;command=$Command;output=$output} | ConvertTo-Json
    return
}
foreach ($key in @('MINECRAFT_SFTP_HOST','MINECRAFT_SFTP_USER','MINECRAFT_SFTP_PASSWORD')) {
    if (![Environment]::GetEnvironmentVariable($key)) { throw "Missing environment variable: $key" }
}
Import-Module Posh-SSH -ErrorAction Stop
[IO.Directory]::CreateDirectory($output) | Out-Null
$port=if($env:MINECRAFT_SFTP_PORT){[int]$env:MINECRAFT_SFTP_PORT}else{22}
$credential=[pscredential]::new($env:MINECRAFT_SFTP_USER,(ConvertTo-SecureString $env:MINECRAFT_SFTP_PASSWORD -AsPlainText -Force))
# Host must already be trusted through a separately verified interactive connection.
$session=New-SFTPSession -ComputerName $env:MINECRAFT_SFTP_HOST -Port $port -Credential $credential -ErrorOnUntrusted
$client=$session.Session
$client.OperationTimeout=[TimeSpan]::FromSeconds(15)
function Upload-Bytes([byte[]]$Bytes,[string]$Path) {
    $stream=[IO.MemoryStream]::new($Bytes,$false)
    try {$client.UploadFile($stream,$Path,$false)} finally {$stream.Dispose()}
}
function Fetch-Bytes([string]$Path) {
    $stream=[IO.MemoryStream]::new()
    try {$client.DownloadFile($Path,$stream);return ,$stream.ToArray()} finally {$stream.Dispose()}
}
function Hash-Bytes([byte[]]$Bytes) {
    $hash=[Security.Cryptography.SHA256]::Create()
    try {return ([BitConverter]::ToString($hash.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}finally{$hash.Dispose()}
}
function Queue-LastOrder([string]$Value) {
    $id=[guid]::NewGuid().ToString('N')
    $stage="$plugins/.jev-$id.upload"
    Upload-Bytes ([Text.Encoding]::UTF8.GetBytes($Value)) $stage
    $client.RenameFile($stage,"$plugins/lastorder-command-$id.txt")
    return $id
}
try {
    switch ($Action) {
        'Preflight' {
            $list=@($client.ListDirectory($plugins) | Where-Object {$_.Name -notin @('.','..')})
            $result=[ordered]@{action=$Action;plugins_directory=$plugins;jev_artifacts=@($list | Where-Object {$_.Name -like '*jev*.jar'} | ForEach-Object {$_.Name});lastorder_present=(@($list | Where-Object {$_.Name -like 'last-order*.jar'}).Count -gt 0)}
        }
        'Deploy' {
            $bytes=[IO.File]::ReadAllBytes($Artifact)
            $sha=Hash-Bytes $bytes
            $other=@($client.ListDirectory($plugins) | Where-Object {$_.Name -like '*jev*.jar' -and $_.Name -ne 'jev-control-paper.jar'})
            if ($other.Count) {throw 'Other Jev JAR names exist; resolve duplicate plugins before deployment'}
            $backup=$null
            if ($client.Exists($target)) {
                $backup=Join-Path $output 'previous-jev-control-paper.jar'
                [IO.File]::WriteAllBytes($backup,(Fetch-Bytes $target))
            }
            $stage="$plugins/.jev-$safeId.upload"
            Upload-Bytes $bytes $stage
            if ((Hash-Bytes (Fetch-Bytes $stage)) -ne $sha) {throw 'Staged remote SHA-256 mismatch'}
            if ($client.Exists($target)) {$client.DeleteFile($target)}
            try {$client.RenameFile($stage,$target)} catch {
                if ($backup -and !$client.Exists($target)) {Upload-Bytes ([IO.File]::ReadAllBytes($backup)) $target}
                throw
            }
            if ((Hash-Bytes (Fetch-Bytes $target)) -ne $sha) {throw 'Final remote SHA-256 mismatch'}
            $result=[ordered]@{action=$Action;target=$target;sha256=$sha;verified=$true;backup=$backup;activated=$false}
        }
        'Reload' {
            $marker="JEV_ACTIVATE_$safeId"
            Queue-LastOrder "say $marker" | Out-Null
            $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
            do {
                Start-Sleep -Milliseconds 500
                $log=[Text.Encoding]::UTF8.GetString((Fetch-Bytes "$remoteRoot/logs/latest.log"))
            } until ($log.Contains($marker) -or [DateTime]::UtcNow -ge $deadline)
            if (!$log.Contains($marker)) {throw 'Activation marker not observed; reload was not queued'}
            if (!$client.Exists($target)) {throw 'No deployed Jev JAR'}
            $sha=Hash-Bytes (Fetch-Bytes $target)
            Queue-LastOrder $Command | Out-Null
            $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
            do {
                Start-Sleep -Milliseconds 500
                $raw=Fetch-Bytes "$remoteRoot/logs/latest.log"
                $log=[Text.Encoding]::UTF8.GetString($raw)
                $index=$log.LastIndexOf($marker)
                $fresh=if($index -ge 0){$log.Substring($index)}else{''}
                $ready=$fresh -match ('JEV_READY[^\r\n]*sha256='+$sha)
            } until ($ready -or [DateTime]::UtcNow -ge $deadline)
            [IO.File]::WriteAllBytes((Join-Path $output 'activation.raw.log'),$raw)
            if (!$ready) {throw 'No fresh JEV_READY with deployed SHA-256; do not repeat reload blindly'}
            $result=[ordered]@{action=$Action;sha256=$sha;activated=$true;marker=$marker}
        }
        'Command' {
            if ($Transport -eq 'LastOrder') {
                $id=Queue-LastOrder $Command
                $result=[ordered]@{id=$id;status='QUEUED_NOT_VERIFIED';transport=$Transport}
            } else {
                if ($Command -notmatch '^jev (spawn|despawn|status|observe|goal|smoke|step|start|stop)( |$)') {throw 'Jev inbox accepts jev commands only; use LastOrder for its allowed console commands'}
                $id=[guid]::NewGuid().ToString()
                $request=@{id=$id;command=$Command;expires_at_ms=[DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds).ToUnixTimeMilliseconds()} | ConvertTo-Json -Compress
                $stage="$data/inbox/.$id.upload"
                Upload-Bytes ([Text.Encoding]::UTF8.GetBytes($request)) $stage
                $client.RenameFile($stage,"$data/inbox/$id.json")
                $receipt="$data/receipts/$id.json"
                $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds+2)
                while (!$client.Exists($receipt) -and [DateTime]::UtcNow -lt $deadline) {Start-Sleep -Milliseconds 250}
                if (!$client.Exists($receipt)) {throw "No receipt for $id. Outcome UNKNOWN; no automatic retry."}
                $raw=Fetch-Bytes $receipt
                [IO.File]::WriteAllBytes((Join-Path $output "$id.receipt.json"),$raw)
                $result=[Text.Encoding]::UTF8.GetString($raw) | ConvertFrom-Json
                if ($result.id -ne $id) {throw 'Receipt request ID mismatch'}
                if (!$result.success) {throw ('Command rejected: '+($result.output -join '; '))}
            }
        }
        'Log' {
            $raw=Fetch-Bytes "$remoteRoot/logs/latest.log"
            $path=Join-Path $output 'latest.raw.log'
            [IO.File]::WriteAllBytes($path,$raw)
            $result=[ordered]@{path=$path;sha256=(Hash-Bytes $raw);jev_lines=@([Text.Encoding]::UTF8.GetString($raw) -split "`n" | Where-Object {$_ -match 'JEV_|\[JevControl\]'} | Select-Object -Last 30)}
        }
        'Traces' {
            $files=@($client.ListDirectory("$data/traces") | Where-Object {$_.Name -match '^[a-zA-Z0-9-]+\.jsonl$' -and !$_.IsSymbolicLink})
            foreach ($file in $files) {[IO.File]::WriteAllBytes((Join-Path $output $file.Name),(Fetch-Bytes $file.FullName))}
            $result=[ordered]@{directory=$output;trace_count=$files.Count}
        }
    }
    $json=$result | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText((Join-Path $output "$Action.json"),$json,[Text.UTF8Encoding]::new($false))
    $json
} finally {Remove-SFTPSession -SessionId $session.SessionId | Out-Null}
