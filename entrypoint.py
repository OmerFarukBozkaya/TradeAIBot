import argparse
import os
import signal
import sys
import time
import logging
import json
import subprocess
from dotenv import load_dotenv
from Trade import Trade
from Tarama import Tarama

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('entrypoint')

class GracefulKiller:
    kill_now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True
        logger.info("Shutdown signal received. Finishing pending tasks...")

def run_auto_mode(args):
    """
    Reads CALISACAK_PERIYOTLAR from .env and spawns a subprocess for each period.
    Monitors processes and handles shutdown.
    """
    try:
        calisacak_periyotlar_str = os.getenv("CALISACAK_PERIYOTLAR")
        if not calisacak_periyotlar_str:
            logger.error("CALISACAK_PERIYOTLAR variable is empty or not found in .env")
            sys.exit(1)
        
        # Parse the JSON string list, e.g., "['15m', '1h']" or '["15m", "1h"]'
        # Replacing single quotes with double quotes for valid JSON if necessary
        calisacak_periyotlar = json.loads(calisacak_periyotlar_str.replace("'", '"'))
        
        if not isinstance(calisacak_periyotlar, list):
            logger.error("CALISACAK_PERIYOTLAR should be a list.")
            sys.exit(1)
            
        logger.info(f"Auto mode: Found periods to run: {calisacak_periyotlar}")
        
    except Exception as e:
        logger.error(f"Failed to parse CALISACAK_PERIYOTLAR: {e}")
        sys.exit(1)

    processes = []
    for period in calisacak_periyotlar:
        logger.info(f"Spawning trade bot for period: {period}")
        # Construct the command for the subprocess
        cmd = [sys.executable, "entrypoint.py", "--mode", "trade", "--period", period]
        if args.live:
            cmd.append("--live")
        
        # Spawn the process
        p = subprocess.Popen(cmd)
        processes.append((period, p))
        
    # Monitor loop
    try:
        while True:
            time.sleep(5)
            # Check if any process has died
            for period, p in processes:
                if p.poll() is not None:
                    logger.warning(f"Process for period {period} (PID {p.pid}) has exited with code {p.returncode}. Restarting...")
                    # Removing dead process from list
                    processes.remove((period, p))
                    # Restart logic (optional: add delay or retry limit)
                    cmd = [sys.executable, "entrypoint.py", "--mode", "trade", "--period", period]
                    if args.live:
                        cmd.append("--live")
                    new_p = subprocess.Popen(cmd)
                    processes.append((period, new_p))
                    logger.info(f"Restarted process for period {period} with PID {new_p.pid}")
                    break # Break to avoid modifying list while iterating, will check again next loop

    except KeyboardInterrupt:
        logger.info("Auto mode stopping...")
    finally:
        logger.info("Terminating all child processes...")
        for period, p in processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        logger.info("All processes terminated.")

def main():
    parser = argparse.ArgumentParser(description='TradeAIBot Entrypoint')
    parser.add_argument('--mode', type=str, required=True, choices=['trade', 'scan', 'trade-ai', 'auto'], help='Operation mode')
    parser.add_argument('--period', type=str, required=False, help='Time period (e.g., 15m, 1h, 4h)')
    parser.add_argument('--coin', type=str, required=False, help='Coin pair for specific operations (e.g., BTCUSDT)')
    parser.add_argument('--live', action='store_true', help='Run in live mode (real trades)')
    parser.add_argument('--cash', type=float, default=100.0, help='Initial cash amount')
    parser.add_argument('--temp-trade', action='store_true', help='Temporary trade mode (does not load/save state)')
    
    args = parser.parse_args()
    
    # Load env
    load_dotenv()
    
    killer = GracefulKiller()
    
    if args.mode == 'auto':
        run_auto_mode(args)

    elif args.mode == 'trade':
        if not args.period:
            logger.error("--period is required for trade mode.")
            sys.exit(1)
        
        logger.info(f"Starting Trade mode. Period: {args.period}, Live: {args.live}")
        trade_bot = Trade()
        
        try:
            trade_bot.TradeEt(args.period, args.live, args.cash, args.temp_trade)
        except KeyboardInterrupt:
            logger.info("Stopping...")
            
    elif args.mode == 'trade-ai':
        if not args.coin or not args.period:
            logger.error("--coin and --period are required for trade-ai mode.")
            sys.exit(1)
            
        logger.info(f"Starting Trade AI mode. Coin: {args.coin}, Period: {args.period}, Live: {args.live}")
        trade_bot = Trade()
        try:
            trade_bot.TradeEtAI(args.coin, args.period, args.live, args.cash, args.temp_trade)
        except KeyboardInterrupt:
            logger.info("Stopping...")

    elif args.mode == 'scan':
        # Default scan all coins
        from Binance import Binance
        binance = Binance()
        coinlist = binance.coin_list()
        
        if not args.period:
            logger.error("--period is required for scan mode.")
            sys.exit(1)
            
        logger.info(f"Starting Scan mode. Period: {args.period}")
        try:
             # Tara takes (coinlist, periyot, mum_bekle=True)
            Tarama.Tara(coinlist, args.period)
        except KeyboardInterrupt:
            logger.info("Stopping...")

if __name__ == "__main__":
    main()
