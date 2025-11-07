import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
import io
from flask import Flask
import threading

TOKEN = "MTQzMjQ1MDc0NDQwNTE5Njg3Mw.GS1h8f.mvYdecGxfsjN301l1g1N-g8WBY9hwoR5qL_-_g"
GUILD_ID = 1424815111541096530  # Replace with your Discord server ID
TICKET_LOG_CHANNEL_ID = 1434241829733404692  # Replace with the ticket log channel ID

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

cooldowns = {}
tickets = {}

# Flask server to keep bot alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ---- Utility ----
def cooldown_expired(user_id):
    if user_id not in cooldowns:
        return True
    return (datetime.datetime.utcnow() - cooldowns[user_id]).total_seconds() >= 86400

# ---- Ticket Command ----
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
            "Here are the list of premium apps we are currently providing:\n"
            "• Spotify\n• YouTube\n• Kinemaster\n• Hotstar\n• Truecaller\n• Castle\n\n"
            "_More apps will come soon!_"
        ),
        color=discord.Color.green()
    )

    await channel.send(content=f"{user.mention}", embed=embed)
    await interaction.response.send_message(f"✅ Your ticket has been created: {channel.mention}", ephemeral=True)

# ---- Message Listener ----
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id in tickets:
        apps = ["spotify", "youtube", "kinemaster", "hotstar", "truecaller", "castle"]
        msg_content = message.content.lower()
        for app in apps:
            if app in msg_content:
                embed = discord.Embed(
                    title="✅ Verification Required",
                    description=(
                        "You have to first **verify** to get your app.\n\n"
                        "**Step 1:** Subscribe to our channel.\n"
                        "**Step 2:** Send a screenshot here for verification.\n\n"
                        "Once verified, you'll get your download link!"
                    ),
                    color=discord.Color.blue()
                )
                await message.channel.send(embed=embed)
                break

# ---- Close Ticket Button ----
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

# ---- Admin Commands ----
@bot.tree.command(name="remove_cooldown", description="Remove cooldown for a user (Admin only).")
@app_commands.describe(user="User to remove cooldown for")
async def remove_cooldown(interaction: discord.Interaction, user: discord.User):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)
        return

    if user.id in cooldowns:
        del cooldowns[user.id]
        await interaction.response.send_message(f"✅ Cooldown removed for {user.mention}", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ {user.mention} has no cooldown.", ephemeral=True)

@bot.tree.command(name="view_tickets", description="View all open tickets (Admin only).")
async def view_tickets(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)
        return

    if not tickets:
        await interaction.response.send_message("📭 No open tickets right now.", ephemeral=True)
    else:
        msg = "\n".join([f"<#{ch}> — <@{uid}>" for ch, uid in tickets.items()])
        await interaction.response.send_message(f"🎟️ **Open Tickets:**\n{msg}", ephemeral=True)

# ---- Bot Events ----
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print("✅ Slash commands synced.")

# Start Flask in background
threading.Thread(target=run_flask).start()

bot.run(TOKEN)
