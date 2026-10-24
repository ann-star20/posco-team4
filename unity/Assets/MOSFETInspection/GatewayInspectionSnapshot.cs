using System;

// Values from one completed inspection, independent of the Gateway worker's input schema.
[Serializable]
public class GatewayInspectionSnapshot
{
    public string inspection_id,lot_id,unit_id,equipment_id="ELLIP-01",data_source="simulation",completed_at,verdict;
    public float[] thickness_points_nm;
    public double thickness_mean_nm,oxide_thickness_um,target_nm,lower_nm,upper_nm;
    public string electrical_source,csv_sample_id,csv_sha256;
    public int n_wafers;
    public bool has_csv_ratios;
    public double csv_dose_ratio,csv_epi_ratio,csv_oxide_ratio,reference_thickness_nm;
    public Electrical electrical;
    [Serializable] public class Electrical
    {
        public double vth_v,gm_us_per_um,id4v_ua_per_um,bv_v;
        public bool has_bv;
        public string current_quantity="id4v",original_gm_unit="A/V/um",original_current_unit="A/um";
    }
    public static GatewayInspectionSnapshot Capture(EllipsometerCycle cycle,LotProcessAnalysis.Record record)
    {
        if(!cycle||record==null||record.source!=cycle||!record.evaluated||record.inspectionId!=cycle.InspectionId||record.lotId!=cycle.lotId||record.superseded)
            throw new ArgumentException("완료된 해당 검사 기록이 필요합니다.");
        var s=Create(cycle.InspectionId,cycle.lotId,cycle.waferId,record.readings,record.electrical,record.hasBv);
        s.verdict=cycle.verdict;s.target_nm=record.target;s.lower_nm=record.lower;s.upper_nm=record.upper;s.electrical_source=cycle.InspectionCsv?.measurement_source??(record.electrical==null?"none":"paired_synthetic");
        var csv=cycle.InspectionCsv;
        s.csv_sample_id=csv?.row?.id;s.csv_sha256=csv?.dataset_sha256;
        if(csv?.row!=null)
        {
            s.has_csv_ratios=true;s.csv_dose_ratio=csv.row.dose_ratio;s.csv_epi_ratio=csv.row.epi_doping_ratio;s.csv_oxide_ratio=csv.row.oxide_ratio;
            s.reference_thickness_nm=csv.reference_target_nm;
        }
        return s;
    }
    public static GatewayInspectionSnapshot Create(string inspection,string lot,string unit,float[] points,ProcessAnalysisView.Input input,bool hasBv)
    {
        if(string.IsNullOrWhiteSpace(inspection)||string.IsNullOrWhiteSpace(lot)||points==null||points.Length!=3)
            throw new ArgumentException("검사 ID·LOT·3지점 측정값이 필요합니다.");
        double sum=0;
        foreach(float point in points)
        {if(!GatewayInspectionProtocol.Positive(point))throw new ArgumentException("산화막 측정 완료 전에는 전송할 수 없습니다.");sum+=point;}
        var snapshot=new GatewayInspectionSnapshot{inspection_id=inspection,lot_id=lot,unit_id=string.IsNullOrWhiteSpace(unit)?"SIM-WAFER-"+inspection:unit,
            thickness_points_nm=(float[])points.Clone(),thickness_mean_nm=sum/3,oxide_thickness_um=sum/3000,
            completed_at=DateTimeOffset.UtcNow.ToString("O"),n_wafers=input?.n_wafers??0};
        if(input!=null)
        {
            var m=input.measurement;
            if(input.lot_id!=lot||m==null||!GatewayInspectionProtocol.Positive(m.vth)||!GatewayInspectionProtocol.Positive(m.gm)||
                !GatewayInspectionProtocol.Positive(m.id4v)||hasBv&&!GatewayInspectionProtocol.Positive(m.bv))throw new ArgumentException("검사에 연결된 전기특성 데이터 오류");
            snapshot.electrical=new Electrical{vth_v=m.vth,gm_us_per_um=(double)m.gm*1e6,id4v_ua_per_um=(double)m.id4v*1e6,bv_v=hasBv?m.bv:0,has_bv=hasBv};
        }
        return snapshot;
    }
    [Serializable] public class InspectionResult
    {
        public string purpose="film_inspection_record",completed_at,verdict,thickness_verdict,electrical_verdict,thickness_unit="nm";
        public double thickness_mean_nm,oxide_thickness_um,target_nm,lower_nm,upper_nm;
        public float[] thickness_points_nm;
        public Electrical electrical;
        public bool diagnosis_requested,correction_candidate=false;
    }
    [Serializable] public class RecordProvenance
    {
        public string equipment_id="ELLIP-01",data_source,sample_id,csv_sha256,electrical_source,inspection_id,condition_source;
        public string process_origin,dose_unit="cm^-2",epi_unit="cm^-3",oxide_unit="um";
        public InspectionResult inspection_result;
    }
    [Serializable] public class RecordInput
    {
        public GatewayInspectionProtocol.Parameters process_parameters;
        public string[] requested_outputs={"vth","gm","id_on","bv"};
        public RecordProvenance provenance;
    }
    [Serializable] public class RecordRequest
    {
        public string type="surrogate.requested",request_id,run_id,lot_id,unit_id,stage_id="film_inspection_record",model_contract_version="fab-ml-v1";
        public int schema_version=1,stage_attempt=1;
        public RecordInput input_payload;
    }
    public static RecordRequest BuildRecord(GatewayInspectionProtocol.Request request,GatewayInspectionSnapshot snapshot)
    {
        if(request?.input_payload?.provenance==null||snapshot==null||request.lot_id!=snapshot.lot_id||
            request.unit_id!=snapshot.unit_id||request.input_payload.provenance.inspection_id!=snapshot.inspection_id||
            !Guid.TryParse(request.request_id,out _)||!Guid.TryParse(request.run_id,out _))throw new ArgumentException("해당 산화막 검사와 요청 연결이 필요합니다.");
        var s=UnityEngine.JsonUtility.FromJson<GatewayInspectionSnapshot>(UnityEngine.JsonUtility.ToJson(snapshot));
        // Keep missing electrical data missing; JsonUtility may construct an empty nested class.
        if(snapshot.electrical==null)s.electrical=null;
        var electrical=s.electrical==null?ElectricalSpec.Verdict.Pending:ElectricalSpec.Evaluate((float)s.electrical.vth_v,s.electrical.has_bv?(float?)s.electrical.bv_v:null);
        bool ng=s.verdict=="FAIL"||electrical==ElectricalSpec.Verdict.NG;
        string verdict=ng?"NG":s.verdict=="PASS"&&electrical==ElectricalSpec.Verdict.OK?"OK":"PENDING";
        var p=request.input_payload.provenance;
        return new RecordRequest{request_id=request.request_id,run_id=request.run_id,lot_id=request.lot_id,unit_id=request.unit_id,
            input_payload=new RecordInput{process_parameters=request.input_payload.process_parameters,provenance=new RecordProvenance{
                data_source=s.data_source,sample_id=s.csv_sample_id,csv_sha256=s.csv_sha256,electrical_source=s.electrical_source,
                inspection_id=s.inspection_id,condition_source=p.condition_source,process_origin=p.process_origin,
                inspection_result=new InspectionResult{completed_at=s.completed_at,verdict=verdict,thickness_verdict=s.verdict=="PASS"?"OK":s.verdict=="FAIL"?"NG":"PENDING",
                    electrical_verdict=electrical.ToString(),thickness_mean_nm=s.thickness_mean_nm,oxide_thickness_um=s.oxide_thickness_um,
                    thickness_points_nm=s.thickness_points_nm,target_nm=s.target_nm,lower_nm=s.lower_nm,upper_nm=s.upper_nm,
                    electrical=s.electrical,diagnosis_requested=ng&&s.electrical!=null&&electrical!=ElectricalSpec.Verdict.Pending}}}};
    }
}
