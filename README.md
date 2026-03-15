# 🦞 ListenClaw

[![GitHub stars](https://img.shields.io/github/stars/tinywatermonster/listenclaw?style=social)](https://github.com/tinywatermonster/listenclaw)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](https://docs.docker.com/compose/)

### The open voice gateway that connects any microphone to any AI agent

> 🎬 Demo coming soon — [watch on YouTube](...)

---

## 🤔 Why ListenClaw?

- **🔌 Plug-and-play provider matrix** — swap ASR, Agent, and TTS backends with a single line in `config.yaml`. No code changes, ever.
- **🦾 First-class OpenClaw support** — built around [OpenClaw](https://openclaw.ai) as the primary agent runtime. Run your local agents with your own voice.
- **🎙️ Works with everything** — Whisper locally, Deepgram/Azure in the cloud, ElevenLabs/Edge-TTS for voice output, OpenAI/Claude/Ollama as fallbacks.
- **⚡ Real-time streaming pipeline** — FastAPI WebSocket backend keeps latency low. Push-to-talk UI shows every step of the pipeline live.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ListenClaw Pipeline                       │
│                                                                  │
│  🎤 Mic  ──►  ASR  ──►  Router  ──►  Agent  ──►  TTS  ──►  🔊  │
│              │                      │                            │
│         Whisper / Azure        OpenClaw  (primary)               │
│         Deepgram / FunASR      OpenAI / Claude / Ollama          │
│                                                                  │
│         Edge-TTS / OpenAI / Azure / CosyVoice ◄── TTS           │
└─────────────────────────────────────────────────────────────────┘
```

WebSocket flow:
```
Browser  ──[audio blob]──►  FastAPI WS  ──►  ASR Provider
                                                   │
                                              transcript
                                                   │
                                             Intent Router
                                                   │
                                            Agent Provider
                                           (subprocess / ws)
                                                   │
                                              Agent reply
                                                   │
                                             TTS Provider
                                                   │
                         Browser  ◄──[audio + text]──  FastAPI WS
```

---

## 🚀 Quick Start

```bash
git clone https://github.com/tinywatermonster/listenclaw
cp config.example.yaml config.yaml  # edit with your API keys
docker compose up
```

Then open [http://localhost:3000](http://localhost:3000) — hold the button, speak, release.

---

## ⚙️ Configuration

Edit `config.yaml` to choose your providers:

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
    voice: en-US-JennyNeural
```

---

## 🗂️ Provider Matrix

### ASR (Speech-to-Text)

| Provider | Status | Notes |
|----------|--------|-------|
| **Whisper** (local) | ✅ Done | Default, runs fully offline |
| **Azure Speech** | 📋 Planned | Low-latency cloud option |
| **Deepgram** | 📋 Planned | Fast streaming API |
| **FunASR** | 📋 Planned | Best for Chinese/Mandarin |

### Agent (AI Brain)

| Provider | Status | Notes |
|----------|--------|-------|
| **OpenClaw** | ✅ Done | Primary — CLI & WebSocket modes |
| **OpenAI** | 📋 Planned | GPT-4o, tool use supported |
| **Claude** | 📋 Planned | Anthropic API |
| **Ollama** | 📋 Planned | Fully local LLM fallback |

### TTS (Text-to-Speech)

| Provider | Status | Notes |
|----------|--------|-------|
| **Edge-TTS** | ✅ Done | Default, free, 300+ voices |
| **OpenAI TTS** | 📋 Planned | Natural, HD voices |
| **Azure Neural** | 📋 Planned | Enterprise-grade voice |
| **CosyVoice** | 📋 Planned | Best for Chinese output |

---

## 🖥️ Web UI

> 📸 Screenshot coming soon

The web interface includes:

- **Push-to-Talk button** — hold to record, release to process
- **Live pipeline status bar** — see each step in real time: `Recording → ASR → Routing → Agent → TTS → Playing`
- **Conversation bubbles** — full transcript with role labels
- **Provider config drawer** — switch ASR / Agent / TTS and enter API keys from the browser, saved to localStorage
- **Status bar** — OpenClaw Gateway connection indicator + active provider combo

---

## 📁 Project Structure

```
listenclaw/
├── server/                    # FastAPI backend
│   ├── main.py                # WebSocket entry point
│   ├── config.py              # Config loader
│   ├── pipeline/core.py       # Main pipeline orchestration
│   ├── router/intent.py       # Intent routing logic
│   └── providers/
│       ├── asr/               # whisper / azure / deepgram / funasr
│       ├── agent/             # openclaw / openai / claude / ollama
│       └── tts/               # edge_tts / openai / azure / cosyvoice
├── web/                       # Next.js 14 frontend
│   └── src/
│       ├── app/               # Pages
│       ├── components/        # VoiceButton, Bubbles, PipelineStatus, ProviderPanel
│       └── lib/               # WebSocket client, audio utils
├── openclaw-skill/
│   ├── listenclaw.md          # OpenClaw skill definition
│   └── install.sh             # One-command install
├── config.yaml                # Your config (gitignored)
├── config.example.yaml        # Config template
├── docker-compose.yml
└── Dockerfile
```

---

## 🦾 OpenClaw Integration

ListenClaw is built to be the voice layer for [OpenClaw](https://openclaw.ai). If you already have OpenClaw installed, you can add voice in two commands:

```bash
# Install the ListenClaw skill into OpenClaw
bash openclaw-skill/install.sh

# Start the voice gateway
docker compose up server
```

OpenClaw will now accept voice commands forwarded by ListenClaw and respond with spoken audio.

---

## 🛠️ Local Development

```bash
# Backend
cd server
pip install -r ../requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8765 --reload

# Frontend
cd web
npm install
npm run dev
```

---

## 🤝 Contributing

Contributions are welcome. Here's where help is most needed:

1. **New ASR providers** — add a class in `server/providers/asr/` that implements the base interface
2. **New TTS providers** — same pattern in `server/providers/tts/`
3. **Agent adapters** — OpenAI, Claude, Ollama adapters in `server/providers/agent/`
4. **Frontend polish** — animations, mobile layout, accessibility

To add a provider, implement the abstract base class and register it in `config.py`. One file, no framework magic.

Please open an issue before large PRs. Bug fixes and docs are always welcome without prior discussion.

---

## 📄 License

MIT © [tinywatermonster](https://github.com/tinywatermonster)

---

<p align="center">
  Built for voice-first AI experiences. Star ⭐ if this is useful to you.
</p>
