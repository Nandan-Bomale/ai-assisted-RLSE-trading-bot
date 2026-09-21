class SweepStrategy:
    def __init__(self, symbol, true_pdh, true_pdl, active_high, active_low, sl_buffer):
        self.symbol = symbol
        
        # Store true PDH/PDL for dashboard display
        self.pdh = true_pdh
        self.pdl = true_pdl
        
        # Active targets which could be today's high if already broken
        self.active_high_target = active_high
        self.active_low_target = active_low
        
        self.sl_buffer = sl_buffer
        
        # Sweep State Tracking
        self.sweep_high_active = False
        self.sweep_low_active = False
        
        # Track the highest/lowest price reached during a sweep
        self.current_swing_high = 0.0
        self.current_swing_low = float('inf')
        
        # V-Shape Time tracking
        self.high_candle_time = None
        self.low_candle_time = None
        self.last_checked_candle_time = None
        
    def update(self, current_price, df_1m):
        """
        Takes the current tick price and the recent 1m dataframe.
        Returns a dictionary with trade signal if triggered, else None.
        """
        signal = None
        
        if df_1m is None or len(df_1m) < 4:
            return signal
            
        current_candle_time = df_1m.iloc[-1]['time']
        
        # 1. Check for sweeps
        if current_price > self.active_high_target:
            if not self.sweep_high_active:
                print(f"[{self.symbol}] 🚨 Price SWEPT the High Target ({self.active_high_target})! Watching for V-Shape reversal...")
            self.sweep_high_active = True
            
            # Update the highest point reached so far & record WHEN it happened
            if current_price > self.current_swing_high:
                self.current_swing_high = current_price
                self.high_candle_time = current_candle_time
                
        if current_price < self.active_low_target:
            if not self.sweep_low_active:
                print(f"[{self.symbol}] 🚨 Price SWEPT the Low Target ({self.active_low_target})! Watching for V-Shape reversal...")
            self.sweep_low_active = True
            
            # Update the lowest point reached so far & record WHEN it happened
            if current_price < self.current_swing_low:
                self.current_swing_low = current_price
                self.low_candle_time = current_candle_time

        # 2. Check confirmation patterns if a sweep is active
        c2 = df_1m.iloc[-2] # Last fully closed candle
        c1 = df_1m.iloc[-3] # The candle before it
        c0 = df_1m.iloc[-4] # The candle before that
        cp = df_1m.iloc[-5] if len(df_1m) >= 5 else c0 # Candle before c0
        
        # Only evaluate the pattern once per closed candle
        if self.last_checked_candle_time != c2['time']:
            self.last_checked_candle_time = c2['time']
            
            is_c0_red = c0['close'] < c0['open']
            is_c1_red = c1['close'] < c1['open']
            is_c2_red = c2['close'] < c2['open']
            
            is_c0_green = c0['close'] > c0['open']
            is_c1_green = c1['close'] > c1['open']
            is_c2_green = c2['close'] > c2['open']
            
            # Short Setup (After High Sweep)
            if self.sweep_high_active:
                # Pattern 1: 2 Continuous Red Candles
                pattern_1_short = is_c1_red and is_c2_red and (c2['close'] < c1['low'])
                
                # Pattern 2: Red -> Green -> Red (Engulfing lows)
                pattern_2_short = is_c0_red and is_c1_green and is_c2_red and (c2['close'] < min(c0['low'], c1['low']))
                
                if pattern_1_short and self.high_candle_time in [c0['time'], c1['time']]:
                    print(f"[{self.symbol}] 🎯 SHORT Setup Confirmed! (Immediate V-Shape 2 Red Candles)")
                    
                    sl = self.current_swing_high + self.sl_buffer
                    signal = {
                        "action": "SHORT",
                        "sl": sl,
                        "tp_target": self.active_low_target
                    }
                    self.active_high_target = self.current_swing_high
                    self.sweep_high_active = False
                    self.current_swing_high = 0.0 
                    
                elif pattern_2_short and self.high_candle_time in [cp['time'], c0['time'], c1['time']]:
                    print(f"[{self.symbol}] 🎯 SHORT Setup Confirmed! (Red-Green-Red Engulfing Pattern)")
                    
                    sl = self.current_swing_high + self.sl_buffer
                    signal = {
                        "action": "SHORT",
                        "sl": sl,
                        "tp_target": self.active_low_target
                    }
                    self.active_high_target = self.current_swing_high
                    self.sweep_high_active = False
                    self.current_swing_high = 0.0
                    
                else:
                    # Timeout logic. 
                    # If high was older than cp, it's definitively too late.
                    if self.high_candle_time is not None and self.high_candle_time < cp['time']:
                        print(f"[{self.symbol}] ❌ Sweep timed out (No valid pattern). Target updated to {self.current_swing_high}")
                        self.active_high_target = self.current_swing_high
                        self.sweep_high_active = False
                        self.current_swing_high = 0.0
            
            # Long Setup (After Low Sweep)
            if self.sweep_low_active:
                # Pattern 1: 2 Continuous Green Candles
                pattern_1_long = is_c1_green and is_c2_green and (c2['close'] > c1['high'])
                
                # Pattern 2: Green -> Red -> Green (Engulfing highs)
                pattern_2_long = is_c0_green and is_c1_red and is_c2_green and (c2['close'] > max(c0['high'], c1['high']))
                
                if pattern_1_long and self.low_candle_time in [c0['time'], c1['time']]:
                    print(f"[{self.symbol}] 🎯 LONG Setup Confirmed! (Immediate V-Shape 2 Green Candles)")
                    
                    sl = self.current_swing_low - self.sl_buffer
                    signal = {
                        "action": "LONG",
                        "sl": sl,
                        "tp_target": self.active_high_target
                    }
                    self.active_low_target = self.current_swing_low
                    self.sweep_low_active = False
                    self.current_swing_low = float('inf') 
                    
                elif pattern_2_long and self.low_candle_time in [cp['time'], c0['time'], c1['time']]:
                    print(f"[{self.symbol}] 🎯 LONG Setup Confirmed! (Green-Red-Green Engulfing Pattern)")
                    
                    sl = self.current_swing_low - self.sl_buffer
                    signal = {
                        "action": "LONG",
                        "sl": sl,
                        "tp_target": self.active_high_target
                    }
                    self.active_low_target = self.current_swing_low
                    self.sweep_low_active = False
                    self.current_swing_low = float('inf')
                    
                else:
                    # Timeout logic
                    if self.low_candle_time is not None and self.low_candle_time < cp['time']:
                        print(f"[{self.symbol}] ❌ Sweep timed out (No valid pattern). Target updated to {self.current_swing_low}")
                        self.active_low_target = self.current_swing_low
                        self.sweep_low_active = False
                        self.current_swing_low = float('inf')
                    
        return signal
