"use strict";

const sections = {
  ideas: {title:"Идеи для видео", description:"Выбирайте темы, которые хочется превратить в новые ролики.", overline:"ПРОСТРАНСТВО ИДЕЙ", heading:"Ваши идеи", subtitle:"Всё, что поможет выбрать следующую тему."},
  competitors: {title:"Конкуренты", description:"Каналы и находки, которые помогут лучше понять вашу нишу.", overline:"ОБЗОР НИШИ", heading:"Кандидаты в конкуренты", subtitle:"Материалы, подготовленные вашим продюсером."},
  niche: {title:"Ваша ниша", description:"Общая картина, стратегия и направления развития канала.", overline:"ОСНОВА КАНАЛА", heading:"Анализ и стратегия", subtitle:"Опираемся на сохранённые материалы проекта."},
  analytics: {title:"Аналитика ниши", description:"Что происходит в вашей теме и какие видео привлекают внимание.", overline:"ДАННЫЕ И ВЫВОДЫ", heading:"Результаты анализа", subtitle:"Информация из сохранённых отчётов продюсера."},
  plan: {title:"Контент-план", description:"Принятые темы и план публикаций в одном пространстве.", overline:"ПЛАН НА МЕСЯЦ", heading:"План по неделям", subtitle:"Сохранённый план вашего выбранного запуска."},
  videos: {title:"Видео", description:"Брифы, сценарии и доступные данные о ваших роликах.", overline:"ВАШИ МАТЕРИАЛЫ", heading:"Работа над видео", subtitle:"Материалы, которые подготовил продюсер."},
};
const labels = {"":"На рассмотрении", "принят":"Принято", "отклонён":"Отклонено", "позже":"Позже", "черновик":"Черновик", "утверждена":"Утверждена"};
const statusClasses = {"принят":"accepted", "утверждена":"accepted", "отклонён":"rejected", "позже":"later"};
const choices = [["принят","Принять"],["отклонён","Отклонить"],["позже","Позже"]];
const $ = (selector) => document.querySelector(selector);
let savedSelection = {};
try {
  const value = JSON.parse(localStorage.getItem("producer.board.selection") || "{}");
  if (value && typeof value === "object") savedSelection = value;
} catch (_) { /* Continue without persistence when browser storage is unavailable. */ }
let state = {channel:typeof savedSelection.channel === "string" ? savedSelection.channel : "",
  run:typeof savedSelection.run === "string" ? savedSelection.run : "", section:"ideas", snapshot:null, token:"", busy:false};
let requestNumber = 0;
function rememberSelection() {
  try { localStorage.setItem("producer.board.selection", JSON.stringify({channel:state.channel, run:state.run})); }
  catch (_) { /* The current session remains usable without browser storage. */ }
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function option(value, title) { const node = element("option", "", title); node.value = value; return node; }
function statusLabel(status) { return status === null || status === undefined ? "Статус не распознан" : (labels[status] || "Статус не распознан"); }
function statusNode(status) { return element("span", "card-status " + (statusClasses[status] || ""), statusLabel(status)); }
function showAlert(message, isError = false) {
  const box = $("#alerts");
  box.replaceChildren();
  if (message) box.append(element("div", "notice" + (isError ? " error" : ""), message));
}
async function getJSON(path, options) {
  let response;
  try { response = await fetch(path, options); } catch (_) { throw new Error("Не удалось связаться с доской. Проверьте, что программа запущена, и обновите страницу."); }
  let data;
  try { data = await response.json(); } catch (_) { throw new Error("Не удалось прочитать ответ программы. Попробуйте обновить данные."); }
  if (!response.ok) throw new Error(data.error || "Не удалось выполнить действие. Попробуйте ещё раз.");
  return data;
}
function baseURL() { return "/api/channels/" + encodeURIComponent(state.channel) + "/runs/" + encodeURIComponent(state.run); }
function fillSelect(select, items, placeholder, selected) {
  select.replaceChildren(option("", placeholder));
  for (const item of items) select.append(option(item, item));
  select.value = items.includes(selected) ? selected : (items[0] || "");
  select.disabled = items.length === 0;
}
async function loadChannels() {
  const data = await getJSON("/api/channels");
  const channels = Array.isArray(data.channels) ? data.channels : [];
  fillSelect($("#channel"), channels, "Выберите канал", state.channel);
  state.channel = $("#channel").value;
  await loadRuns();
}
async function loadRuns() {
  const channel = state.channel;
  const thisRequest = ++requestNumber;
  const select = $("#run");
  if (!state.channel) {
    fillSelect(select, [], "Нет доступных запусков", "");
    state.run = ""; state.snapshot = null; render(); return;
  }
  const data = await getJSON("/api/channels/" + encodeURIComponent(channel) + "/runs");
  if (thisRequest !== requestNumber || channel !== state.channel) return;
  const runs = Array.isArray(data.runs) ? data.runs : [];
  fillSelect(select, runs, "Выберите запуск", state.run);
  state.run = select.value;
  await loadSnapshot();
}
async function loadSnapshot() {
  const currentRequest = ++requestNumber;
  if (!state.channel || !state.run) { state.snapshot = null; render(); return false; }
  try {
    const data = await getJSON(baseURL());
    if (currentRequest !== requestNumber) return false;
    state.snapshot = data;
    rememberSelection();
    showAlert("");
    render();
    return true;
  } catch (err) {
    if (currentRequest !== requestNumber) return false;
    state.snapshot = null; render(); showAlert(err.message, true);
    return false;
  }
}
function setSection(section) {
  state.section = section;
  for (const button of document.querySelectorAll(".nav-item")) {
    const active = button.dataset.section === section;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  render();
}
function empty(title, text) {
  const panel = element("div", "empty-card");
  const icon = element("span", "empty-icon", "✳"); icon.setAttribute("aria-hidden", "true");
  const copy = element("div"); copy.append(element("h3", "", title), element("p", "", text));
  panel.append(icon, copy); return panel;
}
function createCard(title, type, number, status) {
  const card = element("article", "card");
  const header = element("div", "card-heading");
  header.append(element("span", "card-number", number), statusNode(status));
  card.append(header, element("h3", "", title || "Без названия"));
  if (type) card.append(element("p", "card-type", type));
  return card;
}
function sourceLine(card, source) { if (source) card.append(element("p", "card-source", "Источник: " + source)); }
function fullText(card, text, title = "Открыть полный текст") {
  const details = element("details", "full-text");
  details.append(element("summary", "", title), element("pre", "", text));
  card.append(details);
}
async function decide(kind, item, status, revision, trigger) {
  if (state.busy) return;
  state.busy = true;
  const oldLabel = trigger.textContent;
  trigger.textContent = "Сохраняем…";
  for (const button of document.querySelectorAll(".decision")) button.disabled = true;
  $("#channel").disabled = true; $("#run").disabled = true;
  try {
    if (!state.token) state.token = (await getJSON("/api/session")).token;
    await getJSON(baseURL() + "/decision", {method:"POST", headers:{"Content-Type":"application/json", "X-Board-Token":state.token}, body:JSON.stringify({kind,item,status,revision})});
    const reloaded = await loadSnapshot();
    if (reloaded) showAlert("Ваше решение сохранено. Скопируйте сообщение для агента ниже: в нём указан выбранный канал и запуск.");
    else showAlert("Решение сохранено, но обновить данные не удалось. Нажмите «Обновить» и попробуйте ещё раз.", true);
  } catch (err) {
    showAlert(err.message, true);
    trigger.textContent = oldLabel;
    for (const button of document.querySelectorAll(".decision")) button.disabled = false;
  } finally {
    state.busy = false;
    $("#channel").disabled = $("#channel").options.length <= 1;
    $("#run").disabled = $("#run").options.length <= 1;
  }
}
function addChoices(card, kind, id, status, revision, available = choices) {
  if (!revision || status === null || status === undefined) {
    card.append(element("p", "card-source", "Решение недоступно: статус или формат файла не распознан."));
    return;
  }
  const row = element("div", "decision-row");
  for (const [value, label] of available) {
    const button = element("button", "decision", label); button.type = "button";
    button.setAttribute("aria-pressed", String(status === value));
    button.addEventListener("click", () => decide(kind, id, value, revision, button));
    row.append(button);
  }
  card.append(row);
}
function documentCard(title, documentData, description) {
  const card = element("article", "card document-card");
  card.append(element("h3", "", title));
  if (description) card.append(element("p", "", description));
  const lines = (documentData.content || "").split("\n").filter((line) => line.trim()).slice(1, 6);
  if (lines.length) {
    const preview = element("div", "document-preview");
    for (const line of lines) {
      const trimmed = line.trim();
      preview.append(element(trimmed.startsWith("#") ? "h4" : "p", "", trimmed.replace(/^#{1,6}\s*/, "").replace(/^[-*]\s*/, "• ")));
    }
    card.append(preview);
  }
  fullText(card, documentData.content || "", "Открыть полный документ");
  sourceLine(card, documentData.source);
  return card;
}
function renderIdeas(content, snapshot) {
  const ideas = Array.isArray(snapshot.ideas) ? snapshot.ideas : [];
  if (!ideas.length) { content.append(empty("Идей пока нет", "Продолжите работу с агентом: он подготовит предложения, которые появятся здесь.")); return; }
  ideas.forEach((idea, index) => {
    const card = createCard(idea.title, "ИДЕЯ ДЛЯ ВИДЕО", String(index + 1).padStart(2, "0"), idea.status);
    if (idea.description) card.append(element("p", "", idea.description));
    sourceLine(card, idea.source || "ideas.json");
    addChoices(card, "idea", idea.id, idea.status, snapshot.ideas_revision);
    content.append(card);
  });
}
function renderDocuments(content, docs, keys, missingTitle, missingText) {
  let found = 0;
  for (const [key, title, description] of keys) {
    if (!docs[key]) continue;
    content.append(documentCard(title, docs[key], description)); found++;
  }
  if (!found) content.append(empty(missingTitle, missingText));
}
function renderPlan(content, docs) {
  if (!docs.plan) {
    content.append(empty("План пока не составлен", "Примите идеи и продолжите работу с агентом, чтобы подготовить план.")); return;
  }
  const text = docs.plan.content || "";
  const parts = text.split(/(?=^## Неделя\s+[^\n]+)/m).filter((part) => /^## Неделя\s+/m.test(part));
  for (const [index, part] of parts.entries()) {
    const lines = part.trim().split("\n");
    const name = lines.shift().replace(/^##\s*/, "");
    const card = element("article", "card");
    const header = element("div", "card-heading"); header.append(element("span", "card-number", String(index + 1).padStart(2, "0")));
    card.append(header, element("h3", "", name));
    const details = lines.join("\n").trim();
    if (details) card.append(element("p", "week-text", details));
    sourceLine(card, docs.plan.source);
    content.append(card);
  }
  content.append(documentCard("Полный план", docs.plan, "Все детали сохранённого плана."));
}
function renderNiche(content, docs) {
  renderDocuments(content, docs, [["niche","Анализ ниши","Сохранённые выводы о вашей теме."],["strategy","Стратегия канала","Утвердить стратегию можете только вы."]], "Ниша пока не изучена", "Продолжите работу с агентом, чтобы получить анализ ниши и стратегию.");
  if (docs.strategy) {
    const card = Array.from(content.querySelectorAll(".document-card")).find((node) => node.querySelector("h3").textContent === "Стратегия канала");
    if (card) {
      card.append(statusNode(docs.strategy.status));
      addChoices(card, "strategy", "strategy", docs.strategy.status, docs.strategy.revision, [["утверждена","Утвердить"],["черновик","Вернуть в черновик"]]);
    }
  }
}
function videoRecords(data) {
  const result = [];
  function visit(value, label, depth) {
    if (depth > 3 || !value) return;
    if (Array.isArray(value)) { value.forEach((entry) => visit(entry, label, depth + 1)); return; }
    if (typeof value !== "object") return;
    if (typeof value.title === "string") { result.push({title:value.title, views:value.views, source:label, url:value.url}); return; }
    for (const [key, item] of Object.entries(value)) {
      if (Array.isArray(item) || (item && typeof item === "object")) visit(item, label + " · " + key, depth + 1);
    }
  }
  for (const [key, value] of Object.entries(data || {})) visit(value, key + ".json", 0);
  return result;
}
function renderVideos(content, snapshot) {
  const briefs = Array.isArray(snapshot.briefs) ? snapshot.briefs : [];
  const videos = videoRecords(snapshot.video_data);
  if (!briefs.length && !videos.length) { content.append(empty("Видео пока нет", "Здесь появятся брифы и доступные сведения о роликах после работы продюсера.")); return; }
  briefs.forEach((brief, index) => {
    const card = createCard(brief.title, "БРИФ ДЛЯ ВИДЕО", String(index + 1).padStart(2, "0"), brief.status);
    fullText(card, brief.content || "", "Открыть бриф и сценарий");
    sourceLine(card, brief.source);
    addChoices(card, "brief", brief.id, brief.status, brief.revision);
    content.append(card);
  });
  videos.forEach((video, index) => {
    const card = createCard(video.title, "ДАННЫЕ О ВИДЕО", String(index + 1).padStart(2,"0"), "");
    if (typeof video.views === "number") card.append(element("p", "", "Просмотры: " + new Intl.NumberFormat("ru-RU").format(video.views)));
    sourceLine(card, video.source); content.append(card);
  });
}
function render() {
  const info = sections[state.section];
  const title = $("#page-title"); title.replaceChildren(document.createTextNode(info.title), element("span", "title-dot", "."));
  $("#page-description").textContent = info.description;
  $("#breadcrumb").textContent = info.heading.toUpperCase();
  $("#section-overline").textContent = info.overline;
  $("#section-title").textContent = info.heading;
  $("#section-subtitle").textContent = info.subtitle;
  const content = $("#content"); content.replaceChildren();
  const snapshot = state.snapshot;
  $("#agent-prompt-area").hidden = !snapshot;
  $("#agent-no-selection").hidden = Boolean(snapshot);
  $("#copy-status").textContent = "";
  $("#agent-prompt").textContent = snapshot
    ? "Продолжи месяц с доской.\nКанал: " + JSON.stringify(state.channel)
      + "\nЗапуск: " + JSON.stringify(state.run)
    : "";
  $("#stage-panel").hidden = !snapshot;
  $("#idea-count").textContent = snapshot && snapshot.ideas && snapshot.ideas.length ? String(snapshot.ideas.length) : "";
  $("#section-count").textContent = "";
  if (!snapshot) {
    content.append(empty(state.channel ? "Выберите запуск" : "Начнём с канала", state.channel ? "В этом канале пока нет доступных запусков. Попросите агента начать месяц." : "Каналов пока нет. Напишите агенту: «Подготовь демонстрационный канал для доски» — или начните настройку своего канала."));
    return;
  }
  $("#stage-name").textContent = snapshot.stage || "Этап недоступен";
  const pill = $(".stage-pill");
  let stageLabel = "В РАБОТЕ";
  if (!snapshot.stage) stageLabel = "СОСТОЯНИЕ НЕ ОПРЕДЕЛЕНО";
  else if (snapshot.stage === "брифы на решение" || snapshot.stage === "стратегия ждёт утверждения") stageLabel = "ЖДЁТ ВАШЕГО РЕШЕНИЯ";
  else if (snapshot.stage === "план готов") stageLabel = "ПЛАН ГОТОВ";
  pill.replaceChildren(element("span"), document.createTextNode(" " + stageLabel));
  if (Array.isArray(snapshot.warnings) && snapshot.warnings.length) {
    const warnings = $("#alerts");
    warnings.replaceChildren(...snapshot.warnings.map((message) => element("div", "notice", message)));
  }
  const docs = snapshot.documents || {};
  switch (state.section) {
    case "ideas": renderIdeas(content, snapshot); break;
    case "competitors": renderDocuments(content, docs, [["competitors","Кандидаты в конкуренты","Список, подготовленный продюсером."]], "Конкурентов пока нет", "Когда агент подготовит список, он появится здесь."); break;
    case "niche": renderNiche(content, docs); break;
    case "analytics": renderDocuments(content, docs, [["report","Отчёт по видео","Открытые данные и результаты отбора."],["analysis","Разбор результатов","Выводы продюсера по доступным данным."],["covers","Разбор обложек","Сохранённые наблюдения по обложкам."]], "Аналитика пока не готова", "После сбора и анализа результаты появятся в этом разделе."); break;
    case "plan": renderPlan(content, docs); break;
    case "videos": renderVideos(content, snapshot); break;
  }
  if (state.section === "ideas" && Array.isArray(snapshot.ideas)) $("#section-count").textContent = "Идей: " + snapshot.ideas.length;
}
async function refresh() {
  state.token = "";
  showAlert("");
  try { await loadChannels(); } catch (err) { state.snapshot = null; render(); showAlert(err.message, true); }
}
$("#channel").addEventListener("change", async (event) => {
  state.channel = event.target.value; state.run = ""; state.snapshot = null; rememberSelection(); showAlert(""); render();
  try { await loadRuns(); } catch (err) { state.snapshot = null; render(); showAlert(err.message, true); }
});
$("#run").addEventListener("change", (event) => { state.run = event.target.value; state.snapshot = null; showAlert(""); render(); loadSnapshot(); });
$("#refresh").addEventListener("click", refresh);
$("#copy-prompt").addEventListener("click", async () => {
  try {
    if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText($("#agent-prompt").textContent);
    $("#copy-status").textContent = "Скопировано. Отправьте сообщение агенту.";
  } catch (_) {
    $("#copy-status").textContent = "Не удалось скопировать автоматически. Выделите сообщение и скопируйте его вручную.";
  }
});
for (const button of document.querySelectorAll(".nav-item")) button.addEventListener("click", () => setSection(button.dataset.section));
refresh();
