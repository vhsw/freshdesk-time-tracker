import os
from pathlib import Path
from shutil import copyfile

copyfile('./timer.py', os.path.expanduser('~/timer.py'))
config_file = Path(os.path.expanduser('~/config.ini'))
if not config_file.exists():
    copyfile('./config.ini', os.path.expanduser('~/config.ini'))
