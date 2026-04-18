/* DevFolio Portfolio Studio */

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
};

let toastTimer = null;

document.addEventListener('DOMContentLoaded', () => {
  bindTabs();
  bindErrorDialog();
  bindDirectoryDialog();
  bindGlobalActions();
  bindDraftEditors();
  bindSettingsForms();
  bindPreviewControls();
  loadInitialData();
});

function emptyTask() {
  return {
    id: '',
    name: '',
    period: { start: '', end: '' },
    problem: '',
    solution: '',
    result: '',
    tech_used: [],
    keywords: [],
    ai_generated_text: '',
  };
}

function emptyDraft() {
  return {
    id: '',
    name: '',
    type: 'company',
    status: 'done',
    organization: '',
    period: { start: '', end: '' },
    role: '',
    team_size: 1,
    tech_stack: [],
    summary: '',
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
    return value.filter(Boolean);
  }
  if (typeof value === 'string') {
    return value
      .split(',')
      .map(item => item.trim())
      .filter(Boolean);
  }
  return [];
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
  draft.tasks = Array.isArray(draft.tasks) && draft.tasks.length
    ? draft.tasks.map(task => ({
        ...emptyTask(),
        ...task,
        period: {
          start: task?.period?.start || '',
          end: task?.period?.end || '',
        },
        tech_used: normalizeArray(task?.tech_used),
        keywords: normalizeArray(task?.keywords),
      }))
    : [emptyTask()];
  return draft;
}

function escHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
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

function bindErrorDialog() {
  document.getElementById('error-dialog-close')?.addEventListener('click', closeErrorDialog);
  document.querySelectorAll('[data-error-dialog-close]').forEach(element => {
    element.addEventListener('click', closeErrorDialog);
  });
}

function bindDirectoryDialog() {
  document.getElementById('directory-dialog-close')?.addEventListener('click', closeDirectoryDialog);
  document.querySelectorAll('[data-directory-dialog-close]').forEach(element => {
    element.addEventListener('click', closeDirectoryDialog);
  });
  document.getElementById('btn-directory-parent')?.addEventListener('click', () => {
    if (state.scanPicker.parentPath) {
      loadDirectoryDialog(state.scanPicker.parentPath);
    }
  });
  document.getElementById('btn-directory-select')?.addEventListener('click', () => {
    const input = document.getElementById('scan-repo-path');
    input.value = state.scanPicker.currentPath || '';
    closeDirectoryDialog();
    showToast('저장소 경로를 선택했습니다.');
  });
  document.getElementById('btn-scan-pick-dir')?.addEventListener('click', openDirectoryDialog);
}

function showErrorDialog(title, message) {
  const dialog = document.getElementById('error-dialog');
  document.getElementById('error-dialog-title').textContent = title || '오류';
  document.getElementById('error-dialog-message').textContent = message || '요청 처리 중 오류가 발생했습니다.';
  dialog.classList.add('show');
  dialog.setAttribute('aria-hidden', 'false');
}

function closeErrorDialog() {
  const dialog = document.getElementById('error-dialog');
  dialog.classList.remove('show');
  dialog.setAttribute('aria-hidden', 'true');
}

function openDirectoryDialog() {
  const inputPath = document.getElementById('scan-repo-path')?.value.trim();
  const dialog = document.getElementById('directory-dialog');
  dialog.classList.add('show');
  dialog.setAttribute('aria-hidden', 'false');
  loadDirectoryDialog(inputPath || '');
}

function closeDirectoryDialog() {
  const dialog = document.getElementById('directory-dialog');
  dialog.classList.remove('show');
  dialog.setAttribute('aria-hidden', 'true');
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

  currentEl.textContent = state.scanPicker.currentPath || '-';
  parentButton.disabled = !state.scanPicker.parentPath;

  rootsEl.innerHTML = state.scanPicker.roots.map(root => {
    const active = root === state.scanPicker.currentPath ? ' active' : '';
    return `<button type="button" class="directory-root-chip${active}" data-directory-root="${escHtml(root)}">${escHtml(root)}</button>`;
  }).join('');

  rootsEl.querySelectorAll('[data-directory-root]').forEach(button => {
    button.addEventListener('click', () => loadDirectoryDialog(button.dataset.directoryRoot));
  });

  if (!state.scanPicker.entries.length) {
    listEl.innerHTML = '<div class="directory-empty">하위 폴더가 없습니다.</div>';
    return;
  }

  listEl.innerHTML = state.scanPicker.entries.map(entry => `
    <button type="button" class="directory-entry" data-directory-path="${escHtml(entry.path)}">
      <span>
        <span class="directory-entry-name">${escHtml(entry.name)}</span>
        <span class="directory-entry-meta">${escHtml(entry.path)}</span>
      </span>
      ${entry.is_git_repo ? '<span class="directory-entry-badge">Git 저장소</span>' : ''}
    </button>
  `).join('');

  listEl.querySelectorAll('[data-directory-path]').forEach(button => {
    button.addEventListener('click', () => loadDirectoryDialog(button.dataset.directoryPath));
  });
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
      'DevFolio의 Git 분석은 원격 URL을 직접 읽지 않고, 현재 PC에 clone된 Git 저장소 폴더를 스캔합니다.',
      '',
      '해결 방법',
      `- 잘못 입력한 값: ${repoPath}`,
      '- 예시 경로: /Users/yourname/projects/DevFolio',
      '- Docker에서는 위처럼 호스트 경로를 그대로 넣어도 됩니다.',
    ].join('\n');
  }
  return errorMessage || 'Git 분석 중 오류가 발생했습니다.';
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || payload.message || `HTTP ${response.status}`);
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
    body: JSON.stringify(data),
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

async function withButtonState(button, busyLabel, callback) {
  if (!button) {
    return callback();
  }
  const original = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  try {
    await callback();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function bindTabs() {
  document.querySelectorAll('.nav-item').forEach(button => {
    button.addEventListener('click', () => switchTab(button.dataset.tab));
  });
}

function switchTab(tabId) {
  document.querySelectorAll('.nav-item').forEach(button => {
    button.classList.toggle('active', button.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === `tab-${tabId}`);
  });
}

function bindGlobalActions() {
  document.getElementById('btn-intake-generate')?.addEventListener('click', handleIntakeGenerate);
  document.getElementById('btn-intake-manual')?.addEventListener('click', () => {
    const rawText = document.getElementById('intake-raw-text').value.trim();
    state.currentDraft = normalizeDraft({ raw_text: rawText, tasks: [emptyTask()] });
    state.loadedProjectId = '';
    renderDraft();
    showToast('빈 초안을 열었습니다.');
  });

  document.getElementById('btn-new-draft')?.addEventListener('click', () => {
    state.currentDraft = normalizeDraft({ raw_text: document.getElementById('intake-raw-text').value.trim() });
    state.loadedProjectId = '';
    state.lastPreview = null;
    renderDraft();
    renderProjectsDetail();
    renderPreviewOutput();
    showToast('새 초안을 시작했습니다.');
    switchTab('intake');
  });

  document.getElementById('btn-go-preview')?.addEventListener('click', async () => {
    document.getElementById('preview-source').value = 'draft';
    state.preview.source = 'draft';
    switchTab('preview');
    await renderPreview();
  });

  document.getElementById('btn-draft-summary')?.addEventListener('click', handleDraftSummary);
  document.getElementById('btn-draft-tasks')?.addEventListener('click', handleDraftTaskBullets);
  document.getElementById('btn-draft-add-task')?.addEventListener('click', () => {
    state.currentDraft.tasks.push(emptyTask());
    renderDraftTasks();
  });
  document.getElementById('btn-draft-preview')?.addEventListener('click', async () => {
    document.getElementById('preview-source').value = 'draft';
    state.preview.source = 'draft';
    switchTab('preview');
    await renderPreview();
  });
  document.getElementById('btn-draft-save')?.addEventListener('click', handleDraftSave);

  document.getElementById('projects-library')?.addEventListener('click', handleProjectLibraryClick);
  document.getElementById('preview-saved-projects')?.addEventListener('change', handlePreviewProjectSelection);

  document.getElementById('btn-preview-render')?.addEventListener('click', renderPreview);
  document.getElementById('btn-preview-export')?.addEventListener('click', exportPreview);

  document.getElementById('btn-scan-run')?.addEventListener('click', handleGitScan);
  document.getElementById('btn-scan-load-draft')?.addEventListener('click', handleScanLoadDraft);
  document.getElementById('scan-analyze')?.addEventListener('change', event => {
    const visible = event.target.checked;
    const langField = document.getElementById('scan-lang-field');
    if (langField) langField.style.display = visible ? '' : 'none';
  });

  document.getElementById('ai-name')?.addEventListener('change', () => {
    syncProviderForm();
    loadModelsForProvider();
  });
  document.getElementById('ai-key')?.addEventListener('change', loadModelsForProvider);
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

async function loadModelsForProvider() {
  const provider = document.getElementById('ai-name')?.value;
  const apiKey = document.getElementById('ai-key')?.value?.trim();
  const baseUrl = document.getElementById('ai-base-url')?.value?.trim();
  const modelSelect = document.getElementById('ai-model');
  const loadBtn = document.getElementById('btn-load-models');
  if (!modelSelect || !provider) return;

  const params = new URLSearchParams({ provider });
  if (apiKey) params.set('api_key', apiKey);
  if (baseUrl) params.set('base_url', baseUrl);

  const prevLabel = loadBtn?.textContent;
  if (loadBtn) { loadBtn.textContent = '...'; loadBtn.disabled = true; }
  modelSelect.innerHTML = '<option value="">불러오는 중...</option>';

  try {
    const data = await apiGet(`/api/models?${params}`);
    const models = data.models || [];
    if (!models.length) {
      modelSelect.innerHTML = '<option value="">사용 가능한 모델 없음</option>';
      return;
    }
    const defaultModel = DEFAULT_MODELS[provider] || '';
    modelSelect.innerHTML = models.map(m =>
      `<option value="${escHtml(m)}"${m === defaultModel ? ' selected' : ''}>${escHtml(m)}</option>`
    ).join('');
  } catch {
    modelSelect.innerHTML = '<option value="">목록 불러오기 실패 — 직접 입력</option>';
    showToast('모델 목록을 불러오지 못했습니다.', 'error');
  } finally {
    if (loadBtn) { loadBtn.textContent = prevLabel; loadBtn.disabled = false; }
  }
}

function bindDraftEditors() {
  document.getElementById('draft-meta')?.addEventListener('input', event => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.dataset.field) {
      state.currentDraft[target.dataset.field] = target.value;
    }
    if (target.dataset.period) {
      state.currentDraft.period[target.dataset.period] = target.value;
    }
    if (target.dataset.listField) {
      state.currentDraft[target.dataset.listField] = normalizeArray(target.value);
    }
    if (target.dataset.teamSize) {
      state.currentDraft.team_size = Number(target.value) > 0 ? Number(target.value) : 1;
    }
  });

  document.getElementById('draft-tasks')?.addEventListener('input', event => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const index = Number(target.dataset.taskIndex);
    if (Number.isNaN(index) || !state.currentDraft.tasks[index]) return;

    if (target.dataset.taskField) {
      state.currentDraft.tasks[index][target.dataset.taskField] = target.value;
    }
    if (target.dataset.taskPeriod) {
      state.currentDraft.tasks[index].period[target.dataset.taskPeriod] = target.value;
    }
    if (target.dataset.taskList) {
      state.currentDraft.tasks[index][target.dataset.taskList] = normalizeArray(target.value);
    }
  });

  document.getElementById('draft-tasks')?.addEventListener('click', event => {
    const button = event.target.closest('[data-action="remove-task"]');
    if (!button) return;
    const index = Number(button.dataset.index);
    if (Number.isNaN(index)) return;
    state.currentDraft.tasks.splice(index, 1);
    if (!state.currentDraft.tasks.length) state.currentDraft.tasks = [emptyTask()];
    renderDraftTasks();
  });
}

function bindSettingsForms() {
  bindForm('form-profile', '/api/config/user', 'PUT', async () => {
    state.config = await apiGet('/api/config');
    populateProviders();
  });
  bindForm('form-export', '/api/config/export', 'PUT', async () => {
    state.config = await apiGet('/api/config');
    applyConfigToForms();
  });
  bindForm('form-sync', '/api/config/sync', 'PUT', async () => {
    state.config = await apiGet('/api/config');
  });
  bindForm('form-general', '/api/config/general', 'PUT', async () => {
    state.config = await apiGet('/api/config');
    applyConfigToForms();
    populateProviders();
  });

  document.getElementById('form-ai')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('[type="submit"]');
    const data = formToJson(form);
    if (!data.api_key) delete data.api_key;
    if (!data.base_url) delete data.base_url;

    await runUserAction(button, '저장 중...', async () => {
      await apiPost('/api/config/ai', data);
      state.config = await apiGet('/api/config');
      populateProviders();
      applyConfigToForms();
      form.reset();
      syncProviderForm();
      showToast('AI 제공자를 저장했습니다.');
    }, {
      title: 'AI 제공자 저장 실패',
      toastMessage: 'AI 제공자 저장에 실패했습니다.',
      fallbackMessage: 'AI 제공자를 저장하지 못했습니다.',
    });
  });
}

function bindForm(formId, endpoint, method, onSuccess) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('[type="submit"]');
    await runUserAction(button, '저장 중...', async () => {
      const payload = formToJson(form);
      if (method === 'PUT') {
        await apiPut(endpoint, payload);
      } else {
        await apiPost(endpoint, payload);
      }
      if (onSuccess) await onSuccess();
      showToast('저장되었습니다.');
    }, {
      title: '설정 저장 실패',
      toastMessage: '저장에 실패했습니다.',
      fallbackMessage: '설정을 저장하지 못했습니다.',
    });
  });
}

function bindPreviewControls() {
  ['preview-doc-type', 'preview-source', 'preview-template', 'preview-format'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', syncPreviewState);
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
    renderDraft();
    renderProjects();
    renderPreviewControls();
    renderPreviewOutput();
    syncProviderForm();
    updateGuideSteps();
    const initialized = document.body.dataset.initialized === 'true';
    if (!initialized) switchTab('guide');
  } catch (error) {
    showToast(error.message || '초기 데이터를 불러오지 못했습니다.', 'error');
  }
}

function updateGuideSteps() {
  const initialized = document.body.dataset.initialized === 'true';
  const hasAI = state.config && state.config.ai_providers && state.config.ai_providers.length > 0;
  const hasProjects = state.projects.length > 0;

  const step1 = document.getElementById('guide-step-1');
  const step3 = document.getElementById('guide-step-3');
  const step4 = document.getElementById('guide-step-4');
  const complete = document.getElementById('guide-complete');

  if (step1) step1.classList.toggle('done', initialized);
  if (step3) step3.classList.toggle('done', hasAI);
  if (step4) step4.classList.toggle('done', hasProjects);

  const allDone = initialized && hasAI && hasProjects;
  if (complete) complete.classList.toggle('hidden', !allDone);
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
  document.getElementById('general-provider').value = general.default_ai_provider || '';

  document.getElementById('intake-lang').value = general.default_language || 'ko';
  state.preview.template = exportConfig.default_template || 'default';
  renderPreviewControls();
}

function populateProviders() {
  const providers = state.config?.ai_providers || [];
  const intakeProvider = document.getElementById('intake-provider');
  if (intakeProvider) {
    intakeProvider.innerHTML = '<option value="">자동 선택</option>' + providers
      .map(provider => `<option value="${escHtml(provider.name)}">${escHtml(provider.name)} · ${escHtml(provider.model)}</option>`)
      .join('');
  }

  const scanProvider = document.getElementById('scan-provider');
  if (scanProvider) {
    scanProvider.innerHTML = '<option value="">자동 선택</option>' + providers
      .map(provider => `<option value="${escHtml(provider.name)}">${escHtml(provider.name)} · ${escHtml(provider.model)}</option>`)
      .join('');
  }

  const providerList = document.getElementById('provider-list');
  if (providerList) {
    if (!providers.length) {
      providerList.innerHTML = '<div class="empty-surface">등록된 AI가 없습니다. 수동으로 작성하고 미리보기는 계속 이용할 수 있습니다.</div>';
    } else {
      providerList.innerHTML = providers
        .map(provider => `
          <article class="provider-item">
            <div>
              <strong>${escHtml(provider.name)}</strong>
              <p>${escHtml(provider.model)}</p>
              <small>${escHtml(provider.key_masked)}${provider.is_default ? ' · 기본 제공자' : ''}</small>
            </div>
            <div class="inline-actions">
              <button type="button" class="btn btn-ghost" data-provider-action="test" data-provider-name="${escHtml(provider.name)}">테스트</button>
              <button type="button" class="btn btn-ghost danger" data-provider-action="remove" data-provider-name="${escHtml(provider.name)}">삭제</button>
            </div>
          </article>
        `)
        .join('');
    }
  }

  providerList?.querySelectorAll('[data-provider-action]').forEach(button => {
    button.addEventListener('click', async () => {
      const name = button.dataset.providerName;
      const action = button.dataset.providerAction;
      if (!name) return;
      if (action === 'test') {
        await runUserAction(button, '테스트 중...', async () => {
          const result = await apiPost(`/api/config/ai/${encodeURIComponent(name)}/test`, {});
          if (result.status === 'ok') {
            showToast(`${name} 연결이 확인되었습니다.`);
          } else {
            throw new Error(result.message || '연결 확인 실패');
          }
        }, {
          title: 'AI 연결 테스트 실패',
          toastMessage: '연결 확인에 실패했습니다.',
          fallbackMessage: 'AI 연결을 확인하지 못했습니다.',
        });
      }
      if (action === 'remove') {
        if (!window.confirm(`'${name}'을(를) 삭제하시겠습니까?`)) return;
        await runUserAction(button, '삭제 중...', async () => {
          await apiDelete(`/api/config/ai/${encodeURIComponent(name)}`);
          state.config = await apiGet('/api/config');
          populateProviders();
          applyConfigToForms();
          showToast(`${name}을(를) 삭제했습니다.`);
        }, {
          title: 'AI 제공자 삭제 실패',
          toastMessage: '삭제에 실패했습니다.',
          fallbackMessage: 'AI 제공자를 삭제하지 못했습니다.',
        });
      }
    });
  });
}

function syncProviderForm() {
  const select = document.getElementById('ai-name');
  const apiField = document.getElementById('field-api-key');
  const baseUrlField = document.getElementById('field-base-url');
  if (!select) return;

  const isOllama = select.value === 'ollama';
  apiField.classList.toggle('hidden', isOllama);
  baseUrlField.classList.toggle('hidden', !isOllama);
}

function renderDraft() {
  renderDraftMeta();
  renderDraftTasks();
}

function renderDraftMeta() {
  const draft = normalizeDraft(state.currentDraft);
  state.currentDraft = draft;

  const meta = document.getElementById('draft-meta');
  const saveMode = state.loadedProjectId ? '기존 프로젝트 수정 중' : '새 프로젝트 초안';
  meta.innerHTML = `
    <div class="status-line">${escHtml(saveMode)}</div>
    <div class="field-grid">
      <label class="field">
        <span>프로젝트명</span>
        <input type="text" data-field="name" value="${escHtml(draft.name)}" placeholder="프로젝트명을 입력하세요" />
      </label>
      <label class="field">
        <span>소속/주관</span>
        <input type="text" data-field="organization" value="${escHtml(draft.organization)}" placeholder="회사명 또는 팀명" />
      </label>
    </div>
    <div class="field-grid">
      <label class="field">
        <span>유형</span>
        <select data-field="type">
          <option value="company" ${draft.type === 'company' ? 'selected' : ''}>정규 프로젝트</option>
          <option value="side" ${draft.type === 'side' ? 'selected' : ''}>사이드 프로젝트</option>
          <option value="course" ${draft.type === 'course' ? 'selected' : ''}>교육/과정</option>
        </select>
      </label>
      <label class="field">
        <span>상태</span>
        <select data-field="status">
          <option value="done" ${draft.status === 'done' ? 'selected' : ''}>완료</option>
          <option value="in_progress" ${draft.status === 'in_progress' ? 'selected' : ''}>진행 중</option>
          <option value="planned" ${draft.status === 'planned' ? 'selected' : ''}>계획 중</option>
        </select>
      </label>
      <label class="field">
        <span>시작 월</span>
        <input type="text" data-period="start" value="${escHtml(draft.period.start)}" placeholder="YYYY-MM" />
      </label>
      <label class="field">
        <span>종료 월</span>
        <input type="text" data-period="end" value="${escHtml(draft.period.end)}" placeholder="YYYY-MM 또는 빈 값" />
      </label>
    </div>
    <div class="field-grid">
      <label class="field">
        <span>역할</span>
        <input type="text" data-field="role" value="${escHtml(draft.role)}" placeholder="예: 백엔드 개발자" />
      </label>
      <label class="field">
        <span>팀 규모</span>
        <input type="number" min="1" data-team-size="true" value="${escHtml(draft.team_size)}" />
      </label>
    </div>
    <div class="field-grid">
      <label class="field">
        <span>기술 스택</span>
        <input type="text" data-list-field="tech_stack" value="${escHtml(draft.tech_stack.join(', '))}" placeholder="Python, FastAPI, Docker" />
      </label>
      <label class="field">
        <span>태그</span>
        <input type="text" data-list-field="tags" value="${escHtml(draft.tags.join(', '))}" placeholder="backend, infra" />
      </label>
    </div>
    <label class="field">
      <span>프로젝트 요약</span>
      <textarea rows="5" data-field="summary" placeholder="포트폴리오에 들어갈 소개 문단 또는 핵심 요약">${escHtml(draft.summary)}</textarea>
    </label>
  `;
}

function renderDraftTasks() {
  const container = document.getElementById('draft-tasks');
  const tasks = state.currentDraft.tasks || [];
  if (!tasks.length) {
    container.innerHTML = '<div class="empty-surface">아직 작업이 없습니다. 작업 추가 버튼으로 첫 작업을 넣으세요.</div>';
    return;
  }

  container.innerHTML = tasks
    .map((task, index) => `
      <article class="task-item">
        <div class="task-head">
          <div>
            <p class="eyebrow">작업 ${index + 1}</p>
            <h4>${escHtml(task.name || '새 작업')}</h4>
          </div>
          <button type="button" class="btn btn-ghost danger" data-action="remove-task" data-index="${index}">삭제</button>
        </div>
        <div class="field-grid">
          <label class="field">
            <span>작업명</span>
            <input type="text" data-task-index="${index}" data-task-field="name" value="${escHtml(task.name)}" placeholder="예: 배포 자동화 구축" />
          </label>
          <label class="field">
            <span>사용 기술</span>
            <input type="text" data-task-index="${index}" data-task-list="tech_used" value="${escHtml(task.tech_used.join(', '))}" placeholder="Docker, GitHub Actions" />
          </label>
        </div>
        <div class="field-grid">
          <label class="field">
            <span>시작 월</span>
            <input type="text" data-task-index="${index}" data-task-period="start" value="${escHtml(task.period.start)}" placeholder="YYYY-MM" />
          </label>
          <label class="field">
            <span>종료 월</span>
            <input type="text" data-task-index="${index}" data-task-period="end" value="${escHtml(task.period.end)}" placeholder="YYYY-MM 또는 빈 값" />
          </label>
        </div>
        <label class="field">
          <span>문제 상황</span>
          <textarea rows="3" data-task-index="${index}" data-task-field="problem">${escHtml(task.problem)}</textarea>
        </label>
        <label class="field">
          <span>해결 방법</span>
          <textarea rows="3" data-task-index="${index}" data-task-field="solution">${escHtml(task.solution)}</textarea>
        </label>
        <div class="field-grid">
          <label class="field">
            <span>성과</span>
            <textarea rows="3" data-task-index="${index}" data-task-field="result">${escHtml(task.result)}</textarea>
          </label>
          <label class="field">
            <span>키워드</span>
            <textarea rows="3" data-task-index="${index}" data-task-list="keywords">${escHtml(task.keywords.join(', '))}</textarea>
          </label>
        </div>
        <label class="field">
          <span>포트폴리오 문구</span>
          <textarea rows="5" data-task-index="${index}" data-task-field="ai_generated_text" placeholder="작업 항목을 생성하면 여기에 표시됩니다.">${escHtml(task.ai_generated_text)}</textarea>
        </label>
      </article>
    `)
    .join('');
}

function renderProjects() {
  const library = document.getElementById('projects-library');
  if (!state.projects.length) {
    library.innerHTML = '<div class="empty-surface">저장된 프로젝트가 없습니다. Intake 탭에서 초안을 저장하세요.</div>';
    renderProjectsDetail();
    renderSavedProjectChecklist();
    return;
  }

  library.innerHTML = state.projects
    .map(project => `
      <article class="project-item ${project.id === state.loadedProjectId ? 'selected' : ''}">
        <div>
          <h4>${escHtml(project.name)}</h4>
          <p>${escHtml(project.role || project.organization || project.type)} · ${escHtml(project.tech_stack?.join(', ') || '기술 스택 없음')}</p>
          <small>${escHtml(project.summary || '요약이 없습니다.')}</small>
        </div>
        <div class="inline-actions">
          <button type="button" class="btn btn-ghost" data-project-action="load" data-project-id="${escHtml(project.id)}">에디터로</button>
          <button type="button" class="btn btn-ghost" data-project-action="summary" data-project-id="${escHtml(project.id)}">요약 재생성</button>
          <button type="button" class="btn btn-ghost" data-project-action="tasks" data-project-id="${escHtml(project.id)}">항목 생성</button>
          <button type="button" class="btn btn-ghost danger" data-project-action="delete" data-project-id="${escHtml(project.id)}">삭제</button>
        </div>
      </article>
    `)
    .join('');

  renderProjectsDetail();
  renderSavedProjectChecklist();
}

function renderProjectsDetail(project = null) {
  const detail = document.getElementById('projects-detail');
  const current = project || state.projects.find(item => item.id === state.loadedProjectId) || state.projects[0];
  if (!current) {
    detail.textContent = '저장된 프로젝트가 아직 없습니다. Intake 탭에서 초안을 저장하세요.';
    return;
  }
  detail.innerHTML = `
    <h4>${escHtml(current.name)}</h4>
    <p>${escHtml(current.summary || '아직 요약이 없습니다.')}</p>
    <p>작업 수: ${current.tasks?.length || 0} · 역할: ${escHtml(current.role || '미입력')}</p>
    <p>에디터로 불러와 수정하거나, 미리보기 탭에서 문서로 바로 렌더링할 수 있습니다.</p>
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
}

function renderSavedProjectChecklist() {
  const container = document.getElementById('preview-saved-projects');
  const isSavedSource = state.preview.source === 'saved';
  container.classList.toggle('disabled', !isSavedSource);
  if (!state.projects.length) {
    container.innerHTML = '<div class="empty-surface">저장된 프로젝트가 없습니다.</div>';
    return;
  }

  const selectedIds = new Set(state.preview.projectIds);
  container.innerHTML = state.projects
    .map(project => `
      <label class="selection-item">
        <input type="checkbox" value="${escHtml(project.id)}" ${selectedIds.has(project.id) ? 'checked' : ''} ${!isSavedSource ? 'disabled' : ''} />
        <span>
          <strong>${escHtml(project.name)}</strong>
          <small>${escHtml(project.role || project.organization || project.type)}</small>
        </span>
      </label>
    `)
    .join('');
}

function renderPreviewOutput() {
  const output = document.getElementById('preview-output');
  const meta = document.getElementById('preview-meta');
  if (!state.lastPreview) {
    output.innerHTML = '<div class="empty-surface">Preview 버튼을 눌러 문서를 생성하세요.</div>';
    meta.textContent = '아직 생성된 미리보기가 없습니다.';
    return;
  }
  output.innerHTML = state.lastPreview.html;
  meta.textContent = `${state.lastPreview.doc_type} · ${state.lastPreview.project_count}개 프로젝트 · 템플릿: ${state.lastPreview.template}`;
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

async function handleIntakeGenerate() {
  const button = document.getElementById('btn-intake-generate');
  const rawText = document.getElementById('intake-raw-text').value.trim();
  if (!rawText) {
    showToast('원본 텍스트를 먼저 붙여넣으세요.', 'error');
    return;
  }
  await runUserAction(button, '초안 생성 중...', async () => {
    const result = await apiPost('/api/intake/project-draft', {
      raw_text: rawText,
      lang: document.getElementById('intake-lang').value,
      provider: document.getElementById('intake-provider').value || null,
    });
    state.currentDraft = normalizeDraft(result.draft);
    state.loadedProjectId = '';
    renderDraft();
    showToast('AI 초안이 생성되었습니다. 내용을 검토한 뒤 저장하세요.');
  }, {
    title: 'AI 초안 생성 실패',
    toastMessage: '초안 생성에 실패했습니다.',
    fallbackMessage: 'AI 초안을 생성하지 못했습니다.',
  });
}

async function handleDraftSummary() {
  const button = document.getElementById('btn-draft-summary');
  await runUserAction(button, '생성 중...', async () => {
    const result = await apiPost('/api/draft/generate-summary', {
      draft: normalizeDraft(state.currentDraft),
      lang: document.getElementById('intake-lang').value,
      provider: document.getElementById('intake-provider').value || null,
    });
    state.currentDraft = normalizeDraft(result.draft);
    renderDraft();
    showToast('프로젝트 요약을 다시 생성했습니다.');
  }, {
    title: '프로젝트 요약 생성 실패',
    toastMessage: '요약 생성에 실패했습니다.',
    fallbackMessage: '프로젝트 요약을 생성하지 못했습니다.',
  });
}

async function handleDraftTaskBullets() {
  const button = document.getElementById('btn-draft-tasks');
  await runUserAction(button, '생성 중...', async () => {
    const result = await apiPost('/api/draft/generate-task-bullets', {
      draft: normalizeDraft(state.currentDraft),
      lang: document.getElementById('intake-lang').value,
      provider: document.getElementById('intake-provider').value || null,
    });
    state.currentDraft = normalizeDraft(result.draft);
    renderDraftTasks();
    showToast('작업 항목을 생성했습니다.');
  }, {
    title: '작업 항목 생성 실패',
    toastMessage: '작업 항목 생성에 실패했습니다.',
    fallbackMessage: '작업 항목을 생성하지 못했습니다.',
  });
}

async function handleDraftSave() {
  const button = document.getElementById('btn-draft-save');
  await runUserAction(button, '저장 중...', async () => {
    const draft = normalizeDraft(state.currentDraft);
    const result = state.loadedProjectId
      ? await apiPut(`/api/projects/${encodeURIComponent(state.loadedProjectId)}`, draft)
      : await apiPost('/api/projects', draft);

    state.currentDraft = normalizeDraft(result.project);
    state.loadedProjectId = result.project.id;
    upsertProject(result.project);
    renderDraft();
    renderProjects();
    renderPreviewControls();
    showToast('프로젝트를 저장했습니다.');
  }, {
    title: '프로젝트 저장 실패',
    toastMessage: '저장에 실패했습니다.',
    fallbackMessage: '프로젝트를 저장하지 못했습니다.',
  });
}

function upsertProject(project) {
  const index = state.projects.findIndex(item => item.id === project.id);
  if (index >= 0) {
    state.projects[index] = project;
  } else {
    state.projects.unshift(project);
  }
  if (!state.preview.projectIds.includes(project.id)) {
    state.preview.projectIds.push(project.id);
  }
}

async function handleProjectLibraryClick(event) {
  const button = event.target.closest('[data-project-action]');
  if (!button) return;
  const projectId = button.dataset.projectId;
  const action = button.dataset.projectAction;
  const project = state.projects.find(item => item.id === projectId);
  if (!project) return;

  if (action === 'load') {
    state.currentDraft = normalizeDraft(project);
    state.loadedProjectId = project.id;
    renderDraft();
    renderProjects();
    switchTab('intake');
    showToast(`${project.name} 프로젝트를 열었습니다.`);
    return;
  }

  if (action === 'delete') {
    if (!window.confirm(`'${project.name}' 프로젝트를 삭제하시겠습니까?`)) return;
    await runUserAction(button, '삭제 중...', async () => {
      await apiDelete(`/api/projects/${encodeURIComponent(project.id)}`);
      state.projects = state.projects.filter(item => item.id !== project.id);
      state.preview.projectIds = state.preview.projectIds.filter(id => id !== project.id);
      if (state.loadedProjectId === project.id) {
        state.loadedProjectId = '';
      }
      renderProjects();
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
    const busyLabel = action === 'summary' ? '요약 생성 중...' : '항목 생성 중...';

    await runUserAction(button, busyLabel, async () => {
      const result = await apiPost(endpoint, {
        lang: document.getElementById('intake-lang').value,
        provider: document.getElementById('intake-provider').value || null,
      });
      const updated = normalizeDraft(result.project);
      upsertProject(updated);
      if (state.loadedProjectId === updated.id) {
        state.currentDraft = updated;
        renderDraft();
      }
      renderProjects();
      showToast(action === 'summary' ? '프로젝트 요약을 갱신했습니다.' : '작업 항목을 갱신했습니다.');
    }, {
      title: action === 'summary' ? '프로젝트 요약 갱신 실패' : '작업 항목 갱신 실패',
      toastMessage: action === 'summary' ? '요약 갱신에 실패했습니다.' : '작업 항목 갱신에 실패했습니다.',
      fallbackMessage: action === 'summary' ? '프로젝트 요약을 갱신하지 못했습니다.' : '작업 항목을 갱신하지 못했습니다.',
    });
  }
}

function handlePreviewProjectSelection(event) {
  const checkbox = event.target;
  if (!(checkbox instanceof HTMLInputElement)) return;
  const selected = Array.from(
    document.querySelectorAll('#preview-saved-projects input[type="checkbox"]:checked')
  ).map(input => input.value);
  state.preview.projectIds = selected;
}

async function renderPreview() {
  syncPreviewState();
  const button = document.getElementById('btn-preview-render');
  await runUserAction(button, '렌더링 중...', async () => {
    const payload = buildPreviewPayload();
    const result = await apiPost(`/api/preview/${state.preview.docType}`, payload);
    state.lastPreview = result;
    renderPreviewOutput();
    showToast('미리보기를 갱신했습니다.');
  }, {
    title: '미리보기 생성 실패',
    toastMessage: '미리보기 생성에 실패했습니다.',
    fallbackMessage: '미리보기를 생성하지 못했습니다.',
  });
}

async function exportPreview() {
  syncPreviewState();
  const button = document.getElementById('btn-preview-export');
  await runUserAction(button, '내보내는 중...', async () => {
    const payload = buildPreviewPayload();
    const result = await apiPost(`/api/export/${state.preview.docType}`, payload);
    showToast(`내보내기 완료: ${result.path}`);
    document.getElementById('preview-meta').textContent = `내보내기 완료 · ${result.format} · ${result.path}`;
  }, {
    title: '내보내기 실패',
    toastMessage: '내보내기에 실패했습니다.',
    fallbackMessage: '문서를 내보내지 못했습니다.',
  });
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

  const busyLabel = analyze ? 'AI 분석 중...' : '분석 중...';
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
    const p = result.payload;
    const metrics = p.scan_metrics || {};
    const cacheNote = result.cached ? ' (이전 결과 재사용)' : '';
    const analyzeNote = result.analyzed ? ' · AI 상세 분석 완료' : '';

    resultEl.innerHTML = `
      <dl class="scan-summary">
        <dt>프로젝트명</dt><dd>${escHtml(p.name || '-')}</dd>
        <dt>기간</dt><dd>${escHtml(p.period_start || '-')} ~ ${escHtml(p.period_end || '현재')}</dd>
        <dt>커밋</dt><dd>${metrics.commit_count ?? '-'}건 / 내 커밋 ${((metrics.authorship_ratio ?? 0) * 100).toFixed(0)}%</dd>
        <dt>변경</dt><dd>+${metrics.insertions ?? 0} / -${metrics.deletions ?? 0} LOC, ${metrics.files_touched ?? 0}파일</dd>
        <dt>언어</dt><dd>${escHtml(Object.keys(metrics.languages || {}).join(', ') || '-')}</dd>
        <dt>요약</dt><dd>${escHtml(p.summary || '-')}</dd>
        <dt>작업 수</dt><dd>${(p.tasks || []).length}개${cacheNote}${analyzeNote}</dd>
      </dl>
    `;
    if (actionsEl) actionsEl.style.display = '';

    const toastMsg = result.analyzed
      ? `AI 분석 완료: ${p.name || '프로젝트'}`
      : `분석 완료: ${p.name || '프로젝트'}${cacheNote}`;
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
  const p = state.lastScanPayload;

  const tasks = (p.tasks || []).map((t, i) => ({
    id: `scan_task_${i + 1}`,
    name: t.name || '',
    period: { start: t.period_start || '', end: t.period_end || '' },
    problem: t.problem || '',
    solution: t.solution || '',
    result: t.result || '',
    tech_used: t.tech_used || [],
    keywords: t.keywords || [],
    ai_generated_text: t.ai_generated_text || '',
  }));

  state.currentDraft = normalizeDraft({
    name: p.name || '',
    type: p.type || 'company',
    status: p.status || 'done',
    organization: p.organization || '',
    period: { start: p.period_start || null, end: p.period_end || null },
    role: p.role || '',
    team_size: p.team_size || 1,
    tech_stack: p.tech_stack || [],
    summary: p.summary || '',
    tags: p.tags || [],
    tasks: tasks.length ? tasks : [emptyTask()],
  });
  state.loadedProjectId = '';

  renderDraft();
  switchTab('intake');
  showToast('스캔 결과를 초안으로 불러왔습니다. 검토 후 저장하세요.');
}
