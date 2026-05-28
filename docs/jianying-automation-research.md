# JianYing Automation Research

Date: 2026-05-28

## Summary

This workspace already contains enough source material to build a useful JianYing/CapCut automation controller. The practical path is not an official JianYing SDK. It is a layered controller:

1. Generate or mutate JianYing draft files.
2. Ask the installed JianYing desktop app to load and render those drafts.
3. Use UI automation only for the narrow operations that require the app, especially export.

The strongest local base is `process/pyJianYingDraft` for direct draft editing, with `process/capcut-mate` as an API-wrapper reference, and `process/jianying-editor-skill` as an orchestration/reference layer.

## Local Candidates

### pyJianYingDraft

Path: `process/pyJianYingDraft`

Best for:
- Creating JianYing drafts programmatically.
- Adding video, image, audio, text, subtitles, effects, filters, masks, keyframes, and transitions.
- Duplicating older unencrypted templates and replacing material/text.
- Export automation on Windows through `uiautomation`.

Important limits from its README:
- Template mode depends on unencrypted `draft_content.json`; JianYing 6+ encrypts that file, so template loading is documented as supporting JianYing 5.9 and below.
- Batch export is documented as supporting JianYing 6 and below, because JianYing 7+ hides controls.
- Windows supports draft generation, template mode, and automatic export. Linux/macOS can generate drafts but cannot automatically export; generated drafts still need Windows JianYing for rendering.

Core code evidence:
- `DraftFolder.create_draft()` creates a draft folder and writes `draft_content.json`.
- `JianyingController.export_draft()` finds the desktop window, opens a draft by name, clicks export, sets resolution/FPS, waits for success, and moves the exported file.
- The controller relies on UI Automation descriptors such as `HomePageDraftTitle`, `MainWindowTitleBarExportBtn`, `ExportPath`, `ExportOkBtn`, and `ExportSucceedCloseBtn`.

Assessment: best foundation for the local Python controller.

### pyCapCut

Path: `process/pyCapCut`

Best for:
- CapCut draft generation with an API similar to `pyJianYingDraft`.

Limits:
- It targets CapCut rather than Chinese JianYing Pro.
- Useful as a parallel reference, but not the first choice if your target is local JianYing Pro.

Assessment: good reference, lower priority.

### capcut-mate

Path: `process/capcut-mate`

Best for:
- A FastAPI service layer around draft creation and editing.
- REST endpoints such as `create_draft`, `add_videos`, `add_audios`, `add_images`, `add_captions`, `add_keyframes`, `save_draft`, and `gen_video`.
- Desktop client reference and API docs.

Important distinction:
- Its README says video generation is cloud rendering. That is different from controlling your local JianYing desktop app. For a local controller, reuse the API shape and draft-editing service ideas, but verify the actual export backend before claiming a local video render succeeded.

Assessment: strongest reference if you want a web/API controller.

### jianying-protocol-service

Path: `process/jianying-protocol-service`

Best for:
- A lower-level FastAPI protocol service with tasks, tracks, and segments.
- A clean task/track/segment resource model.
- Managing in-memory tasks with per-task locking and autosave.

Limits:
- The `/export` endpoint creates/upload draft artifacts to OSS in the code I checked; it does not itself prove local JianYing desktop video rendering.

Assessment: useful architecture reference, especially if you want a controller API with task lifecycle.

### jianying-editor-skill

Path: `process/jianying-editor-skill`

Best for:
- End-to-end workflow examples: media import, captions, TTS, web-to-video capture, smart zoom, movie-commentary generation, and auto export.
- Practical constraints and product wording.
- A ready `auto_exporter.py` wrapper around `pyJianYingDraft.JianyingController`.

Important limits from its README:
- It is not a replacement for JianYing; final render and playback still rely on JianYing itself.
- It cannot operate all JianYing UI buttons, including built-in AI features such as one-click video generation.
- Auto export is documented as depending on JianYing 5.9 or earlier.
- During export, the user should not move mouse or keyboard.

Assessment: best workflow playbook.

### JianYingSrt

Path: `process/JianYingSrt`

Best for:
- Older subtitle/download automation and UI automation references.

Assessment: historical reference only; not a main foundation.

## External Evidence

Public projects found in this area match the same pattern as the local code:

- `GuanYixuan/pyJianYingDraft`: Python draft generation and export automation for JianYing.
- `Hommy-master/capcut-mate`: FastAPI-based CapCut/JianYing draft automation assistant.
- `luoluoluo22/jianying-editor-skill`: AI editor skill that drives draft creation workflows and local export.
- `P-PPPP/JianYingApi`: older Windows UI automation ecosystem referenced by `JianYingSrt`.

The evidence points to an unofficial automation ecosystem. I did not find evidence of a stable official desktop JianYing automation SDK/API for local rendering.

## Feasible Controller Design

### Controller Scope

Start with a local Windows controller that owns these actions:

- Discover JianYing draft directory.
- Create draft.
- Add media tracks and segments.
- Add captions and text styling.
- Add simple effects, filters, transitions, and keyframes.
- Save draft.
- Open/render/export with installed JianYing, reporting real success or failure.

### Recommended Architecture

```text
automation-controller/
  config/
    settings.toml
  src/
    controller/
      draft_service.py
      export_service.py
      job_store.py
      media_probe.py
      api.py
  tests/
    test_draft_service.py
    test_export_status.py
```

Core modules:

- `draft_service`: thin wrapper around `pyJianYingDraft` for create/add/save.
- `export_service`: wrapper around `JianyingController`, with version checks, status phases, timeout, and clear failure messages.
- `job_store`: local SQLite or JSON job queue so long exports are trackable.
- `media_probe`: FFmpeg/ffprobe helpers to read durations and validate input files.
- `api`: optional FastAPI layer if you want HTTP control from other tools.

### Suggested Milestones

1. Minimal CLI:
   - `create --name demo --video path --caption "hello"`
   - creates a real draft in the configured draft folder.

2. Export wrapper:
   - `export --name demo --output D:\out\demo.mp4 --res 1080 --fps 30`
   - reports started, waiting, succeeded, failed, or timed out.

3. API mode:
   - `POST /drafts`
   - `POST /drafts/{id}/videos`
   - `POST /drafts/{id}/captions`
   - `POST /drafts/{id}/save`
   - `POST /exports`
   - `GET /exports/{id}`

4. Workflow presets:
   - vlog
   - subtitle video
   - image slideshow
   - short commentary video

## Main Risks

- JianYing version drift: UI automation selectors and draft file formats change across versions.
- Template support: encrypted JianYing 6+ drafts are not reliable for template loading.
- Export fragility: popups, login state, VIP restrictions, update prompts, and user input can break UI automation.
- Rendering truth: generating a draft is not the same as exporting a playable MP4.
- Licensing: local projects have different licenses. Check licenses before merging code into a distributable project.

## Recommendation

Build your own controller by composing the existing local projects instead of starting from scratch.

Use `pyJianYingDraft` as the engine, borrow API patterns from `capcut-mate`, and borrow workflow/export lessons from `jianying-editor-skill`. Keep UI automation boxed into one export module, and make every user-facing status distinguish:

- draft created
- draft saved
- export started
- export succeeded
- export failed

That gives you a realistic controller without pretending JianYing has a full official automation API.
