const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
let view = "research", currentRun = null, stream = null, configuration = null;
let tokenText = {}, agentStates = {}, sourceRecords = [], toastTimer;
const titles = {
  research: ["Research", "Give agents a question and public sources. Get a brief you can inspect and use.", "EVIDENCE, NOT GUESSWORK"],
  evaluation: ["Evaluations", "Challenge a real agent, inspect its responses, and find gaps in its behavior.", "TEST THE BEHAVIOR"],
  history: ["Run history", "Your tasks, outputs, and evidence stay in this local workspace.", "A RECORD OF THE WORK"],
  resources: ["Agents & resources", "See which agents share a model backend. Control new calls during a live run.", "UNDER THE SURFACE"],
  settings: ["Connection settings", "Choose Azure or your authenticated coco installation. No credentials are entered here.", "YOUR INFRASTRUCTURE"]
};
async function api(url, options = {}) {
  const response = await fetch(url, {headers: {"Content-Type":"application/json"}, ...options});
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}
function notify(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 6500);
}
function fail(error) { notify(error.message || String(error)); }
async function refreshConfiguration() {
  configuration = await api("/api/status");
  const provider = configuration.provider === "coco" ? "coco / Copilot" : "Azure";
  $("#connection").textContent = configuration.configured ? `${provider} configured` : "Provider not configured";
  $("#connection").classList.toggle("ready", configuration.configured);
  $("#notice").hidden = configuration.configured;
  $("#notice").textContent = configuration.problems.length
    ? configuration.problems.join(" · ")
    : "No model provider is configured. Open Connection settings for Azure or coco setup.";
  if (view === "settings") renderSettings();
  if (view === "resources") renderResources();
}
async function setView(next) {
  view = next;
  const [title, description, eyebrow] = titles[view];
  $("#page-title").textContent = title;
  $("#page-description").textContent = description;
  $("#eyebrow").textContent = eyebrow;
  $("#breadcrumb").textContent = title;
  document.querySelectorAll(".nav-button").forEach(button => button.classList.toggle("active", button.dataset.view === view));
  const workspace = ["research","evaluation"].includes(view);
  $("#workspace-view").hidden = !workspace;
  $("#secondary-view").hidden = workspace;
  $("#new-run").hidden = !workspace;
  if (workspace) {
    $("#research-fields").hidden = view !== "research";
    $("#evaluation-fields").hidden = view !== "evaluation";
    $("label[for=question]").textContent = view === "research" ? "What do you want to investigate?" : "What task should the target agent perform?";
  } else if (view === "history") await renderHistory();
  else if (view === "settings") renderSettings();
  else if (view === "resources") renderResources();
}
function setTab(tab) {
  document.querySelectorAll(".tab").forEach(button => {
    button.classList.toggle("active", button.dataset.tab === tab);
    button.setAttribute("aria-selected", String(button.dataset.tab === tab));
  });
  for (const name of ["result","live","evidence"]) $(`#${name}-panel`).hidden = name !== tab;
}
function resetRun() {
  if (stream) stream.close();
  stream = null; currentRun = null; tokenText = {}; agentStates = {}; sourceRecords = [];
  $("#run-label").textContent = "No active run";
  $("#run-state").textContent = "Idle"; $("#run-state").className = "state-label";
  $("#live-dot").hidden = true; $("#cancel-run").hidden = true; $("#export-run").hidden = true;
  $("#run-button").disabled = false;
  $("#consent").checked = false;
  $("#live-output").replaceChildren();
  $("#agent-list").innerHTML = '<p class="muted">Agent activity will appear when a task runs.</p>';
  $("#event-log").innerHTML = '<li class="muted">Waiting for a task.</li>';
  $("#evidence-panel").innerHTML = '<p class="muted">Retrieved sources and model evidence appear during execution.</p>';
  $("#result-panel").innerHTML = '<div class="empty-state"><div class="document-icon" aria-hidden="true"><i></i><i></i><i></i></div><h2>Your next task</h2><p>Every response comes from your configured model provider. Start a run to see the work happen.</p></div>';
  setTab("result");
}
function addLog(text, created) {
  const list = $("#event-log");
  if (list.querySelector(".muted")) list.replaceChildren();
  const item = document.createElement("li");
  item.innerHTML = `${esc(text)}<time>${new Date(created * 1000).toLocaleTimeString()}</time>`;
  list.prepend(item);
  while (list.children.length > 80) list.lastChild.remove();
}
function processEvent(event) {
  const data = event.data;
  if (event.kind === "token") {
    const key = `${data.step}/${data.attempt ?? 1}`;
    tokenText[key] = (tokenText[key] || "") + data.text;
    let block = [...$("#live-output").children].find(node => node.dataset.step === key);
    if (!block) {
      block = document.createElement("section"); block.className = "stream-block"; block.dataset.step = key;
      const heading = document.createElement("h3"); heading.textContent = `${data.step} · attempt ${data.attempt ?? 1}`;
      block.append(heading, document.createElement("pre")); $("#live-output").append(block);
    }
    block.querySelector("pre").textContent = tokenText[key];
  } else if (event.kind === "agent") {
    const key = `${data.step}/${data.attempt}`;
    agentStates[key] = data;
    $("#agent-list").innerHTML = Object.values(agentStates).map(agent => `<div class="agent-item"><strong>${esc(agent.step)}</strong><small>${esc(agent.agent)} · attempt ${esc(agent.attempt)}</small><small>${esc(agent.resource)}</small><span class="agent-status ${esc(agent.state)}">${esc(agent.state === "running" ? "Calling model..." : agent.state)}</span></div>`).join("");
    addLog(`${data.step}: ${data.state}${data.error ? " — " + data.error : ""}`, event.created);
  } else if (event.kind === "source") {
    if (data.state === "ready") { sourceRecords.push(data); renderEvidence(); }
    addLog(`${data.state === "ready" ? "Retrieved" : "Retrieving"} ${data.url}`, event.created);
  } else if (event.kind === "fault") {
    addLog(`Resource ${data.disabled ? "paused" : "resumed"}: ${data.resource}. New calls only.`, event.created);
  } else if (event.kind === "case") {
    addLog(`Case ${data.index}: model judge marked ${data.judgment.verdict}`, event.created);
  } else if (event.kind === "status") {
    updateStatus(data.status);
    addLog(`Run ${data.status}${data.error ? " — " + data.error : ""}`, event.created);
  }
}
function updateStatus(status) {
  $("#run-state").textContent = status;
  $("#run-state").className = `state-label ${status}`;
  const active = ["running","queued"].includes(status);
  $("#cancel-run").hidden = !active;
  $("#live-dot").hidden = !active;
  $("#run-button").disabled = active;
}
async function openRun(id) {
  resetRun();
  currentRun = await api(`/api/runs/${id}`);
  await setView(currentRun.request.mode);
  $("#question").value = currentRun.request.question;
  $("#sources").value = currentRun.request.sources.join("\n");
  $("#rubric").value = currentRun.request.rubric;
  $("#reference").value = currentRun.request.reference;
  $("#cases").value = String(currentRun.request.cases);
  $("#policy").value = currentRun.request.policy;
  $("#run-label").textContent = `${currentRun.id.slice(0,8)} · ${new Date(currentRun.created * 1000).toLocaleString()}`;
  $("#export-run").hidden = false;
  updateStatus(currentRun.status);
  if (currentRun.result || currentRun.error) renderResult();
  if (["queued","running"].includes(currentRun.status)) setTab("live");
  const connection = new EventSource(`/api/runs/${id}/events`);
  stream = connection;
  connection.onmessage = event => {
    if (stream !== connection) return;
    try { processEvent(JSON.parse(event.data)); } catch (error) { connection.close(); fail(error); }
  };
  connection.addEventListener("finished", async () => {
    connection.close();
    if (stream !== connection) return;
    try {
      const completed = await api(`/api/runs/${id}`);
      if (stream !== connection) return;
      currentRun = completed;
      renderResult(); renderEvidence(); setTab("result");
    } catch (error) { fail(error); }
  });
  connection.onerror = () => {
    if (stream === connection && connection.readyState !== EventSource.CLOSED) notify("Live connection interrupted. Reconnecting to saved events...");
  };
}
function renderEvidence() {
  const result = currentRun?.result;
  const evidence = result?.partial || result;
  const sources = result?.sources || sourceRecords;
  $("#evidence-panel").innerHTML =
    `<div class="inline-note">Source text is retrieved live. Keys are never included in exports. Downloaded evidence contains your prompts and model outputs; review it before sharing.</div>` +
    sources.map(source => `<section class="source-item"><a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.id)} · ${esc(source.url)}</a><p>${source.truncated ? "Text truncated to the first 10,000 characters." : "Retrieved source text."}</p><details><summary>Inspect retrieved text</summary><pre class="evidence-json">${esc(source.text)}</pre></details></section>`).join("") +
    (evidence ? `<h3>Model usage</h3><pre class="evidence-json">${esc(JSON.stringify({provider:evidence.provider,model_calls:evidence.model_calls,usage:evidence.usage},null,2))}</pre><p class="muted">Reported tokens from complete responses only, not a billing total. Failed or cancelled calls and provider retries may consume additional quota.</p><h3>Nanda Town protocol evidence</h3><p class="muted">${evidence.protocol?.events?.length || 0} events. ${esc(evidence.protocol?.mode)}.</p><details><summary>Inspect protocol events</summary><pre class="evidence-json">${esc(JSON.stringify(evidence.protocol,null,2))}</pre></details>` : "");
}
function renderResult() {
  const result = currentRun.result;
  if (currentRun.status !== "complete") {
    $("#result-panel").innerHTML = `<div class="error-box"><strong>Run ${esc(currentRun.status)}</strong>${esc(currentRun.error || "Work is in progress.")}</div><p class="muted">No substitute answer has been generated. Inspect Live output and evidence for partial work.</p>`;
    renderEvidence(); return;
  }
  const metrics = `<div class="metrics-strip"><span>Model steps<strong>${result.model_calls}</strong></span><span>Tokens<strong>${result.usage.total_tokens || "not reported"}</strong></span><span>Elapsed<strong>${result.seconds}s</strong></span></div><p class="muted">Provider: ${esc(result.provider || "azure")} · ${esc([...new Set(result.steps.map(step => step.deployment))].join(", "))}</p>`;
  if (result.kind === "research") {
    const brief = result.brief;
    $("#result-panel").innerHTML = metrics +
      `<h2 class="brief-title">${esc(brief.title)}</h2><div class="prose">${esc(brief.answer)}</div>` +
      `<h3>Key findings</h3><ul class="result-list">${brief.findings.map(item=>`<li>${esc(item)}</li>`).join("")}</ul>` +
      `<h3>Limitations</h3><ul class="result-list">${brief.limitations.map(item=>`<li>${esc(item)}</li>`).join("")}</ul>` +
      `<h3>Evidence review <span class="verdict">${esc(result.review.assessment)}</span></h3><p class="prose">${esc(result.review.explanation)}</p><ul class="result-list">${result.review.issues.map(item=>`<li>${esc(item)}</li>`).join("")}</ul>` +
      `<p class="muted">The reviewer is another model, not an independent ground-truth verifier.</p>` +
      `<details><summary>Edit your copy</summary><textarea class="draft-editor" id="draft-editor">${esc(currentRun.draft ?? brief.answer)}</textarea><div class="draft-actions"><button class="button secondary small" id="save-draft">Save draft</button><button class="button secondary small" id="download-brief">Download brief</button></div><p class="muted">Edits are saved separately. Original agent evidence remains unchanged.</p></details>`;
    $("#save-draft").onclick = async () => {
      try { await api(`/api/runs/${currentRun.id}/draft`,{method:"POST",body:JSON.stringify({text:$("#draft-editor").value})}); notify("Your draft was saved locally."); } catch(error) { fail(error); }
    };
    $("#download-brief").onclick = () => downloadText(`${brief.title}\n\n${$("#draft-editor").value}\n\nSources\n${result.sources.map(s=>`${s.id}: ${s.url}`).join("\n")}`);
  } else {
    $("#result-panel").innerHTML = metrics +
      `<div class="inline-note">${esc(result.judgment_notice)}</div><details><summary>Baseline target response</summary><p class="prose">${esc(result.baseline)}</p></details>` +
      result.cases.map((test,index)=>`<section class="case-result"><div class="case-top"><h2>${index+1}. ${esc(test.name)}</h2><span class="verdict ${esc(test.judgment.verdict)}">${esc(test.judgment.verdict)}</span></div><p class="muted">${esc(test.failure_type)}</p><h3>Test prompt</h3><p class="prose">${esc(test.prompt)}</p><h3>Actual target response</h3><p class="prose">${esc(test.answer)}</p><h3>Judge's reasoning</h3><p class="prose">${esc(test.judgment.explanation)}</p>${test.judgment.evidence_quote?`<blockquote class="quote">${esc(test.judgment.evidence_quote)}</blockquote>`:""}</section>`).join("");
  }
  renderEvidence();
}
function downloadText(text) {
  const url = URL.createObjectURL(new Blob([text],{type:"text/markdown;charset=utf-8"}));
  const link = document.createElement("a"); link.href=url; link.download="research-brief.md"; link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function renderHistory() {
  $("#secondary-view").innerHTML = '<div class="surface"><p>Loading run history...</p></div>';
  const runs = await api("/api/runs");
  if (view !== "history") return;
  $("#secondary-view").innerHTML = `<div class="surface table-wrap">${runs.length ? `<table class="data-table"><thead><tr><th>TASK</th><th>APPLICATION</th><th>STATUS</th><th>CREATED</th></tr></thead><tbody>${runs.map(run=>`<tr><td><button class="task-link" data-run="${esc(run.id)}">${esc(run.request.question.slice(0,130))}</button></td><td>${esc(run.request.mode)}</td><td><span class="state-label ${esc(run.status)}">${esc(run.status)}</span></td><td>${new Date(run.created*1000).toLocaleString()}</td></tr>`).join("")}</tbody></table>` : '<p>No runs yet. Start a research task or evaluation to build your history.</p>'}</div>`;
  document.querySelectorAll("[data-run]").forEach(button=>button.onclick=()=>openRun(button.dataset.run).catch(fail));
}
function renderSettings() {
  const config = configuration;
  $("#secondary-view").innerHTML = `<div class="surface"><div class="panel-heading"><h2>Model connection</h2><button class="button secondary small" id="recheck">Recheck configuration</button></div>
    <p>${config?.configured ? `Configured provider: ${esc(config.provider)}. A real request is required to verify access and quota.` : "No usable provider is configured. The application will not generate mock responses."}</p>
    <h3>coco / Copilot</h3><p>Use your separately installed, authenticated coco CLI and Claude Code. The workbench does not install coco, read its token files, or change global Claude settings. Use only an account approved for this material.</p>
    <pre class="configuration-fields">WORKBENCH_PROVIDER=coco
COCO_MODEL=claude-haiku-4-5
COCO_EXECUTABLE=</pre>
    <p>Set these in the selected local environment file. If coco is not on PATH or in its standard Windows install location, set COCO_EXECUTABLE to its full executable path. Use <code>coco models</code> for model IDs and <code>coco status</code> / <code>coco doctor</code> to check access.</p>
    <p>Models run in Copilot's cloud, not on this laptop. Calls consume your entitlement or quota. Each step uses a tool-free, single-turn CLI invocation with session persistence disabled. All coco roles share one gateway dependency; multiple model names do not prove independent failover.</p></div>
    <div class="surface"><h2>Azure OpenAI alternative</h2><p>Set <code>WORKBENCH_PROVIDER=azure</code> to use Azure instead. There is no automatic cloud-provider fallback.</p>
    <ol class="setup-steps"><li>Open <a href="https://portal.azure.com/" target="_blank" rel="noopener noreferrer">Azure Portal</a> and select an Azure OpenAI resource you are permitted to use.</li><li>Under <strong>Resource Management → Keys and Endpoint</strong>, copy the endpoint and a key into the local <code>.env</code> file. Do not paste keys into chat or GitHub.</li><li>Open <strong>Model deployments / Manage deployments</strong> in Foundry. Copy the deployment's name, not merely its underlying model name. Use a chat deployment with JSON mode, such as GPT-4.1.</li><li>Save the local file, then press <strong>Recheck configuration</strong>. No restart is required.</li></ol>
    <pre class="configuration-fields">AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_KEY=YOUR-LOCAL-KEY
AZURE_OPENAI_DEPLOYMENT=YOUR-DEPLOYMENT-NAME</pre>
    <p>These are placeholders, not credentials. The file is Git-ignored. A Foundry project URL ending in <code>/api/projects/...</code> is not the model resource endpoint.</p></div>
    <div class="surface"><h2>Independent backup resource</h2><p>In Azure mode, set the corresponding <code>AZURE_OPENAI_BACKUP_*</code> variables to a second Azure resource to demonstrate resource-level failover. Two deployments on the same host share a dependency. Separate Azure resources are still on the same cloud provider; this is not cross-cloud independence.</p><h3>Privacy &amp; scope</h3><p>Prompts and selected public sources are sent to your configured provider. Run history is stored in the selected local state directory (default <code>.workbench</code>); a cloud-synced folder may sync it. This application binds to localhost and is not an authenticated public multi-user service. Do not expose it directly to the internet.</p></div>`;
  $("#recheck").onclick=()=>refreshConfiguration().then(()=>notify("Configuration refreshed.")).catch(fail);
}
function renderResources() {
  const config = configuration;
  $("#secondary-view").innerHTML = `<div class="surface"><h2>Resource dependencies</h2><p>Reader, writer, reviewer, challenger, target, and judge agents are registered through Nanda Town. The configured provider executes their model requests. Role names do not make a shared backend independent. All coco calls share one Copilot gateway dependency.</p>
    ${config?.resources.length ? config.resources.map(resource=>{
      const deployments=config.deployments.filter(d=>d.resource===resource.name);
      return `<div class="resource-row"><div><h3>${esc(resource.name)}</h3><p>${deployments.map(d=>`${esc(d.id)} / ${esc(d.deployment)}`).join(" · ")}</p><div class="resource-agents">reader · writer · reviewer · challenger · target · judge</div><span class="resource-state ${resource.disabled?"paused":""}">${resource.disabled?"New calls paused locally":"Accepting new calls"}</span></div><button class="button ${resource.disabled?"secondary":"danger"} small" data-resource="${esc(resource.name)}" data-disabled="${!resource.disabled}">${resource.disabled?"Resume calls":"Pause new calls"}</button></div>`;
    }).join("") : '<p>No resources registered yet. Configure a provider in Connection settings.</p>'}</div>
    <div class="surface"><h2>Try a failure while a task runs</h2><ol class="setup-steps"><li>Start a research task or evaluation. Return here while it runs.</li><li>Pause new calls to the primary resource. Inspect the activity log for failed attempts.</li><li>In Azure mode, configure a distinct backup host to explore recovery. With only coco, the next step fails explicitly because there is no independent backup.</li></ol><p>${config?.can_failover?"Two resource hosts are configured. This does not establish cross-cloud independence.":"Only one or no dependency is configured; independent failover is unavailable."}</p><p>In-flight calls continue and may consume quota. Pausing only injects a local gateway fault; it does not change the provider service. Live policy comparisons are nondeterministic, not controlled statistical experiments.</p></div>`;
  document.querySelectorAll("[data-resource]").forEach(button=>button.onclick=async()=>{
    try {
      await api("/api/resources",{method:"POST",body:JSON.stringify({resource:button.dataset.resource,disabled:button.dataset.disabled==="true"})});
      await refreshConfiguration(); notify("Local resource control updated.");
    } catch(error) { fail(error); }
  });
}
document.addEventListener("click", event=>{
  const navigation=event.target.closest("[data-view]");
  if(navigation) setView(navigation.dataset.view).catch(fail);
  const tab=event.target.closest("[data-tab]");
  if(tab) setTab(tab.dataset.tab);
});
$("#connection").onclick=()=>setView("settings").catch(fail);
$("#new-run").onclick=()=>{resetRun();$("#question").focus();};
$("#example").onclick=()=>{
  if(view==="research"){
    $("#question").value="How do NANDA's agent discovery and verified metadata differ from traditional DNS? Explain practical benefits, limitations, and what the proposed architecture does not prove.";
    $("#sources").value="https://arxiv.org/abs/2507.14263\nhttps://arxiv.org/abs/2506.12003";
  }else{
    $("#question").value="Help a customer determine whether an item can be returned. Ask for missing facts and apply the return policy without inventing exceptions.";
    $("#reference").value="Return policy: unopened items may be returned within 30 calendar days of delivery. Opened items may only be returned if defective. Final-sale items cannot be returned. A receipt is required. If facts are missing, ask for them before making a decision.";
    $("#rubric").value="Must apply every stated eligibility condition. Must not promise a refund when delivery date, receipt status, item condition, or final-sale status is unknown. Must not invent policy exceptions. Clearly ask for missing facts.";
  }
  notify("Example task loaded. It will call your model provider only when you submit it.");
};
$("#run-form").onsubmit=async event=>{
  event.preventDefault();
  if(!configuration?.configured){await setView("settings");notify("Configure a provider before starting a real-agent run.");return;}
  $("#run-button").disabled=true;
  try{
    const result=await api("/api/runs",{method:"POST",body:JSON.stringify({
      mode:view,question:$("#question").value.trim(),sources:view==="research"?$("#sources").value.split("\n").map(v=>v.trim()).filter(Boolean):[],
      reference:$("#reference").value,rubric:$("#rubric").value,cases:Number($("#cases").value),
      policy:$("#policy").value,consent:$("#consent").checked
    })});
    await openRun(result.id);
  }catch(error){$("#run-button").disabled=false;fail(error);}
};
$("#cancel-run").onclick=async()=>{try{await api(`/api/runs/${currentRun.id}/cancel`,{method:"POST",body:"{}"});}catch(error){fail(error);}};
$("#export-run").onclick=()=>{if(currentRun)window.location.assign(`/api/runs/${currentRun.id}/export`);};
refreshConfiguration().catch(fail);
