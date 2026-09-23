[CmdletBinding()]
param(
    [string] $DataRoot = $env:ROSLYN_GRAPH_DATA_ROOT,
    [Parameter(Mandatory)] [string] $AssemblyPath,
    [Parameter(Mandatory)] [ValidateSet('source', 'nuget')] [string] $OriginKind,
    [Parameter(Mandatory)] [string] $OriginId,
    [Parameter(Mandatory)] [string] $BuildFingerprint,
    [Parameter(Mandatory)] [string] $TargetFramework,
    [Parameter(Mandatory)] [string] $Roslyn2RdfDll,
    [string] $ProjectPath,
    [string] $Branch,
    [string] $Commit,
    [string] $Configuration,
    [string] $Platform,
    [string] $PackageVersion,
    [string] $PackageHash,
    [string] $PackageFeed,
    [string[]] $SearchDirectory = @(),
    [string] $OxigraphCommand = 'oxigraph'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function ConvertTo-PathSegment([string] $Value) {
    return [regex]::Replace($Value, '[<>:"/\\|?*]', '_')
}

function Get-Sha256([string] $Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Get-Sha256Text([string] $Value) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') })
    }
    finally {
        $sha.Dispose()
    }
}

function Resolve-ArtifactDestination([string] $BasePath, [string] $ArtifactId) {
    foreach ($length in @(20, 32, 64)) {
        $candidate = Join-Path $BasePath $ArtifactId.Substring(0, $length)
        if (-not (Test-Path -LiteralPath $candidate)) { return $candidate }
        $existingManifestPath = Join-Path $candidate 'manifest.json'
        if (-not (Test-Path -LiteralPath $existingManifestPath -PathType Leaf)) {
            throw "Artifact directory exists without a manifest: $candidate"
        }
        $existingManifest = Get-Content -LiteralPath $existingManifestPath -Raw | ConvertFrom-Json
        if ($existingManifest.artifactId -eq $ArtifactId) { return $candidate }
    }
    throw "Artifact ID prefix collision could not be disambiguated: $ArtifactId"
}

$resolvedAssemblyPath = [IO.Path]::GetFullPath($AssemblyPath)
if (-not (Test-Path -LiteralPath $resolvedAssemblyPath -PathType Leaf)) {
    throw "Assembly does not exist: $resolvedAssemblyPath"
}

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw 'DataRoot was not supplied and ROSLYN_GRAPH_DATA_ROOT is not set.'
}

$resolvedDataRoot = [IO.Path]::GetFullPath($DataRoot)
$artifactRoot = Join-Path $resolvedDataRoot '.roslyn-graph'
$assemblyIdentity = [Reflection.AssemblyName]::GetAssemblyName($resolvedAssemblyPath)
$assemblyName = $assemblyIdentity.Name
$assemblyVersion = $assemblyIdentity.Version.ToString()
$assemblyToken = if ($assemblyIdentity.GetPublicKeyToken().Length -gt 0) {
    -join ($assemblyIdentity.GetPublicKeyToken() | ForEach-Object { $_.ToString('x2') })
} else {
    'unsigned'
}
$artifactIdentity = "$OriginKind|$OriginId|$BuildFingerprint|$assemblyName|$assemblyVersion|$assemblyToken|$TargetFramework"
$artifactId = Get-Sha256Text $artifactIdentity
$graphIri = "urn:roslyn-graph:assembly:$($artifactId.Substring(0, 32))"

if ($OriginKind -eq 'source') {
    foreach ($required in @($Branch, $Commit)) {
        if ([string]::IsNullOrWhiteSpace($required)) { throw 'Source artifacts require Branch and Commit.' }
    }
    $destinationBase = Join-Path $artifactRoot (Join-Path 'assemblies' (Join-Path 'source' (ConvertTo-PathSegment $OriginId)))
} else {
    foreach ($required in @($PackageVersion, $PackageHash)) {
        if ([string]::IsNullOrWhiteSpace($required)) { throw 'NuGet artifacts require PackageVersion and PackageHash.' }
    }
    $destinationBase = Join-Path $artifactRoot (Join-Path 'assemblies' (Join-Path 'nuget' (Join-Path (ConvertTo-PathSegment $OriginId) (ConvertTo-PathSegment $PackageVersion))))
}
$destination = Resolve-ArtifactDestination $destinationBase $artifactId
$publishedCurrentPath = Join-Path (Join-Path $destination 'store.oxigraph') 'CURRENT'
if ($publishedCurrentPath.Length -gt 240) { throw "Published Oxigraph path is too long ($($publishedCurrentPath.Length)): $publishedCurrentPath" }

if (Test-Path -LiteralPath $destination) {
    $manifestPath = Join-Path $destination 'manifest.json'
    if (Test-Path -LiteralPath $manifestPath) {
        Get-Content -LiteralPath $manifestPath -Raw
        return
    }
    throw "Artifact destination already exists without a manifest: $destination"
}

$stagingRoot = Join-Path (Join-Path $artifactRoot 'staging') ([Guid]::NewGuid().ToString('N'))
$stagingArtifact = Join-Path $stagingRoot 'artifact'
$ttlPath = Join-Path $stagingArtifact 'graph.ttl'
$storePath = Join-Path $stagingArtifact 'store.oxigraph'
$manifestPath = Join-Path $stagingArtifact 'manifest.json'
New-Item -ItemType Directory -Path $stagingArtifact -Force | Out-Null

try {
    $toolArguments = @($Roslyn2RdfDll, $resolvedAssemblyPath, '--output', $ttlPath, '--format', 'Turtle', '--include-private', '--quiet')
    foreach ($directory in $SearchDirectory) {
        $toolArguments += '--search-dir'
        $toolArguments += [IO.Path]::GetFullPath($directory)
    }
    & dotnet @toolArguments
    if ($LASTEXITCODE -ne 0) { throw "roslyn2rdf failed with exit code $LASTEXITCODE." }

    $ttlHash = Get-Sha256 $ttlPath
    & $OxigraphCommand load --location $storePath --file $ttlPath --non-atomic
    if ($LASTEXITCODE -ne 0) { throw "Oxigraph load failed with exit code $LASTEXITCODE." }

    $countOutput = & $OxigraphCommand query --location $storePath --query 'SELECT (COUNT(*) AS ?count) WHERE { ?subject ?predicate ?object }' --results-format csv
    if ($LASTEXITCODE -ne 0) { throw "Oxigraph count query failed with exit code $LASTEXITCODE." }
    $tripleCount = [Int64](($countOutput | Select-Object -Last 1).Trim())

    $manifest = [ordered]@{
        schemaVersion = 1
        artifactId = $artifactId
        graphIri = $graphIri
        createdUtc = [DateTime]::UtcNow.ToString('O')
        origin = [ordered]@{
            kind = $OriginKind
            id = $OriginId
            branch = $Branch
            commit = $Commit
            packageVersion = $PackageVersion
            packageHash = $PackageHash
            packageFeed = $PackageFeed
        }
        build = [ordered]@{
            fingerprint = $BuildFingerprint
            targetFramework = $TargetFramework
            configuration = $Configuration
            platform = $Platform
            projectPath = $ProjectPath
        }
        assembly = [ordered]@{
            inputPath = $resolvedAssemblyPath
            name = $assemblyName
            version = $assemblyVersion
            publicKeyToken = $assemblyToken
            sha256 = Get-Sha256 $resolvedAssemblyPath
        }
        extraction = [ordered]@{
            tool = $Roslyn2RdfDll
            includePrivate = $true
            searchDirectories = @($SearchDirectory | ForEach-Object { [IO.Path]::GetFullPath($_) })
            temporaryTtlSha256 = $ttlHash
            temporaryTtlRetained = $false
            tripleCount = $tripleCount
            storeFormat = 'Oxigraph 0.5.8'
        }
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM
    Remove-Item -LiteralPath $ttlPath

    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Move-Item -LiteralPath $stagingArtifact -Destination $destination
    Remove-Item -LiteralPath $stagingRoot -Force
    Get-Content -LiteralPath (Join-Path $destination 'manifest.json') -Raw
}
catch {
    Write-Error "Snapshot staging was preserved for inspection: $stagingRoot"
    throw
}
