# https://qtmfinance.io/のGenesisPoolからの報酬をClaimする

import os
from web3 import Web3
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#envから秘密鍵を取得
from dotenv import load_dotenv
load_dotenv()   # .envファイルを読み込む

# SonicチェーンのRPCエンドポイントに接続（ご自身の環境に合わせてURLを設定してください）
rpc_url = "https://sonic-rpc.publicnode.com"
genesis_pool_contract_address = "0x10a2b4f8ef1deda10cef90a7bdf178547b1efb54"



web3 = Web3(Web3.HTTPProvider(rpc_url))
# RPC接続の確認
if not web3.is_connected():
    print("Sonicチェーンへの接続に失敗しました。RPCエンドポイントやネットワーク設定を確認してください。")
    exit()

# 秘密鍵からアカウントを生成
account = web3.eth.account.from_key(os.getenv("PRIVATE_KEY"))
account_address = account.address

# GenesisRewardPoolのコントラクトアドレス（チェックサム形式に変換）
contract_address = web3.to_checksum_address(genesis_pool_contract_address)
# 確認ログ出力
logger.info("アカウントアドレス: %s GenesisRewardPoolアドレス: %s", account_address, contract_address)

# withdraw関数のABI（GenesisRewardPoolのwithdraw関数は2つのuint256型引数を取ります）
abi = [
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

# コントラクトインスタンスの生成
contract = web3.eth.contract(address=contract_address, abi=abi)

# ここで、withdraw(3, 0)を実行する意図：
# - 第1引数（_pid = 3）：対象のプールID（GenesisRewardPoolのpoolInfo配列内の対象プール）
# - 第2引数（_amount = 0）：LPトークンの引き出し額。0の場合、保有LPトークンは変化せず、計算されたpending報酬（QUANT）がClaimされます。


# ガスの見積もりはちゃんとチェーンから取得する
# 最新ブロックからbaseFeePerGasを取得（EIP-1559対応のチェーンの場合）
latest_block = web3.eth.get_block('latest')
base_fee = latest_block['baseFeePerGas']
add_gwei = web3.to_wei(10, 'gwei')  # 50 Gwei に増加
# 優先料金（miner tip）は、争わない場合は例えば2 gwei程度が適当
# 急いでいるときは固定で10Gwei
# ネットワーク状況に応じて、Base Feeに対して+1 GweiのTipを設定
max_priority_fee_per_gas = base_fee + add_gwei

# ガスリミットは、チェーンからの見積もりを使用
gas_estimate = contract.functions.withdraw(3, 0).estimate_gas({
    'from': account_address
})
# ガス価格のログ出力を改善
logger.info("Gas Estimate: %d gas units", gas_estimate)
logger.info("Base Fee: %f Gwei", web3.from_wei(base_fee, 'gwei'))
logger.info("Max Priority Fee: %f Gwei", web3.from_wei(max_priority_fee_per_gas, 'gwei'))

# トランザクションのビルド
tx = contract.functions.withdraw(3, 0).build_transaction({
    'chainId': 146,  # SonicチェーンのchainId
    'gas': int(gas_estimate * 1.2),  # ガスリミットに20%のバッファーを追加
    'maxFeePerGas': int(max_priority_fee_per_gas*1.2),  # 最大ガス料金を優先ガス*1.2倍に設定
    'maxPriorityFeePerGas': max_priority_fee_per_gas,  # 優先ガス料金
    'nonce': web3.eth.get_transaction_count(account_address),
    'from': account_address
})

# txを確認,data部を確認
print(tx)
# {
#     "chainId": 146,
#     "from": "0x70f180853e7b5c04950f2356e923f85bc338d5a1",
#     "to": "0x10a2b4f8ef1deda10cef90a7bdf178547b1efb54",
#     "data": "0x441a3e7000000000000000000000000000000000000000000000000000000000000000030000000000000000000000000000000000000000000000000000000000000000",
#     "gas": "0x2930a",
#     "maxFeePerGas": "0xcced9fc80",
#     "maxPriorityFeePerGas": "0xcced9fc80",
#     "nonce": "0xda"
# }

print(f"Gas Estimate: {gas_estimate}") 
print(f"Max Fee Per Gas: {web3.from_wei(tx['maxFeePerGas'], 'gwei')} Gwei")# 許容値
print(f"Max Priority Fee: {web3.from_wei(tx['maxPriorityFeePerGas'], 'gwei')} Gwei")# マイナー報酬

# トランザクションに署名（秘密鍵を使用）
signed_tx = web3.eth.account.sign_transaction(tx, private_key=os.getenv("PRIVATE_KEY"))

# # 署名済みトランザクションをネットワークに送信
tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)

print("トランザクションハッシュ:", web3.to_hex(tx_hash))
