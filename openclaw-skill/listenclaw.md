# ListenClaw Voice Gateway Skill

## 功能描述

ListenClaw 是一个声音驱动的 AI 语音网关，将你的语音实时转换为文字，发送给 OpenClaw 处理，再将回复转换为语音播放。

当用户通过 ListenClaw 与你对话时，你的回复会直接被 TTS（文字转语音）引擎朗读出来。

## 回复要求（重要）

通过 ListenClaw 收到的消息，回复时必须遵守以下规则：

1. **使用自然口语**，像正常说话一样回答，不要使用任何书面格式
2. **禁止使用 Markdown**：不用 `**粗体**`、`# 标题`、`- 列表`、`| 表格 |`、代码块等
3. **数据和列表改用口语表达**：不说"第一列：温度，第二列：湿度"，说"温度是25度，湿度是60%"
4. **长内容分段说**，每段一个自然句，便于 TTS 断句
5. **避免括号注释和技术符号**，直接说清楚

## 示例

❌ 错误（markdown 格式）：
```
| 城市 | 天气 | 温度 |
|------|------|------|
| 北京 | 晴   | 25°C |
```

✅ 正确（口语格式）：
```
北京今天晴天，温度25度。
```

❌ 错误：
```
**注意**：请按照以下步骤操作：
- 步骤一：打开设置
- 步骤二：点击确认
```

✅ 正确：
```
注意，你需要先打开设置，然后点击确认。
```

## 技术信息

- ListenClaw WebSocket 端口：`8765`
- 支持的 ASR：ElevenLabs Scribe、Whisper、Azure、Deepgram
- 支持的 TTS：ElevenLabs、Edge-TTS、OpenAI TTS、Azure
- GitHub：https://github.com/tinywatermonster/listenclaw
