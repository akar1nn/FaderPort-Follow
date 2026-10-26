Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-FollowLibrary {
    param([string]$UserLibrary)
    if ($UserLibrary) {
        if (-not (Test-Path -LiteralPath $UserLibrary -PathType Container)) {
            throw "User Library directory does not exist: $UserLibrary"
        }
        return (Resolve-Path -LiteralPath $UserLibrary).ProviderPath
    }
    $abletonSettings = Join-Path $env:APPDATA 'Ableton'
    if (Test-Path -LiteralPath $abletonSettings) {
        $versions = Get-ChildItem -LiteralPath $abletonSettings -Directory |
            Where-Object { $_.Name -match '^Live 12\.\d+\.\d+$' } |
            Sort-Object { [version]($_.Name -replace '^Live ', '') } -Descending
        foreach ($version in $versions) {
            $config = Join-Path $version.FullName 'Preferences\Library.cfg'
            if (Test-Path -LiteralPath $config -PathType Leaf) {
                [xml]$document = Get-Content -LiteralPath $config -Raw
                $node = $document.SelectSingleNode('/Ableton/ContentLibrary/UserLibrary/LibraryProject/ProjectPath')
                if ($null -ne $node) {
                    $libraryPath = $node.GetAttribute('Value')
                    $nameNode = $document.SelectSingleNode('/Ableton/ContentLibrary/UserLibrary/LibraryProject/ProjectName')
                    if ($null -ne $nameNode -and $nameNode.GetAttribute('Value')) {
                        # Library.cfg stores the parent and the folder name separately.
                        $libraryPath = Join-Path $libraryPath $nameNode.GetAttribute('Value')
                    }
                    if ($libraryPath -and (Test-Path -LiteralPath $libraryPath -PathType Container)) {
                        return (Resolve-Path -LiteralPath $libraryPath).ProviderPath
                    }
                }
            }
        }
    }
    throw 'Cannot detect Live 12 User Library. Pass -UserLibrary with the path shown in Live Preferences > Library.'
}

function Get-FollowPaths {
    param([string]$UserLibrary)
    $library = Get-FollowLibrary -UserLibrary $UserLibrary
    $remote = Join-Path $library 'Remote Scripts'
    $target = Join-Path $remote 'FaderPort_Follow'
    $backups = Join-Path $library '.FaderPort_Follow_Backups'
    foreach ($directory in @($remote, $target, $backups)) {
        if (Test-Path -LiteralPath $directory) {
            $item = Get-Item -LiteralPath $directory -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing to change a junction or symbolic link: $directory"
            }
            if (-not $item.PSIsContainer) { throw "Expected a directory: $directory" }
        }
    }
    # These fixed names are the only directories this module ever moves.
    return @{ Library = $library; Remote = $remote; Target = $target; Backups = $backups }
}

function New-FollowBackupPath {
    param([hashtable]$Paths, [string]$Label)
    New-Item -ItemType Directory -Path $Paths.Backups -Force | Out-Null
    $name = '{0}-{1}-{2}' -f $Label, (Get-Date -Format 'yyyyMMdd-HHmmssfff'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
    return (Join-Path $Paths.Backups $name)
}

Export-ModuleMember -Function Get-FollowLibrary, Get-FollowPaths, New-FollowBackupPath

