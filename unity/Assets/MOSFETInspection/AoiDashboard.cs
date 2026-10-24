using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Rendering.HighDefinition;

[ExecuteAlways]
public partial class AoiDashboard : MonoBehaviour
{
    public AoiJetsonFeed feed;
    public Text connection,identity,verdict,kind,confidence,route,message,counts,imageState;
    public RawImage cameraImage;
    public AspectRatioFitter imageFit;
    [SerializeField] Text metadata,detailCount,detailNote,provenance,recentText,historyTitle,historyDetail,historyPage;
    [SerializeField] Text[] statValues,defectNames,historyRows,recentCells;
    [SerializeField] RawImage[] crops;
    [SerializeField] GameObject inspectionRoot,historyRoot;
    [SerializeField] Image resultPanel;
    [SerializeField] Text detectionList,inspectionInfo;
    [SerializeField] Button[] defectButtons;
    Font font;
    Camera popupCamera;
    RenderTexture popupTexture;
    bool open;
    bool cameraSettings;
    string cameraAddress="";
    string previewCameraId="",previewToken="";
    AoiCameraStream cameraStream;
    bool inspectCurrentCamera=true;
    string tokenInput="",shownResult;
    Rect window;
    int view,photoView,selectedDefect,defectPage,page,filter;
    DateTime historyDay;
    float nextRefresh;
    readonly List<RectTransform> outlines=new List<RectTransform>();
    List<AoiInspectionHistory.Entry> visibleHistory=new List<AoiInspectionHistory.Entry>();
    RectTransform buildParent;
    public bool WindowOpen=>open;
    public int DetailCount=>feed&&feed.current!=null&&feed.current.defects!=null?feed.current.defects.Length:0;
    public int SelectedDefect=>selectedDefect;
    public int PhotoView=>photoView;
    public int View=>view;
    public string TodaySummary=>statValues==null?"":string.Join(" | ",statValues.Select(v=>v?v.text:""));
    static readonly Color Ink=new Color32(231,235,239,255),Muted=new Color32(171,183,195,255),Blue=new Color32(130,183,228,255),Soft=new Color32(55,66,77,255),Green=new Color32(100,211,155,255),Red=new Color32(255,119,126,255),Panel=new Color32(30,37,44,255),Bar=new Color32(49,59,69,255);
    void OnEnable(){historyDay=DateTime.Today;ApplyFont();BindButtons();Refresh();}
    void ApplyFont()
    {
        if(!font)font=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Noto Sans CJK KR","Arial"},28);
        if(!font)font=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        if(!signalSurface)foreach(var t in GetComponentsInChildren<Text>(true))t.font=font;
    }
    RectTransform Box(string name,float x,float y,float w,float h)
    {
        var g=new GameObject(name,typeof(RectTransform));g.transform.SetParent(buildParent?buildParent:transform,false);
        var r=g.GetComponent<RectTransform>();r.anchorMin=r.anchorMax=r.pivot=new Vector2(0,1);r.anchoredPosition=new Vector2(x,-y);r.sizeDelta=new Vector2(w,h);return r;
    }
    Image Fill(string name,float x,float y,float w,float h,Color color)
    {var r=Box(name,x,y,w,h);var im=r.gameObject.AddComponent<Image>();im.color=color;im.raycastTarget=false;return im;}
    Text Label(string name,string value,float x,float y,float w,float h,int size,Color color,bool bold=false,TextAnchor align=TextAnchor.MiddleLeft)
    {
        var r=Box(name,x,y,w,h);var t=r.gameObject.AddComponent<Text>();t.font=font;t.text=value;t.fontSize=size;t.fontStyle=bold?FontStyle.Bold:FontStyle.Normal;t.color=color;t.alignment=align;t.supportRichText=false;t.raycastTarget=false;t.horizontalOverflow=HorizontalWrapMode.Wrap;t.verticalOverflow=VerticalWrapMode.Truncate;return t;
    }
    Button Button(string name,string text,float x,float y,float w,float h)
    {
        var image=Fill(name,x,y,w,h,Soft);image.raycastTarget=true;var b=image.gameObject.AddComponent<Button>();b.targetGraphic=image;
        var old=buildParent;buildParent=image.rectTransform;Label("Label",text,4,0,w-8,h,16,Blue,true,TextAnchor.MiddleCenter);buildParent=old;return b;
    }
    RawImage Picture(string name,float x,float y,float w,float h,bool fit)
    {
        var viewport=Box(name+"Viewport",x,y,w,h);viewport.gameObject.AddComponent<RectMask2D>();
        var g=new GameObject(name,typeof(RectTransform),typeof(RawImage));g.transform.SetParent(viewport,false);var r=(RectTransform)g.transform;r.anchorMin=Vector2.zero;r.anchorMax=Vector2.one;r.offsetMin=r.offsetMax=Vector2.zero;
        var image=g.GetComponent<RawImage>();image.raycastTarget=false;
        if(fit){var fitter=g.AddComponent<AspectRatioFitter>();fitter.aspectMode=AspectRatioFitter.AspectMode.FitInParent;if(name=="JetsonImage")imageFit=fitter;}
        return image;
    }
    GameObject Group(string name){buildParent=null;return Box(name,0,0,1200,970).gameObject;}
    public void Build(AoiJetsonFeed source) => BuildSignal(source);
    void BindButtons()
    {
        foreach(var b in GetComponentsInChildren<Button>(true))
        {
            string name=b.name;b.onClick.RemoveAllListeners();
            if(name=="ViewInspection")b.onClick.AddListener(()=>SetView(0));else if(name=="ViewHistory")b.onClick.AddListener(()=>SetView(1));
            else if(name=="PhotoFull")b.onClick.AddListener(()=>SetPhotoView(0));else if(name=="PhotoZoom")b.onClick.AddListener(()=>SetPhotoView(1));else if(name=="PhotoLive")b.onClick.AddListener(()=>SetPhotoView(2));
            else if(name=="PhotoProduct")b.onClick.AddListener(()=>SetPhotoView(3));
            else if(name=="SelectDefect0")b.onClick.AddListener(()=>SelectDefect(defectPage*2));else if(name=="SelectDefect1")b.onClick.AddListener(()=>SelectDefect(defectPage*2+1));
            else if(name=="DefectPrevious")b.onClick.AddListener(()=>ShiftDefectPage(-1));else if(name=="DefectNext")b.onClick.AddListener(()=>ShiftDefectPage(1));
            else if(name=="ConnectionSettings")b.onClick.AddListener(()=>{connectionSettings=true;});
            else if(name=="DefectTab")b.onClick.AddListener(()=>{productTab=false;Refresh();});
            else if(name=="ProductTab")b.onClick.AddListener(()=>{productTab=true;Refresh();});
            else if(name=="SignalClose")b.onClick.AddListener(ToggleWindow);
            else if(name=="RequestInspection")b.onClick.AddListener(BeginRequest);else if(name=="SortProduct")b.onClick.AddListener(()=>feed.BeginSort());
            else if(name=="HistoryPreviousDay")b.onClick.AddListener(()=>ShiftDay(1));else if(name=="HistoryNextDay")b.onClick.AddListener(()=>ShiftDay(-1));
            else if(name=="HistoryPreviousPage")b.onClick.AddListener(()=>{page=Math.Max(0,page-1);Refresh();});else if(name=="HistoryNextPage")b.onClick.AddListener(()=>{page++;Refresh();});
            else if(name=="HistoryFilter")b.onClick.AddListener(()=>{filter=(filter+1)%4;page=0;Refresh();});
            else if(name.StartsWith("HistoryRow")&&int.TryParse(name.Substring(10),out int row)){int index=row;b.onClick.AddListener(()=>SelectHistory(index));}
        }
    }
    public void SetView(int value){view=Mathf.Clamp(value,0,1);Refresh();}
    AoiCameraStream CameraStream
    {
        get {if(!cameraStream&&Application.isPlaying){cameraStream=GetComponent<AoiCameraStream>();if(!cameraStream)cameraStream=gameObject.AddComponent<AoiCameraStream>();}return cameraStream;}
    }
    public void SetPhotoView(int value)
    {
        photoView=Mathf.Clamp(value,0,3);
        if(photoView==2&&Application.isPlaying){cameraAddress=CameraStream.Address;cameraSettings=!CameraStream.Running;}
        Refresh();
    }
    public void SelectDefect(int index){if(index<0||index>=DetailCount)return;selectedDefect=index;photoView=1;Refresh();}
    void ShiftDefectPage(int delta){defectPage=Mathf.Clamp(defectPage+delta,0,Mathf.Max(0,(DetailCount-1)/2));Refresh();}
    public void ShiftDay(int delta)
    {var days=AoiInspectionHistory.Instance.Days(Source);int i=days.IndexOf(historyDay.Date);historyDay=days[Mathf.Clamp(Math.Max(0,i)+delta,0,days.Count-1)];page=0;Refresh();}
    void SelectHistory(int index)
    {int row=page*6+index;if(row<visibleHistory.Count){var e=visibleHistory[row];historyDetail.text="검사 ID: "+e.inspection_id+" | LOT: "+e.lot_id+" | 출처: "+e.source+" | 불량 위치 "+e.defect_count+"곳";}}
    string Source=>feed&&feed.demoMode?"demo":feed&&feed.current!=null?(string.IsNullOrWhiteSpace(feed.current.data_source)?"unspecified":feed.current.data_source):"prod";
    public static string DefectTitle(string value)=>value=="normal"?"정상":value=="crash"?"파손 / crash":value=="scratch"?"스크래치 / scratch":value=="band"?"밴드 / band":value=="bend"?"휘어짐 / bend":value+" · 검토";
    static Rect CropRect(float[] region,bool pad)
    {
        float x=region[0],y=region[1],right=region[2],bottom=region[3];float mx=pad?Mathf.Max(.01f,(right-x)*.12f):0,my=pad?Mathf.Max(.01f,(bottom-y)*.12f):0;
        float left=Mathf.Max(0,x-mx),top=Mathf.Max(0,y-my);right=Mathf.Min(1,right+mx);bottom=Mathf.Min(1,bottom+my);return new Rect(left,1-bottom,right-left,bottom-top);
    }
    void ClearOutlines(){foreach(var item in outlines)if(item){item.gameObject.SetActive(false);Destroy(item.gameObject);}outlines.Clear();}
    void RebuildOutlines()
    {
        ClearOutlines();if(!feed.frame||feed.current==null||feed.current.defects==null)return;
        // shortcut: only the first 128 boxes are drawn together; every defect remains available through paged crops.
        for(int i=0;i<feed.current.defects.Length&&i<128;i++)
        {
            if(!AoiDirectProtocol.TryRegion(feed.current.defects[i],feed.frame.width,feed.frame.height,out var region))continue;
            var g=new GameObject("Region"+i,typeof(RectTransform));g.transform.SetParent(cameraImage.transform,false);var r=(RectTransform)g.transform;r.anchorMin=new Vector2(region[0],1-region[3]);r.anchorMax=new Vector2(region[2],1-region[1]);r.offsetMin=r.offsetMax=Vector2.zero;
            for(int edge=0;edge<4;edge++)
            {
                var e=new GameObject("Edge",typeof(RectTransform),typeof(Image));e.transform.SetParent(r,false);var rect=(RectTransform)e.transform;
                if(edge<2){rect.anchorMin=new Vector2(0,edge);rect.anchorMax=new Vector2(1,edge);rect.offsetMin=new Vector2(0,-1);rect.offsetMax=new Vector2(0,1);}else{rect.anchorMin=new Vector2(edge-2,0);rect.anchorMax=new Vector2(edge-2,1);rect.offsetMin=new Vector2(-1,0);rect.offsetMax=new Vector2(1,0);}
                var image=e.GetComponent<Image>();image.color=Red;image.raycastTarget=false;
            }
            var label=new GameObject("Number",typeof(RectTransform),typeof(Text));label.transform.SetParent(r,false);var lr=(RectTransform)label.transform;lr.anchorMin=lr.anchorMax=new Vector2(0,1);lr.pivot=new Vector2(0,0);lr.anchoredPosition=new Vector2(2,2);lr.sizeDelta=new Vector2(100,23);
            var text=label.GetComponent<Text>();text.font=font;text.fontSize=18;text.fontStyle=FontStyle.Bold;text.color=Red;text.text=(i+1).ToString("00");text.raycastTarget=false;outlines.Add(r);
        }
    }
    public void Refresh()
    {
        if(signalSurface){RefreshSignal();return;}
        if(!feed||!connection||!metadata||!inspectionRoot||recentCells==null||recentCells.Length!=12||historyRows==null||historyRows.Length!=36)return;
        var p=feed.current;var client=feed.GetComponent<AoiDirectClient>();bool inspecting=client&&client.Inspecting;
        if(shownResult!=(p==null?null:p.result_id)){shownResult=p==null?null:p.result_id;selectedDefect=defectPage=0;if(photoView!=2)photoView=p==null?0:3;historyDetail.text="";RebuildOutlines();}
        if(p==null&&outlines.Count>0)ClearOutlines();
        connection.text="AOI-01  |  "+feed.connection;
        metadata.text="설비 AOI-01    |    LOT: "+(p==null||string.IsNullOrEmpty(p.lot_id)?"—":p.lot_id)+"    |    제품: "+(p==null?"—":p.product_id)+"    |    본체 · 리드 외관";
        string status=inspecting?"검사 중":feed.Verdict;verdict.text=status;verdict.fontSize=status=="검사 중"?34:54;verdict.color=status=="NG"?Red:status=="OK"?Green:Muted;
        resultPanel.color=Panel;
        bool multiple=DetailCount>1;kind.fontSize=multiple?15:17;
        kind.text=multiple?"불량 "+DetailCount+"곳: "+string.Join(" · ",p.defects.Select(d=>DefectTitle(d.class_name).Split('/')[0].Trim()).Distinct()):"불량 유형: "+(p==null?"—":p.label=="normal"?"검출 없음":DefectTitle(p.label));
        confidence.text=(multiple?"최대 모델 점수: ":"모델 점수: ")+(p==null||p.label=="normal"?"—":(p.confidence*100).ToString("F1")+"%")+(p!=null&&(p.data_source=="demo"||p.data_source=="mock")?" (시험)":"");
        route.text=feed.Busy?"분류 동작 중":feed.SortCompleted?feed.Verdict+" 박스 도착 · 완료":feed.CanSort?feed.Verdict+" 박스 방향 · 수동 분류 대기":"분류 대기 · 정지";
        identity.text=p==null?"제품 · 검사 ID · 시각: 수신 대기":"제품: "+p.product_id+"\n검사: "+(string.IsNullOrEmpty(p.request_id)?p.result_id:p.request_id)+"\n시각: "+DateTimeOffset.FromUnixTimeMilliseconds(p.captured_at_ms).ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss");
        Texture2D display=photoView==2?(CameraStream?CameraStream.Frame:null):(feed.DisplayCurrent?feed.frame:null);
        bool show=display;cameraImage.texture=display;cameraImage.enabled=show;cameraImage.uvRect=new Rect(0,0,1,1);
        imageState.gameObject.SetActive(!show);imageState.text=photoView==2?(CameraStream?CameraStream.Status:"카메라 주소 입력 대기")+"\n실시간 영상 버튼에서 주소 설정":inspecting?"Jetson 검사·사진 수신 중":"검사 사진 수신 대기";
        if(photoView==2)identity.text="영상: "+(CameraStream?CameraStream.Status:"연결 대기")+"\n우측 OK/NG는 마지막 검사 결과입니다.\n영상 표시만으로 새 검사가 실행되지는 않습니다.";
        if(show)
        {
            if(photoView==1&&DetailCount>0&&AoiDirectProtocol.TryRegion(p.defects[selectedDefect],feed.frame.width,feed.frame.height,out var selected))cameraImage.uvRect=CropRect(selected,true);
            if(photoView==3&&p!=null)
            {
                var regions=(p.parts??new AoiDirectProtocol.Detection[0]).Concat(p.defects??new AoiDirectProtocol.Detection[0]);
                float left=1,top=1,right=0,bottom=0;
                foreach(var d in regions)if(AoiDirectProtocol.TryRegion(d,display.width,display.height,out var region)){left=Mathf.Min(left,region[0]);top=Mathf.Min(top,region[1]);right=Mathf.Max(right,region[2]);bottom=Mathf.Max(bottom,region[3]);}
                if(right>left&&bottom>top)cameraImage.uvRect=CropRect(new[]{left,top,right,bottom},true);
            }
            imageFit.aspectRatio=display.width*cameraImage.uvRect.width/(display.height*cameraImage.uvRect.height);
        }
        foreach(var outline in outlines)if(outline)outline.gameObject.SetActive(show&&photoView==0);
        if(detectionList){int first=defectPage*2;detectionList.text=DetailCount==0?(p==null?"검사 전":p.label=="normal"?"검출된 불량 없음":"불량 목록 미수신"):string.Join("\n",p.defects.Skip(first).Take(2).Select((d,i)=>(first+i+1).ToString("00")+"   "+DefectTitle(d.class_name)+"   "+d.confidence.ToString("F3")));}
        if(inspectionInfo)inspectionInfo.text="검사 ID: "+(p==null?"—":Short(string.IsNullOrEmpty(p.request_id)?p.result_id:p.request_id))+"\nDB: 미연결 · 검사 결과 로컬 저장";
        detailCount.text=DetailCount>0?"검출 "+DetailCount+"곳":p==null?"검사 전":p.label=="normal"?"검출 0곳":"좌표 미수신";
        defectPage=Mathf.Clamp(defectPage,0,Mathf.Max(0,(DetailCount-1)/2));
        for(int i=0;i<2;i++)
        {
            int index=defectPage*2+i;bool exists=index<DetailCount;defectButtons[i].gameObject.SetActive(exists);crops[i].enabled=false;defectNames[i].text="";
            if(!exists)continue;var d=p.defects[index];bool valid=feed.frame&&AoiDirectProtocol.TryRegion(d,feed.frame.width,feed.frame.height,out _);
            if(valid){AoiDirectProtocol.TryRegion(d,feed.frame.width,feed.frame.height,out var region);crops[i].texture=feed.frame;crops[i].uvRect=CropRect(region,true);crops[i].GetComponent<AspectRatioFitter>().aspectRatio=feed.frame.width*crops[i].uvRect.width/(feed.frame.height*crops[i].uvRect.height);crops[i].enabled=true;}
            defectNames[i].text=(index+1).ToString("00")+"  "+DefectTitle(d.class_name)+"\n"+(d.confidence*100).ToString("F1")+"%"+(valid?" · 눌러서 확대":" · 위치 좌표 없음");defectNames[i].color=index==selectedDefect?Red:Ink;defectButtons[i].interactable=valid;
        }
        detailNote.text=DetailCount==0?(p==null?"검사 후 검출 위치 표시":p.label=="normal"?"검출된 불량이 없습니다.":"불량 판정 수신 · 위치 좌표는 제공되지 않았습니다."):"불량 위치 "+(defectPage*2+1)+"–"+Math.Min(DetailCount,defectPage*2+2)+" / "+DetailCount+" · 확대 사진 선택";
        message.text=feed.notice;var store=AoiInspectionHistory.Instance;var stats=store.ForDay(DateTime.Today,Source);
        statValues[0].text=store.Readable?stats.total+" 건":"집계 확인 필요";statValues[1].text=stats.pass+" 건";statValues[2].text=stats.ng+" 건";statValues[3].text=store.Readable?(stats.total==0?"—":stats.normalRate.ToString("F1")+"%"):"—";
        counts.text="분류 완료  OK "+feed.sorter.okCount+" / NG "+feed.sorter.ngCount+"  · 검사 집계와 별도";
        var recent=store.OnDay(DateTime.Today,Source).Take(2).ToList();recentText.text=recent.Count==0?"검사 완료 후 기록 표시":"";
        for(int row=0;row<2;row++)for(int col=0;col<6;col++){recentCells[row*6+col].text=row<recent.Count?Cell(recent[row],col):"";recentCells[row*6+col].color=row<recent.Count&&recent[row].verdict=="NG"?Red:Ink;}
        provenance.text=!string.IsNullOrEmpty(store.LastError)?store.LastError:"출처: "+Source+" · 오늘 판정 완료 기준 / DEMO·MOCK 분리 / 검토 제외 · "+(photoView==2?"실시간 영상 / 판정은 마지막 검사":"결과 사진 / 실시간 아님");
        visibleHistory=store.OnDay(historyDay,Source).Where(e=>filter==0||e.verdict==(filter==1?"OK":filter==2?"NG":"검토")).ToList();page=Mathf.Clamp(page,0,Mathf.Max(0,(visibleHistory.Count-1)/6));historyTitle.text="검사 이력 · "+historyDay.ToString("yyyy-MM-dd")+" · "+Source;
        for(int row=0;row<6;row++)for(int col=0;col<6;col++){int index=page*6+row;historyRows[row*6+col].text=index<visibleHistory.Count?Cell(visibleHistory[index],col):"";historyRows[row*6+col].color=index<visibleHistory.Count&&visibleHistory[index].verdict=="NG"?Red:Ink;}
        historyPage.text=visibleHistory.Count+"건 · "+(page+1)+" / "+Math.Max(1,(visibleHistory.Count+5)/6)+" 페이지 · 행을 누르면 전체 검사 ID 표시";inspectionRoot.SetActive(view==0);historyRoot.SetActive(view==1);
        foreach(var b in GetComponentsInChildren<Button>(true))
        {
            if(b.name=="SortProduct")b.interactable=feed.CanSort;else if(b.name=="RequestInspection")b.interactable=!feed.Busy&&!inspecting&&!feed.demoMode;
            else if(b.name=="DefectPrevious")b.interactable=defectPage>0;else if(b.name=="DefectNext")b.interactable=(defectPage+1)*2<DetailCount;else if(b.name=="PhotoZoom")b.interactable=feed.frame&&DetailCount>0;
            var label=b.transform.Find("Label");if(label&&b.name=="HistoryFilter")label.GetComponent<Text>().text=new[]{"전체","OK","NG","검토"}[filter];
            if(label&&b.name=="RequestInspection"){label.GetComponent<Text>().text=inspectCurrentCamera?"현재 화면 검사":"시험 사진 검사";b.interactable=b.interactable&&client&&client.HasToken&&(!inspectCurrentCamera||(CameraStream&&CameraStream.CanInspectFrame));}
            if(b.name=="ViewInspection"||b.name=="ViewHistory")b.GetComponent<Image>().color=(view==0&&b.name=="ViewInspection"||view==1&&b.name=="ViewHistory")?new Color32(70,88,106,255):Soft;
        }
    }
    static string Short(string id)=>id==null?"—":id.Substring(0,Math.Min(12,id.Length));
    static string Cell(AoiInspectionHistory.Entry e,int col)
    {switch(col){case 0:return Short(e.inspection_id);case 1:return e.Time.LocalDateTime.ToString("HH:mm:ss");case 2:return e.unit_id;case 3:return e.verdict;case 4:return DefectTitle(e.label);default:return e.label=="normal"?"—":(e.confidence*100).ToString("F1")+"%";}}
    void BeginRequest()
    {
        var direct=feed.GetComponent<AoiDirectClient>();if(!direct)return;if(!open)ToggleWindow();
        if(!string.IsNullOrWhiteSpace(tokenInput)){direct.SessionToken=tokenInput;tokenInput="";}
        if(direct.HasToken){if(inspectCurrentCamera)direct.BeginCameraInspection(CameraStream);else direct.BeginInspection();}
    }
    public bool HandlePointer(Vector2 pixel,Camera camera)
    {
        if(scanPresenting)return false;
        foreach(var b in GetComponentsInChildren<Button>(false))
        {
            if(!b.interactable)continue;var corners=new Vector3[4];((RectTransform)b.transform).GetWorldCorners(corners);var a=RectTransformUtility.WorldToScreenPoint(camera,corners[0]);var c=RectTransformUtility.WorldToScreenPoint(camera,corners[2]);
            if(new Rect(Vector2.Min(a,c),Vector2.Max(a,c)-Vector2.Min(a,c)).Contains(pixel)){b.onClick.Invoke();return true;}
        }
        return false;
    }
    public void ToggleWindow()
    {
        open=!open;if(!open){if(signalOverlay)signalOverlay.gameObject.SetActive(false);connectionSettings=false;cameraSettings=false;previewCameraId=previewToken="";if(popupCamera)popupCamera.enabled=false;return;}
        if(!popupCamera)
        {
            popupTexture=new RenderTexture(1800,1455,24);popupTexture.Create();popupCamera=new GameObject("AOI_MONITOR_WINDOW_CAMERA").AddComponent<Camera>();popupCamera.targetTexture=popupTexture;popupCamera.nearClipPlane=.01f;popupCamera.farClipPlane=2;popupCamera.allowDynamicResolution=false;
            var hd=popupCamera.gameObject.AddComponent<HDAdditionalCameraData>();hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;hd.allowDynamicResolution=false;
        }
        ConfigureSignalCamera();
        var rect=(RectTransform)transform;popupCamera.transform.position=transform.position-transform.forward*.6f;popupCamera.transform.LookAt(transform.position,transform.up);popupCamera.orthographic=true;popupCamera.orthographicSize=rect.rect.height*transform.lossyScale.y*.515f;popupCamera.enabled=true;
        ShowSignalOverlay();
        float scale=Mathf.Min(Screen.width/1280f,Screen.height/720f);window=new Rect((Screen.width/scale-1050)/2,8,1050,704);
    }
    void Update(){if(Application.isPlaying&&Time.unscaledTime>=nextRefresh){nextRefresh=Time.unscaledTime+.4f;Refresh();}}
    void DrawWindow(int id)
    {
        if(GUI.Button(new Rect(window.width-36,3,30,24),"X"))ToggleWindow();var direct=feed.GetComponent<AoiDirectClient>();
        if(direct)
        {
            GUI.Label(new Rect(12,32,100,26),"토큰 (숨김)");bool previous=GUI.enabled;GUI.enabled=!direct.Inspecting&&!feed.Busy&&!feed.demoMode;
            tokenInput=GUI.PasswordField(new Rect(112,32,Mathf.Max(100,window.width-390),27),tokenInput,'*',2048);
            if(GUI.Button(new Rect(window.width-268,32,84,27),"붙여넣기"))tokenInput=(GUIUtility.systemCopyBuffer??"").Trim();
            GUI.enabled=GUI.enabled&&(direct.HasToken||!string.IsNullOrWhiteSpace(tokenInput));
            GUI.enabled=GUI.enabled&&(!inspectCurrentCamera||(CameraStream&&CameraStream.CanInspectFrame));
            if(GUI.Button(new Rect(window.width-178,32,166,27),direct.Inspecting?"검사 중...":inspectCurrentCamera?"현재 화면 검사":"시험 사진 검사"))BeginRequest();GUI.enabled=previous;
            bool beforeMode=GUI.enabled;GUI.enabled=!direct.Inspecting;
            inspectCurrentCamera=GUI.Toggle(new Rect(12,62,180,25),inspectCurrentCamera,"현재 카메라 검사");GUI.enabled=beforeMode;
            GUI.Label(new Rect(202,62,window.width-214,25),(inspectCurrentCamera?"카메라 한 장 → Jetson · ":"시험 사진 검사 · ")+direct.Status);
        }
        var area=new Rect(8,direct?94:32,window.width-16,window.height-(direct?102:40));float ratio=popupTexture.width/(float)popupTexture.height;
        if(area.width/area.height>ratio){float width=area.height*ratio;area.x+=(area.width-width)/2;area.width=width;}else{float height=area.width/ratio;area.y+=(area.height-height)/2;area.height=height;}
        GUI.DrawTexture(area,popupTexture,ScaleMode.StretchToFill,false);var ev=Event.current;
        if(!cameraSettings&&ev.type==EventType.MouseDown&&ev.button==0&&area.Contains(ev.mousePosition)){var pixel=new Vector2((ev.mousePosition.x-area.x)/area.width*popupTexture.width,(1-(ev.mousePosition.y-area.y)/area.height)*popupTexture.height);if(HandlePointer(pixel,popupCamera))ev.Use();}
        GUI.DragWindow(new Rect(0,0,window.width-40,28));
    }
    void OnGUI()
    {
        if(!Application.isPlaying||!feed)return;
        var old=GUI.matrix;float s=Mathf.Min(Screen.width/1280f,Screen.height/720f);GUI.matrix=Matrix4x4.Scale(new Vector3(s,s,1));var panelMatrix=GUI.matrix;
        if(FactoryControlBar.BeginPanel(FactoryControlBar.Equipment.AOI,new Rect(15,448,550,224)))
        {
            GUI.Box(new Rect(15,448,550,224),"");GUI.Label(new Rect(28,458,520,25),"AOI | "+feed.connection);GUI.Label(new Rect(28,486,520,25),feed.Verdict+" | "+feed.notice);
            if(GUI.Button(new Rect(28,518,170,30),open?"Close AOI monitor":"AOI monitor window"))ToggleWindow();var direct=feed.GetComponent<AoiDirectClient>();bool prior=GUI.enabled;GUI.enabled=!feed.Busy&&(!direct||!direct.Inspecting);
            if(GUI.Button(new Rect(208,518,160,30),feed.demoMode?"Use Jetson":"Use DEMO"))feed.SetMode(!feed.demoMode);GUI.enabled=feed.CanSort;if(GUI.Button(new Rect(378,518,170,30),"Start OK / NG sort"))feed.BeginSort();GUI.enabled=prior;
            if(feed.demoMode){GUI.enabled=!feed.Busy;string[] names={"normal","crash","band","scratch"};for(int i=0;i<4;i++)if(GUI.Button(new Rect(28+i*130,560,120,30),names[i]))feed.Demo(names[i]);GUI.enabled=prior;}
            else if(direct){if(GUI.Button(new Rect(28,560,260,30),"Jetson 검사 요청 · 모니터 열기")){if(!open)ToggleWindow();}GUI.Label(new Rect(298,560,250,45),direct.Status);}
            else GUI.Label(new Rect(28,560,520,48),feed.useWebSocket?"WebSocket | "+feed.connection+" | manual sort":"HTTP | Waiting for Jetson inspection service");
            if(GUI.Button(new Rect(28,612,170,30),"AOI equipment view")){foreach(var camera in Camera.allCameras)if(!camera.targetTexture)camera.enabled=false;feed.sorter.overview.enabled=true;}
            GUI.Label(new Rect(208,612,340,45),"Manual sort | "+(feed.Busy?feed.sorter.Status:"Waiting for result"));
        }
        GUI.matrix=old;
        if(open&&signalSurface){DrawSignalInput();return;}
    }
    void DrawCameraSettings(int id)
    {
        if(string.IsNullOrEmpty(previewCameraId))previewCameraId=CameraStream.CameraId;
        GUI.Label(new Rect(18,35,565,27),"Jetson IP 또는 Preview WebSocket 주소");
        cameraAddress=GUI.TextField(new Rect(18,68,565,32),cameraAddress,512);
        GUI.Label(new Rect(18,106,565,46),"영상: ws://IP:8500/camera/preview\n검사: 같은 Jetson의 8400/aoi · 최신 프레임 번호로 요청");
        GUI.Label(new Rect(18,163,110,28),"카메라 ID");
        previewCameraId=GUI.TextField(new Rect(132,162,451,30),previewCameraId,256);
        GUI.Label(new Rect(18,203,110,28),"영상 토큰");
        previewToken=GUI.PasswordField(new Rect(132,202,451,30),previewToken,'*',2048);
        GUI.Label(new Rect(18,239,565,26),"CAMERA_PREVIEW_TOKEN · 검사 토큰과 별도");
        GUI.Label(new Rect(18,270,565,28),CameraStream.Status);
        if(GUI.Button(new Rect(18,307,180,34),"영상 연결")){if(CameraStream.ConnectJetson(cameraAddress,previewToken,previewCameraId)){cameraAddress=CameraStream.Address;cameraSettings=false;previewToken="";}Refresh();}
        if(GUI.Button(new Rect(208,307,180,34),"연결 해제")){CameraStream.Disconnect();previewCameraId=previewToken="";Refresh();}
        if(GUI.Button(new Rect(398,307,185,34),"닫기")){cameraSettings=false;previewCameraId=previewToken="";}
        GUI.Label(new Rect(18,350,565,30),"주소·카메라 ID만 저장 · 영상 토큰 저장 안 함 · AI 판정은 별도");
    }
    void OnDisable(){scanPresenting=false;ReleaseScanFrame();tokenInput="";previewCameraId=previewToken="";open=false;cameraSettings=false;if(cameraStream)cameraStream.Disconnect();if(popupCamera){popupCamera.targetTexture=null;DestroyImmediate(popupCamera.gameObject);}if(popupTexture){popupTexture.Release();DestroyImmediate(popupTexture);}if(signalOverlay)DestroyImmediate(signalOverlay.gameObject);}
}
