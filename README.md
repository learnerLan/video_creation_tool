# 日语学习视频剪辑工具

把日剧 / 动漫片段自动加工成**三段式学习视频**：

| 段落 | 时长 | 内容 |
|------|------|------|
| Part 1 | ~1 分钟 | 原视频，**字幕区模糊遮挡**（先听，不看字幕） |
| 过渡 | 1.5 秒 | "Next Part" 提示画面 |
| Part 2 | ~1 分钟 | 原视频，叠加 **N3+ 单词 & 文法讲解** |

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
python3 jp_video_editor.py video/input.mp4 --config config_example.json
```

### 参数说明

| 参数 | 默认 | 说明 |
|------|------|------|
| `input` | — | 输入视频文件 |
| `--config` / `-c` | — | JSON 配置文件路径（必填） |
| `--duration` / `-d` | `60` | 每段使用的视频秒数 |
| `--subtitle-cover` | `0.13` | 字幕遮挡高度比例（0.10~0.20 常用） |
| `--mode` | `split` | `split`=前半单词/后半文法；`combined`=左单词右文法同时显示 |

---

## 工作流建议

1. 从日剧 / 动漫中截取 1 分钟片段
2. 听一遍，找出 N3 以上的单词和文法（5 个左右）
3. 填写 `config_example.json`（或新建一个 json 文件）
4. 把视频放入 `video/`，双击 `run.command`
5. 从 `product/` 取成品

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
