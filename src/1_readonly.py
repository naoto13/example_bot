from web3 import Web3

# RPCノードへの接続（Arbitrumの場合）
RPC_URL = "https://arb1.arbitrum.io/rpc"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# ========================================
# チェーン系のRead-Only操作
# ========================================

#　ガス代取得
gas_price = w3.eth.gas_price
print(f"現在のガス価格: {w3.from_wei(gas_price, 'gwei')} Gwei")

# ========================================
#　　Address系(EOA)のRead-Only操作
# ========================================

# ユーザーアドレス(秘密鍵ではない)
user_address = "0x22209F34ad54D6D9572B4984e97f4B31Fa558F45" # dummy

# nonce取得
def get_nonce(address):
    return w3.eth.get_transaction_count(address)

print(f"Nonce: {get_nonce(user_address)}")

# nativeトークンの残高確認
def get_balance(address):
    balance_wei = w3.eth.get_balance(address)  # 残高をWei単位で取得
    balance_eth = w3.from_wei(balance_wei, 'ether')  # ETH単位に変換
    return balance_eth

print(f"ETH残高: {get_balance(user_address)} ETH")

# ========================================
# ERC-20のトークンのRead-only操作
# ========================================

# コントラクト情報
# 取得したいコントラクトのアドレス（USDC）
ERC20_CONTRACT_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"  

CONTRACT_ABI = [
    {
    "inputs": [
      { "internalType": "address", "name": "account", "type": "address" }
    ],
    "name": "balanceOf",
    "outputs": [{ "internalType": "uint256", "name": "", "type": "uint256" }],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [],
    "name": "decimals",
    "outputs": [{ "internalType": "uint8", "name": "", "type": "uint8" }],
    "stateMutability": "view",
    "type": "function"
  },
    {
    "inputs": [],
    "name": "totalSupply",
    "outputs": [{ "internalType": "uint256", "name": "", "type": "uint256" }],
    "stateMutability": "view",
    "type": "function"
  },
    {
    "inputs": [
      { "internalType": "address", "name": "_owner", "type": "address" },
      { "internalType": "address", "name": "_spender", "type": "address" }
    ],
    "name": "allowance",
    "outputs": [{ "internalType": "uint256", "name": "", "type": "uint256" }],
    "stateMutability": "view",
    "type": "function"
  },
]


# トークンコントラクトのインスタンス
token_contract = w3.eth.contract(address=ERC20_CONTRACT_ADDRESS, abi=CONTRACT_ABI)

# decialms取得
def get_decimals(contract):
    return contract.functions.decimals().call()

def get_token_balance(address):
    balance = token_contract.functions.balanceOf(address).call()  # トークン残高取得
    decimals = get_decimals(token_contract)  # 小数点の桁数
    return balance / (10 ** decimals)

print(f"token残高: {get_token_balance(user_address)} ")

## 発行量
def format_large_number(number):
    if number >= 10**9:
        return f"{number / 10**9:.1f}b"
    elif number >= 10**6:
        return f"{number / 10**6:.1f}m"
    elif number >= 10**3:
        return f"{number / 10**3:.1f}k"
    else:
        return str(number)

def get_total_supply(token_contract):
    total_supply = token_contract.functions.totalSupply().call()
    decimals = get_decimals(token_contract)  
    return total_supply / (10 ** decimals)

total_supply = get_total_supply(token_contract)

print(f"トークン総供給量: {total_supply}")
print(f"トークン総供給量を略で観: {format_large_number(total_supply)}")

# 指定したアドレスが特定のアドレスに承認したトークン量
def get_allowance(owner, spender, token_contract):
    allowance = token_contract.functions.allowance(owner, spender).call()
    decimals = get_decimals(token_contract)
    return allowance / (10 ** decimals)

# 対象となるContract(sushiswapV3routerアドレス)
spender_address = "0xf2614A233c7C3e7f08b1F887Ba133a13f1eb2c55" 
print(f"Sushiswapに承認したトークン量: {get_allowance(user_address, spender_address, token_contract)}")

# ========================================
# 指定したトランザクションの詳細情報
def get_transaction(tx_hash):
    return w3.eth.get_transaction(tx_hash)

tx_hash = "0xYourTransactionHash"
print(f"トランザクション情報: {get_transaction(tx_hash)}")

#  指定したトランザクションのステータス
def get_transaction_receipt(tx_hash):
    return w3.eth.get_transaction_receipt(tx_hash)

print(f"トランザクション結果: {get_transaction_receipt(tx_hash)}")
