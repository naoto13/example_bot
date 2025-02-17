import os
from web3 import Web3
from dotenv import load_dotenv
from decimal import Decimal, getcontext

load_dotenv()

# 接続先（例：BSCのRPCエンドポイント）
w3 = Web3(Web3.HTTPProvider("https://bsc.drpc.org"))

# 環境変数から秘密鍵を取得し、送信元アドレスを導出
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
SENDER_ADDRESS = w3.eth.account.from_key(PRIVATE_KEY).address

# 送金先アドレスの設定（例）
recipient = "0xRecipientAddressHere"  # 送金先アドレスを設定

# USDTのコントラクトアドレス（bsc）
USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"

# 送金額（decimal考慮前で良い）
amount_usdt = 0.001

# bscのチェーンID（未指定の場合は内部でデフォルト値を採用）
default_chain_id = 56

# USDCのERC20コントラクトABI（必要最低限：balanceOf, transfer）
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "recipient", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {   
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType":"uint8","name":"","type":"uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
]

def get_token_contract(token_address):
    """ 指定されたアドレスのERC20トークンコントラクトを取得する """
    return w3.eth.contract(address=token_address, abi=ERC20_ABI)

def get_decimals(token_contract):
    """トークンの小数点桁数を取得する"""
    try:
        return token_contract.functions.decimals().call()
    except Exception as e:
        print("decimalsの取得エラー:", e)
        # エラー時はデフォルト値（例: 18）を返す
        return 18

def print_token_balances(token_contract, sender, receiver, label="トークン残高"):
    """
    送信元・受信先のERC20トークン残高を表示する  
    ※ トークンによって小数点以下の桁数は異なるため、ここでは生の数値を表示
    """
    decimals = get_decimals(token_contract)
    sender_balance = token_contract.functions.balanceOf(sender).call()
    receiver_balance = token_contract.functions.balanceOf(receiver).call()
    
    # Decimalで整形（例: USDTなら小数点以下6桁）
    sender_formatted = Decimal(sender_balance) / (10 ** decimals)
    receiver_formatted = Decimal(receiver_balance) / (10 ** decimals)

    print(f"{label}確認:")
    print(f"  Sender ({sender}): {sender_formatted} (raw: {sender_balance})")
    print(f"  Receiver ({receiver}): {receiver_formatted} (raw: {receiver_balance})")
    print("-" * 40)

def create_token_transaction(sender, receiver, token_contract, amount, chain_id=None):
    """
    ERC20トークン送信用トランザクション情報を作成する  
    引数 chain_id が指定されなければ、デフォルト値を採用する
    """
    if chain_id is None:
        chain_id = default_chain_id

    nonce = w3.eth.get_transaction_count(sender)
    print(f"Nonce: {nonce}")

    # 初期トランザクション情報（from, nonce, chainIdは必須）
    tx = {
        'from': sender,
        'nonce': nonce,
        'chainId': chain_id
    }

    # ガス価格取得後、追加
    gas_price = w3.eth.gas_price
    print(f"Gas Price: {w3.from_wei(gas_price, 'gwei')} Gwei")
    tx['gasPrice'] = gas_price

    decimals = get_decimals(token_contract)
    # Decimalを利用して送金額を単位変換
    # 例えば、amountが "1.5" USDT で decimals が6なら、
    # converted_amount = int(Decimal("1.5") * (10 ** 6)) → 1500000
    converted_amount = int(Decimal(amount) * (10 ** decimals))
    print(f"Amount: {amount}, Converted Amount: {converted_amount}")

    transfer_tx = token_contract.functions.transfer(receiver, converted_amount).build_transaction(tx)

    # オンチェーンでガスリミットを見積もる
    estimated_gas = w3.eth.estimate_gas(transfer_tx)
    transfer_tx['gas'] = int(estimated_gas * 1.2) 
    print(f"Estimated Gas: {estimated_gas}, Using Gas: {transfer_tx['gas']}")
    return transfer_tx

def sign_and_send_transaction(tx, private_key):
    """
    トランザクションに署名して送信する  
    ※ Web3.py v6 以降では raw_transaction 属性を使用
    """
    signed_tx = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    return tx_hash

def safe_transfer_usdc(receiver, amount, chain_id=None):
    """
    ERC20送金の一連の処理を実行する  
    ・送金前のトークン残高確認  
    ・トランザクション作成、署名、送信  
    ・トランザクション完了待ち  
    ・送金後のトークン残高確認
    """
    try:
        token_contract = get_token_contract(USDT_ADDRESS)
        # 送金前の残高確認
        print_token_balances(token_contract, SENDER_ADDRESS, receiver, label="送金前のトークン残高")

        # トランザクション作成
        tx = create_token_transaction(SENDER_ADDRESS, receiver, token_contract, amount, chain_id)
        print("生成されたトランザクション:", tx)

        # 署名＆送信
        tx_hash = sign_and_send_transaction(tx, PRIVATE_KEY)
        print(f"トークン送金トランザクション送信中: {w3.to_hex(tx_hash)}")

        # トランザクション完了待ち
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print("トークン送金トランザクション完了:", receipt)

        # 送金後の残高確認
        print_token_balances(token_contract, SENDER_ADDRESS, receiver, label="送金後のトークン残高")
    except Exception as e:
        print("エラーが発生しました:", e)

# ================================
# USDC送金の実行例
safe_transfer_usdc(recipient, amount_usdt)
