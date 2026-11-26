"use strict";
const el=id=>document.getElementById(id);
let raw="", summary=null, local=false, held=false, previewDataset=null, previewRevision=0;
let chartDates=[], chartSeries=new Map();
function* csvRecords(text){
  const source=text.replace(/^\uFEFF/,"").replace(/\r\n?/g,"\n");
  let cells=[],field="",quoted=false,closed=false,started=false,line=1;
  for(let i=0;i<=source.length;i++){
    const eof=i===source.length, c=eof?"\n":source[i];
    if(quoted){
      if(eof)throw Error("第 "+line+" 行引号未闭合");
      if(c==='"'){
        if(source[i+1]==='"'){field+='"';i++}
        else{quoted=false;closed=true}
      }else{field+=c;if(c==="\n")line++}
      continue;
    }
    if(c===","||c==="\n"){
      if(c==="\n"){
        if(cells.length||started||line===1)yield {cells:[...cells,field],line};
        cells=[];line++;
      }else cells.push(field);
      field="";closed=false;started=false;
    }else if(closed)throw Error("第 "+line+" 行引号后有多余字符");
    else if(!started&&c==='"'){quoted=true;started=true}
    else{field+=c;started=true}
  }
}
function inspect(text,label){
  previewRevision++;previewDataset=null;el("save").textContent="存入本机研究项目";
  el("importStatus").textContent="";chartDates=[];chartSeries=new Map();el("chartPanel").hidden=true;
  raw="";summary=null;el("preview").replaceChildren();el("metrics").textContent="";el("export").disabled=el("save").disabled=true;
  try{
    const records=csvRecords(text), header=records.next().value?.cells||[];
    const fields=["date","symbol","adjusted_close"].map(x=>header.indexOf(x));
    if(header.length!==3||fields.includes(-1))throw Error("列名应为 date,symbol,adjusted_close");
    const series=new Map();
    const keys=new Set(),days=new Set(),symbols=new Set(),preview=[];
    for(const {cells,line} of records){
      const [d,s,p]=fields.map(n=>cells[n]||""), symbol=s.trim().toUpperCase();
      const numeric=p.trim().replace(/(?<=\d)_(?=\d)/g,"");
      const stamp=Date.parse(d+"T00:00:00Z");
      if(cells.length!==3||!/^\d{4}-\d{2}-\d{2}$/.test(d)||d.startsWith("0000")||!Number.isFinite(stamp)||new Date(stamp).toISOString().slice(0,10)!==d||!(/^[A-Z0-9][A-Z0-9.^_-]{0,31}$/).test(symbol)||!(/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i).test(numeric)||!Number.isFinite(+numeric)||+numeric<=0)throw Error("第 "+line+" 行格式或价格无效");
      if(keys.has(d+"|"+symbol))throw Error("第 "+line+" 行日期与品种重复");
      if(!series.has(symbol))series.set(symbol,new Map());
      series.get(symbol).set(d,+numeric);
      keys.add(d+"|"+symbol);days.add(d);symbols.add(symbol);if(preview.length<6)preview.push([d,symbol,p]);
    }
    if(!keys.size)throw Error("缺少行情记录");
    const dates=[...days].sort();summary={file:label,first:dates[0],last:dates.at(-1),records:keys.size,symbols:[...symbols],missing:days.size*symbols.size-keys.size};
    raw=text;el("info").textContent=label+" · "+summary.first+" 至 "+summary.last;
    el("metrics").textContent=keys.size+" 条记录　"+symbols.size+" 个品种　"+summary.missing+" 个缺失格";
    for(const [i,row] of [["交易日","品种","复权收盘价（USD）"],...preview].entries()){const tr=el("preview").insertRow();for(const val of row){const cell=document.createElement(i?"td":"th");cell.textContent=val;tr.append(cell)}}
    chartDates=dates;chartSeries=series;
    const select=el("chartSymbol");select.replaceChildren();
    for(const symbol of symbols){
      const option=document.createElement("option");option.value=option.textContent=symbol;select.append(option);
    }
    el("chartPanel").hidden=false;
    if(el("chartPanel").open)drawChart();
    el("export").disabled=false;el("save").disabled=!local||held;
  }catch(e){el("info").textContent="检查失败 · "+e.message}
}
el("file").onchange=async e=>{const file=e.target.files[0];if(file){if(file.size>5e6){inspect("","");el("info").textContent="文件超过 5 MB";return}inspect(await file.text(),file.name)}};
el("demo").onclick=()=>inspect("date,symbol,adjusted_close\n2025-01-02,DEMO,100\n2025-01-03,DEMO,101.5\n2025-01-06,DEMO,100.75","内置格式示例（合成数据）");
el("export").onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(summary,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="行情检查.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
async function api(action, body){
  const options=body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{signal:AbortSignal.timeout(4000)};
  let res;
  try{res=await fetch("/api/"+action,options)}
  catch{connectionLost();throw Error("本机服务无响应。请确认启动窗口仍在运行，再点击「重新连接」。")}
  const obj=await res.json();
  if(!res.ok)throw Error(obj.error||"请求失败");
  return obj;
}

function connectionLost(){
  local=false;
  el("mode").textContent="本机服务未连接";
  el("reconnect").hidden=false;
  updateActions();
}

function updateActions(){
  el("create").disabled=!local||held||!el("dataset").value;
  el("run").disabled=!local||held||!el("projects").value;
  el("save").disabled=!local||held||!raw;
  el("ibkrDownload").disabled=!local;
  el("rerunArchive").disabled=!local||held||!archive;
}

async function state(){
  const state=await api("state");
  if(state.platform!=="quant-local")throw Error("本机服务响应无效");
  local=true;
  el("reconnect").hidden=true;
  el("save").hidden=false;
  el("simulationNotice").hidden=true;
  el("practiceSection").hidden=false;
  setLedgers(state.ledgers||[]);
  el("tools").hidden=false;
  el("ibkrOffline").hidden=true;
  el("ibkrForm").hidden=false;
  el("mode").textContent="本机工作区";
  el("localInfo").textContent="创建项目后，可直接执行已保存的 Python 笔记。";
  el("savedData").hidden=!state.datasets.length;
  const replayDatasets=state.datasets.filter(key=>!key.startsWith("csv-"));
  for(const [id,items] of [["dataset",state.datasets],["savedDataset",state.datasets],["replayDataset",replayDatasets],["projects",state.projects]]){
    const select=el(id), old=select.value;
    select.replaceChildren(...items.map(key=>new Option(key,key)));
    if(items.includes(old))select.value=old;
  }
  el("replayRun").disabled=!replayDatasets.length;
  if(!replayDatasets.length)el("replayStatus").textContent="当前没有支持整股演练的历史行情快照。";
  el("noDataset").hidden=Boolean(state.datasets.length);
  updateActions();
}

async function connect(){
  el("mode").textContent="正在连接本机…";
  el("reconnect").disabled=true;
  try{await state();void loadHistory()}
  catch{connectionLost();updateActions()}
  finally{el("reconnect").disabled=false}
}

async function act(action,body){if(held)return;held=true;updateActions();el("result").textContent="正在执行…";
try{const r=await api(action,body);await state();if(r.dataset){el("dataset").value=r.dataset;el("importStatus").textContent=r.message;location.hash="research"}if(r.project){el("projects").value=r.project;syncEditor()}el("result").textContent=r.message}catch(e){el("result").textContent="操作失败 · "+e.message;if(action==="import")el("importStatus").textContent=el("result").textContent}finally{held=false;updateActions();void loadHistory()}}
el("create").onclick=()=>act("create",{name:el("name").value,dataset:el("dataset").value});el("run").onclick=()=>{if(draft?.name===el("projects").value && draft.code!==el("code").value){el("result").textContent="请先保存分析代码，再运行项目。";return}act("run",{name:el("projects").value})};el("save").onclick=()=>{
  if(!previewDataset){act("import",{csv:raw});return}
  el("dataset").value=previewDataset;
  updateActions();
  location.hash="research";
};
el("loadDataset").onclick=async()=>{
  const key=el("savedDataset").value;
  const revision=previewRevision;
  el("loadDataset").disabled=true;
  el("importStatus").textContent="正在读取本地数据…";
  try{
    const result=await api("dataset",{dataset:key});
    if(revision!==previewRevision || key!==el("savedDataset").value)return;
    inspect(result.csv,key==="base"?"基础行情快照":key);
    if(summary){
      previewDataset=key;
      el("save").textContent="选入研究项目";
    }
  }catch(e){
    if(revision===previewRevision)el("importStatus").textContent="读取失败 · "+e.message;
  }finally{el("loadDataset").disabled=false}
};
el("reconnect").onclick=connect;

let version=0, archive=null;
async function loadHistory(){
  const seq=++version, name=el("projects").value;
  const info=el("projectData"), preview=el("projectPreview");
  info.hidden=!name;
  info.textContent=name?(local?"正在读取项目…":"请重新连接本机服务。"):"";
  preview.hidden=true;
  archive=null;resetRunChart();el("runTables").replaceChildren();el("downloadRun").disabled=true;el("rerunArchive").disabled=true;el("archives").replaceChildren();
  el("past").textContent=name?"读取中…":"尚无项目";
  if(!name || !local)return;
  try{
    const {runs,dataset}=await api("history",{name});
    if(seq!==version)return;
    const status=r=>r.status==="success"?"成功":"失败";
    const last=runs[0];
    const date=last?.id.replace(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2}).*$/,"$1-$2-$3 $4:$5:$6 UTC");
    info.textContent="项目数据 · "+(dataset==="base"?"基础行情快照":dataset)
      +" ｜ "+(last?"最近运行 "+status(last)+" · "+date:"尚无运行记录");
    const source=el("savedDataset");
    if([...source.options].some(option=>option.value===dataset)){
      preview.hidden=false;
      preview.onclick=()=>{
        source.value=dataset;
        location.hash="data";
        el("loadDataset").click();
      };
    }
    el("archives").replaceChildren(...runs.map(r=>new Option(r.id+" · "+status(r),r.id)));
    if(!runs.length)el("past").textContent="该项目尚无归档。";
    else if(el("archivePanel").open)await loadArchive();
  }catch(e){
    if(seq===version){info.textContent="无法读取项目 · "+e.message;el("past").textContent=e.message}
  }
}
async function loadArchive(){
  const seq=++version,name=el("projects").value,id=el("archives").value;
  archive=null;resetRunChart();el("runTables").replaceChildren();el("downloadRun").disabled=true;el("rerunArchive").disabled=true;el("past").textContent="读取中…";
  try{
    const r=await api("archive",{name,id});
    if(seq!==version)return;
    archive={id,name,file:name+"-"+id+".ipynb",text:r.notebook};
    el("past").textContent=r.message;el("downloadRun").disabled=false;updateActions();
    const tables=r.tables||[];
    el("runChartPanel").hidden=!tables.length;
    el("runChartFile").replaceChildren(...tables.map(file=>new Option(file,file)));
    for(const table of r.tables||[]){
      const button=document.createElement("button");
      button.textContent="下载 "+table;
      button.onclick=async()=>{
        button.disabled=true;
        try{
          const result=await api("run-table",{name,id,table});
          if(seq!==version)return;
          const url=URL.createObjectURL(new Blob([result.csv],{type:"text/csv;charset=utf-8"}));
          const link=document.createElement("a");
          link.href=url;link.download=table;link.click();
          setTimeout(()=>URL.revokeObjectURL(url),1000);
        }catch(e){if(seq===version)el("past").textContent="下载失败 · "+e.message}
        finally{button.disabled=false}
      };
      el("runTables").append(button);
    }
  }catch(e){if(seq===version)el("past").textContent=e.message}
}
el("archivePanel").ontoggle=()=>{if(el("archivePanel").open)loadHistory()};
el("projects").onchange=loadHistory;
el("archives").onchange=loadArchive;
el("rerunArchive").onclick=()=>{if(archive)act("rerun",{name:archive.name,id:archive.id})};
el("downloadRun").onclick=()=>{
  if(!archive)return;
  const url=URL.createObjectURL(new Blob([archive.text],{type:"application/x-ipynb+json"}));
  const a=document.createElement("a");a.href=url;a.download=archive.file;a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
};

let draft=null;
function syncEditor(){
  const matched=draft && draft.name===el("projects").value;
  el("code").disabled=!matched;
  el("storeCode").disabled=!matched || !el("code").value.trim() || el("code").value===draft?.code;
}
el("projects").addEventListener("change",syncEditor);
el("code").oninput=syncEditor;
el("loadCode").onclick=async()=>{
  const name=el("projects").value;
  if(!name){el("editStatus").textContent="请先创建项目。";return}
  if(draft && draft.code!==el("code").value && !confirm("放弃未保存的草稿并重新载入？"))return;
  try{
    const r=await api("editor",{name});
    if(name!==el("projects").value)return;
    draft={name,...r};el("code").value=r.code;
    el("editStatus").textContent="正在编辑 · "+name;syncEditor();
  }catch(e){el("editStatus").textContent=e.message}
};
el("storeCode").onclick=async()=>{
  const current=draft,code=el("code").value;
  if(!current || current.name!==el("projects").value)return;
  try{
    const r=await api("save-cell",{name:current.name,revision:current.revision,code});
    if(draft!==current)return;
    draft={name:current.name,revision:r.revision,code};
    el("editStatus").textContent="已保存到 "+current.name+"。点击「运行代码」查看结果。";syncEditor();
  }catch(e){el("editStatus").textContent=e.message}
};

function drawSeries(canvas, dates, quotes, unit){
  const width=canvas.clientWidth,height=190,scale=window.devicePixelRatio||1;
  if(!width)return;
  canvas.width=Math.round(width*scale);canvas.height=Math.round(height*scale);
  const ctx=canvas.getContext("2d");
  ctx.scale(scale,scale);
  let min=Infinity,max=-Infinity;
  for(const value of quotes.values()){min=Math.min(min,value);max=Math.max(max,value)}
  const fmt=v=>v.toLocaleString("en-US",{maximumSignificantDigits:8});
  const first=dates[0],last=dates.at(-1),start=Date.parse(first),end=Date.parse(last);
  const left=8,right=width-8,top=28,bottom=height-28;
  const x=d=>end===start?width/2:left+(right-left)*(Date.parse(d)-start)/(end-start);
  const y=v=>max===min?(top+bottom)/2:bottom-(bottom-top)*((v-min)/(max-min));
  ctx.font="12px sans-serif";ctx.fillStyle="#426354";ctx.fillText(unit+" · "+fmt(max),left,15);
  ctx.strokeStyle="#d1ded6";ctx.beginPath();
  for(const row of [top,(top+bottom)/2,bottom]){ctx.moveTo(left,row);ctx.lineTo(right,row)}
  ctx.stroke();
  ctx.fillText(fmt(min),left,bottom-4);
  ctx.fillText(first,left,height-6);
  if(first!==last){ctx.textAlign="right";ctx.fillText(last,right,height-6)}
  ctx.strokeStyle=ctx.fillStyle="#13775a";ctx.lineWidth=2;ctx.beginPath();
  let previous=false;
  for(let i=0;i<dates.length;i++){
    const d=dates[i],value=quotes.get(d);
    if(value===undefined){previous=false;continue}
    const px=x(d),py=y(value);
    if(previous){ctx.lineTo(px,py)}else{ctx.moveTo(px,py)}
    if(!previous && !quotes.has(dates[i+1]))ctx.fillRect(px-2,py-2,4,4);
    previous=true;
  }
  ctx.stroke();
  return {min:fmt(min),max:fmt(max)};
}

let runCurve=null;
function clearRunCurve(){
  runCurve=null;
  el("runChart").hidden=true;
  el("runChartStatus").textContent="";
}
function resetRunChart(){
  clearRunCurve();
  el("runChartPanel").hidden=true;
}

function readRunCurve(csv){
  const records=csvRecords(csv);
  const columns=records.next().value?.cells||[];
  const nav=columns.indexOf("nav"), drawdown=columns.indexOf("drawdown");
  if(nav<1 || drawdown<1)throw Error("此表缺少净值（nav）或回撤（drawdown）列。");
  const curve=[];
  for(const {cells,line} of records){
    const [day]=cells;
    const stamp=Date.parse(day+"T00:00:00Z");
    const value=Number(cells[nav]), dd=Number(cells[drawdown]);
    if(!Number.isFinite(stamp) || new Date(stamp).toISOString().slice(0,10)!==day
      || (curve.length && day<=curve.at(-1)[0]) || !cells[drawdown]?.trim()
      || !Number.isFinite(value) || value<=0 || !Number.isFinite(dd) || dd>0 || dd< -1){
      throw Error("第 "+line+" 行的日期、净值或回撤无效。");
    }
    curve.push([day,value,dd*100]);
  }
  if(!curve.length)throw Error("归档表格没有数据行。");
  return curve;
}

function drawRunCurve(){
  if(!runCurve || el("runChartPanel").hidden || !el("runChartPanel").open)return;
  const metric=Number(el("runChartMetric").value);
  drawSeries(el("runChart"),runCurve.map(point=>point[0]),
    new Map(runCurve.map(point=>[point[0],point[metric]])),metric===1?"USD":"%");
}

el("loadRunChart").onclick=async()=>{
  if(!archive)return;
  const seq=version, {name,id}=archive, table=el("runChartFile").value;
  clearRunCurve();
  const button=el("loadRunChart");
  button.disabled=true;
  el("runChartStatus").textContent="正在读取归档…";
  try{
    const {csv}=await api("run-table",{name,id,table});
    if(seq!==version || table!==el("runChartFile").value)return;
    runCurve=readRunCurve(csv);
    const trough=runCurve.reduce((low,point)=>point[2]<low[2]?point:low);
    el("runChartStatus").textContent=runCurve[0][0]+" 至 "+runCurve.at(-1)[0]+" · "+runCurve.length
      +" 个交易日 · 最大回撤 "+trough[2].toFixed(2)+"%"
      +(trough[2]<0?"（谷底 "+trough[0]+"）":"");
    el("runChart").hidden=false;
    drawRunCurve();
  }catch(e){if(seq===version && table===el("runChartFile").value)el("runChartStatus").textContent=e.message}
  finally{button.disabled=false}
};
el("runChartFile").onchange=clearRunCurve;
el("runChartMetric").onchange=drawRunCurve;
el("runChartPanel").ontoggle=drawRunCurve;
el("archivePanel").addEventListener("toggle",drawRunCurve);
window.addEventListener("resize",drawRunCurve);

function drawChart(){
  const symbol=el("chartSymbol").value;
  const quotes=chartSeries.get(symbol);
  if(!quotes || !el("chartPanel").open || el("chartPanel").hidden)return;
  const range=drawSeries(el("priceChart"),chartDates,quotes,"USD");
  if(!range)return;
  el("chartSummary").textContent=symbol+" · "+quotes.size+" 个观测 · 最低 "+range.min
    +" / 最高 "+range.max+" USD · 缺失 "+(chartDates.length-quotes.size)+" 个日期";
}

function drawLedger(){
  const panel=el("ledgerChartPanel");
  if(!audited || !panel.open || panel.hidden)return;
  const metric=Number(el("ledgerMetric").value);
  const dates=audited.curve.map(point=>point[0]);
  const values=new Map(audited.curve.map(point=>[point[0],Number(point[metric])]));
  drawSeries(el("ledgerChart"),dates,values,metric===1?"USD":"%");
}

el("chartPanel").ontoggle=drawChart;
el("chartSymbol").onchange=drawChart;
window.addEventListener("resize",drawChart);
el("ledgerChartPanel").ontoggle=drawLedger;
el("auditPanel").ontoggle=drawLedger;
el("ledgerMetric").onchange=drawLedger;
window.addEventListener("resize",drawLedger);

let audited=null, auditVersion=0;
function resetAudit(){
  audited=null;auditVersion++;
  el("orders").replaceChildren();
  el("ledgerSummary").textContent="";
  el("ledgerChartPanel").hidden=true;
  el("ledgerDownloads").replaceChildren();
  const ready=Boolean(el("ledgers").value);
  el("audit").disabled=!ready;
  el("refused").disabled=true;
  el("balance").textContent=ready?"请选择账本并运行核对。":"本机尚无模拟账本。";
}
function setLedgers(entries){
  const select=el("ledgers"), old=select.value;
  el("ledgerSection").hidden=false;
  select.replaceChildren(...entries.map(([label,id])=>new Option(label,id)));
  if(entries.some(([,id])=>id===old))select.value=old;
  if(!audited || select.value!==old)resetAudit();
}
function renderOrders(){
  const table=el("orders");table.replaceChildren();
  if(!audited)return;
  const filtered=audited.orders.filter(o=>!el("refused").checked||o.status!=="filled");
  const rows=[["日期","品种","股数","参考价 USD","状态","费用 USD"],...filtered.map(o=>
    [o.date,o.symbol,o.signed_shares,o.fill_reference_close,o.status==="filled"?"成交":"资金不足",Number(o.fee).toFixed(4)])];
  for(const [i,cols] of rows.entries()){
    const row=table.insertRow();for(const value of cols){const c=document.createElement(i?"td":"th");c.textContent=value;row.append(c)}
  }
  if(!filtered.length){const cell=table.insertRow().insertCell();cell.colSpan=6;cell.textContent="没有符合条件的委托。"}
}
el("ledgers").onchange=resetAudit;
el("refused").onchange=renderOrders;
el("audit").onclick=async()=>{
  resetAudit();const seq=auditVersion;
  el("audit").disabled=true;el("balance").textContent="正在逐日核对…";
  try{
    const data=await api("ledger",{id:el("ledgers").value});
    if(seq!==auditVersion)return;
    audited=data;const a=data.account;
    el("balance").textContent="对账通过 · "+a.date+" · 现金 "+Number(a.cash).toFixed(2)+" USD · SPY "+a.spy_shares+" 股 · BIL "+a.bil_shares+" 股 · 总市值（分红单列） "+Number(a.price_only_equity).toFixed(2)+" USD";
    const stats=data.summary;
    el("ledgerSummary").textContent=stats.first+" 至 "+a.date+" · "+stats.sessions+" 个交易日 · 期初 "
      +Number(stats.capital).toFixed(2)+" USD · 价格口径收益 "+Number(stats.return_pct).toFixed(2)
      +"% · 最大回撤 "+Number(stats.drawdown_pct).toFixed(2)+"%"
      +(stats.trough_date?"（谷底 "+stats.trough_date+"）":"");
    el("ledgerChartPanel").hidden=false;
    drawLedger();
    for(const [index,file] of data.files.entries()){
      const button=document.createElement("button");
      button.textContent=index===0?"下载逐日账户 CSV":"下载委托 CSV";
      button.onclick=()=>{
        const url=URL.createObjectURL(new Blob([file.csv],{type:"text/csv;charset=utf-8"}));
        const link=document.createElement("a");
        link.href=url;link.download=file.name;link.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
      };
      el("ledgerDownloads").append(button);
    }
    el("refused").disabled=false;renderOrders();
  }catch(e){if(seq===auditVersion)el("balance").textContent="核对失败 · "+e.message}
  finally{if(seq===auditVersion)el("audit").disabled=false}
};

el("replayRun").onclick=async()=>{
  const button=el("replayRun"), status=el("replayStatus");
  button.disabled=true;
  status.textContent="正在生成并核对账本…";
  try{
    const {id}=await api("replay",{
      dataset:el("replayDataset").value,
      capital:el("replayCapital").value.trim(),
      method:el("replayMethod").value
    });
    await state();
    el("ledgers").value=id;
    el("auditPanel").open=true;
    el("audit").click();
    status.textContent="新账本已保存。";
  }catch(e){status.textContent="演练失败 · "+e.message}
  finally{button.disabled=!el("replayDataset").value}
};

let practiceBusy=false, pendingTicket=null;
const usd=cents=>(cents/100).toFixed(2);
const orderFields=["ticker","side","amount","price"];
let ticketRevision=0;
function clearTradePreview(){
  ticketRevision++;
  el("tradePreview").hidden=true;
}
for(const field of orderFields)el(field).addEventListener("input",clearTradePreview);
function renderMarks(holdings){
  const list=el("marks");
  const previous=new Map([...list.querySelectorAll("input")].map(input=>[input.dataset.symbol,input.value]));
  list.replaceChildren();
  el("markPanel").hidden=!Object.keys(holdings).length;
  el("markResult").textContent="";
  for(const symbol of Object.keys(holdings)){
    const label=document.createElement("label");
    label.textContent=symbol+" 每股参考价（USD）";
    const input=document.createElement("input");
    input.inputMode="decimal";
    input.dataset.symbol=symbol;
    input.value=previous.get(symbol)||"";
    label.append(input);
    list.append(label);
  }
}

let batchVersion=0;
async function showPracticeBatch(batch_id){
  const seq=++batchVersion;
  el("batchDetail").hidden=false;
  el("batchSummary").textContent="正在读取批次…";
  el("batchSource").textContent="";
  try{
    const batch=await api("practice",{action:"batch",batch_id});
    if(seq!==batchVersion)return;
    const before=batch.cash_before===null?"":" · 期初现金 "+usd(batch.cash_before)+" USD";
    el("batchSummary").textContent="调仓 "+batch.batch_id.slice(0,8)+" · "+batch.utc+" UTC · "+batch.orders
      +" 笔"+before+" · 期末现金 "+usd(batch.cash_after)+" USD · 费用 "+usd(batch.fee)+" USD";
    el("batchSource").textContent=batch.source_csv||"此历史批次没有保存原始目标仓位。";
  }catch(e){if(seq===batchVersion)el("batchSummary").textContent="读取失败 · "+e.message}
}

async function practice(action){
  if(practiceBusy)return;
  practiceBusy=true;el("openAccount").disabled=el("submitTrade").disabled=el("previewTrade").disabled=el("exportTrades").disabled=el("valueAccount").disabled=true;
  try{
    let body={action};
    if(action==="open")body.capital=el("capital").value.trim();
    if(action==="trade"||action==="preview"){
      Object.assign(body,{symbol:el("ticker").value,side:el("side").value,quantity:el("amount").value,price:el("price").value.trim()});
      if(action==="trade"){
        const signature=JSON.stringify(body);
        if(!pendingTicket||pendingTicket.signature!==signature)pendingTicket={signature,token:crypto.randomUUID()};
        body.token=pendingTicket.token;
      }
    }
    if(action!=="export")clearTradePreview();
    const revision=ticketRevision;
    if(action==="valuation"){
      const inputs=[...el("marks").querySelectorAll("input")];
      body.marks=Object.fromEntries(inputs.map(input=>[input.dataset.symbol,input.value.trim()]));
      const data=await api("practice",body);
      if(inputs.some(input=>body.marks[input.dataset.symbol]!==input.value.trim()))return;
      el("markResult").textContent="持仓市值 "+usd(data.market_value)+" USD · 未实现盈亏 "+usd(data.unrealized_pnl)
        +" USD · 账户总值 "+usd(data.equity)+" USD · 累计盈亏 "+usd(data.total_pnl)+" USD";
      return;
    }
    const data=await api("practice",body);
    if(action==="export"){
      const url=URL.createObjectURL(new Blob(["\uFEFF",data.csv],{type:"text/csv;charset=utf-8"}));
      const link=document.createElement("a");
      link.href=url;
      link.download="practice-orders.csv";
      link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
      el("practiceMsg").textContent="已导出 "+data.count+" 笔委托";
      return;
    }
    if(action==="preview"){
      if(revision!==ticketRevision)return;
      const preview=el("tradePreview");
      const expected=data.status==="成交"?"预计成交":"预计拒单（"+data.status+"）";
      preview.textContent=expected+" · 委托金额 "+usd(data.value)+" USD · 费用 "+usd(data.fee)
        +" USD · 预计现金 "+usd(data.cash)+" USD · "+data.symbol+" "+data.shares+" 股";
      preview.hidden=false;
      return;
    }
    if(action==="trade")pendingTicket=null;
    el("practiceOpen").hidden=data.open;el("ticket").hidden=!data.open;
    el("practiceMsg").textContent=action==="trade"?"委托结果 · "+data.outcome:"";
    if(!data.open)return;
    renderMarks(data.holdings);
    clearPlan();
    const holdings=Object.entries(data.holdings).map(([s,q])=>s+" "+q+" 股").join("，")||"空仓";
    el("positions").textContent="现金 "+usd(data.cash)+" USD · "+holdings;
    if(data.audit){
      const a=data.audit, baseline=a.origin==="inferred"?"旧账本推算期初":"期初本金";
      el("positions").textContent+=" ｜ "+baseline+" "+usd(a.capital)+" USD · 已核对 "+a.count+" 笔 · 累计费用 "+usd(a.fees)+" USD";
      el("practicePnl").textContent="已实现盈亏（FIFO、含费用） "+usd(a.realized_pnl)+" USD · 剩余持仓成本 "+usd(a.open_cost)+" USD";
    }
    const table=el("trades");table.replaceChildren();
    batchVersion++;el("batchDetail").hidden=true;
    const header=["时间 UTC","品种","股数","价格 USD","费用 USD","结果","调仓批次"];
    const head=table.insertRow();
    for(const label of header){
      const cell=document.createElement("th");cell.textContent=label;head.append(cell);
    }
    for(const order of data.orders){
      const row=table.insertRow();
      for(const value of [order.time,order.symbol,order.qty,usd(order.price),usd(order.fee),order.status]){
        row.insertCell().textContent=value;
      }
      const cell=row.insertCell();
      if(order.batch_id){
        const button=document.createElement("button");
        button.textContent=order.batch_id.slice(0,8);
        button.title="查看调仓草案";
        button.onclick=()=>showPracticeBatch(order.batch_id);
        cell.append(button);
      }
    }
  }catch(e){el(action==="valuation"?"markResult":"practiceMsg").textContent="操作失败 · "+e.message}
  finally{practiceBusy=false;el("openAccount").disabled=el("submitTrade").disabled=el("previewTrade").disabled=el("exportTrades").disabled=el("valueAccount").disabled=false}
}
el("practicePanel").ontoggle=()=>{if(el("practicePanel").open)practice("view")};
el("openAccount").onclick=()=>practice("open");
el("submitTrade").onclick=()=>practice("trade");
el("previewTrade").onclick=()=>practice("preview");
el("exportTrades").onclick=()=>practice("export");
el("marks").oninput=()=>{el("markResult").textContent=""};
el("valueAccount").onclick=()=>practice("valuation");

let planVersion=0, pendingPlan=null;
function clearPlan(){
  planVersion++;pendingPlan=null;el("recordPlan").disabled=true;
  el("planStatus").textContent="";
  el("planRows").replaceChildren();
}
el("planCsv").oninput=clearPlan;
el("planRun").onclick=async()=>{
  clearPlan();
  const seq=planVersion, button=el("planRun");
  button.disabled=true;
  el("planStatus").textContent="正在核对练习账户…";
  try{
    const csv=el("planCsv").value;
    const result=await api("order-plan",{csv});
    if(seq!==planVersion)return;
    el("planStatus").textContent="预计现金 "+usd(result.projected_cash_cents)+" USD · 费用 "
      +usd(result.total_fee_cents)+" USD · "+result.orders.length+" 笔草案";
    if(result.orders.length){
      pendingPlan={csv,count:result.count,revision:result.revision};
      el("recordPlan").disabled=false;
    }
    const bySymbol=new Map(result.orders.map(order=>[order.symbol,order]));
    const rows=[["品种","目标股数","预计股数","买卖股数","费用 USD"]];
    for(const [symbol,target] of Object.entries(result.target_shares)){
      const order=bySymbol.get(symbol);
      rows.push([symbol,target,result.holdings[symbol],order?.signed_shares||0,usd(order?.fee_cents||0)]);
    }
    for(const [i,values] of rows.entries()){
      const row=el("planRows").insertRow();
      for(const value of values){
        const cell=document.createElement(i?"td":"th");
        cell.textContent=value;
        row.append(cell);
      }
    }
  }catch(e){if(seq===planVersion)el("planStatus").textContent="计算失败 · "+e.message}
  finally{button.disabled=false}
};

el("recordPlan").onclick=async()=>{
  if(!pendingPlan || practiceBusy)return;
  const preview=pendingPlan;
  clearPlan();
  el("planStatus").textContent="正在记录模拟委托…";
  el("planRun").disabled=true;
  try{
    const result=await api("practice",{action:"record-plan",...preview});
    await practice("view");
    el("planStatus").textContent="已记录 "+result.recorded+" 笔模拟委托 · 批次 "+result.batch_id.slice(0,8)+"。";
  }catch(e){el("planStatus").textContent="记录失败 · "+e.message}
  finally{el("planRun").disabled=false}
};

el("ibkrForm").onsubmit=async event=>{
  event.preventDefault();
  const button=el("ibkrDownload"), status=el("ibkrStatus");
  button.disabled=true;
  status.textContent="正在生成委托文件…";
  try{
    const ticket=await api("ibkr-ticket",{
      symbol:el("ibkrSymbol").value,
      primary_exchange:el("ibkrPrimary").value,
      side:el("ibkrSide").value,
      quantity:el("ibkrQty").value.trim(),
      price:el("ibkrPrice").value.trim()
    });
    const url=URL.createObjectURL(new Blob([ticket.csv],{type:"text/csv;charset=utf-8"}));
    const link=document.createElement("a");
    link.href=url;link.download=ticket.filename;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    status.textContent="已生成文件。请到 TWS 导入、核对并确认发送。";
  }catch(e){status.textContent="生成失败 · "+e.message}
  finally{button.disabled=!local}
};

function navigate(){
  const slug=location.hash.slice(1);
  const page=["data","research","simulation","orders"].includes(slug)?slug:"data";
  for(const link of document.querySelectorAll("nav [data-page]")){
    const current=link.dataset.page===page;
    el(link.dataset.page+"Page").hidden=!current;
    if(current)link.setAttribute("aria-current","page");
    else link.removeAttribute("aria-current");
  }
  if(page==="research")requestAnimationFrame(drawRunCurve);
  if(page==="simulation")requestAnimationFrame(drawLedger);
  if(page==="data" && el("chartPanel").open)requestAnimationFrame(drawChart);
}
window.addEventListener("hashchange",navigate);
navigate();

if(["127.0.0.1","localhost"].includes(location.hostname))connect();
