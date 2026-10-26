[CmdletBinding()]
param([string]$UserLibrary, [switch]$DebugMidi)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'tools\Installation.psm1') -Force

$paths = Get-FollowPaths -UserLibrary $UserLibrary
$source = Join-Path $PSScriptRoot 'FaderPort_Follow'
if (-not (Test-Path -LiteralPath (Join-Path $source '__init__.py') -PathType Leaf)) {
    throw 'Missing source package. Extract the entire ZIP before running Install.ps1.'
}
$sourceFiles = @(Get-ChildItem -LiteralPath $source -Filter '*.py' -File)
if ($sourceFiles.Count -lt 6) { throw 'Incomplete source package.' }

New-Item -ItemType Directory -Path $paths.Remote -Force | Out-Null
$staging = Join-Path $paths.Remote ('_FaderPort_Follow_staging_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null
foreach ($file in $sourceFiles) {
    Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $staging $file.Name)
}
if ($DebugMidi) {
    $settingsFile = Join-Path $staging 'settings.py'
    $settingsText = [IO.File]::ReadAllText($settingsFile)
    $settingsText = $settingsText.Replace('DEBUG_MIDI = False', 'DEBUG_MIDI = True')
    [IO.File]::WriteAllText($settingsFile, $settingsText, (New-Object Text.UTF8Encoding($false)))
}
$previous = $null
if (Test-Path -LiteralPath $paths.Target) {
    $previous = New-FollowBackupPath -Paths $paths -Label 'previous'
}
$metadata = @{
    package = 'FaderPort_Follow'
    installedUtc = [DateTime]::UtcNow.ToString('o')
    source = $source
    previousBackup = $previous
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $staging '.faderport-follow-install.json') -Encoding UTF8
if ($previous) {
    Move-Item -LiteralPath $paths.Target -Destination $previous
}
try {
    Move-Item -LiteralPath $staging -Destination $paths.Target
} catch {
    if ($previous -and -not (Test-Path -LiteralPath $paths.Target)) {
        Move-Item -LiteralPath $previous -Destination $paths.Target
    }
    throw
}
Write-Output ('Installed: ' + $paths.Target)
if ($previous) { Write-Output ('Previous version saved: ' + $previous) }
Write-Output 'Restart Live, select FaderPort Follow and set its FaderPort MIDI input and output.'

