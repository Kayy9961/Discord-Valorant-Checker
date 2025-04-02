import os
import math
import requests
import urllib.parse
import io
import concurrent.futures
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import discord
from discord.ext import commands
from discord import app_commands

forced_rarity = {"c5482640-4652-6948-29c6-769e8198db27","d6c7ff28-467e-bb3f-3c0c-c5b9445e55ca", "596ce51d-40e3-dc21-b02d-b08d070a7883"}

def get_user_info(token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = "https://auth.riotgames.com/userinfo"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_entitlements(token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = "https://entitlements.auth.riotgames.com/api/token/v1"
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data.get("entitlements_token")

def get_loadout(token, entitlements_token, region, sub):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-Entitlements-JWT": entitlements_token,
        "X-Riot-ClientVersion": "release-02.03-shipping-8-521855",
        "X-Riot-ClientPlatform": "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9"
    }
    url = f"https://pd.{region}.a.pvp.net/personalization/v2/players/{sub}/playerloadout"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_skin_data(skin_uuid):
    url = f"https://valorant-api.com/v1/weapons/skins/{skin_uuid}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def get_rarity(content_tier_uuid):
    url = f"https://valorant-api.com/v1/contenttiers/{content_tier_uuid}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def ensure_cache_folder():
    cache_folder = "cache"
    if not os.path.exists(cache_folder):
        os.makedirs(cache_folder)
    return cache_folder

def obtener_display_icon(skin_data):
    icon = skin_data.get("displayIcon")
    if icon:
        return icon
    for chroma in skin_data.get("chromas", []):
        if isinstance(chroma, dict) and chroma.get("displayIcon"):
            return chroma["displayIcon"]
    return None

def sort_skins_by_order(skin_list, desired_order):
    rarity_order_map = {
        "fuego": 0,
        "exclusive edition": 1,
        "ultra edition": 2,
        "premium edition": 3,
        "deluxe edition": 4,
        "select edition": 5
    }
    def sort_key(item):
        skin_name, _, rarity, _ = item
        name_lower = skin_name.lower()
        weapon_index = len(desired_order)
        for index, keyword in enumerate(desired_order):
            if keyword.lower() in name_lower:
                weapon_index = index
                break
        rarity_lower = rarity.lower() if rarity else ""
        rarity_index = rarity_order_map.get(rarity_lower, 999)
        return (rarity_index, weapon_index, name_lower)
    return sorted(skin_list, key=sort_key)

def annotate_cell(img, skin_name, skin_uuid, rarity, cell_width, cell_height):
    text_area = 100
    original_skin = img.copy()
    scale_factor = min(cell_width / original_skin.width, cell_height / original_skin.height)
    new_width = int(original_skin.width * scale_factor)
    new_height = int(original_skin.height * scale_factor)
    original_skin = original_skin.resize((new_width, new_height), Image.Resampling.LANCZOS)
    rarity_lower = rarity.lower() if rarity else ""
    background_files = {
        "fuego": "fuego.jpg",
        "exclusive edition": "Exclusive_Edition.png",
        "ultra edition": "Ultra_Edition.png",
        "premium edition": "Premium_Edition.png",
        "deluxe edition": "Deluxe_Edition.png",
        "select edition": "Select_Edition.png"
    }
    background_file = background_files.get(rarity_lower)
    background_path = os.path.join("Fondos", background_file) if background_file else None
    try:
        if background_path and os.path.exists(background_path):
            background_img = Image.open(background_path).convert("RGBA")
        else:
            background_img = Image.new("RGBA", (cell_width, cell_height), (0, 0, 0, 255))
        background_img = background_img.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
    except:
        background_img = Image.new("RGBA", (cell_width, cell_height), (0, 0, 0, 255))
    offset_x = (cell_width - new_width) // 2
    offset_y = (cell_height - new_height) // 2
    background_img.paste(original_skin, (offset_x, offset_y), original_skin)
    barrier = Image.new("RGBA", (cell_width, text_area), (0, 0, 0, int(255 * 0.7)))
    background_img.paste(barrier, (0, cell_height - text_area), barrier)
    draw = ImageDraw.Draw(background_img)
    caption = f"{skin_name}"
    try:
        FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "font.ttf")
        font = ImageFont.truetype(FONT_PATH, size=90)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), caption, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = (cell_width - text_width) // 2
    text_y = (cell_height - text_area) + (text_area - text_height) // 2
    draw.text((text_x, text_y), caption, fill="white", font=font)
    return background_img

def combine_images_fixed_ordered_with_logo(skin_tuples, username, item_count, base_cols=6, logo_filename="logo.png", custom_link="Discord.gg/KayyShop", tier_icon=None):
    desired_order = ["Knife","Vandal","Phantom","Guardian","Sheriff","Operator","Bulldog","Spectre","Ghost","Odin","Judge","Bucky","Shorty","Ares","Frenzy","Classic","Stinger"]
    ordered = sort_skins_by_order(skin_tuples, desired_order)
    cell_width = 1200
    cell_height = 600
    annotated_cells = []
    for skin_name, img, rarity, skin_uuid in ordered:
        cell_img = annotate_cell(img, skin_name, skin_uuid, rarity, cell_width, cell_height)
        annotated_cells.append(cell_img)
    num_images = len(annotated_cells)
    rows = math.ceil(num_images / base_cols)
    grid_width = base_cols * cell_width
    grid_height = rows * cell_height
    info_area_height = cell_height
    total_width = grid_width
    total_height = grid_height + info_area_height
    combined = Image.new("RGBA", (total_width, total_height), (0, 0, 0, 255))
    for idx, cell in enumerate(annotated_cells):
        col = idx % base_cols
        row = idx // base_cols
        position = (col * cell_width, row * cell_height)
        combined.paste(cell, position)
    info_bg = Image.new("RGBA", (total_width, info_area_height), (0, 0, 0, int(255 * 0.7)))
    combined.paste(info_bg, (0, grid_height), info_bg)
    draw = ImageDraw.Draw(combined)
    if tier_icon is not None:
        logo = tier_icon
    else:
        try:
            logo = Image.open(logo_filename).convert("RGBA")
        except:
            logo = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    logo_height = int(info_area_height * 0.6)
    logo_width = int((logo_height / logo.height) * logo.width)
    logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
    logo_x = 10
    logo_y = grid_height + (info_area_height - logo_height) // 2
    combined.paste(logo, (logo_x, logo_y), logo)
    text1 = f"Total Skins: {item_count}"
    current_date = datetime.now().strftime("%d/%m/%y")
    text2 = f"Checkeado Por {username} | {current_date}"
    text3 = custom_link
    text_x = logo_x + logo_width + 10
    max_text_width = total_width - text_x - 20
    font_size = logo_height // 3
    try:
        FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "font.ttf")
        font = ImageFont.truetype(FONT_PATH, size=font_size)
    except:
        font = ImageFont.load_default()
    def measure_text(txt, fnt):
        bbox = draw.textbbox((0, 0), txt, font=fnt)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    w1, h1 = measure_text(text1, font)
    w2, h2 = measure_text(text2, font)
    w3, h3 = measure_text(text3, font)
    while (w1 > max_text_width or w2 > max_text_width or w3 > max_text_width) and font_size > 8:
        font_size -= 1
        try:
            font = ImageFont.truetype(FONT_PATH, size=font_size)
        except:
            font = ImageFont.load_default()
        w1, h1 = measure_text(text1, font)
        w2, h2 = measure_text(text2, font)
        w3, h3 = measure_text(text3, font)
    total_text_height = h1 + h2 + h3 + 10
    text_y_start = grid_height + (info_area_height - total_text_height) // 2
    draw.text((text_x, text_y_start), text1, fill="white", font=font)
    draw.text((text_x, text_y_start + h1 + 5), text2, fill="white", font=font)
    draw.text((text_x, text_y_start + h1 + 5 + h2 + 5), text3, fill="white", font=font)
    return combined

def obtener_access_token(url):
    parsed_url = urllib.parse.urlparse(url)
    fragment = urllib.parse.parse_qs(parsed_url.fragment)
    access_token = fragment.get("access_token", [None])[0]
    return access_token

def get_rank(token, entitlements_token, region, sub):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-Entitlements-JWT": entitlements_token,
        "X-Riot-ClientVersion": "release-02.03-shipping-8-521855",
        "X-Riot-ClientPlatform": "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9"
    }
    url = f"https://pd.{region}.a.pvp.net/mmr/v1/players/{sub}/competitiveupdates"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    matches = data.get("Matches", [])
    if not matches:
        return "Unranked"
    last_match = matches[-1]
    tier_after = last_match.get("TierAfterUpdate")
    RankIDtoRank = {
        "0": "Unranked","1": "Unused1","2": "Unused2","3": "Iron 1","4": "Iron 2","5": "Iron 3",
        "6": "Bronz 1","7": "Bronz 2","8": "Bronz 3","9": "Silver 1","10": "Silver 2","11": "Silver 3",
        "12": "Gold 1","13": "Gold 2","14": "Gold 3","15": "Platinum 1","16": "Platinum 2","17": "Platinum 3",
        "18": "Diamond 1","19": "Diamond 2","20": "Diamond 3","21": "Immortal 1","22": "Immortal 2","23": "Immortal 3","24": "Radiant"
    }
    return RankIDtoRank.get(str(tier_after), "Unknown")

def get_tier_number(rank):
    mapping = {
        "Unranked": 0,"Unused1": 1,"Unused2": 2,"Iron 1": 3,"Iron 2": 4,"Iron 3": 5,
        "Bronz 1": 6,"Bronz 2": 7,"Bronz 3": 8,"Silver 1": 9,"Silver 2": 10,"Silver 3": 11,
        "Gold 1": 12,"Gold 2": 13,"Gold 3": 14,"Platinum 1": 15,"Platinum 2": 16,"Platinum 3": 17,
        "Diamond 1": 18,"Diamond 2": 19,"Diamond 3": 20,"Immortal 1": 21,"Immortal 2": 22,"Immortal 3": 23,"Radiant": 24
    }
    return mapping.get(rank, None)

def get_cached_tier_icon(rank):
    cache_folder = ensure_cache_folder()
    tier_num = get_tier_number(rank)
    if tier_num is None:
        return None
    filename = os.path.join(cache_folder, f"competitive_{tier_num}.png")
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        try:
            return Image.open(filename).convert("RGBA")
        except:
            pass
    constructed_url = f"https://media.valorant-api.com/competitivetiers/564d8e28-c226-3180-6285-e48a390db8b1/{tier_num}/largeicon.png"
    try:
        icon_response = requests.get(constructed_url)
        icon_response.raise_for_status()
        with open(filename, "wb") as f:
            f.write(icon_response.content)
        return Image.open(filename).convert("RGBA")
    except:
        return None

def process_skin_uuid(skin_uuid, cache_folder):
    try:
        skin_info = get_skin_data(skin_uuid)
        skin_data = skin_info.get("data", {})
        skin_name = skin_data.get("displayName", "Desconocido")
        if "Standard" in skin_name:
            return None
        content_tier_uuid = skin_data.get("contentTierUuid")
        if content_tier_uuid:
            rarity_info = get_rarity(content_tier_uuid)
            rarity = rarity_info.get("data", {}).get("displayName", "Unknown")
        else:
            rarity = "Unknown"
        if skin_uuid in forced_rarity:
            rarity = "fuego"
        display_icon = obtener_display_icon(skin_data)
        if not display_icon:
            return None
        safe_name = "".join(c for c in skin_name if c.isalnum() or c in " -_").rstrip()
        save_path = os.path.join(cache_folder, f"{safe_name}.png")
        if not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
            r = requests.get(display_icon)
            r.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(r.content)
        img = Image.open(save_path).convert("RGBA")
        return (skin_name, img, rarity, skin_uuid)
    except:
        return None

class ValorantCheckerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self):
        await self.tree.sync()

bot = ValorantCheckerBot()

@bot.tree.command(name="checker", description="Procesa tu access_token y muestra tus skins de Valorant")
@app_commands.describe(access_token="Ingresa el access_token obtenido de la URL (opcional)")
async def checker(interaction: discord.Interaction, access_token: str = None):
    if not access_token:
        embed = discord.Embed(
            title="¡Importante!",
            description="Antes de hacer los pasos, debes cerrar sesión en tu cuenta de Riot Games (Solo del Navegador). Luego, inicia sesión en: https://auth.riotgames.com/authorize?redirect_uri=https%3A%2F%2Fplayvalorant.com%2Fopt_in&client_id=play-valorant-web-prod&response_type=token%20id_token&nonce=1&scope=account%20openid Una vez inicies sesión, verás un error. Copia el enlace y vuelve a intentarlo con /checker https://playvalorant.com...",
            color=0xFF0000
        )
        try:
            referencia_image = discord.File("referencia.png", filename="referencia.png")
            embed.set_image(url="attachment://referencia.png")
            await interaction.response.send_message(embed=embed, file=referencia_image, ephemeral=True)
        except:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    token = obtener_access_token(access_token)
    if not token:
        embed = discord.Embed(
            title="¡Importante!",
            description="Copia el enlace completo al iniciar sesión y pégalo en /checker. Revisa que contenga #access_token=...",
            color=0xFF0000
        )
        try:
            referencia_image = discord.File("referencia.png", filename="referencia.png")
            embed.set_image(url="attachment://referencia.png")
            await interaction.response.send_message(embed=embed, file=referencia_image, ephemeral=True)
        except:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    await interaction.response.defer()
    try:
        discord_username = interaction.user.display_name
        user_info = get_user_info(token)
        sub = user_info.get("sub")
        entitlements_token = get_entitlements(token)
        if not entitlements_token:
            await interaction.followup.send("No se pudo obtener el token de entitlements.", ephemeral=True)
            return
        loadout = get_loadout(token, entitlements_token, "eu", sub)
        guns = loadout.get("Guns", [])
        if not guns:
            await interaction.followup.send("No se encontraron skins.", ephemeral=True)
            return
        cache_folder = ensure_cache_folder()
        skin_uuids = [gun.get("SkinID") for gun in guns]
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_skin_uuid, s, cache_folder) for s in skin_uuids]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        skin_tuples = [res for res in results if res]
        if not skin_tuples:
            await interaction.followup.send("No se descargaron imágenes de skins para combinar.", ephemeral=True)
            return
        try:
            rank = get_rank(token, entitlements_token, "eu", sub)
        except:
            rank = "Unknown"
        tier_icon_img = get_cached_tier_icon(rank)
        combined_image = combine_images_fixed_ordered_with_logo(
            skin_tuples, discord_username, len(skin_tuples), base_cols=6,
            logo_filename="logo.png", custom_link="Discord.gg/KayyShop", tier_icon=tier_icon_img
        )
        output_buffer = io.BytesIO()
        combined_image.save(output_buffer, format="PNG")
        output_buffer.seek(0)
        image_file = discord.File(fp=output_buffer, filename="valorant_skins_combined.png")
        embed_info = discord.Embed(title="Información de tu cuenta", color=0x00FF00)
        embed_info.add_field(name="Nombre de usuario", value=discord_username, inline=False)
        embed_info.add_field(name="Rango Actual", value=rank, inline=False)
        embed_info.add_field(name="Total Skins", value=str(len(skin_tuples)), inline=False)
        embed_info.set_image(url="attachment://valorant_skins_combined.png")
        await interaction.followup.send(embed=embed_info, file=image_file)
    except Exception as e:
        await interaction.followup.send(f"Ocurrió un error: {e}", ephemeral=True)

bot.run("EL TOKEN DE TU BOT DE DISCORD")
