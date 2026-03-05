/* ── State ────────────────────────────────────────────────────────── */
const state = {
  engine: 'claude',
  currentFile: null,   // { path, name, content }
  viewerEditing: false,
  aiResult: null,      // last AI output string
  uploadFiles: [],
  uploadDestPath: '',
  treeData: null,
  autoWatchEnabled: false,
  autoWatchBusy: false,
  autoWatchStatus: null,
  autoWatchPollTimer: null,
  autoWatchLastSeenCount: 0,
  abortController: null, // for AI streaming cancellation
  promptTemplates: {},
  defaultPrompt: '',
};

const PROMPT_TEMPLATE_STORAGE_KEY = 'prompt_templates_v1';
const PROMPT_TEMPLATE_LAST_KEY = 'prompt_template_last_v1';

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

function parseMarkdownSafe(markdownText) {
  const rawHtml = marked.parse(markdownText || '');
  if (typeof DOMPurify !== 'undefined') {
    return DOMPurify.sanitize(rawHtml);
  }
  return rawHtml;
}

/* ── Mermaid.js setup ────────────────────────────────────────────── */
if (typeof mermaid !== 'undefined') {
  mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    securityLevel: 'loose',
  });
}

async function renderMermaidBlocks(containerEl) {
  if (typeof mermaid === 'undefined') return;

  // Update mermaid theme based on current theme
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  mermaid.initialize({ startOnLoad: false, theme: isDark ? 'dark' : 'default', securityLevel: 'loose' });

  const codeBlocks = containerEl.querySelectorAll('pre code.language-mermaid, pre code.hljs.language-mermaid');
  let idx = 0;
  for (const block of codeBlocks) {
    const pre = block.parentElement;
    const code = block.textContent;
    const id = `mermaid-${Date.now()}-${idx++}`;
    try {
      const { svg } = await mermaid.render(id, code);
      const div = document.createElement('div');
      div.className = 'mermaid-diagram';
      div.innerHTML = svg;
      pre.replaceWith(div);
    } catch (e) {
      // If mermaid fails, leave the code block as-is
      console.warn('Mermaid render error:', e);
    }
  }
}

/* ── Init ─────────────────────────────────────────────────────────── */
window.addEventListener('DOMContentLoaded', () => {
  loadConfig();
  loadTree();
  loadAutoWatchStatus();
  startAutoWatchPolling();
  setupResize();
  initTheme();
  initPromptTemplates();
  updateViewerActionButtons();
  loadGitStatus();
  setInterval(loadGitStatus, 30000); // refresh badge every 30s
});

/* ── Theme ───────────────────────────────────────────────────────── */
function initTheme() {
  const saved = localStorage.getItem('theme');
  if (saved) {
    applyTheme(saved);
  } else {
    // No saved preference — update button icon to match effective system theme
    const isLight = window.matchMedia('(prefers-color-scheme: light)').matches;
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) btn.innerHTML = `${isLight ? '🌙' : '☀️'} <span class="btn-text">테마</span>`;
  }
}

function toggleTheme() {
  // getAttribute returns null when no data-theme set → fall back to system preference
  const attr = document.documentElement.getAttribute('data-theme');
  const effective = attr || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  const next = effective === 'light' ? 'dark' : 'light';
  applyTheme(next);
  localStorage.setItem('theme', next);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const darkSheet = document.getElementById('hljs-dark-theme');
  const lightSheet = document.getElementById('hljs-light-theme');
  if (darkSheet && lightSheet) {
    darkSheet.disabled = theme === 'light';
    lightSheet.disabled = theme !== 'light';
  }
  // Update button icon
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) {
    btn.innerHTML = `${theme === 'light' ? '🌙' : '☀️'} <span class="btn-text">테마</span>`;
  }
}

function loadPromptTemplatesFromStorage() {
  try {
    const raw = localStorage.getItem(PROMPT_TEMPLATE_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    const result = {};
    Object.entries(parsed).forEach(([name, value]) => {
      if (typeof name !== 'string' || !name.trim()) return;
      if (typeof value !== 'string') return;
      result[name.trim()] = value;
    });
    return result;
  } catch {
    return {};
  }
}

function savePromptTemplatesToStorage() {
  const output = {};
  Object.entries(state.promptTemplates || {}).forEach(([name, value]) => {
    if (!name || name === '기본') return;
    output[name] = value;
  });
  localStorage.setItem(PROMPT_TEMPLATE_STORAGE_KEY, JSON.stringify(output));
}

function renderPromptTemplateOptions(selectedName = '') {
  const select = document.getElementById('prompt-template-select');
  if (!select) return;

  select.innerHTML = '';
  const names = Object.keys(state.promptTemplates || {});
  names.sort((a, b) => {
    if (a === '기본') return -1;
    if (b === '기본') return 1;
    return a.localeCompare(b, 'ko');
  });

  names.forEach(name => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    if (name === selectedName) option.selected = true;
    select.appendChild(option);
  });
}

function initPromptTemplates() {
  const textarea = document.getElementById('prompt-textarea');
  if (!textarea) return;

  state.defaultPrompt = textarea.value || '';
  const storedTemplates = loadPromptTemplatesFromStorage();
  state.promptTemplates = {
    기본: state.defaultPrompt,
    ...storedTemplates,
  };

  const last = localStorage.getItem(PROMPT_TEMPLATE_LAST_KEY) || '기본';
  const selected = state.promptTemplates[last] ? last : '기본';
  renderPromptTemplateOptions(selected);
  applyPromptTemplate(selected, { silent: true });
}

function applyPromptTemplate(name, options = {}) {
  const silent = options.silent === true;
  if (!name) return;
  const textarea = document.getElementById('prompt-textarea');
  if (!textarea) return;
  if (!state.promptTemplates[name]) return;

  textarea.value = state.promptTemplates[name];
  localStorage.setItem(PROMPT_TEMPLATE_LAST_KEY, name);
  if (!silent) toast(`프롬프트 템플릿 적용: ${name}`, 'success');
}

function savePromptTemplate() {
  const textarea = document.getElementById('prompt-textarea');
  if (!textarea) return;
  const content = textarea.value.trim();
  if (!content) return toast('저장할 프롬프트 내용을 입력해 주세요.', 'error');

  const rawName = prompt('저장할 템플릿 이름을 입력하세요:');
  const name = String(rawName || '').trim();
  if (!name) return;
  if (name === '기본') return toast('"기본" 이름은 사용할 수 없습니다.', 'error');

  state.promptTemplates[name] = textarea.value;
  savePromptTemplatesToStorage();
  renderPromptTemplateOptions(name);
  localStorage.setItem(PROMPT_TEMPLATE_LAST_KEY, name);
  toast(`템플릿 저장 완료: ${name}`, 'success');
}

function deletePromptTemplate() {
  const select = document.getElementById('prompt-template-select');
  if (!select) return;
  const selected = select.value;
  if (!selected) return;
  if (selected === '기본') return toast('기본 템플릿은 삭제할 수 없습니다.', 'error');

  const ok = confirm(`"${selected}" 템플릿을 삭제할까요?`);
  if (!ok) return;

  delete state.promptTemplates[selected];
  savePromptTemplatesToStorage();
  renderPromptTemplateOptions('기본');
  applyPromptTemplate('기본', { silent: true });
  toast(`템플릿 삭제 완료: ${selected}`, 'success');
}

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
    const searchQuery = document.getElementById('file-search-input')?.value || '';
    if (searchQuery.trim()) {
      filterTree(searchQuery);
    } else {
      container.innerHTML = '';
      if (state.treeData.children && state.treeData.children.length > 0) {
        renderTreeChildren(container, state.treeData.children);
      } else {
        container.innerHTML = '<div style="padding:16px;color:var(--text-dim);font-size:12px;">마크다운 파일이 없습니다.</div>';
      }
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

function hasExtension(name, extension) {
  if (!name || !extension) return false;
  return String(name).toLowerCase().endsWith(String(extension).toLowerCase());
}

function getFileExtension(path) {
  const value = String(path || '');
  const index = value.lastIndexOf('.');
  if (index < 0) return '';
  return value.slice(index).toLowerCase();
}

function isEditableTextFile(name) {
  return hasExtension(name, '.md') || hasExtension(name, '.txt');
}

function getViewerEditorValue() {
  const editor = document.getElementById('viewer-editor');
  return editor ? editor.value : '';
}

function hasUnsavedViewerChanges() {
  if (!state.viewerEditing || !state.currentFile) return false;
  return getViewerEditorValue() !== (state.currentFile.content || '');
}

function updateViewerActionButtons() {
  const hasCurrent = !!state.currentFile;
  const editable = hasCurrent && isEditableTextFile(state.currentFile.name);
  const editBtn = document.getElementById('viewer-edit-btn');
  const saveBtn = document.getElementById('viewer-save-btn');
  const cancelBtn = document.getElementById('viewer-cancel-btn');
  const summarizeBtn = document.getElementById('summarize-btn');
  const downloadBtn = document.getElementById('download-sidebar-btn');
  const summarizeEnabled = hasCurrent && isEditableTextFile(state.currentFile.name);

  if (summarizeBtn) summarizeBtn.style.display = summarizeEnabled ? '' : 'none';
  if (downloadBtn) downloadBtn.style.display = hasCurrent ? '' : 'none';

  if (!editable) {
    if (editBtn) editBtn.style.display = 'none';
    if (saveBtn) saveBtn.style.display = 'none';
    if (cancelBtn) cancelBtn.style.display = 'none';
    return;
  }

  if (editBtn) {
    editBtn.style.display = '';
    editBtn.classList.toggle('active', state.viewerEditing);
  }
  if (saveBtn) {
    saveBtn.style.display = state.viewerEditing ? '' : 'none';
    saveBtn.disabled = false;
    saveBtn.textContent = '💾';
  }
  if (cancelBtn) cancelBtn.style.display = state.viewerEditing ? '' : 'none';
}

function renderViewerPlaceholder() {
  const content = document.getElementById('viewer-content');
  const tocContainer = document.getElementById('toc-container');
  content.classList.remove('viewer-editing');
  content.innerHTML = '<div id="viewer-placeholder"><div class="placeholder-icon">📄</div><div>왼쪽 트리에서 마크다운 파일을 선택하세요</div></div>';
  if (tocContainer) tocContainer.style.display = 'none';
}

function resetViewerState() {
  state.currentFile = null;
  state.viewerEditing = false;
  document.getElementById('viewer-filename').textContent = '마크다운 뷰어';
  document.getElementById('viewer-path').textContent = '';
  const runBtn = document.getElementById('run-btn');
  const issueSaveBtn = document.getElementById('save-btn');
  if (runBtn) runBtn.disabled = true;
  if (issueSaveBtn) issueSaveBtn.disabled = true;
  renderViewerPlaceholder();
  updateViewerActionButtons();
}

async function renderViewerMarkdown(contentText) {
  const content = document.getElementById('viewer-content');
  const placeholder = document.getElementById('viewer-placeholder');
  if (placeholder) placeholder.remove();
  content.classList.remove('viewer-editing');
  content.innerHTML = parseMarkdownSafe(contentText || '');

  content.querySelectorAll('pre code').forEach(block => {
    hljs.highlightElement(block);
  });

  await renderMermaidBlocks(content);
  generateTOC(content);
}

function renderViewerEditor(contentText) {
  const content = document.getElementById('viewer-content');
  const tocContainer = document.getElementById('toc-container');
  const placeholder = document.getElementById('viewer-placeholder');
  if (placeholder) placeholder.remove();
  if (tocContainer) tocContainer.style.display = 'none';

  content.classList.add('viewer-editing');
  content.innerHTML = '';

  const editor = document.createElement('textarea');
  editor.id = 'viewer-editor';
  editor.className = 'viewer-editor';
  editor.value = contentText || '';
  content.appendChild(editor);
  editor.focus();
}

async function toggleViewerEditMode() {
  if (!state.currentFile) return toast('먼저 파일을 선택해 주세요.', 'error');
  if (!isEditableTextFile(state.currentFile.name)) return toast('이 파일은 편집할 수 없습니다.', 'error');

  if (state.viewerEditing) {
    await cancelViewerEdits();
    return;
  }

  state.viewerEditing = true;
  updateViewerActionButtons();
  renderViewerEditor(state.currentFile.content || '');
}

async function cancelViewerEdits(force = false) {
  if (!state.viewerEditing) return;
  if (!force && hasUnsavedViewerChanges()) {
    const shouldDiscard = confirm('저장되지 않은 변경사항이 있습니다. 편집을 취소할까요?');
    if (!shouldDiscard) return;
  }
  state.viewerEditing = false;
  updateViewerActionButtons();
  await renderViewerMarkdown(state.currentFile?.content || '');
}

async function saveViewerEdits() {
  if (!state.currentFile || !state.viewerEditing) return;
  const nextContent = getViewerEditorValue();
  const saveBtn = document.getElementById('viewer-save-btn');
  if (!saveBtn) return;

  saveBtn.disabled = true;
  saveBtn.textContent = '...';

  try {
    const res = await fetch('/api/file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: state.currentFile.path,
        content: nextContent,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '파일 저장 실패');
    }

    state.currentFile.content = nextContent;
    state.viewerEditing = false;
    updateViewerActionButtons();
    await renderViewerMarkdown(nextContent);
    toast(`저장 완료: ${state.currentFile.name}`, 'success');
    loadTree();
  } catch (e) {
    toast(`파일 저장 실패: ${e.message}`, 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = '💾';
  }
}

window.addEventListener('beforeunload', e => {
  if (!hasUnsavedViewerChanges()) return;
  e.preventDefault();
  e.returnValue = '';
});

function renderTreeNode(node) {
  const wrapper = document.createElement('div');
  wrapper.className = 'tree-node';
  wrapper.setAttribute('role', 'treeitem');

  const item = document.createElement('div');
  item.className = 'tree-item';
  item.dataset.path = node.path;
  item.dataset.type = node.type;
  item.setAttribute('tabindex', '0');

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
    item.setAttribute('aria-expanded', 'false');

    const childContainer = document.createElement('div');
    childContainer.className = 'tree-children';
    childContainer.style.display = 'none';
    childContainer.setAttribute('role', 'group');

    item.addEventListener('click', () => {
      const isOpen = childContainer.style.display !== 'none';
      childContainer.style.display = isOpen ? 'none' : 'block';
      arrow.classList.toggle('open', !isOpen);
      icon.textContent = isOpen ? '📁' : '📂';
      item.setAttribute('aria-expanded', String(!isOpen));
    });

    item.addEventListener('contextmenu', e => {
      showContextMenu(e, node.path, node.name, 'directory');
    });

    if (node.children && node.children.length > 0) {
      renderTreeChildren(childContainer, node.children);
    }
    wrapper.append(item, childContainer);
  } else {
    const icon = document.createElement('span');
    icon.className = 'tree-icon';
    const isPptx = hasExtension(node.name, '.pptx');
    const isPdf = hasExtension(node.name, '.pdf');
    const isImage =
      hasExtension(node.name, '.png') ||
      hasExtension(node.name, '.jpg') ||
      hasExtension(node.name, '.jpeg') ||
      hasExtension(node.name, '.gif') ||
      hasExtension(node.name, '.svg') ||
      hasExtension(node.name, '.webp');
    icon.textContent = isPptx ? '📊' : isPdf ? '📕' : isImage ? '🖼️' : hasExtension(node.name, '.txt') ? '📝' : '📄';
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
        if (isMobile()) {
          // Mobile: trigger native browser download/open dialog
          downloadFile(node.path, node.name);
        } else {
          // Desktop: show PPTX options modal
          openPptxModal(node.path, node.name);
        }
      } else {
        openFile(node.path, node.name);
      }
    });

    item.addEventListener('contextmenu', e => {
      showContextMenu(e, node.path, node.name, 'file');
    });

    wrapper.appendChild(item);
  }

  return wrapper;
}

const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']);
const PDF_EXTENSIONS = new Set(['.pdf']);
const MODAL_BINARY_EXTENSIONS = new Set(['.pptx', '.ppt']);
const DOWNLOAD_BINARY_EXTENSIONS = new Set(['.xlsx', '.xls', '.docx', '.doc', '.zip']);

function renderImagePreview(path, name) {
  const content = document.getElementById('viewer-content');
  const tocContainer = document.getElementById('toc-container');
  content.classList.remove('viewer-editing');
  content.innerHTML = '';
  if (tocContainer) tocContainer.style.display = 'none';

  const wrap = document.createElement('div');
  wrap.className = 'viewer-media-preview';
  const img = document.createElement('img');
  img.src = `/api/view?path=${encodeURIComponent(path)}`;
  img.alt = name || '';
  img.className = 'viewer-preview-image';
  wrap.appendChild(img);
  content.appendChild(wrap);
}

function renderPdfPreview(path) {
  const content = document.getElementById('viewer-content');
  const tocContainer = document.getElementById('toc-container');
  content.classList.remove('viewer-editing');
  content.innerHTML = '';
  if (tocContainer) tocContainer.style.display = 'none';

  const wrap = document.createElement('div');
  wrap.className = 'viewer-media-preview';
  const frame = document.createElement('iframe');
  frame.className = 'viewer-preview-pdf';
  frame.src = `/api/view?path=${encodeURIComponent(path)}`;
  frame.title = 'PDF 미리보기';
  wrap.appendChild(frame);
  content.appendChild(wrap);
}

/* ── File Viewer ─────────────────────────────────────────────────── */
async function openFile(path, name) {
  const ext = getFileExtension(path || name);
  const fileName = name || String(path || '').split('/').pop() || '';

  // Guard: binary files are handled separately from markdown rendering
  if (MODAL_BINARY_EXTENSIONS.has(ext)) {
    if (!isMobile()) {
      openPptxModal(path, fileName);
    } else {
      downloadFile(path, fileName);
    }
    return;
  }

  if (DOWNLOAD_BINARY_EXTENSIONS.has(ext)) {
    downloadFile(path, fileName);
    return;
  }
  try {
    if (
      state.viewerEditing &&
      state.currentFile &&
      hasUnsavedViewerChanges()
    ) {
      const shouldMove = confirm('저장되지 않은 변경사항이 있습니다. 저장하지 않고 다른 파일을 열까요?');
      if (!shouldMove) return;
    }

    if (IMAGE_EXTENSIONS.has(ext) || PDF_EXTENSIONS.has(ext)) {
      state.currentFile = { path, name: fileName, content: '' };
      state.viewerEditing = false;

      document.getElementById('viewer-filename').textContent = fileName;
      document.getElementById('viewer-path').textContent = path;
      updateViewerActionButtons();
      expandSection('viewer');

      if (IMAGE_EXTENSIONS.has(ext)) {
        renderImagePreview(path, fileName);
      } else {
        renderPdfPreview(path);
      }

      document.getElementById('viewer-scroll').scrollTop = 0;
      if (isMobile()) closeSidebar();
      document.getElementById('run-btn').disabled = true;
      document.getElementById('save-btn').disabled = true;
      resetAIResult();
      return;
    }

    const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
    if (!res.ok) throw new Error((await res.json()).detail);
    const data = await res.json();
    state.currentFile = data;
    state.viewerEditing = false;

    // Update section-bar
    document.getElementById('viewer-filename').textContent = data.name;
    document.getElementById('viewer-path').textContent = data.path;
    updateViewerActionButtons();

    // Expand viewer if collapsed
    expandSection('viewer');

    await renderViewerMarkdown(data.content);

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

/* ── TOC (Table of Contents) ─────────────────────────────────────── */
function generateTOC(contentEl) {
  const tocContainer = document.getElementById('toc-container');
  const tocList = document.getElementById('toc-list');
  tocList.innerHTML = '';

  const headings = contentEl.querySelectorAll('h1, h2, h3');
  if (headings.length < 2) {
    tocContainer.style.display = 'none';
    return;
  }

  headings.forEach((heading, i) => {
    // Add anchor id to heading
    const id = 'heading-' + i;
    heading.id = id;

    const li = document.createElement('li');
    li.className = `toc-item toc-${heading.tagName.toLowerCase()}`;
    li.textContent = heading.textContent;
    li.onclick = () => {
      heading.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    tocList.appendChild(li);
  });

  tocContainer.style.display = '';
}

function toggleToc() {
  const tocList = document.getElementById('toc-list');
  const toggle = document.getElementById('toc-toggle');
  const isCollapsed = tocList.classList.toggle('collapsed');
  toggle.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
}

function renderAIResult(rawText) {
  const resultArea = document.getElementById('result-area');
  state.aiResult = (rawText || '').trim();
  resultArea.innerHTML = `<div class="result-rendered">${parseMarkdownSafe(state.aiResult)}</div>`;
  resultArea.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
}

/* ── Engine Select ───────────────────────────────────────────────── */
function selectEngine(engine) {
  state.engine = engine;
  document.getElementById('btn-claude').classList.toggle('active', engine === 'claude');
  document.getElementById('btn-codex').classList.toggle('active', engine === 'codex');
}

/* ── AI Run ──────────────────────────────────────────────────────── */
async function runAI() {
  await runAIStream();
}

// Better SSE streaming with cancel support
async function runAIStream() {
  if (!state.currentFile) return toast('먼저 파일을 선택해 주세요.', 'error');
  const prompt = document.getElementById('prompt-textarea').value.trim();
  if (!prompt) return toast('프롬프트를 입력해 주세요.', 'error');
  const fileContent = state.viewerEditing ? getViewerEditorValue() : state.currentFile.content;

  const runBtn = document.getElementById('run-btn');
  const cancelBtn = document.getElementById('cancel-btn');
  runBtn.disabled = true;
  runBtn.innerHTML = '<span class="spinner"></span> 실행 중...';
  cancelBtn.style.display = '';

  // 결과 섹션 펼치기
  expandSection('result-section');

  const resultArea = document.getElementById('result-area');
  resultArea.innerHTML = '<div id="streaming-output" style="white-space:pre-wrap;font-family:monospace;font-size:12px;"></div>';
  state.aiResult = null;

  const accumulated = [];
  state.abortController = new AbortController();

  try {
    const res = await fetch('/api/ai/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        engine: state.engine,
        content: fileContent,
        prompt,
        file_path: state.currentFile.path,
      }),
      signal: state.abortController.signal,
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
        renderAIResult(data.trim() || accumulated.join('').trim());
        toast('AI 실행 완료', 'success');
      } else if (event === 'error') {
        toast(`AI 오류: ${data}`, 'error');
      }
    });
  } catch (e) {
    if (e.name === 'AbortError') {
      resultArea.innerHTML = '<div id="result-placeholder" style="color:var(--text-dim);font-style:italic;">실행이 취소되었습니다.</div>';
      toast('AI 실행 취소됨', 'info');
    } else {
      toast(`AI 실행 오류: ${e.message}`, 'error');
    }
  } finally {
    state.abortController = null;
    runBtn.disabled = false;
    runBtn.textContent = '▶ 실행';
    cancelBtn.style.display = 'none';
  }
}

function cancelAI() {
  if (state.abortController) {
    state.abortController.abort();
  }
}

// Override runAI to use streaming version
window.runAI = runAIStream;

/* ── Save to Issue ───────────────────────────────────────────────── */
async function saveToIssue() {
  if (!state.currentFile) return toast('파일을 먼저 선택해 주세요.', 'error');
  if (state.viewerEditing && hasUnsavedViewerChanges()) {
    return toast('편집 중인 변경사항을 먼저 저장해 주세요.', 'error');
  }
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
/* ── PPTX Modal (desktop) ────────────────────────────────────────── */
function openPptxModal(path, name) {
  state._pptxPath = path;
  state._pptxName = name;
  const el = document.getElementById('pptx-modal-filename');
  if (el) el.textContent = name;
  showModal('pptx-modal');
}

function openPptxNewTab() {
  if (!state._pptxPath) return;
  window.open(`/api/view?path=${encodeURIComponent(state._pptxPath)}`, '_blank');
  closeModal('pptx-modal');
}

function downloadPptxFile() {
  if (!state._pptxPath) return;
  downloadFile(state._pptxPath, state._pptxName);
  closeModal('pptx-modal');
}

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
        loadGitStatus();
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
        loadGitStatus();
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

/* ── Git Status Badge ────────────────────────────────────────────── */
async function loadGitStatus() {
  const badge = document.getElementById('git-badge');
  if (!badge) return;
  try {
    const res = await fetch('/api/git/status');
    if (!res.ok) { badge.style.display = 'none'; return; }
    const data = await res.json();
    if (!data.is_git_repo || !data.status) {
      badge.style.display = 'none';
      return;
    }
    // status is "git status --short" output; count non-empty lines
    const count = data.status.split('\n').filter(l => l.trim()).length;
    if (count === 0) {
      badge.style.display = 'none';
    } else {
      badge.textContent = count;
      badge.style.display = 'inline-flex';
      badge.title = data.status;
    }
  } catch {
    badge.style.display = 'none';
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
  el.setAttribute('role', 'alert');

  const msgSpan = document.createElement('span');
  msgSpan.className = 'toast-message';
  msgSpan.textContent = message;

  const closeBtn = document.createElement('button');
  closeBtn.className = 'toast-close';
  closeBtn.innerHTML = '✕';
  closeBtn.setAttribute('aria-label', '알림 닫기');
  closeBtn.onclick = () => el.remove();

  el.append(msgSpan, closeBtn);
  el.addEventListener('click', () => el.remove());
  container.appendChild(el);

  // Error toasts stay until manually closed; others auto-dismiss
  if (type !== 'error') {
    setTimeout(() => el.remove(), 3500);
  }
}

/* ── Collapsible Sections ────────────────────────────────────────── */
function toggleSection(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('collapsed');
  const isExpanded = !el.classList.contains('collapsed');
  // Update aria-expanded on the section bar
  const bar = el.querySelector('.section-bar[aria-expanded]');
  if (bar) bar.setAttribute('aria-expanded', String(isExpanded));
}

function expandSection(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('collapsed');
  const bar = el.querySelector('.section-bar[aria-expanded]');
  if (bar) bar.setAttribute('aria-expanded', 'true');
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

/* ── Context Menu ────────────────────────────────────────────────── */
let contextMenuTarget = null; // { path, name, type }

function showContextMenu(e, path, name, type) {
  e.preventDefault();
  contextMenuTarget = { path, name, type };
  const menu = document.getElementById('context-menu');
  menu.style.display = 'block';
  menu.style.left = Math.min(e.clientX, window.innerWidth - 180) + 'px';
  menu.style.top = Math.min(e.clientY, window.innerHeight - 120) + 'px';
}

function hideContextMenu() {
  document.getElementById('context-menu').style.display = 'none';
  contextMenuTarget = null;
}

document.addEventListener('click', hideContextMenu);

async function contextMenuAction(action) {
  if (!contextMenuTarget) return;
  const { path, name, type } = contextMenuTarget;
  hideContextMenu();

  if (action === 'download') {
    downloadFile(path, name);
  } else if (action === 'rename') {
    const newName = prompt(`새 이름을 입력하세요:`, name);
    if (!newName || newName === name) return;
    try {
      const res = await fetch('/api/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, new_name: newName }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '이름 변경 실패');
      }
      toast(`이름 변경 완료: ${newName}`, 'success');
      loadTree();
    } catch (e) {
      toast(`이름 변경 실패: ${e.message}`, 'error');
    }
  } else if (action === 'delete') {
    if (!confirm(`"${name}" 파일을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return;
    try {
      const res = await fetch('/api/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '삭제 실패');
      }
      toast(`삭제 완료: ${name}`, 'success');
      if (state.currentFile && state.currentFile.path === path) {
        resetViewerState();
      }
      loadTree();
    } catch (e) {
      toast(`삭제 실패: ${e.message}`, 'error');
    }
  }
}

/* ── Tree Keyboard Navigation ────────────────────────────────────── */
document.addEventListener('keydown', e => {
  const active = document.activeElement;
  if (!active || !active.classList.contains('tree-item')) return;
  if (!['ArrowUp', 'ArrowDown', 'Enter', ' '].includes(e.key)) return;
  e.preventDefault();

  if (e.key === 'Enter' || e.key === ' ') {
    active.click();
    return;
  }

  const items = Array.from(document.querySelectorAll('#tree-container .tree-item'));
  const visible = items.filter(el => {
    let node = el.closest('.tree-node');
    while (node) {
      if (node.style.display === 'none') return false;
      node = node.parentElement?.closest('.tree-node');
    }
    return true;
  });
  const idx = visible.indexOf(active);
  if (idx < 0) return;

  if (e.key === 'ArrowDown' && idx < visible.length - 1) {
    visible[idx + 1].focus();
  } else if (e.key === 'ArrowUp' && idx > 0) {
    visible[idx - 1].focus();
  }
});

/* ── File Search / Filter ────────────────────────────────────────── */
function filterTree(query) {
  const clearBtn = document.getElementById('search-clear-btn');
  clearBtn.style.display = query ? '' : 'none';

  const items = document.querySelectorAll('#tree-container .tree-node');
  if (!query) {
    // Reset: show all, collapse all
    items.forEach(node => {
      node.style.display = '';
      const item = node.querySelector('.tree-item');
      if (item) item.classList.remove('search-highlight');
    });
    return;
  }

  const lowerQ = query.toLowerCase();

  // For each tree node, determine visibility
  items.forEach(node => {
    const item = node.querySelector('.tree-item');
    if (!item) return;

    const isDir = item.dataset.type === 'directory';
    const name = (item.textContent || '').toLowerCase();

    if (isDir) {
      // Directory: show if any child matches
      const childNodes = node.querySelectorAll('.tree-item[data-type="file"]');
      let hasMatch = false;
      childNodes.forEach(child => {
        if ((child.textContent || '').toLowerCase().includes(lowerQ)) {
          hasMatch = true;
        }
      });
      node.style.display = hasMatch ? '' : 'none';
      if (hasMatch) {
        // Expand directory
        const childContainer = node.querySelector('.tree-children');
        const arrow = node.querySelector('.tree-arrow');
        if (childContainer) childContainer.style.display = 'block';
        if (arrow) arrow.classList.add('open');
      }
      item.classList.remove('search-highlight');
    } else {
      // File: match name
      const match = name.includes(lowerQ);
      node.style.display = match ? '' : 'none';
      item.classList.toggle('search-highlight', match);
    }
  });
}

function clearSearch() {
  const input = document.getElementById('file-search-input');
  input.value = '';
  filterTree('');
  input.focus();
}

/* ── Keyboard shortcuts ──────────────────────────────────────────── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (state.viewerEditing) {
      cancelViewerEdits();
      return;
    }
    ['settings-modal', 'upload-modal', 'git-modal', 'git-push-modal'].forEach(id => {
      const el = document.getElementById(id);
      if (el && el.style.display !== 'none') closeModal(id);
    });
    // Clear search on Escape
    const searchInput = document.getElementById('file-search-input');
    if (document.activeElement === searchInput) {
      clearSearch();
      searchInput.blur();
    }
  }
  // Ctrl+K / Cmd+K to focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.getElementById('file-search-input');
    searchInput.focus();
    searchInput.select();
    // Open sidebar on mobile
    if (isMobile()) {
      document.getElementById('sidebar').classList.add('open');
      document.getElementById('sidebar-overlay').classList.add('visible');
    }
  }
  // Ctrl+Enter to run AI
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    const runBtn = document.getElementById('run-btn');
    if (!runBtn.disabled) runAI();
  }
  // Ctrl+S / Cmd+S to save viewer edits
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    if (!state.viewerEditing) return;
    e.preventDefault();
    saveViewerEdits();
  }
});
