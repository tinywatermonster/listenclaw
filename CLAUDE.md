# CLAUDE.md — ListenClaw

## 项目定位

**ListenClaw** 是一个声音驱动的 AI Agent 语音网关框架。

核心闭环：耳机/麦克风收音 → ASR → Router → Agent（首选 OpenClaw）→ TTS → 音频输出

定位是**独立可运行的中间层框架**，同时提供 OpenClaw skill 文件，让 OpenClaw 用户两条命令即可接入。

## 用户信息

- 震宇（Zhenyu），AI 硬件产品经理，EverBuds Pro + SnapMind 项目负责人
- 熟悉产品但非纯工程背景，沟通简洁直接，不需要啰嗦解释

## 本地 OpenClaw 信息

- 安装路径：`/Users/tinywatermonster/.openclaw/`
- Gateway：WebSocket，端口 `18789`，token 认证
- 可用 agents：`main`（默认）、`assistant`、`work-agent`
- CLI 调用方式：`openclaw agent --message "..." --json`
- ACP bridge：`openclaw acp --url ws://localhost:18789`
- 接入 OpenClaw 优先用 CLI subprocess 模式，WebSocket Gateway 模式作为备选

## 技术栈决策

| 层 | 选择 | 原因 |
|----|------|------|
| 后端 | Python FastAPI + WebSocket | 异步音频流处理 |
| 前端 | Next.js 14 + TailwindCSS + shadcn/ui | 现代、易看 |
| ASR | Whisper(默认) / Azure / Deepgram / FunASR | 覆盖云端+本地 |
| Agent | OpenClaw(首选) / OpenAI / Claude / Ollama | OpenClaw 是核心差异化 |
| TTS | Edge-TTS(默认免费) / OpenAI / Azure / CosyVoice | 开箱即用 |
| 部署 | Docker Compose | 一键启动 |

## 项目结构

```
listenclaw/
├── server/                    # FastAPI 后端
│   ├── main.py                # WebSocket 入口
│   ├── config.py              # 配置加载
│   ├── pipeline/core.py       # 主流程串联
│   ├── router/intent.py       # 路由逻辑
│   └── providers/
│       ├── asr/               # whisper / azure / deepgram / funasr
│       ├── agent/             # openclaw / openai / claude / ollama
│       └── tts/               # edge_tts / openai / azure / cosyvoice
├── web/                       # Next.js 前端
│   └── src/
│       ├── app/               # 页面
│       ├── components/        # 语音按钮、气泡、Pipeline状态、Provider面板
│       └── lib/               # WebSocket client、音频工具
├── openclaw-skill/
│   ├── listenclaw.md          # OpenClaw skill 定义
│   └── install.sh             # 一键安装
├── config.yaml                # 用户配置（已 gitignore）
├── config.example.yaml        # 配置模板
├── docker-compose.yml
└── README.md / README_CN.md
```

## 前端页面规划

1. **核心交互区**：Push-to-Talk 语音按钮、Pipeline 实时状态条（录音→ASR→路由→OpenClaw→TTS→播放）、对话气泡流
2. **Provider 配置面板**（侧边抽屉）：ASR / Agent / TTS 下拉选择 + API Key 输入，保存到 localStorage
3. **状态栏**：OpenClaw Gateway 连接状态、当前 Provider 组合显示

## TODO 进度

- [x] 初始化项目结构（目录 + git）
- [ ] Python FastAPI 后端骨架 + WebSocket 入口
- [ ] ASR 模块（Whisper / Azure / Deepgram / FunASR）
- [ ] OpenClaw Agent 适配器（CLI + WebSocket 两种模式）
- [ ] 其他 LLM 适配器（OpenAI / Claude / Ollama）
- [ ] TTS 模块（Edge-TTS / OpenAI / Azure / CosyVoice）
- [ ] Pipeline 主流程（ASR → Router → Agent → TTS）
- [ ] Next.js 前端
- [ ] config.yaml 配置系统
- [ ] OpenClaw skill 文件
- [ ] docker-compose.yml
- [ ] 中英双语 README

## 开发原则

- Provider 全部通过 `config.yaml` 切换，无需改代码
- OpenClaw 是核心差异化，适配器要做好 CLI 和 WebSocket 两种模式
- 保持简洁，不过度工程化