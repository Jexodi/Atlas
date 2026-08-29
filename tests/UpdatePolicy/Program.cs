using Atlas.UI.Services;
using System.Net;
using System.Text.Json;

var cases = new[] {
    ("3.3.5", "rc", "3.3.5-rc.2", "3.3.5", AtlasUpdateStatus.UpToDate),
    ("3.3.5", "rc", "3.3.6-rc.1", "3.3.5", AtlasUpdateStatus.UpdateAvailable),
    ("3.3.6-rc.2", "rc", "3.3.6-rc.1", "3.3.5", AtlasUpdateStatus.UpToDate),
    ("3.3.6-rc.1", "rc", "3.3.6-rc.1", "3.3.5", AtlasUpdateStatus.UpToDate),
    ("3.3.5", "release", "3.3.5", "3.3.5", AtlasUpdateStatus.ReinstallAvailable),
    ("3.3.6-rc.1", "release", "3.3.5", "3.3.5", AtlasUpdateStatus.ReinstallAvailable),
    ("3.3.5-rc.2", "release", "3.3.5", "3.3.5", AtlasUpdateStatus.UpdateAvailable),
};
foreach (var (installed, channel, candidate, stable, expected) in cases) {
    using var client = new HttpClient(new Manifests(channel, candidate, stable));
    var result = await new AtlasUpdateService(client).CheckAsync(installed,
        new(true, channel, true, $"https://test.invalid/{channel}.json"));
    if (result.Status != expected) throw new Exception($"{installed}/{candidate}: {result.Status} != {expected}");
}
using (var client = new HttpClient(new Manifests("rc", "3.3.6-rc.1", "3.3.5", true))) {
    try {
        await new AtlasUpdateService(client).CheckAsync("3.3.5", new(true, "rc", true, "https://test.invalid/rc.json"));
        throw new Exception("Missing stable reference must block RC");
    } catch (HttpRequestException) { }
}
Console.WriteLine("8 update policy checks passed.");

sealed class Manifests(string channel, string candidate, string stable, bool failStable = false) : HttpMessageHandler {
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) {
        bool isStableReference = channel == "rc" && request.RequestUri!.AbsolutePath.EndsWith("release.json");
        if (isStableReference && failStable) return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
            Content = new StringContent(JsonSerializer.Serialize(new {
                version = isStableReference ? stable : candidate,
                channel = isStableReference ? "release" : channel,
                url = "https://test.invalid/Atlas.exe", sha256 = new string('a', 64)
            }))
        });
    }
}
