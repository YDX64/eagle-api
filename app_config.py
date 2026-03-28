"""
Merkezi config loader - Tüm modüller buradan config almalı
Bu dosya circular import sorunlarını önler
"""
import os
from config import config

# FLASK_ENV'e göre config yükle
env = os.getenv('FLASK_ENV', 'development')
current_config = config.get(env, config['development'])

# Kullanım:
# from app_config import current_config
# base_url = current_config.NOWGOAL_BASE_URL
