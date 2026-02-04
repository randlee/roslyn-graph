namespace RoslynToRdf.Core.Extraction;

/// <summary>
/// Options for controlling assembly extraction.
/// </summary>
public sealed class ExtractionOptions
{
    /// <summary>
    /// Base URI for generated IRIs.
    /// </summary>
    public string BaseUri { get; set; } = "http://dotnet.example/";

    /// <summary>
    /// Include private members in the output.
    /// </summary>
    public bool IncludePrivate { get; set; } = false;

    /// <summary>
    /// Include internal members in the output.
    /// </summary>
    public bool IncludeInternal { get; set; } = true;

    /// <summary>
    /// Include compiler-generated members.
    /// </summary>
    public bool IncludeCompilerGenerated { get; set; } = false;

    /// <summary>
    /// Extract exception types from XML documentation.
    /// </summary>
    public bool ExtractExceptions { get; set; } = true;

    /// <summary>
    /// Extract seealso references from XML documentation.
    /// </summary>
    public bool ExtractSeeAlso { get; set; } = true;

    /// <summary>
    /// Include attributes on types and members.
    /// </summary>
    public bool IncludeAttributes { get; set; } = true;

    /// <summary>
    /// Include reference types (external assemblies) as nodes with minimal info.
    /// </summary>
    public bool IncludeExternalTypes { get; set; } = true;

    /// <summary>
    /// Verbosity level for logging.
    /// </summary>
    public LogLevel LogLevel { get; set; } = LogLevel.Info;
}

public enum LogLevel
{
    Quiet,
    Info,
    Verbose
}
