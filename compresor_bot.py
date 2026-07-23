#!/usr/bin/env python3
"""
CompresUltra Bot V.6 — Telegram video compression bot
Motor: FFmpeg + libx265 | Admin: @nautaii
"""

import os, sys, json, time, asyncio, subprocess, shutil, math, re, uuid, traceback, sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from collections import deque
from typing import Tuple

# Auto-cargar config.env si existe
_env_file = Path("compresor_data/config.env")
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from pyrogram import Client, filters, enums, idle
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
)
from pyrogram.errors import FloodWait, RPCError

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = os.getenv("API_ID", "")
API_HASH = os.getenv("API_HASH", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "nautaii")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

DATA_DIR = Path(os.getenv("DATA_DIR", "compresor_data"))
DOWNLOADS_DIR = DATA_DIR / "downloads"
COMPRESSED_DIR = DATA_DIR / "compressed"
DB_PATH = DATA_DIR / "bot.db"

for d in [DOWNLOADS_DIR, COMPRESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Calidades de compresión
QUALITY_PRESETS = {
    "ultra":     {"label": "🎯 Máxima Compresión",  "crf": 28, "preset": "veryslow", "desc": "Mínimo peso posible"},
    "high":      {"label": "⚖️ Alta Compresión",    "crf": 24, "preset": "slower",   "desc": "Buen balance peso/calidad"},
    "balanced":  {"label": "✅ Equilibrado ✓",       "crf": 21, "preset": "slow",     "desc": "Calidad óptima recomendada"},
    "best":      {"label": "💎 Mejor Calidad",       "crf": 18, "preset": "medium",   "desc": "Máxima calidad (menos compresión)"},
}
DEFAULT_QUALITY = "balanced"

# Modos de compresión (codec + audio)
COMPRESSION_MODES = {
    "hevc_aac":  {"label": "🎯 H.265 + AAC",   "vcodec": "libx265", "acodec": "aac",     "abitrate": "128k", "desc": "Estándar, buena compresión"},
    "hevc_opus": {"label": "🔊 H.265 + Opus",   "vcodec": "libx265", "acodec": "libopus", "abitrate": "64k",  "desc": "Audio más ligero, misma calidad"},
    "h264_aac":  {"label": "🔄 H.264 + AAC",    "vcodec": "libx264", "acodec": "aac",     "abitrate": "128k", "desc": "Máxima compatibilidad"},
}
DEFAULT_MODE = "hevc_aac"

# Planes
PLANS = {
    "free": {
        "name": "🆓 Free", "daily": 2, "max_mb": 200,
        "price": "Gratis", "badge": "🆓",
        "features": ["2 compresiones/día", "Máx 200MB por archivo", "Cola normal"]
    },
    "basic": {
        "name": "⭐ Básico", "daily": 15, "max_mb": 500,
        "price": "$5 USD/mes", "badge": "⭐",
        "features": ["15 compresiones/día", "Máx 500MB por archivo", "Prioridad media",
                     "Descarga directa"]
    },
    "pro": {
        "name": "💎 Pro", "daily": 50, "max_mb": 2000,
        "price": "$10 USD/mes", "badge": "💎",
        "features": ["50 compresiones/día", "Máx 2GB por archivo", "Alta prioridad",
                     "2 compresiones simultáneas", "Descarga directa"]
    },
    "ultimate": {
        "name": "👑 Ultimate", "daily": -1, "max_mb": 4000,
        "price": "$20 USD/mes", "badge": "👑",
        "features": ["Ilimitado 🚀", "Máx 4GB por archivo", "Máxima prioridad",
                     "3 simultáneas", "Soporte VIP 24/7"]
    }
}

# ═══════════════════════════════════════════════════════════════
# BASE DE DATOS (JSON)
# ═══════════════════════════════════════════════════════════════

_db_lock = asyncio.Lock()
_db_conn = None

def _init_db():
    global _db_conn
    _db_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _db_conn.row_factory = sqlite3.Row
    _db_conn.execute("PRAGMA journal_mode=WAL")
    _db_conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT DEFAULT '',
        first_name TEXT DEFAULT '',
        plan TEXT DEFAULT 'free',
        plan_expiry TEXT,
        quality TEXT DEFAULT 'balanced',
        total_compressions INTEGER DEFAULT 0,
        total_saved_bytes INTEGER DEFAULT 0,
        daily_count INTEGER DEFAULT 0,
        daily_date TEXT DEFAULT '',
        joined TEXT DEFAULT '',
        is_banned INTEGER DEFAULT 0
    )""")
    _db_conn.execute("""CREATE TABLE IF NOT EXISTS queue (
        id TEXT PRIMARY KEY,
        user_id INTEGER,
        username TEXT DEFAULT '',
        chat_id INTEGER,
        message_id INTEGER,
        file_path TEXT,
        original_size INTEGER DEFAULT 0,
        quality TEXT DEFAULT 'balanced',
        status TEXT DEFAULT 'waiting',
        progress REAL DEFAULT 0,
        created_at TEXT,
        status_msg_id INTEGER DEFAULT 0,
        saved_bytes INTEGER DEFAULT 0,
        output_path TEXT,
        error TEXT
    )""")
    # Migración: columna mode para cola
    try: _db_conn.execute("ALTER TABLE queue ADD COLUMN mode TEXT DEFAULT 'hevc_aac'")
    except: pass
    _db_conn.commit()

def _db():
    if _db_conn is None:
        _init_db()
    return _db_conn

async def load_users():
    async with _db_lock:
        rows = _db().execute("SELECT * FROM users").fetchall()
        return {str(r["user_id"]): dict(r) for r in rows}

async def get_user(user_id, username="", first_name=""):
    uid = int(user_id)
    async with _db_lock:
        db = _db()
        row = db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        if row is None:
            today = datetime.now().strftime("%Y-%m-%d")
            db.execute(
                "INSERT INTO users (user_id, username, first_name, daily_date, joined) VALUES (?,?,?,?,?)",
                (uid, username, first_name, today, datetime.now().isoformat())
            )
            db.commit()
            row = db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            if username:
                db.execute("UPDATE users SET username=? WHERE user_id=?", (username, uid))
            if first_name:
                db.execute("UPDATE users SET first_name=? WHERE user_id=?", (first_name, uid))
            if row["daily_date"] != today:
                db.execute("UPDATE users SET daily_count=0, daily_date=? WHERE user_id=?", (today, uid))
            db.commit()
        return dict(row)

async def update_user(user_id, **kwargs):
    uid = int(user_id)
    async with _db_lock:
        db = _db()
        row = db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        if row is None:
            return None
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [uid]
        db.execute(f"UPDATE users SET {cols} WHERE user_id=?", vals)
        db.commit()
        return dict(db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone())

# ── Queue ──
async def load_queue():
    async with _db_lock:
        rows = _db().execute("SELECT * FROM queue ORDER BY rowid").fetchall()
        return [dict(r) for r in rows]

async def add_to_queue(entry):
    async with _db_lock:
        cols = ", ".join(entry.keys())
        placeholders = ", ".join("?" for _ in entry)
        _db().execute(f"INSERT INTO queue ({cols}) VALUES ({placeholders})", list(entry.values()))
        _db().commit()

async def remove_from_queue(job_id):
    async with _db_lock:
        _db().execute("DELETE FROM queue WHERE id=?", (job_id,))
        _db().commit()

async def update_job(job_id, **kwargs):
    async with _db_lock:
        db = _db()
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [job_id]
        db.execute(f"UPDATE queue SET {cols} WHERE id=?", vals)
        db.commit()

async def get_user_job(user_id):
    async with _db_lock:
        row = _db().execute(
            "SELECT * FROM queue WHERE user_id=? AND status IN ('waiting','processing') LIMIT 1",
            (int(user_id),)
        ).fetchone()
        return dict(row) if row else None

# ═══════════════════════════════════════════════════════════════
# INLINE KEYBOARDS
# ═══════════════════════════════════════════════════════════════

def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Mi Perfil", callback_data="profile"),
         InlineKeyboardButton("📋 Mi Plan", callback_data="myplan")],
        [InlineKeyboardButton("⚙️ Cambiar Calidad", callback_data="quality"),
         InlineKeyboardButton("📊 Planes", callback_data="plans")],
        [InlineKeyboardButton("🧵 Ver Cola", callback_data="queue"),
         InlineKeyboardButton("❓ Ayuda", callback_data="help")],
        [InlineKeyboardButton("👨‍💻 Desarrollador", callback_data="developer"),
         InlineKeyboardButton("📝 Reportar", callback_data="report")],
    ])

def back_kb(action="menu"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Volver", callback_data=action)]
    ])

def quality_kb(current=None):
    kb = []
    for key, q in QUALITY_PRESETS.items():
        mark = " ✅" if key == current else ""
        kb.append([InlineKeyboardButton(f"{q['label']}{mark}", callback_data=f"qset:{key}")])
    kb.append([InlineKeyboardButton("🔙 Volver", callback_data="menu")])
    return InlineKeyboardMarkup(kb)

def quality_kb_video(current=None, mode_key=None):
    kb = []
    for key, q in QUALITY_PRESETS.items():
        mark = " ✅" if key == current else ""
        kb.append([InlineKeyboardButton(f"{q['label']}{mark}", callback_data=f"cqvid:{mode_key}:{key}")])
    kb.append([InlineKeyboardButton("🔙 Volver", callback_data="cmode:sel")])
    return InlineKeyboardMarkup(kb)

def plans_kb():
    kb = []
    for key in PLANS:
        if key == "free": continue
        kb.append([InlineKeyboardButton(f"{PLANS[key]['name']} — {PLANS[key]['price']}",
                                        callback_data=f"pland:{key}")])
    kb.append([InlineKeyboardButton("🔙 Volver", callback_data="menu")])
    return InlineKeyboardMarkup(kb)

def confirm_cancel_kb(job_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sí, cancelar", callback_data=f"cnfrm_cancel:{job_id}")],
        [InlineKeyboardButton("❌ No, continuar", callback_data="queue")]
    ])

# ═══════════════════════════════════════════════════════════════
# MENSAJES FORMATEADOS
# ═══════════════════════════════════════════════════════════════

WELCOME_MSG = """👋 ¡Hola, {name}!

🤖 Bienvenido a <b>CompresUltra Bot V.6</b>
━━━━━━━━━━━━━━━━━━━━━
🗜️ <b>Comprimo tus videos con la mejor calidad</b>
⚡ Motor: FFmpeg + libx265
━━━━━━━━━━━━━━━━━━━━━
📋 Tu plan: {plan}
🌐 Modo: Público
━━━━━━━━━━━━━━━━━━━━━

📌 <b>Envía un video como documento o directo para comprimirlo.</b>

<i>Usa los botones de abajo para navegar</i> 👇"""

HELP_MSG = """📖 <b>CompresUltra Bot — Comandos</b>
━━━━━━━━━━━━━━━━━━━━━

👤 <b>Usuario:</b>
/start — 👋 Bienvenida con menú
/help — 📖 Ver esta ayuda
/miperfil — 👤 Tu perfil y estadísticas
/miplan — 📋 Tu plan con días restantes
/planes — 📊 Ver planes disponibles
/micalidad — ⚙️ Tu calidad actual
/calidad — 🎛️ Cambiar calidad (menú visual)
/cola — 🧵 Ver estado de la cola
/cancelar — ❌ Cancelar tu compresión activa
/reporte — 📝 Reportar un problema
/id — 🆔 Ver tu ID
/about — ℹ️ Info del bot
/ping — 🏓 Verificar si el bot responde
/velocidad — ⚡ Test de velocidad

━━━━━━━━━━━━━━━━━━━━━
📌 <i>Envía cualquier video para comprimirlo automáticamente.</i>"""

ABOUT_MSG = """ℹ️ <b>CompresUltra Bot V.6</b>
━━━━━━━━━━━━━━━━━━━━━
🗜️ Bot de compresión de videos
⚡ FFmpeg + libx265
👨‍💻 Desarrollador: {admin}
📅 Versión: 6.0
━━━━━━━━━━━━━━━━━━━━━
<i>Comprime tus videos sin perder calidad
y ahorra espacio en Telegram.</i>"""

# ═══════════════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════════════

def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"

def human_time(seconds: int) -> str:
    if seconds < 60: return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60: return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"

def _progress_bar(pct: float, width: int = 10) -> str:
    filled = int(pct / 100 * width)
    return "▓" * filled + "░" * (width - filled)

# Cache de admin ID (se resuelve al arrancar)
ADMIN_USER_ID = None

# ── Helpers de texto (desduplicados) ──

def _profile_text(u, user_id, first_name):
    plan_name = PLANS.get(u["plan"], PLANS["free"])["name"]
    quality_label = QUALITY_PRESETS.get(u.get("quality", DEFAULT_QUALITY),
                                        QUALITY_PRESETS[DEFAULT_QUALITY])["label"]
    daily_limit = PLANS.get(u["plan"], PLANS["free"])["daily"]
    limit_str = f"{daily_limit}" if daily_limit > 0 else "∞"
    return (
        f"👤 <b>Mi Perfil</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Nombre: {first_name}\n"
        f"📋 Plan: {plan_name}\n"
        f"⚙️ Calidad: {quality_label}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Estadísticas</b>\n"
        f"🗜️ Compresiones: {u.get('total_compressions', 0)}\n"
        f"💾 Datos ahorrados: {human_size(u.get('total_saved_bytes', 0))}\n"
        f"📅 Hoy: {u.get('daily_count', 0)}/{limit_str}"
    )

def _plan_text(u):
    plan = PLANS.get(u["plan"], PLANS["free"])
    txt = (
        f"📋 <b>Tu Plan: {plan['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Precio: {plan['price']}\n"
        f"📅 Compresiones/día: {plan['daily'] if plan['daily'] > 0 else '∞ Ilimitado'}\n"
        f"📦 Máx por archivo: {plan['max_mb']}MB\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Características:</b>\n" + "\n".join(f"• {f}" for f in plan['features'])
    )
    if u["plan"] != "free" and u.get("plan_expiry"):
        try:
            expiry = datetime.fromisoformat(u["plan_expiry"])
            remaining = (expiry - datetime.now()).days
            txt += f"\n⏳ Días restantes: {remaining}"
        except: pass
    return txt

def is_admin(user_id: int, username: str = "") -> bool:
    if OWNER_ID and user_id == OWNER_ID:
        return True
    if ADMIN_USER_ID and user_id == ADMIN_USER_ID:
        return True
    if username and username.lower().lstrip("@") == ADMIN_USERNAME:
        return True
    return False

def check_space(path: str, needed_bytes: int) -> bool:
    stat = shutil.disk_usage(path)
    return stat.free > needed_bytes * 1.5  # 50% margin

# ═══════════════════════════════════════════════════════════════
# MOTOR DE COMPRESIÓN (FFmpeg)
# ═══════════════════════════════════════════════════════════════

async def ffmpeg_compress(
    input_path: str, output_path: str, quality_key: str,
    mode_key: str = DEFAULT_MODE,
    progress_callback=None
) -> Tuple[bool, str, int]:
    """
    Comprime un video según modo y calidad.
    Retorna (exito, mensaje, duracion_segundos).
    """
    mode = COMPRESSION_MODES[mode_key]
    quality = QUALITY_PRESETS[quality_key]
    cmd = [
        "ffmpeg", "-i", input_path,
        "-c:v", mode["vcodec"],
        "-crf", str(quality["crf"]),
        "-preset", quality["preset"],
        "-c:a", mode["acodec"], "-b:a", mode["abitrate"],
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
    ]
    if mode["vcodec"] == "libx265":
        cmd += ["-tag:v", "hvc1"]
    cmd += ["-stats", "-y", output_path]

    start = time.time()
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    global _current_proc
    _current_proc = proc

    # Parse progress from FFmpeg stderr
    last_update = 0
    total_frames_est = 0
    frame_pattern = re.compile(r"frame=\s*(\d+)")
    dur_pattern = re.compile(r"Duration: (\d+):(\d+):(\d+\.\d+)")

    async def read_progress():
        nonlocal last_update, total_frames_est
        buf = b""
        while True:
            chunk = await proc.stderr.read(4096)
            if not chunk:
                break
            buf += chunk
            text = buf.decode("utf-8", errors="replace")

            # Estimar frames totales desde la duración
            if total_frames_est == 0:
                m = dur_pattern.search(text)
                if m:
                    h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                    total_secs = h * 3600 + mn * 60 + s
                    fps_m = re.search(r"(\d+\.?\d*)\s*fps", text)
                    fps = float(fps_m.group(1)) if fps_m else 30.0
                    total_frames_est = int(total_secs * fps) or 1

            # Extraer frame actual y calcular %
            frames = frame_pattern.findall(text)
            if frames and progress_callback:
                curr = int(frames[-1])
                if total_frames_est > 0:
                    pct = min(curr / total_frames_est * 100, 99.9)
                    now = time.time()
                    if now - last_update >= 3:
                        last_update = now
                        # fire-and-forget para no bloquear la lectura
                        asyncio.create_task(progress_callback(pct))

    read_task = asyncio.create_task(read_progress())
    try:
        await asyncio.wait_for(proc.wait(), timeout=7200)  # 2h max
    except asyncio.TimeoutError:
        proc.kill()
        read_task.cancel()
        return False, "Tiempo de compresión agotado (>2h)", int(time.time() - start)
    read_task.cancel()

    duration = int(time.time() - start)

    if proc.returncode != 0:
        _current_proc = None
        return False, f"FFmpeg error (código {proc.returncode})", duration

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 100:
        _current_proc = None
        return False, "El archivo de salida no se generó correctamente", duration

    _current_proc = None
    return True, "Compresión exitosa", duration


# ═══════════════════════════════════════════════════════════════
# GESTOR DE COLA
# ═══════════════════════════════════════════════════════════════

_queue_worker_task = None
_cancellation_flag = set()  # job_ids marcados para cancelación
_current_proc = None  # proc ffmpeg activo, para matarlo al cancelar
_pending_videos = {}  # user_id -> {msg_id, chat_id, file_size, username}

async def queue_worker(client: Client):
    """Procesa trabajos de la cola en orden FIFO."""
    while True:
        try:
            q = await load_queue()
            # Filtra jobs pendientes o en proceso
            pending = [j for j in q if j["status"] in ("waiting", "processing")]
            if not pending:
                await asyncio.sleep(2)
                continue

            # Busca el primero en espera
            job = None
            for j in q:
                if j["status"] == "waiting":
                    job = j
                    break

            if not job:
                await asyncio.sleep(2)
                continue

            await update_job(job["id"], status="processing")

            user_id = job["user_id"]
            chat_id = job["chat_id"]
            msg_id = job["message_id"]
            file_path = job["file_path"]
            quality_key = job.get("quality", DEFAULT_QUALITY)
            mode_key = job.get("mode", DEFAULT_MODE)
            original_size = job.get("original_size", 0)

            # Verificar que el archivo existe (pudo borrarse tras reinicio)
            if not os.path.exists(file_path):
                await update_job(job["id"], status="failed", error="Archivo no encontrado")
                try:
                    await client.send_message(
                        chat_id, "❌ El archivo original ya no existe. Envía el video de nuevo.",
                        reply_to_message_id=msg_id
                    )
                except: pass
                await remove_from_queue(job["id"])
                continue

            # Verificar si fue cancelado
            if job["id"] in _cancellation_flag:
                _cancellation_flag.discard(job["id"])
                await update_job(job["id"], status="cancelled")
                try:
                    await client.send_message(
                        chat_id, "❌ Compresión cancelada.",
                        reply_to_message_id=msg_id
                    )
                except: pass
                continue

            # Notificar inicio
            try:
                status_msg = await client.send_message(
                    chat_id,
                    f"⏳ <b>Comprimiendo video...</b>\n"
                    f"📏 Tamaño original: {human_size(original_size)}\n"
                    f"⚙️ Calidad: {QUALITY_PRESETS[quality_key]['label']}\n"
                    f"🎬 {_progress_bar(0)} 0%",
                    reply_to_message_id=msg_id
                )
                job["status_msg_id"] = status_msg.id
                await update_job(job["id"], status_msg_id=status_msg.id)
            except: pass

            # Callback de progreso
            async def progress_callback(pct, _job_id=job["id"], _cid=chat_id, _smid=job.get("status_msg_id")):
                if _job_id in _cancellation_flag:
                    if _current_proc:
                        try: _current_proc.kill()
                        except: pass
                    return
                try:
                    # También actualizar job en db
                    await update_job(_job_id, progress=pct)
                    if _smid:
                        await client.edit_message_text(
                            _cid, _smid,
                            f"⏳ <b>Comprimiendo video...</b>\n"
                            f"📏 Tamaño original: {human_size(original_size)}\n"
                            f"⚙️ Calidad: {QUALITY_PRESETS[quality_key]['label']}\n"
                            f"🎬 {_progress_bar(pct)} {pct:.1f}%"
                        )
                except: pass

            # Comprimir
            output_filename = f"{job['id']}_compressed.mp4"
            output_path = str(COMPRESSED_DIR / output_filename)

            success, msg, dur = await ffmpeg_compress(
                file_path, output_path, quality_key, mode_key, progress_callback
            )

            # Si fue cancelado durante procesamiento
            if job["id"] in _cancellation_flag:
                _cancellation_flag.discard(job["id"])
                await update_job(job["id"], status="cancelled")
                for p in [file_path, output_path]:
                    try: os.remove(p)
                    except: pass
                try:
                    await client.edit_message_text(
                        chat_id, job.get("status_msg_id", 0),
                        "❌ Compresión cancelada."
                    )
                except: pass
                continue

            if not success:
                await update_job(job["id"], status="failed", error=msg)
                try:
                    await client.edit_message_text(
                        chat_id, job.get("status_msg_id", 0),
                        f"❌ <b>Error de compresión</b>\n{msg}"
                    )
                except: pass
                for p in [file_path, output_path]:
                    try: os.remove(p)
                    except: pass
                continue

            compressed_size = os.path.getsize(output_path)
            saved = original_size - compressed_size if original_size > 0 else 0

            # Si el comprimido es más grande, enviar original
            if compressed_size >= original_size * 0.95 and original_size > 0:
                await update_job(job["id"], status="completed", saved_bytes=0)
                try:
                    await client.edit_message_text(
                        chat_id, job.get("status_msg_id", 0),
                        f"⚠️ <b>El video ya está optimizado.</b>\n"
                        f"El archivo comprimido no reduce el tamaño.\n"
                        f"📏 Original: {human_size(original_size)}"
                    )
                except: pass
                # Intentar reenviar el video original
                try:
                    await client.copy_message(chat_id, chat_id, msg_id)
                except: pass
            else:
                # Enviar comprimido
                await update_job(job["id"], status="completed",
                                 output_path=output_path, saved_bytes=saved)
                try:
                    # Actualizar mensaje de estado
                    ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                    await client.edit_message_text(
                        chat_id, job.get("status_msg_id", 0),
                        f"✅ <b>¡Compresión completada!</b>\n"
                        f"📏 {human_size(original_size)} → {human_size(compressed_size)} "
                        f"({ratio:.1f}% menos)\n"
                        f"⚡ Tiempo: {human_time(int(dur))}\n"
                        f"⬇️ <i>Enviando archivo...</i>"
                    )

                    # Enviar el video comprimido
                    caption = (
                        f"🗜️ <b>CompresUltra Bot V.6</b>\n"
                        f"📏 Original: {human_size(original_size)}\n"
                        f"📦 Comprimido: {human_size(compressed_size)} ({ratio:.1f}% menos)\n"
                        f"⚙️ Calidad: {QUALITY_PRESETS[quality_key]['label']}\n"
                        f"⚡ Tiempo: {human_time(int(dur))}"
                    )
                    await client.send_document(
                        chat_id, output_path, caption=caption,
                        reply_to_message_id=msg_id
                    )

                    # Actualizar mensaje de estado
                    await client.edit_message_text(
                        chat_id, job.get("status_msg_id", 0),
                        f"✅ <b>Compresión completada ✓</b>\n"
                        f"📏 {human_size(original_size)} → {human_size(compressed_size)} ({ratio:.1f}% menos)\n"
                        f"⚡ Tiempo: {human_time(int(dur))}"
                    )
                except RPCError as e:
                    await client.edit_message_text(
                        chat_id, job.get("status_msg_id", 0),
                        f"⚠️ <b>Error al enviar:</b> {e}\n"
                        f"📏 Original: {human_size(original_size)} | Comprimido: {human_size(compressed_size)}"
                    )

            # Actualizar estadísticas del usuario
            u = await get_user(user_id)
            new_daily = u.get("daily_count", 0) + 1
            new_total = u.get("total_compressions", 0) + 1
            new_saved = u.get("total_saved_bytes", 0) + max(0, saved)
            await update_user(user_id, daily_count=new_daily,
                             total_compressions=new_total, total_saved_bytes=new_saved)

            # Limpiar archivos
            try:
                os.remove(file_path)
                if os.path.exists(output_path) and saved >= 0:
                    os.remove(output_path)
            except: pass

            # Remover job de cola
            await remove_from_queue(job["id"])

        except Exception as e:
            print(f"[Queue Worker Error] {traceback.format_exc()}")
            await asyncio.sleep(5)


# ═══════════════════════════════════════════════════════════════
# HANDLERS — COMANDOS
# ═══════════════════════════════════════════════════════════════

app = Client(
    "compresor_session",
    api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN,
    workdir=str(DATA_DIR)
)

# ── /start ──

@app.on_message(filters.command("start"))
async def start_cmd(client: Client, msg: Message):
    u = await get_user(msg.from_user.id, msg.from_user.username or "",
                       msg.from_user.first_name)
    plan_name = PLANS.get(u["plan"], PLANS["free"])["name"]
    await msg.reply_text(
        WELCOME_MSG.format(name=msg.from_user.first_name, plan=plan_name),
        reply_markup=main_menu_kb()
    )

# ── /help ──

@app.on_message(filters.command("help"))
async def help_cmd(client: Client, msg: Message):
    await msg.reply_text(HELP_MSG, reply_markup=back_kb("menu"))

# ── /miperfil ──

@app.on_message(filters.command("miperfil"))
async def perfil_cmd(client: Client, msg: Message):
    u = await get_user(msg.from_user.id)
    txt = _profile_text(u, msg.from_user.id, msg.from_user.first_name)
    await msg.reply_text(txt, reply_markup=back_kb("menu"))

# ── /miplan ──

@app.on_message(filters.command("miplan"))
async def miplan_cmd(client: Client, msg: Message):
    u = await get_user(msg.from_user.id)
    txt = _plan_text(u)
    await msg.reply_text(txt, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Ver Planes", callback_data="plans")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu")]
    ]))

# ── /planes ──

@app.on_message(filters.command("planes"))
async def planes_cmd(client: Client, msg: Message):
    await show_plans(msg, edit=False)

# ── /micalidad ──

@app.on_message(filters.command("micalidad"))
async def micalidad_cmd(client: Client, msg: Message):
    u = await get_user(msg.from_user.id)
    q = u.get("quality", DEFAULT_QUALITY)
    ql = QUALITY_PRESETS.get(q, QUALITY_PRESETS[DEFAULT_QUALITY])
    txt = (
        f"⚙️ <b>Tu calidad actual</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ql['label']}\n"
        f"📝 {ql['desc']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Usa /calidad para cambiar."
    )
    await msg.reply_text(txt, reply_markup=quality_kb(q))

# ── /calidad ──

@app.on_message(filters.command("calidad"))
async def calidad_cmd(client: Client, msg: Message):
    u = await get_user(msg.from_user.id)
    await msg.reply_text(
        "🎛️ <b>Selecciona la calidad de compresión:</b>\n\n"
        "<i>Más compresión = menos peso, pero menor calidad.</i>",
        reply_markup=quality_kb(u.get("quality", DEFAULT_QUALITY))
    )

# ── /cola ──

@app.on_message(filters.command("cola"))
async def cola_cmd(client: Client, msg: Message):
    await show_queue(msg, edit=False)

# ── /cancelar ──

@app.on_message(filters.command("cancelar"))
async def cancelar_cmd(client: Client, msg: Message):
    job = await get_user_job(msg.from_user.id)
    if not job:
        await msg.reply_text("❌ No tienes ninguna compresión activa.")
        return
    await msg.reply_text(
        f"⚠️ <b>¿Cancelar compresión?</b>\n"
        f"ID: <code>{job['id'][:8]}</code>\n"
        f"Estado: {job['status']}",
        reply_markup=confirm_cancel_kb(job["id"])
    )

# ── /reporte ──

@app.on_message(filters.command("reporte"))
async def reporte_cmd(client: Client, msg: Message):
    txt = msg.text[len("/reporte"):].strip()
    if not txt:
        await msg.reply_text(
            "📝 <b>Reportar un problema</b>\n\n"
            "Uso: <code>/reporte descripción del problema</code>\n\n"
            "Ejemplo: <code>/reporte el bot no comprime videos mp4</code>",
            reply_markup=back_kb("menu")
        )
        return
    # Enviar al admin
    admin_id = None
    try:
        user = await client.get_users(ADMIN_USERNAME)
        admin_id = user.id
    except: pass
    if admin_id:
        try:
            await client.send_message(
                admin_id,
                f"📝 <b>Reporte de usuario</b>\n"
                f"👤 {msg.from_user.first_name} (@{msg.from_user.username or 'N/A'})\n"
                f"🆔 <code>{msg.from_user.id}</code>\n"
                f"💬 {txt}"
            )
        except: pass
    await msg.reply_text("✅ <b>Reporte enviado.</b>\nGracias por ayudar a mejorar el bot.", reply_markup=back_kb("menu"))

# ── /id ──

@app.on_message(filters.command("id"))
async def id_cmd(client: Client, msg: Message):
    txt = f"🆔 <b>Tu ID:</b> <code>{msg.from_user.id}</code>"
    if msg.reply_to_message and msg.reply_to_message.from_user:
        txt += f"\n👤 <b>Usuario:</b> <code>{msg.reply_to_message.from_user.id}</code>"
    if msg.chat.type != enums.ChatType.PRIVATE:
        txt += f"\n💬 <b>Chat:</b> <code>{msg.chat.id}</code>"
    await msg.reply_text(txt)

# ── /about ──

@app.on_message(filters.command("about"))
async def about_cmd(client: Client, msg: Message):
    await msg.reply_text(
        ABOUT_MSG.format(admin=f"@{ADMIN_USERNAME}"),
        reply_markup=back_kb("menu")
    )

# ── /ping ──

@app.on_message(filters.command("ping"))
async def ping_cmd(client: Client, msg: Message):
    print(f"[CMD] /ping from {msg.from_user.id}")
    start = time.time()
    m = await msg.reply_text("🏓 Pong...")
    delta = int((time.time() - start) * 1000)
    await m.edit_text(f"🏓 <b>Pong!</b> {delta}ms")

# ── /velocidad ──

@app.on_message(filters.command("velocidad"))
async def velocidad_cmd(client: Client, msg: Message):
    m = await msg.reply_text("⚡ <b>Test de velocidad...</b>")
    # Prueba de escritura
    start = time.time()
    fsize = 50 * 1024 * 1024  # 50MB
    test_file = COMPRESSED_DIR / "speed_test.tmp"
    try:
        with open(test_file, "wb") as f:
            f.write(os.urandom(fsize))
        write_time = time.time() - start
        write_speed = fsize / write_time / 1024 / 1024  # MB/s

        # Prueba de lectura
        start = time.time()
        with open(test_file, "rb") as f:
            while f.read(8192):
                pass
        read_time = time.time() - start
        read_speed = fsize / read_time / 1024 / 1024

        os.remove(test_file)

        # Ping a Telegram
        start = time.time()
        me = await client.get_me()
        api_ping = int((time.time() - start) * 1000)

        await m.edit_text(
            f"⚡ <b>Test de Velocidad</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💾 Escritura: {write_speed:.1f} MB/s\n"
            f"📖 Lectura: {read_speed:.1f} MB/s\n"
            f"🌐 API Ping: {api_ping}ms\n"
            f"📊 CPU: {os.cpu_count()} cores\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Los resultados pueden variar según la carga del servidor.</i>",
            reply_markup=back_kb("menu")
        )
    except Exception as e:
        await m.edit_text(f"⚠️ Error en test: {e}")

# ═══════════════════════════════════════════════════════════════
# HANDLERS — VIDEOS
# ═══════════════════════════════════════════════════════════════

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, msg: Message):
    user_id = msg.from_user.id

    # ¿Baneado?
    u = await get_user(user_id)
    if u.get("is_banned"):
        await msg.reply_text("⛔ Estás baneado del bot.")
        return

    # Obtener info del archivo
    file_info = None
    file_size = 0
    if msg.video:
        file_info = msg.video
        file_size = msg.video.file_size or 0
    elif msg.document:
        mime = msg.document.mime_type or ""
        if not mime.startswith("video/"):
            return
        file_info = msg.document
        file_size = msg.document.file_size or 0

    if not file_info:
        return

    # Verificar límite diario
    plan_key = u.get("plan", "free")
    plan = PLANS.get(plan_key, PLANS["free"])
    daily_limit = plan["daily"]
    if daily_limit > 0 and u.get("daily_count", 0) >= daily_limit:
        await msg.reply_text(
            f"❌ <b>Límite diario alcanzado</b>\n"
            f"Ya usaste tus {daily_limit} compresiones de hoy.\n"
            f"📊 Mejora tu plan en /planes para obtener más.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Ver Planes", callback_data="plans")]
            ])
        )
        return

    # Verificar tamaño máximo
    max_bytes = plan["max_mb"] * 1024 * 1024
    if file_size > max_bytes:
        await msg.reply_text(
            f"❌ <b>Archivo demasiado grande</b>\n"
            f"📏 Tamaño: {human_size(file_size)}\n"
            f"📦 Límite de tu plan ({plan['name']}): {plan['max_mb']}MB\n\n"
            f"📊 Mejora tu plan en /planes para comprimir archivos más grandes.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Ver Planes", callback_data="plans")]
            ])
        )
        return

    # Verificar espacio en disco
    if not check_space(str(DOWNLOADS_DIR), file_size):
        await msg.reply_text("⚠️ El servidor no tiene suficiente espacio. Intenta más tarde.")
        return

    # Verificar que no tenga otro trabajo activo
    existing = await get_user_job(user_id)
    if existing:
        await msg.reply_text(
            f"⚠️ <b>Ya tienes una compresión en curso.</b>\n"
            f"ID: <code>{existing['id'][:8]}</code>\n"
            f"Estado: {existing['status']}\n"
            f"Usa /cancelar para cancelarla primero.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧵 Ver Cola", callback_data="queue")],
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"cnfrm_cancel:{existing['id']}")]
            ])
        )
        return

    # Guardar pending y mostrar selección de modo
    _pending_videos[user_id] = {
        "msg_id": msg.id, "chat_id": msg.chat.id,
        "file_size": file_size, "username": msg.from_user.username or "",
    }

    rows = [[InlineKeyboardButton(m["label"], callback_data=f"cmode:{k}")] for k, m in COMPRESSION_MODES.items()]
    rows.append([InlineKeyboardButton("❌ Cancelar", callback_data="del_pending")])
    await msg.reply_text(
        f"📹 <b>Video recibido</b>\n📏 Tamaño: {human_size(file_size)}\n\n"
        f"<b>Seleccioná el modo de compresión:</b>",
        reply_markup=InlineKeyboardMarkup(rows)
    )


# ═══════════════════════════════════════════════════════════════
# CALLBACKS — INLINE KEYBOARD
# ═══════════════════════════════════════════════════════════════

@app.on_callback_query()
async def handle_callback(client: Client, cb: CallbackQuery):
    data = cb.data
    user_id = cb.from_user.id

    try:
        if data == "del_pending":
            _pending_videos.pop(user_id, None)
            await cb.message.edit_text("❌ Compresión cancelada.")

        elif data.startswith("cmode:"):
            mode_key = data.split(":", 1)[1]
            if mode_key == "sel":
                pending = _pending_videos.get(user_id)
                if not pending: return await cb.answer("❌ Expirado", show_alert=True)
                rows = [[InlineKeyboardButton(m["label"], callback_data=f"cmode:{k}")] for k, m in COMPRESSION_MODES.items()]
                rows.append([InlineKeyboardButton("❌ Cancelar", callback_data="del_pending")])
                await cb.message.edit_text("📹 <b>Seleccioná el modo de compresión:</b>", reply_markup=InlineKeyboardMarkup(rows))
                return
            pending = _pending_videos.get(user_id)
            if not pending: return await cb.answer("❌ Sesión expirada. Enviá el video de nuevo.", show_alert=True)
            pending["mode"] = mode_key
            u = await get_user(user_id)
            await cb.message.edit_text(
                f"🎛️ <b>Seleccioná la calidad:</b>\nModo: {COMPRESSION_MODES[mode_key]['label']}",
                reply_markup=quality_kb_video(u.get("quality", DEFAULT_QUALITY), mode_key)
            )

        elif data.startswith("cqvid:"):
            _, mode_key, quality_key = data.split(":", 2)
            pending = _pending_videos.get(user_id)
            if not pending: return await cb.answer("❌ Sesión expirada. Enviá el video de nuevo.", show_alert=True)

            await cb.message.edit_text(
                f"⬇️ <b>Descargando video...</b>\n📏 Tamaño: {human_size(pending['file_size'])}\n"
                f"🎛️ {COMPRESSION_MODES[mode_key]['label']} | {QUALITY_PRESETS[quality_key]['label']}"
            )

            try:
                orig = await client.get_messages(pending["chat_id"], pending["msg_id"])
                file_path = await client.download_media(orig, file_name=str(DOWNLOADS_DIR / f"{user_id}_{int(time.time())}.mp4"))
            except Exception as e:
                _pending_videos.pop(user_id, None)
                await cb.message.edit_text(f"❌ <b>Error al descargar:</b> {e}")
                return

            if not file_path:
                _pending_videos.pop(user_id, None)
                await cb.message.edit_text("❌ No se pudo descargar el archivo.")
                return

            job_id = str(uuid.uuid4())
            await add_to_queue({
                "id": job_id, "user_id": user_id,
                "username": pending.get("username", ""),
                "chat_id": pending["chat_id"], "message_id": pending["msg_id"],
                "file_path": file_path, "original_size": pending["file_size"],
                "quality": quality_key, "mode": mode_key,
                "status": "waiting", "progress": 0,
                "created_at": datetime.now().isoformat(),
                "status_msg_id": cb.message.id,
            })

            _pending_videos.pop(user_id, None)
            queue = await load_queue()
            pos = sum(1 for j in queue if j["status"] == "waiting" and j["id"] != job_id) + 1
            await cb.message.edit_text(
                f"✅ <b>Video añadido a la cola</b>\n🆔 ID: <code>{job_id[:8]}</code>\n"
                f"📏 Tamaño: {human_size(pending['file_size'])}\n"
                f"🎛️ {COMPRESSION_MODES[mode_key]['label']} | {QUALITY_PRESETS[quality_key]['label']}\n"
                f"📌 Posición: #{pos}\n━━━━━━━━━━━━━━━━━━━━━\n⏳ <i>Espera mientras se procesa...</i>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🧵 Ver Cola", callback_data="queue"),
                     InlineKeyboardButton("❌ Cancelar", callback_data=f"cnfrm_cancel:{job_id}")]
                ])
            )

        elif data == "menu":
            u = await get_user(user_id)
            plan_name = PLANS.get(u["plan"], PLANS["free"])["name"]
            await cb.message.edit_text(
                WELCOME_MSG.format(name=cb.from_user.first_name, plan=plan_name),
                reply_markup=main_menu_kb()
            )

        elif data == "profile":
            u = await get_user(user_id)
            txt = _profile_text(u, user_id, cb.from_user.first_name)
            await cb.message.edit_text(txt, reply_markup=back_kb("menu"))

        elif data == "myplan":
            u = await get_user(user_id)
            txt = _plan_text(u)
            await cb.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Ver Planes", callback_data="plans")],
                [InlineKeyboardButton("🔙 Volver", callback_data="menu")]
            ]))

        elif data == "quality":
            u = await get_user(user_id)
            await cb.message.edit_text(
                "🎛️ <b>Selecciona la calidad de compresión:</b>\n\n"
                "<i>Más compresión = menos peso, pero menor calidad visual.</i>\n"
                "<i>Elige la que mejor se adapte a tus necesidades.</i>",
                reply_markup=quality_kb(u.get("quality", DEFAULT_QUALITY))
            )

        elif data.startswith("qset:"):
            key = data.split(":", 1)[1]
            if key in QUALITY_PRESETS:
                await update_user(user_id, quality=key)
                q = QUALITY_PRESETS[key]
                await cb.answer(f"✅ Calidad cambiada a: {q['label']}", show_alert=False)
                await cb.message.edit_text(
                    f"✅ <b>Calidad actualizada</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{q['label']}\n"
                    f"📝 {q['desc']}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Tu próximo video usará esta configuración.</i>",
                    reply_markup=quality_kb(key)
                )

        elif data == "plans":
            await show_plans(cb.message, edit=True)

        elif data.startswith("pland:"):
            key = data.split(":", 1)[1]
            plan = PLANS.get(key)
            if not plan:
                return
            features_list = "\n".join(f"✅ {f}" for f in plan["features"])
            txt = (
                f"📊 <b>{plan['name']} — {plan['price']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Características:</b>\n{features_list}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💳 <i>Para adquirir este plan, contacta al {ADMIN_USERNAME}</i>"
            )
            await cb.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Ver Planes", callback_data="plans")],
                [InlineKeyboardButton("👨‍💻 Contactar Admin", url=f"https://t.me/{ADMIN_USERNAME}")],
                [InlineKeyboardButton("🔙 Volver", callback_data="menu")]
            ]))

        elif data == "queue":
            await show_queue(cb.message, edit=True)

        elif data == "help":
            await cb.message.edit_text(HELP_MSG, reply_markup=back_kb("menu"))

        elif data == "developer":
            await cb.message.edit_text(
                f"👨‍💻 <b>Desarrollador</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 Bot: CompresUltra Bot V.6\n"
                f"⚡ Motor: FFmpeg + libx265\n"
                f"👤 Creador: {ADMIN_USERNAME}\n"
                f"📚 Librería: Pyrogram 2.0.106\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💬 <i>¿Sugerencias o bugs? Usa /reporte o escribe al admin.</i>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 Reportar", callback_data="report")],
                    [InlineKeyboardButton("🔙 Volver", callback_data="menu")]
                ])
            )

        elif data == "report":
            await cb.message.edit_text(
                "📝 <b>Reportar un problema</b>\n\n"
                "Usa el comando <code>/reporte descripción</code>\n\n"
                "Ejemplo: <code>/reporte el bot no responde</code>\n\n"
                "Tu reporte será enviado al administrador.",
                reply_markup=back_kb("menu")
            )

        elif data.startswith("cnfrm_cancel:"):
            job_id = data.split(":", 1)[1]
            job = await get_user_job(user_id)
            if not job or job["id"] != job_id:
                await cb.answer("❌ Esta compresión ya no está activa.", show_alert=True)
                return

            if job["status"] == "waiting":
                await remove_from_queue(job_id)
                await cb.message.edit_text("✅ Compresión cancelada.")
                # Limpiar archivo
                try: os.remove(job["file_path"])
                except: pass
            elif job["status"] == "processing":
                _cancellation_flag.add(job_id)
                await update_job(job_id, status="cancelled")
                await cb.message.edit_text("⏳ Cancelando compresión en curso... Espera un momento.")
            await cb.answer("✅ Cancelado")

        # ── Admin ──
        elif data == "admin_menu" and is_admin(user_id, cb.from_user.username or ""):
            await cb.message.edit_text(
                "🛠️ <b>Panel de Administración</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 Estadísticas", callback_data="admin_stats")],
                    [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
                    [InlineKeyboardButton("👥 Usuarios", callback_data="admin_users")],
                    [InlineKeyboardButton("🔙 Salir", callback_data="menu")]
                ])
            )

        elif data == "admin_stats" and is_admin(user_id, cb.from_user.username or ""):
            users = await load_users()
            queue = await load_queue()
            active = sum(1 for j in queue if j["status"] in ("waiting", "processing"))
            total_users = len(users)
            total_compressions = sum(u.get("total_compressions", 0) for u in users.values())
            total_saved = sum(u.get("total_saved_bytes", 0) for u in users.values())
            disk = shutil.disk_usage(str(DATA_DIR))
            txt = (
                f"📊 <b>Estadísticas del Bot</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 Usuarios totales: {total_users}\n"
                f"🗜️ Compresiones totales: {total_compressions}\n"
                f"💾 Datos ahorrados: {human_size(total_saved)}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 Cola activa: {active}\n"
                f"💽 Disco libre: {human_size(disk.free)} / {human_size(disk.total)}"
            )
            await cb.message.edit_text(txt, reply_markup=back_kb("admin_menu"))

        elif data == "admin_users" and is_admin(user_id, cb.from_user.username or ""):
            users = await load_users()
            # Top 10 usuarios recientes
            sorted_users = sorted(users.values(), key=lambda u: u.get("total_compressions", 0), reverse=True)
            txt = "👥 <b>Usuarios (Top 10)</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            for i, u in enumerate(sorted_users[:10], 1):
                name = u.get("first_name", "Unknown")
                uid = u.get("user_id", "?")
                comps = u.get("total_compressions", 0)
                plan = u.get("plan", "free")
                badge = PLANS.get(plan, PLANS["free"])["badge"]
                txt += f"{i}. {badge} {name} — {comps} comp. — <code>{uid}</code>\n"
            await cb.message.edit_text(txt, reply_markup=back_kb("admin_menu"))

        elif data == "admin_broadcast" and is_admin(user_id, cb.from_user.username or ""):
            await cb.message.edit_text(
                "📢 <b>Broadcast</b>\n\n"
                "Para enviar un mensaje a todos los usuarios, usa:\n"
                "<code>/broadcast tu mensaje aquí</code>\n\n"
                "<i>El mensaje se enviará a todos los usuarios registrados.</i>",
                reply_markup=back_kb("admin_menu")
            )
        else:
            await cb.answer("Acción no disponible", show_alert=True)

    except Exception as e:
        print(f"[Callback Error] {data}: {traceback.format_exc()}")
        try:
            await cb.answer(f"⚠️ Error: {str(e)[:100]}", show_alert=True)
        except: pass


# ═══════════════════════════════════════════════════════════════
# COMANDOS ADMIN
# ═══════════════════════════════════════════════════════════════

@app.on_message(filters.command("admin") & filters.private)
async def admin_cmd(client: Client, msg: Message):
    if not is_admin(msg.from_user.id, msg.from_user.username or ""):
        return
    await msg.reply_text(
        "🛠️ <b>Panel de Administración</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Estadísticas", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton("👥 Usuarios", callback_data="admin_users")],
        ])
    )


@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_cmd(client: Client, msg: Message):
    if not is_admin(msg.from_user.id, msg.from_user.username or ""):
        return
    text = msg.text[len("/broadcast"):].strip()
    if not text:
        await msg.reply_text("Uso: <code>/broadcast mensaje a enviar</code>")
        return
    users = await load_users()
    sent = 0
    failed = 0
    status = await msg.reply_text(f"📢 Enviando broadcast a {len(users)} usuarios...")
    for uid, u in users.items():
        try:
            await client.send_message(int(uid), text)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)  # evitar flood
    await status.edit_text(
        f"✅ Broadcast completado\n"
        f"✅ Enviados: {sent}\n"
        f"❌ Fallidos: {failed}\n"
        f"📊 Total usuarios: {len(users)}"
    )


@app.on_message(filters.command("stats") & filters.private)
async def stats_cmd(client: Client, msg: Message):
    if not is_admin(msg.from_user.id, msg.from_user.username or ""):
        return
    users = await load_users()
    q = await load_queue()
    active = sum(1 for j in q if j["status"] in ("waiting", "processing"))
    txt = (
        f"📊 Estadísticas:\n"
        f"Usuarios: {len(users)}\n"
        f"Cola activa: {active}\n"
        f"Compresiones totales: {sum(u.get('total_compressions', 0) for u in users.values())}"
    )
    await msg.reply_text(txt)


@app.on_message(filters.command("ban") & filters.private)
async def ban_cmd(client: Client, msg: Message):
    if not is_admin(msg.from_user.id, msg.from_user.username or ""):
        return
    args = msg.text.split()
    if len(args) < 2:
        await msg.reply_text("Uso: /ban <user_id>")
        return
    try:
        target = int(args[1])
        await update_user(target, is_banned=True)
        await msg.reply_text(f"✅ Usuario {target} baneado.")
    except:
        await msg.reply_text("❌ ID inválido.")


@app.on_message(filters.command("unban") & filters.private)
async def unban_cmd(client: Client, msg: Message):
    if not is_admin(msg.from_user.id, msg.from_user.username or ""):
        return
    args = msg.text.split()
    if len(args) < 2:
        await msg.reply_text("Uso: /unban <user_id>")
        return
    try:
        target = int(args[1])
        await update_user(target, is_banned=False)
        await msg.reply_text(f"✅ Usuario {target} desbaneado.")
    except:
        await msg.reply_text("❌ ID inválido.")


@app.on_message(filters.command("setplan") & filters.private)
async def setplan_cmd(client: Client, msg: Message):
    if not is_admin(msg.from_user.id, msg.from_user.username or ""):
        return
    args = msg.text.split()
    if len(args) < 3:
        await msg.reply_text("Uso: /setplan <user_id> <plan>\nPlanes: free, basic, pro, ultimate")
        return
    try:
        target = int(args[1])
        plan = args[2].lower()
        if plan not in PLANS:
            await msg.reply_text(f"Plan inválido. Opciones: {', '.join(PLANS.keys())}")
            return
        expiry = (datetime.now() + timedelta(days=30)).isoformat() if plan != "free" else None
        await update_user(target, plan=plan, plan_expiry=expiry, daily_count=0)
        await msg.reply_text(f"✅ Usuario {target} actualizado a plan {plan}.")
    except Exception as e:
        await msg.reply_text(f"❌ Error: {e}")


# ═══════════════════════════════════════════════════════════════
# FUNCIONES AUXILIARES (menús)
# ═══════════════════════════════════════════════════════════════

async def show_plans(msg_or_cb, edit=False):
    txt = "📊 <b>Planes Disponibles</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for key, plan in PLANS.items():
        if key == "free":
            continue  # mostrar gratis en el texto pero no como botón
        txt += (
            f"{plan['badge']} <b>{plan['name']}</b> — {plan['price']}\n"
            f"📅 {plan['daily'] if plan['daily'] > 0 else '∞'} compresiones/día\n"
            f"📦 Máx {plan['max_mb']}MB por archivo\n\n"
        )
    txt += "━━━━━━━━━━━━━━━━━━━━━\n💳 <i>Selecciona un plan para más detalles</i>"
    if edit:
        await msg_or_cb.edit_text(txt, reply_markup=plans_kb())
    else:
        await msg_or_cb.reply_text(txt, reply_markup=plans_kb())


async def show_queue(msg_or_cb, edit=False):
    user_id = msg_or_cb.from_user.id
    q = await load_queue()
    user_jobs = [j for j in q if j["user_id"] == user_id]
    all_waiting = [j for j in q if j["status"] == "waiting"]
    total_active = sum(1 for j in q if j["status"] in ("waiting", "processing"))

    txt = "🧵 <b>Estado de la Cola</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    txt += f"📊 En cola ahora: {total_active}\n\n"

    if not user_jobs:
        txt += "📭 <i>No tienes compresiones activas.</i>\n\nEnvía un video para empezar."
    else:
        for j in user_jobs:
            status_emoji = {"waiting": "⏳", "processing": "🔄", "completed": "✅",
                           "failed": "❌", "cancelled": "🚫"}.get(j["status"], "❓")
            quality_label = QUALITY_PRESETS.get(j.get("quality", DEFAULT_QUALITY),
                                                QUALITY_PRESETS[DEFAULT_QUALITY])["label"]
            pos = 1
            for i, wj in enumerate(q):
                if wj["id"] == j["id"]:
                    pos = sum(1 for x in q[:i] if x["status"] == "waiting") + 1
                    break

            txt += (
                f"{status_emoji} <code>{j['id'][:8]}</code>\n"
                f"   📎 Estado: {j['status']}\n"
                f"   📏 {human_size(j.get('original_size', 0))} | ⚙️ {quality_label}\n"
            )
            if j["status"] == "waiting":
                txt += f"   🎯 Posición: #{pos}\n"
            elif j["status"] == "processing":
                pct = j.get("progress", 0)
                txt += f"   🎬 {_progress_bar(pct)} {pct:.1f}%\n"
            txt += "\n"

    if edit:
        await msg_or_cb.edit_text(txt, reply_markup=back_kb("menu"))
    else:
        await msg_or_cb.reply_text(txt, reply_markup=back_kb("menu"))


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

async def startup():
    """Inicialización: verifica entorno y arranca el worker de cola."""
    print("🚀 CompresUltra Bot V.6 iniciando...")

    if not BOT_TOKEN or not API_ID or not API_HASH:
        print("❌ Faltan variables de entorno: BOT_TOKEN, API_ID, API_HASH")
        print("💡 Configúralas y vuelve a intentar.")
        sys.exit(1)

    await app.start()

    # Info admin
    try:
        admin = await app.get_users(ADMIN_USERNAME)
        global ADMIN_USER_ID
        ADMIN_USER_ID = admin.id
        print(f"✅ Admin detectado: {admin.first_name} (ID: {admin.id})")
    except:
        print(f"⚠️ No se pudo resolver @{ADMIN_USERNAME}")

    # Iniciar worker de cola
    global _queue_worker_task
    _queue_worker_task = asyncio.create_task(queue_worker(app))
    print("✅ Worker de cola iniciado")

    # Verificar FFmpeg
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version", stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        out, _ = await proc.communicate()
        ver = out.decode().split("\n")[0] if out else "n/a"
        print(f"✅ FFmpeg: {ver}")
    except:
        print("❌ FFmpeg no encontrado. Instálalo para usar el bot.")

    # Registrar comandos en la UI de Telegram
    try:
        await app.set_bot_commands([
            BotCommand("start", "👋 Bienvenida"),
            BotCommand("help", "📖 Comandos disponibles"),
            BotCommand("miperfil", "👤 Tu perfil y estadísticas"),
            BotCommand("miplan", "📋 Tu plan actual"),
            BotCommand("planes", "📊 Ver planes disponibles"),
            BotCommand("calidad", "🎛️ Cambiar calidad"),
            BotCommand("cola", "🧵 Estado de la cola"),
            BotCommand("cancelar", "❌ Cancelar compresión"),
            BotCommand("reporte", "📝 Reportar problema"),
            BotCommand("id", "🆔 Tu ID"),
            BotCommand("ping", "🏓 Verificar respuesta"),
            BotCommand("velocidad", "⚡ Test de velocidad"),
            BotCommand("about", "ℹ️ Info del bot"),
        ])
    except:
        pass

    print("🤖 Bot listo!")
    print("━" * 40)


async def main():
    await startup()
    await idle()

if __name__ == "__main__":
    try:
        app.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot detenido por el usuario.")
    except Exception:
        print(f"❌ Error fatal: {traceback.format_exc()}")
