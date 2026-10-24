using System;
using System.Text.Json.Nodes;
using P=GatewayFullCycleProtocol;

class Program
{
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static string Event(P.State s,long seq,string kind,object payload)=>System.Text.Json.JsonSerializer.Serialize(new{sequence=seq,event_id=Guid.NewGuid().ToString(),run_id=s.Run,event_type=kind,payload});
    static string Prediction(P.State s,long seq=1,double vth=2.874)=>Event(s,seq,"surrogate.completed",new{request_id=s.PredictionId,job_id=Guid.NewGuid().ToString(),response=new{status="succeeded",result_origin="prod",result_payload=new{vth,gm=3.767,id_on=3.468,bv=44.186},metadata=new{units=new{vth="V",gm="uS/um",id_on="uA/um",bv="V"}}}});
    static string Diagnosis(P.State s,string route,long seq=2)=>Event(s,seq,"diagnosis.completed",new{request_id=s.DiagnosisId,job_id=Guid.NewGuid().ToString(),response=new{status="succeeded",result_origin="prod",result_payload=new{decision=new{top_category="oxide",top_probability=.95,decided=true},compensation=new{route,high_confidence=false,target_process_parameters=new{body_dose=7.7e12,epi_doping=1.7e16,oxide_thickness=.06}}}}});
    static P.State New(bool equipmentOk=true,bool originalOk=true)=>new P.State(Guid.NewGuid().ToString(),Guid.NewGuid().ToString(),"LOT-TEST","WAFER-1",equipmentOk,originalOk);
    static void Main(string[] args)
    {
        if(args.Length==2&&args[0]=="--serve"){MockServer.Run(int.Parse(args[1])).GetAwaiter().GetResult();return;}
        var s=New();Check(s.Accept(Prediction(s)),"prediction not accepted");
        Check(s.PendingDiagnosis&&s.Electrical.gm==3.767,"micro units or NG branch");
        var request=JsonNode.Parse(s.DiagnosisJson());
        Check((string)request["run_id"]==s.Run&&(string)request["request_id"]!=s.PredictionId,"correlation IDs");
        Check((double)request["input_payload"]["measurements"]["id_on"]==3.468,"double conversion");
        Check(request["task_type"]==null&&(int)request["input_payload"]["n_wafers"]==1&&!(bool)request["input_payload"]["refine"],"Gateway contract");
        s.Accept(Diagnosis(s,"tcad_verify"));Check(s.WaitingTcad&&!s.Done,"TCAD completed prematurely");
        var proposal=Guid.NewGuid().ToString();var candidate=Guid.NewGuid().ToString();
        string Tcad(long seq,string status)=>Event(s,seq,"tcad.verification.candidate_"+status,new{request_id=s.DiagnosisId,job_id=s.DiagnosisJob,proposal_id=proposal,tcad_request_id=candidate,candidate_index=0,status,result_payload=status=="succeeded"?new{vth=2.4,gm=4.5,id_on=4.6,bv=48.0}:null});
        s.Accept(Tcad(3,"running"));Check(s.Candidates.Count==1&&!s.Done,"candidate running");
        s.Accept(Tcad(4,"succeeded"));Check(!s.Done,"single candidate mistaken for batch");
        Check(!s.Accept(Tcad(4,"running")),"duplicate sequence replay");
        s.Accept(Event(s,5,"tcad.verification.batch_completed",new{request_id=s.DiagnosisId,job_id=s.DiagnosisJob,proposal_id=proposal,status="completed"}));
        Check(s.Done&&s.BatchReceived&&s.Candidates.Count==1&&s.KeepSubscription,"batch completion must retain review subscription");
        s.ObserveReview(proposal);Check(s.KeepSubscription&&!s.DecisionReceived,"review subscription");
        s.ObserveDecision(proposal,"approved");Check(!s.KeepSubscription,"approval subscription terminal");
        foreach(var route in new[]{"apply","manual","no_action"}){var r=New();r.Accept(Prediction(r));r.DiagnosisJson();r.Accept(Diagnosis(r,route));Check(r.Done&&!r.WaitingTcad&&r.Route==route,"route "+route);}
        foreach(bool equipmentOk in new[]{true,false})foreach(bool predictionOk in new[]{true,false})
        {
            var pending=new P.State(Guid.NewGuid().ToString(),Guid.NewGuid().ToString(),"LOT-PENDING","UNIT-1",equipmentOk,false,false);
            Check(!pending.NormalInspection&&!pending.PendingDiagnosis,"Pending was prematurely completed");
            pending.Accept(Prediction(pending,vth:predictionOk?2.260060537596672:2.9));
            bool normal=equipmentOk&&predictionOk;
            Check(pending.NormalInspection==normal&&pending.PendingDiagnosis!=normal,"Original Pending incorrectly acted as NG");
            if(normal)Check(pending.DiagnosisId==null&&!pending.InspectionNg,"Normal created diagnosis or HOLD");
        }
        var ok=New();ok.Accept(Prediction(ok,vth:2.2));Check(ok.Done&&!ok.PendingDiagnosis,"all OK must skip diagnosis");
        foreach(var flags in new[]{(false,true),(true,false),(false,false)}){var r=New(flags.Item1,flags.Item2);r.Accept(Prediction(r,vth:2.2));Check(r.PendingDiagnosis,"equipment or original NG must diagnose");}
        var missing=New();var wire=JsonNode.Parse(Prediction(missing));wire["payload"]["response"]["result_payload"].AsObject().Remove("gm");
        try{missing.Accept(wire.ToJsonString());throw new Exception("missing gm accepted");}catch(FormatException){}
        var wrong=New();var foreign=JsonNode.Parse(Prediction(wrong));foreign["payload"]["request_id"]=Guid.NewGuid().ToString();Check(!wrong.Accept(foreign.ToJsonString()),"foreign request");
        var units=New();var bad=JsonNode.Parse(Prediction(units));bad["payload"]["response"]["metadata"]["units"]["gm"]="A/V/um";
        try{units.Accept(bad.ToJsonString());throw new Exception("SI accepted as micro");}catch(FormatException){}
        var nullBv=New();var nb=JsonNode.Parse(Prediction(nullBv));nb["payload"]["response"]["result_payload"]["bv"]=null;nullBv.Accept(nb.ToJsonString());Check(JsonNode.Parse(nullBv.DiagnosisJson())["input_payload"]["measurements"]["bv"]==null,"explicit null BV");
        var ack=New();string ackJob=Guid.NewGuid().ToString();
        ack.AcceptAck(System.Text.Json.JsonSerializer.Serialize(new{type="request.accepted",request_id=ack.PredictionId,job_id=ackJob}),ack.PredictionId);
        Check(!ack.Done&&ack.Electrical==null,"ACK counted as completion");
        try{ack.AcceptAck("{\"type\":\"request.rejected\",\"code\":\"invalid_request\"}",ack.PredictionId);throw new Exception("Rejected ACK accepted");}catch(FormatException e){Check(e.Message.Contains("invalid_request"),"Rejection reason hidden");}
        try{ack.Accept(Prediction(ack));throw new Exception("Different job accepted");}catch(FormatException){}
        var failed=New();var failure=JsonNode.Parse(Prediction(failed));failure["payload"]["response"]["status"]="failed";
        try{failed.Accept(failure.ToJsonString());throw new Exception("Failed prediction became success");}catch(FormatException){}
        var multi=New();multi.Accept(Prediction(multi));multi.DiagnosisJson();multi.Accept(Diagnosis(multi,"tcad_verify"));
        for(int i=0;i<2;i++)multi.Accept(Event(multi,3+i,"tcad.verification.candidate_running",new{request_id=multi.DiagnosisId,job_id=multi.DiagnosisJob,proposal_id=proposal,tcad_request_id=Guid.NewGuid().ToString(),candidate_index=i,status="running"}));
        Check(multi.Candidates.Count==2&&!multi.Done,"Multiple candidates collapsed");
        Console.WriteLine("FULL_CYCLE_CONTRACT_OK: prediction -> diagnosis -> routes -> TCAD batch / OK skip / equipment NG / units / IDs / replay / null BV");
    }
}
