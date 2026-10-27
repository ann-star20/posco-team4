using System;
using System.Collections;
using System.Linq;
using UnityEngine;

// Carrier logistics and existing equipment animations share one simulated LOT.
[DefaultExecutionOrder(100)]
public partial class OhtFabCycle : MonoBehaviour
{
    [Serializable] class Layout {public Vector3[] points;}
    public TextAsset route;
    public Transform carrier,lift,attachPoint,leftJaw,rightJaw,foup,foupGrip,foupDock;
    public Transform[] docks,stationCarriers,beltTops,beltBottoms;
    public Material beltMaterial;
    public IntegratedOxidationCycle oxidation;
    public EllipsometerCycle ellipsometer;
    public IonImplantCycle implanter;
    public StockerCycle stocker;
    public Camera overview,followCamera;
    public float travelSpeed=1.6f,hoistSpeed=.85f;
    public string machine_id="OHT_01",lot_id="LOT-001",carrier_id="FOUP-001";
    public string status="READY",command="NONE",source_port="STOCKER_IO",destination_port="OX_LOADPORT";
    public bool completed,failed;
    public int placements,completedRuns;
    public bool Running=>running;
    public bool Held=>held;
    public bool Paused=>paused;
    bool running,paused,held,initialized;
    Vector3[] points;
    float[] lengths,stopDistances;
    float distance;
    Vector3 liftHome,leftClosed,rightClosed;
    Quaternion carrierRotation;
    Transform[] belts;
    Texture2D panelBackground;
    Font panelFont;
    public string StartBlockReason
    {
        get
        {
            if(failed)return "OHT 오류 · "+status;
            if(!initialized)return "OHT 초기화 대기 · 설비 연결 상태를 확인하세요.";
            if(running)return "OHT 이송이 이미 진행 중입니다.";
            if(!oxidation||!ellipsometer||!implanter)return "OHT 설비 연결이 없습니다.";
            if(ellipsometer.lotHeld&&!IsParked(ellipsometer.InspectionId))return "ELLIP-01 / "+ellipsometer.lotId+" HOLD · 검사 결과·재측정·검토 승인 확인 필요";
            if(oxidation.Running)return "산화로 공정 진행 중 · 설비 종료 후 이송을 시작하세요.";
            if(ellipsometer.Running)return "산화막 검사 진행 중 · 검사 종료 후 이송을 시작하세요.";
            if(implanter.Running)return "이온주입 공정 진행 중 · 설비 종료 후 이송을 시작하세요.";
            if(stocker&&stocker.failed)return "스토커 오류 · 설비 상태를 확인하세요.";
            if(stocker&&stocker.IsHeldSlot(stocker.reservedSlot)&&stocker.NextFreeSlot<0)return "스토커 가득 참 · HOLD 격리 슬롯 확보 후 새 LOT 투입 가능";
            if(stocker&&stocker.Running)return "스토커 입출고 진행 중 · 완료 후 이송을 시작하세요.";
            return null;
        }
    }
    string[] portIds={"STOCKER_IO","OX_LOADPORT","ELLIP_LOADPORT","IMP_LOADPORT"};
    [NonSerialized] public float validationDelta;
    float Delta=>validationDelta>0?validationDelta:paused?0:Time.deltaTime;
    public static void Require(bool ok,string reason){if(!ok)throw new InvalidOperationException(reason);}
    void Awake()
    {
        try{Initialize();}catch(Exception e){failed=true;status="ERROR / "+e.Message;Debug.LogException(e);}
    }
    void Initialize()
    {
        if(initialized)return;
        Require(route&&carrier&&lift&&attachPoint&&foup&&oxidation&&ellipsometer&&implanter,"OHT references missing");
        points=JsonUtility.FromJson<Layout>(route.text).points;
        Require(points!=null&&points.Length>100&&docks.Length==4&&stationCarriers.Length==4,"OHT route/stations missing");
        lengths=new float[points.Length+1];
        for(int i=0;i<points.Length;i++)lengths[i+1]=lengths[i]+Vector3.Distance(points[i],points[(i+1)%points.Length]);
        stopDistances=new float[4];
        for(int i=0;i<4;i++)
        {
            var target=docks[i].position;target.y=points[0].y;
            int nearest=Enumerable.Range(0,points.Length).OrderBy(j=>Vector3.Distance(points[j],target)).First();
            Require(Vector2.Distance(new Vector2(points[nearest].x,points[nearest].z),new Vector2(target.x,target.z))<.09f,"Dock outside hoist alignment range: "+docks[i].name);
            stopDistances[i]=lengths[nearest];
        }
        liftHome=lift.localPosition;leftClosed=leftJaw.localPosition;rightClosed=rightJaw.localPosition;carrierRotation=carrier.rotation;
        Require(beltTops.Length==2&&beltBottoms.Length==2,"Two hoist belts required");
        belts=new Transform[2];
        for(int i=0;i<2;i++)
        {
            var belt=GameObject.CreatePrimitive(PrimitiveType.Cube);belt.name="OHT_Live_Belt_"+i;
            Destroy(belt.GetComponent<Collider>());belt.transform.SetParent(transform,true);belt.GetComponent<Renderer>().sharedMaterial=beltMaterial;belts[i]=belt.transform;
        }
        oxidation.Initialize();ellipsometer.Initialize();implanter.Initialize();
        // Port-specific FOUP representations preserve each existing wafer/door animation.
        // Continuous transport owns these only while running; idle allows individual demos.
        SetTransportOwnership(false);
        distance=stopDistances[0];Pose(distance);if(stocker)stocker.Initialize();else SetFoupAt(0);Jaws(false);UpdateBelts();initialized=true;
        if(!Camera.allCameras.Any(c=>!c.targetTexture))overview.enabled=true;
    }
    void SetDocked(int port)
    {oxidation.transportDocked=port==1;ellipsometer.transportDocked=port==2;implanter.transportDocked=port==3;}
    void SetTransportOwnership(bool owned,int pickupPort=-1)
    {
        oxidation.transportControlled=ellipsometer.transportControlled=implanter.transportControlled=owned;
        SetDocked(-1);
        stationCarriers[0].gameObject.SetActive(false);
        // Keep the completed tool's FOUP visible until Pick swaps it for the transport mesh.
        for(int i=1;i<stationCarriers.Length;i++)stationCarriers[i].gameObject.SetActive((!owned||i==pickupPort)&&!CurrentCarrierParked(i));
    }
    void State(string next,string cmd)
    {status=next;command=cmd;Debug.Log("OHT_FAB "+status+" | "+source_port+" -> "+destination_port+" | "+carrier_id);}
    public static Quaternion RailRotation(Vector3 direction,Quaternion baseline)
    {
        var horizontal=Vector3.ProjectOnPlane(direction,Vector3.up);
        Require(horizontal.sqrMagnitude>.00000001f,"OHT rail has no horizontal direction");
        // FromToRotation can roll 180 degrees at the reverse straight; turn only around world up.
        return Quaternion.AngleAxis(Vector3.SignedAngle(Vector3.right,horizontal,Vector3.up),Vector3.up)*baseline;
    }
    void Pose(float along)
    {
        float d=Mathf.Repeat(along,lengths[lengths.Length-1]);int i=0;
        while(i<points.Length-1&&lengths[i+1]<=d)i++;
        int next=(i+1)%points.Length;float t=(d-lengths[i])/(lengths[i+1]-lengths[i]);
        carrier.position=Vector3.Lerp(points[i],points[next],t);
        var forward=(points[next]-points[i]).normalized;
        carrier.rotation=RailRotation(forward,carrierRotation);
    }
    void Jaws(bool closed)
    {leftJaw.localPosition=leftClosed*(closed?1:1.4f);rightJaw.localPosition=rightClosed*(closed?1:1.4f);}
    void UpdateBelts()
    {
        if(belts==null)return;
        for(int i=0;i<2;i++)
        {
            var a=beltTops[i].position;var b=beltBottoms[i].position;
            belts[i].position=(a+b)*.5f;belts[i].rotation=Quaternion.FromToRotation(Vector3.up,a-b);
            belts[i].localScale=new Vector3(.02f,Vector3.Distance(a,b),.006f);
        }
    }
    void LateUpdate()
    {
        UpdateBelts();
        if(followCamera&&followCamera.enabled)
        {followCamera.transform.position=carrier.position+new Vector3(2,1.1f,-3.2f);followCamera.transform.LookAt(carrier.position-Vector3.up*.75f);}
    }
    IEnumerator Wait(float seconds)
    {for(float t=0;t<seconds;){t+=Delta;yield return null;}}
    IEnumerator ShiftLift(Vector3 to)
    {
        var from=lift.position;float duration=Mathf.Max(.3f,Vector3.Distance(from,to)/hoistSpeed);
        for(float t=0;t<duration;){t+=Delta;lift.position=Vector3.Lerp(from,to,Mathf.SmoothStep(0,1,Mathf.Clamp01(t/duration)));yield return null;}
        lift.position=to;
    }
    IEnumerator GripTo(Vector3 target){yield return ShiftLift(lift.position+target-attachPoint.position);}
    IEnumerator Retract(){yield return ShiftLift(lift.parent.TransformPoint(liftHome));}
    void SetFoupAt(int port)
    {
        foup.SetParent(docks[port],true);foup.rotation=stationCarriers[port].rotation;
        foup.position+=docks[port].position-foupDock.position;foup.gameObject.SetActive(true);held=false;
    }
    IEnumerator OrientPayload(int port)
    {
        var start=foup.rotation;var target=stationCarriers[port].rotation;
        for(float t=0;t<.6f;){t+=Delta;foup.rotation=Quaternion.Slerp(start,target,Mathf.SmoothStep(0,1,Mathf.Clamp01(t/.6f)));foup.position+=attachPoint.position-foupGrip.position;yield return null;}
        foup.rotation=target;foup.position+=attachPoint.position-foupGrip.position;
    }
    IEnumerator Pick(int port,bool quarantine=false)
    {
        Require(!held&&!oxidation.Running&&!ellipsometer.Running&&!implanter.Running,"Equipment is still processing");
        if(port==0&&stocker)Require(stocker.AtPort&&!stocker.Running&&!stocker.DoorOpen,"Wait for stocker dispatch completion");
        Require(port!=2||ellipsometer.CanProceed||quarantine&&ellipsometer.SafeToUnload,"Metrology HOLD or unsafe unload");
        Require(port!=3||implanter.SafeToUnload,"Implanter unsafe unload");SetDocked(-1);
        stationCarriers[port].gameObject.SetActive(false);SetFoupAt(port);
        State("LOWERING / PICK","PICK");Jaws(false);yield return GripTo(foupGrip.position);
        Require(Vector3.Distance(attachPoint.position,foupGrip.position)<.002f,"FOUP handle not aligned");
        Jaws(true);yield return Wait(.35f);foup.SetParent(attachPoint,true);held=true;
        if(port==0&&stocker)stocker.NotifyOhtPickup();
        State("RAISING / LOADED","PICK");yield return Retract();
        Require(Vector3.Distance(attachPoint.position,foupGrip.position)<.002f,"FOUP slipped in gripper");
        if(port==2&&!quarantine)departedInspections.Add(ellipsometer.InspectionId);
    }
    IEnumerator Travel(int port)
    {
        Require(Vector3.Distance(lift.position,lift.parent.TransformPoint(liftHome))<.002f,"Hoist must retract before travel");
        if(held)Require(foupDock.position.y>4.20f,"Payload is too low for tools");
        float from=distance,total=lengths[lengths.Length-1],to=stopDistances[port];
        float remaining=Mathf.Repeat(to-from,total);
        // Arriving at the current stop is not an instruction to drive another loop.
        if(Mathf.Min(remaining,total-remaining)<=.002f){distance=to;Pose(distance);yield break;}
        State("MOVING","MOVE");
        while(to<from+.001f)to+=total;
        float span=to-from,duration=span/travelSpeed+.6f;
        for(float t=0;t<duration;){t+=Delta;distance=from+span*Mathf.SmoothStep(0,1,Mathf.Clamp01(t/duration));Pose(distance);yield return null;}
        distance=to;Pose(distance);distance=Mathf.Repeat(distance,total);
    }
    IEnumerator Place(int port)
    {
        Require(held,"No FOUP to place");yield return OrientPayload(port);State("LOWERING / PLACE","PLACE");
        var target=foupGrip.position+(docks[port].position-foupDock.position);yield return GripTo(target);
        foup.SetParent(docks[port],true);held=false;
        Require(Vector3.Distance(foupDock.position,docks[port].position)<.002f,"FOUP not seated on loadport");
        if(port==0&&stocker)stocker.NotifyOhtDropoff();
        Jaws(false);yield return Wait(.35f);
        if(port>0){stationCarriers[port].gameObject.SetActive(true);foup.gameObject.SetActive(false);SetDocked(port);}
        placements++;State("RAISING / EMPTY","PLACE");yield return Retract();
    }
    IEnumerator Process(int port)
    {
        State(port==1?"OXIDATION / WAIT WAFER RETURN":port==2?"METROLOGY / WAIT WAFER RETURN":"IMPLANT / WAIT WAFER RETURN","WAIT");
        if(port==1)oxidation.StartCycle();else if(port==2)ellipsometer.StartScan();else implanter.StartCycle();
        for(float elapsed=0;;)
        {
            bool error=port==1?oxidation.failed:port==2?ellipsometer.failed:implanter.failed;
            bool done=port==1?oxidation.completed:port==2?ellipsometer.completed:implanter.completed;
            Require(!error,"Equipment animation interlock: "+portIds[port]);
            if(done)break;
            if(port==3&&!implanter.Running&&implanter.status.StartsWith("CSV TEST DATA NOT READY",StringComparison.Ordinal))
            {
                StateOnce("이온주입 CSV 입력 대기 · Jetson 데이터 받기 후 같은 FOUP로 자동 재시도");
                elapsed=0;yield return Wait(.5f);
                if(JetsonTestDataView.TryIonInput(implanter,out var ready))
                {implanter.StartCycle();State("IMPLANT / WAIT WAFER RETURN","WAIT");}
                continue;
            }
            elapsed+=Delta;Require(elapsed<240,"Equipment completion timed out: "+portIds[port]);yield return null;
        }
        Require(!implanter.AnyGateOpen,"Implanter gate left open");
    }
    void StateOnce(string value){if(status!=value)State(value,"WAIT");}
    IEnumerator Sequence()
    {
        placements=0;completed=failed=false;running=true;paused=false;
        Require(PrepareNextLot(2),"Next simulation LOT preparation failed");
        SetTransportOwnership(true);
        oxidation.lotId=ellipsometer.lotId=implanter.incomingLotId=lot_id;
        Require(JetsonTestDataView.PrepareIncoming(ellipsometer,true),"CSV test wafer preparation failed; check CSV panel");
        oxidation.ResetPreview();ellipsometer.ResetPreview();implanter.ResetPreview();
        if(stocker)
        {
            source_port=portIds[0];destination_port=portIds[1];State("STOCKER DISPATCH / WAIT I/O READY","WAIT");
            yield return stocker.Dispatch();Require(stocker.AtPort&&!stocker.failed&&!stocker.Running,"Stocker dispatch failed");
        }
        for(int destination=1;destination<=3;destination++)
        {
            int source=destination-1;source_port=portIds[source];destination_port=portIds[destination];
            yield return Pick(source);yield return Travel(destination);yield return Place(destination);yield return Process(destination);
            if(destination>=2&&NeedsQuarantine(destination))
            {yield return ReturnHeld(destination);yield break;}
        }
        yield return ReturnHeld(3);
    }
    IEnumerator Guard(IEnumerator task)
    {
        while(true)
        {
            object item;
            try{if(!task.MoveNext())yield break;item=task.Current;}
            catch(Exception e){failed=true;running=false;State("STOPPED / "+e.Message,"STOP");Debug.LogException(e);yield break;}
            if(item is IEnumerator child){yield return Guard(child);if(failed)yield break;}else yield return item;
        }
    }
    public void StartCycle()
    {
        if(running)return;
        if(singleDockedPort>0){State("설비별 FOUP가 "+portIds[singleDockedPort]+"에 있습니다. 다음 설비 시작 버튼으로 이어서 진행하세요.","WAIT");return;}
        if(ellipsometer.SafeToUnload&&!IsParked(ellipsometer.InspectionId))
        {StartRecovery(2);return;}
        if(implanter.SafeToUnload&&!IsParked(implanter.InspectionId))
        {StartRecovery(3);return;}
        var blocked=StartBlockReason;
        if(!string.IsNullOrEmpty(blocked)){State("START BLOCKED / "+blocked,"WAIT");return;}
        if(!JetsonTestDataView.CanPrepareOht(ellipsometer,implanter,out var inputReason))
        {State("START WAIT / "+inputReason,"WAIT");return;}
        StartCoroutine(Guard(Sequence()));
    }
    public void TogglePause()
    {
        if(!running)return;paused=!paused;
        oxidation.SetTransportPaused(paused);ellipsometer.SetTransportPaused(paused);implanter.SetTransportPaused(paused);
        if(stocker)stocker.SetPaused(paused);
    }
    public void ToggleCamera()
    {
        bool follow=!followCamera.enabled;foreach(var camera in Camera.allCameras)if(!camera.targetTexture)camera.enabled=false;
        (follow?followCamera:overview).enabled=true;
    }
    void OnDisable()
    {
        if(!initialized)return;
        oxidation.transportControlled=ellipsometer.transportControlled=implanter.transportControlled=false;
        oxidation.SetTransportPaused(false);ellipsometer.SetTransportPaused(false);implanter.SetTransportPaused(false);
    }
    void OnDestroy(){if(panelBackground)Destroy(panelBackground);}
    void OnGUI()
    {
        var old=GUI.matrix;GUI.matrix=Matrix4x4.Scale(Vector3.one*Mathf.Min(Screen.width/1280f,Screen.height/720f));
        if(FactoryControlBar.BeginPanel(FactoryControlBar.Equipment.OHT,new Rect(15,15,680,235)))
        {
            if(!panelBackground){panelBackground=new Texture2D(1,1);panelBackground.SetPixel(0,0,new Color32(15,27,42,245));panelBackground.Apply();}
            if(!panelFont)panelFont=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Arial"},16);
            GUI.DrawTexture(new Rect(15,15,680,235),panelBackground);var label=new GUIStyle(GUI.skin.label){font=panelFont,fontSize=16,wordWrap=true,normal={textColor=Color.white}};
            GUI.Label(new Rect(29,23,650,27),"OHT-01 | "+carrier_id+" | "+lot_id+" | SIMULATION",label);
            GUI.Label(new Rect(29,54,650,27),running?(paused?"일시 정지 · ":"")+status:completed?"이송 완료":failed?"OHT 오류 · 아래 사유 확인":string.IsNullOrEmpty(StartBlockReason)?"이송 시작 가능":"이송 시작 대기 · 아래 사유 확인",label);
            GUI.Label(new Rect(29,84,650,27),source_port+" → "+destination_port,label);
            bool was=GUI.enabled;GUI.enabled=running||!failed;
            if(GUI.Button(new Rect(29,119,205,32),running?(paused?"Resume":"Pause"):"Start / Restart")){if(running)TogglePause();else StartCycle();}
            GUI.enabled=was;if(GUI.Button(new Rect(245,119,205,32),"OHT / Overview camera"))ToggleCamera();
            var reason=running?"설비 종료 후 NG/분석 대기 LOT는 스토커로 격리합니다. TCAD 수신은 LOT별로 계속됩니다.":StartBlockReason??(string.IsNullOrEmpty(HoldNotice)?null:HoldNotice);
            var notice=new GUIStyle(label){normal={textColor=string.IsNullOrEmpty(reason)?Color.white:new Color32(255,205,115,255)}};
            GUI.Label(new Rect(29,160,650,76),reason??"시작하면 공정 순서대로 FOUP 이송과 설비 시연을 실행합니다.\n이송 움직임은 ‘OHT / Overview camera’로 확대해서 볼 수 있습니다.",notice);
        }
        GUI.matrix=old;
    }
}
