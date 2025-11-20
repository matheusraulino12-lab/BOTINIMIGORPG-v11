import discord
from discord.ext import commands
import asyncio
import os

# =============== CONFIGURAÇÕES ===============

TOKEN = "MTQ0MDQxNzc3NjI3NDUxMDA0NA.G1sFlo.WQ0AwnC3w1QpCSgRTrQo8P8RH4VhdnF4W6XSoI"  # <<< COLE SEU TOKEN AQUI

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True
INTENTS.guilds = True
INTENTS.reactions = True

bot = commands.Bot(
    command_prefix="!",
    intents=INTENTS,
    help_command=None  # desativa !help padrão
)

# Lista das COGS usadas no projeto
COGS = [
    "cogs.help",
    "cogs.combate",
    "cogs.monster_admin",
    "cogs.player_admin",
    "cogs.item_admin",
    "cogs.dice_roll",
    "cogs.clear",
    "cogs.loot"
]

# =============== EVENTO: BOT ONLINE ===============

@bot.event
async def on_ready():
    print(f"🤖 Bot conectado como {bot.user}")
    print("Sincronizando comandos / ...")

    try:
        synced = await bot.tree.sync()
        print(f"🔧 {len(synced)} comandos sincronizados.")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

    print("✨ Bot está pronto!")

# =============== CARREGAMENTO DAS COGS ===============

async def load_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"📦 Cog carregada: {cog}")
        except Exception as e:
            print(f"❌ Erro ao carregar {cog}: {e}")

# =============== INICIAR BOT ===============

async def main():
    await load_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
