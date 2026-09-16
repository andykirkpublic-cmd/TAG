// Never cache API responses, login pages or child information.
const CACHE='tag-shell-v1';
const ASSETS=['/static/style.css','/static/app.js','/static/icon.svg','/static/offline.html'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('tag-shell-')&&key!==CACHE).map(key=>caches.delete(key)))));});
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(url.origin!==self.location.origin||event.request.method!=='GET'||url.pathname.startsWith('/api/'))return;
  if(event.request.mode==='navigate'){
    event.respondWith(fetch(event.request).catch(()=>caches.match('/static/offline.html')));
  }else if(ASSETS.includes(url.pathname)){
    event.respondWith(fetch(event.request).catch(()=>caches.match(event.request)));
  }
});
