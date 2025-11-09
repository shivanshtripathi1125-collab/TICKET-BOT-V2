import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
import os
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
import json

load_dotenv()

# -------------------- CONFIG --------------------
TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL") or "https://www.youtube.com/@YourChannel"

TICKET_COMMAND_CHANNEL_ID = 1431633723467501769
TICKET_LOG_CHANNEL_ID = 1434241829733404692
COOLDOWN_HOURS = 24

APPS_FILE = "apps.json"

# -------------------- DISCORD SETUP --------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tickets = {}
user_cooldowns = {}
banned_users = set()
last_requested_app = {}

# Load apps from file
if os.path.exists(APPS_FILE):
    with open(APPS_FILE, "r") as f:
        apps_dict = json.load(f)
else:
    apps_dict = {}  # format: {"spotify": "link", "youtube": "link", ...}

# -------------------- FLASK KEEPALIVE --------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_flask).start()

# -------------------- HELPER FUNCTIONS --------------------
async def create_transcript_embed(channel, user, created_at):
    messages = [m async for m in channel.history(limit=100, oldest_first=True)]
    content = ""
    for m in messages:
        time = m.created_at.strftime("%H:%M")
        content += f"[{time}] {m.author.display_name}: {m.content or '[Attachment]'}\n"

    embed = discord.Embed(
        title=f"🧾 Ticket Transcript - {channel.name}",
        description=content[:4000] or "No messages found.",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text=f"Closed ticket by {user.display_name}")
    return embed

async def close_ticket(channel, user):
    info = tickets.pop(channel.id, None)
    if info:
        log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
        transcript_embed = await create_transcript_embed(channel, user, info["created_at"])
        if log_channel:
            await log_channel.send(embed=transcript_embed)
        await channel.delete()

# -------------------- VIEWS --------------------
class CreateTicketButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Create Ticket", style=discord.ButtonStyle.green, emoji="🎟️")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_ticket_creation(interaction)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red)
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏳ This ticket will close in 5 seconds...", ephemeral=True)
        await asyncio.sleep(5)
        await close_ticket(interaction.channel, interaction.user)

class ConfirmForceCloseView(discord.ui.View):
    def __init__(self, channel, user):
        super().__init__(timeout=30)
        self.channel = channel
        self.user = user

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Only the admin who issued the command can confirm.", ephemeral=True)
            return
        await interaction.response.send_message("🕒 Closing ticket in 3 seconds...", ephemeral=True)
        await asyncio.sleep(3)
        await close_ticket(self.channel, interaction.user)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Only the admin who issued the command can cancel.", ephemeral=True)
            return
        await interaction.response.send_message("✅ Force-close canceled.", ephemeral=True)
        self.stop()

# -------------------- MAIN LOGIC --------------------
async def handle_ticket_creation(interaction: discord.Interaction):
    user = interaction.user
    now = datetime.datetime.utcnow()

    if user.id in banned_users:
        await interaction.response.send_message("🚫 You are banned from creating tickets.", ephemeral=True)
        return

    if user.id in user_cooldowns:
        diff = now - user_cooldowns[user.id]
        if diff.total_seconds() < COOLDOWN_HOURS * 3600:
            remaining = COOLDOWN_HOURS - (diff.total_seconds() / 3600)
            await interaction.response.send_message(f"⏳ You can open another ticket in **{int(remaining)} hours**.", ephemeral=True)
            return

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)
    }

    channel = await interaction.guild.create_text_channel(
        name=f"ticket-{user.name}",
        overwrites=overwrites,
        category=None
    )

    tickets[channel.id] = {"user_id": user.id, "created_at": now, "last_activity": now}
    user_cooldowns[user.id] = now

    embed = discord.Embed(
        title="🎫 Premium App Ticket Created",
        description=(
            f"Hello {user.mention} 👋\n\n"
            "Welcome to your personal ticket.\n\n"
            f"💠 **Available Apps:**\n" +
            "\n".join([f"{app.capitalize()} 🎁" for app in apps_dict.keys()]) +
            "\n\n💬 Type the app name below to get your app link!"
        ),
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="Ticket System | Powered by Rash Tech")

    await channel.send(embed=embed)
    await interaction.response.send_message(f"🎟️ Ticket created: {channel.mention}", ephemeral=True)

# -------------------- BOT COMMANDS --------------------
@bot.tree.command(name="ticket", description="Create a new premium app ticket.")
async def ticket_command(interaction: discord.Interaction):
    await handle_ticket_creation(interaction)

@bot.tree.command(name="send_app", description="Send app download link and close button (Admin only)")
@app_commands.describe(app_name="Name of the app")
async def send_app(interaction: discord.Interaction, app_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can send app links.", ephemeral=True)
        return

    # Case-insensitive search for the app
    app_key = None
    for key in apps_dict.keys():
        if key.lower() == app_name.lower():
            app_key = key
            break

    if not app_key:
        await interaction.response.send_message(f"⚠️ No link found for **{app_name}**. Please add it using /addapp first.", ephemeral=True)
        return

    link = apps_dict[app_key]

    embed = discord.Embed(
        title=f"🎁 Your Premium App: {app_key.capitalize()}",
        description=f"Here is your app link: {link}\n\nThank you! ❤️\nPlease close this ticket when done.",
        color=discord.Color.blurple(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="Premium Delivery | Rash Tech")

    await interaction.channel.send(embed=embed, view=CloseTicketView())
    await interaction.response.send_message(f"✅ App link for **{app_key.capitalize()}** sent successfully.", ephemeral=True)

@bot.tree.command(name="addapp", description="Add a new app with its download link (Admin only)")
@app_commands.describe(app_name="Name of the app", app_link="Download link for the app")
async def addapp(interaction: discord.Interaction, app_name: str, app_link: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can add apps.", ephemeral=True)
        return

    apps_dict[app_name] = app_link
    # Save to file
    with open(APPS_FILE, "w") as f:
        json.dump(apps_dict, f, indent=4)

    await interaction.response.send_message(f"✅ App **{app_name}** added successfully with link.", ephemeral=True)

@bot.tree.command(name="force_close", description="Force close the current or mentioned ticket (Admin only)")
@app_commands.describe(channel="(Optional) Ticket channel to close")
async def force_close(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can use this command.", ephemeral=True)
        return

    channel = channel or interaction.channel
    if channel.id not in tickets:
        await interaction.response.send_message("⚠️ This is not a valid ticket channel.", ephemeral=True)
        return

    embed = discord.Embed(
        title="⚠️ Confirm Ticket Closure",
        description=f"Are you sure you want to **force close** `{channel.name}`?\nThis will delete the channel and log the transcript.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="Admin Confirmation Required | Auto-cancels in 30s")
    view = ConfirmForceCloseView(channel, interaction.user)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="remove_cooldown", description="Remove a user's ticket cooldown (Admin only)")
@app_commands.describe(user="User to remove cooldown")
async def remove_cooldown(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can remove cooldowns.", ephemeral=True)
        return

    if user.id in user_cooldowns:
        user_cooldowns.pop(user.id)
        await interaction.response.send_message(f"✅ Cooldown removed for {user.mention}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ {user.mention} does not have an active cooldown.", ephemeral=True)

# -------------------- ON MESSAGE --------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id in tickets:
        tickets[message.channel.id]["last_activity"] = datetime.datetime.utcnow()

        content = message.content.lower()

        for app in apps_dict.keys():
            if app.lower() in content:
                last_requested_app[message.channel.id] = app
                embed = discord.Embed(
                    title="💫 Premium App Requested",
                    description=f"You requested **{app.capitalize()}**!\n\nAn admin will send you the download link shortly.",
                    color=discord.Color.blurple(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_footer(text="Rash Tech | Ticket System")
                await message.channel.send(embed=embed)
                break

    await bot.process_commands(message)

# -------------------- ON READY --------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    channel = bot.get_channel(TICKET_COMMAND_CHANNEL_ID)
    if channel:
        async for msg in channel.history(limit=10):
            if msg.author == bot.user:
                await msg.delete()

        embed = discord.Embed(
            title="🎟️ Premium App Support",
            description="💫 To get a **premium app**, please create a ticket below!\nOur team will help you as soon as possible.",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Rash Tech | Support Bot")

        await channel.send(embed=embed, view=CreateTicketButton())

# -------------------- RUN --------------------
bot.run(TOKEN)
