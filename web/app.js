const $ = (id) => document.getElementById(id);
const defaults = {
  chapterRelevance: .18, visualImpact: .18, smallScreenReadability: .16,
  mainSubjectClarity: .14, emotionalImpact: .10, curiosity: .10,
  platformAdaptability: .06, continuityAccuracy: .04, spoilerSafety: .04,
};
const jobFromUrl = new URLSearchParams(location.search).get("job") || "";
let currentJob = jobFromUrl || localStorage.getItem("spalingJob") || "";
let editorJob = "";
if (jobFromUrl) localStorage.setItem("spalingJob", jobFromUrl);
let saveTimeout = null;

function debouncedSave() {
  if (saveTimeout) clearTimeout(saveTimeout);
  saveTimeout = setTimeout(savePreferences, 500);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function readFile(id) {
  const file = $(id).files[0];
  if (!file) throw new Error("Chưa chọn file chương");
  return file.text();
}

function detectChapterNumber(filename) {
  const match = filename.match(/chapter[_\s]*(\d+)/i);
  return match ? parseInt(match[1], 10) : 1;
}

function detectStoryName(dirPath) {
  const parts = dirPath.replace(/[\\/]+$/, "").split(/[\\/]/);
  const parentDir = parts.slice(0, -1).join("\\");
  return parentDir.split("\\").pop() || "";
}

function number(id) {
  const value = $(id).value.trim();
  return value === "" ? null : Number(value);
}

function selected(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || "";
}

function sceneWeights() {
  return Object.fromEntries([...document.querySelectorAll("[data-weight]")].map((input) => [
    input.dataset.weight, Number(input.value),
  ]));
}

function setBusy(busy) {
  $("start").disabled = busy;
  $("cancel").disabled = !busy;
  $("resume").hidden = true;
}

function savePreferences() {
  const ids = [
    "platform",
    "ttsProvider", "voice", "temperature", "topK",
    "topP", "repetition", "pitch", "tempo", "videoSubtitleMode", "sceneDensity", "modelProfile",
    "contextDir",
  ];
  const values = Object.fromEntries(ids.map((id) => [id, $(id).value]));
  values.productType = selected("productType");
  values.audioImageScope = selected("audioImageScope");
  for (const id of ["audioSrt", "audioImages", "videoMp3", "videoSrt", "overnight", "force", "ai"]) {
    values[id] = $(id).checked;
  }
  localStorage.setItem("spalingPreferencesV2", JSON.stringify(values));
}

function restorePreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem("spalingPreferencesV2") || "{}");
    for (const [id, value] of Object.entries(saved)) {
      if (id === "productType" || id === "audioImageScope") {
        const radio = document.querySelector(`input[name="${id}"][value="${value}"]`);
        if (radio) radio.checked = true;
      } else if ($(id) && typeof value === "boolean") {
        $(id).checked = value;
      } else if ($(id)) {
        $(id).value = value;
      }
    }
  } catch {}
}

function updateOutputOptions() {
  const audioOnly = selected("productType") === "audio";
  $("audioOptions").hidden = !audioOnly;
  $("videoOptions").hidden = audioOnly;
  $("audioImageOptions").hidden = !$("audioImages").checked;
  const needsImages = !audioOnly || $("audioImages").checked;
  $("imageSettings").hidden = !needsImages;
  const sceneImages = !audioOnly || selected("audioImageScope") === "scenes";
  for (const element of document.querySelectorAll(".scene-option")) {
    element.hidden = !sceneImages;
  }
}

function applyOvernightPreset() {
  if (!$("overnight").checked) return;
  $("sceneDensity").value = "max";
  $("modelProfile").value = "max";
  $("ai").checked = true;
}

async function recommendWorkers() {
  if ($("renderMode").value !== "parallel") {
    $("parallelWorkers").value = 1;
    $("workerReason").textContent = "Chế độ tuần tự luôn dùng 1 luồng xử lý.";
    return;
  }
  $("recommendWorkers").disabled = true;
  $("workerReason").textContent = "AI đang đọc cấu hình CPU, GPU và VRAM…";
  try {
    const result = await api("/api/recommend-workers", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        device: $("device").value,
        image_provider: $("imageProvider").value,
      }),
    });
    $("parallelWorkers").value = result.workers;
    $("workerReason").textContent = `${result.source}: ${result.reason}`;
  } catch (error) {
    $("parallelWorkers").value = 1;
    $("workerReason").textContent = `Không lấy được đề xuất AI; dùng 1 luồng xử lý an toàn. ${error.message}`;
  } finally {
    $("recommendWorkers").disabled = false;
  }
}

async function loadConfig() {
  const config = await api("/api/config");
  $("output").value = config.default_output;
  const backendSummary = (config.backends || [])
    .map((item) => `${item.name}: ${item.ready ? "sẵn sàng" : "có lỗi"}`)
    .join(" · ");
  $("system").textContent = backendSummary || `FFmpeg: ${config.system.ffmpeg ? "sẵn sàng" : "thiếu"} · Node: ${config.system.node ? "sẵn sàng" : "thiếu"} · GPU: ${config.system.gpu ? "đã phát hiện" : "không phát hiện"} · Ollama: ${config.models.length ? "sẵn sàng" : "chưa sẵn sàng"}`;

  $("voice").replaceChildren();
  for (const voice of config.voices || []) {
    $("voice").add(new Option(voice.name, voice.name));
  }
  const tts = config.tts || {};
  if (tts.voice && [...$("voice").options].some((option) => option.value === tts.voice)) {
    $("voice").value = tts.voice;
  }
  for (const [id, key] of [
    ["temperature","temperature"], ["topK","top_k"], ["topP","top_p"],
    ["repetition","repetition_penalty"], ["pitch","pitch_ratio"], ["tempo","tempo_ratio"],
  ]) {
    if (tts[key] != null) $(id).value = tts[key];
  }
  restorePreferences();
  updateOutputOptions();
}

$("chapterFile").addEventListener("change", () => {
  const file = $("chapterFile").files[0];
  if (file && !$("story").value) $("story").value = file.name.replace(/\.txt$/i, "");
});

for (const input of document.querySelectorAll('input[name="productType"], input[name="audioImageScope"]')) {
  input.addEventListener("change", updateOutputOptions);
}
$("audioImages").addEventListener("change", updateOutputOptions);

// Auto-save preferences on input change (debounced)
for (const input of document.querySelectorAll("select, input[type=range], input[type=number]")) {
  input.addEventListener("change", debouncedSave);
}

$("overnight").addEventListener("change", applyOvernightPreset);

/* Legacy worker controls removed from UI; backend is fixed to sequential low-VRAM.
$("renderMode").addEventListener("change", () => {
  $("recommendWorkers").disabled = $("renderMode").value !== "parallel";
  recommendWorkers();
});
for (const id of ["device", "imageProvider"]) {
  $(id).addEventListener("change", () => {
    if ($("renderMode").value === "parallel") recommendWorkers();
  });
}
$("recommendWorkers").addEventListener("click", recommendWorkers);
*/

$("chooseOutput").addEventListener("click", async () => {
  $("chooseOutput").disabled = true;
  try {
    const result = await api("/api/select-output", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({initial: $("output").value.trim()}),
    });
    if (result.path) $("output").value = result.path;
  } catch (error) {
    $("jobStatus").textContent = `Không mở được hộp chọn thư mục: ${error.message}`;
  } finally {
    $("chooseOutput").disabled = false;
  }
});

$("chooseContextDir").addEventListener("click", async () => {
  $("chooseContextDir").disabled = true;
  try {
    const result = await api("/api/select-output", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({initial: $("contextDir").value.trim()}),
    });
    if (result.path) {
      $("contextDir").value = result.path;
      // Auto-detect story name from parent directory
      const storyName = detectStoryName(result.path);
      if (storyName && !$("story").value.trim()) {
        $("story").value = storyName;
      }
      // Auto-set output to parent directory
      if (!$("output").value.trim()) {
        const parentDir = result.path.replace(/[\\/]+\.md$/, "").replace(/[\\/]+$/, "");
        $("output").value = parentDir;
      }
    }
  } catch (error) {
    $("jobStatus").textContent = `Không mở được hộp chọn thư mục: ${error.message}`;
  } finally {
    $("chooseContextDir").disabled = false;
  }
});

$("chapterFile").addEventListener("change", () => {
  const file = $("chapterFile").files[0];
  if (file) {
    $("chapterNumber").value = detectChapterNumber(file.name);
  }
});

$("resetWeights").addEventListener("click", () => {
  for (const input of document.querySelectorAll("[data-weight]")) {
    input.value = defaults[input.dataset.weight];
  }
});

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (currentJob) {
    currentJob = "";
    localStorage.removeItem("spalingJob");
  }
  setBusy(true);
  $("jobStatus").textContent = "Đang tạo tác vụ…";
  $("logs").textContent = "";
  $("outputs").replaceChildren();
  try {
    savePreferences();
    const productType = selected("productType");
    const contextDir = $("contextDir").value.trim();
    if (!contextDir) throw new Error("Chưa chọn thư mục .md");

    const chapterText = await readFile("chapterFile");
    const payload = {
      context_dir: contextDir,
      chapter_text: chapterText,
      story: $("story").value.trim() || detectStoryName(contextDir),
      chapter_number: number("chapterNumber"),
      output: $("output").value.trim(),
      product_type: productType,
      audio_srt: $("audioSrt").checked,
      audio_images: $("audioImages").checked,
      audio_image_scope: selected("audioImageScope"),
      video_mp3: $("videoMp3").checked,
      video_srt: $("videoSrt").checked,
      video_subtitle_mode: $("videoSubtitleMode").value,
      audiobook: $("sceneDensity").value,
      images: null,
      device: "gpu",
      platform: $("platform").value,
      image_provider: "comfyui",
      auto_parallel: true,
      overnight: $("overnight").checked,
      force: $("force").checked,
      ai: $("ai").checked,
      tts_provider: $("ttsProvider").value,
      voice: $("voice").value,
      temperature: number("temperature"),
      top_k: number("topK"),
      top_p: number("topP"),
      repetition_penalty: number("repetition"),
      pitch_ratio: number("pitch"),
      tempo_ratio: number("tempo"),
      scene_weights: sceneWeights(),
      model_profile: $("modelProfile").value,
    };
    const result = await api("/api/jobs", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    currentJob = result.job_id;
    localStorage.setItem("spalingJob", currentJob);
    poll();
  } catch (error) {
    $("jobStatus").textContent = `Lỗi: ${error.message}`;
    setBusy(false);
  }
});

function formatTime(seconds) {
  if (!seconds || seconds <= 0) return "--:--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function sceneField(card, name) {
  return card.querySelector(`[data-field="${name}"]`);
}

async function saveSceneCard(card) {
  const sceneId = card.dataset.sceneId;
  const platform = sceneField(card, "platform").value;
  const prompt = sceneField(card, "prompt").value.trim();
  const references = sceneField(card, "references").value.split(";").map((item) => item.trim()).filter(Boolean);
  await api(`/api/jobs/${editorJob}/storyboard`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      scene_id: sceneId,
      location: sceneField(card, "location").value,
      action: sceneField(card, "action").value,
      prompts: {[platform]: prompt},
      tone: sceneField(card, "tone").value,
      camera: sceneField(card, "camera").value,
      order: Number(sceneField(card, "order").value),
      enabled: sceneField(card, "enabled").checked,
      locked: sceneField(card, "locked").checked,
      reference_images: references,
    }),
  });
  card.querySelector(".scene-save-state").textContent = "Đã lưu";
}

function createSceneCard(scene) {
  const card = document.createElement("article");
  card.className = "scene-card";
  card.dataset.sceneId = scene.scene_id;
  const visual = document.createElement("div");
  const platformNames = Object.keys(scene.images || {});
  const firstPlatform = platformNames[0] || "youtube";
  const image = document.createElement("img");
  image.alt = `Cảnh ${scene.index}`;
  image.src = scene.image_urls?.[firstPlatform] || "";
  visual.append(image);
  const evidence = document.createElement("p");
  evidence.className = "scene-evidence";
  const quote = (scene.evidence || []).map((item) => item.quote).filter(Boolean).join(" ");
  evidence.textContent = `Dòng ${scene.start_line}–${scene.end_line}: ${quote || scene.action}`;
  visual.append(evidence);
  const meaning = document.createElement("p");
  meaning.className = "hint";
  meaning.textContent = (scene.narrative_meaning || []).filter(Boolean).join(" · ");
  visual.append(meaning);

  const editor = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = `Cảnh ${scene.index} · ${scene.scene_id}${scene.characters?.length ? ` · ${scene.characters.join(", ")}` : ""}`;
  editor.append(title);
  const field = (labelText, name, value, multiline = false) => {
    const label = document.createElement("label");
    label.append(document.createTextNode(labelText));
    const input = multiline ? document.createElement("textarea") : document.createElement("input");
    input.dataset.field = name;
    input.value = value || "";
    label.append(input);
    editor.append(label);
    return input;
  };
  field("Địa điểm", "location", scene.location);
  field("Hành động và ý chính", "action", scene.action, true);
  const prompt = field("Prompt ảnh", "prompt", scene.prompts?.[firstPlatform] || "", true);
  prompt.classList.add("prompt-editor");
  field("Ảnh reference, phân cách bằng dấu ;", "references", (scene.reference_images || []).join("; "));

  const toolbar = document.createElement("div");
  toolbar.className = "scene-toolbar";
  const select = (name, values, current) => {
    const element = document.createElement("select");
    element.dataset.field = name;
    for (const [value, label] of values) element.add(new Option(label, value));
    element.value = current || values[0][0];
    toolbar.append(element);
    return element;
  };
  const platform = select("platform", platformNames.map((item) => [item, item.toUpperCase()]), firstPlatform);
  platform.addEventListener("change", () => {
    prompt.value = scene.prompts?.[platform.value] || "";
    image.src = scene.image_urls?.[platform.value] || "";
  });
  select("tone", [["source", "Tông theo truyện"], ["dark", "Tối"], ["neutral", "Trung tính"]], scene.tone);
  select("camera", [["source", "Góc máy theo cảnh"], ["wide", "Toàn cảnh"], ["medium", "Trung cảnh"], ["close", "Cận cảnh"]], scene.camera);
  const order = document.createElement("input");
  order.type = "number"; order.min = "1"; order.value = scene.order || scene.index; order.dataset.field = "order";
  order.title = "Thứ tự"; toolbar.append(order);
  for (const [name, labelText, checked] of [["enabled", "Dùng cảnh", scene.enabled !== false], ["locked", "Khóa cảnh", Boolean(scene.locked)]]) {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox"; input.dataset.field = name; input.checked = checked;
    label.append(input, document.createTextNode(labelText)); toolbar.append(label);
  }
  const save = document.createElement("button");
  save.type = "button"; save.textContent = "Lưu cảnh";
  save.addEventListener("click", async () => {
    save.disabled = true;
    try { await saveSceneCard(card); } catch (error) { card.querySelector(".scene-save-state").textContent = `Lỗi: ${error.message}`; }
    finally { save.disabled = false; }
  });
  const rerender = document.createElement("button");
  rerender.type = "button"; rerender.textContent = "Render lại cảnh này";
  rerender.addEventListener("click", async () => {
    rerender.disabled = true;
    try {
      await saveSceneCard(card);
      await api(`/api/jobs/${editorJob}/storyboard/rerender`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({scene_id: scene.scene_id, platform: platform.value}),
      });
      card.querySelector(".scene-save-state").textContent = "Đang render lại…";
      setTimeout(() => loadSceneEditor(editorJob), 3000);
    } catch (error) {
      card.querySelector(".scene-save-state").textContent = `Lỗi: ${error.message}`;
    } finally { rerender.disabled = false; }
  });
  const state = document.createElement("span");
  state.className = "scene-save-state";
  state.textContent = scene.render_status === "failed" ? `Render lỗi: ${scene.render_error || ""}` : scene.render_status || "";
  toolbar.append(save, rerender, state);
  editor.append(toolbar);
  card.append(visual, editor);
  return card;
}

async function loadSceneEditor(jobId) {
  editorJob = jobId;
  try {
    const data = await api(`/api/jobs/${jobId}/storyboard`);
    $("sceneCards").replaceChildren(...data.scenes.map(createSceneCard));
    $("sceneEditor").hidden = false;
    const running = data.scenes.some((scene) => ["queued", "running"].includes(scene.render_status));
    $("sceneEditorStatus").textContent = `${data.scenes.length} cảnh · chất lượng ${data.quality || ""}${running ? " · đang render lại" : ""}`;
    if (running) setTimeout(() => loadSceneEditor(jobId), 4000);
  } catch {
    $("sceneEditor").hidden = true;
  }
}

async function poll() {
  if (!currentJob) return;
  try {
    const job = await api(`/api/jobs/${currentJob}`);
    $("progress").value = job.percent || 0;
    $("percent").textContent = `${Number(job.percent || 0).toFixed(1)}%`;
    $("jobStatus").textContent = `${job.stage}: ${job.message}`;
    $("logs").textContent = (job.logs || []).join("\n") || "Đang chờ nhật ký…";
    $("logs").scrollTop = $("logs").scrollHeight;
    if (job.elapsed > 1 && job.status === "running") {
      $("jobTiming").style.display = "";
      $("elapsed").textContent = formatTime(job.elapsed);
      $("eta").textContent = formatTime(job.eta);
    }
    if (job.status === "completed") {
      const completedJob = currentJob;
      setBusy(false);
      $("jobTiming").style.display = "none";
      localStorage.removeItem("spalingJob");
      for (const [key] of Object.entries(job.outputs || {})) {
        const link = document.createElement("a");
        link.href = `/api/jobs/${currentJob}/files/${key}`;
        link.textContent = `Mở ${key.toUpperCase()}`;
        link.target = "_blank";
        $("outputs").append(link);
      }
      await loadSceneEditor(completedJob);
      currentJob = "";
      return;
    }
    if (job.status === "failed" || job.status === "cancelled") {
      setBusy(false);
      $("jobTiming").style.display = "none";
      $("resume").hidden = false;
      return;
    }
    setTimeout(poll, 2000);
  } catch (error) {
    if (error.message && error.message.includes("Không tìm thấy job")) {
      currentJob = "";
      localStorage.removeItem("spalingJob");
      setBusy(false);
      $("jobStatus").textContent = "Job cũ đã mất (server khởi động lại). Sẵn sàng tạo job mới.";
      return;
    }
    $("jobStatus").textContent = `Mất kết nối: ${error.message}`;
    setTimeout(poll, 4000);
  }
}

$("cancel").addEventListener("click", async () => {
  if (!currentJob) return;
  $("cancel").disabled = true;
  try {
    await api(`/api/jobs/${currentJob}/cancel`, {method: "POST"});
    $("jobStatus").textContent = "Đang dừng tác vụ…";
  } catch (error) {
    $("jobStatus").textContent = `Không thể huỷ: ${error.message}`;
    $("cancel").disabled = false;
  }
});

$("resume").addEventListener("click", async () => {
  if (!currentJob) return;
  $("resume").disabled = true;
  try {
    await api(`/api/jobs/${currentJob}/resume`, {method: "POST"});
    setBusy(true);
    poll();
  } catch (error) {
    $("jobStatus").textContent = `Không thể tiếp tục: ${error.message}`;
  } finally {
    $("resume").disabled = false;
  }
});

async function reconnectJob() {
  if (!currentJob) {
    try {
      const active = await api("/api/jobs/active");
      currentJob = active.job?.id || "";
      if (currentJob) localStorage.setItem("spalingJob", currentJob);
    } catch {}
  }
  if (currentJob) {
    setBusy(true);
    poll();
  }
}

async function loadSessions() {
  try {
    const result = await api("/api/jobs");
    $("sessionList").replaceChildren();
    for (const job of result.jobs || []) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${job.id} · ${job.status} · ${Number(job.percent || 0).toFixed(1)}%`;
      button.addEventListener("click", () => {
        currentJob = job.id;
        localStorage.setItem("spalingJob", currentJob);
        setBusy(job.status === "queued" || job.status === "running");
        poll();
      });
      $("sessionList").append(button);
    }
    if (!(result.jobs || []).length) $("sessionList").textContent = "Chưa có phiên.";
  } catch (error) {
    $("sessionList").textContent = `Không tải được phiên: ${error.message}`;
  }
}

reconnectJob();
loadSessions();
loadConfig().catch((error) => {
  $("system").textContent = `Không tải được cấu hình: ${error.message}`;
});
