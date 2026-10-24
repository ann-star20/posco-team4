using System;
using System.Globalization;
using UnityEngine;

public static class GatewayInspectionProtocol
{
    [Serializable] public class Parameters {public double body_dose,epi_doping,oxide_thickness;}
    [Serializable] public class Provenance
    {
        public string equipment_id;
        public double completed_dose_cm2;
        public string data_source="jetson_csv_test",sample_id,csv_sha256,electrical_source,inspection_id;
        public string dose_unit="cm^-2",epi_unit="cm^-3",oxide_unit="um",process_origin="synthetic_csv_ratios",scene_thickness_origin="simulation",condition_source;
        [NonSerialized] public float dose_ratio,epi_ratio,oxide_ratio;
        public GatewayTcadProtocol.Context tcad;
        public float[] scene_readings_nm;
    }
    [Serializable] public class Input
    {
        public Parameters process_parameters;
        public string[] requested_outputs={"vth","gm","id_on","bv"};
        public Provenance provenance;
    }
    [Serializable] public class Request
    {
        public string type="surrogate.requested";
        public int schema_version=1;
        public string request_id,run_id,lot_id,unit_id,stage_id="electrical";
        public int stage_attempt=1;
        public string model_contract_version="fab-ml-v1";
        public Input input_payload;
    }
    [Serializable] public class Accepted {public string type,request_id,job_id,status;}
    public static bool Positive(double v)=>!double.IsNaN(v)&&!double.IsInfinity(v)&&v>0;
    public static Request Build(JetsonTestDataProtocol.Selection selection,string lot,string unit,string inspection,float[] readings,double dose,double epi,double oxideUm)
        =>Create(selection,lot,unit,inspection,readings,dose,epi,oxideUm,true);
    public static Request BuildPhysical(JetsonTestDataProtocol.Selection selection,string lot,string unit,string inspection,float[] readings,double dose,double epi,double oxideUm)
        =>Create(selection,lot,unit,inspection,readings,dose,epi,oxideUm,false);
    public static Request BuildAutomatic(GatewayInspectionSnapshot snapshot,GatewayLotConditions.Condition condition)
    {
        if(snapshot==null||condition==null||snapshot.lot_id!=condition.lot_id||!Positive(snapshot.oxide_thickness_um)||condition.dose_unit!="cm^-2"||condition.epi_unit!="cm^-3")
            throw new ArgumentException("완료된 검사와 같은 LOT의 공정조건이 필요합니다.");
        double dose=condition.body_dose,epi=condition.epi_doping;
        if(snapshot.has_csv_ratios)
        {
            if(!Positive(snapshot.csv_dose_ratio)||!Positive(snapshot.csv_epi_ratio)||!Positive(snapshot.csv_oxide_ratio)||!Positive(condition.oxide_reference_um)||
                Math.Abs(snapshot.reference_thickness_nm-condition.oxide_reference_um*1000)>.001)
                throw new ArgumentException("CSV 기준 두께가 TCAD 모델과 다릅니다. 기존 웨이퍼 입력을 해제하고 60 nm 기준으로 새 시험 웨이퍼를 준비하세요.");
            dose*=snapshot.csv_dose_ratio;epi*=snapshot.csv_epi_ratio;
        }
        var request=BuildPhysical(null,snapshot.lot_id,snapshot.unit_id,snapshot.inspection_id,snapshot.thickness_points_nm,dose,epi,snapshot.oxide_thickness_um);
        var p=request.input_payload.provenance;
        p.data_source=snapshot.data_source;p.process_origin=snapshot.has_csv_ratios?"tcad_reference_times_csv_ratios_and_completed_inspection":"registered_lot_conditions_and_completed_inspection";p.condition_source=condition.source;
        if(snapshot.has_csv_ratios){p.dose_ratio=(float)snapshot.csv_dose_ratio;p.epi_ratio=(float)snapshot.csv_epi_ratio;p.oxide_ratio=(float)snapshot.csv_oxide_ratio;}
        p.sample_id=snapshot.csv_sample_id;p.csv_sha256=snapshot.csv_sha256;p.electrical_source=snapshot.electrical_source;
        return request;
    }
    static Request Create(JetsonTestDataProtocol.Selection selection,string lot,string unit,string inspection,float[] readings,double dose,double epi,double oxideUm,bool ratios)
    {
        if(ratios&&(selection?.row==null||!JetsonTestDataProtocol.CanSelect(selection.row,selection.measurement_source)))throw new ArgumentException("이 검사에 고정된 CSV 입력이 없습니다.");
        if(string.IsNullOrWhiteSpace(lot)||string.IsNullOrWhiteSpace(unit)||string.IsNullOrWhiteSpace(inspection))throw new ArgumentException("LOT・웨이퍼・검사 ID 필요");
        var row=selection?.row;
        var p=new Parameters{body_dose=ratios?dose*row.dose_ratio:dose,epi_doping=ratios?epi*row.epi_doping_ratio:epi,oxide_thickness=ratios?oxideUm*row.oxide_ratio:oxideUm};
        if(!Positive(dose)||!Positive(epi)||!Positive(oxideUm)||!Positive(p.body_dose)||!Positive(p.epi_doping)||!Positive(p.oxide_thickness))throw new ArgumentException("모델 입력값과 단위를 확인하세요.");
        return new Request{request_id=Guid.NewGuid().ToString(),run_id=Guid.NewGuid().ToString(),lot_id=lot,unit_id=unit,
            input_payload=new Input{process_parameters=p,provenance=new Provenance{sample_id=row?.id,csv_sha256=selection?.dataset_sha256,
                data_source=ratios?"jetson_csv_test":"manual_physical_input",process_origin=ratios?"synthetic_csv_ratios":"manual_physical_values",
                electrical_source=selection?.measurement_source,inspection_id=inspection,dose_ratio=row?.dose_ratio??1,epi_ratio=row?.epi_doping_ratio??1,oxide_ratio=row?.oxide_ratio??1,
                scene_readings_nm=readings==null?null:(float[])readings.Clone()}}};
    }
    public static string ResultText(GatewayStreamClient.Result value,bool hasIdOn,bool hasId,bool mock)
    {
        if(value==null)return "전기특성 예측 결과 없음";
        string N(double n)=>n.ToString("G8",CultureInfo.InvariantCulture);
        string current=hasIdOn?"id_on "+N(value.id_on)+(mock?"":" µA/µm"):hasId?"id "+N(value.id)+" (단위 미확인)":"id_on 미수신";
        return "Vth "+(value.vth_present?N(value.vth):"—")+(mock?"":" V")+" / gm "+(value.gm_present?N(value.gm):"—")+(mock?"":" µS/µm")+" / "+current+" / BV "+(value.bv_present?N(value.bv):"—")+(mock?"":" V");
    }
    public static string ErrorCode(GatewayStreamClient.Response response)=>!string.IsNullOrWhiteSpace(response?.error_code)?response.error_code:response?.error?.code;
    public static string ErrorMessage(GatewayStreamClient.Response response)=>!string.IsNullOrWhiteSpace(response?.error_message)?response.error_message:response?.error?.message;
    public static string FailureTitle(GatewayStreamClient.Response response)=>ErrorCode(response)=="OUT_OF_DOMAIN"?"모델 학습 범위 밖 · 전기특성 예측 결과 없음":"서버 분석 실패 · 전기특성 예측 결과 없음";
    public static bool Matches(Request r,GatewayStreamClient.DbEvent e)
    {
        var p=e?.payload;
        string request=p?.request_id??p?.response?.request_id;
        return r!=null&&e!=null&&p!=null&&e.run_id==r.run_id&&request==r.request_id&&p.lot_id==r.lot_id&&
            (string.IsNullOrEmpty(p.unit_id)||p.unit_id==r.unit_id);
    }
    public static Accepted ParseAccepted(string raw,Request request)
    {
        var ack=JsonUtility.FromJson<Accepted>(raw);
        if(ack==null||ack.type!="request.accepted"||ack.request_id!=request.request_id||!Guid.TryParse(ack.job_id,out _)||ack.status!="queued")throw new FormatException("요청 접수 응답 불일치 · 같은 요청 ID로 서버 기록을 확인하세요.");
        return ack;
    }
}
