using System;
using System.Collections;
using System.Linq;
using UnityEngine;

// Simplified three-axis stocker; the authoritative transport FOUP is reused throughout.
[DefaultExecutionOrder(90)]
public class StockerCycle : MonoBehaviour
{
    public enum CarrierLocation { Stored, Fork, Port, InTransit, Exported }
    public OhtFabCycle oht;
    public Transform frameOrigin,frameX,frameFront,elevator,slider,fork,attachPoint,shutter,ioDock;
    public Transform[] slots;
    public Renderer[] fixedParts,forkParts,movingParts,cutawayPanels;
    public Camera detail;
    public bool[] occupied={true,false,false,true,true,false};
    public CarrierLocation location=CarrierLocation.Stored;
    public string status="STORED / SLOT 01";
    public int reservedSlot=0,outgoingRuns,incomingRuns;
    public bool failed;
    public bool Running=>running;
    public bool AtPort=>location==CarrierLocation.Port;
    public bool Stored=>location==CarrierLocation.Stored;
    public bool Exported=>location==CarrierLocation.Exported;
    public bool DoorOpen=>doorOpen;
    public int OccupiedCount=>occupied.Count(v=>v);
    [NonSerialized] public string[] heldInspections=new string[6];
    public bool IsHeldSlot(int slot)=>slot>=0&&slot<heldInspections.Length&&!string.IsNullOrEmpty(heldInspections[slot]);
    public int NextFreeSlot {get{for(int i=0;i<occupied.Length;i++)if(!occupied[i]&&!IsHeldSlot(i))return i;return -1;}}
    public bool CanDispatchReserved=>reservedSlot>=0&&reservedSlot<occupied.Length&&occupied[reservedSlot]&&!IsHeldSlot(reservedSlot);
    public void MarkHeld(string inspection,bool qualityHold=true)
    {
        OhtFabCycle.Require(Stored&&!Running&&!string.IsNullOrEmpty(inspection),"HOLD storage not complete");
        heldInspections[reservedSlot]=inspection;State((qualityHold?"NG HOLD / SLOT ":"RESULT WAIT / SLOT ")+(reservedSlot+1).ToString("D2"));
    }
    public void BeginToolRecovery()
    {
        OhtFabCycle.Require(Stored&&!Running&&!failed&&!IsHeldSlot(reservedSlot),"Active carrier not available for tool recovery");
        occupied[reservedSlot]=false;location=CarrierLocation.InTransit;
    }
    public void PrepareSimulationCarrier(int slot)
    {
        OhtFabCycle.Require(initialized&&(Stored&&IsHeldSlot(reservedSlot)||Exported)&&!Running&&!failed,"Store HOLD carrier before next simulation LOT");
        OhtFabCycle.Require(slot>=0&&slot<slots.Length&&!occupied[slot]&&!IsHeldSlot(slot),"No free simulation carrier slot");
        // Preserve the parked FOUP; the existing transport mesh now represents a new simulated carrier.
        if(Stored)
        {var parked=Instantiate(oht.foup.gameObject,slots[reservedSlot],true);parked.name="HOLD_FOUP_"+heldInspections[reservedSlot];}
        reservedSlot=slot;occupied[slot]=true;location=CarrierLocation.Stored;
        oht.foup.SetParent(slots[slot],true);oht.foup.position+=slots[slot].position-oht.foupDock.position;oht.foup.gameObject.SetActive(true);
        State("NEW SIMULATION LOT / SLOT "+(slot+1).ToString("D2"));
    }
    bool initialized,running,paused,doorOpen,inside,normalExport;
    Vector3 origin,xAxis,depthAxis,upAxis,shutterClosed,payloadMin,payloadMax;
    Bounds[] obstacles;
    bool[] originalPanels;
    Font font;
    Texture2D background;
    const float Lane=-.26f,Release=.008f,Clearance=.02f;
    [NonSerialized] public float validationDelta;
    float Delta=>validationDelta>0?validationDelta:paused?0:Time.deltaTime;
    void Awake(){try{Initialize();}catch(Exception e){failed=true;status="ERROR / "+e.Message;Debug.LogException(e);}}
    public Vector3 Design(Vector3 world)
    {var d=world-origin;return new Vector3(Vector3.Dot(d,xAxis),Vector3.Dot(d,depthAxis),Vector3.Dot(d,upAxis));}
    public Vector3 World(Vector3 p)=>origin+xAxis*p.x+depthAxis*p.y+upAxis*p.z;
    public void Initialize()
    {
        if(initialized)return;
        OhtFabCycle.Require(oht&&slots.Length==6&&occupied.Length==6,"Stocker references/slots missing");
        origin=frameOrigin.position;xAxis=(frameX.position-origin).normalized;depthAxis=-(frameFront.position-origin).normalized;upAxis=Vector3.up;
        OhtFabCycle.Require(Mathf.Abs(Vector3.Dot(xAxis,depthAxis))<.001f,"Invalid stocker axes");
        shutterClosed=shutter.position;originalPanels=cutawayPanels.Select(r=>r.enabled).ToArray();
        ResetStoredPreview();
        var box=BoundsOf(oht.foup.GetComponentsInChildren<Renderer>(true));var basePoint=Design(oht.foupDock.position);
        payloadMin=box.min-basePoint;payloadMax=box.max-basePoint;
        obstacles=fixedParts.Select(r=>BoundsOf(new[]{r})).ToArray();
        OhtFabCycle.Require(payloadMax.x-payloadMin.x<.45f&&payloadMax.z-payloadMin.z<.40f,"Unexpected FOUP envelope");
        foreach(var slot in slots)
        {var p=Design(slot.position);OhtFabCycle.Require(Mathf.Abs(p.x)<.60f&&p.z>.60f&&p.z+payloadMax.z<2.5f,"Slot outside stocker envelope");}
        initialized=true;ValidateMechanism();
    }
    public void ResetStoredPreview()
    {
        OhtFabCycle.Require(!Application.isPlaying||!running,"Cannot reset moving stocker");
        OhtFabCycle.Require(!heldInspections.Any(id=>!string.IsNullOrEmpty(id)),"Cannot reset occupied HOLD inventory");
        origin=frameOrigin.position;xAxis=(frameX.position-origin).normalized;depthAxis=-(frameFront.position-origin).normalized;upAxis=Vector3.up;
        if(!initialized)shutterClosed=shutter.position;
        SetBaseImmediate(new Vector3(Design(slots[0].position).x,Lane,Design(slots[0].position).z-Release));
        oht.foup.rotation=oht.stationCarriers[0].rotation;oht.foup.position+=slots[0].position-oht.foupDock.position;oht.foup.SetParent(slots[0],true);oht.foup.gameObject.SetActive(true);
        location=CarrierLocation.Stored;reservedSlot=0;occupied=new[]{true,false,false,true,true,false};
        shutter.position=shutterClosed;doorOpen=running=paused=failed=false;outgoingRuns=incomingRuns=0;status="STORED / SLOT 01";
    }
    void SetBaseImmediate(Vector3 target)
    {
        var difference=target-Design(attachPoint.position);
        elevator.position+=upAxis*difference.z;slider.position+=xAxis*difference.x;fork.position+=depthAxis*difference.y;
    }
    Bounds BoundsOf(Renderer[] renderers)
    {
        var result=new Bounds();bool first=true;
        foreach(var r in renderers)
        {
            var mesh=r.GetComponent<MeshFilter>();if(!mesh||!mesh.sharedMesh)continue;var b=mesh.sharedMesh.bounds;
            for(int i=0;i<8;i++)
            {
                var p=Design(r.transform.TransformPoint(b.center+Vector3.Scale(b.extents,new Vector3((i&1)==0?-1:1,(i&2)==0?-1:1,(i&4)==0?-1:1))));
                if(first){result=new Bounds(p,Vector3.zero);first=false;}else result.Encapsulate(p);
            }
        }
        OhtFabCycle.Require(!first,"Missing stocker mesh bounds");return result;
    }
    static bool Overlap(Bounds a,Bounds b)=>Mathf.Min(a.max.x,b.max.x)-Mathf.Max(a.min.x,b.min.x)>.001f&&Mathf.Min(a.max.y,b.max.y)-Mathf.Max(a.min.y,b.min.y)>.001f&&Mathf.Min(a.max.z,b.max.z)-Mathf.Max(a.min.z,b.min.z)>.001f;
    public void ValidateMechanism()
    {
        if(!initialized)return;
        foreach(var part in forkParts)
        {
            var b=BoundsOf(new[]{part});
            for(int i=0;i<obstacles.Length;i++)OhtFabCycle.Require(!Overlap(b,obstacles[i]),"Fork crosses "+fixedParts[i].name);
            OhtFabCycle.Require(!Overlap(b,BoundsOf(shutter.GetComponentsInChildren<Renderer>())) ,"Fork crosses I/O shutter");
        }
        if(location!=CarrierLocation.Fork)return;
        var p=Design(oht.foupDock.position);var payload=new Bounds((payloadMin+payloadMax)*.5f+p,payloadMax-payloadMin);
        for(int i=0;i<obstacles.Length;i++)OhtFabCycle.Require(!Overlap(payload,obstacles[i]),"FOUP crosses "+fixedParts[i].name);
        foreach(var moving in movingParts)OhtFabCycle.Require(!Overlap(payload,BoundsOf(new[]{moving})),"FOUP crosses "+moving.name);
        for(int i=0;i<slots.Length;i++)if(occupied[i])
        {var other=new Bounds(Design(slots[i].position)+(payloadMin+payloadMax)*.5f,payloadMax-payloadMin);OhtFabCycle.Require(!Overlap(payload,other),"FOUP crosses occupied slot "+(i+1));}
        if(payload.min.y<-.69f&&payload.max.y>-.75f)
            OhtFabCycle.Require(doorOpen&&payload.min.x>.29f&&payload.max.x<.85f&&payload.min.z>1.02f&&payload.max.z<1.5775f,"FOUP crosses closed/wrong opening");
        OhtFabCycle.Require(Vector3.Distance(oht.foupDock.position,attachPoint.position)<.002f,"FOUP slipped off stocker fork");
    }
    void State(string next){status=next;Debug.Log("STOCKER_CYCLE "+status);}
    IEnumerator Move(Transform item,Vector3 target,float speed)
    {
        var start=item.position;float duration=Mathf.Max(.18f,Vector3.Distance(start,target)/speed);
        for(float t=0;t<duration;){t+=Delta;item.position=Vector3.Lerp(start,target,Mathf.SmoothStep(0,1,Mathf.Clamp01(t/duration)));ValidateMechanism();yield return null;}
        item.position=target;ValidateMechanism();
    }
    IEnumerator X(float target){yield return Move(slider,slider.position+xAxis*(target-Design(attachPoint.position).x),.55f);}
    IEnumerator Z(float target){yield return Move(elevator,elevator.position+upAxis*(target-Design(attachPoint.position).z),.50f);}
    IEnumerator Y(float target){yield return Move(fork,fork.position+depthAxis*(target-Design(attachPoint.position).y),.45f);}
    IEnumerator Door(bool open)
    {
        if(!open)OhtFabCycle.Require(Design(attachPoint.position).y>-.27f,"Retract fork before closing shutter");
        yield return Move(shutter,shutterClosed+(open?upAxis*.60f:Vector3.zero),.55f);doorOpen=open;
    }
    void Grab()
    {
        OhtFabCycle.Require(Vector3.Distance(oht.foupDock.position,attachPoint.position)<.002f,"Stocker fork pickup misaligned");
        oht.foup.SetParent(attachPoint,true);location=CarrierLocation.Fork;
    }
    IEnumerator DispatchSteps()
    {
        if(AtPort)yield break;
        OhtFabCycle.Require(Stored&&!running&&!failed&&(CanDispatchReserved||normalExport),"Carrier not available in reserved slot");running=true;paused=false;
        var source=Design(slots[reservedSlot].position);var port=Design(ioDock.position);
        State("APPROACH SLOT "+(reservedSlot+1).ToString("D2"));yield return Y(Lane);yield return X(source.x);yield return Z(source.z-Release);yield return Y(source.y);yield return Z(source.z);
        Grab();occupied[reservedSlot]=false;yield return Z(source.z+Clearance);
        State("EXTRACT FROM SLOT");yield return Y(Lane);yield return Z(port.z+Clearance);yield return X(port.x);
        State("OPEN I/O SHUTTER");yield return Door(true);
        State("DELIVER TO I/O");yield return Y(port.y);yield return Z(port.z);
        oht.foup.SetParent(ioDock,true);location=CarrierLocation.Port;
        OhtFabCycle.Require(Vector3.Distance(oht.foupDock.position,ioDock.position)<.002f,"I/O placement failed");
        yield return Z(port.z-Release);yield return Y(Lane);yield return Door(false);
        outgoingRuns++;running=false;State("READY FOR OHT PICKUP");
    }
    IEnumerator ReceiveSteps()
    {
        OhtFabCycle.Require(AtPort&&!running&&!failed&&!occupied[reservedSlot],"Return slot not free or I/O has no FOUP");
        OhtFabCycle.Require(Vector3.Distance(oht.foupDock.position,ioDock.position)<.002f&&!oht.Held,"Incoming FOUP not seated");running=true;paused=false;
        var port=Design(ioDock.position);var target=Design(slots[reservedSlot].position);
        State("OPEN I/O SHUTTER");yield return Y(Lane);yield return X(port.x);yield return Z(port.z-Release);yield return Door(true);
        State("PICK RETURNED FOUP");yield return Y(port.y);yield return Z(port.z);Grab();yield return Z(port.z+Clearance);
        State("RETRACT INTO STOCKER");yield return Y(Lane);yield return Door(false);
        yield return Z(target.z+Clearance);yield return X(target.x);
        State("STORE IN SLOT "+(reservedSlot+1).ToString("D2"));yield return Y(target.y);yield return Z(target.z);
        oht.foup.SetParent(slots[reservedSlot],true);location=CarrierLocation.Stored;occupied[reservedSlot]=true;
        OhtFabCycle.Require(Vector3.Distance(oht.foupDock.position,slots[reservedSlot].position)<.002f,"Storage slot placement failed");
        yield return Z(target.z-Release);yield return Y(Lane);incomingRuns++;running=false;State("STORED / SLOT "+(reservedSlot+1).ToString("D2"));
    }
    public void RemoveSimulationLot(int slot,string inspection)
    {
        OhtFabCycle.Require(!running&&!failed&&!oht.Running&&!oht.Held&&(Stored||Exported),"Wait for stationary stocker and OHT");
        OhtFabCycle.Require(IsHeldSlot(slot)&&heldInspections[slot]==inspection&&occupied[slot],"Manual removal slot/inspection mismatch");
        OhtFabCycle.Require(oht.HeldLots.Any(item=>item.slot==slot&&item.inspectionId==inspection&&oht.CanManualRemove(item)),"Manual removal not available");
        bool active=slot==reservedSlot&&Stored;
        var payload=active?oht.foup:slots[slot].Find("HOLD_FOUP_"+inspection);
        OhtFabCycle.Require(payload,"Stored simulation FOUP missing");
        payload.gameObject.SetActive(false);
        if(active)location=CarrierLocation.Exported;
        else if(Application.isPlaying)Destroy(payload.gameObject);else DestroyImmediate(payload.gameObject);
        occupied[slot]=false;heldInspections[slot]=null;
        State("MANUAL SIMULATION REMOVAL · SLOT "+(slot+1).ToString("D2")+" FREE / ORIGINAL VERDICT UNCHANGED");
    }
    public IEnumerator ExportNormal(int slot,string inspection)
    {
        OhtFabCycle.Require(!running&&!failed&&!oht.Held&&(Stored||Exported),"Stocker must be idle before normal export");
        OhtFabCycle.Require(IsHeldSlot(slot)&&heldInspections[slot]==inspection&&occupied[slot],"Normal export slot/inspection mismatch");
        OhtFabCycle.Require(oht.HeldLots.Any(item=>item.slot==slot&&item.inspectionId==inspection&&oht.CanAutoExport(item)),"Original inspection and prediction are not both OK");
        var activeFoup=oht.foup;var activeDock=oht.foupDock;int activeSlot=reservedSlot;var activeLocation=location;
        bool isActive=slot==reservedSlot&&Stored;
        var payload=isActive?activeFoup:slots[slot].Find("HOLD_FOUP_"+inspection);
        OhtFabCycle.Require(payload,"Normal export carrier missing");
        string dockPath="";for(var node=activeDock;node!=activeFoup;node=node.parent)
        {OhtFabCycle.Require(node,"FOUP dock is outside carrier hierarchy");dockPath=node.name+(dockPath.Length==0?"":"/"+dockPath);}
        var payloadDock=isActive?activeDock:payload.Find(dockPath);
        OhtFabCycle.Require(payloadDock,"Normal export dock missing");
        oht.foup=payload;oht.foupDock=payloadDock;reservedSlot=slot;location=CarrierLocation.Stored;normalExport=true;
        try
        {
            yield return Dispatch();OhtFabCycle.Require(!failed&&AtPort&&!Running&&!DoorOpen,"Normal export dispatch failed");
            State("NORMAL OUTBOUND / HANDOFF · "+inspection);
            // Simulation boundary: stocker I/O hands the normal carrier to outbound logistics.
            for(float elapsed=0;elapsed<.7f;){elapsed+=Delta;yield return null;}
            payload.gameObject.SetActive(false);occupied[slot]=false;heldInspections[slot]=null;
            if(isActive)location=CarrierLocation.Exported;
            else
            {
                oht.foup=activeFoup;oht.foupDock=activeDock;reservedSlot=activeSlot;location=activeLocation;
                if(Application.isPlaying)Destroy(payload.gameObject);else DestroyImmediate(payload.gameObject);
            }
            State("NORMAL LOT EXPORTED · SLOT "+(slot+1).ToString("D2")+" FREE");
        }
        finally{normalExport=false;}
    }
    public IEnumerator Dispatch(){yield return Guard(DispatchSteps());}
    public IEnumerator Receive(){yield return Guard(ReceiveSteps());}
    IEnumerator Guard(IEnumerator task)
    {
        while(true)
        {
            object item;try{if(!task.MoveNext())yield break;item=task.Current;}
            catch(Exception e){failed=true;running=false;State("STOPPED / "+e.Message);Debug.LogException(e);yield break;}
            if(item is IEnumerator child){yield return Guard(child);if(failed)yield break;}else yield return item;
        }
    }
    public void NotifyOhtPickup()
    {OhtFabCycle.Require(AtPort&&!running&&!doorOpen,"Stocker not ready for OHT pickup");location=CarrierLocation.InTransit;State("OHT IN TRANSIT / RETURN SLOT RESERVED");}
    public void NotifyOhtDropoff()
    {OhtFabCycle.Require(location==CarrierLocation.InTransit&&!running,"Unexpected OHT return");location=CarrierLocation.Port;State("RETURNED FOUP AT I/O");}
    public void StartDispatch(){if(!running&&!oht.Running&&Stored&&!failed&&CanDispatchReserved)StartCoroutine(Dispatch());}
    public void StartReceive(){if(!running&&!oht.Running&&AtPort&&!failed)StartCoroutine(Receive());}
    public void SetPaused(bool value){paused=value;}
    public void TogglePause(){if(running)paused=!paused;}
    public void ToggleInside(){inside=!inside;for(int i=0;i<cutawayPanels.Length;i++)cutawayPanels[i].enabled=inside?false:originalPanels[i];}
    public void View(){foreach(var c in Camera.allCameras)if(!c.targetTexture)c.enabled=false;detail.enabled=true;}
    void OnDestroy(){if(background)Destroy(background);if(font)Destroy(font);}
    void OnGUI()
    {
        var old=GUI.matrix;GUI.matrix=Matrix4x4.Scale(Vector3.one*Mathf.Min(Screen.width/1280f,Screen.height/720f));
        if(FactoryControlBar.BeginPanel(FactoryControlBar.Equipment.Stocker,new Rect(15,15,860,360)))
        {
            if(!font)font=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Arial"},18);
            if(!background){background=new Texture2D(1,1);background.SetPixel(0,0,new Color32(15,27,42,245));background.Apply();}
            GUI.DrawTexture(new Rect(15,15,860,360),background);var label=new GUIStyle(GUI.skin.label){font=font,fontSize=16,wordWrap=true,normal={textColor=Color.white}};var button=new GUIStyle(GUI.skin.button){font=font,fontSize=16};
            GUI.Label(new Rect(28,24,650,28),"MINI STOCKER | 6 SLOT | "+oht.carrier_id+" | SIMULATION",label);
            GUI.Label(new Rect(28,56,650,28),(paused?"PAUSED | ":"")+status,label);
            GUI.Label(new Rect(28,87,650,28),"보관 "+OccupiedCount+" / 6 | "+(Stored?"반환 예약: 없음":"반환 예약: SLOT "+(reservedSlot+1).ToString("D2"))+" | "+location,label);
            bool enabled=GUI.enabled;GUI.enabled=enabled&&!running&&!oht.Running&&!failed&&Stored&&CanDispatchReserved;
            if(GUI.Button(new Rect(28,124,145,32),"출고",button))StartDispatch();
            GUI.enabled=enabled&&!running&&!oht.Running&&!failed&&AtPort;if(GUI.Button(new Rect(183,124,145,32),"입고",button))StartReceive();
            GUI.enabled=enabled&&running;if(GUI.Button(new Rect(338,124,145,32),paused?"계속":"일시 정지",button))TogglePause();GUI.enabled=enabled;
            if(GUI.Button(new Rect(493,124,175,32),inside?"외관 보기":"내부 보기",button))ToggleInside();
            if(GUI.Button(new Rect(28,172,180,30),"스토커 시점",button))View();
            GUI.Label(new Rect(222,173,600,28),"격리·대기 "+oht.HeldLots.Count+" LOT · 빈 슬롯 "+occupied.Count(v=>!v)+" · 정상 자동 출고 / NG 승인 전 HOLD 유지",label);
            int row=0;foreach(var item in oht.HeldLots)
            {
                if(row>=4)break;
                GUI.Label(new Rect(28,210+row*32,650,31),oht.HeldLotSummary(item),label);
                if(GUI.Button(new Rect(688,210+row*32,120,28),"결과 보기",button))
                {
                    var gateway=GatewayInspectionBridge.Instance;var job=gateway?gateway.FullCycleJob(item.inspectionId):null;
                    if(job!=null&&ProcessAnalysisView.Instance)ProcessAnalysisView.Instance.OpenFullCycle(job);
                }
                GUI.enabled=enabled&&oht.CanManualRemove(item);
                bool remove=GUI.Button(new Rect(818,210+row*32,38,28),new GUIContent("×","시연 FOUP 수동 반출 · 슬롯 비움 / 검사·TCAD 기록 유지"),button);
                GUI.enabled=enabled;
                if(remove){oht.ManualRemove(item);break;}
                row++;
            }
            GUI.Label(new Rect(28,342,820,25),"×: 시연 슬롯 비우기 · 검사·진단·TCAD 기록 유지 / 정상 승인 아님",label);
        }
        GUI.matrix=old;
    }
}
