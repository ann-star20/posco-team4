#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;

[InitializeOnLoad]
public static class GatewayNullResultChecks
{
    static GatewayNullResultChecks(){EditorApplication.update+=Tick;}
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode||!File.Exists("GatewayNullResultCheck.once"))return;
        File.Delete("GatewayNullResultCheck.once");
        try
        {
            string run="8eacb6a1-f651-4e96-864c-047cf7df3d8c";
            string raw=File.ReadAllText("Tools/Gateway/failed-inspection-e71dc350.events.json");
            raw=raw.Substring(raw.IndexOf('[')+1);raw=raw.Substring(0,raw.LastIndexOf(']')).Trim();
            var failed=GatewayStreamClient.Parse(raw,run);
            Check(failed.payload.response.status=="failed"&&failed.payload.response.result_payload==null,"Actual failed/null response became zero-valued prediction");
            Check(GatewayInspectionProtocol.ErrorCode(failed.payload.response)=="OUT_OF_DOMAIN","Server failure code lost");
            Check(GatewayInspectionProtocol.FailureTitle(failed.payload.response).Contains("학습 범위 밖"),"Failure presented as electrical NG or zero");
            Check(Math.Abs(failed.payload.response.metadata.input_ratios.tox-1.643667)<1e-9,"Server input ratio lost");
            string prefix="{\"sequence\":1,\"event_id\":\""+Guid.NewGuid()+"\",\"run_id\":\""+run+"\",\"event_type\":\"surrogate.completed\",\"payload\":{\"response\":{\"status\":\"succeeded\",\"result_payload\":";
            var zero=GatewayStreamClient.Parse(prefix+"{\"vth\":0,\"gm\":0,\"id_on\":0,\"bv\":0}}}}",run);
            var r=zero.payload.response.result_payload;
            Check(r!=null&&r.vth_present&&r.gm_present&&r.bv_present&&zero.hasIdOn,"Real numeric zeros hidden as missing");
            var partial=GatewayStreamClient.Parse(prefix+"{\"vth\":2.2,\"gm\":null}}}}",run);
            r=partial.payload.response.result_payload;
            Check(r!=null&&r.vth_present&&!r.gm_present&&!r.bv_present,"Missing metric defaulted to zero");
            Check(GatewayInspectionProtocol.ResultText(r,false,false,false).Contains("gm —"),"Missing gm rendered as 0");
            Check(GatewayStreamClient.Parse(prefix+"null}}}",run).payload.response.result_payload==null,"Succeeded/null became a prediction");
            Check(GatewayStreamClient.Parse(prefix+"{}}}}",run).payload.response.result_payload==null,"Empty result became a prediction");
            File.WriteAllText("GatewayNullResultCheck.result","GATEWAY_NULL_RESULT_OK\nActual OUT_OF_DOMAIN replay / null and empty payloads absent / partial metrics absent / genuine numeric zeros preserved / failure text and server ratio retained\nOffline replay only; no new Gateway job");
        }
        catch(Exception e){File.WriteAllText("GatewayNullResultCheck.result",e.ToString());}
    }
}
#endif
