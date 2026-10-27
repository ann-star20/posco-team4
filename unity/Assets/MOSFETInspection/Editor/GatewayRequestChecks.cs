#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class GatewayRequestChecks
{
    static GatewayRequestChecks(){EditorApplication.update+=Tick;}
    static void Check(bool value,string why){if(!value)throw new Exception(why);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode||!File.Exists("GatewayRequestCheck.once"))return;
        File.Delete("GatewayRequestCheck.once");
        try
        {
            var selection=new JetsonTestDataProtocol.Selection{measurement_source="TCAD",dataset_sha256=new string('a',64),wafer_key="SIM-TEST",row=new JetsonTestDataProtocol.Row{
                id="TEST-ONLY",dose_ratio=1.25f,epi_doping_ratio=1.5f,oxide_ratio=.75f,has_tcad=true,
                tcad=new JetsonTestDataProtocol.Measurement{vth=2.2f,gm=1e-6f,id4v=2e-6f,bv=41}}};
            var readings=new[]{75f,75f,75f};
            var request=GatewayInspectionProtocol.Build(selection,"LOT-TEST","SIM-TEST","INSPECT-TEST",readings,8e12,2e16,.08);
            Check(request.input_payload.process_parameters.body_dose==1e13,"Dose scale incorrect");
            Check(request.input_payload.process_parameters.epi_doping==3e16,"Epi scale incorrect");
            Check(Math.Abs(request.input_payload.process_parameters.oxide_thickness-.06)<1e-12,"Micrometre scale incorrect");
            selection.row.oxide_ratio=9;readings[0]=999;
            Check(request.input_payload.provenance.oxide_ratio==.75f&&request.input_payload.provenance.scene_readings_nm[0]==75,"Inspection snapshot mutated");
            Check(Guid.TryParse(request.request_id,out _)&&Guid.TryParse(request.run_id,out _)&&request.request_id!=request.run_id,"IDs not independent UUIDs");
            string wire=JsonUtility.ToJson(request);
            Check(wire.Contains("surrogate.requested")&&!wire.Contains("api_token")&&!wire.Contains("X-Unity-Token"),"Incorrect envelope or token stored in body");
            var again=JsonUtility.FromJson<GatewayInspectionProtocol.Request>(wire);
            Check(again.input_payload.process_parameters.epi_doping==3e16,"Large numeric value corrupted");
            bool rejected=false;try{GatewayInspectionProtocol.Build(selection,"LOT-TEST","SIM-TEST","INSPECT",null,0,1,1);}catch(ArgumentException){rejected=true;}
            Check(rejected,"Unconfirmed baseline silently defaulted");
            var e=new GatewayStreamClient.DbEvent{run_id=request.run_id,payload=new GatewayStreamClient.Payload{lot_id=request.lot_id,unit_id=request.unit_id,request_id=request.request_id}};
            Check(GatewayInspectionProtocol.Matches(request,e),"Matching result rejected");
            e.payload.request_id=Guid.NewGuid().ToString();Check(!GatewayInspectionProtocol.Matches(request,e),"Wrong request accepted");
            e.payload.request_id=request.request_id;e.payload.lot_id="OTHER";Check(!GatewayInspectionProtocol.Matches(request,e),"Wrong LOT accepted");
            e.payload.lot_id=request.lot_id;e.run_id=Guid.NewGuid().ToString();Check(!GatewayInspectionProtocol.Matches(request,e),"Wrong run accepted");
            Check(!GatewayInspectionProtocol.Matches(request,null),"Null result accepted");
            string ack="{\"type\":\"request.accepted\",\"status\":\"queued\",\"request_id\":\""+request.request_id+"\",\"job_id\":\""+Guid.NewGuid()+"\"}";
            Check(GatewayInspectionProtocol.ParseAccepted(ack,request).status=="queued","Queued ack rejected");
            rejected=false;try{GatewayInspectionProtocol.ParseAccepted(ack.Replace(request.request_id,Guid.NewGuid().ToString()),request);}catch(FormatException){rejected=true;}
            Check(rejected,"Unrelated accepted response accepted");
            Check(GatewayInspectionBridge.ControlUri("ws://127.0.0.1:8000/api/v1/stream",request.run_id).ToString()=="ws://127.0.0.1:8000/api/v1/control","Control URL mismatch");
            var physical=GatewayInspectionProtocol.BuildPhysical(selection,"LOT-TEST","SIM-TEST","PHYSICAL",null,8e12,2e16,.08);
            Check(physical.input_payload.process_parameters.body_dose==8e12&&physical.input_payload.process_parameters.epi_doping==2e16&&physical.input_payload.process_parameters.oxide_thickness==.08,"Physical values multiplied by CSV ratios");
            Check(physical.input_payload.provenance.data_source=="manual_physical_input"&&physical.input_payload.provenance.dose_unit=="cm^-2"&&physical.input_payload.provenance.epi_unit=="cm^-3"&&physical.input_payload.provenance.oxide_unit=="um","Physical unit provenance lost");
            Check(GatewayInspectionProtocol.BuildPhysical(null,"LOT-TEST","SIM-TEST","PHYSICAL",null,8e12,2e16,.08).input_payload.process_parameters.oxide_thickness==.08,"Physical input still requires CSV");
            var micro=new GatewayStreamClient.Result{vth=2.2,gm=4.6,id_on=5.2,bv=41,vth_present=true,gm_present=true,bv_present=true};
            string label=GatewayInspectionProtocol.ResultText(micro,true,false,false);
            Check(label.Contains("gm 4.6 µS/µm")&&label.Contains("id_on 5.2 µA/µm")&&micro.gm==4.6&&micro.id_on==5.2,"Gateway micro units converted twice");
            Check(!GatewayInspectionProtocol.ResultText(micro,true,false,true).Contains("µA"),"Normalized fixture assigned physical units");
            Check(GatewayInspectionProtocol.ResultText(micro,false,true,false).Contains("단위 미확인"),"Legacy id silently treated as id_on");
            File.WriteAllText("GatewayRequestCheck.result","GATEWAY_REQUEST_PROTOCOL_OK\nCSV scaling / frozen snapshot / UUIDs / request correlation / large numbers / no token in JSON / accepted-is-queued / endpoint checked\nPhysical input unchanged / physical input without CSV / unit provenance / micro results unchanged / mock remains unitless / legacy id distinct\nOffline tests only; no team Gateway job submitted");
        }
        catch(Exception error){File.WriteAllText("GatewayRequestCheck.result",error.ToString());}
    }
}
#endif
