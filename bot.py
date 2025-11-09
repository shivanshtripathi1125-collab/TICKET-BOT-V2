import discord
from discord.ext import commands
from discord import app_commands, ui
import os, json, asyncio, datetime
from flask import Flask
from threading import Thread

# -----------------------------
# Environment Variables
# -----------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 1424815111541096530))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID", 1434241829733404692))
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL", "https://www.youtube.com/@RASH-TECH")

# -----------------------------
# Fixed IDs
# -----------------------------
TICKET_COUNTER_CHANNEL_ID = 1431633723467501769
VERIFICATION_CHANNEL_ID = 1437035128802246697
STAFF_ROLE_NAME = "Staff"

# -----------------------------
# Load apps
# -----------------------------
with open("apps.json") as f:
    apps = json.load(f)

# -----------------------------
# Load cooldowns
# -----------------------------
COOLDOWN_FILE = "cooldowns.json"
if os.path.exists(COOLDOWN_FILE):
    with open(COOLDOWN_FILE) as f:
        cooldowns = json.load(f)
else:
    cooldowns = {}

def save_cooldowns():
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(cooldowns, f)

# -----------------------------
# Bot Setup
# -----------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

# -----------------------------
# Flask Heartbeat
# -----------------------------
app = Flask("")

@app.route("/")
def home():
    return "RASH TECH Bot is running ✅"

def run():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run).start()

# -----------------------------
# Ticket Close Button
# -----------------------------
class CloseTicketView(ui.View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel

    @ui.button(label="Close Ticket", style=discord.ButtonStyle.red)
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(embed=discord.Embed(
            description="Ticket will close in 5 seconds ⏱️",
            color=discord.Color.red()
        ))
        await asyncio.sleep(5)
        messages = await self.ticket_channel.history(limit=None, oldest_first=True).flatten()
        transcript = "\n".join([f"{m.author}: {m.content}" for m in messages])
        log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
        await log_channel.send(f"Transcript for ticket {self.ticket_channel.name}:\n```{transcript}```")
        await self.ticket_channel.delete()

# -----------------------------
# Verification Buttons
# -----------------------------
class VerificationView(ui.View):
    def __init__(self, ticket_channel, user, app_name, attachment_url):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.user = user
        self.app_name = app_name
        self.attachment_url = attachment_url

    @ui.button(label="✅ Verify", style=discord.ButtonStyle.green)
    async def verify(self, interaction: discord.Interaction, button: ui.Button):
        app_link = apps.get(self.app_name)
        if not app_link:
            await interaction.response.send_message("App link not found.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Verification Approved ✅",
            description=f"{self.user.mention}, your verification is approved.\nHere is your link: {app_link}",
            color=discord.Color.green()
        )
        await self.ticket_channel.send(embed=embed, view=CloseTicketView(self.ticket_channel))
        try:
            await self.user.send(f"Here is your link for **{self.app_name}**: {app_link}")
        except:
            await self.ticket_channel.send(f"{self.user.mention}, I couldn't DM you. Please check your privacy settings.")
        await interaction.response.send_message("User verified successfully!", ephemeral=True)

    @ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: ui.Button):
        await self.ticket_channel.send(embed=discord.Embed(
            description=f"Sorry {self.user.mention}, your verification for {self.app_name} was declined.",
            color=discord.Color.red()
        ))
        await interaction.response.send_message("Verification declined.", ephemeral=True)

# -----------------------------
# Ready Event
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(e)

# -----------------------------
# /ticket command
# -----------------------------
@bot.tree.command(name="ticket", description="Create a support ticket")
async def ticket(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = datetime.datetime.utcnow()
    last_ticket = cooldowns.get(user_id)
    if last_ticket:
        last_time = datetime.datetime.fromisoformat(last_ticket)
        delta = (now - last_time).total_seconds()
        if delta < 48*3600:
            remaining = 48*3600 - delta
            hours = int(remaining//3600)
            minutes = int((remaining%3600)//60)
            await interaction.response.send_message(embed=discord.Embed(
                title="⏳ Cooldown Active",
                description=f"You can create a new ticket in **{hours}h {minutes}m**.",
                color=discord.Color.orange()
            ), ephemeral=True)
            return

    guild = bot.get_guild(GUILD_ID)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        discord.utils.get(guild.roles, name=STAFF_ROLE_NAME): discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    ticket_channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)
    cooldowns[user_id] = now.isoformat()
    save_cooldowns()

    embed = discord.Embed(
        title=f"Welcome to RASH TECH, {interaction.user.name} 🎉",
        description=f"Thanks for creating a ticket! Here are the apps we currently provide:\n\n" +
                    "\n".join([f"- {a}" for a in apps.keys()]) +
                    f"\n\nTo get an app link, type the app name (case-insensitive).\n"
                    f"**Verification Required:** Subscribe to our YouTube channel: {YOUTUBE_CHANNEL_URL} and upload the screenshot here.",
        color=discord.Color.blue()
    )
    await ticket_channel.send(embed=embed)
    await interaction.response.send_message(f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

# -----------------------------
# Message Handler
# -----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Only handle ticket channels
    if str(message.channel.name).startswith("ticket-"):
        content_lower = message.content.lower()
        for app_name in apps.keys():
            if app_name.lower() in content_lower:
                # Check for attachment (screenshot)
                if message.attachments:
                    for attachment in message.attachments:
                        ver_channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
                        embed = discord.Embed(
                            title="New Verification Pending ⚡",
                            description=f"{message.author} requested verification for **{app_name}**.\nScreenshot attached below.",
                            color=discord.Color.yellow()
                        )
                        embed.set_image(url=attachment.url)
                        await ver_channel.send(embed=embed, view=VerificationView(message.channel, message.author, app_name, attachment.url))
                        await message.channel.send(embed=discord.Embed(
                            description="Upload successful! Please wait until an admin verifies it.",
                            color=discord.Color.green()
                        ))
                else:
                    await message.channel.send(embed=discord.Embed(
                        description=f"To get the link for **{app_name}**, please complete verification and upload the screenshot of your subscription.",
                        color=discord.Color.orange()
                    ))
                return

# -----------------------------
# /remove_cooldown
# -----------------------------
@bot.tree.command(name="remove_cooldown", description="Remove cooldown for a user")
@app_commands.describe(user="User to remove cooldown for")
async def remove_cooldown(interaction: discord.Interaction, user: discord.User):
    if not discord.utils.get(interaction.user.roles, name=STAFF_ROLE_NAME):
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
        return
    cooldowns.pop(str(user.id), None)
    save_cooldowns()
    await interaction.response.send_message(f"Cooldown removed for {user.mention}", ephemeral=True)

# -----------------------------
# /force_close
# -----------------------------
@bot.tree.command(name="force_close", description="Force close a ticket")
@app_commands.describe(channel="Ticket channel to close")
async def force_close(interaction: discord.Interaction, channel: discord.TextChannel):
    if not discord.utils.get(interaction.user.roles, name=STAFF_ROLE_NAME):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    messages = await channel.history(limit=None, oldest_first=True).flatten()
    transcript = "\n".join([f"{m.author}: {m.content}" for m in messages])
    log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
    await log_channel.send(f"Transcript for ticket {channel.name}:\n```{transcript}```")
    await channel.delete()
    await interaction.response.send_message(f"Ticket {channel.name} closed successfully.", ephemeral=True)

# -----------------------------
# Run Bot
# -----------------------------
bot.run(TOKEN)
