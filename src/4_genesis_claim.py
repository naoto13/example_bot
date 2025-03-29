import os
import logging
import time
from web3 import Web3
from dotenv import load_dotenv

# ログの設定：INFOレベルのログを出力する
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# .envファイルを読み込み、秘密鍵などの環境変数を利用可能にする
load_dotenv()  # .envファイルを読み込む

# 定数設定
CHAIN_ID = 146  # SonicチェーンのchainId
RPC_URL = "https://sonic-rpc.publicnode.com"  # SonicチェーンのRPCエンドポイント

# GENESIS_POOL_CONTRACT_ADDRESS = "0x10a2b4F8EF1DEDa10CEf90A7bdF178547b1efb54"  # GenesisRewardPoolのコントラクトアドレス, Quant
GENESIS_POOL_CONTRACT_ADDRESS = "0x49f5BCDBC8B2f3401d1Fc3B5Df75F91eF389657A"  # GenesisRewardPoolのコントラクトアドレス, SHIELD

# POOL_IDs = [0,3]  # プールID QuantPoolのscUSD/QUANT=0, scUSD=3
# POOL_IDs = [0,1]  # プールID SHELDの scUASD/SHIELD=0, scUSD=1
POOL_IDs = [1]  # プールID SHELDの scUASD/SHIELD=0, scUSD=1

# 繰り返し時間
INTERVAL_SECOND = 90  # 60s毎にClaimする

# withdraw関数のABI（GenesisRewardPoolのwithdraw関数は2つのuint256型引数を取ります）
WITHDRAW_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "_pid", "type": "uint256"},
            {"internalType": "uint256", "name": "_amount", "type": "uint256"}
        ],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


def connect_to_rpc(rpc_url: str) -> Web3:
    """
    # RPCエンドポイントに接続して、Web3インスタンスを返す関数
    """
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if not web3.is_connected():
        logger.error("Sonicチェーンへの接続に失敗しました。RPCエンドポイントやネットワーク設定を確認してください。")
        exit(1)
    logger.info("RPC接続に成功しました。")
    return web3


def get_account(web3: Web3) -> (str, str):
    """
    .envから秘密鍵を取得し、アカウントアドレスと秘密鍵を返す関数

    Returns:
        account_address (str): アカウントのアドレス
        private_key (str): 環境変数から取得した秘密鍵
    """
    private_key = os.getenv("PRIVATE_KEY")
    if private_key is None:
        logger.error("PRIVATE_KEYが環境変数に設定されていません。")
        exit(1)
    account = web3.eth.account.from_key(private_key)
    logger.info("アカウントアドレス: %s", account.address)
    return account.address, private_key


def get_contract_instance(web3: Web3, contract_address: str, abi: list):
    """
    指定したコントラクトアドレスとABIからコントラクトインスタンスを生成して返す関数

    Args:
        web3 (Web3): Web3インスタンス
        contract_address (str): コントラクトのアドレス（文字列）
        abi (list): コントラクトのABI

    Returns:
        contract: Web3のコントラクトインスタンス
    """
    # アドレスをチェックサム形式に変換
    checksum_address = web3.to_checksum_address(contract_address)
    logger.info("GenesisRewardPoolアドレス: %s", checksum_address)
    return web3.eth.contract(address=checksum_address, abi=abi)


def build_withdraw_transaction(web3: Web3, contract, account_address: str, pid: int, amount: int) -> dict:
    
    # withdraw関数を呼び出すためのトランザクションを構築する関数
    # ・最新ブロックからBase Fee（baseFeePerGas）を取得し、
    #   MaxPriorityFeePerGas（優先ガス料金）を「BaseFee + 10 Gwei」と設定
    # ・GasリミットはestimateGas()の値に20%のバッファーを追加
    # ・MaxFeePerGasはMaxPriorityFeePerGasの1.2倍に設定（上限値として機能）
    # Args:
    #     web3 (Web3): Web3インスタンス
    #     contract: コントラクトインスタンス
    #     account_address (str): トランザクション送信元アドレス
    #     pid (int): プールID（_pid）
    #     amount (int): 引き出し額（_amount, 0の場合pending報酬のみClaimされる）
    # Returns:
    #     tx (dict): 署名前のトランザクション辞書

    logger.info("Withdraw実行: Pool ID: %d, Amount: %d", pid, amount)

    # 最新ブロックからbaseFeePerGasを取得（EIP-1559対応のチェーンの場合）
    latest_block = web3.eth.get_block('latest')
    base_fee = latest_block['baseFeePerGas']
    # 優先料金（Tip）:BaseFeeに10 Gweiを加算して設定（ここで+10 Gweiとする例）
    add_gwei = web3.to_wei(5, 'gwei')
    max_priority_fee = base_fee + add_gwei
    # 最大ガス料金（MaxFeePerGas）は、優先ガスの1.2倍とする
    max_fee = int(max_priority_fee * 1.2)
    # ガスリミットの見積もり（トランザクションの実行に必要なGasの単位）
    gas_estimate = contract.functions.withdraw(pid, amount).estimate_gas({'from': account_address})
    # バッファとして20%増しのガスリミットを設定
    gas_limit = int(gas_estimate * 1.2)

    # logger.info("最新ブロックのBase Fee: %s Gwei", web3.from_wei(base_fee, 'gwei'))
    # logger.info("設定するMax Priority Fee: %s Gwei", web3.from_wei(max_priority_fee, 'gwei'))
    # logger.info("設定するMax Fee: %s Gwei", web3.from_wei(max_fee, 'gwei'))
    # logger.info("Gas Estimate: %d gas units (バッファ込み: %d)", gas_estimate, gas_limit)

    # 送信元アカウントのnonceを取得（同一アドレスからのトランザクションのカウント）
    nonce = web3.eth.get_transaction_count(account_address)
    # withdraw関数呼び出しのトランザクションをビルド
    tx = contract.functions.withdraw(pid, amount).build_transaction({
        'chainId': CHAIN_ID,                  # SonicチェーンのchainId
        'gas': gas_limit,                     # ガスリミット（estimateGas()に20%バッファー）
        'maxFeePerGas': max_fee,              # 最大ガス料金（上限として設定）
        'maxPriorityFeePerGas': max_priority_fee,  # 優先ガス料金（マイナーへのTip）
        'nonce': nonce,                       # 送信元アカウントのnonce
        'from': account_address               # 送信元アドレス
    })

    logger.info("トランザクション構築完了: %s", tx)
    return tx


def sign_and_send_transaction(web3: Web3, tx: dict, private_key: str) -> str:
    # トランザクションに署名し、ネットワークに送信する関数
    # Args:
    #     web3 (Web3): Web3インスタンス
    #     tx (dict): ビルドされたトランザクション
    #     private_key (str): 署名に使用する秘密鍵
    # Returns:
    #     tx_hash (str): 送信されたトランザクションのハッシュ

    # トランザクションに署名する
    signed_tx = web3.eth.account.sign_transaction(tx, private_key=private_key)
    # 署名済みトランザクションをネットワークに送信
    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
    logger.info("トランザクション送信完了。Tx Hash: %s", web3.to_hex(tx_hash))
    return web3.to_hex(tx_hash)


def main():
    # RPC接続とアカウントの設定
    web3 = connect_to_rpc(RPC_URL)
    account_address, private_key = get_account(web3)

    # コントラクトインスタンスの生成（GenesisRewardPool）
    contract = get_contract_instance(web3, GENESIS_POOL_CONTRACT_ADDRESS, WITHDRAW_ABI)

    # POOL_IDs = [0,3]とした時に1分毎にClaimする
    # POOL_IDs = [0,3]とした時に30秒毎にClaimする
    while True:
        for pid in POOL_IDs:
            # withdraw関数（poolId: pid, amount: 0）のトランザクションを構築
            # ここで、_pid = pid と _amount = 0 を指定すると、LPトークンの残高は変化せず、
            # pending報酬（QUANT）がClaimされます。
            tx = build_withdraw_transaction(web3, contract, account_address, pid=pid, amount=0)
            # 署名済みトランザクションを生成し、ネットワークに送信する
            tx_hash = sign_and_send_transaction(web3, tx, private_key)
            print(f"Pool ID: {pid} のトランザクションハッシュ:", tx_hash)
        logger.info(" %s 秒待機中...",INTERVAL_SECOND)
        time.sleep(INTERVAL_SECOND)

if __name__ == "__main__":
    main()
