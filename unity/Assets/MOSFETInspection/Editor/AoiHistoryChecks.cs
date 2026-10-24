#if UNITY_EDITOR
using System;
using System.IO;
using UnityEngine;

public static class AoiHistoryChecks
{
    static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
    static AoiInspectionHistory.Entry Entry(string id,string verdict,string source,int days=0)=>new AoiInspectionHistory.Entry{result_id=id,inspection_id="REQ-"+id,completed_at=DateTimeOffset.Now.AddDays(days).ToString("O"),unit_id="TEST",lot_id="TEST-LOT",verdict=verdict,label=verdict=="OK"?"normal":"crash",source=source,confidence=.9f,defect_count=verdict=="OK"?0:2};
    public static void Run(string folder)
    {
        Directory.CreateDirectory(folder);string path=Path.Combine(folder,"checks.json");var store=new AoiInspectionHistory(path);
        Check(store.Add(Entry("1","OK","prod")),"Normal record failed");Check(store.Add(Entry("2","NG","prod")),"NG record failed");Check(!store.Add(Entry("2","NG","prod")),"Duplicate counted");
        Check(store.ForDay(DateTime.Today,"prod").total==2&&store.ForDay(DateTime.Today,"prod").normalRate==50,"Two defects counted as two products");
        Check(store.Add(Entry("3","NG","demo"))&&store.Add(Entry("4","NG","mock")),"Test source record failed");Check(store.ForDay(DateTime.Today,"prod").total==2,"Test results mixed into production source");
        Check(store.Add(Entry("5","NG","prod",-1)),"Previous day record failed");Check(store.ForDay(DateTime.Today,"prod").total==2,"Previous day mixed into today");
        Check(new AoiInspectionHistory(path).ForDay(DateTime.Today,"prod").total==2,"Reload lost records");
        var invalid=Entry("6","OK","prod");invalid.confidence=float.NaN;Check(!store.Add(invalid),"NaN archived");
        string corrupt=Path.Combine(folder,"corrupt.json");File.WriteAllText(corrupt,"{ invalid json");var broken=new AoiInspectionHistory(corrupt);Check(!broken.Readable&&!broken.Add(Entry("7","OK","prod"))&&File.ReadAllText(corrupt)=="{ invalid json","Corrupt original overwritten");
        string blocked=Path.Combine(folder,"occupied");File.WriteAllText(blocked,"file");var unwritable=new AoiInspectionHistory(Path.Combine(blocked,"archive.json"));Check(!unwritable.Add(Entry("8","OK","prod"))&&unwritable.ForDay(DateTime.Today,"prod").total==0&&!string.IsNullOrEmpty(unwritable.LastError),"Write failure counted as saved");
    }
}
#endif
