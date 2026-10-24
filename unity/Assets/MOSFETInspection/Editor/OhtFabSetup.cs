#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.HighDefinition;

public static class OhtFabSetup
{
    const string Base="Assets/MOSFETInspection/";
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Tick;EditorApplication.update+=Tick;}
    static Transform Find(Transform root,string name)=>root.GetComponentsInChildren<Transform>(true).FirstOrDefault(t=>t.name==name)??throw new Exception("Missing "+name+" under "+root.name);
    static void Tick()
    {
        if(!File.Exists("OhtFabSetup.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlaying||EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        try{File.Delete("OhtFabSetup.once");}catch(IOException){return;}
        try{Install();}catch(Exception e){File.WriteAllText("OhtFabSetup.result",e.ToString());Debug.LogException(e);}
    }
    [MenuItem("MOSFET Factory/Install OHT Process Animation")]
    public static void Install()
    {
        var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        OhtFabCycle.Require(!EditorApplication.isPlaying&&scene.path==Base+"Scenes/MOSFETSmallFab_Corrected.unity","Open the corrected cleanroom outside Play");
        OhtFabCycle.Require(EditorSceneManager.SaveScene(scene),"Save cancelled");
        string backup=AssetDatabase.GenerateUniqueAssetPath(Base+"Scenes/MOSFETSmallFab_BeforeOhtAnimation.unity");
        OhtFabCycle.Require(AssetDatabase.CopyAsset(scene.path,backup),"Scene backup failed");
        try
        {
            var root=GameObject.Find("OHT_Cleanroom_Loop").transform;
            var old=GameObject.Find("OHT_FAB_CONTROLLER");if(old)UnityEngine.Object.DestroyImmediate(old);
            var test=new GameObject("OHT_FAB_CONTROLLER").AddComponent<OhtFabCycle>();
            test.route=AssetDatabase.LoadAssetAtPath<TextAsset>(Base+"Models/OHTLoop/OHT_Loop_layout.json");
            test.carrier=Find(root,"OHT_Carrier");test.lift=Find(root,"Lift_Frame");test.attachPoint=Find(root,"OHT_FOUP_AttachPoint");
            test.leftJaw=Find(root,"Gripper_Left");test.rightJaw=Find(root,"Gripper_Right");
            test.beltTops=root.GetComponentsInChildren<Transform>().Where(t=>t.name.StartsWith("Belt_Top_")).OrderBy(t=>t.name).ToArray();
            test.beltBottoms=root.GetComponentsInChildren<Transform>().Where(t=>t.name.StartsWith("Belt_Bottom_")).OrderBy(t=>t.name).ToArray();
            foreach(var renderer in root.GetComponentsInChildren<Renderer>().Where(r=>r.name=="Cable_Left"||r.name=="Cable_Right"))renderer.enabled=false;
            test.beltMaterial=AssetDatabase.LoadAssetAtPath<Material>(Base+"Materials/OHTLoop/LOOP_Graphite.mat");
            test.foup=GameObject.Find("OHT_FOUP_01").transform;test.foupGrip=Find(test.foup,"OHT_Grip_Anchor");test.foupDock=Find(test.foup,"LoadPort_Dock_Anchor");
            test.oxidation=UnityEngine.Object.FindAnyObjectByType<IntegratedOxidationCycle>();test.ellipsometer=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();test.implanter=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();
            test.stationCarriers=new[]{Find(GameObject.Find("Mini_Stocker_6Slot").transform,"FOUP_Example_01"),test.oxidation.carrierDoor.parent,test.ellipsometer.carrierDoor.parent,test.implanter.carrier};
            test.docks=new Transform[4];
            for(int i=0;i<4;i++)
            {
                var dock=new GameObject(new[]{"STOCKER_IO","OX_LOADPORT","ELLIP_LOADPORT","IMP_LOADPORT"}[i]+"_Runtime_Dock").transform;
                dock.SetParent(test.transform,true);dock.position=Find(test.stationCarriers[i],"LoadPort_Dock_Anchor").position;
                if(i==0)dock.position=Find(GameObject.Find("Mini_Stocker_6Slot").transform,"FOUP_DockPoint").position;
                test.docks[i]=dock;
            }
            test.overview=test.implanter.overview;
            foreach(var c in Camera.allCameras)if(!c.targetTexture)c.enabled=false;
            test.overview.enabled=true;
            old=GameObject.Find("OHT_FOLLOW_CAMERA");if(old)UnityEngine.Object.DestroyImmediate(old);
            var camera=new GameObject("OHT_FOLLOW_CAMERA").AddComponent<Camera>();camera.CopyFrom(test.overview);camera.enabled=false;camera.targetTexture=null;camera.nearClipPlane=.02f;camera.fieldOfView=55;camera.allowDynamicResolution=false;
            var hd=camera.gameObject.AddComponent<HDAdditionalCameraData>();hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;hd.allowDynamicResolution=false;test.followCamera=camera;
            OhtFabCycle.Require(test.beltTops.Length==2&&test.beltBottoms.Length==2&&test.beltMaterial,"Missing hoist belt anchors/material");
            // Install in a ready state: the transport FOUP is on the stocker I/O deck.
            test.foup.rotation=test.stationCarriers[0].rotation;test.foup.position+=test.docks[0].position-test.foupDock.position;
            for(int i=0;i<test.stationCarriers.Length;i++)test.stationCarriers[i].gameObject.SetActive(i>0);
            StockerAnimationSetup.Configure(test);
            EditorUtility.SetDirty(test);EditorSceneManager.MarkSceneDirty(scene);AssetDatabase.SaveAssets();OhtFabCycle.Require(EditorSceneManager.SaveScene(scene),"Scene save failed");
            Selection.activeObject=null;
            File.WriteAllText("OhtFabSetup.result","OHT_FAB_SETUP_OK\nbackup="+backup+"\nManual OHT tab, closed-loop route, hoist/jaws/two belts, station ownership, existing process cycles and HOLD gate.");
        }
        catch{EditorSceneManager.OpenScene(scene.path);throw;}
    }
}
#endif
