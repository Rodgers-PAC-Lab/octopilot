# Simulate a long-running process
import time

n_lines = 5
for n in range(n_lines):
    print(f'line {n} / {n_lines}')
    time.sleep(1)