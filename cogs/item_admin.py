import discord
from discord.ext import commands
from discord import app_commands
import json
import os

ITEMS_PATH = "./data/items.json"

def load_items():
    if not os.path.exists(ITEMS_PATH):
        with open(ITEMS_PATH, "w", encoding="utf8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
    with open(ITEMS_PATH, "r", encoding="utf8") as f:
        return json.load(f)

def save_items(data):
    with open(ITEMS_PATH, "w", encoding="utf8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

class ItemAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="item_criar", description="Cria um item (admin).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def criar(
        self,
        interaction: discord.Interaction,
        key: str,
        nome: str,
        tipo: str,
        valor: int,
        descricao: str
    ):
        """
        tipo: 'hp' ou 'mana'
        key: identificador sem espaço (usado no comando /usar_item)
        """
        key = key.lower()
        if tipo not in ("hp", "mana", "buff", "craft"):
            return await interaction.response.send_message("Tipo inválido. Use 'hp', 'mana', 'buff' ou 'craft'.", ephemeral=True)

        items = load_items()
        if key in items:
            return await interaction.response.send_message("Já existe um item com essa chave.", ephemeral=True)

        items[key] = {
            "nome": nome,
            "tipo": tipo,
            "valor": int(valor),
            "descricao": descricao
        }
        save_items(items)
        await interaction.response.send_message(f"✅ Item **{nome}** criado com chave `{key}`.")

    @app_commands.command(name="item_listar", description="Lista itens disponíveis.")
    async def listar(self, interaction: discord.Interaction):
        items = load_items()
        if not items:
            return await interaction.response.send_message("Nenhum item cadastrado.", ephemeral=True)

        embed = discord.Embed(title="📦 Itens", color=discord.Color.blurple())
        for key, it in items.items():
            embed.add_field(name=f"{it['nome']} (`{key}`)", value=f"{it['descricao']}\nTipo: {it['tipo']} • Valor: {it['valor']}", inline=False)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(ItemAdmin(bot))
