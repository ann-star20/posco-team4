using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UI;

// A timed process visualization, not a vacuum or implantation physics solver.
public class IonImplantCycle : MonoBehaviour
{
    [Serializable] public class Arm
    {
        public Transform root,j1,j2,wrist,contact;
        public Renderer[] parts;
        public float elbowSign=-1;
        [NonSerialized] public Vector3 origin,x,y,up,command;
        [NonSerialized] public float l1,l2,tip,angle;
        public void Initialize()
        {
            j1.localRotation=j2.localRotation=wrist.localRotation=Quaternion.identity;
            origin=root.position;x=(j2.position-j1.position).normalized;up=j1.parent.TransformDirection(Vector3.forward).normalized;y=Vector3.Cross(up,x).normalized;
            l1=Vector3.Distance(j1.position,j2.position);l2=Vector3.Distance(j2.position,wrist.position);tip=Vector3.Distance(wrist.position,contact.position);
            Require(Vector3.Dot(up,Vector3.up)>.99f,"Robot is not upright");
        }
        public float Heading(Vector3 direction)=>Mathf.Atan2(Vector3.Dot(direction,y),Vector3.Dot(direction,x));
        public void Solve(Vector3 target,float heading)
        {
            var v=target-origin;float px=Vector3.Dot(v,x)-tip*Mathf.Cos(heading),py=Vector3.Dot(v,y)-tip*Mathf.Sin(heading);
            float r=Mathf.Sqrt(px*px+py*py);
            Require(r>Mathf.Abs(l1-l2)+.002f&&r<l1+l2-.002f,root.name+" unreachable: "+r);
            float a2=elbowSign*Mathf.Acos(Mathf.Clamp((r*r-l1*l1-l2*l2)/(2*l1*l2),-1,1));
            float a1=Mathf.Atan2(py,px)-Mathf.Atan2(l2*Mathf.Sin(a2),l1+l2*Mathf.Cos(a2));
            j1.localRotation=Quaternion.AngleAxis(a1*Mathf.Rad2Deg,Vector3.forward);j2.localRotation=Quaternion.AngleAxis(a2*Mathf.Rad2Deg,Vector3.forward);
            wrist.localRotation=Quaternion.AngleAxis((heading-a1-a2)*Mathf.Rad2Deg,Vector3.forward);
            j1.position+=up*Vector3.Dot(target-contact.position,up);
            Require(Vector3.Distance(contact.position,target)<.001f,"Robot endpoint error");
        }
    }
    public Arm atmosphere,vacuum;
    public Transform frameOrigin,frameX,frameY,carrier,carrierDoor,portDoor,outerDoor,innerDoor,processDoor;
    public Transform wafer,alignTarget,lockTarget,stageTarget,stage,tilt;
    public Renderer[] cutawayPanels;
    public Camera overview,detail,internalView;
    public Text monitor;
    public IonImplantDashboard dashboard;
    public bool AnyGateOpen=>portOpen||outerOpen||innerOpen||processOpen;
    public void TogglePause(){if(running)paused=!paused; if(dashboard)dashboard.Refresh();}
    public LineRenderer beam;
    public string status="READY";
    public float pressurePa=101325,dose,progress;
    public bool completed,failed;
    [NonSerialized] public bool transportControlled,transportDocked;
    public bool TransportAvailable=>!transportControlled||transportDocked;
    public bool SafeToUnload=>completed&&!running&&!failed&&!AnyGateOpen;
    public void SetTransportPaused(bool value){paused=value;}
    [NonSerialized] public float validationDelta;
    Vector3 origin,dx,dy,carrierStart,portStart,carrierDoorStart,outerStart,innerStart,processStart,waferStart,waferLocal,waferScale,stageStart;
    Quaternion waferRotation,tiltStart;
    Transform waferParent;
    bool initialized,running,paused,inside,portOpen,outerOpen,innerOpen,processOpen;
    readonly Stack<IEnumerator> steps=new Stack<IEnumerator>();
    public int completedRuns;
    public bool Running=>running;
    public bool Paused=>paused;
    public float targetDose=(float)IonDoseAssessment.MlTarget;
    [NonSerialized] public double approvedEpiDoping;
    [NonSerialized] public string approvedRecipeId;
    public bool useJetsonCsv=true;
    [field:NonSerialized] public JetsonTestDataProtocol.Selection SelectedCsv {get;private set;}
    [field:NonSerialized] public JetsonTestDataProtocol.Selection InspectionCsv {get;private set;}
    [field:NonSerialized] public GatewayLotConditions.Condition InspectionCondition {get;private set;}
    public bool SetCsvTest(JetsonTestDataProtocol.Selection selection)
    {
        if(running)return false;
        if(selection!=null&&(selection.measurement_source!="TCAD"||!JetsonTestDataProtocol.CanSelect(selection.row,"TCAD")))return false;
        SelectedCsv=selection==null?null:JsonUtility.FromJson<JetsonTestDataProtocol.Selection>(JsonUtility.ToJson(selection));
        useJetsonCsv=selection!=null;if(dashboard)dashboard.Refresh();return true;
    }
    public float energyKeV=80;
    public EllipsometerCycle lotQualityGate;
    public string incomingLotId="LOT-001";
    public string incomingWaferId="SIM-IMP01-WAFER13";
    public string InspectionId {get;private set;}
    public string InspectionUnitId {get;private set;}
    public bool LotBlocked=>lotQualityGate&&lotQualityGate.lotId==incomingLotId&&lotQualityGate.lotHeld;
    float Delta=>validationDelta>0?validationDelta:paused?0:Time.deltaTime;
    Vector3 Centre=>wafer.TransformPoint(wafer.GetComponent<MeshFilter>().sharedMesh.bounds.center);
    public Vector3 Design(Vector3 p){var v=p-origin;return new Vector3(Vector3.Dot(v,dx),Vector3.Dot(v,dy),v.y);}
    public Vector3 World(double x,double y,double z)=>origin+dx*(float)x+dy*(float)y+Vector3.up*(float)z;
    public static void Require(bool condition,string message){if(!condition)throw new InvalidOperationException(message);}
    void Awake(){Initialize();}
    public static bool InteriorTrim(Renderer part)=>part&&(part.name=="Front_Header"||part.name=="Rear_Header"||part.name.StartsWith("Port_Status_Panel_")||part.name=="Port_Status_LED"||part.name.StartsWith("Port_Status_LED."));
    public void Initialize()
    {
        cutawayPanels=(cutawayPanels??Array.Empty<Renderer>()).Concat(GetComponentsInChildren<Renderer>(true).Where(InteriorTrim)).Where(r=>r).Distinct().ToArray();
        if(initialized)
        {
            // Script reload restores cached scene state but not the arms' NonSerialized geometry.
            if(atmosphere.l1<=0||atmosphere.l2<=0||vacuum.l1<=0||vacuum.l2<=0){atmosphere.Initialize();vacuum.Initialize();}
            return;
        }
        origin=frameOrigin.position;dx=(frameX.position-origin).normalized;dy=(frameY.position-origin).normalized;
        Require(Mathf.Abs(Vector3.Dot(dx,dy))<.001f,"Invalid model axes");
        atmosphere.Initialize();vacuum.Initialize();
        carrierStart=carrier.position;portStart=portDoor.position;carrierDoorStart=carrierDoor.position;
        outerStart=outerDoor.position;innerStart=innerDoor.position;processStart=processDoor.position;
        waferParent=wafer.parent;waferLocal=wafer.localPosition;waferScale=wafer.localScale;waferRotation=wafer.localRotation;waferStart=Centre;
        stageStart=stage.position;tiltStart=tilt.localRotation;initialized=true;ResetPreview();
    }
    public void ResetPreview()
    {
        if(!initialized)return;
        if(Application.isPlaying&&GatewayInspectionBridge.Instance)GatewayInspectionBridge.Instance.CancelIon(InspectionId);
        running=paused=failed=completed=false;portOpen=outerOpen=innerOpen=processOpen=false;
        carrier.position=carrierStart;carrierDoor.position=carrierDoorStart;portDoor.position=portStart;
        outerDoor.position=outerStart;innerDoor.position=innerStart;processDoor.position=processStart;
        wafer.SetParent(waferParent,false);wafer.localPosition=waferLocal;wafer.localScale=waferScale;wafer.localRotation=waferRotation;
        stage.position=stageStart;tilt.localRotation=tiltStart;
        Home(atmosphere,World(-.35,.55,1.49),-dy);Home(vacuum,World(.10,1.8,1.49),dy);
        pressurePa=101325;dose=progress=0;if(beam)beam.enabled=false;SetState("READY");
    }
    void Home(Arm arm,Vector3 p,Vector3 direction){arm.command=p;arm.angle=arm.Heading(direction);arm.Solve(p,arm.angle);}
    void SetState(string state){status=state;Debug.Log("ION_CYCLE "+state);RefreshMonitor();}
    void RefreshMonitor()
    {
        if(dashboard){dashboard.Refresh();return;}
        if(monitor)monitor.text="ION IMPLANTATION\nSIMULATION / TCAD OFFLINE\n"+status+"\n"+energyKeV.ToString("F0")+" keV | B+\nDose "+dose.ToString("0.00E+00")+" / "+targetDose.ToString("0.00E+00")+" cm-2\nLoad lock "+pressurePa.ToString("0.0E+0")+" Pa\n"+(progress*100).ToString("F0")+"%";
    }
    IEnumerator Move(Transform obj,Vector3 target,float seconds)
    {
        var from=obj.position;
        for(float t=0;t<seconds;){t+=Delta;obj.position=Vector3.Lerp(from,target,Mathf.SmoothStep(0,1,Mathf.Clamp01(t/seconds)));yield return null;}
        obj.position=target;
    }
    IEnumerator Wait(float seconds){for(float t=0;t<seconds;){t+=Delta;yield return null;}}
    IEnumerator Robot(Arm arm,Vector3 target,Vector3 direction,float seconds)
    {
        var from=arm.command;float old=arm.angle,next=arm.Heading(direction),change=Mathf.DeltaAngle(old*Mathf.Rad2Deg,next*Mathf.Rad2Deg)*Mathf.Deg2Rad;
        for(float t=0;t<seconds;){t+=Delta;float f=Mathf.SmoothStep(0,1,Mathf.Clamp01(t/seconds));arm.Solve(Vector3.Lerp(from,target,f),old+change*f);ValidateArm(arm);yield return null;}
        arm.Solve(target,next);ValidateArm(arm);arm.command=target;arm.angle=next;
    }
    void ValidateArm(Arm arm)
    {
        var checks=new List<Renderer>(arm.parts);
        if(wafer.parent==arm.contact)checks.Add(wafer.GetComponent<Renderer>());
        foreach(var part in checks)
        {
            var bounds=part.GetComponent<MeshFilter>().sharedMesh.bounds;
            for(int i=0;i<8;i++)
            {
                var p=Design(part.transform.TransformPoint(bounds.center+Vector3.Scale(bounds.extents,new Vector3((i&1)==0?-1:1,(i&2)==0?-1:1,(i&4)==0?-1:1))));
                Require(p.x> -2.44f&&p.x<1.23f,"Robot side panel clearance: "+part.name+" "+p);
                if(arm==atmosphere)
                {
                    if(p.y>.94f||(p.y>.64f&&p.x>.205f&&p.x<.795f))Require(outerOpen&&p.y<1.325f&&Mathf.Abs(p.x-.5f)<.25f&&Mathf.Abs(p.z-1.49f)<.075f,"Outer loadlock clearance: "+part.name+" "+p);
                    if(p.y<-.56f)Require(portOpen&&p.x> -1.265f&&p.x<-.835f&&p.z>1.30f&&p.z<1.69f,"Port opening clearance: "+part.name+" "+p);
                }
                else
                {
                    Require(p.y>.66f&&p.y<3.23f,"Vacuum robot envelope: "+part.name+" "+p);
                    if(p.y<.995f||(p.y<1.37f&&p.x>.205f&&p.x<.795f))Require(innerOpen&&Mathf.Abs(p.x-.5f)<.25f&&Mathf.Abs(p.z-1.49f)<.075f,"Inner loadlock clearance: "+part.name+" "+p);
                    if(p.y>2.13f)Require(processOpen&&Mathf.Abs(p.x-.5f)<.79f&&Mathf.Abs(p.z-1.49f)<.085f,"Process gate clearance: "+part.name+" "+p);
                }
            }
        }
        Require(!(outerOpen&&innerOpen),"Both loadlock gates are open");
    }
    void Grab(Arm arm)
    {
        Require(Vector3.Distance(Centre,arm.contact.position)<.0015f,"Wafer pickup mismatch");wafer.SetParent(arm.contact,true);
    }
    void Put(Transform target)
    {
        Require(Vector3.Distance(Centre,target.position)<.0015f,"Wafer placement mismatch");wafer.SetParent(target,true);
    }
    IEnumerator Transfer(Arm arm,Vector3 source,Vector3 sourceReady,Vector3 sourceDirection,Transform destination,Vector3 destinationReady,Vector3 destinationDirection,Vector3 clear)
    {
        yield return Robot(arm,sourceReady-Vector3.up*.0035f,sourceDirection,.8f);
        yield return Robot(arm,source-Vector3.up*.0035f,sourceDirection,1.3f);
        yield return Robot(arm,source,sourceDirection,.35f);Grab(arm);
        yield return Robot(arm,source+Vector3.up*.003f,sourceDirection,.35f);
        yield return Robot(arm,sourceReady+Vector3.up*.003f,sourceDirection,1.3f);
        yield return Robot(arm,clear,sourceDirection,.9f);
        yield return Robot(arm,clear,destinationDirection,.7f);
        yield return Robot(arm,destinationReady+Vector3.up*.003f,destinationDirection,.8f);
        yield return Robot(arm,destination.position+Vector3.up*.003f,destinationDirection,1.2f);
        yield return Robot(arm,destination.position,destinationDirection,.35f);Put(destination);
        yield return Robot(arm,destination.position-Vector3.up*.0035f,destinationDirection,.35f);
        yield return Robot(arm,destinationReady-Vector3.up*.0035f,destinationDirection,1.2f);
        yield return Robot(arm,clear,destinationDirection,.8f);
    }
    IEnumerator Pressure(float target,float seconds)
    {
        Require(!outerOpen&&!innerOpen,"Pressure change with a gate open");float start=Mathf.Log10(pressurePa);
        for(float t=0;t<seconds;){t+=Delta;pressurePa=Mathf.Pow(10,Mathf.Lerp(start,Mathf.Log10(target),Mathf.Clamp01(t/seconds)));RefreshMonitor();yield return null;}
        pressurePa=target;
    }
    IEnumerator Gate(Transform door,bool open)
    {
        var start=door==outerDoor?outerStart:door==innerDoor?innerStart:processStart;
        if(open&&door==outerDoor)Require(!innerOpen&&pressurePa>100000,"Outer gate pressure interlock");
        if(open&&door==innerDoor)Require(!outerOpen&&pressurePa<=.011f,"Inner gate vacuum interlock");
        // Keep the logical gate closed until its blade has fully cleared the slot.
        yield return Move(door,start-(open?Vector3.up*.22f:Vector3.zero),.65f);
        if(door==outerDoor)outerOpen=open;else if(door==innerDoor)innerOpen=open;else processOpen=open;
    }
    public IEnumerator Cycle()
    {
        if(!TransportAvailable)yield break;
        if(LotBlocked){SetState("LOT HOLD / REVIEW REQUIRED");yield break;}
        var lotRecipe=DemoApprovedLotRecipes.BeginLot(incomingLotId);
        if(lotRecipe!=null){targetDose=(float)lotRecipe.body_dose;approvedEpiDoping=lotRecipe.epi_doping;approvedRecipeId=lotRecipe.approved_proposal_id;}
        JetsonTestDataProtocol.Selection selected=null;GatewayLotConditions.Condition condition=null;
        if(useJetsonCsv)
        {
            if(!JetsonTestDataView.TryIonInput(this,out selected)){running=false;SetState("CSV TEST DATA NOT READY / CONNECT JETSON");yield break;}
            try{condition=GatewayLotConditions.ForLot(incomingLotId);}
            catch(ArgumentException){running=false;SetState("TCAD LOT CONDITIONS NOT READY");}
            if(condition==null)yield break;
        }
        Initialize();ResetPreview();running=true;
        InspectionCsv=selected==null?null:JsonUtility.FromJson<JetsonTestDataProtocol.Selection>(JsonUtility.ToJson(selected));
        if(InspectionCsv!=null)SelectedCsv=JsonUtility.FromJson<JetsonTestDataProtocol.Selection>(JsonUtility.ToJson(InspectionCsv));
        InspectionCondition=condition;
        float completedDose=InspectionCsv==null?targetDose:(float)JetsonTestDataProtocol.Dose(condition.body_dose,InspectionCsv.row);
        InspectionId=Guid.NewGuid().ToString("N");InspectionUnitId=string.IsNullOrWhiteSpace(incomingWaferId)?"SIM-IMP01-WAFER13":incomingWaferId;
        if(Application.isPlaying&&GatewayInspectionBridge.Instance)GatewayInspectionBridge.Instance.Capture(this);
        SetState("DOCK FOUP");yield return Move(carrier,carrierStart+dy*.06f,1);
        SetState("OPEN LOAD PORT");yield return Move(portDoor,portStart+dy*.09f,.5f);yield return Move(carrierDoor,carrierDoorStart+dy*.315f,.5f);
        yield return Move(portDoor,portStart+dy*.09f-Vector3.up*.48f,.8f);yield return Move(carrierDoor,carrierDoorStart+dy*.315f-Vector3.up*.48f,.8f);portOpen=true;
        var source=Centre;var slot=new GameObject("Ion_Return_Slot").transform;slot.position=source;slot.SetParent(carrier,true);
        try
        {
            SetState("PICK / ALIGN WAFER");
            yield return Transfer(atmosphere,source,World(-1.05,-.26,source.y-origin.y),-dy,alignTarget,World(-1.12,.32,1.49),-dx,World(-.35,.55,1.49));
            var start=wafer.rotation;for(float t=0;t<1.4f;){t+=Delta;wafer.rotation=Quaternion.AngleAxis(Mathf.Min(t/1.4f,1)*360,Vector3.up)*start;yield return null;}wafer.rotation=start;
            SetState("ATM TRANSFER TO LOAD LOCK");yield return Gate(outerDoor,true);
            yield return Transfer(atmosphere,Centre,World(-1.12,.32,1.49),-dx,lockTarget,World(.5,.30,1.49),dy,World(-.35,.55,1.49));
            yield return Gate(outerDoor,false);SetState("PUMP DOWN / SIMULATION");yield return Pressure(.01f,3);
            SetState("VACUUM TRANSFER TO CHUCK");yield return Gate(innerDoor,true);yield return Gate(processDoor,true);
            yield return Transfer(vacuum,Centre,World(.5,1.80,1.49),-dy,stageTarget,World(.5,1.88,1.49),dy,World(.10,1.8,1.49));
            yield return Gate(innerDoor,false);yield return Gate(processDoor,false);
            SetState("CHUCK TILT / SIMULATION");
            var tiltEnd=tiltStart*Quaternion.AngleAxis(75,Vector3.right);
            for(float t=0;t<1.2f;){t+=Delta;tilt.localRotation=Quaternion.Slerp(tiltStart,tiltEnd,Mathf.Clamp01(t/1.2f));yield return null;}
            if(beam)beam.enabled=inside;
            SetState("IMPLANT / SIMULATION");
            for(float t=0;t<6;){t+=Delta;float f=Mathf.Clamp01(t/6);stage.position=stageStart+dx*(Mathf.Sin(f*Mathf.PI*6)*.07f);dose=completedDose*f;progress=f;RefreshMonitor();yield return null;}
            if(beam)beam.enabled=false;stage.position=stageStart;
            for(float t=0;t<1.2f;){t+=Delta;tilt.localRotation=Quaternion.Slerp(tiltEnd,tiltStart,Mathf.Clamp01(t/1.2f));yield return null;}
            tilt.localRotation=tiltStart;
            SetState("VACUUM RETURN TO LOAD LOCK");yield return Gate(processDoor,true);yield return Gate(innerDoor,true);
            yield return Transfer(vacuum,Centre,World(.5,1.88,1.49),dy,lockTarget,World(.5,1.80,1.49),-dy,World(.10,1.8,1.49));
            yield return Gate(processDoor,false);yield return Gate(innerDoor,false);
            SetState("VENT LOAD LOCK / SIMULATION");yield return Pressure(101325,2.5f);yield return Gate(outerDoor,true);
            SetState("RETURN TO FOUP SLOT 13");
            yield return Transfer(atmosphere,Centre,World(.5,.30,1.49),dy,slot,World(-1.05,-.26,source.y-origin.y),-dy,World(-.35,.55,1.49));
            wafer.SetParent(waferParent,true);Require(Vector3.Distance(Centre,source)<.0015f,"Wafer did not return to slot 13");
            yield return Gate(outerDoor,false);portOpen=false;SetState("CLOSE / UNDOCK");
            yield return Move(portDoor,portStart+dy*.09f,.8f);yield return Move(carrierDoor,carrierDoorStart+dy*.315f,.8f);
            yield return Move(carrierDoor,carrierDoorStart+dy*.06f,.5f);yield return Move(portDoor,portStart,.5f);
            yield return Move(carrier,carrierStart,1);
            Require(Vector3.Distance(Centre,waferStart)<.0015f,"Undock wafer return error");
            Require(!outerOpen&&!innerOpen&&!processOpen&&!portOpen,"Gate left open");
            completed=true;completedRuns++;running=false;SetState("COMPLETE / WAFER IN FOUP");
            if(Application.isPlaying&&GatewayInspectionBridge.Instance)GatewayInspectionBridge.Instance.Submit(this);
            if(Application.isPlaying&&ProcessAnalysisView.Instance)ProcessAnalysisView.Instance.OpenIonResult(this);
        }
        finally {if(Application.isPlaying)Destroy(slot.gameObject);else DestroyImmediate(slot.gameObject);}
    }
    public void StartCycle()
    {
        if(!TransportAvailable||running)return;
        if(Application.isPlaying&&!transportControlled&&OhtFabCycle.TryStartInspection(3))return;
        if(Application.isPlaying&&!OhtFabCycle.PrepareInspection(3))return;
        if(LotBlocked){SetState("LOT HOLD / REVIEW REQUIRED");return;}
        Initialize();steps.Clear();ResetPreview();steps.Push(Cycle());running=true;
    }
    void Update()
    {
        RefreshLotGate();
        if(!running||paused||validationDelta>0)return;
        try
        {
            while(steps.Count>0)
            {
                var step=steps.Peek();if(!step.MoveNext()){steps.Pop();continue;}
                if(step.Current is IEnumerator child){steps.Push(child);continue;}break;
            }
        }
        catch(Exception e){foreach(var step in steps)(step as IDisposable)?.Dispose();steps.Clear();running=false;failed=true;if(beam)beam.enabled=false;SetState("STOPPED / INTERLOCK");if(GatewayInspectionBridge.Instance)GatewayInspectionBridge.Instance.CancelIon(InspectionId);Debug.LogException(e);}
    }
    public void RefreshLotGate()
    {
        if(!running&&status=="LOT HOLD / REVIEW REQUIRED"&&!LotBlocked)SetState("READY");
    }
    public void ShowInside()
    {
        inside=!inside;foreach(var panel in cutawayPanels)panel.enabled=!inside;
        SelectCamera(inside?internalView:detail);
        if(beam)beam.enabled=inside&&status=="IMPLANT / SIMULATION";
    }
    public void SelectCamera(Camera camera)
    {foreach(var c in Camera.allCameras)if(!c.targetTexture)c.enabled=false;camera.enabled=true;}
    void OnGUI()
    {
        var old=GUI.matrix;float s=Mathf.Min(Screen.width/1280f,Screen.height/720f);GUI.matrix=Matrix4x4.Scale(new Vector3(s,s,1));
        float x=Screen.width/s-455;
        var panelMatrix=GUI.matrix;
        if(FactoryControlBar.BeginPanel(FactoryControlBar.Equipment.Implanter,new Rect(x,15,440,205)))
        {
        GUI.Box(new Rect(x,15,440,205),"");var label=new GUIStyle(GUI.skin.label){fontSize=15};
        GUI.Label(new Rect(x+12,25,415,25),"ION IMPLANTER | SIMULATION",label);GUI.Label(new Rect(x+12,54,415,25),status,label);
        GUI.Label(new Rect(x+12,82,415,23),"Dose "+dose.ToString("0.00E+00")+" cm-2  |  "+(progress*100).ToString("F0")+"%",label);
        bool prior=GUI.enabled;GUI.enabled=running||((!LotBlocked||OhtFabCycle.NextLotAvailable)&&TransportAvailable);
        if(GUI.Button(new Rect(x+12,115,128,28),running?(paused?"Resume":"Pause"):OhtFabCycle.NextLotAvailable?"Next LOT":LotBlocked?"LOT HOLD":"Start implant")){if(running)TogglePause();else StartCycle();}
        GUI.enabled=prior;
        if(GUI.Button(new Rect(x+150,115,128,28),inside?"Exterior":"View inside"))ShowInside();
        if(GUI.Button(new Rect(x+288,115,138,28),"Implanter view"))SelectCamera(detail.enabled||internalView.enabled?overview:inside?internalView:detail);
        if(dashboard&&GUI.Button(new Rect(x+12,149,414,28),"Monitor window"))dashboard.ToggleWindow();
        GUI.Label(new Rect(x+12,184,415,20),"Manual start | Sample recipe | TCAD offline");}
        GUI.matrix=panelMatrix;GUI.matrix=old;
    }
}




