using System;
public static class IonDoseAssessment
{
    public const double MlTarget=7.70e12, MlLower=7.315e12, MlUpper=8.085e12;
    // The simulator stores dose as float; compare limits at the same precision.
    public static string Evaluate(float dose,double lo,double hi,bool complete,bool interlock)
        =>Evaluate((double)dose,(double)(float)lo,(double)(float)hi,complete,interlock);
    public static bool Finite(double v)=>!double.IsNaN(v)&&!double.IsInfinity(v);
    public static bool HasLimits(double lo,double hi)=>Finite(lo)&&Finite(hi)&&lo>0&&hi>=lo;
    public static string Evaluate(double dose,double lo,double hi,bool complete,bool interlock)
    {if(interlock)return "정지";if(!complete)return "진행 중";if(!Finite(dose)||!HasLimits(lo,hi))return "미판정";return dose>=lo&&dose<=hi?"OK":"FAIL";}
    public static double DeviationPercent(double dose,double target)=>Finite(dose)&&Finite(target)&&target>0?(dose/target-1)*100:double.NaN;
}
