using System.Collections;
using UnityEngine;

public class AoiCycleDemo : MonoBehaviour
{
    public Transform product, stopper, pusher, rod;
    public Vector3 start, inspection, sorting, okEntry, okExit, okTray, ngEntry, ngExit, ngTray, pushDirection;
    public TextMesh monitor;
    public Renderer[] inspectionLeds;
    public Camera overview, inspectionView;
    public bool completed;
    public int okCount, ngCount;
    string status = "READY";
    Vector3 stopperHome, pusherHome, rodHome;
    Material[] ledMaterials;
    bool running;
    bool initialized;
    public bool dashboardControlled;
    public bool Running=>running;
    public bool InspectionReady{get;private set;}
    public void AbortExternalSort(string reason="STOPPED / CONNECTION LOST")
    {
        if(!initialized)return;
        running=false;completed=false;InspectionReady=false;SetLeds(false);product.gameObject.SetActive(false);
        stopper.position=stopperHome;pusher.position=pusherHome;rod.position=rodHome;
        SetStatus(reason,Color.yellow);
    }
    public string Status=>status;
    void Start(){Initialize();}
    public void Initialize()
    {
        if(initialized)return;initialized=true;
        stopperHome=stopper.position;pusherHome=pusher.position;rodHome=rod.position;
        ledMaterials=new Material[inspectionLeds.Length];
        for(int i=0;i<inspectionLeds.Length;i++) ledMaterials[i]=inspectionLeds[i].material;
        SetLeds(false); product.gameObject.SetActive(false); SetStatus("READY / Press Start",Color.white);
    }
    void SetStatus(string value, Color color)
    {
        status=value; monitor.text="AOI | SIMULATION\n"+value+"\nOK "+okCount+"   NG "+ngCount;
        monitor.color=color; Debug.Log("AOI_DEMO_STATE "+value);
    }
    void SetLeds(bool on)
    {
        foreach(var m in ledMaterials) {m.SetColor("_BaseColor",on?Color.white:new Color(.2f,.2f,.2f));m.SetColor("_EmissiveColor",on?Color.white*8:Color.black);}
    }
    IEnumerator Move(Vector3 target, float duration)
    {
        Vector3 from=product.position;
        for(float t=0;t<duration;t+=Time.deltaTime){product.position=Vector3.Lerp(from,target,t/duration);yield return null;}
        product.position=target;
    }
    IEnumerator Run()
    {
        running=true;completed=false;okCount=ngCount=0;
        for(int cycle=0;cycle<2;cycle++)
        {
            yield return SortOne(cycle==1);
        }
        stopper.position=stopperHome;SetStatus("COMPLETE / OK 1 + NG 1",Color.green);
        completed=true;running=false;Debug.Log("AOI_DEMO_PASS OK=1 NG=1");
    }
    public IEnumerator SortOne(bool ng)
    {
            yield return PrepareInspection();
            yield return new WaitForSeconds(2);
            yield return SortPrepared(ng);
    }
    public IEnumerator PrepareInspection()
    {
            Initialize();running=true;completed=false;
            InspectionReady=false;
            product.gameObject.SetActive(true);product.position=start;
            stopper.position=stopperHome; pusher.position=pusherHome;rod.position=rodHome;
            SetStatus("FEED",Color.white);
            yield return Move(inspection,3);
            SetStatus("INSPECTING",Color.yellow);SetLeds(true);
            InspectionReady=true;
    }
    public IEnumerator SortPrepared(bool ng)
    {
            if(!InspectionReady)throw new System.InvalidOperationException("AOI inspection position not ready");
            InspectionReady=false;
            SetStatus(ng?"NG":"OK",ng?Color.red:Color.green);SetLeds(false);
            yield return new WaitForSeconds(.8f);
            stopper.position=stopperHome-Vector3.up*.10f;
            yield return Move(sorting,2.5f);
            if(ng)
            {
                Vector3 from=product.position;
                for(float t=0;t<1;t+=Time.deltaTime)
                {
                    float f=Mathf.Clamp01(t);product.position=Vector3.Lerp(from,ngEntry,f);
                    pusher.position=pusherHome+pushDirection*f;rod.position=rodHome+pushDirection*f;yield return null;
                }
                product.position=ngEntry;yield return Move(ngExit,1);yield return Move(ngTray,.6f);
                pusher.position=pusherHome;rod.position=rodHome;ngCount++;
            }
            else {yield return Move(okEntry,1.5f);yield return Move(okExit,1);yield return Move(okTray,.6f);okCount++;}
            Debug.Log("AOI_DEMO_DELIVERED "+(ng?"NG":"OK")+" "+product.position);
            yield return new WaitForSeconds(1);product.gameObject.SetActive(false);
        stopper.position=stopperHome;SetStatus(ng?"COMPLETE / NG":"COMPLETE / OK",ng?Color.red:Color.green);
        completed=true;running=false;
    }
    void OnGUI()
    {
        if(dashboardControlled)return;
        GUI.skin.label.fontSize=20;
        GUI.Box(new Rect(15,15,410,180),"");
        GUI.Label(new Rect(30,25,390,35),"AOI functional test (SIMULATION)");
        GUI.Label(new Rect(30,65,390,35),status);
        GUI.Label(new Rect(30,100,390,35),"OK: "+okCount+"   NG: "+ngCount);
        if(GUI.Button(new Rect(30,145,170,35),"Switch camera")) {overview.enabled=!overview.enabled;inspectionView.enabled=!overview.enabled;}
        if(!running&&GUI.Button(new Rect(215,145,170,35),"Start / Run again")) StartCoroutine(Run());
    }
}
