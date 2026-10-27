using System;
using Unity.Plastic.Newtonsoft.Json.Linq;

public static class AsyncTcadChecks
{
    static void Require(bool condition, string message) { if (!condition) throw new Exception(message); }
    static void Reject(Action action) { try { action(); } catch (FormatException) { return; } throw new Exception("Invalid contract accepted"); }
    public static string Run()
    {
        string run = Guid.NewGuid().ToString(), request = Guid.NewGuid().ToString(), job = Guid.NewGuid().ToString();
        const string input="{\"measurements\":{\"vth\":2.874,\"gm\":3.767,\"id_on\":3.468,\"bv\":44.186},\"n_wafers\":25,\"refine\":false,\"extension\":{\"keep\":true}}";
        var wire = AsyncTcadContract.Build(input, run, request, "LOT-TEST", "UNIT-TEST");
        Require((string)wire["type"] == "diagnosis.requested", "Wrong request type");
        Require((string)wire["stage_id"]=="electrical","Wrong stage");
        Require(wire["task_type"]==null,"Cached strict Gateway schema must not receive service-only field");
        var worker=AsyncTcadContract.BuildWorkerRequest(wire,job);
        Require((string)worker["task_type"]=="diagnosis","Worker omitted mandatory service task_type");
        Require((double)worker["input_payload"]["measurements"]["gm"]==3.767 && (double)worker["input_payload"]["measurements"]["id_on"]==3.468,"Micro units scaled twice");
        Require((int)worker["input_payload"]["n_wafers"]==25 && !(bool)worker["input_payload"]["refine"],"Wafer count or refine changed");
        var nullBv=JObject.Parse(input); nullBv["measurements"]["bv"]=null;
        Require(AsyncTcadContract.Build(nullBv.ToString(),run,request,"LOT","UNIT")["input_payload"]["measurements"]["bv"].Type==JTokenType.Null,"Unmeasured BV lost");
        nullBv["measurements"].Value<JObject>().Remove("bv");
        Reject(()=>AsyncTcadContract.Build(nullBv.ToString(),run,request,"LOT","UNIT"));
        foreach(var count in new[]{"0","100001","1.5"}) Reject(()=>AsyncTcadContract.Build(input.Replace("25",count),run,request,"LOT","UNIT"));
        Reject(()=>AsyncTcadContract.Build(input.Replace("false","true"),run,request,"LOT","UNIT"));
        Require((bool)wire["input_payload"]["extension"]["keep"], "Unknown model fields discarded");
        Require(wire["tcad_request_id"] == null && wire["input_payload"]["compensation"] == null, "Unity invented routing or TCAD ID");
        Reject(() => AsyncTcadContract.Build("{}", run, request, "LOT", "UNIT"));
        Reject(() => AsyncTcadContract.Build("[]", run, request, "LOT", "UNIT"));
        Reject(() => AsyncTcadContract.Build("{\"x\":1}", "bad", request, "LOT", "UNIT"));
        Reject(() => AsyncTcadContract.Build("{\"x\":1}", run, run, "LOT", "UNIT"));
        var state = new AsyncTcadContract.State(run, request, job);
        Func<int,string,string,JObject> candidate = (index, id, status) => new JObject {
            ["run_id"] = run, ["request_id"] = request, ["job_id"] = job,
            ["proposal_id"] = "94b0302a-1bdb-48c1-ab5b-de2c8989c111", ["tcad_request_id"] = id,
            ["candidate_index"] = index, ["status"] = status
        };
        string first = Guid.NewGuid().ToString(), second = Guid.NewGuid().ToString();
        Func<long,string,JObject,JObject> ev = (seq, type, body) => new JObject {
            ["sequence"] = seq, ["event_id"] = Guid.NewGuid().ToString(), ["run_id"] = run,
            ["event_type"] = type, ["payload"] = body
        };
        var queued = ev(7, "tcad.verification.candidate_queued", candidate(0, first, "queued"));
        Require(state.Accept(queued) && state.Sequence == 7, "Queue event lost");
        Require(!state.Accept(queued), "Replay duplicated");
        state.Accept(ev(8, "tcad.verification.candidate_queued", candidate(1, second, "queued")));
        state.Accept(ev(9, "tcad.verification.candidate_running", candidate(0, first, "running")));
        var succeeded = candidate(0, first, "succeeded");
        succeeded["result_payload"] = new JObject { ["vth"] = 2.4, ["gm"] = 4.5, ["id_on"] = 4.6, ["bv"] = 48 };
        succeeded["metadata"] = new JObject { ["extra_warning"] = "preserve me" };
        state.Accept(ev(10, "tcad.verification.candidate_succeeded", succeeded));
        var failed = candidate(1, second, "failed"); failed["result_payload"] = null; failed["error_code"] = "MOCK_FAILURE";
        state.Accept(ev(11, "tcad.verification.candidate_failed", failed));
        Require(state.Candidates.Count == 2, "Candidates collapsed");
        Require(state.Candidates[second]["result_payload"].Type == JTokenType.Null, "Failure converted to zero");
        Require((string)state.Candidates[first]["metadata"]["extra_warning"] == "preserve me", "Metadata lost");
        var invalid = candidate(0, first, "running"); invalid["job_id"] = Guid.NewGuid().ToString();
        Reject(() => state.Accept(ev(12, "tcad.verification.candidate_running", invalid)));
        Require(state.Sequence == 11, "Invalid event advanced cursor");
        Reject(() => state.Accept(ev(12,"tcad.verification.candidate_succeeded",candidate(0,first,"succeeded"))));
        Reject(() => state.Accept(ev(12,"tcad.verification.candidate_queued",candidate(0,Guid.NewGuid().ToString(),"queued"))));
        Reject(() => state.Accept(ev(12,"tcad.verification.candidate_running",candidate(0,first,"queued"))));
        Require(state.Sequence==11,"Rejected candidate advanced cursor");
        var alien = ev(12, "tcad.verification.candidate_running", candidate(0, first, "running")); alien["run_id"] = Guid.NewGuid().ToString();
        Require(!state.Accept(alien) && state.Sequence == 11, "Other RUN accepted");
        state.Accept(ev(12, "tcad.verification.batch_completed", new JObject { ["request_id"] = request, ["job_id"] = job, ["proposal_id"] = succeeded["proposal_id"], ["success_count"] = 1 }));
        Require(state.Batch != null && state.Candidates.Count == 2, "Batch erased candidate results");
        state.Accept(ev(13, "tcad.verification.candidate_cancelled", candidate(2, Guid.NewGuid().ToString(), "cancelled")));
        state.Accept(ev(14, "tcad.verification.review_required", new JObject { ["request_id"] = request, ["job_id"] = job, ["proposal_id"] = succeeded["proposal_id"] }));
        Require(state.Review != null, "Review event lost");
        var diagnosis = new JObject { ["request_id"]=request,["job_id"]=job,["response"]=new JObject {
            ["status"]="succeeded",["anomaly_detected"]=true,["tcad_proposal"]=null,
            ["result_payload"]=new JObject { ["compensation"]=new JObject { ["route"]="apply",["target_process_parameters"]=new JObject { ["body_dose"]=7.01e12 } } }
        } };
        state.Accept(ev(15,"diagnosis.completed",diagnosis));
        Require((string)state.Diagnosis["result_payload"]["compensation"]["route"]=="apply" && state.Candidates.Count==3,"Apply route invented candidate or lost response");
        return "ASYNC_TCAD_CONTRACT_OK: measurements / micro units unchanged / explicit null BV / n_wafers / refine=false / Gateway-to-Worker task_type projection / apply route preserved without auto-apply / IDs / multiple candidates / replay / null failure / metadata / batch. Offline fixtures only.";
    }
}
