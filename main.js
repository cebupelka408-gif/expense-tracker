const bynFormatter=new Intl.NumberFormat("ru-BY",{style:"currency",currency:"BYN",maximumFractionDigits:2});
const formatBYN=v=>bynFormatter.format(Number(v)||0);
const themeToggle=document.getElementById("themeToggle");const hamburger=document.getElementById("hamburger");const nav=document.getElementById("nav");
if(localStorage.getItem("theme")==="dark")document.body.classList.add("dark");
if(themeToggle)themeToggle.addEventListener("click",()=>{document.body.classList.toggle("dark");localStorage.setItem("theme",document.body.classList.contains("dark")?"dark":"light");});
if(hamburger&&nav)hamburger.addEventListener("click",()=>nav.classList.toggle("open"));
const modal=document.getElementById("expenseModal");const form=document.getElementById("expenseForm");
const modalTitle=document.getElementById("modalTitle");const formError=document.getElementById("formError");let editingId=null;
function openModal(e=null){if(!modal)return;editingId=e?Number(e.id):null;modalTitle.textContent=e?"Редактировать расход":"Новый расход";
document.getElementById("amount").value=e?e.amount:"";document.getElementById("category").value=e?e.category:document.getElementById("category").options[0].value;
document.getElementById("date").value=e?e.date:new Date().toISOString().slice(0,10);document.getElementById("comment").value=e?e.comment:"";
formError.classList.add("hidden");modal.classList.remove("hidden");}
function closeModal(){if(!modal)return;modal.classList.add("hidden");editingId=null;form.reset();}
if(modal){document.getElementById("addExpenseBtn").addEventListener("click",()=>openModal());
document.getElementById("closeModal").addEventListener("click",closeModal);document.getElementById("cancelModal").addEventListener("click",closeModal);
modal.addEventListener("click",e=>{if(e.target===modal)closeModal();});
document.querySelectorAll(".edit").forEach(b=>b.addEventListener("click",()=>openModal(b.dataset)));
document.querySelectorAll(".delete").forEach(b=>b.addEventListener("click",async()=>{if(!confirm("Удалить расход?"))return;
const r=await fetch(`/api/expenses/${b.dataset.id}`,{method:"DELETE"});if(r.ok)location.reload();}));
form.addEventListener("submit",async e=>{e.preventDefault();const p={amount:Number(document.getElementById("amount").value),
category:document.getElementById("category").value,date:document.getElementById("date").value,comment:document.getElementById("comment").value};
const url=editingId?`/api/expenses/${editingId}`:"/api/expenses";const r=await fetch(url,{method:editingId?"PUT":"POST",
headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});if(!r.ok){const d=await r.json();formError.textContent=d.error||"Ошибка сохранения";formError.classList.remove("hidden");return;}location.reload();});}
function renderStat(t,v,h=""){return `<div class="stat"><small>${t}</small><strong>${v}</strong>${h?`<span>${h}</span>`:""}</div>`;}
function renderListItem(i,v){return `<div class="list-item"><div class="list-icon" style="background:${i.color}22;color:${i.color}"><i class="fa-solid ${i.icon}"></i></div><div><div class="title">${i.comment||i.category_name}</div><div class="meta">${i.category_name} · ${i.date}</div></div><div class="value">${v}</div></div>`;}
function destroyChart(id){const c=Chart.getChart(id);if(c)c.destroy();}
async function loadStats(){const s=document.getElementById("stats");const a=document.getElementById("analyticsStats");
if(!s&&!a)return;const stats=await(await fetch("/api/stats")).json();const hasData=stats.byMonth.length>0||stats.recent.length>0;
if(window.pageType==="dashboard"){document.getElementById("emptyDashboard").classList.toggle("hidden",hasData);
document.getElementById("dashboardContent").classList.toggle("hidden",!hasData);if(!hasData)return;
s.innerHTML=[renderStat("Расходы за месяц",formatBYN(stats.currentMonthTotal)),renderStat("Средний расход в день",formatBYN(stats.averagePerDay)),
renderStat("Самая затратная категория",stats.topCategory||"—"),renderStat("Сравнение с прошлым месяцем",`${stats.changePercent>0?"+":""}${stats.changePercent}%`,`Прошлый месяц: ${formatBYN(stats.previousMonthTotal)}`)].join("");
document.getElementById("recentList").innerHTML=stats.recent.map(i=>renderListItem(i,formatBYN(i.amount))).join("");
destroyChart("categoryChart");new Chart(document.getElementById("categoryChart"),{type:"doughnut",data:{labels:stats.byCategory.map(i=>i.name),datasets:[{data:stats.byCategory.map(i=>i.total),backgroundColor:stats.byCategory.map(i=>i.color)}]},options:{plugins:{tooltip:{callbacks:{label:c=>`${c.label}: ${formatBYN(c.raw)}`}}}}});
destroyChart("dailyChart");new Chart(document.getElementById("dailyChart"),{type:"bar",data:{labels:stats.byDay.map(i=>i.date.slice(5)),datasets:[{label:"Расходы",data:stats.byDay.map(i=>i.total),backgroundColor:"#4f46e5",borderRadius:6}]},options:{plugins:{tooltip:{callbacks:{label:c=>formatBYN(c.raw)}}},scales:{y:{ticks:{callback:v=>formatBYN(v)}}}}});
destroyChart("monthlyChart");new Chart(document.getElementById("monthlyChart"),{type:"line",data:{labels:stats.byMonth.map(i=>i.month),datasets:[{label:"Расходы",data:stats.byMonth.map(i=>i.total),borderColor:"#10b981",backgroundColor:"rgba(16,185,129,.15)",fill:true,tension:.35}]},options:{plugins:{tooltip:{callbacks:{label:c=>formatBYN(c.raw)}}},scales:{y:{ticks:{callback:v=>formatBYN(v)}}}}});}
if(window.pageType==="analytics"){document.getElementById("emptyAnalytics").classList.toggle("hidden",hasData);
document.getElementById("analyticsContent").classList.toggle("hidden",!hasData);if(!hasData)return;
a.innerHTML=[renderStat("Расходы в текущем месяце",formatBYN(stats.currentMonthTotal)),renderStat("Средний расход в день",formatBYN(stats.averagePerDay)),renderStat("Прогноз до конца месяца",formatBYN(stats.forecast),"На основе текущего темпа")].join("");
document.getElementById("topExpenses").innerHTML=stats.topExpenses.map(i=>renderListItem(i,formatBYN(i.amount))).join("");
document.getElementById("averageCheck").innerHTML=stats.averageCheck.map(i=>`<div class="list-item"><div class="title">${i.category}</div><div class="meta">${i.count} операций</div><div class="value">${formatBYN(i.average)}</div></div>`).join("");
destroyChart("analyticsMonthlyChart");new Chart(document.getElementById("analyticsMonthlyChart"),{type:"bar",data:{labels:stats.byMonth.map(i=>i.month),datasets:[{label:"Расходы",data:stats.byMonth.map(i=>i.total),backgroundColor:"#8b5cf6",borderRadius:6}]},options:{plugins:{tooltip:{callbacks:{label:c=>formatBYN(c.raw)}}},scales:{y:{ticks:{callback:v=>formatBYN(v)}}}}});}}
loadStats();
