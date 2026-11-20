import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'local-assessment-only-do-not-deploy')
DEBUG = os.getenv('DEBUG', '1') == '1'
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver']
INSTALLED_APPS = ['planner']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.middleware.common.CommonMiddleware']
ROOT_URLCONF = 'config.urls'
# OSM requires browser tile requests to identify the originating site.
# Django's same-origin default suppresses Referer on cross-origin tiles.
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True}]
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
ORS_API_KEY = os.getenv('ORS_API_KEY', '')
GEOAPIFY_API_KEY = os.getenv('GEOAPIFY_API_KEY', '').strip()
ORS_BASE_URL = os.getenv('ORS_BASE_URL', 'https://api.heigit.org/openrouteservice').rstrip('/')
ORS_GEOCODE_URL = os.getenv('ORS_GEOCODE_URL', 'https://api.heigit.org/pelias/v1')
CACHE_TTL = int(os.getenv('CACHE_TTL', '3600'))
CORRIDOR_MILES = float(os.getenv('CORRIDOR_MILES', '1'))
DETOUR_FACTOR = float(os.getenv('DETOUR_FACTOR', '1.5'))
LOGGING = {'version': 1, 'disable_existing_loggers': False, 'handlers': {'console': {'class': 'logging.StreamHandler'}}, 'loggers': {'planner': {'handlers': ['console'], 'level': 'INFO'}}}
