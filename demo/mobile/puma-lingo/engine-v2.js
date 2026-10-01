
(function(){
  const DAY=86400000, MIN=60000;
  const oldHome=window.home;
  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(m){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]})}
  function clamp(x,a,b){return Math.max(a,Math.min(b,x))}
  function sigmoid(x){return 1/(1+Math.exp(-x))}
  function editSim(a,b){
    a=norm(a);b=norm(b);if(!a||!b)return 0;
    const d=Array.from({length:a.length+1},()=>Array(b.length+1).fill(0));
    for(let i=0;i<=a.length;i++)d[i][0]=i;
    for(let j=0;j<=b.length;j++)d[0][j]=j;
    for(let i=1;i<=a.length;i++)for(let j=1;j<=b.length;j++)d[i][j]=Math.min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(a[i-1]===b[j-1]?0:1));
    return Math.round((1-d[a.length][b.length]/Math.max(a.length,b.length))*100);
  }
  function ensureState(){
    S.adaptive=S.adaptive||{};
    S.adaptive[S.lang]=S.adaptive[S.lang]||{ability:1.5,lessons:0,placementDone:false};
    S.vocab2=S.vocab2||{};
    S.vocab2[S.lang]=S.vocab2[S.lang]||{};
    S.mistakeLog=S.mistakeLog||[];
    return S.adaptive[S.lang];
  }
  function rec(word){
    ensureState();
    const db=S.vocab2[S.lang];
    db[word]=db[word]||{seen:0,correct:0,wrong:0,stability:.18,due:0,last:0,avgMs:0,hints:0,stage:0,lastMode:"",lapses:0};
    return db[word];
  }
  function ability(){return ensureState().ability}
  function setAbility(v){ensureState().ability=clamp(v,1,30)}
  function wordMeta(){
    const arr=W[S.lang]||W["en-US"];
    return arr.map((x,i)=>({word:x[0],meaning:x[1],idx:i,difficulty:1+(i/Math.max(1,arr.length-1))*29}));
  }
  function recallProb(m,r,now){
    now=now||Date.now();
    if(!r.seen||!r.last)return 0;
    const elapsedDays=Math.max(0,(now-r.last)/DAY);
    return Math.pow(2,-elapsedDays/Math.max(.08,r.stability));
  }
  function targetSuccess(m){return sigmoid((ability()-m.difficulty)/4.8)}
  function urgency(m,r,now){
    const p=recallProb(m,r,now),due=r.seen&&(r.due<=now||p<.82)?70+(1-p)*80:0;
    const fresh=!r.seen?52:0,zone=45-Math.min(45,Math.abs(targetSuccess(m)-.80)*120);
    const weakness=Math.min(35,r.wrong*5+r.lapses*6)+Math.max(0,5-r.stage)*3;
    return due+fresh+zone+weakness+(r.seen&&r.due>now?-120:0)+Math.random()*5;
  }
  function modeFor(m,r){
    if(!r.seen||r.stage<1)return "meaning";
    if(r.stage<2)return "cloze_choice";
    if(r.stage<3)return "reverse";
    if(r.stage<4)return "cloze_type";
    if(r.stage<5)return "listen";
    if(S.lang==="en-US"&&r.stage>=5)return Math.random()<.35?"speak":"cloze_type";
    return Math.random()<.5?"listen":"cloze_type";
  }
  function chooseSession(limit){
    const now=Date.now(),metas=wordMeta(),picked=[],seen={};
    const due=metas.filter(m=>{const r=rec(m.word);return r.seen&&(r.due<=now||recallProb(m,r,now)<.82)}).sort((a,b)=>urgency(b,rec(b.word),now)-urgency(a,rec(a.word),now));
    const fresh=metas.filter(m=>!rec(m.word).seen).sort((a,b)=>urgency(b,rec(b.word),now)-urgency(a,rec(a.word),now));
    const weak=metas.filter(m=>rec(m.word).seen&&rec(m.word).due>now).sort((a,b)=>urgency(b,rec(b.word),now)-urgency(a,rec(a.word),now));
    function add(m){if(m&&!seen[m.word]&&picked.length<limit){seen[m.word]=1;picked.push(m)}}
    due.slice(0,Math.ceil(limit*.45)).forEach(add);fresh.forEach(add);weak.forEach(add);
    return picked;
  }
  const FB={
    hello:["Hello!","안녕하세요!"],yes:["Yes, please.","네, 부탁해요."],no:["No, thank you.","아니요, 괜찮아요."],
    I:["I am ready.","나는 준비됐어요."],you:["Are you ready?","당신은 준비됐나요?"],we:["We can sit there.","우리는 거기에 앉을 수 있어요."],
    go:["Let's go now.","지금 가요."],come:["Come here, please.","여기로 와 주세요."],sit:["Please sit here.","여기에 앉으세요."],
    seat:["This seat is free.","이 자리는 비어 있어요."],eat:["Let's eat lunch.","점심을 먹어요."],drink:["I want to drink water.","나는 물을 마시고 싶어요."],
    water:["I need some water.","나는 물이 좀 필요해요."],food:["The food is good.","음식이 맛있어요."],hotel:["The hotel is near.","호텔은 가까워요."],
    room:["My room is clean.","내 방은 깨끗해요."],car:["The car is outside.","자동차가 밖에 있어요."],bus:["The bus is here.","버스가 왔어요."],
    train:["The train is fast.","기차는 빨라요."],airport:["The airport is far.","공항은 멀어요."],ticket:["I have a ticket.","나는 표가 있어요."],
    toilet:["Where is the toilet?","화장실이 어디예요?"],here:["Come here.","여기로 오세요."],there:["Sit there.","거기에 앉으세요."],
    good:["This is good.","이건 좋아요."],bad:["This is bad.","이건 나빠요."],big:["It is big.","그것은 커요."],small:["It is small.","그것은 작아요."],
    one:["I need one ticket.","표 한 장이 필요해요."],two:["I need two tickets.","표 두 장이 필요해요."]
  };
  function example(m){
    let e=window.EX&&EX[S.lang]&&EX[S.lang][m.word];
    if(e)return {full:e[0].replace("____",m.word).replace("___",m.word),blank:e[0],ko:e[1]};
    if(S.lang==="en-US"&&FB[m.word]){
      e=FB[m.word];return {full:e[0],blank:e[0].replace(m.word,"___"),ko:e[1]};
    }
    return {full:m.word,blank:"___",ko:m.meaning};
  }
  function knownMeaning(word){const x=(W[S.lang]||[]).find(v=>norm(v[0])===norm(word));return x?x[1]:null}
  function distractorMeanings(m){return [m.meaning].concat(wordMeta().filter(x=>x.word!==m.word&&x.meaning!==m.meaning).sort(()=>Math.random()-.5).slice(0,3).map(x=>x.meaning)).sort(()=>Math.random()-.5)}
  function distractorWords(m){return [m.word].concat(wordMeta().filter(x=>x.word!==m.word).sort(()=>Math.random()-.5).slice(0,3).map(x=>x.word)).sort(()=>Math.random()-.5)}
  function explanation(m,mode,userAnswer,correct,ok,ms,hint){
    const ex=example(m);
    if(ok)return {title:"정답",why:"<b>"+esc(m.word)+"</b> = "+esc(m.meaning),answer:"",example:"예문: <b>"+esc(ex.full)+"</b><br><span class='muted'>"+esc(ex.ko)+"</span>",coach:hint?"힌트를 사용했으니 복습 간격은 짧게 잡아요.":ms<5000?"빠르고 정확했어요. 다음 복습 간격을 늘립니다.":"정답이에요. 기억 강도를 한 단계 올립니다."};
    let why="",sim=editSim(userAnswer,correct);
    if(!String(userAnswer||"").trim())why="답을 입력하지 않았어요.";
    else if(mode==="meaning")why="고른 뜻은 이 단어와 연결되지 않아요. <b>"+esc(m.word)+"</b>의 기본 뜻은 <b>"+esc(m.meaning)+"</b>입니다.";
    else if((mode==="reverse"||mode==="cloze_choice")&&knownMeaning(userAnswer))why="<b>"+esc(userAnswer)+"</b>는 ‘"+esc(knownMeaning(userAnswer))+"’라는 뜻이라 이 문맥과 맞지 않아요.";
    else if(sim>=65)why="뜻은 떠올렸지만 <b>철자</b>가 달라요. 빠진 글자와 순서를 확인하세요.";
    else if(S.lang==="en-US"&&norm(userAnswer).includes("seat")&&norm(correct)==="sit")why="<b>seat</b>는 ‘좌석’, <b>sit</b>은 ‘앉다’예요. 여기에는 동사 sit가 필요합니다.";
    else if(S.lang==="en-US"&&norm(userAnswer).includes("sit")&&norm(correct)==="seat")why="<b>sit</b>은 ‘앉다’, <b>seat</b>는 ‘좌석’이에요. 여기에는 명사 seat가 필요합니다.";
    else why=knownMeaning(userAnswer)?"입력한 <b>"+esc(userAnswer)+"</b>는 ‘"+esc(knownMeaning(userAnswer))+"’라서 이 문맥과 맞지 않아요.":"정답 단어를 아직 정확히 기억하지 못한 것으로 판단했어요.";
    return {title:"왜 오답일까?",why:why,answer:"정답: <b>"+esc(correct)+"</b> — "+esc(m.meaning),example:"예문: <b>"+esc(ex.full)+"</b><br><span class='muted'>"+esc(ex.ko)+"</span>",coach:"이 항목은 바로 반복시키지 않고 잠시 뒤 다시 확인합니다."};
  }
  function updateMemory(m,ok,ms,hint,mode){
    const r=rec(m.word),now=Date.now(),old=Math.max(.12,r.stability);
    r.seen++;r.last=now;r.lastMode=mode;r.avgMs=r.avgMs?Math.round(r.avgMs*.72+ms*.28):ms;if(hint)r.hints++;
    if(ok){
      r.correct++;
      const speed=ms<4500?1.20:(ms<9000?1:.82),help=hint?.58:1;
      r.stability=clamp(old*(1.55*speed*help)+.12,.18,365);
      r.stage=clamp(r.stage+(hint?.35:1),0,6);
      r.due=now+clamp(r.stability*.82,.15,180)*DAY;
      setAbility(ability()+.34*(1-targetSuccess(m))*(hint?.55:1));
      S.ok++;S.xp+=hint?4:7;
    }else{
      r.wrong++;r.lapses++;r.stage=Math.max(0,r.stage-.75);r.stability=clamp(old*.48,.08,365);
      r.due=now+clamp(8+r.lapses*2,8,30)*MIN;setAbility(ability()-.20*targetSuccess(m));S.xp+=1;
      S.mistakeLog.unshift({lang:S.lang,word:m.word,meaning:m.meaning,mode:mode,at:now,due:r.due});S.mistakeLog=S.mistakeLog.slice(0,200);
    }
    S.total++;save();
  }
  function answerPanel(m,ok,mode,userAnswer,correct,ms,hint){
    const q=document.getElementById("wq"),d=explanation(m,mode,userAnswer,correct,ok,ms,hint),p=document.createElement("div");
    p.className="explainPanel "+(ok?"explainOk":"explainBad");
    p.innerHTML="<div class='explainTitle'>"+d.title+"</div><div>"+d.why+"</div>"+(d.answer?"<div class='answerLine'>"+d.answer+"</div>":"")+"<div class='exampleLine'>"+d.example+"</div>"+(d.coach?"<div class='coachLine'>🧠 "+d.coach+"</div>":"");
    q.appendChild(p);const n=document.createElement("button");n.className="primary";n.textContent="다음";n.onclick=function(){wSess.i++;adaptiveQuestion()};q.appendChild(n);
  }
  window.wordStart=function(opts){
    opts=opts||{};ensureState();const limit=Math.max(5,Math.min(S.goal||10,20));
    const all=wordMeta(),p=opts.placement?all.filter((x,i)=>i%Math.max(1,Math.floor(all.length/10))===0).slice(0,10):chooseSession(limit);
    if(!p.length){alert("지금은 복습할 항목이 없어요. 잘 외운 항목은 잊을 가능성이 올라갈 때 다시 나옵니다.");return}
    wSess={p:p,i:0,correct:0,hint:false,started:0,placement:!!opts.placement};show("word");adaptiveQuestion();
  };
  window.placementStart=function(){if(confirm("10문제로 현재 수준을 빠르게 확인할까요?"))wordStart({placement:true})};
  window.adaptiveQuestion=function(){
    if(wSess.i>=wSess.p.length)return adaptiveFinish();
    const m=wSess.p[wSess.i],r=rec(m.word),mode=wSess.placement?"meaning":modeFor(m,r),q=document.getElementById("wq"),ex=example(m);
    wSess.started=Date.now();wSess.hint=false;document.getElementById("wordNo").textContent=(wSess.i+1)+"/"+wSess.p.length;
    const lp=document.getElementById("wordLevel");if(lp)lp.textContent="실력 "+Math.round(ability());
    const names={meaning:"뜻 고르기",cloze_choice:"문맥",reverse:"한국어→단어",cloze_type:"직접 입력",listen:"듣기",speak:"말하기"};
    q.innerHTML="<span class='tag'>"+names[mode]+"</span><div id='promptArea'></div><div id='answerArea'></div>";
    const prompt=document.getElementById("promptArea"),ans=document.getElementById("answerArea");
    if(mode==="meaning"){
      prompt.innerHTML="<div class='big'>"+esc(m.word)+"</div><div class='muted' style='margin-top:9px'>뜻을 고르세요.</div><button class='mic' id='speakWord'>🔊</button>";
      document.getElementById("speakWord").onclick=function(){speak(m.word)};
      distractorMeanings(m).forEach(function(o){const b=document.createElement("button");b.className="choice";b.textContent=o;b.onclick=function(){finishChoice(b,o===m.meaning,o,m,mode,m.meaning,ans)};ans.appendChild(b)});
    }else if(mode==="cloze_choice"){
      prompt.innerHTML="<div class='big'>"+esc(ex.blank)+"</div><div class='muted' style='font-size:17px;margin-top:10px'>"+esc(ex.ko)+"</div>";
      distractorWords(m).forEach(function(o){const b=document.createElement("button");b.className="choice";b.textContent=o;b.onclick=function(){finishChoice(b,norm(o)===norm(m.word),o,m,mode,m.word,ans)};ans.appendChild(b)});addHint(ans,m);
    }else if(mode==="reverse"){
      prompt.innerHTML="<div class='big'>"+esc(m.meaning)+"</div><div class='muted' style='margin-top:9px'>알맞은 단어를 고르세요.</div>";
      distractorWords(m).forEach(function(o){const b=document.createElement("button");b.className="choice";b.textContent=o;b.onclick=function(){finishChoice(b,norm(o)===norm(m.word),o,m,mode,m.word,ans)};ans.appendChild(b)});addHint(ans,m);
    }else if(mode==="cloze_type"){
      prompt.innerHTML="<div class='big'>"+esc(ex.blank)+"</div><div class='muted' style='font-size:17px;margin-top:10px'>"+esc(ex.ko)+"</div>";typedBox(ans,m,mode);
    }else if(mode==="listen"){
      prompt.innerHTML="<div class='big'>듣고 빈칸 단어를 입력하세요.</div><button class='mic' id='playSentence'>🔊</button><div class='muted'>문장을 다시 들을 수 있어요.</div>";
      document.getElementById("playSentence").onclick=function(){speak(ex.full)};typedBox(ans,m,mode);setTimeout(function(){speak(ex.full)},250);
    }else{
      prompt.innerHTML="<div class='big'>"+esc(ex.full)+"</div><div class='muted' style='font-size:17px;margin-top:10px'>"+esc(ex.ko)+"</div><button class='mic' id='sayBtn'>🎙️</button><div class='trans' id='tr'>문장을 말해보세요.</div>";
      document.getElementById("sayBtn").onclick=function(){speechExercise(m,ex.full,ans)};
    }
  };
  function addHint(ans,m){const h=document.createElement("button");h.className="secondary";h.textContent="힌트 듣기";h.onclick=function(){wSess.hint=true;speak(m.word)};ans.appendChild(h)}
  function typedBox(ans,m,mode){
    ans.innerHTML="<input class='ans' id='adaptiveInput' autocomplete='off' autocapitalize='none' spellcheck='false' placeholder='정답 입력'><div class='row'><button class='secondary' id='adaptiveHint'>힌트</button><button class='primary' id='adaptiveCheck'>확인</button></div><div class='muted' id='adaptiveHintText' style='margin-top:8px'></div>";
    document.getElementById("adaptiveHint").onclick=function(){wSess.hint=true;document.getElementById("adaptiveHintText").textContent="첫 글자 "+m.word.slice(0,1)+" · "+m.word.length+"글자";speak(m.word)};
    document.getElementById("adaptiveCheck").onclick=function(){const input=document.getElementById("adaptiveInput"),v=input.value,ok=norm(v)===norm(m.word),ms=Date.now()-wSess.started;input.disabled=true;document.getElementById("adaptiveCheck").disabled=true;document.getElementById("adaptiveHint").disabled=true;updateMemory(m,ok,ms,wSess.hint,mode);if(ok)wSess.correct++;answerPanel(m,ok,mode,v,m.word,ms,wSess.hint)};
  }
  function finishChoice(btn,ok,userAnswer,m,mode,correct,holder){
    if(holder.dataset.done)return;holder.dataset.done="1";const ms=Date.now()-wSess.started;
    holder.querySelectorAll(".choice").forEach(function(b){b.disabled=true;if((mode==="meaning"&&b.textContent===m.meaning)||(mode!=="meaning"&&norm(b.textContent)===norm(m.word)))b.classList.add("ok")});
    if(!ok)btn.classList.add("bad");updateMemory(m,ok,ms,wSess.hint,mode);if(ok)wSess.correct++;answerPanel(m,ok,mode,userAnswer,correct,ms,wSess.hint);
  }
  function speechExercise(m,target,ans){
    const R=window.SpeechRecognition||window.webkitSpeechRecognition,tr=document.getElementById("tr");
    if(!R){tr.textContent="이 Safari에서는 음성 인식이 지원되지 않아 직접 입력 문제로 바꿨어요.";typedBox(ans,m,"cloze_type");return}
    const r=new R();r.lang=S.lang;r.interimResults=true;
    r.onresult=function(e){let t="";for(let i=e.resultIndex;i<e.results.length;i++)t+=e.results[i][0].transcript;tr.textContent=t;if(e.results[e.results.length-1].isFinal){const sc=editSim(t,target),ok=sc>=76,ms=Date.now()-wSess.started;updateMemory(m,ok,ms,false,"speak");if(ok)wSess.correct++;answerPanel(m,ok,"speak",t,target,ms,false)}};
    r.onerror=function(e){tr.textContent="마이크 오류: "+e.error};r.start();
  }
  window.adaptiveFinish=function(){
    ensureState().lessons++;
    if(wSess.placement){const ratio=wSess.p.length?wSess.correct/wSess.p.length:0;setAbility(clamp(1+ratio*12,1,13));ensureState().placementDone=true}
    const t=day();if(S.last!==t){const y=new Date();y.setDate(y.getDate()-1);S.streak=S.last===y.toISOString().slice(0,10)?S.streak+1:1;S.last=t}
    S.done[t]=(S.done[t]||0)+wSess.p.length;save();const pct=Math.round(wSess.correct/Math.max(1,wSess.p.length)*100);
    alert((wSess.placement?"레벨 테스트 완료":"학습 완료")+" · "+pct+"% · 현재 실력 "+Math.round(ability()));show("home");
  };
  window.reviews=function(){
    ensureState();const box=document.getElementById("reviewList"),now=Date.now();
    const due=wordMeta().map(m=>({m:m,r:rec(m.word)})).filter(x=>x.r.seen&&(x.r.due<=now||recallProb(x.m,x.r,now)<.82)).sort((a,b)=>recallProb(a.m,a.r,now)-recallProb(b.m,b.r,now));
    if(!due.length){box.innerHTML="<div class='hero'><h1>지금 복습할 항목이 없어요.</h1><p>잘 외운 단어는 계속 반복하지 않고, 잊을 가능성이 올라갈 때 다시 꺼냅니다.</p></div>";return}
    box.innerHTML="<button class='primary' onclick='wordStart()'>맞춤 복습 시작</button><div class='section'>복습 추천 "+due.length+"개</div>";
    due.slice(0,20).forEach(function(x){const p=Math.round(recallProb(x.m,x.r,now)*100),d=document.createElement("div");d.className="unit";d.innerHTML="<b>"+esc(x.m.word)+"</b><span class='muted'>기억 추정 "+p+"% · 정답 "+x.r.correct+" / 오답 "+x.r.wrong+"</span>";box.appendChild(d)});
  };
  window.typed=function(x){
    const input=document.getElementById("ans"),v=input.value,sc=similar(v,x.t),ok=sc>=80,fb=document.getElementById("fb");input.disabled=true;fb.className="feedback "+(ok?"ok":"bad");
    if(ok)fb.innerHTML="<b>정답!</b><br>"+esc(x.t)+"<br><span class='muted'>"+esc(x.k)+"</span>";
    else{
      let why="",s=editSim(v,x.t);
      if(s>=65)why="<b>철자 또는 일부 표현이 달라요.</b>";
      else if(S.lang==="en-US"&&norm(v).includes("i'm speak"))why="<b>I’m speak</b>는 쓰지 않아요. 현재 사실은 <b>I speak</b>처럼 일반동사를 바로 씁니다.";
      else if(S.lang==="en-US"&&norm(v).includes("can")&&!/\bcan\s+\w+/.test(norm(v)))why="<b>can 뒤에는 동사원형</b>이 필요해요.";
      else why="단어 선택이나 어순이 정답 문장과 달라요.";
      fb.innerHTML="<b>오답</b><br>"+why+"<br><br>정답: <b>"+esc(x.t)+"</b><br><span class='muted'>"+esc(x.k)+"</span>";
    }
    grade(ok,x);nextBtn();
  };
  const css=document.createElement("style");
  css.textContent=".explainPanel{margin-top:14px;padding:16px;border-radius:18px;line-height:1.55}.explainOk{background:#0d2a22;border:1px solid #2d8c70}.explainBad{background:#32151c;border:1px solid #8b3448}.explainTitle{font-size:18px;font-weight:950;margin-bottom:8px}.answerLine{margin-top:9px;font-size:17px}.exampleLine{margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.1)}.coachLine{margin-top:10px;color:#cbd5e1;font-size:13px}.adaptiveStrip{display:grid;grid-template-columns:1fr 1fr 1fr;gap:7px;margin-top:11px}.mini{background:#0e131b;border:1px solid var(--l);border-radius:14px;padding:10px;text-align:center}.mini b{display:block;font-size:17px}.mini small{color:var(--m)}";
  document.head.appendChild(css);
  window.home=function(){
    oldHome();ensureState();
    const hero=document.querySelector("#home .hero");
    if(hero&&!document.getElementById("adaptiveStrip")){const strip=document.createElement("div");strip.id="adaptiveStrip";strip.className="adaptiveStrip";strip.innerHTML="<div class='mini'><b id='aLevel'>1</b><small>실력</small></div><div class='mini'><b id='aDue'>0</b><small>복습</small></div><div class='mini'><b id='aLearned'>0</b><small>학습 단어</small></div>";hero.appendChild(strip)}
    const now=Date.now(),ae=document.getElementById("aLevel"),de=document.getElementById("aDue"),le=document.getElementById("aLearned");
    if(ae)ae.textContent=Math.round(ability());
    if(de)de.textContent=wordMeta().filter(m=>{const r=rec(m.word);return r.seen&&(r.due<=now||recallProb(m,r,now)<.82)}).length;
    if(le)le.textContent=wordMeta().filter(m=>rec(m.word).seen).length;
    const at=document.getElementById("abilityText");if(at)at.textContent="실력 "+Math.round(ability())+" / 30";
    if(!document.getElementById("placementBtn")){const me=document.querySelector("#me .box");if(me){const b=document.createElement("button");b.id="placementBtn";b.className="secondary";b.textContent="빠른 레벨 테스트";b.onclick=placementStart;me.appendChild(b)}}
    reviews();
  };
  setTimeout(function(){home()},0);
})();
