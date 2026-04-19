function appendBubble(role, content) {
  const container = document.getElementById('chat-container');
  const div = document.createElement('div');
  div.className = `bubble ${role}`;

  const avatar = document.createElement('div');
  avatar.className = `avatar ${role}-avatar`;
  avatar.textContent = role === 'bot' ? 'AI' : 'א';

  const msg = document.createElement('div');
  msg.className = 'message';
  msg.innerHTML = content;

  div.appendChild(avatar);
  div.appendChild(msg);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function handleEvent(event, bubble) {
  const msgEl = bubble.querySelector('.message');

  if (event.step === 'error') {
    msgEl.innerHTML = `<span class="error-text">${event.text}</span>`;
    return;
  }

  if (event.done) {
    let html = '';
    if (event.summary) {
      html += `<p style="margin-bottom:8px">${event.summary}</p>`;
    }
    if (event.report_id) {
      html += `<a href="/report/${event.report_id}" class="report-btn">📊 פתח דוח מלא</a>`;
    }
    msgEl.innerHTML = html || event.text;
    return;
  }

  // Append progress line
  const existing = msgEl.innerHTML;
  const line = `<span class="${event.step}">${event.text}</span>`;
  msgEl.innerHTML = existing ? existing + '\n' + line : line;
  bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
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

  try {
    const resp = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    if (!resp.ok) {
      botBubble.querySelector('.message').innerHTML =
        '<span class="error-text">שגיאה — נסה שוב</span>';
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

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
    botBubble.querySelector('.message').innerHTML =
      '<span class="error-text">שגיאת חיבור — נסה שוב</span>';
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
