using System;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Logging;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Unity.Plastic.Newtonsoft.Json;
using Unity.Plastic.Newtonsoft.Json.Linq;

// Local fixture only; does not implement DB transactions, routing, or TCAD execution.
sealed class MockGateway : IDisposable
{
    readonly WebApplication app;
    readonly TaskCompletionSource<bool> finished=new TaskCompletionSource<bool>();
    int connections;
    readonly CancellationTokenSource cancel=new CancellationTokenSource();
    JObject request;
    readonly string job=Guid.NewGuid().ToString(), proposal=Guid.NewGuid().ToString(), candidate=Guid.NewGuid().ToString();
    public Task Work => finished.Task;
    public MockGateway()
    {
        var builder=WebApplication.CreateBuilder(); builder.Logging.ClearProviders();
        builder.WebHost.UseUrls("http://127.0.0.1:18765");
        app=builder.Build(); app.UseWebSockets();
        app.Run(async context =>
        {
            try { await Handle(context); if (Interlocked.Increment(ref connections)==3) finished.TrySetResult(true); }
            catch (Exception e) { finished.TrySetException(e); context.Abort(); }
        });
        app.StartAsync().GetAwaiter().GetResult();
    }
    async Task Handle(Microsoft.AspNetCore.Http.HttpContext context)
    {
            int connection=connections;
            using (var ws=await context.WebSockets.AcceptWebSocketAsync())
            {
                if (context.Request.Path=="/api/v1/control")
                {
                    if (request!=null || context.Request.Headers["X-Unity-Token"]!="local-test-token") throw new Exception("Auth failure or diagnosis resubmitted");
                    request=await Receive(ws);
                    if ((string)request["type"]!="diagnosis.requested" || request["task_type"]!=null) throw new Exception("Wrong Gateway diagnosis envelope");
                    var service=AsyncTcadContract.BuildWorkerRequest(request,job);
                    if ((string)service["task_type"]!="diagnosis" || (double)service["input_payload"]["measurements"]["gm"]!=3.767) throw new Exception("Wrong Worker task_type or micro units");
                    await Send(ws,new JObject { ["type"]="request.accepted", ["request_id"]=request["request_id"], ["job_id"]=job, ["status"]="queued" });
                }
                else
                {
                    var q=context.Request.Query;
                    if (q["run_id"]!=(string)request["run_id"]) throw new Exception("Wrong RUN");
                    int cursor=int.Parse(q["after_sequence"]);
                    if (connection==1 && cursor==0) await Send(ws,Event(1,"candidate_queued","queued"));
                    else if (connection==2 && cursor==1)
                    {
                        await Send(ws,Event(2,"candidate_succeeded","succeeded"));
                        await Send(ws,Event(3,"batch_completed","completed"));
                    }
                    else throw new Exception("Wrong replay cursor");
                }
            }
    }
    JObject Event(long sequence,string type,string status)
    {
        var payload=new JObject { ["run_id"]=request["run_id"], ["request_id"]=request["request_id"], ["job_id"]=job,
            ["proposal_id"]=proposal, ["tcad_request_id"]=candidate, ["candidate_index"]=0, ["status"]=status,
            ["note"]="분할 수신 시험" };
        if (status=="succeeded") payload["result_payload"]=new JObject { ["vth"]=2.4,["gm"]=4.5,["id_on"]=4.6,["bv"]=48 };
        return new JObject { ["sequence"]=sequence, ["event_id"]=Guid.NewGuid().ToString(), ["run_id"]=request["run_id"],
            ["event_type"]="tcad.verification."+type,["payload"]=payload };
    }
    async Task Send(WebSocket ws,JObject body)
    {
        var bytes=Encoding.UTF8.GetBytes(body.ToString(Formatting.None));
        // One byte per fragment also splits Korean UTF-8 codepoints.
        for (int i=0;i<bytes.Length;i++) await ws.SendAsync(new ArraySegment<byte>(bytes,i,1),WebSocketMessageType.Text,i==bytes.Length-1,cancel.Token);
    }
    async Task<JObject> Receive(WebSocket ws)
    {
        using (var data=new System.IO.MemoryStream())
        {
            byte[] buffer=new byte[16384]; WebSocketReceiveResult part;
            do { part=await ws.ReceiveAsync(new ArraySegment<byte>(buffer),cancel.Token); data.Write(buffer,0,part.Count); } while (!part.EndOfMessage);
            return JObject.Parse(Encoding.UTF8.GetString(data.ToArray()));
        }
    }
    public void Dispose() { cancel.Cancel(); app.StopAsync().GetAwaiter().GetResult(); app.DisposeAsync().GetAwaiter().GetResult(); cancel.Dispose(); }
}
