using System;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEngine;

public static class GatewayTcadApprovalProtocol
{
    [Serializable] public class Verdict {public string overall,spec_source;}
    [Serializable] public class Outputs {public double vth,gm,id_on,bv;}
    [Serializable] public class Candidate {public string tcad_request_id;public int candidate_index;public GatewayFullCycleProtocol.Parameters process_parameters;public Outputs result_payload;public Verdict spec_verdict;}
    [Serializable] public class Proposal {public string proposal_id,job_id,run_id,status,created_at;public Candidate[] candidates;}
    [Serializable] public class ListResponse {public Proposal[] proposals;}
    [Serializable] public class DecisionRequest {public string decided_by,decision,selected_tcad_request_id;}
    [Serializable] class RejectRequest {public string decided_by,decision="rejected";}
    [Serializable] public class DecisionResponse {public string proposal_id,status;public GatewayFullCycleProtocol.Parameters process_parameters;}
    [Serializable] public class Notification {public string proposal_id,decision,status,selected_tcad_request_id,decided_by;public GatewayFullCycleProtocol.Parameters process_parameters;}
    [Serializable] public class Event {public string event_id,run_id,event_type;public long sequence;public Notification payload;}
    static void Require(bool ok,string why){if(!ok)throw new ArgumentException(why);}
    public static Uri Address(string stream,string suffix)
    {
        var checkedUri=GatewayStreamClient.StreamUri(stream,Guid.NewGuid().ToString(),0);
        return new UriBuilder(checkedUri){Scheme=checkedUri.Scheme=="wss"?"https":"http",Path="/api/v1/tcad/proposals"+suffix,Query=""}.Uri;
    }
    public static ListResponse ReadList(string raw)
    {
        // An absent BV is explicit in spec_verdict; normalize only its nullable numeric slot for JsonUtility.
        raw=Regex.Replace(raw,"\"bv\"\\s*:\\s*null","\"bv\":0");
        var list=JsonUtility.FromJson<ListResponse>(raw);Require(list?.proposals!=null,"Gateway 후보 목록 형식 확인 필요");
        foreach(var p in list.proposals)
        {
            Require(p!=null&&Guid.TryParse(p.proposal_id,out _)&&Guid.TryParse(p.run_id,out _)&&Guid.TryParse(p.job_id,out _)&&p.candidates!=null,"후보 그룹 식별자/목록 오류");
            Require(p.candidates.All(c=>c!=null&&Guid.TryParse(c.tcad_request_id,out _))&&p.candidates.Select(c=>c.tcad_request_id).Distinct().Count()==p.candidates.Length,"후보 식별자 중복/오류");
            p.candidates=p.candidates.OrderByDescending(Eligible).ThenBy(c=>c.candidate_index).ToArray();
        }
        return list;
    }
    public static bool Eligible(Candidate c)=>c?.spec_verdict?.overall=="in_spec";
    public static bool Positive(GatewayFullCycleProtocol.Parameters p)=>p!=null&&GatewayInspectionProtocol.Positive(p.body_dose)&&GatewayInspectionProtocol.Positive(p.epi_doping)&&GatewayInspectionProtocol.Positive(p.oxide_thickness);
    public static bool Same(GatewayFullCycleProtocol.Parameters a,GatewayFullCycleProtocol.Parameters b)
    {
        bool Eq(double x,double y)=>Math.Abs(x-y)<=Math.Max(Math.Abs(x),Math.Abs(y))*1e-8;
        return Positive(a)&&Positive(b)&&Eq(a.body_dose,b.body_dose)&&Eq(a.epi_doping,b.epi_doping)&&Eq(a.oxide_thickness,b.oxide_thickness);
    }
    public static string Body(string actor,string candidate,bool approve)
    {
        Require(!string.IsNullOrWhiteSpace(actor),"승인자명을 입력하세요.");
        if(!approve)return JsonUtility.ToJson(new RejectRequest{decided_by=actor.Trim()});
        Require(Guid.TryParse(candidate,out _),"승인 후보를 선택하세요.");
        return JsonUtility.ToJson(new DecisionRequest{decided_by=actor.Trim(),decision="approved",selected_tcad_request_id=candidate});
    }
    public static GatewayApprovedRecipe.Approval Confirm(string raw,Proposal group,Candidate selected,string run,string lot,string actor)
    {
        var response=JsonUtility.FromJson<DecisionResponse>(raw);
        Require(group!=null&&group.run_id==run&&(group.status=="review_required"||group.status=="approved")&&selected!=null&&group.candidates.Contains(selected)&&Eligible(selected),"승인 대상 검사·후보 확인 필요");
        Require(response?.proposal_id==group.proposal_id&&response.status=="approved"&&Same(response.process_parameters,selected.process_parameters),"승인 응답의 그룹/공정값 불일치 · 자동 적용하지 않음");
        return new GatewayApprovedRecipe.Approval{proposal_id=group.proposal_id,run_id=run,lot_id=lot,selected_tcad_request_id=selected.tcad_request_id,decision="approved",decided_by=actor,process_parameters=response.process_parameters};
    }
}
