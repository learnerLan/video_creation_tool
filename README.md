# 日语学习视频剪辑工具

把日剧 / 动漫片段自动加工成**两段式学习视频**：

| 段落 | 时长 | 内容 |
|------|------|------|
| Part 1 | ~1 分钟 | 原视频，**字幕遮黑**（先听，不看字幕） |
| Part 2 | ~1 分钟 | 原视频，叠加 **N3+ 单词 & 文法讲解** |

---

## 1. 安装依赖

```bash
pip install imageio-ffmpeg pillow numpy
```

> `imageio-ffmpeg` 会自动下载 ffmpeg 二进制，无需手动安装 ffmpeg。

---

## 2. 准备配置文件

复制 `config_example.json`，按实际视频内容修改单词和文法：

```json
{
  "vocabulary": [
    { "word": "確認", "reading": "かくにん", "meaning": "确认", "level": "N3" },
    { "word": "諦める", "reading": "あきらめる", "meaning": "放弃", "level": "N3" }
  ],
  "grammar": [
    {
      "pattern": "〜てしまう",
      "connection": "V-て形 ＋ しまう",
      "meaning": "完成·遗憾 / ended up doing"
    }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| word | ✓ | 单词（汉字形式） |
| reading | | 假名读音 |
| meaning | | 中文 / 英文释义 |
| level | | JLPT 等级（仅展示用） |
| pattern | ✓ | 文法名称 |
| connection | | 接续方式 |
| meaning | | 含义说明 |

---

## 3. 运行

```bash
# 基本用法（每段 60 秒，字幕覆盖高度 13%）
python jp_video_editor.py input.mp4 --config config.json

# 自定义参数
python jp_video_editor.py input.mp4 \
    --config my_words.json \
    --output my_lesson.mp4 \
    --duration 55 \
    --subtitle-cover 0.15 \
    --mode split
```

### 参数说明

| 参数 | 默认 | 说明 |
|------|------|------|
| `input` | — | 输入视频文件 |
| `--config` / `-c` | — | JSON 配置文件路径（必填） |
| `--output` / `-o` | `<input>_learning.mp4` | 输出文件路径 |
| `--duration` / `-d` | `60` | 每段使用的视频秒数 |
| `--subtitle-cover` | `0.13` | 字幕遮黑高度比例（0.10~0.20 常用） |
| `--mode` | `split` | `split`=前半单词/后半文法；`combined`=左单词右文法同时显示 |

---

## 4. 工作流建议

1. 从日剧 / 动漫中截取 1 分钟片段（可用任意视频工具）
2. 听一遍，找出 N3 以上的单词和文法（5 个左右）
3. 填写 `config.json`
4. 运行脚本 → 得到 `xxx_learning.mp4`
5. 上传发布

---

## 5. 输出效果预览

```
Part 1  ──────────────────────────────  Part 2
┌──────────────────────────────────────┐
│                                      │
│         原始视频画面                  │
│                                      │
│                                      │
│████████████ 字幕遮黑 ████████████████│
└──────────────────────────────────────┘

Part 2 (split 模式前半段)：
┌──────────────────────────────────────┐
│ 今回の単語                            │
│ ▶ 確認（かくにん）                    │
│   → 确认                             │
│ ▶ 諦める（あきらめる）                │
│   → 放弃                             │
│         原始视频画面                  │
│         (字幕保留可见)                │
└──────────────────────────────────────┘
```

---

## 常见问题

**Q: 字幕没被完全遮住**
A: 增大 `--subtitle-cover`，例如 `--subtitle-cover 0.18`

**Q: 中文文字显示乱码 / 方块**
A: 脚本会自动检测 Windows 系统字体（微软雅黑 / Meiryo）。
   如果找不到，可在 `WINDOWS_FONT_CANDIDATES` 列表里添加你的字体路径。

**Q: 想指定每个单词出现的时间点**
A: 目前版本使用前半段/后半段固定切换。后续可在 config.json 中为每个 item 加 `"timestamp"` 字段实现精确时间控制。
