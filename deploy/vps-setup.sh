#!/bin/bash
# Ejecutar EN EL VPS como root, después de clonar el repo en /var/www/mmatilde-ia
# Uso: bash deploy/vps-setup.sh

set -e

APP_DIR="/var/www/mmatilde-ia"
ENV_FILE="/etc/mmatilde/ia.env"

echo "==> Creando directorios..."
mkdir -p /etc/mmatilde
mkdir -p "$APP_DIR"
chown -R www-data:www-data "$APP_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "==> Creando $ENV_FILE"
  cat > "$ENV_FILE" << 'EOF'
GEMINI_API_KEY=PEGAR_ACA_TU_KEY_DESDE_BACKEND_IA_ENV
CATALOG_API_URL=https://api.merceriamatilde.com/api
CORS_ORIGINS=https://www.merceriamatilde.com,https://ia.merceriamatilde.com
PORT=8000
EOF
  chmod 600 "$ENV_FILE"
  echo "!! EDITÁ $ENV_FILE y pegá tu GEMINI_API_KEY real antes de continuar"
  echo "   nano $ENV_FILE"
  exit 1
fi

if grep -q "PEGAR_ACA" "$ENV_FILE"; then
  echo "!! Falta configurar GEMINI_API_KEY en $ENV_FILE"
  echo "   nano $ENV_FILE"
  exit 1
fi

echo "==> Python venv + dependencias..."
cd "$APP_DIR"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
chown -R www-data:www-data venv

echo "==> Systemd..."
cp deploy/mmatilde-ia.service /etc/systemd/system/mmatilde-ia.service
systemctl daemon-reload
systemctl enable mmatilde-ia
systemctl restart mmatilde-ia
systemctl status mmatilde-ia --no-pager

echo "==> Nginx..."
cp deploy/nginx-ia-api.conf.example /etc/nginx/sites-available/ia-api.merceriamatilde.com
ln -sf /etc/nginx/sites-available/ia-api.merceriamatilde.com /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

echo ""
echo "==> Listo. Probá:"
echo "    curl http://127.0.0.1:8000/health"
echo ""
echo "Si responde OK, pedí SSL:"
echo "    certbot --nginx -d ia-api.merceriamatilde.com"
echo ""
echo "Después:"
echo "    curl https://ia-api.merceriamatilde.com/health"
