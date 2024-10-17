import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import os
import asyncio
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Lade die Umgebungsvariablen
load_dotenv()

# FFmpeg Optionen
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# Youtube-DLP Optionen
ytdl_format_options = {
    'format': 'bestaudio[ext=mp4]/bestaudio[ext=webm]/bestaudio',
    'noplaylist': 'True',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'keepvideo': False
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, filename, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.filename = filename

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        filename = None
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))

            if data is None:
                raise ValueError(f'Keine Daten für die URL {url} erhalten.')

            if isinstance(data, dict) and 'entries' in data:
                data = data['entries'][0]

            # Speicherort der heruntergeladenen MP3-Datei
            filename = ytdl.prepare_filename(data).replace('.mp4', '.mp3')
            if filename is None:
                raise ValueError('Keine gültige Datei gefunden.')

            # Lade und konvertiere das Video zu MP3
            await loop.run_in_executor(None, lambda: ytdl.download([url]))

            return cls(discord.FFmpegPCMAudio(filename), data=data, filename=filename)
        except Exception as e:
            print(f"Fehler bei der URL-Extraktion: {e}")
            raise e

    async def cleanup(self):
        # Warte darauf, dass der ffmpeg-Prozess vollständig beendet ist
        while self.filename and os.path.exists(self.filename):
            try:
                os.remove(self.filename)
                print(f"Datei {self.filename} gelöscht.")
                break
            except OSError as e:
                if e.errno == 32:  # WinError 32: Datei wird noch verwendet
                    await asyncio.sleep(1)
                else:
                    print(f"Fehler beim Löschen der Datei: {e}")
                    break

@bot.command(name='join')
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("Du musst in einem Sprachkanal sein, damit ich beitreten kann.")
        return
    channel = ctx.message.author.voice.channel
    await channel.connect()

@bot.command(name='leave')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Bot hat den Sprachkanal verlassen.")
    else:
        await ctx.send("Ich bin nicht in einem Sprachkanal.")

@bot.command(name='play')
async def play(ctx, url: str):
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(url)
            ctx.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(player.cleanup(), loop=bot.loop).result())
            await ctx.send(f'Spiele jetzt: {player.title}')
        except Exception as e:
            await ctx.send(f'Fehler beim Abspielen des Songs: {e}')

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client.is_playing():
        player = ctx.voice_client.source
        if isinstance(player, YTDLSource):
            await player.cleanup()
        ctx.voice_client.stop()
        await ctx.send("Musik wurde gestoppt.")

@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client.is_playing():
        player = ctx.voice_client.source
        if isinstance(player, YTDLSource):
            await player.cleanup()
        ctx.voice_client.stop()
        await ctx.send("Musik wurde übersprungen.")

# Flask Webserver für UptimeRobot
app = Flask('')

@app.route('/')
def home():
    return "Bot is online!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Token aus der Umgebungsvariablen laden
token = os.getenv("DISCORD_TOKEN")

if token is None:
    raise ValueError("Discord-Token wurde nicht gefunden. Stelle sicher, dass DISCORD_TOKEN in der .env-Datei gesetzt ist.")

# Webserver starten
keep_alive()

# Starte den Bot
bot.run(token)
