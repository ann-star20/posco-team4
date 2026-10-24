using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UI;

public partial class FilmInspectionDashboard
{
    public const float SignalWidth=1080,SignalHeight=900;
    static readonly Color Background=new Color32(238,237,232,255),Deep=Color.white,LineColor=new Color32(173,182,175,255);
    [SerializeField] RectTransform signalSurface;
    [SerializeField] Text selectedId,selectedTime,measurementNote,lotNote,recentNote;
    [SerializeField] Text[] recentCells,plotValues;
    [SerializeField] Image judgementBorder;
    Canvas screenOverlay;
    RectTransform screenSurface;
    readonly List<KeyValuePair<Transform,Transform>> overlayTransforms=new List<KeyValuePair<Transform,Transform>>();
    readonly List<KeyValuePair<Graphic,Graphic>> overlayGraphics=new List<KeyValuePair<Graphic,Graphic>>();
    Rect screenArea;
    bool monitorOpen;

    void BoxPanel(string name,float x,float y,float w,float h,string caption)
    {
        Fill(name+"Border",x,y,w,h,LineColor);Fill(name,x+1,y+1,w-2,h-2,Panel);
        Fill(name+"Head",x+1,y+1,w-2,39,Soft);Fill(name+"Rule",x,y+40,w,1,LineColor);
        Label(name+"Title",caption,x+14,y+5,w-28,31,17,Ink,TextAnchor.MiddleLeft,true);
    }
    public void Build(EllipsometerCycle source)
    {
        cycle=source;buildParent=null;RemoveSignalOverlay();
        for(int i=transform.childCount-1;i>=0;i--)
        {
            var child=transform.GetChild(i);if(source.monitor&&child==source.monitor.transform)continue;
            if(Application.isPlaying){child.gameObject.SetActive(false);Destroy(child.gameObject);}else DestroyImmediate(child.gameObject);
        }
        ApplyFont();var root=(RectTransform)transform;
        // Keep the physical monitor width when replacing the old 960-pixel layout.
        float oldWidth=root.rect.width;if(oldWidth>0)root.localScale*=oldWidth/SignalWidth;
        root.sizeDelta=new Vector2(SignalWidth,SignalHeight);
        signalSurface=Rect("FilmSignalSurface",0,0,SignalWidth,SignalHeight);buildParent=signalSurface;
        Fill("Background",0,0,SignalWidth,SignalHeight,Background);
        Fill("ClassicTitleBar",0,0,SignalWidth,34,new Color32(190,214,233,255));
        Label("Brand","Film Metrology Monitor — 산화막 두께 검사",17,2,890,30,17,Ink);
        Button("WindowClose","×",1037,3,33,27);
        signalSurface.Find("WindowClose").GetComponent<Image>().color=new Color32(184,88,68,255);
        signalSurface.Find("WindowClose").GetComponentInChildren<Text>().color=Color.white;
        Fill("MenuBar",0,35,SignalWidth,28,Background);Fill("MenuRule",0,62,SignalWidth,1,LineColor);
        Label("WindowMenus","파일(F)     보기(V)     도움말(H)",18,35,700,26,13,Ink);
        Button("TabOverview","검사 현황",96,253,145,33);Button("TabHistory","검사 이력",246,253,145,33);Button("TabCriteria","검사 기준",396,253,145,33);
        title=Label("Title","산화막 두께 검사",96,83,670,44,30,Ink);
        meta=Label("Metadata","",96,133,800,26,14,Muted);
        state=Label("State","",852,119,200,30,16,Blue,TextAnchor.MiddleRight);
        Label("Demo","SIMULATION / 실측 아님",780,85,270,28,13,Muted,TextAnchor.MiddleRight);
        summary=new Text[4];var names=new[]{"오늘 완료 검사","오늘 정상","오늘 NG","오늘 정상 비율"};
        for(int i=0;i<4;i++)
        {
            float x=96+i*242;Fill("StatBorder"+i,x,181,232,44,LineColor);Fill("StatPanel"+i,x+1,182,230,42,Panel);
            Label("StatName"+i,names[i],x+10,185,123,34,13,Muted);
            summary[i]=Label("StatValue"+i,"—",x+125,184,97,35,23,i==1||i==3?Green:i==2?Red:Ink,TextAnchor.MiddleRight);
        }
        todayLabel=Label("TodayNote","",96,229,956,19,11,Muted);
        liveRoot=Group("LiveView");buildParent=(RectTransform)liveRoot.transform;
        
        selectedId=Label("SelectedId","",96,292,640,23,13,Blue);
        selectedTime=Label("SelectedTime","",750,290,300,27,12,Muted,TextAnchor.MiddleRight);
        BoxPanel("WaferPanel",96,320,290,272,"측정 위치 · 3 POINT");
        var map=Rect("WaferMap",130,367,222,155);waferPlot=map.gameObject.AddComponent<FilmDashboardGraphic>();waferPlot.owner=this;waferPlot.wafer=true;waferPlot.raycastTarget=false;
        sites=new Text[3];for(int i=0;i<3;i++){Fill("PointPanel"+i,108+i*90,532,85,47,Deep);sites[i]=Label("Point"+i,"",111+i*90,534,79,43,17,Ink,TextAnchor.MiddleCenter,true);}
        BoxPanel("ResultPanel",398,320,370,272,"검사 결과");
        Label("AverageCaption","AVERAGE THICKNESS / 평균 두께",413,368,340,23,12,Muted);
        average=Label("Mean","",414,397,338,65,52,Ink,TextAnchor.MiddleCenter);
        Fill("SpecPanel",413,467,340,52,Deep);spec=Label("Specification","",426,471,315,44,15,Muted);
        judgementBorder=Fill("VerdictBorder",413,530,340,43,LineColor);
        judgementPanel=Fill("VerdictBackground",415,532,336,39,Soft);judgement=Label("Verdict","",426,531,205,40,25,Ink,TextAnchor.MiddleLeft,true);
        judgementRule=Label("VerdictRule","",631,534,110,34,12,Muted,TextAnchor.MiddleRight);
        BoxPanel("LotPanel",780,320,272,272,"LOT 상태");
        lotPanel=Fill("LotStateBackground",794,375,244,55,Soft);lot=Label("LotState","",803,377,226,50,22,Ink,TextAnchor.MiddleCenter,true);
        lotNote=Label("LotNote","",794,438,244,39,13,Muted);
        Fill("LotDivider",794,485,244,1,LineColor);Label("RangeTitle","측정값 요약",794,493,244,25,16,Ink,TextAnchor.MiddleLeft,true);
        limits=Label("MeasuredRange","",794,523,244,48,14,Muted);
        BoxPanel("GraphPanel",96,605,956,137,"지점별 두께 (nm)");
        graphScale=Label("GraphScale","",510,611,526,27,12,Muted,TextAnchor.MiddleRight);
        var plot=Rect("ThicknessTrend",137,654,875,61);trend=plot.gameObject.AddComponent<FilmDashboardGraphic>();trend.owner=this;trend.raycastTarget=false;
        plotValues=new Text[3];for(int i=0;i<3;i++){float x=211+i*350;plotValues[i]=Label("PlotValue"+i,"",x-24,646,74,20,11,Ink,TextAnchor.MiddleCenter);Label("PlotPoint"+i,"P"+(i+1),x-24,719,74,17,11,Muted,TextAnchor.MiddleCenter);}
        reason=Label("Reason","",98,749,950,23,15,Ink);action=Label("Disposition","",98,774,950,22,13,Muted);
        Fill("RecentPanel",96,804,956,56,Panel);Label("RecentTitle","최근 검사",108,807,100,24,14,Ink,TextAnchor.MiddleLeft,true);
        recentNote=Label("RecentEmpty","검사 완료 후 기록 표시",221,809,700,23,12,Muted);
        recentCells=new Text[3];for(int i=0;i<3;i++){Button("RecentRow"+i,"",218+i*275,810,265,37);recentCells[i]=Label("Recent"+i,"",228+i*275,811,245,35,12,Ink);}
        measurementNote=Label("MeasurementSource","원인·보정안은 별도 분석 화면에서 검토",96,867,956,19,11,Muted);
        historyRoot=Group("HistoryView");buildParent=(RectTransform)historyRoot.transform;
        BoxPanel("HistoryPanel",96,258,956,597,"검사 이력");historyTitle=Label("HistoryTitle","",109,304,410,30,20,Ink,TextAnchor.MiddleLeft,true);
        Button("PreviousDay","이전 날짜",531,305,103,30);Button("NextDay","다음 날짜",642,305,103,30);Button("HistoryFilter","전체",753,305,88,30);Button("PreviousPage","이전",849,305,89,30);Button("NextPage","다음",946,305,89,30);
        var columns=new[]{110f,252,423,558,645,742,840,938};var widths=new[]{136f,165,129,81,91,92,92,91};var heads=new[]{"검사 ID","완료 시간","LOT","결과","평균 nm","P1","P2","P3"};
        Fill("HistoryHeader",108,351,930,30,Soft);for(int i=0;i<8;i++)Label("Column"+i,heads[i],columns[i],351,widths[i],30,13,Muted);
        historyCells=new Text[48];historyBackgrounds=new Image[6];
        for(int row=0;row<6;row++){historyBackgrounds[row]=Fill("HistoryRow"+row,108,387+row*54,930,51,Panel);historyBackgrounds[row].raycastTarget=true;historyBackgrounds[row].gameObject.AddComponent<Button>().targetGraphic=historyBackgrounds[row];for(int col=0;col<8;col++)historyCells[row*8+col]=Label("Cell"+row+"_"+col,"",columns[col],389+row*54,widths[col],47,col==0?13:14,Ink);}
        historyPage=Label("HistoryPage","",110,728,918,29,13,Muted);historyDetail=Label("HistoryDetail","",110,766,918,72,14,Ink);
        criteriaRoot=Group("CriteriaView");buildParent=(RectTransform)criteriaRoot.transform;
        BoxPanel("CriteriaPanel",96,258,956,597,"현재 검사 기준");criteriaText=Label("Criteria","",117,322,908,490,23,Ink);
        buildParent=signalSurface;archiveStatus=Label("HistoryStorageStatus","",96,882,956,17,11,Muted);
        // Use the same centered desktop window in both the monitor and screen overlay.
        foreach(Transform item in signalSurface)
        {
            if(item.gameObject==historyRoot||item.gameObject==criteriaRoot)
                foreach(RectTransform child in item){child.anchoredPosition+=new Vector2(0,-30);if(child.name=="HistoryPanelBorder"||child.name=="HistoryPanel"||child.name=="CriteriaPanelBorder"||child.name=="CriteriaPanel")child.sizeDelta-=new Vector2(0,30);}
            if(item.gameObject==liveRoot||item.gameObject==historyRoot||item.gameObject==criteriaRoot)
                foreach(RectTransform child in item)ExpandClassicContent(child);
            else ExpandClassicContent((RectTransform)item);
        }
        historyDay=DateTime.Today;view=page=filter=0;ApplyFont();BindButtons();Refresh();
    }
    static void ExpandClassicContent(RectTransform item)
    {
        if(item.anchoredPosition.x<90||item.name=="WindowClose")return;
        var p=item.anchoredPosition;p.x=24+(p.x-96)*1.075f;item.anchoredPosition=p;
        item.sizeDelta=new Vector2(item.sizeDelta.x*1.075f,item.sizeDelta.y);
    }
    void OpenRecent(int index)
    {
        var rows=FilmInspectionHistory.Instance.OnDay(DateTime.Today);if(index>=rows.Count)return;
        historyDay=DateTime.Today;selectedHistory=rows[index].inspection_id;filter=page=0;SetView(1);
    }
    void RefreshSignalDetails(FilmInspectionHistory store,FilmInspectionHistory.Entry saved)
    {
        // Update stored layouts too; the enlarged monitor mirrors this Text every frame.
        var resultHeading=signalSurface?signalSurface.Find("LiveView/ResultPanelTitle"):null;
        if(resultHeading&&resultHeading.TryGetComponent<Text>(out var heading))heading.text="검사 결과";
        if(!selectedId)return;
        selectedId.text=saved!=null?saved.inspection_id:string.IsNullOrEmpty(cycle.InspectionId)?"INSP — / 검사 준비":cycle.InspectionId;
        selectedTime.text=(saved!=null?"완료 "+saved.Time.LocalDateTime.ToString("HH:mm:ss"):"측정 결과 대기")+" / "+cycle.lotId;
        lotNote.text=cycle.lotHeld?"다음 공정 이동 차단 · 검토 필요":cycle.CanProceed?"두께 통과 · 후속 공정 조건 확인":"측정 결과 수신 후 상태 표시";
        measurementNote.text=cycle.InspectionCsv!=null?"Jetson CSV 환산값 · 3점 동일 / 전기특성·원인·보정안 별도 분석":"합성 시연 / 전기특성·원인·보정안 별도 분석";
        var records=store.OnDay(DateTime.Today);recentNote.gameObject.SetActive(records.Count==0);
        for(int i=0;i<recentCells.Length;i++)
        {
            var t=recentCells[i];var b=liveRoot.transform.Find("RecentRow"+i);if(b)b.gameObject.SetActive(i<records.Count);
            t.gameObject.SetActive(i<records.Count);if(i>=records.Count)continue;
            var e=records[i];t.text=e.Time.LocalDateTime.ToString("HH:mm")+"  "+e.Mean.ToString("F1")+" nm  "+(e.verdict=="PASS"?"PASS":"NG");t.color=e.verdict=="PASS"?Green:Red;
        }
        for(int i=0;i<3;i++)plotValues[i].text=FilmInspectionRecipe.Finite(cycle.readings[i])?cycle.readings[i].ToString("F1"):"—";
        foreach(var b in signalSurface.GetComponentsInChildren<Button>(true))if(b.name.StartsWith("Tab"))
        {bool active=b.name==(view==0?"TabOverview":view==1?"TabHistory":"TabCriteria");b.GetComponent<Image>().color=active?Color.white:Soft;b.GetComponentInChildren<Text>().color=active?Blue:Muted;}
    }
    public void SetSignalMonitorOpen(bool open)
    {
        if(!signalSurface)return;monitorOpen=open;
        if(open&&!screenOverlay)
        {
            var go=new GameObject("FILM_SIGNAL_SCREEN_OVERLAY",typeof(RectTransform),typeof(Canvas));screenOverlay=go.GetComponent<Canvas>();screenOverlay.renderMode=RenderMode.ScreenSpaceOverlay;screenOverlay.sortingOrder=29990;
            screenSurface=Instantiate(signalSurface,go.transform,false);screenSurface.anchorMin=screenSurface.anchorMax=screenSurface.pivot=new Vector2(.5f,.5f);
            var from=signalSurface.GetComponentsInChildren<Transform>(true);var to=screenSurface.GetComponentsInChildren<Transform>(true);
            for(int i=0;i<from.Length;i++){overlayTransforms.Add(new KeyValuePair<Transform,Transform>(from[i],to[i]));var a=from[i].GetComponent<Graphic>();var b=to[i].GetComponent<Graphic>();if(a&&b)overlayGraphics.Add(new KeyValuePair<Graphic,Graphic>(a,b));}
        }
        SyncSignalOverlay();
    }
    void SyncSignalOverlay()
    {
        if(!screenOverlay)return;screenOverlay.enabled=monitorOpen&&isActiveAndEnabled;if(!monitorOpen)return;
        float scale=Mathf.Max(.1f,Mathf.Min((Screen.width-24)/SignalWidth,(Screen.height-36)/SignalHeight));screenSurface.localScale=Vector3.one*scale;screenSurface.anchoredPosition=new Vector2(0,-8);
        screenArea=new Rect((Screen.width-SignalWidth*scale)/2,(Screen.height-SignalHeight*scale)/2+8,SignalWidth*scale,SignalHeight*scale);
        foreach(var pair in overlayTransforms)if(pair.Key&&pair.Value&&pair.Key!=signalSurface)pair.Value.gameObject.SetActive(pair.Key.gameObject.activeSelf);
        foreach(var pair in overlayGraphics)
        {
            if(!pair.Key||!pair.Value)continue;pair.Value.color=pair.Key.color;pair.Value.enabled=pair.Key.enabled;
            if(pair.Key is Text a&&pair.Value is Text b){b.text=a.text;b.fontSize=a.fontSize;b.fontStyle=a.fontStyle;}
            if(pair.Value is FilmDashboardGraphic plot)plot.SetVerticesDirty();
        }
    }
    void LateUpdate(){SyncSignalOverlay();}
    void OnGUI()
    {
        if(!monitorOpen||!screenOverlay)return;
        // Direct overlay UI bypasses HDRP exposure and tone mapping, as in the AOI screen.
        var previous=GUI.matrix;int previousDepth=GUI.depth;GUI.matrix=Matrix4x4.identity;GUI.depth=-100;

        var ev=Event.current;
        if(ev.type==EventType.MouseDown&&ev.button==0&&screenArea.Contains(ev.mousePosition))
        {
            Vector2 local=(ev.mousePosition-screenArea.position)/(screenArea.width/SignalWidth);
            foreach(var button in signalSurface.GetComponentsInChildren<Button>(false))
            {
                var rect=(RectTransform)button.transform;Vector3 pos=signalSurface.InverseTransformPoint(rect.TransformPoint(new Vector3(rect.rect.xMin,rect.rect.yMax,0)));
                if(button.interactable&&new UnityEngine.Rect(pos.x,-pos.y,rect.rect.width,rect.rect.height).Contains(local)){button.onClick.Invoke();ev.Use();break;}
            }
        }
        GUI.matrix=previous;GUI.depth=previousDepth;
    }
    void RemoveSignalOverlay()
    {
        if(screenOverlay){if(Application.isPlaying)Destroy(screenOverlay.gameObject);else DestroyImmediate(screenOverlay.gameObject);}
        screenOverlay=null;screenSurface=null;overlayTransforms.Clear();overlayGraphics.Clear();
    }
    void OnDisable(){monitorOpen=false;if(screenOverlay)screenOverlay.enabled=false;}
    void OnDestroy(){RemoveSignalOverlay();}
}
