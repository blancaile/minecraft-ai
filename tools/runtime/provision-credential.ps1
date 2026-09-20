param(
    [Parameter(Mandatory=$true)][string]$KeyFile,
    [switch]$Execute
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$remote=Join-Path $PSScriptRoot 'remote.ps1'
if (!$Execute) {
    @{mode='PLAN';transport='RSA-3072 OAEP SHA256 / MGF1-SHA256 ciphertext only';persistent=$true;config_mode='600';private_key_mode='600';secret_directory_mode='700';boundary='Does not isolate from server owner/root or plugins in the same JVM'} | ConvertTo-Json
    return
}
$runId='credential-'+[guid]::NewGuid().ToString()
# The normal remote entrypoint loads only documented SFTP environment settings.
& $remote -Action Command -Command 'jev key-prepare' -RunId $runId | Out-Null
Import-Module Posh-SSH
$port=if($env:MINECRAFT_SFTP_PORT){[int]$env:MINECRAFT_SFTP_PORT}else{22}
$credential=[pscredential]::new($env:MINECRAFT_SFTP_USER,(ConvertTo-SecureString $env:MINECRAFT_SFTP_PASSWORD -AsPlainText -Force))
$session=New-SFTPSession -ComputerName $env:MINECRAFT_SFTP_HOST -Port $port -Credential $credential -ErrorOnUntrusted
$key=$null; $bytes=$null; $rsa=$null
try {
    $client=$session.Session
    $client.OperationTimeout=[TimeSpan]::FromSeconds(15)
    $serverRoot=if($env:MINECRAFT_SERVER_ROOT){$env:MINECRAFT_SERVER_ROOT.TrimEnd('/')}else{'/test_server'}
    if ($serverRoot -notmatch '^/[A-Za-z0-9_/-]+$' -or $serverRoot -match '\.\.' -or !$serverRoot.Trim('/')) {throw 'Invalid server root'}
    $data="$serverRoot/plugins/JevControl"
    $parent=$client.GetAttributes($data)
    $public=$client.GetAttributes("$data/credential-public.json")
    if ($parent.IsSymbolicLink -or !$parent.IsDirectory -or $parent.GroupCanWrite -or $parent.OthersCanWrite -or
        $public.IsSymbolicLink -or !$public.IsRegularFile -or $public.GroupCanWrite -or $public.OthersCanWrite -or
        $public.UserId -ne $parent.UserId) {throw 'Public-key ownership/protection is not verified; refusing to load API key'}
    $info=$client.ReadAllText("$data/credential-public.json") | ConvertFrom-Json
    if ($info.algorithm -ne 'RSA-OAEP-SHA256-MGF1-SHA256' -or $info.bits -ne 3072) {throw 'Unexpected public-key format'}
    $parameters=New-Object Security.Cryptography.RSAParameters
    $parameters.Modulus=[Convert]::FromBase64String($info.modulus)
    $parameters.Exponent=[Convert]::FromBase64String($info.exponent)
    if ($parameters.Modulus.Length -ne 384) {throw 'Unexpected RSA modulus size'}
    # RSACryptoServiceProvider cannot use SHA256 OAEP; explicitly choose CNG on Windows.
    $rsa=if($env:OS -eq 'Windows_NT'){[Security.Cryptography.RSACng]::new()}else{[Security.Cryptography.RSA]::Create()}
    $rsa.ImportParameters($parameters)
    $loader='import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from jev_client import load_jev_api_key; print(load_jev_api_key(Path(sys.argv[2])))'
    $key=& python -c $loader (Join-Path $repo 'tools/probes') $KeyFile
    if ($LASTEXITCODE -ne 0 -or !$key -or $key -is [array] -or $key -cnotmatch '^[!-~]{1,300}$') {throw 'Cannot load bounded API credential'}
    $bytes=[Text.Encoding]::ASCII.GetBytes($key)
    $sealed=[Convert]::ToBase64String($rsa.Encrypt($bytes,[Security.Cryptography.RSAEncryptionPadding]::OaepSHA256))
    $key=$null; [Array]::Clear($bytes,0,$bytes.Length); $bytes=$null
    & $remote -Action Command -Command ('jev key-install '+$sealed) -RunId $runId | Out-Null
    $receipt=(& $remote -Action Command -Command 'jev key-status' -RunId $runId | Out-String) | ConvertFrom-Json
    $status=($receipt.output[0] -replace '^JEV_OK ','') | ConvertFrom-Json
    if (!$status.configured -or $status.storage -ne 'SEALED_RSA_OAEP256' -or $status.config_mode -ne '600' -or $status.private_key_mode -ne '600' -or $status.private_directory_mode -ne '700') {throw 'Server-side credential protection verification failed'}
    $attributes=$client.GetAttributes("$data/jev-control.json")
    if ($attributes.UserId -ne $parent.UserId -or $attributes.GroupCanRead -or $attributes.OthersCanRead -or $attributes.GroupCanWrite -or $attributes.OthersCanWrite) {throw 'SFTP metadata disagrees with server config protection'}
    # Deliberately do not read config/private key contents. Proof includes a live server-side decryption.
    [pscustomobject]@{status='PERSISTENT_CREDENTIAL_CONFIGURED';run_id=$runId;server_status=$status;key_value_logged=$false;restart_required=$false} | ConvertTo-Json -Depth 5
} finally {
    $key=$null
    if ($bytes) {[Array]::Clear($bytes,0,$bytes.Length)}
    if ($rsa) {$rsa.Dispose()}
    Remove-SFTPSession -SessionId $session.SessionId | Out-Null
}
