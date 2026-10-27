using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UI;

[ExecuteAlways]
public partial class FilmInspectionDashboard : MonoBehaviour
{
    public EllipsometerCycle cycle;
    public Text title,meta,state,average,spec,judgement,judgementRule,reason,lot,action,limits,graphScale;
    public Text[] sites;
    public Image judgementPanel,lotPanel;
    public FilmDashboardGraphic waferPlot,trend;
    [SerializeField] Text[] summary,historyCells;
    [SerializeField] Text todayLabel,archiveStatus,historyTitle,historyDetail,historyPage,criteriaText;
    [SerializeField] GameObject liveRoot,historyRoot,criteriaRoot;
    [SerializeField] Image[] historyBackgrounds;
    public static readonly Color Ink=new Color32(37,42,40,255),Muted=new Color32(104,115,112,255),Blue=new Color32(45,94,136,255);
    public static readonly Color Panel=new Color32(250,250,246,255),Soft=new Color32(233,237,230,255),Green=new Color32(36,114,53,255),Red=new Color32(183,40,36,255),Amber=new Color32(147,101,34,255);
    Font runtimeFont;
    RectTransform buildParent;
    DateTime historyDay;
    List<FilmInspectionHistory.Entry> visibleRecords=new List<FilmInspectionHistory.Entry>();
    int view,page,filter;
    string selectedHistory;
    float nextRefresh;
    public int View=>view;
    public Font DisplayFont=>runtimeFont;
    public string TodaySummary=>summary==null?"":string.Join(" | ",summary.Select(t=>t?t.text:""));
    void OnEnable(){ApplyFont();historyDay=DateTime.Today;if(cycle&&cycle.monitor&&!transform.Find("FilmSignalSurface/ClassicTitleBar"))Build(cycle);else{BindButtons();if(cycle)Refresh();}}
    void Update(){if(Application.isPlaying&&Time.unscaledTime>=nextRefresh){nextRefresh=Time.unscaledTime+1;Refresh();}}
    void ApplyFont()
    {
        if(!runtimeFont)runtimeFont=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Noto Sans CJK KR","Arial"},28);
        if(!runtimeFont)runtimeFont=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        foreach(var text in GetComponentsInChildren<Text>(true))text.font=runtimeFont;
    }
    RectTransform Rect(string name,float x,float y,float w,float h)
    {
        var obj=new GameObject(name,typeof(RectTransform));obj.transform.SetParent(buildParent?buildParent:transform,false);
        var r=obj.GetComponent<RectTransform>();r.anchorMin=r.anchorMax=new Vector2(0,1);r.pivot=new Vector2(0,1);r.anchoredPosition=new Vector2(x,-y);r.sizeDelta=new Vector2(w,h);return r;
    }
    Image Fill(string name,float x,float y,float w,float h,Color color)
    {var r=Rect(name,x,y,w,h);var im=r.gameObject.AddComponent<Image>();im.color=color;im.raycastTarget=false;return im;}
    Text Label(string name,string value,float x,float y,float w,float h,int size,Color color,TextAnchor anchor=TextAnchor.MiddleLeft,bool bold=false)
    {
        var r=Rect(name,x,y,w,h);var text=r.gameObject.AddComponent<Text>();text.text=value;text.font=runtimeFont;text.fontSize=size;text.color=color;text.alignment=anchor;text.fontStyle=bold?FontStyle.Bold:FontStyle.Normal;text.raycastTarget=false;text.supportRichText=false;
        text.horizontalOverflow=HorizontalWrapMode.Wrap;text.verticalOverflow=VerticalWrapMode.Truncate;return text;
    }
    void Button(string name,string label,float x,float y,float w,float h)
    {
        var im=Fill(name,x,y,w,h,Soft);im.raycastTarget=true;im.gameObject.AddComponent<Button>().targetGraphic=im;
        var parent=buildParent;buildParent=im.rectTransform;Label("Label",label,5,0,w-10,h,17,Blue,TextAnchor.MiddleCenter,true);buildParent=parent;
    }
    GameObject Group(string name){buildParent=signalSurface;return Rect(name,0,0,SignalWidth,SignalHeight).gameObject;}
    void BindButtons()
    {
        foreach(var b in GetComponentsInChildren<Button>(true))
        {
            b.onClick.RemoveAllListeners();string name=b.name;
            if(name=="WindowClose")b.onClick.AddListener(()=>cycle.ZoomMonitor());
            else if(name=="TabOverview")b.onClick.AddListener(()=>SetView(0));else if(name=="TabHistory")b.onClick.AddListener(()=>SetView(1));else if(name=="TabCriteria")b.onClick.AddListener(()=>SetView(2));
            else if(name=="PreviousDay")b.onClick.AddListener(()=>ShiftDay(1));else if(name=="NextDay")b.onClick.AddListener(()=>ShiftDay(-1));
            else if(name=="PreviousPage")b.onClick.AddListener(()=>{page=Math.Max(0,page-1);Refresh();});else if(name=="NextPage")b.onClick.AddListener(()=>{page++;Refresh();});
            else if(name=="HistoryFilter")b.onClick.AddListener(()=>{filter=(filter+1)%3;page=0;Refresh();});
            else if(name.StartsWith("RecentRow")&&int.TryParse(name.Substring(9),out int recent)){int index=recent;b.onClick.AddListener(()=>OpenRecent(index));}
            else if(name.StartsWith("HistoryRow")&&int.TryParse(name.Substring(10),out int index)){int row=index;b.onClick.AddListener(()=>SelectHistory(row));}
        }
    }
    public void SetView(int value){view=Mathf.Clamp(value,0,2);Refresh();}
    public void ShiftDay(int delta){var days=FilmInspectionHistory.Instance.Days();int i=days.IndexOf(historyDay.Date);if(i<0)i=0;historyDay=days[Mathf.Clamp(i+delta,0,days.Count-1)];page=0;selectedHistory=null;Refresh();}
    void SelectHistory(int row){int i=page*6+row;if(i<visibleRecords.Count){selectedHistory=visibleRecords[i].inspection_id;Refresh();}}
    public bool HandlePointer(Vector2 pixel,Camera camera)
    {
        foreach(var button in GetComponentsInChildren<Button>(false))
        {
            if(!button.interactable)continue;var corners=new Vector3[4];((RectTransform)button.transform).GetWorldCorners(corners);
            var a=RectTransformUtility.WorldToScreenPoint(camera,corners[0]);var b=RectTransformUtility.WorldToScreenPoint(camera,corners[2]);
            if(new UnityEngine.Rect(Vector2.Min(a,b),Vector2.Max(a,b)-Vector2.Min(a,b)).Contains(pixel)){button.onClick.Invoke();return true;}
        }
        return false;
    }
    public void Refresh()
    {
        if(!cycle||!cycle.recipe||!title)return;
        var r=cycle.recipe;bool hasValue=FilmInspectionRecipe.Finite(cycle.Mean),fail=cycle.verdict=="FAIL",pass=cycle.verdict=="PASS";
        var store=FilmInspectionHistory.Instance;var saved=store.Find(cycle.InspectionId);
        meta.text="ELLIP-01 | "+cycle.lotId+" | "+(saved!=null?saved.ShortId+" · "+saved.Time.LocalDateTime.ToString("HH:mm:ss"):"검사 ID "+(string.IsNullOrEmpty(cycle.InspectionId)?"대기":cycle.InspectionId.Substring(0,8).ToUpperInvariant()));
        state.text=cycle.Running?(cycle.activePoint>=0?"측정 "+(cycle.activePoint+1)+" / 3":"웨이퍼 이송 중"):pass||fail?"판정 완료":"검사 준비";
        average.text=hasValue?cycle.Mean.ToString("F1")+" nm":"— nm";average.color=fail?Red:pass?Green:Ink;
        spec.text="목표 두께 "+r.targetNm.ToString("F1")+" nm\n허용 범위 "+r.lowerNm.ToString("F1")+"–"+r.upperNm.ToString("F1")+" nm";
        judgement.text=fail?"FAIL":pass?"PASS":cycle.Running?"측정 중":"검사 대기";judgement.color=fail?Red:pass?Green:Ink;judgementRule.text=fail?"규격 이탈":pass?"3점 모두 통과":"3점 검사";
        if(judgementBorder)judgementBorder.color=fail?Red:pass?Green:LineColor;
        judgementPanel.color=fail?new Color32(247,229,226,255):pass?new Color32(229,240,226,255):Soft;
        if(cycle.InspectionCsv!=null)judgementRule.text="CSV 환산 · 3점 동일";
        lot.fontSize=22;lot.text=cycle.lotHeld?"HOLD · 진행 보류":cycle.CanProceed?"진행 가능":cycle.Running?"검사 중":"검사 대기";lot.color=cycle.lotHeld?Amber:cycle.CanProceed?Green:Ink;lotPanel.color=cycle.lotHeld?new Color32(251,243,217,255):cycle.CanProceed?new Color32(229,240,226,255):Soft;
        float min=float.PositiveInfinity,max=float.NegativeInfinity;for(int i=0;i<3;i++){float v=cycle.readings[i];sites[i].text="P"+(i+1)+" "+(FilmInspectionRecipe.Finite(v)?v.ToString("F1"):"—");sites[i].color=FilmInspectionRecipe.Finite(v)?r.InRange(v)?Green:Red:Muted;if(FilmInspectionRecipe.Finite(v)){min=Mathf.Min(min,v);max=Mathf.Max(max,v);}}
        limits.text=FilmInspectionRecipe.Finite(min)?"최소  "+min.ToString("F1")+" nm\n최대  "+max.ToString("F1")+" nm":"측정값 대기";
        graphScale.text="하한 "+r.lowerNm.ToString("F1")+" / 목표 "+r.targetNm.ToString("F1")+" / 상한 "+r.upperNm.ToString("F1");
        reason.text="사유: "+cycle.inspectionReason;reason.color=fail?Red:Ink;
        action.text=!string.IsNullOrEmpty(cycle.notice)?cycle.notice:cycle.lotHeld?(pass?"재측정 PASS · 검토 승인 전까지 HOLD 유지":"재측정·검토 대기 · 다음 공정 이동 금지"):cycle.CanProceed?"다음 공정 진행 가능 · 물류 명령 대기":"검사 후 판정 · 자동 재작업 없음";
        if(waferPlot)waferPlot.SetVerticesDirty();if(trend)trend.SetVerticesDirty();
        if(summary==null||summary.Length!=4)return;
        var stats=store.ForDay(DateTime.Today);var values=new[]{stats.total+" 건",stats.pass+" 건",stats.ng+" 건",stats.total==0?"—":stats.normalPercent.ToString("F1")+" %"};for(int i=0;i<4;i++)summary[i].text=store.Readable?values[i]:"—";
        todayLabel.text="오늘 "+DateTime.Today.ToString("yyyy.MM.dd")+" · 완료된 두께 검사 ID 기준 · 재검사 포함 · 정상 비율 = 정상 / 전체 ×100";
        archiveStatus.text=string.IsNullOrEmpty(store.LastError)?cycle.InspectionCsv!=null?cycle.InspectionCsv.Label+" · Jetson CSV 시험값 · 실제 계측/팀 DB 아님":"합성 시연 · 검사 기록 로컬 보관 · 실제 계측/팀 DB 아님":store.LastError;archiveStatus.color=string.IsNullOrEmpty(store.LastError)?Muted:Red;
        liveRoot.SetActive(view==0);historyRoot.SetActive(view==1);criteriaRoot.SetActive(view==2);
        criteriaText.text=$"목표 두께     {r.targetNm:F1} nm\n허용 하한     {r.lowerNm:F1} nm\n허용 상한     {r.upperNm:F1} nm\n\n3개 지점이 모두 허용 범위 안이면 PASS\n한 지점이라도 벗어나면 두께 FAIL / NG\n\n프로젝트 시연 기준 · 양산 승인 규격 아님\n전기특성/원인·보정안은 별도 분석창에서 확인";
        RefreshSignalDetails(store,saved);if(view==1)RefreshHistory(store);
    }
    void RefreshHistory(FilmInspectionHistory store)
    {
        if(historyDay==default)historyDay=DateTime.Today;
        visibleRecords=store.OnDay(historyDay).Where(e=>filter==0||e.verdict==(filter==1?"PASS":"FAIL")).ToList();page=Mathf.Clamp(page,0,Math.Max(0,(visibleRecords.Count-1)/6));historyTitle.text="검사 이력 · "+historyDay.ToString("yyyy.MM.dd");
        foreach(var b in historyRoot.GetComponentsInChildren<Button>(true))if(b.name=="HistoryFilter")b.GetComponentInChildren<Text>().text=filter==0?"전체":filter==1?"정상":"NG";
        for(int row=0;row<6;row++)
        {
            int i=page*6+row;var e=i<visibleRecords.Count?visibleRecords[i]:null;historyBackgrounds[row].gameObject.SetActive(e!=null);historyBackgrounds[row].color=e!=null&&e.inspection_id==selectedHistory?Soft:Panel;
            string[] values=e==null?new string[8]:new[]{e.ShortId,e.Time.LocalDateTime.ToString("HH:mm:ss")+(e.remeasurement?" · 재검":""),e.lot_id,e.verdict=="PASS"?"PASS":"NG",e.Mean.ToString("F1"),e.readings[0].ToString("F1"),e.readings[1].ToString("F1"),e.readings[2].ToString("F1")};
            for(int col=0;col<8;col++){var t=historyCells[row*8+col];t.text=values[col]??"";t.color=col==3&&e!=null?(e.verdict=="PASS"?Green:Red):Ink;}
        }
        historyPage.text=visibleRecords.Count==0?"해당 날짜/조건의 검사 기록 없음":$"{visibleRecords.Count}건 · {page+1} / {Math.Max(1,(visibleRecords.Count+5)/6)} 페이지 · 행 선택 시 전체 ID와 기준 표시";
        var selected=visibleRecords.Find(e=>e.inspection_id==selectedHistory);historyDetail.text=selected==null?"정상/NG는 두께 판정입니다. 재검사 기록은 이전 기록을 대체하지 않습니다.":selected.inspection_id+" | "+selected.Time.LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss")+"\n목표 "+selected.target.ToString("F1")+" / 허용 "+selected.lower.ToString("F1")+"–"+selected.upper.ToString("F1")+" nm | "+selected.scenario;
    }
    public static void Install(EllipsometerCycle source)
    {
        var panel=source.monitor.rectTransform.parent.GetComponent<RectTransform>();var existing=panel.GetComponent<FilmInspectionDashboard>();
        if(existing){source.dashboard=existing;existing.Build(source);return;}panel.localScale*=.5f;source.monitor.enabled=false;var dashboard=panel.gameObject.AddComponent<FilmInspectionDashboard>();source.dashboard=dashboard;dashboard.Build(source);
    }
}
