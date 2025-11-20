# cogs/loot.py
# Sistema completo de LOOT, XP, DROP, MOEDAS e LOJA
# Compatível com combate versão B
# ----------------------------------------------

import discord
from discord.ext import commands
from discord import app_commands, Interaction
import json
import os
import random
import math

# paths
PLAYERS_PATH = "./data/players.json"
RANKS_PLAYER_PATH = "./data/ranks_player.json"
ITEMS_PATH = "./data/items.json"
MONSTERS_PATH = "./data/monsters.json"

# import active_combat do combate.py
try:
    from cogs.combate import active_combat, update_main_status
except Exception:
    active_combat = {}
    def update_main_status(*args, **kwargs):
        return

# ----------------------------------------------------
# JSON HELPERS
# ----------------------------------------------------
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
    return load_json(PLAYERS_PATH)

def save_players(data):
    save_json(PLAYERS_PATH, data)

def load_items():
    return load_json(ITEMS_PATH)

def load_monsters():
    return load_json(MONSTERS_PATH)

def load_ranks_player():
    return load_json(RANKS_PLAYER_PATH)

# ----------------------------------------------------
# ROLAGENS
# ----------------------------------------------------
def roll_dice(formula: str) -> int:
    # exemplo "1d4", "2d6+1"
    import re
    s = formula.replace(" ", "")
    m = re.match(r"(\d+)d(\d+)([+\-]\d+)?", s)
    if not m:
        try:
            return int(s)
        except:
            return 0
    n = int(m.group(1))
    faces = int(m.group(2))
    mod = int(m.group(3) or 0)
    total = 0
    for _ in range(n):
        total += random.randint(1, faces)
    return total + mod

# ----------------------------------------------------
# GERAR DROPS PARA CADA MONSTRO (LÓGICA COMPLETA)
# ----------------------------------------------------
def gerar_drop_monstro(mon_key: str, mon_data: dict):
    """Retorna XP, drops e special rolls."""
    results = {
        "xp": 0,
        "drops": [],
        "special_rolls": []
    }

    ranks_player = load_ranks_player()
    rank = mon_data.get("rank", "bronze").lower()
    nivel = str(mon_data.get("nivel", 1))

    # XP baseado no ranks_player.json
    xp = 0
    if rank in ranks_player and nivel in ranks_player[rank]:
        xp = int(ranks_player[rank][nivel].get("qi_xp", 0))
    results["xp"] = xp

    monsters_db = load_monsters()

    # descobrir key correta no banco de monstros
    real_key = None
    for key, info in monsters_db.items():
        if info.get("nome", "").lower() == mon_data.get("nome", "").lower():
            real_key = key
            break
        if key.lower() == mon_key.lower():
            real_key = key
            break

    if real_key is None:
        real_key = mon_key.lower()

    # ----------------------------- 
    # REGRA ESPECIAL CARNEIRO
    # -----------------------------
    if "carneir" in real_key:
        # 1d4 cascos (sempre)
        qtd_cascos = roll_dice("1d4")
        results["drops"].append({
            "item": "cascos",
            "nome": "Cascos",
            "quant": qtd_cascos,
            "chance": 1.0
        })

        # pele (70%)
        if random.random() <= 0.70:
            results["drops"].append({
                "item": "pele",
                "nome": "Pele",
                "quant": 1,
                "chance": 0.70
            })

        # esfera bestial (1d100 >= 90)
        roll_100 = random.randint(1, 100)
        results["special_rolls"].append({
            "item": "esfera_bestial",
            "roll": roll_100,
            "needed": 90,
            "won": roll_100 >= 90
        })
        if roll_100 >= 90:
            results["drops"].append({
                "item": "esfera_bestial",
                "nome": "Esfera Bestial",
                "quant": 1,
                "chance": 0.10
            })

        return results

    # -----------------------------
    # DROPS DEFINIDOS NO monsters.json
    # -----------------------------
    if real_key in monsters_db:
        drop_cfg = monsters_db[real_key].get("drops", [])
        for d in drop_cfg:
            item = d.get("item")
            qtd_formula = d.get("q", "1")
            chance = float(d.get("chance", 1.0))
            if random.random() <= chance:
                quant = roll_dice(qtd_formula)
                if quant > 0:
                    results["drops"].append({
                        "item": item,
                        "nome": item.capitalize(),
                        "quant": quant,
                        "chance": chance
                    })

    return results

# ----------------------------------------------------
# COG LOOT
# ----------------------------------------------------
class LootCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==========================================================
    # /gerar_loot  (TOTAL, XP, DROP, MOEDAS, EMBED BONITO)
    # ==========================================================
    @app_commands.command(name="gerar_loot", description="Gera loot e XP dos inimigos mortos do combate atual.")
    async def gerar_loot(self, interaction: Interaction):

        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)

        gid = guild.id
        if gid not in active_combat:
            return await interaction.response.send_message("Nenhum combate ativo.", ephemeral=True)

        combate = active_combat[gid]
        monsters = combate.get("monsters", {})
        players_snapshot = combate.get("players", {})

        dead = [ (mid, m) for mid, m in monsters.items() if m.get("vida_atual",1) <= 0 ]
        if not dead:
            return await interaction.response.send_message("Nenhum inimigo morto.", ephemeral=True)

        total_xp = 0
        total_drops = {}
        players_list = list(players_snapshot.keys())

        players_db = load_players()
        items_db = load_items()

        log_details = []

        # Processar cada inimigo morto
        for mid, mon in dead:
            mon_key = mon.get("nome","monstro").lower()
            info = gerar_drop_monstro(mon_key, mon)
            xp = info.get("xp", 0)
            total_xp += xp

            log_details.append(f"**{mon['nome']} #{mid}** → XP: {xp}")

            # drops
            for d in info.get("drops", []):
                ik = d["item"]
                total_drops.setdefault(ik, {"nome": d["nome"], "quant": 0})
                total_drops[ik]["quant"] += d["quant"]

            # especiais (como esfera bestial)
            for sr in info.get("special_rolls", []):
                log_details.append(
                    f"🎲 Rolou 1d100: **{sr['roll']}** (Precisa ≥ {sr['needed']}) → {'GANHOU' if sr['won'] else 'NÃO GANHOU'}"
                )

        # ==========================================
        # Distribuir XP igualmente
        # ==========================================
        xp_each = math.floor(total_xp / max(1, len(players_list)))

        if players_list:
            for pid in players_list:
                if pid not in players_db:
                    players_db[pid] = {
                        "rank":"bronze","nivel":1,
                        "vida_max":10,"vida_atual":10,
                        "mana_max":1,"mana_atual":1,
                        "coins":0, "inventory":{}, "xp":0
                    }
                players_db[pid]["xp"] = players_db[pid].get("xp", 0) + xp_each

        # ==========================================
        # Distribuir drops round-robin para inventários
        # ==========================================
        for item_key, info in total_drops.items():
            qty = info["quant"]
            idx = 0
            while qty > 0 and players_list:
                pid = players_list[idx % len(players_list)]
                inv = players_db[pid].setdefault("inventory", {})
                inv[item_key] = inv.get(item_key, 0) + 1
                qty -= 1
                idx += 1

        save_players(players_db)

        # ==========================================
        # EMBED RESULTANTE
        # ==========================================
        embed = discord.Embed(
            title="🎁 Loot do Combate",
            color=discord.Color.gold()
        )

        embed.add_field(name="XP Total", value=str(total_xp), inline=True)
        embed.add_field(name="XP por Jogador", value=str(xp_each), inline=True)

        if total_drops:
            txt = ""
            for ik, info in total_drops.items():
                nome = info["nome"]
                quant = info["quant"]
                txt += f"• **{nome}** x{quant}\n"
            embed.add_field(name="Drops Totais", value=txt, inline=False)
        else:
            embed.add_field(name="Drops Totais", value="Nenhum drop.", inline=False)

        if log_details:
            embed.add_field(name="Detalhes", value="\n".join(log_details), inline=False)

        await interaction.response.send_message(embed=embed)
    # ==========================================================
    # /loja — catálogo completo de itens do items.json
    # ==========================================================
    @app_commands.command(name="loja", description="Mostra a vitrine completa de itens disponíveis.")
    async def loja(self, interaction: Interaction):

        items_db = load_items()
        if not items_db:
            return await interaction.response.send_message("Nenhum item cadastrado na loja.", ephemeral=True)

        embed = discord.Embed(
            title="🏪 Loja de Itens",
            description="Lista completa dos itens disponíveis.",
            color=discord.Color.blue()
        )

        for key, item in items_db.items():
            nome = item.get("nome", key)
            tipo = item.get("tipo", "desconhecido")
            buy = item.get("buy", 0)
            sell = item.get("sell", 0)
            desc = item.get("descricao", "Sem descrição definida.")

            embed.add_field(
                name=f"**{nome}** (`{key}`)",
                value=(
                    f"📦 Tipo: `{tipo}`\n"
                    f"💰 Comprar: `{buy}` coins\n"
                    f"🪙 Vender: `{sell}` coins\n"
                    f"📝 {desc}"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    # ==========================================================
    # /comprar — comprar itens
    # ==========================================================
    @app_commands.command(name="comprar", description="Compra um item da loja usando coins.")
    async def comprar(self, interaction: Interaction, item_key: str, quantidade: int = 1):

        items_db = load_items()
        if item_key not in items_db:
            return await interaction.response.send_message("Item não encontrado.", ephemeral=True)

        if quantidade < 1:
            return await interaction.response.send_message("Quantidade inválida.", ephemeral=True)

        item = items_db[item_key]
        price = int(item.get("buy", 0))
        total = price * quantidade

        players = load_players()
        key = str(interaction.user.id)

        if key not in players:
            return await interaction.response.send_message("Você não tem ficha registrada.", ephemeral=True)

        if players[key].get("coins", 0) < total:
            return await interaction.response.send_message("Você não tem coins suficientes.", ephemeral=True)

        # Deduz coins
        players[key]["coins"] -= total

        # Adiciona ao inventário
        inv = players[key].setdefault("inventory", {})
        inv[item_key] = inv.get(item_key, 0) + quantidade

        save_players(players)

        await interaction.response.send_message(
            f"🛒 Você comprou **{quantidade}x** `{item.get('nome', item_key)}` por **{total} coins**!"
        )

    # ==========================================================
    # /vender — vender itens
    # ==========================================================
    @app_commands.command(name="vender", description="Vende um item do inventário.")
    async def vender(self, interaction: Interaction, item_key: str, quantidade: int = 1):

        if quantidade < 1:
            return await interaction.response.send_message("Quantidade deve ser maior que 0.", ephemeral=True)

        items_db = load_items()
        if item_key not in items_db:
            return await interaction.response.send_message("Item não encontrado.", ephemeral=True)

        item = items_db[item_key]
        price = int(item.get("sell", 0))
        total = price * quantidade

        players = load_players()
        key = str(interaction.user.id)

        if key not in players:
            return await interaction.response.send_message("Você não possui ficha registrada.", ephemeral=True)

        inv = players[key].setdefault("inventory", {})
        if inv.get(item_key, 0) < quantidade:
            return await interaction.response.send_message("Você não possui essa quantidade para vender.", ephemeral=True)

        # Remover item
        inv[item_key] -= quantidade
        if inv[item_key] <= 0:
            del inv[item_key]

        # Adicionar coins
        players[key]["coins"] += total
        save_players(players)

        await interaction.response.send_message(
            f"🪙 Você vendeu **{quantidade}x** `{item.get('nome', item_key)}` e recebeu **{total} coins**!"
        )

    # ==========================================================
    # /dar_item — ADMIN
    # ==========================================================
    @app_commands.command(name="dar_item", description="(ADM) Entrega um item manualmente a um jogador.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def dar_item(self, interaction: Interaction, jogador: discord.Member, item_key: str, quantidade: int = 1):

        items_db = load_items()
        if item_key not in items_db:
            return await interaction.response.send_message("Item não existe.", ephemeral=True)

        if quantidade < 1:
            return await interaction.response.send_message("Quantidade inválida.", ephemeral=True)

        players = load_players()
        key = str(jogador.id)

        if key not in players:
            players[key] = {
                "rank": "bronze",
                "nivel": 1,
                "vida_max": 10,
                "vida_atual": 10,
                "mana_max": 1,
                "mana_atual": 1,
                "coins": 0,
                "inventory": {},
                "xp": 0
            }

        inv = players[key].setdefault("inventory", {})
        inv[item_key] = inv.get(item_key, 0) + quantidade

        save_players(players)

        await interaction.response.send_message(
            f"🎁 Entregue **{quantidade}x {items_db[item_key]['nome']}** para {jogador.mention}."
        )

    # ==========================================================
    # /set_coins — ADMIN
    # ==========================================================
    @app_commands.command(name="set_coins", description="(ADM) Define o valor de coins de um jogador.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_coins(self, interaction: Interaction, jogador: discord.Member, valor: int):

        if valor < 0:
            return await interaction.response.send_message("Valor inválido.", ephemeral=True)

        players = load_players()
        key = str(jogador.id)

        if key not in players:
            players[key] = {
                "rank": "bronze",
                "nivel": 1,
                "vida_max": 10,
                "vida_atual": 10,
                "mana_max": 1,
                "mana_atual": 1,
                "coins": valor,
                "inventory": {},
                "xp": 0
            }
        else:
            players[key]["coins"] = valor

        save_players(players)

        await interaction.response.send_message(
            f"💰 {jogador.mention} agora possui **{valor} coins**!"
        )
# ----------------------------------------------------
    # ==========================================================
    # /inventario — listar inventário + coins
    # ==========================================================
    @app_commands.command(name="inventario", description="Mostra seu inventário e coins.")
    async def inventario(self, interaction: Interaction, jogador: discord.Member = None):

        user = jogador or interaction.user
        key = str(user.id)
        players = load_players()

        if key not in players:
            return await interaction.response.send_message("Este jogador não possui ficha.", ephemeral=True)

        p = players[key]
        inv = p.get("inventory", {})
        coins = p.get("coins", 0)
        items_db = load_items()

        embed = discord.Embed(
            title=f"🎒 Inventário de {user.display_name}",
            color=discord.Color.green()
        )

        embed.add_field(name="Coins", value=str(coins), inline=False)

        if inv:
            txt = ""
            for item_key, quant in inv.items():
                nome = items_db.get(item_key, {}).get("nome", item_key)
                txt += f"• **{nome}** (`{item_key}`): {quant}\n"
            embed.add_field(name="Itens", value=txt, inline=False)
        else:
            embed.add_field(name="Itens", value="Inventário vazio.", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================================
# SETUP DO COG
# ==========================================================
async def setup(bot):
    await bot.add_cog(LootCog(bot))
