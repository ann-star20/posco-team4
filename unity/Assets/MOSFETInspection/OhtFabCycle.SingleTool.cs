using System;
using System.Collections;
using UnityEngine;

public partial class OhtFabCycle
{
    int singleDockedPort=-1;
    public int SingleDockedPort=>singleDockedPort;
    bool SingleInspectionNeedsIsolation()
    {
        var job=JobAt(2);
        return ellipsometer.lotHeld||job!=null&&(job.cycle==null||job.cycle.InspectionNg||job.cycle.Route!=null&&job.cycle.Route!="no_action");
    }
    IEnumerator RecoverSingleTool()
    {
        running=true;paused=false;completed=false;
        SetTransportOwnership(true,2);SetDocked(2);
        yield return Travel(2);singleDockedPort=-1;yield return ReturnHeld(2);
    }
    public static bool TryStartInspection(int port)
    {
        var oht=FindAnyObjectByType<OhtFabCycle>();if(!oht)return false;
        oht.StartSingleTool(port);return true;
    }
    public void StartSingleTool(int port)
    {
        Require(port>=1&&port<=3,"Invalid single tool port");
        var blocked=StartBlockReason;
        if(string.IsNullOrEmpty(blocked)&&port==1)
        {
            if(singleDockedPort>0)blocked="앞 LOT가 "+portIds[singleDockedPort]+"에 있습니다. 다음 공정부터 진행하세요.";
            else if(!stocker||!(stocker.Stored||stocker.Exported))blocked="스토커 FOUP 보관 완료 후 시작하세요.";
            else if(!PrepareNextLot(2))blocked=HoldNotice;
        }
        if(string.IsNullOrEmpty(blocked)&&port>=2)
        {
            if(singleDockedPort!=port-1||!stationCarriers[port-1].gameObject.activeInHierarchy)
                blocked=port==2?"산화로·로딩 공정을 먼저 완료하세요. 산화로 투입구에서 FOUP를 가져옵니다.":"앨립소미터 검사를 먼저 완료하세요. 앨립소미터에서 FOUP를 가져옵니다.";
            else if(port==2&&!oxidation.completed)blocked="산화 공정 완료·웨이퍼 복귀 후 시작하세요.";
            else if(port==3&&(!ellipsometer.CanProceed||NeedsQuarantine(2)))blocked="산화막·전기특성 정상 확인 후 이온주입 가능 · NG/TCAD 대기 LOT는 스토커 격리";
        }
        if(string.IsNullOrEmpty(blocked))
        {
            if(port==1){oxidation.lotId=lot_id;currentSimulationWafer="SIM-WAFER-"+Guid.NewGuid().ToString("N");}
            else if(port==2){lot_id=ellipsometer.lotId=oxidation.lotId;ellipsometer.waferId=currentSimulationWafer;}
            else{lot_id=implanter.incomingLotId=ellipsometer.lotId;implanter.incomingWaferId=ellipsometer.waferId;}
            if(port==2&&!JetsonTestDataView.PrepareIncoming(ellipsometer,true))blocked="산화막 CSV 시험값 준비 후 다시 시작하세요.";
            if(port==3&&implanter.useJetsonCsv)
            {
                if(!JetsonTestDataView.TryIonInput(implanter,out var selection,true))blocked="Jetson 이온주입 CSV 시험값 준비 후 다시 시작하세요.";
                else implanter.SetCsvTest(selection);
            }
        }
        if(!string.IsNullOrEmpty(blocked))
        {
            HoldNotice=blocked;
            if(port==1)oxidation.status=blocked;else if(port==2)ellipsometer.notice=blocked;else implanter.status=blocked;
            if(!running)State("단독 설비 투입 대기 · "+blocked,"WAIT");return;
        }
        StartCoroutine(Guard(SingleToolSequence(port)));
    }
    IEnumerator SingleToolSequence(int port)
    {
        running=true;paused=false;completed=false;placements=0;
        if(port==1){oxidation.lotId=lot_id;oxidation.ResetPreview();}
        else if(port==2){ellipsometer.lotId=lot_id;ellipsometer.ResetPreview();}
        else{implanter.incomingLotId=lot_id;implanter.ResetPreview();}
        int source=port-1;SetTransportOwnership(true,source>0?source:-1);
        source_port=portIds[source];destination_port=portIds[port];State("설비별 이송 · "+source_port+" → "+destination_port,"WAIT");
        if(source==0){yield return stocker.Dispatch();Require(stocker.AtPort&&!stocker.failed&&!stocker.Running,"Stocker dispatch failed");}
        else yield return Travel(source);
        yield return Pick(source);singleDockedPort=-1;yield return Travel(port);yield return Place(port);yield return Process(port);
        if(port==3||port==2&&SingleInspectionNeedsIsolation()){yield return ReturnHeld(port);yield break;}
        // Keep one physical LOT at the completed tool for the next manual process button.
        singleDockedPort=port;SetTransportOwnership(false);SetDocked(port);
        for(int i=1;i<stationCarriers.Length;i++)stationCarriers[i].gameObject.SetActive(i==port);
        completed=true;completedRuns++;running=false;
        State(port==1?"산화 완료 · 앨립소미터 시작 대기 / FOUP 산화로 투입구 유지":"산화막 검사 완료 · 이온주입기 시작 대기 / FOUP 앨립소미터 유지","NONE");
    }
}
