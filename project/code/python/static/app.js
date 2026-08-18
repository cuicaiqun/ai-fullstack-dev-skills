/* ═══════════════════════════════════════════════════════════════════
   Agent Knowledge Hub — Premium Frontend App
   ═══════════════════════════════════════════════════════════════════ */

const API = '/api';
const TOKEN_KEY = 'eka_access_token';

/* ════════════════════ State ════════════════════ */
const state = {
  uploadedDocs: [],
  asking: false,
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: null,
  sessionEpoch: 0,
  sessionId: localStorage.getItem('eka_qa_session_id') || '',
  chatHistory: [],
};

/* ════════════════════ DOM refs ════════════════════ */
const $ = (s) => document.querySelector(s);

const dom = {
  loginGate: $('#loginGate'),
  loginForm: $('#loginForm'),
  loginUsername: $('#loginUsername'),
  loginPassword: $('#loginPassword'),
  loginError: $('#loginError'),
  logoutBtn: $('#logoutBtn'),
  newSessionBtn: $('#newSessionBtn'),
  appWrapper: $('#app-wrapper'),
  statusDot: $('#statusDot'),
  statusText: $('#statusText'),
  tabs: document.querySelectorAll('.tab-btn'),
  panels: {
    qa: $('#panel-qa'),
    upload: $('#panel-upload'),
    dashboard: $('#panel-dashboard'),
  },
  chatContainer: $('#chatContainer'),
  qaInput: $('#qaInput'),
  qaSendBtn: $('#qaSendBtn'),
  uploadZone: $('#uploadZone'),
  uploadVisibility: $('#uploadVisibility'),
  fileInput: $('#fileInput'),
  uploadProgress: $('#uploadProgress'),
  docList: $('#docList'),
  refreshStatsBtn: $('#refreshStatsBtn'),
};

function formatApiDetail(detail) {
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  }
  return JSON.stringify(detail);
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  return headers;
}

async function apiFetch(url, options = {}) {
  const opts = { ...options };
  const tokenUsed = state.token;
  const epoch = state.sessionEpoch;
  opts.headers = authHeaders(opts.headers || {});
  const r = await fetch(url, opts);
  // 仅当仍是同一次会话、且用的还是这枚 token 时，才因 401 退回登录
  if (r.status === 401 && tokenUsed && tokenUsed === state.token && epoch === state.sessionEpoch) {
    clearSession();
    showLogin('登录已过期，请重新登录');
  }
  return r;
}

function showLogin(message = '') {
  if (dom.appWrapper) dom.appWrapper.classList.add('hidden');
  if (dom.loginGate) dom.loginGate.classList.remove('hidden');
  if (message && dom.loginError) {
    dom.loginError.textContent = message;
    dom.loginError.classList.remove('hidden');
  }
}

function showApp() {
  if (dom.loginGate) dom.loginGate.classList.add('hidden');
  if (dom.appWrapper) dom.appWrapper.classList.remove('hidden');
  if (dom.loginError) dom.loginError.classList.add('hidden');
}

function clearSession() {
  state.token = '';
  state.user = null;
  localStorage.removeItem(TOKEN_KEY);
}

async function restoreSession() {
  const epoch = ++state.sessionEpoch;
  if (!state.token) {
    showLogin();
    return false;
  }
  try {
    // 不用 apiFetch，避免旧请求 401 清掉新登录
    const r = await fetch(`${API}/auth/me`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (epoch !== state.sessionEpoch) return false;
    if (!r.ok) throw new Error('unauthorized');
    state.user = await r.json();
    if (epoch !== state.sessionEpoch) return false;
    showApp();
    return true;
  } catch {
    if (epoch !== state.sessionEpoch) return false;
    clearSession();
    showLogin();
    return false;
  }
}

if (dom.loginForm) {
  dom.loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (dom.loginError) dom.loginError.classList.add('hidden');
    const body = new URLSearchParams();
    body.set('username', (dom.loginUsername?.value || '').trim());
    body.set('password', dom.loginPassword?.value || '');
    try {
      const r = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(formatApiDetail(data.detail) || `HTTP ${r.status}`);
      if (!data.access_token) throw new Error('登录响应缺少 token');
      state.sessionEpoch += 1;
      state.token = data.access_token;
      state.user = data.user || null;
      localStorage.setItem(TOKEN_KEY, state.token);
      showApp();
      checkHealth();
    } catch (err) {
      if (dom.loginError) {
        dom.loginError.textContent = err.message || '登录失败';
        dom.loginError.classList.remove('hidden');
      }
    }
  });
}

if (dom.logoutBtn) {
  dom.logoutBtn.addEventListener('click', async () => {
    state.sessionEpoch += 1;
    // Revoke the server-side token before removing the local session.
    if (state.token) {
      try {
        await fetch(`${API}/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${state.token}` },
          keepalive: true,
        });
      } catch {
        // Local cleanup still happens if the API is unavailable.
      }
    }
    clearSession();
    showLogin();
  });
}

function startNewSession() {
  state.sessionId = '';
  state.chatHistory = [];
  localStorage.removeItem('eka_qa_session_id');
  if (dom.chatContainer) {
    dom.chatContainer.innerHTML = '';
  }
}

if (dom.newSessionBtn) {
  dom.newSessionBtn.addEventListener('click', startNewSession);
}

/* ════════════════════ Health Check ════════════════════ */
async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const d = await r.json();
    if (d.status === 'ok') {
      dom.statusDot?.classList.remove('offline');
      const who = state.user ? `${state.user.username}@${state.user.tenant_id}` : (d.service || '系统正常');
      if (dom.statusText) dom.statusText.textContent = who;
    }
  } catch {
    dom.statusDot?.classList.add('offline');
    if (dom.statusText) dom.statusText.textContent = '服务离线';
  }
}
restoreSession().then((ok) => { if (ok) checkHealth(); });
setInterval(checkHealth, 15000);

/* ════════════════════ Tab Switching ════════════════════ */
dom.tabs.forEach(btn => {
  btn.addEventListener('click', () => {
    dom.tabs.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    Object.values(dom.panels).forEach(p => p.classList.add('hidden'));
    dom.panels[tab].classList.remove('hidden');
    // Re-trigger fade animation
    dom.panels[tab].classList.remove('animate-fade-in-up');
    void dom.panels[tab].offsetWidth;
    dom.panels[tab].classList.add('animate-fade-in-up');
    if (tab === 'dashboard') loadStats();
  });
});

/* ════════════════════ Q&A ════════════════════ */
dom.qaSendBtn.addEventListener('click', sendQuestion);
dom.qaInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion(); }
});

async function sendQuestion() {
  const question = dom.qaInput.value.trim();
  if (!question || state.asking) return;

  state.asking = true;
  dom.qaSendBtn.disabled = true;
  dom.qaSendBtn.innerHTML = '<span class="spinner"></span>';
  dom.qaInput.value = '';

  appendMessage('user', question);

  // Show typing indicator
  const typingMsg = showTypingIndicator();

  try {
    const payload = {
      question,
      session_id: state.sessionId || null,
      history: state.chatHistory.slice(-12),
    };
    const r = await apiFetch(`${API}/qa/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(formatApiDetail(err.detail) || `HTTP ${r.status}`);
    }
    const data = await r.json();

    if (data.session_id) {
      state.sessionId = data.session_id;
      localStorage.setItem('eka_qa_session_id', state.sessionId);
    }
    state.chatHistory.push({ role: 'user', content: question });
    state.chatHistory.push({ role: 'assistant', content: data.answer });

    // Remove typing indicator
    typingMsg.remove();

    appendMessage('agent', data.answer, {
      intent: data.intent,
      confidence: data.confidence,
      sources: data.sources,
      reasoning: data.reasoning_steps,
      resolved: data.resolved_question,
      grounded: data.grounded,
      groundingNotes: data.grounding_notes,
    });
  } catch (err) {
    typingMsg.remove();
    appendMessage('agent', `抱歉，请求失败：${err.message}`, { error: true });
  } finally {
    state.asking = false;
    dom.qaSendBtn.disabled = false;
    dom.qaSendBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
  }
}

function showTypingIndicator() {
  const div = document.createElement('div');
  div.className = 'chat-msg agent';
  div.innerHTML = `
    <div class="chat-avatar chat-avatar--agent">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
    </div>
    <div class="chat-body">
      <div class="chat-bubble chat-bubble--agent">
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
  `;
  dom.chatContainer.appendChild(div);
  dom.chatContainer.scrollTop = dom.chatContainer.scrollHeight;
  return div;
}

function appendMessage(role, content, meta) {
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;

  // Avatar
  const avatar = document.createElement('div');
  const avatarClass = role === 'user' ? 'chat-avatar--user' : 'chat-avatar--agent';
  avatar.className = `chat-avatar ${avatarClass}`;
  if (role === 'user') {
    avatar.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
  } else {
    avatar.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>';
  }

  // Body wrapper
  const body = document.createElement('div');
  body.className = 'chat-body';

  // Bubble
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble chat-bubble--${role}`;

  if (meta && meta.error) {
    bubble.innerHTML = `<p style="color:var(--red-500)">${escapeHtml(content)}</p>`;
  } else {
    // Convert newlines to <br>, support simple markdown-like bold
    const lines = escapeHtml(content).split('\n');
    bubble.innerHTML = lines.map(line => `<p>${line || '&nbsp;'}</p>`).join('');
  }

  body.appendChild(bubble);

  // Meta tags
  if (meta) {
    const metaRow = document.createElement('div');
    metaRow.className = 'chat-meta';

    if (meta.intent) {
      const intentTag = document.createElement('span');
      intentTag.className = 'chat-tag chat-tag--intent';
      intentTag.textContent = meta.intent;
      metaRow.appendChild(intentTag);
    }

    if (meta.confidence > 0) {
      const confTag = document.createElement('span');
      confTag.className = 'chat-tag chat-tag--confidence';
      confTag.textContent = `置信度 ${(meta.confidence * 100).toFixed(0)}%`;
      metaRow.appendChild(confTag);
    }

    if (typeof meta.grounded === 'boolean') {
      const groundTag = document.createElement('span');
      groundTag.className = meta.grounded
        ? 'chat-tag chat-tag--grounded'
        : 'chat-tag chat-tag--ungrounded';
      groundTag.textContent = meta.grounded ? '已 grounding' : '未 grounding';
      if (!meta.grounded && meta.groundingNotes && meta.groundingNotes.length) {
        groundTag.title = meta.groundingNotes.join('; ');
      }
      metaRow.appendChild(groundTag);
    }

    if (metaRow.children.length > 0) {
      body.appendChild(metaRow);
    }

    // Sources
    if (meta.sources && meta.sources.length > 0) {
      const src = document.createElement('div');
      src.className = 'chat-sources';
      src.innerHTML = '<strong>参考来源</strong> &nbsp;' +
        meta.sources.map((s, i) =>
          `[${i + 1}] ${escapeHtml(s.source)} (${(s.score * 100).toFixed(0)}%)`
        ).join(' &nbsp;·&nbsp; ');
      body.appendChild(src);
    }

    // Reasoning steps
    if (meta.reasoning && meta.reasoning.length > 0) {
      const steps = document.createElement('div');
      steps.className = 'reasoning-steps';
      meta.reasoning.forEach(step => {
        const span = document.createElement('span');
        span.className = 'reasoning-step';
        span.textContent = step;
        steps.appendChild(span);
      });
      body.appendChild(steps);
    }
  }

  div.appendChild(avatar);
  div.appendChild(body);
  dom.chatContainer.appendChild(div);

  // Smooth scroll to bottom
  dom.chatContainer.scrollTo({
    top: dom.chatContainer.scrollHeight,
    behavior: 'smooth',
  });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/* ════════════════════ Upload ════════════════════ */
dom.uploadZone.addEventListener('click', () => dom.fileInput.click());
dom.fileInput.addEventListener('change', () => uploadFiles(dom.fileInput.files));

dom.uploadZone.addEventListener('dragover', e => {
  e.preventDefault();
  dom.uploadZone.classList.add('drag-over');
});
dom.uploadZone.addEventListener('dragleave', () => {
  dom.uploadZone.classList.remove('drag-over');
});
dom.uploadZone.addEventListener('drop', e => {
  e.preventDefault();
  dom.uploadZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
});

async function uploadFiles(fileList) {
  const files = Array.from(fileList);
  if (!files.length) return;

  const progress = dom.uploadProgress;
  progress.classList.add('show');
  progress.classList.remove('error');

  for (const file of files) {
    progress.textContent = `正在上传: ${file.name} ...`;
    try {
      const form = new FormData();
      form.append('file', file);
      const visibility = (dom.uploadVisibility && dom.uploadVisibility.value) || 'tenant';
      form.append('visibility', visibility);
      const r = await apiFetch(`${API}/ingest/upload`, { method: 'POST', body: form });
      if (!r.ok && r.status !== 202) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      if (r.status === 202 && data.task_id) {
        progress.textContent = `已入队: ${file.name}（任务 ${data.task_id.slice(0, 8)}…）处理中…`;
        const finalData = await pollIngestTask(data.task_id, file.name, progress);
        addDocToList(file.name, finalData);
        progress.textContent = `完成: ${file.name} (${finalData.chunks_count} 个文本块, ${finalData.entities_count} 个实体, ${finalData.relations_count} 个关系)`;
      } else {
        addDocToList(file.name, data);
        progress.textContent = `完成: ${file.name} (${data.chunks_count} 个文本块, ${data.entities_count} 个实体, ${data.relations_count} 个关系)`;
      }
    } catch (err) {
      progress.textContent = `失败: ${file.name} — ${err.message}`;
      progress.classList.add('error');
    }
  }

  setTimeout(() => progress.classList.remove('show'), 6000);
  dom.fileInput.value = '';
}

async function pollIngestTask(taskId, fileName, progressEl) {
  const maxAttempts = 600; // ~10min @ 1s
  for (let i = 0; i < maxAttempts; i++) {
    const r = await apiFetch(`${API}/ingest/tasks/${taskId}`);
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `任务查询失败 HTTP ${r.status}`);
    }
    const task = await r.json();
    if (task.status === 'succeeded' && task.result) {
      return {
        chunks_count: task.result.chunks_count ?? 0,
        entities_count: task.result.entities_count ?? 0,
        relations_count: task.result.relations_count ?? 0,
        status: task.result.status || 'success',
        doc_id: task.result.doc_id || task.doc_id || '',
        task_id: taskId,
      };
    }
    if (task.status === 'failed') {
      throw new Error(task.error || '入库任务失败');
    }
    const label = task.status === 'running' ? '处理中' : '排队中';
    progressEl.textContent = `${label}: ${fileName}（任务 ${taskId.slice(0, 8)}…）`;
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error('入库超时：请稍后在任务列表中查看状态');
}

function addDocToList(name, data) {
  const item = document.createElement('div');
  item.className = 'doc-item';
  item.innerHTML = `
    <span class="doc-icon">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--emerald-500)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
    </span>
    <span class="doc-name">${escapeHtml(name)}</span>
    <span class="doc-meta">${data.chunks_count} 块 · ${data.entities_count} 实体 · ${data.relations_count} 关系</span>
  `;
  dom.docList.prepend(item);
  state.uploadedDocs.push({ name, data });
}

/* ════════════════════ Dashboard ════════════════════ */
async function loadStats() {
  // Reset to loading state
  ['statVectors', 'statEntities', 'statRelations', 'statBackend'].forEach(id => {
    $(`#${id}`).textContent = '...';
  });

  try {
    const r = await apiFetch(`${API}/admin/stats`);
    if (!r.ok) throw new Error('Failed');
    const d = await r.json();

    animateValue($('#statVectors'), d.vector_store?.total_vectors ?? 0);
    animateValue($('#statEntities'), d.knowledge_graph?.total_entities ?? 0);
    animateValue($('#statRelations'), d.knowledge_graph?.total_relations ?? 0);

    const backendEl = $('#statBackend');
    backendEl.textContent = d.vector_store?.backend ?? '--';
    backendEl.style.fontSize = '18px';
    backendEl.style.fontWeight = '700';
  } catch {
    ['statVectors', 'statEntities', 'statRelations', 'statBackend'].forEach(id => {
      $(`#${id}`).textContent = 'ERR';
    });
  }
}

function animateValue(el, target) {
  const isNum = typeof target === 'number';
  if (!isNum) {
    el.textContent = target || '--';
    return;
  }
  const duration = 600;
  const start = performance.now();
  const from = 0;

  function update(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    // ease-out
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(from + (target - from) * eased);
    el.textContent = current.toLocaleString();
    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }

  requestAnimationFrame(update);
}

dom.refreshStatsBtn.addEventListener('click', loadStats);

/* ════════════════════ Keyboard Shortcuts ════════════════════ */
document.addEventListener('keydown', e => {
  // Ctrl+K / Cmd+K: focus QA input
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    // Switch to QA tab if not active
    const qaTab = document.querySelector('[data-tab="qa"]');
    if (!qaTab.classList.contains('active')) {
      qaTab.click();
    }
    dom.qaInput.focus();
  }

  // Escape: blur input
  if (e.key === 'Escape' && document.activeElement === dom.qaInput) {
    dom.qaInput.blur();
  }
});
