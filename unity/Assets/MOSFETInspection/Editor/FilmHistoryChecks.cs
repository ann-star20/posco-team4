#if UNITY_EDITOR
using System;
using System.IO;

public static class FilmHistoryChecks
{
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    public static void Run(string folder)
    {
        var path=Path.Combine(folder,"records.json");var store=new FilmInspectionHistory(path);var now=DateTimeOffset.Now;
        FilmInspectionHistory.Entry Entry(string verdict,DateTimeOffset time)=>new FilmInspectionHistory.Entry{
            inspection_id=Guid.NewGuid().ToString("N"),completed_at=time.ToString("O"),lot_id="TEST-LOT",equipment_id="ELLIP-01",scenario="test",
            data_source="synthetic",verdict=verdict,target=100,lower=95,upper=105,readings=verdict=="PASS"?new[]{99.6f,100.1f,100.3f}:new[]{108.6f,109.1f,109.3f},reason="test"};
        Check(store.ForDay(now.LocalDateTime).total==0&&store.ForDay(now.LocalDateTime).normalPercent==0,"Empty denominator");
        var pass=Entry("PASS",now);var ng=Entry("FAIL",now);
        Check(store.Add(pass)&&store.Add(ng),"Write failed");Check(!store.Add(ng),"Repeated inspection counted twice");
        var stats=store.ForDay(now.LocalDateTime);Check(stats.total==2&&stats.pass==1&&stats.ng==1&&Math.Abs(stats.normalPercent-50)<.001,"Daily counts incorrect");
        Check(store.Add(Entry("PASS",now.AddSeconds(1))),"Remeasurement not recorded");
        Check(store.Add(Entry("FAIL",now.AddDays(-1))),"Previous day not recorded");
        store=new FilmInspectionHistory(path);stats=store.ForDay(now.LocalDateTime);
        Check(stats.total==3&&stats.pass==2&&stats.ng==1&&Math.Abs(stats.normalPercent-200f/3)<.01,"Reload/date isolation failed");
        Check(store.ForDay(now.AddDays(1).LocalDateTime).total==0,"Day rollover failed");
        var invalid=Entry("FAIL",now);invalid.readings[0]=float.NaN;Check(!store.Add(invalid)&&store.ForDay(now.LocalDateTime).total==3,"Invalid readings counted");
        var broken=Path.Combine(folder,"broken.json");File.WriteAllText(broken,"broken");var corrupt=new FilmInspectionHistory(broken);
        Check(!corrupt.Add(pass)&&File.ReadAllText(broken)=="broken"&&!string.IsNullOrEmpty(corrupt.LastError),"Corrupt archive overwritten");
        var occupied=Path.Combine(folder,"occupied");File.WriteAllText(occupied,"file");var unwritable=new FilmInspectionHistory(Path.Combine(occupied,"records.json"));
        Check(!unwritable.Add(pass)&&unwritable.ForDay(now.LocalDateTime).total==0&&!string.IsNullOrEmpty(unwritable.LastError),"Failed write counted as saved");
    }
}
#endif
