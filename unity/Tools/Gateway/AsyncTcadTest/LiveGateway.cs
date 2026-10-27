using System;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Unity.Plastic.Newtonsoft.Json;
using Unity.Plastic.Newtonsoft.Json.Linq;

static class LiveGateway
{
    public static async Task Run()
    {
        const string origin="ws://192.168.213.12:8000";
        const string http="http://192.168.213.12:8000";
        string token=Environment.GetEnvironmentVariable("TCAD_TEST_UNITY_TOKEN");
        if (string.IsNullOrWhiteSpace(token)) throw new Exception("TCAD_TEST_UNITY_TOKEN required");
        string run=Guid.NewGuid().ToString(), request=Guid.NewGuid().ToString();
        string root=Path.GetFullPath("Tools/Gateway/AsyncTcadTest/LiveRuns");
        // A rerun observes the original request instead of submitting a second job.
        if (File.Exists(Path.Combine(root,"active.json"))) throw new Exception("Existing live test: inspect LiveRuns/active.json; no automatic resubmit.");
        string folder=Path.Combine(root,request); Directory.CreateDirectory(folder);
        var input=File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"diagnosis-input.example.json"));
        var body=AsyncTcadContract.Build(input,run,request,"LOT-UNITY-INTEGRATION-TEST","MOSFET-TEST-001");
        void Save(string name,JToken value) => File.WriteAllText(Path.Combine(folder,name),value.ToString(Formatting.Indented));
        Save("request.json",body);
        File.WriteAllText(Path.Combine(root,"active.json"),new JObject { ["run_id"]=run,["request_id"]=request,["folder"]=folder,["input_origin"]="team-provided communication example; n_wafers=25 is fixture, not measured production LOT" }.ToString());
        using var cancel=new CancellationTokenSource(TimeSpan.FromSeconds(210));
        using var client=new HttpClient { Timeout=TimeSpan.FromSeconds(10) };
        Console.WriteLine("LIVE_TEST request_id="+request+" run_id="+run);
        JObject diagnosisEvent=null;
        AsyncTcadContract.State state=null;
        try
        {
            using var stream=await AsyncTcadSocket.ConnectStream(origin,run,0,cancel.Token);
            var ack=await AsyncTcadSocket.SendOnce(origin,token,body,cancel.Token);
            Save("accepted.json",ack);
            Console.WriteLine("ACCEPTED job_id="+(string)ack["job_id"]+" status="+(string)ack["status"]);
            state=new AsyncTcadContract.State(run,request,(string)ack["job_id"]);
            while (!cancel.IsCancellationRequested)
            {
                var e=await AsyncTcadSocket.Receive(stream,cancel.Token);
                File.AppendAllText(Path.Combine(folder,"events.jsonl"),e.ToString(Formatting.None)+Environment.NewLine);
                bool related=state.Accept(e);
                Console.WriteLine("EVENT sequence="+(string)e["sequence"]+" type="+(string)e["event_type"]+" related="+related);
                if (!related) continue;
                string kind=(string)e["event_type"];
                if (kind=="diagnosis.completed" || kind=="diagnosis.failed")
                {
                    diagnosisEvent=e; Save("diagnosis-event.json",e);
                    var response=e["payload"]?["response"];
                    Console.WriteLine("DIAGNOSIS status="+(string)response?["status"]+" origin="+(string)response?["result_origin"]+" route="+(string)response?["result_payload"]?["compensation"]?["route"]);
                    cancel.CancelAfter(TimeSpan.FromSeconds(35));
                    if ((string)response?["status"]!="succeeded") break;
                }
                if (kind=="tcad.verification.batch_completed" || kind=="tcad.verification.review_required") break;
            }
        }
        catch (OperationCanceledException) { Console.WriteLine("OBSERVATION_WINDOW_ENDED; no resubmit, server job not cancelled"); }
        catch (Exception e) { Save("transport-error.json",new JObject { ["type"]=e.GetType().Name,["message"]=e.Message }); Console.WriteLine("TRANSPORT_ERROR "+e.GetType().Name+": "+e.Message); }
        var replay=JObject.Parse(await client.GetStringAsync(http+"/api/v1/events?run_id="+run+"&after_sequence=0&limit=200"));
        Save("db-replay.json",replay);
        bool persisted=false;
        foreach(var e in (JArray)replay["events"])
            if (diagnosisEvent!=null && (string)e["event_id"]==(string)diagnosisEvent["event_id"]) persisted=true;
        if (state!=null)
        {
            using var message=new HttpRequestMessage(HttpMethod.Get,http+"/api/v1/jobs/"+state.Job);
            message.Headers.Add("X-Unity-Token",token);
            using var result=await client.SendAsync(message);
            Save("db-job.json",JToken.Parse(await result.Content.ReadAsStringAsync()));
        }
        var summary=new JObject { ["run_id"]=run,["request_id"]=request,["job_id"]=state?.Job,["diagnosis_event_id"]=diagnosisEvent?["event_id"],
            ["websocket_diagnosis_received"]=diagnosisEvent!=null,["same_event_replayed_from_db"]=persisted,
            ["response"]=diagnosisEvent?["payload"]?["response"],["tcad_candidates_seen"]=state?.Candidates.Count??0,["tcad_batch"]=state?.Batch,
            ["scope"]="Real Gateway via the same C# transport as Unity test window; not an in-Editor button execution" };
        Save("summary.json",summary);
        Console.WriteLine(summary.ToString(Formatting.Indented));
        if (diagnosisEvent==null || !persisted) Environment.ExitCode=2;
    }
}
