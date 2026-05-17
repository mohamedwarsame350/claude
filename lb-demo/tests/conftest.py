# Path manipulation is handled per-file via importlib.util to avoid name
# collisions between broker/main.py and worker/main.py (both named 'main').
