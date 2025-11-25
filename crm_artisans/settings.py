"""
Django settings for crm_artisans project.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# SÉCURITÉ CRITIQUE
# =============================================================================

# SECRET_KEY : Variable d'environnement en prod, fallback en dev local
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if os.environ.get('DEBUG', 'True').lower() == 'true':
        # Clé de développement local uniquement
        SECRET_KEY = 'dev-secret-key-not-for-production-use-only-local'
    else:
        raise ValueError("SECRET_KEY environment variable is required in production")

# DEBUG : Toujours False en production
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# ALLOWED_HOSTS : Domaines explicites uniquement
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')
# Variable Render : ALLOWED_HOSTS=manay.fr,www.manay.fr

# CSRF : Obligatoire Django 4+
CSRF_TRUSTED_ORIGINS = [
    'https://manay.fr',
    'https://www.manay.fr',
]

# =============================================================================
# APPLICATIONS
# =============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'axes',  # Protection brute-force
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',  # Doit être en dernier
]

ROOT_URLCONF = 'crm_artisans.urls'

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

WSGI_APPLICATION = 'crm_artisans.wsgi.application'

# =============================================================================
# BASE DE DONNÉES
# =============================================================================

import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///db.sqlite3',
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# =============================================================================
# MOTS DE PASSE
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =============================================================================
# INTERNATIONALISATION
# =============================================================================

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

# =============================================================================
# FICHIERS STATIQUES
# =============================================================================

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'core' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# AUTHENTIFICATION
# =============================================================================

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',  # Doit être en premier
    'django.contrib.auth.backends.ModelBackend',
]

# =============================================================================
# PROTECTION BRUTE-FORCE (django-axes)
# =============================================================================

AXES_FAILURE_LIMIT = 5              # 5 tentatives max
AXES_COOLOFF_TIME = 0.25            # 15 minutes de blocage
AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True  # Bloque combo user+IP
AXES_RESET_ON_SUCCESS = True        # Reset compteur après succès
AXES_VERBOSE = True                 # Logs détaillés

# =============================================================================
# SÉCURITÉ PRODUCTION
# =============================================================================

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True

# =============================================================================
# SESSIONS
# =============================================================================

SESSION_COOKIE_AGE = 28800
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = 'Lax'