# Deploy manual — Matilde IA (backend-ia)

## 1. Crear repo en GitHub

```bash
# En GitHub: merceriamatilde-ops/mmatilde-backend-ia (vacío)
cd backend-ia
git init
git remote add origin https://github.com/merceriamatilde-ops/mmatilde-backend-ia.git
git add .
git commit -m "feat: asistente IA con Gemini y catálogo"
git push -u origin main
```

## 2. Secrets en GitHub (repo mmatilde-backend-ia)

Los mismos que usa `mmatilde-backend`:

- `VPS_HOST`
- `VPS_USERNAME`
- `VPS_SSH_KEY`
- `VPS_PORT`

## 3. En el VPS (una sola vez)

```bash
sudo mkdir -p /var/www/mmatilde-ia
sudo chown www-data:www-data /var/www/mmatilde-ia

# Variables de entorno (NO commitear)
sudo nano /etc/mmatilde/ia.env
```

Contenido de `/etc/mmatilde/ia.env`:

```
GEMINI_API_KEY=tu_key_de_google_ai
CATALOG_API_URL=https://api.merceriamatilde.com/api
CORS_ORIGINS=https://www.merceriamatilde.com,https://ia.merceriamatilde.com
PORT=8000
```

```bash
# Systemd
sudo cp deploy/mmatilde-ia.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mmatilde-ia
sudo systemctl start mmatilde-ia

# Nginx + SSL (certbot igual que api.merceriamatilde.com)
sudo cp deploy/nginx-ia-api.conf.example /etc/nginx/sites-available/ia-api.merceriamatilde.com
sudo ln -s /etc/nginx/sites-available/ia-api.merceriamatilde.com /etc/nginx/sites-enabled/
sudo certbot --nginx -d ia-api.merceriamatilde.com
```

## 4. DNS

Registro `A` → `ia-api.merceriamatilde.com` → IP del VPS

## 5. Verificar

```bash
curl https://ia-api.merceriamatilde.com/health
```

Debe responder `{"status":"ok","gemini_configured":true}`
