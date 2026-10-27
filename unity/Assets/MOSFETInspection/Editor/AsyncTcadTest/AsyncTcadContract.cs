using System;
using System.Collections.Generic;
using Unity.Plastic.Newtonsoft.Json.Linq;

// Isolated test contract. Does not change the equipment's existing production sender.
public static class AsyncTcadContract
{
    static void Uuid(string value) { if (!Guid.TryParse(value, out _)) throw new FormatException("UUID required"); }
    public static JObject Build(string modelInput, string run, string request, string lot, string unit)
    {
        Uuid(run); Uuid(request);
        if (Guid.Parse(run) == Guid.Parse(request) || string.IsNullOrWhiteSpace(lot) || string.IsNullOrWhiteSpace(unit))
            throw new FormatException("Separate run/request UUIDs and LOT/unit required");
        var input = JToken.Parse(modelInput) as JObject;
        if (input == null || !input.HasValues) throw new FormatException("Confirmed diagnosis input_payload object required; surrogate input is not interchangeable");
        ValidateInput(input);
        return new JObject {
            ["type"] = "diagnosis.requested", ["schema_version"] = 1,
            ["request_id"] = request, ["run_id"] = run, ["lot_id"] = lot, ["unit_id"] = unit,
            ["stage_id"] = "electrical", ["stage_attempt"] = 1, ["model_contract_version"] = "fab-ml-v1",
            ["input_payload"] = input
        };
    }
    static void ValidateInput(JObject input)
    {
        var measurements=input["measurements"] as JObject;
        if (measurements==null) throw new FormatException("measurements required: Vth V, gm uS/um, id_on uA/um, BV V");
        foreach(string key in new[]{"vth","gm","id_on","bv"})
        {
            var value=measurements[key];
            if (key=="bv" && value!=null && value.Type==JTokenType.Null) continue;
            if (value==null || (value.Type!=JTokenType.Float && value.Type!=JTokenType.Integer) || double.IsNaN((double)value) || double.IsInfinity((double)value))
                throw new FormatException("Finite "+key+" required; unmeasured bv must explicitly be null");
        }
        var count=input["n_wafers"];
        if(count==null || count.Type!=JTokenType.Integer || (double)count<1 || (double)count>100000)
            throw new FormatException("n_wafers must be integer 1..100000, actual number averaged");
        var refine=input["refine"];
        if(refine==null || refine.Type!=JTokenType.Boolean || (bool)refine)
            throw new FormatException("Current Jetson contract requires refine=false");
    }
    // Expected Gateway-to-service projection for tests; Unity never sends this directly.
    public static JObject BuildWorkerRequest(JObject gatewayRequest,string job)
    {
        Uuid(job);
        if ((string)gatewayRequest["type"]!="diagnosis.requested") throw new FormatException("Expected diagnosis request");
        ValidateInput((JObject)gatewayRequest["input_payload"]);
        var service=(JObject)gatewayRequest.DeepClone();
        service.Remove("type"); service["task_type"]="diagnosis"; service["job_id"]=job;
        return service;
    }
    public sealed class State
    {
        public readonly string Run, Request, Job;
        public long Sequence { get; private set; }
        public readonly Dictionary<string,JObject> Candidates = new Dictionary<string,JObject>();
        public JObject Batch { get; private set; }
        public JObject Review { get; private set; }
        public JObject Diagnosis { get; private set; }
        public State(string run, string request, string job, long sequence = 0)
        { Uuid(run); Uuid(request); Uuid(job); if (sequence < 0) throw new FormatException("Invalid cursor"); Run=run; Request=request; Job=job; Sequence=sequence; }
        public bool Accept(JObject e)
        {
            if ((string)e["run_id"] != Run) return false;
            var seq = (long?)e["sequence"] ?? 0;
            if (seq <= Sequence) return false;
            Uuid((string)e["event_id"]);
            string type = (string)e["event_type"];
            if (string.IsNullOrEmpty(type)) throw new FormatException("Missing event_type");
            var p = e["payload"] as JObject;
            if (p == null) throw new FormatException("Missing payload");
            if (type.StartsWith("tcad.verification.", StringComparison.Ordinal)) Uuid((string)p["request_id"]);
            if ((string)p["request_id"] != Request) { Sequence=seq; return false; }
            if ((string)p["job_id"] != Job) throw new FormatException("Gateway job_id mismatch");
            if (type=="diagnosis.completed")
            {
                var response=p["response"] as JObject;
                if (response==null) throw new FormatException("diagnosis.completed missing response");
                Diagnosis=(JObject)response.DeepClone();
            }
            if (type.StartsWith("tcad.verification.", StringComparison.Ordinal))
            {
                Uuid((string)p["proposal_id"]);
                if (type.StartsWith("tcad.verification.candidate_", StringComparison.Ordinal))
                {
                    string status = type.Substring("tcad.verification.candidate_".Length);
                    if (status!="queued" && status!="running" && status!="succeeded" && status!="failed" && status!="cancelled")
                        throw new FormatException("Unknown candidate event");
                    string id=(string)p["tcad_request_id"]; Uuid(id);
                    if (id==Request || (int?)p["candidate_index"] == null || (int)p["candidate_index"] < 0 || (string)p["status"] != status)
                        throw new FormatException("Candidate ID/index/status mismatch");
                    if (status=="succeeded")
                        foreach (string key in new[]{"vth","gm","id_on","bv"})
                        {
                            var value=p["result_payload"]?[key];
                            if (value==null || (value.Type!=JTokenType.Float && value.Type!=JTokenType.Integer) || double.IsNaN((double)value) || double.IsInfinity((double)value))
                                throw new FormatException("Successful TCAD event missing finite "+key);
                        }
                    foreach (var pair in Candidates)
                        if (pair.Key != id && (string)pair.Value["proposal_id"] == (string)p["proposal_id"] && (int)pair.Value["candidate_index"] == (int)p["candidate_index"])
                            throw new FormatException("Candidate index changed TCAD identifier");
                    if (Candidates.TryGetValue(id, out var previous) && ((string)previous["proposal_id"] != (string)p["proposal_id"] || (int)previous["candidate_index"] != (int)p["candidate_index"]))
                        throw new FormatException("TCAD identifier changed candidate");
                    Candidates[id]=(JObject)p.DeepClone();
                }
                else if (type=="tcad.verification.batch_completed") Batch=(JObject)p.DeepClone();
                else if (type=="tcad.verification.review_required") Review=(JObject)p.DeepClone();
            }
            Sequence=seq;
            return true;
        }
    }
}
