using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Logging;

// Loopback fixture for the real Unity client; not a Gateway/DB/TCAD implementation.
static class MockServer
{
    public static async Task Run(int port)
    {
        string audit=System.IO.Path.Combine(AppContext.BaseDirectory,"mock-"+port+".log");
        void Log(string message)=>System.IO.File.AppendAllText(audit,DateTime.UtcNow.ToString("O")+" "+message+Environment.NewLine);
        var b=WebApplication.CreateBuilder();b.Logging.ClearProviders();b.WebHost.UseUrls("http://127.0.0.1:"+port);
        var app=b.Build();app.UseWebSockets();var gate=new object();var events=new List<JsonObject>();
        string run=null,prediction=null,diagnosis=null,pj=Guid.NewGuid().ToString(),dj=Guid.NewGuid().ToString(),proposal=Guid.NewGuid().ToString(),candidate=Guid.NewGuid().ToString();int streams=0,submissions=0;
        JsonObject E(long seq,string type,JsonObject payload)=>new(){["sequence"]=seq,["event_id"]=Guid.NewGuid().ToString(),["run_id"]=run,["event_type"]=type,["payload"]=payload};
        JsonObject T(int seq,string suffix,string status)
        {
            var p=new JsonObject{["request_id"]=diagnosis,["job_id"]=dj,["proposal_id"]=proposal,["tcad_request_id"]=candidate,["candidate_index"]=0,["status"]=status};
            if(status=="succeeded")p["result_payload"]=JsonNode.Parse("{\"vth\":2.4,\"gm\":4.5,\"id_on\":4.6,\"bv\":48.0}");
            return E(seq,"tcad.verification."+suffix,p);
        }
        app.Run(async context=>
        {
            Log("connect "+context.Request.Path+" cursor="+context.Request.Query["after_sequence"]);
            try
            {
            using var socket=await context.WebSockets.AcceptWebSocketAsync();
            if(context.Request.Path=="/api/v1/control")
            {
                if(context.Request.Headers["X-Unity-Token"]!="local-fixture-token")throw new Exception("Fixture token missing");
                var r=await Read(socket);bool first=(string)r["type"]=="surrogate.requested";int n=Interlocked.Increment(ref submissions);
                Log("request "+(string)r["type"]+" count="+n);
                if(first&&n!=1||!first&&(n!=2||(string)r["type"]!="diagnosis.requested"))throw new Exception("Unexpected/duplicate request");
                string id=(string)r["request_id"];run??=(string)r["run_id"];if(run!=(string)r["run_id"])throw new Exception("RUN changed");
                if(!first&&((double)r["input_payload"]["measurements"]["gm"]!=3.767||(double)r["input_payload"]["measurements"]["id_on"]!=3.468||r["task_type"]!=null))throw new Exception("Unit/schema changed");
                await Send(socket,new JsonObject{["type"]="request.accepted",["request_id"]=id,["job_id"]=first?pj:dj,["status"]="queued"});
                Log("accepted "+id);
                lock(gate)
                {
                    if(first)
                    {
                        prediction=id;
                        events.Add(E(1,"surrogate.completed",new JsonObject{["request_id"]=id,["job_id"]=pj,["response"]=JsonNode.Parse("{\"status\":\"succeeded\",\"result_origin\":\"prod\",\"result_payload\":{\"vth\":2.874,\"gm\":3.767,\"id_on\":3.468,\"bv\":44.186},\"metadata\":{\"units\":{\"vth\":\"V\",\"gm\":\"uS/um\",\"id_on\":\"uA/um\",\"bv\":\"V\"}}}")}));
                    }
                    else
                    {
                        diagnosis=id;if(diagnosis==prediction)throw new Exception("request_id reused");
                        events.Add(E(2,"diagnosis.completed",new JsonObject{["request_id"]=id,["job_id"]=dj,["response"]=JsonNode.Parse("{\"status\":\"succeeded\",\"result_origin\":\"prod\",\"result_payload\":{\"decision\":{\"top_category\":\"oxide\",\"top_probability\":0.95,\"decided\":true},\"compensation\":{\"route\":\"tcad_verify\"}}}")}));
                        events.Add(T(3,"candidate_running","running"));events.Add(T(4,"candidate_succeeded","succeeded"));events.Add(T(5,"batch_completed","completed"));
                    }
                }
                return;
            }
            int connection=Interlocked.Increment(ref streams);long cursor=long.Parse(context.Request.Query["after_sequence"]);
            if(connection>1&&cursor!=3)throw new Exception("Reconnect cursor must be 3");
            while(!context.RequestAborted.IsCancellationRequested)
            {
                JsonObject[] pending;lock(gate)pending=events.Where(e=>(long)e["sequence"]>cursor).ToArray();
                foreach(var ev in pending)
                {
                    await Send(socket,ev);cursor=(long)ev["sequence"];
                    Log("sent event "+cursor);
                    if(connection==1&&cursor==3){await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure,"fixture reconnect",CancellationToken.None);return;}
                }
                await Task.Delay(25,context.RequestAborted);
            }
            }
            catch(Exception e){Log(e.ToString());throw;}
        });
        await app.RunAsync();
    }
    static Task Send(WebSocket ws,JsonObject value)=>ws.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes(value.ToJsonString())),WebSocketMessageType.Text,true,CancellationToken.None);
    static async Task<JsonObject> Read(WebSocket ws)
    {
        using var buffer=new System.IO.MemoryStream();var bytes=new byte[8192];WebSocketReceiveResult part;
        do{part=await ws.ReceiveAsync(new ArraySegment<byte>(bytes),CancellationToken.None);buffer.Write(bytes,0,part.Count);if(buffer.Length>65536)throw new Exception("Oversized request");}while(!part.EndOfMessage);
        return (JsonObject)JsonNode.Parse(Encoding.UTF8.GetString(buffer.ToArray()));
    }
}
