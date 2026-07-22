# Deploy en Koyeb

## 1. Preparar el repo en GitHub

```bash
git init
git add .
git commit -m "initial"
gh repo create compresor-bot --public --push
```

## 2. Crear el servicio en Koyeb

Desde [app.koyeb.com](https://app.koyeb.com):

- **Type**: Worker (no necesita puerto HTTP)
- **GitHub**: conectá el repo
- **Dockerfile**: build automático (ya está incluido)

### Variables de entorno (obligatorias)

| Variable | De dónde sacarla |
|----------|-----------------|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `API_ID` | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `API_HASH` | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `OWNER_ID` | Tu ID numérico (opcional, `/id` en el bot) |

### Volumen persistente (opcional pero recomendado)

Sin volumen, los usuarios y la cola se pierden al reiniciar.

1. Crear un volumen en Koyeb → `compresor-data` de 1GB
2. Montarlo en `/data`
3. Agregar env var: `DATA_DIR=/data`

## 3. Build & Deploy

Koyeb buildpea automáticamente. Si querés hacerlo local primero:

```bash
docker build -t compresor-bot .
docker run -e BOT_TOKEN=... -e API_ID=... -e API_HASH=... compresor-bot
```

## Notas

- FFmpeg con libx265 ya viene instalado en la imagen.
- Los logs del bot se ven en los logs del servicio en Koyeb.
- Si NO usás volumen, la sesión de Pyrogram se recrea sola en cada deploy.
