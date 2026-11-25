"use strict";
const el=id=>document.getElementById(id);
let raw="", summary=null, local=false, held=false;
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
async function api(action,body){const res=await fetch("/api/"+action,body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{});const obj=await res.json();if(!res.ok)throw Error(obj.error||"请求失败");return obj}
async function state(){const s=await api("state");if(s.platform!=="quant-local")return;local=true;el("save").hidden=false;el("simulationNotice").hidden=true;el("practiceSection").hidden=false;setLedgers(s.ledgers||[]);el("tools").hidden=false;el("mode").textContent="本机工作区";el("localInfo").textContent="创建项目后，可直接执行已保存的 Python 笔记。";
for(const [id,items] of [["dataset",s.datasets],["projects",s.projects]]){const old=el(id).value;el(id).replaceChildren(...items.map(x=>new Option(x,x)));if(items.includes(old))el(id).value=old}el("run").disabled=!s.projects.length;el("save").disabled=!raw}
async function act(action,body){if(held)return;held=true;for(const id of ["create","run","save"])el(id).disabled=true;el("result").textContent="正在执行…";
try{const r=await api(action,body);await state();if(r.dataset){el("dataset").value=r.dataset;el("importStatus").textContent=r.message;location.hash="research"}if(r.project){el("projects").value=r.project;syncEditor()}el("result").textContent=r.message}catch(e){el("result").textContent="操作失败 · "+e.message;if(action==="import")el("importStatus").textContent=el("result").textContent}finally{if(el("archivePanel").open)loadHistory();held=false;el("create").disabled=false;el("run").disabled=!el("projects").options.length;el("save").disabled=!raw}}
el("create").onclick=()=>act("create",{name:el("name").value,dataset:el("dataset").value});el("run").onclick=()=>{if(draft?.name===el("projects").value && draft.code!==el("code").value){el("result").textContent="请先保存分析代码，再运行项目。";return}act("run",{name:el("projects").value})};el("save").onclick=()=>act("import",{csv:raw});
if(["127.0.0.1","localhost"].includes(location.hostname))state().catch(()=>{});

let version=0, archive=null;
async function loadHistory(){
  const seq=++version, name=el("projects").value;
  archive=null;el("downloadRun").disabled=true;el("archives").replaceChildren();
  el("past").textContent=name?"读取中…":"尚无项目";
  if(!name)return;
  try{
    const {runs}=await api("history",{name});
    if(seq!==version)return;
    el("archives").replaceChildren(...runs.map(r=>new Option(r.id+" · "+(r.status==="success"?"成功":"失败"),r.id)));
    if(runs.length)await loadArchive();else el("past").textContent="该项目尚无归档。";
  }catch(e){if(seq===version)el("past").textContent=e.message}
}
async function loadArchive(){
  const seq=++version,name=el("projects").value,id=el("archives").value;
  archive=null;el("downloadRun").disabled=true;el("past").textContent="读取中…";
  try{
    const r=await api("archive",{name,id});
    if(seq!==version)return;
    archive={file:name+"-"+id+".ipynb",text:r.notebook};
    el("past").textContent=r.message;el("downloadRun").disabled=false;
  }catch(e){if(seq===version)el("past").textContent=e.message}
}
el("archivePanel").ontoggle=()=>{if(el("archivePanel").open)loadHistory()};
el("projects").onchange=()=>{if(el("archivePanel").open)loadHistory()};
el("archives").onchange=loadArchive;
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

function drawChart(){
  const canvas=el("priceChart"), symbol=el("chartSymbol").value;
  const quotes=chartSeries.get(symbol);
  if(!quotes || !el("chartPanel").open || el("chartPanel").hidden)return;
  const width=canvas.clientWidth,height=190,scale=window.devicePixelRatio||1;
  if(!width)return;
  canvas.width=Math.round(width*scale);canvas.height=Math.round(height*scale);
  const ctx=canvas.getContext("2d");
  ctx.scale(scale,scale);
  let min=Infinity,max=-Infinity;
  for(const value of quotes.values()){min=Math.min(min,value);max=Math.max(max,value)}
  const fmt=v=>v.toLocaleString("en-US",{maximumSignificantDigits:8});
  const first=chartDates[0],last=chartDates.at(-1),start=Date.parse(first),end=Date.parse(last);
  const left=8,right=width-8,top=28,bottom=height-28;
  const x=d=>end===start?width/2:left+(right-left)*(Date.parse(d)-start)/(end-start);
  const y=v=>max===min?(top+bottom)/2:bottom-(bottom-top)*((v-min)/(max-min));
  ctx.font="12px sans-serif";ctx.fillStyle="#426354";ctx.fillText("USD · "+fmt(max),left,15);
  ctx.strokeStyle="#d1ded6";ctx.beginPath();
  for(const row of [top,(top+bottom)/2,bottom]){ctx.moveTo(left,row);ctx.lineTo(right,row)}
  ctx.stroke();
  ctx.fillText(first,left,height-6);
  if(first!==last){ctx.textAlign="right";ctx.fillText(last,right,height-6)}
  ctx.strokeStyle=ctx.fillStyle="#13775a";ctx.lineWidth=2;ctx.beginPath();
  let previous=false;
  for(let i=0;i<chartDates.length;i++){
    const d=chartDates[i],value=quotes.get(d);
    if(value===undefined){previous=false;continue}
    const px=x(d),py=y(value);
    if(previous){ctx.lineTo(px,py)}else{ctx.moveTo(px,py)}
    if(!previous && !quotes.has(chartDates[i+1]))ctx.fillRect(px-2,py-2,4,4);
    previous=true;
  }
  ctx.stroke();
  el("chartSummary").textContent=symbol+" · "+quotes.size+" 个观测 · 最低 "+fmt(min)+" / 最高 "+fmt(max)+" USD · 缺失 "+(chartDates.length-quotes.size)+" 个日期";
}
el("chartPanel").ontoggle=drawChart;
el("chartSymbol").onchange=drawChart;
window.addEventListener("resize",drawChart);

let audited=null, auditVersion=0;
function resetAudit(){
  audited=null;auditVersion++;
  el("orders").replaceChildren();
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
    el("refused").disabled=false;renderOrders();
  }catch(e){if(seq===auditVersion)el("balance").textContent="核对失败 · "+e.message}
  finally{if(seq===auditVersion)el("audit").disabled=false}
};

let practiceBusy=false, pendingTicket=null;
const usd=cents=>(cents/100).toFixed(2);
async function practice(action){
  if(practiceBusy)return;
  practiceBusy=true;el("openAccount").disabled=el("submitTrade").disabled=true;
  try{
    let body={action};
    if(action==="open")body.capital=el("capital").value.trim();
    if(action==="trade"){
      Object.assign(body,{symbol:el("ticker").value,side:el("side").value,quantity:el("amount").value,price:el("price").value.trim()});
      const signature=JSON.stringify(body);
      if(!pendingTicket||pendingTicket.signature!==signature)pendingTicket={signature,token:crypto.randomUUID()};
      body.token=pendingTicket.token;
    }
    const data=await api("practice",body);
    if(action==="trade")pendingTicket=null;
    el("practiceOpen").hidden=data.open;el("ticket").hidden=!data.open;
    el("practiceMsg").textContent=action==="trade"?"委托结果 · "+data.outcome:"";
    if(!data.open)return;
    const holdings=Object.entries(data.holdings).map(([s,q])=>s+" "+q+" 股").join("，")||"空仓";
    el("positions").textContent="现金 "+usd(data.cash)+" USD · "+holdings;
    if(data.audit){
      const a=data.audit, baseline=a.origin==="inferred"?"旧账本推算期初":"期初本金";
      el("positions").textContent+=" ｜ "+baseline+" "+usd(a.capital)+" USD · 已核对 "+a.count+" 笔 · 累计费用 "+usd(a.fees)+" USD";
    }
    const table=el("trades");table.replaceChildren();
    const rows=[["时间 UTC","品种","股数","价格 USD","费用 USD","结果"],...data.orders.map(o=>[o.time,o.symbol,o.qty,usd(o.price),usd(o.fee),o.status])];
    for(const [i,values] of rows.entries()){const row=table.insertRow();for(const v of values){const cell=document.createElement(i?"td":"th");cell.textContent=v;row.append(cell)}}
  }catch(e){el("practiceMsg").textContent="操作失败 · "+e.message}
  finally{practiceBusy=false;el("openAccount").disabled=el("submitTrade").disabled=false}
}
el("practicePanel").ontoggle=()=>{if(el("practicePanel").open)practice("view")};
el("openAccount").onclick=()=>practice("open");
el("submitTrade").onclick=()=>practice("trade");

function navigate(){
  const slug=location.hash.slice(1);
  const page=["data","research","simulation"].includes(slug)?slug:"data";
  for(const link of document.querySelectorAll("nav [data-page]")){
    const current=link.dataset.page===page;
    el(link.dataset.page+"Page").hidden=!current;
    if(current)link.setAttribute("aria-current","page");
    else link.removeAttribute("aria-current");
  }
  if(page==="data" && el("chartPanel").open)requestAnimationFrame(drawChart);
}
window.addEventListener("hashchange",navigate);
navigate();
