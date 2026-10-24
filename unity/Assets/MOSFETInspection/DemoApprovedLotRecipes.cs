using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

// shortcut: real TCAD provenance is operator-confirmed for this demonstration, not server-attested.
public static class DemoApprovedLotRecipes
{
    [Serializable] class Ledger
    {
        public List<GatewayApprovedRecipe.Approval> approvals=new List<GatewayApprovedRecipe.Approval>();
        public List<GatewayLotConditions.Condition> lots=new List<GatewayLotConditions.Condition>();
    }
    static Ledger state;
    public static string TestPath;
    static string PathName=>TestPath??Path.Combine(Application.persistentDataPath,"demo-approved-lot-recipes.json");
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    public static void Reload(){state=null;}
    static T Copy<T>(T value)=>JsonUtility.FromJson<T>(JsonUtility.ToJson(value));
    static void Load()
    {
        if(state!=null)return;
        var loaded=File.Exists(PathName)?JsonUtility.FromJson<Ledger>(File.ReadAllText(PathName)):new Ledger();
        if(loaded?.approvals==null||loaded.lots==null)throw new IOException("시연 승인값 저장 파일 확인 필요");
        foreach(var a in loaded.approvals)
        {
            GatewayApprovedRecipe.Validate(a,a.run_id,a.lot_id,a.proposal_id,a.selected_tcad_request_id);
            if(!a.real_tcad_confirmed_by_operator)throw new IOException("관리자 실제 TCAD 확인 기록 누락");
        }
        state=loaded;
    }
    static void Save(Ledger next)
    {
        string path=PathName;Directory.CreateDirectory(Path.GetDirectoryName(path));
        File.WriteAllText(path+".tmp",JsonUtility.ToJson(next,true));
        if(File.Exists(path))File.Replace(path+".tmp",path,path+".bak");else File.Move(path+".tmp",path);
        state=next;
    }
    public static void Remember(GatewayApprovedRecipe.Approval approval)
    {
        Load();GatewayApprovedRecipe.Validate(approval,approval.run_id,approval.lot_id,approval.proposal_id,approval.selected_tcad_request_id);
        if(!approval.real_tcad_confirmed_by_operator)throw new ArgumentException("실제 TCAD 결과 관리자 확인 필요");
        var prior=state.approvals.FirstOrDefault(a=>a.proposal_id==approval.proposal_id);
        if(prior!=null)
        {
            if(prior.selected_tcad_request_id!=approval.selected_tcad_request_id||!GatewayTcadApprovalProtocol.Same(prior.process_parameters,approval.process_parameters))throw new ArgumentException("저장된 승인 후보/공정값과 불일치");
            return;
        }
        var next=Copy(state);next.approvals.Add(Copy(approval));Save(next);
    }
    public static GatewayLotConditions.Condition Pinned(string lot)
    {Load();var found=state.lots.FirstOrDefault(c=>c.lot_id==lot);return found==null?null:Copy(found);}
    public static GatewayLotConditions.Condition BeginLot(string lot)
    {
        var pinned=Pinned(lot);if(pinned!=null)return pinned;
        GatewayLotConditions.Condition condition;
        try{condition=GatewayLotConditions.ForLot(lot);}
        catch(ArgumentException){if(state.approvals.Count==0)return null;throw;}
        var approved=state.approvals.LastOrDefault();
        if(approved!=null&&approved.lot_id!=lot)
        {
            var p=approved.process_parameters;
            condition.body_dose=p.body_dose;condition.epi_doping=p.epi_doping;condition.oxide_reference_um=p.oxide_thickness;
            condition.approved_proposal_id=approved.proposal_id;
            condition.source="simulation recipe; real TCAD operator-confirmed; proposal="+approved.proposal_id+"; candidate="+approved.selected_tcad_request_id;
        }
        var next=Copy(state);next.lots.Add(Copy(condition));Save(next);return Copy(condition);
    }
}
