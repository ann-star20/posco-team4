#if UNITY_EDITOR
using System;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering.HighDefinition;

public static class StockerAnimationSetup
{
    static Transform Find(Transform root,string name)=>root.GetComponentsInChildren<Transform>(true).FirstOrDefault(t=>t.name==name)??throw new Exception("Missing stocker node "+name);
    public static void Configure(OhtFabCycle oht)
    {
        var root=GameObject.Find("Mini_Stocker_6Slot").transform;
        var stock=root.GetComponent<StockerCycle>();if(!stock)stock=root.gameObject.AddComponent<StockerCycle>();
        stock.oht=oht;oht.stocker=stock;
        stock.frameOrigin=Find(root,"Stocker_Frame_Origin");stock.frameX=Find(root,"Stocker_Frame_X");stock.frameFront=Find(root,"Stocker_Frame_Front");
        stock.elevator=Find(root,"Elevator_Carriage");stock.slider=Find(root,"Horizontal_Slider");stock.fork=Find(root,"FOUP_Fork");stock.attachPoint=Find(root,"FOUP_AttachPoint");
        stock.shutter=Find(root,"Port_Door_ANIM");stock.ioDock=Find(root,"FOUP_DockPoint");
        stock.slots=Enumerable.Range(1,6).Select(i=>Find(root,"Slot_"+i.ToString("D2")+"_DockPoint")).ToArray();
        var depth=-(stock.frameFront.position-stock.frameOrigin.position).normalized;
        // Match the corrected Blender carriage clearances on the already-unpacked scene model.
        Find(root,"Moving_X_Beam").position=stock.elevator.position-Vector3.up*.05f;
        Find(root,"X_Linear_Guide").position=stock.elevator.position-depth*.058f-Vector3.up*.015f;
        Find(root,"X_Carriage_Block").position=stock.slider.position-Vector3.up*.055f;
        var samples=Enumerable.Range(1,3).Select(i=>Find(root,"FOUP_Example_"+i.ToString("D2"))).ToArray();
        stock.forkParts=stock.fork.GetComponentsInChildren<Renderer>(true);
        stock.movingParts=new[]{"Moving_X_Beam","X_Linear_Guide","X_Carriage_Block"}.Select(n=>Find(root,n).GetComponent<Renderer>()).ToArray();
        var all=root.GetComponentsInChildren<Renderer>(true);
        stock.fixedParts=all.Where(r=>r.GetComponent<MeshFilter>()&&!r.transform.IsChildOf(oht.foup)&&!r.transform.IsChildOf(stock.elevator)&&!r.transform.IsChildOf(stock.shutter)&&!samples.Any(p=>r.transform.IsChildOf(p))&&!r.name.StartsWith("Slot_Locator")&&!r.name.StartsWith("Port_Locator")).ToArray();
        stock.cutawayPanels=all.Where(r=>new[]{"Front_Main_Panel","Front_Right_Lower","Front_Right_Upper","Port_Right_Closure","Roof_Panel","Left_Panel","Right_Panel","Rear_Panel"}.Contains(r.name)||r.name.StartsWith("Maintenance_Door")||r.name.StartsWith("Side_Service_Door")||r.name.StartsWith("Model_Name")||r.name.StartsWith("Capacity_Label")||r.name.StartsWith("HMI_")||r.name=="Emergency_Stop").ToArray();
        var cameraObject=GameObject.Find("STOCKER_DETAIL_CAMERA");var camera=cameraObject?cameraObject.GetComponent<Camera>():new GameObject("STOCKER_DETAIL_CAMERA").AddComponent<Camera>();
        camera.CopyFrom(oht.overview);camera.enabled=false;camera.targetTexture=null;camera.nearClipPlane=.02f;camera.fieldOfView=43;camera.allowDynamicResolution=false;
        var hd=camera.GetComponent<HDAdditionalCameraData>();if(!hd)hd=camera.gameObject.AddComponent<HDAdditionalCameraData>();
        hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;hd.allowDynamicResolution=false;
        stock.detail=camera;stock.ResetStoredPreview();
        camera.transform.position=stock.World(new Vector3(3.2f,-4.6f,3.4f));camera.transform.LookAt(stock.World(new Vector3(0,-.25f,1.40f)));
        samples[0].gameObject.SetActive(false);samples[1].gameObject.SetActive(true);samples[2].gameObject.SetActive(true);
        EditorUtility.SetDirty(stock);
    }
}
#endif
