using System;
using System.Collections;
using System.Linq;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Rendering.HighDefinition;

public class EllipsometerCycle : MonoBehaviour
{
    public Transform robot,joint1,joint2,wrist,contact,wafer,stage,stageTarget,equipmentDoor,carrierDoor;
    public Renderer[] cutawayPanels,armParts;
    public Camera overview,detail;
    public Text monitor;
    public LineRenderer[] beams;
    public string status="READY",result="검사 결과 대기";
    public bool completed,failed,demoHold;
    [NonSerialized] public bool transportControlled,transportDocked;
    public bool TransportAvailable=>!transportControlled||transportDocked;
    public void SetTransportPaused(bool value){paused=value;}
    public FilmInspectionRecipe recipe;
    public FilmInspectionDashboard dashboard;
    public string lotId="LOT-001";
    public string waferId="";
    [NonSerialized] public bool inspectionIsRemeasurement;
    public string InspectionId {get;private set;}
    public bool demoLow;
    public enum ElectricalDemo {ThicknessOnly,Normal,OxidePlus15}
    public ElectricalDemo electricalDemo;
    public JetsonTestDataProtocol.Selection SelectedCsv {get;private set;}
    public JetsonTestDataProtocol.Selection InspectionCsv {get;private set;}
    public bool SetCsvTest(JetsonTestDataProtocol.Selection selection)
    {
        if(running)return false;
        if(selection!=null&&(!JetsonTestDataProtocol.CanSelect(selection.row,selection.measurement_source)||selection.n_wafers<1||selection.n_wafers>10000))return false;
        SelectedCsv=selection==null?null:JsonUtility.FromJson<JetsonTestDataProtocol.Selection>(JsonUtility.ToJson(selection));
        if(dashboard)dashboard.Refresh();return true;
    }
    FilmInspectionHistory.Entry lastCompletedInspection;
    bool HasCurrentMeasurement=>(verdict=="PASS"||verdict=="FAIL")&&readings!=null&&readings.Length==3&&Array.TrueForAll(readings,FilmInspectionRecipe.Finite);
    public string DisplayResultText
    {
        get
        {
            if(HasCurrentMeasurement)
                return Mean.ToString("F1")+" nm | "+verdict+" · "+(InspectionCsv?.row==null?"시연값":"CSV "+InspectionCsv.row.id+" 환산값")+
                    "\n현재 검사 · "+lotId+" / "+ShortInspection(InspectionId);
            string progress=running?"측정 중 · "+Mathf.Clamp(activePoint+1,0,3)+" / 3":"검사 결과 대기";
            if(lastCompletedInspection==null)return progress;
            var old=lastCompletedInspection;
            return "이전 검사 · "+old.Mean.ToString("F1")+" nm | "+old.verdict+
                "\n"+old.lot_id+" / "+ShortInspection(old.inspection_id)+" · "+(string.IsNullOrEmpty(old.test_sample_id)?"시연값":"CSV "+old.test_sample_id+" 환산값")+(running?" / 새 검사 측정 중":"");
        }
    }
    static string ShortInspection(string id)=>string.IsNullOrEmpty(id)?"ID 대기":"INSP-"+id.Substring(0,Math.Min(8,id.Length));
    void RememberMeasurement()
    {
        if(!HasCurrentMeasurement)return;
        lastCompletedInspection=new FilmInspectionHistory.Entry{inspection_id=InspectionId,lot_id=lotId,wafer_id=waferId,equipment_id="ELLIP-01",
            readings=(float[])readings.Clone(),verdict=verdict,test_sample_id=InspectionCsv?.row?.id,completed_at=DateTimeOffset.Now.ToString("O")};
    }
    public string DemoLabel=>SelectedCsv!=null?SelectedCsv.Label:electricalDemo==ElectricalDemo.Normal?"DEMO: 정상 + 전기 OK":electricalDemo==ElectricalDemo.OxidePlus15?"DEMO: 산화막 +15%":demoLow?"DEMO: 두께 LOW":demoHold?"DEMO: 두께 +9%":"DEMO: 두께 PASS";
    float approvedInspectionTargetNm;
    public float[] DemoReadings()
    {
        if(InspectionCsv!=null){float thickness=JetsonTestDataProtocol.Thickness(InspectionCsv.reference_target_nm>0?InspectionCsv.reference_target_nm:recipe.targetNm,InspectionCsv.row);return new[]{thickness,thickness,thickness};}
        var values=electricalDemo==ElectricalDemo.Normal?new[]{recipe.targetNm*.996f,recipe.targetNm*1.001f,recipe.targetNm*1.003f}:electricalDemo==ElectricalDemo.OxidePlus15?new[]{recipe.targetNm*1.146f,recipe.targetNm*1.151f,recipe.targetNm*1.153f}:demoLow?recipe.lowDemo:demoHold?recipe.highDemo:recipe.passDemo;
        float factor=approvedInspectionTargetNm>0?approvedInspectionTargetNm/recipe.targetNm:1;
        return Array.ConvertAll(values,value=>value*factor);
    }
    public void NextDemoScenario()
    {
        if(running)return;
        SelectedCsv=null;
        if(electricalDemo==ElectricalDemo.Normal)electricalDemo=ElectricalDemo.OxidePlus15;
        else if(electricalDemo==ElectricalDemo.OxidePlus15){electricalDemo=ElectricalDemo.ThicknessOnly;demoHold=true;demoLow=false;}
        else if(demoLow){demoHold=demoLow=false;electricalDemo=ElectricalDemo.Normal;}
        else if(demoHold)demoLow=true;
        else electricalDemo=ElectricalDemo.Normal;
    }
    [NonSerialized] public string verdict="PENDING",lotStatus="READY",inspectionReason="검사 대기",notice="";
    [NonSerialized] public float[] readings={float.NaN,float.NaN,float.NaN};
    [NonSerialized] public int activePoint=-1;
    [NonSerialized] public bool lotHeld;
    public bool Running=>running;
    public bool SafeToUnload=>completed&&!running&&!failed&&!doorOpen&&!attached;
    public bool CanProceed=>completed&&!running&&!failed&&!lotHeld&&verdict=="PASS"&&(!LotProcessAnalysis.Instance||!LotProcessAnalysis.Instance.BlocksRelease(lotId));
    public float Mean {get{float sum=0;foreach(float v in readings){if(!FilmInspectionRecipe.Finite(v))return float.NaN;sum+=v;}return sum/3;}}
    [NonSerialized] public float validationDelta;
    Transform originalParent;
    Vector3 originalLocalPosition,originalLocalScale,originalCentre,stageStart,doorStart,carrierDoorStart;
    Quaternion originalLocalRotation;
    Vector3 axisX,axisY,axisUp,origin,feed,inward,home,commanded;
    float l1,l2,tip,heading,feedHeading,stageHeading;
    bool initialized,running,paused,inside,doorOpen,attached;
    Camera monitorCamera;
    RenderTexture monitorTexture;
    bool monitorWindowOpen;
    Rect monitorWindow;
    Vector3 Centre=>wafer.TransformPoint(wafer.GetComponent<MeshFilter>().sharedMesh.bounds.center);
    float Delta=>validationDelta>0?validationDelta:paused?0:Time.deltaTime;
    static void Check(bool ok,string message){if(!ok)throw new InvalidOperationException(message);}
    void Awake(){Initialize();}
    public static bool InteriorTrim(Renderer part)=>part&&(part.name=="Indigo_Header"||part.name.StartsWith("Indigo_Header.")||part.name=="Equipment_Name"||part.name=="Equipment_Name_Export"||part.name=="Equipment_Subtitle"||part.name=="Equipment_Subtitle_Export");
    public void ConfigureInteriorPanels()
    {
        cutawayPanels=(cutawayPanels??Array.Empty<Renderer>()).Where(r=>r&&!r.name.StartsWith("Right_Service")).Concat(GetComponentsInChildren<Renderer>(true).Where(InteriorTrim)).Distinct().ToArray();
    }
    public void ShowInside()
    {
        ConfigureInteriorPanels();inside=!inside;
        foreach(var part in cutawayPanels)part.enabled=!inside;
        foreach(var part in GetComponentsInChildren<Renderer>(true).Where(r=>r.name.StartsWith("Right_Service")))part.enabled=true;
    }
    public void Initialize()
    {
        ConfigureInteriorPanels();
        if(initialized)return;
        joint1.localRotation=joint2.localRotation=wrist.localRotation=Quaternion.identity;
        axisX=(joint2.position-joint1.position).normalized;
        axisUp=joint1.parent.TransformDirection(Vector3.forward).normalized;
        Check(Vector3.Dot(axisUp,Vector3.up)>.99f,"Robot axis is not upright.");
        axisY=Vector3.Cross(axisUp,axisX).normalized;origin=robot.position;
        l1=Vector3.Distance(joint1.position,joint2.position);
        var link=wrist.position-joint2.position;link-=axisUp*Vector3.Dot(link,axisUp);l2=link.magnitude;
        tip=Vector3.Dot(contact.position-wrist.position,axisX);
        Check(Mathf.Abs(l1-.5f)<.001f&&Mathf.Abs(l2-.46f)<.001f&&Mathf.Abs(tip-.31f)<.001f,"Unexpected ellipsometer robot scale.");
        originalParent=wafer.parent;originalLocalPosition=wafer.localPosition;
        originalLocalRotation=wafer.localRotation;originalLocalScale=wafer.localScale;originalCentre=Centre;
        stageStart=stage.position;doorStart=equipmentDoor.position;carrierDoorStart=carrierDoor.position;
        feed=originalCentre-equipmentDoor.position;feed.y=0;feed.Normalize();inward=-feed;
        feedHeading=Angle(feed);stageHeading=Angle(inward);
        // Keep the wrist sweep inside the cabinet after the wafer clears the port.
        home=originalCentre+inward*.765f;home.y=originalCentre.y+.025f;
        initialized=true;lastCompletedInspection=FilmInspectionHistory.Instance.LatestForEquipment("ELLIP-01");ResetPreview();
    }
    float Angle(Vector3 direction)=>Mathf.Atan2(Vector3.Dot(direction,axisY),Vector3.Dot(direction,axisX));
    public void Solve(Vector3 target,float angle)
    {
        var relative=target-origin;
        float x=Vector3.Dot(relative,axisX)-tip*Mathf.Cos(angle),y=Vector3.Dot(relative,axisY)-tip*Mathf.Sin(angle);
        float radius=Mathf.Sqrt(x*x+y*y);
        Check(radius>Mathf.Abs(l1-l2)+.001f&&radius<l1+l2-.001f,"Robot target outside reach: "+target+" radius="+radius);
        float a2=Mathf.Acos(Mathf.Clamp((radius*radius-l1*l1-l2*l2)/(2*l1*l2),-1,1));
        float a1=Mathf.Atan2(y,x)-Mathf.Atan2(l2*Mathf.Sin(a2),l1+l2*Mathf.Cos(a2));
        joint1.localRotation=Quaternion.AngleAxis(a1*Mathf.Rad2Deg,Vector3.forward);
        joint2.localRotation=Quaternion.AngleAxis(a2*Mathf.Rad2Deg,Vector3.forward);
        wrist.localRotation=Quaternion.AngleAxis((angle-a1-a2)*Mathf.Rad2Deg,Vector3.forward);
        joint1.position+=axisUp*Vector3.Dot(target-contact.position,axisUp);
        Check(Vector3.Distance(contact.position,target)<.001f,"Blade endpoint mismatch.");
        foreach(var part in armParts)CheckEnvelope(part.transform,part.GetComponent<MeshFilter>().sharedMesh.bounds,part.name);
        if(attached)CheckEnvelope(wafer,wafer.GetComponent<MeshFilter>().sharedMesh.bounds,"Carried wafer");
    }
    Vector3 DesignPoint(Vector3 world)=>transform.InverseTransformPoint(world)*transform.lossyScale.x;
    void CheckEnvelope(Transform part,Bounds mesh,string name)
    {
        var b=new Bounds(DesignPoint(part.TransformPoint(mesh.center)),Vector3.zero);
        var points=new Vector3[8];
        for(int i=0;i<8;i++){points[i]=DesignPoint(part.TransformPoint(mesh.center+Vector3.Scale(mesh.extents,new Vector3((i&1)==0?-1:1,(i&2)==0?-1:1,(i&4)==0?-1:1))));b.Encapsulate(points[i]);}
        Check(b.min.x> -1.13f&&b.max.x<1.13f&&b.max.y<1.49f,"Side/rear panel clearance: "+name);
        if(b.min.y<-.44f)
        {
            // Check only the portion that crosses the front wall, not the whole diagonal arm.
            var clipped=new Bounds();bool seeded=false;
            void Add(Vector3 p){if(!seeded){clipped=new Bounds(p,Vector3.zero);seeded=true;}else clipped.Encapsulate(p);}
            foreach(var p in points)if(p.y<=-.44f)Add(p);
            for(int i=0;i<8;i++)foreach(int bit in new[]{1,2,4})
            {
                int j=i^bit;if(j<i)continue;var a=points[i];var p=points[j];
                if((a.y<-.44f)!=(p.y<-.44f))Add(Vector3.Lerp(a,p,(-.44f-a.y)/(p.y-a.y)));
            }
            Check(seeded&&doorOpen&&clipped.min.x>DesignPoint(doorStart).x-.39f&&clipped.max.x<DesignPoint(doorStart).x+.39f&&clipped.min.z>1.14f&&clipped.max.z<1.64f,"Loading opening clearance: "+name+" "+clipped+" door="+doorOpen);
        }
    }
    void State(string value)
    {
        status=value;Debug.Log("ELLIP_CYCLE "+value);
        if(dashboard)dashboard.Refresh();
        else if(monitor)monitor.text="FILM METROLOGY / CSV·시연\n"+value+"\n"+DisplayResultText;
    }
    IEnumerator Move(Transform obj,Vector3 target,float seconds)
    {
        var from=obj.position;
        for(float t=0;t<seconds;){t+=Delta;obj.position=Vector3.Lerp(from,target,Mathf.SmoothStep(0,1,Mathf.Clamp01(t/seconds)));yield return null;}
        obj.position=target;
    }
    IEnumerator RobotTo(Vector3 target,float angle,float seconds)
    {
        var from=commanded;float previous=heading;
        float difference=Mathf.DeltaAngle(previous*Mathf.Rad2Deg,angle*Mathf.Rad2Deg)*Mathf.Deg2Rad;
        for(float t=0;t<seconds;){t+=Delta;float f=Mathf.SmoothStep(0,1,Mathf.Clamp01(t/seconds));Solve(Vector3.Lerp(from,target,f),previous+difference*f);yield return null;}
        Solve(target,angle);commanded=target;heading=angle;
    }
    IEnumerator Wait(float seconds){for(float t=0;t<seconds;){t+=Delta;yield return null;}}
    void Grab()
    {
        Check(Vector3.Distance(Centre,contact.position)<.0015f,"Wafer and blade are not aligned.");
        wafer.SetParent(contact,true);
        // The imported wafer's origin is outside its mesh; anchor its centre to the blade.
        wafer.position+=contact.position-Centre;
        Check(wafer.parent==contact&&Vector3.Distance(Centre,contact.position)<.00005f,"Wafer parenting failed.");attached=true;
    }
    void Release(Transform parent)
    {
        var centre=Centre;wafer.SetParent(parent,true);wafer.position+=centre-Centre;
        Check(wafer.parent==parent,"Wafer release failed.");attached=false;
    }
    Vector3 Ready(float height){var p=originalCentre+inward*.765f;p.y=height;return p;}
    Vector3 StageApproach(float height){var p=stageTarget.position+feed*.39f;p.y=height;return p;}
    Vector3 Clear(float height){var p=origin+axisX*.28f+inward*.18f;p.y=height;return p;}
    void Beam(bool on){foreach(var beam in beams)beam.enabled=on;}
    public IEnumerator Cycle()
    {
        if(!TransportAvailable||running)yield break;
        var lotRecipe=DemoApprovedLotRecipes.BeginLot(lotId);
        Initialize();Check(recipe,"Film inspection recipe missing.");recipe.Validate();
        if(!JetsonTestDataView.PrepareIncoming(this)){notice="CSV 자동 선택 준비 실패 · Jetson CSV 시험값 창 확인";State("CSV TEST DATA NOT READY");yield break;}
        ResetPreview();
        approvedInspectionTargetNm=lotRecipe!=null&&!string.IsNullOrEmpty(lotRecipe.approved_proposal_id)?(float)(lotRecipe.oxide_reference_um*1000):0;
        if(InspectionCsv!=null&&lotRecipe!=null)InspectionCsv.reference_target_nm=(float)(lotRecipe.oxide_reference_um*1000);
        running=true;completed=failed=false;paused=false;
        if(Application.isPlaying&&GatewayInspectionBridge.Instance)GatewayInspectionBridge.Instance.Capture(this);
        lotStatus=lotHeld?"HOLD / REMEASURING":"MEASURING";
        State("OPEN EQUIPMENT DOOR");
        yield return Move(equipmentDoor,doorStart+inward*.085f,.4f);
        yield return Move(equipmentDoor,doorStart+inward*.085f-Vector3.up*.60f,1);doorOpen=true;
        State("OPEN FOUP DOOR");
        yield return Move(carrierDoor,carrierDoorStart+inward*.286f,.5f);
        yield return Move(carrierDoor,carrierDoorStart+inward*.286f-Vector3.up*.60f,1);
        State("PICK WAFER");
        yield return RobotTo(Ready(originalCentre.y-.0035f),feedHeading,.8f);
        yield return RobotTo(originalCentre-Vector3.up*.0035f,feedHeading,1.5f);
        yield return RobotTo(originalCentre,feedHeading,.4f);Grab();
        yield return RobotTo(originalCentre+Vector3.up*.003f,feedHeading,.4f);
        yield return RobotTo(Ready(originalCentre.y+.003f),feedHeading,1.5f);
        State("TRANSFER TO STAGE");
        yield return RobotTo(Clear(1.40f),stageHeading,1.5f);
        yield return RobotTo(StageApproach(stageTarget.position.y+.003f),stageHeading,.9f);
        yield return RobotTo(stageTarget.position+Vector3.up*.003f,stageHeading,1.1f);
        yield return RobotTo(stageTarget.position,stageHeading,.4f);Release(stageTarget);
        Check(Vector3.Distance(Centre,stageTarget.position)<.0015f,"Wafer not centred on chuck.");
        State("WAFER ON STAGE");
        yield return RobotTo(stageTarget.position-Vector3.up*.0035f,stageHeading,.4f);
        yield return RobotTo(StageApproach(stageTarget.position.y-.0035f),stageHeading,1);
        yield return RobotTo(Clear(1.40f),stageHeading,.9f);
        Beam(true);
        for(int i=0;i<3;i++)
        {
            yield return Move(stage,stageStart+axisX*((i-1)*.025f),.6f);
            activePoint=i;State("MEASURING "+(i+1)+" / 3 (DEMO)");yield return Wait(.8f);
            var sample=DemoReadings();
            Check(sample!=null&&sample.Length==3,"Demo sample must contain three readings.");readings[i]=sample[i];if(dashboard)dashboard.Refresh();
        }
        yield return Move(stage,stageStart,.6f);Beam(false);
        EvaluateInspection();
        State("RESULT / DEMO DATA");yield return Wait(2);
        State("RETURN WAFER");
        yield return RobotTo(StageApproach(stageTarget.position.y-.0035f),stageHeading,1);
        yield return RobotTo(stageTarget.position-Vector3.up*.0035f,stageHeading,1.1f);
        yield return RobotTo(stageTarget.position,stageHeading,.4f);Grab();
        yield return RobotTo(stageTarget.position+Vector3.up*.003f,stageHeading,.4f);
        yield return RobotTo(StageApproach(stageTarget.position.y+.003f),stageHeading,1.1f);
        yield return RobotTo(Clear(1.40f),stageHeading,.9f);
        yield return RobotTo(Ready(originalCentre.y+.003f),feedHeading,1.5f);
        yield return RobotTo(originalCentre+Vector3.up*.003f,feedHeading,1.5f);
        yield return RobotTo(originalCentre,feedHeading,.4f);Release(originalParent);
        Check(Vector3.Distance(Centre,originalCentre)<.0015f,"Wafer did not return to its original FOUP slot.");
        yield return RobotTo(originalCentre-Vector3.up*.0035f,feedHeading,.4f);
        yield return RobotTo(Ready(originalCentre.y-.0035f),feedHeading,1.5f);
        yield return RobotTo(home,feedHeading,.6f);
        State("CLOSE DOORS");
        yield return Move(carrierDoor,carrierDoorStart+inward*.286f,1);
        yield return Move(carrierDoor,carrierDoorStart,.5f);
        yield return Move(equipmentDoor,doorStart+inward*.085f,1);
        yield return Move(equipmentDoor,doorStart,.4f);doorOpen=false;
        completed=true;running=false;lotStatus=lotHeld?"HOLD":"READY FOR DISPATCH";State("COMPLETE / WAFER IN FOUP");
    }
    public void ResetPreview()
    {
        Check(initialized,"Initialize first.");
        InspectionId=Guid.NewGuid().ToString("N");
        InspectionCsv=SelectedCsv==null?null:JsonUtility.FromJson<JetsonTestDataProtocol.Selection>(JsonUtility.ToJson(SelectedCsv));
        inspectionIsRemeasurement=lotHeld;
        if(Application.isPlaying&&LotProcessAnalysis.Instance)LotProcessAnalysis.Instance.Begin(this);
        wafer.SetParent(originalParent,false);wafer.localPosition=originalLocalPosition;
        wafer.localRotation=originalLocalRotation;wafer.localScale=originalLocalScale;
        stage.position=stageStart;equipmentDoor.position=doorStart;carrierDoor.position=carrierDoorStart;
        attached=doorOpen=running=paused=failed=completed=false;result="검사 결과 대기";Beam(false);
        verdict="PENDING";readings=new[]{float.NaN,float.NaN,float.NaN};activePoint=-1;inspectionReason="검사 대기";notice="";lotStatus=lotHeld?"HOLD":"READY";
        commanded=home;heading=feedHeading;Solve(home,feedHeading);State("READY");
    }
    public void EvaluateInspection()
    {
        verdict=recipe.Evaluate(readings,out inspectionReason);activePoint=-1;
        if(verdict=="FAIL")lotHeld=true;
        lotStatus=lotHeld?"HOLD":"RETURNING TO FOUP";
        result=Mean.ToString("F1")+" nm | "+verdict+(lotHeld?" / HOLD":"")+" ("+(InspectionCsv?.Label??"DEMO")+")";
        RememberMeasurement();
        if(Application.isPlaying&&LotProcessAnalysis.Instance)LotProcessAnalysis.Instance.Inspected(this);
        if(Application.isPlaying&&GatewayInspectionBridge.Instance)GatewayInspectionBridge.Instance.Submit(this);
        if(Application.isPlaying)FilmInspectionHistory.Instance.Record(this,inspectionIsRemeasurement);
        if(dashboard)dashboard.Refresh();
    }
    public bool ApproveRelease()
    {
        if(LotProcessAnalysis.Instance&&LotProcessAnalysis.Instance.BlocksRelease(lotId))
        {notice="해제 불가: 전기특성 NG 또는 전체 판정 대기";if(dashboard)dashboard.Refresh();return false;}
        if(!lotHeld||!completed||running||failed||verdict!="PASS")
        {notice="해제 불가: 재측정 PASS 및 동작 완료 후 검토 승인 필요";if(dashboard)dashboard.Refresh();return false;}
        lotHeld=false;lotStatus="READY FOR DISPATCH";result=Mean.ToString("F1")+" nm | PASS (DEMO)";
        notice="재측정 PASS 확인 · 검토 승인 완료";if(dashboard)dashboard.Refresh();return true;
    }
    public bool TryProceed()
    {
        if(!CanProceed){notice="다음 공정 이동 차단 · 재측정·검토 필요";if(dashboard)dashboard.Refresh();return false;}
        lotStatus="DISPATCH READY";notice="다음 공정 진행 가능 · 물류 명령 대기";if(dashboard)dashboard.Refresh();return true;
    }
#if UNITY_EDITOR
    public void ResetDashboardDemo(){SelectedCsv=null;lotHeld=false;demoHold=demoLow=false;electricalDemo=ElectricalDemo.ThicknessOnly;ResetPreview();}
#endif
    IEnumerator Guard(IEnumerator task)
    {
        while(true)
        {
            object item;
            try{if(!task.MoveNext())yield break;item=task.Current;}
            catch(Exception e){running=false;failed=true;lotHeld=true;lotStatus="HOLD";inspectionReason="장비 동작 오류 · 검토 필요";Beam(false);State("ERROR: "+e.Message);Debug.LogException(e);yield break;}
            if(item is IEnumerator nested){yield return Guard(nested);if(failed)yield break;}else yield return item;
        }
    }
    public void ShowDetail()
    {
        bool back=detail.enabled;foreach(var camera in Camera.allCameras)if(!camera.targetTexture)camera.enabled=false;(back?overview:detail).enabled=true;
    }
    public void StartScan()
    {
        if(!TransportAvailable||running)return;
        if(Application.isPlaying&&!transportControlled&&OhtFabCycle.TryStartInspection(2))return;
        if(Application.isPlaying&&!OhtFabCycle.PrepareInspection(2))return;
        StartCoroutine(Guard(Cycle()));
    }
    public void ZoomMonitor()
    {
        monitorWindowOpen=!monitorWindowOpen;
        if(dashboard){if(monitorCamera)monitorCamera.enabled=false;dashboard.SetSignalMonitorOpen(monitorWindowOpen);return;}
        if(!monitorWindowOpen){if(monitorCamera)monitorCamera.enabled=false;return;}
        if(!monitorCamera)
        {
            monitorTexture=new RenderTexture(1600,1134,24){name="Ellipsometer_Monitor_Window"};monitorTexture.Create();
            monitorCamera=new GameObject("ELLIPSOMETER_MONITOR_WINDOW_CAMERA").AddComponent<Camera>();
            monitorCamera.CopyFrom(detail);monitorCamera.enabled=false;monitorCamera.targetTexture=monitorTexture;
            monitorCamera.allowDynamicResolution=false;
            var hd=monitorCamera.gameObject.AddComponent<HDAdditionalCameraData>();
            hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;hd.allowDynamicResolution=false;
        }
        float scale=Mathf.Min(Screen.width/1280f,Screen.height/720f);
        monitorWindow=new Rect(Mathf.Max(0,(Screen.width/scale-960)/2),15,960,690);
        UpdateMonitorCamera();monitorCamera.enabled=true;
    }
    void LateUpdate(){if(monitorWindowOpen)UpdateMonitorCamera();}
    void UpdateMonitorCamera()
    {
        if(!monitorCamera)return;
        var screen=monitor.rectTransform;
        monitorCamera.transform.position=screen.position-screen.forward*.8f;
        monitorCamera.transform.LookAt(screen.position,screen.up);monitorCamera.orthographic=true;monitorCamera.orthographicSize=.19f;
    }
    void DrawMonitorWindow(int id)
    {
        if(GUI.Button(new Rect(monitorWindow.width-36,3,30,24),"X"))
        {monitorWindowOpen=false;monitorCamera.enabled=false;}
        var controls=new GUIStyle(GUI.skin.button){font=dashboard?dashboard.DisplayFont:null,fontSize=16};
        if(dashboard)
        {
            if(GUI.Button(new Rect(10,31,120,29),"검사 현황",controls))dashboard.SetView(0);
            if(GUI.Button(new Rect(138,31,120,29),"검사 이력",controls))dashboard.SetView(1);
            if(GUI.Button(new Rect(266,31,120,29),"검사 기준",controls))dashboard.SetView(2);
        }
        var area=new Rect(8,66,monitorWindow.width-16,monitorWindow.height-74);float ratio=monitorTexture.width/(float)monitorTexture.height;
        if(area.width/area.height>ratio){float width=area.height*ratio;area.x+=(area.width-width)/2;area.width=width;}else{float height=area.width/ratio;area.y+=(area.height-height)/2;area.height=height;}
        GUI.DrawTexture(area,monitorTexture,ScaleMode.StretchToFill,false);
        var ev=Event.current;
        if(dashboard&&ev.type==EventType.MouseDown&&ev.button==0&&area.Contains(ev.mousePosition))
        {
            var pixel=new Vector2((ev.mousePosition.x-area.x)/area.width*monitorTexture.width,(1-(ev.mousePosition.y-area.y)/area.height)*monitorTexture.height);
            if(dashboard.HandlePointer(pixel,monitorCamera))ev.Use();
        }
        GUI.DragWindow(new Rect(0,0,monitorWindow.width-42,28));
    }
    void OnDisable()
    {
        monitorWindowOpen=false;
        if(dashboard)dashboard.SetSignalMonitorOpen(false);
        if(monitorCamera){monitorCamera.enabled=false;monitorCamera.targetTexture=null;Destroy(monitorCamera.gameObject);}
        if(monitorTexture){monitorTexture.Release();Destroy(monitorTexture);}
    }
    void OnGUI()
    {
        var previous=GUI.matrix;
        GUI.matrix=Matrix4x4.Scale(Vector3.one*Mathf.Min(Screen.width/1280f,Screen.height/720f));GUI.skin.label.fontSize=17;
        var panelMatrix=GUI.matrix;
        if(FactoryControlBar.BeginPanel(FactoryControlBar.Equipment.Ellipsometer,new Rect(15,185,505,253)))
        {
        GUI.Box(new Rect(15,185,505,253),"");GUI.Label(new Rect(28,194,480,25),"ELLIPSOMETER | CSV·시연 두께 검사");
        GUI.Label(new Rect(28,224,480,25),status);GUI.Label(new Rect(28,247,480,36),DisplayResultText,new GUIStyle(GUI.skin.label){fontSize=14,wordWrap=true});
        bool transportEnabled=GUI.enabled;GUI.enabled=transportEnabled&&(running||TransportAvailable);
        if(!running&&GUI.Button(new Rect(28,286,145,34),lotHeld?"Remeasure":"Start scan"))StartScan();
        if(running&&GUI.Button(new Rect(28,286,145,34),paused?"Resume":"Pause"))paused=!paused;
        GUI.enabled=transportEnabled;
        if(GUI.Button(new Rect(183,286,145,34),"View inside"))ShowInside();
        if(GUI.Button(new Rect(338,286,165,34),"Ellipsometer view"))ShowDetail();
        if(!running&&GUI.Button(new Rect(28,336,190,30),DemoLabel))NextDemoScenario();
        if(GUI.Button(new Rect(235,336,268,30),monitorWindowOpen?"Close monitor window":"Monitor window"))ZoomMonitor();
        bool enabled=GUI.enabled;
        GUI.enabled=lotHeld&&completed&&!running&&verdict=="PASS"&&!failed;
        if(GUI.Button(new Rect(28,378,210,30),"Review / release HOLD"))ApproveRelease();
        GUI.enabled=CanProceed;
        if(GUI.Button(new Rect(248,378,255,30),lotHeld?"Next process: BLOCKED":"Next process: ready"))TryProceed();
        GUI.enabled=enabled;
        GUI.Label(new Rect(28,410,480,23),"LOT: "+lotStatus+" | "+verdict);
        }
        GUI.matrix=panelMatrix;
        if(dashboard)dashboard.SetSignalMonitorOpen(monitorWindowOpen);
        if(monitorWindowOpen&&!dashboard)
        {
            float scale=Mathf.Min(Screen.width/1280f,Screen.height/720f);
            monitorWindow.x=Mathf.Clamp(monitorWindow.x,0,Screen.width/scale-monitorWindow.width);
            monitorWindow.y=Mathf.Clamp(monitorWindow.y,0,Screen.height/scale-monitorWindow.height);
            monitorWindow=GUI.Window(714830,monitorWindow,DrawMonitorWindow,"MONITOR | DEMO / TCAD OFFLINE");
        }
        GUI.matrix=previous;
    }
}




