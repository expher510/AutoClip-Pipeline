// popup.js

const warning        = document.getElementById('warning');
const videoCard      = document.getElementById('videoCard');
const hintEl         = document.getElementById('hint');
const videoTitleEl   = document.getElementById('videoTitle');
const videoChannelEl = document.getElementById('videoChannel');
const videoUrlEl     = document.getElementById('videoUrl');
const webhookInput   = document.getElementById('webhookUrl');
const cookiesBtn     = document.getElementById('cookiesBtn');
const klabngBtn      = document.getElementById('klabngBtn');
const actionStatus   = document.getElementById('actionStatus');

let currentTabId  = null;
let isYouTubeVideo = false;

// ============================================================
// نجيب الـ webhook المحفوظ
// ============================================================
chrome.storage.local.get(['webhookUrl'], (result) => {
  if (result.webhookUrl) webhookInput.value = result.webhookUrl;
});

// نحفظ الـ webhook لما المستخدم يكتب
webhookInput.addEventListener('input', () => {
  chrome.storage.local.set({ webhookUrl: webhookInput.value });
});

// ============================================================
// نجيب tab الحالي
// ============================================================
chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
  const tab = tabs[0];
  const url = tab?.url || '';
  currentTabId = tab?.id;

  if (!url.includes('youtube.com/watch')) {
    warning.style.display = 'block';
    // زرار كلبنج متعطل لو مش على فيديو
    klabngBtn.disabled = true;
    klabngBtn.style.background = '#333';
    klabngBtn.style.cursor = 'not-allowed';
    klabngBtn.textContent = '🎬 كلبنج (افتح فيديو الأول)';
    return;
  }

  isYouTubeVideo = true;
  videoCard.style.display = 'block';
  hintEl.style.display    = 'block';

  try {
    const response = await sendMessageToTab(tab.id, {
      action: 'getVideoData',
      includeTranscript: false,
    });
    displayVideoData(response);
  } catch (e) {
    videoTitleEl.textContent = '(انتظر تحميل الصفحة)';
  }
});

// ============================================================
// زرار إرسال الكوكيز
// ============================================================
cookiesBtn.addEventListener('click', async () => {
  const webhookUrl = webhookInput.value.trim();
  if (!webhookUrl) {
    setStatus('⚠️ حط الـ Webhook URL الأول!', 'error');
    return;
  }

  cookiesBtn.disabled     = true;
  cookiesBtn.textContent  = '⏳ جاري الإرسال...';
  setStatus('', '');

  try {
    const cookies       = await chrome.cookies.getAll({ domain: '.youtube.com' });
    const googleCookies = await chrome.cookies.getAll({ domain: '.google.com' });
    const allCookies    = [...cookies, ...googleCookies];
    const cookiesTxt    = convertToNetscapeFormat(allCookies);

    const res = await fetch(webhookUrl, {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({
        type         : 'youtube_cookies',
        cookies_txt  : cookiesTxt,
        cookies_count: allCookies.length,
        timestamp    : new Date().toISOString(),
      }),
    });

    if (res.ok) {
      setStatus(`✅ اتبعت ${allCookies.length} كوكي بنجاح!`, 'success');
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (e) {
    setStatus(`❌ فيه مشكلة: ${e.message}`, 'error');
  }

  cookiesBtn.disabled    = false;
  cookiesBtn.textContent = '🍪 إرسال الكوكيز';
  setTimeout(() => setStatus('', ''), 3000);
});

// ============================================================
// زرار كلبنج — بيبعت بيانات الفيديو + الكوكيز
// ============================================================
klabngBtn.addEventListener('click', async () => {
  const webhookUrl = webhookInput.value.trim();
  if (!webhookUrl) {
    setStatus('⚠️ حط الـ Webhook URL الأول!', 'error');
    return;
  }
  if (!isYouTubeVideo || !currentTabId) {
    setStatus('⚠️ افتح فيديو يوتيوب الأول!', 'error');
    return;
  }

  klabngBtn.disabled     = true;
  klabngBtn.textContent  = '⏳ جاري الإرسال...';
  klabngBtn.style.background = '#555';
  setStatus('', '');

  try {
    // جيب بيانات الفيديو + الترانسكربت من الـ content script
    const videoData = await sendMessageToTab(currentTabId, {
      action           : 'getVideoData',
      includeTranscript: true,
    });

    // جيب الكوكيز
    const ytCookies = await chrome.cookies.getAll({ domain: '.youtube.com' });
    const gCookies  = await chrome.cookies.getAll({ domain: '.google.com' });
    const cookiesTxt = convertToNetscapeFormat([...ytCookies, ...gCookies]);

    const payload = {
      timestamp  : new Date().toISOString(),
      source     : 'YouTube Video Sender Extension',
      url        : videoData.url,
      title      : videoData.title,
      channel    : videoData.channel,
      description: videoData.description,
      transcript : videoData.transcript || null,
      cookies_txt: cookiesTxt || null,
    };

    const res = await fetch(webhookUrl, {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify(payload),
    });

    if (res.ok) {
      klabngBtn.style.background = 'var(--green, #2eca7f)';
      klabngBtn.textContent      = '✅ اتبعت!';
      setStatus('✅ بيانات الفيديو والكوكيز اتبعتوا!', 'success');
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (e) {
    klabngBtn.style.background = '#cc0000';
    klabngBtn.textContent      = '❌ فيه مشكلة';
    setStatus(`❌ ${e.message}`, 'error');
  }

  setTimeout(() => {
    klabngBtn.disabled         = false;
    klabngBtn.textContent      = '🎬 كلبنج';
    klabngBtn.style.background = 'var(--red, #ff2c2c)';
    setStatus('', '');
  }, 2500);
});

// ============================================================
// تحويل الكوكيز لـ Netscape format
// ============================================================
function convertToNetscapeFormat(cookies) {
  const lines = ['# Netscape HTTP Cookie File', '# Generated by YouTube Video Sender Extension', ''];
  for (const cookie of cookies) {
    const domain = cookie.domain;
    const flag   = domain.startsWith('.') ? 'TRUE' : 'FALSE';
    const path   = cookie.path || '/';
    const secure = cookie.secure ? 'TRUE' : 'FALSE';
    const expiry = cookie.expirationDate ? Math.floor(cookie.expirationDate) : 0;
    lines.push(`${domain}\t${flag}\t${path}\t${secure}\t${expiry}\t${cookie.name}\t${cookie.value}`);
  }
  return lines.join('\n');
}

// ============================================================
// helpers
// ============================================================
function setStatus(msg, type) {
  actionStatus.textContent = msg;
  actionStatus.className   = 'action-status' + (type ? ` ${type}` : '');
}

function displayVideoData(data) {
  videoTitleEl.textContent   = data.title   || '(بدون عنوان)';
  videoChannelEl.textContent = data.channel ? `📺 ${data.channel}` : '';
  videoUrlEl.textContent     = data.url     || '';
}

function sendMessageToTab(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
      } else {
        resolve(response);
      }
    });
  });
}
