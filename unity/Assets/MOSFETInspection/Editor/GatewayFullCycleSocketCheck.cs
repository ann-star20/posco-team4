#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using UnityEditor;
using UnityEngine;

// Separate .NET fixture avoids Mono HttpListener's unsupported WebSocket server implementation.
public sealed class GatewayFullCycleSocketCheck : IDisposable
{
    readonly GatewayInspectionBridge bridge,previousBridge;
    readonly GatewayInspectionBridge.Job job;
    readonly GameObject owner;
    readonly System.Diagnostics.Process server;
    readonly DateTime deadline=DateTime.UtcNow.AddSeconds(40);
    public GatewayFullCycleSocketCheck()
    {
        var probe=new TcpListener(IPAddress.Loopback,0);probe.Start();int port=((IPEndPoint)probe.LocalEndpoint).Port;probe.Stop();
        var start=new System.Diagnostics.ProcessStartInfo{
            FileName="C:/Program Files/Unity/Hub/Editor/6000.6.4f1/Editor/Data/DotNetSdk/dotnet.exe",
            Arguments="\""+Path.GetFullPath("Temp/Gateway/FullCycleChecks/Checks.dll")+"\" --serve "+port,
            UseShellExecute=false,CreateNoWindow=true,WindowStyle=System.Diagnostics.ProcessWindowStyle.Hidden};
        server=System.Diagnostics.Process.Start(start);
        previousBridge=GatewayInspectionBridge.Instance;
        owner=new GameObject("Gateway full cycle offline socket check"){hideFlags=HideFlags.HideAndDontSave};bridge=owner.AddComponent<GatewayInspectionBridge>();
        bridge.EnsureSession();bridge.StreamAddress="ws://127.0.0.1:"+port+"/api/v1/stream";bridge.Token="local-fixture-token";
        if(!bridge.Arm())throw new Exception("Could not arm local fixture");
        var request=GatewayInspectionProtocol.BuildPhysical(null,"LOT-OFFLINE-FULL-CYCLE","UNIT-1",Guid.NewGuid().ToString("N"),null,7.7e12,1.7e16,.06);
        job=new GatewayInspectionBridge.Job{kind="gateway_full_cycle",request=request,inspectionId=request.input_payload.provenance.inspection_id,streamAddress=bridge.StreamAddress,
            cycle=new GatewayFullCycleProtocol.State(request.run_id,request.request_id,request.lot_id,request.unit_id,false,true)};
        Set("ready",true);Set("credential",bridge.Token);Set("cycleStarted",DateTime.UtcNow);Set("cycleDeadline",DateTime.UtcNow.AddSeconds(35));
        ((List<GatewayInspectionBridge.Job>)typeof(GatewayInspectionBridge).GetField("jobs",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(bridge)).Add(job);
        EditorApplication.update+=Pump;
    }
    void Set(string name,object value)=>typeof(GatewayInspectionBridge.Job).GetField(name,BindingFlags.Instance|BindingFlags.NonPublic).SetValue(job,value);
    void Pump()
    {
        try
        {
            if(server.HasExited)throw new Exception("Local .NET fixture stopped: "+server.ExitCode);
            typeof(GatewayInspectionBridge).GetMethod("Update",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(bridge,null);
            if(job.cycle.Done)
            {
                if(!job.cycle.BatchReceived||job.cycle.Candidates.Count!=1||job.cycle.Sequence!=5)throw new Exception("Wrong batch/reconnect result");
                File.AppendAllText("GatewayFullCycleCheck.result","\nFULL_CYCLE_RUNTIME_SOCKET_OK\n"+DateTime.UtcNow.ToString("O")+"\nActual runtime GatewayInspectionBridge + GatewayStreamClient / two control submissions / stream disconnect seq3 / resume after_sequence=3 / TCAD batch seq5 / loopback fixture only");
                Dispose();return;
            }
            if((bool)typeof(GatewayInspectionBridge.Job).GetField("finished",BindingFlags.NonPublic|BindingFlags.Instance).GetValue(job))throw new Exception(job.state);
            if(DateTime.UtcNow>deadline)throw new Exception("Local socket timeout: "+job.state+" / sequence "+job.cycle.Sequence);
        }
        catch(Exception e){File.AppendAllText("GatewayFullCycleCheck.result","\nFAILED_SOCKET: "+e);Debug.LogException(e);Dispose();}
    }
    public void Dispose()
    {
        EditorApplication.update-=Pump;
        if(owner)UnityEngine.Object.DestroyImmediate(owner);
        typeof(GatewayInspectionBridge).GetProperty("Instance",BindingFlags.Public|BindingFlags.Static).SetValue(null,previousBridge);
        if(!server.HasExited)server.Kill();server.Dispose();
        foreach(string id in new[]{job.cycle.PredictionId,job.cycle.DiagnosisId})if(id!=null)foreach(string suffix in new[]{".json",".events.jsonl"})File.Delete("Tools/Gateway/Requests/"+id+suffix);
    }
}
#endif
