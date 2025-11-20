import discord
from discord.ext import commands
from discord import app_commands
import json


# ======================
# Funções para JSON
# ======================
def load_monsters():
    with open("./data/monsters.json", "r", encoding="utf8") as f:
        return json.load(f)


def save_monsters(data):
    with open("./data/monsters.json", "w", encoding="utf8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ======================
# AUTOCOMPLETE
# ======================
async def autocomplete_monstros(interaction: discord.Interaction, current: str):
    db = load_monsters()
    nomes = list(db.keys())

    sugestões = [n for n in nomes if current.lower() in n.lower()]

    return [
        app_commands.Choice(name=name.capitalize(), value=name)
        for name in sugestões[:25]
    ]


# ======================
# COG ADMINISTRATIVA
# ======================
class MonsterAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # =======================================================
    # /monstro_criar
    # =======================================================
    @app_commands.command(
        name="monstro_criar",
        description="Cria um monstro novo no JSON."
    )
    async def criar(
        self, interaction: discord.Interaction,
        nome: str,
        imagem_url: str
    ):

        nome_key = nome.lower()
        db = load_monsters()

        if nome_key in db:
            return await interaction.response.send_message(
                "❌ Já existe um monstro com esse nome!",
                ephemeral=True
            )

        # cria monstro
        db[nome_key] = {
            "img": imagem_url
        }

        save_monsters(db)

        await interaction.response.send_message(
            f"✅ Monstro **{nome.capitalize()}** criado com sucesso!"
        )

    # =======================================================
    # /monstro_listar
    # =======================================================
    @app_commands.command(
        name="monstro_listar",
        description="Lista todos os monstros cadastrados no JSON."
    )
    async def listar(self, interaction: discord.Interaction):
        db = load_monsters()

        if not db:
            return await interaction.response.send_message(
                "📭 Nenhum monstro cadastrado.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="📚 Lista de Monstros",
            description=f"Total: **{len(db)}**",
            color=discord.Color.gold()
        )

        for nome, m in db.items():
            embed.add_field(
                name=nome.capitalize(),
                value=f"**Imagem:** {m['img']}",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    # =======================================================
    # /monstro_editar
    # =======================================================
    @app_commands.command(
        name="monstro_editar",
        description="Edita um monstro já cadastrado."
    )
    @app_commands.autocomplete(nome=autocomplete_monstros)
    async def editar(
        self, interaction: discord.Interaction,
        nome: str,
        atributo: str,
        valor: str
    ):

        nome_key = nome.lower()
        atributo = atributo.lower()

        db = load_monsters()

        if nome_key not in db:
            return await interaction.response.send_message(
                "❌ Monstro não encontrado!",
                ephemeral=True
            )

        if atributo not in ["img"]:
            return await interaction.response.send_message(
                "❌ Atributo inválido! Apenas: `img`",
                ephemeral=True
            )

        # atualiza
        db[nome_key][atributo] = valor

        save_monsters(db)

        await interaction.response.send_message(
            f"✅ Monstro **{nome.capitalize()}** atualizado.\n"
            f"`{atributo}` agora é **{valor}**"
        )



async def setup(bot):
    await bot.add_cog(MonsterAdmin(bot))
