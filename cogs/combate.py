# cogs/combate.py
import discord
from discord.ext import commands
from discord import app_commands, Interaction
import asyncio
import json
import os
import random

from utils.grid import gerar_grid
from utils.dice import roll_damage
from cogs.monster_admin import load_monsters

# ============================================================
# CONFIGURAÇÕES
# ============================================================
RANKS_PATH = "./data/ranks.json"
RANKS_PLAYER_PATH = "./data/ranks_player.json"
PLAYERS_PATH = "./data/players.json"

DEFAULT_IMAGE = "https://i.pinimg.com/736x/85/8d/96/858d96566ab8da9407ae5ccc1af0b5d1.jpg"

active_combat = {}  # controla todos os combates ativos


# ============================================================
# HELPERS GERAIS
# ============================================================
def load_json(path, default={}):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf8") as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
    with open(path, "r", encoding="utf8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_players():
    return load_json(PLAYERS_PATH)


def save_players(data):
    save_json(PLAYERS_PATH, data)


def load_ranks():
    return load_json(RANKS_PATH)


def load_ranks_player():
    return load_json(RANKS_PLAYER_PATH)


# ============================================================
# BARRA DE VIDA
# ============================================================
def life_bar(current, max_hp, size=20):
    current = max(0, current)
    filled = int((current / max_hp) * size)
    empty = size - filled
    return f"[{'█'*filled}{'░'*empty}] {current}/{max_hp}"


# ============================================================
# AUTOCOMPLETE
# ============================================================
async def autocomplete_rank(interaction: Interaction, current: str):
    ranks = ["bronze", "prata", "ouro", "ouro negro", "lendário"]
    return [
        app_commands.Choice(name=r.capitalize(), value=r)
        for r in ranks if current.lower() in r.lower()
    ]


async def autocomplete_nivel(interaction: Interaction, current: str):
    return [
        app_commands.Choice(name=n, value=n)
        for n in ["1", "2", "3", "4", "5"] if current in n
    ]


# ============================================================
# ATUALIZA STATUS GERAL DO COMBATE
# ============================================================
async def update_status(guild_id: int, bot):

    if guild_id not in active_combat:
        return

    data = active_combat[guild_id]
    channel = bot.get_channel(data["channel_id"])
    if not channel:
        return

    monsters = data["monsters"]
    players = data["players"]

    vivos = sum(1 for m in monsters.values() if m["vida_atual"] > 0)

    # === GRID ===
    try:
        buffer = await gerar_grid(monsters, colunas=3)
    except:
        buffer = None

    # === EMBED ===
    embed = discord.Embed(title="📋 Status do Combate", color=discord.Color.blurple())

    # --- Monstros ---
    text_mon = ""
    for mid, m in monsters.items():
        estado = "⚔️ Vivo" if m["vida_atual"] > 0 else "💀 Morto"
        text_mon += (
            f"**{m['nome']} #{mid}**\n"
            f"{life_bar(m['vida_atual'], m['vida_max'])}\n"
            f"KI: {m['ki']} • CA: {m['ca']} • BBA: {m.get('bba',0)} • {estado}\n\n"
        )

    embed.add_field(name=f"🟥 Inimigos (Vivos: {vivos})", value=text_mon, inline=False)

    # --- Players ---
    text_play = ""
    for pid, p in players.items():
        member = channel.guild.get_member(int(pid))
        nome = member.display_name if member else pid
        estado = "❌ Inconsciente" if p["vida_atual"] <= 0 else "⚔️ Ativo"

        text_play += (
            f"**{nome}**\n"
            f"HP: {p['vida_atual']}/{p['vida_max']} • "
            f"QI: {p['mana_atual']}/{p['mana_max']} • {estado}\n\n"
        )

    embed.add_field(name="🟦 Jogadores", value=text_play, inline=False)

    if buffer:
        file = discord.File(buffer, filename="grid.png")
        embed.set_image(url="attachment://grid.png")
    else:
        file = None

    # EDITA MENSAGEM PRINCIPAL
    try:
        msg = await channel.fetch_message(data["main_message_id"])
        await msg.edit(embed=embed, attachments=[file] if file else [])
    except:
        sent = await channel.send(embed=embed, file=file)
        data["main_message_id"] = sent.id

    # ATUALIZA NOME DO CANAL
    base = data["base_name"]
    new_name = f"{base} ({vivos} vivos)"
    if len(new_name) > 100:
        new_name = new_name[:100]
    try:
        await channel.edit(name=new_name)
    except:
        pass


# ============================================================
# APLICA DANO AO PLAYER
# ============================================================
async def damage_player(guild_id, player_id, dano, bot):
    db = load_players()
    key = str(player_id)

    if key not in db:
        return

    before = db[key]["vida_atual"]
    db[key]["vida_atual"] = max(0, before - dano)
    save_players(db)

    # Atualiza snapshot
    if key in active_combat[guild_id]["players"]:
        active_combat[guild_id]["players"][key] = db[key]

    channel = bot.get_channel(active_combat[guild_id]["channel_id"])

    await channel.send(
        f"💥 <@{player_id}> sofreu **{dano}** de dano!\n"
        f"❤️ {db[key]['vida_atual']}/{db[key]['vida_max']}"
    )

    await update_status(guild_id, bot)


# ============================================================
# VIEW DO ATAQUE DO MONSTRO
# ============================================================
class AttackView(discord.ui.View):
    def __init__(self, guild_id, mon_id, mon, target, bot):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.mon_id = mon_id
        self.mon = mon
        self.target = target
        self.bot = bot
        self.used = False

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self.used:
            await interaction.response.send_message("❌ Já resolvido.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✔ Acertou", style=discord.ButtonStyle.success)
    async def hit(self, interaction: Interaction, _):
        self.used = True

        dano = roll_damage(self.mon["dano"])
        await damage_player(self.guild_id, self.target.id, dano, self.bot)

        await interaction.response.send_message(
            f"🎯 **{self.mon['nome']} #{self.mon_id} acertou {self.target.mention}!**\n"
            f"💥 Dano: **{dano}**",
            allowed_mentions=discord.AllowedMentions(users=True)
        )

        for c in self.children:
            c.disabled = True

        try:
            await interaction.message.edit(view=self)
        except:
            pass

    @discord.ui.button(label="❌ Errou", style=discord.ButtonStyle.danger)
    async def miss(self, interaction: Interaction, _):
        self.used = True

        await interaction.response.send_message(
            f"❌ **{self.mon['nome']} #{self.mon_id} errou o ataque!**\n"
            f"🔁 {self.target.mention} tem ATAQUE DE OPORTUNIDADE!",
            allowed_mentions=discord.AllowedMentions(users=True)
        )

        for c in self.children:
            c.disabled = True

        try:
            await interaction.message.edit(view=self)
        except:
            pass


# ============================================================
# COG PRINCIPAL
# ============================================================
class Combate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --------------------------------------------------------
    # /combate_iniciar
    # --------------------------------------------------------
    @app_commands.command(name="combate_iniciar", description="Inicia um combate com inimigos.")
    @app_commands.autocomplete(inimigo=lambda i, c: [
        app_commands.Choice(name=key.capitalize(), value=key)
        for key in load_monsters().keys() if c.lower() in key.lower()
    ])
    @app_commands.autocomplete(rank=autocomplete_rank)
    @app_commands.autocomplete(nivel=autocomplete_nivel)
    async def iniciar(self, interaction: Interaction, inimigo: str, rank: str, nivel: str, quantidade: int):

        monsters_db = load_monsters()
        ranks = load_ranks()

        if inimigo not in monsters_db:
            return await interaction.response.send_message("❌ Monstro inválido.", ephemeral=True)

        stats = ranks[rank][nivel]

        guild = interaction.guild

        # Categoria COMBATES
        category = discord.utils.get(guild.categories, name="COMBATES")
        if not category:
            category = await guild.create_category("COMBATES")

        base_name = f"combate-{inimigo}-{quantidade}"
        channel = await guild.create_text_channel(
            f"{base_name} ({quantidade} vivos)",
            category=category
        )

        await interaction.response.send_message(f"✔ Canal criado: {channel.mention}", ephemeral=True)

        # inicia combate
        active_combat[guild.id] = {
            "channel_id": channel.id,
            "main_message_id": None,
            "base_name": base_name,
            "monsters": {},
            "players": {}
        }

        # cria os monstros
        for i in range(1, quantidade + 1):
            active_combat[guild.id]["monsters"][i] = {
                "id": i,
                "nome": monsters_db[inimigo]["nome"],
                "rank": rank,
                "nivel": int(nivel),
                "vida_max": stats["vida"],
                "vida_atual": stats["vida"],
                "ca": stats["ca"],
                "ki": stats["ki"],
                "dano": stats["dano"],
                "img": monsters_db[inimigo].get("img") or DEFAULT_IMAGE,
                "bba": stats.get("bba", 0)
            }

        # entrada por reação
        msg = await channel.send("⚔️ **Reaja com ✅ para entrar no combate!** (20s)")
        await msg.add_reaction("✅")
        await asyncio.sleep(20)

        players = []
        msg = await channel.fetch_message(msg.id)
        for r in msg.reactions:
            if str(r.emoji) == "✅":
                async for u in r.users():
                    if not u.bot:
                        players.append(u.id)

        players_db = load_players()

        for pid in players:
            pid = str(pid)
            if pid not in players_db:
                # cria player padrão bronze 1
                rp = load_ranks_player()
                hp = rp["bronze"]["1"]["hp"]
                qi = rp["bronze"]["1"]["qi"]
                players_db[pid] = {
                    "rank": "bronze",
                    "nivel": 1,
                    "vida_max": hp,
                    "vida_atual": hp,
                    "mana_max": qi,
                    "mana_atual": qi
                }

            active_combat[guild.id]["players"][pid] = players_db[pid]

        save_players(players_db)

        await update_status(guild.id, self.bot)

    # --------------------------------------------------------
    # /monstro_atacar
    # --------------------------------------------------------
    @app_commands.command(name="monstro_atacar", description="Faz um monstro atacar um jogador.")
    async def monstro_atacar(self, interaction: Interaction, inimigo_id: int, alvo: discord.Member):

        gid = interaction.guild.id
        if gid not in active_combat:
            return await interaction.response.send_message("❌ Nenhum combate ativo.", ephemeral=True)

        monsters = active_combat[gid]["monsters"]

        if inimigo_id not in monsters:
            return await interaction.response.send_message("❌ Monstro inválido.", ephemeral=True)

        mon = monsters[inimigo_id]

        d20 = random.randint(1, 20)
        total = d20 + mon.get("bba", 0)

        embed = discord.Embed(
            title=f"🗡️ Ataque do {mon['nome']} #{inimigo_id}",
            description=(
                f"**Alvo:** {alvo.mention}\n"
                f"Rolagem: 1d20 → **{d20}** + BBA **{mon.get('bba',0)}** = **{total}**\n\n"
                "Escolha abaixo se o ataque **acertou** ou **errou**."
            ),
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=mon["img"])

        view = AttackView(gid, inimigo_id, mon, alvo, self.bot)

        channel = self.bot.get_channel(active_combat[gid]["channel_id"])
        await channel.send(embed=embed, view=view)

        await interaction.response.send_message("✔ Ataque iniciado!", ephemeral=True)

    # --------------------------------------------------------
    # /combate_status
    # --------------------------------------------------------
    @app_commands.command(name="combate_status", description="Atualiza a mensagem de status.")
    async def combate_status(self, interaction: Interaction):
        gid = interaction.guild.id
        if gid not in active_combat:
            return await interaction.response.send_message("❌ Nenhum combate ativo.", ephemeral=True)
        await update_status(gid, self.bot)
        await interaction.response.send_message("✔ Status atualizado!", ephemeral=True)

    # --------------------------------------------------------
    # /combate_encerrar
    # --------------------------------------------------------
    @app_commands.command(name="combate_encerrar", description="Encerra o combate.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def combate_encerrar(self, interaction: Interaction, deletar_canal: bool = False):

        gid = interaction.guild.id
        if gid not in active_combat:
            return await interaction.response.send_message("❌ Nenhum combate ativo.", ephemeral=True)

        data = active_combat[gid]
        channel = self.bot.get_channel(data["channel_id"])

        del active_combat[gid]

        if deletar_canal and channel:
            try:
                await channel.delete()
            except:
                pass

        await interaction.response.send_message("✔ Combate encerrado!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Combate(bot))
