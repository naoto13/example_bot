import os
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

# 接続先（例：Arbitrum OneのRPCエンドポイント）
w3 = Web3(Web3.HTTPProvider("https://arb1.arbitrum.io/rpc"))

# 環境変数から秘密鍵を取得し、送信元アドレスを導出
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
SENDER_ADDRESS = w3.eth.account.from_key(PRIVATE_KEY).address

# 送金先アドレスを設定
recipient = "0xRecipientAddressHere"  # 送金先アドレスを設定

# 送金額（ETH）
amount = 0.0002
#arbitrumのチェーンID
chain_id = 42161

def print_balances(sender, receiver, label="残高"):
    """
    指定されたアドレスのETH残高を表示する
    """
    sender_balance = w3.eth.get_balance(sender)
    receiver_balance = w3.eth.get_balance(receiver)
    print(f"{label}確認:")
    print(f"  Sender ({sender}): {w3.from_wei(sender_balance, 'ether')} ETH")
    print(f"  Receiver ({receiver}): {w3.from_wei(receiver_balance, 'ether')} ETH")
    print("-" * 40)

def create_transaction(sender, receiver, amount_eth, chain_id=42161):
    """
    トランザクション情報を作成する
    """
    nonce = w3.eth.get_transaction_count(sender)
    gas_price = w3.eth.gas_price  # 最新のガス価格を取得
    print(f"Nonce: {nonce}")
    print(f"Gas Price: {w3.from_wei(gas_price, 'gwei')} Gwei")

    tx = {
        'nonce': nonce,
        'to': receiver,
        'value': w3.to_wei(amount_eth, 'ether'),
        'gasPrice': gas_price,
        'chainId': chain_id
    }

    estimated_gas = w3.eth.estimate_gas(tx)
    tx['gas'] = int(estimated_gas * 1.2)
    print(f"Estimated Gas: {estimated_gas}")

    return tx

def sign_and_send_transaction(tx, private_key):
    """
    トランザクションに署名して送信する
    """
    signed_tx = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    return tx_hash

def send_eth(receiver, amount_eth):
    """
    ネイティブETH送金の一連の処理を実行する（送金前後の残高確認、エラーハンドリング付き）
    """
    try:
        # 送金前の残高確認
        print_balances(SENDER_ADDRESS, receiver, label="送金前の残高")
        # トランザクション作成
        tx = create_transaction(SENDER_ADDRESS, receiver, amount_eth)
        # デバッグ: 生成されたトランザクションの内容を表示
        print("生成されたトランザクション:", tx)
        # 署名＆送信
        tx_hash = sign_and_send_transaction(tx, PRIVATE_KEY)
        print(f"トランザクション送信中: {w3.to_hex(tx_hash)}")
        # トランザクション完了待ち
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print("トランザクション完了:", receipt)
        # 送金後の残高確認
        return print_balances(SENDER_ADDRESS, receiver, label="送金後の残高")
    except Exception as e:
        return print("エラーが発生しました:", e)

# 送金
send_eth(recipient, amount)



