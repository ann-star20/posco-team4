using UnityEngine;

public class WaferFeedDemo : MonoBehaviour
{
    public Animation motion;
    public string clipName;
    public Renderer[] cutawayPanels;
    bool started,paused,cutaway=true;
    void Start(){motion.playAutomatically=false;motion.Stop();ApplyCutaway();}
    void ApplyCutaway(){foreach(var r in cutawayPanels)if(r)r.enabled=!cutaway;}
    void OnGUI()
    {
        GUI.skin.label.fontSize=19;
        GUI.Box(new Rect(16,16,460,180),"");
        float t=started?motion[clipName].time:0;
        string state=!started?"READY":t<1.2f?"FOUP docking":t<2.2f?"Door opening":t<4.1f?"Wafer pickup":t<7.8f?"Transfer to aligner":t<10.4f?"Robot return":"Complete";
        GUI.Label(new Rect(30,25,440,35),"WAFER FEED / SIMULATION");
        GUI.Label(new Rect(30,62,440,35),state);
        if(GUI.Button(new Rect(30,105,130,35),"Start / Restart"))
        {motion.Stop();motion[clipName].time=0;motion[clipName].speed=1;motion.Play(clipName);started=true;paused=false;}
        if(GUI.Button(new Rect(170,105,130,35),paused?"Resume":"Pause"))
        {if(started){paused=!paused;motion[clipName].speed=paused?0:1;}}
        if(GUI.Button(new Rect(310,105,150,35),"Cutaway on/off")){cutaway=!cutaway;ApplyCutaway();}
        GUI.Label(new Rect(30,150,430,30),"Manual start | 11.6 sec | Single wafer");
    }
}
