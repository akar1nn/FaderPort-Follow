[CmdletBinding()]
param([string]$UserLibrary, [switch]$RestorePrevious)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'tools\Installation.psm1') -Force
$paths = Get-FollowPaths -UserLibrary $UserLibrary
if (-not (Test-Path -LiteralPath $paths.Target)) {
    Write-Output 'FaderPort Follow is not installed in this User Library.'
    return
}
$marker = Join-Path $paths.Target '.faderport-follow-install.json'
if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
    throw 'No installer marker found. Move the manually installed FaderPort_Follow folder out of Remote Scripts yourself.'
}
$metadata = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
if ($metadata.package -ne 'FaderPort_Follow') { throw 'Unexpected installation marker.' }
$restorePath = $null
if ($RestorePrevious) {
    if (-not $metadata.previousBackup) { throw 'This installation has no previous backup to restore.' }
    $restorePath = [IO.Path]::GetFullPath($metadata.previousBackup)
    $backupRoot = [IO.Path]::GetFullPath($paths.Backups).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $restorePath.StartsWith($backupRoot, [StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-Path -LiteralPath $restorePath -PathType Container)) {
        throw 'Previous backup is missing or is outside this User Library backup directory.'
    }
    if ((Get-Item -LiteralPath $restorePath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Refusing to restore a symbolic link or junction.'
    }
}
$removed = New-FollowBackupPath -Paths $paths -Label 'removed'
Move-Item -LiteralPath $paths.Target -Destination $removed
if ($restorePath) {
    Move-Item -LiteralPath $restorePath -Destination $paths.Target
    Write-Output ('Restored: ' + $paths.Target)
} else {
    Write-Output 'Uninstalled FaderPort Follow. Select None in its Live Control Surface row.'
}
Write-Output ('Removed copy preserved: ' + $removed)

