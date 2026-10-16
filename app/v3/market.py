"""Indian NSE/BSE equity quote adapter with timestamp and source disclosure.

Twelve Data entitlements and feed delays vary by plan. A quote is not guaranteed
real-time; never claim a live price without provider freshness evidence.
"""
import re
import httpx
from datetime import datetime,timezone
from app.config import get_settings

class MarketUnavailable(ValueError): pass


async def quote(symbol,exchange='NSE'):
    exchange=exchange.upper()
    if exchange not in {'NSE','BSE'}:raise MarketUnavailable('Only NSE and BSE are supported')
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,24}',symbol):
        raise MarketUnavailable('Invalid exchange symbol')
    key=get_settings().twelve_data_api_key
    if not key:raise MarketUnavailable('TWELVE_DATA_API_KEY is not configured')
    async with httpx.AsyncClient(timeout=10) as client:
        r=await client.get('https://api.twelvedata.com/quote',params={
            'symbol':symbol,'exchange':exchange,'apikey':key})
        r.raise_for_status()
    data=r.json()
    if 'code' in data or data.get('status')=='error':
        raise MarketUnavailable('Market provider returned an error or unlicensed instrument')
    if str(data.get('exchange','')).upper()!=exchange:
        raise MarketUnavailable('Quote returned for unexpected exchange')
    return {'symbol':str(data.get('symbol',symbol)),'exchange':exchange,
            'currency':data.get('currency'),'price':data.get('close'),
            'change':data.get('change'),'change_pct':data.get('percent_change'),
            'provider_quote_timestamp':data.get('timestamp') or data.get('datetime'),
            'fetched_at':datetime.now(timezone.utc).isoformat(),
            'source':'Twelve Data /quote',
            'freshness':'Provider timestamps and subscription govern freshness. May be delayed.',
            'investment_advice':False}
