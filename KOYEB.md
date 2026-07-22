# Deploy en Koyeb

## Opción A: Imagen con credenciales incluidas (más simple)

```bash
# Buildear con las vars de config.env y pushear a Docker Hub
./build-and-push.sh
```

En Koyeb: **Worker Service → Docker registry → `iroennys-admin/compresor-bot:latest`**
No necesitás configurar env vars ni volumen.

## Opción B: Build desde GitHub (sin credenciales en la imagen)

1. Subir el repo a GitHub
2. En Koyeb: **Worker Service → GitHub → conectar el repo**
3. Agregar env vars:

| Variable | De dónde sacarla |
|----------|-----------------|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `API_ID` | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `API_HASH` | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `OWNER_ID` | Tu ID numérico (opcional, `/id` en el bot) |

## Build local (cualquier opción)

```bash
docker build \
  --build-arg BOT_TOKEN=... \
  --build-arg API_ID=... \
  --build-arg API_HASH=... \
  -t compresor-bot .
docker run compresor-bot
```

## Volumen persistente (opcional)

Sin volumen los datos de usuarios/cola se pierden al reiniciar.

1. Crear volumen en Koyeb → `compresor-data` de 1GB
2. Montar en `/data`
3. Env var: `DATA_DIR=/data`

## Notas

- FFmpeg con libx265 ya viene en la imagen.
- Logs del bot → logs del servicio en Koyeb.
