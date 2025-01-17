import os
import asyncio
from datetime import datetime
from pprint import pprint
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, BookParams
from dotenv import load_dotenv
from py_clob_client.constants import POLYGON

load_dotenv()
os.environ['HTTP_PROXY'] = os.getenv('HTTP_PROXY')
os.environ['HTTPS_PROXY'] = os.getenv('HTTPS_PROXY')

def filter_markets(markets, min_price=0.8, end_date=datetime(2025, 6, 30)):
    """
    筛选符合条件的市场:
    - 价格 >= min_price
    - 结束时间在 end_date 之前
    """
    filtered = []
    for market in markets:
        # 检查是否有结束时间
        if 'resolutionTime' not in market:
            continue
            
        # 解析结束时间
        resolution_time = datetime.fromtimestamp(market['resolutionTime'])
        if resolution_time > end_date:
            continue
            
        # 获取价格
        if 'token_id' not in market:
            continue
            
        filtered.append(market)
    
    return filtered

def calculate_liquidity(orderbook):
    """计算订单簿的流动性（买卖双方各取前3档）"""
    liquidity = 0
    if orderbook.bids:
        for level in orderbook.bids[:3]:  # 取买方前3档
            liquidity += float(level.size) * float(level.price)
    if orderbook.asks:
        for level in orderbook.asks[:3]:  # 取卖方前3档
            liquidity += float(level.size) * float(level.price)
    return liquidity

async def get_high_prob_markets(client: ClobClient):
    """获取高概率市场"""
    # 获取所有市场
    markets = client.get_simplified_markets()
    
    # 筛选符合条件的市场
    # filtered_markets = filter_markets(markets)
    filtered_markets = markets
    # print('filtered_markets: ', filtered_markets)
    
    # 获取每个市场的最新价格和流动性
    high_prob_markets = []
    for market in filtered_markets:
        try:
            # 获取最新成交价
            last_price = client.get_last_trade_price(market['token_id'])
            print('last_price: ', last_price)
            if last_price and float(last_price['price']) >= 0.8:
                # 获取订单簿
                orderbook = client.get_order_book(market['token_id'])
                if orderbook:
                    liquidity = calculate_liquidity(orderbook)
                    market['last_price'] = float(last_price['price'])
                    market['liquidity'] = liquidity
                    high_prob_markets.append(market)
        except Exception as e:
            print(f"Error processing market {market['token_id']}: {e}")
            continue
    
    # 按流动性排序并返回前5个
    high_prob_markets.sort(key=lambda x: x['liquidity'], reverse=True)
    return high_prob_markets[:5]

async def main():
    # 初始化 ClobClient
    host = "https://clob.polymarket.com"
    key = os.getenv("PK")
    creds = ApiCreds(
        api_key=os.getenv("CLOB_API_KEY"),
        api_secret=os.getenv("CLOB_SECRET"),
        api_passphrase=os.getenv("CLOB_PASS_PHRASE"),
    )
    chain_id = POLYGON
    client = ClobClient(host, key=key, chain_id=chain_id, creds=creds)

    # 获取高概率市场
    markets = await get_high_prob_markets(client)
    
    # 打印结果
    print(f"\nTop 5 high probability markets by liquidity:")
    for market in markets:
        print(f"\nTitle: {market.get('title', 'N/A')}")
        print(f"Price: {market.get('last_price', 'N/A'):.3f}")
        print(f"Liquidity: {market.get('liquidity', 'N/A'):.2f} USDC")
        print(f"Resolution Time: {datetime.fromtimestamp(market['resolutionTime'])}")
        print(f"Token ID: {market.get('token_id', 'N/A')}")
        print("-" * 80)

if __name__ == "__main__":
    asyncio.run(main())
