# RLSE Algotrading Bot

An advanced, fully autonomous algorithmic trading system integrated directly with MetaTrader 5 (MT5). The RLSE Algotrading Bot executes high-probability automated trades using a highly robust internal pattern-recognition engine, operating seamlessly through a real-time web dashboard.

*Built by Nandan&trade;*

## Key Features
- **Real-Time Web Dashboard:** A sleek, dark-themed UI for live monitoring of your account equity, server time, and trade history.
- **Dynamic Account Manager:** Seamlessly add and switch between multiple MT5 trading accounts (Demo, Prop Firm, Live) directly from the web interface without restarting the bot.
- **Live Parameter Tuning:** Adjust Risk-to-Reward (RR) ratios, lot sizes, and buffer metrics in real-time.
- **Advanced Analytics:** Auto-generated performance heatmaps, win-rate radars, and execution logs.
- **Automated Execution:** Hands-free, low-latency market execution via the MT5 Python engine.

## Installation & Setup

### Prerequisites
1. **MetaTrader 5 (MT5)** installed and running.
2. **Python 3.9+** installed (Make sure to check "Add Python to PATH" during installation).

### 1. Clone the Repository
Download the project to your local machine:
```bash
git clone https://github.com/Nandan-Bomale/RLSE-Algotrading-Bot.git
cd RLSE-Algotrading-Bot
```

### 2. Install Dependencies
Open a terminal in the folder and install the required Python libraries:
```bash
pip install -r requirements.txt
```

### 3. Add Your Initial Credentials
Rename `config.example.py` to `config.py` and input your default MT5 account details:
```python
ACCOUNT_ID = 12345678            # Your MT5 Account ID
PASSWORD = "YOUR_PASSWORD"       # Your MT5 Password
SERVER = "XMGlobal-MT5 7"        # Your Broker's Server Name
```

### 4. Launch the Bot
Simply double-click the **`start.bat`** file! 

This will automatically:
1. Boot the MT5 Terminal in the background.
2. Start the Python execution engine.
3. Open the Web Dashboard (`http://127.0.0.1:5000`) in your default browser.

From there, you can use the **Accounts** tab in the dashboard to add and switch between other MT5 accounts on the fly.

---
*Disclaimer: This software is for educational and algorithmic testing purposes. Use on live accounts at your own risk.*


## Vario Nandan's RLSE TradingView Indicator
The repository also includes the custom-built **Vario Nandan's RLSE Indicator** (`RLSE_Indicator.pine`) for TradingView. This indicator visually maps out the advanced algorithmic logic directly on your charts, drawing precise execution boxes, SL/TP levels, and real-time accuracy statistics. It is specifically optimized for the **1-minute timeframe**.

### How to Apply the Indicator:
1. Open [TradingView](https://www.tradingview.com/) and navigate to your desired chart (e.g., XAUUSD or BTCUSD) on the **1m timeframe**.
2. Click on the **Pine Editor** tab at the bottom of the screen.
3. Delete any existing code in the editor.
4. Open the `RLSE_Indicator.pine` file from this repository, copy all the code, and paste it into the Pine Editor.
5. Click the **Save** button in the Pine Editor, name the script, and then click **Add to Chart**.
6. The indicator will instantly overlay onto your chart. You can customize visual colors, SL buffer types, and RR ratios by clicking the settings gear icon next to the indicator name on your chart.
