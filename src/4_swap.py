import os
import time
from decimal import Decimal, getcontext
from web3 import Web3
import logging

# 精度設定
getcontext().prec = 28

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 共通の ERC20 decimals 用ABI（最低限）
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    }
]

###########################################
# BaseSwapper クラス：共通処理をまとめる
###########################################
class BaseSwapper:
    def __init__(self, web3: Web3, config: dict):
        self.web3 = web3
        self.private_key = config["PRIVATE_KEY"]
        self.sender = Web3.toChecksumAddress(config["USER_ADDRESS"])
        self.slippage = Decimal(config.get("SLIPPAGE_TOLERANCE", "0.01"))
        self.deadline_offset = int(config.get("DEADLINE_OFFSET", 20 * 60))
    
    def get_nonce(self):
        return self.web3.eth.get_transaction_count(self.sender)
    
    def get_decimals(self, token_address: str) -> int:
        try:
            token_contract = self.web3.eth.contract(address=token_address, abi=ERC20_ABI)
            decimals = token_contract.functions.decimals().call()
            return decimals
        except Exception as e:
            logger.error("Token(%s) の decimals 取得に失敗: %s", token_address, e)
            return 18  # 取得失敗時は 18 を返す
    
    def get_symbol(self, token_address: str) -> str:
        try:
            token_contract = self.web3.eth.contract(address=token_address, abi=ERC20_ABI)
            symbol = token_contract.functions.symbol().call()
            return symbol
        except Exception as e:
            logger.error("Token(%s) の symbol 取得に失敗: %s", token_address, e)
            return "Unknown"

    def build_common_tx(self, value: int):
        """共通のトランザクションパラメータを返す"""
        return {
            'from': self.sender,
            'value': value,
            'nonce': self.get_nonce(),
            'gasPrice': self.web3.eth.gas_price,
        }

###########################################
# PancakeSwapV3Swapper クラス：PancakeSwap v3 固有の処理
###########################################
# PancakeSwap v3 のルーターABI（最低限必要な部分）
PANCAKE_ROUTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "internalType": "struct ISwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    }
]

# PancakeSwap v3 用のスワッパークラス(BaseSwapperを継承)
class PancakeSwapV3Swapper(BaseSwapper):
    def __init__(self, web3: Web3, config: dict):
        super().__init__(web3, config)
        # swap 対象のトークン（例：TOKEN_IN=WBNB、TOKEN_OUT=USDT）を設定（チェックサム付き）
        self.token_in = Web3.toChecksumAddress(config["TOKEN_IN_ADDRESS"])
        self.token_out = Web3.toChecksumAddress(config["TOKEN_OUT_ADDRESS"])
        self.router_address = Web3.toChecksumAddress(config["PANCAKESWAP_V3_ROUTER"])
        self.fee = config.get("FEE", 3000)
        # ルーターABIはこのクラス内定数を利用
        self.router = self.web3.eth.contract(address=self.router_address, abi=PANCAKE_ROUTER_ABI)
        # 各トークンの decimals, symbol を取得
        self.token_in_decimals = self.get_decimals(self.token_in)
        self.token_out_decimals = self.get_decimals(self.token_out)
        self.token_in_symbol = self.get_symbol(self.token_in)
        self.token_out_symbol = self.get_symbol(self.token_out)
        logger.info("Token In: %s (decimals: %d)", self.token_in_symbol, self.token_in_decimals)
        logger.info("Token Out: %s (decimals: %d)", self.token_out_symbol, self.token_out_decimals)
    
    def get_quote(self, amount_in_wei: int):
        """
        ルーターの exactInputSingle を call() でシミュレーションし、
        指定した amountIn に対する出力量を取得する
        """
        params = (
            self.token_in,
            self.token_out,
            self.fee,
            self.sender,
            int(time.time()) + self.deadline_offset,
            amount_in_wei,
            0,  # シミュレーション用に最低受取量は 0
            0
        )
        try:
            quoted = self.router.functions.exactInputSingle(params).call({
                'from': self.sender,
                'value': amount_in_wei
            })
            return quoted
        except Exception as e:
            logger.error("見積もり取得失敗: %s", e)
            return None

    def print_price(self, label: str, amount_in_wei: int):
        """
        指定した amount_in に対して、token_out の出力量を decimals を考慮して表示する
        """
        quoted = self.get_quote(amount_in_wei)
        if quoted is None:
            logger.info("%s: 価格取得失敗", label)
            return
        price = Decimal(quoted) / Decimal(10 ** self.token_out_decimals)
        logger.info("%s: %s %s は約 %s %s 相当",
                    label,
                    self.web3.fromWei(amount_in_wei, 'ether'),
                    self.token_in_symbol,
                    price,
                    self.token_out_symbol)

    def build_swap_tx(self, amount_in_wei: int):
        """
        スワップトランザクションを構築する
        """
        quoted = self.get_quote(amount_in_wei)
        if quoted is None:
            raise Exception("スワップ見積もり取得失敗")
        min_amount_out = int(Decimal(quoted) * (Decimal("1") - self.slippage))
        params = (
            self.token_in,
            self.token_out,
            self.fee,
            self.sender,
            int(time.time()) + self.deadline_offset,
            amount_in_wei,
            min_amount_out,
            0
        )
        tx_dict = self.router.functions.exactInputSingle(params).build_transaction(
            dict(self.build_common_tx(amount_in_wei))
        )
        try:
            estimated_gas = self.router.functions.exactInputSingle(params).estimate_gas({
                'from': self.sender,
                'value': amount_in_wei
            })
            tx_dict['gas'] = int(estimated_gas * 1.2)
        except Exception as e:
            logger.warning("Gas見積もりに失敗: %s. 固定値を使用", e)
            tx_dict['gas'] = 300000
        return tx_dict

    def perform_swap(self, swap_amount_wei: int):
        self.print_price("スワップ前の価格", Web3.toWei(1, 'ether'))
        tx = self.build_swap_tx(swap_amount_wei)
        logger.info("生成されたトランザクション: %s", tx)
        signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        logger.info("トランザクション送信中、ハッシュ: %s", self.web3.toHex(tx_hash))
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("トランザクション完了、ブロック番号: %s", receipt.blockNumber)
        self.print_price("スワップ後の価格", Web3.toWei(1, 'ether'))

###########################################
# メイン処理
###########################################
if __name__ == "__main__":
    # 設定情報（環境変数やファイルから取得する方法も検討）
    config = {
        "PRIVATE_KEY": os.getenv("PRIVATE_KEY"),
        "USER_ADDRESS": os.getenv("USER_ADDRESS"),
        # ここを swap したいトークンに合わせて変更（例: WBNB と USDT）　　
        # TODO： nativetoken非対応。V3の場合は前処理でラップする必要あり
        "TOKEN_IN_ADDRESS": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",# swap元 WBNB
        "TOKEN_OUT_ADDRESS": "0x55d398326f99059Ff775485246999027B3197955",# swap先 USDT
        "PANCAKESWAP_V3_ROUTER":"0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",# チェーンによっても変わります。
        "FEE": 3000,# 0.3%のSwap手数料　（Routing最適ではない）
        "SLIPPAGE_TOLERANCE": "0.01",# 1%のスリッページまで許容
        "DEADLINE_OFFSET": 20 * 60, # 20分
        "SWAP_AMOUNT": "0.001" # 0.001 BNB
    }
    
    
    # BSC RPC への接続
    web3 = Web3(Web3.HTTPProvider("https://bsc.drpc.org"))
    
    if not web3.isConnected():
        raise Exception("BSC RPCに接続できません。")
    
    swapper = PancakeSwapV3Swapper(web3, config)
    
    # 例として、0.1 BNB を swap する
    try:
        swapper.perform_swap(Web3.toWei(config["SWAP_AMOUNT"], 'ether'))
    except Exception as e:
        logger.error("スワップ実行中にエラーが発生しました: %s", e)