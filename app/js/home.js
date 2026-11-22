// Головна: проєкти, новий монтаж, записи Twitch, місце на диску.
// ── проєкти ──
const videoName = v => !v ? '' : /^https?:/.test(v) ? `Twitch · ${v.split('/').pop()}` : v.split(/[\\/]/).pop();   // файл — його назва, запис Twitch — його номер
const projName = p => p.name || videoName(p.video) || 'Без назви';
let homeProjects = [], twVideos = null, twPoll = null;
const fmtSize = b => b < 2 ** 30 ? `${Math.round(b / 2 ** 20)} МБ` : `${(b / 2 ** 30).toFixed(1)} ГБ`;
const fmtLen = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? `${h}:${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}` : `${m}:${String(s % 60).padStart(2, '0')}`; };
async function loadHome() {
  loadTwitch(); loadStore();
  const ps = homeProjects = await api('/api/projects');
  const last = ps.find(p => P && p.id === P.id) || ps[0];                // продовжити — відкритий зараз або останній змінений
  $('#hCont').innerHTML = last ? (() => { const tw = /^https?:/.test(last.video || ''), cov = last.cover || (last.video && !tw ? `/api/cover?id=${last.id}` : '');
    return `<button class="hcont" data-open="${last.id}"><span class="hc-cov">${cov ? `<img src="${esc(cov)}" alt="" onerror="this.remove()">` : ''}</span>
      <span class="hc-txt"><span class="hc-k">Продовжити</span><b>${esc(projName(last))}</b><small>${last.clips.length ? plural(last.clips.length, 'кліп', 'кліпи', 'кліпів') : 'кліпів ще немає'}</small></span></button>`; })() : '';
  $('#plist').innerHTML = ps.map(p => {
    const files = p.renders.flatMap(r => r.files), seen = new Set(), shorts = files.filter(f => f.exists && !seen.has(f.path) && seen.add(f.path)), tw = /^https?:/.test(p.video || '');
    const cov = p.cover || (p.video && !tw ? `/api/cover?id=${p.id}` : '');
    return `<div class="pj ${P && P.id === p.id ? 'cur' : ''}" data-open="${p.id}">
      <div class="pcov" data-cov="${esc(p.video || '')}">${/\p{L}/u.test(projName(p)[0]) ? esc(projName(p)[0].toUpperCase()) : '▶'}${cov ? `<img src="${esc(cov)}" alt="" onerror="this.remove()">` : ''}${tw ? '<span class="src">Twitch</span>' : ''}</div>
      <div class="pact">${p.renders[0] ? `<button data-reveal="${esc(p.renders[0].out)}" title="Папка з шортами">Папка</button><button data-publish="${p.id}">Опублікувати</button>` : ''}<button data-del="${p.id}" title="Видалити проєкт" aria-label="Видалити проєкт">✕</button></div>
      <div class="pinfo"><b>${esc(projName(p))}</b><small>${new Date(p.updated * 1000).toLocaleDateString(LOCALE, {day: 'numeric', month: 'short'})} · ${[p.clips.length ? plural(p.clips.length, 'кліп', 'кліпи', 'кліпів') : 'кліпів ще немає', shorts.length ? plural(shorts.length, 'шорт', 'шорти', 'шортів') : p.clips.length ? 'не зарендерено' : ''].filter(Boolean).join(' · ')}</small></div>
      ${shorts.length ? `<div class="pshorts">${shorts.slice(0, 6).map(f => `<div class="sf" data-play="${esc(f.path)}"><img src="${fileUrl(f.thumb)}" alt="" onerror="this.remove()"><span>${fmt(f.len ?? f.b - f.a).replace(/\.\d$/, '')}</span></div>`).join('')}${shorts.length > 6 ? `<span class="more">+${shorts.length - 6}</span>` : ''}</div>` : ''}
    </div>`;
  }).join('');
}
async function loadTwitch(refresh) {                              // свої записи (після входу) або канал за назвою; список тримаємо, щоб не питати Twitch щоразу
  const [st, brands] = await Promise.all([api('/api/twitch').catch(() => ({})), pub.brands || api('/api/brands').catch(() => ({}))]);
  pub.brands ||= brands; if (brands.twitch) $('#twIcon').innerHTML = `<svg viewBox="0 0 24 24"><path d="${brands.twitch.path}"/></svg>`;
  const ch = cfg.twitch_channel || '', who = st.user;
  clearTimeout(twPoll); twHead(st);
  if (st.pending?.code) twPoll = setTimeout(() => loadTwitch(true), 2000);   // вхід триває: код у шапці, чекаємо підтвердження
  if (st.pending?.err) msg('Вхід у Twitch: ' + st.pending.err, 1);
  const other = ch && (!who || ch.toLowerCase() !== who.login);   // чужий канал — його записи; порожньо — свої
  $('#twCtl').innerHTML = (other ? `<span class="chtag">${esc(ch)}${who ? '<button data-tw="mine" title="Назад до моїх етерів" aria-label="Назад до моїх етерів">✕</button>' : ''}</span>` : '') +
    `<form class="chsearch" id="twCh"><input id="twChIn" placeholder="${who ? 'Інший канал' : 'Канал на Twitch'}" aria-label="Канал на Twitch"><button class="sec">Знайти</button></form>`;
  if (!who && !ch) { twVideos = null; $('#twList').innerHTML = `<p class="mut">${st.login ? 'Увійди через Twitch угорі праворуч — тут з\'являться твої етери' : 'Знайди канал — тут з\'являться його етери'}</p>`; return; }
  if (twVideos && !refresh) return renderTwitch();
  $('#twList').innerHTML = '<p class="mut">Завантажую записи…</p>';
  try { twVideos = await api('/api/twitch/videos' + (other ? '?channel=' + encodeURIComponent(ch) : '')); renderTwitch(); }
  catch (e) { twVideos = null; $('#twList').innerHTML = `<p class="mut">${esc(e.message)}</p>`; }
}
function twHead(st) {                                            // акаунт Twitch у шапці: увійти або хто ти
  const b = $('#twHead'), icon = pub.brands?.twitch ? `<i class="twi"><svg viewBox="0 0 24 24"><path d="${pub.brands.twitch.path}"/></svg></i>` : '';
  b.hidden = !st.login && !st.user; b.className = st.user || st.pending?.code ? 'ghost twh' : 'sec twh'; twLast = st;
  b.innerHTML = st.user ? `<img src="${esc(st.user.avatar)}" alt="">${esc(st.user.name)}` : st.pending?.code ? `${icon}Код ${esc(st.pending.code)}` : `${icon}Увійти через Twitch`;
  b.title = st.user ? 'Твої етери на Twitch' : 'Увійти через Twitch, щоб бачити свої етери';
}
let twLast = {};
$('#twHead').onclick = async e => {                               // не увійшов — вхід; увійшов чи чекає коду — меню акаунта
  const st = twLast;
  if (!st.user && !st.pending?.code) return twAction('login');
  $('#twMenu').innerHTML = st.user
    ? `<div class="twm"><img src="${esc(st.user.avatar)}" alt="">${esc(st.user.name)}</div><button data-tw="mine">Мої етери</button><button data-tw="refresh">Оновити список</button><button data-tw="logout">Вийти</button>`
    : `<p>Підтверди вхід на Twitch цим кодом</p><span class="twcode"><b>${esc(st.pending.code)}</b></span><button data-tw="activate" class="pri">Відкрити Twitch</button><button data-tw="cancel">Скасувати вхід</button>`;
  togglePop('#twMenu', e);
};
function renderTwitch() {
  const byVideo = new Map(homeProjects.map(p => [p.video, p]));
  $('#twList').innerHTML = twVideos.length ? twVideos.map((v, i) => `<button class="vc ${byVideo.has(v.url) ? 'inp' : ''}" data-vod="${i}">
      <span class="vt">${v.thumb ? `<img src="${esc(v.thumb)}" alt="" loading="lazy" onerror="this.remove()">` : ''}<i>${fmtLen(v.dur)}</i>${byVideo.has(v.url) ? `<em>${byVideo.get(v.url).clips.length ? 'У монтажі · ' + plural(byVideo.get(v.url).clips.length, 'кліп', 'кліпи', 'кліпів') : 'У монтажі'}</em>` : ''}</span>
      <b>${esc(v.title)}</b><small>${[v.date && new Date(v.date).toLocaleDateString(LOCALE, {day: 'numeric', month: 'short'}), v.views && (v.views >= 1000 ? `${Math.round(v.views / 1000)} тис. переглядів` : plural(v.views, 'перегляд', 'перегляди', 'переглядів'))].filter(Boolean).join(' · ')}</small></button>`).join('')
    : '<p class="mut">Записів етерів немає</p>';
  for (const v of twVideos) {                                     // проєкт із цим записом без обкладинки — бере її зі списку
    const c = v.thumb && [...$$('.pcov[data-cov]')].find(x => x.dataset.cov === v.url); if (c && !c.querySelector('img')) c.insertAdjacentHTML('beforeend', `<img src="${esc(v.thumb)}" alt="" onerror="this.remove()">`);
  }
}
$('#hLink').onsubmit = async e => {                               // головна дія: запис Twitch → новий проєкт
  e.preventDefault(); const inp = $('#hUrl'), url = inp.value.trim();
  inp.setCustomValidity(/twitch\.tv\/(?:\w+\/)?videos?\/\d+/.test(url) ? '' : 'Потрібне посилання на запис: twitch.tv/videos/…'); if (!inp.reportValidity()) return;
  inp.value = ''; openLink(url, $('#hLink .pri'));
};
$('#hUrl').oninput = e => e.target.setCustomValidity('');
$('#hFile').onclick = async () => { const {path} = await api('/api/pick', {kind: 'video'}); if (path) projectFor(path, path.split(/[\\/]/).pop().replace(/\.[^.]+$/, '')); };
$('#new').onclick = e => { togglePop('#nPop', e); if ($('#nPop').classList.contains('on')) $('#nUrl').focus(); };
$('#nFile').onclick = () => { $('#nPop').classList.remove('on'); $('#hFile').click(); };
$('#nLink').onsubmit = e => { e.preventDefault(); const url = $('#nUrl').value.trim(); $('#nPop').classList.remove('on'); $('#nUrl').value = ''; openLink(url, $('#new')); };
$('#twList').onclick = async e => {                               // запис — у новий проєкт; уже є проєкт з ним — відкрити його
  const b = e.target.closest('[data-vod]'); if (!b) return; const v = twVideos[+b.dataset.vod];
  projectFor(v.url, v.title, v.thumb);
};
$('#twCtl').addEventListener('submit', async e => {
  e.preventDefault(); const ch = $('#twChIn').value.trim().replace(/^.*twitch\.tv\//, '').replace(/[/?#].*$/, '');
  cfg.twitch_channel = ch; await api('/api/config', {twitch_channel: ch}).catch(() => {}); twVideos = null; loadTwitch(true);
});
async function twAction(a) {                                      // дії акаунта й списку: з меню шапки й з розділу «Твої етери»
  $('#twMenu').classList.remove('on');
  try {
    if (a === 'login') { await api('/api/twitch/login', {}); api('/api/open', {link: 'twitch_activate'}); }
    if (a === 'activate') api('/api/open', {link: 'twitch_activate'});
    if (a === 'logout' || a === 'cancel') { await api('/api/twitch/logout', {}); twVideos = null; }
    if (a === 'mine') { cfg.twitch_channel = ''; await api('/api/config', {twitch_channel: ''}).catch(() => {}); twVideos = null; return loadTwitch(true); }
    if (a === 'mine' || a === 'refresh') show('home');
    loadTwitch(a === 'refresh' || a === 'login');
  } catch (err) { msg(err.message, 1); }
}
$('#twCtl').addEventListener('click', e => { const a = e.target.closest('[data-tw]')?.dataset.tw; if (a) twAction(a); });
$('#twMenu').onclick = e => { const a = e.target.closest('[data-tw]')?.dataset.tw; if (a) twAction(a); };
async function setupAI(btn) {                                     // локальний ШІ (~5 ГБ) — для пошуку моментів за змістом мови
  try {
    await busy(btn, 'Локальний ШІ', [['ai', 900]], async () => {
      await api('/api/ai/setup', {});
      for (;;) {
        await new Promise(r => setTimeout(r, 1500)); const ai = await api('/api/ai');
        if (ai.model) return; if (ai.setup?.err) throw new Error(ai.setup.err); if (!ai.setup?.running) return;
      }
    }, 'ai');
  } catch (err) { $('#storeTotal').textContent = 'ШІ: ' + err.message; }
  loadStore();
}
async function loadStore() {                                      // що займає місце; усе, що тут, завантажиться чи порахується знову, коли знадобиться
  const rows = await api('/api/storage').catch(() => []);
  $('#storeTotal').textContent = rows.length ? fmtSize(rows.reduce((s, r) => s + r.size, 0)) : '';
  $('#storeRows').innerHTML = rows.map(r => `<b>${esc(r.name)}</b><span>${fmtSize(r.size)}</span>${r.key === 'ai' && !r.size
    ? '<button data-setup="ai" class="sec">Встановити</button>' : `<button data-clear="${r.key}" ${r.size ? '' : 'disabled'}>Очистити</button>`}`).join('');
}
$('#storeRows').onclick = async e => {
  if (e.target.closest('[data-setup]')) return setupAI(e.target.closest('[data-setup]'));
  const b = e.target.closest('[data-clear]'); if (!b) return; const k = b.dataset.clear, name = b.previousElementSibling.previousElementSibling.textContent;
  if (['models', 'ai'].includes(k) && !confirm(`Видалити «${name}»? Завантажиться знову, коли знадобиться.`)) return;
  b.disabled = true; await api('/api/storage/clear', {key: k}).catch(err => msg(err.message, 1)); loadStore();
  if (k === 'view' && P) loadVideo();                             // прев'ю відкритого проєкту — підготувати знову
};
$('#hCont').onclick = async e => { const t = e.target.closest('[data-open]'); if (t) { await openProject(await api('/api/project?id=' + t.dataset.open)); show('editor'); } };
$('#plist').onclick = async e => {
  const t = e.target.closest('[data-open],[data-reveal],[data-del],[data-play],[data-publish]'); if (!t) return;
  if (t.dataset.publish) { show('pub'); return loadPub(t.dataset.publish); }
  if (t.dataset.reveal) return api('/api/reveal', {path: t.dataset.reveal});
  if (t.dataset.del) {
    if (!confirm('Видалити проєкт? Відео й готові шортси на диску залишаться.')) return;
    await api('/api/project/delete', {id: t.dataset.del}); if (P && P.id === t.dataset.del) P = null; return loadHome();
  }
  if (t.dataset.play) { $('#mv').src = fileUrl(t.dataset.play); $('#mv').dataset.path = t.dataset.play; $('#modal').classList.add('on'); return $('#mv').play(); }
  await openProject(await api('/api/project?id=' + t.dataset.open)); show('editor');
};
$('#mclose').onclick = () => { $('#mv').pause(); $('#modal').classList.remove('on'); };
$('#modal').onclick = e => { if (e.target.id === 'modal') $('#mclose').click(); };
$('#mreveal').onclick = () => api('/api/reveal', {path: $('#mv').dataset.path});

async function projectFor(video, name, cover) {                     // проєкт = одне відео з його назвою; відоме відео — той самий проєкт
  const ex = (await api('/api/projects')).find(p => p.video === video);
  await openProject(ex ? await api('/api/project?id=' + ex.id) : await api('/api/project/new', {video, name, cover}));
  show('editor');
}
async function openProject(p) {
  await api('/api/project/open', {id: p.id});
  P = p; P.elements = P.elements.filter(e => TYPES[e.type]); multi.clear(); migrateMusic();   // типів, яких більше немає (емодзі, позначки, алерти), — геть sel = selCue = -1; selEl = null; curve = []; dur = 0; arts.clear();
  const oldLang = subsEls()[0]?.lang;                                // мова й слів на екрані були в елементі «Субтитри» — тепер біля генерації
  if (oldLang && ['uk', 'en'].includes(oldLang) && !cfg.stt_lang) { cfg.stt_lang = oldLang; api('/api/config', {stt_lang: oldLang}).catch(() => {}); }
  $('#pname').value = P.name; resetHist(); renderAll(); loadVideo();
}
let videoMissing = false;
function videoChip(text) {                                         // відео — основа проєкту: обирається раз; нове відео — новий проєкт з головної
  const c = $('#videoChip'); c.querySelector('span').textContent = videoMissing ? 'Файл не знайдено — вказати' : text || (P && P.video ? videoName(P.video) : 'Обрати відео');
  c.hidden = !!(P && P.video && !videoMissing); c.classList.toggle('miss', videoMissing);   // назва вже в назві проєкту — не дублюємо
  c.title = videoMissing ? 'Файл перемістили чи видалили. Вкажи, де він тепер, — монтаж збережеться' : '';
}
async function pickVideo(relink) {                                 // relink — той самий запис в іншому місці: кліпи, субтитри й область лишаються
  const {path} = await api('/api/pick', {kind: 'video'}); if (!path) return;
  P.video = path; videoMissing = false; if (!relink) { P.region = null; P.clips = []; P.cues = []; P.cover = ''; } if (!P.name) { P.name = path.split(/[\\/]/).pop().replace(/\.[^.]+$/, ''); $('#pname').value = P.name; }
  await save(true); renderAll(); loadVideo();
}
$('#videoChip').onclick = e => P && (videoMissing ? pickVideo(true) : togglePop('#vPop', e));
$('#vFile').onclick = () => { $('#vPop').classList.remove('on'); pickVideo(); };
$('#vLink').onsubmit = e => { e.preventDefault(); openLink($('#vUrl').value, $('#videoChip'), true); };
async function openLink(url, btn, here) {                         // запис Twitch: на диск нічого не качаємо — лише потрібні шматки, коли знадобляться
  const id = (url.match(/twitch\.tv\/(?:\w+\/)?videos?\/(\d+)/) || [])[1];
  if (!id) return msg('Потрібне посилання на запис етеру: twitch.tv/videos/…', 1);
  $('#vPop').classList.remove('on'); url = 'https://www.twitch.tv/videos/' + id;
  try {
    const v = await busy(btn, 'Twitch', [['twitch', 10]], task => api('/api/vod', {url, task})); $('#vUrl').value = '';
    if (!here) return projectFor(url, v.title, v.thumb);
    P.video = url; P.region = null; P.clips = []; P.cues = []; P.cover = v.thumb || ''; if (!P.name) { P.name = v.title; $('#pname').value = P.name; }   // старий проєкт без відео
    await save(true); renderAll(); loadVideo();
  } catch (e) { msg(e.message, 1); }
}
let hlsPlayer = null;
const hlsStop = () => { hlsPlayer?.destroy(); hlsPlayer = null; };
async function playHls(url) {                                     // плейлист через наш сервер; шматки вантажаться лише біля курсора
  if (!window.Hls) await new Promise((ok, no) => document.head.append(Object.assign(document.createElement('script'), {src: '/hls.js', onload: ok, onerror: () => no(new Error('Плеєр для Twitch не завантажився'))})));
  const net = {maxTimeToFirstByteMs: 20000, maxLoadTimeMs: 90000, timeoutRetry: {maxNumRetry: 4, retryDelayMs: 500, maxRetryDelayMs: 4000}, errorRetry: {maxNumRetry: 6, retryDelayMs: 1000, maxRetryDelayMs: 8000}};
  hlsStop(); hlsPlayer = new Hls({progressive: true, maxBufferLength: 20, maxMaxBufferLength: 40, backBufferLength: 30, fragLoadPolicy: {default: net}});   // progressive — кадр уже з перших байтів шматка
  hlsPlayer.on(Hls.Events.ERROR, (_, d) => {                       // Twitch буває повільний: мережевий збій — тягнемо далі, а не зупиняємось
    if (!d.fatal) return;
    if (d.type === Hls.ErrorTypes.NETWORK_ERROR) return setTimeout(() => hlsPlayer?.startLoad(vid.currentTime), 1000);
    if (d.type === Hls.ErrorTypes.MEDIA_ERROR) return hlsPlayer.recoverMediaError();
    msg('Запис Twitch: ' + (d.details || 'не грає'), 1);
  });
  hlsPlayer.on(Hls.Events.FRAG_LOADED, refreshWave);              // скачаний шматок — ще шматок хвилі
  hlsPlayer.loadSource(url); hlsPlayer.attachMedia(vid);
}
