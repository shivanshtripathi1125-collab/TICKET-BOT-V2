import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import os
import datetime
from flask import Flask
from threading import Thread

# ---------------------------
# Environment Variables
# ---------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID"))
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL")

# Verification channel ID (you gave earlier)
VERIFICATION_CHANNEL_ID = 1437035128802246697

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
# Discord Bot Setup
# ---------------------------
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Store cooldowns and apps
cooldowns = {}
apps = {
    "Spotify": "https://example.com/spotify",
    "Castle": "https://example.com/castle",
    "YouTube": "https://example.com/youtube",
    "Hotstar": "https://example.com/hotstar",
    "Truecaller": "https://example.com/truecaller",
    "Kinemaster": "https://example.com/kinemaster",
}

# ---------------------------
# Verification Buttons
# ---------------------------
class VerificationView(View):
    def __init__(self, ticket_channel, user, app_name, screenshot_url):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.user = user
        self.app_name = app_name
        self.screenshot_url = screenshot_url

    @discord.ui.button(label="✅ Verify", style=discord.ButtonStyle.green)
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        app_link = apps.get(self.app_name)
        if not app_link:
            await interaction.response.send_message("❌ App link not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="✅ Verification Approved",
            description=f"{self.user.mention}, your verification for **{self.app_name}** has been approved!\n\nHere’s your link:\n[Click Here]({app_link})",
            color=discord.Color.green()
        )
        await self.ticket_channel.send(embed=embed)

        try:
            await self.user.send(embed=embed)
        except:
            await self.ticket_channel.send(f"⚠️ Couldn't DM {self.user.mention}. Please enable DMs.")

        # Close ticket prompt
        close_view = CloseTicketView()
        await self.ticket_channel.send(embed=discord.Embed(
            description="If you are satisfied with our service, you can close this ticket using the button below 👇",
            color=discord.Color.blurple()
        ), view=close_view)

        await interaction.response.send_message("✅ User verified successfully!", ephemeral=True)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ticket_channel.send(embed=discord.Embed(
            title="❌ Verification Declined",
            description=f"Your verification for **{self.app_name}** has been declined. Please try again after re-checking your requirements.",
            color=discord.Color.red()
        ))
        await interaction.response.send_message("Declined successfully.", ephemeral=True)

# ---------------------------
# Ticket Close Button
# ---------------------------
class CloseTicketView(View):
    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏳ Closing this ticket in 5 seconds...", ephemeral=True)
        await discord.utils.sleep_until(datetime.datetime.utcnow() + datetime.timedelta(seconds=5))

        transcript_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
        transcript_embed = discord.Embed(
            title="📜 Ticket Closed",
            description=f"Ticket closed by {interaction.user.mention}",
            color=discord.Color.blurple()
        )
        await transcript_channel.send(embed=transcript_embed)
        await interaction.channel.delete()

# ---------------------------
# Commands
# ---------------------------
@bot.tree.command(name="ticket", description="🎟️ Create a new support ticket")
async def ticket(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = datetime.datetime.utcnow()

    if user_id in cooldowns:
        remaining = cooldowns[user_id] - now
        if remaining.total_seconds() > 0:
            hours = remaining.total_seconds() // 3600
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⏳ Cooldown Active",
                    description=f"You can open another ticket in **{int(hours)} hours**.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

    # 48-hour cooldown
    cooldowns[user_id] = now + datetime.timedelta(hours=48)

    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }

    ticket_channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)

    app_list = "\n".join([f"💠 {name}" for name in apps.keys()])
    embed = discord.Embed(
        title=f"🎫 Welcome to Rash Tech Support, {interaction.user.name}!",
        description=(
            "Thank you for creating a ticket!\n\n"
            f"Please complete the following steps to get your premium app link:\n"
            f"1️⃣ Subscribe to our [YouTube Channel]({YOUTUBE_CHANNEL_URL})\n"
            "2️⃣ Take a screenshot 📸\n"
            "3️⃣ Upload it here after typing the app name.\n\n"
            f"**Available Apps:**\n{app_list}\n\n"
            "We’ll verify and send your app link soon!"
        ),
        color=discord.Color.blurple()
    )

    await ticket_channel.send(content=interaction.user.mention, embed=embed)
    await interaction.response.send_message(f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

# ---------------------------
# /remove_cooldown
# ---------------------------
@bot.tree.command(name="remove_cooldown", description="🧹 Remove cooldown for a user")
@app_commands.checks.has_permissions(manage_channels=True)
async def remove_cooldown(interaction: discord.Interaction, user: discord.Member):
    if user.id in cooldowns:
        del cooldowns[user.id]
        await interaction.response.send_message(f"✅ Cooldown removed for {user.mention}", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ {user.mention} had no cooldown.", ephemeral=True)

# ---------------------------
# /force_close
# ---------------------------
@bot.tree.command(name="force_close", description="🔒 Force close a ticket channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def force_close(interaction: discord.Interaction, channel: discord.TextChannel):
    transcript_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
    embed = discord.Embed(
        title="🧾 Ticket Force Closed",
        description=f"Ticket {channel.mention} was force-closed by {interaction.user.mention}.",
        color=discord.Color.red()
    )
    await transcript_channel.send(embed=embed)
    await channel.delete()
    await interaction.response.send_message("✅ Ticket closed successfully.", ephemeral=True)

# ---------------------------
# /addapp Command
# ---------------------------
@bot.tree.command(name="addapp", description="➕ Add a new app to the premium list")
@app_commands.checks.has_permissions(manage_guild=True)
async def addapp(interaction: discord.Interaction, name: str, link: str):
    apps[name] = link
    await interaction.response.send_message(embed=discord.Embed(
        title="✅ App Added",
        description=f"Added **{name}** with link: [Click Here]({link})",
        color=discord.Color.green()
    ))

# ---------------------------
# /removeapp Command
# ---------------------------
@bot.tree.command(name="removeapp", description="➖ Remove an app from the list")
@app_commands.checks.has_permissions(manage_guild=True)
async def removeapp(interaction: discord.Interaction, name: str):
    if name in apps:
        del apps[name]
        await interaction.response.send_message(f"✅ Removed **{name}** from the list.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ App **{name}** not found.", ephemeral=True)

# ---------------------------
# /listapps Command
# ---------------------------
@bot.tree.command(name="listapps", description="📜 View all available premium apps")
async def listapps(interaction: discord.Interaction):
    if not apps:
        await interaction.response.send_message(
            embed=discord.Embed(
                title="📭 No Apps Available",
                description="There are currently no premium apps available.",
                color=discord.Color.orange(),
            ),
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="💎 Premium Apps List",
        description="Here are all the premium apps currently available:",
        color=discord.Color.blurple(),
    )
    for name, link in sorted(apps.items()):
        embed.add_field(name=name, value=f"[🔗 Click Here]({link})", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------------------------
# Message Handler
# ---------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if not message.channel.name.startswith("ticket-"):
        return

    content_lower = message.content.lower()
    matched_app = None

    for app_name in apps.keys():
        if app_name.lower() in content_lower:
            matched_app = app_name
            break

    if matched_app:
        if message.attachments:
            ver_channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
            embed = discord.Embed(
                title="🧾 Verification Pending",
                description=f"{message.author.mention} requested verification for **{matched_app}**.\nScreenshot below 👇",
                color=discord.Color.yellow()
            )
            embed.set_image(url=message.attachments[0].url)
            await ver_channel.send(embed=embed, view=VerificationView(message.channel, message.author, matched_app, message.attachments[0].url))
            await message.channel.send(embed=discord.Embed(
                description="✅ Screenshot uploaded successfully!\nPlease wait while an admin verifies it.",
                color=discord.Color.green()
            ))
        else:
            await message.channel.send(embed=discord.Embed(
                description=(
                    f"🪄 To get your **{matched_app}** link, please complete verification first:\n"
                    f"1️⃣ Subscribe to our [YouTube Channel]({YOUTUBE_CHANNEL_URL})\n"
                    f"2️⃣ Take a screenshot of the subscription.\n"
                    f"3️⃣ Upload it here 📸"
                ),
                color=discord.Color.orange()
            ))
    await bot.process_commands(message)

# ---------------------------
# Sync and Run
# ---------------------------
@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Synced slash commands to guild {GUILD_ID}")
    print(f"🤖 Logged in as {bot.user}")

Thread(target=run_flask).start()
bot.run(TOKEN)
