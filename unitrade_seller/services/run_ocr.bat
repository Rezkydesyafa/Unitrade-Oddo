@echo off
REM Wrapper to run ocr_runner.py with oneDNN disabled
set FLAGS_use_mkldnn=0
set MKLDNN_ENABLED=0
set FLAGS_enable_pir_api=0
set FLAGS_enable_pir_in_executor=0
set PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
set FLAGS_call_stack_level=0
set PYTHONPATH=C:\Users\Lenovo\AppData\Roaming\Python\Python312\site-packages;C:\Program Files\Odoo 17.0.20260217\python\Lib\site-packages

"C:\Program Files\Odoo 17.0.20260217\python\python.exe" "d:\Unitrade_Oddo\unitrade_seller\services\ocr_runner.py" %1
