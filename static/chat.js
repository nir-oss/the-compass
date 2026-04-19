function appendBubble(role, content) {
  const container = document.getElementById('chat-container');
  const div = document.createElement('div');
  div.className = `bubble ${role}`;

  const avatar = document.createElement('div');
  avatar.className = `avatar ${role}-avatar`;
  avatar.textContent = role === 'bot' ? 'AI' : 'א';

  const msg = document.createElement('div');
  msg.className = 'message';
  if (content) msg.textContent = content;

  div.appendChild(avatar);
  div.appendChild(msg);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function handleEvent(event, bubble) {
  const msgEl = bubble.querySelector('.message');

  // Remove typing indicator on first real event
  const typing = bubble.querySelector('.typing-indicator');
  if (typing) typing.remove();

  if (event.step === 'error') {
    const span = document.createElement('span');
    span.className = 'error-text';
    span.textContent = event.text || 'שגיאה';
    msgEl.textContent = '';
    msgEl.appendChild(span);
    return;
  }

  if (event.done) {
    msgEl.textContent = '';
    if (event.summary) {
      const p = document.createElement('p');
      p.className = 'summary-text';
      p.textContent = event.summary;
      msgEl.appendChild(p);
    }
    if (event.report_id) {
      const a = document.createElement('a');
      a.href = `/report/${Number(event.report_id)}`;
      a.className = 'report-btn';
      a.textContent = '📊 פתח דוח מלא';
      msgEl.appendChild(a);
    }
    if (!event.summary && !event.report_id) {
      msgEl.textContent = event.text || '';
    }
    return;
  }

  // Append progress line
  if (msgEl.childNodes.length > 0) {
    msgEl.appendChild(document.createTextNode('\n'));
  }
  const span = document.createElement('span');
  span.className = event.step || 'progress';
  const stepIcons = {
    parsed: '✓',
    fetching: '⟳',
    progress: '·',
    analyzing: '⟳',
    summarizing: '⟳',
  };
  const icon = stepIcons[event.step] || '·';
  span.textContent = `${icon} ${event.text}`;
  msgEl.appendChild(span);

  const container = bubble.parentElement;
  if (container) container.scrollTop = container.scrollHeight;
}

async function sendQuestion() {
  const input = document.getElementById('question-input');
  const question = input.value.trim();
  if (!question) return;

  input.value = '';
  input.disabled = true;
  document.getElementById('send-btn').disabled = true;

  appendBubble('user', question);
  const botBubble = appendBubble('bot', '');
  const msgEl = botBubble.querySelector('.message');
  // Show typing indicator
  const typingDiv = document.createElement('div');
  typingDiv.className = 'typing-indicator';
  typingDiv.innerHTML = '<span></span><span></span><span></span>';
  msgEl.appendChild(typingDiv);

  let reader = null;

  try {
    const resp = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    if (!resp.ok) {
      resp.body.cancel();
      const span = document.createElement('span');
      span.className = 'error-text';
      span.textContent = 'שגיאה — נסה שוב';
      botBubble.querySelector('.message').appendChild(span);
      return;
    }

    reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (value) {
        buffer += decoder.decode(value, { stream: true });
      }

      if (done) {
        // Flush remaining buffer
        if (buffer.startsWith('data: ')) {
          try { handleEvent(JSON.parse(buffer.slice(6)), botBubble); } catch (_) {}
        }
        break;
      }

      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            handleEvent(JSON.parse(line.slice(6)), botBubble);
          } catch (_) {}
        }
      }
    }
  } catch (e) {
    if (reader) {
      try { await reader.cancel(); } catch (_) {}
    }
    const span = document.createElement('span');
    span.className = 'error-text';
    span.textContent = 'שגיאת חיבור — נסה שוב';
    const msgEl = botBubble.querySelector('.message');
    msgEl.textContent = '';
    msgEl.appendChild(span);
  } finally {
    input.disabled = false;
    document.getElementById('send-btn').disabled = false;
    input.focus();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('question-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuestion();
    }
  });
});
