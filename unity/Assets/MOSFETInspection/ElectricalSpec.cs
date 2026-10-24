// Project specification from 진단에이전트.py SPEC; not a qualified production specification.
public static class ElectricalSpec
{
    public enum Verdict {Pending,OK,NG}
    public const float VthMin=1.7f,VthMax=2.6f,BvMin=40f;
    static bool Finite(float x)=>!float.IsNaN(x)&&!float.IsInfinity(x);
    public static Verdict Evaluate(float vth,float? bv)
    {
        if(Finite(vth)&&(vth<VthMin||vth>VthMax))return Verdict.NG;
        if(bv.HasValue&&Finite(bv.Value)&&bv.Value>0&&bv.Value<BvMin)return Verdict.NG;
        if(!Finite(vth)||!bv.HasValue||!Finite(bv.Value)||bv.Value<=0)return Verdict.Pending;
        return Verdict.OK;
    }
    public static string Describe(float vth,float? bv)
    {
        var verdict=Evaluate(vth,bv);
        string reason=Finite(vth)&&(vth<VthMin||vth>VthMax)?"Vth 규격 이탈":
            bv.HasValue&&Finite(bv.Value)&&bv.Value>0&&bv.Value<BvMin?"BV 하한 미달":
            verdict==Verdict.Pending?"필수 값 누락/유효성 확인 필요":"Vth·BV 두 항목 통과";
        return "ML 예측 판정: "+(verdict==Verdict.Pending?"대기":verdict.ToString())+" · "+reason+"\n프로젝트 규격 Vth 1.7–2.6 V / BV ≥40 V · gm·Id 규격 미정";
    }
}
