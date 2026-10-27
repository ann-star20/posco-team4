using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

// Inspection counts are separate from completed sorting animations and split by source.
public sealed class AoiInspectionHistory
{
    [Serializable] public class Entry
    {
        public string result_id,inspection_id,completed_at,lot_id,unit_id,verdict,label,source;
        public float confidence;
        public int defect_count;
        public DateTimeOffset Time=>DateTimeOffset.Parse(completed_at);
    }
    [Serializable] class Archive {public int version=1;public List<Entry> entries=new List<Entry>();}
    public struct Stats {public int pass,ng;public int total=>pass+ng;public float normalRate=>total==0?0:100f*pass/total;}
    static AoiInspectionHistory current;
    public static AoiInspectionHistory Instance=>current??(current=new AoiInspectionHistory(Path.Combine(Application.persistentDataPath,"InspectionHistory","aoi-inspections.json")));
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]static void Reset(){current=null;}
#if UNITY_EDITOR
    public static void UseTestStore(AoiInspectionHistory value){current=value;}
#endif
    public string FilePath {get;}
    public string LastError {get;private set;}
    public int Revision {get;private set;}
    public bool Readable=>!loadFailed;
    Archive archive=new Archive();
    readonly HashSet<string> ids=new HashSet<string>(StringComparer.Ordinal);
    bool loadFailed;
    static string Key(Entry e)=>e.source+"|"+e.result_id;
    static bool Valid(Entry e)=>e!=null&&!string.IsNullOrWhiteSpace(e.result_id)&&e.result_id.Length<=100&&!string.IsNullOrWhiteSpace(e.inspection_id)&&!string.IsNullOrWhiteSpace(e.unit_id)&&!string.IsNullOrWhiteSpace(e.source)&&DateTimeOffset.TryParse(e.completed_at,out _)&&(e.verdict=="OK"||e.verdict=="NG"||e.verdict=="검토")&&!float.IsNaN(e.confidence)&&!float.IsInfinity(e.confidence)&&e.confidence>=0&&e.confidence<=1&&e.defect_count>=0;
    public AoiInspectionHistory(string path)
    {
        FilePath=path;
        try
        {
            if(!File.Exists(path))return;
            var loaded=JsonUtility.FromJson<Archive>(File.ReadAllText(path));
            if(loaded==null||loaded.version!=1||loaded.entries==null)throw new InvalidDataException();
            foreach(var e in loaded.entries)if(!Valid(e)||!ids.Add(Key(e)))throw new InvalidDataException();
            archive=loaded;
        }
        catch(Exception){loadFailed=true;ids.Clear();archive=new Archive();LastError="검사 이력 읽기 실패 · 원본 보존 · 집계 확인 필요";}
    }
    public bool Add(Entry e)
    {
        if(loadFailed)return false;
        if(!Valid(e)){LastError="검사 기록 형식 오류 · 저장 제외";return false;}
        if(ids.Contains(Key(e)))return false;
        var copy=JsonUtility.FromJson<Entry>(JsonUtility.ToJson(e));archive.entries.Add(copy);
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath));string temp=FilePath+".tmp";
            File.WriteAllText(temp,JsonUtility.ToJson(archive,true));
            if(File.Exists(FilePath))File.Replace(temp,FilePath,FilePath+".bak");else File.Move(temp,FilePath);
            ids.Add(Key(copy));Revision++;LastError=null;return true;
        }
        catch(Exception){archive.entries.Remove(copy);LastError="검사 이력 저장 실패 · 집계에 반영되지 않음";return false;}
    }
    public List<Entry> OnDay(DateTime date,string source)=>archive.entries.Where(e=>e.Time.LocalDateTime.Date==date.Date&&e.source==source).OrderByDescending(e=>e.Time).ToList();
    public List<DateTime> Days(string source)=>archive.entries.Where(e=>e.source==source).Select(e=>e.Time.LocalDateTime.Date).Append(DateTime.Today).Distinct().OrderByDescending(d=>d).ToList();
    public Stats ForDay(DateTime date,string source){var rows=OnDay(date,source);return new Stats{pass=rows.Count(e=>e.verdict=="OK"),ng=rows.Count(e=>e.verdict=="NG")};}
    public void Record(AoiJetsonFeed feed)
    {
        var p=feed.current;if(p==null)return;
        Add(new Entry{result_id=p.result_id,inspection_id=string.IsNullOrEmpty(p.request_id)?p.result_id:p.request_id,completed_at=DateTimeOffset.FromUnixTimeMilliseconds(p.captured_at_ms).ToString("O"),lot_id=p.lot_id,unit_id=p.product_id,verdict=feed.Verdict,label=p.label,source=feed.demoMode?"demo":string.IsNullOrWhiteSpace(p.data_source)?"unspecified":p.data_source,confidence=p.confidence,defect_count=p.defects==null?0:p.defects.Length});
    }
}
