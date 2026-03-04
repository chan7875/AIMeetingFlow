/* ── State ────────────────────────────────────────────────────────── */
const state = {
  engine: 'claude',
  currentFile: null,   // { path, name, content }
  aiResult: null,      // last AI output string
  uploadFiles: [],
  uploadDestPath: '',
  treeData: null,
  autoWatchEnabled: false,
  autoWatchBusy: false,
  autoWatchStatus: null,
  autoWatchPollTimer: null,
  autoWatchLastSeenCount: 0,
};

/* ── Marked.js setup ─────────────────────────────────────────────── */
marked.setOptions({
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true,
});

/* ── Init ─────────────────────────────────────────────────────────── */
window.addEventListener('DOMContentLoaded', () => {
  loadConfig();
  loadTree();
  loadAutoWatchStatus();
  startAutoWatchPolling();
  setupResize();
});

/* ── Config ───────────────────────────────────────────────────────── */
async function loadConfig() {
  const res = await fetch('/api/config');
  const data = await res.json();
  document.getElementById('vault-path-display').textContent = data.vault_path;
  document.getElementById('settings-vault-input').value = data.vault_path;
}

function openSettingsModal() {
  loadConfig();
  showModal('settings-modal');
}

async function saveSettings() {
  const path = document.getElementById('settings-vault-input').value.trim();
  if (!path) return toast('경로를 입력해 주세요.', 'error');
  const res = await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vault_path: path }),
  });
  if (!res.ok) {
    const err = await res.json();
    return toast(err.detail || '설정 저장 실패', 'error');
  }
  closeModal('settings-modal');
  toast('볼트 경로가 변경되었습니다.', 'success');
  loadConfig();
  loadTree();
  loadAutoWatchStatus();
}

/* ── Auto Watch ───────────────────────────────────────────────────── */
async function loadAutoWatchStatus(options = {}) {
  const silent = options.silent === true;
  try {
    const res = await fetch('/api/ai/auto-watch');
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '자동 감시 상태 조회 실패');
    }
    const data = await res.json();
    state.autoWatchEnabled = !!data.enabled;
    state.autoWatchStatus = data;
    state.autoWatchLastSeenCount = Number(data.processed_count || 0);
    renderAutoWatchButton();
    return data;
  } catch (e) {
    if (!silent) toast(`자동 감시 상태 조회 실패: ${e.message}`, 'error');
    return null;
  }
}

function renderAutoWatchButton() {
  const btn = document.getElementById('auto-watch-btn');
  if (!btn) return;
  const isOn = !!state.autoWatchEnabled;
  btn.innerHTML = `🛰 <span class="btn-text">${isOn ? '자동 분석 ON' : '자동 분석 OFF'}</span>`;
  btn.classList.toggle('toggle-on', isOn);
  btn.disabled = !!state.autoWatchBusy;

  const status = state.autoWatchStatus || {};
  const lastSaved = status.last_saved_path || '없음';
  const lastError = status.last_error || '없음';
  btn.title = `새 파일 자동 Codex 분석 (${isOn ? 'ON' : 'OFF'})\n최근 저장: ${lastSaved}\n최근 오류: ${lastError}`;
}

async function toggleAutoWatch() {
  if (state.autoWatchBusy) return;
  state.autoWatchBusy = true;
  renderAutoWatchButton();

  const nextEnabled = !state.autoWatchEnabled;
  try {
    const res = await fetch('/api/ai/auto-watch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: nextEnabled }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '자동 감시 전환 실패');
    }

    const data = await res.json();
    state.autoWatchEnabled = !!data.enabled;
    state.autoWatchStatus = data;
    state.autoWatchLastSeenCount = Number(data.processed_count || 0);
    renderAutoWatchButton();
    toast(`자동 분석이 ${state.autoWatchEnabled ? '활성화' : '비활성화'}되었습니다.`, 'success');
  } catch (e) {
    toast(`자동 감시 전환 실패: ${e.message}`, 'error');
  } finally {
    state.autoWatchBusy = false;
    renderAutoWatchButton();
  }
}

function startAutoWatchPolling() {
  if (state.autoWatchPollTimer) {
    clearInterval(state.autoWatchPollTimer);
  }
  state.autoWatchPollTimer = setInterval(async () => {
    const prevCount = state.autoWatchLastSeenCount;
    const data = await loadAutoWatchStatus({ silent: true });
    if (!data) return;

    const nextCount = Number(data.processed_count || 0);
    state.autoWatchLastSeenCount = nextCount;

    if (nextCount > prevCount) {
      loadTree();
    }
  }, 6000);
}

/* ── Tree ─────────────────────────────────────────────────────────── */
async function loadTree() {
  const container = document.getElementById('tree-container');
  container.innerHTML = '<div style="padding:16px;color:var(--text-dim);font-size:12px;">로딩 중...</div>';
  try {
    const res = await fetch('/api/tree');
    if (!res.ok) throw new Error((await res.json()).detail);
    state.treeData = await res.json();
    container.innerHTML = '';
    if (state.treeData.children && state.treeData.children.length > 0) {
      renderTreeChildren(container, state.treeData.children);
    } else {
      container.innerHTML = '<div style="padding:16px;color:var(--text-dim);font-size:12px;">마크다운 파일이 없습니다.</div>';
    }
  } catch (e) {
    container.innerHTML = `<div style="padding:16px;color:var(--red);font-size:12px;">오류: ${e.message}</div>`;
  }
}

function renderTreeChildren(container, children) {
  children.forEach(node => {
    const el = renderTreeNode(node);
    container.appendChild(el);
  });
}

function renderTreeNode(node) {
  const wrapper = document.createElement('div');
  wrapper.className = 'tree-node';

  const item = document.createElement('div');
  item.className = 'tree-item';
  item.dataset.path = node.path;
  item.dataset.type = node.type;

  if (node.type === 'directory') {
    const arrow = document.createElement('span');
    arrow.className = 'tree-arrow';
    arrow.textContent = '▶';
    const icon = document.createElement('span');
    icon.className = 'tree-icon';
    icon.textContent = '📁';
    const label = document.createElement('span');
    label.textContent = node.name;
    label.style.flex = '1';
    label.style.overflow = 'hidden';
    label.style.textOverflow = 'ellipsis';
    item.append(arrow, icon, label);

    const childContainer = document.createElement('div');
    childContainer.className = 'tree-children';
    childContainer.style.display = 'none';

    item.addEventListener('click', () => {
      const isOpen = childContainer.style.display !== 'none';
      childContainer.style.display = isOpen ? 'none' : 'block';
      arrow.classList.toggle('open', !isOpen);
      icon.textContent = isOpen ? '📁' : '📂';
    });

    if (node.children && node.children.length > 0) {
      renderTreeChildren(childContainer, node.children);
    }
    wrapper.append(item, childContainer);
  } else {
    const icon = document.createElement('span');
    icon.className = 'tree-icon';
    const isPptx = node.name.endsWith('.pptx');
    icon.textContent = isPptx ? '📊' : node.name.endsWith('.txt') ? '📝' : '📄';
    const label = document.createElement('span');
    label.textContent = node.name;
    label.style.flex = '1';
    label.style.overflow = 'hidden';
    label.style.textOverflow = 'ellipsis';
    item.append(icon, label);

    if (isPptx) {
      const dlIcon = document.createElement('span');
      dlIcon.className = 'tree-icon';
      dlIcon.textContent = '⬇';
      dlIcon.style.opacity = '0.6';
      dlIcon.style.fontSize = '11px';
      item.appendChild(dlIcon);
    }

    item.addEventListener('click', () => {
      // Deactivate previous
      document.querySelectorAll('.tree-item.active').forEach(el => el.classList.remove('active'));
      item.classList.add('active');
      if (isPptx) {
        downloadFile(node.path, node.name);
      } else {
        openFile(node.path, node.name);
      }
    });

    wrapper.appendChild(item);
  }

  return wrapper;
}

/* ── File Viewer ─────────────────────────────────────────────────── */
async function openFile(path, name) {
  try {
    const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
    if (!res.ok) throw new Error((await res.json()).detail);
    const data = await res.json();
    state.currentFile = data;

    // Update section-bar
    document.getElementById('viewer-filename').textContent = data.name;
    document.getElementById('viewer-path').textContent = data.path;
    document.getElementById('summarize-btn').style.display = '';
    document.getElementById('download-sidebar-btn').style.display = '';

    // Expand viewer if collapsed
    expandSection('viewer');

    // Render markdown
    const content = document.getElementById('viewer-content');
    const placeholder = document.getElementById('viewer-placeholder');
    if (placeholder) placeholder.remove();
    content.innerHTML = marked.parse(data.content);

    // Apply hljs to code blocks
    content.querySelectorAll('pre code').forEach(block => {
      hljs.highlightElement(block);
    });

    // Scroll to top
    document.getElementById('viewer-scroll').scrollTop = 0;

    // Mobile: auto-close sidebar after file selection
    if (isMobile()) closeSidebar();

    // Enable AI buttons
    document.getElementById('run-btn').disabled = false;
    document.getElementById('save-btn').disabled = false;

    // Clear previous AI result
    resetAIResult();
  } catch (e) {
    toast(`파일 열기 실패: ${e.message}`, 'error');
  }
}

/* ── Engine Select ───────────────────────────────────────────────── */
function selectEngine(engine) {
  state.engine = engine;
  document.getElementById('btn-claude').classList.toggle('active', engine === 'claude');
  document.getElementById('btn-codex').classList.toggle('active', engine === 'codex');
}

/* ── AI Run ──────────────────────────────────────────────────────── */
async function runAI() {
  if (!state.currentFile) return toast('먼저 파일을 선택해 주세요.', 'error');
  const prompt = document.getElementById('prompt-textarea').value.trim();
  if (!prompt) return toast('프롬프트를 입력해 주세요.', 'error');

  const runBtn = document.getElementById('run-btn');
  runBtn.disabled = true;
  runBtn.innerHTML = '<span class="spinner"></span> 실행 중...';

  const resultArea = document.getElementById('result-area');
  resultArea.innerHTML = '<div class="result-streaming" id="streaming-output"></div>';
  const streamEl = document.getElementById('streaming-output');
  state.aiResult = null;

  try {
    const res = await fetch('/api/ai/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        engine: state.engine,
        content: state.currentFile.content,
        prompt,
        file_path: state.currentFile.path,
      }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullOutput = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith('event: error')) continue;
        if (line.startsWith('data: ')) {
          const text = line.slice(6);
          // Check if this is a done event (comes after "event: done" line)
          fullOutput += text + '\n';
          streamEl.textContent = fullOutput;
          resultArea.scrollTop = resultArea.scrollHeight;
        }
      }
    }

    // Parse SSE properly
    const events = parseSSE(await getBodyText(res));
    // We already processed - just finalize
    state.aiResult = fullOutput.trim();

    // Render as markdown
    resultArea.innerHTML = `<div class="result-rendered">${marked.parse(state.aiResult)}</div>`;
    resultArea.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
    document.getElementById('save-btn').disabled = false;
    toast('AI 실행 완료', 'success');
  } catch (e) {
    toast(`AI 실행 오류: ${e.message}`, 'error');
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = '▶ 실행';
  }
}

// Better SSE streaming
async function runAIStream() {
  if (!state.currentFile) return toast('먼저 파일을 선택해 주세요.', 'error');
  const prompt = document.getElementById('prompt-textarea').value.trim();
  if (!prompt) return toast('프롬프트를 입력해 주세요.', 'error');

  const runBtn = document.getElementById('run-btn');
  runBtn.disabled = true;
  runBtn.innerHTML = '<span class="spinner"></span> 실행 중...';

  // 결과 섹션 펼치기
  expandSection('result-section');

  const resultArea = document.getElementById('result-area');
  resultArea.innerHTML = '<div id="streaming-output" style="white-space:pre-wrap;font-family:monospace;font-size:12px;"></div>';
  state.aiResult = null;

  const accumulated = [];

  try {
    const res = await fetch('/api/ai/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        engine: state.engine,
        content: state.currentFile.content,
        prompt,
        file_path: state.currentFile.path,
      }),
    });

    await readSSE(res, (event, data) => {
      if (event === 'chunk') {
        accumulated.push(data);
        const el = document.getElementById('streaming-output');
        if (el) {
          el.textContent = accumulated.join('');
          resultArea.scrollTop = resultArea.scrollHeight;
        }
      } else if (event === 'done') {
        state.aiResult = data.trim() || accumulated.join('').trim();
        resultArea.innerHTML = `<div class="result-rendered">${marked.parse(state.aiResult)}</div>`;
        resultArea.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
        toast('AI 실행 완료', 'success');
      } else if (event === 'error') {
        toast(`AI 오류: ${data}`, 'error');
      }
    });
  } catch (e) {
    toast(`AI 실행 오류: ${e.message}`, 'error');
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = '▶ 실행';
  }
}

// Override runAI to use streaming version
window.runAI = runAIStream;

/* ── Save to Issue ───────────────────────────────────────────────── */
async function saveToIssue() {
  if (!state.currentFile) return toast('파일을 먼저 선택해 주세요.', 'error');
  const prompt = document.getElementById('prompt-textarea').value.trim();

  const saveBtn = document.getElementById('save-btn');
  saveBtn.disabled = true;
  saveBtn.innerHTML = '<span class="spinner"></span>';

  try {
    const res = await fetch('/api/ai/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        engine: state.engine,
        file_path: state.currentFile.path,
        prompt: prompt || undefined,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '저장 실패');
    }

    const data = await res.json();
    toast(`저장 완료: ${data.name}`, 'success');
    loadTree();
  } catch (e) {
    toast(`저장 실패: ${e.message}`, 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 issue 저장';
  }
}

async function summarizeCurrentFile() {
  if (!state.currentFile) return toast('파일을 먼저 선택해 주세요.', 'error');
  // Scroll to AI panel, then trigger save
  document.getElementById('ai-panel').scrollIntoView({ behavior: 'smooth' });
  await saveToIssue();
}

/* ── Download ────────────────────────────────────────────────────── */
function downloadFile(path, name) {
  const url = `/api/download?path=${encodeURIComponent(path)}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = name || '';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function downloadCurrentFile() {
  if (!state.currentFile) return toast('파일을 먼저 선택해 주세요.', 'error');
  downloadFile(state.currentFile.path, state.currentFile.name);
}

function resetAIResult() {
  state.aiResult = null;
  const resultArea = document.getElementById('result-area');
  resultArea.innerHTML = '<div id="result-placeholder">실행 결과가 여기에 표시됩니다.</div>';
}

/* ── Upload ──────────────────────────────────────────────────────── */
function openUploadModal() {
  state.uploadFiles = [];
  state.uploadDestPath = '';
  document.getElementById('selected-files-info').textContent = '';
  document.getElementById('selected-dest-path').textContent = '/';
  document.getElementById('upload-btn').disabled = true;
  // Populate folder picker
  buildFolderPicker(document.getElementById('upload-folder-picker'), state.treeData);
  showModal('upload-modal');
}

function handleFileSelect(event) {
  state.uploadFiles = Array.from(event.target.files);
  updateFileInfo();
}

function handleDrop(event) {
  event.preventDefault();
  document.getElementById('drop-zone').classList.remove('drag-over');
  state.uploadFiles = Array.from(event.dataTransfer.files);
  updateFileInfo();
}

function updateFileInfo() {
  const info = document.getElementById('selected-files-info');
  if (state.uploadFiles.length === 0) {
    info.textContent = '';
    document.getElementById('upload-btn').disabled = true;
    return;
  }
  info.textContent = `선택된 파일: ${state.uploadFiles.map(f => f.name).join(', ')}`;
  document.getElementById('upload-btn').disabled = false;
}

function buildFolderPicker(container, treeNode, depth = 0) {
  container.innerHTML = '';
  if (!treeNode) return;
  // Root
  const rootItem = document.createElement('div');
  rootItem.className = 'folder-item' + (state.uploadDestPath === '' ? ' selected' : '');
  rootItem.innerHTML = `<span>📁</span> / (루트)`;
  rootItem.style.paddingLeft = '8px';
  rootItem.onclick = () => selectUploadDest('', rootItem, container);
  container.appendChild(rootItem);
  if (treeNode.children) {
    appendFolderItems(container, treeNode.children, 1);
  }
}

function appendFolderItems(container, nodes, depth) {
  nodes.forEach(node => {
    if (node.type !== 'directory') return;
    const item = document.createElement('div');
    item.className = 'folder-item' + (state.uploadDestPath === node.path ? ' selected' : '');
    item.style.paddingLeft = (8 + depth * 14) + 'px';
    item.innerHTML = `<span>📁</span> ${node.name}`;
    item.onclick = () => selectUploadDest(node.path, item, container);
    container.appendChild(item);
    if (node.children) appendFolderItems(container, node.children, depth + 1);
  });
}

function selectUploadDest(path, el, container) {
  state.uploadDestPath = path;
  container.querySelectorAll('.folder-item').forEach(i => i.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('selected-dest-path').textContent = '/' + (path || '');
}

async function doUpload() {
  if (state.uploadFiles.length === 0) return toast('파일을 선택해 주세요.', 'error');

  const btn = document.getElementById('upload-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 업로드 중...';

  let successCount = 0;
  for (const file of state.uploadFiles) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('dest_path', state.uploadDestPath);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json();
        toast(`${file.name} 업로드 실패: ${err.detail}`, 'error');
      } else {
        successCount++;
      }
    } catch (e) {
      toast(`${file.name} 업로드 오류: ${e.message}`, 'error');
    }
  }

  btn.disabled = false;
  btn.textContent = '업로드';

  if (successCount > 0) {
    toast(`${successCount}개 파일 업로드 완료`, 'success');
    closeModal('upload-modal');
    loadTree();
  }
}

/* ── Git ─────────────────────────────────────────────────────────── */
function openGitPushModal() {
  showModal('git-push-modal');
}

async function runGit(action) {
  const title = action === 'pull' ? '⬇ Git Pull' : '⬆ Git Push';
  document.getElementById('git-modal-title').textContent = `${title} 실행 중...`;
  document.getElementById('git-output').textContent = '';
  document.getElementById('git-close-btn').disabled = true;
  showModal('git-modal');

  const endpoint = `/api/git/${action}`;
  const options = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' };

  const outputEl = document.getElementById('git-output');
  try {
    const res = await fetch(endpoint, options);
    await readSSE(res, (event, data) => {
      outputEl.textContent += data;
      outputEl.scrollTop = outputEl.scrollHeight;
      if (event === 'done') {
        document.getElementById('git-modal-title').textContent = `${title} 완료`;
        toast(`${title} 완료`, 'success');
        loadTree();
      } else if (event === 'error') {
        document.getElementById('git-modal-title').textContent = `${title} 오류`;
        toast(`${title} 오류`, 'error');
      }
    });
  } catch (e) {
    outputEl.textContent += `\n오류: ${e.message}`;
  } finally {
    document.getElementById('git-close-btn').disabled = false;
  }
}

async function runGitPush() {
  const msg = document.getElementById('git-commit-msg').value.trim() || '웹 뷰어에서 업데이트';
  closeModal('git-push-modal');

  document.getElementById('git-modal-title').textContent = '⬆ Git Push 실행 중...';
  document.getElementById('git-output').textContent = '';
  document.getElementById('git-close-btn').disabled = true;
  showModal('git-modal');

  const outputEl = document.getElementById('git-output');
  try {
    const res = await fetch('/api/git/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
    await readSSE(res, (event, data) => {
      outputEl.textContent += data;
      outputEl.scrollTop = outputEl.scrollHeight;
      if (event === 'done') {
        document.getElementById('git-modal-title').textContent = '⬆ Git Push 완료';
        toast('Git Push 완료', 'success');
      } else if (event === 'error') {
        document.getElementById('git-modal-title').textContent = '⬆ Git Push 오류';
      }
    });
  } catch (e) {
    outputEl.textContent += `\n오류: ${e.message}`;
  } finally {
    document.getElementById('git-close-btn').disabled = false;
  }
}

/* ── SSE Reader ──────────────────────────────────────────────────── */
async function readSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = 'message';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split('\n\n');
    buffer = parts.pop(); // keep incomplete block

    for (const block of parts) {
      const lines = block.split('\n');
      let eventType = 'message';
      const dataLines = [];

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          dataLines.push(line.slice(6));
        }
      }

      if (dataLines.length > 0) {
        onEvent(eventType, dataLines.join('\n'));
      }
    }
  }
}

/* ── Modal helpers ───────────────────────────────────────────────── */
function showModal(id) {
  document.getElementById(id).style.display = 'flex';
}

function closeModal(id) {
  document.getElementById(id).style.display = 'none';
}

/* ── Toast ───────────────────────────────────────────────────────── */
function toast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

/* ── Collapsible Sections ────────────────────────────────────────── */
function toggleSection(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('collapsed');
}

function expandSection(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('collapsed');
}

/* ── Mobile Sidebar Drawer ───────────────────────────────────────── */
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar.classList.contains('open')) {
    closeSidebar();
  } else {
    sidebar.classList.add('open');
    document.getElementById('sidebar-overlay').classList.add('visible');
  }
}

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('visible');
}

function isMobile() {
  return window.innerWidth <= 768;
}

/* ── Sidebar Resize (desktop only) ──────────────────────────────── */
function setupResize() {
  const handle = document.getElementById('resize-handle');
  const sidebar = document.getElementById('sidebar');
  let startX, startW;

  handle.addEventListener('mousedown', e => {
    if (isMobile()) return;
    startX = e.clientX;
    startW = sidebar.offsetWidth;
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', () => {
      document.removeEventListener('mousemove', onMouseMove);
    }, { once: true });
  });

  function onMouseMove(e) {
    const newW = Math.max(180, Math.min(480, startW + e.clientX - startX));
    sidebar.style.width = newW + 'px';
  }
}

/* ── Keyboard shortcuts ──────────────────────────────────────────── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    ['settings-modal', 'upload-modal', 'git-modal', 'git-push-modal'].forEach(id => {
      const el = document.getElementById(id);
      if (el && el.style.display !== 'none') closeModal(id);
    });
  }
  // Ctrl+Enter to run AI
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    const runBtn = document.getElementById('run-btn');
    if (!runBtn.disabled) runAI();
  }
});
