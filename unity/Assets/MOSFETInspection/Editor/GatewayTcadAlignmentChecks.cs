#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class GatewayTcadAlignmentChecks
{
    // Historical calibration evidence contains evaluation truth; current model requests deliberately omit it.
    [Serializable] class HistoricalRatios {public float dose_ratio,epi_ratio,oxide_ratio;}
    [Serializable] class HistoricalInput {public GatewayInspectionProtocol.Parameters process_parameters;public HistoricalRatios provenance;}
    [Serializable] class HistoricalRequest {public HistoricalInput input_payload;}
    [Serializable] class Verification {public HistoricalRequest request;public GatewayStreamClient.DbEvent @event;}
    static GatewayTcadAlignmentChecks(){EditorApplication.update+=Tick;}
    static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode||!File.Exists("GatewayTcadAlignmentCheck.once"))return;
        File.Delete("GatewayTcadAlignmentCheck.once");
        try
        {
            var recipe=AssetDatabase.LoadAssetAtPath<FilmInspectionRecipe>("Assets/MOSFETInspection/Settings/FilmInspectionDemo.asset");
            Check(recipe&&recipe.targetNm==60&&recipe.lowerNm==57&&recipe.upperNm==63,"Scene recipe not aligned to 60 nm / +/-5% demo rule");
            Check(recipe.Evaluate(recipe.passDemo,out _)=="PASS"&&recipe.Evaluate(recipe.highDemo,out _)=="FAIL"&&recipe.Evaluate(recipe.lowDemo,out _)=="FAIL","Default demo cases lost PASS/FAIL distinction");
            var cycle=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();Check(cycle&&cycle.recipe==recipe,"Open scene uses a different recipe");
            var condition=GatewayLotConditions.ForLot("LOT-001");Check(condition.oxide_reference_um==.06,"Missing confirmed oxide reference");
            int count=0;
            foreach(string path in Directory.GetFiles("Tools/Gateway/AlignmentChecks","B*.json"))
            {
                var live=JsonUtility.FromJson<Verification>(File.ReadAllText(path));
                Check(live.@event.payload.response.status=="succeeded"&&live.@event.payload.response.result_origin=="prod","Live verification was not a real-model success");
                var reference=live.request.input_payload.provenance;
                float thickness=60*reference.oxide_ratio;
                var s=GatewayInspectionSnapshot.Create("CHECK","LOT-001","SIM-CHECK",new[]{thickness,thickness,thickness},null,false);
                s.has_csv_ratios=true;s.csv_dose_ratio=reference.dose_ratio;s.csv_epi_ratio=reference.epi_ratio;s.csv_oxide_ratio=reference.oxide_ratio;s.reference_thickness_nm=60;
                var actual=GatewayInspectionProtocol.BuildAutomatic(s,condition).input_payload.process_parameters;
                var expected=live.request.input_payload.process_parameters;
                Check(Math.Abs(actual.body_dose/expected.body_dose-1)<1e-6&&Math.Abs(actual.epi_doping/expected.epi_doping-1)<1e-6&&Math.Abs(actual.oxide_thickness/expected.oxide_thickness-1)<1e-6,"Unity snapshot differs from live server-verified parameters");
                s.reference_thickness_nm=100;bool blocked=false;
                try{GatewayInspectionProtocol.BuildAutomatic(s,condition);}catch(ArgumentException){blocked=true;}
                Check(blocked,"Stale 100 nm CSV selection reused after calibration");count++;
            }
            Check(count>=4,"Expected normal, BV-NG, Vth-NG and thickness-only cases");
            if(!cycle.Running){cycle.SetCsvTest(null);if(cycle.dashboard)cycle.dashboard.Refresh();}
            File.WriteAllText("GatewayTcadAlignmentCheck.result","GATEWAY_TCAD_ALIGNMENT_OK\nScene recipe 60 nm / 57-63 demo limits / default PASS-HIGH-LOW preserved\nUnity parameters match four real Gateway prod/succeeded cases / CSV dose-epi ratios preserved / stale 100 nm selection blocked\nNo new Gateway jobs sent by this Editor check; model service verified separately");
        }
        catch(Exception e){File.WriteAllText("GatewayTcadAlignmentCheck.result",e.ToString());}
    }
}
#endif
