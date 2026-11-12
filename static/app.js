const $ = id => document.getElementById(id);
const textEl = $('text'), durationEl = $('duration'), voiceListEl = $('voiceList');
const previewAudio = $('previewAudio'), outputAudio = $('outputAudio');

let voices = [];
let selectedVoiceId = '';
let language = 'ar';
let selectedEngine = 'xtts';
let targetSeconds = 15;
let currentPreviewPlaying = null;

// Helpers
function words(s) {
  const m = s.match(/[\p{L}\p{N}]+(?:['’\-][\p{L}\p{N}]+)*/gu);
  return m ? m.length : 0;
}

function analyze() {
  const s = textEl.value, n = words(s), chars = s.length;
  const wpm = language === 'ar' ? 145 : 150;
  const targetWords = Math.round(targetSeconds * wpm / 60);
  const estimatedSeconds = n ? (n / wpm * 60) : 0;
  const speedRatio = (estimatedSeconds && targetSeconds) ? (estimatedSeconds / targetSeconds) : 1.0;

  $('wordCount').textContent = n;
  $('charCount').textContent = chars;
  $('targetWords').textContent = targetWords + ' كلمة';
  $('estimated').textContent = estimatedSeconds.toFixed(1) + ' ثانية';
  $('guaranteedDuration').textContent = targetSeconds.toFixed(2) + ' ثانية بالضبط';
  $('currentSliderSec').textContent = targetSeconds + ' ثانية';

  // Speed bar update
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

  // Visual meter
  // Normal range: 0.85x to 1.25x
  const pct = Math.min(Math.max((speedRatio / 2.0) * 100, 10), 100);
  speedFill.style.width = pct + '%';

  if (speedRatio >= 0.85 && speedRatio <= 1.25) {
    speedRatioEl.textContent = `${speedRatio.toFixed(2)}x (إلقاء طبيعي ومتناسق)`;
    speedFill.classList.add('good');
    fit.classList.add('good');
    fit.textContent = `✓ ممتاز! النص متناسق تماماً مع مدة ${targetSeconds} ثانية. سيخرج المقطع بـ ${targetSeconds}.00 ثانية بالضبط وبنبرة طبيعية.`;
  } else if (speedRatio < 0.85) {
    speedRatioEl.textContent = `${speedRatio.toFixed(2)}x (إلقاء هادئ ومتأنٍ)`;
    speedFill.classList.add('warn');
    fit.classList.add('short');
    fit.textContent = `النص قصير مقارنة بـ ${targetSeconds} ثانية. يمكنك إضافة كلمات إن رغبت، أو سيقوم النظام بمد الإلقاء بدقة ليصل إلى ${targetSeconds}.00 ثانية بالضبط.`;
  } else {
    speedRatioEl.textContent = `${speedRatio.toFixed(2)}x (إلقاء سريع ومضغوط)`;
    speedFill.classList.add('danger');
    fit.classList.add('long');
    fit.textContent = `النص طويل مقارنة بـ ${targetSeconds} ثانية. سيلتزم النظام بـ ${targetSeconds}.00 ثانية بالضبط، ولكن يُفضل تقليل بضع كلمات لتفادي السرعة الزائدة.`;
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
  voiceListEl.innerHTML = '';
  const filtered = voices.filter(v => {
    if (filter === 'male') return v.gender === 'male';
    if (filter === 'female') return v.gender === 'female';
    if (filter === 'ar') return v.lang === 'ar';
    if (filter === 'en') return v.lang === 'en';
    return true;
  });

  filtered.forEach(v => {
    const card = document.createElement('div');
    card.className = 'voice' + (v.id === selectedVoiceId ? ' selected' : '');
    card.dataset.id = v.id;

    const avatarLetter = v.gender === 'female' ? '♀' : '♂';
    const avatarClass = v.gender === 'female' ? 'avatar female' : 'avatar male';

    card.innerHTML = `
      <div class="${avatarClass}">${avatarLetter}</div>
      <div class="vinfo">
        <b>${v.name}</b>
        <small>${v.dialect} · ${v.description.slice(0, 48)}...</small>
      </div>
      <button class="preview-btn" title="استماع للعينة الأصلية" data-file="${v.file}">▶</button>
      <span class="check">✓</span>
    `;

    // Click card to select
    card.addEventListener('click', (e) => {
      if (e.target.closest('.preview-btn')) return;
      selectVoice(v.id);
    });

    // Preview audio button
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
    $('engineMessage').textContent = `تم اختيار: ${v.name} (${v.dialect}) — المدة المستهدفة: ${targetSeconds} ثانية`;
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

// Fetch initial data
async function init() {
  try {
    const hRes = await fetch('/api/health');
    const hData = await hRes.json();
    if (hData.status === 'ok') {
      $('sysStatus').innerHTML = `<span class="dot"></span> ${hData.gpu} (CUDA 12.1)`;
      $('gpuName').textContent = hData.gpu;
      $('cudaStatus').textContent = hData.cuda ? 'مفعّل بنجاح' : 'غير متوفر';
    }

    const vRes = await fetch('/api/voices');
    voices = await vRes.json();
    if (voices.length > 0) {
      selectedVoiceId = voices[0].id;
      renderVoices('all');
    }
  } catch (err) {
    console.error('Init error:', err);
    $('sysStatus').textContent = 'تعذر الاتصال بالخادم';
  }
}

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

// Text presets
$('arSampleBtn').addEventListener('click', () => {
  textEl.value = 'أهلاً بكم في استوديو سام للصوتيات. نقدم لكم دقة متناهية والتزاماً تاماً بالوقت والسرعة المحددة لكل مشروع.';
  language = 'ar';
  document.querySelectorAll('.lang').forEach(b => b.classList.toggle('active', b.dataset.lang === 'ar'));
  analyze();
});

$('enSampleBtn').addEventListener('click', () => {
  textEl.value = 'Welcome to SAM Voice Studio. Strict time-fitted AI speech synthesis, matching your exact target duration.';
  language = 'en';
  document.querySelectorAll('.lang').forEach(b => b.classList.toggle('active', b.dataset.lang === 'en'));
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
  genText.textContent = `جارٍ توليد المقطع وضبطه على ${targetSeconds} ثانية بالضبط...`;
  msg.textContent = `يجري الآن تطبيق الذكاء الاصطناعي والمطابقة الزمنية الصارمة على ${targetSeconds} ثانية...`;
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
        strict_duration: true
      })
    });

    const data = await res.json();
    if (res.ok && data.status === 'success') {
      msg.textContent = `✓ اكتمل التوليد بنجاح! المدة الصادرة: ${data.exact_duration} ثانية بالضبط.`;
      outputAudio.src = data.audio_url + '?t=' + Date.now();
      $('resultVoice').textContent = `الشخصية: ${data.voice}`;
      $('resultLang').textContent = `اللغة: ${data.language === 'ar' ? 'العربية' : 'الإنجليزية'}`;
      $('resultEngine').textContent = `المحرك: ${data.engine}`;
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
analyze();
init();
