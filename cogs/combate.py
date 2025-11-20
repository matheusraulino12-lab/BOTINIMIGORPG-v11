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
# CONFIGURAÇÕES / PATHS
# ============================================================
RANKS_PATH = "./data/ranks.json"
RANKS_PLAYER_PATH = "./data/ranks_player.json"
PLAYERS_PATH = "./data/players.json"

# Imagem padrão para monstros sem img
DEFAULT_IMAGE = "https://i.pinimg.com/736x/85/8d/96/858d96566ab8da9407ae5ccc1af0b5d1.jpg"

# estrutura global de combates ativos
active_combat = {}


# ============================================================
# Helpers JSON
# ============================================================
def load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        with open(path, "w", encoding="utf8") as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
    with open(path, "r", encoding="utf8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_players():
    return load_json(PLAYERS_PATH, {})


def save_players(data):
    save_json(PLAYERS_PATH, data)


def load_ranks():
    return load_json(RANKS_PATH, {})


def load_ranks_player():
    return load_json(RANKS_PLAYER_PATH, {})


# ============================================================
# Barra de vida (texto)
# ============================================================
def life_bar(current, max_hp, size=20):
    current = max(0, int(current))
    max_hp = max(1, int(max_hp))
    filled = int((current / max_hp) * size)
    empty = size - filled
    return f"[{'█'*filled}{'░'*empty}] {current}/{max_hp}"


# ============================================================
# AUTOCOMPLETE (async)
# ============================================================
async def autocomplete_inimigo(interaction: Interaction, current: str):
    monsters = load_monsters()
    choices = []
    current = (current or "").lower()
    for key in monsters.keys():
        if current in key.lower():
            choices.append(app_commands.Choice(name=monsters[key].get("nome", key).capitalize(), value=key))
    return choices[:25]


async def autocomplete_rank(interaction: Interaction, current: str):
    ranks = ["bronze", "prata", "ouro", "ouro negro", "lendário"]
    return [app_commands.Choice(name=r.capitalize(), value=r) for r in ranks if current.lower() in r.lower()][:25]


async def autocomplete_nivel(interaction: Interaction, current: str):
    niveis = ["1", "2", "3", "4", "5"]
    return [app_commands.Choice(name=n, value=n) for n in niveis if current in n][:25]


# ============================================================
# Update status message (grid + embed listing monsters & players)
# ============================================================
async def update_main_status(guild_id: int, bot: commands.Bot):
    if guild_id not in active_combat:
        return

    data = active_combat[guild_id]
    channel = bot.get_channel(data.get("channel_id"))
    if channel is None:
        return

    monsters = data.get("monsters", {})
    players = data.get("players", {})

    # gerar grid (pode falhar; catch)
    try:
        grid_buffer = await gerar_grid(monsters, colunas=3)
    except Exception:
        grid_buffer = None

    embed = discord.Embed(title="📋 Status do Combate", color=discord.Color.blurple())

    # Monstros
    alive_count = 0
    monster_text = ""
    # ordenar por id (se chaves forem ints)
    keys = sorted([k for k in monsters.keys()], key=lambda x: int(x) if isinstance(x, (int, str)) and str(x).isdigit() else x)
    for mid in keys:
        m = monsters[mid]
        estado = "💀 Morto" if m.get("vida_atual", 0) <= 0 else "⚔️ Vivo"
        if m.get("vida_atual", 0) > 0:
            alive_count += 1
        monster_text += f"**{m.get('nome','?')} #{mid}**\n{life_bar(m.get('vida_atual',0), m.get('vida_max',1))}\nKI: {m.get('ki',0)} • CA: {m.get('ca',0)} • BBA: {m.get('bba',0)} • {estado}\n\n"

    embed.add_field(name=f"🟥 Inimigos (Vivos: {alive_count})", value=monster_text or "Nenhum inimigo em campo.", inline=False)

    # Players
    players_text = ""
    for uid, p in players.items():
        member = channel.guild.get_member(int(uid)) if channel and channel.guild else None
        display = member.display_name if member else uid
        estado = "❌ Inconsciente" if p.get("vida_atual", 0) <= 0 else "⚔️ Ativo"
        players_text += f"**{display}** — HP: {p.get('vida_atual',0)}/{p.get('vida_max',0)} • QI: {p.get('mana_atual',0)}/{p.get('mana_max',0)} • {estado}\n\n"

    embed.add_field(name="🟦 Jogadores", value=players_text or "Nenhum jogador no combate.", inline=False)
    embed.set_footer(text="Grid: monstros | Lista: players")

    # enviar/editar mensagem
    try:
        if grid_buffer:
            file = discord.File(grid_buffer, filename="grid.png")
            embed.set_image(url="attachment://grid.png")
            if data.get("main_message_id"):
                try:
                    msg = await channel.fetch_message(data["main_message_id"])
                    await msg.edit(embed=embed, attachments=[file])
                except Exception:
                    sent = await channel.send(embed=embed, file=file)
                    data["main_message_id"] = sent.id
            else:
                sent = await channel.send(embed=embed, file=file)
                data["main_message_id"] = sent.id
        else:
            if data.get("main_message_id"):
                try:
                    msg = await channel.fetch_message(data["main_message_id"])
                    await msg.edit(embed=embed)
                except Exception:
                    sent = await channel.send(embed=embed)
                    data["main_message_id"] = sent.id
            else:
                sent = await channel.send(embed=embed)
                data["main_message_id"] = sent.id
    except Exception:
        # fallback simples: enviar embed sem imagem
        try:
            sent = await channel.send(embed=embed)
            data["main_message_id"] = sent.id
        except Exception:
            pass

    # update channel name
    try:
        base = data.get("channel_base_name", channel.name)
        new_name = f"{base} ({alive_count} vivos)"
        if len(new_name) > 100:
            new_name = new_name[:100]
        await channel.edit(name=new_name)
    except Exception:
        pass


# ============================================================
# Aplicar dano em player (persistente)
# ============================================================
async def apply_damage_to_player(guild_id: int, target_id: int, amount: int, bot: commands.Bot, channel: discord.TextChannel):
    players_db = load_players()
    key = str(target_id)
    if key not in players_db:
        # cria ficha padrão bronze nível 1 a partir de ranks_player.json
        rp = load_ranks_player()
        if "bronze" in rp and "1" in rp["bronze"]:
            entry = rp["bronze"]["1"]
            players_db[key] = {
                "rank": "bronze",
                "nivel": 1,
                "vida_max": entry.get("hp", 10),
                "vida_atual": entry.get("hp", 10),
                "mana_max": entry.get("qi", 0),
                "mana_atual": entry.get("qi", 0)
            }
        else:
            players_db[key] = {
                "rank": "bronze",
                "nivel": 1,
                "vida_max": 10,
                "vida_atual": 10,
                "mana_max": 1,
                "mana_atual": 1
            }

    players_db[key]["vida_atual"] = max(0, int(players_db[key].get("vida_atual", 0)) - int(amount))
    save_players(players_db)

    # atualizar snapshot no combate
    if guild_id in active_combat and key in active_combat[guild_id].get("players", {}):
        active_combat[guild_id]["players"][key] = players_db[key]

    await channel.send(f"⚔️ <@{target_id}> sofreu **{amount}** de dano! Vida atual: {players_db[key]['vida_atual']}/{players_db[key]['vida_max']}")
    await update_main_status(guild_id, bot)


# ============================================================
# View de confirmação de ataque (botões)
# ============================================================
class MonsterAttackView(discord.ui.View):
    def __init__(self, guild_id: int, monster_id: int, monster: dict, target: discord.Member, bot: commands.Bot):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.monster_id = monster_id
        self.monster = monster
        self.target = target
        self.bot = bot
        self.resolved = False

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self.resolved:
            await interaction.response.send_message("Esta ação já foi resolvida.", ephemeral=False)
            return False
        return True

    @discord.ui.button(label="✔ Acertou", style=discord.ButtonStyle.success)
    async def hit_button(self, interaction: Interaction, button: discord.ui.Button):
        self.resolved = True
        # rolar dano e aplicar
        dano = roll_damage(self.monster.get("dano", "1d4"))
        channel = self.bot.get_channel(active_combat[self.guild_id]["channel_id"])
        await apply_damage_to_player(self.guild_id, self.target.id, dano, self.bot, channel)

        # enviar resultado público
        await interaction.response.send_message(
            f"🎯 **{self.monster.get('nome')} #{self.monster_id}** acertou {self.target.mention}!\n"
            f"💥 Dano causado: **{dano}**\n"
            f"❤️ Vida atual: **{load_players().get(str(self.target.id), {}).get('vida_atual', 0)}**/"
            f"**{load_players().get(str(self.target.id), {}).get('vida_max', 0)}**",
            allowed_mentions=discord.AllowedMentions(users=True)
        )

        # desabilitar botões
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="❌ Errou", style=discord.ButtonStyle.danger)
    async def miss_button(self, interaction: Interaction, button: discord.ui.Button):
        self.resolved = True
        channel = self.bot.get_channel(active_combat[self.guild_id]["channel_id"])
        await interaction.response.send_message(
            f"❌ **{self.monster.get('nome')} #{self.monster_id} errou o ataque!**\n"
            f"🔁 {self.target.mention} tem chance de ataque de oportunidade!",
            allowed_mentions=discord.AllowedMentions(users=True)
        )
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass


# ============================================================
# COG Combate
# ============================================================
class Combate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------
    # /combate_iniciar
    # -----------------------
    @app_commands.command(name="combate_iniciar", description="Inicia um combate (cria canal na categoria COMBATES).")
    @app_commands.autocomplete(inimigo=autocomplete_inimigo)
    @app_commands.autocomplete(rank=autocomplete_rank)
    @app_commands.autocomplete(nivel=autocomplete_nivel)
    async def combate_iniciar(self, interaction: Interaction, inimigo: str, rank: str, nivel: str, quantidade: int):
        monsters_db = load_monsters()
        ranks = load_ranks()

        inimigo_key = inimigo
        rank_key = rank

        if inimigo_key not in monsters_db:
            return await interaction.response.send_message("❌ Monstro não encontrado.", ephemeral=True)
        if rank_key not in ranks:
            return await interaction.response.send_message("❌ Rank inválido.", ephemeral=True)
        if nivel not in ranks[rank_key]:
            return await interaction.response.send_message("❌ Nível inválido.", ephemeral=True)

        stats = ranks[rank_key][nivel]

        guild = interaction.guild
        # categoria COMBATES
        category = discord.utils.get(guild.categories, name="COMBATES")
        if category is None:
            category = await guild.create_category("COMBATES")

        safe_name = inimigo_key.replace(" ", "-")
        base_channel_name = f"combate-{safe_name}-{quantidade}"
        channel = await guild.create_text_channel(name=f"{base_channel_name} ({quantidade} vivos)", category=category)

        # inicializa combate
        active_combat[guild.id] = {
            "channel_id": channel.id,
            "main_message_id": None,
            "channel_base_name": base_channel_name,
            "monsters": {},
            "players": {}
        }

        # cria inimigos
        for i in range(1, quantidade + 1):
            mon_src = monsters_db[inimigo_key]
            active_combat[guild.id]["monsters"][i] = {
                "id": i,
                "nome": mon_src.get("nome", inimigo_key).capitalize(),
                "rank": rank_key.capitalize(),
                "nivel": int(nivel),
                "vida_max": stats["vida"],
                "vida_atual": stats["vida"],
                "ca": stats["ca"],
                "ki": stats["ki"],
                "dano": stats["dano"],
                "img": mon_src.get("img") or DEFAULT_IMAGE,
                "bba": stats.get("bba", 0)
            }

        # mensagens de entrada por reação
        start_msg = await channel.send("⚔️ **Iniciando combate!** Reaja com ✅ para entrar no combate. Você tem 20 segundos.")
        await start_msg.add_reaction("✅")
        await interaction.response.send_message(f"Canal criado: {channel.mention}", ephemeral=False)

        await asyncio.sleep(20)
        fetched = await channel.fetch_message(start_msg.id)
        users_in = []
        for reaction in fetched.reactions:
            if str(reaction.emoji) == "✅":
                async for user in reaction.users():
                    if user.bot:
                        continue
                    if user.id not in users_in:
                        users_in.append(user.id)

        # criar snapshot de players
        players_db = load_players()
        for uid in users_in:
            key = str(uid)
            if key not in players_db:
                # cria ficha padrão bronze 1
                rp = load_ranks_player()
                bronze1 = rp.get("bronze", {}).get("1", {})
                hp = bronze1.get("hp", 10)
                qi = bronze1.get("qi", 0)
                players_db[key] = {
                    "rank": "bronze",
                    "nivel": 1,
                    "vida_max": hp,
                    "vida_atual": hp,
                    "mana_max": qi,
                    "mana_atual": qi
                }
            # snapshot do combate
            active_combat[guild.id]["players"][key] = players_db[key]

        save_players(players_db)

        # envia status inicial
        await update_main_status(guild.id, self.bot)

    # -----------------------
    # /monstro_atacar
    # -----------------------
    @app_commands.command(name="monstro_atacar", description="Faz um monstro atacar um jogador.")
    async def monstro_atacar(self, interaction: Interaction, inimigo_id: int, alvo: discord.Member):
        gid = interaction.guild.id
        if gid not in active_combat:
            return await interaction.response.send_message("❌ Nenhum combate ativo.", ephemeral=True)

        monsters = active_combat[gid]["monsters"]
        if inimigo_id not in monsters:
            return await interaction.response.send_message("❌ Monstro não encontrado.", ephemeral=True)

        monster = monsters[inimigo_id]

        # rola 1d20 + BBA
        d20 = random.randint(1, 20)
        bba = int(monster.get("bba", 0))
        total = d20 + bba

        embed = discord.Embed(
            title=f"🗡️ Ataque: {monster.get('nome')} #{inimigo_id}",
            description=(
                f"🎯 Alvo: {alvo.mention}\n"
                f"🎲 Rolagem: `1d20` → **{d20}** + BBA **{bba}** = **{total}**\n\n"
                "Clique no botão apropriado para confirmar se o ataque acertou ou errou."
            ),
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=monster.get("img") or DEFAULT_IMAGE)

        view = MonsterAttackView(gid, inimigo_id, monster, alvo, self.bot)

        channel = self.bot.get_channel(active_combat[gid]["channel_id"]) or interaction.channel
        await channel.send(embed=embed, view=view)

        await interaction.response.send_message(f"✅ Ataque iniciado para {alvo.mention}.", ephemeral=False)

    # -----------------------
    # /player_recuperar (público)
    # -----------------------
    @app_commands.command(name="player_recuperar", description="Recupera vida de um jogador (público).")
    async def player_recuperar(self, interaction: Interaction, jogador: discord.Member, valor: int):
        db = load_players()
        key = str(jogador.id)
        if key not in db:
            # cria default
            rp = load_ranks_player()
            bronze1 = rp.get("bronze", {}).get("1", {})
            hp = bronze1.get("hp", 10)
            qi = bronze1.get("qi", 0)
            db[key] = {
                "rank": "bronze",
                "nivel": 1,
                "vida_max": hp,
                "vida_atual": hp,
                "mana_max": qi,
                "mana_atual": qi
            }

        before = db[key]["vida_atual"]
        db[key]["vida_atual"] = min(db[key]["vida_max"], db[key]["vida_atual"] + int(valor))
        save_players(db)

        # atualizar snapshot em combates ativos
        for gid, data in active_combat.items():
            if key in data.get("players", {}):
                data["players"][key] = db[key]
                channel = self.bot.get_channel(data["channel_id"])
                if before <= 0 and db[key]["vida_atual"] >= (db[key]["vida_max"] * 0.5):
                    await channel.send(f"✨ {jogador.mention} recuperou e voltou ao combate!")
                await update_main_status(gid, self.bot)

        await interaction.response.send_message(f"🩹 {jogador.mention} recuperou **{db[key]['vida_atual'] - before}** de vida. Vida atual: {db[key]['vida_atual']}/{db[key]['vida_max']}", allowed_mentions=discord.AllowedMentions(users=True))

    # -----------------------
    # /combate_status
    # -----------------------
    @app_commands.command(name="combate_status", description="Atualiza a mensagem principal do combate.")
    async def combate_status(self, interaction: Interaction):
        gid = interaction.guild.id
        if gid not in active_combat:
            return await interaction.response.send_message("❌ Nenhum combate ativo.", ephemeral=True)
        await update_main_status(gid, self.bot)
        await interaction.response.send_message("Status atualizado.", ephemeral=True)

    # -----------------------
    # /combate_encerrar
    # -----------------------
    @app_commands.command(name="combate_encerrar", description="Encerra o combate.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def combate_encerrar(self, interaction: Interaction, deletar_canal: bool = False):
        gid = interaction.guild.id
        if gid not in active_combat:
            return await interaction.response.send_message("❌ Nenhum combate ativo.", ephemeral=False)

        data = active_combat[gid]
        channel = self.bot.get_channel(data.get("channel_id"))
        del active_combat[gid]
        if deletar_canal and channel:
            try:
                await channel.delete()
            except Exception:
                pass
        await interaction.response.send_message("Combate encerrado.", ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Combate(bot))
