import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import json, os, io, pytesseract
from PIL import Image
from datetime import datetime, timedelta
from flask import Flask
import threading

# ====== ENVIRONMENT VARIABLES ======
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

# ====== HARDCODED VALUES ======
TICKET_CATEGORY_ID = 1434241829733404692
TICKET_LOG_CHANNEL_ID = 1434863996787495016
TICKET_COMMAND_CHANNEL_ID = 1431633723467501769
YOUTUBE_URL = "https://youtube.com/@RashTech"

# ====== BOT SETUP ======
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

cooldowns = {}
apps_file = "apps.json"

# ====== HELPERS ======
def load_apps():
    if not os.path.exists(apps_file):
        with open(apps_file, "w") as f:
            json.dump({}, f)
    with open(apps_file, "r") as f:
        return json.load(f)

def save_apps(data):
    with open(apps_file, "w") as f:
        json.dump(data, f, indent=4)

def create_embed(title, description, color=0x2b2d31):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="Rash Tech • Premium App System", icon_url="https://i.imgur.com/ZLJYp9J.png")
    embed.timestamp = datetime.utcnow()
    return embed

# ====== TICKET CREATION FUNCTION ======
async def create_ticket_channel(user: discord.Member, guild: discord.Guild):
    now = datetime.utcnow()
    if user.id in cooldowns and now - cooldowns[user.id] < timedelta(hours=24):
        return None, "⏳ You can only create one ticket every 24 hours."

    cooldowns[user.id] = now
    category = guild.get_channel(TICKET_CATEGORY_ID)
    channel = await category.create_text_channel(
        name=f"ticket-{user.name}",
        topic=f"user_id:{user.id}",
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
    )

    # Welcome & verification messages
    await channel.send(embed=create_embed(
        "🎉 Welcome to Your Ticket!",
        f"Hey {user.mention}, welcome!\nHere are the premium apps we currently provide:\n\n"
        "• Spotify\n• YouTube\n• Kinemaster\n• Hotstar\n• Truecaller\n• Castle\n\n"
        "Type the name of any app to begin verification."
    ))

    await channel.send(embed=create_embed(
        "🔐 Verification Required",
        f"Please **subscribe** to our YouTube channel first:\n[{YOUTUBE_URL}]({YOUTUBE_URL})\n\n"
        "After subscribing, send a **screenshot** in this ticket. Once verified, you'll get your app link."
    ))

    return channel, None

# ====== SATISFACTION VIEW ======
class SatisfactionView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="✅ Satisfied", style=discord.ButtonStyle.green)
    async def satisfied(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("You’re not the ticket owner!", ephemeral=True)
        await handle_ticket_close(interaction.channel, interaction.user, True)

    @discord.ui.button(label="❌ Not Satisfied", style=discord.ButtonStyle.red)
    async def not_satisfied(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("You’re not the ticket owner!", ephemeral=True)
        await handle_ticket_close(interaction.channel, interaction.user, False)

# ====== OCR VERIFICATION ======
async def process_verification_image(message):
    if not message.attachments:
        return
    attachment = message.attachments[0]
    image_bytes = await attachment.read()
    image = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(image).lower()

    if "rash tech" in text and "subscribed" in text:
        apps = load_apps()
        user_id = int(message.channel.topic.split(":")[1])
        user = message.guild.get_member(user_id)
        await message.channel.send(embed=create_embed(
            "✅ Verification Complete",
            f"{user.mention}, verification successful!\nHere’s your app download link 👇",
            0x00ff99
        ))
        if apps:
            app_name, app_link = list(apps.items())[0]
            await message.channel.send(embed=create_embed(f"🎁 {app_name} Download Link", app_link, 0x00ff99))
        await message.channel.send(embed=create_embed(
            "💬 Feedback Time",
            "If you're satisfied with your app, please choose below:",
            0x7289da
        ), view=SatisfactionView(user.id))
    else:
        await message.channel.send(embed=create_embed(
            "❌ Invalid Screenshot",
            "Your screenshot doesn’t show **RASH TECH** or **Subscribed**. Please try again.",
            0xff0000
        ))

# ====== TRANSCRIPT FUNCTION ======
async def handle_ticket_close(channel, closed_by, satisfied):
    user_id = int(channel.topic.split(":")[1])
    user = channel.guild.get_member(user_id)

    messages = [msg async for msg in channel.history(limit=50, oldest_first=True)]
    transcript_lines = []
    for msg in messages:
        transcript_lines.append(f"[{msg.created_at.strftime('%H:%M:%S')}] {msg.author}: {msg.content}")

    embed = discord.Embed(
        title="🎟️ Ticket Closed",
        description=(
            f"**Opened By:** {user.mention}\n"
            f"**Closed By:** {closed_by.mention}\n"
            f"**Satisfied:** {'✅ Yes' if satisfied else '❌ No'}\n"
            f"**Opened:** {messages[0].created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"**Closed:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            f"**Last Messages:**\n```{chr(10).join(transcript_lines[-30:])}```"
        ),
        color=0xffcc00
    )

    log_channel = channel.guild.get_channel(TICKET_LOG_CHANNEL_ID)
    await log_channel.send(embed=embed)

    await channel.send("⏳ Ticket will close in **5 seconds**...")
    await discord.utils.sleep_until(datetime.utcnow() + timedelta(seconds=5))
    await channel.delete()

# ====== CREATE TICKET BUTTON VIEW ======
class CreateTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Create Ticket", style=discord.ButtonStyle.blurple, emoji="✅")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, error = await create_ticket_channel(interaction.user, interaction.guild)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)
        await interaction.response.send_message(f"🎟️ Ticket created: {channel.mention}", ephemeral=True)

# ====== BOT EVENTS ======
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    guild = discord.Object(id=GUILD_ID)
    await tree.sync(guild=guild)

    # Delete old panel message and resend
    channel = bot.get_channel(TICKET_COMMAND_CHANNEL_ID)
    async for msg in channel.history(limit=10):
        if msg.author == bot.user:
            await msg.delete()
    await channel.send(
        embed=create_embed("🎟️ Premium App Tickets", "To get a premium app, please create a ticket below."),
        view=CreateTicketView()
    )

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if isinstance(message.channel, discord.TextChannel) and message.channel.category_id == TICKET_CATEGORY_ID:
        await process_verification_image(message)
    await bot.process_commands(message)

# ====== COMMANDS ======
@tree.command(name="ticket", description="Create a new ticket")
async def ticket_command(interaction: discord.Interaction):
    channel, error = await create_ticket_channel(interaction.user, interaction.guild)
    if error:
        return await interaction.response.send_message(error, ephemeral=True)
    await interaction.response.send_message(f"🎟️ Ticket created: {channel.mention}", ephemeral=True)

@tree.command(name="add_app", description="Add a new premium app.")
@app_commands.describe(app_name="App name", app_link="App link")
async def add_app(interaction: discord.Interaction, app_name: str, app_link: str):
    apps = load_apps()
    apps[app_name] = app_link
    save_apps(apps)
    await interaction.response.send_message(embed=create_embed("✅ App Added", f"{app_name} has been added successfully!"))

@tree.command(name="send_app", description="Send an app link manually.")
@app_commands.describe(user="User to send app", app_name="App name")
async def send_app(interaction: discord.Interaction, user: discord.Member, app_name: str):
    apps = load_apps()
    app = apps.get(app_name)
    if not app:
        await interaction.response.send_message(embed=create_embed("⚠️ Not Found", f"No app named **{app_name}** found."))
        return
    await interaction.response.send_message(embed=create_embed("📦 Sent", f"App **{app_name}** sent to {user.mention}."))
    await user.send(embed=create_embed(f"🎁 {app_name} Download Link", app, 0x00ff99))

@tree.command(name="force_close", description="Force close a ticket.")
async def force_close(interaction: discord.Interaction):
    if not interaction.channel.category_id == TICKET_CATEGORY_ID:
        await interaction.response.send_message("❌ This isn’t a ticket channel.", ephemeral=True)
        return
    await handle_ticket_close(interaction.channel, interaction.user, satisfied=False)
    await interaction.response.send_message("🛑 Ticket closed.", ephemeral=True)

@tree.command(name="remove_cooldown", description="Remove 24h ticket cooldown for a user (admin only).")
@app_commands.describe(user="User to remove cooldown for")
async def remove_cooldown(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
        return

    if user.id in cooldowns:
        del cooldowns[user.id]
        await interaction.response.send_message(embed=create_embed("✅ Cooldown Removed", f"{user.mention} can now create a ticket immediately."))
    else:
        await interaction.response.send_message(embed=create_embed("ℹ️ No Cooldown", f"{user.mention} does not have any active cooldown."))

# ====== FLASK KEEPALIVE ======
app = Flask('')

@app.route('/')
def home():
    return "Rash Tech Ticket Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask).start()

# ====== RUN BOT ======
bot.run(TOKEN)
