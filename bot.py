import os
import json
import asyncio
import datetime
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


async def create_transcript_embed(channel: discord.TextChannel, user: discord.User, created_at: datetime.datetime):
    """Return a beautiful Discord Embed transcript summary."""
    messages = [msg async for msg in channel.history(limit=100, oldest_first=True)]
    total_messages = len(messages)

    transcript_text = ""
    for msg in messages:
        clean = msg.content.replace("`", "'")
        transcript_text += f"**{msg.author.display_name}:** {clean}\n"

    if len(transcript_text) > 4000:
        transcript_text = transcript_text[-4000:]  # keep last 4000 chars

    closed_at = datetime.datetime.utcnow()
    duration = closed_at - created_at
    duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))

    embed = discord.Embed(
        title=f"📜 Ticket Transcript — {channel.name}",
        color=discord.Color.gold(),
        timestamp=closed_at
    )
    embed.add_field(
        name="👤 Ticket Owner",
        value=f"{user.mention}\n(ID: `{user.id}`)",
        inline=False
    )
    embed.add_field(
        name="🕒 Opened",
        value=created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
        inline=True
    )
    embed.add_field(
        name="🔒 Closed",
        value=closed_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
        inline=True
    )
    embed.add_field(
        name="💬 Messages",
        value=f"{total_messages} total messages",
        inline=True
    )
    embed.add_field(
        name="🧾 Conversation Summary",
        value=transcript_text or "_(No messages found)_",
        inline=False
    )
    embed.set_footer(text=f"Ticket Duration: {duration_str} | Powered by Your Server")
    return embed


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
    tickets[channel.id] = {
        "user_id": user.id,
        "created_at": datetime.datetime.utcnow()
    }

    embed = discord.Embed(
        title="🎟️ Welcome to Your Ticket!",
        description=(
            f"Hello {user.mention}! 👋\n\n"
            "Welcome to your personal support ticket.\n"
            "Here’s what we currently offer:\n\n"
            "💠 **Spotify**\n"
            "💠 **YouTube**\n"
            "💠 **Kinemaster**\n"
            "💠 **Hotstar**\n"
            "💠 **Truecaller**\n"
            "💠 **Castle**\n\n"
            "_More premium apps are coming soon!_\n\n"
            "👉 Please type the **name** of the app you want below."
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
# /send_app Command
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
            f"Click below to download your app:\n\n"
            f"[🔗 **Download {app_name.capitalize()}**]({app_link})\n\n"
            "When you're done, please close the ticket using the button below."
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

        view = CloseTicketButton(user)
        await interaction.channel.send(
            content=f"{user.mention}, here’s your verified app link!",
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
        msg = "\n".join([f"<#{cid}> — <@{info['user_id']}>" for cid, info in tickets.items()])
        await interaction.response.send_message(f"🎟️ **Open Tickets:**\n{msg}", ephemeral=True)


# ----------------------------------------------------------
# Close Ticket Button (Enhanced Transcript)
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

        info = tickets.pop(interaction.channel.id, None)
        if info:
            user = interaction.guild.get_member(info["user_id"])
            created_at = info["created_at"]
        else:
            user = interaction.user
            created_at = datetime.datetime.utcnow()

        embed_transcript = await create_transcript_embed(interaction.channel, user, created_at)
        log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=embed_transcript)

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
