import os
import logging
import time
from web3 import Web3
from eth_account import Account
from decimal import Decimal
from dotenv import load_dotenv

# ログの設定：INFOレベルのログを出力する
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()  # .envファイルを読み込む

# ========== 設定 ==========
RPC_URL = "https://sonic-rpc.publicnode.com"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CHAIN_ID = 146

# アドレスとABI
TOKEN_ADDRESS = Web3.to_checksum_address("0x6706Adb93117C0a7235dCBe639E12ed13fa5752f")  # shield
# TOKEN_ADDRESS = Web3.to_checksum_address("0x29219dd400f2Bf60E5a23d13Be72B486D4038894")  # USDC.e テスト用
TO_TOKEN_ADDRESS = Web3.to_checksum_address("0xd3DCe716f3eF535C5Ff8d041c1A41C3bd89b97aE")  # scUSDC
SWAP_ADDRESS = Web3.to_checksum_address("0xA047e2AbF8263FcA7c368F43e2f960A06FD9949f") #routerCA

SLLIPAGE_PERCENT = 5  # 1%スリッページ、100なら無限

TOKEN_ABI = [
    {
        "name": "approve",
        "type": "function",
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "name": "allowance",
        "type": "function",
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

SWAP_ABI = [
    {
        "name": "swapExactTokensForTokens",
        "type": "function",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {
                "name": "routes",
                "type": "tuple[]",
                "components": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "stable", "type": "bool"}
                ]
            },
            {"name": "to", "type": "address"}
        ],
        "outputs": [
            {"name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "nonpayable"
    }
]

# ========== 初期化 ==========
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    logger.error("Sonicチェーンへの接続に失敗しました。RPCエンドポイントやネットワーク設定を確認してください。")
    exit(1)
account = Account.from_key(PRIVATE_KEY)
wallet_address = account.address

token = w3.eth.contract(address=Web3.to_checksum_address(TOKEN_ADDRESS), abi=TOKEN_ABI)
to_token = w3.eth.contract(address=Web3.to_checksum_address(TO_TOKEN_ADDRESS), abi=TOKEN_ABI)
swap = w3.eth.contract(address=Web3.to_checksum_address(SWAP_ADDRESS), abi=SWAP_ABI)

# ========== ユーティリティ関数 ==========
def get_nonce():
    return w3.eth.get_transaction_count(wallet_address)

def estimate_gas_with_margin(tx, margin=1.2):
    gas = w3.eth.estimate_gas(tx)
    return int(gas * margin)

def send_tx(signed):
    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"Transaction sent: {tx_hash.hex()}")
        return tx_hash
    except Exception as e:
        print(f"Error sending transaction: {e}")

def get_decimals(token_contract):
    try:
        return token_contract.functions.decimals().call()
    except:
        return 18  # fallback（ERC20標準がない場合）

def ensure_approval(swap_address, amount):
    # 現在のガス価格を取得
    gas_price = w3.eth.gas_price
    logger.info("Current gas price: %s", gas_price)
    # トランザクションの作成
    tx = {
        'to': swap_address,
        'value': 0,
        'gas': 200000,  # 適切なガスリミットを設定d
        'gasPrice': gas_price,  # 現在のガス価格を設定
        'nonce': w3.eth.get_transaction_count(wallet_address),
        'data': token.functions.approve(swap_address, amount).build_transaction({
            'gas': 200000,
            'gasPrice': gas_price,
            'nonce': w3.eth.get_transaction_count(wallet_address),
        })['data'],
    }

    # トランザクションに署名
    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    
    # トランザクションを送信
    send_tx(signed)

# ========== Sllipage計算 ==========
def get_amount_out_min(from_amount, from_token_address, to_token_address, is_stable, slippage_percent):
    """
    予想される出力量を計算し、スリッページに基づいて最小出力量を返す
    
    Args:
        from_amount: 入力トークン量
        from_token_address: 入力トークンアドレス
        to_token_address: 出力トークンアドレス
        is_stable: ステーブルペアかどうか
        slippage_percent: スリッページパーセント
        
    Returns:
        最小出力量
    """
    # ステーブルトークンの場合は簡易計算（ほぼ1:1に近い）
    if is_stable:
        # ステーブルペアの場合の簡易計算（少しマージンを取る）
        # 実際の価格は1:1に近いが、手数料などを考慮
        from_decimals = get_decimals(token)
        to_decimals = get_decimals(to_token)
        
        # デシマル差の調整
        decimal_diff = to_decimals - from_decimals
        adjusted_amount = from_amount * (10 ** decimal_diff) if decimal_diff > 0 else from_amount / (10 ** abs(decimal_diff))
        
        # 0.3%のスワップ手数料を考慮
        fee_adjusted = adjusted_amount * 0.997
        
        # スリッページを適用
        return int(fee_adjusted * (1 - slippage_percent / 100))
    else:
        # 非ステーブルペアの場合は別の計算方法が必要
        # ここではシンプルな計算として入力量の割合で計算
        return int(from_amount * (1 - slippage_percent / 100))

# ========== Swap実行 ==========

def swap_all_balance():
    # fromTokenの残高を取得
    from_balance = token.functions.balanceOf(wallet_address).call()
    from_decimals = get_decimals(token)
    formatted_from_balance = from_balance / 10 ** from_decimals
    logger.info("Swap対象(from)トークンの残高: %s ,CA: %s", formatted_from_balance, TOKEN_ADDRESS)

    # スワップに使用する量 
    swap_amount = from_balance
    formatted_swap_amount = swap_amount / 10 ** from_decimals
    logger.info("実際にスワップする量: %s ,CA: %s", formatted_swap_amount, TOKEN_ADDRESS)

    # 承認の確認
    current_allowance = token.functions.allowance(wallet_address, SWAP_ADDRESS).call()
    formatted_allowance = current_allowance / 10 ** from_decimals
    logger.info("Current allowance: %s ,CA: %s", formatted_allowance, TOKEN_ADDRESS)

    if swap_amount > current_allowance:
        logger.info("Approving %s トークン...", formatted_swap_amount)
        ensure_approval(SWAP_ADDRESS, swap_amount)

    logger.info("Approval 済み")
    
    # toTokenの前残高の取得
    to_decimals = get_decimals(to_token)
    before_to_balance = to_token.functions.balanceOf(wallet_address).call()
    formatted_before_to_balance = before_to_balance / 10 ** to_decimals
    logger.info("Swap前のtoToken残高: %s ,CA: %s", formatted_before_to_balance, TO_TOKEN_ADDRESS)

    # ガス設定
    latest_block = w3.eth.get_block('latest')
    base_fee = latest_block['baseFeePerGas']
    add_gwei = w3.to_wei(5, 'gwei')
    max_priority_fee = base_fee + add_gwei
    max_fee = int(max_priority_fee * 1.2)

    logger.info("Swap開始: fromToken: %s, toToken: %s", TOKEN_ADDRESS, TO_TOKEN_ADDRESS)

    # ルート設定
    # is_stable = True  # stable
    is_stable = False  # not stable
    routes = [(
        TOKEN_ADDRESS,
        TO_TOKEN_ADDRESS,
        is_stable
    )]
    logger.info("routes: %s", routes)

    # 改善されたスリッページ計算
    # amountOutMin = get_amount_out_min(
    #     swap_amount, 
    #     TOKEN_ADDRESS, 
    #     TO_TOKEN_ADDRESS, 
    #     is_stable, 
    #     SLLIPAGE_PERCENT
    # )
    
    amountOutMin=0
    
    # ログ出力用にフォーマット
    formatted_amount_out_min = amountOutMin / 10 ** to_decimals
    logger.info("スリッページ設定: %s%%, 最小受取量(toToken単位): %s ,CA: %s", 
                SLLIPAGE_PERCENT, formatted_amount_out_min, TO_TOKEN_ADDRESS)

    # トランザクション作成
    tx = swap.functions.swapExactTokensForTokens(
        swap_amount,
        amountOutMin,
        routes,
        wallet_address
    ).build_transaction({
        'from': wallet_address,
        'chainId': CHAIN_ID,
        'nonce': get_nonce(),
        'gas': 3000000,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority_fee,
    })
    logger.info("Transaction data: %s", tx)

    # トランザクション署名と送信
    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = send_tx(signed)
    
    # トランザクション確認を待機
    print("トランザクション確認待ち...")
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        print(f"トランザクション確認済み。ステータス: {receipt['status']}")
        
        # 実行後のtoToken残高
        after_to_balance = to_token.functions.balanceOf(wallet_address).call()
        formatted_after_to_balance = after_to_balance / 10 ** to_decimals
        received = after_to_balance - before_to_balance
        formatted_received = received / 10 ** to_decimals
        
        logger.info("Swap後のtoToken残高: %s ,CA: %s", formatted_after_to_balance, TO_TOKEN_ADDRESS)
        logger.info("受け取ったトークン量: %s ,CA: %s", formatted_received, TO_TOKEN_ADDRESS)
        
        if received == 0:
            logger.warning("⚠️ スワップは成功しましたが、受け取ったトークン量が 0 でした")
    except Exception as e:
        logger.error("トランザクション待機エラー: %s", e)

# ========== 実行 ==========
if __name__ == "__main__":
    swap_all_balance()

# {
#     "chainId": 146,
#     "from": "0x70F180853E7b5C04950f2356e923F85Bc338D5A1",
#     "to": "0xA047e2AbF8263FcA7c368F43e2f960A06FD9949f",
#     "value": "0x0",
#     "data": "0x2fdb223900000000000000000000000000000000000000000000000010ff3c9fdbedc1fe000000000000000000000000000000000000000000000000000000000022b4b7000000000000000000000000000000000000000000000000000000000000008000000000000000000000000070f180853e7b5c04950f2356e923f85bc338d5a100000000000000000000000000000000000000000000000000000000000000010000000000000000000000006706adb93117c0a7235dcbe639e12ed13fa5752f000000000000000000000000d3dce716f3ef535c5ff8d041c1a41c3bd89b97ae0000000000000000000000000000000000000000000000000000000000000001",
#     "gas": "0x22586c",
#     "maxFeePerGas": "0xcced9fc80",
#     "maxPriorityFeePerGas": "0xcced9fc80",
#     "nonce": "0x26a"
# }