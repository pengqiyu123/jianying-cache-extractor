const state = {
  connected: false,
  hotkey: 'shift+g',
  files: [],
  selectedRow: null,
  busy: false
};

const $ = (id) => document.getElementById(id);

const els = {
  connectionBadge: $('connectionBadge'),
  processBadge: $('processBadge'),
  versionText: $('versionText'),
  draftDirText: $('draftDirText'),
  detectBtn: $('detectBtn'),
  projectSelect: $('projectSelect'),
  confirmOpen: $('confirmOpen'),
  scanBtn: $('scanBtn'),
  phaseTitle: $('phaseTitle'),
  trackedText: $('trackedText'),
  cacheHint: $('cacheHint'),
  cacheTable: $('cacheTable'),
  hotkeyInput: $('hotkeyInput'),
  compoundBtn: $('compoundBtn'),
  restartBtn: $('restartBtn'),
  importBtn: $('importBtn'),
  uncomposeBtn: $('uncomposeBtn'),
  draftResult: $('draftResult'),
  openDraftBtn: $('openDraftBtn'),
  clearLogBtn: $('clearLogBtn'),
  logList: $('logList')
};

window.__onPyEvent = function onPyEvent(event, payload) {
  switch (event) {
    case 'action_started':
      state.busy = true;
      addLog(`开始: ${payload.action}`);
      break;
    case 'action_finished':
      state.busy = false;
      addLog(`结束: ${payload.action}`);
      break;
    case 'env_info':
      els.versionText.textContent = payload.version || '-';
      els.draftDirText.textContent = payload.draftDir || '-';
      addLog(`环境检测完成: ${payload.version || 'unknown'}`);
      break;
    case 'projects':
      renderProjects(payload.projects || []);
      addLog(`检测到 ${(payload.projects || []).length} 个近 30 分钟项目`);
      break;
    case 'process_status':
      updateProcess(payload.status);
      break;
    case 'selection':
      if (typeof payload.confirmed === 'boolean') {
        els.confirmOpen.checked = payload.confirmed;
      }
      if (payload.projectPath) {
        els.openDraftBtn.disabled = false;
        els.draftResult.textContent = payload.projectPath;
      }
      break;
    case 'scan_result':
      renderCacheTable(payload.files || []);
      addLog(`扫描到 ${(payload.files || []).length} 个缓存文件`);
      break;
    case 'tracked_media':
      renderTracked(payload);
      break;
    case 'button_states':
      updateButtonStates(payload.states || {});
      updatePhase(payload.phase);
      if (typeof payload.confirmed === 'boolean') {
        els.confirmOpen.checked = payload.confirmed;
      }
      break;
    case 'compound_result':
      addLog(payload.message || payload.status || '复合片段请求结束');
      break;
    case 'restart_result':
      addLog(payload.message || payload.status || '重启请求结束');
      break;
    case 'import_result':
      addLog(payload.message || payload.error || payload.status || '导入请求结束');
      break;
    case 'uncompose_result':
      addLog(payload.status || '解除复合请求结束');
      break;
    case 'draft_created':
      els.draftResult.textContent = `${payload.name || '-'}  ${payload.path || ''}`;
      addLog('草稿已创建，请回到剪映首页查看。');
      break;
    case 'error':
      addLog(`失败: ${payload.message || payload.code || '未知错误'}`);
      break;
    default:
      addLog(`${event}: ${JSON.stringify(payload)}`);
  }
};

window.addEventListener('pywebviewready', connectPywebview);
document.addEventListener('pywebviewready', connectPywebview);

window.addEventListener('DOMContentLoaded', () => {
  wireEvents();
  addLog('等待 pywebview 连接');
  waitForPywebviewApi();
});

function wireEvents() {
  els.detectBtn.addEventListener('click', () => pywebview.api.detect_environment());
  els.projectSelect.addEventListener('change', () => {
    const value = els.projectSelect.value;
    if (value !== '') {
      pywebview.api.select_project(Number(value));
    }
  });
  els.confirmOpen.addEventListener('change', () => pywebview.api.set_confirmed_open(els.confirmOpen.checked));
  els.scanBtn.addEventListener('click', () => pywebview.api.scan_cache());
  els.compoundBtn.addEventListener('click', () => pywebview.api.compound_clip(state.hotkey));
  els.restartBtn.addEventListener('click', () => pywebview.api.restart_jianying());
  els.importBtn.addEventListener('click', () => pywebview.api.auto_import());
  els.uncomposeBtn.addEventListener('click', () => pywebview.api.uncompose_clip());
  els.openDraftBtn.addEventListener('click', () => pywebview.api.open_draft_dir());
  els.clearLogBtn.addEventListener('click', () => {
    els.logList.innerHTML = '';
  });
  els.hotkeyInput.addEventListener('keydown', captureHotkey);
  els.hotkeyInput.addEventListener('focus', () => {
    els.hotkeyInput.value = '按下快捷键';
  });
  els.hotkeyInput.addEventListener('blur', () => {
    els.hotkeyInput.value = displayHotkey(state.hotkey);
  });
}

function connectPywebview() {
  if (state.connected || !window.pywebview || !window.pywebview.api) {
    return;
  }
  state.connected = true;
  setBadge(els.connectionBadge, '已连接', 'ok');
  addLog('pywebview 已连接');
  pywebview.api.detect_environment();
  pywebview.api.start_process_polling();
}

function waitForPywebviewApi(attempt = 0) {
  connectPywebview();
  if (state.connected || attempt >= 100) {
    if (!state.connected) {
      addLog('pywebview 连接超时');
    }
    return;
  }
  window.setTimeout(() => waitForPywebviewApi(attempt + 1), 100);
}

function renderProjects(projects) {
  els.projectSelect.innerHTML = '<option value="">请选择项目</option>';
  projects.forEach((project) => {
    const option = document.createElement('option');
    option.value = String(project.index);
    option.textContent = project.name;
    option.title = project.path;
    els.projectSelect.appendChild(option);
  });
}

function renderCacheTable(files) {
  state.files = files;
  state.selectedRow = null;
  els.cacheTable.innerHTML = '';
  if (!files.length) {
    els.cacheTable.innerHTML = '<tr><td colspan="5" class="empty">暂无缓存视频</td></tr>';
    els.cacheHint.textContent = '未找到缓存视频。';
    return;
  }
  els.cacheHint.textContent = '点击行选择要追踪的视频。';
  files.forEach((file) => {
    const tr = document.createElement('tr');
    tr.dataset.index = String(file.index);
    tr.innerHTML = `
      <td title="${escapeHtml(file.path)}">${escapeHtml(file.name)}</td>
      <td>${escapeHtml(file.sizeText || '-')}</td>
      <td>${escapeHtml(file.resolution || '-')}</td>
      <td>${escapeHtml(file.duration || '-')}</td>
      <td class="tag-${escapeHtml(file.tag || 'rejected')}">${escapeHtml(file.display || file.status || '-')}</td>
    `;
    tr.addEventListener('click', () => selectRow(tr, file.index));
    els.cacheTable.appendChild(tr);
  });
}

function selectRow(row, index) {
  if (state.selectedRow) {
    state.selectedRow.classList.remove('selected');
  }
  state.selectedRow = row;
  row.classList.add('selected');
  pywebview.api.select_media(Number(index));
}

function renderTracked(payload) {
  if (!payload || !payload.path) {
    els.trackedText.textContent = '未选择缓存视频';
    return;
  }
  els.trackedText.textContent = `${payload.name} (${payload.sizeText || '-'})`;
}

function updateButtonStates(states) {
  const mapping = {
    scan: els.scanBtn,
    compound: els.compoundBtn,
    restart: els.restartBtn,
    auto_import: els.importBtn,
    uncompose: els.uncomposeBtn
  };
  Object.entries(mapping).forEach(([key, button]) => {
    button.disabled = !states[key];
  });
}

function updateProcess(status) {
  const labels = {
    not_installed: '未安装',
    stopped: '未运行',
    starting: '启动中',
    running: '已打开',
    background: '后台运行',
    tray_only: '仅托盘'
  };
  const tone = status === 'running' ? 'ok' : (status === 'not_installed' ? 'error' : (status === 'stopped' ? 'muted' : 'busy'));
  setBadge(els.processBadge, labels[status] || status || '未检测', tone);
}

function updatePhase(phase) {
  const labels = {
    idle: '准备中',
    composite_done: '已复合片段',
    restarted: '已重启，请打开目标项目',
    imported: '已导入'
  };
  els.phaseTitle.textContent = labels[phase] || '准备中';
}

function captureHotkey(event) {
  event.preventDefault();
  if (['Shift', 'Control', 'Alt', 'Meta'].includes(event.key)) {
    return;
  }
  const parts = [];
  if (event.ctrlKey) parts.push('ctrl');
  if (event.shiftKey) parts.push('shift');
  if (event.altKey) parts.push('alt');
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key.toLowerCase();
  if (!parts.length || key === 'meta') {
    return;
  }
  parts.push(key);
  state.hotkey = parts.join('+');
  els.hotkeyInput.value = displayHotkey(state.hotkey);
  els.hotkeyInput.blur();
}

function displayHotkey(value) {
  return value.split('+').map((part) => {
    if (part === 'ctrl') return 'Ctrl';
    if (part === 'shift') return 'Shift';
    if (part === 'alt') return 'Alt';
    return part.length === 1 ? part.toUpperCase() : part;
  }).join(' + ');
}

function setBadge(el, text, tone) {
  el.textContent = text;
  el.className = `badge ${tone}`;
}

function addLog(message) {
  const row = document.createElement('div');
  row.className = 'log-entry';
  row.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  els.logList.appendChild(row);
  els.logList.scrollTop = els.logList.scrollHeight;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[char]));
}
