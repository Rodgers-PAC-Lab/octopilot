# Simulate a long-running process
import time
import paclab_sukrith

n_lines = 15
for n in range(n_lines):
    print(f'line {n} / {n_lines}')
    time.sleep(1)
    
    #~ if n == 3:
        #~ 1/0
