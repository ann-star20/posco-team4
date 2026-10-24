using System;
using UnityEngine;

public static class GatewayLotConditions
{
    [Serializable] public class Condition
    {
        public string lot_id,source,dose_unit,epi_unit,approved_proposal_id;
        public double body_dose,epi_doping;
        public double oxide_reference_um;
    }
    [Serializable] class Table {public Condition[] lots;}
    public static Condition Resolve(string json,string lot)
    {
        var table=JsonUtility.FromJson<Table>(json);
        var matches=table?.lots==null?new Condition[0]:Array.FindAll(table.lots,c=>c!=null&&c.lot_id==lot);
        if(matches.Length!=1||!GatewayInspectionProtocol.Positive(matches[0].body_dose)||!GatewayInspectionProtocol.Positive(matches[0].epi_doping)||
            matches[0].dose_unit!="cm^-2"||matches[0].epi_unit!="cm^-3"||string.IsNullOrWhiteSpace(matches[0].source))
            throw new ArgumentException("LOT "+lot+"의 도즈·에피 공정조건 등록이 필요합니다. 다른 LOT 값으로 대체하지 않습니다.");
        return matches[0];
    }
    static readonly System.Collections.Generic.Dictionary<string,Condition> simulationLots=new System.Collections.Generic.Dictionary<string,Condition>();
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]static void ResetSimulationLots()=>simulationLots.Clear();
    public static void RegisterSimulationLot(string lot,Condition template)
    {
        if(!lot.StartsWith("SIM-LOT-",StringComparison.Ordinal)||template==null)throw new ArgumentException("Explicit simulation LOT/reference required");
        var condition=JsonUtility.FromJson<Condition>(JsonUtility.ToJson(template));condition.lot_id=lot;
        condition.source+="; explicit new simulated LOT, same TCAD reference recipe";simulationLots[lot]=condition;
    }
    public static Condition ForLot(string lot)
    {
        var pinned=DemoApprovedLotRecipes.Pinned(lot);if(pinned!=null)return pinned;
        if(simulationLots.TryGetValue(lot,out var simulated))return JsonUtility.FromJson<Condition>(JsonUtility.ToJson(simulated));
        var asset=Resources.Load<TextAsset>("GatewayLotConditions");
        if(!asset)throw new ArgumentException("Gateway LOT 공정조건 파일이 없습니다.");
        return Resolve(asset.text,lot);
    }
}
