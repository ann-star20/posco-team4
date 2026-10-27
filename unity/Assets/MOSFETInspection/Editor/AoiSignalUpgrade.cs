#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class AoiSignalUpgrade
{
    static AoiSignalUpgrade(){EditorApplication.update+=Tick;}
    static void Tick()
    {
        bool final=File.Exists("AoiSignalFinal.once");
        if((!File.Exists("AoiSignalUpgrade.once")&&!final)||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        if(final)File.Delete("AoiSignalFinal.once");
        if(File.Exists("AoiSignalUpgrade.once"))File.Delete("AoiSignalUpgrade.once");
        try
        {
            AssetDatabase.ImportAsset("Assets/MOSFETInspection/Resources/AoiSignal/layout.json",ImportAssetOptions.ForceUpdate);
            foreach(var path in Directory.GetFiles("Assets/MOSFETInspection/Resources/AoiSignal","*.png"))
            {
                var importer=(TextureImporter)AssetImporter.GetAtPath(path.Replace('\\','/'));
                if(!importer)throw new Exception("Signal artwork not imported: "+path);
                importer.textureCompression=TextureImporterCompression.Uncompressed;importer.sRGBTexture=true;importer.mipmapEnabled=false;importer.npotScale=TextureImporterNPOTScale.None;importer.maxTextureSize=4096;importer.filterMode=FilterMode.Bilinear;importer.wrapMode=TextureWrapMode.Clamp;importer.alphaIsTransparency=false;importer.SaveAndReimport();
            }
            AssetDatabase.SaveAssets();File.WriteAllText("AoiSignalUpgrade.status","Approved artwork imported without compression; scene build and runtime checks pending.");File.WriteAllText("AoiLightUpgrade.once","signal-workstation");
        }
        catch(Exception e){File.WriteAllText("AoiSignalUpgrade.status","FAILED: "+e);Debug.LogException(e);}
    }
}
#endif
