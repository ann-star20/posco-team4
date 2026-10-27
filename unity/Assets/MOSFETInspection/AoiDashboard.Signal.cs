using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Rendering.HighDefinition;

// Static artwork and element geometry come from the approved browser design.
public partial class AoiDashboard
{
    [Serializable] class SignalLayout { public float width,height;public SignalItem[] items; }
    [Serializable] class SignalItem
    {
        public string name,font,color,text,align;public float x,y,w,h,fontSize,padLeft,padTop,padRight,padBottom;public bool bold;
    }
    [SerializeField] RectTransform signalSurface;
    SignalLayout signalLayout;
    readonly Dictionary<string,Text> signalLabels=new Dictionary<string,Text>();
    readonly Dictionary<string,Sprite> signalSprites=new Dictionary<string,Sprite>();
    readonly Dictionary<string,Font> signalFonts=new Dictionary<string,Font>();
    Canvas signalOverlay;
    RectTransform signalOverlayRoot;
    readonly List<KeyValuePair<Graphic,Graphic>> signalGraphics=new List<KeyValuePair<Graphic,Graphic>>();
    readonly List<KeyValuePair<Transform,Transform>> signalTransforms=new List<KeyValuePair<Transform,Transform>>();
    readonly List<KeyValuePair<Button,Button>> signalButtons=new List<KeyValuePair<Button,Button>>();
    [SerializeField] RawImage signalVerdict;
    [SerializeField] GameObject signalProductRoot;
    bool productTab,connectionSettings;
    Rect signalScreenRect;
    static readonly Color SignalInk=new Color32(231,239,238,255),SignalSub=new Color32(154,175,175,255),SignalAcid=new Color32(209,237,137,255),SignalRed=new Color32(255,121,112,255),SignalPanel=new Color32(23,32,36,255);
    SignalItem Item(string name)=>signalLayout.items.FirstOrDefault(i=>i.name==name)??throw new InvalidOperationException("Signal layout item missing: "+name);
    void LoadSignalLayout(){if(signalLayout==null)signalLayout=JsonUtility.FromJson<SignalLayout>(Resources.Load<TextAsset>("AoiSignal/layout").text);}
    Sprite SignalSprite(string key)
    {
        if(signalSprites.TryGetValue(key,out var cached))return cached;
        var texture=Resources.Load<Texture2D>("AoiSignal/"+key);if(!texture)return null;
        var sprite=Sprite.Create(texture,new Rect(0,0,texture.width,texture.height),new Vector2(.5f,.5f),100);signalSprites[key]=sprite;return sprite;
    }
    Font SignalFont(string family)
    {
        string key=family.Contains("Consolas")?"Consolas":family.Contains("Bahnschrift")?"Bahnschrift":"Segoe UI";
        if(!signalFonts.TryGetValue(key,out var f)){f=Font.CreateDynamicFontFromOSFont(new[]{key,"Malgun Gothic","Arial"},24);signalFonts[key]=f;}return f;
    }
    Text SignalText(string name)
    {
        var i=Item(name);var text=Label(name,"",i.x+i.padLeft,i.y+i.padTop,Mathf.Max(1,i.w-i.padLeft-i.padRight),Mathf.Max(1,i.h-i.padTop-i.padBottom),Mathf.RoundToInt(i.fontSize),SignalInk,i.bold,i.align=="right"?TextAnchor.UpperRight:TextAnchor.UpperLeft);
        text.font=SignalFont(i.font??"");text.lineSpacing=1;text.horizontalOverflow=HorizontalWrapMode.Overflow;text.verticalOverflow=VerticalWrapMode.Overflow;
        var parts=(i.color??"").Replace("rgb(","").Replace(")","").Split(',');
        if(parts.Length==3&&byte.TryParse(parts[0].Trim(),out var r)&&byte.TryParse(parts[1].Trim(),out var g)&&byte.TryParse(parts[2].Trim(),out var b))text.color=new Color32(r,g,b,255);
        signalLabels[name]=text;return text;
    }
    Button SignalButton(string name)
    {
        var i=Item(name);var image=Fill(name,i.x,i.y,i.w,i.h,Color.white);image.sprite=SignalSprite(name+"-normal");image.raycastTarget=true;
        var button=image.gameObject.AddComponent<Button>();button.targetGraphic=image;button.transition=Selectable.Transition.None;
        var previous=buildParent;buildParent=image.rectTransform;var label=Label("Label",i.text,0,0,i.w,i.h,12,new Color(1,1,1,0));label.font=SignalFont("Segoe UI");buildParent=previous;return button;
    }
    void SignalSet(string name,string value)
    {
        if(!signalLabels.TryGetValue(name,out var label)||!label)return;
        value=value??"";var lines=value.Split('\n');
        for(int i=0;i<lines.Length;i++)
        {
            var text=lines[i];float Width(string s){float width=0;label.font.RequestCharactersInTexture(s,label.fontSize,label.fontStyle);foreach(char c in s)if(label.font.GetCharacterInfo(c,out var info,label.fontSize,label.fontStyle))width+=info.advance;return width;}
            float available=label.rectTransform.rect.width;
            if(Width(text)>available){while(text.Length>0&&Width(text+"…")>available)text=text.Substring(0,text.Length-1);lines[i]=text+"…";}
        }
        label.text=string.Join("\n",lines);
    }
    static Rect SignalDisplayRegion(float[] region,Texture2D texture,RectTransform viewport,bool product)
    {
        float width=region[2]-region[0],height=region[3]-region[1];
        float cx=(region[0]+region[2])*.5f,cy=(region[1]+region[3])*.5f;
        width*=product?1.60f:1.26f;height*=product?1.33f:1.76f;
        if(product)cx+=width*.03f;
        // Match SVG's uniform scaling while showing the source image beyond its viewBox.
        float target=viewport.rect.width/viewport.rect.height;
        float aspect=width*texture.width/(height*texture.height);
        if(aspect<target)width=height*texture.height*target/texture.width;else height=width*texture.width/(target*texture.height);
        width=Mathf.Min(1,width);height=Mathf.Min(1,height);
        float left=Mathf.Clamp(cx-width*.5f,0,1-width),top=Mathf.Clamp(cy-height*.5f,0,1-height);
        return new Rect(left,1-top-height,width,height);
    }
    void BuildSignal(AoiJetsonFeed source)
    {
        feed=source;signalLayout=null;LoadSignalLayout();ApplyFont();buildParent=null;
        var rect=(RectTransform)transform;if(rect.rect.width>0)transform.localScale*=rect.rect.width/signalLayout.width;rect.sizeDelta=new Vector2(signalLayout.width,signalLayout.height);
        for(int i=transform.childCount-1;i>=0;i--){var child=transform.GetChild(i).gameObject;if(Application.isPlaying){child.SetActive(false);Destroy(child);}else DestroyImmediate(child);}
        signalSurface=Box("AOI_SIGNAL_WORKSTATION",0,0,signalLayout.width,signalLayout.height);buildParent=signalSurface;signalLabels.Clear();outlines.Clear();shownResult=null;
        var background=Box("ApprovedArtwork",0,0,signalLayout.width,signalLayout.height).gameObject.AddComponent<RawImage>();background.texture=Resources.Load<Texture2D>("AoiSignal/background");background.color=Color.white;background.raycastTarget=false;
        inspectionRoot=Box("InspectionView",0,0,signalLayout.width,signalLayout.height).gameObject;buildParent=(RectTransform)inspectionRoot.transform;
        var photo=Item("Photo");cameraImage=Picture("JetsonImage",photo.x,photo.y,photo.w,photo.h,true);
        imageState=Label("ImageState","검사 이미지 대기",photo.x+10,photo.y+10,photo.w-20,photo.h-20,14,SignalSub,false,TextAnchor.MiddleCenter);
        var crop=Item("Crop");crops=new RawImage[2];crops[0]=Picture("Crop0",crop.x,crop.y,crop.w,crop.h,true);crops[1]=Picture("Crop1",crop.x,crop.y,crop.w,crop.h,true);crops[1].gameObject.SetActive(false);
        // This label is a compatibility target for older scene automation, not a second rendered caption.
        identity=Label("Product","",0,0,1,1,12,Color.clear);identity.gameObject.SetActive(false);
        foreach(var name in new[]{"Pixels","StageTag","ImageCaption","PhotoMode","Verdict","Class","ClassCode","Completion","Route","DetailCount","Score","DefectIndex","DefectTitle","DefectCode","LocationCount","CropTag","InspectionId","ResultSource","Storage","Step","Message","RecordCount","Recent0","Recent1","Recent2","Recent3","Recent4","Recent5"})SignalText(name);
        verdict=signalLabels["Verdict"];kind=signalLabels["Class"];confidence=signalLabels["Score"];route=signalLabels["Route"];message=signalLabels["Message"];
        var vi=Item("Verdict");signalVerdict=Box("VerdictArtwork",vi.x,vi.y,vi.w,vi.h).gameObject.AddComponent<RawImage>();signalVerdict.raycastTarget=false;verdict.color=Color.clear;
        foreach(var name in new[]{"PhotoProduct","PhotoFull","PhotoZoom","DefectTab","ProductTab","SelectDefect0","RequestInspection","SortProduct"})SignalButton(name);
        var live=Button("PhotoLive","실시간 영상",265,185,91,29);live.transition=Selectable.Transition.None;
        var liveLabel=live.GetComponentInChildren<Text>();liveLabel.font=SignalFont("Segoe UI");liveLabel.fontSize=12;liveLabel.fontStyle=FontStyle.Normal;
        BuildScanPresentation();
        // The two crop-selection names and page controls remain available for multi-defect results.
        var row=Item("SelectDefect0");defectButtons=new Button[2];defectButtons[0]=GetComponentsInChildren<Button>(true).First(b=>b.name=="SelectDefect0");
        var second=Button("SelectDefect1","",row.x,row.y+row.h*.5f,row.w,row.h*.5f);second.gameObject.SetActive(false);defectButtons[1]=second;
        var previousButton=Button("DefectPrevious","〈",row.x+row.w-69,row.y-28,29,24);var nextButton=Button("DefectNext","〉",row.x+row.w-34,row.y-28,29,24);previousButton.gameObject.SetActive(false);nextButton.gameObject.SetActive(false);
        defectNames=new[]{signalLabels["DefectTitle"],Label("DefectName1","",row.x+38,row.y+row.h*.5f,row.w-45,row.h*.5f,12,SignalInk)};defectNames[1].gameObject.SetActive(false);
        foreach(var name in new[]{"Score","DefectIndex","DefectTitle","DefectCode"})signalLabels[name].transform.SetAsLastSibling();
        var productBounds=Item("ProductPanel");signalProductRoot=Box("ProductRecognition",productBounds.x,productBounds.y,productBounds.w,productBounds.h).gameObject;
        var previousParent=buildParent;buildParent=(RectTransform)signalProductRoot.transform;Fill("ProductRecognitionSurface",0,0,productBounds.w,productBounds.h,SignalPanel);
        foreach(var tuple in new[]{("body","BODY / 본체"),("lead","LEAD / 리드"),("tab","TAB / 탭")})
        {int index=tuple.Item1=="body"?0:tuple.Item1=="lead"?1:2;Label("PartLabel"+tuple.Item1,tuple.Item2,14,14+index*25,160,24,12,SignalSub);signalLabels["PartState"+tuple.Item1]=Label("PartState"+tuple.Item1,"—",productBounds.w-95,14+index*25,80,24,12,SignalInk,false,TextAnchor.MiddleRight);}
        buildParent=previousParent;
        detailCount=signalLabels["DetailCount"];detailNote=signalLabels["LocationCount"];inspectionInfo=signalLabels["InspectionId"];detectionList=signalLabels["DefectCode"];
        recentCells=new Text[12];for(int i=0;i<6;i++)recentCells[i]=signalLabels["Recent"+i];for(int i=6;i<12;i++){recentCells[i]=Label("UnusedRecent"+i,"",0,0,1,1,11,Color.clear);recentCells[i].gameObject.SetActive(false);}
        recentText=Label("RecentEmpty","검사 완료 후 기록 표시",Item("Recent0").x,Item("Recent0").y,800,30,12,SignalSub);counts=Label("SortCounts","",0,0,1,1,11,Color.clear);counts.gameObject.SetActive(false);
        var decision=Item("Decision");resultPanel=Fill("ResultPanel",decision.x,decision.y,0,0,Color.clear);resultPanel.gameObject.SetActive(false);
        buildParent=signalSurface;
        foreach(var name in new[]{"Connection","Lot","Product","Replay","CameraStatus","JetsonStatus","DatabaseStatus","Provenance"})SignalText(name);
        connection=signalLabels["Connection"];metadata=signalLabels["Lot"];provenance=signalLabels["Provenance"];
        foreach(var name in new[]{"ViewInspection","ViewHistory","ConnectionSettings"})SignalButton(name);
        historyRoot=Box("HistoryView",67,131,signalLayout.width-68,signalLayout.height-162).gameObject;buildParent=(RectTransform)historyRoot.transform;
        Fill("HistorySurface",0,0,signalLayout.width-68,signalLayout.height-162,SignalPanel);
        historyTitle=Label("HistoryTitle","검사 이력",16,18,460,34,20,SignalInk,true);
        Button("HistoryPreviousDay","이전 날짜",16,65,112,30);Button("HistoryNextDay","다음 날짜",136,65,112,30);Button("HistoryFilter","전체",256,65,86,30);Button("HistoryPreviousPage","〈",352,65,40,30);Button("HistoryNextPage","〉",400,65,40,30);
        var hx=new[]{18f,185,306,568,646,810};var hw=new[]{157f,111,252,68,154,105};var headers=new[]{"검사 ID","시각","제품 ID","판정","검출 항목","모델 점수"};
        for(int i=0;i<6;i++)Label("HistoryHeader"+i,headers[i],hx[i],117,hw[i],30,13,SignalSub,true);
        historyRows=new Text[36];for(int r=0;r<6;r++){Button("HistoryRow"+r,"",10,153+r*48,signalLayout.width-90,46);for(int c=0;c<6;c++)historyRows[r*6+c]=Label("HistoryCell"+r+"_"+c,"",hx[c],154+r*48,hw[c],44,13,SignalInk);}
        historyPage=Label("HistoryPage","",16,468,signalLayout.width-110,28,12,SignalSub);historyDetail=Label("HistoryDetail","",16,506,signalLayout.width-110,55,12,SignalInk);
        statValues=new Text[4];var labels=new[]{"오늘 판정 완료","정상 OK","불량 NG","정상 비율"};for(int i=0;i<4;i++){Label("StatLabel"+i,labels[i],16+i*225,592,210,24,12,SignalSub);statValues[i]=Label("StatValue"+i,"—",16+i*225,620,210,35,24,SignalInk,true);}
        buildParent=null;view=0;photoView=3;selectedDefect=defectPage=page=filter=0;historyDay=DateTime.Today;productTab=false;BindButtons();RefreshSignal();
    }
    void SignalButtonState(string name,bool available,bool selected=false)
    {
        var button=GetComponentsInChildren<Button>(true).FirstOrDefault(b=>b.name==name);if(!button)return;
        available=available&&!scanPresenting;button.interactable=available;var image=button.GetComponent<Image>();string prefix=name=="SortProduct"&&feed.Verdict=="OK"?"SortProductOK":name;var sprite=SignalSprite(name=="RequestInspection"&&scanPresenting?"RequestInspection-busy":prefix+(available?(selected?"-active":"-normal"):"-disabled"));if(sprite){image.sprite=sprite;image.color=Color.white;}
    }
    void RefreshSignal()
    {
        if(!feed||!signalSurface)return;LoadSignalLayout();if(signalLabels.Count==0)foreach(var t in signalSurface.GetComponentsInChildren<Text>(true))if(!signalLabels.ContainsKey(t.name))signalLabels[t.name]=t;
        var p=feed.current;var client=feed.GetComponent<AoiDirectClient>();bool inspecting=scanPresenting||client&&client.Inspecting;
        if(shownResult!=(p==null?null:p.result_id)){shownResult=p==null?null:p.result_id;selectedDefect=defectPage=0;if(photoView!=2)photoView=p==null?0:3;}
        selectedDefect=Mathf.Clamp(selectedDefect,0,Mathf.Max(0,DetailCount-1));defectPage=Mathf.Clamp(defectPage,0,Mathf.Max(0,(DetailCount-1)/2));
        string status=inspecting?"검사 중":feed.Verdict;verdict.text=status;
        var v=Resources.Load<Texture2D>("AoiSignal/Verdict-"+(status=="NG"?"NG":status=="OK"?"OK":"Wait"));if(signalVerdict&&v){signalVerdict.texture=v;signalVerdict.color=Color.white;signalVerdict.rectTransform.sizeDelta=new Vector2(v.width/2f,v.height/2f);}
        string label=p==null?"—":p.label=="normal"?"검출된 불량 없음":DefectTitle(p.label).Split('/')[0].Trim()+" 검출";
        SignalSet("Class",inspecting?"분석 요청 중":label);SignalSet("ClassCode",p==null?"WAITING FOR IMAGE":p.label=="normal"?"NO DEFECT DETECTED":p.label.ToUpperInvariant()+" / "+DetailCount+" REGION");
        SignalSet("Completion",inspecting?"분석 중":p==null?"검사 전":"분석 완료");
        route.text=scanPresenting?"검사 중 · 분류 잠금":feed.InspectionCycleRunning?"AOI 검사·자동 분류 연동 중":feed.Busy?"자동 분류 동작 중":feed.SortCompleted?feed.Verdict+" 박스 도착 · 완료":p!=null&&!feed.CanSort?"분류 보류 · "+feed.SortBlockReason:"분류 대기";
        SignalSet("Connection","MANUAL INSPECTION\n"+(feed.demoMode?"DEMO / 시험 모드":feed.connection));
        SignalSet("Lot",p==null||string.IsNullOrEmpty(p.lot_id)?"—":p.lot_id);SignalSet("Product",p==null?"MOSFET":p.product_id);
        SignalSet("Replay",scanPresenting?"FRAME LOCKED":photoView==2?"LIVE CAMERA":p==null?"STANDBY":"RESULT IMAGE");
        Texture2D display=scanPresenting?scanFrame:photoView==2?(CameraStream?CameraStream.Frame:null):(feed.DisplayCurrent?feed.frame:null);
        cameraImage.texture=display;cameraImage.enabled=display;cameraImage.uvRect=new Rect(0,0,1,1);
        SignalSet("Pixels",display?display.width+" × "+display.height+" px":"— × — px");
        if(!scanPresenting&&display&&p!=null&&photoView==1&&DetailCount>0&&AoiDirectProtocol.TryRegion(p.defects[selectedDefect],display.width,display.height,out var region))cameraImage.uvRect=SignalDisplayRegion(region,display,(RectTransform)cameraImage.transform.parent,false);
        if(!scanPresenting&&display&&p!=null&&photoView==3)
        {
            float left=1,top=1,right=0,bottom=0;
            foreach(var d in (p.parts??Array.Empty<AoiDirectProtocol.Detection>()).Concat(p.defects??Array.Empty<AoiDirectProtocol.Detection>()))if(AoiDirectProtocol.TryRegion(d,display.width,display.height,out var part)){left=Mathf.Min(left,part[0]);top=Mathf.Min(top,part[1]);right=Mathf.Max(right,part[2]);bottom=Mathf.Max(bottom,part[3]);}
            if(right>left&&bottom>top)cameraImage.uvRect=SignalDisplayRegion(new[]{left,top,right,bottom},display,(RectTransform)cameraImage.transform.parent,true);
        }
        if(display)imageFit.aspectRatio=display.width*cameraImage.uvRect.width/(display.height*cameraImage.uvRect.height);
        imageState.gameObject.SetActive(!display);imageState.text=photoView==2?(CameraStream?CameraStream.Status:"카메라 연결 대기"):inspecting?"Jetson 결과 수신 대기":"검사 이미지 대기";
        SignalSet("StageTag",scanPresenting?"FRAME LOCK / 검사 중":photoView==2?"LIVE CAMERA / 판정은 별도":p==null?"ACQUISITION / STANDBY":"RESULT IMAGE / 01");
        if(!scanPresenting&&photoView==2&&CameraStream&&CameraStream.FrameId>=0)SignalSet("StageTag","JETSON / FRAME "+CameraStream.FrameId);
        SignalSet("ImageCaption",scanPresenting?"CAPTURED FRAME / 검사 중":photoView==2?"MJPEG / 실시간 카메라":"ANNOTATED JPEG / 결과 사진");SignalSet("PhotoMode",scanPresenting?"FRAME LOCK":"ZOOM: "+(photoView==0?"FULL":photoView==1?"REGION "+(selectedDefect+1).ToString("00"):photoView==2?"LIVE":"PRODUCT"));
        if(!scanPresenting&&photoView==2&&CameraStream&&CameraStream.IsJetsonPreview)SignalSet("ImageCaption","WEBSOCKET JPEG / Jetson 8500");
        bool has=DetailCount>0&&feed.frame;var cropItem=has?p.defects[selectedDefect]:null;
        crops[0].enabled=false;if(has&&AoiDirectProtocol.TryRegion(cropItem,feed.frame.width,feed.frame.height,out var cropRegion)){crops[0].texture=feed.frame;crops[0].uvRect=SignalDisplayRegion(cropRegion,feed.frame,(RectTransform)crops[0].transform.parent,false);crops[0].GetComponent<AspectRatioFitter>().aspectRatio=feed.frame.width*crops[0].uvRect.width/(feed.frame.height*crops[0].uvRect.height);crops[0].enabled=true;}
        var rowItem=has?p.defects[defectPage*2]:null;
        SignalSet("DetailCount",DetailCount.ToString("00"));SignalSet("DefectIndex",has?(defectPage*2+1).ToString("00"):"—");SignalSet("DefectTitle",has?DefectTitle(rowItem.class_name).Split('/')[0].Trim():p==null?"검사 전":"검출된 불량 없음");
        SignalSet("DefectCode",has?rowItem.class_name+" · 선택 영역":"—");SignalSet("Score",has?rowItem.confidence.ToString("F3"):"—");
        SignalSet("LocationCount",has?"DETAIL / "+(selectedDefect+1).ToString("00"):"DETAIL / —");SignalSet("CropTag",has?(selectedDefect+1).ToString("00")+" / "+cropItem.class_name.ToUpperInvariant():"NO REGION");
        SignalSet("InspectionId",p==null?"—":Short(string.IsNullOrEmpty(p.request_id)?p.result_id:p.request_id));SignalSet("ResultSource",p==null?"결과 수신 대기":p.data_source+" / Jetson 검사 결과");
        SignalSet("Storage",p!=null&&p.persistence_status=="queued"?"Jetson 저장 대기 / 로컬 이력 저장":"로컬 검사 이력 / DB 완료 확인 안 됨");SignalSet("Step",p==null?"01":"02");SignalSet("Message",scanPresenting?"현재 프레임 검사 중":client!=null&&client.Status.Contains("실패")?client.Status:p==null?"카메라 연결 → 검사":"검사 결과 확인 → 제품 분류");
        if(!scanPresenting&&!feed.Busy&&!feed.InspectionCycleRunning&&p!=null&&!feed.SortCompleted&&!feed.CanSort)SignalSet("Message","자동 분류 보류 · "+feed.SortBlockReason);
        SignalSet("CameraStatus",CameraStream&&CameraStream.Frame?"LIVE":"—");SignalSet("JetsonStatus",inspecting?"PROCESSING":p==null?"WAITING":"RESULT RECEIVED");SignalSet("DatabaseStatus","NOT CONNECTED");SignalSet("Provenance",Source+" / "+(photoView==2?"LIVE VIEW":"RESULT IMAGE"));
        var store=AoiInspectionHistory.Instance;var stats=store.ForDay(DateTime.Today,Source);statValues[0].text=stats.total+" 건";statValues[1].text=stats.pass+" 건";statValues[2].text=stats.ng+" 건";statValues[3].text=stats.total==0?"—":stats.normalRate.ToString("F1")+"%";
        var recent=store.OnDay(DateTime.Today,Source).FirstOrDefault();recentText.text=recent==null?"검사 완료 후 기록 표시":"";
        var values=recent==null?new[]{"","","","","",""}:new[]{Short(recent.inspection_id),recent.unit_id,recent.verdict,DefectTitle(recent.label),recent.label=="normal"?"—":recent.confidence.ToString("F3"),feed.SortCompleted?"완료":"미실행"};for(int i=0;i<6;i++)SignalSet("Recent"+i,values[i]);
        SignalSet("RecordCount","TODAY / "+stats.total.ToString("00")+" RESULTS");
        visibleHistory=store.OnDay(historyDay,Source).Where(e=>filter==0||e.verdict==(filter==1?"OK":filter==2?"NG":"검토")).ToList();page=Mathf.Clamp(page,0,Mathf.Max(0,(visibleHistory.Count-1)/6));historyTitle.text="검사 이력 · "+historyDay.ToString("yyyy-MM-dd")+" · "+Source;
        for(int r=0;r<6;r++)for(int c=0;c<6;c++){int index=page*6+r;historyRows[r*6+c].text=index<visibleHistory.Count?Cell(visibleHistory[index],c):"";historyRows[r*6+c].color=index<visibleHistory.Count&&visibleHistory[index].verdict=="NG"?SignalRed:SignalInk;}
        historyPage.text=visibleHistory.Count+"건 · "+(page+1)+" / "+Math.Max(1,(visibleHistory.Count+5)/6)+" 페이지";
        inspectionRoot.SetActive(view==0);historyRoot.SetActive(view==1);
        foreach(string name in new[]{"PhotoProduct","PhotoFull","PhotoZoom"})SignalButtonState(name,name!="PhotoZoom"||has,name=="PhotoProduct"&&photoView==3||name=="PhotoFull"&&photoView==0||name=="PhotoZoom"&&photoView==1);
        var liveButton=GetComponentsInChildren<Button>(true).FirstOrDefault(b=>b.name=="PhotoLive");
        if(liveButton){liveButton.interactable=!scanPresenting;liveButton.image.color=photoView==2?new Color32(48,64,53,255):new Color32(18,27,31,255);liveButton.GetComponentInChildren<Text>().color=photoView==2?SignalAcid:SignalSub;}
        SignalButtonState("DefectTab",true,!productTab);SignalButtonState("ProductTab",true,productTab);
        SignalButtonState("ViewInspection",true,view==0);SignalButtonState("ViewHistory",true,view==1);SignalButtonState("ConnectionSettings",true,connectionSettings);
        SignalButtonState("RequestInspection",client&&client.HasToken&&!inspecting&&!feed.Busy&&!feed.InspectionCycleRunning&&!feed.demoMode&&(!inspectCurrentCamera||CameraStream&&CameraStream.CanInspectFrame));SignalButtonState("SortProduct",feed.CanSort);
        bool twoRows=defectPage*2+1<DetailCount;var rowBounds=Item("SelectDefect0");defectButtons[0].GetComponent<RectTransform>().sizeDelta=new Vector2(rowBounds.w,twoRows?rowBounds.h*.5f:rowBounds.h);
        defectButtons[0].interactable=has;defectButtons[1].gameObject.SetActive(twoRows);defectButtons[1].interactable=twoRows;
        foreach(var b in GetComponentsInChildren<Button>(true))
        {
            if(b.name=="DefectPrevious"||b.name=="DefectNext"){b.gameObject.SetActive(DetailCount>1);b.interactable=b.name=="DefectPrevious"?defectPage>0:(defectPage+1)*2<DetailCount;}
            if(b.name=="HistoryFilter")b.transform.Find("Label").GetComponent<Text>().text=new[]{"전체","OK","NG","검토"}[filter];
        }
        if(twoRows){defectButtons[1].GetComponent<Image>().color=new Color32(32,44,49,255);defectNames[1].gameObject.SetActive(true);var d=p.defects[defectPage*2+1];defectNames[1].text=(defectPage*2+2).ToString("00")+"  "+DefectTitle(d.class_name);}else defectNames[1].gameObject.SetActive(false);
        if(!signalProductRoot)signalProductRoot=signalSurface.GetComponentsInChildren<Transform>(true).FirstOrDefault(t=>t.name=="ProductRecognition")?.gameObject;
        if(signalProductRoot)signalProductRoot.SetActive(productTab);
        foreach(string partName in new[]{"body","lead","tab"})SignalSet("PartState"+partName,p?.parts!=null&&p.parts.Any(d=>d.class_name==partName)?"검출됨":"—");
        UpdateScanPresentation();SyncSignalOverlay();
    }
    void ConfigureSignalCamera()
    {
        if(!popupCamera)return;var hd=popupCamera.GetComponent<HDAdditionalCameraData>();hd.customRenderingSettings=true;
        var settings=hd.renderingPathCustomFrameSettings;var mask=hd.renderingPathCustomFrameSettingsOverrideMask;
        foreach(var field in new[]{FrameSettingsField.Postprocess,FrameSettingsField.ExposureControl}){settings.SetEnabled(field,false);mask.mask[(uint)field]=true;}
        hd.renderingPathCustomFrameSettings=settings;hd.renderingPathCustomFrameSettingsOverrideMask=mask;
        popupCamera.backgroundColor=new Color32(16,22,25,255);
        if(popupTexture&&(popupTexture.width!=2048||popupTexture.height!=Mathf.CeilToInt(signalLayout.height*2))){popupCamera.targetTexture=null;popupTexture.Release();Destroy(popupTexture);popupTexture=new RenderTexture(2048,Mathf.CeilToInt(signalLayout.height*2),24);popupTexture.Create();popupCamera.targetTexture=popupTexture;}
    }
    void ShowSignalOverlay()
    {
        if(!Application.isPlaying||!signalSurface)return;
        if(!signalOverlay)
        {
            var go=new GameObject("AOI_SIGNAL_SCREEN_OVERLAY",typeof(RectTransform),typeof(Canvas));signalOverlay=go.GetComponent<Canvas>();signalOverlay.renderMode=RenderMode.ScreenSpaceOverlay;signalOverlay.sortingOrder=30000;
            signalOverlayRoot=Instantiate(signalSurface,go.transform,false);signalOverlayRoot.name="SignalScreen";signalOverlayRoot.anchorMin=signalOverlayRoot.anchorMax=signalOverlayRoot.pivot=new Vector2(.5f,.5f);
            signalGraphics.Clear();signalTransforms.Clear();signalButtons.Clear();
            var from=signalSurface.GetComponentsInChildren<Transform>(true);var to=signalOverlayRoot.GetComponentsInChildren<Transform>(true);
            for(int i=0;i<from.Length;i++){signalTransforms.Add(new KeyValuePair<Transform,Transform>(from[i],to[i]));var a=from[i].GetComponent<Graphic>();var b=to[i].GetComponent<Graphic>();if(a&&b)signalGraphics.Add(new KeyValuePair<Graphic,Graphic>(a,b));var ba=from[i].GetComponent<Button>();var bb=to[i].GetComponent<Button>();if(ba&&bb)signalButtons.Add(new KeyValuePair<Button,Button>(ba,bb));}
        }
        signalOverlay.gameObject.SetActive(true);SyncSignalOverlay();
    }
    void SyncSignalOverlay()
    {
        if(!signalOverlay||!signalOverlayRoot)return;LoadSignalLayout();
        signalOverlay.enabled=open&&!cameraSettings&&!connectionSettings;
        float scale=Mathf.Min((Screen.width-20)/signalLayout.width,(Screen.height-20)/signalLayout.height);signalOverlayRoot.localScale=Vector3.one*Mathf.Max(.1f,scale);signalOverlayRoot.anchoredPosition=Vector2.zero;
        signalScreenRect=new Rect((Screen.width-signalLayout.width*scale)*.5f,(Screen.height-signalLayout.height*scale)*.5f,signalLayout.width*scale,signalLayout.height*scale);
        foreach(var pair in signalTransforms)if(pair.Key&&pair.Value&&pair.Key!=signalSurface){pair.Value.gameObject.SetActive(pair.Key.gameObject.activeSelf);var a=pair.Key as RectTransform;var b=pair.Value as RectTransform;if(a&&b){b.anchorMin=a.anchorMin;b.anchorMax=a.anchorMax;b.pivot=a.pivot;b.anchoredPosition=a.anchoredPosition;b.sizeDelta=a.sizeDelta;}}
        foreach(var pair in signalGraphics)
        {
            if(!pair.Key||!pair.Value)continue;pair.Value.color=pair.Key.color;pair.Value.enabled=pair.Key.enabled;
            if(pair.Key is Text a&&pair.Value is Text b){b.text=a.text;b.font=a.font;b.fontSize=a.fontSize;b.fontStyle=a.fontStyle;}
            else if(pair.Key is RawImage ra&&pair.Value is RawImage rb){rb.texture=ra.texture;rb.uvRect=ra.uvRect;}
            else if(pair.Key is Image ia&&pair.Value is Image ib)ib.sprite=ia.sprite;
        }
        foreach(var pair in signalButtons)if(pair.Key&&pair.Value)pair.Value.interactable=pair.Key.interactable;
    }
    void LateUpdate(){UpdateScanPresentation();if(open&&signalSurface)SyncSignalOverlay();}
    void DrawSignalInput()
    {
        SyncSignalOverlay();var ev=Event.current;
        if(!scanPresenting&&!cameraSettings&&!connectionSettings&&ev.type==EventType.MouseDown&&ev.button==0&&signalScreenRect.Contains(ev.mousePosition))
        {
            var logical=new Vector2((ev.mousePosition.x-signalScreenRect.x)/signalScreenRect.width*signalLayout.width,(ev.mousePosition.y-signalScreenRect.y)/signalScreenRect.height*signalLayout.height);
            var corners=new Vector3[4];foreach(var b in GetComponentsInChildren<Button>(false))if(b.interactable){((RectTransform)b.transform).GetWorldCorners(corners);var a=signalSurface.InverseTransformPoint(corners[0]);var c=signalSurface.InverseTransformPoint(corners[2]);var hit=new Rect(a.x-signalSurface.rect.xMin,signalSurface.rect.yMax-c.y,c.x-a.x,c.y-a.y);if(hit.Contains(logical)){b.onClick.Invoke();ev.Use();break;}}
        }
        // The settings modal is deliberately separate; credentials are never baked into the artwork.
        if(connectionSettings)GUI.ModalWindow(76323,new Rect((Screen.width-600)/2f,(Screen.height-390)/2f,600,390),DrawSignalConnection,"AOI 연결 설정");
        if(cameraSettings)GUI.ModalWindow(76322,new Rect((Screen.width-600)/2f,(Screen.height-390)/2f,600,390),DrawCameraSettings,"Jetson 실시간 영상 연결 · 8500");
        if(ev.type==EventType.KeyDown&&ev.keyCode==KeyCode.Escape){if(cameraSettings)cameraSettings=false;else if(connectionSettings)connectionSettings=false;else ToggleWindow();ev.Use();}
    }
    void DrawSignalConnection(int id)
    {
        var client=feed.GetComponent<AoiDirectClient>();GUI.Label(new Rect(18,34,565,28),"Jetson 검사 토큰 · AOI_UNITY_TOKEN · 현재 Play에서만 사용");
        tokenInput=GUI.PasswordField(new Rect(18,66,435,30),tokenInput,'*',2048);if(GUI.Button(new Rect(463,66,120,30),"붙여넣기"))tokenInput=(GUIUtility.systemCopyBuffer??"").Trim();
        if(GUI.Button(new Rect(18,108,180,32),"토큰 적용")){if(client&&!string.IsNullOrWhiteSpace(tokenInput)){client.SessionToken=tokenInput;tokenInput="";}Refresh();}
        GUI.Label(new Rect(208,110,375,30),client&&client.HasToken?"토큰 입력됨 · 검사 요청으로 인증 확인":"토큰 입력 대기");
        inspectCurrentCamera=true;GUI.Label(new Rect(18,152,565,28),"Jetson 8500 최신 프레임 번호 → 같은 Jetson 8400 검사 요청");
        GUI.Label(new Rect(18,191,565,54),client?client.Status:"Jetson 직접 검사 구성 대기");
        if(GUI.Button(new Rect(18,254,275,36),"Jetson 영상 연결 · 8500")){connectionSettings=false;photoView=2;cameraAddress=CameraStream.Address;cameraSettings=true;}
        if(GUI.Button(new Rect(303,254,280,36),"제품 결과 사진 보기")){connectionSettings=false;SetPhotoView(3);}
        GUI.Label(new Rect(18,305,565,30),"영상 8500 / 검사 8400 · 영상·검사 토큰 별도 · 토큰 저장 안 함");
        if(GUI.Button(new Rect(18,343,565,30),"닫기")){connectionSettings=false;tokenInput="";Refresh();}
    }
}
