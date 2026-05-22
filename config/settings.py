from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-dev-key')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'drf_yasg',
    'satellite',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'uz'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = False
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []

SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {},
    'USE_SESSION_AUTH': False,
    'SUPPORTED_SUBMIT_METHODS': ['get', 'post', 'put', 'patch', 'delete'],
    'DEFAULT_MODEL_RENDERING': 'example',
    'DOC_EXPANSION': 'list',
    'DEEP_LINKING': True,
    'SHOW_EXTENSIONS': True,
    'DEFAULT_INFO': 'config.urls.schema_view',
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [],   # permission yo'q — faqat filtrlash
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.JSONParser',
    ],
}

# Media files — rasm yuklash uchun
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

# AgroMonitoring — Sentinel-2 haqiqiy NDVI (asosiy manba)
# Bepul ro'yxat: https://agromonitoring.com/  → API key oling
AGRO_API_KEY = os.getenv('AGRO_API_KEY', '')

# Copernicus Data Space — zaxira manba (ixtiyoriy)
# Bepul ro'yxat: https://dataspace.copernicus.eu/
CDSE_USERNAME = os.getenv('CDSE_USERNAME', '')
CDSE_PASSWORD = os.getenv('CDSE_PASSWORD', '')

# GeoNames — suv manbalari (daryo, ko'l, kanal)
# Bepul ro'yxat: https://www.geonames.org/login  → "Free Web Services" ni yoqing
GEONAMES_USERNAME = os.getenv('GEONAMES_USERNAME', '')
