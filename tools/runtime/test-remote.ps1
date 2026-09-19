param([string]$Artifact = 'build/libs/jev-control-paper-0.2.0.jar')
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (![IO.Path]::IsPathRooted($Artifact)) {$Artifact=Join-Path $repo $Artifact}
$remote=Join-Path $PSScriptRoot 'remote.ps1'
# No network, no production credentials: replace the transport with an in-memory SFTP peer.
if (!('JevTestSftp' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
public class JevTestEntry { public string Name; public string FullName; public bool IsSymbolicLink; }
public class JevTestSftp {
    public Dictionary<string, byte[]> Files = new Dictionary<string, byte[]>();
    public TimeSpan OperationTimeout {get;set;}
    public bool CorruptStage;
    public bool FailRename;
    public bool Exists(string path) { return Files.ContainsKey(path); }
    public void UploadFile(Stream stream, string path, bool overwrite) {
        if (!overwrite && Exists(path)) throw new IOException("Already exists");
        using (var output = new MemoryStream()) { stream.CopyTo(output); Files[path]=output.ToArray(); }
    }
    public void DownloadFile(string path, Stream output) {
        var bytes=Files[path];
        if (CorruptStage && path.EndsWith(".upload")) bytes=new byte[]{0};
        output.Write(bytes,0,bytes.Length);
    }
    public void DeleteFile(string path) { if (!Files.Remove(path)) throw new IOException("Missing file"); }
    public void RenameFile(string from, string to) {
        if (FailRename) throw new IOException("Injected rename failure");
        if (Exists(to)) throw new IOException("Already exists");
        Files[to]=Files[from]; Files.Remove(from);
    }
    public JevTestEntry[] ListDirectory(string path) {
        return Files.Keys.Where(k => k.StartsWith(path+"/") && !k.Substring(path.Length+1).Contains("/"))
            .Select(k => new JevTestEntry {Name=k.Substring(path.Length+1),FullName=k}).ToArray();
    }
}
'@
}
function Import-Module { param($Name,$ErrorAction) if ($Name -ne 'Posh-SSH') {throw 'Unexpected module'} }
function New-SFTPSession { param($ComputerName,$Port,$Credential,[switch]$ErrorOnUntrusted) return [pscustomobject]@{Session=$fake;SessionId=42} }
function Remove-SFTPSession { param($SessionId) if ($SessionId -ne 42) {throw 'Unexpected session'} }
function Assert($Condition,[string]$Message) {if (!$Condition) {throw $Message}}
function Expect-Failure([scriptblock]$Operation,[string]$Pattern) {
    $caught=$null
    try {& $Operation | Out-Null} catch {$caught=$_.Exception.Message}
    Assert ($caught -and $caught -match $Pattern) "Expected failure matching: $Pattern; got: $caught"
}
$saved=@{}
$testEnvironment=@{MINECRAFT_SERVER_ROOT='/test_server';MINECRAFT_SFTP_HOST='invalid.test';MINECRAFT_SFTP_USER='offline-test';MINECRAFT_SFTP_PASSWORD='offline-test';MINECRAFT_SFTP_PORT='22'}
foreach($key in $testEnvironment.Keys) {$saved[$key]=[Environment]::GetEnvironmentVariable($key);[Environment]::SetEnvironmentVariable($key,$testEnvironment[$key])}
$target='/test_server/plugins/jev-control-paper.jar'
$old=[Text.Encoding]::UTF8.GetBytes('old artifact')
$run='offline-'+[guid]::NewGuid().ToString('N')
try {
    $script:fake=New-Object JevTestSftp
    $fake.Files[$target]=$old
    $result=(& $remote -Action Deploy -Artifact $Artifact -RunId "$run-ok" | Out-String) | ConvertFrom-Json
    Assert ($result.verified -and !$result.activated) 'Deploy must verify but not claim activation'
    Assert ($result.sha256 -eq (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()) 'Wrong artifact hash'
    Assert ([Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($result.backup)) -eq 'old artifact') 'Old artifact not backed up'
    Assert ([Convert]::ToBase64String($fake.Files[$target]) -eq [Convert]::ToBase64String([IO.File]::ReadAllBytes($Artifact))) 'Wrong deployed bytes'

    $script:fake=New-Object JevTestSftp
    $fake.Files[$target]=$old
    $fake.Files['/test_server/plugins/jev-other.jar']=$old
    Expect-Failure {& $remote -Action Deploy -Artifact $Artifact -RunId "$run-duplicate"} 'duplicate'
    Assert ($fake.Files.Count -eq 2) 'Duplicate rejection mutated remote files'

    $script:fake=New-Object JevTestSftp
    $fake.Files[$target]=$old
    $fake.CorruptStage=$true
    Expect-Failure {& $remote -Action Deploy -Artifact $Artifact -RunId "$run-corrupt"} 'Staged remote SHA-256 mismatch'
    Assert ([Text.Encoding]::UTF8.GetString($fake.Files[$target]) -eq 'old artifact') 'Corrupt staging replaced old artifact'

    $script:fake=New-Object JevTestSftp
    $fake.Files[$target]=$old
    $fake.FailRename=$true
    Expect-Failure {& $remote -Action Deploy -Artifact $Artifact -RunId "$run-rollback"} 'rename failure'
    Assert ([Text.Encoding]::UTF8.GetString($fake.Files[$target]) -eq 'old artifact') 'Rename failure did not restore previous artifact'

    $script:fake=New-Object JevTestSftp
    Expect-Failure {& $remote -Action Command -Command 'stop' -RunId "$run-denied"} 'Jev inbox accepts'
    Assert ($fake.Files.Count -eq 0) 'Rejected command wrote a file'
    $result=(& $remote -Action Command -Transport LastOrder -Command 'say offline-test' -RunId "$run-queued" | Out-String) | ConvertFrom-Json
    Assert ($result.status -eq 'QUEUED_NOT_VERIFIED') 'Queue insertion claimed command execution'
    Assert (@($fake.Files.Keys | Where-Object {$_ -match '/lastorder-command-[a-f0-9]+\.txt$'}).Count -eq 1) 'No complete LastOrder command file'
    $script:fake=New-Object JevTestSftp
    Expect-Failure {& $remote -Action Traces -RunId "$run-no-plugin"} 'data directory does not exist'
    $fake.Files['/test_server/plugins/JevControl']=@()
    $result=(& $remote -Action Traces -RunId "$run-no-traces" | Out-String) | ConvertFrom-Json
    Assert ($result.trace_count -eq 0 -and !$result.remote_trace_directory_exists) 'Unused plugin should return zero traces'
    Assert ($fake.Files.Count -eq 1) 'Empty trace collection mutated remote files'
    'PASS: 7 offline transport checks (replace, duplicate, hash mismatch, rollback, rejected command, queue receipt, absent traces)'
} finally {
    foreach($key in $saved.Keys) {[Environment]::SetEnvironmentVariable($key,$saved[$key])}
}
