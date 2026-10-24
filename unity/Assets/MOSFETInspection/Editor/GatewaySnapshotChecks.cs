#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;

[InitializeOnLoad]
public static class GatewaySnapshotChecks
{
    static GatewaySnapshotChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode||!File.Exists("GatewaySnapshotCheck.once"))return;
        File.Delete("GatewaySnapshotCheck.once");
        try
        {
            var points=new[]{99f,100f,101f};
            var input=new ProcessAnalysisView.Input{lot_id="LOT-A",n_wafers=1,measurement=new ProcessAnalysisView.Measurement{vth=2.2f,gm=4.6e-6f,id4v=5.2e-6f,bv=41}};
            var s=GatewayInspectionSnapshot.Create("INSPECT-A","LOT-A","WAFER-A",points,input,true);
            Check(s.thickness_mean_nm==100&&Math.Abs(s.oxide_thickness_um-.1)<1e-12,"Equipment nm-to-um conversion failed");
            Check(Math.Abs(s.electrical.gm_us_per_um-4.6)<1e-5&&Math.Abs(s.electrical.id4v_ua_per_um-5.2)<1e-5,"CSV A-to-micro conversion failed");
            points[0]=999;input.measurement.gm=999;
            Check(s.thickness_points_nm[0]==99&&s.electrical.gm_us_per_um<5,"Frozen inspection changed after capture");
            Check(s.electrical.current_quantity=="id4v","Id4V incorrectly relabeled as id_on");
            string conditions="{\"lots\":[{\"lot_id\":\"LOT-A\",\"body_dose\":7700000000000,\"epi_doping\":17000000000000000,\"dose_unit\":\"cm^-2\",\"epi_unit\":\"cm^-3\",\"source\":\"test configured conditions\"}]}";
            var condition=GatewayLotConditions.Resolve(conditions,"LOT-A");
            var automatic=GatewayInspectionProtocol.BuildAutomatic(s,condition);
            Check(automatic.input_payload.process_parameters.body_dose==7700000000000&&automatic.input_payload.process_parameters.epi_doping==17000000000000000,"Registered conditions changed");
            Check(Math.Abs(automatic.input_payload.process_parameters.oxide_thickness-.1)<1e-12,"Target/example thickness used instead of measured mean");
            Check(automatic.input_payload.provenance.scene_readings_nm[0]==99&&automatic.input_payload.provenance.data_source=="simulation","Inspection/source lost in Gateway request");
            bool unknownRejected=false;try{GatewayLotConditions.Resolve(conditions,"LOT-OTHER");}catch(ArgumentException){unknownRejected=true;}
            Check(unknownRejected,"Other LOT silently reused configured conditions");
            unknownRejected=false;try{GatewayInspectionProtocol.BuildAutomatic(s,new GatewayLotConditions.Condition{lot_id="LOT-OTHER",body_dose=1,epi_doping=1,dose_unit="cm^-2",epi_unit="cm^-3"});}catch(ArgumentException){unknownRejected=true;}
            Check(unknownRejected,"Other LOT conditions attached to inspection");
            var thicknessOnly=GatewayInspectionSnapshot.Create("INSPECT-B","LOT-B",null,new[]{70f,70f,70f},null,false);
            Check(thicknessOnly.electrical==null&&thicknessOnly.unit_id.StartsWith("SIM-"),"Missing measurements fabricated");
            bool rejected=false;try{GatewayInspectionSnapshot.Create("I","L","W",new[]{float.NaN,100,100},null,false);}catch(ArgumentException){rejected=true;}
            Check(rejected,"Pending thickness accepted");
            input.lot_id="OTHER";rejected=false;try{GatewayInspectionSnapshot.Create("I","L","W",new[]{100f,100f,100f},input,true);}catch(ArgumentException){rejected=true;}
            Check(rejected,"Other LOT electrical data accepted");
            File.WriteAllText("GatewaySnapshotCheck.result","GATEWAY_SNAPSHOT_OK\nCompleted equipment values / nm-to-um / A-to-micro / frozen snapshot / missing-data handling / LOT isolation / id4v identity\nAutomatic request uses measured mean, not target or example / registered LOT conditions preserved / unknown LOT blocked\nOffline only; no Gateway job submitted");
        }
        catch(Exception e){File.WriteAllText("GatewaySnapshotCheck.result",e.ToString());}
    }
}
#endif
