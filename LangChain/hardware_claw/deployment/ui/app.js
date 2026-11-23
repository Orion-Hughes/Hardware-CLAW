"use strict";
const base = "/hardware-claw-flash/api";
const $ = (id) => document.getElementById(id);
const state = {csrf: null, projects: [], info: null, plan: null, job: null, busy: false, poll: null, selecting: 0};
const done = new Set(["completed", "failed", "cancelled"]);

function notice(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}
function describe(error) {
  const d = error.detail ?? error;
  if (Array.isArray(d)) return d.map((e) => e.msg).join("；");
  return typeof d === "string" ? d : (d.summary || d.code || "本地请求失败");
}
async function api(path, body) {
  const options = {credentials: "same-origin", cache: "no-store"};
  if (body !== undefined) {
    options.method = "POST";
    options.headers = {"Content-Type": "application/json", "X-HWClaw-CSRF": state.csrf};
    options.body = JSON.stringify(body);
  }
  const response = await fetch(base + path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(describe(data));
  return data;
}
function busy(value) {
  state.busy = value;
  for (const id of ["project-search", "project-select", "port-select", "board-select", "rebuild",
                    "hardware-reviewed", "risk-reviewed", "refresh-projects", "refresh-ports"]) $(id).disabled = value;
  $("cancel-button").disabled = !value || !state.job;
  updateButtons();
}
function updateButtons() {
  $("prepare-button").disabled = state.busy || !state.info || !state.info.supported;
  $("prepare-button").textContent = $("rebuild").checked ? "检查、编译并准备预览" : "检查并准备预览";
  $("flash-button").disabled = state.busy || !state.plan?.ready;
}
function invalidate() {
  state.plan = null;
  $("preview").hidden = true;
  $("preview-empty").hidden = false;
  if ($("confirm-dialog").open) $("confirm-dialog").close();
  updateButtons();
}
function options(select, items, placeholder, selected = "") {
  select.replaceChildren(new Option(placeholder, ""));
  for (const item of items) select.add(new Option(item.label, item.value));
  if ([...select.options].some((o) => o.value === selected)) select.value = selected;
}
function filterProjects() {
  const query = $("project-search").value.trim().toLowerCase();
  const selected = $("project-select").value;
  const visible = state.projects.filter((p) => (p.id + " " + p.title).toLowerCase().includes(query));
  options($("project-select"), visible.map((p) => ({value: p.id, label: p.id + " · v" + p.version})),
          visible.length ? "请选择工程文件夹" : "没有匹配的工程", selected);
  // Filtering must not leave a hidden, previously selected project actionable.
  if (!$("project-select").value && state.info) {
    state.info = null; $("project-info").hidden = true; invalidate();
  }
}
async function refreshProjects() {
  const selected = $("project-select").value;
  state.projects = (await api("/projects")).items;
  filterProjects();
  if (selected) $("project-select").value = selected;
}
async function chooseProject() {
  const id = $("project-select").value;
  const revision = ++state.selecting;
  state.info = null; invalidate(); $("project-info").hidden = true;
  if (!id) return;
  try {
    const info = await api("/projects/" + encodeURIComponent(id));
    if (revision !== state.selecting) return;
    state.info = info;
    sessionStorage.setItem("hwclaw.flash.project", id);
    $("project-info").hidden = false;
    $("project-title").textContent = info.title || id;
    $("project-path").textContent = info.folder;
    $("project-requirement").textContent = info.requirement || "未记录需求";
    $("project-components").textContent = "元件：" + (info.components.map((c) => c.hardware_id).join("、") || "无外设");
    const labels = ["版本 " + info.version, "静态检查 " + info.check, "编译 " + info.build];
    $("project-badges").replaceChildren(...labels.map((text) => {
      const el = document.createElement("span"); el.className = "badge"; el.textContent = text; return el;
    }));
    $("project-build-hint").textContent = !info.supported ? info.unsupported_reason :
      (!info.build_matches ? "旧构建与当前源码/本地驱动不匹配，请勾选重新编译。" :
      (info.upload_images !== "ready" ? "旧构建缺少完整烧录镜像，请勾选重新编译。" : "已有匹配构建；准备时仍会重新检查镜像与版本。"));
    notice();
    updateButtons();
  } catch (e) { notice(e.message); }
}
async function refreshPorts() {
  const selected = $("port-select").value;
  const data = await api("/ports");
  options($("port-select"), data.items.map((p) => ({value: p.device, label: p.device + " · " + (p.description || "串口设备")})),
          data.items.length ? "请选择开发板对应的串口" : "未枚举到串口（仍可编译和预览）", selected);
  $("port-hint").textContent = data.items.length ? "共 " + data.items.length + " 个端口；未自动选择，也未打开设备。" :
    "检查 USB 数据线、连接与驱动后点刷新；端口列表为空不代表工程编译失败。";
}
function lines(parent, values) {
  parent.replaceChildren(...values.map((value) => {const el = document.createElement("li"); el.textContent = value; return el;}));
}
function showPlan(plan) {
  state.plan = plan;
  $("preview-empty").hidden = true; $("preview").hidden = false;
  $("plan-status").textContent = plan.ready ? "可确认烧录 · 尚未执行" : "预览完成 · 待确认";
  $("plan-version").textContent = "版本 " + plan.version;
  const pairs = [["工程", plan.project_id], ["串口", plan.port?.device || "未选择"],
    ["目标", plan.profile.module || plan.profile.board],
    ["Flash / PSRAM", plan.profile.flash_size + " / " + (plan.profile.psram_enabled ? "OPI PSRAM 已配置（未实测）" : "未启用 PSRAM")],
    ["有效期", new Date(plan.expires_at * 1000).toLocaleTimeString()]];
  $("plan-meta").replaceChildren(...pairs.flatMap(([key, value]) => {
    const term = document.createElement("dt"), def = document.createElement("dd");
    term.textContent = key; def.textContent = value; return [term, def];
  }));
  $("image-list").replaceChildren(...plan.images.map((image) => {
    const row = document.createElement("tr");
    for (const value of [image.name, "0x" + image.offset.toString(16).padStart(4, "0"), image.bytes.toLocaleString() + " B"]) {
      const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
    }
    row.title = "SHA-256: " + image.sha256;
    return row;
  }));
  lines($("plan-blockers"), plan.blockers || []); lines($("plan-warnings"), plan.warnings || []);
  $("plan-path").textContent = plan.plan_path;
  if (state.info?.id === plan.project_id) {
    $("project-build-hint").textContent = "本次预览的检查、编译指纹及完整镜像已通过校验；仍须核对实物和目标设备。";
    $("project-badges").replaceChildren(...["版本 " + plan.version, "静态检查 pass", "编译 pass"].map((text) => {
      const el = document.createElement("span"); el.className = "badge"; el.textContent = text; return el;
    }));
  }
  updateButtons();
}
function renderJob(job) {
  state.job = job.id;
  const names = {queued: "等待执行", checking: "静态检查", compiling: "正在编译", preparing: "准备预览", uploading: "正在烧录"};
  const finished = {completed: "操作完成", failed: "操作失败", cancelled: "任务已取消"};
  $("job-status").textContent = finished[job.status] || names[job.phase] || "执行中";
  $("job-message").textContent = job.message || "";
  $("job-dot").className = "dot " + (done.has(job.status) ? job.status : "running");
  const log = $("job-log"), atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 30;
  log.textContent = job.log_tail || (job.kind === "prepare" ? "正在检查或准备；本任务不会写入开发板。" : "正在等待烧录日志…");
  if (atBottom) log.scrollTop = log.scrollHeight;
  $("error-details").hidden = !job.error;
  $("error-json").textContent = job.error ? JSON.stringify({error: job.error, result: job.result}, null, 2) : "";
  if (done.has(job.status)) {
    busy(false);
    if (job.kind === "prepare" && job.result?.plan) showPlan(job.result.plan);
    else if (job.kind === "execute") {
      state.plan = null; updateButtons();
      if (job.status === "completed") $("plan-status").textContent = "烧录工具完成 · 功能尚未验证";
    }
  } else busy(true);
}
async function pollJob(id, failures = 0) {
  clearTimeout(state.poll);
  try {
    const job = await api("/jobs/" + encodeURIComponent(id));
    renderJob(job);
    if (!done.has(job.status)) state.poll = setTimeout(() => pollJob(id), 850);
  } catch (e) {
    notice("读取任务状态失败：" + e.message + "。这不代表后台任务已经停止。");
    if (failures < 4) state.poll = setTimeout(() => pollJob(id, failures + 1), 1800);
    else {busy(true); $("cancel-button").disabled = true; $("job-status").textContent = "连接中断，请刷新页面恢复状态";}
  }
}
$("prepare-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy || !state.info) return;
  const request = {project_id: state.info.id, version: state.info.version,
    port: $("port-select").value || null, board: $("board-select").value || null,
    hardware_reviewed: $("hardware-reviewed").checked && $("risk-reviewed").checked,
    rebuild: $("rebuild").checked};
  notice(); invalidate(); busy(true);
  try {const job = await api("/prepare", request); renderJob(job); pollJob(job.id);}
  catch (e) {busy(false); notice(e.message);}
});
$("flash-button").addEventListener("click", () => {
  if (state.busy || !state.plan?.ready) return;
  if (Date.now() > state.plan.expires_at * 1000) {invalidate(); notice("预览已过期，请重新准备。"); return;}
  $("confirm-summary").textContent = "工程：" + state.plan.project_id + " · v" + state.plan.version +
    "\n串口：" + state.plan.port.device + "\n板卡：" + (state.plan.profile.module || state.plan.profile.board);
  $("confirm-text").value = ""; $("execute-button").disabled = true;
  $("confirm-dialog").showModal(); $("confirm-text").focus();
});
$("confirm-text").addEventListener("input", () => {$("execute-button").disabled = $("confirm-text").value !== "确认烧录";});
$("dismiss-confirm").addEventListener("click", () => $("confirm-dialog").close());
$("execute-button").addEventListener("click", async () => {
  if (!state.plan?.ready || $("confirm-text").value !== "确认烧录" || state.busy) return;
  const id = state.plan.plan_id;
  $("confirm-dialog").close(); notice(); busy(true);
  try {const job = await api("/execute", {plan_id: id, confirmation_text: "确认烧录"}); state.plan = null; renderJob(job); pollJob(job.id);}
  catch (e) {busy(false); invalidate(); notice(e.message);}
});
$("cancel-button").addEventListener("click", async () => {
  if (!state.job) return;
  $("cancel-button").disabled = true;
  try {renderJob(await api("/jobs/" + encodeURIComponent(state.job) + "/cancel", {}));}
  catch (e) {notice(e.message + "。请确认后台状态，不要假设任务已停止。");}
});
$("refresh-projects").addEventListener("click", () => {invalidate(); refreshProjects().then(chooseProject).catch((e) => notice(e.message));});
$("refresh-ports").addEventListener("click", () => {invalidate(); refreshPorts().catch((e) => notice(e.message));});
$("project-search").addEventListener("input", filterProjects);
$("project-select").addEventListener("change", chooseProject);
for (const id of ["port-select", "board-select", "hardware-reviewed", "risk-reviewed", "rebuild"]) $(id).addEventListener("change", invalidate);

(async () => {
  try {
    const data = await api("/bootstrap"); state.csrf = data.csrf;
    $("workspace-path").textContent = "工程根目录：" + data.workspace;
    options($("board-select"), data.boards.map((b) => ({value: b.id, label: b.id + " · " + b.description})), "请选择并核对目标配置");
    await Promise.all([refreshProjects(), refreshPorts()]);
    const prior = data.latest_job ? await api("/jobs/" + encodeURIComponent(data.latest_job)).catch(() => null) : null;
    const selected = prior?.project_id || sessionStorage.getItem("hwclaw.flash.project");
    if (state.projects.some((p) => p.id === selected)) {$("project-select").value = selected; await chooseProject();}
    if (prior) await pollJob(prior.id);
  } catch (e) {notice("页面初始化失败：" + e.message + "。请刷新页面重试。");}
})();
