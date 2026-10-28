'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const defaults = {fit:'cover',zoom:1,x:0,y:0,brightness:1,contrast:1,saturation:1,rotation:0,effect:'none',background:'#0b0e12',layout:'image',title:'MERHABA',subtitle:'BENİM EKRANIM',color:'#bcf26d'};
  let settings = {...defaults};
  let assetId = null;
  let assetName = 'Stüdyo örneği';
  let render = null;
  let state = {device:{connected:false},job:{state:'idle',progress:0}};
  let token = null;
  let importing = false;
  let rendering = true;
  let sendPending = false;
  let presetPending = false;
  let renderVersion = 0;
  let previewTimer;
  let previewInFlight = false;
  let queuedPreviewVersion = null;
  let toastTimer;
  let polling = false;
  let serverAvailable = false;
  let animationPaused = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let sendRenderId = null;
  let pendingKind = null;
  let rgbDraft = {mode:1,color:'#ffffff',brightness:5,speed:3,multicolor:false,direction:0};
  let rgbInitialized = false;
  let rgbDirty = true;
  let rgbAction = null;
  let rgbJobId = null;
  let jobVersion = 0;
  let hostLink = null;
  let hostPolling = false;
  let hostFailed = false;
  let deviceSettings = null;
  let settingsPending = false;
  let settingsPolling = false;
  let settingsFailed = false;
  let sleepDirty = false;
  let settingsVersion = 0;
  let connections = null;
  let connectionsPolling = false;
  let connectionsPending = null;
  let connectionsFailed = false;
  let connectionsVersion = 0;
  let mediaState = null;
  let mediaPending = false;
  let mediaPolling = false;
  let mediaFailed = false;
  let mediaVersion = 0;

  function isQmk() { return state.device?.firmware === 'qmk' || hostLink?.device?.firmware === 'qmk'; }
  function imageSendAvailable() { return state.capabilities?.screen?.hardware_send_available === true; }
  function imageFrameLimit() { return Number(state.capabilities?.screen?.max_frames) || (isQmk() ? 96 : 140); }
  function imageOverLimit() { return Number(render?.frame_count) > imageFrameLimit(); }

  async function api(path, options = {}) {
    const headers = {...(options.headers || {})};
    if (options.method && options.method !== 'GET') {
      if (!token) throw new Error('Yerel bağlantı henüz hazır değil. Birkaç saniye sonra yeniden deneyin.');
      headers['X-AK820-Token'] = token;
      if (options.body) headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(path, {...options, headers, cache:'no-store'});
    let payload;
    try { payload = await response.json(); } catch { throw new Error('Yerel uygulamadan beklenmeyen yanıt alındı.'); }
    if (!response.ok) throw new Error(payload.error || 'İşlem tamamlanamadı. Lütfen yeniden deneyin.');
    return payload;
  }

  function error(message) {
    $('error-message').textContent = message;
    $('error-notice').hidden = false;
  }

  function clearError() { $('error-notice').hidden = true; }
  function toast(message) {
    clearTimeout(toastTimer);
    $('toast').textContent = message;
    $('toast').hidden = false;
    toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4000);
  }

  function isSending() { return sendPending || mediaPending || state.job?.state === 'sending'; }

  function updateControls() {
    const busy = isSending();
    const qmk = isQmk();
    const imageLocked = !imageSendAvailable();
    $('protocol-notice').hidden = !qmk || (!$('panel-connections').hidden || !$('panel-sources').hidden) || (!$('panel-screen').hidden && imageSendAvailable()) || (!$('panel-lighting').hidden && state.capabilities?.rgb?.hardware_send_available === true);
    $('send-button').disabled = !imageSendAvailable() || !serverAvailable || !state.device?.connected || !render || rendering || importing || busy || imageOverLimit() || mediaPending;
    $('send-button-label').textContent = busy ? 'İşlem sürüyor…' : state.job?.kind !== 'rgb' && state.job?.state === 'sent' && sendRenderId === render?.render_id ? 'Yeniden gönder' : 'Klavyeye gönder';
    $('dropzone').disabled = imageLocked || busy || importing;
    $('file-input').disabled = imageLocked || busy || importing;
    $('settings-fieldset').disabled = imageLocked || busy || importing;
    $('reset-settings').disabled = imageLocked || busy || importing;
    $('load-preset').disabled = imageLocked || !$('preset-select').value || busy || importing;
    $('preset-select').disabled = imageLocked || busy || importing;
    $('save-preset').disabled = imageLocked || !serverAvailable || importing || busy || presetPending;
    $('animation-toggle').disabled = imageLocked || rendering || importing;
    $('screen-stage').classList.toggle('unavailable-preview', imageLocked);
    if (imageLocked) $('preview-caption').textContent = 'Yerel görsel alanı · klavye ekranından okunmadı';
    $('transfer-progress').hidden = !busy;
    $('job-progress').value = Number(state.job?.progress) || 0;
    $('progress-label').textContent = `${Math.round((Number(state.job?.progress) || 0) * 100)}%`;
    $('preview-loading').hidden = !rendering && !importing;
    $('render-chip').classList.toggle('pending', rendering || importing || !render);
    $('render-chip').textContent = importing ? 'Yükleniyor' : rendering ? 'Hazırlanıyor' : render ? 'Önizleme hazır' : 'Önizleme yok';
    if (imageLocked) $('render-chip').textContent = qmk ? 'QMK aktarımı yok' : 'Aktarım kullanılamıyor';
    document.querySelector('#panel-screen .page-description').textContent = imageLocked ? 'Görsel ve GIF aktarımı için desteklenen firmware bağlantısı gerekli.' : 'Bir görsel seçin, kendinize göre ayarlayın, klavyenize gönderin.';
    document.querySelector('#panel-screen .firmware-note p').textContent = imageLocked ? 'Bu görsel alanı klavyeden okunan canlı bir görüntü değildir. Desteklenmeyen firmware için aktarım araçları kapalıdır.' : qmk ? 'Gönderim doğrulandıktan sonra görsel gösterilir. Fn + Del ile görsel ve canlı ekran arasında geçiş yapabilirsiniz. Menü açıldığında öncelik menüdedir; çıkınca görsel geri gelir.' : 'Görsel, klavyenin resim/GIF alanına gönderilir. Yerleşik saat ve ayar sayfaları klavyenin kendi menüsünde kalır.';
    $('image-limits').textContent = qmk && !imageLocked ? `En fazla 12 MB · Gönderim en fazla ${imageFrameLimit()} kare · Her kare en az ${Number(state.capabilities?.screen?.min_frame_ms) || 100} ms. Daha hızlı GIF kareleri gönderimde yavaşlatılır.` : 'En fazla 12 MB · GIF için 140 kare · Görselleriniz bu Mac’te kalır.';
    document.querySelector('#panel-lighting .page-description').textContent = qmk ? 'Stock sürücü kataloğu ve yerel renk önizlemesi. QMK’ye komut gönderimi kapalı.' : 'Resmî efektinizi seçin, ışığı ayarlayın ve USB üzerinden uygulayın.';
    document.querySelector('#panel-lighting .page-heading .neutral-badge').textContent = qmk ? 'Yalnızca önizleme' : 'USB aydınlatma kontrolü';
    document.querySelector('.rgb-catalog-heading p').textContent = qmk ? 'Stock firmware kataloğu. Değişiklikler yalnızca yerel taslaktır.' : 'Değişiklikler yalnızca Uygula ile gönderilir.';
    document.querySelector('.rgb-actions > p').textContent = qmk ? 'Bu stock işlem düğmeleri QMK üzerinde kullanılamaz.' : 'Son yerel seçimle açılır; cihaz ayarı okunmaz. Bu düğmeler yalnızca aydınlatmayı kontrol eder.';
    document.querySelector('.rgb-source-note p').textContent = qmk ? 'Bu katalog resmî stock sürücünün modlarını gösterir. QMK LED davranışının veya mevcut klavye ayarlarının karşılığı değildir.' : 'USB komutları resmî sürücünün kodundan çıkarıldı. Komut yanıtı, LED’lerin istenen görünümde olduğunu tek başına doğrulamaz; uyguladıktan sonra klavyeyi kontrol edin.';
    let title, description;
    if (!serverAvailable) { title = 'Yerel uygulamaya bağlanılamıyor'; description = 'Uygulamanın çalıştığından emin olun.'; }
    else if (qmk && imageLocked) { title = 'QMK için görsel aktarımı hazır değil'; description = 'Görsel/GIF araçları kapalı. Klavyenin kendi menüsü kullanılabilir.'; }
    else if (busy) { title = (pendingKind || state.job?.kind) === 'rgb' ? 'Aydınlatma komutu gönderiliyor' : 'Görsel klavyeye aktarılıyor'; description = state.job?.message || 'Tamamlanana kadar USB bağlantısını koruyun.'; }
    else if (importing) { title = 'Görsel açılıyor'; description = 'Kareler ve ekran önizlemesi hazırlanıyor.'; }
    else if (rendering) { title = 'Önizleme güncelleniyor'; description = 'Ayarlarınız hazırlanıyor; klavyeye henüz gönderilmedi.'; }
    else if (state.job?.state === 'error' && state.job?.kind !== 'rgb') { title = 'Aktarım tamamlanamadı'; description = state.job.message || 'Bağlantıyı kontrol edip yeniden deneyin.'; }
    else if (state.job?.kind !== 'rgb' && state.job?.state === 'sent' && sendRenderId === render?.render_id) { title = state.device?.simulated ? 'Test aktarımı tamamlandı' : 'Aktarım tamamlandı'; description = state.device?.simulated ? 'Bu testte fiziksel klavyeye yazılmadı.' : 'Cihaz yanıtı alındı · ekranı klavyeden kontrol edin.'; }
    else if (!state.device?.connected) { title = 'Klavyeyi USB ile bağlayın'; description = 'Önizlemeyi düzenleyebilirsiniz. Göndermek için USB bağlantısı gerekir.'; }
    else if (!render) { title = 'Önizleme hazırlanamadı'; description = 'Görseli veya ayarları değiştirerek yeniden deneyin.'; }
    else if (imageOverLimit()) { title = `Görsel ${imageFrameLimit()} kare sınırını aşıyor`; description = 'Daha kısa bir GIF seçin. Bu görsel klavyeye gönderilemez.'; }
    else if (!imageSendAvailable()) { title = 'Görsel aktarımı kullanılamıyor'; description = 'Bu firmware için gönderim desteği doğrulanmadı.'; }
    else { title = 'Görseliniz gönderilmeye hazır'; description = 'Yalnızca Gönder’e bastığınızda klavyeniz güncellenir.'; }
    $('send-status-title').textContent = title;
    $('send-status-description').textContent = description;
    updateRgbState();
    displayMediaState();
  }

  function displayMediaState() {
    const available = isQmk() && imageSendAvailable() && mediaState?.available === true;
    $('media-display-controls').hidden = !available;
    const count = Number(mediaState?.frame_count) || 0;
    const busy = mediaPending || mediaState?.uploading === true || isSending();
    $('media-display-state').textContent = mediaFailed ? 'Klavye görünümü doğrulanamadı. Bağlantı yeniden kontrol edilecek.' : busy ? 'Ekran işlemi sürüyor…' : count === 0 ? 'Klavyede kullanılabilir bir görsel yok.' : `${mediaState?.show ? 'Görsel alanı etkin' : 'Canlı ekran etkin'} · ${count} kare. Menü açıksa menü gösterilir.`;
    $('media-show').disabled = !available || mediaFailed || !token || busy || count === 0 || mediaState?.show === true;
    $('media-hide').disabled = !available || mediaFailed || !token || busy || mediaState?.show !== true;
  }

  async function refreshMediaState() {
    if (mediaPolling || mediaPending) return;
    if (!isQmk() || !imageSendAvailable()) {mediaState = null; displayMediaState(); return;}
    mediaPolling = true;
    const version = mediaVersion;
    try {const next = await api('/api/media/state',{signal:AbortSignal.timeout(6000)}); if (version === mediaVersion) {mediaState = next;mediaFailed = false;}}
    catch {if (version === mediaVersion) mediaFailed = true;}
    finally {mediaPolling = false;displayMediaState();}
  }

  async function setMediaDisplay(show) {
    if ($(show ? 'media-show' : 'media-hide').disabled) return;
    mediaVersion++;
    mediaPending = true;
    const result = $('media-display-result');
    result.hidden = false;result.classList.remove('is-error');result.textContent = 'Klavye onayı bekleniyor…';
    updateControls();
    try {
      const next = await api('/api/media/display',{method:'POST',body:JSON.stringify({show}),signal:AbortSignal.timeout(6000)});
      if (next?.available !== true || next.show !== show) throw new Error('Klavye görünümü doğrulanamadı. Son durum yeniden okunacak.');
      mediaState = next;mediaFailed = false;
      result.textContent = show ? 'Görsel alanı etkinleştirildi.' : 'Canlı ekrana dönüş onaylandı.';
    } catch (err) {result.textContent = err.message;result.classList.add('is-error');mediaFailed = true;}
    finally {mediaPending = false;updateControls();}
  }

  function displayState() {
    const connected = serverAvailable && state.device?.connected;
    $('device-status').classList.toggle('connected', Boolean(connected));
    $('device-status').classList.toggle('disconnected', !connected);
    $('device-label').textContent = !serverAvailable ? 'Servis kapalı' : state.device?.simulated ? 'TEST · USB’ye yazılmaz' : connected ? isQmk() ? 'AK820 · QMK' : 'AK820 bağlı' : 'Klavye bağlı değil';
    document.querySelector('.status-port').textContent = state.device?.simulated ? connected ? 'BAĞLI' : 'BAĞLI DEĞİL' : 'USB';
    $('device-status').title = state.device?.message || '';
    updateControls();
    displayDeviceSettings();
    displayConnections();
  }

  function displayConnections() {
    const labels = {disconnected:'Bağlantı kapalı',connecting:'Bağlanıyor',available:'Veri alındı',waiting:'Veri bekleniyor',stale:'Eski veri',error:'Bağlantı hatası'};
    const feedback = $('connections-feedback');
    feedback.classList.toggle('is-error', connectionsFailed);
    feedback.textContent = connectionsFailed ? 'Bağlantı durumu alınamadı. Son bilinen bilgiler gösteriliyor; Yenile ile yeniden deneyin.' : connections ? 'Bağlantı durumu bu Mac’teki uygulamalardan okunur.' : 'Bağlantılar okunuyor.';
    for (const name of ['codex','claude_code']) {
      const provider = connections?.providers?.[name];
      const prefix = `connection-${name}-`;
      const badge = $(prefix+'status');
      badge.textContent = connectionsFailed ? 'Doğrulanamadı' : labels[provider?.state] || 'Bekleniyor';
      badge.classList.toggle('is-stale', connectionsFailed || ['stale','error'].includes(provider?.state));
      $(prefix+'message').textContent = provider?.message || 'Bu kaynaktan henüz bağlantı bilgisi alınmadı.';
      $(prefix+'forwarding').textContent = provider?.enabled === true ? 'Açık' : provider?.enabled === false ? 'Kapalı' : 'Bilinmiyor';
      const observed = readableTime(provider?.observed_at);
      $(prefix+'time').textContent = observed || 'Henüz veri alınmadı';
      const setupNote = provider?.setup?.user_action;
      $(prefix+'setup-note').textContent = typeof setupNote === 'string' ? setupNote : '';
      $(prefix+'setup-note').hidden = !setupNote;
      for (const action of ['connect','disconnect','refresh','setup']) {
        const button = $(prefix+action);
        const allowed = provider?.actions?.[action] === true;
        button.hidden = action === 'disconnect' ? !allowed && provider?.enabled !== true : action === 'connect' ? !allowed && provider?.enabled === true : action === 'setup' ? !allowed : false;
        button.disabled = !token || Boolean(connectionsPending) || (action !== 'refresh' && connectionsFailed) || !allowed;
        // A read failure can always be retried without assuming a provider action is available.
        if (action === 'refresh' && connectionsFailed) button.disabled = Boolean(connectionsPending) || connectionsPolling;
        button.setAttribute('aria-label', `${name === 'codex' ? 'Codex' : 'Claude Code'}: ${action === 'connect' ? 'Bağla' : action === 'disconnect' ? 'Bağlantıyı kes' : action === 'refresh' ? 'Yenile' : 'Kurulumu tamamla'}`);
        button.setAttribute('aria-busy', String(connectionsPending?.name === name && connectionsPending?.action === action));
      }
    }
  }

  function acceptConnections(next) {
    if (!next?.providers || !next.providers.codex || !next.providers.claude_code) throw new Error('Bağlantı yanıtı eksik. Yeniden deneyin.');
    connections = next;
    connectionsFailed = false;
  }

  async function refreshConnections() {
    if (connectionsPolling || connectionsPending) return;
    connectionsPolling = true;
    const version = connectionsVersion;
    try { const next = await api('/api/connections',{signal:AbortSignal.timeout(12000)}); if (version === connectionsVersion) acceptConnections(next); }
    catch { if (version === connectionsVersion) connectionsFailed = true; }
    finally { connectionsPolling = false; displayConnections(); }
  }

  async function connectionAction(name, action) {
    if (connectionsPending) return;
    if (action === 'refresh' && connectionsFailed) { await refreshConnections(); return; }
    if (!token || connections?.providers?.[name]?.actions?.[action] !== true) return;
    connectionsVersion++;
    connectionsPending = {name,action};
    const result = $(`connection-${name}-result`);
    result.hidden = false;
    result.classList.remove('is-error');
    result.textContent = ({connect:'Bağlantı hazırlanıyor…',disconnect:'Studio’ya aktarım durduruluyor…',refresh:'Yeni veri kontrol ediliyor…',setup:'Yerel bağlantı kurulumu hazırlanıyor…'})[action];
    displayConnections();
    try {
      acceptConnections(await api(`/api/connections/${name}/${action}`,{method:'POST',body:'{}',signal:AbortSignal.timeout(30000)}));
      result.textContent = 'İşlem yanıtı alındı. Güncel durum yukarıda gösteriliyor.';
      await refreshHostLink();
    } catch (err) {result.textContent = err.message; result.classList.add('is-error'); connectionsFailed = true;}
    finally {connectionsPending = null; displayConnections();}
  }

  function readableTime(value) {
    if (value === null || value === undefined || value === '') return null;
    const date = new Date(typeof value === 'number' ? value * 1000 : value);
    if (!Number.isFinite(date.getTime())) return null;
    return new Intl.DateTimeFormat('tr-TR', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(date);
  }

  function validPercent(value) { return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100; }

  function showUsage(name, data = {}) {
    data = data || {};
    const hasSnapshot = Boolean(readableTime(data.observed_at)) || ['short','weekly'].some(key => validPercent(data[key]?.remaining_percent));
    const stale = hasSnapshot && (hostFailed || data.stale === true || data.status === 'stale');
    const labels = {available:'Veri alındı',stale:'Eski veri',not_connected:'Bağlı değil',error:'Veri alınamadı'};
    $(`${name}-badge`).textContent = stale ? 'Eski veri' : hostFailed ? 'Veri alınamadı' : labels[data.status] || 'Veri yok';
    $(`${name}-badge`).classList.toggle('is-stale', stale || data.status === 'error');
    $(`${name}-message`).textContent = stale ? 'Son alınan bilgiler gösteriliyor; güncelliği doğrulanamadı.' : data.message || (data.status === 'available' ? 'Hesap limitlerinden alınan kalan kullanım.' : 'Bu kaynaktan kullanılabilir veri alınmadı.');
    for (const window of ['short','weekly']) {
      const value = data[window]?.remaining_percent;
      const available = validPercent(value);
      $(`${name}-${window}-value`).textContent = available ? `%${value.toLocaleString('tr-TR',{maximumFractionDigits:1})}` : 'Veri yok';
      const meter = $(`${name}-${window}-meter`);
      meter.hidden = !available;
      if (available) meter.value = value;
      const reset = readableTime(data[window]?.reset_at);
      $(`${name}-${window}-reset`).textContent = reset ? `Yenilenme: ${reset}` : 'Yenilenme zamanı bilinmiyor';
    }
    $(`${name}-source`).textContent = `Kaynak: ${typeof data.source === 'string' && data.source ? data.source : 'Henüz belirtilmedi'}`;
    const observed = readableTime(data.observed_at);
    $(`${name}-time`).textContent = observed ? `Son alınan: ${observed}` : 'Henüz tarihli veri alınmadı';
  }

  function displayHostLink() {
    const device = hostLink?.device || {};
    const sync = hostLink?.sync || {};
    const stale = Boolean(readableTime(device.observed_at)) && (hostFailed || device.stale === true);
    $('host-feedback').classList.toggle('is-error', hostFailed);
    $('host-feedback').textContent = hostFailed ? 'Durum verisi alınamadı. Yerel bağlantıyı kontrol edip Yenile’yi deneyin.' : 'Bu sayfa cihaz ölçümlerini ve hesaplardan alınan son verileri gösterir.';
    $('host-device-badge').textContent = stale ? 'Eski ölçüm' : device.connected ? 'Bağlı' : 'Bağlı değil';
    $('host-device-badge').classList.toggle('is-stale', stale);
    const links = {usb:'USB',bluetooth:'Bluetooth','2.4ghz':'2,4 GHz','2.4g':'2,4 GHz',wired:'USB'};
    $('host-connection').textContent = links[String(device.connection || '').toLowerCase()] || 'Bilinmiyor';
    $('host-battery').textContent = validPercent(device.battery_percent) ? `%${device.battery_percent.toLocaleString('tr-TR',{maximumFractionDigits:0})}` : 'Ölçüm yok';
    $('host-charging').textContent = device.charging === true ? 'Şarj oluyor' : device.charging === false ? 'Şarj olmuyor' : 'Bilinmiyor';
    $('host-firmware').textContent = ({qmk:'QMK',stock:'Stock'})[device.firmware] || 'Bilinmiyor';
    const observed = readableTime(device.observed_at);
    $('host-device-time').textContent = observed ? `Son ölçüm: ${observed}${stale ? ' · güncel değil' : ''}` : 'Henüz tarihli ölçüm alınmadı.';
    $('host-device-note').textContent = device.message || 'Pil ve bağlantı bilgisi cihazdan alınır. Ölçülemeyen değerler boş bırakılır.';
    showUsage('codex',hostLink?.codex);
    showUsage('claude',hostLink?.claude);
    $('host-sync-title').textContent = hostFailed ? 'Bağlantı durumu güncellenemedi' : ({connected:'Klavye veri bağlantısı açık',disconnected:'Klavye veri bağlantısı kapalı',unsupported:'Bu firmware için veri bağlantısı yok',error:'Klavye veri bağlantısı hatası'})[sync.state] || 'Klavye veri bağlantısı bekleniyor';
    $('host-sync-description').textContent = sync.message || 'Bu sayfa alınan verileri gösterir; klavye ekranının canlı görüntüsü değildir.';
    const success = readableTime(sync.last_success_at);
    $('host-sync-time').textContent = success ? `Son başarılı bağlantı: ${success}` : 'Henüz başarılı bağlantı kaydı yok.';
    updateControls();
  }

  function displayDeviceSettings() {
    const available = deviceSettings?.available === true && !settingsFailed;
    $('host-settings-controls').hidden = !available;
    $('host-settings-controls').disabled = !available || settingsPending || !token;
    $('host-settings-note').textContent = settingsFailed ? 'Ekran ayarları okunamadı. Bağlantı yeniden denenecek.' : available ? deviceSettings.message || 'Bu ayarlar klavye yeniden başlayana kadar geçerlidir.' : 'Bu ayarlar için klavye veri bağlantısı bekleniyor.';
    const screenKnown = typeof deviceSettings?.screen_on === 'boolean';
    $('host-screen-current').textContent = screenKnown ? deviceSettings.screen_on ? 'Açık' : 'Kapalı' : 'Durum bilinmiyor';
    $('host-screen-toggle').textContent = screenKnown ? deviceSettings.screen_on ? 'Ekranı kapat' : 'Ekranı aç' : 'Durum bilinmiyor';
    $('host-screen-toggle').disabled = !available || !screenKnown || settingsPending || !token;
    const select = $('host-sleep-select');
    const choices = Array.isArray(deviceSettings?.sleep_choices) ? deviceSettings.sleep_choices.filter(n => Number.isInteger(n) && n >= 0) : [];
    const currentSleep = deviceSettings?.sleep_minutes;
    const currentKnown = Number.isInteger(currentSleep) && currentSleep >= 0;
    const signature = JSON.stringify([choices,currentSleep]);
    if (select.dataset.choices !== signature) {
      const draft = select.value;
      select.dataset.choices = signature;
      select.replaceChildren(new Option('Süre seçin',''));
      for (const n of choices) select.add(new Option(n === 0 ? 'Hiçbir zaman' : `${n} dakika`,String(n)));
      if (currentKnown && !choices.includes(currentSleep)) {
        const measured = new Option(`${currentSleep} dakika · mevcut`,String(currentSleep));
        measured.disabled = true; select.add(measured);
      }
      if (sleepDirty && choices.includes(Number(draft))) select.value = draft;
    }
    if (!sleepDirty) select.value = currentKnown ? String(currentSleep) : '';
    $('host-sleep-apply').disabled = !available || !token || settingsPending || !sleepDirty || select.value === '' || !choices.includes(Number(select.value));
  }

  async function refreshDeviceSettings() {
    if (settingsPolling || settingsPending) return;
    settingsPolling = true;
    const version = settingsVersion;
    try { const next = await api('/api/settings',{signal:AbortSignal.timeout(6000)}); if (version === settingsVersion) {deviceSettings = next; settingsFailed = false;} }
    catch { if (version === settingsVersion) settingsFailed = true; }
    finally { settingsPolling = false; displayDeviceSettings(); }
  }

  async function applyDeviceSettings(change) {
    if (settingsPending || settingsFailed || deviceSettings?.available !== true || !token) return;
    settingsVersion++;
    settingsPending = true;
    const result = $('host-settings-result');
    result.hidden = false; result.classList.remove('is-error'); result.textContent = 'Klavye onayı bekleniyor…';
    displayDeviceSettings();
    try {
      deviceSettings = await api('/api/settings',{method:'POST',body:JSON.stringify(change),signal:AbortSignal.timeout(6000)});
      if (deviceSettings?.available !== true || !Object.entries(change).every(([key,value]) => deviceSettings[key] === value)) throw new Error('İstenen ayarın uygulandığı doğrulanamadı. Yenile ile cihaz durumunu kontrol edin.');
      settingsFailed = false;
      if ('sleep_minutes' in change) sleepDirty = false;
      result.textContent = 'Klavye ayarı onayladı. Değişiklik bu oturum için geçerli.';
    } catch (err) { result.textContent = err.message; result.classList.add('is-error'); }
    finally { settingsPending = false; displayDeviceSettings(); }
  }

  async function refreshHostLink() {
    if (hostPolling) return;
    hostPolling = true;
    $('refresh-host-link').disabled = true;
    $('refresh-host-link').setAttribute('aria-busy','true');
    try {
      const next = await api('/api/host-link',{signal:AbortSignal.timeout(6000)});
      if (!next || typeof next.device !== 'object' || typeof next.sync !== 'object') throw new Error('Durum yanıtı eksik.');
      hostLink = next;
      hostFailed = false;
    } catch { hostFailed = true; }
    finally {
      hostPolling = false;
      $('refresh-host-link').disabled = false;
      $('refresh-host-link').removeAttribute('aria-busy');
      displayHostLink();
    }
  }

  function populatePresets(presets = []) {
    const select = $('preset-select');
    const selected = select.value;
    const signature = JSON.stringify(presets.map(p => [p.id,p.name]));
    if (select.dataset.signature === signature) return;
    select.dataset.signature = signature;
    select.replaceChildren(new Option(presets.length ? 'Kayıtlı önayar seçin' : 'Henüz kayıtlı önayar yok', ''));
    for (const preset of presets) select.add(new Option(preset.name, preset.id));
    if ([...select.options].some(option => option.value === selected)) select.value = selected;
  }

  async function refreshState() {
    if (polling) return;
    polling = true;
    const readJobVersion = jobVersion;
    const wasImageAvailable = imageSendAvailable();
    try {
      const next = await api('/api/state');
      if (next.token === token && readJobVersion !== jobVersion) next.job = state.job;
      state = next;
      if (next.token) token = next.token;
      serverAvailable = true;
      if (!rgbInitialized && next.rgb) {
        if (next.rgb.last_settings) {rgbDraft = {...rgbDraft,...next.rgb.last_settings}; rgbDirty = false;}
        rgbInitialized = true;
        $('rgb-mode-select').value = String(rgbDraft.mode);
        showRgbMode();
      }
      populatePresets(next.presets || []);
      if (!wasImageAvailable && imageSendAvailable()) {schedulePreview(true);refreshMediaState();}
    } catch {
      serverAvailable = false;
    } finally {
      polling = false;
      displayState();
    }
  }

  function syncSettingsUI() {
    for (const key of ['fit','zoom','x','y','brightness','contrast','saturation','rotation','background','title','subtitle']) {
      const id = key === 'fit' ? 'fit-select' : `${key}-input`;
      $(id).value = settings[key];
    }
    $('accent-input').value = settings.color;
    for (const button of document.querySelectorAll('[data-layout]')) {
      const active = button.dataset.layout === settings.layout;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    }
    for (const button of document.querySelectorAll('[data-effect]')) {
      const active = button.dataset.effect === settings.effect;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    }
    $('template-settings').hidden = settings.layout === 'image';
    $('zoom-output').textContent = `${Number(settings.zoom).toFixed(2)}×`;
    for (const key of ['x','y']) $(`${key}-output`).textContent = String(Math.round(settings[key] * 100));
    for (const key of ['brightness','contrast','saturation']) $(`${key}-output`).textContent = `${Math.round(settings[key] * 100)}%`;
  }

  function updateAnimation() {
    if (!render) return;
    const animated = render.frame_count > 1;
    $('animation-toggle').hidden = !animated;
    $('animation-toggle').setAttribute('aria-label', animationPaused ? 'Animasyonu oynat' : 'Animasyonu duraklat');
    $('animation-toggle').querySelector('use').setAttribute('href', animationPaused ? '#i-play' : '#i-pause');
    $('screen-preview').src = animationPaused && render.still_url ? render.still_url : render.preview_url;
    $('preview-caption').textContent = imageOverLimit() ? 'Yerel önizleme · kare sınırı nedeniyle gönderilemez' : animated ? animationPaused ? 'Animasyon duraklatıldı · gönderim tüm kareleri içerir' : 'Animasyon önizlemesi · tüm kareler gönderilir' : 'Klavyeye gönderilecek 128 × 128 görüntü';
  }

  async function buildPreview(version) {
    if (!imageSendAvailable()) { rendering = false; updateControls(); return; }
    if (version !== renderVersion) return;
    if (previewInFlight) { queuedPreviewVersion = version; return; }
    previewInFlight = true;
    try {
      const result = await api('/api/preview', {method:'POST', body:JSON.stringify({asset_id:assetId, settings:{...settings}})});
      if (version !== renderVersion) return;
      render = result;
      $('frame-label').textContent = `${result.frame_count} kare${result.frame_count > 1 ? ` · ${(result.duration_ms / 1000).toLocaleString('tr-TR',{maximumFractionDigits:1})} sn` : ''}`;
      $('size-label').textContent = `${Math.round(result.bytes / 1024)} KB`;
      const notes = [...(result.warnings || [])];
      if (imageOverLimit()) notes.unshift(`Bu GIF ${result.frame_count} kare. Gönderim sınırı ${imageFrameLimit()} kare; daha kısa bir GIF seçin.`);
      else if (result.frame_count > 1 && !state.capabilities?.screen?.physical_animation_verified) notes.unshift('GIF önizlemesi hazır; bu klavyede animasyon oynatımı henüz doğrulanmadı.');
      $('preview-note').textContent = notes.join(' ');
      $('preview-note').hidden = notes.length === 0;
      updateAnimation();
      // Keep Send disabled until the exact new preview is decoded and displayed.
      try { await $('screen-preview').decode(); }
      catch { throw new Error('Önizleme görüntüsü yüklenemedi. Görseli veya ayarları değiştirerek yeniden deneyin.'); }
      if (version !== renderVersion) return;
    } catch (err) {
      if (version !== renderVersion) return;
      render = null;
      error(err.message);
    } finally {
      previewInFlight = false;
      if (version === renderVersion) {
        rendering = false;
        updateControls();
      }
      if (queuedPreviewVersion !== null) {
        const queued = queuedPreviewVersion;
        queuedPreviewVersion = null;
        if (queued === renderVersion) buildPreview(queued);
      }
    }
  }

  function schedulePreview(immediate = false) {
    clearTimeout(previewTimer);
    if (!imageSendAvailable()) { rendering = false; updateControls(); return; }
    const version = ++renderVersion;
    rendering = true;
    updateControls();
    previewTimer = setTimeout(() => buildPreview(version), immediate ? 0 : 180);
  }

  async function importFile(file) {
    if (!imageSendAvailable() || !file || isSending() || importing) return;
    if (!/\.(png|jpe?g|webp|gif)$/i.test(file.name)) { error('PNG, JPG, WebP veya GIF biçiminde bir görsel seçin.'); return; }
    if (file.size > 12 * 1024 * 1024) { error('Lütfen 12 MB veya daha küçük bir görsel seçin.'); return; }
    clearError();
    importing = true;
    renderVersion++;
    clearTimeout(previewTimer);
    updateControls();
    try {
      const data = await new Promise((resolve,reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(',')[1]);
        reader.onerror = () => reject(new Error('Görsel okunamadı. Dosyayı yeniden seçin.'));
        reader.readAsDataURL(file);
      });
      const asset = await api('/api/import', {method:'POST',body:JSON.stringify({name:file.name,data})});
      assetId = asset.asset_id;
      assetName = asset.name;
      settings.zoom = 1; settings.x = 0; settings.y = 0;
      syncSettingsUI();
      $('asset-name').textContent = asset.name;
      $('asset-details').textContent = `${asset.width} × ${asset.height} px · ${asset.frame_count} kare · değiştirmek için seçin`;
      $('preset-select').value = '';
      schedulePreview(true);
    } catch (err) {
      error(err.message);
      if (!render) rendering = false;
      else { rendering = false; updateAnimation(); }
    } finally {
      importing = false;
      $('file-input').value = '';
      updateControls();
    }
  }

  async function sendImage() {
    if ($('send-button').disabled || !render || isSending()) return;
    clearError();
    jobVersion++;
    sendPending = true;
    pendingKind = 'image';
    sendRenderId = render.render_id;
    updateControls();
    try {
      const job = await api('/api/send', {method:'POST',body:JSON.stringify({render_id:render.render_id})});
      state.job = job;
    } catch (err) {
      error(err.message);
      state.job = {state:'error',message:err.message,progress:0};
    } finally {
      jobVersion++;
      sendPending = false;
      pendingKind = null;
      updateControls();
    }
  }

  function switchPanel(panel, updateHash = true) {
    const panels = {screen:['Ekran','ekran'],lighting:['Aydınlatma','aydinlatma'],connections:['Durum','durum'],sources:['Bağlantılar','baglantilar']};
    if (!panels[panel]) panel = 'screen';
    for (const button of document.querySelectorAll('[data-panel]')) {
      const active = button.dataset.panel === panel;
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current');
    }
    for (const name of Object.keys(panels)) $(`panel-${name}`).hidden = name !== panel;
    $('sendbar').hidden = panel !== 'screen';
    $('breadcrumb-page').textContent = panels[panel][0];
    if (updateHash) history.replaceState(null,'',`#${panels[panel][1]}`);
    updateControls();
    if (panel === 'sources') refreshConnections();
  }

  $('file-input').addEventListener('change', event => importFile(event.target.files[0]));
  $('dropzone').addEventListener('click', () => $('file-input').click());
  for (const event of ['dragenter','dragover']) $('dropzone').addEventListener(event, e => {e.preventDefault(); if (!isSending()) $('dropzone').classList.add('dragover');});
  for (const event of ['dragleave','drop']) $('dropzone').addEventListener(event, e => {e.preventDefault(); $('dropzone').classList.remove('dragover');});
  $('dropzone').addEventListener('drop', event => importFile(event.dataTransfer.files[0]));
  window.addEventListener('dragover', event => {if ([...(event.dataTransfer?.types || [])].includes('Files')) event.preventDefault();});
  window.addEventListener('drop', event => {if ([...(event.dataTransfer?.types || [])].includes('Files')) event.preventDefault();});
  $('dismiss-error').addEventListener('click', clearError);
  $('send-button').addEventListener('click', sendImage);
  $('animation-toggle').addEventListener('click', () => {animationPaused = !animationPaused; updateAnimation();});
  $('reset-settings').addEventListener('click', () => {settings = {...defaults}; syncSettingsUI(); clearError(); schedulePreview(true);});
  for (const key of ['fit','zoom','x','y','brightness','contrast','saturation','rotation','background','title','subtitle','color']) {
    const element = $(key === 'fit' ? 'fit-select' : key === 'color' ? 'accent-input' : `${key}-input`);
    element.addEventListener('input', () => {
      settings[key] = ['zoom','x','y','brightness','contrast','saturation','rotation'].includes(key) ? Number(element.value) : element.value;
      syncSettingsUI(); schedulePreview();
    });
  }
  for (const button of document.querySelectorAll('[data-layout]')) button.addEventListener('click', () => { settings.layout = button.dataset.layout; syncSettingsUI(); schedulePreview(); });
  for (const button of document.querySelectorAll('[data-effect]')) button.addEventListener('click', () => { settings.effect = button.dataset.effect; syncSettingsUI(); schedulePreview(); });
  for (const button of document.querySelectorAll('[data-panel]')) button.addEventListener('click', () => switchPanel(button.dataset.panel));
  window.addEventListener('hashchange', () => switchPanel(({ekran:'screen',aydinlatma:'lighting',baglantilar:'sources',durum:'connections'})[location.hash.slice(1)] || 'connections', false));
  const keys = ['esc','1','2','3','4','5','6','7','8','9','0','−','⌫','tab','Q','W','E','R','T','Y','U','I','O','P','[',']','⇧','A','S','D','F','G','H','J','K','L',';','↵','↑','ctrl','alt','⌘','space','⌘','alt','←','↓','→'];
  for (const key of keys) { const item = document.createElement('i'); item.textContent = key === 'space' ? '' : key; if (key === 'space') item.className = 'space'; $('rgb-preview').append(item); }

  // Mode metadata extracted from the official driver; writes use guarded backend endpoints.
  const RGB_CATALOG = {"schema_version":1,"mode":"explicit_apply","hardware_verified":false,"hardware_send_available":true,"status_label":"Kaynakta doğrulandı · cihazda denenmedi","preview_note":"Görsel temsil; efektin klavye LED’lerindeki davranışı birebir doğrulanmadı.","software_defaults":{"mode":11,"brightness":5,"speed":3,"note":"Sürücü varsayılanlarıdır; cihazdan okunmuş mevcut ayarlar değildir."},"controls":{"brightness":{"name":"Parlaklık","mask":"01","range":{"min":1,"max":5,"step":1},"software_default":5,"note":"Resmî arayüz ve slider sınıfında 1–5 aralığı doğrulandı."},"speed":{"name":"Hız","mask":"02","range":{"min":1,"max":5,"step":1},"software_default":3,"note":"Resmî arayüz ve slider sınıfında 1–5 aralığı doğrulandı."},"direction_a":{"name":"Yön seçimi A","mask":"04","values":[{"value":0,"name":"Sol"},{"value":1,"name":"Sağ"}],"note":"Resmî yön düğmeleri: Sol 0, Sağ 1."},"direction_b":{"name":"Yön seçimi B","mask":"08","values":[{"value":2,"name":"Yukarı"},{"value":3,"name":"Aşağı"}],"note":"Resmî yön düğmeleri: Yukarı 2, Aşağı 3."},"color":{"name":"Özel renk","mask":"10","note":"Resmî arayüzde özel RGB renk alanları etkin."},"multicolor":{"name":"Palet / çok renkli","mask":"20","values":[{"value":false,"name":"Tek renk"},{"value":true,"name":"Çok renkli"}],"note":"Resmî seçim: kapalı 0, açık 1."}},"modes":[{"id":0,"name":"Kapalı","official_name":"LED Off","capability_mask":"00","controls":[]},{"id":1,"name":"Sabit","official_name":"Static","capability_mask":"31","controls":["brightness","color","multicolor"]},{"id":2,"name":"Tekli yanma","official_name":"SingleOn","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":3,"name":"Tekli sönme","official_name":"SingleOff","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":4,"name":"Parıltı","official_name":"Glittering","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":5,"name":"Düşüş","official_name":"Falling","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":6,"name":"Çok renkli","official_name":"Colourful","capability_mask":"03","controls":["brightness","speed"]},{"id":7,"name":"Nefes","official_name":"Breath","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":8,"name":"Spektrum","official_name":"Spectrum","capability_mask":"03","controls":["brightness","speed"]},{"id":9,"name":"Dışa yayılma","official_name":"Outward","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":10,"name":"Kayma","official_name":"Scrolling","capability_mask":"3B","controls":["brightness","speed","direction_b","color","multicolor"]},{"id":11,"name":"Yuvarlanma","official_name":"Rolling","capability_mask":"37","controls":["brightness","speed","direction_a","color","multicolor"]},{"id":12,"name":"Dönme","official_name":"Rotating","capability_mask":"37","controls":["brightness","speed","direction_a","color","multicolor"]},{"id":13,"name":"Patlama","official_name":"Explode","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":14,"name":"Fırlatma","official_name":"Launch","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":15,"name":"Dalgacıklar","official_name":"Ripples","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":16,"name":"Akış","official_name":"Flowing","capability_mask":"37","controls":["brightness","speed","direction_a","color","multicolor"]},{"id":17,"name":"Nabız","official_name":"Pulsating","capability_mask":"33","controls":["brightness","speed","color","multicolor"]},{"id":18,"name":"Eğim","official_name":"Tilt","capability_mask":"37","controls":["brightness","speed","direction_a","color","multicolor"]},{"id":19,"name":"Mekik","official_name":"Shuttle","capability_mask":"33","controls":["brightness","speed","color","multicolor"]}],"provenance":{"local_report":"work/rgb-provenance.txt","official_driver_url":"https://ajazzstore.com/blogs/software/ajazz-ak820-pro-driver","device_driver_sha256":"14b6919b59b86f6bd1465e544032b41ca4f12ca35e36bd81d3ab33aca14a605a","mode_initializer":"DeviceDriver.exe 0x42B3B0–0x42B7A1; evidence/driver-text.asm:56245","control_masks":"DeviceDriver.exe 0x42AB40; brightness 0x42ABC4, speed 0x42AC07, direction_a 0x42AC47, direction_b 0x42ACA1, color 0x42AD89, multicolor 0x42AD21","official_names":"extracted/app/language/1033.lan localization keys 521–539 for mode1–19; 540 for mode0","ranges_defaults":"extracted/app/layouts/rgb-keyboard.xml:9","translation_note":"Türkçe adlar arayüz çevirisidir; efekt animasyon algoritmasının doğrulaması değildir.","verified_ranges":"UI0x438155–0x438177,0x43825C–0x438284; mui.dll SetMinProgress0x100872B0,SetMaxProgress0x10087290","verified_directions":"UI0x43833D–0x43844F icon addresses; event0x42C68A–0x42C6C2 maps IDs5B/5C/5D/5E to1/0/2/3","verified_multicolor":"GetCheck0x42B8C7 normalized0/1 at0x42B8CD–0x42B8D3"}};
  let rgbCatalog = null;
  const rgbControlLabels = {brightness:'Parlaklık',speed:'Hız',color:'Özel RGB rengi',multicolor:'Çok renkli',direction_a:'Yön',direction_b:'Yön'};
  function rgbMode() { return rgbCatalog?.modes.find(mode => mode.id === Number(rgbDraft.mode)); }
  function updateRgbPreview() {
    $('rgb-preview').style.setProperty('--rgb',rgbDraft.color);
    $('rgb-color-dot').style.background = rgbDraft.color;
    $('rgb-preview-color-label').textContent = `${rgbDraft.color.toUpperCase()} · renk önizlemesi`;
  }
  function editRgb(field, value) {
    rgbDraft[field] = value;
    rgbDirty = true;
    $('rgb-catalog-error').hidden = true;
    updateRgbPreview();
    updateRgbState();
  }
  function showRgbMode() {
    if (!rgbCatalog) return;
    const selected = rgbMode();
    if (!selected) return;
    $('rgb-mode-select').value = String(selected.id);
    $('rgb-mode-number').textContent = `MOD ${String(selected.id).padStart(2,'0')}`;
    $('rgb-mode-subtitle').textContent = `Resmî ad: ${selected.official_name || selected.name}`;
    $('rgb-mode-controls').replaceChildren();
    for (const control of selected.controls) {
      const definition = rgbCatalog.controls[control] || {};
      const row = document.createElement('div');
      row.className = 'rgb-edit-row';
      const term = document.createElement('dt');
      const label = document.createElement('label');
      const value = document.createElement('dd');
      label.textContent = rgbControlLabels[control] || definition.name || control;
      const field = control.startsWith('direction_') ? 'direction' : control;
      const input = document.createElement(control.startsWith('direction_') ? 'select' : 'input');
      input.id = `rgb-setting-${field}`;
      label.htmlFor = input.id;
      if (control === 'brightness' || control === 'speed') {
        input.type = 'range'; input.min = definition.range.min; input.max = definition.range.max; input.step = definition.range.step; input.value = rgbDraft[field];
        const output = document.createElement('output');
        output.htmlFor = input.id; output.textContent = `${rgbDraft[field]} / 5`;
        input.addEventListener('input', () => {editRgb(field,Number(input.value)); output.textContent = `${input.value} / 5`;});
        value.append(input,output);
      } else if (control === 'color') {
        input.type = 'color'; input.value = rgbDraft.color;
        const output = document.createElement('output'); output.htmlFor = input.id; output.textContent = rgbDraft.color.toUpperCase();
        input.addEventListener('input', () => {editRgb(field,input.value); output.textContent = input.value.toUpperCase();});
        value.append(input,output);
      } else if (control === 'multicolor') {
        input.type = 'checkbox'; input.checked = rgbDraft.multicolor;
        const output = document.createElement('span'); output.textContent = input.checked ? 'Açık' : 'Kapalı';
        input.addEventListener('change', () => {editRgb(field,input.checked); output.textContent = input.checked ? 'Açık' : 'Kapalı';});
        value.append(input,output);
      } else {
        const directions = definition.values.map(option => [option.value,option.name]);
        if (!directions.some(([id]) => id === Number(rgbDraft.direction))) rgbDraft.direction = directions[0][0];
        for (const [id,name] of directions) input.add(new Option(name,id));
        input.value = String(rgbDraft.direction);
        input.addEventListener('change', () => editRgb(field,Number(input.value)));
        value.append(input);
      }
      term.append(label); row.append(term,value); $('rgb-mode-controls').append(row);
    }
    $('rgb-no-controls').hidden = selected.controls.length !== 0;
    $('rgb-no-controls').textContent = selected.id === 0 ? isQmk() ? 'Stock katalogda LED Off olarak tanımlanır.' : 'Uygula düğmesi LED aydınlatmasını kapatır.' : 'Bu modda ayarlanabilir parametre yok.';
    updateRgbPreview();
    updateRgbState();
  }
  function updateRgbState() {
    const busy = isSending();
    const available = !isQmk() && serverAvailable && state.capabilities?.rgb?.hardware_send_available === true;
    const canSend = available && state.device?.connected && Boolean(rgbCatalog) && !busy;
    $('rgb-mode-select').disabled = !rgbCatalog || busy;
    $('rgb-settings-fieldset').disabled = busy;
    for (const id of ['rgb-apply-button','rgb-power-on','rgb-power-off']) $(id).disabled = !canSend;
    $('rgb-apply-label').textContent = busy && (pendingKind || state.job?.kind) === 'rgb' ? 'Gönderiliyor…' : rgbDraft.mode === 0 ? 'Kapatmayı uygula' : 'Ayarları uygula';
    const job = state.job;
    if (rgbJobId && job?.id === rgbJobId && ['sent','error'].includes(job.state)) {
      if (job.state === 'sent' && rgbAction === 'apply') rgbDirty = false;
      rgbJobId = null; rgbAction = null;
    }
    $('rgb-draft-label').textContent = rgbDirty ? 'YEREL TASLAK' : 'YEREL SEÇİM';
    let title, description;
    if (!serverAvailable) {title = 'Yerel uygulamaya bağlanılamıyor'; description = 'Uygulamanın çalıştığından emin olun.';}
    else if (busy) {title = (pendingKind || job?.kind) === 'rgb' ? 'Aydınlatma komutları gönderiliyor' : 'Ekran aktarımı sürüyor'; description = job?.message || 'Tamamlanana kadar USB bağlantısını koruyun.';}
    else if (isQmk()) {title = 'Stock RGB komutları QMK için kapalı'; description = 'Buradaki katalog ve renk çizimi yerel önizlemedir. QMK aydınlatma kontrolüne bağlanmadı.';}
    else if (!available) {title = 'RGB bağlantısı hazır değil'; description = 'Ayarları düzenleyebilirsiniz; gönderim henüz kullanılamıyor.';}
    else if (!state.device?.connected) {title = 'Klavyeyi USB ile bağlayın'; description = 'Göndermek için desteklenen USB cihazı bağlı olmalı.';}
    else if (job?.kind === 'rgb' && job.state === 'error') {title = 'Aydınlatma komutu tamamlanamadı'; description = job.message || 'Bağlantıyı kontrol edip yeniden deneyin.';}
    else if (job?.kind === 'rgb' && job.state === 'sent') {title = state.device?.simulated ? 'Test komutları tamamlandı' : 'USB komutları iletildi; LED’leri kontrol edin'; description = state.device?.simulated ? 'Bu testte fiziksel klavyeye yazılmadı.' : rgbDirty ? 'Son komut iletildi. Yeni taslağınız henüz uygulanmadı.' : 'USB yanıtı alındı; fiziksel görünüm klavyeden doğrulanır.';}
    else {title = 'Uygulamaya hazır'; description = 'Yalnızca bir işlem düğmesine bastığınızda komut gönderilir.';}
    $('rgb-transfer-title').textContent = title;
    $('rgb-transfer-description').textContent = description;
    $('rgb-transfer-status').classList.toggle('is-error',job?.kind === 'rgb' && job.state === 'error');
    $('rgb-progress').hidden = !busy;
    $('rgb-progress').value = Number(job?.progress) || 0;
    const last = state.rgb?.last_enabled;
    const saved = state.rgb?.last_settings;
    const lastMode = rgbCatalog?.modes.find(mode => mode.id === Number(saved?.mode));
    $('rgb-local-status').textContent = last === true ? `Son yerel komut: aydınlatmayı aç${lastMode ? ` · ${lastMode.official_name}` : ''}. Cihazdan okunmadı.` : last === false ? 'Son yerel komut: aydınlatmayı kapat. Cihazdan okunmadı.' : 'Mevcut ışık durumu bilinmiyor; cihazdan okunmadı.';
  }
  async function sendRgb(action) {
    const button = $(action === 'apply' ? 'rgb-apply-button' : action === 'on' ? 'rgb-power-on' : 'rgb-power-off');
    if (button.disabled || isSending()) return;
    $('rgb-catalog-error').hidden = true;
    jobVersion++;
    sendPending = true; pendingKind = 'rgb'; rgbAction = action;
    updateControls();
    try {
      const path = action === 'apply' ? '/api/rgb/apply' : '/api/rgb/power';
      const body = action === 'apply' ? {settings:{...rgbDraft}} : {enabled:action === 'on'};
      const job = await api(path,{method:'POST',body:JSON.stringify(body)});
      state.job = job; rgbJobId = job.id;
    } catch (err) {
      $('rgb-catalog-error').textContent = err.message; $('rgb-catalog-error').hidden = false;
      state.job = {state:'error',kind:'rgb',message:err.message,progress:0};
      rgbJobId = null;
    } finally {
      jobVersion++;
      sendPending = false; pendingKind = null; updateControls();
    }
  }
  function loadRgbCatalog() {
    try {
      rgbCatalog = RGB_CATALOG;
      if (!Array.isArray(rgbCatalog.modes) || rgbCatalog.modes.length !== 20) throw new Error('Resmî efekt kataloğu okunamadı.');
      $('rgb-mode-select').replaceChildren();
      for (const mode of rgbCatalog.modes) $('rgb-mode-select').add(new Option(`${String(mode.id).padStart(2,'0')} · ${mode.name} — ${mode.official_name}`, mode.id));
      $('rgb-mode-select').value = String(rgbDraft.mode);
      $('rgb-software-defaults').textContent = 'Ayarlar bu Mac’te taslak olarak tutulur; kendiliğinden gönderilmez.';
      showRgbMode();
    } catch (err) {
      $('rgb-mode-select').replaceChildren(new Option('Katalog yüklenemedi',''));
      $('rgb-mode-subtitle').textContent = 'Bilgileri tekrar yüklemek için sayfayı yenileyin.';
      $('rgb-catalog-error').textContent = err.message; $('rgb-catalog-error').hidden = false;
    }
  }
  $('rgb-mode-select').addEventListener('change',() => {
    rgbDraft.mode = Number($('rgb-mode-select').value); rgbDirty = true;
    $('rgb-catalog-error').hidden = true;
    showRgbMode();
  });
  $('rgb-apply-button').addEventListener('click',() => sendRgb('apply'));
  $('rgb-power-on').addEventListener('click',() => sendRgb('on'));
  $('rgb-power-off').addEventListener('click',() => sendRgb('off'));
  loadRgbCatalog();

  $('save-preset').addEventListener('click', () => {
    $('preset-error').hidden = true;
    $('preset-name').value = '';
    $('preset-dialog').showModal();
    $('preset-name').focus();
  });
  for (const id of ['close-preset-dialog','cancel-preset']) $(id).addEventListener('click', () => $('preset-dialog').close());
  $('preset-form').addEventListener('submit', async event => {
    event.preventDefault();
    const name = $('preset-name').value.trim();
    if (!name || presetPending) return;
    presetPending = true;
    $('confirm-save-preset').disabled = true;
    $('confirm-save-preset').textContent = 'Kaydediliyor…';
    $('preset-error').hidden = true;
    try {
      const preset = await api('/api/presets', {method:'POST',body:JSON.stringify({name,asset_id:assetId,settings:{...settings}})});
      await refreshState();
      $('preset-select').value = preset.id;
      $('preset-dialog').close();
      toast(`“${name}” önayarı kaydedildi.`);
    } catch (err) {
      $('preset-error').textContent = err.message;
      $('preset-error').hidden = false;
    } finally {
      presetPending = false;
      $('confirm-save-preset').disabled = false;
      $('confirm-save-preset').textContent = 'Kaydet';
      updateControls();
    }
  });
  $('preset-select').addEventListener('change', updateControls);
  $('load-preset').addEventListener('click', async () => {
    const id = $('preset-select').value;
    if (!id || isSending()) return;
    importing = true; updateControls(); clearError();
    try {
      const preset = await api(`/api/presets/${encodeURIComponent(id)}`);
      settings = {...defaults,...preset.settings};
      assetId = preset.asset_id;
      assetName = preset.name;
      $('asset-name').textContent = preset.name;
      $('asset-details').textContent = 'Kayıtlı görsel ve ayarları yüklendi';
      syncSettingsUI(); schedulePreview(true);
      toast(`“${preset.name}” yüklendi. Göndermeye hazır olduğunuzda Gönder’e basın.`);
    } catch (err) {error(err.message);} finally {importing = false; updateControls();}
  });

  let drag = null;
  const bezel = document.querySelector('.screen-bezel');
  bezel.addEventListener('pointerdown', event => {
    if (!imageSendAvailable() || isSending() || importing || !render || event.button !== 0) return;
    drag = {pointer:event.pointerId,startX:event.clientX,startY:event.clientY,x:settings.x,y:settings.y};
    bezel.setPointerCapture(event.pointerId);
  });
  bezel.addEventListener('pointermove', event => {
    if (!drag || drag.pointer !== event.pointerId) return;
    const width = bezel.getBoundingClientRect().width;
    settings.x = Math.max(-1,Math.min(1,drag.x - (event.clientX - drag.startX) / width * 2));
    settings.y = Math.max(-1,Math.min(1,drag.y - (event.clientY - drag.startY) / width * 2));
    syncSettingsUI(); schedulePreview();
  });
  for (const event of ['pointerup','pointercancel','lostpointercapture']) bezel.addEventListener(event, () => { drag = null; });

  syncSettingsUI();
  switchPanel(({ekran:'screen',aydinlatma:'lighting',baglantilar:'sources',durum:'connections'})[location.hash.slice(1)] || 'connections', false);
  refreshState().then(() => { if (serverAvailable) schedulePreview(true); else {rendering = false; updateControls();} });
  $('refresh-host-link').addEventListener('click',() => {refreshHostLink();refreshDeviceSettings();});
  $('host-screen-toggle').addEventListener('click',() => {if (!$('host-screen-toggle').disabled) applyDeviceSettings({screen_on:!deviceSettings.screen_on});});
  $('host-sleep-select').addEventListener('change',() => {sleepDirty = true;displayDeviceSettings();});
  $('host-sleep-apply').addEventListener('click',() => {if (!$('host-sleep-apply').disabled) applyDeviceSettings({sleep_minutes:Number($('host-sleep-select').value)});});
  refreshHostLink();
  refreshDeviceSettings();
  for (const name of ['codex','claude_code']) for (const action of ['connect','disconnect','refresh','setup']) $(`connection-${name}-${action}`).addEventListener('click',() => connectionAction(name,action));
  refreshConnections();
  $('media-show').addEventListener('click',() => setMediaDisplay(true));
  $('media-hide').addEventListener('click',() => setMediaDisplay(false));
  setInterval(refreshMediaState,4000);
  setInterval(() => {if (!$('panel-sources').hidden) refreshConnections();},4000);
  setInterval(refreshHostLink,4000);
  setInterval(refreshDeviceSettings,4000);
  setInterval(async () => {
    const wasAvailable = serverAvailable;
    await refreshState();
    if (!wasAvailable && serverAvailable && !render && !importing) schedulePreview(true);
  }, 1000);
})();
