// State for clarification flow
let pendingSettlement = null;
let pendingNeighborhood = null;
let pendingRooms = null;
let pendingPropertyType = null;

// ── History & Memory ──────────────────────────────────────────
const HISTORY_KEY = 'compass_history';
const MAX_HISTORY = 5;

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
  catch { return []; }
}

function saveHistory(items) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
}

function pushHistory(entry) {
  const items = loadHistory();
  // Remove duplicate of same question
  const filtered = items.filter(h => h.question !== entry.question);
  filtered.unshift(entry);
  saveHistory(filtered.slice(0, MAX_HISTORY));
  renderHistoryList();
}

function getLastSettlement() {
  const items = loadHistory();
  return items.length > 0 ? (items[0].settlement || null) : null;
}

function formatTimeAgo(ts) {
  const diff = (Date.now() - ts) / 1000;
  if (diff < 60) return 'עכשיו';
  if (diff < 3600) return `לפני ${Math.floor(diff/60)} דק'`;
  if (diff < 86400) return `לפני ${Math.floor(diff/3600)} שע'`;
  return `לפני ${Math.floor(diff/86400)} ימים`;
}

function deleteHistoryItem(ts) {
  const items = loadHistory().filter(i => i.ts !== ts);
  localStorage.setItem('nadlan_history', JSON.stringify(items));
  renderHistoryList();
}

function renderHistoryList() {
  const list = document.getElementById('history-list');
  if (!list) return;
  const items = loadHistory();
  if (!items.length) {
    list.innerHTML = '<p class="history-empty">אין היסטוריה עדיין</p>';
    return;
  }
  list.innerHTML = '';
  items.forEach(item => {
    const el = document.createElement('div');
    el.className = 'history-item';

    const dealsText = item.total_deals ? `${item.total_deals} עסקאות` : '';
    const reportLink = item.report_id
      ? `<a class="history-report-link" href="/report/${item.report_id}" target="_blank" onclick="event.stopPropagation()">דוח ↗</a>`
      : '';

    el.innerHTML = `
      <div class="history-item-label">
        <span>${item.label || item.settlement || ''}</span>
        ${reportLink}
      </div>
      <div class="history-item-q">${item.question}</div>
      <div class="history-item-meta">
        ${dealsText ? `<span class="history-item-deals">${dealsText}</span>` : ''}
        <span class="history-item-time">${formatTimeAgo(item.ts)}</span>
      </div>
      <button class="history-delete-btn" aria-label="מחק" title="מחק">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    `;
    el.querySelector('.history-delete-btn').addEventListener('click', e => {
      e.stopPropagation();
      deleteHistoryItem(item.ts);
    });
    el.addEventListener('click', () => {
      closeHistoryPanel();
      const input = document.getElementById('question-input');
      if (input) input.value = item.question;
      sendQuestion(item.question);
    });
    list.appendChild(el);
  });
}

function openHistoryPanel() {
  renderHistoryList();
  const panel = document.getElementById('history-panel');
  const overlay = document.getElementById('history-overlay');
  if (panel) { panel.classList.add('open'); }
  if (overlay) { overlay.style.display = 'block'; }
}

function closeHistoryPanel() {
  const panel = document.getElementById('history-panel');
  const overlay = document.getElementById('history-overlay');
  if (panel) { panel.classList.remove('open'); }
  if (overlay) { overlay.style.display = 'none'; }
}

// ── Compass SVG string for bot avatar and loader ──
const COMPASS_SVG_AVATAR = `<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" width="24" height="24" aria-hidden="true">
  <circle cx="60" cy="60" r="56" fill="none" stroke="rgba(184,150,62,0.3)" stroke-width="2"/>
  <g class="needle-group" style="transform-origin:60px 60px">
    <polygon points="60,16 56,64 64,64" fill="#b8963e"/>
    <polygon points="60,104 56,64 64,64" fill="rgba(184,150,62,0.25)"/>
  </g>
  <circle cx="60" cy="60" r="6" fill="#b8963e" opacity="0.9"/>
  <circle cx="60" cy="60" r="3" fill="#f7f4ef"/>
</svg>`;

function _disableChips(chips) {
  chips.querySelectorAll('.chip').forEach(c => (c.disabled = true));
}

function showClarifyChips(bubble, settlement, extraParams) {
  const input = document.getElementById('question-input');
  const chips = document.createElement('div');
  chips.className = 'clarify-chips';

  const options = [
    { label: `כל ${settlement}`, action: 'all' },
    { label: 'רחוב ספציפי', action: 'street' },
    { label: 'שכונה / רובע', action: 'neighborhood' },
  ];

  options.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.textContent = opt.label;
    btn.addEventListener('click', () => {
      _disableChips(chips);
      btn.classList.add('chip-selected');
      if (opt.action === 'all') {
        if (extraParams && extraParams.rooms) pendingRooms = extraParams.rooms;
        if (extraParams && extraParams.property_type) pendingPropertyType = extraParams.property_type;
        pendingSettlement = null;
        sendQuestion(`כל ${settlement}`, settlement);
      } else {
        input.placeholder = opt.action === 'street' ? 'שם הרחוב...' : 'שם השכונה / הרובע...';
        input.focus();
      }
    });
    chips.appendChild(btn);
  });

  bubble.querySelector('.message').appendChild(chips);
  bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
}

function showYearsChips(bubble, settlement, curYear, neighborhood) {
  const chips = document.createElement('div');
  chips.className = 'clarify-chips';

  const yearOptions = [
    { label: 'שנה אחרונה',   minYear: curYear - 1 },
    { label: '3 שנים',       minYear: curYear - 3 },
    { label: '5 שנים',       minYear: curYear - 5 },
    { label: 'כל הנתונים',   minYear: null },
  ];

  yearOptions.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'chip' + (opt.minYear === null ? ' chip-secondary' : '');
    btn.textContent = opt.label;
    btn.addEventListener('click', () => {
      _disableChips(chips);
      btn.classList.add('chip-selected');
      const extra = { no_year_clarify: true, no_more_clarify: true };
      if (opt.minYear) extra.min_year = opt.minYear;
      if (neighborhood) extra.neighborhood = neighborhood;
      pendingNeighborhood = null;
      sendQuestion(opt.label, settlement, extra);
    });
    chips.appendChild(btn);
  });

  bubble.querySelector('.message').appendChild(chips);
  bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
}

function showRoomsChips(bubble, settlement, neighborhood) {
  const chips = document.createElement('div');
  chips.className = 'clarify-chips';

  const allBtn = document.createElement('button');
  allBtn.className = 'chip chip-secondary';
  allBtn.textContent = 'כל מספר חדרים';
  allBtn.addEventListener('click', () => {
    _disableChips(chips);
    allBtn.classList.add('chip-selected');
    pendingRooms = null; pendingPropertyType = null; pendingSettlement = null; pendingNeighborhood = null;
    const extra = { no_more_clarify: true };
    if (neighborhood) extra.neighborhood = neighborhood;
    sendQuestion('כל מספר חדרים', settlement, extra);
  });
  chips.appendChild(allBtn);

  const roomOptions = [
    { label: '2 חד\'', value: '2' },
    { label: '3 חד\'', value: '3' },
    { label: '3–4 חד\'', value: '3-4' },
    { label: '4.5 חד\'', value: '4.5' },
    { label: '5+ חד\'', value: '5+' },
  ];

  roomOptions.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.textContent = opt.label;
    btn.addEventListener('click', () => {
      _disableChips(chips);
      btn.classList.add('chip-selected');
      const extra = { no_more_clarify: true, rooms: opt.value };
      if (pendingPropertyType) extra.property_type = pendingPropertyType;
      if (neighborhood) extra.neighborhood = neighborhood;
      pendingRooms = null; pendingPropertyType = null; pendingSettlement = null; pendingNeighborhood = null;
      sendQuestion(opt.label, settlement, extra);
    });
    chips.appendChild(btn);
  });

  bubble.querySelector('.message').appendChild(chips);
  bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
}

async function loadMoreDeals(reportId, offset, container, loadBtn) {
  loadBtn.disabled = true;
  loadBtn.textContent = 'טוען...';
  try {
    const resp = await fetch(`/api/deals/${reportId}?offset=${offset}&limit=10`);
    if (!resp.ok) throw new Error('error');
    const data = await resp.json();
    data.deals.forEach(d => {
      const row = document.createElement('div');
      row.className = 'deal-row';
      const price = d.price ? `₪${Number(d.price).toLocaleString('he-IL')}` : '—';
      const rooms = d.rooms ? `${d.rooms} חד'` : '—';
      const area  = d.area  ? `${d.area} מ"ר` : '—';
      const date  = (d.date || '').slice(0, 7);
      row.innerHTML = `<span class="deal-date">${date}</span><span class="deal-addr">${d.address || '—'}</span><span class="deal-price">${price}</span><span class="deal-meta">${rooms} · ${area} · ${d.floor || '—'}</span>`;
      container.insertBefore(row, loadBtn);
    });
    const newOffset = offset + data.deals.length;
    if (newOffset < data.total) {
      loadBtn.disabled = false;
      loadBtn.textContent = `טען עוד (${data.total - newOffset} נותרו)`;
      loadBtn.onclick = () => loadMoreDeals(reportId, newOffset, container, loadBtn);
    } else {
      loadBtn.remove();
    }
  } catch {
    loadBtn.textContent = 'שגיאה — נסה שוב';
    loadBtn.disabled = false;
  }
}

// ── Create compass loader element ──
function makeCompassLoader(text) {
  const wrap = document.createElement('div');
  wrap.className = 'compass-loader';
  wrap.innerHTML = `<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <circle cx="60" cy="60" r="54" fill="none" stroke="rgba(184,150,62,0.2)" stroke-width="2"/>
    <g class="needle-group" style="transform-origin:60px 60px">
      <polygon points="60,14 56,62 64,62" fill="#b8963e"/>
      <polygon points="60,106 56,62 64,62" fill="rgba(184,150,62,0.22)"/>
    </g>
    <circle cx="60" cy="60" r="6" fill="#b8963e" opacity="0.85"/>
    <circle cx="60" cy="60" r="3" fill="#f7f4ef"/>
  </svg><span class="compass-loader-text">${text || 'מחפש נתונים...'}</span>`;
  return wrap;
}

function appendBubble(role, content) {
  const container = document.getElementById('chat-container');
  const div = document.createElement('div');
  div.className = `bubble ${role}`;

  const avatar = document.createElement('div');
  avatar.className = `avatar ${role}-avatar`;
  if (role === 'bot') {
    avatar.innerHTML = COMPASS_SVG_AVATAR;
  } else {
    avatar.textContent = 'א';
  }

  const msg = document.createElement('div');
  msg.className = 'message';
  if (content) msg.textContent = content;

  div.appendChild(avatar);
  div.appendChild(msg);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function handleEvent(event, bubble, questionText) {
  const msgEl = bubble.querySelector('.message');

  // Only remove the compass loader when we have actual content to show
  const contentSteps = ['done', 'error', 'clarify', 'clarify_rooms', 'clarify_years', 'needs_token'];
  if (contentSteps.includes(event.step)) {
    const loader = bubble.querySelector('.compass-loader');
    if (loader) loader.remove();
  }

  if (event.step === 'needs_token') {
    msgEl.innerHTML = '';
    const card = document.createElement('div');
    card.className = 'token-card';
    card.innerHTML = `
      <p class="token-card-title">נדרש אישור reCAPTCHA</p>
      <p class="token-card-desc">Google חוסם קבלת token אוטומטית מהשרת. עליך לספק אותו ידנית:</p>
      <ol class="token-card-steps">
        <li><a href="${event.url}" target="_blank" rel="noopener" class="token-link">פתח את nadlan.gov.il ↗</a> והמתן 20 שניות</li>
        <li>לחץ F12 → Console</li>
        <li>הקלד: <code dir="ltr">sessionStorage.getItem('recaptchaServerToken')</code></li>
        <li>העתק את הערך (ללא גרשיים)</li>
      </ol>
      <div class="token-input-row">
        <input type="text" class="token-input" placeholder="הדבק token כאן..." dir="ltr" autocomplete="off" />
        <button class="chip token-submit-btn">שלח</button>
      </div>
    `;
    msgEl.appendChild(card);

    const tokenInput = card.querySelector('.token-input');
    const tokenSubmit = card.querySelector('.token-submit-btn');

    const submitToken = () => {
      const val = tokenInput.value.trim();
      if (!val) { tokenInput.focus(); return; }
      tokenSubmit.disabled = true;
      tokenInput.disabled = true;
      sendQuestion(questionText, event.settlement, {
        no_more_clarify: true,
        no_year_clarify: true,
        street: event.street || '',
        neighborhood: event.neighborhood || '',
        rooms: event.rooms || null,
        property_type: event.property_type || null,
        min_year: event.min_year || null,
        token: val,
      });
    };

    tokenSubmit.addEventListener('click', submitToken);
    tokenInput.addEventListener('keydown', e => { if (e.key === 'Enter') submitToken(); });
    return;
  }

  if (event.step === 'error') {
    const span = document.createElement('span');
    span.className = 'error-text';
    span.textContent = event.text || 'שגיאה';
    msgEl.textContent = '';
    msgEl.appendChild(span);
    return;
  }

  if (event.step === 'clarify') {
    msgEl.textContent = event.text;
    pendingSettlement = event.settlement;
    if (event.rooms) pendingRooms = event.rooms;
    if (event.property_type) pendingPropertyType = event.property_type;
    showClarifyChips(bubble, event.settlement, event);
    return;
  }

  if (event.step === 'clarify_rooms') {
    msgEl.textContent = event.text;
    pendingSettlement = event.settlement;
    pendingNeighborhood = event.neighborhood || null;
    showRoomsChips(bubble, event.settlement, event.neighborhood || '');
    return;
  }

  if (event.step === 'clarify_years') {
    msgEl.textContent = event.text;
    pendingSettlement = event.settlement;
    pendingNeighborhood = event.neighborhood || null;
    showYearsChips(bubble, event.settlement, event.cur_year || new Date().getFullYear(), event.neighborhood || '');
    return;
  }

  if (event.step === 'done') {
    msgEl.textContent = '';

    if (event.summary) {
      const p = document.createElement('p');
      p.className = 'summary-text';
      p.textContent = event.summary;
      msgEl.appendChild(p);
    }

    if (event.report_id) {
      const rid = Number(event.report_id);
      const btns = document.createElement('div');
      btns.className = 'result-btns';

      const reportLink = document.createElement('a');
      reportLink.href = `/report/${rid}`;
      reportLink.className = 'report-btn';
      reportLink.textContent = 'דוח מלא';
      btns.appendChild(reportLink);

      const dealsBtn = document.createElement('button');
      dealsBtn.className = 'report-btn report-btn-secondary';
      dealsBtn.textContent = 'ראה עסקאות';
      btns.appendChild(dealsBtn);

      msgEl.appendChild(btns);

      const dealsList = document.createElement('div');
      dealsList.className = 'deals-list';
      dealsList.style.display = 'none';
      msgEl.appendChild(dealsList);

      let dealsOpen = false;
      let initialised = false;
      dealsBtn.addEventListener('click', async () => {
        if (!dealsOpen) {
          dealsOpen = true;
          dealsList.style.display = 'block';
          if (!initialised) {
            initialised = true;
            const lb = document.createElement('button');
            lb.className = 'load-more-btn';
            lb.textContent = 'טוען...';
            dealsList.appendChild(lb);
            await loadMoreDeals(rid, 0, dealsList, lb);
          }
          dealsBtn.textContent = 'סגור עסקאות';
        } else {
          dealsOpen = false;
          dealsList.style.display = 'none';
          dealsBtn.textContent = 'ראה עסקאות';
        }
        bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
      });
    } else if (!event.summary) {
      msgEl.textContent = event.text || '';
    }

    // Follow-up suggestion chips
    if (event.suggestions && event.suggestions.length) {
      const sugWrap = document.createElement('div');
      sugWrap.className = 'clarify-chips suggestion-chips';
      event.suggestions.forEach(sug => {
        const btn = document.createElement('button');
        btn.className = 'chip chip-suggestion';
        btn.textContent = sug;
        btn.addEventListener('click', () => {
          sugWrap.querySelectorAll('.chip').forEach(c => (c.disabled = true));
          btn.classList.add('chip-selected');
          sendQuestion(sug);
        });
        sugWrap.appendChild(btn);
      });
      msgEl.appendChild(sugWrap);
    }

    // Save to history — store city (settlement) separately from label for context memory
    if (event.report_id || event.summary) {
      pushHistory({
        question: questionText || '',
        settlement: event.settlement || event.label || '',
        label: event.label || '',
        report_id: event.report_id || null,
        total_deals: event.total_deals || 0,
        ts: Date.now(),
      });
    }

    // Settle the hero compass if visible
    const heroCompass = document.querySelector('.hero-compass');
    if (heroCompass) {
      heroCompass.classList.remove('spinning');
      heroCompass.classList.add('settling');
    }

    const container = bubble.parentElement;
    if (container) container.scrollTop = container.scrollHeight;
    return;
  }

  // All intermediate steps (parsed, loading, fetching, etc.) are hidden from the user.
  // The compass loader already signals that work is happening.

  const container = bubble.parentElement;
  if (container) container.scrollTop = container.scrollHeight;
}

// ── Hero → Chat transition ──
function showChatScreen() {
  const heroEl = document.getElementById('hero-screen');
  const chatEl = document.getElementById('chat-screen');
  if (!heroEl || heroEl.style.display === 'none') return;

  heroEl.style.transition = 'opacity .35s ease, transform .35s ease';
  heroEl.style.opacity = '0';
  heroEl.style.transform = 'translateY(-16px)';
  setTimeout(() => {
    heroEl.style.display = 'none';
    chatEl.style.display = 'flex';
    chatEl.style.opacity = '0';
    chatEl.style.transition = 'opacity .3s ease';
    requestAnimationFrame(() => {
      chatEl.style.opacity = '1';
    });
    document.getElementById('question-input').focus();
    const hhb = document.getElementById('hero-history-btn');
    if (hhb) hhb.style.display = 'none';
  }, 340);
}

async function sendQuestion(overrideText, overrideSettlement, extraBody) {
  // If called from hero, grab hero input value
  const heroInput = document.getElementById('hero-input');
  const chatInput = document.getElementById('question-input');

  const heroScreen = document.getElementById('hero-screen');
  const isHero = heroScreen && heroScreen.style.display !== 'none';

  const question = overrideText || (isHero ? heroInput.value.trim() : chatInput.value.trim());
  if (!question) return;

  if (isHero) {
    showChatScreen();
    // Small delay so transition starts before we spin
    await new Promise(r => setTimeout(r, 50));
    const hc = document.querySelector('.hero-compass');
    if (hc) { hc.classList.add('spinning'); }
  }

  const settlement = overrideSettlement || pendingSettlement;
  const neighborhood = (extraBody && extraBody.neighborhood) || pendingNeighborhood || null;
  const rooms = (extraBody && extraBody.rooms) || pendingRooms;
  const propertyType = (extraBody && extraBody.property_type) || pendingPropertyType;
  const noMoreClarify = (extraBody && extraBody.no_more_clarify) || false;
  const noYearClarify = (extraBody && extraBody.no_year_clarify) || false;
  const minYear = (extraBody && extraBody.min_year) || null;
  pendingSettlement = null;
  pendingNeighborhood = null;
  pendingRooms = null;
  pendingPropertyType = null;
  chatInput.placeholder = 'חפש עסקאות נוספות...';

  if (heroInput) heroInput.value = '';
  chatInput.value = '';
  chatInput.disabled = true;
  const sendBtn = document.getElementById('send-btn');
  if (sendBtn) sendBtn.disabled = true;

  appendBubble('user', question);
  const botBubble = appendBubble('bot', '');
  const msgEl = botBubble.querySelector('.message');
  const loader = makeCompassLoader('מחפש...');
  msgEl.appendChild(loader);

  let reader = null;
  const body = { question };
  if (settlement) body.settlement = settlement;
  if (neighborhood) body.neighborhood = neighborhood;
  if (rooms) body.rooms = rooms;
  if (propertyType) body.property_type = propertyType;
  if (noMoreClarify) body.no_more_clarify = true;
  if (noYearClarify) body.no_year_clarify = true;
  if (minYear) body.min_year = minYear;
  if (extraBody && extraBody.token) body.token = extraBody.token;
  if (extraBody && extraBody.street) body.street = extraBody.street;
  // Pass last known settlement for context-aware parsing
  const lastSettlement = getLastSettlement();
  if (lastSettlement && !settlement) body.last_settlement = lastSettlement;

  try {
    const resp = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      resp.body.cancel();
      const loaderEl = botBubble.querySelector('.compass-loader');
      if (loaderEl) loaderEl.remove();
      const span = document.createElement('span');
      span.className = 'error-text';
      span.textContent = resp.status === 429
        ? 'יותר מדי בקשות — נסה שוב בעוד מספר דקות.'
        : 'שגיאה — נסה שוב';
      botBubble.querySelector('.message').appendChild(span);
      return;
    }

    reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (value) buffer += decoder.decode(value, { stream: true });
      if (done) {
        if (buffer.startsWith('data: ')) {
          try { handleEvent(JSON.parse(buffer.slice(6)), botBubble, question); } catch (_) {}
        }
        break;
      }
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { handleEvent(JSON.parse(line.slice(6)), botBubble, question); } catch (_) {}
        }
      }
    }
  } catch (e) {
    if (reader) { try { await reader.cancel(); } catch (_) {} }
    const span = document.createElement('span');
    span.className = 'error-text';
    span.textContent = 'שגיאת חיבור — נסה שוב';
    const msgEl2 = botBubble.querySelector('.message');
    msgEl2.textContent = '';
    msgEl2.appendChild(span);
  } finally {
    chatInput.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
    chatInput.focus();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // Hero input
  const heroInput = document.getElementById('hero-input');
  const heroSendBtn = document.getElementById('hero-send-btn');
  if (heroInput) {
    heroInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion(); }
    });
  }
  if (heroSendBtn) heroSendBtn.addEventListener('click', () => sendQuestion());

  // Example chips
  document.querySelectorAll('.example-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const q = chip.dataset.q;
      if (heroInput) heroInput.value = q;
      sendQuestion();
    });
  });

  // Back to hero from nav logo
  const navBrand = document.getElementById('nav-brand-link');
  if (navBrand) {
    navBrand.addEventListener('click', () => {
      const chatEl = document.getElementById('chat-screen');
      const heroEl = document.getElementById('hero-screen');
      if (chatEl && heroEl) {
        chatEl.style.display = 'none';
        heroEl.style.display = 'flex';
        heroEl.style.opacity = '1';
        heroEl.style.transform = 'none';
        const hc = document.querySelector('.hero-compass');
        if (hc) { hc.classList.remove('spinning', 'settling'); }
      }
    });
  }

  // Chat input
  const chatInput = document.getElementById('question-input');
  if (chatInput) {
    chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion(); }
    });
  }

  // History panel — both nav button and hero button
  const historyBtn = document.getElementById('history-btn');
  const heroHistoryBtn = document.getElementById('hero-history-btn');
  const historyClose = document.getElementById('history-close');
  const historyOverlay = document.getElementById('history-overlay');
  if (historyBtn) historyBtn.addEventListener('click', openHistoryPanel);
  if (heroHistoryBtn) heroHistoryBtn.addEventListener('click', openHistoryPanel);
  if (historyClose) historyClose.addEventListener('click', closeHistoryPanel);
  if (historyOverlay) historyOverlay.addEventListener('click', closeHistoryPanel);

  // Keyboard: Escape closes history
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeHistoryPanel();
  });
});
