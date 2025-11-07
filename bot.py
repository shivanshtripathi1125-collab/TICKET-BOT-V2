import os
import json
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
import io
from flask import Flask
import threading
from dotenv import load_dotenv

load_dotenv()

# ---- Environment Variables ----
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID"))
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL")  # 👈 Add this to your .env

# ---- Load App Links ----
def load_apps():
    with open("apps.json", "r") as f:
        return json.load(f)

apps_data = load_apps()

# ---- Discord Setup ----
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
cooldowns = {}
tickets = {}

# ---- Flask Server ----
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ---- Cooldown Helper ----
def cooldown_expired(user_id):
    if user_id not in cooldowns:
        return True
    return (datetime.datetime.utcnow() - cooldowns[user_id]).total_seconds() >= 86400

# ---- /ticket Command ----
@bot.tree.command(name="ticket", description="Create a new support ticket.")
async def ticket(interaction: discord.Interaction):
    user = interaction.user

    if not cooldown_expired(user.id):
        remaining = 86400 - (datetime.datetime.utcnow() - cooldowns[user.id]).total_seconds()
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        await interaction.response.send_message(
            f"⏳ You can create another ticket in **{hours}h {mins}m**.", ephemeral=True
        )
        return

    guild = interaction.guild
    category = discord.utils.get(guild.categories, name="Tickets")
    if category is None:
        category = await guild.create_category("Tickets")

    channel = await guild.create_text_channel(
        f"ticket-{user.name}",
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
    )

    cooldowns[user.id] = datetime.datetime.utcnow()
    tickets[channel.id] = user.id

    embed = discord.Embed(
        title="🎟️ Welcome to your ticket!",
        description=(
            "Hello! Please wait while our team assists you.\n\n"
            "Here are the premium apps we currently provide:\n"
            "• Spotify\n• YouTube\n• Kinemaster\n• Hotstar\n• Truecaller\n• Castle\n\n"
            "_More apps will come soon!_"
        ),
        color=discord.Color.green()
    )

    await channel.send(content=f"{user.mention}", embed=embed)
    await interaction.response.send_message(f"✅ Your ticket has been created: {channel.mention}", ephemeral=True)

# ---- Listen for App Names ----
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id in tickets:
        msg_content = message.content.lower()
        for app_name in apps_data.keys():
            if app_name.lower() in msg_content:
                embed = discord.Embed(
                    title="🔐 Verification Required",
                    description=(
                        f"To get your **{app_name.capitalize()}** app link:\n\n"
                        f"👉 First, [**Subscribe to our YouTube channel**]({YOUTUBE_CHANNEL_URL})\n"
                        "📸 Then, **send a screenshot** of your subscription in this ticket.\n\n"
                        "Once verified by staff, you'll receive your app link!"
                    ),
                    color=discord.Color.blue()
                )
                await message.channel.send(embed=embed)
                break

    await bot.process_commands(message)

# ---- Admin Command: Send App Link ----
@bot.tree.command(name="send_app", description="Send the verified app link to a user (Admin only).")
@app_commands.describe(user="User to send the app link to", app_name="Name of the app")
async def send_app(interaction: discord.Interaction, user: discord.User, app_name: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    app_name = app_name.lower()
    if app_name not in apps_data:
        await interaction.response.send_message(f"❌ App `{app_name}` not found in apps.json.", ephemeral=True)
        return

    app_link = apps_data[app_name]

    embed = discord.Embed(
        title=f"🎉 Here’s your {app_name.capitalize()} download link!",
        description=f"[Click here to download]({app_link})\n\nThank you for verifying!",
        color=discord.Color.green()
    )
    await user.send(embed=embed)
    await interaction.response.send_message(f"✅ Sent **{app_name.capitalize()}** link to {user.mention}", ephemeral=True)

# ---- Transcript + Close Ticket ----
class CloseTicketButton(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You can’t close this ticket.", ephemeral=True)
            return

        transcript = ""
        async for msg in interaction.channel.history(limit=None, oldest_first=True):
            transcript += f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author}: {msg.content}\n"

        file = discord.File(io.StringIO(transcript), filename=f"transcript-{interaction.channel.name}.txt")
        log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
        await log_channel.send(f"🗂️ Transcript for {interaction.channel.name}", file=file)

        await interaction.response.send_message("✅ Ticket closed. Transcript saved!", ephemeral=True)
        await interaction.channel.delete()

# ---- Bot Events ----
@bot.event
async def on_ready():
    await asyncio.sleep(2)
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("✅ Slash commands synced to guild.")
    except Exception as e:
        print(f"⚠️ Command sync error: {e}")

    print(f"🤖 Logged in as {bot.user}")

# ---- Run Flask + Bot ----
threading.Thread(target=run_flask).start()
bot.run(TOKEN)
