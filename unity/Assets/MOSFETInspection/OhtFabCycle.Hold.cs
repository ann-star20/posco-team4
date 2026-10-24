using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

public partial class OhtFabCycle
{
    [Serializable] public sealed class HeldLot
    {
        public string lotId,unitId,inspectionId,carrierId,equipment,storedAt,runId;
        public int slot;
        public string disposition="검사 결과 대기",exportedAt;
        public bool qualityHold,exported,manualRemoved;
    }
    [Serializable] sealed class HoldArchive {public List<HeldLot> lots;}
    readonly List<HeldLot> heldLots=new List<HeldLot>();
    readonly HashSet<string> departedInspections=new HashSet<string>();
    public IReadOnlyList<HeldLot> HeldLots=>heldLots.FindAll(h=>!h.exported);
    public bool IsParked(string inspection)=>!string.IsNullOrEmpty(inspection)&&(departedInspections.Contains(inspection)||heldLots.Exists(h=>h.inspectionId==inspection));
    public string HoldNotice {get;private set;}="";
    public bool HasParkedCarrier=>stocker&&(stocker.Stored&&stocker.IsHeldSlot(stocker.reservedSlot)||stocker.Exported);
    public static bool NextLotAvailable {get{var oht=FindAnyObjectByType<OhtFabCycle>();return oht&&oht.HasParkedCarrier;}}
    bool CurrentCarrierParked(int port)=>port>=2&&(departedInspections.Contains(InspectionAt(port))||heldLots.Exists(h=>h.inspectionId==InspectionAt(port)&&h.lotId==LotAt(port)));
    string InspectionAt(int port)=>port==2?ellipsometer.InspectionId:implanter.InspectionId;
    string LotAt(int port)=>port==2?ellipsometer.lotId:implanter.incomingLotId;
    GatewayInspectionBridge.Job JobAt(int port)=>GatewayInspectionBridge.Instance?GatewayInspectionBridge.Instance.FullCycleJob(InspectionAt(port)):null;
    public bool NeedsQuarantine(int port)
    {
        if(port==2&&ellipsometer.lotHeld)return true;
        var job=JobAt(port);
        // Accepted asynchronous work cannot hold the physical tool; unload to quarantine, never to production.
        if(job!=null&&(job.cycle==null||!job.cycle.Done||job.cycle.Route!=null&&job.cycle.Route!="no_action"))return true;
        if(port==2)return !ellipsometer.CanProceed;
        if(implanter.InspectionCsv==null)return true;
        return IonGatewayProtocol.ReviewCompleted(implanter)!=IonGatewayProtocol.Review.Normal;
    }
    void Update()
    {
        if(!Application.isPlaying||!initialized||running||failed||!stocker||stocker.failed||stocker.Running||
            oxidation.Running||ellipsometer.Running||implanter.Running)return;
        if(singleDockedPort>0)
        {
            if(singleDockedPort==2&&SingleInspectionNeedsIsolation())StartCoroutine(Guard(RecoverSingleTool()));
            return;
        }
        foreach(var item in heldLots)
        {
            if(item.exported)continue;
            var job=GatewayInspectionBridge.Instance?GatewayInspectionBridge.Instance.FullCycleJob(item.inspectionId):null;
            if(job?.cycle?.InspectionNg==true)item.qualityHold=true;
            item.disposition=item.qualityHold?"HOLD · NG / 검토 승인 필요":CanAutoExport(item)?"정상 확인 · 자동 출고 대기":"검사 결과 대기 · 정상 미확정";
            if(CanAutoExport(item)){StartCoroutine(Guard(ExportNormal(item)));return;}
        }
        if(ellipsometer.SafeToUnload&&!IsParked(ellipsometer.InspectionId))StartRecovery(2);
        else if(implanter.SafeToUnload&&!IsParked(implanter.InspectionId))StartRecovery(3);
    }
    bool StartRecovery(int port)
    {
        if(failed){HoldNotice="OHT 회수 중단 · "+status;return false;}
        if(!initialized||!stocker){HoldNotice="OHT·스토커 연결 초기화 확인 필요";return false;}
        if(running){HoldNotice="OHT 이송 진행 중 · "+status;return false;}
        if(stocker.failed){HoldNotice="스토커 오류 · "+stocker.status;return false;}
        if(stocker.Running||oxidation.Running||ellipsometer.Running||implanter.Running)
        {HoldNotice="설비 동작 완료 후 FOUP 회수 가능";return false;}
        if(!stocker.Stored){HoldNotice="FOUP 회수 대기 · 스토커 위치: "+stocker.location;return false;}
        if(stocker.IsHeldSlot(stocker.reservedSlot))
        {HoldNotice="다음 LOT 투입 전 · 기존 HOLD FOUP 보관 완료 / 빈 슬롯 준비 필요";return false;}
        StartCoroutine(Guard(RecoverStandalone(port)));return true;
    }
    IEnumerator RecoverStandalone(int port)
    {
        running=true;paused=false;completed=false;
        SetRecoveryPanelNotice(port,"OHT가 FOUP 수거 위치로 이동 중");
        lot_id=LotAt(port);stocker.BeginToolRecovery();
        SetTransportOwnership(true,port);SetDocked(port);
        source_port=portIds[port];destination_port=portIds[0];
        yield return Travel(port);yield return ReturnHeld(port);
    }
    IEnumerator ReturnHeld(int port)
    {
        singleDockedPort=-1;
        Require(stocker,"HOLD isolation requires stocker");
        Require(port==2?ellipsometer.SafeToUnload:implanter.SafeToUnload,"Wafer/doors are not safe for quarantine pickup");
        string inspection=InspectionAt(port);var job=JobAt(port);
        var item=new HeldLot{lotId=LotAt(port),unitId=port==2?ellipsometer.waferId:implanter.InspectionUnitId,
            inspectionId=inspection,carrierId=carrier_id,equipment=port==2?"ELLIP-01":"IMP-01",slot=stocker.reservedSlot,
            qualityHold=job?.cycle?.InspectionNg==true||port==2&&ellipsometer.lotHeld||port==3&&implanter.InspectionCsv!=null&&IonGatewayProtocol.ReviewCompleted(implanter)==IonGatewayProtocol.Review.Diagnosis,
            runId=job?.request.run_id,storedAt=DateTimeOffset.UtcNow.ToString("O")};
        source_port=portIds[port];destination_port=portIds[0];
        State("HOLD LOT → STOCKER / TCAD CONTINUES","QUARANTINE");
        SetRecoveryPanelNotice(port,"OHT가 FOUP를 집어 스토커로 회수 중");
        yield return Pick(port,true);yield return Travel(0);yield return Place(0);
        SetRecoveryPanelNotice(port,"스토커 인계 완료 · 슬롯에 입고 중");
        yield return stocker.Receive();Require(stocker.Stored&&!stocker.failed&&!stocker.Running,"HOLD stocker storage failed");
        item.disposition=item.qualityHold?"HOLD · NG / 검토 승인 필요":"검사 결과 대기 · 정상 미확정";
        stocker.MarkHeld(inspection,item.qualityHold);heldLots.Add(item);SaveHeldLots();
        // Keep inspection IDs, original verdicts and Gateway subscriptions. Only free the equipment's physical port.
        if(port==2){ellipsometer.lotHeld=true;ellipsometer.lotStatus="HOLD · 스토커 SLOT "+(item.slot+1).ToString("D2");ellipsometer.notice="FOUP 격리 보관 · 다음 LOT 검사 가능 / TCAD 별도 수신";}
        stationCarriers[port].gameObject.SetActive(false);
        SetTransportOwnership(false);stationCarriers[port].gameObject.SetActive(false);
        completed=true;completedRuns++;running=false;
        SetRecoveryPanelNotice(port,"FOUP 스토커 SLOT "+(item.slot+1).ToString("D2")+" 보관 완료 · 다음 LOT 검사 가능");
        HoldNotice=item.lotId+" → HOLD SLOT "+(item.slot+1).ToString("D2")+" · TCAD 수신 유지 / 다음 LOT 준비 가능";
        State(HoldNotice,"NONE");
    }
    void SetRecoveryPanelNotice(int port,string message)
    {
        if(port==2){ellipsometer.notice=message;if(ellipsometer.dashboard)ellipsometer.dashboard.Refresh();}
        else{implanter.status="검사 완료 · "+message;if(implanter.dashboard)implanter.dashboard.Refresh();}
    }
    void SaveHeldLots()
    {
        string folder=Path.Combine(Application.dataPath,"../Tools/Logistics/Hold");Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder,"session-"+GetEntityId().ToString().Replace(':','-')+".json"),JsonUtility.ToJson(new HoldArchive{lots=heldLots},true));
    }
    string currentSimulationWafer;
    void BindSimulationLot(int port,string lot)
    {
        if(string.IsNullOrEmpty(currentSimulationWafer))currentSimulationWafer="SIM-WAFER-"+Guid.NewGuid().ToString("N");
        if(port==2)
        {
            ellipsometer.lotId=lot;ellipsometer.waferId=currentSimulationWafer;ellipsometer.lotHeld=false;ellipsometer.lotStatus="새 LOT 검사 준비";
            ellipsometer.SetCsvTest(null);oxidation.lotId=lot;implanter.incomingLotId=lot;implanter.incomingWaferId=currentSimulationWafer;
        }
        else{implanter.incomingLotId=lot;implanter.incomingWaferId=currentSimulationWafer;implanter.SetCsvTest(null);}
        stationCarriers[port].gameObject.SetActive(true);
    }
    public bool PrepareNextLot(int port)
    {
        var previous=stocker&&(stocker.IsHeldSlot(stocker.reservedSlot)||stocker.Exported)?heldLots.FindLast(h=>h.slot==stocker.reservedSlot):
            heldLots.Find(h=>h.inspectionId==InspectionAt(port)&&h.lotId==LotAt(port));
        if(previous==null)return true;
        if(oxidation.Running||ellipsometer.Running||implanter.Running)
        {HoldNotice="공유 FOUP 이송 중인 설비 종료 후 다음 LOT를 투입하세요.";return false;}
        if(!stocker||!(stocker.Stored||stocker.Exported)||stocker.Running||stocker.failed)
        {HoldNotice="HOLD FOUP의 스토커 보관 완료 후 새 LOT를 투입하세요.";return false;}
        if(stocker.Stored&&stocker.CanDispatchReserved&&lot_id!=previous.lotId)
        {BindSimulationLot(port,lot_id);return true;}
        int slot=stocker.NextFreeSlot;
        if(slot<0){HoldNotice="스토커 가득 참 · HOLD LOT를 승인 없이 덮어쓰거나 출고할 수 없습니다.";return false;}
        if(GatewayInspectionBridge.Instance!=null&&GatewayInspectionBridge.Instance.Jobs.Count>0)
        {
            int pending=0;foreach(var j in GatewayInspectionBridge.Instance.Jobs)if(!j.finished)pending++;
            if(pending>=8){HoldNotice="Gateway 대기 작업 8건 · 기존 작업 수신 유지 / 새 투입 보류";return false;}
        }
        try
        {
            string next="SIM-LOT-"+Guid.NewGuid().ToString("N");
            GatewayLotConditions.RegisterSimulationLot(next,GatewayLotConditions.ForLot(previous.lotId));
            stocker.PrepareSimulationCarrier(slot);lot_id=next;carrier_id="SIM-FOUP-"+Guid.NewGuid().ToString("N");
            currentSimulationWafer="SIM-WAFER-"+Guid.NewGuid().ToString("N");BindSimulationLot(port,next);
            HoldNotice=previous.lotId+(previous.manualRemoved?" 시연 수동 반출 완료 · ":previous.exported?" 정상 출고 완료 · ":" 격리 보관 유지 · ")+next+" 새 시뮬레이션 LOT 투입";return true;
        }
        catch(Exception error) when(error is ArgumentException||error is InvalidOperationException)
        {HoldNotice="새 LOT 준비 실패 · "+error.Message;return false;}
    }
    public static bool PrepareInspection(int port)
    {
        var oht=FindAnyObjectByType<OhtFabCycle>();
        if(!oht||oht.Running)return true;
        if(oht.oxidation.Running||oht.ellipsometer.Running||oht.implanter.Running)
            oht.HoldNotice="다른 설비의 FOUP 처리가 끝난 뒤 새 LOT를 투입하세요.";
        else if(oht.ellipsometer.SafeToUnload&&!oht.IsParked(oht.ellipsometer.InspectionId))
        {if(oht.StartRecovery(2))oht.HoldNotice="산화막 완료 FOUP 회수 진행 중 · 스토커 보관 후 다음 LOT 투입 가능";}
        else if(oht.implanter.SafeToUnload&&!oht.IsParked(oht.implanter.InspectionId))
        {if(oht.StartRecovery(3))oht.HoldNotice="이온주입 완료 FOUP 회수 진행 중 · 스토커 보관 후 다음 LOT 투입 가능";}
        else if(oht.PrepareNextLot(port))return true;
        if(port==2){oht.ellipsometer.notice=oht.HoldNotice;if(oht.ellipsometer.dashboard)oht.ellipsometer.dashboard.Refresh();}
        else{oht.implanter.status=oht.HoldNotice;if(oht.implanter.dashboard)oht.implanter.dashboard.Refresh();}
        return false;
    }
    public bool CanManualRemove(HeldLot item)=>item!=null&&!item.exported&&heldLots.Contains(item)&&stocker&&
        !running&&!held&&!stocker.Running&&!stocker.failed&&(stocker.Stored||stocker.Exported)&&
        !oxidation.Running&&!ellipsometer.Running&&!implanter.Running&&stocker.IsHeldSlot(item.slot)&&stocker.heldInspections[item.slot]==item.inspectionId;
    public bool ManualRemove(HeldLot item)
    {
        if(!CanManualRemove(item)){HoldNotice="시연 슬롯 비우기 대기 · 설비/OHT 이송 종료 또는 슬롯 상태 확인 필요";return false;}
        try
        {
            stocker.RemoveSimulationLot(item.slot,item.inspectionId);
            item.manualRemoved=item.exported=true;item.exportedAt=DateTimeOffset.UtcNow.ToString("O");
            item.disposition="시연 수동 반출 · 원 판정 유지 / 정상 승인 아님";
            HoldNotice=item.lotId+" 시연 수동 반출 · SLOT "+(item.slot+1).ToString("D2")+" 비움 / 검사·TCAD 기록 유지";
            try{SaveHeldLots();}
            catch(Exception error) when(error is IOException||error is UnauthorizedAccessException)
            {HoldNotice+=" · 로컬 반출 기록 저장 실패: "+error.Message;}
            return true;
        }
        catch(InvalidOperationException error){HoldNotice="시연 슬롯 비우기 실패 · "+error.Message;return false;}
    }
    public bool CanAutoExport(HeldLot item)
    {
        if(item==null||item.exported||item.qualityHold)return false;
        var job=GatewayInspectionBridge.Instance?GatewayInspectionBridge.Instance.FullCycleJob(item.inspectionId):null;
        return job?.cycle?.NormalInspection==true&&job.request.lot_id==item.lotId&&job.inspectionId==item.inspectionId;
    }
    IEnumerator ExportNormal(HeldLot item)
    {
        Require(CanAutoExport(item),"Only both-OK original inspection and prediction may export automatically");
        running=true;paused=false;State("NORMAL LOT AUTO EXPORT / "+item.lotId,"EXPORT");
        yield return stocker.ExportNormal(item.slot,item.inspectionId);
        Require(!stocker.failed&&!stocker.IsHeldSlot(item.slot)&&!stocker.occupied[item.slot],"Normal export failed to free slot");
        item.exported=true;item.exportedAt=DateTimeOffset.UtcNow.ToString("O");item.disposition="정상 자동 출고 완료";
        if(item.equipment=="ELLIP-01"&&ellipsometer.InspectionId==item.inspectionId&&ellipsometer.lotId==item.lotId)
        {ellipsometer.lotHeld=false;ellipsometer.lotStatus="정상 출고 완료";ellipsometer.notice="정상 검사·예측 OK · 출고 완료 / 다음 LOT 검사 가능";}
        if(item.equipment=="IMP-01"&&implanter.InspectionId==item.inspectionId)
            implanter.status="검사 완료 · 정상 LOT 출고 완료 / 슬롯 비움";
        SaveHeldLots();running=false;completed=true;HoldNotice=item.lotId+" 정상 출고 완료 · SLOT "+(item.slot+1).ToString("D2")+" 비움";State(HoldNotice,"NONE");
    }
    public string HeldLotSummary(HeldLot item)
    {
        var job=GatewayInspectionBridge.Instance?GatewayInspectionBridge.Instance.FullCycleJob(item.inspectionId):null;
        return item.lotId+" | "+item.equipment+" | SLOT "+(item.slot+1).ToString("D2")+" | "+item.disposition+" · "+(job?.state??"진단/검토 대기");
    }
}
