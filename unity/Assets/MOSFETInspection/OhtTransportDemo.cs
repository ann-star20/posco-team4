using System;
using System.Collections;
using UnityEngine;

public class OhtTransportDemo : MonoBehaviour
{
    public Transform carrier,lift,attachPoint,gripper,leftJaw,rightJaw,foup,foupGrip,foupDock;
    public Transform[] docks,beltTops,beltBottoms;
    public Material beltMaterial;
    public float travelGripHeight;
    public string machine_id="OHT_01",lot_id="LOT-001",carrier_id="FOUP-001";
    public string status="IDLE",command="NONE",source_port="SOURCE_PORT",destination_port="OX_LOADPORT_01";
    public bool completed,failed;
    bool running,paused,held;
    Vector3 railDirection,initialCarrier,initialLift,initialFoup;
    Quaternion initialFoupRotation;
    Transform[] belts;
    void Awake()
    {
        railDirection=(docks[2].position-docks[0].position).normalized;
        initialCarrier=carrier.position;initialLift=lift.position;initialFoup=foup.position;initialFoupRotation=foup.rotation;
        belts=new Transform[beltTops.Length];
        for(int i=0;i<belts.Length;i++)
        {
            var o=GameObject.CreatePrimitive(PrimitiveType.Cube);o.name="OHT_Animated_Belt_"+i;
            Destroy(o.GetComponent<Collider>());o.GetComponent<Renderer>().sharedMaterial=beltMaterial;belts[i]=o.transform;
        }
        Jaws(false);UpdateBelts();
    }
    void UpdateBelts()
    {
        for(int i=0;i<belts.Length;i++)
        {
            Vector3 a=beltTops[i].position,b=beltBottoms[i].position;
            belts[i].position=(a+b)*.5f;belts[i].rotation=Quaternion.FromToRotation(Vector3.up,a-b);
            belts[i].localScale=new Vector3(.018f,Vector3.Distance(a,b),.004f);
        }
    }
    void LateUpdate(){if(belts!=null)UpdateBelts();}
    void Jaws(bool closed)
    {
        float width=closed?.10f:.14f;
        leftJaw.position=gripper.position-railDirection*width;rightJaw.position=gripper.position+railDirection*width;
    }
    void State(string next,string cmd)
    {
        status=next;command=cmd;Debug.Log("OHT_DEMO "+status+" "+command+" carrier="+carrier_id);
    }
    IEnumerator Delay(float seconds)
    {for(float t=0;t<seconds;){if(!paused)t+=Time.deltaTime;yield return null;}}
    IEnumerator Shift(Transform target,Vector3 to,float seconds)
    {
        var from=target.position;
        for(float t=0;t<seconds;){if(!paused)t+=Time.deltaTime;float f=Mathf.SmoothStep(0,1,Mathf.Clamp01(t/seconds));target.position=Vector3.Lerp(from,to,f);yield return null;}
        target.position=to;
    }
    IEnumerator LiftTo(float gripHeight)
    {
        var to=lift.position;to.y+=gripHeight-attachPoint.position.y;
        yield return Shift(lift,to,2);
    }
    void Check(bool condition,string message){if(!condition)throw new InvalidOperationException(message);}
    IEnumerator Pick(int port)
    {
        State("LOWERING / PICK","PICK");Jaws(false);
        yield return LiftTo(foupGrip.position.y);
        Check(Vector3.Distance(attachPoint.position,foupGrip.position)<.003f,"OHT gripper does not align to FOUP handle.");
        Jaws(true);yield return Delay(.4f);
        foup.SetParent(attachPoint,true);held=true;
        State("RAISING / LOADED","PICK");yield return LiftTo(travelGripHeight);
        Check(Vector3.Distance(attachPoint.position,foupGrip.position)<.003f,"FOUP slipped during lifting.");
    }
    IEnumerator Travel(int port)
    {
        Check(Mathf.Abs(attachPoint.position.y-travelGripHeight)<.003f,"Raise hoist before horizontal travel.");
        State("MOVING","MOVE");
        Vector3 delta=docks[port].position-attachPoint.position;delta.y=0;
        yield return Shift(carrier,carrier.position+delta,3);
    }
    IEnumerator Place(int port)
    {
        Check(held,"No FOUP to place.");State("LOWERING / PLACE","PLACE");
        float bottomToGrip=foupGrip.position.y-foupDock.position.y;
        yield return LiftTo(docks[port].position.y+bottomToGrip);
        foup.SetParent(docks[port],true);held=false;
        Check(Vector3.Distance(foupDock.position,docks[port].position)<.003f,"FOUP not seated on dock.");
        Jaws(false);yield return Delay(.4f);
        Debug.Log("OHT_DOCK_PASS "+docks[port].name+" ownership="+foup.parent.name);
        State("RAISING / EMPTY","PLACE");yield return LiftTo(travelGripHeight);
    }
    IEnumerator Sequence()
    {
        running=true;completed=failed=false;paused=false;
        foup.SetParent(docks[0],true);foup.SetPositionAndRotation(initialFoup,initialFoupRotation);
        carrier.position=initialCarrier;lift.position=initialLift;held=false;
        source_port="SOURCE_PORT";destination_port="OX_LOADPORT_01";
        yield return Pick(0);yield return Travel(1);yield return Place(1);
        State("OX PROCESS READY (MOCK)","WAIT");yield return Delay(2);
        source_port="OX_LOADPORT_01";destination_port="IMP_LOADPORT_01";
        yield return Pick(1);yield return Travel(2);yield return Place(2);
        State("COMPLETE / IMP DOCKED","NONE");completed=true;running=false;
        Debug.Log("OHT_DEMO_PASS source -> oxide -> implant; FOUP dock and ownership checks passed");
    }
    // Nested coroutine exceptions are caught so a failed demo cannot silently continue.
    IEnumerator Guard(IEnumerator task)
    {
        while(true)
        {
            object item;
            try{if(!task.MoveNext())yield break;item=task.Current;}
            catch(Exception e){failed=true;running=false;State("ERROR / "+e.Message,"STOP");Debug.LogException(e);yield break;}
            if(item is IEnumerator nested){yield return Guard(nested);if(failed)yield break;}
            else yield return item;
        }
    }
    void OnGUI()
    {
        GUI.skin.label.fontSize=18;GUI.Box(new Rect(15,15,480,205),"");
        GUI.Label(new Rect(30,25,450,30),"OHT-01 | FOUP-001 | LOT-001");
        GUI.Label(new Rect(30,60,450,30),status);
        GUI.Label(new Rect(30,95,450,30),source_port+" -> "+destination_port);
        GUI.Label(new Rect(30,130,450,25),"SIMULATION | Oxidation process signal: MOCK");
        if(!running&&GUI.Button(new Rect(30,170,200,35),"Start / Restart"))StartCoroutine(Guard(Sequence()));
        if(running&&GUI.Button(new Rect(245,170,200,35),paused?"Resume":"Pause"))paused=!paused;
    }
}
