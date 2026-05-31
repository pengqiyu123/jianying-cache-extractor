"""Standalone entry point for PyInstaller."""
import sys
import os

# When running from PyInstaller bundle, add _internal to path so our package is found
if getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.join(sys._MEIPASS, 'src'))

import jianying_controller.gui
jianying_controller.gui.main()
