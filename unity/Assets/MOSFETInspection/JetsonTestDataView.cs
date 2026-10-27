using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

// CSV stays on Jetson. localhost is an authenticated SSH forward, not a local CSV fallback.
public class JetsonTestDataView : MonoBehaviour
{
    const string Address="http://127.0.0.1:8601/api/v1/test-samples";
    JetsonTestDataProtocol.Dataset dataset;
    static JetsonTestDataView instance;
    readonly JetsonTestDataProtocol.AutoSequence sequence=new JetsonTestDataProtocol.AutoSequence();
    readonly JetsonTestDataProtocol.AutoSequence ionSequence=new JetsonTestDataProtocol.AutoSequence();
    int ionGeneration;
    bool open,loading,automatic=true,csvRequested;
    int waferGeneration;
    int index,mode;
    string status="Jetson 시험 데이터 연결 대기",search="",waferCount="1";
    Vector2 scroll;
    UnityWebRequest request;
    Font font;
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]static void ResetStatic(){instance=null;}
    void Awake(){instance=this;}
#if UNITY_EDITOR
    public void UseTestDataset(JetsonTestDataProtocol.Dataset data){JetsonTestDataProtocol.Validate(data);instance=this;dataset=data;automatic=true;mode=0;}
#endif
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Attach()
    {
        var view=FindAnyObjectByType<JetsonTestDataView>();
        if(!view&&FindAnyObjectByType<EllipsometerCycle>())view=new GameObject("JETSON_CSV_TEST_DATA").AddComponent<JetsonTestDataView>();
        instance=view;
    }
    public static bool PrepareIncoming(EllipsometerCycle film,bool newWafer=false)
    {
        var self=instance;if(!self||!self.automatic)return true;
        if(self.dataset==null){if(!self.csvRequested)return true;self.status="Jetson CSV 수신 완료 후 검사하세요. 기존 시연값으로 자동 대체하지 않습니다.";return false;}
        if(!film||!film.recipe||film.Running){self.status="설비 검사 완료 후 새 시험 웨이퍼를 준비하세요. 기존 분석은 별도로 계속됩니다.";return false;}
        int count;if(!int.TryParse(self.waferCount,out count)||count<1||count>10000){self.status="분석 웨이퍼 수는 1~10000으로 입력하세요.";return false;}
        int generation=self.waferGeneration+(newWafer?1:0);
        string key=film.GetEntityId()+"|"+film.lotId+"|"+film.waferId+"|"+generation;
        try
        {
            var selection=self.sequence.Bind(self.dataset,self.mode==0?"TCAD":"PC",key,film.recipe.targetNm,film.recipe.lowerNm,film.recipe.upperNm,count);
            if(!film.SetCsvTest(selection))return false;
            self.waferGeneration=generation;self.index=Math.Max(0,Array.FindIndex(self.dataset.rows,row=>row.id==selection.row.id));
            self.status=selection.Label+" · "+Category(selection.category)+" · 같은 웨이퍼 재검사 시 유지";return true;
        }
        catch(ArgumentException){self.status="시험 데이터·두께 기준 확인 필요";return false;}
        catch(InvalidOperationException){self.status="선택 출처에 정상·두께 이상·전기특성 이상 사례가 모두 필요합니다.";return false;}
    }
    // Probe independent sequences so checking readiness never consumes the next inspection's CSV row.
    public static bool CanPrepareOht(EllipsometerCycle film,IonImplantCycle ion,out string reason)
    {
        reason=null;var self=instance;
        if(!film||!film.recipe||!ion){reason="산화막·이온주입 설비 설정 확인 필요";return false;}
        if(!self||self.dataset?.rows==null||self.dataset.rows.Length==0)
        {reason="CSV 입력 대기 · Jetson CSV 시험값 → Jetson 데이터 받기를 먼저 완료하세요.";return false;}
        try
        {
            if(self.automatic)
            {
                int count;if(!int.TryParse(self.waferCount,out count)||count<1||count>10000)throw new ArgumentException("웨이퍼 수 확인 필요");
                new JetsonTestDataProtocol.AutoSequence().Bind(self.dataset,self.mode==0?"TCAD":"PC","OHT-READINESS",film.recipe.targetNm,film.recipe.lowerNm,film.recipe.upperNm,count);
                if(ion.useJetsonCsv)new JetsonTestDataProtocol.AutoSequence().BindIon(self.dataset,"TCAD","OHT-READINESS",(float)IonDoseAssessment.MlTarget,
                    (float)(ion.dashboard?ion.dashboard.doseLower:IonDoseAssessment.MlLower),(float)(ion.dashboard?ion.dashboard.doseUpper:IonDoseAssessment.MlUpper));
            }
            else
            {
                if(film.SelectedCsv==null||!JetsonTestDataProtocol.CanSelect(film.SelectedCsv.row,film.SelectedCsv.measurement_source))
                    throw new ArgumentException("산화막 TCAD 시험 행 선택 필요");
                if(ion.useJetsonCsv&&(ion.SelectedCsv?.row==null||ion.SelectedCsv.measurement_source!="TCAD"||!JetsonTestDataProtocol.CanSelect(ion.SelectedCsv.row,"TCAD")))
                    throw new ArgumentException("이온주입 TCAD 시험 행 선택 필요 · CSV 자동 순서 권장");
            }
            return true;
        }
        catch(Exception error) when(error is ArgumentException||error is InvalidOperationException)
        {reason="CSV 입력 확인 필요 · "+error.Message;return false;}
    }
    public static bool TryIonInput(IonImplantCycle ion,out JetsonTestDataProtocol.Selection selection,bool newWafer=false)
    {
        selection=null;var self=instance;
        if(!self||self.dataset?.rows==null||self.dataset.rows.Length==0)return false;
        try
        {
            int generation=self.ionGeneration+(newWafer?1:0);
            string key="IMP-01|"+ion.incomingLotId+"|"+ion.incomingWaferId+"|"+generation;
            if(self.automatic)
            {
                var d=ion.dashboard;
                selection=self.ionSequence.BindIon(self.dataset,"TCAD",key,(float)IonDoseAssessment.MlTarget,
                    (float)(d?d.doseLower:IonDoseAssessment.MlLower),(float)(d?d.doseUpper:IonDoseAssessment.MlUpper));
            }
            else selection=ion.SelectedCsv;
            if(selection?.row==null||selection.measurement_source!="TCAD"||!JetsonTestDataProtocol.CanSelect(selection.row,"TCAD"))return false;
            selection=JsonUtility.FromJson<JetsonTestDataProtocol.Selection>(JsonUtility.ToJson(selection));selection.n_wafers=1;
            self.ionGeneration=generation;string rowId=selection.row.id;self.index=Math.Max(0,Array.FindIndex(self.dataset.rows,r=>r.id==rowId));
            self.status=selection.Label+" · "+Category(selection.category)+" · 이온주입 시험값 준비";return true;
        }
        catch(ArgumentException){self.status="Jetson 주입량 시험 데이터·TCAD 기준 확인 필요";return false;}
        catch(InvalidOperationException){self.status="주입량 정상·주입량 이상·전기특성 이상 사례가 모두 필요합니다.";return false;}
    }
    static string Category(string category)=>category=="normal"?"정상":category=="thickness"?"두께 이상":category=="dose"?"주입량 이상":"전기특성 이상";
    IEnumerator Fetch()
    {
        csvRequested=true;loading=true;status="Jetson CSV 수신 중";
        using(var query=UnityWebRequest.Get(Address))
        {
            request=query;query.timeout=10;yield return query.SendWebRequest();
            if(query.result!=UnityWebRequest.Result.Success){dataset=null;status="연결 실패 · start-jetson-test-data.cmd 창의 READY를 확인하세요.";}
            else
            {
                try
                {
                    if(query.downloadHandler.data.Length>5_000_000)throw new ArgumentException();
                    var received=JsonUtility.FromJson<JetsonTestDataProtocol.Dataset>(query.downloadHandler.text);JetsonTestDataProtocol.Validate(received);
                    dataset=received;index=0;status="Jetson CSV "+dataset.rows.Length+"행 수신 · "+(automatic?"자동 순서 준비 · 다음 투입/검사 때 선택":"적용할 시험값을 선택하세요.");
                }
                catch(Exception){dataset=null;status="시험 데이터 검증 실패 · CSV 형식 확인 필요";}
            }
            request=null;
        }
        loading=false;
    }
    void Draw(int id)
    {
        if(GUI.Button(new Rect(724,5,28,25),"X"))open=false;
        GUI.Label(new Rect(16,35,730,28),"Jetson CSV 시험 데이터 · 실제 측정 아님 / 설비 레시피 변경 없음");
        bool enabled=GUI.enabled;GUI.enabled=!loading;
        if(GUI.Button(new Rect(16,69,180,32),loading?"받는 중...":"Jetson 데이터 받기"))StartCoroutine(Fetch());GUI.enabled=enabled;
        GUI.Label(new Rect(209,70,535,50),status);
        if(dataset?.rows==null||dataset.rows.Length==0)return;
        index=Mathf.Clamp(index,0,dataset.rows.Length-1);
        int selectedMode=GUI.Toolbar(new Rect(16,114,255,28),automatic?0:1,new[]{"자동 순서","직접 선택"});
        if((selectedMode==0)!=automatic){automatic=selectedMode==0;status=automatic?"자동 순서 준비 · 다음 투입/검사 때 선택":"직접 선택 모드 · 행 선택 후 적용하세요. 기존 검사값은 유지됩니다.";}
        GUI.Label(new Rect(16,151,80,26),"ID 검색");search=GUI.TextField(new Rect(94,151,180,26),search,100);
        scroll=GUI.BeginScrollView(new Rect(16,188,255,327),scroll,new Rect(0,0,225,Math.Max(302,dataset.rows.Length*30)));
        int y=0;for(int i=0;i<dataset.rows.Length;i++)
        {
            var row=dataset.rows[i];if(search.Length>0&&row.id.IndexOf(search,StringComparison.OrdinalIgnoreCase)<0)continue;
            GUI.enabled=enabled&&!automatic;
            if(GUI.Button(new Rect(0,y,220,27),(index==i?"> ":"")+row.id+" · "+row.kind))index=i;y+=30;
        }
        GUI.EndScrollView();GUI.enabled=enabled;
        var ion=FindAnyObjectByType<IonImplantCycle>();bool forIon=FactoryControlBar.Selected==FactoryControlBar.Equipment.Implanter&&ion;
        if(forIon)mode=0;
        var selected=dataset.rows[index];string source=mode==0?"TCAD":"PC";
        GUI.Label(new Rect(290,115,450,28),"선택: "+selected.id+" / "+selected.kind);
        GUI.enabled=enabled&&!forIon;mode=GUI.Toolbar(new Rect(290,150,450,32),mode,new[]{"TCAD 값","PC 예측값"});source=mode==0?"TCAD":"PC";GUI.enabled=enabled;
        GUI.Label(new Rect(290,195,450,85),$"투입 웨이퍼: 드리프트 도핑 ×{selected.epi_doping_ratio:F4}\n이온주입 조건: 도즈 ×{selected.dose_ratio:F4}\n산화막 두께 배율: ×{selected.oxide_ratio:F4}");
        var film=FindAnyObjectByType<EllipsometerCycle>();
        if(film&&film.recipe)GUI.Label(new Rect(290,280,450,47),$"목표 {film.recipe.targetNm:F1} nm → 시험 두께 {JetsonTestDataProtocol.Thickness(film.recipe.targetNm,selected):F2} nm\n허용 {film.recipe.lowerNm:F1}–{film.recipe.upperNm:F1} nm");
        bool available=JetsonTestDataProtocol.CanSelect(selected,source);var m=mode==0?selected.tcad:selected.pc;
        GUI.Label(new Rect(290,335,450,62),available?$"{source}: Vth {m.vth:F4} V / BV {m.bv:F3} V\ngm {m.gm:E3} A/V/μm / Id4V {m.id4v:E3} A/μm":"이 행에는 "+source+" 전기특성 값이 없습니다. 다른 출처를 선택하세요.");
        GUI.Label(new Rect(290,400,450,40),"산화막은 3개 지점에 같은 환산값을 표시합니다.\n지점별 측정값·편차는 CSV에 없습니다.");
        GUI.Label(new Rect(290,447,285,27),"분석 웨이퍼 수 (시험 가정)");waferCount=GUI.TextField(new Rect(580,447,80,27),waferCount,5);
        int count;bool validCount=int.TryParse(waferCount,out count)&&count>=1&&count<=10000;
        bool busy=forIon?ion.Running:!film||film.Running;
        GUI.enabled=enabled&&!busy&&!automatic&&available&&validCount;
        if(GUI.Button(new Rect(290,490,450,34),automatic?"자동 순서 사용 중 · 행 지정 불필요":forIon?"다음 이온주입 검사에 적용":"다음 산화막 검사에 적용"))
        {
            var choice=new JetsonTestDataProtocol.Selection{row=selected,measurement_source=source,dataset_sha256=dataset.dataset_sha256,n_wafers=forIon?1:count,reference_target_nm=forIon?0:film.recipe.targetNm};
            if(forIon?ion.SetCsvTest(choice):film.SetCsvTest(choice))status="적용됨: "+selected.id+" / "+source+" · "+(forIon?"이온주입":"산화막")+" 검사를 시작하세요.";
        }
        GUI.enabled=enabled&&!busy;
        GUI.enabled=enabled&&!busy&&automatic&&validCount;
        if(GUI.Button(new Rect(16,535,255,31),"새 시험 웨이퍼 준비"))
        {if(forIon){if(TryIonInput(ion,out var next,true))ion.SetCsvTest(next);}else PrepareIncoming(film,true);}
        GUI.enabled=enabled&&!busy;
        if(GUI.Button(new Rect(16,578,255,31),"CSV 해제 · 기존 시연값 사용")){if(forIon?ion.SetCsvTest(null):film&&film.SetCsvTest(null)){automatic=false;status="CSV 해제 · 기존 시연값 사용";}}
        GUI.enabled=enabled;
        GUI.Label(new Rect(290,535,450,78),automatic?(forIon?"이온주입: 정상 → 주입량 이상 → 전기특성 이상\n같은 웨이퍼는 유지 / 새 시험 웨이퍼로 다음 사례":"순서: 정상 → 두께 이상 → 전기특성 이상 → 반복\n새 OHT 투입 때 자동 선택 / 같은 웨이퍼는 유지")+"\n단독 검사 시 왼쪽 '새 시험 웨이퍼 준비' 사용":"Jetson CSV 배율 × TCAD 기준값으로 시연합니다.\n실제 센서 계측·보정 적용과는 별도입니다.");
        GUI.DragWindow(new Rect(0,0,715,28));
    }
    void OnGUI()
    {
        if(!Application.isPlaying)return;
        var matrix=GUI.matrix;int depth=GUI.depth;var oldFont=GUI.skin.font;
        float scale=Mathf.Min(Screen.width/1280f,Screen.height/720f);GUI.matrix=Matrix4x4.Scale(Vector3.one*scale);GUI.depth=-70;
        if(!font)font=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Arial"},16);GUI.skin.font=font;
        if(GUI.Button(new Rect(15,65,225,34),"Jetson CSV 시험값"))open=!open;
        var film=FindAnyObjectByType<EllipsometerCycle>();
        if(film&&film.SelectedCsv!=null)GUI.Label(new Rect(15,103,550,28),film.SelectedCsv.Label+(film.SelectedCsv.automatic?" · "+Category(film.SelectedCsv.category):" · 직접 선택"));
        if(open)GUI.ModalWindow(714880,new Rect((Screen.width/scale-760)/2,80,760,630),Draw,"설비 시험값 · Jetson → Unity");
        GUI.skin.font=oldFont;GUI.matrix=matrix;GUI.depth=depth;
    }
    void OnDisable(){request?.Abort();}
    void OnDestroy(){if(instance==this)instance=null;}
}
