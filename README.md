# 日语学习视频剪辑工具

把日剧 / 动漫片段自动加工成**三段式学习视频**：

| 段落 | 时长 | 内容 |
|------|------|------|
| Part 1 | ~1 分钟 | 原视频，**字幕区模糊遮挡**（先听，不看字幕） |
| 过渡 | 1.5 秒 | "Next Part" 提示画面 |
| Part 2 | ~1 分钟 | 原视频，叠加 **N3+ 单词 & 文法讲解** |

**自动模式**：脚本会 OCR 识别视频里的硬字幕，自动匹配 N3/N2/N1 语法和词汇，无需手写 config 文件。

---

## 快速开始（macOS 双击运行）

1. 克隆项目
   ```bash
   git clone https://github.com/你的用户名/仓库名.git
   cd 仓库名
   ```

2. 授权启动脚本（**只需做一次**）
   ```bash
   chmod +x run.command
   ```

3. 安装依赖
   ```bash
   pip3 install -r requirements.txt
   ```

4. 把视频放入 `video/` 文件夹，**双击 `run.command`** 即可

> 首次运行如果未安装依赖，脚本会自动执行 `pip install`。

---

## 文件夹结构

```
项目根目录/
├── video/           ← 把原始视频放这里（.mp4）
├── unsubtitled/     ← 自动生成：字幕遮挡版（Part 1）
├── product/         ← 自动生成：最终成品（Part 1 + 过渡 + Part 2）
├── jp_video_editor.py
├── config_example.json
├── requirements.txt
└── run.command      ← macOS 双击启动
```

输出文件名自动带时间戳，例如：
```
product/test_learning_20260403_185221.mp4
```

---

## 配置文件

复制 `config_example.json`，按实际视频内容填写单词和文法：

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

| 字段 | 必填 | 说明 |
|------|------|------|
| `word` | ✓ | 单词（汉字形式） |
| `reading` | | 假名读音 |
| `meaning` | | 中文 / 英文释义 |
| `level` | | JLPT 等级（仅展示用） |
| `pattern` | ✓ | 文法名称 |
| `connection` | | 接续方式 |

---

## 命令行运行（进阶）

```bash
# 自动模式（OCR 识别字幕 → 自动匹配 N3+ 语法）
python3 jp_video_editor.py video/input.mp4 --auto

# 手动模式（提供自己的词汇/语法 config）
python3 jp_video_editor.py video/input.mp4 --config config_example.json
```

### 参数说明

| 参数 | 默认 | 说明 |
|------|------|------|
| `input` | — | 输入视频文件 |
| `--auto` / `-a` | — | 自动模式：OCR 字幕 + 匹配 N3+ 语法（与 --config 二选一）|
| `--config` / `-c` | — | 手动指定词汇/语法 JSON 文件 |
| `--duration` / `-d` | `60` | 每段使用的视频秒数 |
| `--subtitle-cover` | `0.13` | 字幕区高度比例（0.10~0.20 常用） |
| `--mode` | `split` | `split`=前半单词/后半文法；`combined`=左单词右文法同时显示 |

---

## 工作流建议

**自动模式（推荐）**
1. 截取日剧 / 动漫片段（带硬字幕）
2. 把视频放入 `video/`
3. 双击 `run.command` — 自动 OCR 字幕、匹配 N3+ 语法、生成成品
4. 从 `product/` 取成品

**手动模式（自定义内容）**
1. 截取视频片段
2. 把视频放入 `video/`，填写自己的 `config.json`
3. `python3 jp_video_editor.py video/xxx.mp4 --config config.json`
4. 从 `product/` 取成品

---

## 常见问题

**Q: 字幕没被完全遮住**
A: 增大 `--subtitle-cover`，例如 `--subtitle-cover 0.18`

**Q: 中文 / 日文显示方块**
A: 脚本会自动检测系统字体。Linux 可安装 Noto 字体：
```bash
sudo apt install fonts-noto-cjk
```

**Q: 不想用 `run.command`，想手动指定 config 文件**
A: 直接用命令行，`--config` 参数指定你的 json 文件路径即可。
