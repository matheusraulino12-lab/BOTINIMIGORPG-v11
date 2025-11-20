# cogs/help.py
import discord
from discord.ext import commands
from discord import app_commands, Interaction

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Mostra os comandos disponíveis organizados por categoria.")
    async def help(self, interaction: Interaction):
        embed = discord.Embed(title="📚 Ajuda - Comandos", color=discord.Color.green())
        embed.add_field(name="🧑‍🎓 Player", value=(
            "/ficha - mostra sua ficha\n"
            "/player_criar - cria ficha\n"
            "/player_equipar - equipar item\n"
            "/player_desequipar - desequipar slot\n"
            "/inventario - mostra inventário\n"
            "/usar_item - usar item consumível\n"
        ), inline=False)
        embed.add_field(name="🔧 Admin", value=(
            "/player_criar (admin) - criar ficha para outro\n"
            "/player_dar_item - dar item a jogador\n"
            "/player_add_xp - adicionar xp (teste)\n"
            "/set_coins - setar coins\n"
            "/dar_item - entregar item (loot cog)\n"
        ), inline=False)
        embed.add_field(name="⚔️ Combate", value=(
            "/combate_iniciar - iniciar combate (novo sistema)\n"
            "/combate_status - atualizar embed do combate\n"
            "/combate_encerrar - encerrar combate\n"
        ), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
