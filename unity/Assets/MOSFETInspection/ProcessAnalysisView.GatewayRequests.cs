using System.Globalization;
using UnityEngine;

public partial class ProcessAnalysisView
{
    void DrawGatewayRequests(float w,GUIStyle field)
    {
        var bridge=gatewayBridge;
        bool enabled=GUI.enabled;GUI.enabled=enabled&&!bridge.Armed;
        ClassicLabel(new Rect(15,78,105,25),"Gateway 주소");
        bridge.StreamAddress=GUI.TextField(new Rect(125,75,w-140,28),bridge.StreamAddress,field);
        ClassicLabel(new Rect(15,114,105,25),"요청 토큰");
        bridge.Token=GUI.PasswordField(new Rect(125,111,w-140,28),bridge.Token,'●',4096,field);
        GUI.enabled=enabled;
        ClassicFill(new Rect(15,153,w-30,71),classicSelected);
        ClassicLabel(new Rect(27,159,w-55,27),"자동 전송 · 설비 검사 완료값 사용",17,ClassicInk,true);
        ClassicLabel(new Rect(27,190,w-55,28),"산화막·이온주입: 검사값 저장 → 예측 → NG일 때 진단 → route에 따른 TCAD 자동 수신",13,ClassicMuted);
        if(ClassicButton(new Rect(15,239,230,30),bridge.Armed?"자동 검사 연동 중":"자동 검사 연동 시작",!bridge.Armed))bridge.Arm();
        if(ClassicButton(new Rect(255,239,150,30),"새 전송 끄기",bridge.Armed))bridge.Disarm();
        ClassicLabel(new Rect(420,244,w-435,28),"검사값 수동 입력 없음 · 정상/NG 모두 전송",13,ClassicMuted);
        ClassicLabel(new Rect(15,281,w-30,40),bridge.Notice,14,!string.IsNullOrEmpty(bridge.Last?.errorCode)?ClassicRed:bridge.Armed?ClassicGreen:ClassicAmber);
        var job=bridge.Last;
        if(job?.cycle!=null){DrawFullCycleGateway(job,w,field);return;}
        if(job?.ion!=null){DrawIonGatewayJob(job,w,field);return;}
        if(job?.filmRecordRequest!=null)
        {
            var r=job.filmRecordRequest.input_payload.provenance.inspection_result;
            var e=r.electrical;
            ClassicWell(new Rect(15,328,w-30,261));
            ClassicLabel(new Rect(27,336,w-55,31),job.state,16,ClassicInk,true);
            ClassicLabel(new Rect(27,375,w-55,30),$"ELLIP-01 / {job.request.lot_id} / 검사 판정 {r.verdict}",17,r.verdict=="OK"?ClassicGreen:ClassicAmber,true);
            ClassicLabel(new Rect(27,411,w-55,26),$"두께 {r.thickness_mean_nm:F3} nm ({r.thickness_verdict}) / 전기특성 {r.electrical_verdict}",15,ClassicInk);
            ClassicLabel(new Rect(27,445,w-55,48),e==null?"전기특성 입력 없음":$"원 검사: Vth {e.vth_v:F3} V / gm {e.gm_us_per_um:F3} µS/µm / Id4V {e.id4v_ua_per_um:F3} µA/µm / BV {e.bv_v:F3} V",14,ClassicInk);
            ClassicLabel(new Rect(27,500,w-55,67),"request_id "+job.request.request_id+"\nRUN "+job.request.run_id+"\n"+(r.verdict=="OK"?"정상 완료 · 진단·보정 불필요":"NG 원인분석·보정 후보는 별도 요청"),13,ClassicMuted);
            ClassicLabel(new Rect(15,601,w-30,58),"원 검사값·판정: input_payload.provenance.inspection_result\n"+(job.sequence>0?"DB sequence "+job.sequence+" / "+job.eventId:"완료 이벤트 확인 대기")+" / 서버 예측값과 원 검사값은 별도",12,ClassicMuted);
            return;
        }
        if(job!=null)
        {
            ClassicWell(new Rect(15,328,w-30,261));
            var request=job.request;
            string N(double n)=>n.ToString("G8",CultureInfo.InvariantCulture);
            ClassicLabel(new Rect(27,336,w-55,31),job.state,16,!string.IsNullOrEmpty(job.errorCode)?ClassicRed:job.origin=="mock"?ClassicAmber:ClassicInk,true);
            bool candidate=job.kind=="tcad_candidate_prediction";
            string thickness=candidate?"보정 후보 산화막 "+N(request.input_payload.process_parameters.oxide_thickness)+" µm":job.inspection==null?"산화막 측정 완료 대기":N(job.inspection.thickness_mean_nm)+" nm → "+N(job.inspection.oxide_thickness_um)+" µm";
            ClassicLabel(new Rect(27,372,w-55,26),request.lot_id+" / "+thickness,15,ClassicInk,true);
            ClassicLabel(new Rect(27,401,100,22),"request_id",13);GUI.TextField(new Rect(130,398,w-160,26),request.request_id,field);
            ClassicLabel(new Rect(27,433,100,22),"run_id",13);GUI.TextField(new Rect(130,430,w-160,26),request.run_id,field);
            var physical=request.input_payload?.process_parameters;
            ClassicLabel(new Rect(27,465,w-55,25),physical==null?"같은 CSV 행의 도즈·에피와 측정 두께로 전송 조건 준비 중":"전송 조건: 도즈 "+N(physical.body_dose)+" cm⁻² / 에피 "+N(physical.epi_doping)+" cm⁻³ ("+(candidate?"모델 보정 후보":"시연 조건")+")",13);
            if(job.result!=null)
            {
                ClassicLabel(new Rect(27,495,w-55,40),GatewayInspectionProtocol.ResultText(job.result,job.hasIdOn,job.hasId,job.origin=="mock"),14,ClassicInk,true);
                ClassicLabel(new Rect(27,537,w-55,40),"출처 "+(job.origin??"미확인")+" / 모델 "+(job.model??"미확인")+" / sequence "+job.sequence+" / "+job.eventId,12,ClassicMuted);
            }
            else if(!string.IsNullOrEmpty(job.errorCode))
            {
                ClassicLabel(new Rect(27,497,w-55,24),"결과 없음 · "+job.errorCode+" · 0으로 측정된 것이 아닙니다.",15,ClassicRed,true);
                string detail=job.errorMessage??"서버 오류 응답 확인 필요";
                if(detail.Length>180)detail=detail.Substring(0,180);
                ClassicLabel(new Rect(27,526,w-55,52),detail+(job.oxideInputRatio>0?" / 서버 산화막 입력 배율 "+N(job.oxideInputRatio):""),13,ClassicMuted);
            }
            else ClassicLabel(new Rect(27,504,w-55,60),job.finished?"전기특성 예측 결과 미수신 · 위 종료 상태와 요청 ID를 확인하세요.":candidate?"보정 후보를 Gateway DB에 접수하고 이 후보의 새 모델 예측값을 기다립니다. TCAD 실행은 Gateway 팀원이 전달합니다.":"검사가 끝나면 같은 검사의 산화막 값을 자동 전송합니다. 접수는 queued로, 최종 결과는 완료 이벤트 수신 후 표시합니다.",14,ClassicMuted);
        }
        else ClassicLabel(new Rect(20,346,w-40,160),"주소·토큰을 확인하고 자동 검사 연동을 켠 뒤, 설비 모니터의 기존 ‘검사’를 누르세요.\n\n산화막 검사 완료값 또는 이온주입 누적 주입량을 자동 전송합니다. 이온주입은 정상 검사값도 전송하며, NG일 때 같은 CSV 전기특성으로 진단을 요청합니다. 목표 두께나 임의 입력값을 측정값 대신 사용하지 않습니다.\n\n다른 LOT 공정조건이 등록되어 있지 않으면 전송을 보류합니다.",16,ClassicMuted);
        ClassicLabel(new Rect(15,601,w-30,38),"현재 설비 값은 CSV/시뮬레이션 출처로 기록 · 결과 수신은 LOT 판정·보정·레시피를 자동 변경하지 않음 · 기록: Tools/Gateway/Requests",12,ClassicMuted);
    }
    void DrawIonGatewayJob(GatewayInspectionBridge.Job job,float w,GUIStyle field)
    {
        string N(double n)=>n.ToString("G7",CultureInfo.InvariantCulture);
        var root=gatewayBridge.IonJob(job.inspectionId);var diagnosis=gatewayBridge.IonDiagnosis(job.inspectionId);
        bool candidate=job.kind=="tcad_candidate_prediction";
        bool normal=job.kind=="ion_inspection_record";
        var inspection=normal?job.normalRequest.input_payload.provenance.inspection_result:null;
        ClassicWell(new Rect(15,328,w-30,261));
        ClassicLabel(new Rect(27,334,w-55,28),"IMP-01 / "+job.ion.lot_id+" / 주입량 "+N(job.ion.dose_cm2)+" cm⁻²",16,ClassicInk,true);
        ClassicLabel(new Rect(27,365,100,23),"검사 ID",13);GUI.TextField(new Rect(130,362,w-160,25),job.inspectionId,field);
        ClassicLabel(new Rect(27,395,100,23),"request_id",13);GUI.TextField(new Rect(130,392,w-160,25),job.request.request_id,field);
        ClassicLabel(new Rect(27,425,100,23),"run_id",13);GUI.TextField(new Rect(130,422,w-160,25),job.request.run_id,field);
        ClassicLabel(new Rect(27,454,w-55,24),"TCAD CSV "+job.ion.csv_sample_id+(candidate?"의 직접 진단 → 보정 후보 전기특성 예측 / 실제 TCAD 검증 아님":" · 저장된 시험값 / 센서 실측·새 ML 예측 아님"),13,ClassicMuted);
        if(candidate)
        {
            var p=job.request.input_payload.process_parameters;
            ClassicLabel(new Rect(27,480,w-55,25),"보정 후보: 도즈 "+N(p.body_dose)+" cm⁻² / 에피 "+N(p.epi_doping)+" cm⁻³ / 산화막 "+N(p.oxide_thickness)+" µm",13,ClassicInk,true);
        }
        else if(normal&&inspection!=null)
        {
            var m=inspection.measurements;
            ClassicLabel(new Rect(27,480,w-55,25),$"원 검사 OK · Vth {m.vth:F3} V / gm {m.gm:F3} µS/µm / Id {m.id_on:F3} µA/µm / BV {m.bv:F3} V",13,ClassicGreen,true);
        }
        else if(root?.result!=null)
        {
            var r=root.result;string verdict=ElectricalSpec.Evaluate((float)r.vth,(float)r.bv).ToString();
            ClassicLabel(new Rect(27,480,w-55,25),"전기특성 "+verdict+" · "+GatewayInspectionProtocol.ResultText(r,root.hasIdOn,root.hasId,false),13,ClassicInk,true);
        }
        string prediction=candidate&&job.result!=null?"\n후보 ML 예측: "+GatewayInspectionProtocol.ResultText(job.result,job.hasIdOn,job.hasId,false):"";
        ClassicLabel(new Rect(27,508,w-55,76),(normal?"주입량 OK · 전기특성 OK / 진단·보정 후보 생략\n"+job.state:gatewayBridge.IonSummary(job.inspectionId)+prediction),13,ClassicInk);
        ClassicLabel(new Rect(15,597,w-30,61),normal?
            "원 검사값·OK 판정: input_payload.provenance.inspection_result\n"+job.state+(job.sequence>0?" / DB sequence "+job.sequence+" / "+job.eventId:"")+"\n서버 예측은 원 검사값과 별도 · 진단·보정 후보·TCAD 검증 요청 없음":candidate?
            job.state+"\n원인·보정안: input_payload.provenance.tcad / "+(job.tcadForward==null?"후보 ML 결과 대기 또는 오류 확인 필요":"DB sequence "+job.sequence+" / "+job.eventId)+" / TCAD 재검증·승인 별도":job.directDiagnosis!=null?
            job.state+"\n직접 진단 원문: input_payload.provenance.direct_diagnosis / Gateway 서버 재진단 완료와 별도":diagnosis?.diagnosis!=null?
            "진단 완료 이벤트 수신 · DB sequence "+diagnosis.sequence+" / "+diagnosis.eventId+"\n보정 후보 TCAD 전달·검증은 Gateway가 관리 · 엔지니어 승인/레시피 자동 적용 없음":
            "Jetson 직접 진단 응답을 기다립니다. 완료 후 진단 원문을 포함해 Gateway에 보냅니다.\n한 장의 CSV TCAD 시험값으로 진단 · 실측/양산 검증 결과와 별도",12,ClassicMuted);
    }
}
