
import os
import multiprocessing

# Hardline Requirement: Preload app to ensure warm_cache runs at boot
preload_app = True

# Start with 1 worker until stable
workers = 1

# Bind
bind = "0.0.0.0:8080"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Timeout
timeout = 120
