using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;

public partial class ProcessAnalysisView
{
    sealed class IonInspection
    {
        public string id,lot,unit;
        public JetsonTestDataProtocol.Selection csv;
        public IonGatewayProtocol.Measurements electrical;
        public Input directInput;
        public Payload directResult;
        public IonGatewayProtocol.Review review;
        public string directState="Jetson 직접 진단 연결·순서 대기",archiveState;
        public int directAttempts;
    }
    readonly List<IonInspection> ionInspections=new List<IonInspection>();
    IonInspection ionInspection;
    public string IonInspectionId=>ionInspection?.id;
    public ElectricalSpec.Verdict IonElectricalVerdict=>ionInspection==null?ElectricalSpec.Verdict.Pending:
        ElectricalSpec.Evaluate((float)ionInspection.electrical.vth,(float)ionInspection.electrical.bv);
    public bool OpenIonResult(IonImplantCycle cycle)
    {
        if(!cycle||!cycle.completed||cycle.failed||cycle.InspectionCsv==null)return false;
        try
        {
            var record=ionInspections.Find(r=>r.id==cycle.InspectionId);
            if(record==null)
            {
                var csv=JsonUtility.FromJson<JetsonTestDataProtocol.Selection>(JsonUtility.ToJson(cycle.InspectionCsv));
                record=new IonInspection{id=cycle.InspectionId,lot=cycle.incomingLotId,unit=cycle.InspectionUnitId,csv=csv,electrical=IonGatewayProtocol.CsvMeasurements(csv)};
                record.review=IonGatewayProtocol.ReviewCompleted(cycle);
                if(record.review==IonGatewayProtocol.Review.Diagnosis)
                {
                    if(GatewayInspectionBridge.Instance&&GatewayInspectionBridge.Instance.OwnsInspection(record.id))
                        record.directState="Gateway 전체 사이클 · 예측 → 진단 → 조건부 TCAD 검증";
                    else
                    {
                        var m=csv.row.tcad;
                        record.directInput=NewInput(record.lot,samples?.baseline_version,1,new Measurement{vth=m.vth,gm=m.gm,id4v=m.id4v,bv=m.bv});
                    }
                }
                else
                {
                    record.directState=record.review==IonGatewayProtocol.Review.Normal?"주입량·전기특성 모두 OK · 정상 완료 / 보정 불필요":"검사 판정 대기 · 입력·허용 범위 확인 필요";
                    record.archiveState="진단·보정 후보 생략 · 검사 결과 DB 전송은 Gateway 연동 상태 확인";
                }
                if(ionInspections.Count==32)ionInspections.RemoveAt(0);ionInspections.Add(record);
            }
            selectedFullCycle=null;ionInspection=record;lotContext=null;WindowOpen=true;gatewayOpen=false;SetAnalysisTab(0);return true;
        }
        catch(ArgumentException error){LastError=error.Message;return false;}
    }
    void PumpIonDirect()
    {
        if(!CanRequest)return;
        var next=ionInspections.Find(r=>r.directAttempts==0&&r.directInput!=null&&r.directResult==null&&
            !(GatewayInspectionBridge.Instance&&GatewayInspectionBridge.Instance.OwnsInspection(r.id)));
        if(next!=null)_=SendIonDirect(next);
    }
    async Task SendIonDirect(IonInspection record)
    {
        record.directAttempts++;record.directState="Jetson 직접 진단 계산 중 · 원인·보정안 대기";
        bool sent=await RequestInput(record.directInput,true);
        if(!sent&&record.directResult==null)record.directState="직접 진단 전송 실패 · 연결·모델 기준 확인 / 자동 재전송 없음";
    }
    void FailIonDirect(string requestId,string reason)
    {
        var record=ionInspections.Find(r=>r.directInput?.request_id==requestId);
        if(record!=null)record.directState="직접 진단 실패 · "+reason;
    }
    void ReceiveIonDirect(Payload result)
    {
        var record=ionInspections.Find(r=>r.directInput?.request_id==result.request_id&&r.lot==result.lot_id);
        if(record==null||record.directResult!=null)return;
        record.directResult=result;record.directState="Jetson 직접 진단 완료 · "+result.mode+" / "+result.model_version;
        var bridge=GatewayInspectionBridge.Instance;
        record.archiveState=bridge?bridge.QueueIonTcadCandidate(record.id,result):"Gateway 연결 없음 · DB 미전송";
        if(ionInspection==record){WindowOpen=true;SetAnalysisTab(1);}
    }
    public string IonDirectSummary(string inspection)
    {
        var record=ionInspections.Find(r=>r.id==inspection);
        return record==null?null:record.directResult==null?record.directState:IonGatewayProtocol.DescribeDirect(record.directResult);
    }
    public string[][] IonElectricalRows()
    {
        var m=ionInspection?.electrical;if(m==null)return new string[0][];
        bool vthOk=m.vth>=ElectricalSpec.VthMin&&m.vth<=ElectricalSpec.VthMax,bvOk=m.bv>=ElectricalSpec.BvMin;
        return new[]{new[]{"문턱전압 (Vth)",m.vth.ToString("F3")+" V","1.7–2.6 V",vthOk?"OK":"NG"},
            new[]{"항복전압 (BV)",m.bv.ToString("F3")+" V","40 V 이상",bvOk?"OK":"NG"},
            new[]{"트랜스컨덕턴스 (gm)",m.gm.ToString("F3")+" µS/µm","진단용 관측값","판정 제외"},
            new[]{"드레인 전류 (Id @ 4 V)",m.id_on.ToString("F3")+" µA/µm","진단용 관측값","판정 제외"}};
    }
    void DrawIonClassic(float w)
    {
        var r=ionInspection;var bridge=GatewayInspectionBridge.Instance;var job=bridge?bridge.IonJob(r.id):null;
        var diagnosis=job?.diagnosis;var verdict=IonElectricalVerdict;
        string direct=r.directResult==null?r.directState:IonGatewayProtocol.DescribeDirect(r.directResult);
        string archive=job?.state??r.archiveState??"Gateway 자동 연동 꺼짐 · DB 미전송";
        ClassicLabel(new Rect(14,65,w-30,25),"이온주입 검사 완료 · 저장된 TCAD 전기특성",14,ClassicGreen);
        ClassicLabel(new Rect(14,93,w-30,25),"IMP-01 | "+r.lot+" | "+r.unit+" | 검사 "+r.id,15,ClassicInk,true);
        ClassicLabel(new Rect(14,122,w-30,25),"입력: Jetson CSV "+r.csv.row.id+" / TCAD · 센서 실측·새 ML 예측 아님",13,ClassicMuted);
        ClassicLabel(new Rect(14,150,w-30,28),r.directState,14,r.review==IonGatewayProtocol.Review.Normal?ClassicGreen:ClassicAmber);
        float half=(w-37)*.59f;ClassicWell(new Rect(13,189,half,83));ClassicWell(new Rect(half+24,189,w-half-37,83));
        ClassicLabel(new Rect(24,193,half-20,20),"전기특성 판정 / 해당 CSV 행 기준",12,ClassicMuted);
        ClassicLabel(new Rect(24,217,63,39),verdict.ToString(),28,verdict==ElectricalSpec.Verdict.OK?ClassicGreen:ClassicRed);
        ClassicLabel(new Rect(92,218,half-94,34),verdict==ElectricalSpec.Verdict.OK?"TCAD 전기특성 적합":"TCAD 전기특성 부적합",22,ClassicInk,true);
        ClassicLabel(new Rect(half+38,193,w-half-60,20),"보정 후보 TCAD 재검증 / 승인",12,ClassicMuted);
        ClassicLabel(new Rect(half+38,217,w-half-60,28),r.review==IonGatewayProtocol.Review.Normal?"보정 불필요":"미검증 · 적용 전",21,r.review==IonGatewayProtocol.Review.Normal?ClassicGreen:ClassicAmber,true);
        ClassicLabel(new Rect(half+38,245,w-half-60,21),r.review==IonGatewayProtocol.Review.Normal?"주입량·전기특성 모두 OK · 정상 완료":"입력 CSV 결과와 보정 후보 재검증은 별도",12,ClassicMuted);
        var tabs=new[]{"전기특성","원인 분석","보정 제안","TCAD 검증","분석 기록"};
        for(int i=0;i<tabs.Length;i++)if(GUI.Button(new Rect(15+i*139,285,137,31),tabs[i],analysisTab==i?classicSelectedTab:classicTab))SetAnalysisTab(i);
        ClassicWell(new Rect(13,316,w-26,window.height-444));
        float ionContentHeight=analysisTab==4?Mathf.Max(360,36+ionInspections.Count*33):analysisTab==2?Mathf.Max(440,330+classicLabel.CalcHeight(new GUIContent((r.directResult?.warning??"")+"\n\nGateway: "+archive),w-75)):360;
        classicScroll=GUI.BeginScrollView(new Rect(20,325,w-40,window.height-461),classicScroll,new Rect(0,0,w-70,ionContentHeight));
        float width=w-75;
        if(analysisTab==0)
        {
            ClassicLabel(new Rect(2,0,width,25),"같은 검사에 고정한 CSV 행 "+r.csv.row.id+" · gm/Id는 마이크로 단위로 환산",13,ClassicMuted);
            ClassicTable(30,width,new[]{"항목","현재 값","허용 기준","상태"},new[]{.33f,.3f,.21f,.16f},IonElectricalRows());
            ClassicParagraph(205,width,"주입량 판정과 전기특성 판정은 별개입니다. gm·Id는 원인 분석에만 사용합니다.",ClassicMuted);
        }
        else if(analysisTab==1)
        {
            var p=r.directResult;
            if(r.review==IonGatewayProtocol.Review.Normal)ClassicParagraph(12,width,"주입량·전기특성 모두 OK · 원인 분석 불필요\n정상 완료했으며 진단 요청을 보내지 않았습니다.",ClassicGreen);
            else if(p==null)ClassicParagraph(12,width,"원인 분석 결과 수신 대기 · "+r.directState,ClassicMuted);
            else
            {
                ClassicLabel(new Rect(2,2,width-160,32),"최우선 후보: "+p.top_cause,20,ClassicInk,true);
                ClassicLabel(new Rect(width-160,2,155,30),$"{p.top_probability*100:F1}%",22,new Color32(42,88,132,255),false,TextAnchor.UpperRight);
                ClassicLabel(new Rect(2,37,width-4,25),p.decided?"모델이 선택한 원인 후보 · TCAD로 확인된 원인은 아님":"원인 구분 불가 · 추가 측정 필요",14,ClassicAmber);
                ClassicTable(68,width,new[]{"공정 항목","추정 상태 비율","의미"},new[]{.24f,.25f,.51f},new[]{
                    new[]{"도즈",p.estimated_dose.ToString("F3"),"이온 주입 도즈 비율"},
                    new[]{"에피",p.estimated_epi.ToString("F3"),"웨이퍼 드리프트층 도핑 사양"},
                    new[]{"산화막",p.estimated_oxide.ToString("F3"),"산화막 두께 비율"}});
                ClassicParagraph(205,width,"다음 확인: "+p.recommendation+"\n후보 점수는 합격률이나 보정 성공률이 아닙니다.",ClassicMuted);
            }
        }
        else if(analysisTab==2)
        {
            var p=r.directResult;
            if(r.review==IonGatewayProtocol.Review.Normal)ClassicParagraph(12,width,"보정 불필요 · 현재 조건 유지\n주입량·전기특성이 모두 OK여서 진단·보정 후보만 생략합니다.\n\n검사 결과 DB: "+archive,ClassicGreen);
            else if(p==null)ClassicParagraph(12,width,"보정 제안 수신 대기 · "+r.directState,ClassicMuted);
            else
            {
                ClassicLabel(new Rect(2,2,width-4,24),p.top_cause=="정상"?"정상 진단 · 보정 필요성 확인되지 않음":"보정계수: 모델 추정 상태에 곱하는 배율 / 장비 설정값 아님",14,ClassicAmber);
                string Delta(float f)=>Mathf.Abs(f-1)<.0001f?"유지":((f-1)*100).ToString("+0.0;-0.0")+"%";
                ClassicTable(30,width,new[]{"항목","제안 계수","변경량","구분"},new[]{.24f,.25f,.20f,.31f},new[]{
                    new[]{"도즈","×"+p.dose_factor.ToString("F3"),Delta(p.dose_factor),"TCAD 검토 필요"},
                    new[]{"산화막","×"+p.oxide_factor.ToString("F3"),Delta(p.oxide_factor),"TCAD 검토 필요"},
                    new[]{"에피","변경 없음","—","설비 제어 불가"}});
                ClassicTable(160,width,new[]{"추정 비율 (모델 기준=1)","변경 전","보정 후보"},new[]{.44f,.28f,.28f},new[]{
                    new[]{"도즈",p.estimated_dose.ToString("F3"),(p.estimated_dose*p.dose_factor).ToString("F3")},
                    new[]{"산화막",p.estimated_oxide.ToString("F3"),(p.estimated_oxide*p.oxide_factor).ToString("F3")},
                    new[]{"에피",p.estimated_epi.ToString("F3"),p.estimated_epi.ToString("F3")}});
                ClassicParagraph(290,width,(p.decided?"":"원인 불확실 · 탐색용 후보\n")+(string.IsNullOrEmpty(p.warning)?"TCAD 검증·승인 전에는 적용하지 않습니다.":p.warning)+"\n\nGateway: "+archive,ClassicMuted);
            }
        }
        else if(analysisTab==3)
            ClassicParagraph(4,width,r.review==IonGatewayProtocol.Review.Normal?"주입량·전기특성 모두 OK · 보정 및 TCAD 후보 검증 요청 불필요":
                "보정 후보 TCAD 재검증: 미확인 / 레시피 미적용\n\n"+direct+"\n\n"+archive+"\n진단 완료를 TCAD 검증 완료로 표시하지 않습니다.",r.review==IonGatewayProtocol.Review.Normal?ClassicGreen:ClassicAmber);
        else
        {
            var rows=new List<string[]>();foreach(var entry in ionInspections)
                rows.Add(new[]{entry.id,entry.lot,entry.csv.row.id,ElectricalSpec.Evaluate((float)entry.electrical.vth,(float)entry.electrical.bv).ToString()});
            ClassicTable(4,width,new[]{"검사 ID","LOT","CSV 행","전기 판정"},new[]{.44f,.24f,.18f,.14f},rows.ToArray());
        }
        GUI.EndScrollView();
        float fy=window.height-116;
        ClassicLabel(new Rect(15,fy,w-30,27),r.directResult==null?r.directState:archive,15,ClassicInk,true);
        ClassicLabel(new Rect(15,fy+35,440,25),"검사 "+r.id+" / TCAD CSV "+r.csv.row.id,13,ClassicMuted);
        if(ClassicButton(new Rect(w-460,fy+32,145,29),"원인 분석 보기"))SetAnalysisTab(1);
        if(ClassicButton(new Rect(w-307,fy+32,145,29),"보정 제안 보기"))SetAnalysisTab(2);
        if(ClassicButton(new Rect(w-154,fy+32,138,29),"Gateway DB 결과"))OpenGatewayRequests();
        ClassicFill(new Rect(13,window.height-33,w-26,24),classicHeader);
        ClassicLabel(new Rect(20,window.height-31,w-40,22),r.review==IonGatewayProtocol.Review.Normal?"CSV TCAD 시험값 · 실측 아님 | 정상 완료 / 보정 불필요":"CSV TCAD 시험값 · 실측 아님 | 보정 후보 미승인 / 레시피 미적용",12,ClassicMuted);
    }
}
