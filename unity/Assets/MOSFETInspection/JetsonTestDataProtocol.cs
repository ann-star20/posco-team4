using System;
using System.Collections.Generic;

public static class JetsonTestDataProtocol
{
    [Serializable] public class Measurement {public float vth,gm,id4v,bv;public Measurement Snapshot()=>(Measurement)MemberwiseClone();}
    [Serializable] public class Row
    {
        public string id,kind;
        public float dose_ratio,epi_doping_ratio,oxide_ratio;
        public bool has_tcad,has_pc,has_high_precision_vth,has_high_precision_bv;
        public Measurement tcad,pc;
        public float high_precision_vth,high_precision_bv;
        public Row Snapshot(){var copy=(Row)MemberwiseClone();copy.tcad=tcad?.Snapshot();copy.pc=pc?.Snapshot();return copy;}
    }
    [Serializable] public class Dataset
    {
        public int schema_version;
        public string data_source,dataset_sha256,epi_semantics;
        public Row[] rows;
    }
    [Serializable] public class Selection
    {
        public Row row;
        public string measurement_source,dataset_sha256,wafer_key,category;
        public bool automatic;
        public float reference_target_nm;
        public int n_wafers=1;
        public Measurement Measurement=>measurement_source=="TCAD"?row.tcad:row.pc;
        public string Label=>(automatic?"CSV 자동 시연 · ":"CSV ")+row.id+" / "+measurement_source;
    }
    public class AutoSequence
    {
        readonly Dictionary<string,Selection> assigned=new Dictionary<string,Selection>();
        int next;
        public Selection Bind(Dataset data,string source,string waferKey,float target,float lower,float upper,int count)
            =>BindCore(data,source,waferKey,target,lower,upper,count,false);
        public Selection BindIon(Dataset data,string source,string waferKey,float target,float lower,float upper)
            =>BindCore(data,source,waferKey,target,lower,upper,1,true);
        Selection BindCore(Dataset data,string source,string waferKey,float target,float lower,float upper,int count,bool ion)
        {
            if(string.IsNullOrWhiteSpace(waferKey))throw new ArgumentException("시험 웨이퍼 ID 필요");
            if(assigned.TryGetValue(waferKey,out var prior))return prior;
            Validate(data);
            if(count<1||count>10000||!Positive(target)||!Positive(lower)||!Positive(upper)||lower>=upper||target<lower||target>upper)throw new ArgumentException("시험 기준 또는 웨이퍼 수 오류");
            var cases=new Row[3];
            bool thicknessOnly=false;
            foreach(var row in data.rows)
            {
                if(!CanSelect(row,source))continue;
                float thickness=ion?(float)Dose(target,row):Thickness(target,row);bool inRange=thickness>=lower&&thickness<=upper;
                var m=source=="TCAD"?row.tcad:row.pc;
                bool electricalOk=ElectricalSpec.Evaluate(m.vth,m.bv)==ElectricalSpec.Verdict.OK;
                int kind=!inRange?1:electricalOk?0:2;
                // Prefer a thickness-only deviation so the two verdicts remain easy to compare.
                if(cases[kind]==null||kind==1&&electricalOk&&!thicknessOnly){cases[kind]=row;if(kind==1)thicknessOnly=electricalOk;}
            }
            if(Array.Exists(cases,row=>row==null))throw new InvalidOperationException("선택 출처에 정상·두께 이상·전기특성 이상 사례가 모두 필요합니다.");
            var result=new Selection{row=cases[next].Snapshot(),measurement_source=source,dataset_sha256=data.dataset_sha256,wafer_key=waferKey,category=new[]{"normal",ion?"dose":"thickness","electrical"}[next],automatic=true,reference_target_nm=ion?0:target,n_wafers=count};
            assigned.Add(waferKey,result);next=(next+1)%3;return result;
        }
    }
    static bool Finite(float v)=>!float.IsNaN(v)&&!float.IsInfinity(v);
    static bool Positive(float v)=>Finite(v)&&v>0;
    static bool Valid(Measurement m)=>m!=null&&Finite(m.vth)&&Positive(m.gm)&&Positive(m.id4v)&&Positive(m.bv);
    public static void Validate(Dataset data)
    {
        if(data==null||data.schema_version!=1||data.data_source!="jetson_csv_test"||data.epi_semantics!="drift_doping_ratio"||data.dataset_sha256==null||data.dataset_sha256.Length!=64||data.rows==null||data.rows.Length<1||data.rows.Length>10000)throw new ArgumentException("시험 데이터 형식 불일치");
        foreach(char c in data.dataset_sha256)if(!Uri.IsHexDigit(c))throw new ArgumentException("CSV 해시 오류");
        var ids=new HashSet<string>();
        foreach(var row in data.rows)
        {
            if(row==null||string.IsNullOrWhiteSpace(row.id)||row.id.Length>100||!ids.Add(row.id)||!Positive(row.dose_ratio)||!Positive(row.epi_doping_ratio)||!Positive(row.oxide_ratio)||row.has_tcad&&!Valid(row.tcad)||row.has_pc&&!Valid(row.pc)||row.has_high_precision_vth&&!Finite(row.high_precision_vth)||row.has_high_precision_bv&&!Positive(row.high_precision_bv))throw new ArgumentException("시험 행 값 오류");
        }
    }
    public static bool CanSelect(Row row,string source)=>row!=null&&(source=="TCAD"?row.has_tcad&&Valid(row.tcad):source=="PC"&&row.has_pc&&Valid(row.pc));
    public static float Thickness(float target,Row row)
    {
        if(!Positive(target)||row==null||!Positive(row.oxide_ratio)||!Positive(target*row.oxide_ratio))throw new ArgumentException("기준 두께 또는 산화막 배율 오류");
        return target*row.oxide_ratio;
    }
    public static double Dose(double reference,Row row)
    {
        if(double.IsNaN(reference)||double.IsInfinity(reference)||reference<=0||row==null||!Positive(row.dose_ratio)||double.IsInfinity(reference*row.dose_ratio))
            throw new ArgumentException("TCAD 기준 주입량·CSV 도즈 배율 확인 필요");
        return reference*row.dose_ratio;
    }
}
