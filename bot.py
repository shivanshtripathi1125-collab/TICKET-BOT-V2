import os
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import asyncio
import json
import pytesseract
from PIL import Image
from io import BytesIO
from flask import Flask
import threading
from datetime import datetime, timedelta

# -----------------------
# ENV VARIABLES
# -----------------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
TICKET_CHANNEL_ID = 1431633723467501769
LOG_CHANNEL_ID = 1434241829733404692
YOUTUBE_URL = "https://www.youtube.com/@RashTechOfficial"  # your channel link

# -----------------------
# BOT SETUP
# -----------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

cooldowns = {}
active_tickets = {}
apps_file = "apps.json"

# -----------------------
# UTILITIES
# -----------------------
def load_apps():
    if not os.path.exists(apps_file):
        with open(apps_file, "w") as f:
            json.dump({}, f)
    with open(apps_file, "r") as f:
        return json.load(f)

def save_apps(apps):
    with open(apps_file, "w") as f:
        json.dump(apps, f, indent=4)

def get_app_link(name):
    apps = load_apps()
    for k, v in apps.items():
        if k.lower() == name.lower():
            return v
    return None

async def make_transcript(channel):
    messages = [f"**{m.author}**: {m.content}" async for m in channel.history(limit=None, oldest_first=True)]
    embed = discord.Embed(
        title=f"🧾 Transcript for {channel.name}",
        description="\n".join(messages[-20:]) or "No messages",
        color=discord.Color.dark_grey()
    )
    embed.set_footer(text=f"Ticket closed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    await log_channel.send(embed=embed)

# -----------------------
# EMBED HELPERS
# -----------------------
def premium_embed(title, description, color):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="RASH TECH • Premium Ticket System")
    return embed

# -----------------------
# COMMANDS
# -----------------------
@tree.command(name="ticket", description="Create a new ticket.")
async def ticket_command(interaction: discord.Interaction):
    user = interaction.user
    now = datetime.utcnow()
    if user.id in cooldowns and now < cooldowns[user.id]:
        remaining = cooldowns[user.id] - now
        await interaction.response.send_message(
            f"⏳ You can create another ticket in {int(remaining.total_seconds() // 3600)}h {int((remaining.total_seconds()%3600)//60)}m.",
            ephemeral=True)
        return

    guild = interaction.guild
    category = discord.utils.get(guild.categories, name="🎫 Tickets")
    if not category:
        category = await guild.create_category(name="🎫 Tickets")

    ticket_channel = await guild.create_text_channel(
        name=f"ticket-{user.name}",
        category=category,
        topic=f"Ticket for {user.name}",
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        },
    )
    cooldowns[user.id] = now + timedelta(hours=24)
    active_tickets[user.id] = ticket_channel.id

    welcome = premium_embed(
        "🎟️ Welcome to Your Ticket!",
        f"Hey {user.mention}, thanks for creating a ticket!\n\nHere are the premium apps we currently provide:\n"
        f"**Spotify** 🎵\n**YouTube** ▶️\n**Kinemaster** 🎬\n**Hotstar** 🍿\n**Truecaller** ☎️\n**Castle** 🏰\n\n"
        "Type the app name to get started!",
        discord.Color.blue()
    )
    await ticket_channel.send(embed=welcome)
    await interaction.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

@tree.command(name="add_app", description="Add a new premium app (admin only).")
@app_commands.describe(app_name="Name of the app", app_link="Download link")
async def add_app(interaction: discord.Interaction, app_name: str, app_link: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
    apps = load_apps()
    apps[app_name] = app_link
    save_apps(apps)
    await interaction.response.send_message(f"✅ Added **{app_name}** to the app list.")

@tree.command(name="send_app", description="Manually send app download link in current ticket.")
@app_commands.describe(app_name="App name")
async def send_app(interaction: discord.Interaction, app_name: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
    link = get_app_link(app_name)
    if not link:
        return await interaction.response.send_message("❌ App not found in list.", ephemeral=True)
    embed = premium_embed("📥 Your Download Link", f"Here is your **{app_name}** download link:\n{link}", discord.Color.green())
    await interaction.response.send_message(embed=embed)
    view = View()
    close_button = Button(label="Close Ticket", style=discord.ButtonStyle.red, emoji="🔒")
    async def close_callback(inter):
        await inter.response.send_message("⏳ Ticket will close in 5 seconds...", ephemeral=True)
        await asyncio.sleep(5)
        await make_transcript(inter.channel)
        await inter.channel.delete()
    close_button.callback = close_callback
    view.add_item(close_button)
    await interaction.followup.send("If you are satisfied, you can close the ticket:", view=view)

@tree.command(name="force_close", description="Force close the current ticket (admin only).")
async def force_close(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
    await make_transcript(interaction.channel)
    await interaction.channel.delete()

# -----------------------
# MESSAGE LISTENER (Verification + OCR)
# -----------------------
@bot.event
async def on_message(message):
    if message.author.bot or not isinstance(message.channel, discord.TextChannel):
        return

    if message.channel.category and "ticket" in message.channel.category.name.lower():
        if message.attachments:
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg"]):
                    img_bytes = await attachment.read()
                    img = Image.open(BytesIO(img_bytes))
                    text = pytesseract.image_to_string(img).lower()
                    if "rash tech" in text and "subscribed" in text:
                        await message.channel.send(embed=premium_embed(
                            "✅ Verification Complete!",
                            f"Thank you {message.author.mention}! Verification successful.\nHere is your app download link:",
                            discord.Color.green()
                        ))
                        await message.channel.send("Use `/send_app` or wait for admin to send your app link.")
                    else:
                        await message.channel.send(embed=premium_embed(
                            "❌ Invalid Screenshot",
                            "Please upload a clear screenshot showing you've subscribed to **RASH TECH**.",
                            discord.Color.red()
                        ))
        else:
            content = message.content.lower()
            app_link = get_app_link(content)
            if app_link:
                verify_embed = premium_embed(
                    "🔐 Verification Required",
                    f"To get **{content.title()}**, you must first verify.\n\n1️⃣ Subscribe to our YouTube channel → {YOUTUBE_URL}\n"
                    "2️⃣ Post a screenshot of your subscription here.\n\nOnce verified, you'll receive your download link.",
                    discord.Color.gold()
                )
                await message.channel.send(embed=verify_embed)
    await bot.process_commands(message)

# -----------------------
# PANEL ON STARTUP
# -----------------------
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    channel = bot.get_channel(TICKET_CHANNEL_ID)
    async for msg in channel.history(limit=10):
        if msg.author == bot.user:
            await msg.delete()
    embed = premium_embed(
        "🎟️ Get Your Premium Apps",
        "To get a premium app, please create a ticket below!\n\nClick the button to begin ⬇️",
        discord.Color.purple()
    )
    view = View()
    create_btn = Button(label="Create Ticket", emoji="✅", style=discord.ButtonStyle.green)

    async def create_callback(interaction):
        await ticket_command(interaction)

    create_btn.callback = create_callback
    view.add_item(create_btn)
    await channel.send(embed=embed, view=view)
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Logged in as {bot.user}")

# -----------------------
# FLASK KEEPALIVE
# -----------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask).start()

bot.run(TOKEN)
