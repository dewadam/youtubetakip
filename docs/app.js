const state = { data:null, sortKey:"views", sortAsc:false,
  filterChannel:"all", period:0, search:"" };

const fmt = (n) => {
  n = Number(n) || 0;
  if (n >= 1e9) return (n/1e9).toFixed(2)+"B";
  if (n >= 1e6) return (n/1e6).toFixed(2)+"M";
  if (n >= 1e3) return (n/1e3).toFixed(1)+"K";
  return n.toString();
};

function timeAgo(iso) {
  const s = (Date.now() - new Date(iso).getTime())/1000;
  if (s < 60) return "az önce";
  if (s < 3600) return Math.floor(s/60)+" dk önce";
  if (s < 86400) return Math.floor(s/3600)+" saat önce";
  if (s < 2592000) return Math.floor(s/86400)+" gün önce";
  return new Date(iso).toLocaleDateString("tr-TR");
}

function timeAgoShort(iso) {
  const s = (Date.now() - new Date(iso).getTime())/1000;
  if (s < 60) return "şimdi";
  if (s < 3600) return Math.floor(s/60)+"dk";
  if (s < 86400) return Math.floor(s/3600)+"s";
  return Math.floor(s/86400)+"g";
}

function delta(history, key, hours) {
  if (!history || history.length < 2) return null;
  const now = history[history.length-1][key];
  const target = Date.now() - hours*3600*1000;
  let ref = null;
  for (let i = history.length-2; i >= 0; i--) {
    if (new Date(history[i].ts).getTime() <= target) { ref = history[i]; break; }
  }
  if (!ref) return null;
  return now - ref[key];
}

function fmtDelta(v) {
  if (v === null || v === undefined) return "";
  const cls = v > 0 ? "up" : v < 0 ? "down" : "";
  const sign = v > 0 ? "+" : "";
  return `<span class="v ${cls}">${sign}${fmt(v)}</span>`;
}

function sparkline(values) {
  if (!values || values.length < 2) return "";
  const w = 300, h = 44, pad = 4;
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const stepX = (w - pad*2)/(values.length-1);
  const pts = values.map((v,i) => {
    const x = pad + i*stepX;
    const y = h - pad - ((v-min)/range)*(h-pad*2);
    return [x,y];
  });
  const line = pts.map((p,i) => (i?"L":"M")+p[0].toFixed(1)+","+p[1].toFixed(1)).join(" ");
  const area = line + ` L${w-pad},${h} L${pad},${h} Z`;
  const id = "g"+Math.random().toString(36).slice(2,7);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ff3b3b" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#ff3b3b" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${area}" fill="url(#${id})"/>
    <path d="${line}" fill="none" stroke="#ff3b3b" stroke-width="1.8"
      stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

function escapeHtml(s) {
  return String(s||"").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

async function load() {
  try {
    const res = await fetch("data/stats.json?t="+Date.now(), {cache:"no-store"});
    if (!res.ok) throw new Error("stats.json okunamadı ("+res.status+")");
    state.data = await res.json();
    renderAll();
  } catch (e) {
    document.getElementById("lastUpdated").textContent = "Hata: "+e.message;
  }
}

function renderSummary() {
  const { channels={}, videos=[], lastUpdated } = state.data || {};
  const chanList = Object.values(channels);
  const totalSubs = chanList.reduce((s,c) => s + (c.lastSnapshot?.subs||0), 0);
  const totalViews = chanList.reduce((s,c) => s + (c.lastSnapshot?.views||0), 0);
  const sum24 = (key) => chanList.reduce((acc,c) => acc + (delta(c.history,key,24)||0), 0);
  const dSubs = sum24("subs"), dViews = sum24("views");

  document.getElementById("summary").innerHTML = `
    <div class="summary-card"><div class="label">Takip Edilen Kanal</div>
      <div class="value">${chanList.length}</div>
      <div class="sub">${videos.length} video izleniyor</div></div>
    <div class="summary-card"><div class="label">Toplam Abone</div>
      <div class="value">${fmt(totalSubs)}</div>
      <div class="sub">${dSubs ? "24s: "+(dSubs>0?"+":"")+fmt(dSubs) : "—"}</div></div>
    <div class="summary-card"><div class="label">Toplam İzlenme</div>
      <div class="value">${fmt(totalViews)}</div>
      <div class="sub">${dViews ? "24s: "+(dViews>0?"+":"")+fmt(dViews) : "—"}</div></div>
    <div class="summary-card"><div class="label">Son Güncelleme</div>
      <div class="value" style="font-size:16px;">${lastUpdated ? timeAgo(lastUpdated) : "—"}</div>
      <div class="sub">${lastUpdated ? new Date(lastUpdated).toLocaleString("tr-TR") : ""}</div></div>`;

  document.getElementById("lastUpdated").textContent =
    lastUpdated ? "Son güncelleme: "+new Date(lastUpdated).toLocaleString("tr-TR") : "";
}

function renderChannels() {
  const grid = document.getElementById("channelsGrid");
  const channels = Object.values(state.data?.channels || {});
  if (!channels.length) {
    grid.innerHTML = `<p class="empty">Henüz kanal yok. channels.json'a ekle.</p>`;
    return;
  }
  grid.innerHTML = channels.map(c => {
    const s = c.lastSnapshot || {};
    const hist = c.history || [];
    const subSeries = hist.map(h => h.subs);
    return `<div class="channel-card">
      <div class="channel-head">
        <img src="${c.thumbnail}" alt="">
        <div><div class="name">${escapeHtml(c.title)}</div>
        <a href="https://youtube.com/channel/${c.id}" target="_blank" rel="noopener">Kanala git ↗</a></div>
      </div>
      <div class="stats-row">
        <div class="stat"><div class="label">Abone</div><div class="value">${fmt(s.subs)}</div></div>
        <div class="stat"><div class="label">İzlenme</div><div class="value">${fmt(s.views)}</div></div>
        <div class="stat"><div class="label">Video</div><div class="value">${fmt(s.videos)}</div></div>
      </div>
      ${sparkline(subSeries)}
      <div class="deltas">
        <div class="delta"><span class="k">24s abone</span>${fmtDelta(delta(hist,"subs",24))}</div>
        <div class="delta"><span class="k">7g abone</span>${fmtDelta(delta(hist,"subs",168))}</div>
        <div class="delta"><span class="k">24s izlenme</span>${fmtDelta(delta(hist,"views",24))}</div>
      </div></div>`;
  }).join("");
}

function filteredVideos() {
  let vids = state.data?.videos || [];
  if (state.filterChannel !== "all")
    vids = vids.filter(v => v.channelId === state.filterChannel);
  if (state.period > 0) {
    const cutoff = Date.now() - state.period*3600*1000;
    vids = vids.filter(v => new Date(v.published).getTime() >= cutoff);
  }
  if (state.search) {
    const q = state.search.toLowerCase();
    vids = vids.filter(v => v.title.toLowerCase().includes(q) ||
      v.channelTitle.toLowerCase().includes(q));
  }
  return vids;
}

function sortVideos(vids) {
  const k = state.sortKey, dir = state.sortAsc ? 1 : -1;
  return [...vids].sort((a,b) => {
    let av, bv;
    if (k === "velocity") {
      const hrsA = (Date.now() - new Date(a.published))/3.6e6 || 1;
      const hrsB = (Date.now() - new Date(b.published))/3.6e6 || 1;
      av = a.views/hrsA; bv = b.views/hrsB;
    } else if (k === "engagement") {
      av = a.views ? a.likes/a.views : 0;
      bv = b.views ? b.likes/b.views : 0;
    } else if (k === "published") { av = new Date(a.published); bv = new Date(b.published); }
    else { av = a[k]; bv = b[k]; }
    if (typeof av === "string") av = av.toLowerCase();
    if (typeof bv === "string") bv = bv.toLowerCase();
    if (av < bv) return -1*dir;
    if (av > bv) return 1*dir;
    return 0;
  });
}

function renderVideos() {
  const vids = sortVideos(filteredVideos());
  const body = document.getElementById("videoBody");
  document.getElementById("videoCount").textContent = vids.length + " video";
  if (!vids.length) {
    body.innerHTML = `<tr><td colspan="9" class="empty">Eşleşen video yok.</td></tr>`;
    return;
  }
  body.innerHTML = vids.map(v => {
    const hrs = (Date.now() - new Date(v.published))/3.6e6 || 1;
    const velocity = v.views/hrs;
    const engagement = v.views ? (v.likes/v.views*100) : 0;
    return `<tr>
      <td><img class="thumb" src="${v.thumbnail}" loading="lazy" alt=""></td>
      <td><a class="video-title" href="https://youtube.com/watch?v=${v.videoId}"
        target="_blank" rel="noopener" title="${escapeHtml(v.title)}">${escapeHtml(v.title)}</a></td>
      <td><span class="channel-tag">${escapeHtml(v.channelTitle)}</span></td>
      <td class="num" title="${new Date(v.published).toLocaleString("tr-TR")}">${timeAgoShort(v.published)}</td>
      <td class="num"><strong>${fmt(v.views)}</strong></td>
      <td class="num">${fmt(Math.round(velocity))}/s</td>
      <td class="num">${fmt(v.likes)}</td>
      <td class="num">${fmt(v.comments)}</td>
      <td class="num">${engagement.toFixed(2)}%</td></tr>`;
  }).join("");
}

function renderChannelFilter() {
  const sel = document.getElementById("channelFilter");
  const channels = Object.values(state.data?.channels || {});
  const current = sel.value;
  sel.innerHTML = `<option value="all">Tüm kanallar</option>` +
    channels.map(c => `<option value="${c.id}">${escapeHtml(c.title)}</option>`).join("");
  sel.value = channels.some(c => c.id === current) ? current : "all";
  state.filterChannel = sel.value;
}

function renderAll() {
  renderSummary(); renderChannelFilter(); renderChannels(); renderVideos();
}

document.querySelectorAll("thead th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (key === "thumbnail") return;
    if (state.sortKey === key) state.sortAsc = !state.sortAsc;
    else { state.sortKey = key; state.sortAsc = false; }
    document.querySelectorAll("thead th").forEach(h => h.classList.remove("sorted","asc"));
    th.classList.add("sorted");
    if (state.sortAsc) th.classList.add("asc");
    renderVideos();
  });
});
document.getElementById("search").addEventListener("input", e => {
  state.search = e.target.value.trim(); renderVideos();
});
document.getElementById("channelFilter").addEventListener("change", e => {
  state.filterChannel = e.target.value; renderVideos();
});
document.getElementById("periodFilter").addEventListener("change", e => {
  state.period = parseInt(e.target.value,10) || 0; renderVideos();
});
document.getElementById("refreshBtn").addEventListener("click", load);

load();
