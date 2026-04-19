/* DevFolio Portfolio Studio */

const COMPOSE_STEPS = [
  {
    id: 'input',
    eyebrow: 'Step 1',
    title: '입력 방식 선택',
    copy: '텍스트를 붙여넣거나 Git 저장소를 분석해 프로젝트 초안을 시작합니다.',
    sticky: '원본 입력 또는 Git 분석으로 포트폴리오 초안의 출발점을 만드세요.',
  },
  {
    id: 'basics',
    eyebrow: 'Step 2',
    title: '프로젝트 기본 정보',
    copy: '프로젝트명, 역할, 기간, 한 줄 소개처럼 문서의 바탕이 되는 정보를 정리합니다.',
    sticky: '채용 담당자가 가장 먼저 읽게 될 기본 정보를 명확히 적어두세요.',
  },
  {
    id: 'problem',
    eyebrow: 'Step 3',
    title: '문제와 목표',
    copy: '왜 만들었는지, 어떤 문제를 해결했는지, 누구를 위한 프로젝트였는지 구조화합니다.',
    sticky: '프로젝트의 맥락과 문제 정의가 분명해야 이후 문장 품질도 좋아집니다.',
  },
  {
    id: 'work',
    eyebrow: 'Step 4',
    title: '작업과 기여',
    copy: '핵심 작업, 기능, 기여 범위를 작업 단위로 정리하고 AI 문구를 보완합니다.',
    sticky: '무엇을 구현했는지보다 무엇을 해결했고 어떤 결과를 만들었는지 보여주세요.',
  },
  {
    id: 'architecture',
    eyebrow: 'Step 5',
    title: '기술과 아키텍처',
    copy: '기술 선택 이유, 구성 요소, 데이터 모델, API 예시, 운영 고려사항을 채웁니다.',
    sticky: '기술 나열이 아니라 설계 판단과 구조를 드러내는 단계입니다.',
  },
  {
    id: 'assets',
    eyebrow: 'Step 6',
    title: '링크, 자산, 회고',
    copy: '성과, 문제 해결 사례, 링크, 스크린샷, 회고를 추가해 케이스 스터디를 완성합니다.',
    sticky: '정량·정성 성과와 회고가 들어가야 포트폴리오의 설득력이 올라갑니다.',
  },
  {
    id: 'review',
    eyebrow: 'Step 7',
    title: '검토 및 저장',
    copy: '문서로 미리보기 전에 핵심 정보와 누락 항목을 마지막으로 점검합니다.',
    sticky: '초안을 저장하고 문서 미리보기까지 연결하면 한 사이클이 완료됩니다.',
  },
];

const VALID_SCREENS = ['home', 'compose', 'library', 'preview', 'settings'];
const DEFAULT_MODELS = {
  pollinations: 'openai-fast',
  groq: 'llama-3.3-70b-versatile',
  openrouter: 'meta-llama/llama-3.3-70b-instruct:free',
  gemini: 'gemini-3.1-flash-lite-preview',
  anthropic: 'claude-sonnet-4-20250514',
  openai: 'gpt-4o',
  ollama: 'llama3.2',
};

const GEMINI_MODEL_INFO = [
  { prefix: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite Preview', free: true },
  { prefix: 'gemini-3-flash-preview', label: 'Gemini 3 Flash Preview', free: true },
  { prefix: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite', free: true },
  { prefix: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', free: true },
  { prefix: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', free: true },
  { prefix: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash', free: false },
  { prefix: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro', free: false },
  { prefix: 'gemma', label: 'Gemma', free: true },
];

const state = {
  config: null,
  projects: [],
  currentDraft: emptyDraft(),
  loadedProjectId: '',
  preview: {
    docType: 'portfolio',
    source: 'draft',
    template: 'default',
    format: 'html',
    projectIds: [],
  },
  lastPreview: null,
  lastScanPayload: null,
  scanPicker: {
    currentPath: '',
    parentPath: '',
    roots: [],
    entries: [],
  },
  ui: {
    screen: 'home',
    composeStep: 'input',
    dirty: false,
    fieldErrors: {},
    modalId: null,
    modalTrigger: null,
    nextFocusSelector: '',
  },
};

let toastTimer = null;
let mermaidInitialized = false;
let confirmResolver = null;

document.addEventListener('DOMContentLoaded', () => {
  applyUrlState();
  bindStaticEvents();
  bindModalEvents();
  bindComposeDynamicEvents();
  bindSettingsForms();
  bindPreviewControls();
  window.addEventListener('beforeunload', handleBeforeUnload);
  window.addEventListener('popstate', handlePopState);
  loadInitialData();
});

function emptyPeriod() {
  return { start: '', end: '' };
}

function emptyTask() {
  return {
    id: '',
    name: '',
    period: emptyPeriod(),
    problem: '',
    solution: '',
    result: '',
    tech_used: [],
    keywords: [],
    ai_generated_text: '',
  };
}

function emptyLinks() {
  return { github: '', demo: '', docs: '', video: '' };
}

function emptyOverview() {
  return {
    background: '',
    problem: '',
    target_users: [],
    goals: [],
    non_goals: [],
  };
}

function emptyUserFlowStep() {
  return { step: 1, title: '', description: '' };
}

function emptyStackReason() {
  return { name: '', reason: '' };
}

function emptyTechStackDetail() {
  return { frontend: [], backend: [], database: [], infra: [], tools: [] };
}

function emptyArchitectureComponent() {
  return { name: '', role: '' };
}

function emptyDataModelEntity() {
  return { entity: '', fields: [] };
}

function emptyApiExample() {
  return { method: 'GET', path: '', purpose: '' };
}

function emptyArchitecture() {
  return {
    summary: '',
    components: [],
    data_model: [],
    api_examples: [],
  };
}

function emptyFeature() {
  return { name: '', user_value: '', implementation: '' };
}

function emptyProblemSolvingCase() {
  return {
    title: '',
    situation: '',
    cause: '',
    action: '',
    decision_reason: '',
    result: '',
    metric: '',
    tech_used: [],
  };
}

function emptyPerformanceSecurityOperations() {
  return { performance: [], security: [], operations: [] };
}

function emptyQuantitativeResult() {
  return { metric_name: '', before: '', after: '', impact: '' };
}

function emptyResults() {
  return { quantitative: [], qualitative: [] };
}

function emptyRetrospective() {
  return {
    what_went_well: [],
    what_was_hard: [],
    what_i_learned: [],
    next_steps: [],
  };
}

function emptyAssetItem() {
  return { title: '', description: '', path: '' };
}

function emptyAssets() {
  return { screenshots: [], diagrams: [] };
}

function emptyDraft() {
  return {
    id: '',
    name: '',
    type: 'company',
    status: 'done',
    organization: '',
    period: emptyPeriod(),
    role: '',
    team_size: 1,
    tech_stack: [],
    one_line_summary: '',
    summary: '',
    links: emptyLinks(),
    overview: emptyOverview(),
    user_flow: [],
    tech_stack_detail: emptyTechStackDetail(),
    architecture: emptyArchitecture(),
    features: [],
    problem_solving_cases: [],
    performance_security_operations: emptyPerformanceSecurityOperations(),
    results: emptyResults(),
    retrospective: emptyRetrospective(),
    assets: emptyAssets(),
    tags: [],
    tasks: [emptyTask()],
    raw_text: '',
  };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function normalizeArray(value) {
  if (Array.isArray(value)) {
    return value.map(item => String(item ?? '').trim()).filter(Boolean);
  }
  if (typeof value === 'string') {
    return value
      .split(',')
      .map(item => item.trim())
      .filter(Boolean);
  }
  return [];
}

function normalizeTextList(value) {
  if (Array.isArray(value)) {
    return value.map(item => String(item ?? '').trim()).filter(Boolean);
  }
  if (typeof value === 'string') {
    return value
      .split(/\n|,/)
      .map(item => item.trim())
      .filter(Boolean);
  }
  return [];
}

function normalizeCollection(value, factory) {
  if (!Array.isArray(value)) return [];
  return value.map(item => ({ ...factory(), ...(item || {}) }));
}

function normalizeDraft(input) {
  const base = emptyDraft();
  const draft = { ...base, ...(input || {}) };
  draft.period = {
    start: draft.period?.start || '',
    end: draft.period?.end || '',
  };
  draft.team_size = Number(draft.team_size) > 0 ? Number(draft.team_size) : 1;
  draft.tech_stack = normalizeArray(draft.tech_stack);
  draft.tags = normalizeArray(draft.tags);
  draft.links = { ...emptyLinks(), ...(draft.links || {}) };
  draft.overview = {
    ...emptyOverview(),
    ...(draft.overview || {}),
    target_users: normalizeTextList(draft.overview?.target_users),
    goals: normalizeTextList(draft.overview?.goals),
    non_goals: normalizeTextList(draft.overview?.non_goals),
  };
  draft.user_flow = normalizeCollection(draft.user_flow, emptyUserFlowStep).map((item, index) => ({
    ...item,
    step: Number(item.step) > 0 ? Number(item.step) : index + 1,
  }));
  draft.tech_stack_detail = { ...emptyTechStackDetail(), ...(draft.tech_stack_detail || {}) };
  ['frontend', 'backend', 'database', 'infra', 'tools'].forEach(group => {
    draft.tech_stack_detail[group] = normalizeCollection(draft.tech_stack_detail[group], emptyStackReason);
  });
  draft.architecture = {
    ...emptyArchitecture(),
    ...(draft.architecture || {}),
    components: normalizeCollection(draft.architecture?.components, emptyArchitectureComponent),
    data_model: normalizeCollection(draft.architecture?.data_model, emptyDataModelEntity).map(item => ({
      ...item,
      fields: normalizeTextList(item.fields),
    })),
    api_examples: normalizeCollection(draft.architecture?.api_examples, emptyApiExample),
  };
  draft.features = normalizeCollection(draft.features, emptyFeature);
  draft.problem_solving_cases = normalizeCollection(draft.problem_solving_cases, emptyProblemSolvingCase).map(item => ({
    ...item,
    tech_used: normalizeTextList(item.tech_used),
  }));
  draft.performance_security_operations = {
    ...emptyPerformanceSecurityOperations(),
    ...(draft.performance_security_operations || {}),
    performance: normalizeTextList(draft.performance_security_operations?.performance),
    security: normalizeTextList(draft.performance_security_operations?.security),
    operations: normalizeTextList(draft.performance_security_operations?.operations),
  };
  draft.results = {
    ...emptyResults(),
    ...(draft.results || {}),
    quantitative: normalizeCollection(draft.results?.quantitative, emptyQuantitativeResult),
    qualitative: normalizeTextList(draft.results?.qualitative),
  };
  draft.retrospective = {
    ...emptyRetrospective(),
    ...(draft.retrospective || {}),
    what_went_well: normalizeTextList(draft.retrospective?.what_went_well),
    what_was_hard: normalizeTextList(draft.retrospective?.what_was_hard),
    what_i_learned: normalizeTextList(draft.retrospective?.what_i_learned),
    next_steps: normalizeTextList(draft.retrospective?.next_steps),
  };
  draft.assets = {
    ...emptyAssets(),
    ...(draft.assets || {}),
    screenshots: normalizeCollection(draft.assets?.screenshots, emptyAssetItem),
    diagrams: normalizeCollection(draft.assets?.diagrams, emptyAssetItem),
  };
  draft.tasks = Array.isArray(draft.tasks) && draft.tasks.length
    ? draft.tasks.map(task => ({
        ...emptyTask(),
        ...(task || {}),
        period: {
          start: task?.period?.start || '',
          end: task?.period?.end || '',
        },
        tech_used: normalizeTextList(task?.tech_used),
        keywords: normalizeTextList(task?.keywords),
      }))
    : [emptyTask()];
  draft.raw_text = draft.raw_text || '';
  draft.one_line_summary = draft.one_line_summary || '';
  draft.summary = draft.summary || '';
  return draft;
}

function escHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function geminiModelLabel(modelId) {
  const info = GEMINI_MODEL_INFO.find(item => modelId.startsWith(item.prefix));
  if (!info) return modelId;
  return info.free ? `${modelId} (무료)` : modelId;
}

function modelLabelForProvider(providerName, modelId) {
  if (!modelId) return '-';
  if (providerName === 'gemini') return geminiModelLabel(modelId);
  if (providerName === 'openrouter' && modelId.endsWith(':free')) return `${modelId} (무료)`;
  return modelId;
}

function providerModelSummary(provider) {
  const displayModel = provider.display_model || provider.model || '';
  const generationModel = provider.generation_model || displayModel;
  if (generationModel && generationModel !== displayModel) {
    return `저장: ${displayModel} · 생성: ${generationModel}`;
  }
  return generationModel || displayModel || '-';
}

function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
}

async function renderMermaidDiagrams(root = document) {
  if (typeof mermaid === 'undefined') return;
  if (!mermaidInitialized) {
    mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });
    mermaidInitialized = true;
  }

  const blocks = root.querySelectorAll('pre code.language-mermaid');
  if (!blocks.length) return;

  let index = 0;
  blocks.forEach(code => {
    const pre = code.closest('pre');
    if (!pre) return;
    const container = document.createElement('div');
    container.className = 'mermaid';
    container.id = `preview-mermaid-${Date.now()}-${index += 1}`;
    container.textContent = code.textContent;
    pre.replaceWith(container);
  });

  try {
    await mermaid.run({ querySelector: '.mermaid' });
  } catch (error) {
    console.warn('Mermaid render failed', error);
  }
}

function normalizeUiError(error, fallbackMessage = '요청 처리 중 오류가 발생했습니다.') {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  return fallbackMessage;
}

async function runUserAction(button, busyLabel, callback, options = {}) {
  const {
    title = '작업 실패',
    toastMessage = '작업에 실패했습니다.',
    fallbackMessage = '요청 처리 중 오류가 발생했습니다.',
    messageBuilder = null,
    onError = null,
    skipDialog = false,
  } = options;

  try {
    return await withButtonState(button, busyLabel, callback);
  } catch (error) {
    console.error(error);
    const baseMessage = normalizeUiError(error, fallbackMessage);
    const message = typeof messageBuilder === 'function'
      ? messageBuilder(baseMessage, error)
      : baseMessage;

    if (typeof onError === 'function') {
      onError(message, error);
    }

    showToast(toastMessage, 'error');
    if (!skipDialog) {
      showErrorDialog(title, message);
    }
    return null;
  }
}

function withButtonState(button, busyLabel, callback) {
  if (!button) {
    return callback();
  }
  const original = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  return Promise.resolve()
    .then(callback)
    .finally(() => {
      button.disabled = false;
      button.textContent = original;
    });
}

function pathTokens(path) {
  return String(path || '')
    .split('.')
    .filter(Boolean)
    .map(token => (/^\d+$/.test(token) ? Number(token) : token));
}

function getPathValue(obj, path) {
  return pathTokens(path).reduce((current, token) => (current == null ? undefined : current[token]), obj);
}

function setPathValue(obj, path, value) {
  const tokens = pathTokens(path);
  if (!tokens.length) return;
  let current = obj;
  for (let index = 0; index < tokens.length - 1; index += 1) {
    const token = tokens[index];
    if (current[token] == null) {
      current[token] = typeof tokens[index + 1] === 'number' ? [] : {};
    }
    current = current[token];
  }
  current[tokens[tokens.length - 1]] = value;
}

function getCollection(path) {
  const value = getPathValue(state.currentDraft, path);
  return Array.isArray(value) ? value : [];
}

function addCollectionItem(path) {
  const collection = getCollection(path);
  const factory = COLLECTION_FACTORIES[path];
  if (!factory) return;
  collection.push(factory());
  setPathValue(state.currentDraft, path, collection);
  markDraftDirty();
  renderCompose();
}

function removeCollectionItem(path, index) {
  const collection = getCollection(path).slice();
  collection.splice(index, 1);
  setPathValue(state.currentDraft, path, collection);
  if (path === 'tasks' && !collection.length) {
    setPathValue(state.currentDraft, path, [emptyTask()]);
  }
  if (path === 'user_flow') {
    getCollection(path).forEach((item, itemIndex) => {
      item.step = itemIndex + 1;
    });
  }
  markDraftDirty();
  renderCompose();
}

const COLLECTION_FACTORIES = {
  tasks: emptyTask,
  user_flow: emptyUserFlowStep,
  features: emptyFeature,
  problem_solving_cases: emptyProblemSolvingCase,
  'tech_stack_detail.frontend': emptyStackReason,
  'tech_stack_detail.backend': emptyStackReason,
  'tech_stack_detail.database': emptyStackReason,
  'tech_stack_detail.infra': emptyStackReason,
  'tech_stack_detail.tools': emptyStackReason,
  'architecture.components': emptyArchitectureComponent,
  'architecture.data_model': emptyDataModelEntity,
  'architecture.api_examples': emptyApiExample,
  'results.quantitative': emptyQuantitativeResult,
  'assets.screenshots': emptyAssetItem,
  'assets.diagrams': emptyAssetItem,
};

function markDraftDirty() {
  state.ui.dirty = true;
  refreshComposeChrome();
  renderRailStatus();
  renderHome();
}

function resetDraftDirty() {
  state.ui.dirty = false;
  refreshComposeChrome();
  renderRailStatus();
  renderHome();
}

function setFieldError(path, message) {
  state.ui.fieldErrors[path] = message;
}

function clearFieldError(path) {
  delete state.ui.fieldErrors[path];
}

function fieldErrorMarkup(path) {
  const message = state.ui.fieldErrors[path];
  return message ? `<div class="field-error">${escHtml(message)}</div>` : '';
}

function clearInlineComposeError() {
  const el = document.getElementById('compose-inline-error');
  if (!el) return;
  el.textContent = '';
  el.classList.add('hidden');
}

function setInlineComposeError(message) {
  const el = document.getElementById('compose-inline-error');
  if (!el) return;
  el.textContent = message;
  el.classList.toggle('hidden', !message);
}

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const legacyTab = params.get('tab');
  const mappedScreen = ({
    guide: 'home',
    intake: 'compose',
    scan: 'compose',
    projects: 'library',
    preview: 'preview',
    settings: 'settings',
  })[legacyTab];
  const requestedScreen = params.get('screen') || mappedScreen || state.ui.screen;
  const requestedStep = params.get('step') || (legacyTab === 'scan' ? 'input' : state.ui.composeStep);
  state.ui.screen = VALID_SCREENS.includes(requestedScreen) ? requestedScreen : 'home';
  state.ui.composeStep = COMPOSE_STEPS.some(step => step.id === requestedStep) ? requestedStep : 'input';
}

function syncUrlState() {
  const url = new URL(window.location.href);
  url.searchParams.set('screen', state.ui.screen);
  if (state.ui.screen === 'compose') {
    url.searchParams.set('step', state.ui.composeStep);
  } else {
    url.searchParams.delete('step');
  }
  url.searchParams.delete('tab');
  window.history.replaceState({}, '', `${url.pathname}${url.search}`);
}

function handlePopState() {
  applyUrlState();
  renderShell();
}

function handleBeforeUnload(event) {
  if (!state.ui.dirty) return;
  event.preventDefault();
  event.returnValue = '';
}

async function switchScreen(screen, options = {}) {
  if (!VALID_SCREENS.includes(screen)) return false;
  if (
    state.ui.screen === 'compose'
    && screen !== 'compose'
    && screen !== 'preview'
    && state.ui.dirty
    && !options.force
  ) {
    const confirmed = await confirmAction({
      title: '저장하지 않은 초안이 있습니다',
      message: '저장하지 않은 변경사항이 있습니다.\n지금 화면을 떠나면 현재 초안 수정 내용이 저장되지 않습니다.',
      confirmLabel: '화면 이동',
    });
    if (!confirmed) return false;
  }

  state.ui.screen = screen;
  closeMobileNav();
  syncUrlState();
  renderShell();
  return true;
}

function setComposeStep(stepId) {
  if (!COMPOSE_STEPS.some(step => step.id === stepId)) return;
  state.ui.composeStep = stepId;
  syncUrlState();
  renderCompose();
}

function currentStepIndex() {
  return COMPOSE_STEPS.findIndex(step => step.id === state.ui.composeStep);
}

function stepById(stepId) {
  return COMPOSE_STEPS.find(step => step.id === stepId) || COMPOSE_STEPS[0];
}

function openMobileNav() {
  document.body.classList.add('rail-open');
  document.getElementById('btn-mobile-nav')?.setAttribute('aria-expanded', 'true');
}

function closeMobileNav() {
  document.body.classList.remove('rail-open');
  document.getElementById('btn-mobile-nav')?.setAttribute('aria-expanded', 'false');
}

function toggleMobileNav() {
  if (document.body.classList.contains('rail-open')) closeMobileNav();
  else openMobileNav();
}

function openModal(id, focusSelector = '') {
  const modal = document.getElementById(id);
  if (!modal) return;
  state.ui.modalTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  state.ui.modalId = id;
  modal.classList.add('show');
  modal.setAttribute('aria-hidden', 'false');
  const focusTarget = focusSelector ? modal.querySelector(focusSelector) : null;
  window.setTimeout(() => {
    if (focusTarget instanceof HTMLElement) focusTarget.focus();
  }, 0);
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.remove('show');
  modal.setAttribute('aria-hidden', 'true');
  if (state.ui.modalId === id) {
    state.ui.modalId = null;
  }
  const previous = state.ui.modalTrigger;
  state.ui.modalTrigger = null;
  if (previous instanceof HTMLElement) {
    previous.focus();
  }
}

function bindModalEvents() {
  document.querySelectorAll('[data-modal-close]').forEach(element => {
    element.addEventListener('click', () => {
      const type = element.getAttribute('data-modal-close');
      if (type === 'error') closeErrorDialog();
      if (type === 'directory') closeDirectoryDialog();
      if (type === 'confirm') resolveConfirm(false);
    });
  });
  document.getElementById('error-dialog-close')?.addEventListener('click', closeErrorDialog);
  document.getElementById('directory-dialog-close')?.addEventListener('click', closeDirectoryDialog);
  document.getElementById('confirm-dialog-close')?.addEventListener('click', () => resolveConfirm(false));
  document.getElementById('confirm-dialog-cancel')?.addEventListener('click', () => resolveConfirm(false));
  document.getElementById('confirm-dialog-confirm')?.addEventListener('click', () => resolveConfirm(true));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (state.ui.modalId === 'error-dialog') closeErrorDialog();
      if (state.ui.modalId === 'directory-dialog') closeDirectoryDialog();
      if (state.ui.modalId === 'confirm-dialog') resolveConfirm(false);
    }
  });
}

function showErrorDialog(title, message) {
  document.getElementById('error-dialog-title').textContent = title || '오류';
  document.getElementById('error-dialog-message').textContent = message || '요청 처리 중 오류가 발생했습니다.';
  openModal('error-dialog', '#error-dialog-close');
}

function closeErrorDialog() {
  closeModal('error-dialog');
}

function openDirectoryDialog() {
  const inputPath = document.getElementById('scan-repo-path')?.value.trim();
  openModal('directory-dialog', '#directory-dialog-close');
  loadDirectoryDialog(inputPath || '');
}

function closeDirectoryDialog() {
  closeModal('directory-dialog');
}

function confirmAction({ title = '확인', message = '', confirmLabel = '계속' }) {
  document.getElementById('confirm-dialog-title').textContent = title;
  document.getElementById('confirm-dialog-message').textContent = message;
  document.getElementById('confirm-dialog-confirm').textContent = confirmLabel;
  openModal('confirm-dialog', '#confirm-dialog-cancel');
  return new Promise(resolve => {
    confirmResolver = resolve;
  });
}

function resolveConfirm(result) {
  closeModal('confirm-dialog');
  if (confirmResolver) {
    confirmResolver(result);
    confirmResolver = null;
  }
}

async function loadDirectoryDialog(path = '') {
  await runUserAction(null, '', async () => {
    const query = path ? `?path=${encodeURIComponent(path)}` : '';
    const result = await apiGet(`/api/fs/directories${query}`);
    state.scanPicker.currentPath = result.current_path || '';
    state.scanPicker.parentPath = result.parent_path || '';
    state.scanPicker.roots = result.roots || [];
    state.scanPicker.entries = result.entries || [];
    renderDirectoryDialog();
  }, {
    title: '폴더 선택 실패',
    toastMessage: '폴더 목록을 불러오지 못했습니다.',
    fallbackMessage: '폴더 목록을 불러오지 못했습니다.',
    onError: () => closeDirectoryDialog(),
  });
}

function renderDirectoryDialog() {
  const currentEl = document.getElementById('directory-dialog-current');
  const rootsEl = document.getElementById('directory-dialog-roots');
  const listEl = document.getElementById('directory-dialog-list');
  const parentButton = document.getElementById('btn-directory-parent');
  if (!currentEl || !rootsEl || !listEl || !parentButton) return;

  currentEl.textContent = state.scanPicker.currentPath || '-';
  parentButton.disabled = !state.scanPicker.parentPath;

  rootsEl.innerHTML = state.scanPicker.roots.map(root => {
    const active = root === state.scanPicker.currentPath ? ' active' : '';
    return `<button type="button" class="directory-root-chip${active}" data-directory-root="${escHtml(root)}">${escHtml(root)}</button>`;
  }).join('');

  listEl.innerHTML = !state.scanPicker.entries.length
    ? '<div class="directory-empty">하위 폴더가 없습니다.</div>'
    : state.scanPicker.entries.map(entry => `
      <button type="button" class="directory-entry" data-directory-path="${escHtml(entry.path)}">
        <span>
          <span class="directory-entry-name">${escHtml(entry.name)}</span>
          <span class="directory-entry-meta">${escHtml(entry.path)}</span>
        </span>
        ${entry.is_git_repo ? '<span class="directory-entry-badge">Git 저장소</span>' : ''}
      </button>
    `).join('');
}

function getConfiguredProvider(name) {
  if (!name) return null;
  return (state.config?.ai_providers || []).find(provider => provider.name === name) || null;
}

function getCurrentLanguageSelection() {
  return document.getElementById('intake-lang')?.value || state.config?.general?.default_language || 'ko';
}

function getCurrentProviderSelection() {
  return document.getElementById('intake-provider')?.value || null;
}

function getScanAnalysisProvider() {
  const selectedName = document.getElementById('scan-provider')?.value || '';
  if (selectedName) return getConfiguredProvider(selectedName);
  const defaultName = state.config?.general?.default_ai_provider || '';
  return getConfiguredProvider(defaultName);
}

function updateScanProviderWarning() {
  const warningEl = document.getElementById('scan-provider-warning');
  if (!warningEl) return;
  const analyze = document.getElementById('scan-analyze')?.checked || false;
  const provider = getScanAnalysisProvider();
  const defaultWarning = state.config?.general?.default_ai_generation_warning || '';
  const warning = analyze
    ? provider?.generation_warning || (!document.getElementById('scan-provider')?.value ? defaultWarning : '')
    : '';

  warningEl.textContent = warning;
  warningEl.classList.toggle('hidden', !warning);
}

function isRemoteRepoInput(value) {
  const raw = String(value || '').trim();
  return raw.startsWith('http://') || raw.startsWith('https://') || raw.startsWith('git@') || raw.startsWith('ssh://');
}

function renderScanError(message) {
  const resultEl = document.getElementById('scan-result');
  const actionsEl = document.getElementById('scan-load-actions');
  if (resultEl) {
    resultEl.innerHTML = `
      <div class="scan-result-error">
        <strong>Git 분석 실패</strong>
        <p>${escHtml(message)}</p>
      </div>
    `;
  }
  if (actionsEl) actionsEl.style.display = 'none';
  state.lastScanPayload = null;
}

function buildScanErrorMessage(repoPath, errorMessage) {
  if (isRemoteRepoInput(repoPath)) {
    return [
      '입력한 값은 로컬 저장소 경로가 아니라 GitHub URL입니다.',
      'DevFolio의 Git 분석은 원격 URL을 직접 읽지 않고, 현재 PC에 clone된 저장소 폴더를 스캔합니다.',
      '',
      '해결 방법',
      `- 잘못 입력한 값: ${repoPath}`,
      '- 예시 경로: /Users/yourname/projects/DevFolio',
      '- Docker에서는 호스트 경로를 그대로 넣어도 됩니다.',
    ].join('\n');
  }
  return errorMessage || 'Git 분석 중 오류가 발생했습니다.';
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const err = new Error(payload.detail || payload.message || `HTTP ${response.status}`);
    err.status = response.status;
    throw err;
  }
  return response.json();
}

function apiGet(path) {
  return api(path);
}

function apiPost(path, data) {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
}

function apiPut(path, data) {
  return api(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

function apiDelete(path) {
  return api(path, { method: 'DELETE' });
}

function bindStaticEvents() {
  document.querySelectorAll('.nav-item').forEach(button => {
    button.addEventListener('click', async () => {
      await switchScreen(button.dataset.screen);
    });
  });

  document.getElementById('btn-mobile-nav')?.addEventListener('click', toggleMobileNav);
  document.getElementById('btn-new-draft')?.addEventListener('click', handleNewDraft);
  document.getElementById('btn-go-preview')?.addEventListener('click', async () => {
    state.preview.source = 'draft';
    document.getElementById('preview-source').value = 'draft';
    await switchScreen('preview', { force: true });
    await renderPreview();
  });

  document.getElementById('btn-home-start-text')?.addEventListener('click', async () => {
    await switchScreen('compose', { force: true });
    setComposeStep('input');
    document.getElementById('intake-raw-text')?.focus();
  });
  document.getElementById('btn-home-start-git')?.addEventListener('click', async () => {
    await switchScreen('compose', { force: true });
    setComposeStep('input');
    document.getElementById('scan-repo-path')?.focus();
  });
  document.getElementById('btn-home-open-library')?.addEventListener('click', async () => {
    await switchScreen('library', { force: true });
  });

  document.getElementById('btn-compose-prev')?.addEventListener('click', () => {
    const index = currentStepIndex();
    if (index > 0) setComposeStep(COMPOSE_STEPS[index - 1].id);
  });
  document.getElementById('btn-compose-next')?.addEventListener('click', () => {
    const index = currentStepIndex();
    if (index < COMPOSE_STEPS.length - 1) setComposeStep(COMPOSE_STEPS[index + 1].id);
  });
  document.getElementById('btn-draft-preview')?.addEventListener('click', async () => {
    state.preview.source = 'draft';
    document.getElementById('preview-source').value = 'draft';
    await switchScreen('preview', { force: true });
    await renderPreview();
  });
  document.getElementById('btn-draft-save')?.addEventListener('click', handleDraftSave);

  document.getElementById('btn-directory-parent')?.addEventListener('click', () => {
    if (state.scanPicker.parentPath) loadDirectoryDialog(state.scanPicker.parentPath);
  });
  document.getElementById('btn-directory-select')?.addEventListener('click', () => {
    const input = document.getElementById('scan-repo-path');
    if (input) input.value = state.scanPicker.currentPath || '';
    closeDirectoryDialog();
    showToast('저장소 경로를 선택했습니다.');
  });

  document.getElementById('directory-dialog-roots')?.addEventListener('click', event => {
    const button = event.target.closest('[data-directory-root]');
    if (!button) return;
    loadDirectoryDialog(button.dataset.directoryRoot);
  });
  document.getElementById('directory-dialog-list')?.addEventListener('click', event => {
    const button = event.target.closest('[data-directory-path]');
    if (!button) return;
    loadDirectoryDialog(button.dataset.directoryPath);
  });

  document.getElementById('home-quick-actions')?.addEventListener('click', handleHomeQuickAction);
  document.getElementById('home-recent-projects')?.addEventListener('click', handleHomeRecentClick);
  document.getElementById('projects-library')?.addEventListener('click', handleProjectLibraryClick);
  document.getElementById('projects-detail')?.addEventListener('click', handleHomeRecentClick);
  document.getElementById('projects-detail')?.addEventListener('click', handleProjectLibraryClick);
  document.getElementById('preview-saved-projects')?.addEventListener('change', handlePreviewProjectSelection);
  document.getElementById('provider-list')?.addEventListener('click', handleProviderActionClick);
}

function bindComposeDynamicEvents() {
  const container = document.getElementById('compose-step-content');
  if (!container) return;

  container.addEventListener('input', handleComposeFieldInput);
  container.addEventListener('change', handleComposeFieldInput);
  container.addEventListener('click', handleComposeClick);
}

function bindSettingsForms() {
  bindForm('form-profile', '/api/config/user', 'PUT', async () => {
    state.config = await apiGet('/api/config');
    populateProviders();
    applyConfigToForms();
    renderHome();
  });
  bindForm('form-export', '/api/config/export', 'PUT', async () => {
    state.config = await apiGet('/api/config');
    applyConfigToForms();
    renderPreviewControls();
  });
  bindForm('form-sync', '/api/config/sync', 'PUT', async () => {
    state.config = await apiGet('/api/config');
    applyConfigToForms();
  });
  bindForm('form-general', '/api/config/general', 'PUT', async () => {
    state.config = await apiGet('/api/config');
    applyConfigToForms();
    populateProviders();
    renderShell();
  });

  document.getElementById('form-ai')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('[type="submit"]');
    const data = formToJson(form);
    if (!data.api_key) delete data.api_key;
    if (!data.base_url) delete data.base_url;
    if (!data.model) {
      data.model = document.getElementById('ai-model')?.value || '';
    }
    if (!data.model && data.name) {
      data.model = DEFAULT_MODELS[data.name] || '';
    }
    if (!data.model) {
      showToast('모델을 먼저 선택하거나 목록을 새로고침하세요.', 'error');
      return;
    }

    await runUserAction(button, '저장 중…', async () => {
      await apiPost('/api/config/ai', data);
      state.config = await apiGet('/api/config');
      populateProviders();
      applyConfigToForms();
      form.reset();
      syncProviderForm();
      showToast('AI 제공자를 저장했습니다.');
      if (state.ui.screen === 'compose' && state.ui.composeStep === 'input') {
        renderComposeStepContent();
        refreshComposeChrome();
      }
    }, {
      title: 'AI 제공자 저장 실패',
      toastMessage: 'AI 제공자 저장에 실패했습니다.',
      fallbackMessage: 'AI 제공자를 저장하지 못했습니다.',
    });
  });

  document.getElementById('ai-name')?.addEventListener('change', () => {
    syncProviderForm();
    const provider = document.getElementById('ai-name')?.value;
    const alreadySaved = state.config?.ai_providers?.some(item => item.name === provider);
    const isBuiltin = provider === 'pollinations';
    const isOllama = provider === 'ollama';
    if (alreadySaved || isBuiltin || isOllama) loadModelsForProvider();
    else resetModelSelect();
  });
  document.getElementById('ai-key')?.addEventListener('change', loadModelsForProvider);
  document.getElementById('ai-key')?.addEventListener('paste', () => setTimeout(loadModelsForProvider, 100));
  document.getElementById('ai-base-url')?.addEventListener('change', loadModelsForProvider);
  document.getElementById('btn-load-models')?.addEventListener('click', loadModelsForProvider);
  document.addEventListener('click', event => {
    const button = event.target.closest('.toggle-password');
    if (!button) return;
    const input = button.parentElement?.querySelector('input');
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
    button.textContent = input.type === 'password' ? '보기' : '숨기기';
  });
}

function bindPreviewControls() {
  ['preview-doc-type', 'preview-source', 'preview-template', 'preview-format'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', syncPreviewState);
  });
  document.getElementById('btn-preview-render')?.addEventListener('click', renderPreview);
  document.getElementById('btn-preview-export')?.addEventListener('click', exportPreview);
}

function bindForm(formId, endpoint, method, onSuccess) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('[type="submit"]');
    await runUserAction(button, '저장 중…', async () => {
      const payload = formToJson(form);
      if (method === 'PUT') {
        await apiPut(endpoint, payload);
      } else {
        await apiPost(endpoint, payload);
      }
      if (onSuccess) await onSuccess();
      showToast('설정을 저장했습니다.');
    }, {
      title: '설정 저장 실패',
      toastMessage: '저장에 실패했습니다.',
      fallbackMessage: '설정을 저장하지 못했습니다.',
    });
  });
}

function formToJson(form) {
  const data = {};
  new FormData(form).forEach((value, key) => {
    data[key] = value;
  });
  form.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
    data[checkbox.name] = checkbox.checked;
  });
  return data;
}

function handleComposeFieldInput(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  if (target.id === 'scan-analyze') {
    const langField = document.getElementById('scan-lang-field');
    if (langField) langField.classList.toggle('hidden', !target.checked);
    updateScanProviderWarning();
    return;
  }
  if (target.id === 'scan-provider') {
    updateScanProviderWarning();
    return;
  }
  if (target.id === 'intake-lang' || target.id === 'intake-provider' || target.id === 'scan-lang') {
    return;
  }

  const path = target.dataset.path;
  const listPath = target.dataset.listPath;
  if (!path && !listPath) return;

  if (path) {
    const type = target.dataset.valueType || 'string';
    const value = type === 'number'
      ? Math.max(1, Number(target.value) || 1)
      : target.value;
    setPathValue(state.currentDraft, path, value);
    clearFieldError(path);
  }
  if (listPath) {
    setPathValue(state.currentDraft, listPath, normalizeTextList(target.value));
    clearFieldError(listPath);
  }

  if (path === 'name' || path === 'role' || path === 'summary' || path === 'one_line_summary' || path?.startsWith('overview.') || path?.startsWith('tasks.')) {
    clearInlineComposeError();
  }

  markDraftDirty();
}

async function handleComposeClick(event) {
  const target = event.target.closest('button');
  if (!target) return;

  if (target.dataset.stepTarget) {
    setComposeStep(target.dataset.stepTarget);
    return;
  }

  if (target.dataset.addCollection) {
    addCollectionItem(target.dataset.addCollection);
    return;
  }

  if (target.dataset.removeCollection) {
    removeCollectionItem(target.dataset.removeCollection, Number(target.dataset.index));
    return;
  }

  if (target.id === 'btn-intake-generate') {
    await handleIntakeGenerate();
    return;
  }

  if (target.id === 'btn-intake-manual') {
    startManualDraft();
    return;
  }

  if (target.id === 'btn-scan-run') {
    await handleGitScan();
    return;
  }

  if (target.id === 'btn-scan-load-draft') {
    handleScanLoadDraft();
    return;
  }

  if (target.id === 'btn-scan-pick-dir') {
    openDirectoryDialog();
    return;
  }

  if (target.dataset.composeAction === 'summary') {
    await handleDraftSummary();
    return;
  }

  if (target.dataset.composeAction === 'generate') {
    await handleIntakeGenerate();
    return;
  }

  if (target.dataset.composeAction === 'manual') {
    startManualDraft();
    return;
  }

  if (target.dataset.composeAction === 'tasks') {
    await handleDraftTaskBullets();
    return;
  }

  if (target.dataset.composeAction === 'add-task') {
    addCollectionItem('tasks');
    return;
  }

  if (target.dataset.composeAction === 'preview') {
    document.getElementById('btn-draft-preview')?.click();
    return;
  }

  if (target.dataset.composeAction === 'save') {
    document.getElementById('btn-draft-save')?.click();
  }
}

async function handleHomeQuickAction(event) {
  const button = event.target.closest('[data-home-action]');
  if (!button) return;
  const action = button.dataset.homeAction;
  if (action === 'settings') {
    await switchScreen('settings', { force: true });
  }
  if (action === 'compose') {
    await switchScreen('compose', { force: true });
    setComposeStep(button.dataset.homeStep || 'input');
  }
  if (action === 'library') {
    await switchScreen('library', { force: true });
  }
  if (action === 'preview') {
    await switchScreen('preview', { force: true });
  }
}

async function handleHomeRecentClick(event) {
  const button = event.target.closest('[data-home-project-action]');
  if (!button) return;
  const projectId = button.dataset.projectId;
  const project = state.projects.find(item => item.id === projectId);
  if (!project) return;

  if (button.dataset.homeProjectAction === 'load') {
    await loadProjectIntoCompose(project);
  }
  if (button.dataset.homeProjectAction === 'preview') {
    state.preview.source = 'saved';
    state.preview.projectIds = [project.id];
    await switchScreen('preview', { force: true });
    renderPreviewControls();
    await renderPreview();
  }
}

async function handleProviderActionClick(event) {
  const button = event.target.closest('[data-provider-action]');
  if (!button) return;
  const name = button.dataset.providerName;
  const action = button.dataset.providerAction;
  if (!name) return;

  if (action === 'test') {
    await runUserAction(button, '테스트 중…', async () => {
      const result = await apiPost(`/api/config/ai/${encodeURIComponent(name)}/test`, {});
      if (result.status !== 'ok') {
        throw new Error(result.message || '연결 확인 실패');
      }
      showToast(`${name} 연결을 확인했습니다.`);
    }, {
      title: 'AI 연결 테스트 실패',
      toastMessage: '연결 확인에 실패했습니다.',
      fallbackMessage: 'AI 연결을 확인하지 못했습니다.',
    });
    return;
  }

  if (action === 'remove') {
    const confirmed = await confirmAction({
      title: 'AI 제공자를 삭제할까요?',
      message: `'${name}' 설정을 삭제합니다.\n저장된 모델과 키 연결 정보도 함께 제거됩니다.`,
      confirmLabel: '삭제',
    });
    if (!confirmed) return;

    await runUserAction(button, '삭제 중…', async () => {
      await apiDelete(`/api/config/ai/${encodeURIComponent(name)}`);
      state.config = await apiGet('/api/config');
      populateProviders();
      applyConfigToForms();
      renderHome();
      resetModelOptionsAndRefreshInputStep();
      showToast(`${name} 설정을 삭제했습니다.`);
    }, {
      title: 'AI 제공자 삭제 실패',
      toastMessage: '삭제에 실패했습니다.',
      fallbackMessage: 'AI 제공자를 삭제하지 못했습니다.',
    });
  }
}

async function loadInitialData() {
  try {
    const [configPayload, projectsPayload] = await Promise.all([
      apiGet('/api/config'),
      apiGet('/api/projects'),
    ]);
    state.config = configPayload;
    state.projects = projectsPayload.projects || [];
    state.preview.projectIds = state.projects.map(project => project.id);
    applyConfigToForms();
    populateProviders();
    syncProviderForm();
    renderShell();
    if (state.config?.general?.default_ai_provider) {
      loadModelsForProvider().catch(() => {});
    }
    if (document.body.dataset.initialized !== 'true') {
      state.ui.screen = 'home';
      syncUrlState();
      renderShell();
    }
  } catch (error) {
    showToast(error.message || '초기 데이터를 불러오지 못했습니다.', 'error');
  }
}

function headerContentForScreen(screen) {
  if (screen === 'home') {
    return {
      eyebrow: 'Portfolio Workflow',
      title: '처음 시작부터 문서 완성까지 한 화면에서 설계된 흐름',
      copy: '지금 해야 할 일과 빠른 시작 경로를 먼저 보여주고, 초안 생성과 문서 작업으로 자연스럽게 이어집니다.',
    };
  }
  if (screen === 'compose') {
    return {
      eyebrow: 'Compose Case Study',
      title: '프로젝트 경험을 구조화된 포트폴리오 데이터로 정리',
      copy: '문제 정의, 기술 판단, 문제 해결 사례까지 채용 관점에서 읽히는 초안을 단계별로 다듬습니다.',
    };
  }
  if (screen === 'library') {
    return {
      eyebrow: 'Project Library',
      title: '저장한 프로젝트를 다시 열고 문장 품질을 반복 개선',
      copy: '이미 저장한 프로젝트를 불러와 요약과 작업 항목을 다시 생성하고, 미리보기까지 이어서 진행할 수 있습니다.',
    };
  }
  if (screen === 'preview') {
    return {
      eyebrow: 'Document Preview',
      title: '문서로 읽히는 결과를 먼저 확인하고 출력 형식을 결정',
      copy: '현재 초안이나 저장된 프로젝트를 선택해 포트폴리오와 이력서를 미리보고 최종 파일로 내보낼 수 있습니다.',
    };
  }
  return {
    eyebrow: 'Workspace Settings',
    title: 'AI 연결, 프로필, 내보내기 설정을 한곳에서 관리',
    copy: '반복해서 쓰는 프로필과 생성 모델, 백업 설정을 미리 맞춰두면 이후 작성 흐름이 훨씬 빨라집니다.',
  };
}

function renderShell() {
  updateHeader();
  activateScreen();
  renderRailStatus();
  renderHome();
  renderCompose();
  renderProjects();
  renderPreviewControls();
  renderPreviewBadges();
  renderPreviewOutput();
}

function updateHeader() {
  const content = headerContentForScreen(state.ui.screen);
  document.getElementById('workspace-eyebrow').textContent = content.eyebrow;
  document.getElementById('workspace-title').textContent = content.title;
  document.getElementById('workspace-copy').textContent = content.copy;
}

function activateScreen() {
  document.querySelectorAll('.nav-item').forEach(button => {
    const active = button.dataset.screen === state.ui.screen;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  document.querySelectorAll('.screen-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === `screen-${state.ui.screen}`);
  });
}

function renderRailStatus() {
  const container = document.getElementById('rail-status-pills');
  if (!container) return;

  const providerCount = state.config?.ai_providers?.length || 0;
  const dirtyText = state.ui.dirty ? '초안 미저장' : '초안 안정';
  const projectCount = `${state.projects.length}개 프로젝트`;
  const defaultProvider = state.config?.general?.default_ai_provider || 'AI 미설정';
  const pills = [
    { label: dirtyText, className: 'dark' },
    { label: providerCount ? `AI ${providerCount}개 연결` : 'AI 연결 없음', className: providerCount ? 'dark' : 'dark warning' },
    { label: projectCount, className: 'dark' },
    { label: `기본 제공자: ${defaultProvider}`, className: 'dark' },
  ];

  container.innerHTML = pills.map(pill => `<span class="status-pill ${pill.className}">${escHtml(pill.label)}</span>`).join('');
}

function renderHome() {
  renderHomeQuickActions();
  renderHomeStatus();
  renderHomeRecentProjects();
}

function renderHomeQuickActions() {
  const container = document.getElementById('home-quick-actions');
  if (!container) return;
  const hasAI = (state.config?.ai_providers || []).length > 0;
  const cards = [
    hasAI
      ? {
          title: '텍스트로 초안 시작',
          copy: '메모, PR 정리, README 초안을 붙여넣고 AI로 구조화 초안을 생성합니다.',
          action: 'compose',
          step: 'input',
          cta: 'Compose 열기',
        }
      : {
          title: 'AI 먼저 연결하기',
          copy: '초안 자동 생성과 문구 보강을 쓰려면 먼저 AI 제공자를 연결해야 합니다.',
          action: 'settings',
          cta: 'Settings 열기',
        },
    {
      title: 'Git 저장소 분석 시작',
      copy: '로컬 저장소를 읽어 프로젝트 개요와 작업 항목을 자동으로 만드는 시작 경로입니다.',
      action: 'compose',
      step: 'input',
      cta: 'Git 분석 화면으로',
    },
    {
      title: state.projects.length ? '기존 프로젝트 이어서 작업' : '프로젝트 라이브러리 보기',
      copy: state.projects.length
        ? '이미 저장한 프로젝트를 다시 열어 요약, 구조, 문구를 반복 개선할 수 있습니다.'
        : '저장된 프로젝트가 생기면 이곳에서 다시 불러와 이어서 작업할 수 있습니다.',
      action: 'library',
      cta: 'Library 열기',
    },
    {
      title: '문서 결과 먼저 확인',
      copy: '현재 초안이나 저장 프로젝트를 포트폴리오 문서로 렌더링해 결과 품질을 바로 확인합니다.',
      action: 'preview',
      cta: 'Preview 열기',
    },
  ];

  container.innerHTML = cards.map(card => `
    <button type="button" class="home-action-card" data-home-action="${escHtml(card.action)}" ${card.step ? `data-home-step="${escHtml(card.step)}"` : ''}>
      <strong>${escHtml(card.title)}</strong>
      <p>${escHtml(card.copy)}</p>
      <span class="section-kicker">${escHtml(card.cta)}</span>
    </button>
  `).join('');
}

function renderHomeStatus() {
  const container = document.getElementById('home-status-grid');
  if (!container) return;
  const providers = state.config?.ai_providers || [];
  const defaultProvider = state.config?.general?.default_ai_provider || '미설정';
  const lastProject = state.projects[0]?.name || '없음';
  const cards = [
    {
      title: '초기 설정',
      value: document.body.dataset.initialized === 'true' ? '완료' : '미완료',
      copy: document.body.dataset.initialized === 'true'
        ? '프로필 초기화가 끝났습니다.'
        : 'CLI init 단계가 아직 완료되지 않았습니다.',
    },
    {
      title: 'AI 연결 상태',
      value: providers.length ? `${providers.length}개` : '없음',
      copy: providers.length
        ? `기본 제공자는 ${defaultProvider}입니다.`
        : '아직 연결된 AI 제공자가 없습니다.',
    },
    {
      title: '저장된 프로젝트',
      value: `${state.projects.length}개`,
      copy: state.projects.length
        ? `가장 최근 프로젝트는 ${lastProject}입니다.`
        : '저장된 프로젝트가 아직 없습니다.',
    },
    {
      title: '현재 초안 상태',
      value: state.ui.dirty ? '미저장' : '안정',
      copy: state.loadedProjectId
        ? `${state.currentDraft.name || '현재 초안'}를 편집 중입니다.`
        : '새 초안 작성 흐름을 시작할 수 있습니다.',
    },
  ];

  container.innerHTML = cards.map(card => `
    <article class="status-card">
      <strong>${escHtml(card.title)}</strong>
      <div class="status-value">${escHtml(card.value)}</div>
      <p>${escHtml(card.copy)}</p>
    </article>
  `).join('');
}

function renderHomeRecentProjects() {
  const container = document.getElementById('home-recent-projects');
  if (!container) return;
  if (!state.projects.length) {
    container.innerHTML = '<div class="empty-surface">아직 저장된 프로젝트가 없습니다. Compose 화면에서 첫 포트폴리오 초안을 저장해보세요.</div>';
    return;
  }

  container.innerHTML = state.projects.slice(0, 3).map(project => `
    <article class="project-item">
      <div>
        <h4>${escHtml(project.name)}</h4>
        <p>${escHtml(project.one_line_summary || project.summary || '프로젝트 소개가 아직 없습니다.')}</p>
        <small>${escHtml(project.role || '역할 미입력')} · ${escHtml(project.tech_stack?.join(', ') || '기술 스택 미입력')}</small>
      </div>
      <div class="inline-actions">
        <button type="button" class="btn btn-ghost" data-home-project-action="load" data-project-id="${escHtml(project.id)}">다시 열기</button>
        <button type="button" class="btn btn-secondary" data-home-project-action="preview" data-project-id="${escHtml(project.id)}">문서로 보기</button>
      </div>
    </article>
  `).join('');
}

function draftCompleteness() {
  const draft = state.currentDraft;
  return {
    basics: Boolean(draft.name && draft.role),
    problem: Boolean(draft.overview.background || draft.overview.problem || draft.one_line_summary),
    work: Boolean(draft.tasks.some(task => task.name || task.problem || task.solution || task.result) || draft.features.length),
    architecture: Boolean(
      draft.architecture.summary
      || Object.values(draft.tech_stack_detail).some(list => list.length)
      || draft.architecture.components.length
      || draft.architecture.api_examples.length
    ),
    assets: Boolean(
      draft.problem_solving_cases.length
      || draft.results.quantitative.length
      || draft.results.qualitative.length
      || draft.links.github
      || draft.assets.screenshots.length
      || draft.assets.diagrams.length
    ),
  };
}

function isStepComplete(stepId) {
  const flags = draftCompleteness();
  if (stepId === 'input') return Boolean(state.currentDraft.raw_text || state.currentDraft.name);
  if (stepId === 'basics') return flags.basics;
  if (stepId === 'problem') return flags.problem;
  if (stepId === 'work') return flags.work;
  if (stepId === 'architecture') return flags.architecture;
  if (stepId === 'assets') return flags.assets;
  if (stepId === 'review') return Boolean(state.loadedProjectId);
  return false;
}

function renderCompose() {
  renderComposeStepper();
  renderComposeStepHeader();
  renderComposeStepContent();
  refreshComposeChrome();
}

function refreshComposeChrome() {
  renderComposeStepper();
  renderComposeSidebar();
  renderComposeSticky();
}

function renderComposeStepper() {
  const container = document.getElementById('compose-stepper');
  if (!container) return;
  container.innerHTML = COMPOSE_STEPS.map((step, index) => `
    <button
      type="button"
      class="compose-step-button ${step.id === state.ui.composeStep ? 'active' : ''} ${isStepComplete(step.id) ? 'done' : ''}"
      data-step-target="${escHtml(step.id)}"
    >
      ${String(index + 1).padStart(2, '0')} · ${escHtml(step.title)}
    </button>
  `).join('');
}

function renderComposeStepHeader() {
  const step = stepById(state.ui.composeStep);
  document.getElementById('compose-step-eyebrow').textContent = step.eyebrow;
  document.getElementById('compose-step-title').textContent = step.title;
  document.getElementById('compose-step-copy').textContent = step.copy;
}

function renderComposeSticky() {
  const sticky = document.getElementById('compose-sticky-copy');
  if (sticky) sticky.textContent = stepById(state.ui.composeStep).sticky;

  const prev = document.getElementById('btn-compose-prev');
  const next = document.getElementById('btn-compose-next');
  const index = currentStepIndex();
  if (prev) prev.disabled = index <= 0;
  if (next) next.disabled = index >= COMPOSE_STEPS.length - 1;
}

function renderComposeSidebar() {
  const status = document.getElementById('compose-draft-status');
  if (status) {
    const draft = state.currentDraft;
    const missing = [];
    if (!draft.name) missing.push('프로젝트명');
    if (!draft.role) missing.push('역할');
    if (!draft.overview.problem) missing.push('핵심 문제');
    if (!draft.tasks.some(task => task.name || task.problem || task.solution || task.result)) missing.push('작업 항목');

    status.innerHTML = `
      <h4>${escHtml(draft.name || '새 포트폴리오 초안')}</h4>
      <p>${escHtml(draft.one_line_summary || draft.summary || '프로젝트를 한 줄로 설명하는 문장이 아직 없습니다.')}</p>
      <p>역할: ${escHtml(draft.role || '미입력')} · 팀 규모: ${escHtml(String(draft.team_size || 1))}명</p>
      <p>작업 ${draft.tasks.length}개 · 문제 해결 사례 ${draft.problem_solving_cases.length}개 · 링크 ${Object.values(draft.links).filter(Boolean).length}개</p>
      <p>${state.ui.dirty ? '저장되지 않은 변경사항이 있습니다.' : '현재 초안은 저장된 상태와 일치합니다.'}</p>
      ${missing.length ? `<p>누락 우선순위: ${escHtml(missing.join(', '))}</p>` : '<p>핵심 필드가 대부분 채워졌습니다. 이제 문서 미리보기로 연결해보세요.</p>'}
    `;
  }

  const actions = document.getElementById('compose-step-actions');
  if (!actions) return;
  if (state.ui.composeStep === 'input') {
    actions.innerHTML = `
      <div class="action-card">
        <strong>AI 초안 만들기</strong>
        <p>붙여넣은 원본 텍스트를 기반으로 프로젝트 기본 구조와 케이스 스터디 초안을 생성합니다.</p>
        <button type="button" class="btn btn-primary" data-compose-action="generate">AI로 구조화 초안 만들기</button>
      </div>
      <div class="action-card">
        <strong>빈 구조로 시작</strong>
        <p>직접 내용을 채우고 싶은 경우, 현재 텍스트를 유지한 채 구조화 폼만 초기화할 수 있습니다.</p>
        <button type="button" class="btn btn-secondary" data-compose-action="manual">빈 초안 열기</button>
      </div>
    `;
    return;
  }
  if (state.ui.composeStep === 'work') {
    actions.innerHTML = `
      <div class="action-card">
        <strong>작업 항목 자동 정리</strong>
        <p>현재 초안의 맥락을 바탕으로 작업 항목 문구를 achievement 중심으로 다시 생성합니다.</p>
        <button type="button" class="btn btn-primary" data-compose-action="tasks">작업 항목 생성</button>
      </div>
      <div class="action-card">
        <strong>작업 카드 추가</strong>
        <p>기능 단위, 개선 단위, 운영 이슈 단위로 작업 카드를 추가해 기여 범위를 세분화할 수 있습니다.</p>
        <button type="button" class="btn btn-secondary" data-compose-action="add-task">작업 카드 추가</button>
      </div>
    `;
    return;
  }
  if (state.ui.composeStep === 'review') {
    actions.innerHTML = `
      <div class="action-card">
        <strong>문서 결과 먼저 확인</strong>
        <p>현재 초안을 포트폴리오 문서로 렌더링해 길이와 톤, 섹션 구성을 먼저 검토합니다.</p>
        <button type="button" class="btn btn-primary" data-compose-action="preview">문서로 바로 확인</button>
      </div>
      <div class="action-card">
        <strong>현재 초안 저장</strong>
        <p>저장하면 Library에서 다시 불러오고, 프로젝트 단위로 문구를 반복 개선할 수 있습니다.</p>
        <button type="button" class="btn btn-secondary" data-compose-action="save">현재 초안 저장</button>
      </div>
    `;
    return;
  }

  actions.innerHTML = `
    <div class="action-card">
      <strong>소개 문단 보강</strong>
      <p>프로젝트 기본 정보와 문제 정의를 바탕으로 포트폴리오 소개 문단을 다시 생성할 수 있습니다.</p>
      <button type="button" class="btn btn-primary" data-compose-action="summary">소개 문단 생성</button>
    </div>
    <div class="action-card">
      <strong>다음 단계로 진행</strong>
      <p>현재 단계에서 핵심 정보만 채워도 다음 단계에서 세부 내용을 이어서 보강할 수 있습니다.</p>
      <button type="button" class="btn btn-secondary" data-step-target="${escHtml(COMPOSE_STEPS[Math.min(currentStepIndex() + 1, COMPOSE_STEPS.length - 1)].id)}">다음 단계 열기</button>
    </div>
  `;
}

function renderInputField(label, path, value, options = {}) {
  const type = options.type || 'text';
  const placeholder = options.placeholder || '';
  const hint = options.hint ? `<p class="field-hint">${escHtml(options.hint)}</p>` : '';
  const valueType = options.valueType ? ` data-value-type="${escHtml(options.valueType)}"` : '';
  const autocomplete = options.autocomplete ? ` autocomplete="${escHtml(options.autocomplete)}"` : '';
  const spellcheck = options.spellcheck === false ? ' spellcheck="false"' : '';
  const inputmode = options.inputmode ? ` inputmode="${escHtml(options.inputmode)}"` : '';
  return `
    <label class="field">
      <span>${escHtml(label)}</span>
      <input type="${escHtml(type)}" data-path="${escHtml(path)}"${valueType} value="${escHtml(value || '')}" placeholder="${escHtml(placeholder)}"${autocomplete}${spellcheck}${inputmode} />
    </label>
    ${fieldErrorMarkup(path)}
    ${hint}
  `;
}

function renderTextareaField(label, path, value, options = {}) {
  const rows = options.rows || 4;
  const placeholder = options.placeholder || '';
  const hint = options.hint ? `<p class="field-hint">${escHtml(options.hint)}</p>` : '';
  return `
    <label class="field">
      <span>${escHtml(label)}</span>
      <textarea rows="${rows}" data-path="${escHtml(path)}" placeholder="${escHtml(placeholder)}">${escHtml(value || '')}</textarea>
    </label>
    ${fieldErrorMarkup(path)}
    ${hint}
  `;
}

function renderInlineListInput(label, listPath, values, options = {}) {
  const placeholder = options.placeholder || '값을 쉼표로 구분해 입력하세요.';
  const hint = options.hint ? `<p class="field-hint">${escHtml(options.hint)}</p>` : '';
  return `
    <label class="field">
      <span>${escHtml(label)}</span>
      <input type="text" data-list-path="${escHtml(listPath)}" value="${escHtml((values || []).join(', '))}" placeholder="${escHtml(placeholder)}" />
    </label>
    ${fieldErrorMarkup(listPath)}
    ${hint}
  `;
}

function renderListField(label, listPath, values, options = {}) {
  const rows = options.rows || 3;
  const placeholder = options.placeholder || '항목마다 줄바꿈 또는 쉼표로 구분해 입력하세요.';
  const hint = options.hint ? `<p class="field-hint">${escHtml(options.hint)}</p>` : '';
  return `
    <label class="field">
      <span>${escHtml(label)}</span>
      <textarea rows="${rows}" data-list-path="${escHtml(listPath)}" placeholder="${escHtml(placeholder)}">${escHtml((values || []).join('\n'))}</textarea>
    </label>
    ${fieldErrorMarkup(listPath)}
    ${hint}
  `;
}

function renderRepeatHeader(title, subtitle, collectionPath, index) {
  return `
    <div class="repeat-head">
      <div>
        <p class="eyebrow">${escHtml(subtitle)}</p>
        <h4 class="repeat-title">${escHtml(title)}</h4>
      </div>
      <button type="button" class="btn btn-ghost danger" data-remove-collection="${escHtml(collectionPath)}" data-index="${index}">삭제</button>
    </div>
  `;
}

function providerOptionsMarkup(selectedValue) {
  const providers = state.config?.ai_providers || [];
  return `
    <option value="">자동 선택</option>
    ${providers.map(provider => `
      <option value="${escHtml(provider.name)}" ${provider.name === selectedValue ? 'selected' : ''}>
        ${escHtml(`${provider.name} · ${providerModelSummary(provider)}`)}
      </option>
    `).join('')}
  `;
}

function renderComposeStepContent() {
  clearInlineComposeError();
  const container = document.getElementById('compose-step-content');
  if (!container) return;

  let html = '';
  if (state.ui.composeStep === 'input') html = renderComposeInputStep();
  if (state.ui.composeStep === 'basics') html = renderComposeBasicsStep();
  if (state.ui.composeStep === 'problem') html = renderComposeProblemStep();
  if (state.ui.composeStep === 'work') html = renderComposeWorkStep();
  if (state.ui.composeStep === 'architecture') html = renderComposeArchitectureStep();
  if (state.ui.composeStep === 'assets') html = renderComposeAssetsStep();
  if (state.ui.composeStep === 'review') html = renderComposeReviewStep();
  container.innerHTML = html;
  updateScanProviderWarning();
}

function renderComposeInputStep() {
  const defaultLang = state.config?.general?.default_language || 'ko';
  const rawText = state.currentDraft.raw_text || '';
  return `
    <div class="compose-card-grid">
      <section class="studio-panel">
        <div class="section-header">
          <p class="eyebrow">Input Method</p>
          <h3>텍스트를 붙여넣어 초안 만들기</h3>
          <p>README, 프로젝트 메모, PR 정리, 회고, 노션 내용처럼 현재 가진 텍스트를 그대로 넣어도 됩니다.</p>
        </div>
        <label class="field">
          <span>원본 텍스트</span>
          <textarea id="intake-raw-text" rows="16" data-path="raw_text" placeholder="예: 결제 서버에서 실패 재처리 파이프라인을 만들었고…">${escHtml(rawText)}</textarea>
        </label>
        <div class="field-grid">
          <label class="field">
            <span>AI 출력 언어</span>
            <select id="intake-lang">
              <option value="ko" ${defaultLang === 'ko' ? 'selected' : ''}>한국어</option>
              <option value="en" ${defaultLang === 'en' ? 'selected' : ''}>English</option>
              <option value="both" ${defaultLang === 'both' ? 'selected' : ''}>한국어 + 영어</option>
            </select>
          </label>
          <label class="field">
            <span>AI 제공자</span>
            <select id="intake-provider">${providerOptionsMarkup('')}</select>
          </label>
        </div>
        <div class="action-row">
          <button id="btn-intake-generate" type="button" class="btn btn-primary">AI로 구조화 초안 만들기</button>
          <button id="btn-intake-manual" type="button" class="btn btn-secondary">빈 초안으로 직접 작성</button>
        </div>
      </section>

      <section class="studio-panel">
        <div class="section-header">
          <p class="eyebrow">Git Scan</p>
          <h3>로컬 저장소 분석으로 시작하기</h3>
          <p>내 커밋 기반으로 프로젝트 개요와 작업 내역을 자동 생성한 뒤 Compose 흐름으로 바로 이어집니다.</p>
        </div>
        <label class="field">
          <span>저장소 경로</span>
          <input type="text" id="scan-repo-path" placeholder="/Users/yourname/projects/my-app 또는 ." />
        </label>
        <p class="field-hint">Docker에서는 호스트 경로를 그대로 붙여넣어도 자동으로 경로 매핑을 시도합니다.</p>
        <div class="action-row">
          <button id="btn-scan-pick-dir" type="button" class="btn btn-ghost">폴더 선택</button>
        </div>
        <label class="field">
          <span>Author Email</span>
          <input type="text" id="scan-author-email" placeholder="you@example.com" spellcheck="false" />
        </label>
        <div class="field-grid">
          <label class="field checkbox-field">
            <input type="checkbox" id="scan-refresh" />
            <span>이미 등록된 프로젝트 다시 분석</span>
          </label>
          <label class="field checkbox-field">
            <input type="checkbox" id="scan-analyze" />
            <span>AI 상세 분석으로 설명 보강</span>
          </label>
        </div>
        <div id="scan-lang-field" class="field-grid hidden">
          <label class="field">
            <span>AI 출력 언어</span>
            <select id="scan-lang">
              <option value="ko">한국어</option>
              <option value="en">English</option>
              <option value="both">한국어 + 영어</option>
            </select>
          </label>
          <label class="field">
            <span>AI 제공자</span>
            <select id="scan-provider">${providerOptionsMarkup('')}</select>
          </label>
        </div>
        <p id="scan-provider-warning" class="field-hint field-warning hidden" role="status" aria-live="polite"></p>
        <div class="action-row">
          <button id="btn-scan-run" type="button" class="btn btn-primary">Git 저장소 분석하기</button>
        </div>
        <div id="scan-result" class="scan-result-placeholder">분석 결과가 여기에 표시됩니다.</div>
        <div class="action-row action-row-end" id="scan-load-actions" style="display:none">
          <button id="btn-scan-load-draft" type="button" class="btn btn-secondary">분석 결과를 초안으로 불러오기</button>
        </div>
      </section>
    </div>
  `;
}

function renderComposeBasicsStep() {
  const draft = state.currentDraft;
  return `
    <div class="field-grid">
      ${renderInputField('프로젝트명', 'name', draft.name, { placeholder: '예: DevFolio Portfolio Studio', autocomplete: 'organization-title' })}
      ${renderInputField('한 줄 소개', 'one_line_summary', draft.one_line_summary, { placeholder: '프로젝트의 목적과 가치를 한 문장으로 설명하세요.' })}
    </div>
    <div class="field-grid">
      <label class="field">
        <span>유형</span>
        <select data-path="type">
          <option value="company" ${draft.type === 'company' ? 'selected' : ''}>정규 프로젝트</option>
          <option value="side" ${draft.type === 'side' ? 'selected' : ''}>사이드 프로젝트</option>
          <option value="course" ${draft.type === 'course' ? 'selected' : ''}>교육/과정</option>
        </select>
      </label>
      <label class="field">
        <span>상태</span>
        <select data-path="status">
          <option value="done" ${draft.status === 'done' ? 'selected' : ''}>완료</option>
          <option value="in_progress" ${draft.status === 'in_progress' ? 'selected' : ''}>진행 중</option>
          <option value="planned" ${draft.status === 'planned' ? 'selected' : ''}>계획 중</option>
        </select>
      </label>
      ${renderInputField('시작 월', 'period.start', draft.period.start, { placeholder: 'YYYY-MM', inputmode: 'numeric' })}
      ${renderInputField('종료 월', 'period.end', draft.period.end, { placeholder: 'YYYY-MM 또는 빈 값', inputmode: 'numeric' })}
    </div>
    <div class="field-grid">
      ${renderInputField('소속/조직', 'organization', draft.organization, { placeholder: '회사명 또는 팀명' })}
      ${renderInputField('역할', 'role', draft.role, { placeholder: '예: 백엔드 개발자' })}
    </div>
    <div class="field-grid">
      ${renderInputField('팀 규모', 'team_size', draft.team_size, { type: 'number', valueType: 'number', placeholder: '1', inputmode: 'numeric' })}
      ${renderInlineListInput('기술 스택', 'tech_stack', draft.tech_stack, { placeholder: 'Python, FastAPI, Docker' })}
    </div>
    ${renderInlineListInput('태그', 'tags', draft.tags, { placeholder: 'backend, ai, docs' })}
    ${renderTextareaField('프로젝트 소개 문단', 'summary', draft.summary, { rows: 6, placeholder: '문서 상단에 들어갈 소개 문단을 작성하거나 AI 액션으로 생성하세요.' })}
  `;
}

function renderUserFlowItems() {
  const items = state.currentDraft.user_flow;
  if (!items.length) {
    return '<div class="empty-surface">아직 사용자 흐름이 없습니다. 아래 버튼으로 단계별 사용 시나리오를 추가하세요.</div>';
  }
  return items.map((item, index) => `
    <article class="repeat-item">
      ${renderRepeatHeader(item.title || `사용 흐름 ${index + 1}`, `User Flow ${index + 1}`, 'user_flow', index)}
      <div class="field-grid">
        ${renderInputField('순서', `user_flow.${index}.step`, item.step, { type: 'number', valueType: 'number', placeholder: String(index + 1), inputmode: 'numeric' })}
        ${renderInputField('단계명', `user_flow.${index}.title`, item.title, { placeholder: '예: 프로젝트 입력' })}
      </div>
      ${renderTextareaField('단계 설명', `user_flow.${index}.description`, item.description, { rows: 3, placeholder: '사용자가 이 단계에서 무엇을 하는지 적어주세요.' })}
    </article>
  `).join('');
}

function renderComposeProblemStep() {
  const draft = state.currentDraft;
  return `
    <div class="compose-card-grid">
      <section class="studio-panel">
        <div class="section-header">
          <p class="eyebrow">Project Context</p>
          <h3>왜 만들었는지와 어떤 문제를 풀었는지</h3>
          <p>프로젝트의 존재 이유와 문제 정의가 명확할수록 소개 문단과 문제 해결 사례의 밀도가 올라갑니다.</p>
        </div>
        ${renderTextareaField('배경', 'overview.background', draft.overview.background, { rows: 5, placeholder: '왜 이 프로젝트가 필요했는지 설명하세요.' })}
        ${renderTextareaField('핵심 문제', 'overview.problem', draft.overview.problem, { rows: 5, placeholder: '해결하려던 핵심 문제를 명확히 적으세요.' })}
      </section>

      <section class="studio-panel">
        <div class="section-header">
          <p class="eyebrow">Scope</p>
          <h3>누구를 위한 프로젝트였고 목표는 무엇이었는지</h3>
          <p>대상 사용자, 목표, 비목표를 분리하면 설명이 더 실무적으로 정리됩니다.</p>
        </div>
        ${renderListField('대상 사용자', 'overview.target_users', draft.overview.target_users, { rows: 3 })}
        ${renderListField('프로젝트 목표', 'overview.goals', draft.overview.goals, { rows: 4 })}
        ${renderListField('의도적으로 제외한 범위', 'overview.non_goals', draft.overview.non_goals, { rows: 3 })}
      </section>
    </div>

    <section class="studio-panel">
      <div class="collection-toolbar">
        <div>
          <p class="eyebrow">User Flow</p>
          <h3>사용 흐름</h3>
        </div>
        <button type="button" class="btn btn-secondary" data-add-collection="user_flow">사용 흐름 추가</button>
      </div>
      <p class="field-hint">프로젝트를 실제로 사용하는 흐름을 단계별로 적으면 포트폴리오 문서의 구조와 아키텍처 설명이 더 자연스러워집니다.</p>
      <div class="repeat-list">${renderUserFlowItems()}</div>
    </section>
  `;
}

function renderTaskItems() {
  const tasks = state.currentDraft.tasks;
  return tasks.map((task, index) => `
    <article class="task-item">
      ${renderRepeatHeader(task.name || `작업 ${index + 1}`, `Task ${index + 1}`, 'tasks', index)}
      <div class="field-grid">
        ${renderInputField('작업명', `tasks.${index}.name`, task.name, { placeholder: '예: AI 제공자 설정 흐름 개선' })}
        ${renderInlineListInput('사용 기술', `tasks.${index}.tech_used`, task.tech_used, { placeholder: 'FastAPI, Jinja2, Docker' })}
      </div>
      <div class="field-grid">
        ${renderInputField('시작 월', `tasks.${index}.period.start`, task.period.start, { placeholder: 'YYYY-MM', inputmode: 'numeric' })}
        ${renderInputField('종료 월', `tasks.${index}.period.end`, task.period.end, { placeholder: 'YYYY-MM 또는 빈 값', inputmode: 'numeric' })}
      </div>
      ${renderTextareaField('문제 상황', `tasks.${index}.problem`, task.problem, { rows: 3 })}
      ${renderTextareaField('해결 방법', `tasks.${index}.solution`, task.solution, { rows: 3 })}
      <div class="field-grid">
        ${renderTextareaField('결과', `tasks.${index}.result`, task.result, { rows: 3 })}
        ${renderListField('키워드', `tasks.${index}.keywords`, task.keywords, { rows: 3 })}
      </div>
      ${renderTextareaField('포트폴리오 문구', `tasks.${index}.ai_generated_text`, task.ai_generated_text, { rows: 5, placeholder: 'AI 문구를 생성하면 여기에 저장됩니다.' })}
    </article>
  `).join('');
}

function renderFeatureItems() {
  const items = state.currentDraft.features;
  if (!items.length) {
    return '<div class="empty-surface">아직 핵심 기능이 없습니다. 사용자 가치와 구현 방식을 기능 단위로 나눠 적어보세요.</div>';
  }
  return items.map((item, index) => `
    <article class="repeat-item">
      ${renderRepeatHeader(item.name || `핵심 기능 ${index + 1}`, `Feature ${index + 1}`, 'features', index)}
      ${renderInputField('기능명', `features.${index}.name`, item.name, { placeholder: '예: Git 저장소 자동 분석' })}
      ${renderTextareaField('사용자 가치', `features.${index}.user_value`, item.user_value, { rows: 3 })}
      ${renderTextareaField('구현 방식', `features.${index}.implementation`, item.implementation, { rows: 3 })}
    </article>
  `).join('');
}

function renderComposeWorkStep() {
  return `
    <section class="studio-panel">
      <div class="collection-toolbar">
        <div>
          <p class="eyebrow">Task Breakdown</p>
          <h3>작업과 기여 내역</h3>
        </div>
        <button type="button" class="btn btn-secondary" data-add-collection="tasks">작업 추가</button>
      </div>
      <p class="field-hint">프로젝트 전체 소개보다 더 구체적인 작업 단위 기여를 적으면 AI 문구와 문서 품질이 훨씬 좋아집니다.</p>
      <div class="repeat-list">${renderTaskItems()}</div>
    </section>

    <section class="studio-panel">
      <div class="collection-toolbar">
        <div>
          <p class="eyebrow">Features</p>
          <h3>핵심 기능</h3>
        </div>
        <button type="button" class="btn btn-secondary" data-add-collection="features">핵심 기능 추가</button>
      </div>
      <div class="repeat-list">${renderFeatureItems()}</div>
    </section>
  `;
}

function renderStackGroup(title, path, items) {
  return `
    <section class="studio-panel">
      <div class="collection-toolbar">
        <div>
          <p class="eyebrow">Tech Stack</p>
          <h3>${escHtml(title)}</h3>
        </div>
        <button type="button" class="btn btn-secondary" data-add-collection="${escHtml(path)}">항목 추가</button>
      </div>
      <div class="repeat-list">
        ${items.length ? items.map((item, index) => `
          <article class="repeat-item">
            ${renderRepeatHeader(item.name || `${title} ${index + 1}`, `${title} ${index + 1}`, path, index)}
            ${renderInputField('기술명', `${path}.${index}.name`, item.name, { placeholder: '예: FastAPI' })}
            ${renderTextareaField('선정 이유', `${path}.${index}.reason`, item.reason, { rows: 3, placeholder: '왜 이 기술을 선택했는지 적어주세요.' })}
          </article>
        `).join('') : '<div class="empty-surface">아직 항목이 없습니다.</div>'}
      </div>
    </section>
  `;
}

function renderArchitectureComponents(collectionPath, title, items, fieldsRenderer) {
  return `
    <section class="studio-panel">
      <div class="collection-toolbar">
        <div>
          <p class="eyebrow">Architecture</p>
          <h3>${escHtml(title)}</h3>
        </div>
        <button type="button" class="btn btn-secondary" data-add-collection="${escHtml(collectionPath)}">항목 추가</button>
      </div>
      <div class="repeat-list">
        ${items.length ? items.map((item, index) => `
          <article class="repeat-item">
            ${renderRepeatHeader(item.name || item.entity || item.path || `${title} ${index + 1}`, `${title} ${index + 1}`, collectionPath, index)}
            ${fieldsRenderer(item, index)}
          </article>
        `).join('') : '<div class="empty-surface">아직 항목이 없습니다.</div>'}
      </div>
    </section>
  `;
}

function renderComposeArchitectureStep() {
  const detail = state.currentDraft.tech_stack_detail;
  const architecture = state.currentDraft.architecture;
  const pso = state.currentDraft.performance_security_operations;
  return `
    <section class="studio-panel">
      <div class="section-header">
        <p class="eyebrow">Architecture Summary</p>
        <h3>시스템 아키텍처 요약</h3>
        <p>전체 구성과 데이터 흐름을 한 문단으로 설명해두면 이후 다이어그램과 문서 구조가 안정됩니다.</p>
      </div>
      ${renderTextareaField('아키텍처 요약', 'architecture.summary', architecture.summary, { rows: 5, placeholder: '예: CLI와 Web이 공용 서비스 계층을 공유하고, YAML 저장소와 템플릿 렌더링을 중심으로 동작합니다.' })}
    </section>

    <div class="compose-card-grid">
      ${renderStackGroup('Frontend', 'tech_stack_detail.frontend', detail.frontend)}
      ${renderStackGroup('Backend', 'tech_stack_detail.backend', detail.backend)}
      ${renderStackGroup('Database', 'tech_stack_detail.database', detail.database)}
      ${renderStackGroup('Infra', 'tech_stack_detail.infra', detail.infra)}
      ${renderStackGroup('Tools', 'tech_stack_detail.tools', detail.tools)}
    </div>

    <div class="compose-card-grid">
      ${renderArchitectureComponents('architecture.components', '구성 요소', architecture.components, (item, index) => `
        ${renderInputField('컴포넌트명', `architecture.components.${index}.name`, item.name, { placeholder: '예: AI Service' })}
        ${renderTextareaField('역할', `architecture.components.${index}.role`, item.role, { rows: 3 })}
      `)}
      ${renderArchitectureComponents('architecture.data_model', '데이터 모델', architecture.data_model, (item, index) => `
        ${renderInputField('엔터티', `architecture.data_model.${index}.entity`, item.entity, { placeholder: '예: Project' })}
        ${renderListField('주요 필드', `architecture.data_model.${index}.fields`, item.fields, { rows: 3 })}
      `)}
    </div>

    ${renderArchitectureComponents('architecture.api_examples', 'API 예시', architecture.api_examples, (item, index) => `
      <div class="field-grid">
        ${renderInputField('메서드', `architecture.api_examples.${index}.method`, item.method, { placeholder: 'GET' })}
        ${renderInputField('경로', `architecture.api_examples.${index}.path`, item.path, { placeholder: '/api/projects' })}
      </div>
      ${renderTextareaField('목적', `architecture.api_examples.${index}.purpose`, item.purpose, { rows: 3 })}
    `)}

    <section class="studio-panel">
      <div class="section-header">
        <p class="eyebrow">Operations</p>
        <h3>성능, 보안, 운영 고려사항</h3>
        <p>품질 관점에서 어떤 고려를 했는지 적으면 포트폴리오가 기능 소개를 넘어 설계 사례로 읽힙니다.</p>
      </div>
      <div class="compose-card-grid">
        ${renderListField('성능', 'performance_security_operations.performance', pso.performance, { rows: 4 })}
        ${renderListField('보안', 'performance_security_operations.security', pso.security, { rows: 4 })}
      </div>
      ${renderListField('운영', 'performance_security_operations.operations', pso.operations, { rows: 4 })}
    </section>
  `;
}

function renderProblemSolvingCases() {
  const items = state.currentDraft.problem_solving_cases;
  if (!items.length) {
    return '<div class="empty-surface">아직 문제 해결 사례가 없습니다. 문제 상황 → 원인 → 해결 방식 → 기술적 판단 → 결과 흐름으로 적어보세요.</div>';
  }
  return items.map((item, index) => `
    <article class="repeat-item">
      ${renderRepeatHeader(item.title || `문제 해결 사례 ${index + 1}`, `Case ${index + 1}`, 'problem_solving_cases', index)}
      ${renderInputField('사례 제목', `problem_solving_cases.${index}.title`, item.title, { placeholder: '예: 동적 모델 선택과 404 대응' })}
      ${renderTextareaField('문제 상황', `problem_solving_cases.${index}.situation`, item.situation, { rows: 3 })}
      ${renderTextareaField('원인', `problem_solving_cases.${index}.cause`, item.cause, { rows: 3 })}
      ${renderTextareaField('내가 한 행동', `problem_solving_cases.${index}.action`, item.action, { rows: 3 })}
      ${renderTextareaField('기술적 판단 이유', `problem_solving_cases.${index}.decision_reason`, item.decision_reason, { rows: 3 })}
      <div class="field-grid">
        ${renderTextareaField('결과', `problem_solving_cases.${index}.result`, item.result, { rows: 3 })}
        ${renderInputField('지표', `problem_solving_cases.${index}.metric`, item.metric, { placeholder: '예: 재배포 의존성 제거' })}
      </div>
      ${renderListField('사용 기술', `problem_solving_cases.${index}.tech_used`, item.tech_used, { rows: 3 })}
    </article>
  `).join('');
}

function renderQuantitativeResults() {
  const items = state.currentDraft.results.quantitative;
  if (!items.length) {
    return '<div class="empty-surface">정량 지표가 없으면 비워둬도 됩니다. 있는 경우에는 before/after를 명확히 적어주세요.</div>';
  }
  return items.map((item, index) => `
    <article class="metric-card">
      ${renderRepeatHeader(item.metric_name || `지표 ${index + 1}`, `Metric ${index + 1}`, 'results.quantitative', index)}
      ${renderInputField('지표명', `results.quantitative.${index}.metric_name`, item.metric_name, { placeholder: '예: 설정 소요 시간' })}
      <div class="field-grid">
        ${renderInputField('개선 전', `results.quantitative.${index}.before`, item.before, { placeholder: '예: 수동 설정 필요' })}
        ${renderInputField('개선 후', `results.quantitative.${index}.after`, item.after, { placeholder: '예: UI에서 즉시 연결' })}
      </div>
      ${renderTextareaField('영향', `results.quantitative.${index}.impact`, item.impact, { rows: 3 })}
    </article>
  `).join('');
}

function renderAssetCollection(path, title, items) {
  return `
    <section class="studio-panel">
      <div class="collection-toolbar">
        <div>
          <p class="eyebrow">Assets</p>
          <h3>${escHtml(title)}</h3>
        </div>
        <button type="button" class="btn btn-secondary" data-add-collection="${escHtml(path)}">자산 추가</button>
      </div>
      <div class="repeat-list">
        ${items.length ? items.map((item, index) => `
          <article class="repeat-item">
            ${renderRepeatHeader(item.title || `${title} ${index + 1}`, `${title} ${index + 1}`, path, index)}
            ${renderInputField('제목', `${path}.${index}.title`, item.title, { placeholder: '예: 포트폴리오 스튜디오 홈 화면' })}
            ${renderTextareaField('설명', `${path}.${index}.description`, item.description, { rows: 3 })}
            ${renderInputField('경로 또는 링크', `${path}.${index}.path`, item.path, { placeholder: '로컬 경로 또는 URL' })}
          </article>
        `).join('') : '<div class="empty-surface">아직 등록된 자산이 없습니다.</div>'}
      </div>
    </section>
  `;
}

function renderComposeAssetsStep() {
  const draft = state.currentDraft;
  return `
    <div class="compose-card-grid">
      <section class="studio-panel">
        <div class="section-header">
          <p class="eyebrow">Links</p>
          <h3>링크 정리</h3>
          <p>GitHub, 배포 링크, 문서 링크, 데모 영상을 정리하면 포트폴리오 활용도가 크게 올라갑니다.</p>
        </div>
        ${renderInputField('GitHub', 'links.github', draft.links.github, { placeholder: 'https://github.com/...', autocomplete: 'url', spellcheck: false })}
        ${renderInputField('데모', 'links.demo', draft.links.demo, { placeholder: 'https://...', autocomplete: 'url', spellcheck: false })}
        ${renderInputField('문서', 'links.docs', draft.links.docs, { placeholder: 'https://...', autocomplete: 'url', spellcheck: false })}
        ${renderInputField('영상', 'links.video', draft.links.video, { placeholder: 'https://...', autocomplete: 'url', spellcheck: false })}
      </section>

      <section class="studio-panel">
        <div class="collection-toolbar">
          <div>
            <p class="eyebrow">Results</p>
            <h3>결과와 성과</h3>
          </div>
          <button type="button" class="btn btn-secondary" data-add-collection="results.quantitative">정량 지표 추가</button>
        </div>
        ${renderListField('정성적 성과', 'results.qualitative', draft.results.qualitative, { rows: 4 })}
        <div class="metric-grid">${renderQuantitativeResults()}</div>
      </section>
    </div>

    <section class="studio-panel">
      <div class="collection-toolbar">
        <div>
          <p class="eyebrow">Problem Solving Cases</p>
          <h3>주요 문제 해결 사례</h3>
        </div>
        <button type="button" class="btn btn-secondary" data-add-collection="problem_solving_cases">문제 해결 사례 추가</button>
      </div>
      <div class="repeat-list">${renderProblemSolvingCases()}</div>
    </section>

    <div class="compose-card-grid">
      <section class="studio-panel">
        <div class="section-header">
          <p class="eyebrow">Retrospective</p>
          <h3>회고</h3>
          <p>무엇이 잘 됐고, 무엇이 어려웠고, 무엇을 배웠는지 정리하면 면접 설명 포인트가 생깁니다.</p>
        </div>
        ${renderListField('잘한 점', 'retrospective.what_went_well', draft.retrospective.what_went_well, { rows: 3 })}
        ${renderListField('어려웠던 점', 'retrospective.what_was_hard', draft.retrospective.what_was_hard, { rows: 3 })}
        ${renderListField('배운 점', 'retrospective.what_i_learned', draft.retrospective.what_i_learned, { rows: 3 })}
        ${renderListField('다음 단계', 'retrospective.next_steps', draft.retrospective.next_steps, { rows: 3 })}
      </section>
      ${renderAssetCollection('assets.screenshots', '스크린샷', draft.assets.screenshots)}
    </div>

    ${renderAssetCollection('assets.diagrams', '다이어그램', draft.assets.diagrams)}
  `;
}

function renderComposeReviewStep() {
  const draft = state.currentDraft;
  const completeness = draftCompleteness();
  return `
    <div class="compose-card-grid">
      <section class="studio-panel">
        <div class="section-header">
          <p class="eyebrow">Readiness Check</p>
          <h3>저장 전 핵심 점검</h3>
          <p>아래 항목이 채워졌다면 포트폴리오 문서로 렌더링했을 때 읽을 만한 품질에 근접합니다.</p>
        </div>
        <ul class="ghost-list">
          <li>프로젝트명: ${draft.name ? '완료' : '필요'}</li>
          <li>역할/기간: ${draft.role && draft.period.start ? '완료' : '보강 권장'}</li>
          <li>문제 정의: ${completeness.problem ? '완료' : '필요'}</li>
          <li>작업/기여: ${completeness.work ? '완료' : '필요'}</li>
          <li>기술·아키텍처: ${completeness.architecture ? '완료' : '보강 권장'}</li>
          <li>성과/회고: ${completeness.assets ? '완료' : '보강 권장'}</li>
        </ul>
      </section>

      <section class="studio-panel">
        <div class="section-header">
          <p class="eyebrow">Draft Snapshot</p>
          <h3>현재 초안 요약</h3>
          <p>저장하면 Library에서 다시 불러와 프로젝트 단위로 반복 개선할 수 있습니다.</p>
        </div>
        <div class="detail-copy">
          <h4>${escHtml(draft.name || '새 포트폴리오 초안')}</h4>
          <p>${escHtml(draft.one_line_summary || draft.summary || '프로젝트 소개가 아직 없습니다.')}</p>
          <p>역할: ${escHtml(draft.role || '미입력')} · 팀 규모: ${escHtml(String(draft.team_size || 1))}명</p>
          <p>작업 ${draft.tasks.length}개 · 기능 ${draft.features.length}개 · 문제 해결 사례 ${draft.problem_solving_cases.length}개</p>
          <p>${state.loadedProjectId ? '기존 저장 프로젝트를 업데이트합니다.' : '새 프로젝트로 저장됩니다.'}</p>
        </div>
      </section>
    </div>

    <section class="studio-panel">
      <div class="section-header">
        <p class="eyebrow">What Happens Next</p>
        <h3>다음 흐름</h3>
        <p>저장한 뒤에는 Library에서 문구를 반복 생성하고, Preview에서 문서 결과를 검토한 다음 바로 파일로 내보낼 수 있습니다.</p>
      </div>
      <div class="status-pills">
        <span class="status-pill">1. 현재 초안 저장</span>
        <span class="status-pill">2. 문서 미리보기 갱신</span>
        <span class="status-pill">3. 포맷 선택 후 내보내기</span>
      </div>
    </section>
  `;
}

function renderProjects() {
  const library = document.getElementById('projects-library');
  if (!library) return;
  if (!state.projects.length) {
    library.innerHTML = '<div class="empty-surface">저장된 프로젝트가 없습니다. Compose 화면에서 초안을 저장하면 이곳에 카드가 쌓입니다.</div>';
    renderProjectsDetail();
    renderSavedProjectChecklist();
    return;
  }

  library.innerHTML = state.projects.map(project => `
    <article class="project-item ${project.id === state.loadedProjectId ? 'selected' : ''}">
      <div>
        <h4>${escHtml(project.name)}</h4>
        <p>${escHtml(project.one_line_summary || project.summary || '프로젝트 소개가 아직 없습니다.')}</p>
        <small>${escHtml(project.role || '역할 미입력')} · ${escHtml(project.tech_stack?.join(', ') || '기술 스택 없음')}</small>
      </div>
      <div class="inline-actions">
        <button type="button" class="btn btn-ghost" data-project-action="load" data-project-id="${escHtml(project.id)}">다시 열기</button>
        <button type="button" class="btn btn-ghost" data-project-action="summary" data-project-id="${escHtml(project.id)}">소개 문단 재생성</button>
        <button type="button" class="btn btn-ghost" data-project-action="tasks" data-project-id="${escHtml(project.id)}">작업 문구 재생성</button>
        <button type="button" class="btn btn-ghost danger" data-project-action="delete" data-project-id="${escHtml(project.id)}">삭제</button>
      </div>
    </article>
  `).join('');

  renderProjectsDetail();
  renderSavedProjectChecklist();
}

function renderProjectsDetail(project = null) {
  const detail = document.getElementById('projects-detail');
  if (!detail) return;
  const current = project || state.projects.find(item => item.id === state.loadedProjectId) || state.projects[0];
  if (!current) {
    detail.textContent = '저장된 프로젝트가 아직 없습니다. Compose 화면에서 초안을 저장하세요.';
    return;
  }

  detail.innerHTML = `
    <h4>${escHtml(current.name)}</h4>
    <p>${escHtml(current.one_line_summary || current.summary || '프로젝트 소개가 아직 없습니다.')}</p>
    <p>문제 정의: ${escHtml(current.overview?.problem || '아직 입력되지 않았습니다.')}</p>
    <p>핵심 기술: ${escHtml(current.tech_stack?.join(', ') || '기술 스택이 아직 없습니다.')}</p>
    <p>작업 ${current.tasks?.length || 0}개 · 문제 해결 사례 ${current.problem_solving_cases?.length || 0}개</p>
    <div class="action-row">
      <button type="button" class="btn btn-secondary" data-project-action="load" data-project-id="${escHtml(current.id)}">Compose에서 수정</button>
      <button type="button" class="btn btn-primary" data-home-project-action="preview" data-project-id="${escHtml(current.id)}">문서 미리보기</button>
    </div>
  `;
}

function renderPreviewControls() {
  const docType = state.preview.docType;
  const supportedFormats = docType === 'resume'
    ? ['html', 'md', 'pdf', 'docx', 'json', 'csv']
    : ['html', 'md', 'pdf', 'csv'];
  if (!supportedFormats.includes(state.preview.format)) {
    state.preview.format = supportedFormats[0];
  }

  document.getElementById('preview-doc-type').value = docType;
  document.getElementById('preview-source').value = state.preview.source;
  document.getElementById('preview-template').value = state.preview.template;

  const formatSelect = document.getElementById('preview-format');
  formatSelect.innerHTML = supportedFormats
    .map(format => `<option value="${format}" ${format === state.preview.format ? 'selected' : ''}>${format}</option>`)
    .join('');

  renderSavedProjectChecklist();
  renderPreviewBadges();
}

function renderSavedProjectChecklist() {
  const container = document.getElementById('preview-saved-projects');
  if (!container) return;
  const isSavedSource = state.preview.source === 'saved';
  container.classList.toggle('disabled', !isSavedSource);
  if (!state.projects.length) {
    container.innerHTML = '<div class="empty-surface">저장된 프로젝트가 없습니다.</div>';
    return;
  }

  const selectedIds = new Set(state.preview.projectIds);
  container.innerHTML = state.projects.map(project => `
    <label class="selection-item">
      <input type="checkbox" value="${escHtml(project.id)}" ${selectedIds.has(project.id) ? 'checked' : ''} ${!isSavedSource ? 'disabled' : ''} />
      <span>
        <strong>${escHtml(project.name)}</strong>
        <small>${escHtml(project.one_line_summary || project.role || project.organization || project.type)}</small>
      </span>
    </label>
  `).join('');
}

function renderPreviewBadges() {
  const container = document.getElementById('preview-badges');
  if (!container) return;
  const badges = [
    `문서: ${state.preview.docType}`,
    `소스: ${state.preview.source === 'draft' ? '현재 초안' : '저장된 프로젝트'}`,
    `템플릿: ${state.preview.template}`,
    `포맷: ${state.preview.format}`,
    `선택 프로젝트: ${state.preview.source === 'saved' ? state.preview.projectIds.length : 1}개`,
  ];
  container.innerHTML = badges.map(badge => `<span class="status-pill">${escHtml(badge)}</span>`).join('');
}

function renderPreviewOutput() {
  const output = document.getElementById('preview-output');
  const meta = document.getElementById('preview-meta');
  if (!output || !meta) return;
  if (!state.lastPreview) {
    output.innerHTML = '<div class="empty-surface">문서 미리보기를 생성하면 이 영역에 결과가 표시됩니다.</div>';
    meta.textContent = '아직 생성된 미리보기가 없습니다.';
    return;
  }
  output.innerHTML = state.lastPreview.html;
  meta.textContent = `${state.lastPreview.doc_type} · ${state.lastPreview.project_count}개 프로젝트 · 템플릿: ${state.lastPreview.template}`;
  renderMermaidDiagrams(output).catch(error => console.warn('Preview mermaid render failed', error));
}

function syncPreviewState() {
  state.preview.docType = document.getElementById('preview-doc-type').value;
  state.preview.source = document.getElementById('preview-source').value;
  state.preview.template = document.getElementById('preview-template').value;
  state.preview.format = document.getElementById('preview-format').value;
  renderPreviewControls();
}

function buildPreviewPayload() {
  syncPreviewState();
  if (state.preview.source === 'draft') {
    return {
      source: 'draft',
      draft_project: normalizeDraft(state.currentDraft),
      project_ids: [],
      template: state.preview.template,
      format: state.preview.format,
    };
  }
  return {
    source: 'saved',
    draft_project: null,
    project_ids: state.preview.projectIds,
    template: state.preview.template,
    format: state.preview.format,
  };
}

async function renderPreview() {
  syncPreviewState();
  const button = document.getElementById('btn-preview-render');
  await runUserAction(button, '렌더링 중…', async () => {
    const payload = buildPreviewPayload();
    const result = await apiPost(`/api/preview/${state.preview.docType}`, payload);
    state.lastPreview = result;
    renderPreviewOutput();
    renderPreviewBadges();
    showToast('문서 미리보기를 갱신했습니다.');
  }, {
    title: '미리보기 생성 실패',
    toastMessage: '미리보기 생성에 실패했습니다.',
    fallbackMessage: '미리보기를 생성하지 못했습니다.',
  });
}

async function exportPreview() {
  syncPreviewState();
  const button = document.getElementById('btn-preview-export');
  await runUserAction(button, '내보내는 중…', async () => {
    const payload = buildPreviewPayload();
    const result = await apiPost(`/api/export/${state.preview.docType}`, payload);
    showToast(`내보내기 완료: ${result.path}`);
    const meta = document.getElementById('preview-meta');
    meta.innerHTML = '';
    const info = document.createElement('span');
    info.textContent = `내보내기 완료 · ${result.format} · ${result.path}`;
    meta.appendChild(info);
    const openBtn = document.createElement('button');
    openBtn.className = 'btn btn-secondary';
    openBtn.style.marginLeft = '10px';
    openBtn.textContent = '출력 폴더 열기';
    openBtn.onclick = async () => {
      try {
        await apiPost(`/api/fs/open-folder?path=${encodeURIComponent(result.folder || result.path)}`);
      } catch (error) {
        if (error.status === 501) {
          await navigator.clipboard.writeText(result.folder || result.path).catch(() => {});
          showToast(`이 환경에서는 자동으로 열 수 없습니다. 경로를 클립보드에 복사했습니다: ${result.folder || result.path}`);
        } else {
          showToast(`폴더를 열 수 없습니다: ${error.message}`, 'error');
        }
      }
    };
    meta.appendChild(openBtn);
  }, {
    title: '내보내기 실패',
    toastMessage: '내보내기에 실패했습니다.',
    fallbackMessage: '문서를 내보내지 못했습니다.',
  });
}

function applyConfigToForms() {
  if (!state.config) return;
  const { user, export: exportConfig, sync, general } = state.config;
  document.getElementById('user-name').value = user.name || '';
  document.getElementById('user-email').value = user.email || '';
  document.getElementById('user-github').value = user.github || '';
  document.getElementById('user-blog').value = user.blog || '';

  document.getElementById('export-format').value = exportConfig.default_format || 'md';
  document.getElementById('export-template').value = exportConfig.default_template || 'default';
  document.getElementById('export-output-dir').value = exportConfig.output_dir || '';

  document.getElementById('sync-enabled').checked = !!sync.enabled;
  document.getElementById('sync-repo').value = sync.repo_url || '';
  document.getElementById('sync-branch').value = sync.branch || 'main';

  document.getElementById('general-lang').value = general.default_language || 'ko';
  document.getElementById('general-tz').value = general.timezone || 'Asia/Seoul';
  document.getElementById('preview-template').value = exportConfig.default_template || 'default';
  state.preview.template = exportConfig.default_template || 'default';

  const providerSelect = document.getElementById('general-provider');
  providerSelect.value = general.default_ai_provider || '';

  const defaultProvider = general.default_ai_provider;
  if (defaultProvider) {
    const aiNameEl = document.getElementById('ai-name');
    if (aiNameEl) aiNameEl.value = defaultProvider;
    syncProviderForm();
    const savedProvider = (state.config.ai_providers || []).find(item => item.name === defaultProvider);
    const displayModel = savedProvider?.display_model || savedProvider?.model || '';
    if (displayModel) {
      const modelEl = document.getElementById('ai-model');
      if (modelEl && ![...modelEl.options].some(option => option.value === displayModel)) {
        const option = document.createElement('option');
        option.value = displayModel;
        option.textContent = modelLabelForProvider(defaultProvider, displayModel);
        modelEl.appendChild(option);
      }
      if (modelEl) modelEl.value = displayModel;
    }
  }
}

function populateProviders() {
  const providers = state.config?.ai_providers || [];
  const generalProvider = document.getElementById('general-provider');
  if (generalProvider) {
    generalProvider.innerHTML = '<option value="">자동 선택</option>' + providers
      .map(provider => `<option value="${escHtml(provider.name)}">${escHtml(provider.name)} · ${escHtml(providerModelSummary(provider))}</option>`)
      .join('');
    generalProvider.value = state.config?.general?.default_ai_provider || '';
  }

  const providerList = document.getElementById('provider-list');
  if (providerList) {
    if (!providers.length) {
      providerList.innerHTML = '<div class="empty-surface">등록된 AI가 없습니다. 수동으로 초안을 작성하고 문서 미리보기는 계속 사용할 수 있습니다.</div>';
    } else {
      providerList.innerHTML = providers.map(provider => `
        <article class="provider-item">
          <div>
            <strong>${escHtml(provider.name)}</strong>
            <p>저장 모델: ${escHtml(provider.display_model || provider.model || '-')}</p>
            <p>실제 생성 모델: ${escHtml(provider.generation_model || '-')}</p>
            <small>${escHtml(provider.key_masked)}${provider.is_default ? ' · 기본 제공자' : ''}</small>
            ${provider.generation_warning ? `<small class="provider-warning">${escHtml(provider.generation_warning)}</small>` : ''}
          </div>
          <div class="inline-actions">
            <button type="button" class="btn btn-ghost" data-provider-action="test" data-provider-name="${escHtml(provider.name)}">연결 테스트</button>
            <button type="button" class="btn btn-ghost danger" data-provider-action="remove" data-provider-name="${escHtml(provider.name)}">삭제</button>
          </div>
        </article>
      `).join('');
    }
  }

  updateScanProviderWarning();
}

function syncProviderForm() {
  const select = document.getElementById('ai-name');
  const apiField = document.getElementById('field-api-key');
  const baseUrlField = document.getElementById('field-base-url');
  if (!select || !apiField || !baseUrlField) return;
  const isOllama = select.value === 'ollama';
  const isBuiltin = select.value === 'pollinations';
  apiField.classList.toggle('hidden', isOllama || isBuiltin);
  baseUrlField.classList.toggle('hidden', !isOllama);
}

function resetModelSelect() {
  const modelSelect = document.getElementById('ai-model');
  if (modelSelect) {
    modelSelect.innerHTML = '<option value="">-- API 키 입력 후 모델 목록 불러오기 --</option>';
  }
}

async function loadModelsForProvider() {
  const provider = document.getElementById('ai-name')?.value;
  const apiKey = document.getElementById('ai-key')?.value?.trim();
  const baseUrl = document.getElementById('ai-base-url')?.value?.trim();
  const modelSelect = document.getElementById('ai-model');
  const loadBtn = document.getElementById('btn-load-models');
  if (!modelSelect || !provider) return;

  const isOllama = provider === 'ollama';
  const isBuiltin = provider === 'pollinations';
  const hasSavedKey = state.config?.ai_providers?.some(item => item.name === provider);
  if (!apiKey && !hasSavedKey && !isOllama && !isBuiltin) {
    resetModelSelect();
    showToast('API 키를 먼저 입력하세요.', 'error');
    return;
  }

  const params = new URLSearchParams({ provider });
  if (apiKey) params.set('api_key', apiKey);
  if (baseUrl) params.set('base_url', baseUrl);

  const prevLabel = loadBtn?.textContent;
  if (loadBtn) {
    loadBtn.textContent = '…';
    loadBtn.disabled = true;
  }
  modelSelect.innerHTML = '<option value="">불러오는 중…</option>';

  try {
    const data = await apiGet(`/api/models?${params}`);
    const models = data.models || [];
    if (!models.length) {
      modelSelect.innerHTML = '<option value="">사용 가능한 모델 없음</option>';
      return;
    }
    const savedModel = (state.config?.ai_providers || []).find(item => item.name === provider)?.display_model || '';
    const defaultModel = savedModel || DEFAULT_MODELS[provider] || '';
    modelSelect.innerHTML = models.map(model => {
      const label = modelLabelForProvider(provider, model.id);
      const suffix = model.generation_status === 'fallback'
        ? ` · 생성 시 ${model.generation_model}`
        : model.generation_status === 'unavailable'
          ? ' · 생성 비권장'
          : '';
      return `<option value="${escHtml(model.id)}"${model.id === defaultModel ? ' selected' : ''}>${escHtml(label + suffix)}</option>`;
    }).join('');
  } catch (error) {
    const message = error?.message || '';
    let hint = '목록 불러오기 실패';
    if (message.includes('400') || message.includes('API key')) hint = 'API 키가 올바르지 않습니다.';
    else if (message.includes('429') || message.includes('quota') || message.includes('RESOURCE_EXHAUSTED')) hint = 'quota 초과로 잠시 후 다시 시도해야 합니다.';
    else if (message.includes('401') || message.includes('403')) hint = 'API 키 권한 오류입니다.';
    modelSelect.innerHTML = `<option value="">${escHtml(hint)}</option>`;
    showToast(hint, 'error');
  } finally {
    if (loadBtn) {
      loadBtn.textContent = prevLabel;
      loadBtn.disabled = false;
    }
  }
}

async function handleNewDraft() {
  if (state.ui.dirty) {
    const confirmed = await confirmAction({
      title: '새 포트폴리오를 시작할까요?',
      message: '저장하지 않은 변경사항이 있습니다.\n새 초안을 시작하면 현재 작업 중인 초안 내용은 저장되지 않습니다.',
      confirmLabel: '새로 시작',
    });
    if (!confirmed) return;
  }

  state.currentDraft = emptyDraft();
  state.loadedProjectId = '';
  state.lastPreview = null;
  resetDraftDirty();
  clearInlineComposeError();
  state.ui.fieldErrors = {};
  await switchScreen('compose', { force: true });
  setComposeStep('input');
  showToast('새 포트폴리오 초안을 시작했습니다.');
}

function startManualDraft() {
  state.currentDraft = normalizeDraft({
    ...state.currentDraft,
    raw_text: document.getElementById('intake-raw-text')?.value.trim() || state.currentDraft.raw_text,
  });
  state.loadedProjectId = '';
  markDraftDirty();
  setComposeStep('basics');
  showToast('빈 구조의 초안을 열었습니다.');
}

async function handleIntakeGenerate() {
  const button = document.getElementById('btn-intake-generate');
  const rawText = document.getElementById('intake-raw-text')?.value.trim();
  if (!rawText) {
    showToast('원본 텍스트를 먼저 붙여넣으세요.', 'error');
    return;
  }

  await runUserAction(button, '초안 생성 중…', async () => {
    const result = await apiPost('/api/intake/project-draft', {
      raw_text: rawText,
      lang: getCurrentLanguageSelection(),
      provider: getCurrentProviderSelection(),
    });
    state.currentDraft = normalizeDraft(result.draft);
    state.loadedProjectId = '';
    state.ui.fieldErrors = {};
    markDraftDirty();
    setComposeStep('basics');
    renderCompose();
    showToast('AI 초안을 생성했습니다. 이제 단계별로 내용을 보강해보세요.');
  }, {
    title: 'AI 초안 생성 실패',
    toastMessage: '초안 생성에 실패했습니다.',
    fallbackMessage: 'AI 초안을 생성하지 못했습니다.',
  });
}

async function handleDraftSummary() {
  const button = document.querySelector('[data-compose-action="summary"]');
  await runUserAction(button, '생성 중…', async () => {
    const result = await apiPost('/api/draft/generate-summary', {
      draft: normalizeDraft(state.currentDraft),
      lang: getCurrentLanguageSelection(),
      provider: getCurrentProviderSelection(),
    });
    state.currentDraft = normalizeDraft(result.draft);
    markDraftDirty();
    renderCompose();
    showToast('프로젝트 소개 문단을 생성했습니다.');
  }, {
    title: '프로젝트 소개 생성 실패',
    toastMessage: '소개 문단 생성에 실패했습니다.',
    fallbackMessage: '프로젝트 소개 문단을 생성하지 못했습니다.',
  });
}

async function handleDraftTaskBullets() {
  const button = document.querySelector('[data-compose-action="tasks"]');
  await runUserAction(button, '생성 중…', async () => {
    const result = await apiPost('/api/draft/generate-task-bullets', {
      draft: normalizeDraft(state.currentDraft),
      lang: getCurrentLanguageSelection(),
      provider: getCurrentProviderSelection(),
    });
    state.currentDraft = normalizeDraft(result.draft);
    markDraftDirty();
    renderCompose();
    showToast('작업 항목 문구를 생성했습니다.');
  }, {
    title: '작업 항목 생성 실패',
    toastMessage: '작업 항목 생성에 실패했습니다.',
    fallbackMessage: '작업 항목을 생성하지 못했습니다.',
  });
}

function validateDraftForSave() {
  state.ui.fieldErrors = {};
  if (!state.currentDraft.name.trim()) {
    setFieldError('name', '프로젝트명은 필수입니다.');
  }
  if (!state.currentDraft.role.trim()) {
    setFieldError('role', '역할을 적어두면 문서 품질이 더 좋아집니다.');
  }
  if (!state.currentDraft.summary.trim() && !state.currentDraft.one_line_summary.trim()) {
    setInlineComposeError('한 줄 소개 또는 프로젝트 소개 문단 중 하나는 먼저 채워두는 것을 권장합니다.');
  } else {
    clearInlineComposeError();
  }
  return !state.ui.fieldErrors.name;
}

async function handleDraftSave() {
  if (!validateDraftForSave()) {
    showToast('저장 전에 필수 항목을 확인하세요.', 'error');
    setComposeStep('basics');
    renderCompose();
    return;
  }

  const button = document.getElementById('btn-draft-save');
  await runUserAction(button, '저장 중…', async () => {
    const draft = normalizeDraft(state.currentDraft);
    const result = state.loadedProjectId
      ? await apiPut(`/api/projects/${encodeURIComponent(state.loadedProjectId)}`, draft)
      : await apiPost('/api/projects', draft);

    state.currentDraft = normalizeDraft(result.project);
    state.loadedProjectId = result.project.id;
    upsertProject(result.project);
    resetDraftDirty();
    renderShell();
    showToast('프로젝트를 저장했습니다.');
  }, {
    title: '프로젝트 저장 실패',
    toastMessage: '저장에 실패했습니다.',
    fallbackMessage: '프로젝트를 저장하지 못했습니다.',
  });
}

function upsertProject(project) {
  const index = state.projects.findIndex(item => item.id === project.id);
  if (index >= 0) state.projects[index] = project;
  else state.projects.unshift(project);
  if (!state.preview.projectIds.includes(project.id)) {
    state.preview.projectIds.push(project.id);
  }
}

async function loadProjectIntoCompose(project) {
  state.currentDraft = normalizeDraft(project);
  state.loadedProjectId = project.id;
  resetDraftDirty();
  clearInlineComposeError();
  state.ui.fieldErrors = {};
  await switchScreen('compose', { force: true });
  setComposeStep('basics');
  showToast(`${project.name} 프로젝트를 다시 열었습니다.`);
}

async function handleProjectLibraryClick(event) {
  const button = event.target.closest('[data-project-action]');
  if (!button) return;
  const projectId = button.dataset.projectId;
  const action = button.dataset.projectAction;
  const project = state.projects.find(item => item.id === projectId);
  if (!project) return;

  if (action === 'load') {
    await loadProjectIntoCompose(project);
    return;
  }

  if (action === 'delete') {
    const confirmed = await confirmAction({
      title: '프로젝트를 삭제할까요?',
      message: `'${project.name}' 프로젝트를 라이브러리에서 제거합니다.\n저장된 데이터가 삭제되며 되돌릴 수 없습니다.`,
      confirmLabel: '삭제',
    });
    if (!confirmed) return;

    await runUserAction(button, '삭제 중…', async () => {
      await apiDelete(`/api/projects/${encodeURIComponent(project.id)}`);
      state.projects = state.projects.filter(item => item.id !== project.id);
      state.preview.projectIds = state.preview.projectIds.filter(id => id !== project.id);
      if (state.loadedProjectId === project.id) {
        state.loadedProjectId = '';
      }
      renderProjects();
      renderHome();
      renderPreviewControls();
      showToast('프로젝트를 삭제했습니다.');
    }, {
      title: '프로젝트 삭제 실패',
      toastMessage: '삭제에 실패했습니다.',
      fallbackMessage: '프로젝트를 삭제하지 못했습니다.',
    });
    return;
  }

  if (action === 'summary' || action === 'tasks') {
    const endpoint = action === 'summary'
      ? `/api/projects/${encodeURIComponent(project.id)}/generate-summary`
      : `/api/projects/${encodeURIComponent(project.id)}/generate-task-bullets`;
    const busyLabel = action === 'summary' ? '생성 중…' : '재정리 중…';

    await runUserAction(button, busyLabel, async () => {
      const result = await apiPost(endpoint, {
        lang: getCurrentLanguageSelection(),
        provider: getCurrentProviderSelection(),
      });
      const updated = normalizeDraft(result.project);
      upsertProject(updated);
      if (state.loadedProjectId === updated.id) {
        state.currentDraft = updated;
        resetDraftDirty();
      }
      renderShell();
      showToast(action === 'summary' ? '소개 문단을 갱신했습니다.' : '작업 문구를 갱신했습니다.');
    }, {
      title: action === 'summary' ? '프로젝트 소개 갱신 실패' : '작업 문구 갱신 실패',
      toastMessage: action === 'summary' ? '소개 문단 갱신에 실패했습니다.' : '작업 문구 갱신에 실패했습니다.',
      fallbackMessage: action === 'summary' ? '프로젝트 소개를 갱신하지 못했습니다.' : '작업 문구를 갱신하지 못했습니다.',
    });
  }
}

function handlePreviewProjectSelection(event) {
  const checkbox = event.target;
  if (!(checkbox instanceof HTMLInputElement)) return;
  const selected = Array.from(document.querySelectorAll('#preview-saved-projects input[type="checkbox"]:checked')).map(input => input.value);
  state.preview.projectIds = selected;
  renderPreviewBadges();
}

async function handleGitScan() {
  const button = document.getElementById('btn-scan-run');
  const repoPath = document.getElementById('scan-repo-path')?.value.trim();
  const authorEmail = document.getElementById('scan-author-email')?.value.trim() || null;
  const refresh = document.getElementById('scan-refresh')?.checked || false;
  const analyze = document.getElementById('scan-analyze')?.checked || false;
  const lang = document.getElementById('scan-lang')?.value || 'ko';
  const provider = document.getElementById('scan-provider')?.value || null;

  if (!repoPath) {
    showToast('저장소 경로를 입력하세요.', 'error');
    return;
  }

  if (isRemoteRepoInput(repoPath)) {
    const message = buildScanErrorMessage(repoPath);
    renderScanError(message);
    showToast('GitHub URL은 바로 분석할 수 없습니다.', 'error');
    showErrorDialog('Git 분석 실패', message);
    return;
  }

  const busyLabel = analyze ? 'AI 분석 중…' : '분석 중…';
  await runUserAction(button, busyLabel, async () => {
    const result = await apiPost('/api/scan/git', {
      repo_path: repoPath,
      author_email: authorEmail,
      refresh,
      analyze,
      lang,
      provider: provider || null,
    });

    state.lastScanPayload = result.payload;
    const resultEl = document.getElementById('scan-result');
    const actionsEl = document.getElementById('scan-load-actions');
    const payload = result.payload;
    const metrics = payload.scan_metrics || {};
    const cacheNote = result.cached ? ' (이전 결과 재사용)' : '';
    const analyzeNote = result.analyzed ? ' · AI 상세 분석 완료' : '';

    if (resultEl) {
      resultEl.innerHTML = `
        <dl class="scan-summary">
          <dt>프로젝트명</dt><dd>${escHtml(payload.name || '-')}</dd>
          <dt>기간</dt><dd>${escHtml(payload.period_start || '-')} ~ ${escHtml(payload.period_end || '현재')}</dd>
          <dt>커밋</dt><dd>${metrics.commit_count ?? '-'}건 / 내 커밋 ${((metrics.authorship_ratio ?? 0) * 100).toFixed(0)}%</dd>
          <dt>변경</dt><dd>+${metrics.insertions ?? 0} / -${metrics.deletions ?? 0} LOC, ${metrics.files_touched ?? 0}파일</dd>
          <dt>언어</dt><dd>${escHtml(Object.keys(metrics.languages || {}).join(', ') || '-')}</dd>
          <dt>요약</dt><dd>${escHtml(payload.summary || '-')}</dd>
          <dt>작업 수</dt><dd>${(payload.tasks || []).length}개${cacheNote}${analyzeNote}</dd>
        </dl>
      `;
    }
    if (actionsEl) actionsEl.style.display = '';

    const toastMsg = result.analyzed
      ? `AI 분석 완료: ${payload.name || '프로젝트'}`
      : `분석 완료: ${payload.name || '프로젝트'}${cacheNote}`;
    showToast(toastMsg);
  }, {
    title: 'Git 분석 실패',
    toastMessage: 'Git 분석에 실패했습니다.',
    fallbackMessage: 'Git 분석 중 오류가 발생했습니다.',
    messageBuilder: baseMessage => buildScanErrorMessage(repoPath, baseMessage),
    onError: message => renderScanError(message),
  });
}

function handleScanLoadDraft() {
  if (!state.lastScanPayload) return;
  const payload = state.lastScanPayload;
  const tasks = (payload.tasks || []).map((task, index) => ({
    id: `scan_task_${index + 1}`,
    name: task.name || '',
    period: { start: task.period_start || '', end: task.period_end || '' },
    problem: task.problem || '',
    solution: task.solution || '',
    result: task.result || '',
    tech_used: task.tech_used || [],
    keywords: task.keywords || [],
    ai_generated_text: task.ai_generated_text || '',
  }));

  state.currentDraft = normalizeDraft({
    ...state.currentDraft,
    name: payload.name || '',
    type: payload.type || 'company',
    status: payload.status || 'done',
    organization: payload.organization || '',
    period: { start: payload.period_start || '', end: payload.period_end || '' },
    role: payload.role || '',
    team_size: payload.team_size || 1,
    tech_stack: payload.tech_stack || [],
    one_line_summary: payload.one_line_summary || '',
    summary: payload.summary || '',
    tags: payload.tags || [],
    tasks: tasks.length ? tasks : [emptyTask()],
  });
  state.loadedProjectId = '';
  markDraftDirty();
  setComposeStep('basics');
  renderCompose();
  showToast('분석 결과를 초안으로 불러왔습니다. 이제 내용을 보강해보세요.');
}

function resetModelOptionsAndRefreshInputStep() {
  if (state.ui.screen === 'compose' && state.ui.composeStep === 'input') {
    renderComposeStepContent();
    refreshComposeChrome();
  }
}

function renderInputStateSelect(path, value, options) {
  return `
    <label class="field">
      <span>${escHtml(options.label)}</span>
      <select data-path="${escHtml(path)}">
        ${options.items.map(item => `<option value="${escHtml(item.value)}" ${item.value === value ? 'selected' : ''}>${escHtml(item.label)}</option>`).join('')}
      </select>
    </label>
  `;
}
