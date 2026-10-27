#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

[InitializeOnLoad]
public static class FilmWindowsUpgrade
{
    const string Key="FILM_WINDOWS_STYLE_CHECK";
    static double after;
    static FilmWindowsUpgrade(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        if(phase==3)
        {
            if(EditorApplication.isPlayingOrWillChangePlaymode)return;
            EditorSettings.enterPlayModeOptionsEnabled=SessionState.GetBool(Key+"Options",false);
            EditorSettings.enterPlayModeOptions=(EnterPlayModeOptions)SessionState.GetInt(Key+"Flags",0);
            SessionState.SetInt(Key,0);return;
        }
        try
        {
            if(phase==0)
            {
                if(!File.Exists("FilmWindowsUpgrade.once")||EditorApplication.isPlayingOrWillChangePlaymode||Application.isPlaying)return;
                SessionState.SetBool(Key+"Options",EditorSettings.enterPlayModeOptionsEnabled);
                SessionState.SetInt(Key+"Flags",(int)EditorSettings.enterPlayModeOptions);
                File.Delete("FilmWindowsUpgrade.once");
                var c=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();Check(c&&c.monitor,"Film monitor missing");
                var backup="Tools/Backups/FilmWindowsScene-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(backup);
                Check(!string.IsNullOrEmpty(c.gameObject.scene.path)&&File.Exists(c.gameObject.scene.path),"Saved factory scene required for backup");
                File.Copy(c.gameObject.scene.path,backup+"/BeforeFilmWindows.unity",true);
                FilmInspectionDashboard.Install(c);
                Check(c.dashboard.transform.Find("FilmSignalSurface/ClassicTitleBar"),"Classic title bar missing");
                EditorUtility.SetDirty(c.dashboard);Check(EditorSceneManager.SaveScene(c.gameObject.scene),"Scene save failed");
                SessionState.SetBool(Key+"Options",EditorSettings.enterPlayModeOptionsEnabled);
                SessionState.SetInt(Key+"Flags",(int)EditorSettings.enterPlayModeOptions);
                EditorSettings.enterPlayModeOptionsEnabled=false;SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(!Application.isPlaying)return;
            if(phase==2)
            {
                if(EditorApplication.timeSinceStartup<after)return;
                ScreenCapture.CaptureScreenshot("Temp/FilmWindows/FilmWindowsFail.png");
                File.AppendAllText("FilmWindowsUpgrade.result","\nScreenshot requested: Temp/FilmWindows/FilmWindowsFail.png");
                SessionState.SetInt(Key,4);after=EditorApplication.timeSinceStartup+2;return;
            }
            if(phase==4)
            {
                if(EditorApplication.timeSinceStartup<after)return;
                Check(File.Exists("Temp/FilmWindows/FilmWindowsFail.png"),"Screenshot missing");
                SessionState.SetInt(Key,3);EditorApplication.isPlaying=false;return;
            }
            var cycle=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();if(!cycle||!cycle.dashboard)return;
            var bridge=GatewayInspectionBridge.Instance;if(bridge){bridge.Disarm();bridge.enabled=false;}
            var manager=LotProcessAnalysis.Instance;if(manager)manager.enabled=false;
            var client=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();if(client)client.enabled=false;
            var d=cycle.dashboard;var root=d.transform.Find("FilmSignalSurface");
            Check(root.Find("ClassicTitleBar")&&!root.Find("Navigation"),"Dark sidebar layout returned");
            Check(root.Find("Background").GetComponent<Image>().color.r>.8f&&FilmInspectionDashboard.Ink.r<.3f,"Window palette is not light");
            Check(root.Find("TabHistory").GetComponent<RectTransform>().anchoredPosition.y==root.Find("TabOverview").GetComponent<RectTransform>().anchoredPosition.y,"Tabs are not horizontal");
            cycle.readings=new[]{float.NaN,float.NaN,float.NaN};cycle.verdict="PENDING";cycle.lotHeld=false;d.Refresh();
            Check(d.average.text=="— nm"&&d.judgement.text=="검사 대기","Pending changed");
            cycle.readings=new[]{60f,60f,60f};cycle.verdict="PASS";d.Refresh();
            Check(d.judgement.text=="PASS"&&d.judgementPanel.color.g>.8f,"PASS state changed");
            d.SetView(1);Check(d.View==1,"History tab failed");d.SetView(2);Check(d.View==2,"Criteria tab failed");d.SetView(0);
            cycle.readings=new[]{42f,42f,42f};cycle.verdict="FAIL";cycle.lotHeld=true;d.Refresh();
            Check(d.judgement.text=="FAIL"&&d.judgement.color==FilmInspectionDashboard.Red&&d.lot.text.Contains("HOLD"),"FAIL/HOLD changed");
            FactoryControlBar.Select(FactoryControlBar.Equipment.Ellipsometer);
            cycle.ZoomMonitor();cycle.ZoomMonitor();cycle.ZoomMonitor();
            var overlay=GameObject.Find("FILM_SIGNAL_SCREEN_OVERLAY");Check(overlay&&overlay.GetComponent<Canvas>().enabled&&overlay.transform.Find("FilmSignalSurface(Clone)/ClassicTitleBar"),"Classic style lost on reopen");
            Directory.CreateDirectory("Temp/FilmWindows");EditorApplication.ExecuteMenuItem("Window/General/Game");
            File.WriteAllText("FilmWindowsUpgrade.result","FILM_WINDOWS_STYLE_OK\nScene backed up and saved / light window and title bar / horizontal tabs / pending-PASS-FAIL-HOLD / history and criteria / centered overlay close-reopen preserved / offline only, no requests sent");
            SessionState.SetInt(Key,2);after=EditorApplication.timeSinceStartup+1;
        }
        catch(Exception e){File.WriteAllText("FilmWindowsUpgrade.result","FAILED: "+e);Debug.LogException(e);SessionState.SetInt(Key,3);EditorApplication.isPlaying=false;}
    }
}
#endif
