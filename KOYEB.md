# Deploy en Koyeb

## Auto-deploy desde GitHub (recomendado)

Cada vez que pusheás al repo, Koyeb buildcea y deploya solo.

1. En [app.koyeb.com](https://app.koyeb.com) → **Create Service**
2. **Type**: Worker (no necesita puerto HTTP)
3. **GitHub** → conectar el repo `iroennys-admin/wsi`
4. **Builder**: Dockerfile
5. Agregar environment variables (obligatorias):

| Variable | Valor |
|----------|-------|
| `BOT_TOKEN` | Token de [@BotFather](https://t.me/BotFather) |
| `API_ID` | De [my.telegram.org/apps](https://my.telegram.org/apps) |
| `API_HASH` | De [my.telegram.org/apps](https://my.telegram.org/apps) |

6. **Deploy**

A partir de ahí, cada `git push` redeploya automáticamente.

## Build local con credenciales incluidas

Para correr en cualquier lado sin setear env vars:

```bash
./build-and-push.sh
```

Esto buildcea la imagen con las vars de `compresor_data/config.env` y la pushea a Docker Hub. En Koyeb creás Worker Service → Docker registry → `iroennys-admin/compresor-bot:latest`.

## Build manual

```bash
docker build \
  --build-arg BOT_TOKEN=... \
  --build-arg API_ID=... \
  --build-arg API_HASH=... \
  -t compresor-bot .
docker run compresor-bot
```

## Volumen persistente

Sin volumen los datos de usuarios/cola se pierden al reiniciar.

1. Crear volumen en Koyeb → `compresor-data` de 1GB
2. Montar en `/data`
3. Agregar env var: `DATA_DIR=/data`

## Notas

- FFmpeg con libx265 ya viene instalado.
- Logs del bot → pestaña Logs del servicio en Koyeb.
