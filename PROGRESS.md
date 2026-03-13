# ListenClaw 开发进度

> 每完成一个大任务会向震宇汇报。

---

## 当前焦点

**Phase 4 — 前端 + 部署**

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
| 2.1 | 唤醒词模块 (`pipeline/wake.py`) | ✅ | openWakeWord + keyword 两种模式，config 控制开关 |
| 2.2 | 持续对话 follow-up window | ✅ | FOLLOW_UP 状态 + 超时回 IDLE |
| 2.3 | Barge-in 打断 | ✅ | SPEAKING 时继续跑 VAD，连续 5 帧语音自动打断 |
| 2.4 | 句级流式 TTS | ✅ | Agent token → 句子边界 → 立即 TTS，并行流水线 |
| 2.5 | CLI demo (`scripts/demo_cli.py`) | ✅ | Push-to-talk + 颜色状态条 + 播放 TTS |

---

## Phase 3：可插拔 Provider 适配

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 3.1 | ElevenLabs TTS adapter | ✅ | 流式，multilingual v2，lazy load |
| 3.2 | OpenAI TTS | 📋 | [issue #1](https://github.com/tinywatermonster/listenclaw/issues/1) |
| 3.3 | OpenAI / Claude / Ollama agent | 📋 | [issue #2](https://github.com/tinywatermonster/listenclaw/issues/2) |
| 3.4 | Deepgram / Azure ASR | 📋 | [issue #3](https://github.com/tinywatermonster/listenclaw/issues/3) |

---

## Phase 4：设备化 + 前端

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 4.1 | Next.js 前端 (Push-to-Talk + Pipeline 状态条) | ✅ | PTT 本地录音、状态条、对话气泡 |
| 4.2 | Provider 配置面板 (侧边抽屉) | ✅ | 右侧抽屉，localStorage 保存 |
| 4.3 | 手机 App 音频代理 | ⬜ | |
| 4.4 | Docker Compose 完整部署 | ⬜ | |
| 4.5 | OpenClaw skill 文件完善 | ⬜ | |

---

## 汇报记录

| 时间 | 里程碑 | 内容 |
|------|--------|------|
| 2026-03-13 | Phase 1 完成 | 最小闭环跑通，骨架代码全部实现 |
| 2026-03-13 | Phase 2 完成 | Barge-in、持续对话、句级流式 TTS、唤醒词模块、CLI demo |
| 2026-03-13 | Phase 3 完成 | ElevenLabs TTS 适配；其余 adapter 开 issue 等社区提交 |
| 2026-03-13 | Phase 4 前端完成 | Next.js PTT 前端上线；修复多句 TTS 播放、base64 decode、AudioContext autoplay |
