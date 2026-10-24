using System;
class ElectricalSpecCheck
{
    static int count;
    static void Check(float vth,float? bv,ElectricalSpec.Verdict expected)
    {
        var result=ElectricalSpec.Evaluate(vth,bv);
        if(result!=expected)throw new Exception($"{vth}/{bv}: {result} != {expected}");
        count++;
    }
    static void Main()
    {
        Check(1.7f,40,ElectricalSpec.Verdict.OK);
        Check(2.6f,40,ElectricalSpec.Verdict.OK);
        Check(1.699f,42,ElectricalSpec.Verdict.NG);
        Check(2.601f,42,ElectricalSpec.Verdict.NG);
        Check(2.26f,39.999f,ElectricalSpec.Verdict.NG);
        Check(2.26f,null,ElectricalSpec.Verdict.Pending);
        Check(2.63f,null,ElectricalSpec.Verdict.NG);
        Check(float.NaN,42,ElectricalSpec.Verdict.Pending);
        Check(2.26f,float.PositiveInfinity,ElectricalSpec.Verdict.Pending);
        Check(2.26f,0,ElectricalSpec.Verdict.Pending);
        Check(2.482527f,42.24754f,ElectricalSpec.Verdict.OK);
        Console.WriteLine($"ELECTRICAL_SPEC_OK {count} cases");
    }
}
