using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
// Local simulation process history, separate from Gateway and electrical results.
public sealed class IonImplantHistory
{
    [Serializable] public class Entry {public string id,lot_id,completed_at,recipe_id,verdict,sample_id,csv_sha256,electrical_source,source="simulation";public double dose,target,lower,upper;}
    [Serializable] class Store {public List<Entry> entries=new List<Entry>();}
    readonly string path;Store data=new Store();
    public bool Readable {get;private set;}=true;
    public string Error {get;private set;}="";
    static IonImplantHistory instance;
    public static IonImplantHistory Instance=>instance??(instance=new IonImplantHistory(Path.Combine(Application.persistentDataPath,"ion-implant-history.json")));
    public static void UseTestStore(IonImplantHistory value){instance=value;}
    public IonImplantHistory(string file)
    {path=file;try{if(File.Exists(path)){data=JsonUtility.FromJson<Store>(File.ReadAllText(path));if(data?.entries==null||data.entries.Any(e=>e==null||string.IsNullOrEmpty(e.id)))throw new FormatException("Invalid history");}}catch(Exception e){data=new Store();Readable=false;Error=e.Message;}}
    public bool Add(Entry value)
    {
        if(!Readable||data.entries.Any(e=>e.id==value.id))return false;data.entries.Add(value);
        try{Directory.CreateDirectory(Path.GetDirectoryName(path));string temp=path+".tmp";File.WriteAllText(temp,JsonUtility.ToJson(data,true));if(File.Exists(path))File.Replace(temp,path,null);else File.Move(temp,path);return true;}
        catch(Exception e){data.entries.Remove(value);Readable=false;Error=e.Message;return false;}
    }
    public List<Entry> Today()=>data.entries.Where(e=>DateTimeOffset.TryParse(e.completed_at,out var t)&&t.LocalDateTime.Date==DateTime.Today).OrderByDescending(e=>e.completed_at).ToList();
    public List<Entry> Latest()=>data.entries.OrderByDescending(e=>e.completed_at).Take(6).ToList();
}
