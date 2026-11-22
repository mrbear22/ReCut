// Рендер і міні-туторіал.
// ── рендер ──
$('#render').onclick = async () => {
  if (!P || !P.clips.some(c => c.on)) return msg('Немає увімкнених кліпів', 1);
  if (subsEls()[0]?.on && !P.cues.length) msg('Субтитрів ще немає', 1);
  const list = structuredClone(P.clips).sort((x, y) => x.a - y.a).map(c => ({...c, cut: c.cut || []}));
  try {
    await save(true);
    const {path} = await api('/api/pick_dir', {id: P.id}); if (!path) return;   // закрили діалог — рендеру немає (і випадковий клік нічого не запускає)
    msg(''); $('#open').style.display = 'none';
    await rendering(plans.render(list.filter(c => c.on)), task => api('/api/render', {id: P.id, clips: list, elements: P.elements, cues: P.cues, music: P.music, out: path, task}));
  } catch (e) { msg(e.message, 1); }
};
let outDir = '';
$('#open').onclick = () => api('/api/reveal', {path: outDir});
async function rendering(plan, start, key) {                      // рядок «Рендер» згори, поки сервер рендерить; потім — підсумок
  const j = await busy($('#render'), 'Рендер', plan, async task => {
    await start(task);
    for (;;) { await new Promise(r => setTimeout(r, 700)); const s = await api('/api/status').catch(() => null); if (s && !s.running) return s; }
  }, key, true);
  outDir = j.out;
  if (j.cancelled) msg(`Рендер скасовано${j.out ? ' · готові кліпи лишились у теці' : ''}`);
  else if (j.err) msg('Помилка рендеру: ' + j.err, 1);
  else msg(`Готово: ${j.n} шт. у ${j.out}`);
  $('#open').style.display = j.out && !j.err ? 'block' : 'none';
}

// ── міні-туторіал: підсвічує місце й пояснює фішку; сам запускається при першому відкритті редактора ──
const key = (k, col = '#383634', ink = '#e2dfda') => `<i style="background:${col};color:${ink}">${k}</i>`;
const TOUR = [
  [null, 'ReCut', '<p>Основні інструменти. Довідка знову — кнопка <b>?</b> угорі.</p>'],
  ['#videoChip', 'Відео', '<p>Запис етеру, з якого робимо шорти: файл на диску або посилання на запис Twitch.</p>'],
  ['#rbar', 'Область аналізу', '<p><b>Знайти моменти</b> шукає кліпи в області, <b>Згенерувати субтитри</b> розпізнає мовлення. Область тягнеться за плашку й краї.</p>'],
  ['#keysBtn', 'Клавіші', `<p>Усі клавіші — тут або ${key('?')}.</p>`],
  ['#tl', 'Таймлайн', `<p>Кліп і його краї тягнуться мишею, ${key('Ctrl')} вимикає прилипання. Покладене зверху підрізає те, що під ним. Смужки в кліпі показують, коли видно кожен елемент: права кнопка розріже смужку чи сховає елемент лише в цьому кліпі.</p>`],
  ['#addEl', 'Елементи', '<p>Плашка, чат, вебкамера, музика, субтитри тощо. Новий елемент з’являється в поточному кліпі. Щоб додати його в інший кліп, перетягни елемент зі списку на кліп на таймлайні. Налаштування в цій панелі — для всіх кліпів. Зняти <b>Глобальний</b> у меню правої кнопки — і в цьому кліпі елемент матиме свої налаштування: рядком під елементом.</p>'],
  ['#pv', 'Прев\'ю', `<p>Елементи тягнуться мишею, кут змінює розмір. ${key('Ctrl')} вимикає прилипання.</p><div class="combo">
    <span>${key('Ctrl')} + ${key('C')} / ${key('V')} / ${key('D')}</span><span>копіювати, вставити, дублювати</span>
    <span>${key('Del')}</span><span>видалити вибране</span>
    <span>${key('Ctrl')} + ${key('Z')}</span><span>скасувати</span></div>`],
  ['#render', 'Рендер', '<p>Спершу обираєш теку, куди зберегти шорти.</p>'],
];
let tourI = -1;
function tour(i) {
  tourI = i; const st = TOUR[i], box = $('#tour');
  if (!st) { box.classList.remove('on'); try { localStorage.setItem('tour', '1'); } catch (e) {} return; }
  if (!$('#editor').classList.contains('on')) show('editor');
  const [sel_, title, body] = st, tip = $('#tourTip'), hole = $('#tourHole'), pad = 6;
  box.classList.add('on'); tip.querySelector('.tt-step').textContent = `${i + 1} з ${TOUR.length}`; $('#tourTitle').textContent = title;
  tip.querySelector('.tt-body').innerHTML = body; $('#tourBack').style.visibility = i ? 'visible' : 'hidden'; $('#tourNext').textContent = i === TOUR.length - 1 ? 'Почати' : 'Далі';
  const r = sel_ && $(sel_).getBoundingClientRect(), W = innerWidth, H = innerHeight;
  Object.assign(hole.style, r ? {left: r.left - pad + 'px', top: r.top - pad + 'px', width: r.width + 2 * pad + 'px', height: r.height + 2 * pad + 'px'}
                              : {left: W / 2 + 'px', top: H / 2 + 'px', width: 0, height: 0});
  const tw = tip.offsetWidth, th = tip.offsetHeight;             // вікно — під ціллю, над нею або збоку, де влазить
  let x = r ? r.left + r.width / 2 - tw / 2 : W / 2 - tw / 2, y = r ? r.bottom + 16 : H / 2 - th / 2;
  if (r && y + th > H - 12) y = r.top - th - 16;
  if (r && y < 12) { y = clamp(r.top + r.height / 2 - th / 2, 12, H - th - 12); x = r.right + 16 + tw < W ? r.right + 16 : r.left - tw - 16; }
  Object.assign(tip.style, {left: clamp(x, 12, W - tw - 12) + 'px', top: clamp(y, 12, H - th - 12) + 'px'});
  $('#tourNext').focus();
}
$('#tourNext').onclick = () => tour(tourI + 1); $('#tourBack').onclick = () => tour(tourI - 1); $('#tourSkip').onclick = () => tour(TOUR.length);
$('#help').onclick = () => tour(0);
addEventListener('resize', () => { if (tourI >= 0 && tourI < TOUR.length && $('#tour').classList.contains('on')) tour(tourI); });
addEventListener('keydown', e => {
  if (!$('#tour').classList.contains('on')) return;
  if (e.key === 'Escape') tour(TOUR.length); else if (e.key === 'ArrowRight') tour(tourI + 1); else if (e.key === 'ArrowLeft' && tourI) tour(tourI - 1); else return;
  e.preventDefault(); e.stopImmediatePropagation();
}, true);
const tourSeen = () => { try { return !!localStorage.getItem('tour'); } catch (e) { return true; } };

const KEYS = [
  ['Відтворення', [['Space', 'грати / пауза'], ['Shift+Space', 'програти вибраний кліп чи репліку'], ['← →', 'на 1 с'], ['Shift+← →', 'на 5 с'], ['Клік по шкалі часу', 'перемотати']]],
  ['Розрізати й обрізати', [['B', 'розрізати вибране під курсором'], ['Q', 'початок вибраного — на курсор'], ['W', 'кінець вибраного — на курсор'],
    ['I', 'початок області аналізу'], ['O', 'кінець області аналізу'], ['Alt+перетягування', 'вирізати шматок кліпу']]],
  ['Створити', [['N', 'новий кліп'], ['M', 'музика в кліп'], ['Shift+перетягування', 'новий кліп; у рядку реплік — репліка'], ['Ctrl+перетягування', 'нова область аналізу'],
    ['Рядок зі списку на кліп', 'додати елемент у кліп']]],
  ['Вибране', [['Перетягування по порожньому місцю таймлайна', 'лассо: кілька кліпів і реплік — ПКМ по них дає дії з усіма разом'], ['Del', 'прибрати з кліпу (той, що в усіх кліпах, — сховати тут)'], ['Ctrl+Del', 'видалити елемент повністю'], ['Ctrl+C / Ctrl+V', 'копіювати / вставити'], ['Ctrl+D', 'дублювати'],
    ['H', 'сховати / показати елемент'], ['G', 'глобальний у цьому кліпі чи репліці / свої налаштування'], ['] / [', 'шар вище / нижче'], ['Shift+] / Shift+[', 'на передній / задній план'], ['Esc', 'зняти вибір']]],
  ['Кліпи й репліки', [['Правий Alt+клік по кліпу', 'петля: шорт почнеться звідси, а початок кліпу піде в кінець'], ['Правий Alt+перетягування', 'хук: цей шматок повториться на самому початку шорту'], ['Ctrl+B / Ctrl+I / Ctrl+U', 'форматування виділених слів репліки'], ['R', 'рендерити кліп чи ні'], ['Z', 'наблизити кліп'], ['J', 'об\'єднати репліку з наступною'], ['Enter', 'редагувати текст репліки']]],
  ['Перетягування', [['Ctrl', 'без прилипання'], ['Shift', 'зберегти пропорції в прев\'ю'], ['Колесо', 'масштаб таймлайна чи прев\'ю'], ['Затиснуте колесо', 'рухати прев\'ю'], ['Права кнопка', 'усі дії з тим, що під курсором']]],
  ['Загальне', [['Ctrl+Z', 'скасувати'], ['Ctrl+Y / Ctrl+Shift+Z', 'повторити'], ['?', 'це вікно']]],
];
const kbd = k => k.split(' / ').map(alt => alt.split('+').map(x => /^(Space|Shift|Ctrl|Alt|Del|Esc|Enter|\S{1,2}|← →)$/.test(x) ? `<kbd>${esc(x)}</kbd>` : esc(x)).join('+')).join(' / ');
$('#keysBody').innerHTML = KEYS.map(([g, list]) => `<section><h4>${g}</h4><dl>${list.map(([k, d]) => `<dt>${kbd(k)}</dt><dd>${d}</dd>`).join('')}</dl></section>`).join('');
const toggleKeys = on => $('#keys').classList.toggle('on', on ?? !$('#keys').classList.contains('on'));
$('#keysBtn').onclick = () => toggleKeys(true);
$('#keysClose').onclick = () => toggleKeys(false);
$('#keys').onclick = e => { if (e.target.id === 'keys') toggleKeys(false); };
addEventListener('keydown', e => {
  const on = $('#keys').classList.contains('on');
  if (on && e.key === 'Escape') { toggleKeys(false); e.preventDefault(); e.stopImmediatePropagation(); return; }
  if (e.key === '?' && !e.target.matches?.('input,textarea,select,[contenteditable]')) { toggleKeys(); e.preventDefault(); e.stopImmediatePropagation(); }
}, true);

function renderAll() { renderEls(); renderList(); renderCanvasBar(); fitCanvas(); videoChip(); $('#cueEdit').classList.remove('on'); }

(async () => {
  const page = Math.random().toString(36).slice(2), ping = () => api('/api/ping', {page}).catch(() => {});   // програма живе, поки відкрите хоч одне вікно
  ping(); setInterval(ping, 20000);
  const checkUpdate = async () => {                                // нова версія на GitHub — кнопка в шапці
    const u = await api('/api/update').catch(() => ({}));
    $('#upd').hidden = !u.version; if (u.version) $('#upd').textContent = `Оновити до ${u.version}`;
  };
  setTimeout(checkUpdate, 4000);
  document.addEventListener('click', e => { const b = e.target.closest('[data-link]'); if (b) api('/api/open', {link: b.dataset.link}); });   // у звичайному браузері, не у вікні програми
  (async function ffmpegRow() {                                    // перший запуск: ffmpeg завантажується у фоні — показуємо поступ
    const s = await api('/api/status').catch(() => ({}));
    if (s.ffmpeg !== false) return;
    busy(document.createElement('button'), 'ffmpeg', [['ffmpeg', 60]], task => new Promise(done => {
      const iv = setInterval(async () => { const t = await api('/api/status').catch(() => ({})); if (t.ffmpeg) { clearInterval(iv); done(); } }, 1000);
    }), 'ffmpeg');
  })();
  $('#upd').onclick = async () => {
    try {
      const r = await busy($('#upd'), 'Оновлення', [['update', 15]], task => api('/api/update/apply', {task}));
      if (r.kind === 'full') return msg('Встановлюю оновлення. Програма відкриється сама.');
      msg('Перезапускаю…');
      const was = (await api('/api/version').catch(() => ({}))).boot;
      for (let i = 0; i < 60; i++) {                               // піднявся новий процес — перезавантажуємо сторінку
        await new Promise(r => setTimeout(r, 500));
        const v = (await api('/api/version').catch(() => ({}))).boot;
        if (v && v !== was) { window.reloading = true; return location.reload(); }   // це не закриття вікна
      }
      msg('Не вдалося перезапустити. Закрий і відкрий програму.', 1);
    } catch (e) { msg('Оновлення: ' + e.message, 1); }
  };
  addEventListener('pagehide', () => window.reloading || navigator.sendBeacon('/api/bye', JSON.stringify({page})));   // закрили вікно — програма зупиняється одразу
  addEventListener('keydown', e => { if (e.key === 'F5' || ((e.ctrlKey || e.metaKey) && e.code === 'KeyR')) e.preventDefault(); }, true);   // перезавантаження сторінки = закриття вікна, тож його вимкнено
  Promise.all([api('/api/twitch'), api('/api/brands')]).then(([st, br]) => { pub.brands ||= br; twHead(st); }).catch(() => {});
  let s = null;
  try {
    for (let i = 0; !s; i++) s = await api('/api/state').catch(e => { if (i >= 20) throw e; return new Promise(r => setTimeout(r, 300)).then(() => null); });   // сервер ще піднімається — ще раз
    cfg = s.cfg; renderPops(); setMode('short'); scaleUI();
    api('/api/fonts').then(f => $('#fontlist').innerHTML = f.map(n => `<option value="${esc(n)}">`).join(''));
    const p = cfg.project && await api('/api/project?id=' + cfg.project).catch(() => null);
    if (p) await openProject(p).catch(e => { reportError('open last project: ' + (e.stack || e)); });
  } catch (e) { reportError('startup: ' + (e.stack || e)); }
  finally { show('home'); fitTL(); }                              // екран — завжди, навіть якщо щось вище не вдалося
  if (s?.job.running) rendering([['render', 60]], async () => {}, s.job.task).catch(() => {});   // вікно відкрили під час рендеру
})();
