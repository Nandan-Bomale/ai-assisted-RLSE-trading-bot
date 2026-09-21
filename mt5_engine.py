import MetaTrader5 as mt5
import pandas as pd

def initialize(account, password, server):
    """Initializes the MT5 connection."""
    print("Initializing MT5 connection...")
    # Pass credentials directly to initialize to force the correct login on startup
    if not mt5.initialize(login=account, password=password, server=server):
        print(f"MT5 initialize() failed, error code = {mt5.last_error()}")
        return False
    
    authorized = mt5.login(account, password=password, server=server)
    if authorized:
        print(f"Successfully connected to MT5 - Account: {account}")
        return True
    else:
        print(f"Failed to connect to MT5 account {account}. Error: {mt5.last_error()}")
        return False

def get_daily_high_low(symbol):
    """Fetches the Previous Day High (PDH) and Previous Day Low (PDL)."""
    # mt5.TIMEFRAME_D1, start_pos=1 (yesterday), count=1
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 1, 1)
    if rates is None or len(rates) == 0:
        return None, None
    
    df = pd.DataFrame(rates)
    return df['high'].iloc[0], df['low'].iloc[0]

def get_last_closed_candles(symbol, timeframe=mt5.TIMEFRAME_M1, count=5):
    """Fetches the most recent 1m candles. Note: The last candle (index -1) might still be open."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def execute_trade(symbol, order_type, lots, sl, tp, magic, comment="RLSE Algo"):
    """Executes a market order with SL and TP."""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Symbol {symbol} not found.")
        return None

    if not symbol_info.visible:
        print(f"Symbol {symbol} is not visible, trying to switch on...")
        if not mt5.symbol_select(symbol, True):
            print(f"symbol_select({symbol}) failed.")
            return None

    point = symbol_info.point
    price = mt5.symbol_info_tick(symbol).bid if order_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC, # Standard for XM
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Order failed for {symbol}: {result.comment} (Code: {result.retcode})")
    
    return result
