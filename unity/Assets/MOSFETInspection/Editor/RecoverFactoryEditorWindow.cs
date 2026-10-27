#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

[InitializeOnLoad] public static class RecoverFactoryEditorWindow
{
    static RecoverFactoryEditorWindow(){EditorApplication.update+=Tick;}
    static void Tick()
    {
        if(File.Exists("RestoreSceneGameHalves.once")&&!EditorApplication.isCompiling&&!EditorApplication.isUpdating){
            File.Delete("RestoreSceneGameHalves.once");
            try{
                var type=typeof(Editor).Assembly.GetType("UnityEditor.WindowLayout");
                var method=type.GetMethods(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static).Where(m=>m.Name=="LoadWindowLayout").First(m=>m.GetParameters().Length>0&&m.GetParameters()[0].ParameterType==typeof(string)&&m.GetParameters().Skip(1).All(p=>p.ParameterType==typeof(bool)));
                var ps=method.GetParameters();var args=new object[ps.Length];args[0]=Path.GetFullPath("Tools/Layouts/SceneGameHalves.dwlt");for(int i=1;i<args.Length;i++)args[i]=ps[i].Name=="keepMainWindow"||ps[i].Name=="setLastLoadedLayoutName";
                method.Invoke(null,args);
                foreach(SceneView view in SceneView.sceneViews){view.drawGizmos=false;var camera=GameObject.Find("FAB_OVERVIEW_CAMERA");if(camera)view.LookAt(new Vector3(-.1f,2.8f,0),camera.transform.rotation,16f);}
                File.WriteAllText("RestoreSceneGameHalves.result","SCENE_GAME_HALVES_LOADED\n"+DateTime.UtcNow.ToString("O"));
            }catch(Exception e){File.WriteAllText("RestoreSceneGameHalves.result",e.ToString());}
            return;
        }
        if(!File.Exists("RecoverFactoryEditorWindow.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("RecoverFactoryEditorWindow.once");
        try{
            var scene=SceneManager.GetActiveScene();
            if(scene.isDirty&&!EditorSceneManager.SaveScene(scene))throw new IOException("Could not preserve scene");
            string dir="Tools/Backups/BeforeEditorWindowRecovery-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(dir);
            foreach(var p in Directory.GetFiles("UserSettings/Layouts","*.dwlt"))File.Copy(p,Path.Combine(dir,Path.GetFileName(p)),true);
            bool reset=EditorApplication.ExecuteMenuItem("Window/Layouts/Default");
            var view=EditorWindow.GetWindow<SceneView>();view.Show();view.Focus();view.Repaint();
            File.WriteAllText("RecoverFactoryEditorWindow.result","EDITOR_WINDOW_RECOVERY_REQUESTED\n"+DateTime.UtcNow.ToString("O")+"\nLayout menu: "+reset+"\nScene: "+scene.path+"\nLayout backup: "+dir);
        }catch(Exception e){File.WriteAllText("RecoverFactoryEditorWindow.result","FAILED\n"+e);}
    }
}
#endif
