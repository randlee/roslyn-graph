using RoslynToRdf.Cli;
namespace RoslynToRdf.Tests;
public class PluginInstallerTests
{
 [Fact] public void DryRun_DefaultsToBothWithoutWriting() { var (s,t)=Roots(); Environment.SetEnvironmentVariable("ROSLYN2RDF_PLUGIN_ROOT",s); var o=new StringWriter(); Assert.Equal(0,PluginInstaller.Install(new DirectoryInfo(t),false,false,true,o,new StringWriter())); Assert.Contains("Claude",o.ToString()); Assert.Contains("Codex",o.ToString()); Assert.False(Directory.Exists(Path.Combine(t,".claude"))); }
 [Fact] public void ClaudeOnly_CopiesBundle() { var(s,t)=Roots(); Environment.SetEnvironmentVariable("ROSLYN2RDF_PLUGIN_ROOT",s); Assert.Equal(0,PluginInstaller.Install(new DirectoryInfo(t),true,false,false,TextWriter.Null,new StringWriter())); Assert.True(File.Exists(Path.Combine(t,".claude","plugins","roslyn-graph",".claude-plugin","plugin.json"))); Assert.False(Directory.Exists(Path.Combine(t,".codex"))); }
 static (string,string) Roots() { var r=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N")); var s=Path.Combine(r,"source"); Directory.CreateDirectory(Path.Combine(s,".claude-plugin")); File.WriteAllText(Path.Combine(s,".claude-plugin","plugin.json"),"{}"); return(s,Path.Combine(r,"target")); }
}
