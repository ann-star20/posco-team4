using System;
class IonDoseChecks
{
    static void Main()
    {
        void Check(bool ok,string message){if(!ok)throw new Exception(message);}
        Check(IonDoseAssessment.Evaluate(1e13,0,0,true,false)=="미판정","Missing bounds invented OK");
        Check(IonDoseAssessment.Evaluate(1e13,9e12,11e12,false,false)=="진행 중","Incomplete process judged");
        Check(IonDoseAssessment.Evaluate(1e13,9e12,11e12,true,false)=="OK","In-range dose rejected");
        Check(IonDoseAssessment.Evaluate(8.7e12,9e12,11e12,true,false)=="FAIL","Out-of-range dose accepted");
        Check(IonDoseAssessment.Evaluate(1e13,9e12,11e12,true,true)=="정지","Interlock mistaken for quality verdict");
        Check(IonDoseAssessment.Evaluate(double.NaN,9e12,11e12,true,false)=="미판정","NaN accepted");
        Check(IonDoseAssessment.Evaluate(1e13,11e12,9e12,true,false)=="미판정","Reversed bounds accepted");
        Check(Math.Abs(IonDoseAssessment.DeviationPercent(8.7e12,1e13)+13)<1e-8,"Deviation not -13 percent");
        Check(double.IsNaN(IonDoseAssessment.DeviationPercent(1,0)),"Invalid target accepted");
        Check(IonDoseAssessment.Evaluate((float)7.315e12,7.315e12,8.085e12,true,false)=="OK","Float lower boundary rejected");
        Check(IonDoseAssessment.Evaluate((float)8.085e12,7.315e12,8.085e12,true,false)=="OK","Float upper boundary rejected");
        Check(IonDoseAssessment.Evaluate((float)7.3e12,7.315e12,8.085e12,true,false)=="FAIL","Below ML range accepted");
        Check(IonDoseAssessment.Evaluate((float)7.7e12,7.315e12,8.085e12,true,false)=="OK","ML target rejected");
        Check(IonDoseAssessment.Evaluate((float)8.1e12,7.315e12,8.085e12,true,false)=="FAIL","Above ML range accepted");
        Console.WriteLine("ION_DOSE_CHECKS_OK: no invented limits / pending / OK / FAIL / interlock / nonfinite / reversed limits / deviation");
    }
}
