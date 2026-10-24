using System;
using System.Collections;
using System.Linq;
using UnityEngine;

public class IntegratedOxidationCycle : MonoBehaviour
{
    public Transform robot,joint1,joint2,wrist,contact,wafer,boat,boatTarget,boatUp,carrierDoor;
    public Transform[] equipmentDoors;
    public Renderer[] cutawayPanels,armRenderers;
    public Transform wristLimit;
    public Camera overview,detail;
    public string status="READY";
    public string lotId="LOT-001";
    public float targetOxideNm=60;
    [NonSerialized] public double approvedEpiDoping;
    [NonSerialized] public string approvedRecipeId;
    public bool completed,failed;
    [NonSerialized] public bool transportControlled,transportDocked;
    public bool Running=>running;
    public bool TransportAvailable=>!transportControlled||transportDocked;
    public void SetTransportPaused(bool value){paused=value;}
    [NonSerialized] public float validationDelta;
    Vector3 axisX,axisY,axisZ,origin,waferStart,waferLocalStart,boatStart,carrierDoorStart,home,source;
    Vector3[] doorStart;
    Quaternion waferRotation;
    Transform waferParent;
    float l1,l2,tip,contactHeight,heading,sourceHeading,boatHeading;
    Vector3 feedDirection,boatDirection;
    Vector3 commanded;
    bool initialized,running,paused,inside;
    void Awake(){Initialize();}
    public void ConfigureInteriorPanels()
    {
        cutawayPanels=(cutawayPanels??Array.Empty<Renderer>()).Where(r=>r&&r.name!="Demo_Enclosure_Back").Concat(GetComponentsInChildren<Renderer>(true).Where(r=>r.name=="REF_SystemMark")).Distinct().ToArray();
    }
    public void ShowInside()
    {
        ConfigureInteriorPanels();inside=!inside;
        foreach(var r in cutawayPanels)r.enabled=!inside;
        foreach(var r in GetComponentsInChildren<Renderer>(true).Where(r=>r.name=="Demo_Enclosure_Back"))r.enabled=true;
    }
    public void Initialize()
    {
        ConfigureInteriorPanels();
        if(initialized)return;
        origin=robot.position;
        joint1.localRotation=joint2.localRotation=wrist.localRotation=Quaternion.identity;
        axisX=(joint2.position-joint1.position).normalized;
        axisZ=joint1.parent.TransformDirection(Vector3.forward).normalized;
        Require(Vector3.Dot(axisZ,Vector3.up)>.99f,"Imported robot axis is not upright.");
        axisY=Vector3.Cross(axisZ,axisX).normalized;
        l1=Vector3.Dot(joint2.position-joint1.position,axisX);
        l2=Vector3.Dot(wrist.position-joint2.position,axisX);
        tip=Vector3.Dot(contact.position-wrist.position,axisX);
        contactHeight=Vector3.Dot(contact.position-joint1.position,axisZ);
        Require(l1>.9f&&l1<1&&l2>.8f&&l2<.9f&&tip>.8f&&tip<.85f,"Unexpected robot scale.");
        waferParent=wafer.parent;waferLocalStart=wafer.localPosition;waferStart=wafer.position;waferRotation=wafer.rotation;
        // The wafer mesh origin lies at the FOUP origin; use its actual surface centre.
        source=WaferCentre;
        boatStart=boat.position;carrierDoorStart=carrierDoor.position;
        doorStart=new Vector3[equipmentDoors.Length];for(int i=0;i<doorStart.Length;i++)doorStart[i]=equipmentDoors[i].position;
        feedDirection=source-equipmentDoors[1].position;feedDirection.y=0;feedDirection.Normalize();
        boatDirection=boatTarget.position-wristLimit.position;boatDirection.y=0;boatDirection.Normalize();
        sourceHeading=Mathf.Atan2(Vector3.Dot(feedDirection,axisY),Vector3.Dot(feedDirection,axisX));
        boatHeading=Mathf.Atan2(Vector3.Dot(boatDirection,axisY),Vector3.Dot(boatDirection,axisX));
        home=source-feedDirection*1.285f+boatDirection*.65f;home.y=source.y;
        initialized=true;commanded=home;heading=boatHeading;Solve(home,boatHeading);
    }
    float Delta=>validationDelta>0?validationDelta:paused?0:Time.deltaTime;
    static void Require(bool condition,string message){if(!condition)throw new InvalidOperationException(message);}
    void State(string value){status=value;Debug.Log("OX_CYCLE "+value);}
    public void Solve(Vector3 target,float angle)
    {
        Vector3 relative=target-origin;
        float x=Vector3.Dot(relative,axisX)-tip*Mathf.Cos(angle);
        float y=Vector3.Dot(relative,axisY)-tip*Mathf.Sin(angle);
        float r=Mathf.Sqrt(x*x+y*y);
        Require(r>Mathf.Abs(l1-l2)+.001f&&r<l1+l2-.001f,"Robot target outside reach: "+target);
        float a2=Mathf.Acos(Mathf.Clamp((r*r-l1*l1-l2*l2)/(2*l1*l2),-1,1));
        float a1=Mathf.Atan2(y,x)-Mathf.Atan2(l2*Mathf.Sin(a2),l1+l2*Mathf.Cos(a2));
        joint1.localRotation=Quaternion.AngleAxis(a1*Mathf.Rad2Deg,Vector3.forward);
        joint2.localRotation=Quaternion.AngleAxis(a2*Mathf.Rad2Deg,Vector3.forward);
        wrist.localRotation=Quaternion.AngleAxis((angle-a1-a2)*Mathf.Rad2Deg,Vector3.forward);
        joint1.position+=axisZ*Vector3.Dot(target-contact.position,axisZ);
        Require(Vector3.Distance(contact.position,target)<.002f,"Blade failed to reach target.");
        float limit=Vector3.Dot(wristLimit.position-origin,axisX);
        foreach(var renderer in armRenderers)
        {
            // Conservative world AABB projection catches a hand/arm crossing the side partition.
            var local=renderer.GetComponent<MeshFilter>().sharedMesh.bounds;
            var b=new Bounds(renderer.transform.TransformPoint(local.center),Vector3.zero);
            for(int i=0;i<8;i++)b.Encapsulate(renderer.transform.TransformPoint(local.center+Vector3.Scale(local.extents,new Vector3((i&1)==0?-1:1,(i&2)==0?-1:1,(i&4)==0?-1:1))));
            float max=Vector3.Dot(b.center-origin,axisX)+Mathf.Abs(axisX.x)*b.extents.x+Mathf.Abs(axisX.y)*b.extents.y+Mathf.Abs(axisX.z)*b.extents.z;
            Require(max<limit+.001f,"Robot arm crosses furnace-side wall: "+renderer.name);
        }
    }
    IEnumerator Wait(float duration){for(float t=0;t<duration;){t+=Delta;yield return null;}}
    IEnumerator MoveRobot(Vector3 target,float angle,float duration)
    {
        var from=commanded;float oldAngle=heading;
        for(float t=0;t<duration;){t+=Delta;float f=Mathf.SmoothStep(0,1,Mathf.Clamp01(t/duration));Solve(Vector3.Lerp(from,target,f),Mathf.Lerp(oldAngle,angle,f));yield return null;}
        Solve(target,angle);commanded=target;heading=angle;
    }
    IEnumerator Move(Transform item,Vector3 target,float duration)
    {
        var from=item.position;
        for(float t=0;t<duration;){t+=Delta;item.position=Vector3.Lerp(from,target,Mathf.SmoothStep(0,1,Mathf.Clamp01(t/duration)));yield return null;}
        item.position=target;
    }
    Vector3 Inward=>-feedDirection;
    Vector3 SourceReady(float height){var p=source-feedDirection*1.155f;p.y=height;return p;}
    Vector3 Clear(float height){var p=origin+boatDirection*.95f+feedDirection*.49f;p.y=height;return p;}
    Vector3 BoatApproach(float height){var p=boatTarget.position-boatDirection*.95f;p.y=height;return p;}
    Vector3 WaferCentre=>wafer.TransformPoint(wafer.GetComponent<MeshFilter>().sharedMesh.bounds.center);
    void Grab(){wafer.SetParent(contact,true);Require(Vector3.Distance(WaferCentre,contact.position)<.003f,"Wafer not on blade. Centre="+WaferCentre+" contact="+contact.position+" delta="+(WaferCentre-contact.position));}
    public IEnumerator Cycle()
    {
        if(!TransportAvailable||running)yield break;
        var lotRecipe=DemoApprovedLotRecipes.BeginLot(lotId);
        if(lotRecipe!=null){targetOxideNm=(float)(lotRecipe.oxide_reference_um*1000);approvedEpiDoping=lotRecipe.epi_doping;approvedRecipeId=lotRecipe.approved_proposal_id;}
        Initialize();running=true;completed=failed=false;paused=false;
        wafer.SetParent(waferParent,false);wafer.localPosition=waferLocalStart;wafer.rotation=waferRotation;boat.position=boatStart;
        foreach(var i in new[]{0,1,2})equipmentDoors[i].position=doorStart[i];carrierDoor.position=carrierDoorStart;
        commanded=home;heading=boatHeading;Solve(home,boatHeading);
        State("OPEN EQUIPMENT DOOR");
        yield return Move(equipmentDoors[1],doorStart[1]+Inward*.085f,.4f);
        yield return Move(equipmentDoors[1],doorStart[1]+Inward*.085f-Vector3.up*.60f,1);
        State("OPEN FOUP DOOR");
        yield return Move(carrierDoor,carrierDoorStart+Inward*.286f,.6f);
        yield return Move(carrierDoor,carrierDoorStart+Inward*.286f-Vector3.up*.60f,1);
        State("PICK WAFER");
        yield return MoveRobot(SourceReady(source.y-.012f),sourceHeading,1.2f);
        yield return MoveRobot(source-Vector3.up*.012f,sourceHeading,1.6f);
        yield return MoveRobot(source,sourceHeading,.5f);Grab();
        yield return MoveRobot(source+Vector3.up*.015f,sourceHeading,.5f);
        yield return MoveRobot(SourceReady(source.y+.015f),sourceHeading,1.6f);
        State("TRANSFER TO BOAT");
        yield return MoveRobot(Clear(1.40f+boatStart.y-.8f),boatHeading,2);
        yield return MoveRobot(BoatApproach(boatTarget.position.y+.015f),boatHeading,1);
        yield return MoveRobot(boatTarget.position+Vector3.up*.015f,boatHeading,1.6f);
        yield return MoveRobot(boatTarget.position,boatHeading,.5f);
        wafer.SetParent(boat,true);State("WAFER ON BOAT");
        yield return MoveRobot(boatTarget.position-Vector3.up*.012f,boatHeading,.4f);
        yield return MoveRobot(BoatApproach(boatTarget.position.y-.012f),boatHeading,1.4f);
        yield return MoveRobot(Clear(source.y+.03f),boatHeading,1);
        State("BOAT UP");yield return Move(boat,boatUp.position,2);
        State("OXIDATION / SIMULATED");yield return Wait(2);
        State("BOAT DOWN");yield return Move(boat,boatStart,2);
        State("RETURN WAFER");
        yield return MoveRobot(BoatApproach(boatTarget.position.y-.012f),boatHeading,1);
        yield return MoveRobot(boatTarget.position-Vector3.up*.012f,boatHeading,1.6f);
        yield return MoveRobot(boatTarget.position,boatHeading,.4f);Grab();
        yield return MoveRobot(boatTarget.position+Vector3.up*.015f,boatHeading,.4f);
        yield return MoveRobot(BoatApproach(boatTarget.position.y+.015f),boatHeading,1.4f);
        yield return MoveRobot(Clear(source.y+.03f),boatHeading,1);
        yield return MoveRobot(SourceReady(source.y+.015f),sourceHeading,2);
        yield return MoveRobot(source+Vector3.up*.015f,sourceHeading,1.5f);
        yield return MoveRobot(source,sourceHeading,.5f);
        wafer.SetParent(waferParent,true);
        Require(Vector3.Distance(WaferCentre,source)<.003f,"Wafer did not return to original slot.");
        yield return MoveRobot(source-Vector3.up*.012f,sourceHeading,.4f);
        yield return MoveRobot(SourceReady(source.y-.012f),sourceHeading,1.5f);
        yield return MoveRobot(home,boatHeading,1.5f);
        State("CLOSE DOORS");
        yield return Move(carrierDoor,carrierDoorStart+Inward*.286f,1);
        yield return Move(carrierDoor,carrierDoorStart,.6f);
        yield return Move(equipmentDoors[1],doorStart[1]+Inward*.085f,1);
        yield return Move(equipmentDoors[1],doorStart[1],.4f);
        State("COMPLETE / WAFER BACK IN FOUP");running=false;completed=true;
    }
    public void ResetPreview()
    {
        wafer.SetParent(waferParent,false);wafer.localPosition=waferLocalStart;wafer.rotation=waferRotation;
        boat.position=boatStart;carrierDoor.position=carrierDoorStart;
        for(int i=0;i<doorStart.Length;i++)equipmentDoors[i].position=doorStart[i];
        commanded=home;heading=boatHeading;Solve(home,boatHeading);status="READY";completed=failed=running=paused=false;validationDelta=0;
    }
    IEnumerator Guard(IEnumerator task)
    {
        while(true)
        {
            object item;try{if(!task.MoveNext())yield break;item=task.Current;}
            catch(Exception e){failed=true;running=false;status="ERROR: "+e.Message;Debug.LogException(e);yield break;}
            if(item is IEnumerator nested){yield return Guard(nested);if(failed)yield break;}else yield return item;
        }
    }
    public void StartCycle()
    {
        if(!TransportAvailable||running)return;
        if(Application.isPlaying&&!transportControlled&&OhtFabCycle.TryStartInspection(1))return;
        StartCoroutine(Guard(Cycle()));
    }
    void OnGUI()
    {
        var previous=GUI.matrix;GUI.matrix=Matrix4x4.Scale(Vector3.one*Mathf.Min(Screen.width/1280f,Screen.height/720f));
        var panelMatrix=GUI.matrix;
        if(FactoryControlBar.BeginPanel(FactoryControlBar.Equipment.Oxidation,new Rect(15,15,505,155)))
        {
        GUI.skin.label.fontSize=17;GUI.Box(new Rect(15,15,505,155),"");
        GUI.Label(new Rect(28,23,485,30),"LOADER + OXIDATION | SIMULATION");GUI.Label(new Rect(28,57,485,30),approvedRecipeId==null?status:status+" | "+targetOxideNm.ToString("F2")+" nm setpoint");
        bool transportEnabled=GUI.enabled;GUI.enabled=transportEnabled&&(running||TransportAvailable);
        if(!running&&GUI.Button(new Rect(28,102,145,35),"Start / Restart"))StartCycle();
        if(running&&GUI.Button(new Rect(28,102,145,35),paused?"Resume":"Pause"))paused=!paused;GUI.enabled=transportEnabled;
        if(GUI.Button(new Rect(183,102,145,35),"View inside"))ShowInside();
        if(GUI.Button(new Rect(338,102,165,35),"Switch camera")){bool back=detail.enabled;foreach(var camera in Camera.allCameras)if(!camera.targetTexture)camera.enabled=false;(back?overview:detail).enabled=true;}
        }
        GUI.matrix=panelMatrix;
        GUI.matrix=previous;
    }
}

