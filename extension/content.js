// content.js

// ============================================================
// 1. جلب بيانات الفيديو
// ============================================================
function getVideoData() {
  const videoId = new URLSearchParams(window.location.search).get('v');
  const url     = `https://www.youtube.com/watch?v=${videoId}`;

  const title =
    document.querySelector('h1.ytd-video-primary-info-renderer yt-formatted-string')?.innerText ||
    document.querySelector('h1.ytd-watch-metadata yt-formatted-string')?.innerText ||
    document.title?.replace(' - YouTube', '') || '';

  const channel =
    document.querySelector('ytd-channel-name yt-formatted-string a')?.innerText ||
    document.querySelector('#channel-name a')?.innerText ||
    document.querySelector('ytd-video-owner-renderer yt-formatted-string a')?.innerText || '';

  const description =
    document.querySelector('ytd-text-inline-expander yt-attributed-string')?.innerText ||
    document.querySelector('#description-inline-expander yt-attributed-string')?.innerText ||
    document.querySelector('#description')?.innerText || '';

  return { url, videoId, title, channel, description };
}

// ============================================================
// 2. جلب الترانسكربت
// ============================================================
async function getTranscript(videoId) {
  try {
    const playerResponse = window.ytInitialPlayerResponse;
    if (!playerResponse) return null;

    const captionTracks =
      playerResponse?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
    if (!captionTracks || captionTracks.length === 0) return null;

    const arabicTrack  = captionTracks.find(t => t.languageCode === 'ar');
    const englishTrack = captionTracks.find(t => t.languageCode === 'en');
    const track = arabicTrack || englishTrack || captionTracks[0];

    const response = await fetch(track.baseUrl);
    const xmlText  = await response.text();

    const parser    = new DOMParser();
    const xmlDoc    = parser.parseFromString(xmlText, 'text/xml');
    const textNodes = xmlDoc.querySelectorAll('text');

    const transcript = Array.from(textNodes)
      .map(node => node.textContent
        .replace(/&#39;/g,  "'")
        .replace(/&amp;/g,  '&')
        .replace(/&lt;/g,   '<')
        .replace(/&gt;/g,   '>')
        .replace(/&quot;/g, '"')
        .trim()
      )
      .filter(Boolean)
      .join(' ');

    return { text: transcript, language: track.languageCode, trackName: track.name?.simpleText || '' };
  } catch (e) {
    console.error('Transcript error:', e);
    return null;
  }
}

// ============================================================
// 3. جلب الكوكيز عبر رسالة للـ background
// ============================================================
function getCookies() {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: 'getCookies' }, (response) => {
      resolve(response?.cookiesTxt || null);
    });
  });
}

// ============================================================
// 4. حالات الزرار
// ============================================================
function setBtnState(btn, state) {
  const states = {
    idle:    { text: '🎬 كلبنج',        bg: '#ff2c2c', cursor: 'pointer',      disabled: false },
    loading: { text: '⏳ جاري...',       bg: '#555555', cursor: 'not-allowed',  disabled: true  },
    success: { text: '✅ اتبعت!',        bg: '#2eca7f', cursor: 'default',      disabled: false },
    error:   { text: '❌ فيه مشكلة',    bg: '#cc0000', cursor: 'default',      disabled: false },
    nourl:   { text: '⚠️ حط الـ Webhook', bg: '#cc7700', cursor: 'default',    disabled: false },
  };
  const s = states[state];
  btn.innerText        = s.text;
  btn.style.background = s.bg;
  btn.style.cursor     = s.cursor;
  btn.disabled         = s.disabled;
}

// ============================================================
// 5. إرسال البيانات + الكوكيز للـ Webhook
// ============================================================
async function sendToWebhook(webhookUrl, btn) {
  setBtnState(btn, 'loading');

  const basicData  = getVideoData();
  const transcript = await getTranscript(basicData.videoId);
  const cookiesTxt = await getCookies();

  const payload = {
    timestamp:   new Date().toISOString(),
    source:      'YouTube Video Sender Extension',
    url:         basicData.url,
    title:       basicData.title,
    channel:     basicData.channel,
    description: basicData.description,
    transcript:  transcript || null,
    cookies_txt: cookiesTxt || null,
  };

  try {
    const res = await fetch(webhookUrl, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    setBtnState(btn, res.ok ? 'success' : 'error');
  } catch (e) {
    console.error('Webhook error:', e);
    setBtnState(btn, 'error');
  }

  setTimeout(() => setBtnState(btn, 'idle'), 2500);
}

// ============================================================
// 6. إضافة زرار كلبنج
// ============================================================
function injectKlabngButton() {
  if (document.getElementById('klabng-btn')) return;

  const likeContainer =
    document.querySelector('ytd-segmented-like-dislike-button-renderer') ||
    document.querySelector('#segmented-like-dislike-button')             ||
    document.querySelector('ytd-menu-renderer #top-level-buttons-computed');

  if (!likeContainer) return;

  const btn = document.createElement('button');
  btn.id = 'klabng-btn';
  btn.style.cssText = `
    background    : #ff2c2c;
    color         : #ffffff;
    border        : none;
    border-radius : 20px;
    padding       : 8px 18px;
    font-size     : 14px;
    font-weight   : 700;
    font-family   : 'Cairo', 'Segoe UI', Arial, sans-serif;
    cursor        : pointer;
    margin-inline-start: 10px;
    transition    : opacity 0.2s;
    vertical-align: middle;
    line-height   : 1.4;
    white-space   : nowrap;
  `;

  setBtnState(btn, 'idle');

  btn.addEventListener('mouseenter', () => { if (!btn.disabled) btn.style.opacity = '0.85'; });
  btn.addEventListener('mouseleave', () => { btn.style.opacity = '1'; });

  btn.addEventListener('click', () => {
    chrome.storage.local.get(['webhookUrl'], (result) => {
      const webhookUrl = result.webhookUrl?.trim();
      if (!webhookUrl) {
        setBtnState(btn, 'nourl');
        setTimeout(() => setBtnState(btn, 'idle'), 3000);
        return;
      }
      sendToWebhook(webhookUrl, btn);
    });
  });

  likeContainer.parentElement.insertBefore(btn, likeContainer.nextSibling);
}

// ============================================================
// 7. MutationObserver
// ============================================================
let lastUrl = '';

function watchForVideoPage() {
  const observer = new MutationObserver(() => {
    const currentUrl = window.location.href;
    if (currentUrl !== lastUrl || !document.getElementById('klabng-btn')) {
      lastUrl = currentUrl;
      if (currentUrl.includes('youtube.com/watch')) {
        setTimeout(injectKlabngButton, 1500);
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

// ============================================================
// 8. Start
// ============================================================
if (window.location.href.includes('youtube.com/watch')) {
  setTimeout(injectKlabngButton, 1500);
}
watchForVideoPage();

// ============================================================
// 9. رسايل من الـ popup
// ============================================================
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getVideoData') {
    const basicData = getVideoData();
    if (request.includeTranscript) {
      getTranscript(basicData.videoId).then(transcript => {
        sendResponse({ ...basicData, transcript });
      });
      return true;
    } else {
      sendResponse(basicData);
    }
  }
});
