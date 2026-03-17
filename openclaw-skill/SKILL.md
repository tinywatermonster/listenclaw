---
name: listenclaw
version: 1.0.0
description: |
  Voice gateway skill for ListenClaw. When a message starts with [ListenClaw],
  it means the user is speaking — the reply will be read aloud by TTS.
  Always respond in natural spoken language. No markdown, no tables, no lists.
---

# ListenClaw Voice Gateway

## Trigger

This skill activates when the message starts with `[ListenClaw]`.

## Rules

When handling a `[ListenClaw]` message:

- Reply in natural spoken language only — the response will be read aloud by a TTS engine
- Do not use any Markdown: no `**bold**`, no `# headings`, no `- lists`, no `| tables |`, no code blocks
- Express data and enumerations as sentences, not as structured formatting
- Keep sentences short and self-contained so TTS can pause naturally between them
- Do not include parenthetical notes, technical symbols, or formatting characters

## Examples

Message: `[ListenClaw] 北京今天天气怎么样`

Wrong:
```
| 指标 | 数值 |
|------|------|
| 天气 | 晴   |
| 气温 | 25°C |
```

Correct:
```
北京今天晴天，气温25度，比较适合出门。
```

---

Message: `[ListenClaw] 帮我设一个明天早上9点的提醒`

Wrong:
```
**已完成**
- 时间：明天 09:00
- 内容：提醒
```

Correct:
```
好的，明天早上9点的提醒已经设好了。
```
