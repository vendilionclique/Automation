function sendResult(sendResponse, success, data = null, error = null) {
  sendResponse({ success, data, error });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.action) {
    dispatchAction(message, sendResponse);
    return true; // 异步响应
  }
});

async function dispatchAction(message, sendResponse) {
  try {
    switch (message.action) {
      case 'offscreen-ping':
        sendResult(sendResponse, true, 'pong');
        break;
      case 'offscreen-fetch':
        await handleFetch(message, sendResponse);
        break;
      case 'offscreen-set-timer':
        await handleSetTimer(message, sendResponse);
        break;
      case 'offscreen-clear-timer':
        await handleClearTimer(message, sendResponse);
        break;
      case 'offscreen-notify':
        await handleNotify(message, sendResponse);
        break;
      case 'offscreen-cache-set':
        await handleCacheSet(message, sendResponse);
        break;
      case 'offscreen-cache-get':
        await handleCacheGet(message, sendResponse);
        break;
      case 'offscreen-cache-remove':
        await handleCacheRemove(message, sendResponse);
        break;
      case 'offscreen-parse-html':
        await handleParseHtml(message, sendResponse);
        break;
      case 'offscreen-create-blob':
        await handleCreateBlob(message, sendResponse);
        break;
      case 'offscreen-download-blob':
        await handleDownloadBlob(message, sendResponse);
        break;
      case 'offscreen-capture-screen':
        await handleCaptureScreen(message, sendResponse);
        break;
      case 'offscreen-webrtc-offer':
        await handleWebRTCOffer(message, sendResponse);
        break;
      case 'offscreen-clipboard-write':
        await handleClipboardWrite(message, sendResponse);
        break;
      case 'offscreen-clipboard-read':
        await handleClipboardRead(message, sendResponse);
        break;
      default:
        sendResult(sendResponse, false, null, '未知 action');
    }
  } catch (e) {
    sendResult(sendResponse, false, null, e?.message || e);
  }
}

async function handleFetch(message, sendResponse) {
  try {
    const { url, options } = message.data || {};
    if (!url) return sendResult(sendResponse, false, null, '缺少 url');
    const res = await fetch(url, options || {});
    const contentType = res.headers.get('content-type') || '';
    let data;
    if (contentType.includes('json')) {
      data = await res.json();
    } else if (contentType.includes('text')) {
      data = await res.text();
    } else {
      data = await res.blob();
    }
    sendResult(sendResponse, true, data);
  } catch (e) {
    sendResult(sendResponse, false, null, e?.message || e);
  }
}

const timerMap = {};
let timerIdSeed = 1;

async function handleSetTimer(message, sendResponse) {
  const { type, delay } = message.data || {};
  if (!['timeout', 'interval'].includes(type)) {
    return sendResult(sendResponse, false, null, 'type 必须为 timeout 或 interval');
  }
  const id = timerIdSeed++;
  if (type === 'timeout') {
    timerMap[id] = setTimeout(() => {
      chrome.runtime.sendMessage({ action: 'offscreen-timer-fired', id });
      delete timerMap[id];
    }, delay || 1000);
  } else {
    timerMap[id] = setInterval(() => {
      chrome.runtime.sendMessage({ action: 'offscreen-timer-fired', id });
    }, delay || 1000);
  }
  sendResult(sendResponse, true, { id });
}

async function handleClearTimer(message, sendResponse) {
  const { id, type } = message.data || {};
  if (!id || !timerMap[id]) return sendResult(sendResponse, false, null, '无效的 timer id');
  if (type === 'interval') {
    clearInterval(timerMap[id]);
  } else {
    clearTimeout(timerMap[id]);
  }
  delete timerMap[id];
  sendResult(sendResponse, true);
}

async function handleNotify(message, sendResponse) {
  const { title, message: msg, iconUrl } = message.data || {};
  if (!title || !msg) return sendResult(sendResponse, false, null, 'title 和 message 必填');
  chrome.notifications.create('', {
    type: 'basic',
    iconUrl: iconUrl || 'icon.png',
    title,
    message: msg
  }, (notificationId) => {
    sendResult(sendResponse, true, { notificationId });
  });
}

const cacheKey = 'offscreen-cache-dts';

async function handleCacheSet(message, sendResponse) {
  const { key, value } = message.data || {};
  if (!key) return sendResult(sendResponse, false, null, 'key 必填');
  localStorage.setItem(`${cacheKey}:${key}`, JSON.stringify(value));
  sendResult(sendResponse, true);
}

async function handleCacheGet(message, sendResponse) {
  const { key } = message.data || {};
  if (!key) return sendResult(sendResponse, false, null, 'key 必填');
  const value = localStorage.getItem(`${cacheKey}:${key}`);
  sendResult(sendResponse, true, value ? JSON.parse(value) : null);
}

async function handleCacheRemove(message, sendResponse) {
  const { key } = message.data || {};
  if (!key) return sendResult(sendResponse, false, null, 'key 必填');
  localStorage.removeItem(`${cacheKey}:${key}`);
  sendResult(sendResponse, true);
}

async function handleParseHtml(message, sendResponse) {
  const { html, selector } = message.data || {};
  if (!html) return sendResult(sendResponse, false, null, 'html 必填');
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    let result = null;
    if (selector) {
      const el = doc.querySelector(selector);
      result = el ? el.outerHTML : null;
    } else {
      result = doc.body.innerHTML;
    }
    sendResult(sendResponse, true, result);
  } catch (e) {
    sendResult(sendResponse, false, null, e?.message || e);
  }
}

async function handleCreateBlob(message, sendResponse) {
  const { data, type } = message.data || {};
  try {
    const blob = new Blob([data], { type: type || 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    sendResult(sendResponse, true, { url });
  } catch (e) {
    sendResult(sendResponse, false, null, e?.message || e);
  }
}

async function handleDownloadBlob(message, sendResponse) {
  const { url, filename } = message.data || {};
  if (!url || !filename) return sendResult(sendResponse, false, null, 'url 和 filename 必填');
  try {
    chrome.downloads.download({ url, filename }, downloadId => {
      sendResult(sendResponse, true, { downloadId });
    });
  } catch (e) {
    sendResult(sendResponse, false, null, e?.message || e);
  }
}

async function handleCaptureScreen(message, sendResponse) {
  try {
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    // 这里只能返回 stream id，不能直接传递 stream
    sendResult(sendResponse, true, { streamId: stream.id });
    // 注意：stream 只能在 offscreen 内部用，不能直接传递到 background
  } catch (e) {
    sendResult(sendResponse, false, null, e?.message || e);
  }
}

let rtcPeerConnection = null;
async function handleWebRTCOffer(message, sendResponse) {
  try {
    rtcPeerConnection = new RTCPeerConnection();
    const offer = await rtcPeerConnection.createOffer();
    await rtcPeerConnection.setLocalDescription(offer);
    sendResult(sendResponse, true, { offer });
  } catch (e) {
    sendResult(sendResponse, false, null, e?.message || e);
  }
}

async function handleClipboardWrite(message, sendResponse) {
  const { text } = message.data || {};
  if (!text) return sendResult(sendResponse, false, null, 'text 必填');
  try {
    await navigator.clipboard.writeText(text);
    sendResult(sendResponse, true);
  } catch (e) {
    sendResult(sendResponse, false, null, e?.message || e);
  }
}

async function handleClipboardRead(message, sendResponse) {
  try {
    const text = await navigator.clipboard.readText();
    sendResult(sendResponse, true, { text });
  } catch (e) {
    sendResult(sendResponse, false, null, e?.message || e);
  }
} 