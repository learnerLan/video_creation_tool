#!/bin/bash
# 切换到脚本所在目录（双击时工作目录不固定，必须加这行）
cd "$(dirname "$0")"

echo "========================================"
echo "  Japanese Learning Video Editor"
echo "========================================"
echo ""

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: 未找到 python3，请先安装 Python 3。"
    read -p "按 Enter 关闭..."
    exit 1
fi

# 检查依赖
python3 -c "import imageio_ffmpeg, PIL" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "正在安装依赖..."
    pip3 install -r requirements.txt
    echo ""
fi

# 处理 video/ 下所有 mp4
count=0
for video in video/*.mp4; do
    [ -f "$video" ] || continue
    echo ">>> 处理: $video"
    python3 jp_video_editor.py "$video" --config config_example.json
    echo ""
    count=$((count + 1))
done

if [ $count -eq 0 ]; then
    echo "video/ 文件夹里没有找到 mp4 文件。"
    echo "请把视频放入 video/ 文件夹后再双击运行。"
else
    echo "========================================"
    echo "  完成！共处理 $count 个视频"
    echo "  成品在 product/ 文件夹"
    echo "========================================"
fi

echo ""
read -p "按 Enter 关闭..."
