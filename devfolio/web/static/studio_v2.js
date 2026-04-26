(function () {
  "use strict";

  const SCREEN_ALIASES = {
    home: "dashboard",
    compose: "experiences",
    library: "experiences",
    preview: "editor",
    settings: "settings",
  };

  const SCREENS = ["dashboard", "experiences", "generate", "editor", "export", "settings"];
  const EXPERIENCE_TYPES = {
    work: { label: "실무", accent: "blue", desc: "회사 실무 프로젝트" },
    personal: { label: "개인", accent: "amber", desc: "직접 기획한 개인 프로젝트" },
    study: { label: "학습", accent: "green", desc: "강의·스터디·실험 프로젝트" },
    toy: { label: "토이", accent: "default", desc: "짧은 범위의 토이 프로젝트" },
  };
  const DOC_TYPES = {
    resume: { label: "이력서", short: "Resume", desc: "핵심 위주 1-2장 구성" },
    career: { label: "경력기술서", short: "Career", desc: "프로젝트별 상세 서술" },
    portfolio: { label: "포트폴리오", short: "Portfolio", desc: "케이스 스터디 중심 구성" },
  };
  const TONES = {
    work: { label: "실무 중심", desc: "역할, 기여, 협업을 전면에 둡니다." },
    tech: { label: "기술 중심", desc: "아키텍처, 기술 선택, 구현 판단을 강조합니다." },
    problem: { label: "문제 해결 중심", desc: "문제 정의부터 해결 흐름을 앞에 둡니다." },
    impact: { label: "성과 중심", desc: "지표와 결과를 가장 먼저 읽히게 배치합니다." },
  };
  const SETTINGS_TABS = {
    profile: { label: "Profile", desc: "문서 상단 프로필" },
    ai: { label: "AI", desc: "Provider 및 모델" },
    export: { label: "Export", desc: "기본 템플릿과 저장 경로" },
    general: { label: "General", desc: "언어, 타임존, reasoning" },
    logs: { label: "AI Logs", desc: "요청·응답 기록" },
  };
  const COMMON_PROVIDERS = ["anthropic", "openai", "gemini", "groq", "openrouter", "ollama", "pollinations"];
  const PROJECT_TYPE_BY_EXPERIENCE_KIND = {
    work: "company",
    personal: "side",
    study: "course",
    toy: "side",
  };
  const EXPERIENCE_KIND_BY_PROJECT_TYPE = {
    company: "work",
    side: "personal",
    course: "study",
  };

  let root = null;
  let previewTimer = null;
  let toastTimer = null;
  let dragSectionId = "";
  let lastRenderedScreen = "";

  const state = {
    initialized: document.body.dataset.initialized === "true",
    config: null,
    experiences: [],
    experienceSummary: {
      total: 0,
      by_type: { work: 0, personal: 0, study: 0, toy: 0 },
      by_document: { resume: 0, career: 0, portfolio: 0 },
    },
    experienceForm: emptyExperience(),
    editingExperienceId: "",
    currentDoc: {
      docType: "career",
      tone: "work",
      template: "default",
      format: "html",
      selectedIds: [],
      hiddenIds: [],
      preview: null,
      lastExport: null,
    },
    generate: {
      step: 0,
      docType: "",
      selectedIds: [],
      tone: "",
      filter: "all",
      busy: false,
    },
    importer: {
      repoPath: "",
      authorEmail: "",
      analyze: true,
    },
    ui: {
      loading: true,
      screen: "dashboard",
      expMode: "list",
      expView: "card",
      expFilter: "all",
      expSearch: "",
      formSection: "intake",
      settingsTab: "profile",
      toast: null,
      searchFocus: false,
      aiLoading: false,
      aiLoadingMsg: "",
      logs: [],
      logsLoading: false,
      fileBrowser: {
        open: false,
        targetField: "scan-repo-path",
        currentPath: null,
        parentPath: null,
        entries: [],
        roots: [],
        loading: false,
      },
    },
  };

  document.addEventListener("DOMContentLoaded", () => {
    root = document.getElementById("app");
    applyRoute(location.hash.replace(/^#/, ""));
    bindEvents();
    render();
    loadInitialData();
  });

  function emptyPeriod() {
    return { start: "", end: "" };
  }

  function emptyTask() {
    return {
      id: "",
      name: "",
      period: emptyPeriod(),
      problem: "",
      solution: "",
      result: "",
      tech_used: [],
      keywords: [],
      ai_generated_text: "",
    };
  }

  function baseExperienceTemplate() {
    return {
      id: "",
      title: "",
      type: "work",
      status: "done",
      organization: "",
      period: emptyPeriod(),
      role: "",
      team_size: 1,
      tech_stack: [],
      one_line_summary: "",
      summary: "",
      links: { github: "", demo: "", docs: "", video: "" },
      overview: {
        background: "",
        problem: "",
        target_users: [],
        goals: [],
        non_goals: [],
      },
      user_flow: [],
      tech_stack_detail: { frontend: [], backend: [], database: [], infra: [], tools: [] },
      architecture: { summary: "", components: [], data_model: [], api_examples: [] },
      features: [],
      problem_solving_cases: [],
      performance_security_operations: { performance: [], security: [], operations: [] },
      results: { quantitative: [], qualitative: [] },
      retrospective: {
        what_went_well: [],
        what_was_hard: [],
        what_i_learned: [],
        next_steps: [],
      },
      assets: { screenshots: [], diagrams: [] },
      studio_meta: {
        experience_kind: "work",
        priority: 3,
        document_targets: [],
        collaboration: false,
        extra_links: [],
      },
      tags: [],
      tasks: [emptyTask()],
      raw_text: "",
    };
  }

  function emptyExperience() {
    return normalizeExperience(baseExperienceTemplate());
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function normalizeArray(value) {
    if (Array.isArray(value)) {
      return value.map((item) => String(item || "").trim()).filter(Boolean);
    }
    if (typeof value === "string") {
      return value
        .split(/\n|,/)
        .map((item) => item.trim())
        .filter(Boolean);
    }
    return [];
  }

  function normalizePeriod(period) {
    return {
      start: period && period.start ? String(period.start) : "",
      end: period && period.end ? String(period.end) : "",
    };
  }

  function normalizeTask(task) {
    return {
      ...emptyTask(),
      ...(task || {}),
      period: normalizePeriod(task && task.period),
      tech_used: normalizeArray(task && task.tech_used),
      keywords: normalizeArray(task && task.keywords),
    };
  }

  function normalizeExperience(input) {
    const base = baseExperienceTemplate();
    const item = { ...base, ...(input || {}) };
    item.type = item.type || item.studio_meta?.experience_kind || "work";
    item.period = normalizePeriod(item.period);
    item.team_size = Number(item.team_size) > 0 ? Number(item.team_size) : 1;
    item.tech_stack = normalizeArray(item.tech_stack);
    item.tags = normalizeArray(item.tags);
    item.links = { ...base.links, ...(item.links || {}) };
    item.overview = {
      ...base.overview,
      ...(item.overview || {}),
      target_users: normalizeArray(item.overview && item.overview.target_users),
      goals: normalizeArray(item.overview && item.overview.goals),
      non_goals: normalizeArray(item.overview && item.overview.non_goals),
    };
    item.tasks = Array.isArray(item.tasks) && item.tasks.length ? item.tasks.map(normalizeTask) : [emptyTask()];
    item.studio_meta = {
      ...base.studio_meta,
      ...(item.studio_meta || {}),
      experience_kind: item.type || item.studio_meta?.experience_kind || "work",
      priority: clamp(Number(item.studio_meta?.priority || 3), 1, 5),
      document_targets: normalizeArray(item.studio_meta?.document_targets).filter((docType) => DOC_TYPES[docType]),
      collaboration: Boolean(item.studio_meta?.collaboration || item.team_size > 1),
      extra_links: Array.isArray(item.studio_meta?.extra_links)
        ? item.studio_meta.extra_links
            .map((link) => ({
              label: String((link && link.label) || "").trim(),
              url: String((link && link.url) || "").trim(),
            }))
            .filter((link) => link.label || link.url)
        : [],
    };
    item.results = { ...base.results, ...(item.results || {}) };
    item.retrospective = { ...base.retrospective, ...(item.retrospective || {}) };
    item.assets = { ...base.assets, ...(item.assets || {}) };
    return item;
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function normalizeConfig(input) {
    return input || {
      user: { name: "", email: "", github: "", blog: "" },
      export: { default_format: "md", default_template: "default", output_dir: "" },
      sync: { enabled: false, repo_url: "", branch: "main" },
      general: {
        default_language: "ko",
        timezone: "Asia/Seoul",
        default_ai_provider: "",
        reasoning_strategy: "single",
        reasoning_samples: 1,
        judge_provider: "",
      },
      ai_providers: [],
    };
  }

  function summarizeExperiences() {
    const byType = { work: 0, personal: 0, study: 0, toy: 0 };
    const byDocument = { resume: 0, career: 0, portfolio: 0 };
    state.experiences.forEach((experience) => {
      byType[experience.type] = (byType[experience.type] || 0) + 1;
      experience.studio_meta.document_targets.forEach((docType) => {
        byDocument[docType] = (byDocument[docType] || 0) + 1;
      });
    });
    state.experienceSummary = {
      total: state.experiences.length,
      by_type: byType,
      by_document: byDocument,
    };
  }

  function docTemplateFor(docType, tone) {
    if (tone === "impact" && docType === "resume") {
      return "achievement";
    }
    return "default";
  }

  function formatPeriod(period) {
    if (!period || (!period.start && !period.end)) {
      return "기간 미정";
    }
    return `${period.start || "?"} - ${period.end || "현재"}`;
  }

  function typeLabel(type) {
    return EXPERIENCE_TYPES[type] ? EXPERIENCE_TYPES[type].label : type;
  }

  function typeAccent(type) {
    return EXPERIENCE_TYPES[type] ? EXPERIENCE_TYPES[type].accent : "default";
  }

  function docLabel(docType) {
    return DOC_TYPES[docType] ? DOC_TYPES[docType].label : docType;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function selected(condition) {
    return condition ? " selected" : "";
  }

  function checked(condition) {
    return condition ? " checked" : "";
  }

  function priorityStars(priority) {
    return "★".repeat(priority) + "☆".repeat(5 - priority);
  }

  function ensureDocumentSession() {
    const validIds = new Set(state.experiences.map((experience) => experience.id));
    state.currentDoc.selectedIds = state.currentDoc.selectedIds.filter((id) => validIds.has(id));
    state.currentDoc.hiddenIds = state.currentDoc.hiddenIds.filter((id) => validIds.has(id));
    state.generate.selectedIds = state.generate.selectedIds.filter((id) => validIds.has(id));
  }

  function experienceById(id) {
    return state.experiences.find((experience) => experience.id === id) || null;
  }

  function experienceToProjectDraft(experience) {
    const item = normalizeExperience(experience);
    return {
      id: item.id,
      name: item.title,
      type: PROJECT_TYPE_BY_EXPERIENCE_KIND[item.type] || "company",
      status: item.status,
      organization: item.organization,
      period: item.period,
      role: item.role,
      team_size: item.team_size,
      tech_stack: item.tech_stack,
      one_line_summary: item.one_line_summary,
      summary: item.summary,
      links: item.links,
      overview: item.overview,
      user_flow: item.user_flow,
      tech_stack_detail: item.tech_stack_detail,
      architecture: item.architecture,
      features: item.features,
      problem_solving_cases: item.problem_solving_cases,
      performance_security_operations: item.performance_security_operations,
      results: item.results,
      retrospective: item.retrospective,
      assets: item.assets,
      studio_meta: {
        ...item.studio_meta,
        experience_kind: item.type,
      },
      tags: item.tags,
      tasks: item.tasks,
      raw_text: item.raw_text,
    };
  }

  function projectDraftToExperience(projectDraft) {
    return normalizeExperience({
      ...projectDraft,
      title: projectDraft.name || "",
      type: projectDraft.studio_meta?.experience_kind || EXPERIENCE_KIND_BY_PROJECT_TYPE[projectDraft.type] || "work",
    });
  }

  function scanPayloadToExperience(payload) {
    const projectType = payload.type || "side";
    return normalizeExperience({
      title: payload.name || "",
      type: EXPERIENCE_KIND_BY_PROJECT_TYPE[projectType] || "personal",
      status: payload.status || "done",
      organization: payload.organization || "",
      period: {
        start: payload.period?.start || payload.period_start || "",
        end: payload.period?.end || payload.period_end || "",
      },
      role: payload.role || "개발자",
      team_size: payload.team_size || 1,
      tech_stack: payload.tech_stack || [],
      summary: payload.summary || "",
      tags: payload.tags || [],
      tasks: Array.isArray(payload.tasks)
        ? payload.tasks.map((task) =>
            normalizeTask({
              name: task.name || "",
              problem: task.problem || "",
              solution: task.solution || "",
              result: task.result || "",
              tech_used: task.tech_used || [],
              keywords: task.keywords || [],
              ai_generated_text: task.ai_generated_text || "",
              period: task.period || emptyPeriod(),
            })
          )
        : [emptyTask()],
      links: {
        github: payload.repo_url || "",
        demo: "",
        docs: "",
        video: "",
      },
      studio_meta: {
        experience_kind: EXPERIENCE_KIND_BY_PROJECT_TYPE[projectType] || "personal",
        priority: 3,
        document_targets: [],
        collaboration: Number(payload.team_size || 1) > 1,
        extra_links: [],
      },
    });
  }

  function yieldToBrowser() {
    return new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 0)));
  }

  function requestJson(path, options) {
    return fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...(options && options.headers ? options.headers : {}),
      },
      ...options,
    }).then(async (response) => {
      const text = await response.text();
      const payload = text ? safeJsonParse(text) : null;
      if (!response.ok) {
        const detail = payload && (payload.detail || payload.message || payload.error);
        throw new Error(detail || response.statusText || "요청 실패");
      }
      return payload;
    });
  }

  function safeJsonParse(text) {
    try {
      return JSON.parse(text);
    } catch (error) {
      return null;
    }
  }

  async function loadInitialData() {
    state.ui.loading = true;
    render();
    try {
      const [configPayload, experiencesPayload] = await Promise.all([
        requestJson("/api/config"),
        requestJson("/api/experiences"),
      ]);
      state.config = normalizeConfig(configPayload);
      state.experiences = (experiencesPayload.experiences || []).map(normalizeExperience);
      summarizeExperiences();
      if (!state.importer.authorEmail) {
        state.importer.authorEmail = state.config.user?.email || "";
      }
      ensureDocumentSession();
      if (!state.currentDoc.selectedIds.length) {
        const firstTargeted = state.experiences
          .filter((experience) => experience.studio_meta.document_targets.length)
          .sort((left, right) => right.studio_meta.priority - left.studio_meta.priority)
          .slice(0, 3)
          .map((experience) => experience.id);
        state.currentDoc.selectedIds = firstTargeted;
      }
      state.ui.loading = false;
      render();
      if ((state.ui.screen === "editor" || state.ui.screen === "export") && state.currentDoc.selectedIds.length) {
        queuePreview();
      }
    } catch (error) {
      state.ui.loading = false;
      showToast(error.message || "초기 데이터를 불러오지 못했습니다.", "error");
      render();
    }
  }

  function applyRoute(rawRoute) {
    const route = SCREEN_ALIASES[rawRoute] || rawRoute || "dashboard";
    state.ui.screen = SCREENS.includes(route) ? route : "dashboard";
    if (rawRoute === "compose") {
      state.ui.expMode = "new";
      state.ui.formSection = "intake";
    }
  }

  function setRoute(screen) {
    const safeScreen = SCREENS.includes(screen) ? screen : "dashboard";
    if (location.hash.replace(/^#/, "") !== safeScreen) {
      history.pushState({}, "", `#${safeScreen}`);
    }
    state.ui.screen = safeScreen;
  }

  function bindEvents() {
    window.addEventListener("hashchange", () => {
      applyRoute(location.hash.replace(/^#/, ""));
      render();
      if ((state.ui.screen === "editor" || state.ui.screen === "export") && state.currentDoc.selectedIds.length) {
        queuePreview();
      }
    });

    document.addEventListener("click", handleClick);
    document.addEventListener("input", handleInput);
    document.addEventListener("submit", handleSubmit);
  }

  function handleInput(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (target.id === "experience-search" && target instanceof HTMLInputElement) {
      state.ui.expSearch = target.value;
      state.ui.searchFocus = true;
      render();
      return;
    }

    if (target.id === "scan-repo-path" && target instanceof HTMLInputElement) {
      state.importer.repoPath = target.value;
      return;
    }

    if (target.id === "scan-author-email" && target instanceof HTMLInputElement) {
      state.importer.authorEmail = target.value;
      return;
    }

    if (target.id === "scan-analyze" && target instanceof HTMLInputElement) {
      state.importer.analyze = target.checked;
    }
  }

  async function handleSubmit(event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    event.preventDefault();

    try {
      if (form.id === "settings-profile-form") {
        const data = new FormData(form);
        await requestJson("/api/config/user", {
          method: "PUT",
          body: JSON.stringify({
            name: String(data.get("name") || ""),
            email: String(data.get("email") || ""),
            github: String(data.get("github") || ""),
            blog: String(data.get("blog") || ""),
          }),
        });
        await refreshConfig();
        showToast("프로필 설정을 저장했습니다.", "ok");
      } else if (form.id === "settings-export-form") {
        const data = new FormData(form);
        await requestJson("/api/config/export", {
          method: "PUT",
          body: JSON.stringify({
            default_format: String(data.get("default_format") || "md"),
            default_template: String(data.get("default_template") || "default"),
            output_dir: String(data.get("output_dir") || ""),
          }),
        });
        await refreshConfig();
        showToast("내보내기 기본값을 저장했습니다.", "ok");
      } else if (form.id === "settings-general-form") {
        const data = new FormData(form);
        await requestJson("/api/config/general", {
          method: "PUT",
          body: JSON.stringify({
            default_language: String(data.get("default_language") || "ko"),
            timezone: String(data.get("timezone") || "Asia/Seoul"),
            default_ai_provider: String(data.get("default_ai_provider") || ""),
            reasoning_strategy: String(data.get("reasoning_strategy") || "single"),
            reasoning_samples: Number(data.get("reasoning_samples") || 1),
            judge_provider: String(data.get("judge_provider") || ""),
          }),
        });
        await refreshConfig();
        showToast("일반 설정을 저장했습니다.", "ok");
      } else if (form.id === "settings-ai-form") {
        const data = new FormData(form);
        await requestJson("/api/config/ai", {
          method: "POST",
          body: JSON.stringify({
            name: String(data.get("provider_name") || ""),
            model: String(data.get("provider_model") || ""),
            api_key: String(data.get("provider_api_key") || ""),
            base_url: String(data.get("provider_base_url") || ""),
          }),
        });
        await refreshConfig();
        showToast("AI Provider를 저장했습니다.", "ok");
      }
      render();
    } catch (error) {
      showToast(error.message || "설정을 저장하지 못했습니다.", "error");
      render();
    }
  }

  async function refreshConfig() {
    state.config = normalizeConfig(await requestJson("/api/config"));
  }

  async function refreshExperiences() {
    const payload = await requestJson("/api/experiences");
    state.experiences = (payload.experiences || []).map(normalizeExperience);
    summarizeExperiences();
    ensureDocumentSession();
  }

  async function handleClick(event) {
    const target = event.target instanceof Element ? event.target.closest("[data-action], [data-screen], [data-exp-id], [data-form-section], [data-tab], [data-doc-type], [data-tone], [data-generate-filter], [data-exp-filter], [data-exp-view]") : null;
    if (!target) {
      return;
    }

    if (state.ui.screen === "experiences" && state.ui.expMode !== "list") {
      syncExperienceFormFromDom();
    }

    const screen = target.getAttribute("data-screen");
    if (screen) {
      setRoute(screen);
      if (screen === "experiences" && state.ui.expMode === "list") {
        state.ui.expMode = "list";
      }
      render();
      if ((screen === "editor" || screen === "export") && state.currentDoc.selectedIds.length) {
        queuePreview();
      }
      return;
    }

    const formSection = target.getAttribute("data-form-section");
    if (formSection) {
      state.ui.formSection = formSection;
      render();
      return;
    }

    const tab = target.getAttribute("data-tab");
    if (tab) {
      state.ui.settingsTab = tab;
      render();
      if (tab === "logs") loadAiLogs();
      return;
    }

    const docType = target.getAttribute("data-doc-type");
    if (docType) {
      state.generate.docType = docType;
      if (!state.generate.selectedIds.length) {
        state.generate.selectedIds = state.experiences
          .filter((experience) => experience.studio_meta.document_targets.includes(docType))
          .map((experience) => experience.id);
      }
      render();
      return;
    }

    const tone = target.getAttribute("data-tone");
    if (tone) {
      state.generate.tone = tone;
      render();
      return;
    }

    const expFilter = target.getAttribute("data-exp-filter");
    if (expFilter) {
      state.ui.expFilter = expFilter;
      render();
      return;
    }

    const expView = target.getAttribute("data-exp-view");
    if (expView) {
      state.ui.expView = expView;
      render();
      return;
    }

    const generateFilter = target.getAttribute("data-generate-filter");
    if (generateFilter) {
      state.generate.filter = generateFilter;
      render();
      return;
    }

    const action = target.getAttribute("data-action");
    const experienceId = target.getAttribute("data-exp-id") || "";

    if (!action) {
      return;
    }

    try {
      switch (action) {
        case "new-experience":
          state.ui.expMode = "new";
          state.ui.formSection = "intake";
          state.editingExperienceId = "";
          state.experienceForm = emptyExperience();
          setRoute("experiences");
          render();
          break;
        case "edit-experience":
          openExperience(experienceId);
          break;
        case "back-to-list":
          state.ui.expMode = "list";
          setRoute("experiences");
          render();
          break;
        case "duplicate-experience":
          duplicateExperience(experienceId);
          break;
        case "delete-experience":
          await deleteExperience(experienceId);
          break;
        case "save-experience":
          await saveExperience();
          break;
        case "add-task":
          state.experienceForm.tasks.push(emptyTask());
          render();
          break;
        case "remove-task":
          removeTask(target);
          render();
          break;
        case "add-extra-link":
          state.experienceForm.studio_meta.extra_links.push({ label: "", url: "" });
          render();
          break;
        case "remove-extra-link":
          removeExtraLink(target);
          render();
          break;
        case "import-text":
          await importFromText();
          break;
        case "import-scan":
          await importFromScan();
          break;
        case "generate-summary":
          await generateSummaryForForm();
          break;
        case "generate-task-bullets":
          await generateTaskBulletsForForm();
          break;
        case "pick-generate-step":
          state.generate.step = clamp(Number(target.getAttribute("data-step") || 0), 0, 3);
          render();
          break;
        case "generate-next":
          await advanceGenerate();
          break;
        case "generate-prev":
          state.generate.step = Math.max(0, state.generate.step - 1);
          render();
          break;
        case "toggle-generate-selection":
          toggleGenerateSelection(experienceId);
          render();
          break;
        case "select-targeted-experiences":
          state.generate.selectedIds = state.experiences
            .filter((experience) => experience.studio_meta.document_targets.includes(state.generate.docType))
            .map((experience) => experience.id);
          render();
          break;
        case "open-editor":
          setRoute("editor");
          render();
          queuePreview();
          break;
        case "open-export":
          setRoute("export");
          render();
          queuePreview();
          break;
        case "reset-generate":
          state.generate = { step: 0, docType: "", selectedIds: [], tone: "", filter: "all", busy: false };
          render();
          break;
        case "toggle-section-visibility":
          toggleSectionVisibility(experienceId);
          render();
          queuePreview();
          break;
        case "refresh-preview":
          await refreshDocumentPreview(false);
          break;
        case "export-document":
          await exportCurrentDocument();
          break;
        case "open-folder":
          await openExportFolder();
          break;
        case "remove-provider":
          await removeProvider(target.getAttribute("data-provider-name") || "");
          break;
        case "test-provider":
          await testProvider(target.getAttribute("data-provider-name") || "");
          break;
        case "use-doc-type":
          state.currentDoc.docType = target.getAttribute("data-value") || state.currentDoc.docType;
          state.currentDoc.template = docTemplateFor(state.currentDoc.docType, state.currentDoc.tone);
          render();
          queuePreview();
          break;
        case "use-template":
          state.currentDoc.template = target.getAttribute("data-value") || state.currentDoc.template;
          render();
          queuePreview();
          break;
        case "use-format":
          state.currentDoc.format = target.getAttribute("data-value") || state.currentDoc.format;
          render();
          break;
        case "open-file-browser":
          state.ui.fileBrowser.open = true;
          state.ui.fileBrowser.targetField = target.getAttribute("data-target") || "scan-repo-path";
          await loadFileBrowserDir(null);
          break;
        case "file-browser-navigate":
          await loadFileBrowserDir(target.getAttribute("data-path") || null);
          break;
        case "file-browser-parent":
          await loadFileBrowserDir(state.ui.fileBrowser.parentPath);
          break;
        case "file-browser-select":
          if (state.ui.fileBrowser.targetField === "scan-repo-path") {
            state.importer.repoPath = state.ui.fileBrowser.currentPath || "";
          }
          state.ui.fileBrowser.open = false;
          render();
          break;
        case "file-browser-close":
          state.ui.fileBrowser.open = false;
          render();
          break;
        case "refresh-ai-logs":
          await loadAiLogs();
          break;
        case "clear-ai-logs":
          await requestJson("/api/ai-logs", { method: "DELETE" });
          state.ui.logs = [];
          showToast("AI 로그를 삭제했습니다.", "ok");
          render();
          break;
        default:
          break;
      }
    } catch (error) {
      showToast(error.message || "요청을 처리하지 못했습니다.", "error");
      render();
    }
  }

  function removeTask(target) {
    const index = Number(target.getAttribute("data-task-index"));
    if (Number.isNaN(index)) {
      return;
    }
    state.experienceForm.tasks = state.experienceForm.tasks.filter((_, taskIndex) => taskIndex !== index);
    if (!state.experienceForm.tasks.length) {
      state.experienceForm.tasks = [emptyTask()];
    }
  }

  function removeExtraLink(target) {
    const index = Number(target.getAttribute("data-link-index"));
    if (Number.isNaN(index)) {
      return;
    }
    state.experienceForm.studio_meta.extra_links = state.experienceForm.studio_meta.extra_links.filter((_, linkIndex) => linkIndex !== index);
  }

  function openExperience(experienceId) {
    const experience = experienceById(experienceId);
    if (!experience) {
      showToast("경험을 찾을 수 없습니다.", "error");
      return;
    }
    state.ui.expMode = "edit";
    state.ui.formSection = "basics";
    state.editingExperienceId = experience.id;
    state.experienceForm = clone(experience);
    setRoute("experiences");
    render();
  }

  function duplicateExperience(experienceId) {
    const experience = experienceById(experienceId);
    if (!experience) {
      showToast("복제할 경험을 찾을 수 없습니다.", "error");
      render();
      return;
    }
    const copy = clone(experience);
    copy.id = "";
    copy.title = `${copy.title} 사본`;
    state.ui.expMode = "new";
    state.ui.formSection = "basics";
    state.editingExperienceId = "";
    state.experienceForm = normalizeExperience(copy);
    setRoute("experiences");
    showToast("경험 사본을 열었습니다. 저장하면 새 항목으로 등록됩니다.", "ok");
    render();
  }

  async function deleteExperience(experienceId) {
    if (!experienceId) {
      return;
    }
    if (!window.confirm("이 경험을 삭제할까요?")) {
      return;
    }
    await requestJson(`/api/experiences/${encodeURIComponent(experienceId)}`, { method: "DELETE" });
    await refreshExperiences();
    if (state.editingExperienceId === experienceId) {
      state.editingExperienceId = "";
      state.ui.expMode = "list";
      state.experienceForm = emptyExperience();
    }
    showToast("경험을 삭제했습니다.", "ok");
    render();
  }

  function syncExperienceFormFromDom() {
    if (state.ui.screen !== "experiences" || state.ui.expMode === "list") {
      return;
    }
    const form = document.getElementById("experience-editor");
    if (!(form instanceof HTMLElement)) {
      return;
    }

    const next = clone(state.experienceForm);

    const readInput = (name, fallback) => {
      const element = form.querySelector(`[name="${name}"]`);
      if (!element) {
        return fallback;
      }
      if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) {
        if (element.type === "checkbox") {
          return element.checked;
        }
        return element.value;
      }
      return fallback;
    };

    next.type = String(readInput("type", next.type) || next.type);
    next.title = String(readInput("title", next.title) || "");
    next.status = String(readInput("status", next.status) || "done");
    next.organization = String(readInput("organization", next.organization) || "");
    next.role = String(readInput("role", next.role) || "");
    next.period.start = String(readInput("period_start", next.period.start) || "");
    next.period.end = String(readInput("period_end", next.period.end) || "");
    next.team_size = clamp(Number(readInput("team_size", next.team_size) || 1), 1, 50);
    next.one_line_summary = String(readInput("one_line_summary", next.one_line_summary) || "");
    next.summary = String(readInput("summary", next.summary) || "");
    next.raw_text = String(readInput("raw_text", next.raw_text) || "");
    next.tech_stack = normalizeArray(readInput("tech_stack", next.tech_stack));
    next.tags = normalizeArray(readInput("tags", next.tags));
    next.links.github = String(readInput("link_github", next.links.github) || "");
    next.links.demo = String(readInput("link_demo", next.links.demo) || "");
    next.links.docs = String(readInput("link_docs", next.links.docs) || "");
    next.links.video = String(readInput("link_video", next.links.video) || "");
    next.overview.background = String(readInput("overview_background", next.overview.background) || "");
    next.overview.problem = String(readInput("overview_problem", next.overview.problem) || "");
    next.overview.target_users = normalizeArray(readInput("overview_target_users", next.overview.target_users));
    next.overview.goals = normalizeArray(readInput("overview_goals", next.overview.goals));
    next.overview.non_goals = normalizeArray(readInput("overview_non_goals", next.overview.non_goals));
    next.studio_meta.priority = clamp(Number(readInput("priority", next.studio_meta.priority) || 3), 1, 5);
    next.studio_meta.collaboration = Boolean(readInput("collaboration", next.studio_meta.collaboration));
    next.studio_meta.experience_kind = next.type;

    const targetInputs = Array.from(form.querySelectorAll('input[name="document_target"]:checked'));
    if (targetInputs.length) {
      next.studio_meta.document_targets = targetInputs
        .map((input) => input.value)
        .filter((docType) => DOC_TYPES[docType]);
    } else if (form.querySelector('input[name="document_target"]')) {
      next.studio_meta.document_targets = [];
    }

    const taskRows = Array.from(form.querySelectorAll("[data-task-row]"));
    if (taskRows.length) {
      next.tasks = taskRows.map((row, index) => {
        const readFromRow = (field) => {
          const element = row.querySelector(`[name="${field}"]`);
          return element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement ? element.value : "";
        };
        return normalizeTask({
          ...(next.tasks[index] || emptyTask()),
          id: row.getAttribute("data-task-id") || next.tasks[index]?.id || "",
          name: readFromRow("task_name"),
          problem: readFromRow("task_problem"),
          solution: readFromRow("task_solution"),
          result: readFromRow("task_result"),
          tech_used: normalizeArray(readFromRow("task_tech_used")),
          keywords: normalizeArray(readFromRow("task_keywords")),
          period: {
            start: readFromRow("task_period_start"),
            end: readFromRow("task_period_end"),
          },
        });
      });
    }

    const extraLinks = Array.from(form.querySelectorAll("[data-extra-link-row]"));
    if (extraLinks.length || form.querySelector("[data-extra-link-anchor]")) {
      next.studio_meta.extra_links = extraLinks
        .map((row) => {
          const label = row.querySelector('[name="extra_link_label"]');
          const url = row.querySelector('[name="extra_link_url"]');
          return {
            label: label instanceof HTMLInputElement ? label.value.trim() : "",
            url: url instanceof HTMLInputElement ? url.value.trim() : "",
          };
        })
        .filter((link) => link.label || link.url);
    }

    state.experienceForm = normalizeExperience(next);
  }

  async function saveExperience() {
    syncExperienceFormFromDom();
    const method = state.editingExperienceId ? "PUT" : "POST";
    const path = state.editingExperienceId
      ? `/api/experiences/${encodeURIComponent(state.editingExperienceId)}`
      : "/api/experiences";
    const payload = await requestJson(path, {
      method,
      body: JSON.stringify(state.experienceForm),
    });
    const saved = normalizeExperience(payload.experience);
    const existingIndex = state.experiences.findIndex((experience) => experience.id === saved.id);
    if (existingIndex >= 0) {
      state.experiences.splice(existingIndex, 1, saved);
    } else {
      state.experiences.unshift(saved);
    }
    summarizeExperiences();
    state.editingExperienceId = saved.id;
    state.ui.expMode = "edit";
    state.ui.formSection = "basics";
    state.experienceForm = clone(saved);
    if (state.currentDoc.selectedIds.includes(saved.id)) {
      queuePreview();
    }
    showToast("경험을 저장했습니다.", "ok");
    render();
  }

  async function importFromText() {
    syncExperienceFormFromDom();
    if (!state.experienceForm.raw_text.trim()) {
      showToast("텍스트 입력이 필요합니다.", "warn");
      render();
      return;
    }
    state.ui.aiLoading = true;
    state.ui.aiLoadingMsg = "텍스트를 분석하고 있습니다...";
    render();
    await yieldToBrowser();
    try {
      const payload = await requestJson("/api/intake/project-draft", {
        method: "POST",
        body: JSON.stringify({
          raw_text: state.experienceForm.raw_text,
          lang: (state.config && state.config.general && state.config.general.default_language) || "ko",
        }),
      });
      state.experienceForm = projectDraftToExperience(payload.draft);
      state.ui.formSection = "basics";
      showToast("텍스트를 구조화해 초안을 채웠습니다.", "ok");
    } finally {
      state.ui.aiLoading = false;
      state.ui.aiLoadingMsg = "";
      render();
    }
  }

  async function importFromScan() {
    if (!state.importer.repoPath.trim()) {
      showToast("저장소 경로를 입력하세요.", "warn");
      render();
      return;
    }
    state.ui.aiLoading = true;
    state.ui.aiLoadingMsg = state.importer.analyze ? "Git 스캔 및 AI 분석 중입니다..." : "Git 저장소를 스캔하고 있습니다...";
    render();
    await yieldToBrowser();
    try {
      const payload = await requestJson("/api/scan/git", {
        method: "POST",
        body: JSON.stringify({
          repo_path: state.importer.repoPath.trim(),
          author_email: state.importer.authorEmail.trim(),
          refresh: true,
          analyze: state.importer.analyze,
          lang: (state.config && state.config.general && state.config.general.default_language) || "ko",
        }),
      });
      state.experienceForm = scanPayloadToExperience(payload.payload || {});
      state.ui.formSection = "basics";
      showToast(payload.analyzed ? "Git 스캔과 AI 분석 결과를 불러왔습니다." : "Git 스캔 결과를 불러왔습니다.", "ok");
    } finally {
      state.ui.aiLoading = false;
      state.ui.aiLoadingMsg = "";
      render();
    }
  }

  async function generateSummaryForForm() {
    syncExperienceFormFromDom();
    state.ui.aiLoading = true;
    state.ui.aiLoadingMsg = "AI가 요약을 생성하고 있습니다...";
    render();
    await yieldToBrowser();
    try {
      if (state.editingExperienceId) {
        const payload = await requestJson(`/api/experiences/${encodeURIComponent(state.editingExperienceId)}/generate-summary`, {
          method: "POST",
          body: JSON.stringify({ lang: "ko" }),
        });
        const saved = normalizeExperience(payload.experience);
        state.experienceForm = clone(saved);
        const index = state.experiences.findIndex((experience) => experience.id === saved.id);
        if (index >= 0) {
          state.experiences.splice(index, 1, saved);
        }
      } else {
        const payload = await requestJson("/api/draft/generate-summary", {
          method: "POST",
          body: JSON.stringify({
            draft: experienceToProjectDraft(state.experienceForm),
            lang: "ko",
          }),
        });
        state.experienceForm = projectDraftToExperience(payload.draft);
      }
      showToast("요약을 생성했습니다.", "ok");
    } finally {
      state.ui.aiLoading = false;
      state.ui.aiLoadingMsg = "";
      render();
    }
  }

  async function generateTaskBulletsForForm() {
    syncExperienceFormFromDom();
    state.ui.aiLoading = true;
    state.ui.aiLoadingMsg = "AI가 작업 설명을 생성하고 있습니다...";
    render();
    await yieldToBrowser();
    try {
      if (state.editingExperienceId) {
        const payload = await requestJson(`/api/experiences/${encodeURIComponent(state.editingExperienceId)}/generate-task-bullets`, {
          method: "POST",
          body: JSON.stringify({ lang: "ko" }),
        });
        const saved = normalizeExperience(payload.experience);
        state.experienceForm = clone(saved);
        const index = state.experiences.findIndex((experience) => experience.id === saved.id);
        if (index >= 0) {
          state.experiences.splice(index, 1, saved);
        }
      } else {
        const payload = await requestJson("/api/draft/generate-task-bullets", {
          method: "POST",
          body: JSON.stringify({
            draft: experienceToProjectDraft(state.experienceForm),
            lang: "ko",
          }),
        });
        state.experienceForm = projectDraftToExperience(payload.draft);
      }
      showToast("작업 문구를 생성했습니다.", "ok");
    } finally {
      state.ui.aiLoading = false;
      state.ui.aiLoadingMsg = "";
      render();
    }
  }

  function toggleGenerateSelection(experienceId) {
    if (!experienceId) {
      return;
    }
    const exists = state.generate.selectedIds.includes(experienceId);
    state.generate.selectedIds = exists
      ? state.generate.selectedIds.filter((id) => id !== experienceId)
      : [...state.generate.selectedIds, experienceId];
  }

  async function advanceGenerate() {
    if (state.generate.step === 0 && !state.generate.docType) {
      showToast("문서 종류를 선택하세요.", "warn");
      render();
      return;
    }
    if (state.generate.step === 1 && !state.generate.selectedIds.length) {
      showToast("포함할 경험을 선택하세요.", "warn");
      render();
      return;
    }
    if (state.generate.step === 2 && !state.generate.tone) {
      showToast("문서 톤을 선택하세요.", "warn");
      render();
      return;
    }

    if (state.generate.step < 2) {
      state.generate.step += 1;
      render();
      return;
    }

    state.generate.busy = true;
    render();
    state.currentDoc.docType = state.generate.docType;
    state.currentDoc.tone = state.generate.tone;
    state.currentDoc.template = docTemplateFor(state.generate.docType, state.generate.tone);
    state.currentDoc.selectedIds = [...state.generate.selectedIds];
    state.currentDoc.hiddenIds = [];
    state.currentDoc.preview = null;
    state.currentDoc.lastExport = null;
    await refreshDocumentPreview(true);
    state.generate.busy = false;
    state.generate.step = 3;
    showToast("문서 세션을 생성했습니다.", "ok");
    render();
  }

  function toggleSectionVisibility(experienceId) {
    if (!experienceId) {
      return;
    }
    const hidden = state.currentDoc.hiddenIds.includes(experienceId);
    state.currentDoc.hiddenIds = hidden
      ? state.currentDoc.hiddenIds.filter((id) => id !== experienceId)
      : [...state.currentDoc.hiddenIds, experienceId];
  }

  function visibleSelectedIds() {
    return state.currentDoc.selectedIds.filter((id) => !state.currentDoc.hiddenIds.includes(id));
  }

  function queuePreview() {
    window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(() => {
      refreshDocumentPreview(true).catch((error) => {
        showToast(error.message || "미리보기를 갱신하지 못했습니다.", "error");
        render();
      });
    }, 220);
  }

  async function refreshDocumentPreview(silent) {
    const selectedIds = visibleSelectedIds();
    if (!selectedIds.length) {
      state.currentDoc.preview = null;
      render();
      return;
    }
    const payload = await requestJson(`/api/preview/${encodeURIComponent(state.currentDoc.docType)}`, {
      method: "POST",
      body: JSON.stringify({
        source: "saved",
        project_ids: selectedIds,
        template: state.currentDoc.template,
        format: "html",
      }),
    });
    state.currentDoc.preview = payload;
    if (!silent) {
      showToast("문서 미리보기를 갱신했습니다.", "ok");
    }
    render();
  }

  async function exportCurrentDocument() {
    const selectedIds = visibleSelectedIds();
    if (!selectedIds.length) {
      showToast("내보낼 경험이 없습니다.", "warn");
      render();
      return;
    }
    const payload = await requestJson(`/api/export/${encodeURIComponent(state.currentDoc.docType)}`, {
      method: "POST",
      body: JSON.stringify({
        source: "saved",
        project_ids: selectedIds,
        template: state.currentDoc.template,
        format: state.currentDoc.format,
      }),
    });
    state.currentDoc.lastExport = payload;
    showToast(`${docLabel(state.currentDoc.docType)} 문서를 ${state.currentDoc.format.toUpperCase()}로 내보냈습니다.`, "ok");
    render();
  }

  async function openExportFolder() {
    const folder = state.currentDoc.lastExport && state.currentDoc.lastExport.folder;
    if (!folder) {
      showToast("먼저 문서를 내보내세요.", "warn");
      render();
      return;
    }
    await requestJson(`/api/fs/open-folder?path=${encodeURIComponent(folder)}`, { method: "POST", headers: {} });
    showToast("출력 폴더를 열었습니다.", "ok");
    render();
  }

  async function removeProvider(name) {
    if (!name) {
      return;
    }
    if (!window.confirm(`${name} provider를 삭제할까요?`)) {
      return;
    }
    await requestJson(`/api/config/ai/${encodeURIComponent(name)}`, { method: "DELETE" });
    await refreshConfig();
    showToast("AI Provider를 삭제했습니다.", "ok");
    render();
  }

  async function testProvider(name) {
    if (!name) {
      return;
    }
    const payload = await requestJson(`/api/config/ai/${encodeURIComponent(name)}/test`, { method: "POST" });
    showToast(payload.message || "연결을 확인했습니다.", payload.status === "ok" ? "ok" : "warn");
    render();
  }

  function showToast(message, tone) {
    state.ui.toast = {
      message,
      tone: tone || "ok",
    };
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      state.ui.toast = null;
      render();
    }, 2400);
  }

  function render() {
    if (!root) {
      return;
    }

    const animateScreen = state.ui.screen !== lastRenderedScreen;
    lastRenderedScreen = state.ui.screen;

    root.innerHTML = `
      <div class="studio-app">
        ${renderSidebar()}
        <div class="shell-main">
          ${renderTopbar()}
          <main class="workspace">
            ${state.ui.loading ? renderLoading() : renderScreen()}
          </main>
        </div>
        ${renderToast()}
      </div>
      ${renderLoadingOverlay()}
      ${renderFileBrowserModal()}
    `;

    if (!animateScreen) {
      const screenEl = root.querySelector(".screen");
      if (screenEl) screenEl.classList.add("no-animate");
    }

    mountPreviewFrames();
    bindSectionDrag();
    if (state.ui.searchFocus) {
      const search = document.getElementById("experience-search");
      if (search instanceof HTMLInputElement) {
        search.focus();
        search.setSelectionRange(search.value.length, search.value.length);
      }
      state.ui.searchFocus = false;
    }
  }

  function renderSidebar() {
    const summary = state.experienceSummary;
    const items = [
      { id: "dashboard", label: "Dashboard", copy: `${summary.total}개 경험` },
      { id: "experiences", label: "Experiences", copy: `${summary.by_type.work || 0}개 실무` },
      { id: "generate", label: "Generate", copy: "문서 세션 생성" },
      { id: "editor", label: "Editor", copy: "실시간 문서 미리보기" },
      { id: "export", label: "Export", copy: "형식별 내보내기" },
      { id: "settings", label: "Settings", copy: "AI와 기본값 관리" },
    ];
    return `
      <aside class="sidebar">
        <div class="brand">
          <div class="brand-top">
            <div class="brand-mark">DF</div>
            <div class="brand-copy">
              <strong>DevFolio v2</strong>
              <span>portfolio studio</span>
            </div>
          </div>
        </div>
        <div class="nav-group">
          ${items
            .map(
              (item) => `
              <button class="nav-button ${state.ui.screen === item.id ? "active" : ""}" data-screen="${item.id}" type="button">
                <div class="nav-label">
                  <strong>${item.label}</strong>
                  <span>${item.copy}</span>
                </div>
              </button>
            `
            )
            .join("")}
        </div>
        <div class="nav-note">
          <strong>Workspace Status</strong>
          <p>경험 ${summary.total}개 · 문서 연결 ${Object.values(summary.by_document).reduce((total, count) => total + count, 0)}건</p>
          <div class="section-list">
            <span class="badge blue">${summary.by_type.work || 0} 실무</span>
            <span class="badge amber">${summary.by_type.personal || 0} 개인</span>
            <span class="badge green">${summary.by_type.study || 0} 학습</span>
            <span class="badge default">${summary.by_type.toy || 0} 토이</span>
          </div>
        </div>
      </aside>
    `;
  }

  function renderTopbar() {
    const visibleCount = visibleSelectedIds().length;
    const previewLabel = state.currentDoc.preview
      ? `${docLabel(state.currentDoc.docType)} · ${visibleCount}개 경험`
      : "문서 세션 미리보기 없음";
    return `
      <header class="topbar">
        <div class="crumbs">
          <span>DevFolio Studio</span>
          <strong>${screenTitle(state.ui.screen)}</strong>
        </div>
        <div class="topbar-actions">
          <span class="status-pill">${previewLabel}</span>
          <button class="btn btn-secondary" data-action="new-experience" type="button">새 경험</button>
          <button class="btn btn-primary" data-screen="generate" type="button">문서 생성</button>
        </div>
      </header>
    `;
  }

  function screenTitle(screen) {
    const mapping = {
      dashboard: "Dashboard",
      experiences: state.ui.expMode === "list" ? "Experiences" : "Experience Editor",
      generate: "Generate",
      editor: "Editor",
      export: "Export",
      settings: "Settings",
    };
    return mapping[screen] || "Studio";
  }

  function renderLoading() {
    return `
      <section class="screen">
        <div class="hero">
          <div>
            <div class="eyebrow">Loading</div>
            <h2>Studio 데이터를 불러오는 중입니다</h2>
            <p>설정, 저장된 경험, 문서 세션 상태를 정리하고 있습니다.</p>
          </div>
        </div>
        <div class="empty-panel">Loading...</div>
      </section>
    `;
  }

  function renderScreen() {
    switch (state.ui.screen) {
      case "dashboard":
        return renderDashboard();
      case "experiences":
        return state.ui.expMode === "list" ? renderExperiencesList() : renderExperienceEditor();
      case "generate":
        return renderGenerate();
      case "editor":
        return renderEditor();
      case "export":
        return renderExport();
      case "settings":
        return renderSettings();
      default:
        return renderDashboard();
    }
  }

  function renderDashboard() {
    const summary = state.experienceSummary;
    const docsReady = state.experiences.filter((experience) => experience.studio_meta.document_targets.length > 0).length;
    const recent = [...state.experiences]
      .sort((left, right) => right.studio_meta.priority - left.studio_meta.priority)
      .slice(0, 4);
    const actions = buildNextActions();
    return `
      <section class="screen">
        <div class="hero">
          <div>
            <div class="eyebrow">Dashboard</div>
            <h2>경험에서 문서까지 한 번에 이어지는 작업 공간</h2>
            <p>Claude 시안의 워크스페이스 구조를 기준으로 경험 관리, 문서 생성, 편집, 내보내기를 한 흐름으로 정리했습니다.</p>
          </div>
          <div class="hero-actions">
            <button class="btn btn-primary" data-action="new-experience" type="button">새 경험 추가</button>
            <button class="btn btn-secondary" data-screen="generate" type="button">문서 생성 시작</button>
          </div>
        </div>

        <div class="stats-grid">
          ${renderStatCard("전체 경험", summary.total, "등록된 프로젝트와 케이스")}
          ${renderStatCard("실무 경험", summary.by_type.work || 0, "회사 실무 프로젝트")}
          ${renderStatCard("포트폴리오 소재", (summary.by_type.personal || 0) + (summary.by_type.study || 0), "개인/학습 경험")}
          ${renderStatCard("문서 연결", docsReady, "resume / career / portfolio 대상")}
        </div>

        <div class="workspace-split">
          <div class="surface-list">
            <section class="panel">
              <div class="panel-header">
                <div>
                  <div class="eyebrow">Next Actions</div>
                  <h3>지금 이어서 할 작업</h3>
                  <p>현재 저장 상태를 기준으로 다음 액션을 정리했습니다.</p>
                </div>
              </div>
              <div class="list-stack">
                ${actions
                  .map(
                    (action) => `
                    <button class="card-button" data-screen="${action.screen}" ${action.action ? `data-action="${action.action}"` : ""} type="button">
                      <h4>${action.title}</h4>
                      <p>${action.copy}</p>
                    </button>
                  `
                  )
                  .join("")}
              </div>
            </section>
            <section class="panel">
              <div class="panel-header">
                <div>
                  <div class="eyebrow">Recent Experiences</div>
                  <h3>우선순위가 높은 최근 경험</h3>
                  <p>중요도와 문서 연결 상태를 기준으로 바로 편집할 수 있습니다.</p>
                </div>
                <button class="btn btn-ghost" data-screen="experiences" type="button">전체 보기</button>
              </div>
              <div class="cards-grid">
                ${recent.length ? recent.map(renderExperienceDashboardCard).join("") : `<div class="empty-panel">아직 저장된 경험이 없습니다.</div>`}
              </div>
            </section>
          </div>
          <div class="surface-list">
            <section class="panel">
              <div class="panel-header">
                <div>
                  <div class="eyebrow">Document Status</div>
                  <h3>문서 준비 상태</h3>
                  <p>어떤 문서가 얼마나 준비되었는지 빠르게 볼 수 있습니다.</p>
                </div>
              </div>
              <div class="list-stack">
                ${Object.keys(DOC_TYPES)
                  .map(
                    (docType) => `
                    <div class="surface-item">
                      <div class="inline-actions" style="justify-content:space-between;">
                        <strong>${docLabel(docType)}</strong>
                        <span class="badge ${state.experienceSummary.by_document[docType] ? "green" : "default"}">${state.experienceSummary.by_document[docType] || 0}개 연결</span>
                      </div>
                      <p class="mini-copy">${DOC_TYPES[docType].desc}</p>
                    </div>
                  `
                  )
                  .join("")}
              </div>
            </section>
            <section class="panel">
              <div class="panel-header">
                <div>
                  <div class="eyebrow">Current Session</div>
                  <h3>현재 문서 세션</h3>
                </div>
              </div>
              ${
                state.currentDoc.selectedIds.length
                  ? `
                    <div class="surface-item">
                      <strong>${docLabel(state.currentDoc.docType)}</strong>
                      <p>${visibleSelectedIds().length}개 경험 · ${TONES[state.currentDoc.tone]?.label || "톤 미지정"} · 템플릿 ${state.currentDoc.template}</p>
                    </div>
                    <div class="section-list">
                      ${state.currentDoc.selectedIds
                        .map((id) => experienceById(id))
                        .filter(Boolean)
                        .map((experience) => `<span class="chip">${escapeHtml(experience.title)}</span>`)
                        .join("")}
                    </div>
                  `
                  : `<div class="empty-panel">아직 생성된 문서 세션이 없습니다.</div>`
              }
            </section>
          </div>
        </div>
      </section>
    `;
  }

  function buildNextActions() {
    const actions = [];
    if (!state.experiences.length) {
      actions.push({
        title: "첫 경험 추가",
        copy: "회사·개인·학습·토이 경험 중 하나를 등록해 워크스페이스를 시작합니다.",
        screen: "experiences",
        action: "new-experience",
      });
    }
    if (!state.config || !state.config.ai_providers || !state.config.ai_providers.length) {
      actions.push({
        title: "AI Provider 연결",
        copy: "요약 생성과 task bullet 보강을 위해 기본 provider를 먼저 등록합니다.",
        screen: "settings",
      });
    }
    if (state.experiences.length && !state.currentDoc.selectedIds.length) {
      actions.push({
        title: "문서 세션 생성",
        copy: "resume / career / portfolio 중 하나를 선택해 경험 조합을 만듭니다.",
        screen: "generate",
      });
    }
    if (state.currentDoc.selectedIds.length && !state.currentDoc.preview) {
      actions.push({
        title: "편집기에서 문서 검토",
        copy: "선택한 경험 순서와 포함 여부를 조정하면서 실시간 preview를 봅니다.",
        screen: "editor",
      });
    }
    if (!actions.length) {
      actions.push({
        title: "내보내기 준비 완료",
        copy: "현재 세션을 PDF, HTML, DOCX, Markdown 중 필요한 형식으로 출력하세요.",
        screen: "export",
      });
    }
    return actions;
  }

  function renderStatCard(label, value, copy) {
    return `
      <section class="panel stat-card">
        <div>
          <div class="eyebrow">${label}</div>
          <div class="stat-value">${value}</div>
        </div>
        <p class="mini-copy">${copy}</p>
      </section>
    `;
  }

  function renderExperienceDashboardCard(experience) {
    return `
      <button class="experience-card" data-action="edit-experience" data-exp-id="${escapeHtml(experience.id)}" type="button">
        <div class="inline-actions" style="justify-content:space-between;margin-bottom:10px;">
          <span class="badge ${typeAccent(experience.type)}">${typeLabel(experience.type)}</span>
          <span class="mono">${priorityStars(experience.studio_meta.priority)}</span>
        </div>
        <h4>${escapeHtml(experience.title)}</h4>
        <p>${escapeHtml(experience.role || "역할 미정")} · ${escapeHtml(formatPeriod(experience.period))}</p>
        <div class="stack-list" style="margin-top:12px;">
          ${experience.tech_stack.slice(0, 4).map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}
        </div>
      </button>
    `;
  }

  function renderExperiencesList() {
    const filtered = filteredExperiences();
    return `
      <section class="screen">
        <div class="hero">
          <div>
            <div class="eyebrow">Experiences</div>
            <h2>경험 관리</h2>
            <p>저장된 경험을 유형별로 정리하고, 새 시안의 섹션형 편집기로 바로 수정합니다.</p>
          </div>
          <div class="hero-actions">
            <button class="btn btn-primary" data-action="new-experience" type="button">새 경험 추가</button>
          </div>
        </div>

        <div class="filters">
          <div class="tabs">
            <button class="tab ${state.ui.expFilter === "all" ? "active" : ""}" data-exp-filter="all" type="button">전체 ${state.experienceSummary.total}</button>
            ${Object.keys(EXPERIENCE_TYPES)
              .map(
                (type) => `
                <button class="tab ${state.ui.expFilter === type ? "active" : ""}" data-exp-filter="${type}" type="button">
                  ${typeLabel(type)} ${(state.experienceSummary.by_type && state.experienceSummary.by_type[type]) || 0}
                </button>
              `
              )
              .join("")}
          </div>
          <div class="inline-actions">
            <input id="experience-search" class="input search" type="search" placeholder="제목 또는 기술 검색" value="${escapeHtml(state.ui.expSearch)}" />
            <div class="segment">
              <button class="${state.ui.expView === "card" ? "active" : ""}" data-exp-view="card" type="button">Cards</button>
              <button class="${state.ui.expView === "table" ? "active" : ""}" data-exp-view="table" type="button">Table</button>
            </div>
          </div>
        </div>

        ${
          !filtered.length
            ? `<div class="empty-panel">조건에 맞는 경험이 없습니다.</div>`
            : state.ui.expView === "card"
              ? `<div class="cards-grid">${filtered.map(renderExperienceCard).join("")}</div>`
              : renderExperienceTable(filtered)
        }
      </section>
    `;
  }

  function filteredExperiences() {
    return state.experiences.filter((experience) => {
      const typeMatch = state.ui.expFilter === "all" || experience.type === state.ui.expFilter;
      const keyword = state.ui.expSearch.trim().toLowerCase();
      const searchMatch =
        !keyword ||
        experience.title.toLowerCase().includes(keyword) ||
        experience.tech_stack.some((item) => item.toLowerCase().includes(keyword));
      return typeMatch && searchMatch;
    });
  }

  function renderExperienceCard(experience) {
    return `
      <article class="experience-card">
        <div class="inline-actions" style="justify-content:space-between;margin-bottom:12px;">
          <span class="badge ${typeAccent(experience.type)}">${typeLabel(experience.type)}</span>
          <span class="mono">${priorityStars(experience.studio_meta.priority)}</span>
        </div>
        <h4>${escapeHtml(experience.title)}</h4>
        <p>${escapeHtml(experience.organization || "개인")} · ${escapeHtml(experience.role || "역할 미정")} · ${escapeHtml(formatPeriod(experience.period))}</p>
        <div class="stack-list" style="margin-top:12px;">
          ${experience.tech_stack.slice(0, 5).map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}
        </div>
        <div class="section-list" style="margin-top:12px;">
          ${experience.studio_meta.document_targets.length
            ? experience.studio_meta.document_targets.map((docType) => `<span class="badge ${typeAccent(experience.type)}">${docLabel(docType)}</span>`).join("")
            : `<span class="badge default">문서 미연결</span>`}
        </div>
        <div class="toolbar">
          <button class="btn btn-secondary" data-action="edit-experience" data-exp-id="${escapeHtml(experience.id)}" type="button">편집</button>
          <button class="btn btn-ghost" data-action="duplicate-experience" data-exp-id="${escapeHtml(experience.id)}" type="button">복제</button>
          <button class="btn btn-danger" data-action="delete-experience" data-exp-id="${escapeHtml(experience.id)}" type="button">삭제</button>
        </div>
      </article>
    `;
  }

  function renderExperienceTable(experiences) {
    return `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>유형</th>
              <th>경험명</th>
              <th>역할</th>
              <th>기간</th>
              <th>기술</th>
              <th>문서</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${experiences
              .map(
                (experience) => `
                <tr>
                  <td><span class="badge ${typeAccent(experience.type)}">${typeLabel(experience.type)}</span></td>
                  <td><strong>${escapeHtml(experience.title)}</strong></td>
                  <td>${escapeHtml(experience.role || "-")}</td>
                  <td>${escapeHtml(formatPeriod(experience.period))}</td>
                  <td>${escapeHtml(experience.tech_stack.slice(0, 3).join(", ") || "-")}</td>
                  <td>${escapeHtml(experience.studio_meta.document_targets.join(", ") || "-")}</td>
                  <td><button class="btn btn-secondary" data-action="edit-experience" data-exp-id="${escapeHtml(experience.id)}" type="button">편집</button></td>
                </tr>
              `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderExperienceEditor() {
    const form = state.experienceForm;
    return `
      <section class="screen">
        <div class="hero">
          <div>
            <div class="eyebrow">${state.editingExperienceId ? "Edit Experience" : "New Experience"}</div>
            <h2>${state.editingExperienceId ? "경험 편집" : "새 경험 등록"}</h2>
            <p>기존 Compose 흐름을 경험 편집기에 흡수했습니다. 텍스트 intake, Git scan, AI 보강, 저장을 한 화면에서 처리합니다.</p>
          </div>
          <div class="hero-actions">
            <button class="btn btn-secondary" data-action="back-to-list" type="button">목록으로</button>
            <button class="btn btn-secondary" data-action="generate-summary" type="button">요약 생성</button>
            <button class="btn btn-secondary" data-action="generate-task-bullets" type="button">Task 문구 생성</button>
            <button class="btn btn-primary" data-action="save-experience" type="button">저장</button>
          </div>
        </div>

        <div class="form-layout">
          <aside class="form-sidebar">
            <section class="panel panel-tight">
              <div class="eyebrow">Sections</div>
              <div class="form-nav">
                ${renderFormSectionButton("intake", "Import / Intake")}
                ${renderFormSectionButton("basics", "Basics")}
                ${renderFormSectionButton("story", "Narrative")}
                ${renderFormSectionButton("work", "Tasks & Tech")}
                ${renderFormSectionButton("links", "Links & Delivery")}
              </div>
            </section>
            <section class="panel panel-tight">
              <div class="eyebrow">Current Draft</div>
              <div class="list-stack">
                <div class="surface-item">
                  <strong>${escapeHtml(form.title || "제목 없음")}</strong>
                  <p>${typeLabel(form.type)} · ${escapeHtml(form.role || "역할 미정")}</p>
                </div>
                <div class="surface-item">
                  <strong>문서 대상</strong>
                  <p>${form.studio_meta.document_targets.length ? form.studio_meta.document_targets.map(docLabel).join(", ") : "아직 선택되지 않음"}</p>
                </div>
              </div>
            </section>
          </aside>
          <div class="surface-list">
            <section class="panel">
              <form id="experience-editor">
                ${renderExperienceEditorSection(form)}
              </form>
            </section>
          </div>
        </div>
      </section>
    `;
  }

  function renderFormSectionButton(id, label) {
    return `
      <button class="${state.ui.formSection === id ? "active" : ""}" data-form-section="${id}" type="button">${label}</button>
    `;
  }

  function renderExperienceEditorSection(form) {
    switch (state.ui.formSection) {
      case "intake":
        return renderExperienceIntakeSection(form);
      case "basics":
        return renderExperienceBasicsSection(form);
      case "story":
        return renderExperienceStorySection(form);
      case "work":
        return renderExperienceWorkSection(form);
      case "links":
        return renderExperienceLinksSection(form);
      default:
        return renderExperienceBasicsSection(form);
    }
  }

  function renderExperienceIntakeSection(form) {
    return `
      <div class="section-block">
        <div class="eyebrow">Import / Intake</div>
        <h3>원본에서 경험 초안 채우기</h3>
        <p>붙여넣은 설명을 구조화하거나 Git 저장소를 읽어 초안을 바로 채웁니다.</p>
        <div class="grid-2">
          <div class="panel panel-tight">
            <div class="eyebrow">Text Intake</div>
            <div class="field-stack">
              <span>원본 설명</span>
              <textarea class="textarea" name="raw_text" placeholder="프로젝트 소개, 역할, 문제, 해결 내용 등을 자유롭게 붙여넣으세요.">${escapeHtml(form.raw_text)}</textarea>
            </div>
            <div class="toolbar">
              <button class="btn btn-primary" data-action="import-text" type="button">텍스트로 초안 생성</button>
            </div>
          </div>
          <div class="panel panel-tight">
            <div class="eyebrow">Git Scan</div>
            <div class="field-stack">
              <span>저장소 경로</span>
              <div class="input-with-action">
                <input id="scan-repo-path" class="input" type="text" value="${escapeHtml(state.importer.repoPath)}" placeholder="/Users/you/projects/my-repo" />
                <button class="btn btn-secondary" data-action="open-file-browser" data-target="scan-repo-path" type="button">찾아보기</button>
              </div>
            </div>
            <div class="field-grid" style="margin-top:12px;">
              <div class="field">
                <span>작성자 이메일</span>
                <input id="scan-author-email" class="input" type="email" value="${escapeHtml(state.importer.authorEmail)}" placeholder="you@example.com" />
              </div>
              <label class="field">
                <span>AI 분석 포함</span>
                <input id="scan-analyze" type="checkbox"${checked(state.importer.analyze)} />
              </label>
            </div>
            <div class="toolbar">
              <button class="btn btn-primary" data-action="import-scan" type="button">Git 스캔 불러오기</button>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderExperienceBasicsSection(form) {
    return `
      <div class="section-block">
        <div class="eyebrow">Basics</div>
        <h3>경험의 기본 정보</h3>
        <p>문서에서 가장 먼저 읽히는 제목, 역할, 기간, 중요도, 문서 연결 대상을 정리합니다.</p>
        <div class="field-grid wide-3">
          <label class="field">
            <span>경험 유형</span>
            <select class="select" name="type">
              ${Object.keys(EXPERIENCE_TYPES)
                .map((type) => `<option value="${type}"${selected(form.type === type)}>${typeLabel(type)}</option>`)
                .join("")}
            </select>
          </label>
          <label class="field">
            <span>상태</span>
            <select class="select" name="status">
              <option value="done"${selected(form.status === "done")}>완료</option>
              <option value="in_progress"${selected(form.status === "in_progress")}>진행 중</option>
              <option value="planned"${selected(form.status === "planned")}>계획</option>
            </select>
          </label>
          <label class="field">
            <span>중요도</span>
            <input class="input" name="priority" type="number" min="1" max="5" value="${escapeHtml(form.studio_meta.priority)}" />
          </label>
        </div>
        <div class="field-grid" style="margin-top:14px;">
          <label class="field">
            <span>경험명</span>
            <input class="input" name="title" type="text" value="${escapeHtml(form.title)}" placeholder="결제 시스템 MSA 전환" />
          </label>
          <label class="field">
            <span>소속 / 주관</span>
            <input class="input" name="organization" type="text" value="${escapeHtml(form.organization)}" placeholder="회사명 또는 개인 프로젝트" />
          </label>
          <label class="field">
            <span>역할</span>
            <input class="input" name="role" type="text" value="${escapeHtml(form.role)}" placeholder="백엔드 엔지니어" />
          </label>
          <label class="field">
            <span>팀 규모</span>
            <input class="input" name="team_size" type="number" min="1" max="50" value="${escapeHtml(form.team_size)}" />
          </label>
          <label class="field">
            <span>시작 월</span>
            <input class="input" name="period_start" type="month" value="${escapeHtml(form.period.start)}" />
          </label>
          <label class="field">
            <span>종료 월</span>
            <input class="input" name="period_end" type="month" value="${escapeHtml(form.period.end)}" />
          </label>
        </div>
        <div class="field-grid" style="margin-top:14px;">
          <label class="field">
            <span>협업 프로젝트</span>
            <input name="collaboration" type="checkbox"${checked(form.studio_meta.collaboration)} />
          </label>
        </div>
        <div class="section-block">
          <div class="eyebrow">Document Targets</div>
          <div class="section-list">
            ${Object.keys(DOC_TYPES)
              .map(
                (docType) => `
                <label class="chip">
                  <input name="document_target" type="checkbox" value="${docType}"${checked(form.studio_meta.document_targets.includes(docType))} />
                  ${docLabel(docType)}
                </label>
              `
              )
              .join("")}
          </div>
        </div>
      </div>
    `;
  }

  function renderExperienceStorySection(form) {
    return `
      <div class="section-block">
        <div class="eyebrow">Narrative</div>
        <h3>문제 맥락과 프로젝트 설명</h3>
        <p>한 줄 소개, 요약, 배경, 문제 정의, 목표를 문장으로 정리합니다.</p>
        <div class="field-stack">
          <span>한 줄 소개</span>
          <input class="input" name="one_line_summary" type="text" value="${escapeHtml(form.one_line_summary)}" placeholder="사용자와 운영 흐름을 한 문장으로 설명" />
        </div>
        <div class="field-stack" style="margin-top:14px;">
          <span>프로젝트 요약</span>
          <textarea class="textarea" name="summary" placeholder="프로젝트를 3~5문장으로 설명하세요.">${escapeHtml(form.summary)}</textarea>
        </div>
        <div class="field-grid" style="margin-top:14px;">
          <label class="field">
            <span>배경</span>
            <textarea class="textarea" name="overview_background" placeholder="왜 만들었는지">${escapeHtml(form.overview.background)}</textarea>
          </label>
          <label class="field">
            <span>핵심 문제</span>
            <textarea class="textarea" name="overview_problem" placeholder="어떤 문제가 있었는지">${escapeHtml(form.overview.problem)}</textarea>
          </label>
          <label class="field">
            <span>대상 사용자</span>
            <textarea class="textarea" name="overview_target_users" placeholder="예: 운영자, 내부 개발자, 최종 사용자">${escapeHtml(form.overview.target_users.join("\n"))}</textarea>
          </label>
          <label class="field">
            <span>목표</span>
            <textarea class="textarea" name="overview_goals" placeholder="예: 응답 시간 단축, 운영 효율 개선">${escapeHtml(form.overview.goals.join("\n"))}</textarea>
          </label>
          <label class="field">
            <span>비범위</span>
            <textarea class="textarea" name="overview_non_goals" placeholder="이번 범위에서 제외한 것">${escapeHtml(form.overview.non_goals.join("\n"))}</textarea>
          </label>
        </div>
      </div>
    `;
  }

  function renderExperienceWorkSection(form) {
    return `
      <div class="section-block">
        <div class="eyebrow">Tasks & Tech</div>
        <h3>기술 스택과 작업 단위</h3>
        <p>여기서 task bullet 생성 결과를 다듬으면 문서 미리보기의 품질이 바로 올라갑니다.</p>
        <div class="field-stack">
          <span>기술 스택</span>
          <textarea class="textarea" name="tech_stack" placeholder="기술명을 줄바꿈 또는 콤마로 입력">${escapeHtml(form.tech_stack.join("\n"))}</textarea>
        </div>
        <div class="section-block">
          <div class="panel-header">
            <div>
              <div class="eyebrow">Tasks</div>
              <h4>세부 작업</h4>
            </div>
            <button class="btn btn-secondary" data-action="add-task" type="button">Task 추가</button>
          </div>
          <div class="surface-list">
            ${form.tasks.map((task, index) => renderTaskEditor(task, index)).join("")}
          </div>
        </div>
      </div>
    `;
  }

  function renderTaskEditor(task, index) {
    return `
      <article class="panel panel-tight" data-task-row data-task-id="${escapeHtml(task.id)}">
        <div class="panel-header">
          <div>
            <div class="eyebrow">Task ${index + 1}</div>
            <h4>${escapeHtml(task.name || "새 작업")}</h4>
          </div>
          <button class="btn btn-danger" data-action="remove-task" data-task-index="${index}" type="button">삭제</button>
        </div>
        <div class="field-grid wide-3">
          <label class="field">
            <span>작업명</span>
            <input class="input" name="task_name" type="text" value="${escapeHtml(task.name)}" />
          </label>
          <label class="field">
            <span>시작 월</span>
            <input class="input" name="task_period_start" type="month" value="${escapeHtml(task.period.start)}" />
          </label>
          <label class="field">
            <span>종료 월</span>
            <input class="input" name="task_period_end" type="month" value="${escapeHtml(task.period.end)}" />
          </label>
        </div>
        <div class="field-grid" style="margin-top:14px;">
          <label class="field">
            <span>문제</span>
            <textarea class="textarea" name="task_problem">${escapeHtml(task.problem)}</textarea>
          </label>
          <label class="field">
            <span>해결</span>
            <textarea class="textarea" name="task_solution">${escapeHtml(task.solution)}</textarea>
          </label>
          <label class="field">
            <span>결과</span>
            <textarea class="textarea" name="task_result">${escapeHtml(task.result)}</textarea>
          </label>
          <label class="field">
            <span>사용 기술</span>
            <textarea class="textarea" name="task_tech_used">${escapeHtml(task.tech_used.join("\n"))}</textarea>
          </label>
          <label class="field">
            <span>키워드</span>
            <textarea class="textarea" name="task_keywords">${escapeHtml(task.keywords.join("\n"))}</textarea>
          </label>
        </div>
      </article>
    `;
  }

  function renderExperienceLinksSection(form) {
    return `
      <div class="section-block">
        <div class="eyebrow">Links & Delivery</div>
        <h3>링크, 태그, 문서 대상</h3>
        <p>canonical 링크와 임의 링크를 함께 저장하고, 문서 대상과 중요도를 마무리합니다.</p>
        <div class="field-grid">
          <label class="field">
            <span>GitHub</span>
            <input class="input" name="link_github" type="url" value="${escapeHtml(form.links.github)}" />
          </label>
          <label class="field">
            <span>Demo</span>
            <input class="input" name="link_demo" type="url" value="${escapeHtml(form.links.demo)}" />
          </label>
          <label class="field">
            <span>Docs</span>
            <input class="input" name="link_docs" type="url" value="${escapeHtml(form.links.docs)}" />
          </label>
          <label class="field">
            <span>Video</span>
            <input class="input" name="link_video" type="url" value="${escapeHtml(form.links.video)}" />
          </label>
        </div>

        <div class="section-block">
          <div class="panel-header">
            <div>
              <div class="eyebrow">Extra Links</div>
              <h4>추가 링크</h4>
            </div>
            <button class="btn btn-secondary" data-action="add-extra-link" type="button">링크 추가</button>
          </div>
          <div class="surface-list" data-extra-link-anchor>
            ${form.studio_meta.extra_links.map((link, index) => renderExtraLinkRow(link, index)).join("") || `<div class="empty-panel">추가 링크가 없습니다.</div>`}
          </div>
        </div>

        <div class="field-grid" style="margin-top:14px;">
          <label class="field">
            <span>태그</span>
            <textarea class="textarea" name="tags">${escapeHtml(form.tags.join("\n"))}</textarea>
          </label>
          <label class="field">
            <span>원본 메모</span>
            <textarea class="textarea" name="raw_text">${escapeHtml(form.raw_text)}</textarea>
          </label>
        </div>
      </div>
    `;
  }

  function renderExtraLinkRow(link, index) {
    return `
      <article class="panel panel-tight" data-extra-link-row>
        <div class="field-grid">
          <label class="field">
            <span>라벨</span>
            <input class="input" name="extra_link_label" type="text" value="${escapeHtml(link.label)}" />
          </label>
          <label class="field">
            <span>URL</span>
            <input class="input" name="extra_link_url" type="url" value="${escapeHtml(link.url)}" />
          </label>
        </div>
        <div class="toolbar">
          <button class="btn btn-danger" data-action="remove-extra-link" data-link-index="${index}" type="button">삭제</button>
        </div>
      </article>
    `;
  }

  function renderGenerate() {
    const filtered = state.experiences.filter((experience) => state.generate.filter === "all" || experience.type === state.generate.filter);
    const steps = ["문서 종류", "경험 선택", "톤 선택", "생성 완료"];
    return `
      <section class="screen">
        <div class="hero">
          <div>
            <div class="eyebrow">Generate</div>
            <h2>문서 세션 생성</h2>
            <p>resume / career / portfolio 중 하나를 선택하고 포함할 경험과 톤을 정하면 편집기로 이어집니다.</p>
          </div>
        </div>

        <div class="panel">
          <div class="wizard-stepper">
            ${steps
              .map(
                (label, index) => `
                <div class="step ${state.generate.step === index ? "active" : ""} ${state.generate.step > index ? "done" : ""}">
                  <button class="step-dot" data-action="pick-generate-step" data-step="${index}" type="button">${index + 1}</button>
                  <span>${label}</span>
                  ${index < steps.length - 1 ? `<div class="step-line"></div>` : ""}
                </div>
              `
              )
              .join("")}
          </div>
          ${renderGenerateStep(filtered)}
        </div>
      </section>
    `;
  }

  function renderGenerateStep(filtered) {
    if (state.generate.step === 0) {
      return `
        <div class="section-block">
          <div class="doc-grid">
            ${Object.keys(DOC_TYPES)
              .map(
                (docType) => `
                <button class="doc-card ${state.generate.docType === docType ? "active" : ""}" data-doc-type="${docType}" type="button">
                  <div class="eyebrow">${DOC_TYPES[docType].short}</div>
                  <h4>${docLabel(docType)}</h4>
                  <p>${DOC_TYPES[docType].desc}</p>
                </button>
              `
              )
              .join("")}
          </div>
          <div class="toolbar" style="justify-content:flex-end;">
            <button class="btn btn-primary" data-action="generate-next" type="button">다음</button>
          </div>
        </div>
      `;
    }
    if (state.generate.step === 1) {
      return `
        <div class="section-block">
          <div class="filters">
            <div class="tabs">
              <button class="tab ${state.generate.filter === "all" ? "active" : ""}" data-generate-filter="all" type="button">전체</button>
              ${Object.keys(EXPERIENCE_TYPES)
                .map(
                  (type) => `
                  <button class="tab ${state.generate.filter === type ? "active" : ""}" data-generate-filter="${type}" type="button">${typeLabel(type)}</button>
                `
                )
                .join("")}
            </div>
            ${state.generate.docType ? `<button class="btn btn-ghost" data-action="select-targeted-experiences" type="button">${docLabel(state.generate.docType)} 추천 선택</button>` : ""}
          </div>
          <div class="list-stack">
            ${filtered
              .map((experience) => {
                const active = state.generate.selectedIds.includes(experience.id);
                return `
                  <button class="check-row ${active ? "active" : ""}" data-action="toggle-generate-selection" data-exp-id="${escapeHtml(experience.id)}" type="button">
                    <div class="inline-actions" style="justify-content:space-between;width:100%;">
                      <div>
                        <div class="inline-actions">
                          <span class="badge ${typeAccent(experience.type)}">${typeLabel(experience.type)}</span>
                          <strong>${escapeHtml(experience.title)}</strong>
                        </div>
                        <p class="mini-copy">${escapeHtml(experience.role || "역할 미정")} · ${escapeHtml(formatPeriod(experience.period))}</p>
                      </div>
                      <span class="badge ${active ? "amber" : "default"}">${active ? "선택됨" : "미선택"}</span>
                    </div>
                  </button>
                `;
              })
              .join("")}
          </div>
          <div class="toolbar" style="justify-content:space-between;">
            <button class="btn btn-ghost" data-action="generate-prev" type="button">이전</button>
            <button class="btn btn-primary" data-action="generate-next" type="button">다음</button>
          </div>
        </div>
      `;
    }
    if (state.generate.step === 2) {
      return `
        <div class="section-block">
          <div class="tone-grid">
            ${Object.keys(TONES)
              .map(
                (tone) => `
                <button class="tone-card ${state.generate.tone === tone ? "active" : ""}" data-tone="${tone}" type="button">
                  <div class="eyebrow">${tone.toUpperCase()}</div>
                  <h4>${TONES[tone].label}</h4>
                  <p>${TONES[tone].desc}</p>
                </button>
              `
              )
              .join("")}
          </div>
          <div class="toolbar" style="justify-content:space-between;">
            <button class="btn btn-ghost" data-action="generate-prev" type="button">이전</button>
            <button class="btn btn-primary" data-action="generate-next" type="button">${state.generate.busy ? "생성 중..." : "문서 세션 생성"}</button>
          </div>
        </div>
      `;
    }
    return `
      <div class="section-block">
        <div class="empty-panel">
          <div>
            <h3>${docLabel(state.currentDoc.docType)} 세션 생성 완료</h3>
            <p>${visibleSelectedIds().length}개 경험 · ${TONES[state.currentDoc.tone]?.label || ""} · 템플릿 ${state.currentDoc.template}</p>
            <div class="toolbar" style="justify-content:center;">
              <button class="btn btn-primary" data-action="open-editor" type="button">편집기 열기</button>
              <button class="btn btn-secondary" data-action="open-export" type="button">내보내기</button>
              <button class="btn btn-ghost" data-action="reset-generate" type="button">새 문서 생성</button>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderEditor() {
    const selectedExperiences = state.currentDoc.selectedIds.map(experienceById).filter(Boolean);
    return `
      <section class="screen">
        <div class="hero">
          <div>
            <div class="eyebrow">Editor</div>
            <h2>문서 편집기</h2>
            <p>왼쪽 레일에서 경험 순서와 포함 여부를 조정하면 저장된 경험 기준으로 preview가 갱신됩니다.</p>
          </div>
          <div class="hero-actions">
            <button class="btn btn-secondary" data-screen="generate" type="button">세션 다시 구성</button>
            <button class="btn btn-primary" data-action="refresh-preview" type="button">미리보기 새로고침</button>
          </div>
        </div>
        <div class="editor-grid">
          <aside class="section-rail">
            <section class="panel">
              <div class="panel-header">
                <div>
                  <div class="eyebrow">Sections</div>
                  <h3>경험 섹션</h3>
                  <p>드래그로 순서를 바꾸고 표시 여부를 조정합니다.</p>
                </div>
              </div>
              ${
                selectedExperiences.length
                  ? `
                    <div class="surface-list">
                      <div class="surface-item">
                        <strong>고정 블록</strong>
                        <p>프로필 / 요약은 템플릿에 따라 유지됩니다.</p>
                      </div>
                      ${selectedExperiences.map(renderSectionRow).join("")}
                    </div>
                  `
                  : `<div class="empty-panel">먼저 Generate에서 문서 세션을 만드세요.</div>`
              }
            </section>
          </aside>
          <section class="panel preview-panel">
            <div class="panel-header">
              <div>
                <div class="eyebrow">Preview</div>
                <h3>${docLabel(state.currentDoc.docType)}</h3>
                <p>${TONES[state.currentDoc.tone]?.label || "톤 없음"} · visible ${visibleSelectedIds().length}개 경험</p>
              </div>
              <div class="inline-actions">
                ${renderDocTypeSegment("use-doc-type", state.currentDoc.docType)}
              </div>
            </div>
            ${renderPreviewSurface()}
          </section>
        </div>
      </section>
    `;
  }

  function renderSectionRow(experience) {
    const hidden = state.currentDoc.hiddenIds.includes(experience.id);
    return `
      <div class="section-row" draggable="true" data-section-id="${escapeHtml(experience.id)}" data-hidden="${hidden ? "true" : "false"}">
        <div class="section-meta">
          <span class="badge ${typeAccent(experience.type)}">${typeLabel(experience.type)}</span>
          <div>
            <strong>${escapeHtml(experience.title)}</strong>
            <div class="mini-copy">${escapeHtml(experience.role || "역할 미정")}</div>
          </div>
        </div>
        <label class="toggle">
          <input type="checkbox" ${checked(!hidden)} data-action="toggle-section-visibility" data-exp-id="${escapeHtml(experience.id)}" />
          표시
        </label>
      </div>
    `;
  }

  function renderExport() {
    const availableFormats = state.currentDoc.docType === "portfolio"
      ? ["md", "html", "pdf", "csv"]
      : ["md", "html", "pdf", "docx", "json", "csv"];
    const availableTemplates = state.currentDoc.docType === "resume"
      ? ["default", "compact", "achievement"]
      : ["default", "compact"];
    return `
      <section class="screen">
        <div class="hero">
          <div>
            <div class="eyebrow">Export</div>
            <h2>문서 내보내기</h2>
            <p>세션에 포함된 경험과 현재 template/format 조합으로 최종 문서를 출력합니다.</p>
          </div>
          <div class="hero-actions">
            <button class="btn btn-secondary" data-screen="editor" type="button">편집기로 이동</button>
            <button class="btn btn-primary" data-action="export-document" type="button">문서 내보내기</button>
          </div>
        </div>
        <div class="export-grid">
          <aside class="surface-list">
            <section class="panel">
              <div class="panel-header">
                <div>
                  <div class="eyebrow">Document Setup</div>
                  <h3>문서 설정</h3>
                </div>
              </div>
              <div class="section-block">
                <div class="eyebrow">Doc Type</div>
                ${renderDocTypeSegment("use-doc-type", state.currentDoc.docType)}
              </div>
              <div class="section-block">
                <div class="eyebrow">Template</div>
                <div class="surface-list">
                  ${availableTemplates
                    .map(
                      (template) => `
                      <button class="format-row ${state.currentDoc.template === template ? "active" : ""}" data-action="use-template" data-value="${template}" type="button">
                        <strong>${template}</strong>
                        <span class="mini-copy">${template === "compact" && state.currentDoc.docType === "career" ? "career_default 로 폴백" : "선택된 템플릿"}</span>
                      </button>
                    `
                    )
                    .join("")}
                </div>
              </div>
              <div class="section-block">
                <div class="eyebrow">Format</div>
                <div class="surface-list">
                  ${availableFormats
                    .map(
                      (format) => `
                      <button class="format-row ${state.currentDoc.format === format ? "active" : ""}" data-action="use-format" data-value="${format}" type="button">
                        <strong>${format.toUpperCase()}</strong>
                      </button>
                    `
                    )
                    .join("")}
                </div>
              </div>
              ${
                state.currentDoc.lastExport
                  ? `
                    <div class="section-block">
                      <div class="eyebrow">Last Export</div>
                      <div class="surface-item">
                        <strong>${escapeHtml(state.currentDoc.lastExport.path || "")}</strong>
                        <p>${escapeHtml(state.currentDoc.lastExport.folder || "")}</p>
                      </div>
                      <div class="toolbar">
                        <button class="btn btn-secondary" data-action="open-folder" type="button">폴더 열기</button>
                      </div>
                    </div>
                  `
                  : ""
              }
            </section>
          </aside>
          <section class="panel preview-panel">
            <div class="panel-header">
              <div>
                <div class="eyebrow">Rendered Output</div>
                <h3>Export Preview</h3>
                <p>${visibleSelectedIds().length}개 경험이 포함됩니다.</p>
              </div>
              <button class="btn btn-secondary" data-action="refresh-preview" type="button">미리보기 갱신</button>
            </div>
            ${renderPreviewSurface()}
          </section>
        </div>
      </section>
    `;
  }

  function renderDocTypeSegment(action, current) {
    return `
      <div class="segment">
        ${Object.keys(DOC_TYPES)
          .map(
            (docType) => `
            <button class="${current === docType ? "active" : ""}" data-action="${action}" data-value="${docType}" type="button">${docLabel(docType)}</button>
          `
          )
          .join("")}
      </div>
    `;
  }

  function renderPreviewSurface() {
    if (!state.currentDoc.selectedIds.length) {
      return `<div class="empty-panel">선택된 경험이 없습니다. Generate 화면에서 문서 세션을 먼저 만드세요.</div>`;
    }
    if (!state.currentDoc.preview) {
      return `<div class="empty-panel">미리보기가 아직 없습니다. 갱신 버튼을 눌러 preview를 생성하세요.</div>`;
    }
    return `<iframe class="preview-frame" data-preview-frame="current"></iframe>`;
  }

  function mountPreviewFrames() {
    const frames = root.querySelectorAll("[data-preview-frame]");
    frames.forEach((frame) => {
      if (frame instanceof HTMLIFrameElement) {
        frame.srcdoc = (state.currentDoc.preview && state.currentDoc.preview.full_html) || "";
      }
    });
  }

  function bindSectionDrag() {
    const rows = Array.from(root.querySelectorAll("[data-section-id]"));
    rows.forEach((row) => {
      row.addEventListener("dragstart", () => {
        dragSectionId = row.getAttribute("data-section-id") || "";
      });
      row.addEventListener("dragover", (event) => {
        event.preventDefault();
      });
      row.addEventListener("drop", (event) => {
        event.preventDefault();
        const targetId = row.getAttribute("data-section-id") || "";
        if (!dragSectionId || !targetId || dragSectionId === targetId) {
          dragSectionId = "";
          return;
        }
        const order = [...state.currentDoc.selectedIds];
        const fromIndex = order.indexOf(dragSectionId);
        const toIndex = order.indexOf(targetId);
        if (fromIndex < 0 || toIndex < 0) {
          dragSectionId = "";
          return;
        }
        const [moved] = order.splice(fromIndex, 1);
        order.splice(toIndex, 0, moved);
        state.currentDoc.selectedIds = order;
        dragSectionId = "";
        render();
        queuePreview();
      });
      row.addEventListener("dragend", () => {
        dragSectionId = "";
      });
    });
  }

  function renderSettings() {
    return `
      <section class="screen">
        <div class="hero">
          <div>
            <div class="eyebrow">Settings</div>
            <h2>설정</h2>
            <p>프로필, AI provider, export 기본값, reasoning 전략을 시안 스타일에 맞게 재배치했습니다.</p>
          </div>
        </div>
        <div class="settings-grid">
          <aside class="settings-nav">
            ${Object.keys(SETTINGS_TABS)
              .map(
                (tab) => `
                <button class="nav-button ${state.ui.settingsTab === tab ? "active" : ""}" data-tab="${tab}" type="button">
                  <div class="nav-label">
                    <strong>${SETTINGS_TABS[tab].label}</strong>
                    <span>${SETTINGS_TABS[tab].desc}</span>
                  </div>
                </button>
              `
              )
              .join("")}
          </aside>
          <div class="settings-body">
            ${renderSettingsPanel()}
          </div>
        </div>
      </section>
    `;
  }

  function renderSettingsPanel() {
    switch (state.ui.settingsTab) {
      case "profile":
        return renderProfileSettings();
      case "ai":
        return renderAISettings();
      case "export":
        return renderExportSettings();
      case "general":
        return renderGeneralSettings();
      case "logs":
        return renderLogsSettings();
      default:
        return renderProfileSettings();
    }
  }

  function renderProfileSettings() {
    const user = state.config?.user || {};
    return `
      <section class="panel">
        <div class="panel-header">
          <div>
            <div class="eyebrow">Profile</div>
            <h3>문서 프로필</h3>
            <p>이력서와 경력기술서 상단에 쓰이는 기본 정보입니다.</p>
          </div>
        </div>
        <form id="settings-profile-form" class="surface-list">
          <div class="field-grid">
            <label class="field">
              <span>이름</span>
              <input class="input" name="name" type="text" value="${escapeHtml(user.name || "")}" />
            </label>
            <label class="field">
              <span>이메일</span>
              <input class="input" name="email" type="email" value="${escapeHtml(user.email || "")}" />
            </label>
            <label class="field">
              <span>GitHub</span>
              <input class="input" name="github" type="text" value="${escapeHtml(user.github || "")}" />
            </label>
            <label class="field">
              <span>Blog</span>
              <input class="input" name="blog" type="text" value="${escapeHtml(user.blog || "")}" />
            </label>
          </div>
          <div class="toolbar">
            <button class="btn btn-primary" type="submit">저장</button>
          </div>
        </form>
      </section>
    `;
  }

  function renderAISettings() {
    const providers = state.config?.ai_providers || [];
    return `
      <section class="panel">
        <div class="panel-header">
          <div>
            <div class="eyebrow">AI Providers</div>
            <h3>연결된 Provider</h3>
            <p>기본 provider는 General 탭에서 선택합니다.</p>
          </div>
        </div>
        <div class="surface-list">
          ${providers.length
            ? providers
                .map(
                  (provider) => `
                  <div class="provider-row ${provider.is_default ? "active" : ""}">
                    <div>
                      <strong>${escapeHtml(provider.name)}</strong>
                      <p class="mini-copy">${escapeHtml(provider.display_model || provider.model || "")}</p>
                      <p class="mini-copy">generation: ${escapeHtml(provider.generation_model || "")} · ${escapeHtml(provider.generation_status || "")}</p>
                    </div>
                    <div class="inline-actions">
                      <button class="btn btn-secondary" data-action="test-provider" data-provider-name="${escapeHtml(provider.name)}" type="button">Test</button>
                      <button class="btn btn-danger" data-action="remove-provider" data-provider-name="${escapeHtml(provider.name)}" type="button">Delete</button>
                    </div>
                  </div>
                `
                )
                .join("")
            : `<div class="empty-panel">등록된 AI Provider가 없습니다.</div>`}
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">
          <div>
            <div class="eyebrow">Add / Update</div>
            <h3>Provider 등록</h3>
          </div>
        </div>
        <form id="settings-ai-form" class="surface-list">
          <div class="field-grid">
            <label class="field">
              <span>Provider</span>
              <select class="select" name="provider_name">
                ${COMMON_PROVIDERS.map((provider) => `<option value="${provider}">${provider}</option>`).join("")}
              </select>
            </label>
            <label class="field">
              <span>Model</span>
              <input class="input" name="provider_model" type="text" placeholder="비워두면 기본 모델" />
            </label>
            <label class="field">
              <span>API Key</span>
              <input class="input" name="provider_api_key" type="password" placeholder="선택 입력" />
            </label>
            <label class="field">
              <span>Base URL</span>
              <input class="input" name="provider_base_url" type="url" placeholder="Ollama 등 커스텀 엔드포인트" />
            </label>
          </div>
          <div class="toolbar">
            <button class="btn btn-primary" type="submit">Provider 저장</button>
          </div>
        </form>
      </section>
    `;
  }

  function renderExportSettings() {
    const exportConfig = state.config?.export || {};
    return `
      <section class="panel">
        <div class="panel-header">
          <div>
            <div class="eyebrow">Export Defaults</div>
            <h3>기본 출력 설정</h3>
          </div>
        </div>
        <form id="settings-export-form" class="surface-list">
          <div class="field-grid">
            <label class="field">
              <span>기본 포맷</span>
              <select class="select" name="default_format">
                ${["md", "html", "pdf", "docx", "json", "csv"].map((format) => `<option value="${format}"${selected(exportConfig.default_format === format)}>${format}</option>`).join("")}
              </select>
            </label>
            <label class="field">
              <span>기본 템플릿</span>
              <select class="select" name="default_template">
                ${["default", "compact", "achievement"].map((template) => `<option value="${template}"${selected(exportConfig.default_template === template)}>${template}</option>`).join("")}
              </select>
            </label>
            <label class="field" style="grid-column:1 / -1;">
              <span>출력 경로</span>
              <input class="input" name="output_dir" type="text" value="${escapeHtml(exportConfig.output_dir || "")}" placeholder="비워두면 기본 exports 디렉터리" />
            </label>
          </div>
          <div class="toolbar">
            <button class="btn btn-primary" type="submit">저장</button>
          </div>
        </form>
      </section>
    `;
  }

  function renderGeneralSettings() {
    const general = state.config?.general || {};
    const providers = state.config?.ai_providers || [];
    return `
      <section class="panel">
        <div class="panel-header">
          <div>
            <div class="eyebrow">General</div>
            <h3>언어, 타임존, reasoning</h3>
          </div>
        </div>
        <form id="settings-general-form" class="surface-list">
          <div class="field-grid">
            <label class="field">
              <span>기본 언어</span>
              <select class="select" name="default_language">
                ${["ko", "en", "both"].map((value) => `<option value="${value}"${selected(general.default_language === value)}>${value}</option>`).join("")}
              </select>
            </label>
            <label class="field">
              <span>타임존</span>
              <input class="input" name="timezone" type="text" value="${escapeHtml(general.timezone || "Asia/Seoul")}" />
            </label>
            <label class="field">
              <span>기본 AI Provider</span>
              <select class="select" name="default_ai_provider">
                <option value="">선택 안 함</option>
                ${providers.map((provider) => `<option value="${provider.name}"${selected(general.default_ai_provider === provider.name)}>${provider.name}</option>`).join("")}
              </select>
            </label>
            <label class="field">
              <span>Reasoning Strategy</span>
              <select class="select" name="reasoning_strategy">
                <option value="single"${selected(general.reasoning_strategy === "single")}>single</option>
                <option value="best_of_n"${selected(general.reasoning_strategy === "best_of_n")}>best_of_n</option>
              </select>
            </label>
            <label class="field">
              <span>Reasoning Samples</span>
              <input class="input" name="reasoning_samples" type="number" min="1" max="5" value="${escapeHtml(general.reasoning_samples || 1)}" />
            </label>
            <label class="field">
              <span>Judge Provider</span>
              <select class="select" name="judge_provider">
                <option value="">선택 안 함</option>
                ${providers.map((provider) => `<option value="${provider.name}"${selected(general.judge_provider === provider.name)}>${provider.name}</option>`).join("")}
              </select>
            </label>
          </div>
          <div class="toolbar">
            <button class="btn btn-primary" type="submit">저장</button>
          </div>
        </form>
      </section>
    `;
  }

  function renderLogsSettings() {
    const entries = state.ui.logs || [];
    return `
      <section class="panel">
        <div class="panel-header">
          <div>
            <div class="eyebrow">AI Logs</div>
            <h3>요청·응답 기록</h3>
          </div>
          <div class="toolbar">
            <button class="btn btn-secondary" data-action="refresh-ai-logs" type="button">${state.ui.logsLoading ? "로딩 중..." : "새로 고침"}</button>
            <button class="btn btn-danger" data-action="clear-ai-logs" type="button">전체 삭제</button>
          </div>
        </div>
        <div class="surface-list">
          ${entries.length === 0
            ? `<div class="empty-state"><p>${state.ui.logsLoading ? "로딩 중..." : "기록이 없습니다."}</p></div>`
            : entries.map((entry) => renderLogEntry(entry)).join("")}
        </div>
      </section>
    `;
  }

  function renderLogEntry(entry) {
    const ts = entry.ts ? new Date(entry.ts).toLocaleString("ko-KR") : "";
    const isCall = entry.op === "call";
    const statusClass = entry.ok === false ? "tone-error" : entry.ok === true ? "tone-ok" : "tone-warn";
    const statusLabel = entry.ok === false ? "실패" : entry.ok === true ? "성공" : entry.level || "INFO";
    const details = isCall
      ? `<span class="log-meta">${escapeHtml(entry.provider || "")} / ${escapeHtml(entry.model || "")} · ${entry.duration_ms || 0}ms · 입력 ${entry.prompt_chars || 0}자 · 출력 ${entry.response_chars || 0}자</span>`
      : "";
    const preview = isCall
      ? (entry.error ? `<pre class="log-preview error">${escapeHtml(entry.error)}</pre>` : (entry.response_preview ? `<pre class="log-preview">${escapeHtml(entry.response_preview)}</pre>` : ""))
      : `<pre class="log-preview">${escapeHtml(entry.message || "")}</pre>`;
    return `
      <div class="log-entry">
        <div class="log-header">
          <span class="log-badge ${statusClass}">${statusLabel}</span>
          <span class="log-op">${isCall ? "AI 호출" : "로그"}</span>
          ${details}
          <span class="log-ts">${ts}</span>
        </div>
        ${preview}
      </div>
    `;
  }

  async function loadAiLogs() {
    state.ui.logsLoading = true;
    render();
    try {
      const data = await requestJson("/api/ai-logs?limit=100");
      state.ui.logs = data.entries || [];
    } finally {
      state.ui.logsLoading = false;
      render();
    }
  }

  function renderToast() {
    if (!state.ui.toast) {
      return "";
    }
    return `<div class="toast ${state.ui.toast.tone}">${escapeHtml(state.ui.toast.message)}</div>`;
  }

  function renderLoadingOverlay() {
    const busy = state.generate.busy || state.ui.aiLoading;
    if (!busy) return "";
    const message = state.generate.busy
      ? "문서 세션을 생성하고 있습니다..."
      : (state.ui.aiLoadingMsg || "AI가 내용을 생성하고 있습니다...");
    const sub = state.generate.busy
      ? "선택한 경험을 기반으로 문서를 구성합니다. 잠시 기다려 주세요."
      : "잠시 기다려 주세요.";
    return `
      <div class="loading-overlay">
        <div class="loading-overlay-inner">
          <div class="spinner"></div>
          <strong>${escapeHtml(message)}</strong>
          <p>${sub}</p>
        </div>
      </div>
    `;
  }

  function renderFileBrowserModal() {
    const fb = state.ui.fileBrowser;
    if (!fb.open) return "";
    return `
      <div class="modal-overlay" data-action="file-browser-close">
        <div class="modal-box" data-action="">
          <div class="modal-header">
            <div>
              <div class="eyebrow">폴더 선택</div>
              <h3>저장소 경로 지정</h3>
            </div>
            <button class="btn btn-ghost" data-action="file-browser-close" type="button">✕</button>
          </div>
          <div class="modal-body">
            ${fb.loading ? `<div class="empty-panel" style="min-height:160px;">불러오는 중...</div>` : renderFileBrowserEntries(fb)}
          </div>
          <div class="modal-footer">
            <span class="path-display">${escapeHtml(fb.currentPath || "경로 없음")}</span>
            <button class="btn btn-primary" data-action="file-browser-select" type="button">선택</button>
            <button class="btn btn-ghost" data-action="file-browser-close" type="button">취소</button>
          </div>
        </div>
      </div>
    `;
  }

  function renderFileBrowserEntries(fb) {
    let html = "";

    if (fb.roots.length > 0) {
      html += `<div class="dir-roots">`;
      fb.roots.forEach((root) => {
        const name = root.split("/").pop() || root;
        html += `<button class="btn btn-secondary" style="font-size:11px;padding:5px 10px;" data-action="file-browser-navigate" data-path="${escapeHtml(root)}" type="button">⌂ ${escapeHtml(name)}</button>`;
      });
      html += `</div>`;
    }

    if (fb.parentPath) {
      html += `<button class="dir-breadcrumb" data-action="file-browser-parent" type="button">↑ 상위 폴더</button>`;
    }

    if (!fb.entries.length) {
      return html + `<div class="empty-panel" style="min-height:120px;">하위 폴더가 없습니다.</div>`;
    }

    fb.entries.forEach((entry) => {
      const isGit = entry.is_git_repo;
      html += `
        <button class="dir-entry ${isGit ? "git-repo" : ""}" data-action="file-browser-navigate" data-path="${escapeHtml(entry.path)}" type="button">
          <span>${isGit ? "◈" : "▸"}</span>
          <span class="dir-name">${escapeHtml(entry.name)}</span>
          ${isGit ? `<span class="badge green" style="font-size:10px;margin-left:auto;">git</span>` : ""}
        </button>
      `;
    });

    return html;
  }

  async function loadFileBrowserDir(path) {
    state.ui.fileBrowser.loading = true;
    render();
    try {
      const query = path ? `?path=${encodeURIComponent(path)}` : "";
      const payload = await requestJson(`/api/fs/directories${query}`);
      state.ui.fileBrowser.currentPath = payload.current_path;
      state.ui.fileBrowser.parentPath = payload.parent_path || null;
      state.ui.fileBrowser.roots = payload.roots || [];
      state.ui.fileBrowser.entries = payload.entries || [];
    } catch (error) {
      showToast(error.message || "디렉터리를 불러오지 못했습니다.", "error");
    } finally {
      state.ui.fileBrowser.loading = false;
      render();
    }
  }
})();
