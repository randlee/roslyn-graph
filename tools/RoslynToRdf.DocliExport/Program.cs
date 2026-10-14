using Docli;
using RoslynToRdf.DocliExport;

Console.Out.Write(CliModelJson.Serialize(CommandLineAdapter.FromCommand(RoslynGraphDocliCommandTree.CreateRootCommand())));
