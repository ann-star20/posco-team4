using System;
using System.Linq;
using UnityEngine;
using UnityEngine.UI;
using System.Collections.Generic;

[ExecuteAlways]
public class IonImplantDashboard : MonoBehaviour
{
    public IonImplantCycle cycle;
    public Text metadata,state,doseText,recipeText,chamberText,disposition,phaseText;
    public Image progressFill,statePanel,beamIndicator;
    public Text[] stepLabels;
    public string recipeId="";
    public double doseLower=IonDoseAssessment.MlLower,doseUpper=IonDoseAssessment.MlUpper;
    [SerializeField] Text[] daily,conditions,machineValues,historyCells;
    [SerializeField] Text statsNote,verdictText,verdictNote,sourceNote,historyNote,criteria;
    [SerializeField] Image verdictPanel;
    [SerializeField] GameObject[] views;
    Font font;Transform buildParent;Canvas screenOverlay;RectTransform screenSurface;Rect screenArea;
    readonly List<KeyValuePair<RectTransform,RectTransform>> overlayRects=new List<KeyValuePair<RectTransform,RectTransform>>();
    readonly List<KeyValuePair<Graphic,Graphic>> overlayGraphics=new List<KeyValuePair<Graphic,Graphic>>();
    bool windowOpen;int view,seenRuns;float nextRefresh;
    static readonly string Session=Guid.NewGuid().ToString("N");
    const float Width=960,Height=840;
    public static readonly Color Ink=new Color32(32,37,32,255),Muted=new Color32(100,106,101,255),Green=new Color32(24,115,41,255),Red=new Color32(179,38,34,255);
    static readonly Color Face=new Color32(236,235,231,255),Paper=new Color32(249,249,245,255),Line=new Color32(172,179,173,255),Blue=new Color32(40,87,119,255),Amber=new Color32(128,88,19,255);
    public int View=>view;
    public string DoseVerdict=>!cycle?"미판정":cycle.LotBlocked?"보류":cycle.Paused?"일시 정지":!cycle.Running&&!cycle.completed&&!cycle.failed?"검사 대기":IonDoseAssessment.Evaluate(cycle.dose,doseLower,doseUpper,cycle.completed,cycle.failed);
    void OnEnable()
    {
        ApplyFont();seenRuns=cycle?cycle.completedRuns:0;
        if(cycle&&cycle.monitor&&!transform.Find("IonClassicSurface"))Build(cycle);else{BindButtons();Refresh();}
    }
    void ApplyFont()
    {
        if(!font)font=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Tahoma","Arial"},28);
        if(!font)font=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        foreach(var t in GetComponentsInChildren<Text>(true))t.font=font;
    }
    RectTransform Box(string name,float x,float y,float w,float h)
    {
        var obj=new GameObject(name,typeof(RectTransform));obj.transform.SetParent(buildParent?buildParent:transform,false);
        var r=obj.GetComponent<RectTransform>();r.anchorMin=r.anchorMax=r.pivot=new Vector2(0,1);r.anchoredPosition=new Vector2(x,-y);r.sizeDelta=new Vector2(w,h);return r;
    }
    Image Fill(string name,float x,float y,float w,float h,Color color)
    {var im=Box(name,x,y,w,h).gameObject.AddComponent<Image>();im.color=color;im.raycastTarget=false;return im;}
    Text Label(string name,string value,float x,float y,float w,float h,int size,Color color,TextAnchor align=TextAnchor.MiddleLeft)
    {
        var t=Box(name,x,y,w,h).gameObject.AddComponent<Text>();t.font=font;t.text=value;t.fontSize=size;t.color=color;t.raycastTarget=false;t.alignment=align;t.supportRichText=false;t.horizontalOverflow=HorizontalWrapMode.Wrap;t.verticalOverflow=VerticalWrapMode.Truncate;return t;
    }
    void Well(string name,float x,float y,float w,float h,Color color)
    {Fill(name+"Border",x,y,w,h,Line);Fill(name,x+1,y+1,w-2,h-2,color);}
    void Group(string name,string title,float x,float y,float w,float h)
    {Well(name,x,y,w,h,Paper);Fill(name+"LegendBacking",x+7,y-12,Mathf.Min(w-20,title.Length*16+10),26,Paper);Label(name+"Title",title,x+10,y-12,w-20,26,16,Ink);}
    void Button(string name,string text,float x,float y,float w,float h)
    {
        var border=Fill(name,x,y,w,h,Line);border.raycastTarget=true;var parent=buildParent;buildParent=border.transform;
        Fill("Face",1,1,w-2,h-2,Face);Fill("Highlight",1,1,w-2,1,Color.white);Label("Label",text,3,1,w-6,h-2,15,Ink,TextAnchor.MiddleCenter);buildParent=parent;
        border.gameObject.AddComponent<Button>().targetGraphic=border;
    }
    public void Build(IonImplantCycle source)
    {
        if(!source||!source.monitor)throw new ArgumentException("Ion monitor missing");cycle=source;
        for(int i=transform.childCount-1;i>=0;i--){var child=transform.GetChild(i);if(child==source.monitor.transform)continue;DestroyImmediate(child.gameObject);}
        ApplyFont();((RectTransform)transform).sizeDelta=new Vector2(Width,Height);
        buildParent=transform;var surface=Box("IonClassicSurface",0,0,Width,Height);buildParent=surface;Well("Background",0,0,Width,Height,Face);
        for(int i=0;i<28;i++)Fill("TitleGradient"+i,1,1+i,Width-2,1,Color.Lerp(new Color32(221,236,248,255),new Color32(177,204,229,255),i/27f));
        Label("WindowTitle","Ion Implantation Monitor — 바디 이온주입 공정",13,2,800,25,17,Ink);Button("WindowClose","×",921,3,30,22);
        Label("Menu","파일(F)     보기(V)     도움말(H)",15,32,900,23,13,Muted);Label("Title","바디 이온주입 공정",20,61,650,37,29,Ink);
        Label("Source","SIMULATION · 실측 아님",709,70,230,23,13,Muted,TextAnchor.MiddleRight);metadata=Label("Metadata","",20,103,920,26,15,Muted);
        daily=new Text[4];string[] heads={"오늘 완료 공정","오늘 정상","오늘 불량","정상 비율"};
        for(int i=0;i<4;i++){float x=18+i*233;Well("Stat"+i,x,142,225,43,Paper);Label("StatTitle"+i,heads[i],x+9,147,112,32,13,Muted);daily[i]=Label("StatValue"+i,"—",x+110,145,104,35,23,i==2?Red:i>0?Green:Ink,TextAnchor.MiddleRight);}
        statsNote=Label("StatsNote","",20,189,920,23,12,Muted);
        Button("TabLive","공정 현황",22,218,120,29);Button("TabHistory","공정 이력",145,218,120,29);Button("TabRecipe","레시피",268,218,110,29);Well("Page",12,247,936,558,Paper);
        views=new GameObject[3];for(int i=0;i<3;i++){buildParent=surface;views[i]=Box(new[]{"LiveView","HistoryView","RecipeView"}[i],0,0,Width,Height).gameObject;}
        buildParent=views[0].transform;state=Label("State","",24,254,760,29,16,Blue);statePanel=Fill("StateMarker",918,263,8,8,Green);
        Group("Conditions","공정 조건",24,302,280,304);Group("DosePanel","누적 주입량",317,302,325,304);Group("MachinePanel","설비 상태",655,302,281,304);
        conditions=new Text[7];string[] names={"주입 이온","에너지","제어 모드","공정 종류","레시피 ID","주입량 허용 범위","목표 대비 편차"};
        for(int i=0;i<7;i++){float y=326+i*35;Label("ConditionTitle"+i,names[i],35,y,125,30,14,Muted);conditions[i]=Label("ConditionValue"+i,"",155,y,135,30,i==0?24:i==6?23:14,i==0?Blue:Ink,TextAnchor.MiddleRight);if(i<6)Fill("ConditionLine"+i,35,y+32,255,1,new Color32(216,220,212,255));}
        Well("DoseReading",330,325,299,91,Color.white);Label("DoseCaption","ACCUMULATED DOSE / 시뮬레이션",337,330,285,22,12,Muted,TextAnchor.MiddleCenter);
        doseText=Label("Dose","",336,352,286,43,36,Ink,TextAnchor.MiddleCenter);Label("DoseUnit","ions/cm²",337,392,285,20,14,Muted,TextAnchor.MiddleCenter);
        recipeText=Label("Recipe","",330,429,299,27,14,Ink);phaseText=Label("ProgressLabel","",330,466,299,24,14,Muted);
        Fill("ProgressTrack",330,495,299,8,new Color32(216,222,214,255));progressFill=Fill("Progress",330,495,0,8,new Color32(108,165,82,255));
        verdictPanel=Fill("VerdictPanel",330,521,299,43,new Color32(233,242,228,255));verdictText=Label("DoseVerdict","",335,522,289,41,27,Green,TextAnchor.MiddleCenter);verdictNote=Label("VerdictNote","",330,569,299,25,12,Muted,TextAnchor.MiddleCenter);
        chamberText=Label("ChamberStatus","",668,326,254,30,14,Green);machineValues=new Text[4];string[] machineNames={"챔버 압력","게이트","인터록","스테이지"};
        for(int i=0;i<4;i++){float y=369+i*39;Label("MachineTitle"+i,machineNames[i],668,y,100,30,14,Muted);machineValues[i]=Label("MachineValue"+i,"",771,y,152,30,14,Ink,TextAnchor.MiddleRight);}
        Label("MachineNote","설비 상태는 실제 센서값이 아닌\n시뮬레이션 계산값입니다.",668,539,254,48,12,Muted);
        Group("Sequence","공정 진행 순서",24,627,912,72);stepLabels=new Text[4];string[] steps={"01  로딩 · 정렬","02  진공 준비","03  이온주입","04  회수 · 완료"};
        for(int i=0;i<4;i++){Well("StepPanel"+i,35+i*224,646,216,42,Face);stepLabels[i]=Label("Step"+i,steps[i],44+i*224,651,199,32,16,Muted);}
        Group("DispositionPanel","전기특성 · 원인 분석 · 보정안",24,719,912,82);disposition=Label("Disposition","",38,733,878,64,12,Ink);
        buildParent=views[1].transform;Label("HistoryTitle","공정 이력 · 로컬 시뮬레이션",27,268,880,35,22,Ink);
        string[] columns={"공정 ID","LOT","완료 시각","누적 주입량","판정"};float[] xs={31,187,365,529,758};float[] ws={149,170,157,223,163};
        for(int i=0;i<5;i++)Label("HistoryColumn"+i,columns[i],xs[i],318,ws[i],30,15,Muted);
        historyCells=new Text[30];for(int row=0;row<6;row++)for(int col=0;col<5;col++)historyCells[row*5+col]=Label("HistoryCell"+row+"_"+col,"",xs[col],361+row*54,ws[col],47,14,Ink);
        historyNote=Label("HistoryNote","",29,709,886,67,15,Muted);
        buildParent=views[2].transform;Label("RecipeTitle","시연 레시피 · 현재 설정",29,269,885,35,22,Ink);criteria=Label("RecipeDetails","",34,323,876,423,21,Ink);
        buildParent=surface;sourceNote=Label("Footer","",19,812,923,21,12,Muted);source.monitor.enabled=false;buildParent=null;BindButtons();Refresh();
    }
    void BindButtons()
    {
        foreach(var b in GetComponentsInChildren<Button>(true)){b.onClick.RemoveAllListeners();if(b.name=="TabLive")b.onClick.AddListener(()=>SetView(0));if(b.name=="TabHistory")b.onClick.AddListener(()=>SetView(1));if(b.name=="TabRecipe")b.onClick.AddListener(()=>SetView(2));if(b.name=="WindowClose")b.onClick.AddListener(()=>{if(windowOpen)ToggleWindow();});}
    }
    public void SetView(int value){view=Mathf.Clamp(value,0,2);Refresh();}
    public void Refresh()
    {
        if(!cycle||!state||daily==null||conditions==null)return;
        bool hold=cycle.LotBlocked,fault=cycle.failed;string result=DoseVerdict;bool ok=result=="OK",ng=result=="FAIL";
        metadata.text="IMP-01  |  "+cycle.incomingLotId+" / WAFER 13  |  BODY IMPLANT";
        state.text=fault?"STOPPED · 인터록 정지":hold?"LOT HOLD · 진행 보류":cycle.Paused?"PAUSED · 일시 정지":cycle.completed?"공정 완료":cycle.Running?"공정 진행 중":"시작 대기";state.color=hold||fault?Amber:Blue;statePanel.color=hold||fault?Amber:Green;
        doseText.text=IonDoseAssessment.Finite(cycle.dose)?cycle.dose.ToString("0.00E+00"):"—";doseText.color=ng?Red:ok?Green:Ink;
        recipeText.text="목표 주입량   "+cycle.targetDose.ToString("0.00E+00")+" ions/cm²";progressFill.rectTransform.sizeDelta=new Vector2(299*Mathf.Clamp01(cycle.progress),8);phaseText.text="주입 진행률                         "+(cycle.progress*100).ToString("F0")+"%";
        var delta=IonDoseAssessment.DeviationPercent(cycle.dose,cycle.targetDose);string range=IonDoseAssessment.HasLimits(doseLower,doseUpper)?doseLower.ToString("0.000E+00")+"–"+doseUpper.ToString("0.000E+00"):"미설정";
        string[] cv={"B⁺",cycle.energyKeV.ToString("0.#")+" keV","시뮬레이션","바디 이온주입",string.IsNullOrWhiteSpace(recipeId)?"미등록":recipeId,range,cycle.dose==0||!IonDoseAssessment.Finite(delta)?"—":delta.ToString("+0.0;-0.0;0.0")+"%"};for(int i=0;i<7;i++)conditions[i].text=cv[i];conditions[5].fontSize=12;conditions[5].text=range.Replace("–","–\n");conditions[6].color=ng?Red:ok?Green:Muted;
        verdictText.text=result;verdictText.color=ng?Red:ok?Green:Muted;verdictPanel.color=ng?new Color32(247,229,226,255):ok?new Color32(233,242,228,255):Face;verdictNote.text=!IonDoseAssessment.HasLimits(doseLower,doseUpper)?"허용 범위 미설정 · 품질 판정 없음":"TCAD ML 기반 시연 기준 · ±5%";
        bool implant=cycle.status=="IMPLANT / SIMULATION";chamberText.text=fault?"인터록 정지":cycle.completed?"공정 종료 · 회수 완료":cycle.Running?"공정 실행 중":"대기 · 이송 준비";
        string[] mv={cycle.pressurePa.ToString("0.00E+00")+" Pa",cycle.AnyGateOpen?"열림":"닫힘",fault?"정지 발생":"모사 로직 감시",cycle.completed?"회수 완료":implant?"주입 위치":"이송 / 대기"};for(int i=0;i<4;i++)machineValues[i].text=mv[i];
        int phase=cycle.completed?4:cycle.progress>0?cycle.progress>=1?3:2:cycle.status.Contains("PUMP")||cycle.status.Contains("VACUUM")||cycle.status.Contains("TILT")?1:0;for(int i=0;i<4;i++)stepLabels[i].color=cycle.completed||cycle.Running&&i<=phase?Green:Muted;
        disposition.text=fault?"인터록 정지 · 원인 확인 후 재시작 필요":hold?"앞 공정 LOT HOLD · 검토 승인 전 이온주입 시작 불가":cycle.completed?"레시피 실행 완료 · 품질 PASS를 의미하지 않음\n전기특성 및 보정 효과는 TCAD 재검증 필요":cycle.Paused?"일시 정지 · 재개하면 현재 단계부터 진행":"설정 레시피 실행 상태 · 실측 및 품질 판정 아님";
        var gateway=GatewayInspectionBridge.Instance;
        if(cycle.completed&&cycle.InspectionCsv!=null)
        {
            disposition.fontSize=12;disposition.rectTransform.sizeDelta=new Vector2(878,64);
            var panel=disposition.transform.parent.Find("DispositionPanelBorder") as RectTransform;if(panel)panel.sizeDelta=new Vector2(912,82);
            var face=disposition.transform.parent.Find("DispositionPanel") as RectTransform;if(face)face.sizeDelta=new Vector2(910,80);
            var title=disposition.transform.parent.Find("DispositionPanelTitle");if(title)title.GetComponent<Text>().text="전기특성 · 원인 분석 · 보정안";
            var backing=disposition.transform.parent.Find("DispositionPanelLegendBacking") as RectTransform;if(backing)backing.sizeDelta=new Vector2(460,26);
            disposition.text=IonGatewayProtocol.CsvElectricalText(cycle.InspectionCsv)+"\n"+(gateway?gateway.IonSummary(cycle.InspectionId):"Gateway 자동 연동 꺼짐 · 진단 미요청");
        }
        else disposition.fontSize=15;
        var csv=cycle.InspectionCsv?.row==null?null:cycle.InspectionCsv;
        if(csv!=null)
        {
            metadata.text+=" | CSV "+csv.row.id;conditions[2].text="JETSON CSV";

        }
        var caption=transform.Find("IonClassicSurface/LiveView/DoseCaption");if(caption)caption.GetComponent<Text>().text=csv!=null?"ACCUMULATED DOSE / JETSON CSV 환산":"ACCUMULATED DOSE / 시뮬레이션";
        if(cycle.status.StartsWith("CSV TEST DATA NOT READY")){state.text="Jetson CSV 연결 대기";state.color=Amber;disposition.text="Jetson 데이터 받기를 완료한 뒤 이온주입을 시작하세요.";}
        var sourceLabel=transform.Find("IonClassicSurface/Source");if(sourceLabel)sourceLabel.GetComponent<Text>().text=csv!=null?"JETSON CSV · 환산 시연":"SIMULATION · 실측 아님";
        var store=IonImplantHistory.Instance;
        if(Application.isPlaying&&cycle.completed&&cycle.completedRuns>seenRuns){store.Add(new IonImplantHistory.Entry{id=Session+"-"+cycle.GetEntityId()+"-"+cycle.completedRuns,lot_id=cycle.incomingLotId,completed_at=DateTimeOffset.Now.ToString("O"),recipe_id=recipeId,source=csv==null?"simulation":"jetson_csv_test",sample_id=csv?.row?.id,csv_sha256=csv?.dataset_sha256,electrical_source=csv?.measurement_source,dose=cycle.dose,target=cycle.targetDose,lower=doseLower,upper=doseUpper,verdict=IonDoseAssessment.Evaluate(cycle.dose,doseLower,doseUpper,true,false)});seenRuns=cycle.completedRuns;}
        var rows=store.Today();int normal=rows.Count(e=>e.verdict=="OK"),failed=rows.Count(e=>e.verdict=="FAIL"),judged=normal+failed;string[] values={rows.Count+" 건",normal+" 건",failed+" 건",judged==0?"—":(normal*100.0/judged).ToString("F1")+" %"};for(int i=0;i<4;i++)daily[i].text=store.Readable?values[i]:"—";
        statsNote.text="로컬 시뮬레이션 · 완료 "+rows.Count+"건 / 판정 완료 "+judged+"건 · 정상 비율 = OK / (OK + FAIL) · 미판정 제외";
        var recent=store.Latest();for(int row=0;row<6;row++){var e=row<recent.Count?recent[row]:null;string[] cells=e==null?new[]{"","","","",""}:new[]{e.id.Length>12?e.id.Substring(0,4)+"…"+e.id.Substring(e.id.Length-6):e.id,e.lot_id,DateTimeOffset.TryParse(e.completed_at,out var t)?t.LocalDateTime.ToString("MM.dd HH:mm:ss"):"시각 미확인",e.dose.ToString("0.00E+00"),e.verdict};for(int col=0;col<5;col++){historyCells[row*5+col].text=cells[col];historyCells[row*5+col].color=e!=null&&col==4?(e.verdict=="FAIL"?Red:e.verdict=="OK"?Green:Muted):Ink;}}
        historyNote.text=store.Readable?(recent.Count==0?"기록 없음 · 이 대시보드 적용 후 완료한 공정부터 저장됩니다.":"최근 "+recent.Count+"건 · 로컬 시뮬레이션 공정 이력 · 팀원 DB 저장 결과와 별도"):"이력 읽기/저장 실패 · "+store.Error;
        criteria.text="공정: 바디 이온주입 / BODY IMPLANT\n\n주입 이온: B⁺\n에너지: "+cycle.energyKeV.ToString("0.#")+" keV\n목표 주입량: "+cycle.targetDose.ToString("0.00E+00")+" ions/cm²\n허용 범위: "+range+" cm⁻²\n레시피 ID: "+cv[4]+"\n\nTCAD ML 기반 시연 기준 (±5%) · 경계 포함 OK\n시뮬레이션 주입량 판정이며 실제 계측·전기특성 판정이나 양산 승인 규격이 아닙니다.";
        for(int i=0;i<3;i++)views[i].SetActive(i==view);sourceNote.text=(csv==null?"SIMULATION · 실제 계측 아님":"JETSON CSV "+csv.row.id+" / TCAD 전기특성 · 실측 아님")+" | "+(gateway&&gateway.IonJob(cycle.InspectionId)!=null?"Gateway 진단·보정안 / TCAD 재검증·승인 별도":"진단은 Gateway 자동 연동 필요");
    }
    void Update(){if(Application.isPlaying&&Time.unscaledTime>=nextRefresh){nextRefresh=Time.unscaledTime+.25f;Refresh();}}
    public static void Install(IonImplantCycle source)
    {var root=source.monitor.rectTransform.parent.GetComponent<RectTransform>();var d=root.GetComponent<IonImplantDashboard>();if(!d){root.localScale*=Mathf.Min(root.rect.width/Width,root.rect.height/Height);d=root.gameObject.AddComponent<IonImplantDashboard>();}source.dashboard=d;d.Build(source);}
    public void ToggleWindow()
    {
        windowOpen=!windowOpen;
        if(windowOpen&&!screenOverlay)
        {
            var source=transform.Find("IonClassicSurface").GetComponent<RectTransform>();
            var go=new GameObject("ION_CLASSIC_SCREEN_OVERLAY",typeof(RectTransform),typeof(Canvas));
            screenOverlay=go.GetComponent<Canvas>();screenOverlay.renderMode=RenderMode.ScreenSpaceOverlay;screenOverlay.sortingOrder=29990;
            screenSurface=Instantiate(source,go.transform,false);screenSurface.anchorMin=screenSurface.anchorMax=screenSurface.pivot=new Vector2(.5f,.5f);
            var from=source.GetComponentsInChildren<RectTransform>(true);var to=screenSurface.GetComponentsInChildren<RectTransform>(true);
            for(int i=0;i<from.Length;i++)
            {
                if(i>0)overlayRects.Add(new KeyValuePair<RectTransform,RectTransform>(from[i],to[i]));
                var a=from[i].GetComponent<Graphic>();var b=to[i].GetComponent<Graphic>();
                if(a&&b){b.raycastTarget=false;overlayGraphics.Add(new KeyValuePair<Graphic,Graphic>(a,b));}
            }
        }
        SyncOverlay();
    }
    void SyncOverlay()
    {
        if(!screenOverlay)return;screenOverlay.enabled=windowOpen&&isActiveAndEnabled;if(!windowOpen)return;
        float scale=Mathf.Max(.1f,Mathf.Min((Screen.width-24)/Width,(Screen.height-36)/Height));
        screenSurface.localScale=Vector3.one*scale;screenSurface.localRotation=Quaternion.identity;screenSurface.anchoredPosition=new Vector2(0,-8);
        screenArea=new Rect((Screen.width-Width*scale)/2,(Screen.height-Height*scale)/2+8,Width*scale,Height*scale);
        foreach(var pair in overlayRects)
        {
            if(!pair.Key||!pair.Value)continue;
            pair.Value.gameObject.SetActive(pair.Key.gameObject.activeSelf);
            pair.Value.anchoredPosition=pair.Key.anchoredPosition;pair.Value.sizeDelta=pair.Key.sizeDelta;
        }
        foreach(var pair in overlayGraphics)
        {
            if(!pair.Key||!pair.Value)continue;pair.Value.color=pair.Key.color;pair.Value.enabled=pair.Key.enabled;
            if(pair.Key is Text a&&pair.Value is Text b){b.text=a.text;b.font=a.font;b.fontSize=a.fontSize;b.fontStyle=a.fontStyle;}
        }
    }
    void LateUpdate(){SyncOverlay();}
    void OnGUI()
    {
        if(!Application.isPlaying||!windowOpen||!screenOverlay)return;
        // Like the film monitor, draw directly on screen, outside HDRP exposure/tone mapping.
        var previous=GUI.matrix;int depth=GUI.depth;GUI.matrix=Matrix4x4.identity;GUI.depth=-100;
        var ev=Event.current;
        if(ev.type==EventType.MouseDown&&ev.button==0&&screenArea.Contains(ev.mousePosition))
        {
            Vector2 local=(ev.mousePosition-screenArea.position)/(screenArea.width/Width);
            if(new Rect(921,3,30,22).Contains(local)){ToggleWindow();ev.Use();}
            else for(int i=0;i<3;i++)if(new Rect(i==0?22:i==1?145:268,218,i==2?110:120,29).Contains(local)){SetView(i);SyncOverlay();ev.Use();break;}
        }
        GUI.matrix=previous;GUI.depth=depth;
    }
    void RemoveOverlay()
    {
        if(screenOverlay){if(Application.isPlaying)Destroy(screenOverlay.gameObject);else DestroyImmediate(screenOverlay.gameObject);}
        screenOverlay=null;screenSurface=null;overlayRects.Clear();overlayGraphics.Clear();
    }
    void OnDisable(){windowOpen=false;RemoveOverlay();}
    void OnDestroy(){RemoveOverlay();}
}
