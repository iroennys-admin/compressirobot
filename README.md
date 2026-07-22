# CompresUltra Bot V.6 🗜️

Bot de Telegram para comprimir videos usando **FFmpeg + libx265** con la mejor calidad.

## Características

- 🗜️ Compresión de videos con libx265 (H.265/HEVC)
- ⚡ Múltiples niveles de calidad (Máxima Compresión → Mejor Calidad)
- 👥 Sistema de usuarios con planes (Free, Básico, Pro, Ultimate)
- 🧵 Sistema de cola con progreso en tiempo real
- 📊 Estadísticas de uso y datos ahorrados
- 👨‍💻 Panel de administración
- 🚫 Cancelación de compresiones en curso

## Comandos

### Usuario
| Comando | Descripción |
|---------|-------------|
| `/start` | 👋 Bienvenida con menú interactivo |
| `/help` | 📖 Ver lista de comandos |
| `/miperfil` | 👤 Tu perfil y estadísticas |
| `/miplan` | 📋 Tu plan actual |
| `/planes` | 📊 Ver planes disponibles |
| `/micalidad` | ⚙️ Ver calidad actual |
| `/calidad` | 🎛️ Cambiar calidad |
| `/cola` | 🧵 Ver estado de la cola |
| `/cancelar` | ❌ Cancelar compresión activa |
| `/reporte <texto>` | 📝 Reportar un problema |
| `/id` | 🆔 Ver tu ID |
| `/about` | ℹ️ Info del bot |
| `/ping` | 🏓 Verificar respuesta |
| `/velocidad` | ⚡ Test de velocidad |

### Admin
| Comando | Descripción |
|---------|-------------|
| `/admin` | 🛠️ Panel de administración |
| `/broadcast <msg>` | 📢 Enviar mensaje a todos |
| `/stats` | 📊 Estadísticas del bot |
| `/ban <user_id>` | ⛔ Banear usuario |
| `/unban <user_id>` | ✅ Desbanear usuario |
| `/setplan <user_id> <plan>` | 📋 Cambiar plan de usuario |

## Calidades de compresión

| Calidad | CRF | Preset | Descripción |
|---------|-----|--------|-------------|
| 🎯 Máxima Compresión | 28 | veryslow | Mínimo peso posible |
| ⚖️ Alta Compresión | 24 | slower | Buen balance peso/calidad |
| ✅ Equilibrado | 21 | slow | Calidad óptima (recomendado) |
| 💎 Mejor Calidad | 18 | medium | Máxima calidad |

## Planes

| Plan | Precio | Compresiones/día | Máx archivo |
|------|--------|-----------------|-------------|
| 🆓 Free | Gratis | 2 | 200MB |
| ⭐ Básico | $5/mes | 15 | 500MB |
| 💎 Pro | $10/mes | 50 | 2GB |
| 👑 Ultimate | $20/mes | Ilimitado | 4GB |

## Instalación

```bash
# 1. Clonar o copiar los archivos
cd BOT-ZIP/CompresUltraBot

# 2. Configurar credenciales
nano compresor_data/config.env
# Pon tu API_ID, API_HASH (https://my.telegram.org/apps)
# y BOT_TOKEN (de @BotFather)

# 3. Iniciar el bot
chmod +x start_compresor.sh
./start_compresor.sh
```

## Requisitos

- Python 3.8+
- Pyrogram 2.x
- FFmpeg con libx265
- Termux (Android) o cualquier Linux

## Estructura

```
CompresUltraBot/
├── compresor_bot.py           # Código principal del bot
├── start_compresor.sh         # Script de inicio
└── compresor_data/
    ├── config.env             # Configuración (API keys)
    ├── users.json             # Base de datos de usuarios
    ├── queue.json             # Cola de compresión
    ├── downloads/             # Videos descargados temporalmente
    └── compressed/            # Videos comprimidos temporalmente
```

## Motor de compresión

- **Códec de video**: libx265 (H.265/HEVC)
- **Códec de audio**: AAC a 128kbps
- **Contenedor**: MP4 con `faststart` (streaming-ready)
- **Compatible**: Apple (tag hvc1) y Android

## Admin

El admin del bot es **@nautaii**. Para acceder al panel de admin, usa `/admin` en privado con el bot.

---

Desarrollado con ❤️ por @nautaii
