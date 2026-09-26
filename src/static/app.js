// Vera Message Engine — Minimal Single-Column Chatbot Client Logic

// 5 Delhi Merchant Personas (One per vertical, strictly in sync)
const CATEGORY_CONFIG = {
  dentists: {
    name: "Dentist",
    pluralName: "Dentists",
    icon: "🦷",
    merchant: "Rohini Dental Studio",
    locality: "Rohini, Delhi",
    displayLabel: "Rohini Dental Studio (Dentist)",
    suggestions: [
      "DCI revised radiograph dose limits compliance update",
      "6-month patient recall checkup for Priya",
      "IDA clinical research digest on fluoride varnish"
    ]
  },
  salons: {
    name: "Salon",
    pluralName: "Salons",
    icon: "✂️",
    merchant: "Chic Cuts Salon",
    locality: "Lajpat Nagar, Delhi",
    displayLabel: "Chic Cuts Salon (Salon)",
    suggestions: [
      "Diwali festive rush & salon booking surge",
      "Bridal makeup trial package followup for Kavya",
      "Balayage & Hair Spa special offer"
    ]
  },
  restaurants: {
    name: "Restaurant",
    pluralName: "Restaurants",
    icon: "🍽️",
    merchant: "Delhi Darbar Dhaba",
    locality: "Karol Bagh, Delhi",
    displayLabel: "Delhi Darbar Dhaba (Restaurant)",
    suggestions: [
      "FSSAI revised kitchen hygiene guidelines",
      "Profile views up 18% surge - highlight Biryani",
      "IPL match night dining & delivery special"
    ]
  },
  gyms: {
    name: "Gym",
    pluralName: "Gyms",
    icon: "🏋️",
    merchant: "Iron Pulse Fitness",
    locality: "Dwarka, Delhi",
    displayLabel: "Iron Pulse Fitness (Gym)",
    suggestions: [
      "30-day member inactivity recall (38 members)",
      "Complimentary body composition scan promotion",
      "3 FREE trial classes welcome offer"
    ]
  },
  pharmacies: {
    name: "Pharmacy",
    pluralName: "Pharmacies",
    icon: "💊",
    merchant: "Metro Care Pharmacy",
    locality: "Saket, Delhi",
    displayLabel: "Metro Care Pharmacy (Pharmacy)",
    suggestions: [
      "25-day chronic medication refill cycle",
      "Voluntary drug recall alert batch notification",
      "Summer ORS & skincare demand shift"
    ]
  }
};

const THINKING_PHRASES = [
  "Checking merchant context…",
  "Evaluating regulatory & operational signals…",
  "Calibrating zero-hallucination guardrails…",
  "Drafting grounded message…"
];

// App State (Single Source of Truth)
let activeCategory = "dentists";
let currentTurn = 1;
let conversationId = "conv_chat_" + Date.now();
let isGenerating = false;

// DOM Elements
const suggestionChipsContainer = document.getElementById('suggestionChips');
const chatThread = document.getElementById('chatThread');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const btnSend = document.getElementById('btnSend');
const btnNewChat = document.getElementById('btnNewChat');
const welcomeTime = document.getElementById('welcomeTime');

// Active Merchant Persona Dropdown Elements
const personaDropdown = document.getElementById('personaDropdown');
const personaDropdownBtn = document.getElementById('personaDropdownBtn');
const personaCurrentText = document.getElementById('personaCurrentText');
const personaItems = document.querySelectorAll('.persona-item');

// Initialize Welcome Timestamp
if (welcomeTime) {
  welcomeTime.textContent = formatTime(new Date());
}

// 1. Single State Updater: Updates Active Merchant Persona Dropdown
function setCategory(category) {
  if (!CATEGORY_CONFIG[category]) return;
  activeCategory = category;
  const config = CATEGORY_CONFIG[category];

  // A. Update Persona Dropdown Display (In place — single source of truth)
  if (personaCurrentText) {
    personaCurrentText.textContent = config.displayLabel;
  }
  personaItems.forEach(item => {
    const isMatch = item.dataset.category === category;
    item.classList.toggle('active', isMatch);
    item.setAttribute('aria-selected', isMatch ? 'true' : 'false');
  });

  // B. Close Dropdown
  if (personaDropdown) {
    personaDropdown.classList.remove('open');
    personaDropdownBtn?.setAttribute('aria-expanded', 'false');
  }

  // C. Update Suggested Scenario Chips
  renderSuggestions(category);
}

// 2. Render Suggestions for Active Category
function renderSuggestions(category) {
  const config = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.dentists;
  suggestionChipsContainer.innerHTML = '';

  config.suggestions.forEach(text => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'suggestion-chip';
    chip.textContent = text;
    chip.addEventListener('click', () => {
      chatInput.value = text;
      autoResizeTextarea();
      chatInput.focus();
    });
    suggestionChipsContainer.appendChild(chip);
  });
}

// 3. Dropdown Toggle & Selection Listeners
if (personaDropdownBtn) {
  personaDropdownBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = personaDropdown.classList.toggle('open');
    personaDropdownBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  });
}

personaItems.forEach(item => {
  item.addEventListener('click', (e) => {
    e.stopPropagation();
    setCategory(item.dataset.category);
  });
});

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
  if (personaDropdown && !personaDropdown.contains(e.target)) {
    personaDropdown.classList.remove('open');
    personaDropdownBtn?.setAttribute('aria-expanded', 'false');
  }
});

// 5. Auto-Resize Textarea
function autoResizeTextarea() {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
}

chatInput.addEventListener('input', autoResizeTextarea);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!isGenerating && chatInput.value.trim()) {
      chatForm.dispatchEvent(new Event('submit'));
    }
  }
});

// 6. Send Message Form Submit
chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text || isGenerating) return;

  // Append user bubble immediately
  appendUserMessage(text);

  // Clear input
  chatInput.value = '';
  chatInput.style.height = 'auto';
  btnSend.disabled = true;
  isGenerating = true;

  // Show typing indicator in Vera's slot
  const typingElement = appendTypingIndicator();
  scrollToBottom();

  const phraseInterval = startRotatingStatus(typingElement);

  // Simulated delay: 1.8s to 2.4s (guarantees engine does not feel like a static lookup)
  const simulatedDelayMs = 1800 + Math.floor(Math.random() * 600);
  const delayPromise = new Promise(resolve => setTimeout(resolve, simulatedDelayMs));

  // Actual API call to the real compose/decision engine
  let engineResponse = null;
  let apiError = null;

  try {
    const res = await fetch('/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category: activeCategory,
        message: text,
        conversation_id: conversationId,
        turn: currentTurn
      })
    });

    if (!res.ok) {
      throw new Error(`Server returned HTTP ${res.status}`);
    }
    engineResponse = await res.json();
  } catch (err) {
    apiError = err;
  }

  // Wait for simulated delay to complete
  await delayPromise;
  clearInterval(phraseInterval);

  // Remove typing indicator
  if (typingElement && typingElement.parentNode) {
    typingElement.parentNode.removeChild(typingElement);
  }

  // Render Bot Message
  if (apiError) {
    appendBotMessage({
      body: `I encountered an unexpected connection error: ${apiError.message}. Please verify the Vera Engine is reachable on port 8080.`,
      cta: 'error',
      grounding: ['Network or endpoint failure contacting /v1/chat']
    });
  } else if (engineResponse) {
    currentTurn += 1;
    appendBotMessage(engineResponse);
  }

  btnSend.disabled = false;
  isGenerating = false;
  chatInput.focus();
  scrollToBottom();
});

// 7. Append User Message Bubble
function appendUserMessage(text) {
  const row = document.createElement('div');
  row.className = 'msg-row user';
  row.innerHTML = `
    <div class="bubble-meta">
      <span class="msg-time">${formatTime(new Date())}</span>
    </div>
    <div class="chat-bubble user">
      <div class="bubble-body">${escapeHtml(text)}</div>
    </div>
  `;
  chatThread.appendChild(row);
  scrollToBottom();
}

// 8. Append Typing Indicator Bubble
function appendTypingIndicator() {
  const row = document.createElement('div');
  row.className = 'msg-row bot typing';
  row.innerHTML = `
    <div class="bubble-meta">
      <div class="sender-info">
        <span class="sender-name">Vera Engine</span>
        <span class="bot-badge">AI</span>
      </div>
      <span class="msg-time">Thinking…</span>
    </div>
    <div class="chat-bubble bot">
      <div class="typing-box">
        <div class="typing-dots">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
        <div class="typing-status-text" id="typingStatusText">${THINKING_PHRASES[0]}</div>
      </div>
    </div>
  `;
  chatThread.appendChild(row);
  return row;
}

function startRotatingStatus(typingRow) {
  let idx = 0;
  return setInterval(() => {
    idx = (idx + 1) % THINKING_PHRASES.length;
    const label = typingRow.querySelector('#typingStatusText');
    if (label) {
      label.textContent = THINKING_PHRASES[idx];
    }
  }, 650);
}

// 9. Append Bot Message with CTA and Grounding Accordion
function appendBotMessage(data) {
  const msgId = 'grounding_' + Date.now();
  const row = document.createElement('div');
  row.className = 'msg-row bot';

  const groundingListHtml = (data.grounding && data.grounding.length > 0)
    ? data.grounding.map(g => `<li>${escapeHtml(g)}</li>`).join('')
    : '<li>Grounded in active vertical strategy and merchant identity.</li>';

  const ctaVal = data.cta || 'none';

  row.innerHTML = `
    <div class="bubble-meta">
      <div class="sender-info">
        <span class="sender-name">Vera Engine</span>
        <span class="bot-badge">AI</span>
      </div>
      <span class="msg-time">${formatTime(new Date())}</span>
    </div>
    <div class="chat-bubble bot">
      <div class="bubble-body">${escapeHtml(data.body)}</div>
      <div class="bubble-footer">
        <div class="cta-indicator">
          <span class="cta-label">CTA:</span>
          <span class="cta-badge">${escapeHtml(ctaVal)}</span>
        </div>
        <button class="toggle-grounding-btn" data-target="${msgId}">
          <span>Why this message?</span>
          <svg class="chevron-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>
      </div>
      <div class="grounding-panel" id="${msgId}">
        <div class="grounding-header">
          <span class="grounding-title">🛡️ Grounded Facts & Rationale</span>
        </div>
        <ul class="grounding-list">
          ${groundingListHtml}
        </ul>
      </div>
    </div>
  `;

  // Attach toggle listener to "Why this message?"
  const toggleBtn = row.querySelector('.toggle-grounding-btn');
  const panel = row.querySelector(`#${msgId}`);
  if (toggleBtn && panel) {
    toggleBtn.addEventListener('click', () => {
      const isOpen = panel.classList.toggle('open');
      toggleBtn.classList.toggle('open', isOpen);
      scrollToBottom();
    });
  }

  chatThread.appendChild(row);
  scrollToBottom();
}

// 10. Global Accordion Listener for Static Welcoming Message
document.querySelectorAll('.toggle-grounding-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const targetId = btn.dataset.target;
    const panel = document.getElementById(targetId);
    if (panel) {
      const isOpen = panel.classList.toggle('open');
      btn.classList.toggle('open', isOpen);
      scrollToBottom();
    }
  });
});

// 11. New Chat / Reset
btnNewChat.addEventListener('click', () => {
  conversationId = "conv_chat_" + Date.now();
  currentTurn = 1;

  // Clear thread except welcoming message
  chatThread.innerHTML = `
    <div class="msg-row bot" id="msg-welcome">
      <div class="bubble-meta">
        <div class="sender-info">
          <span class="sender-name">Vera Engine</span>
          <span class="bot-badge">AI</span>
        </div>
        <span class="msg-time">${formatTime(new Date())}</span>
      </div>
      <div class="chat-bubble bot">
        <div class="bubble-body">
          Hello! I am Vera. I generate grounded, high-compulsion operational outreach messages tailored specifically to each business vertical.
          <br><br>
          Select an active merchant persona below, then type any operational scenario or choose a suggested prompt to compose a grounded message with zero hallucinations.
        </div>
        <div class="bubble-footer">
          <div class="cta-indicator">
            <span class="cta-label">Status:</span>
            <span class="cta-badge">ready</span>
          </div>
          <button class="toggle-grounding-btn" data-target="grounding-welcome">
            <span>Why this message?</span>
            <svg class="chevron-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </button>
        </div>
        <div class="grounding-panel" id="grounding-welcome">
          <div class="grounding-header">
            <span class="grounding-title">🛡️ Guardrails & Operational Directives</span>
          </div>
          <ul class="grounding-list">
            <li>100% grounded in verified category digest, regulatory updates, and merchant context.</li>
            <li>Strict safety guardrail: 0 URLs in all messages to prevent external link penalties.</li>
            <li>Low-friction binary yes/no CTAs calibrated to maximize response compulsion.</li>
            <li>Inbound turn engine handles commitment, WhatsApp auto-replies, and opt-outs.</li>
          </ul>
        </div>
      </div>
    </div>
  `;

  // Re-attach welcome listener
  const welcomeBtn = chatThread.querySelector('.toggle-grounding-btn');
  const welcomePanel = chatThread.querySelector('#grounding-welcome');
  if (welcomeBtn && welcomePanel) {
    welcomeBtn.addEventListener('click', () => {
      const isOpen = welcomePanel.classList.toggle('open');
      welcomeBtn.classList.toggle('open', isOpen);
    });
  }

  showToast('Started fresh conversation.');
});

// Helper: Scroll Chat to Bottom
function scrollToBottom() {
  window.scrollTo({
    top: document.body.scrollHeight,
    behavior: 'smooth'
  });
}

// Helper: Format Time
function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Helper: HTML Escaping
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Toast Notification
function showToast(msg) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = msg;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 250);
  }, 2500);
}

// Initial Setup: Set Default Persona (Dentists / Rohini Dental Studio)
setCategory(activeCategory);
