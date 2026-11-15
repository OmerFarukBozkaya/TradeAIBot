import sys
import os
from dotenv import load_dotenv

# Suppress output to keep it clean
sys.stdout = open(os.devnull, 'w')
sys.stderr = open(os.devnull, 'w')

try:
    from Trade import Trade
except Exception as e:
    sys.exit(1) # Import failed

sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

modules = sys.modules.keys()
failed = False

if 'tensorflow' in modules:
    print("FAIL: tensorflow is loaded!")
    failed = True
else:
    print("PASS: tensorflow is NOT loaded.")

if 'matplotlib.pyplot' in modules:
    print("FAIL: matplotlib.pyplot is loaded!")
    failed = True
else:
    print("PASS: matplotlib.pyplot is NOT loaded.")

if not failed:
    print("SUCCESS: Lazy loading verification passed.")
    sys.exit(0)
else:
    sys.exit(1)
