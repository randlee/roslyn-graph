[CmdletBinding()]
param(
    [string] $DataRoot = $env:ROSLYN_GRAPH_DATA_ROOT,
    [Parameter(Mandatory)] [string] $SolutionName,
    [Parameter(Mandatory)] [string] $SolutionPath,
    [Parameter(Mandatory)] [string] $Repository,
    [Parameter(Mandatory)] [string] $Branch,
    [Parameter(Mandatory)] [string] $Commit,
    [Parameter(Mandatory)] [string] $BuildFingerprint,
    [Parameter(Mandatory)] [string] $TargetFramework,
    [Parameter(Mandatory)] [string] $Configuration,
    [Parameter(Mandatory)] [string] $Platform,
    [Parameter(Mandatory)] [string[]] $ComponentManifestPath,
    [string] $CommonTargetsPath,
    [string] $OxigraphCommand = 'oxigraph'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Sha256Text([string] $Value) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) }
    finally { $sha.Dispose() }
}

function Resolve-ArtifactDestination([string] $BasePath, [string] $ArtifactId) {
    foreach ($length in @(20, 32, 64)) {
        $candidate = Join-Path $BasePath $ArtifactId.Substring(0, $length)
        if (-not (Test-Path -LiteralPath $candidate)) { return $candidate }
        $existingManifestPath = Join-Path $candidate 'manifest.json'
        if (-not (Test-Path -LiteralPath $existingManifestPath -PathType Leaf)) { throw "Artifact directory exists without a manifest: $candidate" }
        $existingManifest = Get-Content -LiteralPath $existingManifestPath -Raw | ConvertFrom-Json
        if ($existingManifest.artifactId -eq $ArtifactId) { return $candidate }
    }
    throw "Artifact ID prefix collision could not be disambiguated: $ArtifactId"
}

function ConvertTo-NTriplesLiteral([string] $Value) {
    $escaped = $Value.Replace('\', '\\').Replace('"', '\"').Replace("`r", '\r').Replace("`n", '\n')
    return '"' + $escaped + '"'
}

if ([string]::IsNullOrWhiteSpace($DataRoot)) { throw 'DataRoot was not supplied and ROSLYN_GRAPH_DATA_ROOT is not set.' }
if ($ComponentManifestPath.Count -eq 0) { throw 'At least one component manifest is required.' }

$artifactRoot = Join-Path ([IO.Path]::GetFullPath($DataRoot)) '.roslyn-graph'
$resolvedSolutionPath = [IO.Path]::GetFullPath($SolutionPath)
if (-not (Test-Path -LiteralPath $resolvedSolutionPath -PathType Leaf)) { throw "Solution does not exist: $resolvedSolutionPath" }

$components = foreach ($path in $ComponentManifestPath) {
    $resolvedPath = [IO.Path]::GetFullPath($path)
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) { throw "Component manifest does not exist: $resolvedPath" }
    $manifest = Get-Content -LiteralPath $resolvedPath -Raw | ConvertFrom-Json
    $storePath = Join-Path (Split-Path -Parent $resolvedPath) 'store.oxigraph'
    if (-not (Test-Path -LiteralPath $storePath -PathType Container)) { throw "Component store does not exist: $storePath" }
    [PSCustomObject]@{ manifestPath = $resolvedPath; storePath = $storePath; manifest = $manifest }
}

$components = @($components | Sort-Object { $_.manifest.artifactId })
$identityParts = @(
    'solution', $Repository, $SolutionName, $Branch, $Commit, $BuildFingerprint, $TargetFramework, $Configuration, $Platform
) + @($components | ForEach-Object { $_.manifest.artifactId })
$solutionArtifactId = Get-Sha256Text ($identityParts -join '|')
$solutionIri = "urn:roslyn-graph:solution:$($solutionArtifactId.Substring(0, 32))"
$destinationBase = Join-Path $artifactRoot (Join-Path 'solutions' (Join-Path $Repository $SolutionName))
$destination = Resolve-ArtifactDestination $destinationBase $solutionArtifactId
$publishedCurrentPath = Join-Path (Join-Path $destination 'store.oxigraph') 'CURRENT'
if ($publishedCurrentPath.Length -gt 240) { throw "Published Oxigraph path is too long ($($publishedCurrentPath.Length)): $publishedCurrentPath" }

if (Test-Path -LiteralPath $destination) {
    $existingManifest = Join-Path $destination 'manifest.json'
    if (Test-Path -LiteralPath $existingManifest) {
        Get-Content -LiteralPath $existingManifest -Raw
        return
    }
    throw "Solution destination already exists without a manifest: $destination"
}

$stagingRoot = Join-Path (Join-Path $artifactRoot 'staging') ([Guid]::NewGuid().ToString('N'))
$stagingArtifact = Join-Path $stagingRoot 'artifact'
$storePath = Join-Path $stagingArtifact 'store.oxigraph'
$metadataPath = Join-Path $stagingArtifact 'metadata.nt'
$manifestPath = Join-Path $stagingArtifact 'manifest.json'
New-Item -ItemType Directory -Path $stagingArtifact -Force | Out-Null

try {
    $metadataGraphIri = "$solutionIri`:metadata"
    $rdfType = '<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>'
    $rgBase = 'http://roslyn-graph.example/ontology/'
    $metadataLines = [Collections.Generic.List[string]]::new()
    $metadataLines.Add("<$solutionIri> $rdfType <$($rgBase)SolutionBuild> .")
    $metadataLines.Add("<$solutionIri> <$($rgBase)name> $(ConvertTo-NTriplesLiteral $SolutionName) .")
    $metadataLines.Add("<$solutionIri> <$($rgBase)solutionPath> $(ConvertTo-NTriplesLiteral $resolvedSolutionPath) .")
    $metadataLines.Add("<$solutionIri> <$($rgBase)repository> $(ConvertTo-NTriplesLiteral $Repository) .")
    $metadataLines.Add("<$solutionIri> <$($rgBase)branch> $(ConvertTo-NTriplesLiteral $Branch) .")
    $metadataLines.Add("<$solutionIri> <$($rgBase)commit> $(ConvertTo-NTriplesLiteral $Commit) .")
    $metadataLines.Add("<$solutionIri> <$($rgBase)buildFingerprint> $(ConvertTo-NTriplesLiteral $BuildFingerprint) .")
    $metadataLines.Add("<$solutionIri> <$($rgBase)targetFramework> $(ConvertTo-NTriplesLiteral $TargetFramework) .")
    $metadataLines.Add("<$solutionIri> <$($rgBase)configuration> $(ConvertTo-NTriplesLiteral $Configuration) .")
    $metadataLines.Add("<$solutionIri> <$($rgBase)platform> $(ConvertTo-NTriplesLiteral $Platform) .")
    if (-not [string]::IsNullOrWhiteSpace($CommonTargetsPath)) {
        $metadataLines.Add("<$solutionIri> <$($rgBase)commonTargetsPath> $(ConvertTo-NTriplesLiteral ([IO.Path]::GetFullPath($CommonTargetsPath))) .")
    }

    foreach ($component in $components) {
        $metadataLines.Add("<$solutionIri> <$($rgBase)includesGraph> <$($component.manifest.graphIri)> .")
        $metadataLines.Add("<$solutionIri> <$($rgBase)includesArtifact> $(ConvertTo-NTriplesLiteral $component.manifest.artifactId) .")
    }
    Set-Content -LiteralPath $metadataPath -Value $metadataLines -Encoding utf8NoBOM

    foreach ($component in $components) {
        $componentDump = Join-Path $stagingArtifact ("component-" + $component.manifest.artifactId + '.nt')
        & $OxigraphCommand dump --location $component.storePath --file $componentDump --format nt --graph default
        if ($LASTEXITCODE -ne 0) { throw "Oxigraph dump failed for component $($component.manifest.artifactId)." }
        & $OxigraphCommand load --location $storePath --file $componentDump --graph $component.manifest.graphIri --non-atomic
        if ($LASTEXITCODE -ne 0) { throw "Oxigraph load failed for component $($component.manifest.artifactId)." }
        Remove-Item -LiteralPath $componentDump
    }
    & $OxigraphCommand load --location $storePath --file $metadataPath --graph $metadataGraphIri --non-atomic
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph metadata load failed.' }
    Remove-Item -LiteralPath $metadataPath

    $tripleCountOutput = & $OxigraphCommand query --location $storePath --query 'SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?graph { ?subject ?predicate ?object } }' --results-format csv
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph triple count query failed.' }
    $tripleCount = [Int64](($tripleCountOutput | Select-Object -Last 1).Trim())
    $graphCountOutput = & $OxigraphCommand query --location $storePath --query 'SELECT (COUNT(DISTINCT ?graph) AS ?count) WHERE { GRAPH ?graph { ?subject ?predicate ?object } }' --results-format csv
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph graph count query failed.' }
    $graphCount = [Int64](($graphCountOutput | Select-Object -Last 1).Trim())
    if ($graphCount -ne ($components.Count + 1)) { throw "Expected $($components.Count + 1) named graphs, found $graphCount." }

    & $OxigraphCommand optimize --location $storePath
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph optimize failed.' }

    $manifest = [ordered]@{
        schemaVersion = 1
        artifactId = $solutionArtifactId
        solutionIri = $solutionIri
        metadataGraphIri = $metadataGraphIri
        createdUtc = [DateTime]::UtcNow.ToString('O')
        solution = [ordered]@{
            name = $SolutionName; path = $resolvedSolutionPath; repository = $Repository; branch = $Branch; commit = $Commit
            buildFingerprint = $BuildFingerprint; targetFramework = $TargetFramework; configuration = $Configuration; platform = $Platform
            commonTargetsPath = $CommonTargetsPath
        }
        components = @($components | ForEach-Object { [ordered]@{
            artifactId = $_.manifest.artifactId; graphIri = $_.manifest.graphIri; manifestPath = $_.manifestPath
            origin = $_.manifest.origin; assembly = $_.manifest.assembly; tripleCount = $_.manifest.extraction.tripleCount
        } })
        store = [ordered]@{ format = 'Oxigraph 0.5.8'; namedGraphCount = $graphCount; tripleCount = $tripleCount }
    }
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Move-Item -LiteralPath $stagingArtifact -Destination $destination
    Remove-Item -LiteralPath $stagingRoot -Force
    Get-Content -LiteralPath (Join-Path $destination 'manifest.json') -Raw
}
catch {
    Write-Error "Solution staging was preserved for inspection: $stagingRoot"
    throw
}
