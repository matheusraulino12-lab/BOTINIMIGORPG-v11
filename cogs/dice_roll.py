# cogs/dice_roll.py

import discord
from discord.ext import commands
from discord import app_commands
import random
import re


# =====================================================
# Interpreta expressão como "1d20 + 2 Percepção"
# =====================================================
def parse_dice(expression: str):
    tokens = expression.split()
    last_token = tokens[-1]

    if not re.search(r"\d+d\d+", last_token):
        nome = last_token
        formula = " ".join(tokens[:-1])
    else:
        nome = None
        formula = expression

    match = re.search(r"(\d+)d(\d+)", formula)
    if not match:
        raise ValueError("Formato inválido. Use algo como: 1d20 + 2 Percepção")

    qtd = int(match.group(1))
    faces = int(match.group(2))

    modificador = 0
    mod_match = re.search(r"([+\-]\s*\d+)", formula)
    if mod_match:
        modificador = int(mod_match.group(1).replace(" ", ""))

    return qtd, faces, modificador, nome


# =====================================================
# Rola dados (simples)
# =====================================================
def roll_dice(qtd, faces):
    return [random.randint(1, faces) for _ in range(qtd)]


# =====================================================
# Classe da COG
# =====================================================
class DiceRoll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="rolar",
        description="Rola um dado: 1d20 + 2 Percepção (suporta vantagem, desvantagem e rolagem secreta)"
    )
    @app_commands.describe(
        expressao="Ex: 1d20 + 3 Percepção",
        modo="normal / vantagem / desvantagem",
        secreto="A rolagem só aparece para o mestre?"
    )
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="Normal", value="normal"),
            app_commands.Choice(name="Vantagem", value="vantagem"),
            app_commands.Choice(name="Desvantagem", value="desvantagem")
        ],
        secreto=[
            app_commands.Choice(name="Não (público)", value="nao"),
            app_commands.Choice(name="Sim (somente mestre)", value="sim")
        ]
    )
    async def rolar(self, interaction: discord.Interaction, expressao: str, modo: app_commands.Choice[str], secreto: app_commands.Choice[str]):

        # =====================================================
        # PARSE DA EXPRESSÃO
        # =====================================================
        try:
            qtd, faces, modificador, nome = parse_dice(expressao)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

        # =====================================================
        # DIFERENTES MODOS DE ROLAGEM
        # =====================================================
        modo = modo.value

        if modo == "normal":
            rolls = roll_dice(qtd, faces)

        elif modo == "vantagem":
            # rola 2 vezes, pega maior d20 (modo D&D)
            r1 = roll_dice(qtd, faces)
            r2 = roll_dice(qtd, faces)
            rolls = r1 if sum(r1) >= sum(r2) else r2
            rolls.extend(["(vantagem)", r1, r2])  # incluir info extra

        elif modo == "desvantagem":
            r1 = roll_dice(qtd, faces)
            r2 = roll_dice(qtd, faces)
            rolls = r1 if sum(r1) <= sum(r2) else r2
            rolls.extend(["(desvantagem)", r1, r2])

        # calcula valor
        soma = 0
        base_roll = rolls

        # se vantagem/desvantagem → rolls contém info extra
        if isinstance(rolls[0], int):
            soma = sum([x for x in rolls if isinstance(x, int)])
        else:
            soma = 0

        resultado_final = soma + modificador

        # =====================================================
        # Checagem de crítico/falha
        # =====================================================
        color = discord.Color.blurple()
        critico = False
        falha = False

        if qtd == 1 and faces == 20:
            roll = rolls[0]
            if roll == 20:
                critico = True
                color = discord.Color.green()
            elif roll == 1:
                falha = True
                color = discord.Color.red()

        # =====================================================
        # TÍTULO
        # =====================================================
        titulo = f"🎲 Rolagem de {interaction.user.display_name}"
        if nome:
            titulo += f" — **{nome}**"

        # =====================================================
        # EMBED
        # =====================================================
        embed = discord.Embed(title=titulo, color=color)

        embed.add_field(name="🧮 Fórmula", value=f"`{expressao}`", inline=False)

        # modo vantagem/desvantagem
        if "vantagem" in rolls:
            embed.add_field(name="Modo", value="🟩 **VANTAGEM**", inline=False)
            embed.add_field(name="Dados", value=f"1ª: {rolls[-2]} | 2ª: {rolls[-1]}", inline=False)
            embed.add_field(name="Usado", value=f"🎯 {rolls[0]}", inline=True)

        elif "desvantagem" in rolls:
            embed.add_field(name="Modo", value="🟥 **DESVANTAGEM**", inline=False)
            embed.add_field(name="Dados", value=f"1ª: {rolls[-2]} | 2ª: {rolls[-1]}", inline=False)
            embed.add_field(name="Usado", value=f"🎯 {rolls[0]}", inline=True)
        else:
            embed.add_field(name="📊 Resultado do Dado", value=f"`{base_roll}`", inline=False)

        # crítico / falha
        if critico:
            embed.add_field(name="💥 Crítico!", value="**20 natural!**", inline=False)
        elif falha:
            embed.add_field(name="💀 Falha Crítica!", value="**1 natural!**", inline=False)

        embed.add_field(name="🔢 Resultado Final", value=f"**{resultado_final}**", inline=False)

        embed.set_footer(text=f"Rolado por {interaction.user.display_name}")

        # =====================================================
        # ROLAGEM SECRETA (somente mestre vê)
        # =====================================================
        is_secret = (secreto.value == "sim")

        if is_secret:
            # define quem é o mestre → dono do servidor
            guild_owner = interaction.guild.owner

            await interaction.response.send_message(
                f"🔒 Rolagem secreta enviada somente ao mestre.",
                ephemeral=True
            )

            # envia embed apenas para o mestre
            try:
                await guild_owner.send(embed=embed)
            except:
                await interaction.followup.send("⚠️ Não consegui enviar DM ao mestre.", ephemeral=True)

            return

        # =====================================================
        # rolagem pública
        # =====================================================
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(DiceRoll(bot))
