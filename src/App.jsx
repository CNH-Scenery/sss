import React from "react";
import { css } from "./css.js";
import Topbar from "./components/Topbar.jsx";
import Sidebar from "./components/Sidebar.jsx";
import SurveyTab from "./tabs/SurveyTab.jsx";
import StrategyTab from "./tabs/StrategyTab.jsx";
import BacktestTab from "./tabs/BacktestTab.jsx";
import MonitorTab from "./tabs/MonitorTab.jsx";
import { notifPermission, requestNotifyPermission, sendNotification } from "./notify.js";

class App extends React.Component {
  constructor(props){
    super(props);
    this._codeParams={rsiBuy:42,volBuy:1.05,rsiSell:60,pnlTake:10,pnlStop:-6,extra:[]};
    this._open=92418000;
    this.surveys=this._buildSurveys();
    this.state={ screen:'survey', surveyIndex:0, responses:{}, draftAction:null, draftReason:'',
      strategy:null, codifying:false, versions:[], correctionDraft:'',
      backtest:null, backtesting:false, consistency:null,
      price:92418000, prevPrice:92418000, signal:'HOLD', signalReason:'조건 불충족 — 관망', alerts:[], webhookDraft:'', notifPerm:notifPermission() };
  }
  componentDidMount(){ this._t=setInterval(this._tick,2300); if(this.props.demoMode) this.fillDemo(); }
  componentDidUpdate(prev){ if(!prev.demoMode && this.props.demoMode && this.doneCount()===0) this.fillDemo(); }
  componentWillUnmount(){ clearInterval(this._t); }

  _mulberry(a){ return function(){ a|=0; a=a+0x6D2B79F5|0; let t=Math.imul(a^a>>>15,1|a); t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296; }; }
  _marketBase(m){ const b={'KRW-BTC':92000000,'KRW-ETH':5200000,'KRW-SOL':245000,'KRW-XRP':780,'KRW-DOGE':190}; return b[m]||100000; }
  _genCandles(seed,n,drift,base){ const rng=this._mulberry(seed); let price=base; const out=[]; for(let i=0;i<n;i++){ const ch=(rng()-0.5)*0.026+drift; const open=price; const close=price*(1+ch); const hi=Math.max(open,close)*(1+rng()*0.007); const lo=Math.min(open,close)*(1-rng()*0.007); const v=Math.round((0.5+rng()*1.8)*1000); out.push({o:open,h:hi,l:lo,c:close,v}); price=close; } return out; }
  _rsi(cl,p){ if(cl.length<p+1)return 50; let ag=0,al=0; for(let i=1;i<=p;i++){ const d=cl[i]-cl[i-1]; if(d>0)ag+=d; else al-=d; } ag/=p; al/=p; for(let i=p+1;i<cl.length;i++){ const d=cl[i]-cl[i-1]; ag=(ag*(p-1)+(d>0?d:0))/p; al=(al*(p-1)+(d<0?-d:0))/p; } const rs=ag/(al||1e-9); return 100-100/(1+rs); }
  _features(c){ const cl=c.map(x=>x.c),vs=c.map(x=>x.v),hi=c.map(x=>x.h),lo=c.map(x=>x.l); const last=cl[cl.length-1];
    const ma=n=>{ const s=cl.slice(-n); return s.reduce((a,b)=>a+b,0)/s.length; };
    const ma5=ma(5),ma20=ma(20),ma60=ma(Math.min(60,cl.length));
    const align=(ma5>ma20&&ma20>ma60)?'정배열':(ma5<ma20&&ma20<ma60)?'역배열':'혼조';
    const rsi=this._rsi(cl,14);
    const va=vs.slice(-20).reduce((a,b)=>a+b,0)/Math.min(20,vs.length);
    const volr=vs[vs.length-1]/va;
    const ema=p=>{ const k=2/(p+1); let e=cl[0]; for(let i=1;i<cl.length;i++) e=cl[i]*k+e*(1-k); return e; };
    const macd=ema(12)-ema(26);
    const sl=cl.slice(-20),m20=sl.reduce((a,b)=>a+b,0)/sl.length; const sd=Math.sqrt(sl.reduce((a,b)=>a+(b-m20)*(b-m20),0)/sl.length);
    const up=m20+2*sd,lw=m20-2*sd; const bbp=(last-lw)/((up-lw)||1); const bbw=(up-lw)/m20;
    let tr=0; for(let i=1;i<c.length;i++){ tr+=Math.max(hi[i]-lo[i],Math.abs(hi[i]-cl[i-1]),Math.abs(lo[i]-cl[i-1])); } const atr=tr/Math.max(1,c.length-1);
    const h20=Math.max.apply(null,hi.slice(-20)),l20=Math.min.apply(null,lo.slice(-20));
    return {close:last,rsi14:rsi,vol_ratio:volr,ma5,ma20,ma60,ma_align:align,macd,bb_pct:bbp,bb_width:bbw,atr,atr_pct:atr/last*100,dist_from_high20:(last-h20)/h20*100,dist_from_low20:(last-l20)/l20*100}; }
  _featuresAt(c,i){ return this._features(c.slice(0,i+1)); }
  _buildSurveys(){ const M=['KRW-BTC','KRW-ETH','KRW-SOL','KRW-XRP','KRW-DOGE','KRW-BTC','KRW-ETH','KRW-SOL','KRW-XRP','KRW-DOGE']; const tf=['15','60','일','15','240','60','일','15','60','240']; const dr=[-0.006,0.004,-0.003,0.006,-0.008,0.0015,0.005,-0.004,0.0025,-0.0015]; const arr=[]; for(let i=0;i<10;i++){ const m=M[i]; const c=this._genCandles(1000+i*131,52,dr[i],this._marketBase(m)); arr.push({market:m,tf:tf[i],candles:c,features:this._features(c)}); } return arr; }
  _strategyDecide(f,holding,pnl){ const p=this._codeParams; if(!holding && f.rsi14<p.rsiBuy && f.vol_ratio>p.volBuy) return 'BUY'; if(holding && (f.rsi14>p.rsiSell || pnl>p.pnlTake || pnl<p.pnlStop)) return 'SELL'; return 'HOLD'; }
  _runBacktestData(){ const c=this._genCandles(2298,120,0.0006,this._marketBase('KRW-BTC')); const cl=c.map(x=>x.c); let holding=false,entry=0,equity=1; const eq=[],bh=[],mk=[],tr=[]; const p0=cl[0]; for(let i=20;i<c.length;i++){ const f=this._featuresAt(c,i); const pnl=holding?(cl[i]-entry)/entry*100:0; const a=this._strategyDecide(f,holding,pnl); if(a==='BUY'&&!holding){ holding=true; entry=cl[i]; mk.push({i,type:'BUY'}); } else if(a==='SELL'&&holding){ const r=(cl[i]-entry)/entry; tr.push(r); equity*=(1+r); mk.push({i,type:'SELL'}); holding=false; } const cur=holding?equity*(cl[i]/entry):equity; eq.push(cur); bh.push(cl[i]/p0); } if(holding){ const r=(cl[cl.length-1]-entry)/entry; tr.push(r); equity*=(1+r); } const fin=eq[eq.length-1]; const tot=(fin-1)*100; const bhr=(bh[bh.length-1]-1)*100; const wins=tr.filter(x=>x>0).length; const wr=tr.length?wins/tr.length*100:0; let peak=-1e9,mdd=0; eq.forEach(v=>{ if(v>peak)peak=v; const dd=(v-peak)/peak; if(dd<mdd)mdd=dd; }); return {candles:c,markers:mk,eq,bh,metrics:{totalReturn:tot,bhReturn:bhr,winRate:wr,trades:tr.length,mdd:mdd*100,vsBH:tot-bhr}}; }
  _computeConsistency(){ const r=this.state.responses; const ids=Object.keys(r); let match=0; const mism=[]; ids.forEach(id=>{ const a=r[id].action; const s=this._strategyDecide(this.surveys[id].features,false,0); if(s===a)match++; else mism.push({survey:Number(id)+1,user:a,strat:s}); }); return {pct:ids.length?Math.round(match/ids.length*100):0,total:ids.length,match,mism}; }
  _genCode(v){ const p=this._codeParams; const n=this.doneCount(); const buys=Object.keys(this.state.responses).filter(id=>this.state.responses[id].action==='BUY').map(id=>'#'+(Number(id)+1)).join(', ')||'—'; let s='';
    s+='# Tacit Trader 자동 생성 전략  ·  v'+v+'\n';
    s+='# 근거: 설문 응답 '+n+'건'+(p.extra.length?' + 수정 멘트 '+p.extra.length+'건':'')+'\n';
    s+='# 매수 신호가 나온 설문: '+buys+'\n\n';
    s+='def decide(features: dict, position: dict) -> dict:\n';
    s+='    rsi      = features["rsi14"]\n';
    s+='    vol      = features["vol_ratio"]\n';
    s+='    ma_align = features["ma_align"]\n';
    s+='    holding  = position["holding"]\n';
    s+='    pnl      = position["pnl_pct"]\n\n';
    s+='    # 매수: 과매도 반등 + 거래량 동반\n';
    s+='    if (not holding) and rsi < '+p.rsiBuy+' and vol > '+p.volBuy+':\n';
    s+='        return {"action": "BUY", "reason": f"RSI {rsi:.0f} 과매도 + 거래량 {vol:.1f}x"}\n\n';
    s+='    # 매도: 과열 / 목표 / 손절\n';
    s+='    if holding and (rsi > '+p.rsiSell+' or pnl > '+p.pnlTake.toFixed(1)+' or pnl < '+p.pnlStop.toFixed(1)+'):\n';
    s+='        return {"action": "SELL", "reason": "과열 또는 목표·손절 도달"}\n\n';
    if(p.extra.length){ p.extra.slice(-2).forEach(e=>{ s+='    # 정제 반영: '+e+'\n'; }); }
    s+='    return {"action": "HOLD", "reason": "조건 불충족 — 관망"}\n';
    return s; }
  _highlight(code){ const R=React.createElement; const kw=new Set(['def','return','if','elif','else','and','or','not','in','None','True','False','import','for','while','is']); const fn=new Set(['decide','features','position','dict']); const lines=code.split('\n'); const out=lines.map((line,li)=>{ let parts; if(line.trim().indexOf('#')===0){ parts=[R('span',{key:'c',style:{color:'#8b949e'}},line)]; } else { parts=[]; const re=/("(?:[^"\\]|\\.)*"|#.*$|\b\d+\.?\d*\b|[A-Za-z_]\w*|\s+|[^\sA-Za-z0-9_"]+)/g; let m,k=0; while((m=re.exec(line))){ const t=m[0]; let col=null; if(t[0]==='"')col='#a5d6ff'; else if(t[0]==='#')col='#8b949e'; else if(/^\d/.test(t))col='#79c0ff'; else if(kw.has(t))col='#ff7b72'; else if(fn.has(t))col='#d2a8ff'; parts.push(col?R('span',{key:k++,style:{color:col}},t):t); } } return R('div',{key:li,style:{minHeight:'1.5em',whiteSpace:'pre'}},parts.length?parts:'\u00a0'); }); return R('pre',{style:{margin:0,fontFamily:"'JetBrains Mono', monospace",fontSize:'12.5px',lineHeight:1.5,color:'#e6edf3'}},out); }
  _kfmt(v){ if(v>=1e6) return (v/1e4).toLocaleString(undefined,{maximumFractionDigits:0})+'만'; if(v>=1000) return Math.round(v).toLocaleString(); return v.toFixed(1); }
  _candleChart(c,o){ o=o||{}; const R=React.createElement; const W=820,H=o.height||300,pT=14,pB=22,pL=10,pR=58; const lows=c.map(x=>x.l),highs=c.map(x=>x.h); const mn=Math.min.apply(null,lows),mx=Math.max.apply(null,highs),rg=(mx-mn)||1; const pw=W-pL-pR,ph=H-pT-pB,n=c.length,cw=pw/n; const y=v=>pT+(1-(v-mn)/rg)*ph; const x=i=>pL+cw*(i+0.5); const e=[]; for(let g=0;g<=4;g++){ const val=mn+rg*g/4,yy=y(val); e.push(R('line',{key:'g'+g,x1:pL,x2:pL+pw,y1:yy,y2:yy,stroke:'#1a212c',strokeWidth:1})); e.push(R('text',{key:'gl'+g,x:pL+pw+6,y:yy+3,fill:'#5a6472',fontSize:9,fontFamily:'JetBrains Mono, monospace'},this._kfmt(val))); } c.forEach((d,i)=>{ const up=d.c>=d.o,col=up?'#22c55e':'#ef4444',xx=x(i); e.push(R('line',{key:'w'+i,x1:xx,x2:xx,y1:y(d.h),y2:y(d.l),stroke:col,strokeWidth:1})); const bw=Math.max(1.4,cw*0.6),yo=y(d.o),yc=y(d.c); e.push(R('rect',{key:'b'+i,x:xx-bw/2,y:Math.min(yo,yc),width:bw,height:Math.max(0.8,Math.abs(yc-yo)),fill:col})); }); (o.markers||[]).forEach((m,k)=>{ const xx=x(m.i),buy=m.type==='BUY'; const yy=buy?y(c[m.i].l)+13:y(c[m.i].h)-13,col=buy?'#22c55e':'#ef4444',dir=buy?1:-1; e.push(R('path',{key:'m'+k,d:'M '+xx+' '+(yy-6*dir)+' L '+(xx-5)+' '+(yy+2*dir)+' L '+(xx+5)+' '+(yy+2*dir)+' Z',fill:col,stroke:'#0a0e14',strokeWidth:0.8})); }); return R('svg',{viewBox:'0 0 '+W+' '+H,style:{width:'100%',height:'auto',display:'block'}},e); }
  _equityChart(st,bh,A){ const R=React.createElement; const W=820,H=230,pT=12,pB=22,pL=10,pR=46; const all=st.concat(bh),mn=Math.min.apply(null,all),mx=Math.max.apply(null,all),rg=(mx-mn)||1; const pw=W-pL-pR,ph=H-pT-pB,n=st.length; const x=i=>pL+pw*(i/(n-1||1)); const y=v=>pT+(1-(v-mn)/rg)*ph; const path=a=>a.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' '); const e=[]; for(let g=0;g<=3;g++){ const val=mn+rg*g/3,yy=y(val); e.push(R('line',{key:'g'+g,x1:pL,x2:pL+pw,y1:yy,y2:yy,stroke:'#1a212c'})); e.push(R('text',{key:'t'+g,x:pL+pw+6,y:yy+3,fill:'#5a6472',fontSize:9,fontFamily:'JetBrains Mono, monospace'},((val-1)*100).toFixed(0)+'%')); } const yb=y(1); e.push(R('line',{key:'b',x1:pL,x2:pL+pw,y1:yb,y2:yb,stroke:'#2a3340',strokeDasharray:'3 3'})); e.push(R('path',{key:'bh',d:path(bh),fill:'none',stroke:'#5a6472',strokeWidth:1.5})); e.push(R('path',{key:'ar',d:path(st)+' L '+x(n-1).toFixed(1)+' '+(pT+ph).toFixed(1)+' L '+x(0).toFixed(1)+' '+(pT+ph).toFixed(1)+' Z',fill:A+'1f'})); e.push(R('path',{key:'st',d:path(st),fill:'none',stroke:A,strokeWidth:2})); return R('svg',{viewBox:'0 0 '+W+' '+H,style:{width:'100%',height:'auto',display:'block'}},e); }
  _now(){ return new Date().toTimeString().slice(0,8); }
  doneCount(){ return Object.keys(this.state.responses).length; }
  fillDemo(){ const r={}; this.surveys.forEach((sv,i)=>{ const f=sv.features; let a,t; if(f.rsi14<38){ a='BUY'; t='RSI '+f.rsi14.toFixed(0)+'로 과매도인데 거래량 '+f.vol_ratio.toFixed(1)+'x 터져서 반등 노리고 분할 매수.'; } else if(f.rsi14>62){ a='SELL'; t='RSI '+f.rsi14.toFixed(0)+' 과열에 고점 부담이라 일부 익절.'; } else { a='HOLD'; t='방향 애매하고 '+f.ma_align+' 구간이라 일단 관망.'; } r[i]={action:a,reason:t,time:this._now()}; }); this.setState({responses:r}); }

  goSurvey=()=>this.setState({screen:'survey'});
  goStrategy=()=>this.setState({screen:'strategy'});
  goBacktest=()=>this.setState({screen:'backtest'});
  goMonitor=()=>this.setState({screen:'monitor'});
  _setSurvey=(i)=>{ i=Math.max(0,Math.min(9,i)); const r=this.state.responses[i]; this.setState({surveyIndex:i,draftAction:r?r.action:null,draftReason:r?r.reason:''}); };
  goPrev=()=>this._setSurvey(this.state.surveyIndex-1);
  goNext=()=>this._setSurvey(this.state.surveyIndex+1);
  setBuy=()=>this.setState({draftAction:'BUY'});
  setSell=()=>this.setState({draftAction:'SELL'});
  setHold=()=>this.setState({draftAction:'HOLD'});
  onReason=(e)=>this.setState({draftReason:e.target.value});
  submitResponse=()=>{ if(!this.state.draftAction||!this.state.draftReason.trim())return; this.setState(s=>{ const responses={...s.responses}; responses[s.surveyIndex]={action:s.draftAction,reason:s.draftReason.trim(),time:this._now()}; let nx=null; for(let k=0;k<10;k++){ if(!responses[k]){ nx=k; break; } } return {responses,surveyIndex:nx===null?s.surveyIndex:nx,draftAction:nx===null?s.draftAction:null,draftReason:nx===null?s.draftReason:''}; }); };
  runCodify=()=>{ if(this.state.codifying||this.doneCount()===0)return; this.setState({codifying:true}); setTimeout(()=>{ const v=(this.state.strategy?this.state.strategy.version:0)+1; const code=this._genCode(v); const cons=this._computeConsistency(); const cnt=this.doneCount(); this.setState(s=>({codifying:false,strategy:{version:v,code},consistency:cons,backtest:null,versions:[{version:v,label:'초기 코드화 · 응답 '+cnt+'건',time:this._now()},...s.versions]})); },1500); };
  onCorrection=(e)=>this.setState({correctionDraft:e.target.value});
  runRefine=()=>{ const t=this.state.correctionDraft.trim(); if(!t||this.state.codifying||!this.state.strategy)return; const p={...this._codeParams}; if(/손절|stop|빠르|리스크|보수/.test(t)) p.pnlStop=Math.min(-2,p.pnlStop+1); else if(/거래량|volume|볼륨|엄격/.test(t)) p.volBuy=Math.round((p.volBuy+0.2)*100)/100; else if(/익절|목표|수익|길게|버티|버텨/.test(t)) p.pnlTake=p.pnlTake+1.5; else if(/과매도|rsi|민감|덜|공격/.test(t)) p.rsiBuy=Math.min(45,p.rsiBuy+3); else p.rsiBuy=Math.min(45,p.rsiBuy+2); p.extra=[...p.extra,t]; this._codeParams=p; this.setState({codifying:true}); setTimeout(()=>{ const v=this.state.strategy.version+1; const code=this._genCode(v); const cons=this._computeConsistency(); this.setState(s=>({codifying:false,correctionDraft:'',strategy:{version:v,code},consistency:cons,backtest:null,versions:[{version:v,label:'정제: '+(t.length>20?t.slice(0,20)+'…':t),time:this._now()},...s.versions]})); },1400); };
  runBacktest=()=>{ if(this.state.backtesting||!this.state.strategy)return; this.setState({backtesting:true}); setTimeout(()=>{ this.setState({backtesting:false,backtest:this._runBacktestData()}); },1500); };
  onWebhook=(e)=>this.setState({webhookDraft:e.target.value});
  enableNotifications=()=>{ requestNotifyPermission().then(p=>this.setState({notifPerm:p})); };
  testAlert=()=>{ const al={action:'BUY',color:'#22c55e',text:'[테스트] KRW-BTC BUY 신호 · RSI 31 과매도 + 거래량 1.7x · '+this.state.price.toLocaleString()+'원',time:this._now()}; this.setState(s=>({alerts:[al,...s.alerts].slice(0,8)})); sendNotification('Tacit Trader · 테스트 알림', al.text, 'tt-test'); };
  _tick=()=>{ const s=this.state; const ch=(Math.random()-0.48)*0.0035; const np=Math.round(s.price*(1+ch)); const u={prevPrice:s.price,price:np}; let fired=null; if(this.props.liveSim!==false && s.screen==='monitor' && s.strategy && Math.random()<0.28){ const r=Math.random(); let sig='HOLD',rs='조건 불충족 — 관망'; if(r<0.16){ sig='BUY'; rs='RSI 32 과매도 + 거래량 1.6x'; } else if(r<0.27){ sig='SELL'; rs='RSI 74 과열 / 목표 도달'; } if(sig!=='HOLD'){ const col=sig==='BUY'?'#22c55e':'#ef4444'; const text='[KRW-BTC] '+sig+' 신호 · '+rs+' · '+np.toLocaleString()+'원'; u.signal=sig; u.signalReason=rs; u.alerts=[{action:sig,color:col,text,time:this._now()},...s.alerts].slice(0,8); fired={sig,text}; } } this.setState(u); if(fired) sendNotification('Tacit Trader · '+fired.sig+' 신호', fired.text, 'tt-signal'); };

  renderVals(){
    const s=this.state; const A=this.props.accent||'#4f8cff';
    const actColor=a=>a==='BUY'?'#22c55e':a==='SELL'?'#ef4444':'#f59e0b';
    const cur=this.surveys[s.surveyIndex]; const f=cur.features;
    const navBase='display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:8px;cursor:pointer;font-size:13.5px;font-weight:500;transition:all .12s;';
    const nav=k=>navBase+(s.screen===k?'color:#e6edf3;background:#161d28;':'color:#7d8794;background:transparent;');
    const actStyle=k=>{ const map={BUY:'#22c55e',SELL:'#ef4444',HOLD:'#f59e0b'}; const col=map[k]; const b='flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;padding:14px;border-radius:10px;cursor:pointer;transition:all .12s;font-weight:700;'; return s.draftAction===k? b+'border:1.5px solid '+col+';background:'+col+'1f;color:'+col+';' : b+'border:1.5px solid #1f2630;background:#0e131b;color:#8b95a3;'; };
    const subOk=!!s.draftAction&&!!s.draftReason.trim();
    const fr=[
      {label:'RSI (14)',value:f.rsi14.toFixed(0),tone:f.rsi14<35?'u':f.rsi14>65?'d':'m'},
      {label:'거래량비',value:f.vol_ratio.toFixed(2)+'x',tone:f.vol_ratio>1.3?'u':f.vol_ratio<0.7?'d':'m'},
      {label:'MA 배열',value:f.ma_align,tone:f.ma_align==='정배열'?'u':f.ma_align==='역배열'?'d':'m'},
      {label:'MACD',value:(f.macd/f.close*100).toFixed(2),tone:f.macd>=0?'u':'d'},
      {label:'볼린저 %B',value:(f.bb_pct*100).toFixed(0)+'%',tone:f.bb_pct<0.2?'u':f.bb_pct>0.8?'d':'m'},
      {label:'밴드폭',value:(f.bb_width*100).toFixed(1)+'%',tone:'m'},
      {label:'20일 고점대비',value:f.dist_from_high20.toFixed(1)+'%',tone:f.dist_from_high20>-1.5?'d':'m'},
      {label:'20일 저점대비',value:'+'+f.dist_from_low20.toFixed(1)+'%',tone:f.dist_from_low20<3?'u':'m'},
      {label:'ATR',value:f.atr_pct.toFixed(2)+'%',tone:'m'}
    ].map(r=>({label:r.label,value:r.value,color:r.tone==='u'?'#22c55e':r.tone==='d'?'#ef4444':'#aeb7c2'}));
    const ctx=Object.keys(s.responses).map(id=>({survey:'#'+(Number(id)+1),action:s.responses[id].action,color:actColor(s.responses[id].action),reason:s.responses[id].reason,time:s.responses[id].time}));
    const bt=s.backtest; const cons=s.consistency;
    let metricCards=[];
    if(bt){ const m=bt.metrics; metricCards=[
      {label:'총 수익률',value:(m.totalReturn>=0?'+':'')+m.totalReturn.toFixed(1)+'%',color:m.totalReturn>=0?'#22c55e':'#ef4444',sub:'전략 누적'},
      {label:'vs 보유(B&H)',value:(m.vsBH>=0?'+':'')+m.vsBH.toFixed(1)+'%p',color:m.vsBH>=0?'#22c55e':'#ef4444',sub:'보유 '+m.bhReturn.toFixed(1)+'%'},
      {label:'승률',value:m.winRate.toFixed(0)+'%',color:'#e6edf3',sub:m.trades+'회 거래'},
      {label:'MDD',value:m.mdd.toFixed(1)+'%',color:'#f59e0b',sub:'최대 낙폭'} ]; }
    const mism=cons?cons.mism.map(x=>({survey:x.survey,user:x.user,strat:x.strat,userColor:actColor(x.user),stratColor:actColor(x.strat)})):[];
    const brandBtn=(disabled,wait)=>{ const b='border:none;border-radius:10px;padding:13px;font-weight:700;font-size:14px;width:100%;transition:all .12s;'; if(wait)return b+'background:#1a212c;color:#9aa4b1;cursor:wait;'; if(disabled)return b+'background:#1a212c;color:#5a6472;cursor:not-allowed;'; return b+'background:linear-gradient(90deg,'+A+',#22c55e);color:#06101f;cursor:pointer;'; };
    return {
      livePriceFmt:s.price.toLocaleString(),
      topPriceColor:s.price>=s.prevPrice?'#22c55e':'#ef4444',
      navSurveyStyle:nav('survey'),navStrategyStyle:nav('strategy'),navBacktestStyle:nav('backtest'),navMonitorStyle:nav('monitor'),
      doneCount:this.doneCount(),
      isSurvey:s.screen==='survey',isStrategy:s.screen==='strategy',isBacktest:s.screen==='backtest',isMonitor:s.screen==='monitor',
      goSurvey:this.goSurvey,goStrategy:this.goStrategy,goBacktest:this.goBacktest,goMonitor:this.goMonitor,
      progressWidth:(this.doneCount()/10*100)+'%',
      curMarket:cur.market,curTf:cur.tf,surveyNo:s.surveyIndex+1,
      surveyChartEl:this._candleChart(cur.candles,{height:300}),
      featureRows:fr,
      goPrev:this.goPrev,goNext:this.goNext,
      setBuy:this.setBuy,setSell:this.setSell,setHold:this.setHold,
      buyStyle:actStyle('BUY'),sellStyle:actStyle('SELL'),holdStyle:actStyle('HOLD'),
      draftReason:s.draftReason,onReason:this.onReason,
      submitResponse:this.submitResponse,
      submitStyle:'border:none;border-radius:9px;padding:10px 18px;font-weight:700;font-size:13.5px;transition:all .12s;'+(subOk?'background:'+A+';color:#06101f;cursor:pointer;':'background:#1a212c;color:#5a6472;cursor:not-allowed;'),
      allDone:this.doneCount()===10,
      hasResponses:this.doneCount()>0,noResponses:this.doneCount()===0,
      contextItems:ctx,
      codifying:s.codifying,notCodifying:!s.codifying,
      runCodify:this.runCodify,
      codifyStyle:brandBtn(this.doneCount()===0,s.codifying),
      codifyLabel:s.strategy?'코드 재생성 ↻ (컨텍스트 누적)':'코드화 실행 →',
      hasStrategy:!!s.strategy,
      codeEl:s.strategy?this._highlight(s.strategy.code):null,
      versionLabel:s.strategy?('v'+s.strategy.version):'',
      correctionDraft:s.correctionDraft,onCorrection:this.onCorrection,runRefine:this.runRefine,
      refineStyle:'border:none;border-radius:9px;padding:11px 16px;font-weight:700;font-size:13px;white-space:nowrap;transition:all .12s;'+((s.correctionDraft.trim()&&!s.codifying)?'background:'+A+';color:#06101f;cursor:pointer;':'background:#1a212c;color:#5a6472;cursor:not-allowed;'),
      hasVersions:s.versions.length>0,versionItems:s.versions,
      btNeedStrategy:!s.strategy,
      btVersionLabel:s.strategy?('v'+s.strategy.version):'—',
      backtesting:s.backtesting,notBacktesting:!s.backtesting,
      runBacktest:this.runBacktest,
      backtestBtnStyle:'border:none;border-radius:9px;padding:11px 20px;font-weight:700;font-size:13.5px;transition:all .12s;'+(s.backtesting?'background:#1a212c;color:#9aa4b1;cursor:wait;':'background:'+A+';color:#06101f;cursor:pointer;'),
      backtestLabel:s.backtest?'다시 실행 ↻':'백테스트 실행 →',
      showBtIdle:!!s.strategy&&!s.backtest&&!s.backtesting,
      hasBacktest:!!s.backtest,
      metricCards,
      equityChartEl:bt?this._equityChart(bt.eq,bt.bh,A):null,
      backtestChartEl:bt?this._candleChart(bt.candles,{markers:bt.markers,height:300}):null,
      consistencyPct:cons?cons.pct:0,consistencyTotal:cons?cons.total:0,consistencyWidth:cons?(cons.pct+'%'):'0%',
      hasMismatch:!!cons&&cons.mism.length>0,noMismatch:!!cons&&cons.mism.length===0,mismatchItems:mism,
      monNeedStrategy:!s.strategy,
      signalText:s.signal==='BUY'?'BUY · 매수 신호':s.signal==='SELL'?'SELL · 매도 신호':'HOLD · 관망',
      signalColor:s.signal==='BUY'?'#22c55e':s.signal==='SELL'?'#ef4444':'#f59e0b',
      signalReason:s.signalReason,
      priceChangePct:(((s.price-this._open)/this._open*100)>=0?'+':'')+((s.price-this._open)/this._open*100).toFixed(2)+'%',
      webhookDraft:s.webhookDraft,onWebhook:this.onWebhook,testAlert:this.testAlert,
      enableNotifications:this.enableNotifications,
      notifPerm:s.notifPerm,
      notifDisabled:s.notifPerm==='granted'||s.notifPerm==='unsupported',
      notifLabel:s.notifPerm==='granted'?'🔔 알림 켜짐':s.notifPerm==='denied'?'알림 차단됨':s.notifPerm==='unsupported'?'알림 미지원':'🔔 데스크톱 알림 켜기',
      notifBtnStyle:(()=>{ const on=s.notifPerm==='granted'; const off=s.notifPerm==='denied'||s.notifPerm==='unsupported'; const b='border-radius:7px;padding:7px 12px;font-size:12px;white-space:nowrap;'; if(on) return b+'background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.4);color:#22c55e;cursor:default;'; if(off) return b+'background:#0e131b;border:1px solid #1f2630;color:#5a6472;cursor:not-allowed;'; return b+'background:#0e131b;border:1px solid #1f2630;color:#9aa4b1;cursor:pointer;'; })(),
      alertItems:s.alerts,hasAlerts:s.alerts.length>0,noAlerts:s.alerts.length===0,
      liveHint:this.props.liveSim===false?'(시뮬레이션 꺼짐 — 테스트 발송으로 확인)':''
    };
  }

  render() {
    const v = this.renderVals();
    return (
      <div style={css(`height:100vh;display:flex;flex-direction:column;background:#0a0e14;color:#e6edf3;font-family:'Pretendard',-apple-system,sans-serif;font-size:14px;overflow:hidden`)}>
        <Topbar v={v} />
        <div style={css(`flex:1;display:flex;min-height:0`)}>
          <Sidebar v={v} />
          <div style={css(`flex:1;overflow-y:auto;min-width:0`)}>
            <div style={css(`max-width:1080px;margin:0 auto;padding:26px 30px 60px`)}>
              {v.isSurvey && <SurveyTab v={v} />}
              {v.isStrategy && <StrategyTab v={v} />}
              {v.isBacktest && <BacktestTab v={v} />}
              {v.isMonitor && <MonitorTab v={v} />}
            </div>
          </div>
        </div>
      </div>
    );
  }

}

App.defaultProps = { accent: "#4f8cff", demoMode: false, liveSim: true };

export default App;
