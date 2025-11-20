# cogs/combate_turnos.py
import discord
from discord.ext import commands
from discord import app_commands, Interaction
import asyncio
import json
import os
import random
import math
from typing import Dict, Any, List, Optional

# Paths
PLAYERS_PATH = "./data/players.json"
MONSTERS_PATH = "./data/monsters.json"
EQUIP_PATH = "./data/equipamentos.json"
MAGIAS_PATH = "./data/magias.json"
ITEMS_PATH = "./data/items.json"
RANKS_PLAYER_PATH = "./data/ranks_player.json"

# Import active_combat from combate.py (versão B)
try:
    from cogs.combate import active_combat, update_main_status
except Exception:
    active_combat = {}
    def update_main_status(*args, **kwargs):
        return

# ======================================================
# JSON helpers
# ======================================================
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

def load_players():
    return load_json(PLAYERS_PATH, {})

def save_players(data):
    save_json(PLAYERS_PATH, data)

def load_monsters():
    return load_json(MONSTERS_PATH, {})

def load_equip():
    return load_json(EQUIP_PATH, {})

def load_magias():
    return load_json(MAGIAS_PATH, {})

def load_items():
    return load_json(ITEMS_PATH, {})

def load_ranks_player():
    return load_json(RANKS_PLAYER_PATH, {})

# ======================================================
# Dice utils
# ======================================================
import re
def roll_dice(formula: str) -> int:
    s = (formula or "").replace(" ", "")
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

# ======================================================
# Initiative and turn helpers
# ======================================================
def calc_initiative_for_player(player: Dict[str, Any]) -> int:
    dex = int(player.get("atributos", {}).get("destreza", 0))
    return random.randint(1, 20) + dex

def calc_initiative_for_monster(mon: Dict[str, Any]) -> int:
    # monsters may have 'init_bonus'
    return random.randint(1, 20) + int(mon.get("init_bonus", 0))

def build_turn_order(snapshot_players: Dict[str, Any], monsters: Dict[str, Any]) -> List[Dict[str, Any]]:
    order = []
    for uid, p in snapshot_players.items():
        init = calc_initiative_for_player(p)
        order.append({"type": "player", "id": str(uid), "initiative": init})
    for mid, m in monsters.items():
        init = calc_initiative_for_monster(m)
        order.append({"type": "monster", "id": int(mid), "initiative": init})
    # sort desc
    order.sort(key=lambda x: x["initiative"], reverse=True)
    return order

# ======================================================
# Small helpers to compute CA and apply damage
# ======================================================
def compute_ca_for_player(player: Dict[str, Any]) -> int:
    base = int(player.get("ca_base", 10))
    ca_bonus = int(player.get("ca_bonus", 0))
    # equipment bonuses
    equip = player.get("equip", {})
    equip_db = load_equip()
    for slot, key in (equip or {}).items():
        if key:
            info = equip_db.get(key, {})
            base += int(info.get("ca_bonus", 0))
    # buffs
    for b in player.get("buffs", []):
        base += int(b.get("ca_mod", 0))
    return base + ca_bonus

def apply_damage_to_monster(guild_id: int, monster_id: int, dano: int):
    # modifies active_combat in-memory; caller should call update_main_status
    if guild_id not in active_combat:
        return
    monsters = active_combat[guild_id].get("monsters", {})
    if monster_id not in monsters:
        return
    m = monsters[monster_id]
    before = int(m.get("vida_atual", 0))
    m["vida_atual"] = max(0, before - int(dano))
    monsters[monster_id] = m
    active_combat[guild_id]["monsters"] = monsters

# ======================================================
# View: entry and start buttons (no sleep)
# ======================================================
class IniciarCombateView(discord.ui.View):
    def __init__(self, guild_id: int, owner_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.jogadores = set()

    @discord.ui.button(label="Entrar no Combate", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: Interaction, button: discord.ui.Button):
        self.jogadores.add(interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} entrou no combate!", ephemeral=False)

# send "OK PARTE 2" when ready for next part
# ---------------------------
# PARTE 2/5
# ---------------------------

    # botão iniciar (continuação da View)
    @discord.ui.button(label="Iniciar Combate (Mestre)", style=discord.ButtonStyle.red)
    async def iniciar(self, interaction: Interaction, button: discord.ui.Button):
        # somente o mestre/owner pode iniciar (ou permissões)
        if interaction.user.id != self.owner_id and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Apenas o Mestre pode iniciar o combate.", ephemeral=False)

        if self.guild_id not in active_combat:
            return await interaction.response.send_message("Combate não encontrado (inconsistência).", ephemeral=False)

        combate = active_combat[self.guild_id]
        # snapshot de players selecionados
        players_db = load_players()
        for pid in list(self.jogadores):
            k = str(pid)
            if k in players_db:
                combate["players"][k] = players_db[k]
            else:
                # cria ficha padrão
                combate["players"][k] = {
                    "rank": "bronze", "nivel": 1,
                    "vida_max": 10, "vida_atual": 10,
                    "mana_max": 1, "mana_atual": 1,
                    "atributos": {"forca":0,"destreza":0,"constituicao":0,"inteligencia":0,"sabedoria":0,"carisma":0},
                    "equip": {},
                    "ca_base": 10, "ca_bonus": 0, "absorv": 0,
                    "inventory": {}, "coins": 0, "xp_total": 0, "magic_xp": {}, "elementos": {}
                }

        # build turn order
        ordem = build_turn_order(combate.get("players", {}), combate.get("monsters", {}))
        combate["turn_order"] = ordem
        combate["current_index"] = 0
        combate["round"] = 1
        combate["status"] = "running"

        # save back
        active_combat[self.guild_id] = combate

        # send status update and initial turn embed
        await update_main_status(self.guild_id, interaction.client)
        await interaction.response.send_message("⚔️ Combate iniciado! Ordem definida e turno 1 pronto.", ephemeral=False)

# ======================================================
# Command to create combat (replaces old sleep-based)
# ======================================================
class CombateTurnos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="combate_iniciar", description="Inicia um combate (nova versão com botões).")
    @app_commands.describe(inimigo="chave do monstro no monsters.json", rank="rank", nivel="nivel do rank", quantidade="quantidade de inimigos")
    async def combate_iniciar(self, interaction: Interaction, inimigo: str, rank: str, nivel: str, quantidade: int = 1):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("Use em servidor.", ephemeral=True)

        monsters_db = load_monsters()
        ranks = load_ranks_player()

        if inimigo not in monsters_db:
            return await interaction.response.send_message("Monstro não encontrado no banco.", ephemeral=True)
        if rank not in ranks or nivel not in ranks[rank]:
            return await interaction.response.send_message("Rank ou nível inválido.", ephemeral=True)

        stats = ranks[rank][nivel]

        # criar categoria/com canal
        category = discord.utils.get(guild.categories, name="COMBATES")
        if category is None:
            category = await guild.create_category("COMBATES")

        base = f"combate-{inimigo}-{quantidade}"
        channel = await guild.create_text_channel(f"{base} (0 vivos)", category=category)

        # inicializa active_combat
        active_combat[guild.id] = {
            "channel_id": channel.id,
            "main_message_id": None,
            "channel_base_name": base,
            "monsters": {},
            "players": {},
            "turn_order": [],
            "current_index": 0,
            "round": 0,
            "status": "waiting"
        }

        # cria monstros snapshot
        for i in range(1, quantidade+1):
            active_combat[guild.id]["monsters"][i] = {
                "id": i,
                "nome": monsters_db[inimigo].get("nome", inimigo),
                "rank": rank,
                "nivel": int(nivel),
                "vida_max": stats["vida"],
                "vida_atual": stats["vida"],
                "ca": stats["ca"],
                "ki": stats["ki"],
                "dano": stats["dano"],
                "img": monsters_db[inimigo].get("img"),
                "bba": stats.get("bba", 0)
            }

        # envia mensagem inicial com botões de entrar/iniciar
        view = IniciarCombateView(guild.id, interaction.user.id)
        sent = await channel.send(
            "⚔️ **Novo combate criado!** Jogadores: cliquem em Entrar no Combate.\nMestre: clique em Iniciar Combate quando estiver pronto.",
            view=view
        )

        active_combat[guild.id]["main_message_id"] = sent.id

        await interaction.response.send_message(f"Canal criado: {channel.mention}", ephemeral=False)

# ======================================================
# Advance turn and control view
# ======================================================
def get_current_actor(gid: int) -> Optional[Dict[str, Any]]:
    data = active_combat.get(gid)
    if not data:
        return None
    order = data.get("turn_order", [])
    idx = data.get("current_index", 0)
    if not order:
        return None
    # wrap
    if idx < 0 or idx >= len(order):
        idx = 0
        data["current_index"] = 0
    return order[idx]

async def advance_turn(guild_id: int, bot: commands.Bot):
    if guild_id not in active_combat:
        return
    data = active_combat[guild_id]
    order = data.get("turn_order", [])
    if not order:
        return
    data["current_index"] = (data.get("current_index",0) + 1) % len(order)
    if data["current_index"] == 0:
        data["round"] = data.get("round",1) + 1
    active_combat[guild_id] = data
    # update main status and announce current actor
    await update_main_status(guild_id, bot)
    actor = get_current_actor(guild_id)
    channel = bot.get_channel(data["channel_id"])
    if actor:
        if actor["type"] == "player":
            uid = int(actor["id"])
            await channel.send(f"➡️ **Vez de <@{uid}>** — round {data.get('round',1)}")
        else:
            await channel.send(f"➡️ **Vez do Monstro #{actor['id']}** — round {data.get('round',1)}")

class TurnControlView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="Próximo Turno", style=discord.ButtonStyle.blurple)
    async def next_turn(self, interaction: Interaction, button: discord.ui.Button):
        # permission check (allow any in combat or only master?)
        gid = self.guild_id
        await interaction.response.send_message("⏭️ Avançando turno...", ephemeral=False)
        await advance_turn(gid, interaction.client)

    @discord.ui.button(label="Pausar", style=discord.ButtonStyle.gray)
    async def pause(self, interaction: Interaction, button: discord.ui.Button):
        gid = self.guild_id
        if gid in active_combat:
            active_combat[gid]["status"] = "paused"
            await interaction.response.send_message("⏸️ Combate pausado.", ephemeral=False)
            await update_main_status(gid, interaction.client)
        else:
            await interaction.response.send_message("Nenhum combate ativo.", ephemeral=False)

    @discord.ui.button(label="Encerrar Combate", style=discord.ButtonStyle.red)
    async def end_combat(self, interaction: Interaction, button: discord.ui.Button):
        gid = self.guild_id
        if gid in active_combat:
            del active_combat[gid]
            await interaction.response.send_message("🛑 Combate encerrado.", ephemeral=False)
        else:
            await interaction.response.send_message("Nenhum combate ativo.", ephemeral=True)

# ======================================================
# ActionMenuView - botões principais das ações do jogador
# ======================================================
class ActionMenuView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.button(label="Atacar", style=discord.ButtonStyle.primary)
    async def atacar(self, interaction: Interaction, button: discord.ui.Button):
        # abre select de alvos (enviar uma mensagem com selects)
        gid = self.guild_id
        if gid not in active_combat:
            return await interaction.response.send_message("Nenhum combate ativo.", ephemeral=True)
        monsters = active_combat[gid].get("monsters", {})
        options = []
        for mid, m in monsters.items():
            label = f"{m.get('nome')} #{mid} ({m.get('vida_atual')}/{m.get('vida_max')})"
            options.append(discord.SelectOption(label=label, value=str(mid)))
        if not options:
            return await interaction.response.send_message("Nenhum inimigo disponível.", ephemeral=True)

        # dynamic select view
        class TargetSelect(discord.ui.View):
            def __init__(self, opts, guild_id, user_id):
                super().__init__(timeout=60)
                self.select = discord.ui.Select(placeholder="Escolha o inimigo", options=opts, min_values=1, max_values=1)
                self.add_item(self.select)
                self.guild_id = guild_id
                self.user_id = user_id

            @discord.ui.select()
            async def callback(self, select: discord.ui.Select, interaction_sel: Interaction):
                target_id = int(select.values[0])
                await interaction_sel.response.send_message(f"Você escolheu atacar o inimigo #{target_id}. Processando ataque...", ephemeral=False)
                # rolar ataque: 1d20 + bba + forca/destreza do player
                gid = self.guild_id
                player_key = str(interaction_sel.user.id)
                players_db = load_players()
                player = players_db.get(player_key)
                if not player:
                    return await interaction_sel.followup.send("Sua ficha não foi encontrada.", ephemeral=True)
                bba = int(player.get("bba", 0))
                força = int(player.get("atributos", {}).get("forca", 0))
                destreza = int(player.get("atributos", {}).get("destreza", 0))
                # choose whether weapon is finesse etc. For simplicity, use forca + destreza average
                mod_attr = max(força, destreza)
                d20 = random.randint(1,20)
                total = d20 + bba + mod_attr
                # prepare embed with roll
                embed = discord.Embed(title=f"Ataque de {interaction_sel.user.display_name}", description=f"Rolagem: 1d20 → **{d20}** + BBA **{bba}** + Atributo **{mod_attr}** = **{total}**", color=discord.Color.orange())
                # find monster
                monster = active_combat[gid]["monsters"].get(target_id)
                embed.add_field(name='Alvo', value=f"{monster.get('nome')} #{target_id}")
                view = MonsterHitConfirmView(gid, target_id, interaction_sel.user.id, total, interaction_sel.user)
                ch = interaction_sel.client.get_channel(active_combat[gid]["channel_id"])
                try:
                    await ch.send(embed=embed, view=view)
                except:
                    await interaction_sel.followup.send("Erro ao enviar a ação no canal do combate.", ephemeral=True)
                self.stop()

        view = TargetSelect(options, gid, interaction.user.id)
        await interaction.response.send_message("Selecione o alvo no menu (apenas você vê).", view=view, ephemeral=True)

    @discord.ui.button(label="Magia", style=discord.ButtonStyle.secondary)
    async def magia(self, interaction: Interaction, button: discord.ui.Button):
        # abrir menu de magias do jogador
        gid = self.guild_id
        player_key = str(interaction.user.id)
        players_db = load_players()
        player = players_db.get(player_key)
        if not player:
            return await interaction.response.send_message("Você não possui ficha.", ephemeral=True)
        magias_db = load_magias()
        # build options based on learned magias in player (magic_xp keys)
        learned = player.get("magic_xp", {})  # keys are magic ids
        opts = []
        for mk in learned.keys():
            md = magias_db.get(mk)
            if md:
                opts.append(discord.SelectOption(label=md.get("nome", mk), value=mk))
        if not opts:
            return await interaction.response.send_message("Você não conhece magias.", ephemeral=True)

        class MagicSelectView(discord.ui.View):
            def __init__(self, opts, guild_id, user_id):
                super().__init__(timeout=60)
                self.add_item(discord.ui.Select(placeholder="Escolha uma magia", options=opts, min_values=1, max_values=1))
                self.guild_id = guild_id
                self.user_id = user_id

            @discord.ui.select()
            async def callback(self, select, interaction_sel: Interaction):
                magic_key = select.values[0]
                # here we should show ranks available based on player's magic_xp and let them choose rank and targets
                await interaction_sel.response.send_message(f"Você escolheu a magia `{magic_key}` — seleção de rank e alvos não implementada nesta view (placeholder).", ephemeral=True)
                self.stop()

        view = MagicSelectView(opts, gid, interaction.user.id)
        await interaction.response.send_message("Selecione a magia que deseja usar.", view=view, ephemeral=True)

    @discord.ui.button(label="Itens", style=discord.ButtonStyle.gray)
    async def itens(self, interaction: Interaction, button: discord.ui.Button):
        # show player's consumables and let choose
        players_db = load_players()
        player = players_db.get(str(interaction.user.id))
        if not player:
            return await interaction.response.send_message("Você não tem ficha.", ephemeral=True)
        inv = player.get("inventory", {})
        if not inv:
            return await interaction.response.send_message("Seu inventário está vazio.", ephemeral=True)
        items_db = load_items()
        opts = []
        for k, q in inv.items():
            name = items_db.get(k, {}).get("nome", k)
            opts.append(discord.SelectOption(label=f"{name} x{q}", value=k))
        class ItemSelectView(discord.ui.View):
            def __init__(self, opts):
                super().__init__(timeout=60)
                self.add_item(discord.ui.Select(placeholder="Escolha item para usar", options=opts, min_values=1, max_values=1))
            @discord.ui.select()
            async def callback(self, select, interaction_sel: Interaction):
                ik = select.values[0]
                # call usar_item flow
                # for simplicity, reuse player_admin.usar_item command if cog present
                try:
                    from cogs.player_admin import PlayerAdmin
                except:
                    pass
                await interaction_sel.response.send_message(f"Item `{ik}` usado (placeholder).", ephemeral=True)
                self.stop()
        view = ItemSelectView(opts)
        await interaction.response.send_message("Selecione o item que deseja usar.", view=view, ephemeral=True)

# ======================================================
# MonsterHitConfirmView - confirm hit and allow reaction options to target
# ======================================================
class MonsterHitConfirmView(discord.ui.View):
    def __init__(self, guild_id: int, monster_id: int, attacker_id: int, roll_total: int, attacker_user: discord.User):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.monster_id = monster_id
        self.attacker_id = attacker_id
        self.roll_total = roll_total
        self.attacker_user = attacker_user
        self.resolved = False

    @discord.ui.button(label="✔ Acertou", style=discord.ButtonStyle.success)
    async def acertou(self, interaction: Interaction, button: discord.ui.Button):
        if self.resolved:
            return await interaction.response.send_message("Já resolvido.", ephemeral=True)
        self.resolved = True
        # compute damage from attacker's equipped weapon
        players_db = load_players()
        player = players_db.get(str(self.attacker_id))
        weapon_key = player.get("equip", {}).get("mao_direita")
        equip_db = load_equip()
        weapon = equip_db.get(weapon_key, {})
        damage_formula = weapon.get("dano", "1d4")
        dano = roll_dice(damage_formula)
        # apply damage
        apply_damage_to_monster(self.guild_id, self.monster_id, dano)
        # notify channel
        ch = interaction.client.get_channel(active_combat[self.guild_id]["channel_id"])
        await ch.send(f"🎯 {self.attacker_user.mention} acertou {active_combat[self.guild_id]['monsters'][self.monster_id]['nome']} #{self.monster_id} e causou **{dano}** de dano!")
        # now offer reactions to the target player (if target is a player)
        # if the monster attacks a player, we would prompt them; in this flow attacker attacked monster so no reflex needed
        await update_main_status(self.guild_id, interaction.client)
        # disable buttons
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

    @discord.ui.button(label="❌ Errou", style=discord.ButtonStyle.danger)
    async def errou(self, interaction: Interaction, button: discord.ui.Button):
        if self.resolved:
            return await interaction.response.send_message("Já resolvido.", ephemeral=True)
        self.resolved = True
        ch = interaction.client.get_channel(active_combat[self.guild_id]["channel_id"])
        await ch.send(f"❌ {self.attacker_user.mention} errou o ataque em {active_combat[self.guild_id]['monsters'][self.monster_id]['nome']} #{self.monster_id}! Oportunidade gerada.")
        # disable buttons
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

# ======================================================
# ReactionView for player when monster attacks player
# ======================================================
class ReactionView(discord.ui.View):
    def __init__(self, guild_id: int, player_id: int, monster_id: int, damage: int):
        super().__init__(timeout=30)
        self.guild_id = guild_id
        self.player_id = player_id
        self.monster_id = monster_id
        self.damage = damage
        self.resolved = False

    @discord.ui.button(label="Reflexo", style=discord.ButtonStyle.primary)
    async def reflexo(self, interaction: Interaction, button: discord.ui.Button):
        if self.resolved:
            return await interaction.response.send_message("Já resolveu.", ephemeral=True)
        self.resolved = True
        # simple reflex check: 1d20 + destreza vs DC 10 + monster-level
        players_db = load_players()
        player = players_db.get(str(self.player_id))
        if not player:
            return await interaction.response.send_message("Ficha não encontrada.", ephemeral=True)
        dex = int(player.get("atributos", {}).get("destreza", 0))
        roll = random.randint(1,20) + dex
        dc = 10 + int(active_combat[self.guild_id]["monsters"][self.monster_id].get("nivel",1))
        if roll >= dc:
            # success: avoid full damage (half)
            mitig = math.floor(self.damage/2)
            # apply half damage
            # apply absorption first
            absorv = player.get("absorv",0)
            mitig_after_abs = max(0, mitig - absorv)
            player["vida_atual"] = max(0, player.get("vida_atual",0) - mitig_after_abs)
            save_players(players_db)
            ch = interaction.client.get_channel(active_combat[self.guild_id]["channel_id"])
            await ch.send(f"🌀 {interaction.user.mention} fez Reflexo! Dano reduzido para {mitig_after_abs}. Vida atual: {player['vida_atual']}/{player['vida_max']}")
        else:
            # failed reflex: opportunity for others
            ch = interaction.client.get_channel(active_combat[self.guild_id]["channel_id"])
            await ch.send(f"❌ {interaction.user.mention} falhou no Reflexo! Outros jogadores têm oportunidade de reação.")
            # send message to channel allowing others to react (simple ping)
            await ch.send("Outros jogadores: clique em **Atacar (Oportunidade)** se desejar (placeholder).")
        # disable view
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

    @discord.ui.button(label="Magia", style=discord.ButtonStyle.secondary)
    async def magia(self, interaction: Interaction, button: discord.ui.Button):
        # placeholder: allow player to cast a reaction spell (open magic select)
        await interaction.response.send_message("Selecione uma magia de reação (placeholder).", ephemeral=False)

    @discord.ui.button(label="Defender", style=discord.ButtonStyle.gray)
    async def defender(self, interaction: Interaction, button: discord.ui.Button):
        # apply temporary buff to CA for this player for 1 turn
        players_db = load_players()
        p = players_db.get(str(self.player_id))
        if not p:
            return await interaction.response.send_message("Ficha não encontrada.", ephemeral=True)
        p.setdefault("buffs", []).append({"ca_mod": 4, "turns": 1})
        save_players(players_db)
        ch = interaction.client.get_channel(active_combat[self.guild_id]["channel_id"])
        await ch.send(f"🛡️ {interaction.user.mention} se defende! CA aumentada temporariamente.")
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

    @discord.ui.button(label="Levar Dano", style=discord.ButtonStyle.danger)
    async def levar(self, interaction: Interaction, button: discord.ui.Button):
        players_db = load_players()
        p = players_db.get(str(self.player_id))
        if not p:
            return await interaction.response.send_message("Ficha não encontrada.", ephemeral=True)
        absorv = p.get("absorv", 0)
        dano_final = max(0, self.damage - absorv)
        p["vida_atual"] = max(0, p.get("vida_atual",0) - dano_final)
        save_players(players_db)
        ch = interaction.client.get_channel(active_combat[self.guild_id]["channel_id"])
        await ch.send(f"💥 {interaction.user.mention} recebeu {dano_final} de dano (após absorção). Vida atual: {p['vida_atual']}/{p['vida_max']}")
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

# ======================================================
# Helper when monster acts: choose target player and apply flow
# ======================================================
async def monster_attack_flow(guild_id: int, monster_id: int, bot: commands.Bot):
    data = active_combat.get(guild_id)
    if not data:
        return
    monster = data["monsters"].get(monster_id)
    if not monster:
        return
    # choose a random alive player
    players = data.get("players", {})
    alive_players = [pid for pid,p in players.items() if p.get("vida_atual",0) > 0]
    if not alive_players:
        ch = bot.get_channel(data["channel_id"])
        await ch.send("Nenhum jogador vivo para atacar.")
        return
    target_pid = int(random.choice(alive_players))
    # roll attack and damage
    d20 = random.randint(1,20)
    bba = int(monster.get("bba", 0))
    total = d20 + bba
    dmg_formula = monster.get("dano", "1d4")
    dmg = roll_dice(dmg_formula)
    ch = bot.get_channel(data["channel_id"])
    embed = discord.Embed(title=f"{monster.get('nome')} #{monster_id} ataca!", description=f"Rolagem: 1d20 → **{d20}** + BBA **{bba}** = **{total}**\nDano (pré-rolado): **{dmg}**", color=discord.Color.red())
    embed.add_field(name="Alvo", value=f"<@{target_pid}>")
    view = ReactionView(guild_id, target_pid, monster_id, dmg)
    await ch.send(embed=embed, view=view)

# ======================================================
# Setup the cog
# ======================================================
async def setup(bot):
    await bot.add_cog(CombateTurnos(bot))
    
