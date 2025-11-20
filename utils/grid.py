from PIL import Image, ImageDraw, ImageFont
import aiohttp
import io
import math

# Configurações de layout do card
CARD_WIDTH = 360
CARD_HEIGHT = 140
PADDING = 10
IMG_SIZE = 120  # imagem à esquerda (largura e altura)
TEXT_AREA_X = PADDING + IMG_SIZE + 10
TEXT_AREA_WIDTH = CARD_WIDTH - TEXT_AREA_X - PADDING

# Fonte: usar a fonte padrão do PIL (carrega bitmap básico)
try:
    DEFAULT_FONT = ImageFont.truetype("arial.ttf", 16)
    SMALL_FONT = ImageFont.truetype("arial.ttf", 14)
except:
    DEFAULT_FONT = ImageFont.load_default()
    SMALL_FONT = ImageFont.load_default()


async def fetch_image(session, url):
    try:
        async with session.get(url) as resp:
            data = await resp.read()
            return Image.open(io.BytesIO(data)).convert("RGBA")
    except:
        return None


def draw_hp_bar(draw: ImageDraw.Draw, x, y, width, height, current, maximum):
    # Background
    draw.rectangle([x, y, x + width, y + height], outline=None, fill=(60, 60, 60))
    # Filled portion
    if maximum <= 0:
        pct = 0
    else:
        pct = max(0, min(1, current / maximum))
    filled_w = int(width * pct)
    if filled_w > 0:
        draw.rectangle([x, y, x + filled_w, y + height], fill=(50, 205, 50))
    # Border
    draw.rectangle([x, y, x + width, y + height], outline=(0, 0, 0))


async def gerar_grid(inimigos: dict, colunas: int = 3):
    """
    inimigos: dict { id: monster_data, ... }
    Retorna BytesIO de PNG com grid estilo card (imagem à esquerda, texto à direita)
    """
    # coletar monstros (pular GRID_MSG se existir)
    mobs = []
    for k, v in inimigos.items():
        if k == "GRID_MSG":
            continue
        mobs.append(v)

    if not mobs:
        return None

    # baixar imagens em paralelo
    async with aiohttp.ClientSession() as session:
        images = []
        for mob in mobs:
            img = None
            if mob.get("img"):
                img = await fetch_image(session, mob["img"])
            images.append(img)

    # criar cards
    cards = []
    for mob, img in zip(mobs, images):
        card = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (240, 240, 240, 255))
        draw = ImageDraw.Draw(card)

        # borda externa
        draw.rectangle([0, 0, CARD_WIDTH - 1, CARD_HEIGHT - 1], outline=(40, 40, 40), width=2)

        # imagem do lado esquerdo
        if img:
            img = img.copy()
            img.thumbnail((IMG_SIZE, IMG_SIZE))
            # centralizar verticalmente na área da imagem
            img_x = PADDING
            img_y = PADDING + (CARD_HEIGHT - 2 * PADDING - IMG_SIZE) // 2
            card.paste(img, (img_x, img_y), img)
        else:
            # retângulo vazio se sem imagem
            img_x = PADDING
            img_y = PADDING + (CARD_HEIGHT - 2 * PADDING - IMG_SIZE) // 2
            draw.rectangle([img_x, img_y, img_x + IMG_SIZE, img_y + IMG_SIZE], fill=(180, 180, 180))

        # Texto: nome
        name_text = f"{mob.get('nome', 'Monstro')} #{mob.get('id')}"
        draw.text((TEXT_AREA_X, PADDING), name_text, font=DEFAULT_FONT, fill=(10, 10, 10))

        # HP bar and text
        hp_y = PADDING + 28
        bar_x = TEXT_AREA_X
        bar_w = TEXT_AREA_WIDTH - 10
        bar_h = 14
        draw_hp_bar(draw, bar_x, hp_y, bar_w, bar_h, mob.get("vida_atual", 0), mob.get("vida_max", 1))
        hp_text = f"HP: {mob.get('vida_atual',0)}/{mob.get('vida_max',0)}"
        draw.text((TEXT_AREA_X, hp_y + bar_h + 4), hp_text, font=SMALL_FONT, fill=(20,20,20))

        # CA, KI and BBA
        info_y = hp_y + bar_h + 26
        ca_text = f"CA: {mob.get('ca', 0)}"
        ki_text = f"KI: {mob.get('ki', 0)}"
        bba_val = mob.get("bba", 0)
        bba_text = f"BBA: {'+' if bba_val >= 0 else ''}{bba_val}"

        draw.text((TEXT_AREA_X, info_y), ca_text, font=SMALL_FONT, fill=(10,10,10))
        draw.text((TEXT_AREA_X + 110, info_y), ki_text, font=SMALL_FONT, fill=(10,10,10))
        draw.text((TEXT_AREA_X, info_y + 18), bba_text, font=SMALL_FONT, fill=(10,10,10))

        cards.append(card)

    # montar grid
    total = len(cards)
    linhas = math.ceil(total / colunas)
    grid_w = CARD_WIDTH * colunas
    grid_h = CARD_HEIGHT * linhas

    grid = Image.new("RGBA", (grid_w, grid_h), (30, 30, 30, 255))

    for idx, card in enumerate(cards):
        x = (idx % colunas) * CARD_WIDTH
        y = (idx // colunas) * CARD_HEIGHT
        grid.paste(card, (x, y), card)

    # exportar
    buffer = io.BytesIO()
    grid.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
