import discord
from discord.ext import commands
from discord import app_commands
import os, json, datetime, asyncio
from flask import Flask
from threading import Thread

# ==========================
# CONFIG
# ==========================
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID"))
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL")

TICKET_BOOTH_CHANNEL_ID = 1431633723467501769
VERIFICATION_CHANNEL_ID = 1437035128802246697
TICKET_CATEGORY = "Tickets"
STAFF_ROLE = "Staff"
COOLDOWN_HOURS = 48

# ==========================
# BOT SETUP
# ==========================
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================
# DATA
# ==========================
user_cooldowns = {}
bot.ticket_app_requests = {}  # channel.id -> app_name

def load_apps():
    if not os.path.exists("apps.json"):
        with open("apps.json", "w") as f:
            json.dump([], f)
    with open("apps.json", "r") as f:
        return json.load(f)

def make_embed(title: str, desc: str, color=discord.Color.blurple()):
    embed = discord.Embed(title=title, description=desc, color=color)
    embed.set_footer(text="💎 RASH TECH | Premium Support")
    return embed

# ==========================
# TICKET CREATION LOGIC
# ==========================
async def create_ticket(interaction: discord.Interaction):
    user = interaction.user
    guild = interaction.guild
    now = datetime.datetime.utcnow()

    # Cooldown
    if user.id in user_cooldowns:
        diff = now - user_cooldowns[user.id]
        if diff.total_seconds() < COOLDOWN_HOURS * 3600:
            remaining = COOLDOWN_HOURS - (diff.total_seconds() / 3600)
            embed = make_embed(
                "⏳ Cooldown Active",
                f"You can create another ticket in **{int(remaining)} hours**.",
                discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

    # Check existing ticket
    existing = discord.utils.get(guild.channels, name=f"ticket-{user.name.lower()}")
    if existing:
        embed = make_embed("❗ Ticket Exists", "You already have an open ticket.", discord.Color.red())
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    # Category
    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY)
    if not category:
        category = await guild.create_category(TICKET_CATEGORY)

    staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }

    # Create channel
    channel = await guild.create_text_channel(
        name=f"ticket-{user.name}",
        category=category,
        overwrites=overwrites,
        topic=f"Ticket for {user.display_name}"
    )

    user_cooldowns[user.id] = now

    # Welcome embed
    await channel.send(embed=make_embed("🎉 Welcome!", f"Hey {user.mention}, our team will assist you soon.", discord.Color.green()))

    # Apps list
    apps_data = load_apps()
    app_list = "\n".join([f"💠 {a['name']}" for a in apps_data])
    if not app_list:
        app_list = "🎧 Spotify\n🏰 Castle\n🔥 Hotstar\n📞 Truecaller\n▶️ YouTube"
    await channel.send(embed=make_embed("💎 Available Apps", f"{app_list}\nType the app name to start verification.", discord.Color.gold()))

    # Log channel
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=make_embed("🆕 New Ticket", f"{user.mention} created {channel.mention}", discord.Color.blurple()))

    # Confirm to user
    await interaction.followup.send(embed=make_embed("✅ Ticket Created", f"Your ticket: {channel.mention}", discord.Color.green()), ephemeral=True)

# ==========================
# SLASH COMMANDS
# ==========================
@bot.tree.command(name="ticket", description="🎟️ Create a private ticket")
async def ticket(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await create_ticket(interaction)

@bot.tree.command(name="remove_cooldown", description="🛠️ Remove user's cooldown (Admin only)")
@app_commands.default_permissions(administrator=True)
async def remove_cooldown(interaction: discord.Interaction, user: discord.User):
    if user.id in user_cooldowns:
        del user_cooldowns[user.id]
        embed = make_embed("✅ Cooldown Removed", f"{user.mention} can now open a new ticket.", discord.Color.green())
    else:
        embed = make_embed("ℹ️ No Cooldown Found", f"{user.mention} had no active cooldown.", discord.Color.orange())
    await interaction.response.send_message(embed=embed)

# ==========================
# TICKET BOOTH BUTTON
# ==========================
class CreateTicketButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎟️ Create Ticket", style=discord.ButtonStyle.blurple, emoji="💎")
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await create_ticket(interaction)

async def send_ticket_booth():
    channel = bot.get_channel(TICKET_BOOTH_CHANNEL_ID)
    if not channel:
        print("⚠️ Ticket booth channel not found")
        return
    async for msg in channel.history(limit=20):
        if msg.author == bot.user:
            await msg.delete()
    embed = make_embed(
        "💎 Welcome to RASH TECH Premium Apps",
        f"🎉 Click the button below to create a ticket!\nSubscribe here: [RASH TECH]({YOUTUBE_CHANNEL_URL})",
        discord.Color.blurple()
    )
    view = CreateTicketButton()
    await channel.send(embed=embed, view=view)

# ==========================
# VERIFICATION + CLOSE TICKET
# ==========================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.channel.name.startswith("ticket-"):
        await bot.process_commands(message)
        return

    apps_data = load_apps()
    apps = [a["name"].lower() for a in apps_data]
    msg_lower = message.content.lower().strip()

    # User typed app name
    if msg_lower in apps:
        bot.ticket_app_requests[message.channel.id] = msg_lower
        verify_embed = make_embed(
            f"🧾 Verification Required for {msg_lower.capitalize()}",
            f"📢 Steps:\n1️⃣ Subscribe to our channel: [RASH TECH]({YOUTUBE_CHANNEL_URL})\n"
            "2️⃣ Take a screenshot.\n3️⃣ Upload it here in the ticket.\n\nOnce done, we'll verify it and send the app link.",
            discord.Color.orange()
        )
        await message.channel.send(embed=verify_embed)

    # Screenshot upload
    if message.attachments and message.channel.id in bot.ticket_app_requests:
        app_name = bot.ticket_app_requests[message.channel.id]
        screenshot_url = message.attachments[0].url

        # Send to verification channel
        verify_channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
        if verify_channel:
            embed = make_embed(
                f"🕵️ Verification Request – {app_name}",
                f"User: {message.author.mention}\nApp: {app_name}\nScreenshot below 👇",
                discord.Color.blurple()
            )
            embed.set_image(url=screenshot_url)

            class VerificationButtons(discord.ui.View):
                def __init__(self, user: discord.User, app_name: str):
                    super().__init__(timeout=None)
                    self.user = user
                    self.app_name = app_name

                @discord.ui.button(label="✅ VERIFY", style=discord.ButtonStyle.success)
                async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
                    app_data = next((a for a in apps_data if a["name"].lower() == self.app_name.lower()), None)
                    if not app_data:
                        await interaction.response.send_message(embed=make_embed("❌ Error", "App link not found.", discord.Color.red()), ephemeral=True)
                        return
                    try:
                        dm_embed = make_embed(f"🎁 {self.app_name} Premium Link", f"🔗 Link: {app_data['link']}\nEnjoy! 💎", discord.Color.green())
                        await self.user.send(embed=dm_embed)
                        await interaction.response.send_message(embed=make_embed("✅ Verified", f"{self.user.mention} link sent via DM."), ephemeral=True)
                        # Send close ticket button
                        view = CloseButton(self.user)
                        ticket_channel = discord.utils.get(interaction.guild.channels, name=f"ticket-{self.user.name.lower()}")
                        if ticket_channel:
                            await ticket_channel.send(embed=make_embed("🔒 Ticket", "If satisfied, close your ticket:", discord.Color.green()), view=view)
                    except:
                        await interaction.response.send_message(embed=make_embed("⚠️ Cannot DM", f"{self.user.mention} has DMs closed."), ephemeral=True)

                @discord.ui.button(label="❌ DECLINE", style=discord.ButtonStyle.danger)
                async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
                    await self.user.send(embed=make_embed("❌ Verification Failed", "Screenshot invalid. Upload correct subscription screenshot.", discord.Color.red()))
                    await interaction.response.send_message(embed=make_embed("Declined", "User notified."), ephemeral=True)

            view = VerificationButtons(message.author, app_name)
            await verify_channel.send(embed=embed, view=view)

        await message.channel.send(embed=make_embed("📤 Upload Received", "✅ Screenshot received. Please wait for verification.", discord.Color.green()))
        del bot.ticket_app_requests[message.channel.id]

    await bot.process_commands(message)

# ==========================
# CLOSE TICKET BUTTON
# ==========================
class ConfirmClose(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, user: discord.User):
        super().__init__(timeout=60)
        self.channel = channel
        self.user = user

    @discord.ui.button(label="✅ Yes, Close", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message(embed=make_embed("🚫 Not Your Ticket", "Only ticket creator can close."), ephemeral=True)
            return
        await interaction.response.send_message(embed=make_embed("⏳ Closing Ticket", "Ticket closing in 5 seconds..."))
        await asyncio.sleep(5)

        messages = [f"{m.author.display_name}: {m.content}" async for m in self.channel.history(limit=None, oldest_first=True)]
        transcript_text = "\n".join(messages)

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title=f"📜 Ticket Closed - {self.channel.name}",
                description=f"👤 User: {self.user.mention}\n🕒 Closed: <t:{int(datetime.datetime.utcnow().timestamp())}:R>\n\n💬 Transcript:\n```\n{transcript_text[:3900]}\n```",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_author(name=self.user.display_name, icon_url=self.user.display_avatar.url)
            embed.set_footer(text="💎 RASH TECH | Ticket Log")
            await log_channel.send(embed=embed)

        await self.channel.delete()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=make_embed("👍 Cancelled", "Ticket will remain open."), ephemeral=True)

class CloseButton(discord.ui.View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ConfirmClose(interaction.channel, self.user)
        await interaction.response.send_message(embed=make_embed("❔ Confirm", "Are you sure you want to close this ticket?"), view=view)

# ==========================
# FLASK KEEP-ALIVE
# ==========================
app = Flask(__name__)
@app.route('/')
def home():
    return "✅ RASH TECH Bot is alive!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    Thread(target=run_web).start()

# ==========================
# RUN BOT
# ==========================
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
