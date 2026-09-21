# config.example.py

# XM Demo Account Credentials
ACCOUNT_ID = 12345678
PASSWORD = "YOUR_PASSWORD"

# Note: XM Demo servers usually have names like "XMGlobal-MT5" or "XMGlobal-MT5 4". 
# If login fails, check the exact server name in your MT5 terminal (File > Open an Account > Find your broker).
SERVER = "XMGlobal-MT5 7"

# Trading Parameters
SYMBOLS = {
    "GOLD.i#": {
        "enabled": True,
        "sl_buffer": 1.5,       # $1.5 for Gold
        "lot_size": 0.01,       # Base lot size (we will open 3 of these)
        "magic_number": 1001
    },
    "BTCUSD#": {
        "enabled": True,
        "sl_buffer": 100.0,     # $100 for BTC
        "lot_size": 0.01, 
        "magic_number": 1002
    }
}
