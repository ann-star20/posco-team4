#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class GatewayStreamChecks
{
    [Serializable] class Replay {public GatewayStreamClient.DbEvent[] events;}
    static GatewayStreamClient client;
    static double deadline;
    static GatewayStreamChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        try
        {
            if(!client)
            {
                if(!File.Exists("GatewayStreamCheck.once"))return;
                File.Delete("GatewayStreamCheck.once");
                client=new GameObject("Gateway read-only check"){hideFlags=HideFlags.HideAndDontSave}.AddComponent<GatewayStreamClient>();
                string raw=File.ReadAllText("Tools/Gateway/electrical-stream-probe.json");
                var saved=JsonUtility.FromJson<Replay>(raw).events[0];
                string json=raw.Substring(raw.IndexOf('[')+1);
                json=json.Substring(0,json.LastIndexOf(']')).Trim();
                Check(client.ApplyEvent(json),"Saved electrical event rejected");
                Check(client.LastSequence==39&&client.LatestElectrical.payload.response.result_origin=="mock","Mock provenance lost");
                Check(client.LatestElectrical.hasId&&!client.LatestElectrical.hasIdOn,"id/id_on presence lost");
                Check(!client.ApplyEvent(json)&&client.Error==null,"Replay not deduplicated");
                Check(!client.ApplyEvent(json.Replace(client.runId,Guid.NewGuid().ToString()))&&client.LastSequence==39,"Wrong RUN accepted");
                bool rejected=false;try{GatewayStreamClient.StreamUri(client.endpoint,"02c2d",0);}catch(ArgumentException){rejected=true;}
                Check(rejected,"Truncated UUID accepted");
                Check(GatewayStreamClient.StreamUri(client.endpoint,client.runId,39).Query.Contains("after_sequence=39"),"Reconnect cursor missing");
                // Start fresh to prove a real WebSocket event was received, rather than the saved fixture.
                UnityEngine.Object.DestroyImmediate(client.gameObject);
                client=new GameObject("Gateway live read-only check"){hideFlags=HideFlags.HideAndDontSave}.AddComponent<GatewayStreamClient>();
                Check(client.ConnectStream(),"Connect setup failed");deadline=EditorApplication.timeSinceStartup+15;
            }
            client.Pump();
            if(client.LatestElectrical!=null)
            {
                Check(client.LastSequence==39&&client.LatestElectrical.payload.response.result_origin=="mock","Unexpected live event");
                File.WriteAllText("GatewayStreamCheck.result","GATEWAY_STREAM_OK\nLive WebSocket sequence 39 / surrogate.completed / mock / id=1\nUUID validation / run isolation / replay deduplication / resume cursor checked\nNo control, approval or recipe requests sent");
                UnityEngine.Object.DestroyImmediate(client.gameObject);client=null;
            }
            else Check(EditorApplication.timeSinceStartup<deadline,"Timed out waiting for live Gateway event: "+client.Status+" / "+client.Error);
        }
        catch(Exception e)
        {
            File.WriteAllText("GatewayStreamCheck.result",e.ToString());
            if(client)UnityEngine.Object.DestroyImmediate(client.gameObject);client=null;
        }
    }
}
#endif
