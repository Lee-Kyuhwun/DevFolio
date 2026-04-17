/* DevFolio Settings UI — Vanilla JS */

// ── 탭 전환 ──────────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const tabId = link.dataset.tab;

    document.querySelectorAll('.nav-item').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

    link.classList.add('active');
    document.getElementById('tab-' + tabId)?.classList.add('active');

    if (tabId === 'ai') loadProviders();
  });
});

// ── Toast 알림 ────────────────────────────────────────────────────────────────
let _toastTimer = null;

function showToast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = (type === 'success' ? '✓ ' : '✗ ') + msg;
  el.className = `toast show ${type}`;
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.classList.remove('show'); }, 3000);
}

// ── API 헬퍼 ─────────────────────────────────────────────────────────────────
async function apiPut(path, data) {
  const res = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function apiPost(path, data) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function apiDelete(path) {
  const res = await fetch(path, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── 폼 → JSON 변환 ────────────────────────────────────────────────────────────
function formToJson(form) {
  const data = {};
  new FormData(form).forEach((val, key) => { data[key] = val; });
  // checkbox는 FormData에 없으면 false
  form.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    data[cb.name] = cb.checked;
  });
  return data;
}

// ── 폼 제출 핸들러 팩토리 ──────────────────────────────────────────────────────
function bindForm(formId, endpoint, method = 'PUT') {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = form.querySelector('[type="submit"]');
    const orig = btn.textContent;
    btn.disabled = true;
    btn.textContent = '저장 중…';
    try {
      const fn = method === 'POST' ? apiPost : apiPut;
      await fn(endpoint, formToJson(form));
      showToast('저장되었습니다.');
    } catch (err) {
      showToast(err.message || '저장 실패', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = orig;
    }
  });
}

// 각 폼 바인딩
bindForm('form-profile', '/api/config/user');
bindForm('form-export',  '/api/config/export');
bindForm('form-sync',    '/api/config/sync');
bindForm('form-general', '/api/config/general');

// ── AI Provider 폼 ───────────────────────────────────────────────────────────
const aiNameSelect = document.getElementById('ai-name');
const fieldBaseUrl = document.getElementById('field-base-url');
const fieldApiKey  = document.getElementById('field-api-key');

function onProviderChange() {
  const isOllama = aiNameSelect.value === 'ollama';
  fieldBaseUrl.classList.toggle('hidden', !isOllama);
  fieldApiKey.classList.toggle('hidden', isOllama);

  // 모델 기본값 자동 채우기
  const defaults = {
    anthropic: 'claude-sonnet-4-5-20251001',
    openai:    'gpt-4o',
    gemini:    'gemini-1.5-flash',
    ollama:    'llama3.2',
  };
  const modelInput = document.getElementById('ai-model');
  if (!modelInput.value) {
    modelInput.value = defaults[aiNameSelect.value] || '';
  }
}

aiNameSelect?.addEventListener('change', onProviderChange);
onProviderChange();

document.getElementById('form-ai')?.addEventListener('submit', async e => {
  e.preventDefault();
  const btn = e.target.querySelector('[type="submit"]');
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = '저장 중…';
  try {
    const data = formToJson(e.target);
    // 빈 api_key는 null로 (기존 키 유지)
    if (!data.api_key) delete data.api_key;
    if (!data.base_url) delete data.base_url;
    await apiPost('/api/config/ai', data);
    showToast('Provider가 저장되었습니다.');
    await loadProviders();
    e.target.reset();
    onProviderChange();
  } catch (err) {
    showToast(err.message || '저장 실패', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
});

// ── Provider 목록 렌더링 ──────────────────────────────────────────────────────
const PROVIDER_ICONS = {
  anthropic: '🤖',
  openai:    '🧠',
  gemini:    '✨',
  ollama:    '🦙',
};

async function loadProviders() {
  const list = document.getElementById('provider-list');
  if (!list) return;

  list.innerHTML = '<div class="loading">불러오는 중…</div>';
  try {
    const providers = await fetch('/api/config/ai').then(r => r.json());

    if (!providers.length) {
      list.innerHTML = '<div class="empty-state">등록된 Provider가 없습니다.<br>아래 폼에서 추가하세요.</div>';
      return;
    }

    list.innerHTML = providers.map(p => `
      <div class="provider-card ${p.is_default ? 'default-provider' : ''}">
        <div class="provider-icon">${PROVIDER_ICONS[p.name] || '🔌'}</div>
        <div class="provider-info">
          <div class="provider-name">${escHtml(p.name)}
            ${p.is_default ? '<span class="provider-badge">기본</span>' : ''}
          </div>
          <div class="provider-model">${escHtml(p.model)}</div>
          <div class="provider-key">${escHtml(p.key_masked)}</div>
        </div>
        <div class="provider-actions">
          <button class="btn btn-ghost btn-test" data-name="${escHtml(p.name)}">테스트</button>
          <button class="btn btn-danger btn-remove" data-name="${escHtml(p.name)}">삭제</button>
        </div>
      </div>
    `).join('');

    // 테스트 버튼
    list.querySelectorAll('.btn-test').forEach(btn => {
      btn.addEventListener('click', () => testProvider(btn.dataset.name, btn));
    });

    // 삭제 버튼
    list.querySelectorAll('.btn-remove').forEach(btn => {
      btn.addEventListener('click', () => removeProvider(btn.dataset.name));
    });

  } catch (err) {
    list.innerHTML = `<div class="empty-state" style="color:var(--error)">불러오기 실패: ${escHtml(err.message)}</div>`;
  }
}

async function testProvider(name, btn) {
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = '테스트 중…';
  try {
    const res = await apiPost(`/api/config/ai/${encodeURIComponent(name)}/test`, {});
    if (res.status === 'ok') {
      showToast(`${name}: 연결 성공 ✓`);
    } else {
      showToast(`${name}: ${res.message}`, 'error');
    }
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

async function removeProvider(name) {
  if (!confirm(`'${name}' Provider를 삭제하시겠습니까?`)) return;
  try {
    await apiDelete(`/api/config/ai/${encodeURIComponent(name)}`);
    showToast(`${name} 삭제되었습니다.`);
    await loadProviders();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ── 비밀번호 표시/숨기기 ──────────────────────────────────────────────────────
document.querySelectorAll('.toggle-password').forEach(btn => {
  btn.addEventListener('click', () => {
    const input = btn.previousElementSibling;
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
    btn.textContent = input.type === 'password' ? '👁' : '🙈';
  });
});

// ── HTML 이스케이프 ───────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── 초기화: AI 탭이 처음 활성화될 때 로드 ───────────────────────────────────────
// (탭 전환 시 loadProviders() 호출하므로 명시적 초기화 불필요)
