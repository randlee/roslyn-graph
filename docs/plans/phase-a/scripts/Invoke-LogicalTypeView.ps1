[CmdletBinding()]
param(
    [string] $DataRoot = $env:ROSLYN_GRAPH_DATA_ROOT,
    [Parameter(Mandatory)] [string] $BaseSolutionManifestPath,
    [Parameter(Mandatory)] [string[]] $AdditionalComponentManifestPath,
    [string[]] $CompatibleAssemblyName = @('Radiant.Data', 'Radiant.Annotations'),
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
$artifactRoot = Join-Path ([IO.Path]::GetFullPath($DataRoot)) '.roslyn-graph'
$resolvedBaseManifestPath = [IO.Path]::GetFullPath($BaseSolutionManifestPath)
if (-not (Test-Path -LiteralPath $resolvedBaseManifestPath -PathType Leaf)) { throw "Base solution manifest does not exist: $resolvedBaseManifestPath" }
$base = Get-Content -LiteralPath $resolvedBaseManifestPath -Raw | ConvertFrom-Json
$baseStore = Join-Path (Split-Path -Parent $resolvedBaseManifestPath) 'store.oxigraph'
if (-not (Test-Path -LiteralPath $baseStore -PathType Container)) { throw "Base solution store does not exist: $baseStore" }

$additional = foreach ($path in $AdditionalComponentManifestPath) {
    $resolvedPath = [IO.Path]::GetFullPath($path)
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) { throw "Additional component manifest does not exist: $resolvedPath" }
    $manifest = Get-Content -LiteralPath $resolvedPath -Raw | ConvertFrom-Json
    if ($manifest.assembly.name -notin $CompatibleAssemblyName) { throw "Additional assembly is not covered by the compatibility policy: $($manifest.assembly.name)" }
    $store = Join-Path (Split-Path -Parent $resolvedPath) 'store.oxigraph'
    if (-not (Test-Path -LiteralPath $store -PathType Container)) { throw "Additional component store does not exist: $store" }
    [PSCustomObject]@{ manifestPath = $resolvedPath; storePath = $store; manifest = $manifest }
}
$additional = @($additional | Sort-Object { $_.manifest.artifactId })

$policy = 'v1: logical key = assembly name + full metadata name; only explicitly listed additive-compatible assembly versions are linked; physical identities are retained; owl:sameAs is not emitted.'
$viewIdentity = @('logical-type-view', $base.artifactId, $policy) + @($additional | ForEach-Object { $_.manifest.artifactId })
$viewArtifactId = Get-Sha256Text ($viewIdentity -join '|')
$viewIri = "urn:roslyn-graph:view:$($viewArtifactId.Substring(0, 32))"
$destination = Resolve-ArtifactDestination (Join-Path $artifactRoot 'views') $viewArtifactId
$publishedCurrentPath = Join-Path (Join-Path $destination 'store.oxigraph') 'CURRENT'
if ($publishedCurrentPath.Length -gt 240) { throw "Published Oxigraph path is too long ($($publishedCurrentPath.Length)): $publishedCurrentPath" }
if (Test-Path -LiteralPath $destination) {
    $existingManifest = Join-Path $destination 'manifest.json'
    if (Test-Path -LiteralPath $existingManifest) { Get-Content -LiteralPath $existingManifest -Raw; return }
    throw "View destination already exists without a manifest: $destination"
}

$stagingRoot = Join-Path (Join-Path $artifactRoot 'staging') ([Guid]::NewGuid().ToString('N'))
$stagingArtifact = Join-Path $stagingRoot 'artifact'
$storePath = Join-Path $stagingArtifact 'store.oxigraph'
$baseDumpPath = Join-Path $stagingArtifact 'base.nq'
$mappingPath = Join-Path $stagingArtifact 'logical-types.nt'
$manifestPath = Join-Path $stagingArtifact 'manifest.json'
New-Item -ItemType Directory -Path $stagingArtifact -Force | Out-Null

try {
    & $OxigraphCommand dump --location $baseStore --file $baseDumpPath --format nq
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph dump failed for the base solution store.' }
    & $OxigraphCommand load --location $storePath --file $baseDumpPath --non-atomic
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph load failed for the base solution store.' }
    Remove-Item -LiteralPath $baseDumpPath

    foreach ($component in $additional) {
        $componentDump = Join-Path $stagingArtifact ("component-" + $component.manifest.artifactId + '.nt')
        & $OxigraphCommand dump --location $component.storePath --file $componentDump --format nt --graph default
        if ($LASTEXITCODE -ne 0) { throw "Oxigraph dump failed for component $($component.manifest.artifactId)." }
        & $OxigraphCommand load --location $storePath --file $componentDump --graph $component.manifest.graphIri --non-atomic
        if ($LASTEXITCODE -ne 0) { throw "Oxigraph load failed for component $($component.manifest.artifactId)." }
        Remove-Item -LiteralPath $componentDump
    }

    $baseProjectionComponents = @($base.components | Where-Object { $_.assembly.name -in $CompatibleAssemblyName } | ForEach-Object {
        [PSCustomObject]@{
            manifest = [PSCustomObject]@{
                artifactId = $_.artifactId
                graphIri = $_.graphIri
                origin = $_.origin
                assembly = $_.assembly
            }
        }
    })
    $projectionComponents = $baseProjectionComponents + $additional
    $projectionComponents = @($projectionComponents | Sort-Object { $_.manifest.artifactId })
    $mappingLines = [Collections.Generic.List[string]]::new()
    $mappingLines.Add("<$viewIri> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://roslyn-graph.example/ontology/LogicalTypeView> .")
    $mappingLines.Add("<$viewIri> <http://roslyn-graph.example/ontology/policy> $(ConvertTo-NTriplesLiteral $policy) .")
    $seenPhysical = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $seenLogical = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($component in $projectionComponents) {
        $assemblyIri = "http://dotnet.example/assembly/$($component.manifest.assembly.name)/$($component.manifest.assembly.version)"
        $query = "PREFIX dt: <http://dotnet.example/ontology/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> SELECT ?type ?fullName WHERE { GRAPH <$($component.manifest.graphIri)> { ?type rdf:type dt:Type; dt:fullName ?fullName; dt:definedInAssembly <$assemblyIri> } }"
        $queryOutput = & $OxigraphCommand query --location $storePath --query $query --results-format json
        if ($LASTEXITCODE -ne 0) { throw "Type query failed for component $($component.manifest.artifactId)." }
        $results = $queryOutput | ConvertFrom-Json
        foreach ($binding in $results.results.bindings) {
            $physicalIri = $binding.type.value
            if (-not $seenPhysical.Add($physicalIri)) { continue }
            $fullName = $binding.fullName.value
            $logicalIri = "urn:roslyn-graph:logical-type:$((Get-Sha256Text ($component.manifest.assembly.name + '|' + $fullName)).Substring(0, 32))"
            $mappingLines.Add("<$physicalIri> <http://dotnet.example/ontology/logicalType> <$logicalIri> .")
            if ($seenLogical.Add($logicalIri)) {
                $mappingLines.Add("<$logicalIri> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://roslyn-graph.example/ontology/LogicalType> .")
                $mappingLines.Add("<$logicalIri> <http://dotnet.example/ontology/assemblyName> $(ConvertTo-NTriplesLiteral $component.manifest.assembly.name) .")
                $mappingLines.Add("<$logicalIri> <http://dotnet.example/ontology/fullName> $(ConvertTo-NTriplesLiteral $fullName) .")
            }
        }
    }
    Set-Content -LiteralPath $mappingPath -Value $mappingLines -Encoding utf8NoBOM
    $logicalGraphIri = "$viewIri`:logical-types"
    & $OxigraphCommand load --location $storePath --file $mappingPath --graph $logicalGraphIri --non-atomic
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph logical-type mapping load failed.' }
    Remove-Item -LiteralPath $mappingPath

    $tripleCountOutput = & $OxigraphCommand query --location $storePath --query 'SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?graph { ?subject ?predicate ?object } }' --results-format csv
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph triple count query failed.' }
    $tripleCount = [Int64](($tripleCountOutput | Select-Object -Last 1).Trim())
    $graphCountOutput = & $OxigraphCommand query --location $storePath --query 'SELECT (COUNT(DISTINCT ?graph) AS ?count) WHERE { GRAPH ?graph { ?subject ?predicate ?object } }' --results-format csv
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph graph count query failed.' }
    $graphCount = [Int64](($graphCountOutput | Select-Object -Last 1).Trim())
    $expectedGraphCount = [Int64]($base.store.namedGraphCount + $additional.Count + 1)
    if ($graphCount -ne $expectedGraphCount) { throw "Expected $expectedGraphCount named graphs, found $graphCount." }
    & $OxigraphCommand optimize --location $storePath
    if ($LASTEXITCODE -ne 0) { throw 'Oxigraph optimize failed.' }

    $manifest = [ordered]@{
        schemaVersion = 1; artifactId = $viewArtifactId; viewIri = $viewIri; logicalGraphIri = $logicalGraphIri
        createdUtc = [DateTime]::UtcNow.ToString('O'); baseSolutionManifestPath = $resolvedBaseManifestPath; baseSolutionArtifactId = $base.artifactId
        policy = $policy; compatibleAssemblyNames = @($CompatibleAssemblyName)
        additionalComponents = @($additional | ForEach-Object { [ordered]@{ artifactId = $_.manifest.artifactId; graphIri = $_.manifest.graphIri; manifestPath = $_.manifestPath; origin = $_.manifest.origin; assembly = $_.manifest.assembly } })
        projection = [ordered]@{ physicalTypeLinks = $seenPhysical.Count; logicalTypes = $seenLogical.Count }
        store = [ordered]@{ format = 'Oxigraph 0.5.8'; namedGraphCount = $graphCount; tripleCount = $tripleCount }
    }
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Move-Item -LiteralPath $stagingArtifact -Destination $destination
    Remove-Item -LiteralPath $stagingRoot -Force
    Get-Content -LiteralPath (Join-Path $destination 'manifest.json') -Raw
}
catch {
    Write-Error "Logical-type view staging was preserved for inspection: $stagingRoot"
    throw
}
