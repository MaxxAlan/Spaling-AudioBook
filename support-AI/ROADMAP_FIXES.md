# Roadmap chỉnh sửa sau E2E Test

Ưu tiên theo mức độ chặn production. Mỗi mục có tiêu chí Done rõ ràng.

---

## Sprint 1 – Unblock reliable mock e2e (3–5 ngày)

### 1.1 Contract test cho storyboard-qa.json
- [ ] Định nghĩa schema chung (JSON Schema hoặc Zod export)
- [ ] Python `_final_audit` validate bằng schema, message lỗi rõ
- [ ] Unit test: load fixture QA array → audit pass/fail
- **Done khi:** đổi field `approved` → fail test ngay, không còn AttributeError

### 1.2 smoke-test ổn định
- [ ] Không hardcode `chapter1.txt`; nhận `--chapter` hoặc auto-detect trong `testing/`
- [ ] Khi `--mock` và `dist/` thiếu → dùng mock JS fallback (không gọi `pnpm build`)
- [ ] Ghi output mặc định vào `artifacts/smoke-test/`
- **Done khi:** `python audiobook.py smoke-test --mock --force` chạy xanh trên máy sạch

### 1.3 Giảm over-segmentation
- [ ] Log distribution độ dài segment
- [ ] Merge narration ngắn liền kề (< 80 ký tự) trước TTS
- [ ] Target: chương ~50k chars → **40–100 segments** (không phải 400)
- **Done khi:** chapter2 mock chạy < 120 segments và audio vẫn liền mạch

### 1.4 Mock duration realistic hơn
- [ ] Bỏ hoặc nới `mock_max_duration_seconds=0.12`
- [ ] Scale theo độ dài text (ví dụ 80–120 chars/s) với trần 2–3s/segment khi mock
- **Done khi:** chapter2 mock audio ≥ 8–12 phút (đủ để test timeline ảnh/video)

---

## Sprint 2 – TTS & Character quality (1–2 tuần)

### 2.1 Dialogue / speaker parser
- [ ] Sửa cắt speaker (`Amos đột` → `Amos`)
- [ ] Tách attribution khỏi `text` dialogue
- [ ] Normalize tên (Roslet.James.P, Amos Rosselt, Thomas…)
- [ ] Fixture test từ chapter2 (ít nhất 15 dialogue mẫu)
- **Done khi:** ≥ 90% dialogue chapter2 gán đúng speaker

### 2.2 Character cast → voice assignment
- [ ] `CharacterDetector` đổ vào `character_cast` trong manifest
- [ ] Map speaker → voice_id từ `default_voice_profiles.json`
- [ ] Narration = narrator voice; dialogue = character voice
- **Done khi:** manifest.character_cast khác null; WAV segments dùng nhiều voice_id

### 2.3 Semantic QA path
- [ ] Document rõ khi nào semantic bật (cần faster-whisper)
- [ ] Trong mock: optional fake semantic score để exercise retry path
- [ ] Retry chỉ segment fail, không chạy lại cả chương
- **Done khi:** cố ý fail 1 segment → pipeline retry đúng segment đó

---

## Sprint 3 – Storyboard / Image pipeline (1–2 tuần)

### 3.1 Build & mock fallback
- [ ] Release ship sẵn `poster-generator/dist/`
- [ ] `--mock` không phụ thuộc pnpm/tsc
- [ ] `doctor` phân biệt “thiếu build” vs “thiếu model”
- **Done khi:** clone mới + `--mock` không cần `pnpm install`

### 3.2 Scene selection quality
- [ ] Golden test: chapter2 phải cover các beat:
  - Nghi lễ Rửa Hồn / mắt đỏ
  - Đối thoại Amos–Thomas (Teident, Vực Thẳm Ấn)
  - Dấu chân tím trên cát đỏ + Nuil/Emily/Mira
  - Chó địa ngục + pháp lực bảo vệ
  - Hạ cánh phương Bắc + bẻ kết giới
  - Ice Golem + dung hợp Vực Thẳm Ấn
- [ ] Ranking không chỉ đều theo dòng
- **Done khi:** với `--images 8`, ≥ 6/8 beat trên xuất hiện trong storyboard.json

### 3.3 Image QA robustness
- [ ] Đồng bộ field naming (`sceneId` vs `scene_id`) một lần ở biên TS→Python
- [ ] QA fail → message chỉ rõ scene + reason, không crash audit
- **Done khi:** cố ý `approved:false` một scene → lỗi rõ, không traceback

---

## Sprint 4 – Video + Resilience (1 tuần)

### 4.1 Video e2e với mock images
- [ ] Chạy `--mock` **có video** (bỏ `--no-video`)
- [ ] Kiểm tra duration mapping scene↔audio
- [ ] CPU libx264 fallback khi không có NVENC
- **Done khi:** ra file MP4 playable, độ dài ≈ audio

### 4.2 State / cache resilient writes
- [ ] Atomic write (temp + rename) cho state & cache index
- [ ] Retry 2–3 lần khi OSError
- [ ] Message: “Không ghi được state tại path X – kiểm tra quyền/ổ đĩa”
- **Done khi:** không còn traceback trần `Errno 5` từ state_manager

### 4.3 Resume mid-job
- [ ] Nếu đã có segment cache → skip synthesize
- [ ] CLI flag `--resume` rõ ràng
- **Done khi:** dừng giữa chừng + chạy lại chỉ làm phần còn lại

---

## Sprint 5 – Hardening & CI (1 tuần)

### 5.1 CI smoke
- [ ] GitHub Action: install deps tối thiểu → `smoke-test --mock`
- [ ] Upload artifacts (manifest, quality report)
- **Done khi:** PR đỏ nếu smoke-test fail

### 5.2 support-AI / testing fixtures
- [ ] Giữ `testing/master.md`, `request.md`, chapter ngắn + chapter2
- [ ] `support-AI/` chứa report + roadmap (thư mục này)
- [ ] README trỏ tới cách chạy e2e
- **Done khi:** contributor mới chạy được e2e trong < 10 phút

### 5.3 Observability
- [ ] Tách log human vs `@@progress` machine
- [ ] Summary cuối: số segment, số scene, duration, QA pass rate
- **Done khi:** một dòng summary đủ để biết job OK/FAIL

---

## Thứ tự thực hiện đề xuất

```
Sprint 1 (contract + smoke + segment) 
    → Sprint 2 (TTS/character) 
        → Sprint 3 (storyboard quality) 
            → Sprint 4 (video + resume) 
                → Sprint 5 (CI)
```

Không làm song song quá nhiều: mỗi sprint phải có e2e mock xanh trước khi sang sprint sau.

## Metric mục tiêu sau khi xong roadmap

| Metric | Hiện tại (mock) | Mục tiêu |
|--------|------------------|----------|
| Segments / chapter50k | ~400 | 40–100 |
| character_cast | null | populated |
| smoke-test | cần dist + path cố định | 1 lệnh, zero model |
| QA crash | có (schema) | 0 |
| Video mock e2e | chưa | pass |
| Speaker accuracy (chapter2) | ~70–80% ước lượng | ≥ 90% |
