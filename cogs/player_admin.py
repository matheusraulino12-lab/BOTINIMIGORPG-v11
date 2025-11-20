# cogs/player_admin.py - Parte 1/3
import discord
from discord.ext import commands
from discord import app_commands, Interaction
import json
import os
import math
import random
from typing import Dict, Any

# paths
PLAYERS_PATH = "./data/players.json"
RANKS_PLAYER_PATH = "./mnt/data/ranks_player.json"  # arquivo que você carregou
EQUIP_PATH = "./data/equipamentos.json"
MAGIAS_PATH = "./data/magias.json"
ITEMS_PATH = "./data/items.json"

# try import active_combat and update_main_status from combate
try:
    from cogs.combate import active_combat, update_main_status
except Exception:
    active_combat = {}
    def update_main_status(*args, **kwargs):
        return

# -------------------------
# JSON helpers
# -------------------------
def load_json(path: str, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        with open(path, "w", encoding="utf8") as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
    with open(path, "r", encoding="utf8") as f:
        return json.load(f)

def save_json(path: str, data):
    with open(path, "w", encoding="utf8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_players() -> Dict[str, Any]:
    return load_json(PLAYERS_PATH, {})

def save_players(data: Dict[str, Any]):
    save_json(PLAYERS_PATH, data)

def load_ranks():
    return load_json(RANKS_PLAYER_PATH, {})

def load_equip():
    return load_json(EQUIP_PATH, {})

def load_magias():
    return load_json(MAGIAS_PATH, {})

def load_items():
    return load_json(ITEMS_PATH, {})

# -------------------------
# utility: roll dice formulas like "2d8+3"
# -------------------------
import re
def roll_dice(formula: str) -> int:
    if not formula:
        return 0
    s = str(formula).replace(" ", "")
    m = re.match(r"(\d+)d(\d+)([+\-]\d+)?", s)
    if not m:
        try:
            return int(s)
        except:
            return 0
    n = int(m.group(1)); faces = int(m.group(2)); mod = int(m.group(3) or 0)
    total = 0
    for _ in range(n):
        total += random.randint(1, faces)
    return total + mod

# -------------------------
# progression helpers (XP aggregation per ranks)
# -------------------------
def xp_needed_for_rank(rank_name: str, level: int, ranks_data: Dict[str, Any]) -> int:
    """
    Returns XP required for reaching the given level of rank_name
    e.g. cumulative sum of qi_xp up to that level.
    """
    if rank_name not in ranks_data:
        return 0
    total = 0
    for lv in range(1, level+1):
        entry = ranks_data[rank_name].get(str(lv), {})
        total += int(entry.get("qi_xp", 0))
    return total

def recalc_player_rank(player: Dict[str, Any], ranks_data: Dict[str, Any]):
    """
    Based on player['xp_total'], find current rank/level and update hp/mana/bba accordingly.
    Modifies player in-place.
    """
    xp = int(player.get("xp_total", 0))
    # ranks order as in your spec
    rank_order = ["bronze", "prata", "ouro", "ouro negro", "lendário"]
    # find current rank and level by scanning cumulative thresholds
    current_rank = player.get("rank", "bronze")
    current_level = player.get("nivel", 1)
    # We'll scan through rank_order and levels 1..5 until xp < threshold
    cum = 0
    new_rank = None
    new_level = None
    for r in rank_order:
        if r not in ranks_data:
            continue
        for lv in range(1,6):
            qi = int(ranks_data[r].get(str(lv), {}).get("qi_xp", 0))
            cum += qi
            if xp < cum:
                # player is at previous level
                # if lv==1 and xp < qi then level=1
                # compute previous marker:
                prev_cum = cum - qi
                # level is lv (because cum includes this level), but xp < cum means hasn't reached this level yet,
                # so actual level = lv if xp >= prev_cum else lv-1. Simpler: set new_rank/level to r and lv if xp < cum and xp >= prev_cum
                new_rank = r
                new_level = lv if xp >= prev_cum else max(1, lv-1)
                break
        if new_rank:
            break
    # fallback: if xp >= all thresholds, set highest
    if new_rank is None:
        # set to highest
        for r in reversed(rank_order):
            if r in ranks_data:
                new_rank = r
                new_level = 5
                break

    # apply stats from ranks_data for this rank/level
    if new_rank and new_level:
        stats = ranks_data.get(new_rank, {}).get(str(new_level), {})
        player["rank"] = new_rank
        player["nivel"] = int(new_level)
        # update base hp/mana/bba but keep current percent of hp/mana
        old_hp_max = int(player.get("vida_max", 1))
        old_hp = int(player.get("vida_atual", old_hp_max))
        old_mana_max = int(player.get("mana_max", 1))
        old_mana = int(player.get("mana_atual", old_mana_max))
        new_hp_max = int(stats.get("hp", old_hp_max))
        new_mana_max = int(stats.get("qi", old_mana_max))
        player["vida_max"] = new_hp_max
        # keep current hp proportionally
        player["vida_atual"] = min(new_hp_max, max(0, int(old_hp * (new_hp_max / max(1, old_hp_max)))))
        player["mana_max"] = new_mana_max
        player["mana_atual"] = min(new_mana_max, max(0, int(old_mana * (new_mana_max / max(1, old_mana_max)))))
        player["bba"] = int(stats.get("bba", player.get("bba", 0)))
# cogs/player_admin.py - Parte 2/3

# -------------------------
# elements helper
# -------------------------
def add_xp_to_element(player: Dict[str, Any], element_name: str, amount: int, ranks_data: Dict[str, Any]):
    """
    Player can have up to two elements stored in player['elementos'] as keys '1' and '2'.
    If an element matches element_name, add xp and recalc its rank/level similar to player rank.
    If none matches and there's an empty slot, assign it.
    """
    elems = player.setdefault("elementos", {})
    # try to find existing
    for slot in ("1","2"):
        e = elems.get(slot)
        if e and e.get("elemento") == element_name:
            e["xp_total"] = int(e.get("xp_total",0)) + amount
            # recalc level similarly (simpler: use xp_needed_for_rank)
            total_xp = e["xp_total"]
            # calculate new level
            cum = 0
            new_lvl = 1
            for lv in range(1,6):
                qi = int(ranks_data.get(e.get("rank","bronze"), {}).get(str(lv), {}).get("qi_xp", 0))
                cum += qi
                if total_xp < cum:
                    new_lvl = lv
                    break
            else:
                new_lvl = 5
            e["nivel"] = new_lvl
            elems[slot] = e
            return
    # not found: assign in empty slot
    for slot in ("1","2"):
        if slot not in elems or not elems[slot]:
            elems[slot] = {"elemento": element_name, "rank":"bronze", "nivel":1, "xp_total": amount}
            return
    # both occupied and not matching: add to slot 1 by default
    elems["1"]["xp_total"] = int(elems["1"].get("xp_total",0)) + amount

# -------------------------
# equipment equip/unequip
# -------------------------
def equip_item_to_player(player: Dict[str, Any], equip_key: str) -> bool:
    equip_db = load_equip()
    if equip_key not in equip_db:
        return False
    item = equip_db[equip_key]
    slot = item.get("slot")
    if not slot:
        return False
    # ensure equip structure
    equip = player.setdefault("equip", {
        "elmo": None, "peitoral": None, "luva": None, "mao_direita": None, "mao_esquerda": None,
        "botas": None, "amuleto": None, "anel1": None, "anel2": None, "anel3": None, "anel4": None
    })
    # if slot is "anel", find first empty ring slot
    if slot == "anel":
        for rk in ("anel1","anel2","anel3","anel4"):
            if not equip.get(rk):
                equip[rk] = equip_key
                break
        else:
            # replace ring1
            equip["anel1"] = equip_key
    else:
        # straightforward assign (if already something there, it is replaced)
        equip[slot] = equip_key
    # apply bonuses
    apply_equipment_bonuses(player)
    return True

def unequip_item_from_player(player: Dict[str, Any], slot: str) -> bool:
    equip = player.get("equip", {})
    if slot not in equip:
        return False
    equip[slot] = None
    apply_equipment_bonuses(player)
    return True

def apply_equipment_bonuses(player: Dict[str, Any]):
    # reset bonuses
    player["ca_bonus"] = 0
    player["absorv"] = 0
    # hp/mana bonuses are permanent increase to max (but we keep current proportion)
    extra_hp = 0
    extra_mana = 0
    equip = player.get("equip", {}) or {}
    equip_db = load_equip()
    for slot, key in equip.items():
        if not key:
            continue
        info = equip_db.get(key, {})
        extra_hp += int(info.get("hp_bonus", 0))
        extra_mana += int(info.get("mana_bonus", 0))
        player["ca_bonus"] = int(player.get("ca_bonus",0)) + int(info.get("ca_bonus",0))
        player["absorv"] = int(player.get("absorv",0)) + int(info.get("absorv",0))
        # optional attribute bonuses
        for attr in ("forca_bonus","destreza_bonus","sabedoria_bonus","constituicao_bonus"):
            if info.get(attr):
                player.setdefault("atributos", {}).setdefault(attr.replace("_bonus",""), 0)
                player["atributos"][attr.replace("_bonus","")] = int(player["atributos"].get(attr.replace("_bonus",""),0)) + int(info.get(attr,0))
    # adjust hp/mana max and current proportionally
    old_hp_max = int(player.get("vida_max", 0))
    old_hp = int(player.get("vida_atual", old_hp_max))
    new_hp_max = old_hp_max + extra_hp
    player["vida_max"] = new_hp_max
    player["vida_atual"] = min(new_hp_max, int(old_hp * (new_hp_max / max(1, old_hp_max)))) if old_hp_max>0 else new_hp_max
    old_mana_max = int(player.get("mana_max", 0))
    old_mana = int(player.get("mana_atual", old_mana_max))
    new_mana_max = old_mana_max + extra_mana
    player["mana_max"] = new_mana_max
    player["mana_atual"] = min(new_mana_max, int(old_mana * (new_mana_max / max(1, old_mana_max)))) if old_mana_max>0 else new_mana_max

# -------------------------
# commands: register / ficha / equip / unequip / give item / add xp
# -------------------------
class PlayerAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="player_criar", description="Cria ficha de jogador com rank/nível (admin ou jogador).")
    async def player_criar(self, interaction: Interaction, jogador: discord.Member = None, rank: str = "bronze", nivel: str = "1"):
        target = jogador or interaction.user
        players = load_players()
        ranks = load_ranks()
        key = str(target.id)
        if rank not in ranks or nivel not in ranks[rank]:
            return await interaction.response.send_message("Rank/nivel inválido.", ephemeral=True)
        stats = ranks[rank][nivel]
        players[key] = {
            "rank": rank,
            "nivel": int(nivel),
            "xp_total": 0,
            "vida_max": int(stats.get("hp", 10)),
            "vida_atual": int(stats.get("hp", 10)),
            "mana_max": int(stats.get("qi", 0)),
            "mana_atual": int(stats.get("qi", 0)),
            "atributos": {"forca":0,"destreza":0,"constituicao":0,"inteligencia":0,"sabedoria":0,"carisma":0},
            "equip": {"elmo":None,"peitoral":None,"luva":None,"mao_direita":None,"mao_esquerda":None,"botas":None,"amuleto":None,"anel1":None,"anel2":None,"anel3":None,"anel4":None},
            "ca_base": 10,
            "ca_bonus": 0,
            "absorv": 0,
            "inventory": {},
            "coins": 0,
            "magic_xp": {},
            "elementos": {},
            "buffs": []
        }
        save_players(players)
        await interaction.response.send_message(f"Ficha criada para {target.mention}.", ephemeral=True)
# cogs/player_admin.py - Parte 3/3

    @app_commands.command(name="ficha", description="Mostra sua ficha completa (ou de outro jogador).")
    async def ficha(self, interaction: Interaction, jogador: discord.Member = None):
        target = jogador or interaction.user
        players = load_players()
        key = str(target.id)
        if key not in players:
            return await interaction.response.send_message("Ficha não encontrada.", ephemeral=True)
        p = players[key]
        ranks = load_ranks()
        # ensure rank recalculation before showing
        recalc_player_rank(p, ranks)
        # compute CA total with equipment and buffs
        apply_equipment_bonuses(p)
        ca_total = int(p.get("ca_base", 10)) + int(p.get("ca_bonus", 0))
        embed = discord.Embed(title=f"📘 Ficha: {target.display_name}", color=discord.Color.blue())
        embed.add_field(name="Rank", value=f"{p.get('rank','?').capitalize()} (Nv {p.get('nivel',1)})", inline=True)
        embed.add_field(name="XP Total", value=str(p.get("xp_total",0)), inline=True)
        # next level xp
        # compute cum xp for current level
        ranks_data = ranks
        needed = xp_needed_for_rank(p.get("rank","bronze"), p.get("nivel",1), ranks_data)
        embed.add_field(name="Próx. Threshold (acumulado)", value=str(needed), inline=True)

        embed.add_field(name="Vida", value=f"{p.get('vida_atual',0)}/{p.get('vida_max',0)}", inline=False)
        embed.add_field(name="Mana (QI)", value=f"{p.get('mana_atual',0)}/{p.get('mana_max',0)}", inline=False)

        attrs = p.get("atributos", {})
        attrs_text = "\n".join([f"{k.capitalize()}: {v}" for k,v in attrs.items()])
        embed.add_field(name="Atributos", value=attrs_text or "-", inline=False)

        embed.add_field(name="CA Total", value=str(ca_total), inline=True)
        embed.add_field(name="Absorção", value=str(p.get("absorv",0)), inline=True)

        # equipamentos
        equip = p.get("equip", {})
        eq_txt = ""
        equip_db = load_equip()
        for slot, ik in equip.items():
            if ik:
                eq_txt += f"• {slot}: {equip_db.get(ik,{}).get('nome', ik)} (`{ik}`)\n"
            else:
                eq_txt += f"• {slot}: -\n"
        embed.add_field(name="Equipamento", value=eq_txt or "-", inline=False)

        # elementos
        elems = p.get("elementos", {})
        el_txt = ""
        for s in ("1","2"):
            e = elems.get(s)
            if e:
                el_txt += f"• Slot {s}: {e.get('elemento')} — {e.get('rank')} nv{e.get('nivel')} (XP {e.get('xp_total',0)})\n"
            else:
                el_txt += f"• Slot {s}: -\n"
        embed.add_field(name="Elementos", value=el_txt or "-", inline=False)

        # inventory
        inv = p.get("inventory", {})
        items_db = load_items()
        if inv:
            txt = ""
            for ik, q in inv.items():
                nome = items_db.get(ik, {}).get("nome", ik)
                txt += f"• {nome} (`{ik}`): {q}\n"
            embed.add_field(name="Inventário", value=txt, inline=False)
        else:
            embed.add_field(name="Inventário", value="Vazio", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="player_equipar", description="Equipa um item (usa slot definido no equipamento).")
    async def player_equipar(self, interaction: Interaction, item_key: str):
        players = load_players()
        key = str(interaction.user.id)
        if key not in players:
            return await interaction.response.send_message("Você não possui ficha.", ephemeral=True)
        success = equip_item_to_player(players[key], item_key)
        if not success:
            return await interaction.response.send_message("Equipamento inválido.", ephemeral=True)
        save_players(players)
        await interaction.response.send_message(f"✅ Equipado `{item_key}`.", ephemeral=True)
        # update combat snapshot if in combat
        for gid, data in active_combat.items():
            if key in data.get("players", {}):
                data["players"][key] = players[key]
                try:
                    await update_main_status(gid, self.bot)
                except:
                    pass

    @app_commands.command(name="player_desequipar", description="Desequipa um slot (ex: elmo, mao_direita, anel1).")
    async def player_desequipar(self, interaction: Interaction, slot: str):
        players = load_players()
        key = str(interaction.user.id)
        if key not in players:
            return await interaction.response.send_message("Você não possui ficha.", ephemeral=True)
        ok = unequip_item_from_player(players[key], slot)
        if not ok:
            return await interaction.response.send_message("Slot inválido ou vazio.", ephemeral=True)
        save_players(players)
        await interaction.response.send_message(f"✅ Desequipado slot `{slot}`.", ephemeral=True)
        for gid, data in active_combat.items():
            if key in data.get("players", {}):
                data["players"][key] = players[key]
                try:
                    await update_main_status(gid, self.bot)
                except:
                    pass

    @app_commands.command(name="player_dar_item", description="(ADM) Dar item para jogador.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def player_dar_item(self, interaction: Interaction, jogador: discord.Member, item_key: str, quantidade: int = 1):
        players = load_players()
        key = str(jogador.id)
        if key not in players:
            return await interaction.response.send_message("Jogador não possui ficha.", ephemeral=True)
        inv = players[key].setdefault("inventory", {})
        inv[item_key] = inv.get(item_key, 0) + max(1, int(quantidade))
        save_players(players)
        await interaction.response.send_message(f"🎁 Entregue {quantidade}x `{item_key}` para {jogador.mention}.", ephemeral=True)

    @app_commands.command(name="player_add_xp", description="(ADM) Adiciona XP ao jogador (útil para testes).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def player_add_xp(self, interaction: Interaction, jogador: discord.Member, valor: int):
        players = load_players()
        ranks = load_ranks()
        key = str(jogador.id)
        if key not in players:
            return await interaction.response.send_message("Jogador não possui ficha.", ephemeral=True)
        players[key]["xp_total"] = int(players[key].get("xp_total",0)) + int(valor)
        # recalcular rank
        recalc_player_rank(players[key], ranks)
        save_players(players)
        await interaction.response.send_message(f"✅ Adicionado {valor} XP para {jogador.mention}. Nova XP total: {players[key]['xp_total']}.", ephemeral=True)

# setup
async def setup(bot):
    await bot.add_cog(PlayerAdmin(bot))
