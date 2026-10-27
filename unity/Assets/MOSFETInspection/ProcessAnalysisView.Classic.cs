using System;
using System.Collections.Generic;
using UnityEngine;

public partial class ProcessAnalysisView
{
    static readonly Color ClassicInk=new Color32(32,37,32,255),ClassicMuted=new Color32(98,105,98,255),ClassicGreen=new Color32(25,112,35,255),ClassicRed=new Color32(177,36,32,255),ClassicAmber=new Color32(128,83,12,255);
    readonly List<Texture2D> classicTextures=new List<Texture2D>();
    GUIStyle classicWindow,classicButton,classicDisabled,classicTab,classicSelectedTab,classicLabel,classicClose;
    Texture2D classicTitle,classicFace,classicWhite,classicHeader,classicLine,classicSelected;
    Vector2 classicScroll;
    int analysisTab,selectedMetric;
    bool classicMaximized,classicResizePending;
    Rect classicRestoreWindow;
    public int AnalysisTab=>analysisTab;
    public void SetAnalysisTab(int value){analysisTab=Mathf.Clamp(value,0,4);classicScroll=Vector2.zero;}
    public static string PredictionTitle(Measurement m,bool hasBv)
    {
        var value=m==null?ElectricalSpec.Verdict.Pending:ElectricalSpec.Evaluate(m.vth,hasBv?(float?)m.bv:null);
        return value==ElectricalSpec.Verdict.OK?"예측 전기특성 적합":value==ElectricalSpec.Verdict.NG?"예측 전기특성 부적합":"전기특성 판정 대기";
    }
    Texture2D ClassicTexture(Color top,Color bottom,bool bevel=false)
    {
        var t=new Texture2D(32,32,TextureFormat.RGBA32,false){name="ProcessClassicUI",hideFlags=HideFlags.HideAndDontSave};
        for(int y=0;y<32;y++)for(int x=0;x<32;x++)t.SetPixel(x,y,bevel&&(x==0||y==31)?Color.white:bevel&&(x==31||y==0)?new Color32(149,157,150,255):Color.Lerp(bottom,top,y/31f));
        t.Apply();classicTextures.Add(t);return t;
    }
    void EnsureClassicStyles()
    {
        if(classicWindow!=null&&classicTitle)return;
        classicTitle=ClassicTexture(new Color32(221,236,248,255),new Color32(177,204,229,255));
        classicFace=ClassicTexture(new Color32(236,235,231,255),new Color32(236,235,231,255));
        classicWhite=ClassicTexture(Color.white,Color.white);classicHeader=ClassicTexture(Color.white,new Color32(226,231,226,255));
        classicLine=ClassicTexture(new Color32(173,181,172,255),new Color32(173,181,172,255));
        classicSelected=ClassicTexture(new Color32(225,237,251,255),new Color32(225,237,251,255));
        var button=ClassicTexture(Color.white,new Color32(220,222,216,255),true);
        var hover=ClassicTexture(Color.white,new Color32(213,232,246,255),true);
        var pressed=ClassicTexture(new Color32(210,226,240,255),new Color32(228,238,245,255),true);
        classicWindow=new GUIStyle(GUI.skin.window){font=font,padding=new RectOffset(0,0,0,0),border=new RectOffset(1,1,1,1),normal={background=classicFace,textColor=ClassicInk},onNormal={background=classicFace,textColor=ClassicInk}};
        classicLabel=new GUIStyle(GUI.skin.label){font=font,fontSize=14,richText=false,wordWrap=true,normal={textColor=ClassicInk}};
        classicButton=new GUIStyle(GUI.skin.button){font=font,fontSize=14,richText=false,wordWrap=true,border=new RectOffset(1,1,1,1),padding=new RectOffset(6,6,2,2),normal={background=button,textColor=ClassicInk},hover={background=hover,textColor=ClassicInk},active={background=pressed,textColor=ClassicInk},focused={background=hover,textColor=ClassicInk}};
        classicDisabled=new GUIStyle(classicButton){normal={background=classicFace,textColor=ClassicMuted}};
        classicClose=new GUIStyle(classicButton){normal={background=ClassicTexture(new Color32(235,177,161,255),new Color32(180,78,56,255),true),textColor=Color.white}};
        classicTab=new GUIStyle(classicButton){fontSize=14};classicSelectedTab=new GUIStyle(classicTab){fontStyle=FontStyle.Bold,normal={background=classicWhite,textColor=new Color32(35,73,103,255)}};
    }
    void ClassicLabel(Rect r,string value,int size=14,Color? color=null,bool bold=false,TextAnchor align=TextAnchor.UpperLeft)
    {var style=new GUIStyle(classicLabel){fontSize=size,fontStyle=bold?FontStyle.Bold:FontStyle.Normal,alignment=align,normal={textColor=color??ClassicInk}};GUI.Label(r,value??"",style);}
    void ClassicFill(Rect rect,Texture2D texture){GUI.DrawTexture(rect,texture,ScaleMode.StretchToFill,false);}
    void ClassicWell(Rect rect)
    {ClassicFill(rect,classicLine);ClassicFill(new Rect(rect.x+1,rect.y+1,rect.width-2,rect.height-2),classicWhite);}
    bool ClassicButton(Rect rect,string value,bool enabled=true)
    {bool old=GUI.enabled;GUI.enabled=old&&enabled;bool clicked=GUI.Button(rect,value,enabled?classicButton:classicDisabled);GUI.enabled=old;return clicked;}
    float ClassicTable(float y,float width,string[] headers,float[] fractions,string[][] rows,Color[] colors=null,bool select=false)
    {
        float height=29+rows.Length*33;ClassicWell(new Rect(0,y,width,height));float x=1;
        for(int col=0;col<headers.Length;col++){float w=(width-2)*fractions[col];ClassicFill(new Rect(x,y+1,w,27),classicHeader);ClassicLabel(new Rect(x+8,y+4,w-12,24),headers[col],13,ClassicMuted);x+=w;}
        for(int row=0;row<rows.Length;row++)
        {
            float ry=y+29+row*33;
            if(select&&selectedMetric==row)ClassicFill(new Rect(1,ry,width-2,32),classicSelected);
            x=1;for(int col=0;col<headers.Length;col++){float w=(width-2)*fractions[col];ClassicLabel(new Rect(x+8,ry+5,w-13,27),rows[row][col],14,colors!=null&&col==headers.Length-1?colors[row]:ClassicInk);x+=w;}
            ClassicFill(new Rect(1,ry+32,width-2,1),classicLine);
            if(select&&Event.current.type==EventType.MouseDown&&new Rect(1,ry,width-2,33).Contains(Event.current.mousePosition)){selectedMetric=row;Event.current.Use();}
        }
        return y+height;
    }
    void ClassicParagraph(float y,float width,string value,Color color)
    {float height=classicLabel.CalcHeight(new GUIContent(value??""),width);ClassicLabel(new Rect(2,y,width-4,Mathf.Max(32,height+8)),value,14,color);}
    void DrawClassic(int id)
    {
        float w=window.width;
        ClassicFill(new Rect(1,1,w-2,30),classicTitle);
        ClassicLabel(new Rect(12,5,w-145,24),"TCAD Process Analyzer — 공정 분석 및 보정 검토",15,ClassicInk);
        if(ClassicButton(new Rect(w-116,3,30,23),"_"))WindowOpen=false;
        if(ClassicButton(new Rect(w-82,3,30,23),classicMaximized?"▣":"□"))classicResizePending=true;
        if(GUI.Button(new Rect(w-48,3,38,23),"×",classicClose))WindowOpen=false;
        ClassicLabel(new Rect(11,35,400,23),"파일(F)     보기(V)     도움말(H)",13);
        if(ClassicButton(new Rect(w-195,33,180,24),"Gateway DB 결과")){if(ionInspection!=null)OpenGatewayRequests();else OpenGateway();}
        ClassicFill(new Rect(8,59,w-16,1),classicLine);
        var fullCycle=CurrentFullCycle();
        if(fullCycle!=null){DrawFullCycle(fullCycle,w);GUI.DragWindow(new Rect(0,0,w-52,30));return;}
        if(ionInspection!=null){DrawIonClassic(w);GUI.DragWindow(new Rect(0,0,w-52,30));return;}
        var record=lotContext!=null&&LotProcessAnalysis.Instance?LotProcessAnalysis.Instance.Latest(lotContext):null;
        bool filmNormal=LotProcessAnalysis.IsNormal(record);
        var p=lotContext==null?Current:record?.result;
        var input=lotContext==null?p?.input:record?.electrical;
        var m=input?.measurement;bool hasBv=lotContext!=null?record!=null&&record.hasBv:m!=null&&m.bv>0;
        var electrical=m==null?ElectricalSpec.Verdict.Pending:ElectricalSpec.Evaluate(m.vth,hasBv?(float?)m.bv:null);
        string connection=Connected?"서버 연결됨":"연결 끊김 · 마지막 결과";
        ClassicLabel(new Rect(13,65,410,25),connection,14,Connected?ClassicGreen:ClassicAmber);
        string provenance=filmNormal?"정상 완료 · 진단·보정 불필요":p==null?"분석 결과 대기":(p.delivery=="replay"?"저장된 시험 결과 재생":"별도 진단 워커 · 새 계산")+" / "+(p.mode=="gp_tabpfn"?"GP+TabPFN":"기본 GP");
        ClassicLabel(new Rect(445,65,w-461,25),provenance,13,ClassicMuted,false,TextAnchor.UpperRight);
        if(lotContext!=null)
        {
            ClassicLabel(new Rect(14,93,w-30,25),"LOT별 자동 분석 | "+lotContext+" | 검사 "+(record?.inspectionId??"대기"),15,ClassicInk,true);
            ClassicLabel(new Rect(14,120,w-30,23),"입력: "+(record?.scenarioId??"해당 검사 전기특성 수신 대기")+" / 합성 전기특성",13,ClassicMuted);
            ClassicLabel(new Rect(14,145,w-205,32),record?.detail??"이 LOT의 분석 결과 대기",14,ClassicAmber);
            if(ClassicButton(new Rect(w-185,144,170,30),"수동 시험·전체 기록"))Open();
        }
        else
        {
            if(samples?.cases!=null)
            {
                float sw=(w-32)/samples.cases.Length;
                for(int i=0;i<samples.cases.Length;i++)if(ClassicButton(new Rect(14+i*sw,92,sw-5,28),(sampleIndex==i?"● ":"")+samples.cases[i].title,!RequestPending))sampleIndex=i;
                var s=samples.cases[Mathf.Clamp(sampleIndex,0,samples.cases.Length-1)];
                var v=s.measurement;
                ClassicLabel(new Rect(14,122,w-30,22),$"선택 입력 ({s.n_wafers}장 평균): Vth {v.vth:F4} V | gm {v.gm:E3} A/V/μm | Id {v.id4v:E3} A/μm | BV "+(s.has_bv?v.bv.ToString("F3")+" V":"없음")+" / 합성",13,ClassicMuted);
                if(ClassicButton(new Rect(14,148,400,29),RequestPending?"Jetson 분석 응답 대기…":"선택한 시험값으로 Jetson 새 분석 요청",CanRequest))_=RequestSample(sampleIndex);
            }
            ClassicLabel(new Rect(425,149,w-442,28),RequestState,13,ClassicAmber);
        }
        float half=(w-37)*.59f;ClassicWell(new Rect(13,189,half,83));ClassicWell(new Rect(half+24,189,w-half-37,83));
        ClassicLabel(new Rect(24,193,half-20,20),"전기특성 판정 / 해당 결과 입력 기준",12,ClassicMuted);
        Color decisionColor=electrical==ElectricalSpec.Verdict.OK?ClassicGreen:electrical==ElectricalSpec.Verdict.NG?ClassicRed:ClassicMuted;
        ClassicLabel(new Rect(24,217,63,39),electrical==ElectricalSpec.Verdict.Pending?"—":electrical.ToString(),28,decisionColor);
        ClassicLabel(new Rect(92,218,half-94,34),PredictionTitle(m,hasBv),22,ClassicInk,true);
        ClassicLabel(new Rect(half+38,193,w-half-60,20),"TCAD 검증 / 승인",12,ClassicMuted);
        ClassicLabel(new Rect(half+38,217,w-half-60,28),filmNormal?"보정 불필요":"미검증 · 적용 전",21,filmNormal?ClassicGreen:ClassicAmber,true);
        ClassicLabel(new Rect(half+38,245,w-half-60,21),filmNormal?"두께·전기특성 모두 OK · 검사 결과만 저장":"TCAD 결과 확인 후 엔지니어 승인 필요",12,ClassicMuted);
        var tabs=new[]{"전기특성","원인 분석","보정 제안","TCAD 검증","분석 기록"};
        for(int i=0;i<tabs.Length;i++)if(GUI.Button(new Rect(15+i*139,285,137,31),tabs[i],analysisTab==i?classicSelectedTab:classicTab))SetAnalysisTab(i);
        float panelHeight=window.height-441;ClassicWell(new Rect(13,315,w-26,panelHeight));
        float contentWidth=w-66;float textHeight=p==null?0:classicLabel.CalcHeight(new GUIContent((p.recommendation??"")+"\n"+(p.warning??"")),contentWidth-8);
        float contentHeight=analysisTab==2?Mathf.Max(panelHeight-12,187+textHeight+70):analysisTab==3?Mathf.Max(panelHeight-12,440):analysisTab==4?385:panelHeight-12;
        classicScroll=GUI.BeginScrollView(new Rect(17,319,w-34,panelHeight-8),classicScroll,new Rect(0,0,contentWidth,contentHeight));
        if(analysisTab==0)
        {
            ClassicLabel(new Rect(2,2,contentWidth,23),"입력 출처: "+(input==null?"해당 결과의 전기특성 입력 없음":$"{input.lot_id} / {input.n_wafers}장 평균 / {input.data_source}"),13,ClassicMuted);
            string bv=hasBv&&m!=null?m.bv.ToString("F3")+" V":"없음";
            string vth=m==null?"대기":m.vth.ToString("F4")+" V";
            var vthBad=m!=null&&(!Number(m.vth,ElectricalSpec.VthMin,ElectricalSpec.VthMax));
            var bvBad=hasBv&&m!=null&&m.bv<ElectricalSpec.BvMin;
            ClassicTable(29,contentWidth,new[]{"항목","현재 값","허용 기준","상태"},new[]{.33f,.30f,.21f,.16f},new[]{
                new[]{"문턱전압 (Vth)",vth,"1.7–2.6 V",m==null?"대기":vthBad?"부적합":"적합"},
                new[]{"항복전압 (BV)",bv,"40 V 이상",!hasBv||m==null?"판정 대기":bvBad?"부적합":"적합"},
                new[]{"트랜스컨덕턴스 (gm)",m==null?"대기":m.gm.ToString("E3")+" A/V/μm","규격 미정","판정 제외"},
                new[]{"드레인 전류 (Id @ 4 V)",m==null?"대기":m.id4v.ToString("E3")+" A/μm","규격 미정","판정 제외"}},
                new[]{m==null?ClassicMuted:vthBad?ClassicRed:ClassicGreen,!hasBv||m==null?ClassicMuted:bvBad?ClassicRed:ClassicGreen,ClassicMuted,ClassicMuted},true);
            string[] desc={"Vth 허용 범위: 1.7–2.6 V (프로젝트 시연 규격)","BV 하한: 40 V. BV가 없으면 전체 OK 판정을 확정하지 않습니다.","gm 규격 미정 · OK/NG 판정 제외", "Id 규격 미정 · OK/NG 판정 제외"};
            ClassicLabel(new Rect(3,197,contentWidth-6,32),desc[selectedMetric],13,ClassicMuted);
        }
        else if(analysisTab==1)
        {
            if(filmNormal)ClassicParagraph(12,contentWidth,"두께·전기특성 모두 OK · 원인 분석 불필요\n검사값·OK 판정은 Gateway로 전송하며 진단 요청은 생략합니다.",ClassicGreen);
            else if(p==null)ClassicParagraph(12,contentWidth,"원인 분석 결과 수신 대기 · "+(LastError??RequestState),ClassicMuted);
            else
            {
                ClassicLabel(new Rect(2,2,contentWidth-160,32),"최우선 후보: "+p.top_cause,20,ClassicInk,true);
                ClassicLabel(new Rect(contentWidth-160,2,155,30),$"{p.top_probability*100:F1}%",22,new Color32(42,88,132,255),false,TextAnchor.UpperRight);
                ClassicLabel(new Rect(2,37,contentWidth-4,25),p.decided?"모델이 선택한 원인 후보 · TCAD로 확인된 원인은 아님":"원인 구분 불가 · 추가 측정 필요",14,ClassicAmber);
                ClassicTable(68,contentWidth,new[]{"공정 항목","추정 상태 비율","의미"},new[]{.24f,.25f,.51f},new[]{new[]{"도즈",p.estimated_dose.ToString("F3"),"이온 주입 도즈 비율"},new[]{"에피",p.estimated_epi.ToString("F3"),"웨이퍼 드리프트층 도핑 사양"},new[]{"산화막",p.estimated_oxide.ToString("F3"),"산화막 두께 비율"}});
                ClassicLabel(new Rect(2,205,contentWidth-4,27),"후보 점수는 전기특성 합격률이나 보정 성공률이 아닙니다.",13,ClassicMuted);
            }
        }
        else if(analysisTab==2)
        {
            if(filmNormal)ClassicParagraph(12,contentWidth,"보정 불필요 · 현재 조건 유지\n두께·전기특성 모두 OK여서 보정 후보는 전송하지 않습니다.\n검사 결과 저장 상태는 Gateway DB 결과에서 확인할 수 있습니다.",ClassicGreen);
            else if(p==null)ClassicParagraph(12,contentWidth,"보정 제안 수신 대기 · 아직 적용된 조건 없음",ClassicMuted);
            else
            {
                ClassicLabel(new Rect(2,2,contentWidth-4,24),"보정계수: 모델 추정 상태에 곱하는 배율 / 장비 설정값 아님",14,ClassicAmber);
                string Delta(float f)=>Mathf.Abs(f-1)<.0001f?"유지":((f-1)*100).ToString("+0.0;-0.0")+"%";
                ClassicTable(30,contentWidth,new[]{"항목","제안 계수","변경량","구분"},new[]{.24f,.25f,.20f,.31f},new[]{new[]{"도즈","×"+p.dose_factor.ToString("F3"),Delta(p.dose_factor),"TCAD 검토 필요"},new[]{"산화막","×"+p.oxide_factor.ToString("F3"),Delta(p.oxide_factor),"TCAD 검토 필요"},new[]{"에피","변경 없음","—","설비 제어 불가"}});
                ClassicParagraph(170,contentWidth,"다음 확인: "+p.recommendation+"\n\n"+(string.IsNullOrEmpty(p.warning)?"TCAD 검증 대기 · 승인 및 적용 없음":p.warning),ClassicInk);
            }
        }
        else if(analysisTab==3)
        {
            var tcadJob=GatewayInspectionBridge.Instance?.TcadJob(record?.inspectionId);
            ClassicLabel(new Rect(2,2,contentWidth-4,24),filmNormal?"정상 검사 · 보정 및 TCAD 후보 검증 요청 불필요":"Unity → Gateway DB → Gateway 팀원이 TCAD 서버로 전달",14,filmNormal?ClassicGreen:ClassicAmber);
            ClassicTable(30,contentWidth,new[]{"단계","현재 상태","확인 항목"},new[]{.25f,.25f,.50f},new[]{new[]{"1. 진단·후보",p==null?"결과 대기":"완료","별도 진단 워커 결과 / 불확실성 유지"},new[]{"2. Gateway DB",tcadJob?.tcadForward!=null?"저장 확인":"전송·결과 확인 필요","후보 공정값 + 후보의 서버 예측값"},new[]{"3. TCAD 검증","Gateway 팀원 전달 후","동일 deck·바이어스·정규화로 실행"},new[]{"4. 승인·적용","미승인·미적용","검증 결과와 엔지니어 검토 필요"}});
            ClassicLabel(new Rect(2,201,contentWidth-4,28),"현재 화면은 검토용입니다. 승인·레시피 변경·LOT 해제를 실행하지 않습니다.",13,ClassicMuted);
            bool exportable=record!=null&&record.result==p&&p!=null&&!record.superseded;
            if(ClassicButton(new Rect(2,237,245,31),"Gateway에 보정 후보 보내기",exportable))LotProcessAnalysis.Instance.SendTcadToGateway(record);
            if(ClassicButton(new Rect(258,237,190,31),"전송·DB 결과 보기"))OpenGatewayRequests();
            ClassicLabel(new Rect(2,280,contentWidth-4,57),tcadJob?.state??record?.tcadGatewayState??"Gateway 자동 연동을 켜면 진단 완료 후 보정 후보를 자동 전송합니다.",13,ClassicMuted);
            if(tcadJob!=null)ClassicLabel(new Rect(2,339,contentWidth-4,92),"요청 "+tcadJob.request.request_id+"\nRUN "+tcadJob.request.run_id+" / JOB "+(tcadJob.jobId??"접수 대기")+"\nDB event "+(tcadJob.eventId??"완료 수신 대기"),12,ClassicMuted);
        }
        else
        {
            string Date(long ms)=>ms>0?DateTimeOffset.FromUnixTimeMilliseconds(ms).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss"):"—";
            ClassicTable(0,contentWidth,new[]{"구분","내용"},new[]{.24f,.76f},new[]{new[]{"분석 대상",p?.lot_id??lotContext??"대기"},new[]{"분석 방식",p==null?"대기":p.mode+" / "+p.delivery+" / "+p.data_source},new[]{"분석 시간",p==null?"—":p.duration_seconds.ToString("F2")+"초"},new[]{"모델 식별",p?.model_version??"—"},new[]{"기준 버전",p?.baseline_version??"—"},new[]{"요청 ID",p?.request_id??PendingRequestId??"—"},new[]{"RUN ID",p?.run_id??"—"},new[]{"제안 ID",p?.proposal_id??"—"},new[]{"결과 생성",p==null?"—":Date(p.generated_at_ms)},new[]{"입력 출처",input?.data_source??"해당 결과의 입력 없음"}});
        }
        GUI.EndScrollView();
        float fy=window.height-116;
        string notice=RequestPending?"새 요청 처리 중 · 아래 값은 이전에 수신한 결과입니다.":p==null?LastError??"분석 결과 수신 대기":electrical==ElectricalSpec.Verdict.OK?"전기특성 예측 OK · 보정 필요성 검토 후 TCAD 검증":electrical==ElectricalSpec.Verdict.NG?"전기특성 예측 NG · 원인 및 보정안 검토 필요":"전기특성 전체 판정 대기 · 누락된 입력값 확인 필요";
        ClassicLabel(new Rect(15,fy,w-30,27),notice,15,electrical==ElectricalSpec.Verdict.NG?ClassicRed:ClassicInk,true);
        if(lotContext==null)
        {
            if(ClassicButton(new Rect(15,fy+32,65,29),"이전",History.Count>0))SelectResult((SelectedIndex+History.Count-1)%History.Count);
            ClassicLabel(new Rect(91,fy+35,430,24),$"{(p==null?0:SelectedIndex+1)} / {History.Count}   "+(p?.lot_id??"분석 기록 없음"),13,ClassicMuted);
            if(ClassicButton(new Rect(470,fy+32,65,29),"다음",History.Count>0))SelectResult((SelectedIndex+1)%History.Count);
        }
        else ClassicLabel(new Rect(15,fy+35,500,25),"LOT: "+lotContext+" · 해당 검사 결과만 표시",13,ClassicMuted);
        if(ClassicButton(new Rect(w-460,fy+32,145,29),"원인 분석 보기"))SetAnalysisTab(1);
        if(ClassicButton(new Rect(w-307,fy+32,145,29),"보정 제안 보기"))SetAnalysisTab(2);
        if(ClassicButton(new Rect(w-154,fy+32,138,29),"TCAD 전달"))SetAnalysisTab(3);
        ClassicFill(new Rect(13,window.height-33,w-26,24),classicHeader);
        ClassicLabel(new Rect(20,window.height-31,230,22),"TCAD: 미검증 / 레시피: 미적용",12,ClassicAmber);
        ClassicLabel(new Rect(260,window.height-31,w-279,22),"합성 입력 · "+provenance+" / 실제 TCAD 결과 아님",12,ClassicMuted,false,TextAnchor.UpperRight);
        GUI.DragWindow(new Rect(0,0,w-52,30));
    }
    void DestroyClassicTextures()
    {foreach(var texture in classicTextures)if(texture)Destroy(texture);classicTextures.Clear();}
}
