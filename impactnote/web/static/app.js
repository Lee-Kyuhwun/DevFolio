/* 성과노트(ImpactNote) SPA — 서버 API 응답만 그린다. */
(() => {
  const root = document.getElementById("app");
  const toastEl = document.getElementById("toast");

  const SCREENS = [
    { id: "dashboard", label: "대시보드", icon: "▦" },
    { id: "activities", label: "업무 기록", icon: "✎" },
    { id: "achievements", label: "성과 관리", icon: "★" },
    { id: "evidence", label: "근거 자료", icon: "🔗" },
    { id: "projects", label: "프로젝트 분석", icon: "⌕" },
    { id: "ai", label: "AI 성과 분석", icon: "✦" },
    { id: "reports", label: "성과보고서", icon: "▤" },
    { id: "submissions", label: "제출 이력", icon: "📤" },
    { id: "settings", label: "설정", icon: "⚙" },
  ];

  const state = {
    screen: "dashboard",
    meta: null,
    dashboard: null,
    activities: [],
    achievements: [],
    evidence: [],
    reports: [],
    analyses: [],
    projectAnalyses: [],
    projectAnalysis: null,
    projectBusy: false,
    editingIntelCandidate: null,
    selectedActivities: new Set(),
    editingActivity: null,
    editingAchievement: null,
    editingEvidence: null,
    analysis: null,
    reportPreview: null,
    migration: null,
    consentNotice: "",
    loading: true,
    error: "",
  };

  // ---------------------------------------------------------------------
  // 유틸
  // ---------------------------------------------------------------------
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function toast(message, tone) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.className = `toast show ${tone || ""}`;
    window.setTimeout(() => {
      toastEl.className = "toast";
    }, 3200);
  }

  async function api(path, options) {
    const opts = options || {};
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    const text = await response.text();
    let payload = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch (error) {
      payload = null;
    }
    if (!response.ok) {
      const detail = payload && payload.detail;
      const message =
        typeof detail === "string"
          ? detail
          : (detail && detail.message) || `요청 실패 (${response.status})`;
      const error = new Error(message);
      error.code = detail && detail.code;
      throw error;
    }
    return payload;
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function statusBadge(status, labels) {
    const label = (labels || {})[status] || status;
    return `<span class="badge ${esc(status)}">${esc(label)}</span>`;
  }

  function typeLabel(value) {
    const labels = (state.meta && state.meta.activity_type_labels) || {};
    return labels[value] || value;
  }

  function impactLabel(value) {
    const labels = (state.meta && state.meta.impact_labels) || {};
    return labels[value] || value;
  }

  function joinList(values, fallback) {
    const items = (values || []).filter(Boolean);
    return items.length ? items.map((item) => esc(item)).join(" · ") : fallback || "—";
  }

  function evidenceTitle(id) {
    const found = state.evidence.find((item) => item.id === id);
    return found ? found.title : id;
  }

  // ---------------------------------------------------------------------
  // 데이터
  // ---------------------------------------------------------------------
  async function refresh() {
    state.error = "";
    try {
      if (!state.meta) state.meta = await api("/api/meta");
      const [dashboard, activities, achievements, evidence, reports, projectAnalyses] = await Promise.all([
        api("/api/dashboard"),
        api("/api/activities"),
        api("/api/achievements"),
        api("/api/evidence"),
        api("/api/reports"),
        api("/api/projects/analyses"),
      ]);
      state.dashboard = dashboard;
      state.activities = activities.activities || [];
      state.achievements = achievements.achievements || [];
      state.evidence = evidence.evidence || [];
      state.reports = reports.reports || [];
      state.projectAnalyses = projectAnalyses.analyses || [];
      const alive = new Set(state.activities.map((item) => item.id));
      state.selectedActivities.forEach((id) => {
        if (!alive.has(id)) state.selectedActivities.delete(id);
      });
    } catch (error) {
      state.error = error.message || "데이터를 불러오지 못했습니다.";
    } finally {
      state.loading = false;
      render();
    }
  }

  // ---------------------------------------------------------------------
  // 화면
  // ---------------------------------------------------------------------
  function render() {
    if (state.loading) {
      root.innerHTML = `<div class="main"><p class="hint">성과노트를 불러오는 중입니다...</p></div>`;
      return;
    }
    const screen = SCREENS.find((item) => item.id === state.screen) || SCREENS[0];
    root.innerHTML = `
      <div class="layout">
        <aside class="sidebar">
          <div class="brand">
            <span class="brand-mark">SN</span>
            <div><h1>성과노트</h1><small>IMPACTNOTE</small></div>
          </div>
          <p class="tagline">업무는 기록하고, 성과는 근거로 증명합니다.</p>
          <nav class="nav" aria-label="주요 메뉴">
            ${SCREENS.map(
              (item) => `<button type="button" data-screen="${item.id}" class="${item.id === state.screen ? "active" : ""}" aria-current="${item.id === state.screen ? "page" : "false"}"><span class="icon" aria-hidden="true">${item.icon}</span>${item.label}</button>`
            ).join("")}
          </nav>
        </aside>
        <main class="main">
          <div class="page-head">
            <h2>${screen.label}</h2>
            <p>${esc(screenHint(screen.id))}</p>
          </div>
          ${state.error ? `<div class="notice error" role="alert">${esc(state.error)} <button class="btn btn-sm" data-action="refresh" type="button">다시 시도</button></div>` : ""}
          ${SCREEN_RENDERERS[screen.id]()}
        </main>
      </div>`;
  }

  function screenHint(id) {
    return (
      {
        dashboard: "이번 주·월·분기의 기록과 성과 상태를 한눈에 봅니다.",
        activities: "한 일을 먼저 남기세요. 제목과 한 줄 설명만으로 충분합니다.",
        achievements: "업무 기록을 골라 성과로 묶고, 근거와 기여도를 연결합니다.",
        evidence: "커밋·티켓·테스트 결과·문서 등 제출에 필요한 근거를 모읍니다.",
        projects: "프로젝트 경로만 등록하면 문서·코드·Git 변경 전후를 연결해 성과 후보를 발굴합니다.",
        ai: "기록을 바탕으로 성과 구조를 제안합니다. 근거 없는 수치는 자동으로 걸러집니다.",
        reports: "기간과 제출 목적을 고르면 기록된 내용만으로 보고서를 만듭니다.",
        submissions: "생성한 보고서의 버전과 제출 상태를 관리합니다.",
        settings: "작성자 정보, 외부 AI 전송 동의, DevFolio 데이터 이전을 설정합니다.",
      }[id] || ""
    );
  }

  function dashboardScreen() {
    const data = state.dashboard || {};
    const counts = data.counts || {};
    const month = data.month || {};
    return `
      <div class="grid cols-3">
        <div class="card">
          <h3>이번 주 기록</h3>
          <div class="value">${(data.week && data.week.activity_count) || 0}<span style="font-size:13px;color:var(--muted)"> 건</span></div>
          <div class="hint">${esc((data.week && data.week.start) || "")} ~ ${esc((data.week && data.week.end) || "")}</div>
        </div>
        <div class="card">
          <h3>이번 달 성과</h3>
          <div class="value">${month.achievement_count || 0}</div>
          <div class="hint">확인됨 ${month.verified_count || 0}건 · 확인 필요 ${month.needs_review_count || 0}건</div>
        </div>
        <div class="card">
          <h3>이번 분기</h3>
          <div class="value">${(data.quarter && data.quarter.achievement_count) || 0}</div>
          <div class="hint">업무 기록 ${(data.quarter && data.quarter.activity_count) || 0}건</div>
        </div>
      </div>
      <div class="grid cols-2" style="margin-top:14px">
        <div class="card">
          <h3>성과 상태</h3>
          <div class="stat-row">
            <div class="stat"><b>${counts.verified || 0}</b><span>근거 확인됨</span></div>
            <div class="stat"><b>${counts.partially_verified || 0}</b><span>일부 확인</span></div>
            <div class="stat"><b>${counts.needs_review || 0}</b><span>확인 필요</span></div>
          </div>
          <p class="hint" style="margin-top:10px">근거 없는 수치는 보고서 본문에 쓰이지 않습니다.</p>
        </div>
        <div class="card">
          <h3>최근 보고서</h3>
          ${
            (data.recent_reports || []).length
              ? `<ul style="margin:0;padding-left:18px">${data.recent_reports
                  .map((item) => `<li>${esc(item.title)} <span class="hint">v${item.version} · ${esc(item.created_at.slice(0, 10))}</span></li>`)
                  .join("")}</ul>`
              : `<p class="hint">아직 생성한 보고서가 없습니다.</p>`
          }
        </div>
      </div>
      <div class="card" style="margin-top:14px">
        <h3>진행 중인 업무</h3>
        ${
          (data.in_progress || []).length
            ? `<div class="list">${data.in_progress
                .map(
                  (item) => `<div class="item"><div class="item-head"><strong>${esc(item.title)}</strong><span class="hint">${esc(item.date)}</span></div></div>`
                )
                .join("")}</div>`
            : `<p class="hint">진행 중으로 기록된 업무가 없습니다.</p>`
        }
      </div>
      ${
        data.has_data
          ? ""
          : `<div class="notice" style="margin-top:14px">첫 기록을 남겨보세요. <button class="btn btn-primary btn-sm" data-screen="activities" type="button">업무 기록 추가</button></div>`
      }`;
  }

  function activitiesScreen() {
    const editing = state.editingActivity;
    return `
      <details class="panel" ${editing ? "open" : ""}>
        <summary>${editing ? "업무 기록 수정" : "빠른 기록 (제목 + 한 줄 설명)"}</summary>
        <form data-form="activity-save" class="form-grid" style="margin-top:12px">
          <input type="hidden" name="id" value="${esc(editing ? editing.id : "")}" />
          <label class="field span-2">업무 제목
            <input name="title" required maxlength="200" value="${esc(editing ? editing.title : "")}" placeholder="예: 배포 자동화 스크립트 수정" />
          </label>
          <label class="field span-2">수행 내용
            <textarea name="description" placeholder="무엇을 했는지 한두 문장으로">${esc(editing ? editing.description : "")}</textarea>
          </label>
          <label class="field">수행일
            <input type="date" name="date" value="${esc(editing ? editing.date : today())}" />
          </label>
          <label class="field">종료일(기간 업무)
            <input type="date" name="period_end" value="${esc((editing && editing.period_end) || "")}" />
          </label>
          <label class="field">프로젝트 / 업무 영역
            <input name="project" maxlength="120" value="${esc(editing ? editing.project : "")}" placeholder="예: 결제 시스템" />
          </label>
          <label class="field">업무 유형
            <select name="activity_type">
              ${(state.meta.activity_types || [])
                .map((type) => `<option value="${type}" ${editing && editing.activity_type === type ? "selected" : ""}>${esc(typeLabel(type))}</option>`)
                .join("")}
            </select>
          </label>
          <label class="field">문제 / 요구사항
            <textarea name="problem">${esc(editing ? editing.problem : "")}</textarea>
          </label>
          <label class="field">본인이 한 행동
            <textarea name="action">${esc(editing ? editing.action : "")}</textarea>
          </label>
          <label class="field">정량·정성 결과 (기록에 있을 때만)
            <textarea name="result" placeholder="예: 배포 실패 시 자동 복구 절차 추가 (수치는 근거가 있을 때만)">${esc(editing ? editing.result : "")}</textarea>
          </label>
          <label class="field">상태
            <select name="status">
              <option value="done" ${!editing || editing.status === "done" ? "selected" : ""}>완료</option>
              <option value="in_progress" ${editing && editing.status === "in_progress" ? "selected" : ""}>진행 중</option>
              <option value="planned" ${editing && editing.status === "planned" ? "selected" : ""}>계획</option>
            </select>
          </label>
          <label class="field">중요도 (1~5)
            <input type="number" name="importance" min="1" max="5" value="${editing ? editing.importance : 3}" />
          </label>
          <label class="field">태그 (쉼표)
            <input name="tags" value="${esc(editing ? (editing.tags || []).join(", ") : "")}" placeholder="자동화, 운영" />
          </label>
          <label class="field">협업 대상 (쉼표)
            <input name="collaborators" value="${esc(editing ? (editing.collaborators || []).join(", ") : "")}" />
          </label>
          <div class="form-actions span-2">
            <button class="btn btn-primary" type="submit">${editing ? "수정 저장" : "기록 추가"}</button>
            ${editing ? '<button class="btn btn-ghost" type="button" data-action="cancel-activity-edit">취소</button>' : ""}
          </div>
        </form>
      </details>
      ${
        state.activities.length
          ? `<div class="list">${state.activities.map(activityItem).join("")}</div>`
          : `<div class="empty">아직 기록이 없습니다. 위에서 첫 업무를 남겨보세요.</div>`
      }`;
  }

  function activityItem(item) {
    const checked = state.selectedActivities.has(item.id);
    return `<article class="item">
        <div class="item-head">
          <label class="checkline"><input type="checkbox" data-select-activity="${esc(item.id)}" ${checked ? "checked" : ""} /> 선택</label>
          <strong>${esc(item.title)}</strong>
          <span class="badge ${item.status === "done" ? "verified" : "warn"}">${item.status === "done" ? "완료" : item.status === "in_progress" ? "진행 중" : "계획"}</span>
        </div>
        <div class="item-meta">
          <span>${esc(item.date)}${item.period_end ? ` ~ ${esc(item.period_end)}` : ""}</span>
          <span>${esc(typeLabel(item.activity_type))}</span>
          <span>${esc(item.project || "프로젝트 미지정")}</span>
          <span>중요도 ${item.importance}</span>
          ${item.source !== "manual" ? `<span>${esc(item.source === "git" ? "Git 자동 수집" : item.source === "migration" ? "DevFolio 이전" : "AI")}</span>` : ""}
        </div>
        ${item.description ? `<p>${esc(item.description)}</p>` : ""}
        ${item.problem ? `<p class="hint">문제: ${esc(item.problem)}</p>` : ""}
        ${item.result ? `<p class="hint">결과: ${esc(item.result)}</p>` : ""}
        <div class="item-actions">
          <button class="btn btn-sm" data-action="edit-activity" data-id="${esc(item.id)}" type="button">수정</button>
          <button class="btn btn-sm btn-danger" data-action="delete-activity" data-id="${esc(item.id)}" type="button">삭제</button>
          <button class="btn btn-sm" data-action="analyze-activity" data-id="${esc(item.id)}" type="button">AI 분석</button>
        </div>
      </article>`;
  }

  function achievementsScreen() {
    const editing = state.editingAchievement;
    const selectedCount = state.selectedActivities.size;
    return `
      <div class="toolbar">
        <button class="btn btn-primary" data-action="create-achievement" type="button" ${selectedCount ? "" : "disabled"}>
          선택한 업무 ${selectedCount}건으로 성과 만들기
        </button>
        <span class="hint">업무 기록 화면에서 체크한 뒤 돌아오세요.</span>
      </div>
      ${
        editing ? achievementForm(editing) : ""
      }
      ${
        state.achievements.length
          ? `<div class="list">${state.achievements.map(achievementItem).join("")}</div>`
          : `<div class="empty">성과가 없습니다. 업무 기록을 골라 성과로 묶어보세요.</div>`
      }`;
  }

  function achievementForm(item) {
    const categories = state.meta.impact_categories || [];
    return `<details class="panel" open>
        <summary>성과 수정 · 근거/기여도 연결</summary>
        <form data-form="achievement-save" class="form-grid" style="margin-top:12px">
          <input type="hidden" name="id" value="${esc(item.id)}" />
          <label class="field span-2">성과 제목
            <input name="title" required value="${esc(item.title)}" />
          </label>
          <label class="field span-2">문제 / 요구사항
            <textarea name="problem">${esc(item.problem)}</textarea>
          </label>
          <label class="field span-2">수행 내용
            <textarea name="action">${esc(item.action)}</textarea>
          </label>
          <label class="field span-2">결과 (근거 있는 내용만)
            <textarea name="result">${esc(item.result)}</textarea>
          </label>
          <fieldset class="span-2">
            <legend>성과 분류</legend>
            <div class="chips">
              ${categories
                .map(
                  (cat) => `<label class="checkline"><input type="checkbox" name="impact" value="${cat}" ${item.impact_categories.includes(cat) ? "checked" : ""} /> ${esc(impactLabel(cat))}</label>`
                )
                .join("")}
            </div>
          </fieldset>
          <label class="field">본인 역할
            <input name="role" value="${esc(item.contribution.role)}" placeholder="예: 백엔드 담당" />
          </label>
          <label class="field">조직/타 팀 역할
            <input name="org_role" value="${esc(item.contribution.organization_role)}" placeholder="예: QA팀이 시나리오 검증" />
          </label>
          <label class="field">직접 수행 (쉼표)
            <input name="solo" value="${esc((item.contribution.solo || []).join(", "))}" />
          </label>
          <label class="field">공동 수행 (쉼표)
            <input name="shared" value="${esc((item.contribution.shared || []).join(", "))}" />
          </label>
          <label class="field">의사결정 기여 (쉼표)
            <input name="decisions" value="${esc((item.contribution.decisions || []).join(", "))}" />
          </label>
          <label class="field">기간 시작
            <input type="date" name="period_start" value="${esc(item.period_start || "")}" />
          </label>
          <label class="field">기간 종료
            <input type="date" name="period_end" value="${esc(item.period_end || "")}" />
          </label>
          ${
            item.source === "ai" || item.source === "git"
              ? `<label class="checkline span-2"><input type="checkbox" name="confirmed" value="1" ${item.confirmed ? "checked" : ""} /> 자동 수집·AI 제안 내용을 확인했습니다 (체크해야 근거 확인됨으로 올라갑니다)</label>`
              : ""
          }
          <label class="field span-2">근거 자료 (Ctrl/⌘ 로 여러 개)
            <select name="evidence_ids" multiple size="5">
              ${state.evidence
                .map(
                  (ev) => `<option value="${ev.id}" ${item.evidence_ids.includes(ev.id) ? "selected" : ""}>${esc(ev.title)} ${ev.verified ? "(확인)" : "(미확인)"}</option>`
                )
                .join("")}
            </select>
          </label>
          <div class="form-actions span-2">
            <button class="btn btn-primary" type="submit">저장</button>
            <button class="btn btn-ghost" type="button" data-action="cancel-achievement-edit">닫기</button>
          </div>
        </form>
        <form data-form="metric-save" class="form-grid" style="margin-top:12px;border-top:1px dashed var(--border);padding-top:12px">
          <input type="hidden" name="achievement_id" value="${esc(item.id)}" />
          <label class="field">지표 이름 <input name="name" required placeholder="예: 배포 소요 시간" /></label>
          <label class="field">값 <input name="value" placeholder="예: 12" /></label>
          <label class="field">단위 <input name="unit" placeholder="분, %, 건" /></label>
          <label class="field">기간 <input name="period" placeholder="2026-10 ~ 2026-11" /></label>
          <label class="field span-2">측정 기준/산출 방식 <input name="basis" placeholder="예: CI 로그 20회 평균" /></label>
          <label class="field">근거 <select name="evidence_id"><option value="">(선택)</option>${state.evidence.map((ev) => `<option value="${ev.id}">${esc(ev.title)}</option>`).join("")}</select></label>
          <label class="checkline"><input type="checkbox" name="verified" value="1" /> 근거 확인됨</label>
          <p class="hint span-2">값이 기록·근거 텍스트에 그대로 있어야 "근거 확인됨"으로 인정됩니다.</p>
          <div class="form-actions span-2"><button class="btn" type="submit">지표 추가</button></div>
        </form>
      </details>`;
  }

  function achievementItem(item) {
    return `<article class="item">
        <div class="item-head">
          <strong>${esc(item.title)}</strong>
          ${statusBadge(item.status, state.meta.status_labels)}
          ${item.needs_review ? '<span class="badge warn">검토 필요</span>' : ""}
        </div>
        <div class="item-meta">
          <span>${esc(item.period_start || "")}${item.period_end ? ` ~ ${esc(item.period_end)}` : ""}</span>
          <span>업무 ${item.activity_ids.length}건 연결</span>
          <span>근거 ${item.evidence_ids.length}건</span>
          ${item.contribution.role ? `<span>역할: ${esc(item.contribution.role)}</span>` : ""}
        </div>
        ${item.problem ? `<p>문제: ${esc(item.problem)}</p>` : ""}
        ${item.action ? `<p>수행: ${esc(item.action)}</p>` : ""}
        ${item.result ? `<p>결과: ${esc(item.result)}</p>` : ""}
        ${item.evidence_ids.length ? `<p class="hint">근거: ${item.evidence_ids.map((id) => esc(evidenceTitle(id))).join(", ")}</p>` : '<p class="hint">연결된 근거가 없습니다.</p>'}
        <div class="item-actions">
          <button class="btn btn-sm" data-action="edit-achievement" data-id="${esc(item.id)}" type="button">수정·근거 연결</button>
          <button class="btn btn-sm btn-danger" data-action="delete-achievement" data-id="${esc(item.id)}" type="button">삭제</button>
        </div>
      </article>`;
  }

  function evidenceScreen() {
    const editing = state.editingEvidence;
    return `
      <details class="panel" ${editing ? "open" : ""}>
        <summary>${editing ? "근거 수정" : "근거 추가"}</summary>
        <form data-form="evidence-save" class="form-grid" style="margin-top:12px">
          <input type="hidden" name="id" value="${esc(editing ? editing.id : "")}" />
          <label class="field">유형
            <select name="type">${(state.meta.evidence_types || [])
              .map((type) => `<option value="${type}" ${editing && editing.type === type ? "selected" : ""}>${esc(type)}</option>`)
              .join("")}</select>
          </label>
          <label class="field">제목 <input name="title" required value="${esc(editing ? editing.title : "")}" placeholder="예: 결제 API 장애 대응 PR" /></label>
          <label class="field span-2">참조(URL/커밋 SHA/티켓 번호) <input name="reference" value="${esc(editing ? editing.reference : "")}" /></label>
          <label class="field span-2">설명 <textarea name="description">${esc(editing ? editing.description : "")}</textarea></label>
          <label class="checkline"><input type="checkbox" name="verified" value="1" ${editing && editing.verified ? "checked" : ""} /> 직접 확인한 근거</label>
          <div class="form-actions span-2">
            <button class="btn btn-primary" type="submit">${editing ? "수정 저장" : "추가"}</button>
            ${editing ? '<button class="btn btn-ghost" type="button" data-action="cancel-evidence-edit">취소</button>' : ""}
          </div>
        </form>
      </details>
      ${
        state.evidence.length
          ? `<div class="list">${state.evidence
              .map(
                (item) => `<article class="item">
                  <div class="item-head"><strong>${esc(item.title)}</strong><span class="badge ${item.verified ? "verified" : "needs_review"}">${item.verified ? "확인됨" : "미확인"}</span><span class="hint">${esc(item.type)}</span></div>
                  ${item.reference ? `<p class="hint">${esc(item.reference)}</p>` : ""}
                  ${item.description ? `<p>${esc(item.description)}</p>` : ""}
                  <div class="item-actions">
                    <button class="btn btn-sm" data-action="edit-evidence" data-id="${esc(item.id)}" type="button">수정</button>
                    <button class="btn btn-sm btn-danger" data-action="delete-evidence" data-id="${esc(item.id)}" type="button">삭제</button>
                  </div>
                </article>`
              )
              .join("")}</div>`
          : `<div class="empty">근거가 없습니다. 커밋·티켓·테스트 결과를 추가해 성과와 연결하세요.</div>`
      }`;
  }

  function qualityBadge(quality) {
    const labels = (state.meta && state.meta.intel_quality_labels) || {};
    return `<span class="badge ${esc(quality)}">${esc(labels[quality] || quality)}</span>`;
  }

  function intelDocKind(kind) {
    const labels = (state.meta && state.meta.intel_doc_kinds) || {};
    return labels[kind] || kind;
  }

  function projectsScreen() {
    const analysis = state.projectAnalysis;
    return `
      <div class="card">
        <h3>프로젝트 경로로 심층 분석</h3>
        <form data-form="intel-analyze" class="form-grid">
          <label class="field span-2">프로젝트 디렉터리
            <input name="project_path" required placeholder="/Users/you/company-project" />
          </label>
          <label class="field">내 커밋 이메일 (선택)
            <input name="author_email" type="email" placeholder="me@company.com" />
          </label>
          <label class="field">AI Provider (선택)
            <input name="provider" placeholder="예: groq, ollama" />
          </label>
          <label class="checkline"><input type="checkbox" name="use_ai" value="1" checked /> 외부 AI 보강 사용 (설정에서 동의한 경우만 전송)</label>
          <label class="checkline"><input type="checkbox" name="force" value="1" /> 캐시 무시하고 다시 분석</label>
          <div class="form-actions span-2">
            <button class="btn btn-primary" type="submit" ${state.projectBusy ? "disabled" : ""}>${state.projectBusy ? "분석 중..." : "프로젝트 분석"}</button>
            <span class="hint">문서·코드·Git 이력을 읽기 전용으로 조사합니다. 원본 파일과 브랜치는 변경하지 않습니다.</span>
          </div>
        </form>
        ${state.projectBusy ? '<div class="notice" style="margin-top:12px">문서 탐색 → 코드 인벤토리 → Git 변경 전후 비교 → 후보 생성을 진행 중입니다. 큰 저장소는 시간이 걸릴 수 있습니다.</div>' : ""}
      </div>
      ${analysis ? intelDetail(analysis) : `<div class="empty" style="margin-top:14px">분석 결과를 선택하거나 새 프로젝트를 분석하세요.</div>`}
      <div class="card" style="margin-top:14px">
        <h3>분석 이력</h3>
        ${
          state.projectAnalyses.length
            ? `<div class="list">${state.projectAnalyses
                .map(
                  (item) => `<div class="item">
                    <div class="item-head"><strong>${esc(item.project_name)}</strong>${statusBadge(item.status, { completed: "완료", partial: "부분 완료", failed: "실패" })}${item.incremental ? '<span class="badge">캐시 재사용</span>' : ""}</div>
                    <div class="item-meta"><span>${esc(item.created_at.slice(0, 16).replace("T", " "))}</span><span>문서 ${(item.stats || {}).documents || 0}</span><span>코드 ${(item.stats || {}).code_files || 0}</span><span>커밋 ${(item.stats || {}).commits_scanned || 0}</span><span>후보 ${item.candidate_count || 0}</span><span>AI ${esc(item.ai_status || "-")}</span></div>
                    <div class="item-actions"><button class="btn btn-sm" data-action="open-intel" data-id="${esc(item.id)}" type="button">근거 보기</button></div>
                  </div>`
                )
                .join("")}</div>`
            : '<p class="hint">아직 프로젝트 분석 이력이 없습니다.</p>'
        }
      </div>`;
  }

  function intelDetail(analysis) {
    const stats = analysis.stats || {};
    const quality = analysis.quality_summary || {};
    const refs = analysis.evidence || [];
    const refMap = Object.fromEntries(refs.map((item) => [item.id, item]));
    const findings = analysis.findings || [];
    const warnings = analysis.warnings || [];
    const ai = analysis.ai || {};
    return `
      <div class="card" style="margin-top:14px">
        <div class="item-head">
          <h3 style="margin:0">${esc(analysis.project_name)}</h3>
          ${statusBadge(analysis.status, { completed: "완료", partial: "부분 완료", failed: "실패" })}
          ${analysis.incremental ? '<span class="badge">캐시 재사용</span>' : ""}
          <span class="hint">${esc(analysis.project_path)}</span>
        </div>
        <div class="intel-stats">
          <div><b>${stats.documents || 0}</b><span>문서</span></div>
          <div><b>${stats.code_files || 0}</b><span>코드 파일</span></div>
          <div><b>${stats.commits_scanned || 0}</b><span>커밋</span></div>
          <div><b>${stats.candidates || 0}</b><span>성과 후보</span></div>
          <div><b>${stats.measurements || 0}</b><span>측정 자료</span></div>
          <div><b>${analysis.head_sha ? analysis.head_sha.slice(0, 8) : "-"}</b><span>HEAD</span></div>
        </div>
        <p class="hint">분석 범위: ${esc(stats.commit_range || "-")} · 기여자 ${stats.contributors || 0}명 · 코드 ${stats.code_lines || 0}줄</p>
        <div class="chips" style="margin-top:8px">
          ${qualityBadge("VERIFIED")} ${quality.VERIFIED || 0}
          ${qualityBadge("SUPPORTED_INFERENCE")} ${quality.SUPPORTED_INFERENCE || 0}
          ${qualityBadge("HYPOTHESIS")} ${quality.HYPOTHESIS || 0}
          ${qualityBadge("INSUFFICIENT_EVIDENCE")} ${quality.INSUFFICIENT_EVIDENCE || 0}
        </div>
        <p class="hint" style="margin-top:8px">AI 보강: ${esc(ai.status || "skipped")} ${ai.used ? `· ${esc(ai.provider || "")} ${esc(ai.model || "")}` : "· 결정론적 분석만 사용"}${ai.prompt_chars ? ` · prompt ${ai.prompt_chars}자` : ""}</p>
        ${ai.error ? `<div class="notice error" style="margin-top:8px">AI 보강 실패(부분 결과 보존): ${esc(ai.error)}</div>` : ""}
        ${warnings.length ? `<details style="margin-top:10px"><summary class="hint">분석 경고·누락 가능성 ${warnings.length}건</summary><ul class="hint">${warnings.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></details>` : ""}
      </div>

      <div class="card" style="margin-top:14px">
        <h3>발견한 문서 (${(analysis.documents || []).length})</h3>
        ${(analysis.documents || []).length
          ? `<div class="chips" style="margin-bottom:8px">${Array.from(new Set((analysis.documents || []).map((item) => item.kind))).map((kind) => `<span class="badge">${esc(intelDocKind(kind))}</span>`).join(" ")}</div>
            <table><thead><tr><th>문서</th><th>역할</th><th>크기</th><th>상태</th></tr></thead><tbody>
            ${(analysis.documents || []).slice(0, 20).map((item) => `<tr><td>${esc(item.path)}<br /><span class="hint">${esc(item.summary || "")}</span></td><td>${esc(intelDocKind(item.kind))}</td><td>${item.chars}자</td><td>${item.deleted ? "Git 이력" : item.git_tracked ? "Git 추적" : "로컬"}</td></tr>`).join("")}
            </tbody></table>`
          : '<p class="hint">문서를 찾지 못했습니다. 코드와 Git 이력만으로 분석했습니다.</p>'}
      </div>

      <div class="card" style="margin-top:14px">
        <h3>문서 ↔ 코드 교차 분석</h3>
        ${findings.length
          ? `<div class="list">${findings.slice(0, 24).map((item) => `<div class="item">
              <div class="item-head"><strong>${esc(item.title)}</strong>${qualityBadge(item.quality)}</div>
              <p>${esc(item.detail)}</p>
              <div class="item-meta">${(item.paths || []).map((path) => `<code>${esc(path)}</code>`).join(" ")}</div>
            </div>`).join("")}</div>`
          : '<p class="hint">문서 주장과 코드를 연결하지 못했습니다.</p>'}
      </div>

      <div class="card" style="margin-top:14px">
        <h3>기술 진화 타임라인</h3>
        ${(analysis.timeline || []).length
          ? `<div class="list">${(analysis.timeline || []).map((step) => `<div class="item">
              <div class="item-head"><strong>${esc(step.label)}</strong><span class="hint">${esc(step.date || "")}</span>${step.change_kind ? `<span class="badge">${esc(step.change_kind)}</span>` : ""}</div>
              <div class="item-meta">${esc(step.summary || "")}${step.sha ? ` · ${esc(step.sha.slice(0, 8))}` : ""}</div>
              ${step.before || step.after ? `<div class="diff-grid"><div class="diff-box"><span class="hint">변경 전</span><pre class="content">${esc(step.before || "(기록 없음)")}</pre></div><div class="diff-box"><span class="hint">변경 후</span><pre class="content">${esc(step.after || "(기록 없음)")}</pre></div></div>` : ""}
            </div>`).join("")}</div>`
          : '<p class="hint">재구성할 만한 커밋 변경이 없습니다.</p>'}
      </div>

      <div class="card" style="margin-top:14px">
        <h3>측정된 개선 (${(analysis.measurements || []).length})</h3>
        ${(analysis.measurements || []).length
          ? `<table><thead><tr><th>이전</th><th>이후</th><th>변화율</th><th>측정 조건</th><th>검증</th><th>출처</th></tr></thead><tbody>
            ${(analysis.measurements || []).map((item) => `<tr><td>${esc(item.before)}</td><td>${esc(item.after)}</td><td>${item.change_percent == null ? "미측정" : `${item.change_percent}%`}</td><td>${esc(item.conditions)}</td><td>${item.verified ? "측정 문서" : "참고용"}</td><td>${esc(item.source_path)}</td></tr>`).join("")}
            </tbody></table>`
          : '<p class="hint">전후 수치가 기록된 측정 자료가 없습니다. 개선 효과는 정성적으로만 표시됩니다.</p>'}
      </div>

      <div class="card" style="margin-top:14px">
        <h3>성과 후보 (${(analysis.candidates || []).length})</h3>
        ${(analysis.candidates || []).length
          ? `<div class="list">${(analysis.candidates || []).map((item) => intelCandidate(item, refMap)).join("")}</div>`
          : '<p class="hint">근거가 연결된 후보를 만들지 못했습니다. 커밋·코드 변경이 더 필요할 수 있습니다.</p>'}
      </div>
      ${(ai.notes || []).length ? `<div class="notice" style="margin-top:14px">AI 메모: ${(ai.notes || []).map((note) => esc(note)).join(" · ")}</div>` : ""}`;
  }

  function intelCandidate(candidate, refMap) {
    const refs = (candidate.evidence_ids || []).map((id) => refMap[id]).filter(Boolean);
    const contribution = candidate.contribution || {};
    const dismissed = candidate.status === "dismissed";
    const applied = candidate.status === "applied";
    const needsValidation = candidate.status === "needs_validation";
    const editing = state.editingIntelCandidate === candidate.id;
    return `<article class="item" ${dismissed ? 'style="opacity:.55"' : ""}>
        <div class="item-head">
          <strong>${esc(candidate.title)}</strong>
          ${qualityBadge(candidate.quality)}
          <span class="badge">신뢰도 ${candidate.confidence}</span>
          ${needsValidation ? '<span class="badge warn">추가 검증 필요</span>' : ""}
          ${applied ? '<span class="badge verified">성과로 저장됨</span>' : dismissed ? '<span class="badge">제외됨</span>' : ""}
        </div>
        ${editing ? `<form data-form="intel-candidate-save" class="form-grid" style="margin-top:8px">
            <input type="hidden" name="analysis_id" value="${esc(state.projectAnalysis.id)}" />
            <input type="hidden" name="candidate_id" value="${esc(candidate.id)}" />
            <label class="field span-2">제목 <input name="title" required value="${esc(candidate.title)}" /></label>
            <label class="field span-2">문제 <textarea name="problem">${esc(candidate.problem)}</textarea></label>
            <label class="field span-2">수행 <textarea name="action">${esc(candidate.action)}</textarea></label>
            <label class="field span-2">결과 <textarea name="result">${esc(candidate.result)}</textarea></label>
            <div class="form-actions span-2"><button class="btn btn-primary" type="submit">수정 저장</button><button class="btn btn-ghost" type="button" data-action="cancel-intel-candidate">취소</button></div>
          </form>` : `<p><b>문제</b> ${esc(candidate.problem)}</p>
        <p><b>수행</b> ${esc(candidate.action)}</p>
        <p><b>결과</b> ${esc(candidate.result)}</p>`}
        <div class="item-meta">
          <span>기여: ${esc(contribution.role || "미확인")}</span>
          ${(candidate.impact_categories || []).map((cat) => `<span>${esc(impactLabel(cat))}</span>`).join("")}
        </div>
        ${(candidate.notes || []).length ? `<p class="hint">${(candidate.notes || []).map((note) => esc(note)).join(" · ")}</p>` : ""}
        <details>
          <summary class="hint">근거 ${refs.length}건 확인</summary>
          <div class="list" style="margin-top:8px">
            ${refs.map((ref) => `<div class="item" style="background:var(--surface-2)">
              <div class="item-head"><span class="badge">${esc(ref.kind)}</span><strong>${esc(ref.title)}</strong>${ref.verified ? '<span class="badge verified">확인됨</span>' : '<span class="badge warn">추론</span>'}</div>
              <div class="item-meta"><span>${esc(ref.path || "-")}</span><span>${esc(ref.locator || "")}</span><span>수집 ${esc((ref.collected_at || "").slice(0, 10))}</span></div>
              ${ref.excerpt ? `<p class="hint">${esc(ref.excerpt)}</p>` : ""}
            </div>`).join("")}
          </div>
        </details>
        <div class="item-actions">
          ${!applied && !dismissed ? `<select class="intel-activity-select" aria-label="기존 업무 기록에 연결"><option value="">새 업무 기록으로 저장</option>${state.activities.map((item) => `<option value="${esc(item.id)}">${esc(item.date)} · ${esc(item.title)}</option>`).join("")}</select>
          <button class="btn btn-primary btn-sm" data-action="intel-apply" data-id="${esc(candidate.id)}" data-analysis="${esc(state.projectAnalysis.id)}" type="button">성과로 저장 (검토 필요)</button>
          <button class="btn btn-sm" data-action="edit-intel-candidate" data-id="${esc(candidate.id)}" type="button">수정</button>
          <button class="btn btn-sm" data-action="toggle-intel-validation" data-id="${esc(candidate.id)}" data-analysis="${esc(state.projectAnalysis.id)}" data-status="${needsValidation ? "candidate" : "needs_validation"}" type="button">${needsValidation ? "검증 필요 해제" : "추가 검증 필요"}</button>
          <button class="btn btn-sm" data-action="merge-intel-candidate" data-id="${esc(candidate.id)}" data-analysis="${esc(state.projectAnalysis.id)}" type="button">다른 후보와 병합</button>
          <button class="btn btn-sm btn-danger" data-action="intel-dismiss" data-id="${esc(candidate.id)}" data-analysis="${esc(state.projectAnalysis.id)}" type="button">제외</button>` : ""}
          ${applied && candidate.applied_achievement_id ? `<span class="hint">성과 ID: ${esc(candidate.applied_achievement_id)} — 성과 관리에서 확인·확정하세요.</span>` : ""}
        </div>
      </article>`;
  }

  function aiScreen() {
    const consent = state.meta && state.meta.external_ai_enabled;
    const analysis = state.analysis;
    return `
      ${consent ? "" : '<div class="notice">외부 AI 전송이 꺼져 있습니다. 회사 자료 보호를 위해 기본값은 꺼짐입니다. <button class="btn btn-sm" data-screen="settings" type="button">설정으로 이동</button></div>'}
      <div class="card" style="margin-top:12px">
        <h3>업무 기록 → 성과 구조 분석</h3>
        <form data-form="ai-analyze" class="form-grid">
          <label class="field span-2">분석할 업무
            <select name="activity_id">${state.activities.map((item) => `<option value="${item.id}">${esc(item.date)} · ${esc(item.title)}</option>`).join("")}</select>
          </label>
          <label class="field">Provider (선택)
            <input name="provider" placeholder="예: groq, ollama" />
          </label>
          <div class="form-actions span-2">
            <button class="btn btn-primary" type="submit" ${state.activities.length ? "" : "disabled"}>분석 실행</button>
            <span class="hint">원본 기록은 수정되지 않습니다. 결과는 별도로 저장됩니다.</span>
          </div>
        </form>
      </div>
      <div class="card" style="margin-top:12px">
        <h3>Git에서 성과 후보 수집</h3>
        <form data-form="git-import" class="form-grid">
          <label class="field">저장소 경로 <input name="repo_path" placeholder="/Users/you/project" /></label>
          <label class="field">작성자 이메일 <input name="author_email" type="email" placeholder="me@company.com" /></label>
          <label class="field">최대 커밋 수 <input type="number" name="limit" value="20" min="1" max="100" /></label>
          <div class="form-actions span-2"><button class="btn" type="submit">커밋에서 후보 수집</button><span class="hint">AI 없이 커밋 내용만으로 후보를 만들며, 모두 '검토 필요' 상태입니다.</span></div>
        </form>
      </div>
      ${analysis ? analysisPanel(analysis) : ""}`;
  }

  function analysisPanel(analysis) {
    if (analysis.status === "failed") {
      return `<div class="notice error" style="margin-top:12px">
          AI 분석 실패 — 원본 업무 기록은 그대로 보존되었습니다.<br />
          오류 코드: <code>${esc(analysis.error_code || "UNKNOWN_ERROR")}</code> · ${esc(analysis.error_message || "")}
          ${analysis.model ? `<br />모델: ${esc(analysis.model)}` : ""}
        </div>`;
    }
    const result = analysis.result || {};
    const statements = result.statements || {};
    const removed = result.unverified_metrics || [];
    return `<div class="card" style="margin-top:12px">
        <h3>분석 결과 ${statusBadge(analysis.status === "completed" ? "verified" : "needs_review", { verified: "완료", needs_review: "확인 필요" })}</h3>
        <p class="hint">${esc(analysis.provider || "")} ${analysis.model ? `· ${esc(analysis.model)}` : ""}</p>
        <div class="list">
          <div class="item"><strong>${esc(result.title || "")}</strong>
            <p>문제: ${esc(result.problem || "—")}</p>
            <p>수행: ${esc(result.action || "—")}</p>
            <p>결과: ${esc(result.result || "기록 없음")}</p>
            ${result.organization_value ? `<p class="hint">조직 가치: ${esc(result.organization_value)}</p>` : ""}
            ${(result.impact_categories || []).length ? `<p class="hint">분류: ${result.impact_categories.map((cat) => esc(impactLabel(cat))).join(", ")}</p>` : ""}
            ${statements.weekly ? `<p class="hint">업무보고 문장: ${esc(statements.weekly)}</p>` : ""}
          </div>
        </div>
        ${
          removed.length
            ? `<div class="notice" style="margin-top:10px">근거에서 확인되지 않아 제거한 수치 ${removed.length}건: ${removed.map((item) => esc(item.raw)).join(", ")}</div>`
            : ""
        }
        <div class="form-actions" style="margin-top:10px">
          <button class="btn btn-primary" data-action="apply-analysis" data-id="${esc(analysis.id)}" type="button">성과로 저장 (검토 필요)</button>
        </div>
      </div>`;
  }

  function reportsScreen() {
    const preview = state.reportPreview;
    const meta = state.meta || {};
    return `
      <details class="panel" open>
        <summary>보고서 생성</summary>
        <form data-form="report-generate" class="form-grid" style="margin-top:12px">
          <label class="field">제출 목적
            <select name="template">${Object.entries(meta.templates || {})
              .map(([key, label]) => `<option value="${key}" ${key === "monthly" ? "selected" : ""}>${esc(label)}</option>`)
              .join("")}</select>
          </label>
          <label class="field">기간
            <select name="period_kind">
              <option value="week">주간</option>
              <option value="month" selected>월간</option>
              <option value="quarter">분기</option>
              <option value="half">반기</option>
              <option value="year">연간</option>
              <option value="custom">사용자 지정</option>
            </select>
          </label>
          <label class="field">기준일 <input type="date" name="reference" value="${today()}" /></label>
          <label class="field">사용자 지정 시작 <input type="date" name="start" /></label>
          <label class="field">사용자 지정 종료 <input type="date" name="end" /></label>
          <label class="field">제목(선택) <input name="title" placeholder="비우면 기간·목적 자동" /></label>
          <label class="field">글자 수 제한(0=없음) <input type="number" name="char_limit" min="0" value="0" /></label>
          <label class="field">파일 형식
            <select name="format"><option value="md">Markdown</option><option value="docx">DOCX</option><option value="pdf">PDF</option><option value="txt">TXT</option><option value="csv">CSV</option></select>
          </label>
          <label class="field span-2">자유 형식 항목(쉼표 또는 줄바꿈, 'custom' 선택 시)
            <textarea name="custom_sections" placeholder="성과 요약, 주요 업무, 개선 효과, 향후 계획"></textarea>
          </label>
          <div class="form-actions span-2"><button class="btn btn-primary" type="submit">보고서 생성</button><span class="hint">기록되지 않은 내용은 채우지 않습니다.</span></div>
        </form>
      </details>
      ${preview ? `<div class="card"><h3>${esc(preview.title)} (v${preview.version})</h3>
        <div class="item-actions" style="margin-bottom:8px">
          ${["md", "docx", "pdf", "txt", "csv"].map((fmt) => `<a class="btn btn-sm" href="/api/reports/${esc(preview.id)}/download?format=${fmt}">${fmt.toUpperCase()}</a>`).join("")}
        </div>
        <pre class="content">${esc(preview.content)}</pre></div>` : ""}
      <div class="card" style="margin-top:12px">
        <h3>최근 보고서</h3>
        ${
          state.reports.length
            ? `<table><thead><tr><th>제목</th><th>기간</th><th>버전</th><th>상태</th><th>파일</th></tr></thead><tbody>${state.reports
                .slice(0, 8)
                .map(
                  (item) => `<tr><td>${esc(item.title)}</td><td>${esc(item.period_start)} ~ ${esc(item.period_end)}</td><td>v${item.version}</td><td>${statusBadge(item.status, { draft: "초안", submitted: "제출" })}</td><td>${item.file_name ? esc(item.file_name) : "—"}</td></tr>`
                )
                .join("")}</tbody></table>`
            : '<p class="hint">아직 생성한 보고서가 없습니다.</p>'
        }
      </div>`;
  }

  function submissionsScreen() {
    return state.reports.length
      ? `<table><thead><tr><th>제출 목적</th><th>평가 기간</th><th>생성일</th><th>버전</th><th>포함 성과</th><th>상태</th></tr></thead><tbody>${state.reports
          .map(
            (item) => `<tr>
              <td>${esc((state.meta.templates || {})[item.template] || item.template)}</td>
              <td>${esc(item.period_start)} ~ ${esc(item.period_end)}</td>
              <td>${esc(item.created_at.slice(0, 10))}</td>
              <td>v${item.version}</td>
              <td>${item.achievement_ids.length}건</td>
              <td>
                <select data-report-status="${esc(item.id)}" style="width:auto">
                  <option value="draft" ${item.status === "draft" ? "selected" : ""}>초안</option>
                  <option value="submitted" ${item.status === "submitted" ? "selected" : ""}>제출</option>
                </select>
              </td>
            </tr>`
          )
          .join("")}</tbody></table>`
      : `<div class="empty">제출 이력이 없습니다. 보고서를 생성하면 여기에 쌓입니다.</div>`;
  }

  function settingsScreen() {
    const settings = (state.meta && state.meta.settings) || {};
    return `
      <div class="card">
        <h3>작성자·조직</h3>
        <form data-form="settings-save" class="form-grid">
          <label class="field">이름 <input name="user_name" value="${esc(settings.user_name || "")}" /></label>
          <label class="field">조직 <input name="organization" value="${esc(settings.organization || "")}" /></label>
          <fieldset class="span-2">
            <legend>외부 AI 전송</legend>
            <label class="checkline"><input type="checkbox" name="external_ai_consent" value="1" ${settings.external_ai_consent ? "checked" : ""} /> 승인한 Provider 에게만 업무 기록을 전송하는 데 동의합니다.</label>
            <p class="hint">기본값은 꺼짐입니다. 꺼져 있으면 AI 분석 요청이 거부되고 기록은 로컬에만 남습니다.</p>
          </fieldset>
          <label class="field">허용 Provider (쉼표, 비우면 기본 체인)
            <input name="allowed_providers" value="${esc((settings.allowed_providers || []).join(", "))}" placeholder="groq, ollama" />
          </label>
          <label class="field">기본 Provider <input name="default_provider" value="${esc(settings.default_provider || "")}" /></label>
          <div class="form-actions span-2"><button class="btn btn-primary" type="submit">설정 저장</button></div>
        </form>
      </div>
      <div class="card" style="margin-top:12px">
        <h3>DevFolio 데이터 이전</h3>
        <p class="hint">기존 프로젝트·작업을 업무 기록·성과로 옮깁니다. 원본은 수정하지 않고, 실행 전 ZIP 백업을 만듭니다.</p>
        <button class="btn" data-action="run-migration" type="button">데이터 이전 실행</button>
        ${state.migration ? `<div class="notice ${state.migration.status === "migrated" ? "ok" : ""}" style="margin-top:10px">
            ${esc(state.migration.message || "")}
            ${state.migration.backup ? `<br />백업: ${esc(state.migration.backup)}` : ""}
            <br />업무 ${state.migration.migrated_activities || 0}건 · 성과 ${state.migration.migrated_achievements || 0}건 · 건너뜀 ${state.migration.skipped || 0}건
          </div>` : ""}
      </div>`;
  }

  const SCREEN_RENDERERS = {
    dashboard: dashboardScreen,
    activities: activitiesScreen,
    achievements: achievementsScreen,
    evidence: evidenceScreen,
    projects: projectsScreen,
    ai: aiScreen,
    reports: reportsScreen,
    submissions: submissionsScreen,
    settings: settingsScreen,
  };

  // ---------------------------------------------------------------------
  // 폼 처리
  // ---------------------------------------------------------------------
  function listValue(data, name) {
    const raw = String(data.get(name) || "");
    return raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function handleForm(name, form) {
    const data = new FormData(form);
    const payload = Object.fromEntries(data.entries());
    delete payload.impact;
    if (name === "intel-candidate-save") {
      const analysis = (await api(`/api/projects/analyses/${payload.analysis_id}/candidates/${payload.candidate_id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: payload.title,
          problem: payload.problem,
          action: payload.action,
          result: payload.result,
        }),
      })).analysis;
      state.projectAnalysis = analysis;
      state.editingIntelCandidate = null;
      toast("후보 내용을 수정했습니다.", "ok");
      await refresh();
      return;
    }
    if (name === "intel-analyze") {
      state.projectBusy = true;
      render();
      try {
        const result = await api("/api/projects/analyze", {
          method: "POST",
          body: JSON.stringify({
            project_path: payload.project_path,
            author_email: payload.author_email || "",
            provider: payload.provider || "",
            use_ai: payload.use_ai === "1",
            force: payload.force === "1",
          }),
        });
        state.projectAnalysis = result.analysis;
        toast(
          result.analysis.incremental
            ? "변경이 없어 이전 분석을 재사용했습니다."
            : `분석 완료 — 후보 ${result.analysis.candidates.length}건, 문서 ${result.analysis.stats.documents}개`,
          "ok"
        );
      } finally {
        state.projectBusy = false;
      }
      await refresh();
      return;
    }
    if (name === "activity-save") {
      const body = {
        title: payload.title,
        description: payload.description,
        date: payload.date,
        period_end: payload.period_end || null,
        project: payload.project,
        activity_type: payload.activity_type,
        problem: payload.problem,
        action: payload.action,
        result: payload.result,
        status: payload.status,
        importance: Number(payload.importance || 3),
        tags: listValue(data, "tags"),
        collaborators: listValue(data, "collaborators"),
      };
      if (payload.id) await api(`/api/activities/${payload.id}`, { method: "PATCH", body: JSON.stringify(body) });
      else await api("/api/activities", { method: "POST", body: JSON.stringify(body) });
      state.editingActivity = null;
      toast("업무 기록을 저장했습니다.", "ok");
    } else if (name === "achievement-save") {
      const body = {
        title: payload.title,
        problem: payload.problem,
        action: payload.action,
        result: payload.result,
        impact_categories: data.getAll("impact"),
        contribution: {
          role: payload.role,
          solo: listValue(data, "solo"),
          shared: listValue(data, "shared"),
          decisions: listValue(data, "decisions"),
          organization_role: payload.org_role,
        },
        evidence_ids: data.getAll("evidence_ids"),
      };
      body.confirmed = data.get("confirmed") === "1";
      if (payload.period_start) body.period_start = payload.period_start;
      if (payload.period_end) body.period_end = payload.period_end;
      await api(`/api/achievements/${payload.id}`, { method: "PATCH", body: JSON.stringify(body) });
      state.editingAchievement = null;
      toast("성과를 저장했습니다.", "ok");
    } else if (name === "metric-save") {
      const body = {
        name: payload.name,
        value: payload.value,
        unit: payload.unit,
        period: payload.period,
        basis: payload.basis,
        evidence_id: payload.evidence_id,
        verified: payload.verified === "1",
      };
      await api(`/api/achievements/${payload.achievement_id}/metrics`, { method: "POST", body: JSON.stringify(body) });
      toast("지표를 추가했습니다. 근거가 확인되지 않으면 본문에 쓰이지 않습니다.", "ok");
    } else if (name === "evidence-save") {
      const body = {
        type: payload.type,
        title: payload.title,
        reference: payload.reference,
        description: payload.description,
        verified: payload.verified === "1",
      };
      if (payload.id) await api(`/api/evidence/${payload.id}`, { method: "PATCH", body: JSON.stringify(body) });
      else await api("/api/evidence", { method: "POST", body: JSON.stringify(body) });
      state.editingEvidence = null;
      toast("근거를 저장했습니다.", "ok");
    } else if (name === "settings-save") {
      const body = {
        user_name: payload.user_name,
        organization: payload.organization,
        external_ai_consent: payload.external_ai_consent === "1",
        allowed_providers: listValue(data, "allowed_providers"),
        default_provider: payload.default_provider,
      };
      await api("/api/settings", { method: "PUT", body: JSON.stringify(body) });
      state.meta = null;
      toast("설정을 저장했습니다.", "ok");
    } else if (name === "ai-analyze") {
      state.analysis = await api("/api/ai/analyze", {
        method: "POST",
        body: JSON.stringify({ activity_id: payload.activity_id, provider: payload.provider }),
      }).then((res) => res.analysis);
      toast(state.analysis.status === "completed" ? "분석이 완료되었습니다." : "분석에 실패했습니다.", state.analysis.status === "completed" ? "ok" : "error");
    } else if (name === "git-import") {
      const result = await api("/api/git/import", {
        method: "POST",
        body: JSON.stringify({
          repo_path: payload.repo_path,
          author_email: payload.author_email,
          limit: Number(payload.limit || 20),
        }),
      });
      toast(`업무 ${result.created_activities}건 · 성과 후보 ${result.created_candidates}건을 수집했습니다.`, "ok");
    } else if (name === "report-generate") {
      const sections = String(payload.custom_sections || "")
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean);
      const result = await api("/api/reports", {
        method: "POST",
        body: JSON.stringify({
          template: payload.template,
          period_kind: payload.period_kind,
          reference: payload.reference,
          start: payload.start,
          end: payload.end,
          title: payload.title,
          char_limit: Number(payload.char_limit || 0),
          format: payload.format,
          custom_sections: sections,
        }),
      });
      state.reportPreview = result.report;
      toast(`보고서 v${result.report.version} 을 생성했습니다.`, "ok");
    }
    await refresh();
  }

  // ---------------------------------------------------------------------
  // 이벤트
  // ---------------------------------------------------------------------
  root.addEventListener("click", async (event) => {
    const nav = event.target.closest("[data-screen]");
    if (nav) {
      state.screen = nav.getAttribute("data-screen");
      state.analysis = null;
      state.editingIntelCandidate = null;
      render();
      return;
    }
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.getAttribute("data-action");
    const id = button.getAttribute("data-id");
    try {
      if (action === "refresh") await refresh();
      else if (action === "open-intel") {
        state.projectAnalysis = (await api(`/api/projects/analyses/${id}`)).analysis;
        state.screen = "projects";
        render();
      } else if (action === "intel-apply") {
        const analysisId = button.getAttribute("data-analysis");
        const select = button.closest("article")?.querySelector(".intel-activity-select");
        const result = await api(`/api/projects/analyses/${analysisId}/candidates/${id}/apply`, {
          method: "POST",
          body: JSON.stringify({ activity_id: select ? select.value : "" }),
        });
        toast("성과로 저장했습니다. 성과 관리에서 근거를 확인하고 확정하세요.", "ok");
        state.projectAnalysis = (await api(`/api/projects/analyses/${analysisId}`)).analysis;
        state.editingAchievement = result.achievement;
        await refresh();
      } else if (action === "edit-intel-candidate") {
        state.editingIntelCandidate = id;
        render();
      } else if (action === "cancel-intel-candidate") {
        state.editingIntelCandidate = null;
        render();
      } else if (action === "toggle-intel-validation") {
        const analysisId = button.getAttribute("data-analysis");
        const status = button.getAttribute("data-status");
        state.projectAnalysis = (await api(`/api/projects/analyses/${analysisId}/candidates/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ status }),
        })).analysis;
        toast(status === "needs_validation" ? "추가 검증 필요로 표시했습니다." : "검증 필요 표시를 해제했습니다.", "ok");
        await refresh();
      } else if (action === "merge-intel-candidate") {
        const analysisId = button.getAttribute("data-analysis");
        const others = state.projectAnalysis.candidates.filter((item) => item.id !== id && item.status !== "applied" && item.status !== "dismissed");
        if (!others.length) {
          toast("병합할 다른 후보가 없습니다.");
          return;
        }
        const listing = others.map((item, index) => `${index + 1}. ${item.title}`).join("\n");
        const answer = window.prompt(`병합 대상 번호를 입력하세요.\n${listing}`);
        const index = Number(answer) - 1;
        if (!answer || !Number.isInteger(index) || !others[index]) return;
        state.projectAnalysis = (await api(`/api/projects/analyses/${analysisId}/candidates/${id}/merge`, {
          method: "POST",
          body: JSON.stringify({ target_id: others[index].id }),
        })).analysis;
        toast("후보를 병합했습니다. 근거와 메모는 대상 후보에 보존됩니다.", "ok");
        await refresh();
      } else if (action === "intel-dismiss") {
        const analysisId = button.getAttribute("data-analysis");
        state.projectAnalysis = (await api(`/api/projects/analyses/${analysisId}/candidates/${id}/dismiss`, { method: "POST" })).analysis;
        toast("후보를 제외했습니다.", "ok");
        await refresh();
      } else if (action === "edit-activity") {
        state.editingActivity = state.activities.find((item) => item.id === id) || null;
        render();
      } else if (action === "cancel-activity-edit") {
        state.editingActivity = null;
        render();
      } else if (action === "delete-activity") {
        if (window.confirm("이 업무 기록을 삭제할까요? 연결된 성과에서 참조가 제거됩니다.")) {
          await api(`/api/activities/${id}`, { method: "DELETE" });
          toast("삭제했습니다.", "ok");
          await refresh();
        }
      } else if (action === "analyze-activity") {
        state.screen = "ai";
        state.analysis = null;
        render();
        const select = root.querySelector('select[name="activity_id"]');
        if (select) select.value = id;
        toast("AI 분석 화면에서 실행 버튼을 누르세요.");
      } else if (action === "create-achievement") {
        const ids = Array.from(state.selectedActivities);
        if (!ids.length) return;
        const result = await api("/api/achievements/from-activities", {
          method: "POST",
          body: JSON.stringify({ activity_ids: ids }),
        });
        state.selectedActivities.clear();
        state.editingAchievement = result.achievement;
        toast("성과를 만들었습니다. 결과와 근거를 보완하세요.", "ok");
        await refresh();
      } else if (action === "edit-achievement") {
        state.editingAchievement = state.achievements.find((item) => item.id === id) || null;
        render();
      } else if (action === "cancel-achievement-edit") {
        state.editingAchievement = null;
        render();
      } else if (action === "delete-achievement") {
        if (window.confirm("이 성과를 삭제할까요? 연결된 지표도 함께 삭제됩니다.")) {
          await api(`/api/achievements/${id}`, { method: "DELETE" });
          await refresh();
        }
      } else if (action === "edit-evidence") {
        state.editingEvidence = state.evidence.find((item) => item.id === id) || null;
        render();
      } else if (action === "cancel-evidence-edit") {
        state.editingEvidence = null;
        render();
      } else if (action === "delete-evidence") {
        if (window.confirm("이 근거를 삭제할까요? 연결된 성과에서도 제거됩니다.")) {
          await api(`/api/evidence/${id}`, { method: "DELETE" });
          await refresh();
        }
      } else if (action === "apply-analysis") {
        const result = await api(`/api/ai/analyses/${id}/apply`, { method: "POST" });
        state.analysis = null;
        state.screen = "achievements";
        state.editingAchievement = result.achievement;
        toast("성과로 저장했습니다. 근거를 연결해 확정하세요.", "ok");
        await refresh();
      } else if (action === "run-migration") {
        if (!window.confirm("DevFolio 데이터를 이전할까요? 원본은 그대로 두고 백업을 만듭니다.")) return;
        state.migration = (await api("/api/migrate", { method: "POST", body: JSON.stringify({}) })).migration;
        toast(state.migration.message || "이전을 완료했습니다.", "ok");
        await refresh();
      }
    } catch (error) {
      toast(error.message || "요청을 처리하지 못했습니다.", "error");
    }
  });

  root.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-form]");
    if (!form) return;
    event.preventDefault();
    try {
      await handleForm(form.getAttribute("data-form"), form);
    } catch (error) {
      toast(error.message || "저장하지 못했습니다.", "error");
    }
  });

  root.addEventListener("change", async (event) => {
    const checkbox = event.target.closest("[data-select-activity]");
    if (checkbox) {
      const id = checkbox.getAttribute("data-select-activity");
      if (checkbox.checked) state.selectedActivities.add(id);
      else state.selectedActivities.delete(id);
      render();
      return;
    }
    const statusSelect = event.target.closest("[data-report-status]");
    if (statusSelect) {
      try {
        await api(`/api/reports/${statusSelect.getAttribute("data-report-status")}`, {
          method: "PATCH",
          body: JSON.stringify({ status: statusSelect.value }),
        });
        toast("제출 상태를 변경했습니다.", "ok");
        await refresh();
      } catch (error) {
        toast(error.message, "error");
      }
    }
  });

  refresh();
})();
