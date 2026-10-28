(() => {
  const $ = (selector) => document.querySelector(selector);
  const grid = $('#story-grid');
  const empty = $('#empty-state');
  const articleView = $('#article-view');
  const featured = $('#featured-story');
  $('#year').textContent = new Date().getFullYear();

  const escapeHTML = (value = '') => String(value).replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const slugify = (value = '') => String(value).toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const formatDate = (value) => {
    if (!value) return 'ANALYSIS';
    const date = new Date(`${value}T12:00:00`);
    return Number.isNaN(date.getTime()) ? escapeHTML(value) : date.toLocaleDateString('en-GB', {day:'numeric',month:'short',year:'numeric'}).toUpperCase();
  };
  const postURL = (post) => `#story/${encodeURIComponent(post.id || slugify(post.title))}`;
  function card(post, index) {
    const el = document.createElement('article');
    el.className = `story-card${index === 0 ? ' featured' : ''}`;
    el.innerHTML = `<div class="story-card-top"><span class="category">${escapeHTML(post.category || 'RACE ANALYSIS')}</span><span>${formatDate(post.date)}</span></div><div class="story-card-body"><h3>${escapeHTML(post.title || 'Untitled analysis')}</h3><p>${escapeHTML(post.excerpt || 'Evidence-led Formula 1 analysis from available data.')}</p><a class="read-link" href="${postURL(post)}">Read the analysis <span>↗</span></a></div>`;
    return el;
  }
  function showPost(post) {
    if (!post) return;
    grid.hidden = true; empty.hidden = true; featured.hidden = true; articleView.hidden = false;
    const paragraphs = Array.isArray(post.body) ? post.body : [];
    const evidence = Array.isArray(post.evidence) ? post.evidence : [];
    const bodyHTML = paragraphs.map((line) => {
      if (line.startsWith('WHAT THE DATA SHOWS')) return '<h3>What the data shows</h3>';
      if (line.startsWith('WHAT IT DOESN’T PROVE') || line.startsWith("WHAT IT DOESN'T PROVE")) return '<h3>What it does not prove</h3>';
      if (line.startsWith('• ')) return `<p>• ${escapeHTML(line.slice(2))}</p>`;
      return line.trim() ? `<p>${escapeHTML(line)}</p>` : '';
    }).join('');
    const evidenceHTML = evidence.length ? `<h3>Evidence</h3><ul>${evidence.map(item => `<li>${escapeHTML(item)}</li>`).join('')}</ul>` : '';
    articleView.innerHTML = `<a class="article-back" href="#latest">← BACK TO ALL ANALYSIS</a><div class="article-meta">${escapeHTML(post.category || 'RACE ANALYSIS')} &nbsp; / &nbsp; ${formatDate(post.date)}</div><h2>${escapeHTML(post.title || '')}</h2><p class="article-lede">${escapeHTML(post.excerpt || '')}</p><div class="article-content">${bodyHTML}${evidenceHTML}</div>${post.caveat ? `<div class="article-caveat"><strong>Context & limitations</strong><br>${escapeHTML(post.caveat)}</div>` : ''}<p class="muted" style="font-size:11px;margin-top:28px">Independent educational analysis using public data. Review source context and limitations before drawing conclusions.</p>`;
    articleView.scrollIntoView({behavior:'smooth',block:'start'});
  }
  function render(posts) {
    if (!Array.isArray(posts) || posts.length === 0) return;
    const sorted = [...posts].sort((a,b) => String(b.date || '').localeCompare(String(a.date || '')));
    empty.hidden = true;
    sorted.forEach((post,index) => grid.appendChild(card(post,index)));
    grid.hidden = false;
    window.addEventListener('hashchange', () => route(sorted));
    route(sorted);
  }
  function route(posts) {
    const match = decodeURIComponent(location.hash).match(/^#story\/(.+)$/);
    if (!match) { articleView.hidden = true; grid.hidden = false; empty.hidden = posts.length > 0; featured.hidden = true; return; }
    const post = posts.find(item => String(item.id || slugify(item.title)) === match[1]);
    if (post) showPost(post);
  }
  fetch('posts.json', {cache:'no-store'})
    .then(response => { if (!response.ok) throw new Error('No published posts'); return response.json(); })
    .then(render)
    .catch(() => { /* Empty newsroom is an intentional first-run state. */ });
})();
