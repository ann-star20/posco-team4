using System.Globalization;
using UnityEngine;

public partial class ProcessAnalysisView
{
    bool gatewayOpen;
    Rect gatewayRect=new Rect(100,30,1060,650);
    GatewayStreamClient gateway;
    GatewayInspectionBridge gatewayBridge;
    bool gatewayRequests;
    public void OpenGateway()
    {
        gateway=GetComponent<GatewayStreamClient>();
        if(!gateway)gateway=gameObject.AddComponent<GatewayStreamClient>();
        gatewayBridge=GetComponent<GatewayInspectionBridge>();
        if(!gatewayBridge)gatewayBridge=gameObject.AddComponent<GatewayInspectionBridge>();
        gatewayBridge.EnsureSession();
        gatewayOpen=true;
    }
    public void OpenGatewayRequests(){OpenGateway();gatewayRequests=true;}
    void DrawGatewayWindow()
    {
        if(!gatewayOpen||!gateway)return;
        var c=GUI.color;var b=GUI.backgroundColor;var t=GUI.contentColor;
        GUI.color=GUI.backgroundColor=GUI.contentColor=Color.white;
        EnsureClassicStyles();
        gatewayRect=GUI.Window(714845,gatewayRect,DrawGateway,"",classicWindow);
        GUI.color=c;GUI.backgroundColor=b;GUI.contentColor=t;
    }
    void DrawGateway(int id)
    {
        float w=gatewayRect.width;
        ClassicFill(new Rect(1,1,w-2,30),classicTitle);
        ClassicLabel(new Rect(12,5,w-70,24),"Gateway Event Viewer — DB 저장 결과 수신",15);
        if(GUI.Button(new Rect(w-48,3,38,23),"×",classicClose))gatewayOpen=false;
        if(ClassicButton(new Rect(15,37,180,27),"검사 전송·결과"))gatewayRequests=true;
        if(ClassicButton(new Rect(205,37,180,27),"RUN별 수신 기록"))gatewayRequests=false;
        var field=new GUIStyle(GUI.skin.textField){font=font,fontSize=14,normal={background=classicWhite,textColor=ClassicInk},focused={background=classicWhite,textColor=ClassicInk}};
        if(gatewayRequests){DrawGatewayRequests(w,field);GUI.DragWindow(new Rect(0,0,w-55,30));return;}
        ClassicLabel(new Rect(15,77,100,25),"Gateway 주소");
        gateway.endpoint=GUI.TextField(new Rect(120,74,w-135,28),gateway.endpoint,field);
        ClassicLabel(new Rect(15,113,100,25),"RUN ID");
        gateway.runId=GUI.TextField(new Rect(120,110,w-365,28),gateway.runId,field);
        if(ClassicButton(new Rect(w-235,110,105,28),"연결",!gateway.Reconnecting))gateway.ConnectStream();
        if(ClassicButton(new Rect(w-122,110,107,28),"연결 해제",gateway.Reconnecting))gateway.DisconnectStream();
        ClassicLabel(new Rect(15,149,w-30,28),gateway.Error??gateway.Status,14,gateway.Error!=null?ClassicRed:gateway.Connected?ClassicGreen:ClassicAmber);
        ClassicLabel(new Rect(15,178,w-30,24),"수신 RUN: "+(gateway.ActiveRun??"—")+"   |   마지막 sequence: "+gateway.LastSequence,13,ClassicMuted);
        var e=gateway.Events.FindLast(item=>item.event_type=="surrogate.completed"||item.event_type=="surrogate.failed");var response=e?.payload?.response;var result=response?.result_payload;
        ClassicWell(new Rect(15,211,w-30,172));
        string origin=response?.result_origin;
        bool mock=origin=="mock"||response?.metadata?.representation=="synthetic_normalized_fixture";
        bool failed=response?.status=="failed";
        ClassicLabel(new Rect(27,220,w-55,28),failed?GatewayInspectionProtocol.FailureTitle(response):result==null?"전기특성 결과 수신 대기":mock?"MOCK · 통신 시험 데이터 / 물리 모델 예측 아님":"전기특성 수신 · 출처: "+(origin??"미확인"),18,failed?ClassicRed:mock?ClassicAmber:ClassicInk,true);
        if(result!=null)
        {
            string N(double v)=>v.ToString("G8",CultureInfo.InvariantCulture);
            string[] names=mock?new[]{"Vth (시험값)","gm (시험값)",e.hasIdOn?"id_on (시험값)":"id (시험값)","BV (시험값)"}:
                new[]{"Vth (V)","gm (µS/µm)",e.hasIdOn?"id_on (µA/µm)":"id (단위 미확인)","BV (V)"};
            string[] values={result.vth_present?N(result.vth):"—",result.gm_present?N(result.gm):"—",e.hasIdOn?N(result.id_on):e.hasId?N(result.id):"미수신",result.bv_present?N(result.bv):"—"};
            // The received fixture uses id, while the draft contract uses id_on. Do not silently substitute either field.
            for(int i=0;i<4;i++)
            {
                float x=27+i*(w-55)/4;
                ClassicLabel(new Rect(x,260,(w-55)/4,24),names[i],13,ClassicMuted);
                ClassicLabel(new Rect(x,285,(w-55)/4,38),values[i],i==2?16:26,ClassicInk,true);
            }
            ClassicLabel(new Rect(27,333,w-55,40),mock?"정규화 시험값 · 단위 / OK·NG 판정에 사용하지 않음. "+response.metadata?.note:"서버 gm·id_on은 마이크로 단위로 그대로 표시 · 기존 CSV의 A 단위와 별도 · 자동 판정/보정에 사용하지 않음",13,ClassicMuted);
        }
        else ClassicLabel(new Rect(27,265,w-55,90),failed?GatewayInspectionProtocol.ErrorCode(response)+" · "+GatewayInspectionProtocol.ErrorMessage(response):"이 RUN의 surrogate.completed 이벤트를 기다립니다. AOI 이벤트는 아래 수신 기록에서 확인할 수 있습니다.",15,failed?ClassicRed:ClassicMuted);
        ClassicLabel(new Rect(15,396,w-30,25),"최근 수신 이벤트 · 최대 32건 / 재접속 시 이번 Play의 sequence부터 이어받음",13,ClassicMuted);
        int start=Mathf.Max(0,gateway.Events.Count-4);
        for(int i=start;i<gateway.Events.Count;i++)
        {
            var item=gateway.Events[i];float y=428+(i-start)*39;
            ClassicLabel(new Rect(16,y,64,30),item.sequence.ToString(),14,ClassicInk,true);
            ClassicLabel(new Rect(83,y,285,30),item.event_type,14);
            ClassicLabel(new Rect(370,y,w-390,30),item.event_id,13,ClassicMuted);
        }
        ClassicLabel(new Rect(15,604,w-30,30),"이 창은 수신 확인용입니다. 기존 검사 결과·LOT 보류·보정안은 변경하지 않습니다.",13,ClassicMuted);
        GUI.DragWindow(new Rect(0,0,w-55,30));
    }
}
