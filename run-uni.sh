#!/bin/bash

# 一键运行脚本，用于下载并执行 yinghao888/uni 仓库中的 uni.py

# 定义变量
REPO_URL="https://raw.githubusercontent.com/yinghao888/uni/main"
SCRIPT_NAME="uni.py"
SCRIPT_PATH="/tmp/$SCRIPT_NAME"
DEPENDENCIES=("web3==6.15.1" "cryptography==43.0.1" "retrying==1.3.4" "httpx==0.27.2")

# 打印提示信息
echo "正在启动 yinghao888/uni 一键运行脚本..."

# 检查网络连接
if ! ping -c 1 google.com &> /dev/null; then
    echo "错误：无法连接到网络，请检查网络设置！"
    exit 1
fi

# 检查 Python3 是否安装
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

# 检查 pip3 是否安装
if ! command -v pip3 &> /dev/null; then
    echo "错误：未找到 pip3，正在尝试安装..."
    if command -v apt &> /dev/null; then
        sudo apt install -y python3-pip
    else
        echo "错误：无法自动安装 pip3，请手动安装！"
        exit 1
    fi
fi

# 下载 uni.py
echo "正在下载 $SCRIPT_NAME..."
if ! wget -O "$SCRIPT_PATH" "$REPO_URL/$SCRIPT_NAME"; then
    echo "错误：下载 $SCRIPT_NAME 失败，请检查仓库 URL 或网络！"
    exit 1
fi

# 清理 Windows 换行符
echo "清理换行符..."
sed -i 's/\r//' "$SCRIPT_PATH"

# 赋予执行权限
echo "赋予执行权限..."
chmod +x "$SCRIPT_PATH"

# 安装 Python 依赖
echo "安装 Python 依赖..."
for dep in "${DEPENDENCIES[@]}"; do
    if ! pip3 install "$dep"; then
        echo "错误：安装 $dep 失败，请检查 pip3 或网络！"
        exit 1
    fi
done

# 运行脚本
echo "运行 $SCRIPT_NAME..."
python3 "$SCRIPT_PATH"

# 清理临时文件
echo "清理临时文件..."
rm -f "$SCRIPT_PATH"

echo "脚本执行完成！"
