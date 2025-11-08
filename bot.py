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

# ------------------ ENV ------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID"))
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL")

# ------------------ LOAD APPS ------------------
def load_apps():
    with open("apps.json", "r") as f:
        return json.load(f)

apps_data = load_apps()

# ------------------ DISCORD ------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

cooldowns = {}
tickets = {}

# ------------------ FLASK KEEPALIVE ------------------
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ Bot web server running."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ------------------ HELPERS ------------------
def cooldown_expired(user_id: int):
    if user_id not in cooldowns:
        return True
    return (datetime.datetime.utcnow() - cooldowns[user_id]).total_seconds() >= 86400

async def create_transcript_embed(channel: discord.TextChannel, user: discord.User, created_at: datetime.datetime):
    messages = [msg async for msg in channel.history(limit=100, oldest_first=True)]
    transcript_text = ""
    for msg in messages:
        transcript_text += f"**{msg.author.display_name}:** {msg.content}\n"
    if len(transcript_text) > 4000:
        transcript_text = transcript_text[-4000:]
    closed_at = datetime.datetime.utcnow()
    duration = closed_at - created_at
    embed = discord.Embed(
        title=f"📜 Ticket Transcript — {channel.name}",
        color=discord.Color.gold(),
        timestamp=closed_at
    )
    embed.add_field(name="👤 Ticket Owner", value=f"{user.mention}", inline=False)
    embed.add_field(name="🕒 Opened", value=created_at.strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    embed.add_field(name="🔒 Closed", value=closed_at.strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    embed.add_field(name="💬 Transcript", value=transcript_text or "_(No messages found)_", inline=False)
    embed.set_footer(text="Ticket archived | Support Bot")
    return embed

async def auto_close_ticket(channel: discord.TextChannel):
    while True:
        await asyncio.sleep(60)
        if channel.id not in tickets:
            return
        info = tickets[channel.id]
        last_active = info.get("last_active", info["created_at"])
        elapsed = (datetime.datetime.utcnow() - last_active).total_seconds()
        if elapsed >= 600:  # 10 minutes inactivity
            user = channel.guild.get_member(info["user_id"])
            await channel.send("⚠️ This ticket has been inactive for 10 minutes. Closing in 5 seconds...")
            await asyncio.sleep(5)
            embed_transcript = await create_transcript_embed(channel, user, info["created_at"])
            log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=embed_transcript)
            tickets.pop(channel.id, None)
            await channel.delete()
            return

# ------------------ COMMANDS ------------------
@bot.tree.command(name="ticket", description="Create a new support ticket.")
async def ticket(interaction: discord.Interaction):
    user = interaction.user
    if not cooldown_expired(user.id):
        remaining = 86400 - (datetime.datetime.utcnow() - cooldowns[user.id]).total_seconds()
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        await interaction.response.send_message(f"⏳ You can create another ticket in **{hours}h {mins}m**.", ephemeral=True)
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
    tickets[channel.id] = {"user_id": user.id, "created_at": datetime.datetime.utcnow(), "last_active": datetime.datetime.utcnow()}

    embed = discord.Embed(
        title="💫✨ Premium App Ticket Created ✨💫",
        description=(
            f"Hello {user.mention}! 👋\n\n"
            "Welcome to your **personal ticket**.\n\n"
            "**Available Premium Apps:**\n"
            "💠 Spotify\n💠 YouTube\n💠 Kinemaster\n💠 Hotstar\n💠 Truecaller\n💠 Castle\n\n"
            "➡️ Type the **name** of the app you want below to start verification."
        ),
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="Ticket Support | Powered by Your Server")
    await channel.send(content=f"{user.mention}", embed=embed)
    await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)
    asyncio.create_task(auto_close_ticket(channel))

# ------------------ MESSAGE HANDLER ------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.channel.id in tickets:
        tickets[message.channel.id]["last_active"] = datetime.datetime.utcnow()
        msg_content = message.content.lower()
        for app_name in apps_data.keys():
            if app_name.lower() in msg_content:
                embed = discord.Embed(
                    title="💫✨ Premium App Verification ✨💫",
                    description=(
                        f"You're requesting **{app_name.capitalize()}**!\n\n"
                        "Please complete the steps below:\n\n"
                        "[✅] Step 1: Subscribe to our YouTube Channel\n"
                        "[⏳] Step 2: Upload screenshot in this ticket\n"
                        "[❌] Step 3: App delivery upon verification\n\n"
                        f"📌 [Subscribe here]({YOUTUBE_CHANNEL_URL})"
                    ),
                    color=discord.Color.blurple(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_footer(text=f"Verification | Ticket by {message.author.display_name}")
                await message.channel.send(embed=embed)
                break
    await bot.process_commands(message)

# ------------------ SEND APP ------------------
@bot.tree.command(name="send_app", description="Send app link to a verified user (Admin only)")
@app_commands.describe(user="User", app_name="App name")
async def send_app(interaction: discord.Interaction, user: discord.User, app_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    app_key = app_name.lower()
    if app_key not in apps_data:
        await interaction.response.send_message(f"❌ `{app_name}` not found.", ephemeral=True)
        return
    app_link = apps_data[app_key]
    embed = discord.Embed(
        title=f"🎉 {app_name.capitalize()} Download Link",
        description=f"[🔗 Download {app_name.capitalize()}]({app_link})\n\nClose your ticket when done.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="App Distribution | Verified User")
    view = CloseTicketButton(user)
    await interaction.channel.send(content=f"{user.mention}, your app link is ready!", embed=embed, view=view)
    await interaction.response.send_message(f"✅ Sent {app_name.capitalize()} link to {user.mention}", ephemeral=True)

# ------------------ ADMIN TOOLS ------------------
@bot.tree.command(name="remove_cooldown", description="Remove a user's cooldown (Admin only)")
@app_commands.describe(user="User")
async def remove_cooldown(interaction: discord.Interaction, user: discord.User):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    cooldowns.pop(user.id, None)
    await interaction.response.send_message(f"✅ Cooldown removed for {user.mention}", ephemeral=True)

@bot.tree.command(name="view_tickets", description="View open tickets (Admin only)")
async def view_tickets(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    if not tickets:
        await interaction.response.send_message("📭 No open tickets.", ephemeral=True)
    else:
        msg = "\n".join([f"<#{cid}> — <@{info['user_id']}>" for cid, info in tickets.items()])
        await interaction.response.send_message(f"🎟️ Open Tickets:\n{msg}", ephemeral=True)

@bot.tree.command(name="ticket_stats", description="View ticket statistics (Admin only)")
async def ticket_stats(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    total_open = len(tickets)
    total_users = len(set(info['user_id'] for info in tickets.values()))
    await interaction.response.send_message(f"📊 Ticket Stats:\nOpen: {total_open}\nUsers: {total_users}", ephemeral=True)

# ------------------ FORCE CLOSE (With Confirmation) ------------------
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
        info = tickets.pop(self.channel.id, None)
        if info:
            user = self.channel.guild.get_member(info["user_id"])
            embed_transcript = await create_transcript_embed(self.channel, user, info["created_at"])
            log_channel = self.channel.guild.get_channel(TICKET_LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=embed_transcript)
        await self.channel.delete()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Only the admin who issued the command can cancel.", ephemeral=True)
            return
        await interaction.response.send_message("✅ Force-close canceled.", ephemeral=True)
        self.stop()

@bot.tree.command(name="force_close", description="Force close the current or mentioned ticket (Admin only)")
@app_commands.describe(channel="(Optional) Ticket channel to close")
async def force_close(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    channel = channel or interaction.channel
    if channel.id not in tickets:
        await interaction.response.send_message("⚠️ This is not a valid ticket channel.", ephemeral=True)
        return
    embed = discord.Embed(
        title="⚠️ Confirm Ticket Closure",
        description=f"Are you sure you want to **force close** `{channel.name}`?\n\nThis will delete the channel and archive the transcript to the ticket log.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="Admin Confirmation Required | Auto-cancels in 30s")
    view = ConfirmForceCloseView(channel, interaction.user)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ------------------ CLOSE BUTTON ------------------
class CloseTicketButton(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You can't close this ticket.", ephemeral=True)
            return
        await interaction.response.send_message("🕒 Closing ticket in 5 seconds...", ephemeral=True)
        await asyncio.sleep(5)
        info = tickets.pop(interaction.channel.id, None)
        user = interaction.guild.get_member(info["user_id"]) if info else interaction.user
        created_at = info["created_at"] if info else datetime.datetime.utcnow()
        embed_transcript = await create_transcript_embed(interaction.channel, user, created_at)
        log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=embed_transcript)
        await interaction.channel.delete()

# ------------------ READY ------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"🤖 Logged in as {bot.user}")
    print("✅ Slash commands synced.")

# ------------------ RUN ------------------
threading.Thread(target=run_flask).start()
bot.run(TOKEN)
