#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
public static class WaferVisualAudit
{
 [InitializeOnLoadMethod] static void Init(){EditorApplication.delayCall+=Run;}
 [MenuItem("MOSFET Factory/Audit Wafer Preview")]
 static void Run()
 {
  var demo=UnityEngine.Object.FindFirstObjectByType<WaferFeedDemo>();if(!demo)return;
  var camera=GameObject.Find("WAFER_FEED_CAMERA")?.GetComponent<Camera>();if(!camera)return;
  var root=demo.motion.gameObject;var clip=demo.motion.clip;
  string report="PLAYING="+EditorApplication.isPlaying+"\nROOT="+root.transform.position+" SCALE="+root.transform.lossyScale+"\n";
  var bindings=AnimationUtility.GetCurveBindings(clip);
  report+="ROOT_CURVES="+string.Join(",",bindings.Where(b=>b.path=="").Select(b=>b.propertyName))+"\n";
  var rt=new RenderTexture(1100,800,24);rt.Create();
  bool sample=!EditorApplication.isPlaying;
  if(sample)AnimationMode.StartAnimationMode();
  try{
   foreach(float t in sample?new[]{0f,2.13f,3.3f,5.3f,7.63f}:new[]{-1f})
   {
    if(sample){AnimationMode.BeginSampling();AnimationMode.SampleAnimationClip(root,clip,t);AnimationMode.EndSampling();}
    report+="TIME="+t+" ROOT="+root.transform.position+"\n";
    foreach(var n in new[]{"Robot_Wafer_Demo","Robot_Wrist_ANIM","Demo_FOUP_ROOT","REF_LP2_Door_ANIM"}){var o=root.GetComponentsInChildren<Transform>().First(x=>x.name==n);report+=n+"="+o.position+"\n";}
    for(int i=0;i<4;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});
    var old=RenderTexture.active;RenderTexture.active=rt;var image=new Texture2D(1100,800,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,1100,800),0,0);image.Apply();File.WriteAllBytes("WaferAudit_"+t.ToString("F2",System.Globalization.CultureInfo.InvariantCulture)+".png",image.EncodeToPNG());RenderTexture.active=old;UnityEngine.Object.DestroyImmediate(image);
   }
  }catch(Exception e){report+=e.ToString();}finally{if(sample)AnimationMode.StopAnimationMode();rt.Release();UnityEngine.Object.DestroyImmediate(rt);File.WriteAllText("WaferVisualAudit.result",report);}
 }
}
#endif
