# ListenClaw 开发进度

> 每完成一个大任务会向震宇汇报。

---

## 当前焦点

**Phase 1 — 最小闭环**: mic → VAD → ASR → OpenClaw → TTS → speaker

---

## Phase 1：最小闭环 + 核心骨架

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 1.1 | `requirements.txt` + `config.example.yaml` | ✅ | 依赖和配置模板 |
| 1.2 | `server/config.py` | ✅ | YAML 配置加载器 |
| 1.3 | Provider base interfaces (ASR / Agent / TTS) | ✅ | 抽象基类 + 注册机制 |
| 1.4 | Whisper ASR adapter | ✅ | faster-whisper，支持本地 |
| 1.5 | OpenClaw agent adapter | ✅ | CLI subprocess 模式 + WebSocket 模式 |
| 1.6 | Edge-TTS adapter | ✅ | 免费 TTS，流式输出 |
| 1.7 | Audio engine + state machine (`pipeline/core.py`) | ✅ | VAD + 状态机 (idle→listening→processing→speaking) |
| 1.8 | FastAPI WebSocket server (`main.py`) | ✅ | 音频流接入，事件广播 |
| 1.9 | Intent router (`router/intent.py`) | ✅ | 基础路由逻辑 |

---

## Phase 2：语音产品核心交互

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 2.1 | 唤醒词集成 (openWakeWord / Porcupine) | ⬜ | |
| 2.2 | 持续对话 follow-up window | ⬜ | 状态机扩展 |
| 2.3 | Barge-in 打断 | ⬜ | TTS 播放中检测新语音 |
| 2.4 | 流式 TTS 播报 | ⬜ | 首字节延迟优化 |

---

## Phase 3：可插拔 Provider 适配

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 3.1 | OpenAI ASR (Whisper API) | ⬜ | |
| 3.2 | Azure ASR | ⬜ | |
| 3.3 | Deepgram ASR | ⬜ | |
| 3.4 | OpenAI Agent adapter | ⬜ | |
| 3.5 | Claude Agent adapter | ⬜ | |
| 3.6 | Ollama Agent adapter | ⬜ | |
| 3.7 | OpenAI TTS | ⬜ | |
| 3.8 | ElevenLabs / Cartesia TTS | ⬜ | |

---

## Phase 4：设备化 + 前端

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 4.1 | Next.js 前端 (Push-to-Talk + Pipeline 状态条) | ⬜ | |
| 4.2 | Provider 配置面板 (侧边抽屉) | ⬜ | |
| 4.3 | 手机 App 音频代理 | ⬜ | |
| 4.4 | Docker Compose 完整部署 | ⬜ | |
| 4.5 | OpenClaw skill 文件完善 | ⬜ | |

---

## 汇报记录

| 时间 | 里程碑 | 内容 |
|------|--------|------|
| 2026-03-13 | Phase 1 完成 | 最小闭环跑通，骨架代码全部实现 |
