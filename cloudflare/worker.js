// ReCut: сховище відео для Buffer на Cloudflare R2.
// Програма кладе сюди шорт частинами (multipart: POST ?uploads → PUT ?uploadId&part=N → POST ?uploadId),
// Buffer забирає його за посиланням у момент публікації (GET/HEAD частинами),
// щойно пост вийшов — програма прибирає файл (DELETE). Правило життєвого циклу R2 — лише запобіжник для забутих файлів.
// Прив'язка: R2-бакет з назвою змінної MEDIA (Settings → Bindings).

const UPLOAD_KEY = 'b32da63b13f2f4263d6baf0f3ecb65fa';   // той самий ключ, що в програмі: не пароль, а захист від випадкових завантажень
const MAX_BYTES = 100 * 1024 * 1024;                      // безкоштовний Worker не приймає тіло запиту понад 100 МБ — тому великі файли йдуть частинами
const NAME = /^\/v\/[a-f0-9]{16,40}\.mp4$/;
const TYPE = {httpMetadata: {contentType: 'video/mp4'}};

export default {
  async fetch(req, env) {
    const url = new URL(req.url), path = url.pathname, q = url.searchParams;
    if (!NAME.test(path)) return new Response('Not found', {status: 404});
    const key = path.slice(1), done = () => new Response(url.origin + path, {status: 201});

    if (req.method === 'PUT' || req.method === 'POST' || req.method === 'DELETE') {
      if (req.headers.get('x-upload-key') !== UPLOAD_KEY) return new Response('Forbidden', {status: 403});
      const up = q.get('uploadId') && env.MEDIA.resumeMultipartUpload(key, q.get('uploadId'));
      if (req.method === 'POST' && q.has('uploads')) return Response.json({uploadId: (await env.MEDIA.createMultipartUpload(key, TYPE)).uploadId});
      if (req.method === 'POST' && up) { await up.complete(await req.json()); return done(); }
      if (req.method === 'PUT' && up) return Response.json(await up.uploadPart(+q.get('part'), req.body));
      if (req.method === 'DELETE') { await (up ? up.abort() : env.MEDIA.delete(key)); return new Response(null, {status: 204}); }
      if (req.method === 'PUT') {                            // одним запитом — так викладали старі версії програми
        const size = +req.headers.get('content-length');
        if (!size || size > MAX_BYTES) return new Response('Too large', {status: 413});
        await env.MEDIA.put(key, req.body, TYPE); return done();
      }
      return new Response('Bad request', {status: 400});
    }

    if (req.method === 'HEAD') {
      const obj = await env.MEDIA.head(key);
      if (!obj) return new Response(null, {status: 404});
      return new Response(null, {headers: headersOf(obj, {'content-length': obj.size})});
    }

    if (req.method === 'GET') {                              // Buffer читає частинами (Range) — віддаємо 206
      const obj = await env.MEDIA.get(key, {range: req.headers, onlyIf: req.headers});
      if (!obj) return new Response('Not found', {status: 404});
      if (!('body' in obj)) return new Response(null, {status: 304, headers: headersOf(obj)});
      if (!obj.range || !req.headers.has('range')) return new Response(obj.body, {headers: headersOf(obj, {'content-length': obj.size})});
      const offset = 'suffix' in obj.range ? obj.size - obj.range.suffix : obj.range.offset ?? 0;
      const length = 'suffix' in obj.range ? obj.range.suffix : obj.range.length ?? obj.size - offset;
      return new Response(obj.body, {status: 206, headers: headersOf(obj, {
        'content-length': length, 'content-range': `bytes ${offset}-${offset + length - 1}/${obj.size}`})});
    }
    return new Response('Method not allowed', {status: 405, headers: {allow: 'GET, HEAD, PUT, POST, DELETE'}});
  },
};

function headersOf(obj, extra = {}) {
  const h = new Headers({'content-type': 'video/mp4', 'accept-ranges': 'bytes', etag: obj.httpEtag, 'cache-control': 'public, max-age=86400'});
  for (const [k, v] of Object.entries(extra)) h.set(k, String(v));
  return h;
}
