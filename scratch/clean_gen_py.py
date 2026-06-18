import sys
import shutil
import os

try:
    import win32com
    gen_py_path = win32com.__gen_path__
    print("gen_py cache path:", gen_py_path)
    if os.path.exists(gen_py_path):
        shutil.rmtree(gen_py_path)
        print("Successfully removed gen_py cache directory.")
    else:
        print("gen_py cache directory does not exist.")
except Exception as e:
    print("Error while cleaning gen_py cache:", e)
