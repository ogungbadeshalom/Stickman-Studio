# POV "LEVELS" LONG-FORM VIDEO PIPELINE — BUILD SPEC

**For:** coding agent (OpenCode / Claude Code / Hermes)
**Owner:** Shally · **Spec date:** 2026-09-19 · **Status:** research-backed spec, Phase 0 must run before heavy coding
**Reference channels studied:** https://www.youtube.com/@MoneyLifePOV · https://www.youtube.com/@POVFinanceUS
**Image engine (fixed):** ALL images (scenes, backgrounds, character poses, thumbnails if generated) come from **Google Flow (Nano Banana)** on Shally's existing account, via the existing T470 batch tool. No other image provider is to be added. See §5A.
**Goal:** an original channel in the same *genre* (animated, second-person "POV: your life at every level of X" finance stories), produced by a resumable, mostly-automated pipeline with human approval gates. NOT a clone.

---

## 0. Agent operating rules (read first)

1. **Phase 0 first.** Do not build the script/asset stages until `docs/format_bible.md` exists (§3), unless Shally says to skip it.
2. **Reuse before you build.** Existing ZENN code (§5) and open-source repos (§6) come first. Before depending on any repo: check last commit date, license, open issues, and write the result to `docs/deps.md`. Repo facts in this doc were gathered on 2026-09-19 and may be stale.
3. **Every stage is idempotent and resumable.** Each stage reads a JSON artifact, writes a JSON artifact + files, and records status in `projects/<slug>/manifest.json`. Re-running a finished stage is a no-op unless `--force`.
4. **$0 by default, paid by config.** Default providers must be free/local where quality allows (Gemini free tier, Kokoro, Flow batch, Remotion free license). Paid providers plug in behind the same interfaces via env.
5. **Human gates are mandatory, not optional:** G1 topic+outline, G2 script, G3 final video. Nothing uploads publicly without G3. Default upload privacy = `private`.
6. **Don't copy the reference channels.** No reuse of their scripts, wording, characters, art, thumbnails, channel name, or description boilerplate. §4 lists the differentiation requirements.
7. **Log decisions.** Anything you decide without asking goes into `DECISIONS.md` (date, decision, why). Ask Shally only for true blockers.
8. **Images = Google Flow only.** Design every image stage around Flow's real constraints (§5A): daily credit limits, browser-automated batch tool, no official image API in this workflow. Do not add Imagen/Midjourney/OpenAI/etc. Do not call the Gemini API for image *generation* (the Gemini API is used only for text and vision QA).
9. **Test with stubs first.** Every provider (LLM, TTS, image, upload) has a `stub` implementation so the full pipeline can dry-run at zero cost.

---

## 1. Product definition

**Input:** a topic (e.g. "every level of debt") + optional angle.
**Output:** one 16:9, 1080p, ~8–15 min 2D-animated video (length is a config, confirmed in Phase 0), plus thumbnail, 3 title candidates, description with chapters + disclaimers, and a private YouTube upload.

**Success metrics (pipeline):**
- Script→publish for one video in ≤ 1 working day of wall-clock, ≤ 30 min of human attention (mostly gate reviews).
- ≥ 90% of scene images pass automated audio-match QA on first pass (existing `qa_images.py`), ≥ 98% after one regen round.
- Zero un-sourced numeric claims in the final script (claims ledger, §8 S1/S4).
- Full pipeline is resumable: killing it at any stage and re-running loses no completed work.

---

## 2. What I found about the two reference channels

### 2.1 Verified (from channel pages / search snippets, 2026-09-19)
- **@POVFinanceUS ("POV Finance")** describes itself as *2D animated stories told from a POV perspective* that place the viewer inside financial scenarios (inheriting $1M, investing from 18, debt spiralling). Educational-and-entertainment disclaimer, "not financial advice."
- **@MoneyLifePOV ("Money Life POV")** describes *POV-style content* on money, lifestyle, income levels, spending habits, mistakes, side hustles, investing concepts, and money mindset. Same disclaimer.
- **Title pattern (very consistent):** `POV: Your Life at Every Level of {WEALTH | BANKING POWER | ...}` with a subtitle after an em-dash, e.g. "…From Nothing to Generational", "…From Debtor to Owner". Also `POV You Adopted the … Mindset — Your Life Changed`.
- **Description pattern:** POV Finance descriptions reuse near-identical boilerplate ("you'll see what changes when you build real financial knowledge…"). At least one video description promotes a **free "POV Wealth Calculator"** on the channel's own site → the channel uses a lead-magnet funnel.
- Sample POV Finance video URLs seen (titles/dates only, not watched): DmHGvjz3qBU (Apr 13 2026), CFjY7T6mjMg (Apr 10 2026), avWK82b0fUU.

### 2.2 NOT verified — I could not watch the videos
YouTube returned 429s for video pages and blocks RSS for automated fetching, so I have **no observed data** on: runtime, words-per-minute, voice, music, cut rate, art style details, number of levels per video, retention structure, thumbnail style, upload cadence, view counts. **Do not treat §2.4 as fact.** Phase 0 exists to replace guesses with measurements.

**Follow-up attempt:** I tried the `/watch` approach (yt-dlp + ffmpeg, the engine behind `bradautomates/claude-video`) from my own sandbox. YouTube is not reachable from there (its network allowlist blocks it; yt-dlp failed on certificate errors), and I did not try to bypass that. So the video study must run **on Shally's machine, with his agent**, using the workflow in §3.0.

### 2.3 Genre context (third-party, treat as directional)
- The "POV: your life as every level/rank of X" animated format is a broader trend in 2026 (other channels in the same lane use "Every Level of Wealth/Luxury/Debt/Career/Financial Power" titles). Expect saturation → differentiation matters more than production speed.
- Finance is a high-RPM faceless niche but has the highest accuracy/credibility requirement.

### 2.4 Working hypothesis: "Format Bible v0" (UNVERIFIED — confirm in Phase 0)
```
TITLE      POV: Your Life at Every Level of {X} — {From A to B}
LENGTH     8–15 min (?)
HOOK       0:00–0:30 cold open, second person, present tense, high-stakes or curiosity
LADDER     N levels (6–10?), each = level card (name + threshold number)
           + 45–90s "day in your life" vignette (wake up, money decision, spending moment)
           + a "what changed / what it costs" turn
ESCALATION environments, wardrobe, stakes, and emotional tone change per level
PAYOFF     twist at the top ("the hidden level" / "what nobody tells you") + lesson
CTA        subscribe + lead magnet (calculator / newsletter) + disclaimer
VOICE      calm, slightly deadpan second-person narration
VISUAL     flat 2D animation, one recurring "you" avatar moving through escalating scenes
```

---

## 3. Phase 0 — Reference study (agent + Shally, ~half a day)

**Deliverable:** `docs/format_bible.md` with measured targets replacing §2.4. Also `docs/reference/metrics.csv`.

**Legal/ToS rule:** reference material is for **private study only**. Never keep, re-host, or re-use reference video/audio/frames/scripts in the product; delete working files after analysis. Two tiers, Shally chooses:
- **Lower-risk (default):** captions/transcript + metadata only (`--detail transcript`, no video download) plus Shally's own screenshots.
- **Frame analysis (Shally's call):** temporary local download + frame extraction via `/watch` (§3.0). Note that downloading videos with yt-dlp may conflict with YouTube's Terms of Service; keep it to a handful of videos, temp dir only, delete afterwards.

### 3.0 Let the agent actually watch the videos: `bradautomates/claude-video` (`/watch`)
- **What it is (verified 2026-09-19):** an MIT-licensed Agent Skill (17k+ stars) that takes a URL or local file, gets captions via `yt-dlp` (Whisper via Groq/OpenAI only if there are none), extracts frames with `ffmpeg` (scene-aware or keyframes, near-duplicate frames dropped), and hands timestamped frames + transcript to the model, which reads each frame as an image.
- **Install:** Claude Code: `/plugin marketplace add bradautomates/claude-video` then `/plugin install watch@claude-video`. Other Agent-Skills hosts (Codex, Cursor, Gemini CLI, etc.): `npx skills add bradautomates/claude-video -g`. Needs `yt-dlp` + `ffmpeg` on the machine. If the agent host doesn't support skills, run `skills/watch/scripts/watch.py` directly and feed the printed frame paths + transcript to any vision-capable model.
- **Requires a vision-capable model.** If the agent's default LLM cannot read images, run this step in a vision-capable host/model (e.g. Claude Code, or Gemini via the existing API key) and save the resulting notes as files; the rest of the pipeline can continue on any model.
- **Detail modes to use:** `--detail transcript` for all ~30 videos per channel (cheap); `--detail balanced` (scene-aware, ~100 frames) for the 5 key videos per channel; `--start/--end` to zoom into the hook (first 60 s), one level card, one transition, and the ending; `--resolution 1024` when reading on-screen numbers/text.
- **Prompts to run per key video** (save outputs to `docs/reference/<channel>/<video_id>.md`, no copied frames or long quotes):
  1. "Break down the structure with timestamps: hook, each level, transitions, payoff, CTA. Give durations."
  2. "Describe the art style (line weight, palette, character design, backgrounds), motion types (zoom/pan/parallax/character animation), cuts per minute, on-screen text/numbers/charts."
  3. "Describe the narration (pace, tone, second-person usage, sentence length, pauses), music and SFX."
  4. "Where would retention likely dip and why? What feels templated?"
- **Aggregate** the per-video notes into `docs/format_bible.md` (§3.3).

### 3.1 Agent tasks
1. **Metadata.** For each channel, use `yt-dlp` with `--skip-download --write-info-json --write-auto-subs --sub-langs en` on the ~30 most recent long-form videos. Record: title, duration, upload date, view count, like count, chapters, description, tags.
2. **Title/description analysis.** Extract title templates, subtitle patterns, description structure, CTA/link patterns, chapter usage. Output a template inventory (do not reuse strings verbatim).
3. **Transcript analysis (LLM).** For 8 videos per channel, produce a segment map: hook length (sec/words), number of levels, words per level, WPM (words ÷ duration), second-person ratio, sentences per level, number of numeric claims, open loops, CTA position, ending type. Aggregate to ranges.
4. **Performance mapping.** Views vs. duration vs. topic vs. title template → which topics/levels outperform (small-sample; label as directional).
5. **Cadence.** Uploads per week, day/time pattern.

### 3.2 Shally tasks — fallback if `/watch` can't be used (≈10 min per video, 5 videos per channel); otherwise only review the agent's notes for errors
For each video, fill: (a) art style notes (line weight, palette, character design, backgrounds), (b) approx. cuts per minute (count for 60 s), (c) motion types seen (pan/zoom/parallax/character animation/none), (d) on-screen text/level cards/numbers/charts, (e) voice (gender, pace, accent, TTS or human?), (f) music/SFX usage, (g) captions yes/no, (h) where retention likely dips, (i) what feels templated. Optionally screenshot every ~10 s for 2 videos so the agent can run a vision-model style/cut-rate analysis.

### 3.3 Output must include
Target ranges for: duration, levels/video, words/level, WPM, cuts/min, image duration, hook length, chapter count, CTA placement; a **differentiation plan** (what we do differently, §4.1); a **level taxonomy** for 20 candidate topics of our own.

---

## 4. Guardrails: originality, YouTube policy, finance compliance

### 4.1 Differentiation requirements (build these into the pipeline, not just the prompts)
- **Own character:** use the ZENN stickman as "you" (own palette/line style). Never imitate the reference characters.
- **Own voice & structure:** ≥ 3 rotating structural templates (ladder, before/after split, "one day, five incomes" etc.) so videos are not interchangeable.
- **Own taxonomy & angle:** each video needs a unique thesis and at least 3 researched, sourced facts not found in the reference videos.
- **No copied strings:** a checker (`tools/originality_check.py`) fails a script/title/description if it has > N-gram overlap with the Phase 0 reference corpus (default: any 8-word shingle match).

### 4.2 YouTube "inauthentic content" risk
Third-party summaries (July 2026) agree YouTube renamed "repetitious content" to "inauthentic content" (July 2025) and targets **mass-produced/templated** uploads for Partner Program monetization; AI tooling itself is not the trigger, lack of original human editorial input is. The "levels of X" format is inherently templated → this is the main business risk. **Read YouTube's official policy pages yourself before building the publish stage** (summaries conflict on details) and encode the result in `docs/policy_checklist.md`. Pipeline responses:
- G1/G2/G3 human gates with an **approval log** (`projects/<slug>/approvals.json`: who, when, what changed).
- `MAX_UPLOADS_PER_WEEK` (default 2) enforced by the publish stage.
- Structural-template rotation (§4.1) and unique per-video research pack.
- Description generator must not reuse a fixed boilerplate paragraph across videos.
- **Disclosure:** for each video, run the "altered or synthetic content" checklist from YouTube's official help page and store the decision in `projects/<slug>/disclosure.json`. Clearly animated/unrealistic content generally does not need the label per third-party summaries, but sources conflict on synthetic voices → default to the conservative choice until Shally decides.

### 4.3 Finance compliance
- Educational framing; **no personalized advice**, no guarantees, no specific security recommendations.
- Disclaimer in: first ~30 s (spoken or on-screen), description, pinned comment.
- **Claims ledger:** every number/percentile/threshold in the script has `{claim, value, source_url, source_name, retrieved_on, jurisdiction, as_of_date}`. Prefer primary sources (Federal Reserve Survey of Consumer Finances, BLS, Census, IRS, equivalent national stats). The script generator may only use numbers present in the ledger.
- Tag each video's jurisdiction (US default). Never mix US thresholds into a non-US video.
- Affiliate/sponsor links must be disclosed as such; a "not financial advice" line does not replace that.

### 4.4 Licensing
- Remotion: free for individuals and for-profit orgs up to 3 employees; company license required above that. Re-check the license page if the team grows or if this becomes a product.
- Kokoro TTS weights: Apache-2.0.
- Music/SFX: only licensed or CC0 sources; record license + URL per track in `projects/<slug>/credits.json`. Avoid models/assets with non-commercial licenses.
- Fonts: OFL/Apache only.

---

## 5. Existing assets to reuse (ZENN pipeline)

Already built (see earlier deliverables): `zenn_style.py`, `phase1_script.py`, `flow_stage.py`, `qa_images.py`, and the T470 Google Flow batch tool `flow-batch-gen.ps1`.

| Existing piece | Role in long-form | Needed changes |
|---|---|---|
| `zenn_style.py` (locks, `render_action`, `validate_beats`, `enforce_shot_variety`, `full_motion_prompt`) | Image prompt builder + audio-match validator | Add `section_id`/`level_id`, `motion`, `beat_type` (scene / level_card / chart / text_overlay), pose-id support (Mode B). Keep functions backward compatible. |
| `phase1_script.py` v3 (writer → director → validate → repair → lint) | S5 (lines + beats). Three writer modes: `flat` (short explainers), `levels` (outline → one call per section; use for POV ladders when no approved script exists), `file` (`lines_file=` from the approved S3/S4 script — the normal long-form path) | Already done in v3: per-section writing, story lint, presence field, `storyboard.md` export. Still to do: scene count from audio duration, not `TARGET_SECONDS`. |
| `flow_stage.py` (one-line prompts, strict count checks, strict import, regen index map) | S6 Mode A image generation staging | Add batching/resume by section; keep strict 1:1 rules. |
| `qa_images.py` (Gemini vision QA + regen prompts) | S7 image QA | Add per-section pass-rate report; reuse as-is. |
| `ZENN_LOCK_MODE=ref` reference-image path | Best consistency for 100+ images | Prefer `ref` for long-form, backed by a Flow reusable character/element (§5A). Confirm the batch script can attach it on every generation; else `text` mode. |

**Baseline from the reviewed storyboard:** the POV Salary storyboard has **100 scenes / 1,143 narration words ≈ 7.6 min at 150 wpm (~4.6 s per image)**. Treat 100 Flow images as the baseline budget for an ~8-minute video; a 12-minute video needs either ~150 images or longer per-image holds (Mode B helps).

**Long-form scale problem:** at ~4 s/image a 12-min video needs ~180 images. Target **6–10 s average per image** (≈70–120 images) using camera motion (§10), and support **Mode B compositing** (S6) to cut Flow generation volume drastically.

---

## 5B. Reviewed storyboard: `POV_Salary_Storyboard.md` (what it shows, what was wrong)

**Format (keep it — it is a good human-review artifact):** one block per scene: `## Scene N — Title`, `- **Narration:**`, `- **Visual prompt:**`; header line with scene count, character lock, aspect. The pipeline now exports the same layout as `storyboard.md` (with a `# ▸ Section` header per level).

**Measured defects in the 100-scene file (script-checked, not eyeballed):**

| Defect | Count | Cause | Fix status |
|---|---|---|---|
| Entity ids in narration and prompts (`worn_sneakers`, `red_timeclock`, …) — TTS would read "underscore" aloud | 26 narration lines, 24 prompts | Writer used entity ids as words | **Fixed in code** (`clean_text`, writer rule, `story_lint: id_leak`) |
| `The the character is also in frame` | 52 | A find-replace of "stickman" → "the character" over hard-coded strings | **Fixed:** protagonist name is configurable (`ZENN_CHARACTER_FILE`), no hard-coded "stickman" |
| Double period after entity descriptions (`duct tape..`) | 27 | Description ended with "." and the builder added another | **Fixed** |
| Repeated phrases in prompts (`… mahogany table during a meeting a long mahogany table …`) | several (e.g. scenes 65, 69, 89, 90) | `object`/`setting` repeated what `action` already said | **Fixed** (deterministic de-dup + director rule) |
| Protagonist forced into every frame as "also in frame, neutral" | 52 scenes; "neutral" is the mood in 26 scenes overall | Old beat schema had no way to say "not in shot" | **Fixed:** `presence = full | partial | none` (partial = first-person POV, hands only — fits the POV genre) |
| Locked outfit contradicts an entity (white sneakers vs "faded blue sneakers… duct tape") | 7 prompts | Entity described something the character wears | **Fixed:** conflicting entities are dropped with a warning; writer told not to make them |
| Narration reads like image captions, not narration (object as subject, no "you") | 53 / 100 lines; 61 start with "A" | Writer rule "DRAWABLE, name concrete things" | **Fixed for long-form** via the `levels`/`file` writers (second-person, varied openers) + lint gate |
| Almost no numbers or salaries in a video titled "Every Level of Salary" | 9% of lines | No level structure or labels in the writer | **Fixed for long-form:** outline gives every level a label; numbers only from labels/ledger |
| Story loops: scene 64 re-does scene 1 (rusty alarm clock, 4 a.m.); scenes 62–68 replay the poverty stage again; scene 61 (golden toilet, $1M) sits in the middle of it | — | One giant 100-line call drifts | **Fixed:** per-section calls that see all previous lines + repeat lint + one rewrite round |
| Ladder is unbalanced: roughly scenes 1–60 stay in the bottom (poverty / gig-work) stage, and every higher level is crammed into the last ~30 scenes | — | No per-level scene budget | **Fixed:** outline `scenes` budgets per section (comparable, summing to N) |
| No level cards / no level boundaries in the data | — | No section ids | **Fixed:** `section_id`/`level_id` carried in `beats.json` and `storyboard.md` |

**Still a human/design decision (not code):**
1. **Outfit per level.** The character wears the same charcoal tee/navy jeans from broke to billionaire. If the video should visually escalate, create 2–3 outfit tiers as separate Flow reusable characters/references and pick per level (`level_outfit` in the outline).
2. **Off-white vs full-bleed backgrounds.** The built-in style says "off-white background"; this storyboard uses full settings. Set `ZENN_BACKGROUND="full-bleed simple flat-color background that matches the setting"` (or put it in the character profile) so the image model doesn't float objects on white.
3. **Numbers.** Level labels/salaries produced by the outline are placeholders until S1/S4 (claims ledger) verifies them.

---

## 5A. Google Flow constraints (the image engine)

**What I verified (2026-09-19; Flow changes fast, so re-check in the UI before standardizing):**
- Flow is Google's creative studio for Veo (video), Gemini and **Nano Banana** (images). Google announced Nano Banana 2 as Flow's default image model, available to Flow users at **zero credits**. Nano Banana models handle 16:9 output and multiple reference images.
- Flow supports generating from text, frames and **reference "ingredients"**, and creating **consistent elements/reusable characters**.
- Free plan = **50 daily credits** (no rollover); paid Google AI plans raise monthly credits. A single request can produce multiple generations and consume credits for each. Free tier lists 2K image upscaling.
- Independent overview says feature/credit availability varies by plan, platform and region → validate model, region and output settings before a large job.

**Design consequences (build these in):**
1. **One image per prompt.** Force outputs-per-prompt = 1 in the batch tool so credits/time aren't multiplied. Record the credit cost of one image in `docs/deps.md` after a 10-image test.
2. **Credit-aware scheduler.** `tools/flow_budget.py` computes images needed (scenes + regen allowance ~15%) vs. daily capacity, and splits generation into **day-sized batches**. The pipeline must pause/resume between days with no rework (manifest tracks each `scene_id → file`).
3. **Character consistency via Flow, not just text.** Create the ZENN stickman once as a Flow **reusable character/element** (or a reference ingredient) from an approved character sheet (`character_sheet_prompt()` in `zenn_style.py`). Do the same for recurring entities (e.g. "the front door", "the apartment"). Then use `ZENN_LOCK_MODE=ref`. **Confirm** the T470 batch script can attach the reference/element on every generation; if it cannot, fall back to `ZENN_LOCK_MODE=text` (short text lock) and log it.
4. **One Flow project per video** (or per section) so references and history stay together and files are easy to collect.
5. **Prompt length.** Keep prompts ≤ `ZENN_MAX_PROMPT_WORDS` (140). Long prompts previously caused transient `WireFormatError`.
6. **Aspect ratio & resolution.** Set 16:9 in Flow (not only in prompt text). Ken Burns zoom degrades low-res sources: require source width ≥ 1920 px *after* leaving motion headroom (max zoom ≈ 8–10%). Use Flow's 2K upscale where the plan allows; otherwise cap zoom and add a local sharpen step. Add an automated check that rejects images below the minimum size.
7. **The batch tool is a fragile, browser-driven component.** Wrap it behind an `ImageEngine` interface with three implementations: `flow_batch` (the T470 script), `manual_folder` (human pastes `flow_prompts.txt` into Flow and drops images in a folder; the existing strict import validates them), and `stub` (placeholder PNGs for dry runs). Because Flow's UI can change and automation can break, every run must degrade gracefully to `manual_folder`.
8. **Veo (video) is optional and credit-expensive.** Default motion = Remotion camera moves on stills. Allow Veo "frames-to-video" only for flagged hero beats (`beat.hero=true`), capped by `FLOW_VIDEO_CREDIT_CAP`, never in the default path.
9. **Regen budget.** Regeneration (S7) consumes credits; cap rounds (`QA_MAX_REGEN_ROUNDS=2`) and report credits used per video.
10. **Text in images.** Nano Banana renders text well but keep on-image text out of scenes; do numbers/level cards/thumbnail text in Remotion for crispness and editability.


---

## 6. Repo reference map (check before use; verified = seen in search results 2026-09-19)

| Repo | What it is | License / status | Use | Where |
|---|---|---|---|---|
| **remotion-dev/remotion** | Programmatic video in React; renders MP4 | Source-available; free for individuals & ≤3 employees | **Use entirely** as the renderer | S11 |
| **remotion-dev/skills** (+ `remotion.dev/docs/ai/skills`) | Official agent skills (create, markup, render, docs lookup) | Updated days ago (verified) | **Install for yourself** before writing any Remotion code; run `/remotion-docs` for current APIs | S10–S11 |
| **digitalsamba/claude-code-video-toolkit** | Skills + slash commands + reusable components/transitions/theme system + multi-session project lifecycle for Remotion/FFmpeg | Verify license/activity | **Parts:** steal project-lifecycle pattern, theme/brand-profile system, transition components | S11, repo layout |
| **hexgrad/kokoro** (`hexgrad/Kokoro-82M`) | 82M-param open TTS, CPU-friendly, ~1000 chars ≈ 1 min audio, 24 kHz, 4096-token context (chunk by line) | Apache-2.0 (verified) | **Use entirely** as default TTS behind a provider interface | S8 |
| **m-bain/whisperX** | Whisper + wav2vec2 forced alignment → accurate word timestamps | Verify license; GPU-oriented | **Parts:** alignment approach; on a CPU box prefer `SYSTRAN/faster-whisper` (WhisperX's backend) with `word_timestamps=True`, or TTS-native timestamps if available | S9 |
| **gyoridavid/short-video-maker** | Text+searchTerms scenes → Kokoro-js TTS → whisper.cpp captions → Remotion render; REST + MCP server; Docker | MIT per fork README; upstream activity looked old (Pinokio index 2025-06) → verify. Vertical/short, English only, Pexels stock footage | **Parts only:** scene schema, Remotion caption timing from whisper.cpp, REST/MCP job API shape, Docker packaging. **Not** the stock-footage path | S9, S11, API |
| **harry0703/MoneyPrinterTurbo** | Topic → script → footage → subtitles → music → short video; WebUI + API | Very active (release within days, verified); check license | **Parts:** multi-provider LLM abstraction, multi-provider TTS list (ElevenLabs/Chatterbox/Fish Audio paths), fix for measuring narration duration from the audio file (not subtitle cues), task API/state pattern, per-platform caption generation. **Not** for animation (stock-footage, short-form) | S3, S8, S13 |
| **kkm108/Autonomous-Faceless-Short-Form-Video-Automation** | Orchestrator with typed workflow manifest, crash-resume, whole-run lock, retry/backoff | Unknown maturity | **Pattern only** (manifest + resume + lock + retry). Do NOT copy its YouTube-Studio browser automation; use the official API | orchestrator |
| **bradautomates/claude-video** (`/watch`) | Agent Skill: yt-dlp + ffmpeg + captions/Whisper → frames + transcript into the model so it can "watch" a video | MIT, 17k+ stars (verified); Claude Code plugin + Agent-Skills installer | **Use entirely** for Phase 0 reference study and for S12 self-QA of our own renders (local file path) | Phase 0, S12 |
| **yt-dlp/yt-dlp** | Metadata/captions extraction | Well-known; verify | Phase 0 metadata/captions **only** | Phase 0 |
| **Breakthrough/PySceneDetect** | Shot/cut detection | Well-known; verify | Only on footage Shally supplies for personal study, or skip | Phase 0 |
| **danielgatis/rembg** | Background removal | Well-known; verify | Mode B: cut character poses to transparent PNG | S6 |
| **googleapis/google-api-python-client** | YouTube Data/Analytics API | Official | Upload + analytics | S14–S15 |

Rules: prefer **vendoring a small module** over adopting a whole framework; pin versions; never add a repo that requires a paid key by default.

---

## 7. Architecture

```
S0 Topic & angle ──G1──► S1 Research + claims ledger ► S2 Outline ──G1──►
S3 Script (section by section) ► S4 Fact/compliance/originality check ──G2──►
S5 Lines + beats (existing phase1) ► S6 Visuals (Google Flow: Mode A scenes | Mode B poses+plates)
   ► S7 Image QA + regen ► S8 TTS ► S9 Timing/alignment ► S10 Music/SFX/timeline
   ► S11 Render (Remotion) ► S12 Video QA ──G3──► S13 Thumbnail+metadata
   ► S14 Upload (private) ► S15 Analytics loop ► (S16 Shorts, optional)
```

**Stack decision (fits Shally's stack):** Python for AI/data stages (extends existing `stickman_studio`), a TypeScript **Remotion** project for rendering, communicating only through JSON files. Orchestration v1 = a Python CLI (`povlv run <slug> --to S11`) + `manifest.json`. v2 (optional) = BullMQ/Redis workers on Hetzner via Coolify for queuing multiple videos. Do not build v2 until v1 makes one full video.

```
projects/<slug>/
  project.json  manifest.json  approvals.json  disclosure.json  credits.json
  01_research/  claims.json  sources/
  02_outline/   outline.json
  03_script/    script.md  script.json
  04_beats/     lines.json  beats.json
  05_images/    flow_prompts.txt  flow_manifest.json  raw/  final/  qa_report.json
  06_audio/     lines/*.wav  narration.wav  words.json  music.json
  07_timeline/  timeline.json
  08_render/    segments/*.mp4  final.mp4  preview_720p.mp4
  09_publish/   titles.json  thumbnail.png  description.md  chapters.txt  upload.json
render/         (Remotion project)
src/povlv/      (python package, stages as modules)
tools/          originality_check.py  gallery.py  bench.py
docs/           format_bible.md  deps.md  policy_checklist.md
```

---

## 8. Stage specs

### S0 — Topic & angle
- **In:** seed topic or "suggest 10". **Out:** `project.json` {topic, angle, jurisdiction, template_id, target_minutes, thesis, forbidden_overlap_refs}.
- LLM proposes 10 angles from Format Bible taxonomy; rank by (novelty vs reference corpus, evidence availability, visual richness). **G1** picks one.

### S1 — Research pack + claims ledger
- Web-search/fetch primary sources; store snapshots in `sources/`. Output `claims.json` (schema in §9).
- Acceptance: ≥ 3 primary sources per level; every claim has a URL + date + as-of; a script generator later can *only* cite claim ids.

### S2 — Outline
- **Out:** `outline.json` = hook, N levels (name, threshold, one emotional beat, one money decision, one contrast with previous level, claim ids), twist/payoff, CTA, chapter titles. Pick template from rotation. **G1** approves.

### S3 — Script (long-form writer)
- Write **section by section** (hook, each level, payoff), not one giant call, passing the running summary + style guide + outline. Word budget per section from Format Bible WPM × target duration.
- Style: second person, present tense, concrete nouns/verbs (this feeds the existing audio-match director), one idea per sentence-pair, open loops between levels, no filler intros, no unsourced numbers (use `{{claim:id}}` placeholders resolved after check).
- Retention pass: LLM pass that flags flat stretches (> 60 s with no new information, number, or stakes change) and rewrites them.
- **Out:** `script.md` (human-readable with section headers) + `script.json` (sections → paragraphs).

### S4 — Fact / compliance / originality check
- Verify each `{{claim:id}}` against ledger; second LLM pass tries to find errors ("which statements could be false or misleading?").
- Checks: disclaimer present in first 30 s, no personalized advice phrasing, no guarantees, jurisdiction consistent, originality shingle check vs reference corpus.
- **Out:** `script.json` with `checks: {facts: pass|fail, compliance: ..., originality: ...}`. **G2** = human reads script.md and approves; log to `approvals.json`.

### S5 — Lines + beats (`phase1_script.py` v3)
- Normal long-form path: `run(topic, project_dir, lines_file="03_script/lines.json")` (mode `file`). Fallback when no approved script exists: `ZENN_WRITER_MODE=levels`.
- **Gate before S6:** `beats.json.lint` must contain none of `id_leak`, `near_duplicates`, `caption_style`, `openers`; `second_person`/`few_numbers` must be explained in `DECISIONS.md` or fixed; `unresolved` must be empty or waived. Read `storyboard.md` once (this is the review artifact).
- Split approved script into narration lines (1–2 sentences, ~8–18 words) preserving section/level ids. **Narration lines are the single source of truth for audio.**
- Director produces beats (existing fields) + new: `beat_type` (`scene|level_card|chart|text_overlay`), `section_id`, `motion` (`push_in|pull_out|pan_l|pan_r|parallax|static`), `pose_id` (Mode B), `chart_spec` (for finance charts: series, axes, highlight).
- Keep validator + repair loop. Add rule: each level's first beat is a `level_card`; chart beats only for numbers present in the claims ledger.

### S6 — Visuals (Google Flow only; two modes, pick by pilot)
Both modes generate **only through Flow** via the `ImageEngine` interface (§5A). Batches are sized by `tools/flow_budget.py`.

**Mode A — full-scene generation (existing ZENN → Flow):** `flow_stage.py` prompts, `ZENN_LOCK_MODE=ref` with the Flow reusable character/element, `ZENN_ASPECT="horizontal 16:9"`, one output per prompt. Batch by section; strict 1:1 count and strict import stay.

**Mode B — compositing (recommended for scale, still Flow-made assets):**
- **Pose library:** generate ~20–30 poses of the stickman in Flow (walking, sitting, pointing, shrug, panic, celebrating, counting money, etc.) on a flat, high-contrast solid background that shares no color with the character (the tee is green, so avoid green), then cut to transparent PNG with `rembg` (or color-key). Flow images have no alpha channel, so add an edge-quality check (no fringe/halo) and a human approval of the whole library once.
- **Background plates:** one Flow image per scene with **no character** ("empty room, …"), 16:9, same style lock.
- Remotion composes plate + pose (position/scale/bob). Benefits: near-perfect consistency, far fewer credits (poses are reused; only plates are new), easy per-line animation.
- Trade-off: less dynamic physical comedy than full scenes; keep Mode A for beats that need a unique interaction (`beat.needs_full_scene=true`).

**Pilot gate:** build one 90-second sample in each mode; compare Flow credits used, generation time, QA pass-rate, and human preference. Record in `DECISIONS.md`. A hybrid (Mode B default, Mode A for flagged beats) is expected to win.
**Intentional reuse** (a recurring motif such as "the front door") is allowed only when `beat.intentional_reuse = true`; otherwise the duplicate-image check fails the stage.

### S7 — Image QA + regen
- Existing `qa_images.py` (Gemini text/vision API, no image generation); thresholds `QA_MIN_MATCH=4`, `QA_MIN_CHAR=4`. Max 2 regen rounds (each regen costs Flow credits: report them). Add a min-resolution and aspect-ratio check before QA. Then `tools/gallery.py` builds a contact sheet (one HTML page, thumbnails + narration line) for a fast human skim.
- Acceptance: 100% scenes have an accepted image or an explicit human waiver.

### S8 — TTS
- Provider interface `synthesize(text, voice, speed) -> wav`. Default **Kokoro** (CPU). Synthesize **per narration line** (keeps each under context limits and gives exact per-line durations). Optional providers behind env: ElevenLabs, others.
- Normalize loudness (target roughly −14 to −16 LUFS integrated for the final mix; verify against YouTube's current guidance), trim silences, add configurable inter-line padding (0.15–0.4 s; longer at section changes).
- **Benchmark first:** measure real-time factor on the target box (`tools/bench.py`) and write it to `docs/deps.md`.
- Acceptance: no clipped audio, no line > 20 s, pronunciation dictionary for finance terms/numbers ("$1.2M", "401(k)", "APR") applied via a text-normalization pre-step.

### S9 — Timing & alignment
- Per-line duration from the wav file itself (not from subtitle estimates — a known source of drift). Word-level timestamps: TTS-native if available, else `faster-whisper` word timestamps on each line, matched to the script text.
- **Out:** `words.json` and a line table `{line_id, start, end, duration}`.
- Scene duration = line duration + padding; if a beat spans several lines (level card, chart), sum them.
- Acceptance: cumulative drift between audio and `timeline.json` < 1 frame per 60 s.

### S10 — Music, SFX, timeline assembly
- Music: licensed/CC0 track(s) per section mood, ducking under narration (−18 to −22 dB under voice), crossfades at section boundaries. SFX: minimal (whoosh on level card, cash/tick on number reveal) from a licensed pack.
- Build `timeline.json` (§9): the single input to the renderer.

### S11 — Render (Remotion)
See §10. Render in **segments per section** (frame ranges or separate compositions), concat with ffmpeg. Segment outputs make renders resumable. Also produce a 720p preview.
- **Benchmark first** on the target CPU box (Remotion `--concurrency`, `--scale`, codec, fps 24 vs 30); pick settings that render a 10-min video in an acceptable time and record them.

### S12 — Video QA (before G3)
Automated: duration within ±3% of audio; no black/frozen frames beyond tolerance (ffmpeg `blackdetect`/`freezedetect`); audio peak/loudness in range; chapter timestamps valid; sample 1 frame/10 s → vision-model check for text overflow, cut-off characters, wrong palette. Optional: run `/watch projects/<slug>/08_render/preview_720p.mp4` (`--detail balanced`) with a prompt like "compare what is shown against this script; list any scene where the picture doesn't match the narration, text is cut off, or the character looks different" (needs a vision-capable model). **G3:** Shally watches the full preview (or ≥ the hook, each level card, the ending) and approves.

### S13 — Thumbnail & metadata
- 3 title candidates (must match Format-Bible template *shape* but be textually original; pass originality check). 3 thumbnail concepts in our own visual identity: background/character art from Flow, **all text composed in a Remotion still** (crisp, editable). If YouTube's native thumbnail/title testing is available to the channel, prepare variants for it.
- Description: unique hook paragraph, disclaimers, sources list from the claims ledger, chapters from `timeline.json` (first chapter at 0:00, at least 3 chapters, each ≥ 10 s), lead-magnet link, affiliate disclosure if any.

### S14 — Upload (official API only)
- YouTube Data API `videos.insert` + `thumbnails.set`, default `privacyStatus=private`, resumable upload, retry with backoff. Verify current quota costs and **the API-project audit/verification requirement** (unverified API projects have historically had uploads locked to private) — document in `docs/deps.md`. Enforce `MAX_UPLOADS_PER_WEEK`. Write `upload.json` (video id, url, time).

### S15 — Analytics loop
- YouTube Analytics API (own channel): impressions CTR, average view duration/percentage, retention curve, traffic sources. Weekly job writes `analytics/<video>.json` and a one-page summary. Feed learnings to `docs/format_bible.md` (which hook length, level count, and title shapes perform). This is how the format evolves away from the references.

### S16 — Shorts repurposing (optional, later)
Re-render 9:16 compositions from the same `timeline.json` (highlight one level); reuse the existing ZENN Shorts flow rather than cropping 16:9.

---

## 9. Data contracts (JSON, keep stable; add `schema_version`)

```jsonc
// claims.json
{"schema_version":1,"claims":[{"id":"c001","claim":"…","value":"…","unit":"USD","source_name":"…",
  "source_url":"https://…","retrieved_on":"2026-09-19","as_of":"2025","jurisdiction":"US","used_in":["lvl3"]}]}

// outline.json
{"schema_version":1,"template_id":"ladder_v1","target_minutes":12,"hook":{"idea":"…"},
 "levels":[{"id":"lvl1","name":"…","threshold":"…","emotion":"…","decision":"…","contrast":"…","claim_ids":["c001"]}],
 "twist":"…","cta":"…","disclaimer_at":"0:20"}

// lines.json  (source of truth for audio)
{"schema_version":1,"lines":[{"id":"l0001","section_id":"hook","level_id":null,"text":"…"}]}

// beats.json  (extends existing structure)
{"schema_version":1,"entities":{"front_door":"…"},"beats":[{
  "line_id":"l0001","beat_type":"scene","subject":"the stickman","action":"…","object":"…","setting":"in …",
  "shot":"wide shot","pose":"deadpan","props":[],"entities":[],"metaphor":false,"on_screen_text":"",
  "motion":"push_in","pose_id":null,"chart_spec":null,"intentional_reuse":false,
  "presence":"full",              // full | partial (first-person hands) | none
  "needs_full_scene":false,"hero":false}]}

// timeline.json  (only input to Remotion)
{"schema_version":1,"fps":30,"width":1920,"height":1080,"audio":{"narration":"06_audio/narration.wav",
  "music":[{"file":"…","start":0,"end":720,"gain_db":-20}]},
 "scenes":[{"id":"s0001","line_ids":["l0001"],"start_s":0.0,"dur_s":6.4,"type":"scene",
   "image":"05_images/final/scene_001.png","motion":"push_in","pose":null,
   "text_overlay":null,"chart":null,"sfx":[{"file":"whoosh.wav","at_s":0.0}]}],
 "chapters":[{"title":"Level 1 — …","at_s":32.0}]}
```

---

## 10. Remotion project spec (`render/`)

- Use the official Remotion agent skills. Composition `LongForm` receives `timeline.json` as props (validate with zod). One `<Sequence>` per scene, durations from `dur_s × fps` (integers; carry rounding error forward so total frames match audio).
- **Components:** `SceneImage` (Ken Burns: push_in/pull_out/pan with easing, slow by default), `ParallaxScene` (layers, Mode B), `CharacterPose` (Mode B: position/scale/bob), `LevelCard` (animated level number + name + threshold), `NumberCounter` (animated money counters), `ChartScene` (line/bar/compound-growth chart driven by `chart_spec`), `TextOverlay`, `Transition` (cut/whip/fade; default hard cut, variety allowed), `Captions` (optional; word-highlight from `words.json`; default per Format Bible), `Disclaimer` (lower-third in first 30 s), `Outro`.
- Theme file: palette/fonts/spacing from ZENN style (own brand). No CSS animations; drive everything from frame number.
- Determinism: same `timeline.json` → same frames. Seed any randomness.
- Performance: cache decoded images; downscale source images to ≤ 2× output size; benchmark concurrency; render by section.

---

## 11. Config (env, `.env.example`)

```
LLM_PROVIDER=gemini            # gemini | deepseek | openai-compatible ; per-stage override e.g. LLM_SCRIPT_MODEL
GEMINI_API_KEY=  DEEPSEEK_API_KEY=
TARGET_MINUTES=12  JURISDICTION=US  TEMPLATE_ROTATION=ladder_v1,split_v1,oneday_v1
IMAGE_ENGINE=flow_batch        # flow_batch | manual_folder | stub  (Flow only)
IMAGE_MODE=A                   # A (Flow full scenes) | B (composite of Flow-made poses + plates)
FLOW_MODEL=nano-banana-2  FLOW_OUTPUTS_PER_PROMPT=1  FLOW_ASPECT=16:9  FLOW_UPSCALE=2K
FLOW_DAILY_IMAGE_CAP=       # set after measuring credits per image on your plan
FLOW_VIDEO_CREDIT_CAP=0     # Veo disabled by default
IMG_MIN_WIDTH=1920
ZENN_LOCK_MODE=ref  ZENN_ASPECT=horizontal 16:9  ZENN_MAX_PROMPT_WORDS=140
ZENN_WRITER_MODE=file          # file | levels | flat
ZENN_CHARACTER_FILE=character.json   # profile: name/short/style_short/sheet_long (see character.example.json)
ZENN_BACKGROUND=full-bleed simple flat-color background that matches the setting
QA_MIN_MATCH=4  QA_MIN_CHAR=4  QA_MAX_REGEN_ROUNDS=2
TTS_PROVIDER=kokoro  TTS_VOICE=af_heart  TTS_SPEED=1.0  LINE_PAD_MS=250  SECTION_PAD_MS=700
RENDER_FPS=30  RENDER_CONCURRENCY=auto  RENDER_SEGMENTED=1
YOUTUBE_CLIENT_SECRETS=  UPLOAD_PRIVACY=private  MAX_UPLOADS_PER_WEEK=2
STUB_PROVIDERS=0               # 1 = zero-cost dry run
```

---

## 12. Testing & acceptance

- **Unit:** validators (`validate_beats`, claims resolver, originality shingles, chapter builder, timeline builder). Golden JSON fixtures in `tests/fixtures/`.
- **Contract tests:** every stage validates its input/output JSON against schema; fail fast with a readable message.
- **Image engine tests:** `stub` engine returns deterministic placeholder PNGs; `manual_folder` path validated with the strict importer (missing/duplicate/reused/undersized files must abort).
- **Stub dry-run:** `STUB_PROVIDERS=1 povlv run demo --to S14` must complete with placeholder images/tone audio and a rendered ≤ 20 s video, proving orchestration + resume (kill mid-run, re-run, no rework).
- **90-second pilot:** hook + 1 level + ending with real providers before any full video.
- **Regression:** re-running S5 on the same lines yields identical prompts (determinism).

---

## 13. Milestones (definition of done)

| M | Scope | Done when |
|---|---|---|
| M0 | Phase 0 study | `format_bible.md` + `metrics.csv` + differentiation plan approved by Shally |
| M1 | S0–S4 | Topic → approved, source-backed script; claims ledger + originality check working |
| M2 | S5–S7 | Beats + images for a 90 s pilot in Mode A **and** B; pilot comparison logged |
| M3 | S8–S10 | Kokoro audio, timings, timeline.json; drift test passes |
| M4 | S11–S12 | 90 s pilot renders; render benchmarks recorded; video QA passes |
| M5 | S13–S14 | Private upload with thumbnail, chapters, disclaimers; approvals log complete |
| M6 | Full 10–12 min video | End-to-end on one real topic, ≤ 30 min human attention |
| M7 | S15 | Analytics job + first Format-Bible revision from real data |

---

## 14. Prompt appendix (starting drafts, tune after Phase 0)

**Outline system prompt**
```
You design one video outline for an original animated finance-POV channel. Input: topic, angle, jurisdiction, target minutes, claims ledger, template id.
Output JSON per outline schema. Rules: each level has a distinct emotional tone, a concrete money decision, and a contrast with the previous level; escalate stakes; end with a twist that reframes the ladder. Use only claim ids from the ledger for numbers. Do not mimic any existing channel's titles or phrasing.
```
**Section writer system prompt**
```
You write ONE section of a narrated script (second person, present tense, calm and slightly deadpan). Input: outline section, running summary, style guide, allowed claim ids, word budget.
Rules: concrete nouns and physical actions (this will be drawn); no vague openers ("It", "This"); one idea per 1–2 sentences; numbers only as {{claim:ID}}; end the section with an open loop into the next; no advice to the viewer to buy/sell anything; educational tone.
```
**Fact-checker system prompt**
```
You are a skeptical finance editor. For each sentence with a number, comparison or causal claim: mark SUPPORTED (cite claim id) / UNSUPPORTED / MISLEADING and explain. Also flag advice-like phrasing, guarantees, and jurisdiction mismatches. Output JSON list. Be harsh.
```
**Retention pass system prompt**
```
Find stretches over ~60 seconds of narration with no new fact, no stakes change, and no visual change opportunity. Rewrite only those stretches. Keep all {{claim:ID}} placeholders and meaning intact.
```
**Director delta (append to existing director prompt)**
```
Also output beat_type (scene|level_card|chart|text_overlay), motion (push_in|pull_out|pan_l|pan_r|parallax|static) and, when a number from the ledger is the point of the line, a chart_spec. The first beat of every level is a level_card. In Mode B also choose pose_id from the provided pose library.
```

---

## 15. Risks & open questions

**Risks:** (1) templated-content demonetization risk (§4.2); (2) Flow credit/throughput limits and a fragile browser-driven batch tool at ~100 images/video (measure credits/image in M2; Mode B + day-sized batches + `manual_folder` fallback are the mitigations; Flow UI/features/pricing change often); (3) CPU render time (benchmark in M4); (4) Kokoro voice may feel flat for a 12-min narration (A/B against a paid voice on the pilot; keep provider interface); (5) finance accuracy/liability (claims ledger + G2); (6) reference-format saturation (differentiation plan, analytics loop).

**Questions for Shally (agent: ask once, then log answers in `DECISIONS.md`):**
1. Target video length and languages? (assumed 8–15 min, English)
2. Primary jurisdiction for thresholds? (assumed US)
3. Reuse the ZENN stickman as "you", or design a second character?
4. Which Google AI plan is the Flow account on (Free / Plus / Pro / Ultra)? That sets daily credit capacity. Any budget for a paid *voice* (images stay Flow-only)?
5. Do you want a lead-magnet (calculator/newsletter) from day one?
6. Confirm your Flow batch script can (a) attach a reference/element per generation, (b) set 16:9, and (c) force 1 output per prompt. If not, list what it can do.
7. Are you OK with temporary video downloads for frame analysis (§3 legal note), or transcript-only?
8. Which vision-capable model/host will run the `/watch` step (your default model may not read images)?

---

## 16. Suggested first commands for the agent

```
1. Read this file fully; create DECISIONS.md and docs/deps.md.
2. Install Remotion agent skills; run /remotion-docs to confirm current APIs.
3. Inspect `flow-batch-gen.ps1` and record its actual capabilities (reference attach, aspect ratio, outputs per prompt, retries, naming) in `docs/deps.md`; wrap it as the `flow_batch` ImageEngine.
4. Install `/watch` (§3.0), confirm `yt-dlp` and `ffmpeg` work, and confirm a vision-capable model is available for frame reading. Execute Phase 0 §3.0–3.1 (transcripts for all recent videos, frame analysis for the 5 key videos per channel if Shally approves). Generate the §3.2 checklist only for anything `/watch` could not cover; stop and hand results to Shally.
5. While waiting: scaffold repo layout (§7), JSON schemas (§9), stub providers, manifest/resume runner, and the stub dry-run test (§12).
6. Report back with: repo status table (§6 verified live), benchmark numbers (Kokoro RTF, Remotion render), and open questions.
```
