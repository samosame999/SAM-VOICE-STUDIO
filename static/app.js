const $ = id => document.getElementById(id);
const textEl = $('text'), durationEl = $('duration'), voiceListEl = $('voiceList');
const previewAudio = $('previewAudio'), outputAudio = $('outputAudio');

let voices = [];
let selectedVoiceId = '';
let language = 'auto';
let selectedEngine = 'xtts';
let targetSeconds = 15;
let currentPreviewPlaying = null;
let currentFilter = 'all';

// Echo state
let echoEnabled = false;
let echoIntensity = 35;

// Helpers
function words(s) {
  const m = s.match(/[\p{L}\p{N}]+(?:['’\-][\p{L}\p{N}]+)*/gu);
  return m ? m.length : 0;
}

function detectLang(s) {
  const ar = (s.match(/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/g) || []).length;
  const en = (s.match(/[a-zA-Z]/g) || []).length;
  if (ar > en) return 'ar';
  if (en > 0) return 'en';
  return 'ar';
}

function analyze() {
  const s = textEl.value, n = words(s), chars = s.length;
  const detected = detectLang(s);
  
  // Update language badge
  const badge = $('langDetectedBadge');
  if (language === 'auto') {
    badge.textContent = detected === 'ar' ? '🌍 اكتشاف تلقائي: العربية' : '🌍 اكتشاف تلقائي: الإنجليزية';
  } else {
    badge.textContent = language === 'ar' ? '🌍 لغة الإخراج: العربية (يدوي)' : '🌍 لغة الإخراج: الإنجليزية (يدوي)';
  }

  const wpm = (language === 'ar' || (language === 'auto' && detected === 'ar')) ? 145 : 150;
  const targetWords = Math.round(targetSeconds * wpm / 60);
  const estimatedSeconds = n ? (n / wpm * 60) : 0;
  const speedRatio = (estimatedSeconds && targetSeconds) ? (estimatedSeconds / targetSeconds) : 1.0;

  $('wordCount').textContent = n;
  $('charCount').textContent = chars;
  $('targetWords').textContent = targetWords + ' كلمة';
  $('estimated').textContent = estimatedSeconds.toFixed(1) + ' ثانية';
  $('guaranteedDuration').textContent = targetSeconds.toFixed(2) + ' ثانية بالضبط';
  $('currentSliderSec').textContent = targetSeconds + ' ثانية';

  // Speed gauge
  const speedFill = $('speedFill');
  const speedRatioEl = $('speedRatio');
  const fit = $('fit');
  fit.className = 'fit';
  speedFill.className = 'speed-fill';

  if (!n) {
    speedRatioEl.textContent = '1.00x (طبيعي)';
    speedFill.style.width = '50%';
    speedFill.classList.add('good');
    fit.textContent = `اكتب النص لبدء تحليل السرعة وضمان خروج المقطع بـ ${targetSeconds} ثانية بالضبط.`;
    return;
  }

  const pct = Math.min(Math.max((speedRatio / 2.0) * 100, 10), 100);
  speedFill.style.width = pct + '%';

  if (speedRatio >= 0.85 && speedRatio <= 1.25) {
    speedRatioEl.textContent = `${speedRatio.toFixed(2)}x (إلقاء بشري طبيعي ومتناسق)`;
    speedFill.classList.add('good');
    fit.classList.add('good');
    fit.textContent = `✓ ممتاز! النص متناسق تماماً مع مدة ${targetSeconds} ثانية. سيخرج المقطع بـ ${targetSeconds}.00 ثانية بالضبط وبنبرة بشرية طبيعية.`;
  } else if (speedRatio < 0.85) {
    speedRatioEl.textContent = `${speedRatio.toFixed(2)}x (إلقاء هادئ ومتأنٍ)`;
    speedFill.classList.add('warn');
    fit.classList.add('short');
    fit.textContent = `النص قصير مقارنة بـ ${targetSeconds} ثانية. سيقوم النظام بمد الإلقاء باحترافية وبدون أي نبرة روبوتية ليصل إلى ${targetSeconds}.00 ثانية بالضبط.`;
  } else {
    speedRatioEl.textContent = `${speedRatio.toFixed(2)}x (إلقاء سريع ومضغوط)`;
    speedFill.classList.add('danger');
    fit.classList.add('long');
    fit.textContent = `النص طويل مقارنة بـ ${targetSeconds} ثانية. سيلتزم النظام بـ ${targetSeconds}.00 ثانية بالضبط، ولكن يُفضل تقليل بضع كلمات للحفاظ على إلقاء بشري مستريح.`;
  }
}

function setDuration(v) {
  targetSeconds = Number(v);
  durationEl.value = targetSeconds;
  $('durationLabel').textContent = targetSeconds + ' ثانية بالضبط';
  document.querySelectorAll('.preset').forEach(b => {
    b.classList.toggle('active', Number(b.dataset.sec) === targetSeconds);
  });
  analyze();
}

// Render Voices
function renderVoices(filter = 'all') {
  currentFilter = filter;
  voiceListEl.innerHTML = '';
  const filtered = voices.filter(v => {
    if (filter === 'custom') return !!v.is_custom;
    if (filter === 'male') return v.gender === 'male';
    if (filter === 'female') return v.gender === 'female';
    if (filter === 'ar') return v.lang === 'ar';
    if (filter === 'en') return v.lang === 'en';
    return true;
  });

  $('voiceCountBadge').textContent = `${voices.length} صوتاً متاحاً (${filtered.length} مطابق)`;

  if (filtered.length === 0) {
    voiceListEl.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:20px;color:var(--muted)">لا توجد أصوات مطابقة للتصنيف الحالي.</div>';
    return;
  }

  filtered.forEach(v => {
    const card = document.createElement('div');
    card.className = 'voice' + (v.id === selectedVoiceId ? ' selected' : '');
    card.dataset.id = v.id;

    let avatarLetter = v.gender === 'female' ? '♀' : '♂';
    let avatarClass = v.gender === 'female' ? 'avatar female' : 'avatar male';
    if (v.is_custom) {
      avatarLetter = '★';
      avatarClass = 'avatar';
    }

    const badgeSpan = v.is_custom ? '<span style="color:#ffc184;font-size:9px"> [صوت مخصص]</span>' : '';

    card.innerHTML = `
      <div class="${avatarClass}">${avatarLetter}</div>
      <div class="vinfo">
        <b>${v.name}${badgeSpan}</b>
        <small>${v.dialect || 'عينة صوتية'} · ${(v.description || '').slice(0, 48)}...</small>
      </div>
      <button class="preview-btn" title="استماع للعينة المرجعية" data-file="${v.file}">▶</button>
      <span class="check">✓</span>
    `;

    // Click card to select
    card.addEventListener('click', (e) => {
      if (e.target.closest('.preview-btn')) return;
      selectVoice(v.id);
    });

    // Preview audio
    const pBtn = card.querySelector('.preview-btn');
    pBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      playPreview(v.file, pBtn);
    });

    voiceListEl.appendChild(card);
  });
}

function selectVoice(id) {
  selectedVoiceId = id;
  document.querySelectorAll('.voice').forEach(c => {
    c.classList.toggle('selected', c.dataset.id === id);
  });
  const v = voices.find(x => x.id === id);
  if (v) {
    $('engineMessage').textContent = `تم اختيار: ${v.name} — المدة المستهدفة: ${targetSeconds} ثانية`;
  }
}

function playPreview(file, btn) {
  if (currentPreviewPlaying === btn) {
    previewAudio.pause();
    btn.textContent = '▶';
    btn.classList.remove('playing');
    currentPreviewPlaying = null;
    return;
  }

  if (currentPreviewPlaying) {
    currentPreviewPlaying.textContent = '▶';
    currentPreviewPlaying.classList.remove('playing');
  }

  previewAudio.src = `/voices/${file}`;
  previewAudio.play().then(() => {
    btn.textContent = '⏸';
    btn.classList.add('playing');
    currentPreviewPlaying = btn;
  }).catch(err => {
    console.error('Audio play error:', err);
  });

  previewAudio.onended = () => {
    btn.textContent = '▶';
    btn.classList.remove('playing');
    currentPreviewPlaying = null;
  };
}

// Fetch Voices
async function loadVoices() {
  try {
    const vRes = await fetch('/api/voices');
    voices = await vRes.json();
    if (voices.length > 0) {
      if (!selectedVoiceId || !voices.some(v => v.id === selectedVoiceId)) {
        selectedVoiceId = voices[0].id;
      }
      renderVoices(currentFilter);
    }
  } catch (err) {
    console.error('Error fetching voices:', err);
  }
}

// Fetch initial system status
async function init() {
  try {
    const hRes = await fetch('/api/health');
    const hData = await hRes.json();
    if (hData.status === 'ok') {
      $('sysStatus').innerHTML = `<span class="dot"></span> ${hData.gpu} (CUDA 12.1)`;
      $('gpuName').textContent = hData.gpu;
      $('cudaStatus').textContent = hData.cuda ? 'مفعّل بنجاح' : 'غير متوفر';
    }
    await loadVoices();
  } catch (err) {
    console.error('Init error:', err);
    $('sysStatus').textContent = 'تعذر الاتصال بالخادم';
  }
}

// Voice Toolbar Actions
$('refreshVoicesBtn').addEventListener('click', async () => {
  $('voiceCountBadge').textContent = 'جاري التحديث...';
  await loadVoices();
});

$('openVoicesFolderBtn').addEventListener('click', async () => {
  try {
    await fetch('/api/open-voices-folder', { method: 'POST' });
  } catch (e) {
    console.error('Cannot open folder:', e);
  }
});

$('uploadVoiceBtn').addEventListener('click', () => {
  $('voiceFileInput').click();
});

$('voiceFileInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  $('engineMessage').textContent = `جاري رفع وفحص العينة الصوتية: ${file.name}...`;

  try {
    const res = await fetch('/api/voices/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      voices = data.voices;
      // Select the newly added voice
      const newVoice = voices.find(v => v.file === file.name || v.id.includes(file.name.split('.')[0]));
      if (newVoice) {
        selectedVoiceId = newVoice.id;
      }
      renderVoices('all');
      document.querySelectorAll('.vfilter').forEach(b => b.classList.toggle('active', b.dataset.filter === 'all'));
      $('engineMessage').textContent = `✓ ${data.message} تم اختياره وجاهز للتحدث به فوراً!`;
    } else {
      alert('فشل رفع الصوت: ' + (data.detail || 'خطأ غير معروف'));
    }
  } catch (err) {
    console.error('Upload error:', err);
    alert('حدث خطأ أثناء رفع ملف الصوت.');
  } finally {
    $('voiceFileInput').value = '';
  }
});

// Filters
document.querySelectorAll('.vfilter').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.vfilter').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderVoices(btn.dataset.filter);
  });
});

// Engine selection
document.querySelectorAll('.engine-chip').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.engine-chip').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedEngine = btn.dataset.engine;
  });
});

// Language selection
document.querySelectorAll('.lang').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.lang').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    language = btn.dataset.lang;
    analyze();
  });
});

// Echo / Reverb controls
const echoToggle = $('echoToggle');
const echoSlider = $('echoSlider');
const echoLabel = $('echoLabel');
const echoPanel = $('echoPanel');
const sideEchoStatus = $('sideEchoStatus');

function updateEchoUI() {
  echoPanel.classList.toggle('disabled', !echoEnabled);
  if (!echoEnabled) {
    echoLabel.textContent = 'غير مفعّل (صوت جاف 100%)';
    sideEchoStatus.textContent = 'معطل';
    $('echoToggleText').textContent = 'صدى الصوت: غير مفعّل';
  } else {
    sideEchoStatus.textContent = `${echoIntensity}% مفعّل`;
    $('echoToggleText').textContent = 'صدى الصوت: مفعّل ✓';
    if (echoIntensity <= 10) echoLabel.textContent = `${echoIntensity}% (صدى خفيف جداً)`;
    else if (echoIntensity <= 30) echoLabel.textContent = `${echoIntensity}% (صدى استوديو هادئ)`;
    else if (echoIntensity <= 50) echoLabel.textContent = `${echoIntensity}% (صدى بودكاست دافئ)`;
    else if (echoIntensity <= 75) echoLabel.textContent = `${echoIntensity}% (صدى قاعة كبرى)`;
    else echoLabel.textContent = `${echoIntensity}% (إيكو سينمائي عميق)`;
  }
}

echoToggle.addEventListener('change', () => {
  echoEnabled = echoToggle.checked;
  updateEchoUI();
});

echoSlider.addEventListener('input', (e) => {
  echoIntensity = Number(e.target.value);
  if (!echoEnabled && echoIntensity > 0) {
    echoEnabled = true;
    echoToggle.checked = true;
  }
  updateEchoUI();
  document.querySelectorAll('.echo-btn').forEach(b => {
    b.classList.toggle('active', Number(b.dataset.val) === echoIntensity);
  });
});

document.querySelectorAll('.echo-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const val = Number(btn.dataset.val);
    echoIntensity = val;
    echoSlider.value = val;
    echoEnabled = val > 0;
    echoToggle.checked = echoEnabled;
    updateEchoUI();
    document.querySelectorAll('.echo-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

// Text presets
$('arSampleBtn').addEventListener('click', () => {
  textEl.value = 'أهلاً بكم في استوديو سام للصوتيات. نقدم لكم دقة متناهية والتزاماً تاماً بالوقت والسرعة المحددة لكل مشروع.';
  analyze();
});

$('enSampleBtn').addEventListener('click', () => {
  textEl.value = 'Every morning, he watched successful people walk past his small office, dreaming of becoming one of them. One day, his boss handed him a letter. He had just lost his job. Instead of giving up, he opened his old laptop and started building his own business. Five years later, he bought the company that once fired him.';
  analyze();
});

// Presets clicks
document.querySelectorAll('.preset').forEach(btn => {
  btn.addEventListener('click', () => setDuration(btn.dataset.sec));
});
durationEl.addEventListener('input', e => setDuration(e.target.value));
textEl.addEventListener('input', analyze);
$('clearBtn').addEventListener('click', () => { textEl.value = ''; analyze(); textEl.focus(); });

// Generate
$('generate').addEventListener('click', async () => {
  const text = textEl.value.trim();
  if (!text) {
    alert('يرجى كتابة نص أولاً لتوليد الصوت.');
    textEl.focus();
    return;
  }

  const genBtn = $('generate');
  const genText = $('genBtnText');
  const msg = $('engineMessage');
  const resultBox = $('resultBox');

  genBtn.disabled = true;
  genText.textContent = `جارٍ توليد الصوت بنبرة بشرية وضبطه على ${targetSeconds} ثانية بالضبط...`;
  msg.textContent = `يجري التوليد الآن بأعلى جودة بشرية ومطابقة زمنية صارمة على ${targetSeconds} ثانية...`;
  resultBox.classList.remove('active');

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text,
        voice_id: selectedVoiceId,
        language: language,
        engine: selectedEngine,
        target_seconds: targetSeconds,
        strict_duration: true,
        echo_enabled: echoEnabled,
        echo_intensity: echoIntensity
      })
    });

    const data = await res.json();
    if (res.ok && data.status === 'success') {
      msg.textContent = `✓ اكتمل التوليد بنجاح! المدة الصادرة: ${data.exact_duration} ثانية بالضبط.`;
      outputAudio.src = data.audio_url + '?t=' + Date.now();
      $('resultVoice').textContent = `الشخصية: ${data.voice}`;
      $('resultLang').textContent = `اللغة: ${data.language === 'ar' ? 'العربية' : 'الإنجليزية'}`;
      $('resultEngine').textContent = `المحرك: ${data.engine}`;
      $('resultEcho').textContent = data.echo_applied ? `الصدى: مفعّل (${data.echo_intensity}%)` : 'الصدى: بدون';
      $('resultDurationBadge').textContent = `${data.exact_duration}s بالضبط (مطابق 100%)`;
      $('downloadWav').href = data.audio_url;
      $('downloadWav').download = data.filename;
      resultBox.classList.add('active');
      outputAudio.play();
    } else {
      msg.textContent = 'خطأ أثناء التوليد: ' + (data.detail || 'حدث خطأ غير متوقع');
    }
  } catch (err) {
    console.error('Generate error:', err);
    msg.textContent = 'تعذر إتمام التوليد. تأكد من تشغيل الخادم.';
  } finally {
    genBtn.disabled = false;
    genText.textContent = 'بدء توليد الصوت بالوقت الصارم';
  }
});

// Start
setDuration(15);
updateEchoUI();
analyze();
init();
