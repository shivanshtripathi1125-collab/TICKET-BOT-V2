import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import os
import json
import datetime
import asyncio
from flask import Flask
from threading import Thread

# ---------------------------
# Environment Variables
# ---------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID"))
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL")
VERIFICATION_CHANNEL_ID = int(os.getenv("VERIFICATION_CHANNEL_ID"))

# ---------------------------
# Load / Save Apps
# ---------------------------
def load_apps():
    with open("apps.json", "r") as f:
        return json.load(f)

def save_apps(apps):
    with open("apps.json", "w") as f:
        json.dump(apps, f, indent=4)

apps = load_apps()

# ---------------------------
# Flask Keepalive Server
# ---------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ---------------------------
# Bot Setup
# ---------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

cooldowns = {}  # 48-hour ticket cooldowns


# =============================
# VERIFICATION BUTTON VIEW
# =============================
class VerificationView(View):
    def __init__(self, ticket_channel, user, app_name, screenshot_url):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.user = user
        self.app_name = app_name
        self.screenshot_url = screenshot_url

    @discord.ui.button(label="✅ Verify", style=discord.ButtonStyle.green)
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        apps = load_apps()
        app_link = apps.get(self.app_name)

        if not app_link:
            await interaction.response.send_message("❌ App link not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="✅ Verification Approved",
            description=f"{self.user.mention}, your verification for **{self.app_name}** has been approved!\n[Click Here]({app_link})",
            color=discord.Color.green()
        )

        await self.ticket_channel.send(embed=embed)

        try:
            await self.user.send(embed=embed)
        except:
            await self.ticket_channel.send("⚠ Cannot DM the user.")

        await interaction.response.send_message("Verified!", ephemeral=True)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ticket_channel.send(
            embed=discord.Embed(
                title="❌ Verification Declined",
                description="Your verification was declined. Please try again.",
                color=discord.Color.red()
            )
        )
        await interaction.response.send_message("Declined!", ephemeral=True)


# =============================
# /ticket — CREATE TICKET
# =============================
@bot.tree.command(name="ticket", description="🎟️ Create a support ticket")
async def ticket(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = datetime.datetime.utcnow()

    # Cooldown check
    if user_id in cooldowns:
        remaining = cooldowns[user_id] - now
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            await interaction.response.send_message(
                f"⏳ You can open another ticket in **{hours} hours**.",
                ephemeral=True
            )
            return

    cooldowns[user_id] = now + datetime.timedelta(hours=48)

    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }

    channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name}",
        overwrites=overwrites
    )

    embed = discord.Embed(
        title="🎫 Welcome!",
        description=(
            "To receive your app:\n"
            "1️⃣ Subscribe to our YouTube channel\n"
            "2️⃣ Take a screenshot\n"
            "3️⃣ Upload screenshot here\n"
            "4️⃣ Type the app name\n\n"
            "An admin will verify you soon."
        ),
        color=discord.Color.blurple()
    )

    await channel.send(interaction.user.mention, embed=embed)
    await interaction.response.send_message(
        f"Ticket created: {channel.mention}", ephemeral=True
    )


# =============================
# /send_app — SEND APP MANUALLY
# =============================
@bot.tree.command(name="send_app", description="📤 Send a premium app link to a user")
@app_commands.checks.has_permissions(manage_guild=True)
async def send_app(interaction: discord.Interaction, user: discord.Member, app_name: str):
    apps = load_apps()

    if app_name not in apps:
        await interaction.response.send_message("❌ App not found.", ephemeral=True)
        return

    link = apps[app_name]

    embed = discord.Embed(
        title="💎 Premium App Delivered",
        description=f"**App:** {app_name}\n[Click Here]({link})",
        color=discord.Color.green()
    )

    try:
        await user.send(embed=embed)
        await interaction.response.send_message("Sent successfully!", ephemeral=True)
    except:
        await interaction.response.send_message("❌ User has DMs off.", ephemeral=True)


# =============================
# /view_tickets — COUNT TICKETS
# =============================
@bot.tree.command(name="view_tickets", description="📊 View number of open tickets")
@app_commands.checks.has_permissions(manage_channels=True)
async def view_tickets(interaction: discord.Interaction):
    open_tickets = [
        c for c in interaction.guild.channels
        if isinstance(c, discord.TextChannel) and c.name.startswith("ticket-")
    ]

    embed = discord.Embed(
        title="🎟️ Ticket Overview",
        description=f"Open Tickets: **{len(open_tickets)}**",
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# =============================
# /force_close — CLOSE TICKET + TRANSCRIPT
# =============================
@bot.tree.command(name="force_close", description="🔒 Force close a ticket")
@app_commands.checks.has_permissions(manage_channels=True)
async def force_close(interaction: discord.Interaction, channel: discord.TextChannel):

    if not channel.name.startswith("ticket-"):
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)

    await interaction.response.send_message(
        f"Closing **{channel.name}**...",
        ephemeral=True
    )

    # ---- Collect Transcript ----
    messages = await channel.history(limit=200).flatten()
    messages.reverse()

    transcript = ""
    for msg in messages:
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
        entry = f"**[{timestamp}] {msg.author.display_name}:** {msg.content}\n"
        if msg.attachments:
            for att in msg.attachments:
                entry += f"📎 {att.url}\n"
        transcript += entry + "\n"

    if len(transcript) > 4000:
        transcript = transcript[:3990] + "\n...(truncated)"

    embed = discord.Embed(
        title=f"📜 Transcript — {channel.name}",
        description=transcript or "No messages found.",
        color=discord.Color.blurple()
    )

    await log_channel.send(embed=embed)

    # ---- Delete Ticket ----
    await channel.delete()


# =============================
# ON MESSAGE — SCREENSHOT + APP DETECTION
# =============================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not message.channel.name.startswith("ticket-"):
        return

    apps = load_apps()
    content_lower = message.content.lower()

    matched_app = None
    for app in apps.keys():
        if app.lower() in content_lower:
            matched_app = app
            break

    if matched_app:
        if message.attachments:
            ver_channel = bot.get_channel(VERIFICATION_CHANNEL_ID)

            embed = discord.Embed(
                title="🧾 Verification Request",
                description=f"{message.author.mention} requested **{matched_app}**.",
                color=discord.Color.yellow()
            )
            embed.set_image(url=message.attachments[0].url)

            await ver_channel.send(
                embed=embed,
                view=VerificationView(message.channel, message.author, matched_app, message.attachments[0].url)
            )

            await message.channel.send("Screenshot received! Awaiting verification.")

        else:
            await message.channel.send(
                f"📸 Please upload your subscription screenshot to get **{matched_app}**."
            )

    await bot.process_commands(message)


# =============================
# ON READY — SYNC COMMANDS
# =============================
@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"🟢 Bot logged in as {bot.user}")


# =============================
# RUN BOT + KEEPALIVE
# =============================
Thread(target=run_flask).start()
bot.run(TOKEN)
