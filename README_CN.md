# 🦞 ListenClaw

[![GitHub stars](https://img.shields.io/github/stars/tinywatermonster/listenclaw?style=social)](https://github.com/tinywatermonster/listenclaw)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](https://docs.docker.com/compose/)

### 开放的语音网关，连接任意麦克风与任意 AI Agent

> 🎬 演示视频即将上线 — [在 YouTube 上观看](...)

---

## 🤔 为什么选择 ListenClaw？

- **🔌 即插即用的 Provider 矩阵** — 只需修改 `config.yaml` 一行，即可切换 ASR、Agent 和 TTS 后端，无需改动任何代码。
- **🦾 对 OpenClaw 的一流支持** — 以 [OpenClaw](https://openclaw.ai) 为核心 Agent 运行时构建，让本地 Agent 拥有声音。
- **🎙️ 兼容一切** — 本地用 Whisper，云端用 Deepgram / Azure，语音输出支持 ElevenLabs / Edge-TTS，也可回退到 OpenAI / Claude / Ollama。
- **⚡ 实时流式 Pipeline** — FastAPI WebSocket 后端保持低延迟，Push-to-Talk UI 实时呈现 Pipeline 每个步骤的状态。

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     ListenClaw Pipeline                          │
│                                                                  │
│  🎤 麦克风 ──►  ASR  ──►  路由器  ──►  Agent  ──►  TTS  ──►  🔊 │
│                │                       │                         │
│          Whisper / Azure          OpenClaw（首选）                │
│          Deepgram / FunASR        OpenAI / Claude / Ollama       │
│                                                                  │
│         Edge-TTS / OpenAI / Azure / CosyVoice ◄── TTS           │
└─────────────────────────────────────────────────────────────────┘
```

WebSocket 数据流：
```
浏览器  ──[音频数据]──►  FastAPI WS  ──►  ASR Provider
                                                │
                                            转录文本
                                                │
                                          意图路由器
                                                │
                                          Agent Provider
                                         (子进程 / ws)
                                                │
                                           Agent 回复
                                                │
                                          TTS Provider
                                                │
                       浏览器  ◄──[音频 + 文字]──  FastAPI WS
```

---

## 🚀 快速开始

```bash
git clone https://github.com/tinywatermonster/listenclaw
cp config.example.yaml config.yaml  # 填入你的 API Key
docker compose up
```

然后打开 [http://localhost:3000](http://localhost:3000) — 按住按钮说话，松开即处理。

---

## ⚙️ 配置说明

编辑 `config.yaml` 选择你的 Provider：

```yaml
asr:
  provider: whisper          # whisper | azure | deepgram | funasr

agent:
  provider: openclaw         # openclaw | openai | claude | ollama
  openclaw:
    mode: cli                # cli | websocket
    agent: main

tts:
  provider: edge_tts         # edge_tts | openai | azure | cosyvoice
  edge_tts:
    voice: zh-CN-XiaoxiaoNeural
```

---

## 🗂️ Provider 支持矩阵

### ASR（语音转文字）

| Provider | 状态 | 说明 |
|----------|------|------|
| **Whisper**（本地） | ✅ 已完成 | 默认，完全离线运行 |
| **Azure Speech** | 📋 规划中 | 低延迟云端方案 |
| **Deepgram** | 📋 规划中 | 快速流式 API |
| **FunASR** | 📋 规划中 | 中文识别最佳选择 |

### Agent（AI 大脑）

| Provider | 状态 | 说明 |
|----------|------|------|
| **OpenClaw** | ✅ 已完成 | 核心 — 支持 CLI 与 WebSocket 两种模式 |
| **OpenAI** | 📋 规划中 | GPT-4o，支持工具调用 |
| **Claude** | 📋 规划中 | Anthropic API |
| **Ollama** | 📋 规划中 | 完全本地化 LLM 回退方案 |

### TTS（文字转语音）

| Provider | 状态 | 说明 |
|----------|------|------|
| **Edge-TTS** | ✅ 已完成 | 默认，免费，300+ 音色 |
| **OpenAI TTS** | 📋 规划中 | 自然、高清音色 |
| **Azure Neural** | 📋 规划中 | 企业级语音合成 |
| **CosyVoice** | 📋 规划中 | 中文输出最佳选择 |

---

## 🖥️ Web 界面

> 📸 截图即将上线

Web 界面包含：

- **Push-to-Talk 按钮** — 按住录音，松开处理
- **实时 Pipeline 状态条** — 实时查看每个步骤：`录音 → ASR → 路由 → Agent → TTS → 播放`
- **对话气泡流** — 完整转录记录，带角色标注
- **Provider 配置抽屉** — 在浏览器中切换 ASR / Agent / TTS 并输入 API Key，保存至 localStorage
- **状态栏** — OpenClaw Gateway 连接状态 + 当前激活的 Provider 组合

---

## 📁 项目结构

```
listenclaw/
├── server/                    # FastAPI 后端
│   ├── main.py                # WebSocket 入口
│   ├── config.py              # 配置加载器
│   ├── pipeline/core.py       # Pipeline 主流程编排
│   ├── router/intent.py       # 意图路由逻辑
│   └── providers/
│       ├── asr/               # whisper / azure / deepgram / funasr
│       ├── agent/             # openclaw / openai / claude / ollama
│       └── tts/               # edge_tts / openai / azure / cosyvoice
├── web/                       # Next.js 14 前端
│   └── src/
│       ├── app/               # 页面
│       ├── components/        # VoiceButton、对话气泡、PipelineStatus、ProviderPanel
│       └── lib/               # WebSocket client、音频工具
├── openclaw-skill/
│   ├── listenclaw.md          # OpenClaw skill 定义
│   └── install.sh             # 一键安装脚本
├── config.yaml                # 你的配置文件（已 gitignore）
├── config.example.yaml        # 配置模板
├── docker-compose.yml
└── Dockerfile
```

---

## 🦾 与 OpenClaw 集成

ListenClaw 天生是 [OpenClaw](https://openclaw.ai) 的语音层。如果你已安装 OpenClaw，两条命令即可接入语音：

```bash
# 将 ListenClaw skill 安装到 OpenClaw
bash openclaw-skill/install.sh

# 启动语音网关
docker compose up server
```

OpenClaw 将接收 ListenClaw 转发的语音指令，并以语音形式回复。

---

## 🛠️ 本地开发

```bash
# 后端
cd server
pip install -r ../requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8765 --reload

# 前端
cd web
npm install
npm run dev
```

---

## 🤝 参与贡献

欢迎贡献代码。目前最需要帮助的方向：

1. **新增 ASR Provider** — 在 `server/providers/asr/` 中添加实现基础接口的类
2. **新增 TTS Provider** — 同样的模式，位于 `server/providers/tts/`
3. **Agent 适配器** — OpenAI、Claude、Ollama 适配器，位于 `server/providers/agent/`
4. **前端完善** — 动画效果、移动端布局、无障碍支持

新增 Provider 只需实现抽象基类并在 `config.py` 中注册，一个文件搞定，没有框架魔法。

大型 PR 请先开 Issue 讨论。Bug 修复和文档改进无需提前沟通，直接提交即可。

---

## 📄 开源协议

MIT © [tinywatermonster](https://github.com/tinywatermonster)

---

<p align="center">
  为语音优先的 AI 体验而生。如果觉得有用，欢迎 Star ⭐
</p>
