using System;
using UnityEngine;

[CreateAssetMenu(menuName="MOSFET Factory/Film Inspection Recipe")]
public class FilmInspectionRecipe : ScriptableObject
{
    public float targetNm=60,lowerNm=57,upperNm=63;
    public float[] passDemo={59.76f,60.06f,60.18f};
    public float[] highDemo={65.16f,65.46f,65.58f};
    public float[] lowDemo={54.36f,54.66f,54.78f};
    public void Validate()
    {
        if(!Finite(lowerNm)||!Finite(targetNm)||!Finite(upperNm)||lowerNm<=0||lowerNm>=upperNm||targetNm<lowerNm||targetNm>upperNm)
            throw new InvalidOperationException("Invalid film thickness specification.");
    }
    public static bool Finite(float value)=>!float.IsNaN(value)&&!float.IsInfinity(value);
    public bool InRange(float value)=>Finite(value)&&value>=lowerNm&&value<=upperNm;
    // Demo rule: every one of the three sites must meet the inclusive specification.
    public string Evaluate(float[] readings,out string reason)
    {
        Validate();if(readings==null||readings.Length!=3)throw new InvalidOperationException("Three film readings are required.");
        bool high=false,low=false;
        foreach(float value in readings)
        {
            if(!Finite(value)||value<=0)throw new InvalidOperationException("Invalid film reading.");
            high|=value>upperNm;low|=value<lowerNm;
        }
        reason=high&&low?"측정 지점별 상한 초과·하한 미달":high?"산화막 두께 상한 초과":low?"산화막 두께 하한 미달":"모든 측정 지점이 허용 범위 내";
        return high||low?"FAIL":"PASS";
    }
}
