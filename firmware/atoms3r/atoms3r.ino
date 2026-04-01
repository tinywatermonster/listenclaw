/**
 * ListenClaw Firmware — M5Stack AtomS3R-CAM + Atomic Echo Base
 *
 * 功能：
 *   - 短按按键：PTT 录音，松手发送给 ListenClaw
 *   - 长按 2 秒：切换 Agent（A/B/C 轮换，对应 config.yaml 里的路由配置）
 *   - 收到 task_complete：播放 TTS 音频
 *   - 屏幕显示当前状态
 *
 * 依赖库（Arduino IDE 库管理器安装）：
 *   - M5Unified          (by M5Stack)
 *   - ArduinoWebsockets  (by Gil Maimon)
 *   - ArduinoJson        (by Benoit Blanchon)
 *
 * 烧录：
 *   Board: "M5Stack AtomS3R" 或 "ESP32S3 Dev Module"
 *   Flash Size: 8MB, PSRAM: 8MB OPI
 */

#include <M5Unified.h>
#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <ArduinoJson.h>

// ─── 用户配置 ──────────────────────────────────────────────────────────────────

const char* WIFI_SSID   = "YX-CORP";
const char* WIFI_PASS   = "Y1nx1ang816;";
const char* WS_HOST     = "10.228.33.221";
const int   WS_PORT     = 8765;
const char* WS_PATH     = "/ws";

// Agent 切换（对应 ListenClaw config.yaml 里的 alias）
const char* AGENTS[]    = { "", "A", "B" };  // "" = 默认 agent
const int   AGENT_COUNT = 3;

// ─── 常量 ──────────────────────────────────────────────────────────────────────

#define SAMPLE_RATE      16000
#define MAX_RECORD_SECS  10
#define MAX_SAMPLES      (SAMPLE_RATE * MAX_RECORD_SECS)
#define LONG_PRESS_MS    2000

// Echo Base I2S 引脚
#define I2S_BCK   8
#define I2S_WS    6
#define I2S_DOUT  5   // speaker out
#define I2S_DIN   7   // mic in

// ES8311 I2C
#define ES8311_SDA  38
#define ES8311_SCL  39

// ─── 全局状态 ──────────────────────────────────────────────────────────────────

enum State { ST_STANDBY, ST_CONNECTING, ST_LISTENING, ST_PROCESSING, ST_PLAYING, ST_ERROR };
State gState = ST_CONNECTING;

int   gAgentIdx   = 0;
bool  gRecording  = false;
bool  gBtnHeld    = false;
unsigned long gBtnDownAt = 0;

int16_t* gRecBuf  = nullptr;
int      gRecLen  = 0;

uint8_t* gAudioBuf = nullptr;  // decoded TTS MP3
size_t   gAudioLen = 0;

using namespace websockets;
WebsocketsClient ws;

// ─── 工具函数 ──────────────────────────────────────────────────────────────────

void setDisplay(const char* line1, const char* line2 = "", uint32_t color = WHITE) {
    M5.Display.fillScreen(BLACK);
    M5.Display.setTextColor(color);
    M5.Display.setTextSize(1);
    M5.Display.setCursor(2, 20);
    M5.Display.println(line1);
    if (strlen(line2) > 0) {
        M5.Display.setCursor(2, 40);
        M5.Display.setTextColor(DARKGREY);
        M5.Display.println(line2);
    }
}

void updateDisplay() {
    switch (gState) {
        case ST_CONNECTING:
            setDisplay("Connecting...", WIFI_SSID, YELLOW);
            break;
        case ST_STANDBY: {
            char agentLabel[32];
            if (strlen(AGENTS[gAgentIdx]) == 0)
                snprintf(agentLabel, sizeof(agentLabel), "Agent: default");
            else
                snprintf(agentLabel, sizeof(agentLabel), "Agent: %s", AGENTS[gAgentIdx]);
            setDisplay("Ready", agentLabel, GREEN);
            break;
        }
        case ST_LISTENING:
            setDisplay("Listening...", "Release to send", RED);
            break;
        case ST_PROCESSING:
            setDisplay("Processing...", "", YELLOW);
            break;
        case ST_PLAYING:
            setDisplay("Playing...", "", CYAN);
            break;
        case ST_ERROR:
            setDisplay("Error", "Check WiFi/Server", RED);
            break;
    }
}

// Base64 decode
static const char b64chars[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

int b64decode(const char* in, size_t inLen, uint8_t* out) {
    int outLen = 0;
    uint32_t val = 0;
    int bits = 0;
    for (size_t i = 0; i < inLen; i++) {
        char c = in[i];
        if (c == '=') break;
        const char* p = strchr(b64chars, c);
        if (!p) continue;
        val = (val << 6) | (p - b64chars);
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            out[outLen++] = (val >> bits) & 0xFF;
        }
    }
    return outLen;
}

// ─── WebSocket ─────────────────────────────────────────────────────────────────

void onWsMessage(WebsocketsMessage msg) {
    if (msg.isBinary()) return;

    StaticJsonDocument<4096> doc;
    DeserializationError err = deserializeJson(doc, msg.data());
    if (err) return;

    const char* type = doc["type"];
    if (!type) return;

    if (strcmp(type, "state") == 0) {
        const char* s = doc["state"];
        if      (strcmp(s, "listening")  == 0) gState = ST_LISTENING;
        else if (strcmp(s, "processing") == 0) gState = ST_PROCESSING;
        else if (strcmp(s, "speaking")   == 0) gState = ST_PLAYING;
        else if (strcmp(s, "idle")       == 0) gState = ST_STANDBY;
        updateDisplay();
    }
    else if (strcmp(type, "task_complete") == 0) {
        const char* audioB64 = doc["audio"];
        if (audioB64 && strlen(audioB64) > 0) {
            size_t inLen = strlen(audioB64);
            size_t maxOut = (inLen * 3) / 4 + 4;
            if (gAudioBuf) free(gAudioBuf);
            gAudioBuf = (uint8_t*)malloc(maxOut);
            if (gAudioBuf) {
                gAudioLen = b64decode(audioB64, inLen, gAudioBuf);
                playAudio();
            }
        }
        gState = ST_STANDBY;
        updateDisplay();
    }
    else if (strcmp(type, "error") == 0) {
        Serial.printf("[WS] Server error: %s\n", doc["message"].as<const char*>());
        gState = ST_STANDBY;
        updateDisplay();
    }
}

void onWsEvent(WebsocketsEvent event, String data) {
    if (event == WebsocketsEvent::ConnectionOpened) {
        Serial.println("[WS] Connected");
        gState = ST_STANDBY;
        updateDisplay();
    } else if (event == WebsocketsEvent::ConnectionClosed) {
        Serial.println("[WS] Disconnected");
        gState = ST_CONNECTING;
        updateDisplay();
    }
}

void connectWS() {
    ws.onMessage(onWsMessage);
    ws.onEvent(onWsEvent);
    char url[128];
    snprintf(url, sizeof(url), "ws://%s:%d%s", WS_HOST, WS_PORT, WS_PATH);
    Serial.printf("[WS] Connecting to %s\n", url);
    ws.connect(url);
}

// ─── 录音 ──────────────────────────────────────────────────────────────────────

void startRecording() {
    if (gState != ST_STANDBY && gState != ST_PLAYING) return;
    Serial.println("[REC] Start");
    M5.Speaker.end();
    auto mic_cfg = M5.Mic.config();
    mic_cfg.sample_rate = SAMPLE_RATE;
    mic_cfg.stereo = false;
    M5.Mic.config(mic_cfg);
    M5.Mic.begin();
    gRecLen = 0;
    gRecording = true;
    gState = ST_LISTENING;
    updateDisplay();
}

void stopAndSend() {
    if (!gRecording) return;
    gRecording = false;

    // 读取剩余缓冲
    int16_t tmp[256];
    while (M5.Mic.isEnabled()) {
        size_t got = 0;
        if (!M5.Mic.record(tmp, 256, SAMPLE_RATE, false)) break;
        int space = MAX_SAMPLES - gRecLen;
        int copy = min((int)256, space);
        memcpy(gRecBuf + gRecLen, tmp, copy * 2);
        gRecLen += copy;
        if (gRecLen >= MAX_SAMPLES) break;
    }
    M5.Mic.end();
    M5.Speaker.begin();

    if (gRecLen < 100) {
        Serial.println("[REC] Too short, discarding");
        gState = ST_STANDBY;
        updateDisplay();
        return;
    }

    // Agent 前缀注入（服务端路由用）
    String prefix = "";
    if (strlen(AGENTS[gAgentIdx]) > 0) {
        prefix = String(AGENTS[gAgentIdx]) + "，";
    }

    // 发送 JSON 控制帧（告知服务端 agent 前缀）
    if (prefix.length() > 0) {
        StaticJsonDocument<128> ctrl;
        ctrl["type"]   = "agent_hint";
        ctrl["prefix"] = prefix.c_str();
        String out;
        serializeJson(ctrl, out);
        ws.send(out);
    }

    // 发送 PCM 音频（二进制）
    Serial.printf("[REC] Sending %d samples (%d ms)\n",
                  gRecLen, gRecLen * 1000 / SAMPLE_RATE);
    ws.sendBinary((const char*)gRecBuf, gRecLen * sizeof(int16_t));

    gState = ST_PROCESSING;
    updateDisplay();
}

// ─── TTS 播放 ──────────────────────────────────────────────────────────────────

void playAudio() {
    if (!gAudioBuf || gAudioLen == 0) return;
    gState = ST_PLAYING;
    updateDisplay();
    Serial.printf("[SPK] Playing %zu bytes\n", gAudioLen);
    M5.Speaker.playRaw((const int16_t*)gAudioBuf, gAudioLen / 2, SAMPLE_RATE, false, 1, 0, false);
    // 等待播放完成
    while (M5.Speaker.isPlaying()) {
        M5.update();
        delay(10);
    }
}

// ─── setup / loop ──────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);

    // M5Unified 初始化，启用 Atomic Echo Base
    auto cfg = M5.config();
    cfg.external_speaker.atomic_echo = true;
    M5.begin(cfg);

    M5.Display.setRotation(0);
    M5.Display.setTextWrap(true);

    M5.Speaker.begin();
    M5.Speaker.setVolume(200);

    // 分配录音缓冲区
    gRecBuf = (int16_t*)malloc(MAX_SAMPLES * sizeof(int16_t));
    if (!gRecBuf) {
        setDisplay("OOM Error", "No memory", RED);
        while (1) delay(1000);
    }

    // 连接 WiFi
    setDisplay("WiFi...", WIFI_SSID, YELLOW);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    int tries = 0;
    while (WiFi.status() != WL_CONNECTED && tries < 30) {
        delay(500);
        tries++;
        Serial.print(".");
    }
    if (WiFi.status() != WL_CONNECTED) {
        setDisplay("WiFi Failed", "Check SSID/Pass", RED);
        while (1) delay(1000);
    }
    Serial.printf("\n[WiFi] Connected: %s\n", WiFi.localIP().toString().c_str());

    connectWS();
}

void loop() {
    M5.update();
    ws.poll();

    // WebSocket 断线重连
    if (!ws.available() && gState != ST_CONNECTING) {
        gState = ST_CONNECTING;
        updateDisplay();
        delay(2000);
        connectWS();
        return;
    }

    // 录音期间持续读取麦克风
    if (gRecording && gRecLen < MAX_SAMPLES) {
        int16_t tmp[512];
        if (M5.Mic.record(tmp, 512, SAMPLE_RATE, false)) {
            int space = MAX_SAMPLES - gRecLen;
            int copy  = min(512, space);
            memcpy(gRecBuf + gRecLen, tmp, copy * 2);
            gRecLen += copy;
        }
    }

    // 按键处理
    bool btnDown = M5.BtnA.isPressed();

    if (btnDown && !gBtnHeld) {
        gBtnHeld   = true;
        gBtnDownAt = millis();
        startRecording();
    }

    // 长按 2 秒切换 Agent
    if (gBtnHeld && btnDown && (millis() - gBtnDownAt > LONG_PRESS_MS)) {
        if (gRecording) {
            gRecording = false;
            M5.Mic.end();
            M5.Speaker.begin();
        }
        gAgentIdx = (gAgentIdx + 1) % AGENT_COUNT;
        gState = ST_STANDBY;
        updateDisplay();
        // 防抖：等待松手
        while (M5.BtnA.isPressed()) { M5.update(); delay(10); }
        gBtnHeld = false;
        return;
    }

    if (!btnDown && gBtnHeld) {
        gBtnHeld = false;
        stopAndSend();
    }

    delay(10);
}
