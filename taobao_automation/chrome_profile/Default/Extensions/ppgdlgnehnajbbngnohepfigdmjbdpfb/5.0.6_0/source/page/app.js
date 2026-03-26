(function() {

  window.localforage = window.localforage || window.DTS_ISOLATED.localforage;

  const MESSAGE_CONSTANTS = 'DTS__APP__MSG';
  // storage: undefined | { name, storeName }
  function getStore(storage) {
    if (storage) {
      return localforage.createInstance({
        name: storage.name || 'frame_db',
        storeName: storage.storeName || 'frame_store'
      });
    }
    return {
      setItem: (k, v) => Promise.resolve(localStorage.setItem(k, v)),
      getItem: (k) => Promise.resolve(localStorage.getItem(k)),
      removeItem: (k) => Promise.resolve(localStorage.removeItem(k)),
      clear: () => Promise.resolve(localStorage.clear()),
      keys: () => Promise.resolve(Object.keys(localStorage)),
      getAll: () => Promise.resolve(JSON.parse(JSON.stringify(localStorage)))
    };
  }

  function postMessageHandler(data, method, event) {
    event.source.postMessage({
      data,
      method,
      type: MESSAGE_CONSTANTS,
    }, event.origin);
  }

  async function messageListener(e) {
    let payload = null;
    if (typeof e.data === 'string' && !e.data.includes('webpack')) {
      try { payload = JSON.parse(e.data); } catch { return; }
    } else if (e.data && typeof e.data === 'object') {
      payload = e.data;
    }
    if (!payload || payload.type !== MESSAGE_CONSTANTS) {
      return;
    }
    const storage = payload.storage;
    const store = getStore(storage);
    let _data = null;
    switch (payload.method) {
      case 'set': {
        if (storage) {
          await store.setItem(payload.key, payload.data);
        } else {
          await store.setItem(payload.key, JSON.stringify(payload.data));
        }
        break;
      }
      case 'get': {
        let data = await store.getItem(payload.key);
        if (!storage) {
          data = data ? JSON.parse(data) : null;
        }
        _data = data;
        break;
      }
      case 'getAll': {
        if (storage) {
          const keys = await store.keys();
          let all = {};
          for (let k of keys) {
            all[k] = await store.getItem(k);
          }
          _data = all;
        } else {
          let all = {};
          for (let i = 0; i < localStorage.length; i++) {
            let k = localStorage.key(i);
            all[k] = JSON.parse(localStorage.getItem(k));
          }
          _data = all;
        }
        break;
      }
      case 'remove': {
        await store.removeItem(payload.key);
        break;
      }
      case 'clear': {
        await store.clear();
        break;
      }
    }
    postMessageHandler(_data, payload.method, e);
  }

  window.addEventListener('message', messageListener);
})();