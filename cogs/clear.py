# cogs/clear.py
import discord
from discord.ext import commands
from discord import app_commands


class Clear(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="limpar",
        description="Limpa mensagens do chat (admin)."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def limpar(self, interaction: discord.Interaction, quantidade: int):
        if quantidade < 1 or quantidade > 100:
            return await interaction.response.send_message(
                "❌ A quantidade deve ser entre **1 e 100**.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        deleted = await interaction.channel.purge(limit=quantidade)

        await interaction.followup.send(
            f"🧹 **{len(deleted)} mensagens apagadas!**",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Clear(bot))
