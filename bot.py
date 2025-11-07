import os
import json
import asyncio
import datetime
import io
import threading
from flask import Flask
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# ------------------  ENVIRONMENT SETUP  ------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID"))
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL")

# ------------------  LOAD APPS  ------------------
def load_apps():
    with open("apps.json", "r") as f:
        return json.load(f)

apps_data = load_apps()

# ------------------  DISCORD SETUP  ------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

cooldowns = {}
tickets = {}

# ------------------  FLASK KEEPALIVE  ------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot web server running."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ======================================================
#                      HELPERS
# ======================================================
def cooldown_expired(user_id: int):
    """Check if a user can open a ticket again."""
    if user_id not in cooldowns:
        return True
    return (datetime.datetime.utcnow() - cooldowns[user_id]).total_seconds() >= 86400


async def create_transcript(channel):
    transcript = ""
    async for msg in channel.history(limit=None, oldest_first=True):
        transcript += f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author}: {msg.content}\n"
    return io.StringIO(transcript)


# ======================================================
#                      COMMANDS
# ======================================================
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
    category = discord.utils.get(guild.categories, name="🎫 Tickets")
    if category is None:
        category = await guild.create_category("🎫 Tickets")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    channel = await guild.create_text_channel(f"ticket-{user.name}", category=category, overwrites=overwrites)

    cooldowns[user.id] = datetime.datetime.utcnow()
    tickets[channel.id] = user.id

    embed = discord.Embed(
        title="🎟️ Welcome to Your Ticket!",
        description=(
            f"Hello {user.mention}! 👋\n\n"
            "Thank you for reaching out to our support.\n\n"
            "Here are the **Premium Apps** we currently provide:\n"
            "💠 Spotify\n"
            "💠 YouTube\n"
            "💠 Kinemaster\n"
            "💠 Hotstar\n"
            "💠 Truecaller\n"
            "💠 Castle\n\n"
            "_More apps will come soon!_\n\n"
            "To get started, please type the **name** of the app you want below 👇"
        ),
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="Ticket Support System | Powered by Your Server")

    await channel.send(content=f"{user.mention}", embed=embed)
    await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)


# ----------------------------------------------------------
#  Listen for App Name (Verification Trigger)
# ----------------------------------------------------------
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
                        f"You're requesting **{app_name.capitalize()}**!\n\n"
                        f"To continue, please follow these steps:\n\n"
                        f"1️⃣ [**Subscribe to our YouTube Channel**]({YOUTUBE_CHANNEL_URL})\n"
                        "2️⃣ Take a clear screenshot after subscribing.\n"
                        "3️⃣ Upload that screenshot **here in this ticket.**\n\n"
                        "Once verified by a staff member, you’ll receive your app link!"
                    ),
                    color=discord.Color.blurple(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_footer(text="Verification Process | Stay tuned")
                await message.channel.send(embed=embed)
                break

    await bot.process_commands(message)


# ----------------------------------------------------------
# /send_app (Enhanced)
# ----------------------------------------------------------
@bot.tree.command(name="send_app", description="Send the verified app link to a user (Admin only)")
@app_commands.describe(user="User to send the app to", app_name="Name of the app")
async def send_app(interaction: discord.Interaction, user: discord.User, app_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an admin to use this.", ephemeral=True)
        return

    app_key = app_name.lower()
    if app_key not in apps_data:
        await interaction.response.send_message(f"❌ `{app_name}` not found in apps.json.", ephemeral=True)
        return

    app_link = apps_data[app_key]
    embed = discord.Embed(
        title=f"🎉 Your {app_name.capitalize()} Download Link",
        description=(
            f"Thank you for verifying your subscription! ❤️\n\n"
            f"Click the button below to download your app:\n\n"
            f"[🔗 **Download {app_name.capitalize()}**]({app_link})\n\n"
            "Please confirm that everything is working fine.\n"
            "When you're done, press the **Close Ticket** button below."
        ),
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="App Distribution | Verified User")

    try:
        await user.send(embed=embed)
        await interaction.response.send_message(
            f"✅ Sent **{app_name.capitalize()}** link to {user.mention}", ephemeral=True
        )

        # Send in ticket channel as well
        view = CloseTicketButton(user)
        await interaction.channel.send(
            content=f"{user.mention}, here's your app link confirmation.",
            embed=embed,
            view=view
        )

    except discord.Forbidden:
        await interaction.response.send_message(f"⚠️ Can't DM {user.mention}.", ephemeral=True)


# ----------------------------------------------------------
# Admin Commands
# ----------------------------------------------------------
@bot.tree.command(name="remove_cooldown", description="Remove a user's cooldown (Admin only)")
@app_commands.describe(user="User to remove cooldown for")
async def remove_cooldown(interaction: discord.Interaction, user: discord.User):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return

    if user.id in cooldowns:
        del cooldowns[user.id]
        await interaction.response.send_message(f"✅ Cooldown removed for {user.mention}", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ {user.mention} has no cooldown.", ephemeral=True)


@bot.tree.command(name="view_tickets", description="View all open tickets (Admin only)")
async def view_tickets(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return

    if not tickets:
        await interaction.response.send_message("📭 No open tickets.", ephemeral=True)
    else:
        msg = "\n".join([f"<#{cid}> — <@{uid}>" for cid, uid in tickets.items()])
        await interaction.response.send_message(f"🎟️ **Open Tickets:**\n{msg}", ephemeral=True)


# ----------------------------------------------------------
# Close Ticket Button
# ----------------------------------------------------------
class CloseTicketButton(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You can't close this ticket.", ephemeral=True)
            return

        await interaction.response.send_message("🕒 This ticket will close in **5 seconds...**", ephemeral=True)
        await asyncio.sleep(5)

        transcript_file = await create_transcript(interaction.channel)
        file = discord.File(transcript_file, filename=f"transcript-{interaction.channel.name}.txt")

        log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🗂️ Transcript for `{interaction.channel.name}`", file=file)

        await interaction.channel.delete()


# ----------------------------------------------------------
# BOT READY
# ----------------------------------------------------------
@bot.event
async def on_ready():
    await asyncio.sleep(3)
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced globally.")
    except Exception as e:
        print(f"⚠️ Command sync error: {e}")
    print(f"🤖 Logged in as {bot.user}")

# ----------------------------------------------------------
# RUN
# ----------------------------------------------------------
threading.Thread(target=run_flask).start()
bot.run(TOKEN)
