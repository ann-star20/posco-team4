using System;
using System.Collections.Generic;
using UnityEngine;

public partial class ProcessAnalysisView
{
    GatewayInspectionBridge.Job selectedFullCycle;
    GatewayInspectionBridge.Job CurrentFullCycle()
    {
        if(selectedFullCycle?.cycle!=null)return selectedFullCycle;
        var bridge=GatewayInspectionBridge.Instance;if(!bridge)return null;
        string id=ionInspection?.id;
        if(id==null&&lotContext!=null&&LotProcessAnalysis.Instance)id=LotProcessAnalysis.Instance.Latest(lotContext)?.inspectionId;
        return id==null?null:bridge.FullCycleJob(id);
    }
    public void OpenFullCycle(GatewayInspectionBridge.Job job)
    {
        selectedFullCycle=job;
        if(job.ion!=null){ionInspection=ionInspections.Find(r=>r.id==job.inspectionId);lotContext=null;}
        else{ionInspection=null;lotContext=job.request.lot_id;}
        WindowOpen=true;gatewayOpen=false;
    }
    static string Physical(GatewayFullCycleProtocol.Parameters p)=>p==null||!GatewayInspectionProtocol.Positive(p.body_dose)||!GatewayInspectionProtocol.Positive(p.epi_doping)||!GatewayInspectionProtocol.Positive(p.oxide_thickness)?"공정값 미제공/불완전":$"도즈 {p.body_dose:0.000E+00} cm⁻² / 에피 {p.epi_doping:0.000E+00} cm⁻³ / 산화막 {p.oxide_thickness:G6} µm";
    static string RouteName(string r)=>r=="tcad_verify"?"TCAD 검증":r=="apply"?"보정안 승인 대기":r=="manual"?"담당자 검토":r=="no_action"?"추가 보정 없음":"진단 결과 대기";
    void DrawFullCycle(GatewayInspectionBridge.Job job,float w)
    {
        var s=job.cycle;var e=s.Electrical;bool ok=GatewayFullCycleProtocol.ElectricalOk(e);
        ClassicLabel(new Rect(14,65,w-30,26),job.ion==null?"산화막 검사 · Gateway 전체 사이클":"이온주입 검사 · Gateway 전체 사이클",14,ClassicGreen);
        ClassicLabel(new Rect(14,94,w-30,25),job.request.lot_id+" | "+job.request.unit_id+" | 검사 "+job.inspectionId,15,ClassicInk,true);
        ClassicLabel(new Rect(14,123,w-30,25),"공정값 → ML 예측 → Gateway 진단 → 조건부 TCAD 검증 / CSV 실측과 구분",13,ClassicMuted);
        ClassicLabel(new Rect(14,151,w-30,32),job.state,14,ClassicAmber);
        float half=(w-37)*.59f;ClassicWell(new Rect(13,189,half,83));ClassicWell(new Rect(half+24,189,w-half-37,83));
        ClassicLabel(new Rect(24,193,half-20,20),"서로게이트 예측 전기특성 · 센서 실측 아님",12,ClassicMuted);
        ClassicLabel(new Rect(24,217,half-20,39),e==null?"전기특성 예측 대기":!e.hasBv?"BV 미확인 · 전체 판정 대기":ok?"OK · 예측 전기특성 적합":"NG · 예측 전기특성 부적합",23,e==null||!e.hasBv?ClassicMuted:ok?ClassicGreen:ClassicRed,true);
        ClassicLabel(new Rect(half+38,193,w-half-60,20),"TCAD 검증 / 승인",12,ClassicMuted);
        ClassicLabel(new Rect(half+38,217,w-half-60,28),s.DecisionReceived?(s.DecisionStatus=="approved"?"승인 확인":"반려 완료"):s.BatchReceived?"배치 종료 · 검토 필요":RouteName(s.Route),20,ClassicAmber,true);
        ClassicLabel(new Rect(half+38,245,w-half-60,21),s.DecisionReceived?"결정: "+s.DecisionStatus+" · HOLD 자동 해제 없음":"미승인 · 레시피 미적용 · HOLD 자동 해제 없음",12,ClassicMuted);
        string[] tabs={"전기특성","원인 분석","보정 제안","TCAD 검증","분석 기록"};
        for(int i=0;i<tabs.Length;i++)if(GUI.Button(new Rect(15+i*139,285,137,31),tabs[i],analysisTab==i?classicSelectedTab:classicTab))SetAnalysisTab(i);
        float panel=window.height-441,width=w-66;ClassicWell(new Rect(13,315,w-26,panel));
        int candidates=s.Diagnosis?.tcad_proposal?.candidates?.Length??0;
        float height=Mathf.Max(panel-12,analysisTab==2?180+candidates*100:analysisTab==3?180+s.Candidates.Count*75:analysisTab==4?420:300);
        classicScroll=GUI.BeginScrollView(new Rect(17,319,w-34,panel-8),classicScroll,new Rect(0,0,width,height));
        if(analysisTab==0)
        {
            ClassicLabel(new Rect(2,2,width,25),"Gateway surrogate.completed · 마이크로 단위 그대로 표시 / 원 CSV 전기특성과 별도",13,ClassicMuted);
            ClassicTable(31,width,new[]{"항목","예측값","허용 기준","상태"},new[]{.33f,.30f,.21f,.16f},new[]{
                new[]{"문턱전압 (Vth)",e==null?"대기":e.vth.ToString("F4")+" V","1.7–2.6 V",e==null?"대기":e.vth>=1.7-1e-6&&e.vth<=2.6+1e-6?"OK":"NG"},
                new[]{"항복전압 (BV)",e==null?"대기":e.hasBv?e.bv.ToString("F3")+" V":"미측정","40 V 이상",e==null||!e.hasBv?"판정 대기":e.bv>=40-1e-6?"OK":"NG"},
                new[]{"트랜스컨덕턴스 (gm)",e==null?"대기":e.gm.ToString("F3")+" µS/µm","진단용 관측값","판정 제외"},
                new[]{"드레인 전류 (Id @ 4 V)",e==null?"대기":e.id_on.ToString("F3")+" µA/µm","진단용 관측값","판정 제외"}});
            ClassicParagraph(210,width,"원 검사값·판정은 최초 요청의 provenance.inspection_result에 보존합니다.\n진단에는 위 예측값을 measurements로 그대로 전송합니다.",ClassicMuted);
        }
        else if(analysisTab==1)
        {
            var d=s.Diagnosis?.result_payload?.decision;
            ClassicParagraph(6,width,d==null?s.Done&&s.Route==null?"설비 검사·전기특성 예측 OK · 원인 분석 불필요":job.state:
                $"원인 후보: {d.top_category} ({d.top_probability:P1})\n{(d.decided?"모델 원인 후보 판정":"원인 불확실 · 추가 측정 필요")}\n\n다음 확인: {s.Diagnosis.result_payload.next_measurement?.recommendation_code??"미제공"}\n분기: {RouteName(s.Route)}\n\n원인 확률은 보정 성공률이 아닙니다.",ClassicInk);
        }
        else if(analysisTab==2)
        {
            var c=s.Diagnosis?.result_payload?.compensation;
            ClassicParagraph(4,width,c==null?s.Done&&s.Route==null?"정상 완료 · 보정 불필요":job.state:"서버 분기: "+RouteName(s.Route)+"\n목표 공정값: "+Physical(c.target_process_parameters)+"\n\n담당자 승인 전 자동 적용하지 않습니다.",ClassicInk);
            var list=s.Diagnosis?.tcad_proposal?.candidates;
            if(list!=null)for(int i=0;i<list.Length;i++)
            {
                var candidate=list[i];var p=candidate.predicted_outputs;float y=155+i*100;
                ClassicLabel(new Rect(2,y,width,23),"후보 "+(i+1)+" · "+(candidate.name??candidate.label??"TCAD 검토 후보"),15,ClassicInk,true);
                ClassicParagraph(y+26,width,Physical(candidate.process_parameters)+"\n"+(p==null?"후보 예측 미제공":$"후보 예측 Vth {p.vth:F3} V / BV {p.bv:F3} V / gm {p.gm:F3} µS/µm / Id {p.id_on:F3} µA/µm"),ClassicMuted);
            }
        }
        else if(analysisTab==3)
        {
            string elapsed=job.tcadStarted==default?"":$" / 수신 대기 {(DateTime.UtcNow-job.tcadStarted).TotalMinutes:F1}분";
            ClassicParagraph(3,width,(s.Route=="tcad_verify"?"Gateway가 TCAD 후보를 자동 접수·관리합니다. 약 20–30분 소요 예상"+elapsed:s.Done?"현재 분기에는 TCAD 검증 요청 없음":"진단 결과에 따라 TCAD 검증 여부가 정해집니다.")+"\n"+(s.BatchReceived?"배치 종료 이벤트 수신 · 후보별 결과 검토 필요":"배치 완료 이벤트 수신 전입니다."),ClassicAmber);
            float y=91;
            foreach(var pair in s.Candidates)
            {
                var c=pair.Value;var p=c.result_payload;
                string result=c.status=="succeeded"&&p!=null?$"Vth {p.vth:F3} V / BV {(p.hasBv?p.bv.ToString("F3"):"없음")} V · {(c.spec_verdict?.overall=="in_spec"?"정상":c.spec_verdict==null?"서버 판정 미수신":"불가")}":c.error_message??"결과 대기";
                ClassicParagraph(y,width,$"후보 {c.candidate_index+1} · {c.status} / {pair.Key}\n{result} / 실행 모드: {c.metadata?.calc_mode??"미확인"}",ClassicInk);y+=75;
            }
            ClassicParagraph(y+5,width,"검증 종료는 승인·적용 완료를 뜻하지 않습니다. fake 모드는 통신 시험값입니다.",ClassicMuted);
        }
        else ClassicParagraph(5,width,"예측 request_id "+s.PredictionId+"\n진단 request_id "+(s.DiagnosisId??"생략/대기")+"\nRUN "+s.Run+"\n예측 JOB "+(s.PredictionJob??"접수 대기")+"\n진단 JOB "+(s.DiagnosisJob??"접수 대기")+"\n마지막 sequence "+s.Sequence+" / EVENT "+(job.eventId??"수신 대기")+"\n\n재접속 시 마지막 sequence 이후부터 수신 · 요청 자동 재전송 없음\n로컬 원문: Tools/Gateway/Requests/*.events.jsonl",ClassicMuted);
        GUI.EndScrollView();float fy=window.height-116;
        ClassicLabel(new Rect(15,fy,w-30,35),job.cycleWarning??job.state,14,ClassicAmber);
        if(ClassicButton(new Rect(15,fy+38,145,29),"원인 분석 보기"))SetAnalysisTab(1);
        if(ClassicButton(new Rect(168,fy+38,145,29),"보정 제안 보기"))SetAnalysisTab(2);
        if(ClassicButton(new Rect(321,fy+38,145,29),"TCAD 진행 보기"))SetAnalysisTab(3);
        if(s.Route=="tcad_verify"&&ClassicButton(new Rect(474,fy+38,145,29),"TCAD 후보 승인"))GatewayTcadApprovalView.For(GatewayInspectionBridge.Instance).Show(job);
        if(ClassicButton(new Rect(w-195,fy+38,180,29),"Gateway DB 결과"))OpenGatewayRequests();
        ClassicLabel(new Rect(20,window.height-31,w-40,22),"CSV/시뮬레이션 공정 입력 · ML 예측과 TCAD 검증 구분 | "+(s.DecisionStatus??"미승인·미적용"),12,ClassicMuted);
    }
    void DrawFullCycleGateway(GatewayInspectionBridge.Job job,float w,GUIStyle field)
    {
        var s=job.cycle;ClassicWell(new Rect(15,328,w-30,261));
        ClassicLabel(new Rect(27,337,w-55,27),job.state,16,ClassicInk,true);
        ClassicLabel(new Rect(27,373,w-55,26),job.request.lot_id+" / "+job.request.unit_id+" / 검사 "+job.inspectionId,14,ClassicInk);
        ClassicLabel(new Rect(27,407,100,23),"RUN ID",13);GUI.TextField(new Rect(130,403,w-160,28),s.Run,field);
        ClassicLabel(new Rect(27,443,w-55,45),"예측 요청 "+s.PredictionId+"\n진단 요청 "+(s.DiagnosisId??"생략/대기"),13,ClassicMuted);
        ClassicLabel(new Rect(27,492,w-55,26),"분기: "+RouteName(s.Route)+" / 수신 sequence "+s.Sequence,14,ClassicInk,true);
        if(ClassicButton(new Rect(27,534,230,31),"전기특성·진단·TCAD 결과 보기"))OpenFullCycle(job);
        ClassicLabel(new Rect(15,601,w-30,58),job.cycleWarning??"검사 원본·예측·진단을 같은 RUN으로 연결 · TCAD 검증은 Gateway가 자동 접수 · TCAD 후보 승인창에서 확인 후 설정 적용",12,ClassicMuted);
    }
}
