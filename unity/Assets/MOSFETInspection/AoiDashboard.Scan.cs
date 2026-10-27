using UnityEngine;
using UnityEngine.UI;

public partial class AoiDashboard
{
    [SerializeField] GameObject scanRoot;
    [SerializeField] Image[] scanTiles;
    [SerializeField] Text scanCaption;
    Texture2D scanFrame;
    bool scanPresenting;
    float scanStarted;
    public const float ScanDuration=3f;
    void BuildScanPresentation()
    {
        var photo=Item("Photo");scanRoot=Box("InspectionScan",photo.x,photo.y,photo.w,photo.h).gameObject;
        var parent=buildParent;buildParent=(RectTransform)scanRoot.transform;
        float side=Mathf.Min(photo.w,photo.h)*.88f,cell=side/4f,left=(photo.w-side)*.5f,top=(photo.h-side)*.5f;
        scanTiles=new Image[16];
        for(int i=0;i<16;i++)
        {
            float x=left+i%4*cell,y=top+i/4*cell;scanTiles[i]=Fill("ScanCell"+i,x,y,cell,cell,new Color(0,1,0,.06f));
            var old=buildParent;buildParent=scanTiles[i].rectTransform;
            Fill("Top",0,0,cell,1.5f,Color.white);Fill("Bottom",0,cell-1.5f,cell,1.5f,Color.white);Fill("Left",0,0,1.5f,cell,Color.white);Fill("Right",cell-1.5f,0,1.5f,cell,Color.white);
            var number=Label("Region",(i+1).ToString("00"),6,4,38,22,11,new Color32(166,255,193,255));number.font=SignalFont("Consolas");buildParent=old;
        }
        Fill("ScanStatusSurface",(photo.w-286)/2,photo.h-43,286,31,new Color32(16,37,28,240));
        scanCaption=Label("ScanStatus","검사 중 · 01 / 16",(photo.w-286)/2,photo.h-43,286,31,12,new Color32(166,255,193,255),false,TextAnchor.MiddleCenter);
        buildParent=parent;scanRoot.SetActive(false);
    }
    public void BeginScanPresentation(byte[] jpeg)
    {
        ReleaseScanFrame();
        if(jpeg!=null){scanFrame=new Texture2D(2,2,TextureFormat.RGB24,false);if(!ImageConversion.LoadImage(scanFrame,jpeg))ReleaseScanFrame();}
        scanStarted=Time.realtimeSinceStartup;scanPresenting=true;cameraSettings=connectionSettings=false;view=0;Refresh();
    }
    public void EndScanPresentation(bool completed)
    {
        scanPresenting=false;ReleaseScanFrame();if(scanRoot)scanRoot.SetActive(false);
        if(completed){photoView=3;view=0;selectedDefect=defectPage=0;}Refresh();
    }
    void ReleaseScanFrame(){if(scanFrame){Destroy(scanFrame);scanFrame=null;}}
    void UpdateScanPresentation()
    {
        if(!scanRoot)return;scanRoot.SetActive(scanPresenting);if(!scanPresenting)return;
        float elapsed=Mathf.Max(0,Time.realtimeSinceStartup-scanStarted);int current=Mathf.Min(15,Mathf.FloorToInt(elapsed/ScanDuration*16));
        for(int i=0;i<scanTiles.Length;i++)
        {
            bool active=i<=current,highlight=i==current&&elapsed<ScanDuration;var tile=scanTiles[i];tile.gameObject.SetActive(active);
            if(!active)continue;tile.color=new Color32(99,255,150,(byte)(highlight?32:10));
            foreach(var border in tile.GetComponentsInChildren<Image>())if(border!=tile)border.color=new Color32(99,255,150,(byte)(highlight?255:135));
        }
        scanCaption.text=elapsed<ScanDuration?"검사 중 · "+(current+1).ToString("00")+" / 16":"검사 중 · Jetson 결과 대기";
    }
}
