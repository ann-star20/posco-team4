// Export the approved browser layout without approximating its static artwork.
const fs=require('fs'),path=require('path');
const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const project=path.resolve(__dirname,'../..');
const source='C:/Users/Administrator/.codex/visualizations/2026/09/15/01a0a2cf-d6e3-7090-8bf0-89e68a9cbb76/aoi-signal-workstation.html';
const out=path.join(project,'Assets/MOSFETInspection/Resources/AoiSignal');fs.mkdirSync(out,{recursive:true});
const fields={Pixels:'.viewer-head .pixels',Connection:'.head-right',Lot:'.session span:first-child strong',Product:'.session span:nth-child(2) strong',Replay:'.session .replay',StageTag:'.stage-tag',ImageCaption:'.photo-caption span:first-child',PhotoMode:'.photo-caption span:last-child',Verdict:'.decision-word',Class:'.decision-label strong',ClassCode:'.decision-label small',Completion:'.result-completion',Route:'.hold-line span',DetailCount:'.number-detected',Score:'.score',DefectIndex:'.defect-row .index',DefectTitle:'.defect-row strong',DefectCode:'.defect-row small',LocationCount:'.location-head span',CropTag:'.crop-tag',InspectionId:'.record-metadata b:nth-of-type(1)',ResultSource:'.record-metadata b:nth-of-type(2)',Storage:'.record-metadata b:nth-of-type(3)',Step:'.step-number',Message:'.command-state strong',CameraStatus:'.footer .status-group span:first-child b',JetsonStatus:'.footer .status-group span:nth-child(2) b',DatabaseStatus:'.footer .status-group span:nth-child(3) b',Provenance:'.footer>span',RecordCount:'.records-head span'};
const buttons={ViewInspection:'[data-nav="inspection"]',ViewHistory:'[data-nav="records"]',ConnectionSettings:'[data-nav="connection"]',PhotoProduct:'[data-view="product"]',PhotoFull:'[data-view="full"]',PhotoZoom:'[data-view="defect"]',DefectTab:'[data-tab="defect"]',ProductTab:'[data-tab="product"]',SelectDefect0:'.defect-row',RequestInspection:'.command-buttons button:first-child',SortProduct:'.command-buttons .primary'};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1024,height:1200},deviceScaleFactor:2});
 await page.setContent(fs.readFileSync(source,'utf8'));
 await page.locator(buttons.RequestInspection).evaluate(el=>{el.style.width=el.getBoundingClientRect().width+'px';el.textContent='검사';});
 await page.addStyleTag({content:'body{margin:0}.status-preview{display:none!important}'});
 const lucideDir='C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/lucide/dist/umd';
 await page.addScriptTag({path:path.join(lucideDir,'lucide.js')});await page.evaluate(()=>lucide.createIcons());
 const machine=page.locator('.machine');
 await machine.screenshot({path:path.join(out,'reference-ng.png')});
 const items=[];
 async function geometry(name,selector){return await page.locator(selector).evaluate((el,name)=>{const box=el.getBoundingClientRect(),root=document.querySelector('.machine').getBoundingClientRect(),s=getComputedStyle(el);return{name,x:box.x-root.x,y:box.y-root.y,w:box.width,h:box.height,fontSize:parseFloat(s.fontSize),font:s.fontFamily,color:s.color,bold:Number(s.fontWeight)>=600,text:el.textContent.trim(),align:s.textAlign,padLeft:parseFloat(s.paddingLeft),padTop:parseFloat(s.paddingTop),padRight:parseFloat(s.paddingRight),padBottom:parseFloat(s.paddingBottom)};},name);}
 for(const[name,selector]of Object.entries(fields))items.push(await geometry(name,selector));
 for(let i=0;i<6;i++){const selector='.records tbody td:nth-child('+(i+1)+')';fields['Recent'+i]=selector;items.push(await geometry('Recent'+i,selector));}
 for(const[name,selector]of Object.entries(buttons)){
  items.push(await geometry(name,selector));const button=page.locator(selector);
  if(name==='SelectDefect0')await button.evaluate(el=>el.querySelectorAll('*').forEach(x=>x.style.visibility='hidden'));
  for(const mode of['normal','active','disabled']){
   await button.evaluate((el,mode)=>{el.disabled=mode==='disabled';el.style.opacity=mode==='disabled'?'.55':'1';if(el.hasAttribute('aria-pressed'))el.setAttribute('aria-pressed',String(mode==='active'));if(el.hasAttribute('aria-selected'))el.setAttribute('aria-selected',String(mode==='active'));el.classList.toggle('active',mode==='active');},mode);
   await button.screenshot({path:path.join(out,name+'-'+mode+'.png')});
  }
  await button.evaluate(el=>{el.disabled=false;});
  if(name==='RequestInspection'){await button.evaluate(el=>{el.textContent='검사 중…';el.disabled=true;});await button.screenshot({path:path.join(out,'RequestInspection-busy.png')});}
 }
 for(const mode of['normal','disabled']){const el=page.locator(buttons.SortProduct);await el.evaluate((el,mode)=>{el.textContent='OK 분류 실행';el.disabled=mode==='disabled';el.style.opacity=mode==='disabled'?'.55':'1';},mode);await el.screenshot({path:path.join(out,'SortProductOK-'+mode+'.png')});}
 for(const word of['NG','OK','—']){
  await page.locator('.decision-word').evaluate((el,word)=>{el.textContent=word;el.style.color=word==='NG'?'#ff7970':word==='OK'?'#d1ed89':'#9aafaf';},word);
  await page.locator('.decision-word').screenshot({path:path.join(out,'Verdict-'+(word==='—'?'Wait':word)+'.png')});
 }
 // Restore the approved NG state before capturing the empty dynamic regions.
 await page.setContent(fs.readFileSync(source,'utf8'));await page.addStyleTag({content:'body{margin:0}.status-preview{display:none!important}'});
 await page.locator('.command-state small').evaluate(el=>el.textContent='검사 완료 후 판정에 따라 자동 분류합니다.');
 await page.addScriptTag({path:path.join(lucideDir,'lucide.js')});await page.evaluate(()=>lucide.createIcons());
 for(const[name,selector]of Object.entries({Photo:'.stage',Crop:'.crop-stage',Location:'.location',Decision:'.decision',Inspector:'.inspector',List:'.result-list',ProductPanel:'#signal-product-panel',DefectPanel:'#signal-defect-panel',Records:'.records'})){
  if(name==='ProductPanel'){await page.locator('[data-tab="product"]').click();items.push(await geometry(name,selector));await page.locator('[data-tab="defect"]').click();}else items.push(await geometry(name,selector));
 }
 await page.evaluate(({fields,buttons})=>{
  for(const selector of Object.values(fields)){const el=document.querySelector(selector);el.style.color='transparent';el.querySelectorAll('*').forEach(x=>x.style.color='transparent');}
  for(const selector of Object.values(buttons))document.querySelector(selector).style.visibility='hidden';
  document.querySelectorAll('.source-image').forEach(x=>x.style.visibility='hidden');
 },{fields,buttons});
 await machine.screenshot({path:path.join(out,'background.png')});
 // Inline sample spans need room for longer live values without moving their neighbors.
 for(const item of items){item.w+=({Product:360,CameraStatus:15,JetsonStatus:24,DatabaseStatus:40,CropTag:70}[item.name]||0);if(['DetailCount','LocationCount','PhotoMode'].includes(item.name)){const room=item.name==='PhotoMode'?45:30;item.x-=room;item.w+=room;item.align='right';}}
 const jetsonStatus=items.find(i=>i.name==='JetsonStatus');jetsonStatus.w=78;jetsonStatus.fontSize=8;
 const size=await machine.boundingBox();fs.writeFileSync(path.join(out,'layout.json'),JSON.stringify({width:size.width,height:size.height,items},null,2));
 await browser.close();console.log(JSON.stringify({out,width:size.width,height:size.height,items:items.length}));
})();
