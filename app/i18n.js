// Мови інтерфейсу ReCut. Рушій: українська — основна мова (тексти прямо в коді); інша мова — словником з lang/<мова>.js поверх сторінки.
// Сервер віддає цей файл разом зі словниками (LANGS) і мовою з налаштувань (SAVED_LANG); уперше — мова Windows.
const LANG = (typeof SAVED_LANG === 'string' && SAVED_LANG) || (/^(uk|ru|be)/i.test(navigator.language) ? 'uk' : 'en');
const LOCALE = LANG === 'en' ? 'en-US' : 'uk-UA';
const CYR = /[А-Яа-яІіЇїЄєҐґ]/;
const tr = (() => {
  if (LANG !== 'en') return s => s;
  const norm = s => String(s).replace(/\s+/g, ' ').trim(), exact = new Map(), pats = [], cache = new Map();
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  for (const [k, v] of Object.entries(LANGS[LANG] || {})) {
    const nk = norm(k);
    if (!nk.includes('{}')) { exact.set(nk, v); continue; }
    const parts = nk.split('{}'), vparts = v.split('{}');
    pats.push([new RegExp('^' + parts.map(esc).join('(.+?)') + '$', 's'), v, nk.replace(/\{\}/g, '').length]);
    if (parts.length === vparts.length)                              // вставка буває тегом (<kbd>, <b>) — тоді на сторінці окремі шматки тексту
      parts.forEach((p, i) => { const a = norm(p); if (CYR.test(a) && !exact.has(a)) exact.set(a, vparts[i].trim()); });
  }
  pats.sort((a, b) => b[2] - a[2]);                                  // довший сталий текст — точніший шаблон
  const tr = s => {
    if (typeof s !== 'string' || !CYR.test(s)) return s;
    const n = norm(s); if (cache.has(n)) return cache.get(n) ?? s;
    let r = exact.get(n);
    if (r == null) for (const [re, v] of pats) { const m = n.match(re); if (m) { let i = 1; r = v.replace(/\{\}/g, () => tr(m[i++])); break; } }
    if (r == null && n[0] !== n[0].toUpperCase()) { const u = exact.get(n[0].toUpperCase() + n.slice(1)); if (u) r = u[0].toLowerCase() + u.slice(1); }
    if (cache.size > 5000) cache.clear();
    cache.set(n, r); return r ?? s;
  };
  return tr;
})();
const plural = (n, one, few, many) => {                             // 1 шорт, 2 шорти, 5 шортів, 21 шорт · 1 short, 2 shorts
  if (LANG === 'en') return `${n} ${tr(n === 1 ? one : many)}`;
  const d = n % 10, h = n % 100;
  return `${n} ${d === 1 && h !== 11 ? one : d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many}`;
};
if (typeof SAVED_LANG === 'string' && !SAVED_LANG) fetch('/api/config', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lang: LANG})}).catch(() => {});   // уперше: запам'ятати мову Windows
function setLang(l) {                                                // мова інтерфейсу: запам'ятати й перезавантажити сторінку
  window.reloading = true;                                           // перезавантаження — не закриття вікна: програма не виходить
  fetch('/api/config', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lang: l})}).catch(() => {}).finally(() => location.reload());
}
if (LANG === 'en') {
  document.documentElement.lang = 'en';
  const ATTR = ['title', 'placeholder', 'aria-label'], SKIP = 'textarea,script,style,[contenteditable],.noi18n';
  const text = t => {
    const v = t.nodeValue; if (!CYR.test(v) || t.parentElement?.closest(SKIP)) return;
    const r = tr(v); if (r !== v) t.nodeValue = v.match(/^\s*/)[0] + r + v.match(/\s*$/)[0];
  };
  const attr = (e, a) => { const v = e.getAttribute(a); if (v && CYR.test(v) && !e.closest('.noi18n')) { const r = tr(v); if (r !== v) e.setAttribute(a, r); } };   // підказки — і на полях, де пишуть самі
  const walk = n => {
    if (n.nodeType === 3) return text(n);
    if (n.nodeType !== 1) return;
    for (const a of ATTR) attr(n, a);
    const w = document.createTreeWalker(n, 5);                        // елементи й текст
    for (let x = w.nextNode(); x; x = w.nextNode()) x.nodeType === 3 ? text(x) : ATTR.forEach(a => attr(x, a));
  };
  new MutationObserver(ms => {
    for (const m of ms) {
      if (m.type === 'childList') m.addedNodes.forEach(walk);
      else if (m.type === 'characterData') text(m.target);
      else attr(m.target, m.attributeName);
    }
  }).observe(document.documentElement, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTR});
  for (const f of ['alert', 'confirm', 'prompt']) { const o = window[f].bind(window); window[f] = (m, ...a) => o(tr(m), ...a); }
}
