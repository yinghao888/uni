#!/bin/bash
REPO_URL="https://raw.githubusercontent.com/yinghao888/uni/main"
SCRIPT_NAME="uni.py"
SCRIPT_PATH="/tmp/$SCRIPT_NAME"
echo "正在启动 yinghao888/uni 一键运行脚本..."
if ! ping -c 1 google.com &> /dev/null; then
    echo "错误：无法连接到网络，请检查网络设置！"
    exit 1
fi
if ! command -v python3 &> /dev/null; then
    echo "错误：未找到 Python3，正在尝试安装..."
    if command -v apt &> /dev/null; then
        sudo apt update
        sudo apt install -y python3 python3-pip
    else
        echo "错误：无法自动安装 Python3，请手动安装！"
        exit 1
    fi
fi
if ! command -v pip3 &> /dev/null; then
    echo "错误：未找到 pip3，正在尝试安装..."
    if command -v apt &> /dev/null; then
        sudo apt install -y python3-pip
    else
        echo "错误：无法自动安装 pip3，请手动安装！"
        exit 1
    fi
fi
echo "正在下载 $SCRIPT_NAME..."
if ! wget -O "$SCRIPT_PATH" "$REPO_URL/$SCRIPT_NAME"; then
    echo "错误：下载 $SCRIPT_NAME 失败，请检查仓库 URL 或网络！"
    exit 1
fi
echo "清理换行符..."
sed -i 's/\r//' "$SCRIPT_PATH"
echo "赋予执行权限..."
chmod +x "$SCRIPT_PATH"
echo "运行 $SCRIPT_NAME..."
python3 "$SCRIPT_PATH"
echo "清理临时文件..."
rm -f "$SCRIPT_PATH"
echo "脚本执行完成！"
