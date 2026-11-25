// Бібліотека: анімовані емодзі Noto (CC BY 4.0) і звуки (CC0). Що обрали — стає звичайним елементом: стікер — «Зображення», звук — «Музика»,
// плиткою в кліпі під курсором. Файли качає сервер при першому використанні.
const EMOJI_SVG = c => `https://fonts.gstatic.com/s/e/notoemoji/latest/${c}/emoji.svg`;
const EMOJI_GROUPS = {'Smileys and emotions': 'Смайлики й емоції', 'People': 'Люди', 'Animals and nature': 'Тварини й природа', 'Food and drink': 'Їжа й напої',
  'Travel and places': 'Подорожі', 'Activities and events': 'Події', 'Objects': 'Предмети', 'Symbols': 'Символи', 'Flags': 'Прапори'};
let libTab = 'emoji', libEmoji = null, libPacks = null, libOpen = null, libAudio = null;
function openLib(tab = libTab) {
  if (!P) return msg('Спершу відкрий або створи проєкт', 1);
  libTab = tab; $('#lib').classList.add('on'); $('#libQ').value = ''; renderLib(); $('#libQ').focus();
}
function closeLib() { libAudio?.pause(); $('#lib').classList.remove('on'); }
async function renderLib() {
  $$('#libTabs button').forEach(b => b.classList.toggle('on', b.dataset.t === libTab));
  $('#libQ').hidden = libTab !== 'emoji'; const body = $('#libBody');
  if (libTab === 'emoji') {
    if (!libEmoji) { body.innerHTML = '<p class="mut">Завантажую список…</p>'; libEmoji = await api('/api/lib/emoji').catch(e => (body.innerHTML = `<p class="err">${esc(e.message)}</p>`, null)); if (!libEmoji) return; }
    const q = $('#libQ').value.trim().toLowerCase(), hit = libEmoji.filter(x => !q || x.t.includes(q)), groups = [...new Set(hit.map(x => x.g))];
    body.innerHTML = groups.map(g => `<h4>${esc(EMOJI_GROUPS[g] || g)}</h4><div class="lgrid">${hit.filter(x => x.g === g).map(x =>
      `<button data-emoji="${x.c}" title="${esc(x.t)}"><img src="${EMOJI_SVG(x.c)}" alt="${esc(x.t)}" loading="lazy"></button>`).join('')}</div>`).join('') || '<p class="mut">Нічого не знайдено</p>';
    return;
  }
  if (!libPacks) libPacks = await api('/api/lib/sounds').catch(() => []);
  body.innerHTML = libPacks.map(p => `<div class="lpack ${libOpen?.id === p.id ? 'open' : ''}"><button class="lph" data-pack="${p.id}"><b>${esc(p.name)}</b><small>${esc(p.by)}</small><i>${libOpen?.id === p.id ? '▾' : '▸'}</i></button>
    ${libOpen?.id === p.id ? (libOpen.list ? libOpen.list.map((s, i) => `<div class="lsnd"><button class="ghost" data-play="${i}" aria-label="Прослухати">▶</button><span>${esc(s.name)}</span><button data-add="${i}">Додати в кліп</button></div>`).join('')
      : '<p class="mut">Завантажую звуки…</p>') : ''}</div>`).join('');
}
async function openPack(id) {
  if (libOpen?.id === id) { libOpen = null; return renderLib(); }
  libOpen = {id}; renderLib();
  try { const list = await api('/api/lib/sounds', {id}); if (libOpen?.id === id) libOpen.list = list; }
  catch (e) { libOpen = null; msg('Звуки: ' + e.message, 1); }
  renderLib();
}
function tileHere(len) {                                          // кліп і момент для нової плитки: під курсором, інакше початок вибраного кліпу
  const t = vid.currentTime, c = clipAt(t) || (P.clips.length ? ctxClip() : null); if (!c) return null;
  const n = net(c), rel = clipAt(t) === c ? clamp(toOut(c, t), 0, Math.max(0, n - .3)) : 0;
  return {c, rel, seg: [rel, rel + len < n - .05 ? rel + len : 0]};
}
async function addSticker(code) {
  try {
    const {path} = await api('/api/lib/emoji', {code}), w = 300, h = tileHere(2.5);
    const el = {...mk({type: 'image', path, w, y: Math.round(CH() * .38), anim: 'pop'}), x: Math.round((CW() - w) / 2)};
    if (h) { el.solo = true; (h.c.segs ||= {})[el.id] = [h.seg]; }
    P.elements.push(el); selEl = el.id; selOwn = null; focus = 'el'; closeLib(); renderEls(); save(true);
  } catch (e) { msg('Емодзі: ' + e.message, 1); }
}
async function addSound(s) {
  const {dur: d} = await api('/api/audio?p=' + encodeURIComponent(s.path)).catch(() => ({dur: 0}));
  if (!d) return msg('Не вдалося прочитати звук', 1);
  const h = tileHere(d); if (!h) return msg('Спершу зроби кліп: звук лягає плиткою в кліп', 1);
  const el = {...mk({type: 'music', vol: 1, fin: 0, fout: 0}), path: s.path, name: s.name, dur: d, off: -h.rel, solo: true};   // звук починається там, де плитка
  P.elements.push(el); (h.c.segs ||= {})[el.id] = [h.seg]; selEl = el.id; selOwn = null; focus = 'el';
  closeLib(); renderEls(); save(true); loadPeaks(el.path); msg(`Звук «${s.name}» — у кліпі #${P.clips.indexOf(h.c) + 1}`);
}
$('#libBody').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.emoji) return addSticker(b.dataset.emoji);
  if (b.dataset.pack) return openPack(b.dataset.pack);
  const s = libOpen?.list?.[+(b.dataset.play ?? b.dataset.add)]; if (!s) return;
  if (b.dataset.add != null) return addSound(s);
  libAudio?.pause(); libAudio = new Audio(fileUrl(s.path)); libAudio.play().catch(() => {});
};
$('#libTabs').onclick = e => { const b = e.target.closest('button[data-t]'); if (b) { libTab = b.dataset.t; renderLib(); } };
$('#libQ').oninput = () => renderLib();
$('#libClose').onclick = closeLib;
$('#lib').onclick = e => { if (e.target.id === 'lib') closeLib(); };
addEventListener('keydown', e => { if (e.key === 'Escape' && $('#lib').classList.contains('on')) { closeLib(); e.stopImmediatePropagation(); } }, true);

// ── анімований GIF у прев'ю: кадри декодує браузер (ImageDecoder), кадр — за часом від появи плитки, як у рендері ──
const gifs = new Map();                                            // шлях → {frames, at: початок кадру с, len} · null — ще декодується або не анімований
function gifOf(path) {
  if (!/\.gif$/i.test(path || '') || !('ImageDecoder' in window)) return null;
  if (gifs.has(path)) return gifs.get(path); gifs.set(path, null);
  (async () => {
    const dec = new ImageDecoder({data: (await fetch(fileUrl(path))).body, type: 'image/gif'}); await dec.completed;
    const n = dec.tracks.selectedTrack.frameCount, frames = [], at = []; let t = 0;
    for (let i = 0; i < n; i++) {
      const {image} = await dec.decode({frameIndex: i}); at.push(t); t += (image.duration || 1e5) / 1e6;
      frames.push(await createImageBitmap(image, {resizeWidth: 256, resizeQuality: 'medium'})); image.close();
    }
    dec.close(); if (n > 1) gifs.set(path, {frames, at, len: t});
  })().catch(() => {});
  return null;
}
function gifFrame(g, el) {                                        // кадр, що зараз: час від початку першої плитки в кліпі, по колу
  const c = clipAt(vid.currentTime), s = c ? toOut(c, vid.currentTime) - (segsOf(c, el)[0]?.[0] || 0) : 0, t = ((s % g.len) + g.len) % g.len;
  return g.frames[Math.max(0, g.at.findLastIndex(v => v <= t))];
}
