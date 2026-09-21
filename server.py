from flask import Flask, jsonify, request, send_file
import csv
import os
import MetaTrader5 as mt5
import datetime

app = Flask(__name__)
BASE_DIR = os.path.dirname(__file__)

# Shared state populated by main.py
SHARED_STATE = {
    "targets": {}
}

@app.route('/')
def index():
    resp = send_file(os.path.join(BASE_DIR, 'dashboard.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/api/status')
def api_status():
    positions = []
    total_profit = 0.0
    balance = 0.0
    equity = 0.0
    
    if mt5.terminal_info() is not None:
        acc = mt5.account_info()
        if acc:
            balance = acc.balance
            equity = acc.equity
            
        open_pos = mt5.positions_get()
        if open_pos:
            for p in open_pos:
                positions.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "sl": p.sl,
                    "tp": p.tp,
                    "price_current": p.price_current,
                    "profit": p.profit,
                    "time": datetime.datetime.fromtimestamp(p.time).strftime("%H:%M:%S")
                })
                total_profit += p.profit
                
    # Calculate Server time until midnight (for daily candle close)
    server_time = mt5.symbol_info_tick("GOLD.i#").time if mt5.symbol_info_tick("GOLD.i#") else 0
    
    return jsonify({
        "status": "online" if mt5.terminal_info() is not None else "offline",
        "balance": balance,
        "equity": equity,
        "total_floating_profit": total_profit,
        "positions": positions,
        "targets": SHARED_STATE["targets"],
        "server_time": server_time
    })

@app.route('/api/history')
def api_history():
    # Fetch deals for the advanced analytics (Calendar, charts)
    if mt5.terminal_info() is None:
        return jsonify([])
        
    utc_from = datetime.datetime.now() - datetime.timedelta(days=30)
    utc_to = datetime.datetime.now() + datetime.timedelta(days=1)
    
    deals = mt5.history_deals_get(utc_from, utc_to)
    history = []
    if deals:
        for d in deals:
            # We only want trades that closed a position and generated P&L
            if d.entry == mt5.DEAL_ENTRY_OUT:
                # MT5 deal type is opposite of the position. DEAL_TYPE_SELL closes a BUY.
                original_dir = "BUY" if d.type == mt5.DEAL_TYPE_SELL else "SELL"
                history.append({
                    "date": datetime.datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M:%S"),
                    "symbol": d.symbol,
                    "direction": original_dir,
                    "profit": d.profit,
                    "volume": d.volume,
                    "price": d.price
                })
    return jsonify(history)

@app.route('/api/journal')
def api_journal():
    journal_path = os.path.join(BASE_DIR, 'journal.csv')
    trades = []
    if os.path.exists(journal_path):
        with open(journal_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                trades.append(row)
    return jsonify(trades[::-1])

@app.route('/api/close_all', methods=['POST'])
def api_close_all():
    data = request.json
    symbol = data.get('symbol')
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400
    
    open_pos = mt5.positions_get(symbol=symbol)
    closed = 0
    if open_pos:
        for p in open_pos:
            order_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).bid if p.type == 0 else mt5.symbol_info_tick(symbol).ask
            request_close = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": p.volume,
                "type": order_type,
                "position": p.ticket,
                "price": price,
                "deviation": 20,
                "magic": p.magic,
                "comment": "Dashboard Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request_close)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                closed += 1
                
    return jsonify({"success": True, "closed": closed})

@app.route('/api/settings')
def api_get_settings():
    import json
    settings_path = os.path.join(BASE_DIR, 'settings.json')
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                return jsonify(json.load(f))
        except: pass
    return jsonify({})

@app.route('/api/update_settings', methods=['POST'])
def api_update_settings():
    import json
    data = request.json
    if "updates" not in SHARED_STATE:
        SHARED_STATE["updates"] = {}
    for symbol, params in data.items():
        SHARED_STATE["updates"][symbol] = params
    
    # Save to file
    settings_path = os.path.join(BASE_DIR, 'settings.json')
    current_settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                current_settings = json.load(f)
        except: pass
    
    for symbol, params in data.items():
        if symbol not in current_settings: current_settings[symbol] = {}
        current_settings[symbol].update(params)
        
    with open(settings_path, 'w') as f:
        json.dump(current_settings, f, indent=4)
        
    return jsonify({"success": True})

@app.route('/api/accounts', methods=['GET'])
def api_get_accounts():
    import json
    accounts_path = os.path.join(BASE_DIR, 'accounts.json')
    if os.path.exists(accounts_path):
        try:
            with open(accounts_path, 'r') as f:
                return jsonify(json.load(f))
        except: pass
    
    # If no accounts.json, return config.py default as active
    import config
    return jsonify({
        "active": config.ACCOUNT_ID,
        "saved": [{"id": config.ACCOUNT_ID, "password": "HIDDEN", "server": config.SERVER, "name": "Default config.py"}]
    })

@app.route('/api/accounts/add', methods=['POST'])
def api_add_account():
    import json
    data = request.json
    
    # Validate data
    if not data.get("id") or not data.get("password") or not data.get("server"):
        return jsonify({"success": False, "error": "Missing fields"})
        
    accounts_path = os.path.join(BASE_DIR, 'accounts.json')
    acc_data = {"active": None, "saved": []}
    if os.path.exists(accounts_path):
        try:
            with open(accounts_path, 'r') as f:
                acc_data = json.load(f)
        except: pass
    else:
        import config
        acc_data = {
            "active": config.ACCOUNT_ID,
            "saved": [{"id": config.ACCOUNT_ID, "password": config.PASSWORD, "server": config.SERVER, "name": "Default config.py"}]
        }
        
    # Check if already exists
    for acc in acc_data["saved"]:
        if acc["id"] == int(data["id"]):
            return jsonify({"success": False, "error": "Account ID already exists."})
            
    # Add new account
    acc_data["saved"].append({
        "id": int(data["id"]),
        "password": data["password"],
        "server": data["server"],
        "name": data.get("name", f"Account {data['id']}")
    })
    
    with open(accounts_path, 'w') as f:
        json.dump(acc_data, f, indent=4)
    return jsonify({"success": True})

@app.route('/api/accounts/switch', methods=['POST'])
def api_switch_account():
    import json
    data = request.json
    acc_id = int(data.get("id"))
    
    accounts_path = os.path.join(BASE_DIR, 'accounts.json')
    acc_data = None
    if os.path.exists(accounts_path):
        try:
            with open(accounts_path, 'r') as f:
                acc_data = json.load(f)
        except: pass
    
    if not acc_data:
        import config
        acc_data = {
            "active": config.ACCOUNT_ID,
            "saved": [{"id": config.ACCOUNT_ID, "password": config.PASSWORD, "server": config.SERVER, "name": "Default config.py"}]
        }
        
    try:
        target_acc = next((a for a in acc_data["saved"] if a["id"] == acc_id), None)
        if target_acc:
            import MetaTrader5 as mt5
            authorized = mt5.login(target_acc["id"], password=target_acc["password"], server=target_acc["server"])
            if authorized:
                acc_data["active"] = target_acc["id"]
                with open(accounts_path, 'w') as f:
                    json.dump(acc_data, f, indent=4)
                
                SHARED_STATE["account_switched"] = True
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": f"MT5 Login failed. Code: {mt5.last_error()}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
            
    return jsonify({"success": False, "error": "Account not found in accounts.json. Try adding it first."})

def run_server():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    import threading
    t = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False))
    t.daemon = True
    t.start()
