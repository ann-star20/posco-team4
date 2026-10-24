using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEngine;

// Local thickness-inspection audit, independent of diagnostic results and recipe approval.
public sealed class FilmInspectionHistory
{
    [Serializable] public class Entry
    {
        public string inspection_id,completed_at,lot_id,wafer_id,equipment_id,scenario,data_source,verdict,reason;
        public string test_sample_id,measurement_source,dataset_sha256;
        public string test_wafer_key,test_selection_mode,test_category;
        public float test_reference_target_nm;
        public float test_dose_ratio,test_epi_doping_ratio,test_oxide_ratio;
        public float[] readings;
        public float target,lower,upper;
        public bool held,remeasurement;
        public float Mean=>readings.Sum()/readings.Length;
        public DateTimeOffset Time=>DateTimeOffset.Parse(completed_at,CultureInfo.InvariantCulture);
        public string ShortId=>"INSP-"+inspection_id.Substring(0,8).ToUpperInvariant();
    }
    [Serializable] class Archive {public int version=1;public List<Entry> entries=new List<Entry>();}
    public struct Stats {public int total,pass,ng;public float normalPercent=>total==0?0:100f*pass/total;}
    static FilmInspectionHistory current;
    public static FilmInspectionHistory Instance=>current??(current=new FilmInspectionHistory(System.IO.Path.Combine(Application.persistentDataPath,"InspectionHistory","film-inspections.json")));
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]static void Reset(){current=null;}
#if UNITY_EDITOR
    public static void UseTestStore(FilmInspectionHistory store){current=store;}
#endif
    public string FilePath {get;}
    public string LastError {get;private set;}
    public bool Readable=>!loadFailed;
    public int Revision {get;private set;}
    Archive archive=new Archive();
    readonly HashSet<string> ids=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    bool loadFailed;
    public FilmInspectionHistory(string path)
    {
        FilePath=path;
        try
        {
            if(!File.Exists(path))return;
            var loaded=JsonUtility.FromJson<Archive>(File.ReadAllText(path));
            if(loaded==null||loaded.version!=1||loaded.entries==null)throw new InvalidDataException("Unsupported history file");
            foreach(var entry in loaded.entries)if(!Valid(entry)||!ids.Add(entry.inspection_id))throw new InvalidDataException("Invalid or duplicate inspection record");
            archive=loaded;
        }
        catch(Exception e){loadFailed=true;archive=new Archive();ids.Clear();LastError="기록 읽기 실패 · 원본 보존: "+e.Message;}
    }
    static bool Valid(Entry e)
    {
        if(e==null||!Guid.TryParse(e.inspection_id,out _)||string.IsNullOrWhiteSpace(e.lot_id)||e.data_source!="synthetic"||!DateTimeOffset.TryParse(e.completed_at,CultureInfo.InvariantCulture,DateTimeStyles.None,out _)||e.readings==null||e.readings.Length!=3)return false;
        if(!FilmInspectionRecipe.Finite(e.lower)||!FilmInspectionRecipe.Finite(e.upper)||!FilmInspectionRecipe.Finite(e.target)||e.lower<=0||e.upper<=e.lower||e.target<e.lower||e.target>e.upper)return false;
        if(!Array.TrueForAll(e.readings,v=>FilmInspectionRecipe.Finite(v)&&v>0))return false;
        return e.verdict==(Array.TrueForAll(e.readings,v=>v>=e.lower&&v<=e.upper)?"PASS":"FAIL");
    }
    public bool Add(Entry entry)
    {
        if(loadFailed)return false;
        if(!Valid(entry)){LastError="유효하지 않은 검사 기록 · 저장 제외";return false;}
        if(ids.Contains(entry.inspection_id))return false;
        var copy=JsonUtility.FromJson<Entry>(JsonUtility.ToJson(entry));archive.entries.Add(copy);
        try
        {
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(FilePath));
            string temp=FilePath+".tmp";File.WriteAllText(temp,JsonUtility.ToJson(archive,true));
            if(File.Exists(FilePath))File.Replace(temp,FilePath,FilePath+".bak");else File.Move(temp,FilePath);
            ids.Add(copy.inspection_id);Revision++;LastError=null;return true;
        }
        catch(Exception e){archive.entries.Remove(copy);LastError="검사 기록 저장 실패: "+e.Message;return false;}
    }
    public List<Entry> OnDay(DateTime day)=>archive.entries.Where(e=>e.Time.LocalDateTime.Date==day.Date).OrderByDescending(e=>e.Time).ToList();
    public Entry Find(string id)=>archive.entries.Find(e=>e.inspection_id==id);
    public Entry LatestForEquipment(string equipment)
    {
        var entry=archive.entries.Where(e=>e.equipment_id==equipment).OrderByDescending(e=>e.Time).FirstOrDefault();
        return entry==null?null:JsonUtility.FromJson<Entry>(JsonUtility.ToJson(entry));
    }
    public List<DateTime> Days()=>archive.entries.Select(e=>e.Time.LocalDateTime.Date).Append(DateTime.Today).Distinct().OrderByDescending(d=>d).ToList();
    public Stats ForDay(DateTime day)
    {var rows=OnDay(day);return new Stats{total=rows.Count,pass=rows.Count(e=>e.verdict=="PASS"),ng=rows.Count(e=>e.verdict=="FAIL")};}
    public bool Record(EllipsometerCycle c,bool remeasurement)
    {
        var entry=new Entry{inspection_id=c.InspectionId,completed_at=DateTimeOffset.Now.ToString("O"),lot_id=c.lotId,wafer_id=c.waferId,equipment_id="ELLIP-01",scenario=c.InspectionCsv?.Label??c.DemoLabel,data_source="synthetic",test_sample_id=c.InspectionCsv?.row.id,measurement_source=c.InspectionCsv?.measurement_source,dataset_sha256=c.InspectionCsv?.dataset_sha256,test_dose_ratio=c.InspectionCsv?.row.dose_ratio??0,test_epi_doping_ratio=c.InspectionCsv?.row.epi_doping_ratio??0,test_oxide_ratio=c.InspectionCsv?.row.oxide_ratio??0,verdict=c.verdict,reason=c.inspectionReason,readings=(float[])c.readings.Clone(),target=c.recipe.targetNm,lower=c.recipe.lowerNm,upper=c.recipe.upperNm,held=c.lotHeld,remeasurement=remeasurement};
        entry.test_wafer_key=c.InspectionCsv?.wafer_key;entry.test_category=c.InspectionCsv?.category;
        entry.test_selection_mode=c.InspectionCsv==null?null:c.InspectionCsv.automatic?"automatic":"manual";
        entry.test_reference_target_nm=c.InspectionCsv?.reference_target_nm??0;
        return Add(entry);
    }
}
