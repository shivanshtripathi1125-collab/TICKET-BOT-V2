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
# Fixed Channel & Role IDs
# -----------------------------
TICKET_COUNTER_CHANNEL_ID = 1431633723467501769
VERIFICATION_CHANNEL_ID = 1437035128802246697
STAFF_ROLE_NAME = "Staff"

# -----------------------------
# Load Apps
# -----------------------------
with open("apps.json") as f:
    apps = json.load(f)

# -----------------------------
# Load Cooldowns (Persistent)
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
# Flask Heartbeat (Render/Heroku)
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
            description="🔒 Ticket will close in **5 seconds**...",
            color=discord.Color.red()
        ))
        await asyncio.sleep(5)
        messages = await self.ticket_channel.history(limit=None, oldest_first=True).flatten()
        transcript = "\n".join([f"{m.author}: {m.content}" for m in messages if m.content])
        log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
        await log_channel.send(f"📜 Transcript for **{self.ticket_channel.name}**:\n```{transcript}```")
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
            await interaction.response.send_message("⚠️ App link not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Verification Approved ✅",
            description=f"{self.user.mention}, your verification is approved!\n\n**Here is your link:** {app_link}",
            color=discord.Color.green()
        )
        await self.ticket_channel.send(embed=embed, view=CloseTicketView(self.ticket_channel))
        try:
            await self.user.send(f"🎉 Here is your link for **{self.app_name}**:\n{app_link}")
        except:
            await self.ticket_channel.send(f"⚠️ {self.user.mention}, I couldn’t DM you. Please check your privacy settings.")
        await interaction.response.send_message("✅ Verification completed.", ephemeral=True)

    @ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: ui.Button):
        await self.ticket_channel.send(embed=discord.Embed(
            description=f"❌ Sorry {self.user.mention}, your verification for **{self.app_name}** was declined by staff.",
            color=discord.Color.red()
        ))
        await interaction.response.send_message("Declined successfully.", ephemeral=True)

# -----------------------------
# Bot Ready Event
# -----------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔁 Synced {len(synced)} commands.")
    except Exception as e:
        print("❌ Sync failed:", e)

# -----------------------------
# /ticket Command
# -----------------------------
@bot.tree.command(name="ticket", description="🎫 Create a support ticket")
async def ticket(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = datetime.datetime.utcnow()

    last_ticket = cooldowns.get(user_id)
    if last_ticket:
        last_time = datetime.datetime.fromisoformat(last_ticket)
        delta = (now - last_time).total_seconds()
        if delta < 48 * 3600:
            remaining = 48 * 3600 - delta
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
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
        title=f"🎟️ Welcome to RASH TECH, {interaction.user.name}!",
        description=(
            "Thank you for creating a ticket!\n\n"
            "📱 **Here are the premium apps we currently provide:**\n"
            + "\n".join([f"• {a}" for a in apps.keys()]) +
            f"\n\n📋 **To get an app link:**\n1️⃣ Type the app name (e.g., `Spotify`)\n"
            f"2️⃣ Subscribe to our YouTube: {YOUTUBE_CHANNEL_URL}\n"
            "3️⃣ Take a screenshot of your subscription and upload it here."
        ),
        color=discord.Color.blurple()
    )
    await ticket_channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

# -----------------------------
# Message Listener (Case-Insensitive App Detection)
# -----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if str(message.channel.name).startswith("ticket-"):
        content_lower = message.content.lower()

        for app_name, link in apps.items():
            if app_name.lower() in content_lower:
                # If screenshot provided
                if message.attachments:
                    for attachment in message.attachments:
                        ver_channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
                        embed = discord.Embed(
                            title="🕵️ New Verification Request",
                            description=(
                                f"👤 **User:** {message.author}\n"
                                f"📦 **App:** {app_name}\n\nScreenshot below ⬇️"
                            ),
                            color=discord.Color.yellow()
                        )
                        embed.set_image(url=attachment.url)
                        await ver_channel.send(embed=embed, view=VerificationView(message.channel, message.author, app_name, attachment.url))
                        await message.channel.send(embed=discord.Embed(
                            description="✅ Screenshot uploaded successfully! Please wait for admin verification.",
                            color=discord.Color.green()
                        ))
                else:
                    await message.channel.send(embed=discord.Embed(
                        description=f"📸 Please upload a screenshot showing you subscribed to our YouTube for **{app_name}**.",
                        color=discord.Color.orange()
                    ))
                return

# -----------------------------
# /remove_cooldown Command
# -----------------------------
@bot.tree.command(name="remove_cooldown", description="🧹 Remove a user's ticket cooldown")
@app_commands.describe(user="User to remove cooldown for")
async def remove_cooldown(interaction: discord.Interaction, user: discord.User):
    if not discord.utils.get(interaction.user.roles, name=STAFF_ROLE_NAME):
        await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)
        return
    cooldowns.pop(str(user.id), None)
    save_cooldowns()
    await interaction.response.send_message(f"✅ Cooldown removed for {user.mention}.", ephemeral=True)

# -----------------------------
# /force_close Command
# -----------------------------
@bot.tree.command(name="force_close", description="🔒 Force close a ticket manually")
@app_commands.describe(channel="Ticket channel to close")
async def force_close(interaction: discord.Interaction, channel: discord.TextChannel):
    if not discord.utils.get(interaction.user.roles, name=STAFF_ROLE_NAME):
        await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)
        return
    messages = await channel.history(limit=None, oldest_first=True).flatten()
    transcript = "\n".join([f"{m.author}: {m.content}" for m in messages if m.content])
    log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
    await log_channel.send(f"🧾 Transcript for {channel.name}:\n```{transcript}```")
    await channel.delete()
    await interaction.response.send_message(f"✅ Ticket **{channel.name}** closed successfully.", ephemeral=True)

# -----------------------------
# Run Bot
# -----------------------------
bot.run(TOKEN)
