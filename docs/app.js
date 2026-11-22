// docs/config.js is loaded first on GitHub Pages. Leave unset for same-origin hosting.
const rawApiBase = (window.BACON_API_BASE || '').trim();
const apiBase = rawApiBase.replace(/\/+$/, '');
const apiUrl = path => apiBase + path;
const $ = (id) => document.getElementById(id);
const state = { ipa: null, plugin: null, working: false, ready: false };
const formatSize = (bytes) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
let maxIpa = 2048 * 1024 * 1024;
let maxPlugin = 32 * 1024 * 1024;

function message(text, isError = true) {
  $('message').textContent = text;
  $('message').hidden = !text;
  $('message').style.color = isError ? '#ffd4d4' : '#d6efea';
}
function updateButton() {
  $('injectButton').disabled = !state.ipa || !state.plugin || !state.ready || state.working;
  $('injectButton').innerHTML = state.working ? '正在處理…' : '開始注入 <span class="arrow">↗</span>';
}
function setFile(kind, file) {
  if (!file) return;
  const extension = kind === 'ipa' ? '.ipa' : '.dylib';
  if (!file.name.toLowerCase().endsWith(extension)) return message(`這裡只能選擇 ${extension} 格式的檔案`);
  const max = kind === 'ipa' ? maxIpa : maxPlugin;
  if (file.size > max) return message(`檔案超過上傳上限：${formatSize(max)}`);
  state[kind] = file;
  $(`${kind}Label`).textContent = `${file.name} · ${formatSize(file.size)}`;
  $(`${kind}Drop`).classList.add('selected');
  $('result').hidden = true;
  message('');
  updateButton();
}
function setupDrop(kind) {
  const drop = $(`${kind}Drop`), input = $(`${kind}File`);
  drop.addEventListener('click', () => input.click());
  drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
  input.addEventListener('change', () => setFile(kind, input.files?.[0]));
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('dragging'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
  drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('dragging'); setFile(kind, e.dataTransfer.files?.[0]); });
}
setupDrop('ipa'); setupDrop('plugin');
async function setup() {
  try {
    if (location.hostname.endsWith('github.io') && !apiBase) {
      throw new Error('CONFIG_REQUIRED');
    }
    const r = await fetch(apiUrl('/api/config'), { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const config = await r.json();
    maxIpa = config.max_ipa_mb * 1024 * 1024;
    maxPlugin = config.max_plugin_mb * 1024 * 1024;
    $('passwordRow').hidden = !config.password_required;
    state.ready = config.ready;
    $('serverBadge').className = config.ready ? 'status ready' : 'status error';
    $('serverBadge').innerHTML = `<span class="dot"></span>${config.ready ? '注入引擎已就緒' : '尚未安裝 zsign'}`;
    if (!config.ready) message('請先在伺服器安裝 zsign；詳細方法請看專案 README。');
  } catch (error) {
    $('serverBadge').className = 'status error';
    $('serverBadge').innerHTML = '<span class="dot"></span>無法連線伺服器';
    message(error?.message === 'CONFIG_REQUIRED' ? '請先在 GitHub 的 docs/config.js 填入 Render API 網址。' : '無法連線注入伺服器，請檢查 Render 是否啟動、API 網址與 CORS_ORIGINS 設定。');
  }
  updateButton();
}
function showProgress(percent, text) {
  $('progressArea').hidden = false;
  $('progressText').textContent = text;
  $('progressPercent').textContent = `${percent}%`;
  $('progressBar').style.width = `${percent}%`;
}
$('injectButton').addEventListener('click', () => {
  if (state.working || !state.ipa || !state.plugin || !state.ready) return;
  state.working = true; updateButton(); message(''); $('result').hidden = true;
  const data = new FormData(); data.append('ipa', state.ipa); data.append('plugin', state.plugin);
  const xhr = new XMLHttpRequest(); xhr.open('POST', apiUrl('/api/inject'));
  if (!$('passwordRow').hidden) xhr.setRequestHeader('X-App-Password', $('password').value);
  xhr.timeout = 720000;
  showProgress(0, '上傳檔案中…');
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) showProgress(Math.min(98, Math.round(e.loaded / e.total * 98)), '上傳檔案中…'); };
  xhr.upload.onload = () => showProgress(99, '伺服器正在注入並重新打包…');
  xhr.onload = () => {
    state.working = false; updateButton(); $('progressArea').hidden = true;
    let payload; try { payload = JSON.parse(xhr.responseText); } catch { payload = {}; }
    if (xhr.status < 200 || xhr.status >= 300) return message(payload.detail || `伺服器發生錯誤（HTTP ${xhr.status}）`);
    $('result').hidden = false;
    $('resultDetails').textContent = `${payload.app_name} · ${payload.bundle_id} · ${payload.plugin_name} · ${formatSize(payload.size_bytes)}`;
    $('download').href = apiUrl(payload.download_url);
    $('download').setAttribute('download', payload.filename);
    $('result').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };
  xhr.onerror = () => { state.working = false; updateButton(); $('progressArea').hidden = true; message('網路連線中斷，請重新上傳。'); };
  xhr.ontimeout = () => { state.working = false; updateButton(); $('progressArea').hidden = true; message('處理逾時，請縮小 IPA 或查看伺服器紀錄。'); };
  xhr.send(data);
});
setup();
