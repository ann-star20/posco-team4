using UnityEngine;

public class FactoryControlBar : MonoBehaviour
{
    public enum Equipment { Overview, Oxidation, Ellipsometer, Implanter, AOI, OHT, Stocker }
    public static Equipment Selected {get;private set;}
    public static bool Collapsed {get;private set;}
    static Font font;
    static Texture2D background,active;
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetSelection()
    {
        Selected=Equipment.Overview;Collapsed=false;
    }
    public static void Select(Equipment equipment)
    {
        Selected=equipment;Collapsed=false;
        if(equipment!=Equipment.Overview)return;
        var implant=FindAnyObjectByType<IonImplantCycle>();
        if(implant&&implant.overview)implant.SelectCamera(implant.overview);
    }
    public static void ToggleCollapsed(){Collapsed=!Collapsed;}
    public static bool Visible(Equipment equipment)=>Selected==equipment&&!Collapsed;
    public static Rect PanelRect(float width,float height)
    {
        float scale=Mathf.Min(Screen.width/1280f,Screen.height/720f);
        return new Rect((Screen.width/scale-width)*.5f,Screen.height/scale-76-height,width,height);
    }
    public static bool BeginPanel(Equipment equipment,Rect original)
    {
        if(!FindAnyObjectByType<FactoryControlBar>())return true;
        if(!Visible(equipment))return false;
        var target=PanelRect(original.width,original.height);
        GUI.matrix*=Matrix4x4.Translate(new Vector3(target.x-original.x,target.y-original.y,0));return true;
    }
    static Texture2D Solid(Color color)
    {var t=new Texture2D(1,1){hideFlags=HideFlags.HideAndDontSave};t.SetPixel(0,0,color);t.Apply();return t;}
    void OnGUI()
    {
        var matrix=GUI.matrix;var color=GUI.color;
        float scale=Mathf.Min(Screen.width/1280f,Screen.height/720f);GUI.matrix=Matrix4x4.Scale(Vector3.one*scale);
        if(!font)font=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Arial"},20);
        if(!background)background=Solid(new Color32(15,27,42,245));if(!active)active=Solid(new Color32(36,103,122,255));
        var style=new GUIStyle(GUI.skin.button){font=font,fontSize=18,alignment=TextAnchor.MiddleCenter};
        var chosen=new GUIStyle(style);chosen.normal.background=active;chosen.normal.textColor=Color.white;
        float width=1200,x=(Screen.width/scale-width)*.5f,y=Screen.height/scale-64;
        GUI.DrawTexture(new Rect(x-10,y-8,width+20,60),background);
        string[] names={"전체 보기","로딩·산화로","엘립소미터","이온주입기","AOI","OHT 이송","스토커"};
        for(int i=0;i<names.Length;i++)
            if(GUI.Button(new Rect(x+i*145,y,137,44),names[i],(int)Selected==i?chosen:style))Select((Equipment)i);
        bool prior=GUI.enabled;GUI.enabled=Selected!=Equipment.Overview;
        if(GUI.Button(new Rect(x+1015,y,175,44),Collapsed?"조작창 펼치기":"접기",style))ToggleCollapsed();GUI.enabled=prior;
        GUI.color=color;GUI.matrix=matrix;
    }
    void OnDestroy(){if(background)Destroy(background);if(active)Destroy(active);background=active=null;}
}
